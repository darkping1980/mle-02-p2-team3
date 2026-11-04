"""검색 계층 비교와 최종 답변 평가. 실제 DB 읽기와 임베딩·LLM 호출만 하고 DB를 변경하지 않는다.

실행(src/card_benefit 폴더): uv run python -m payment_card.db_pipeline_origin_search.search_eval --out 결과.json
정답은 등록 데이터 기준이다. 정답 혜택이 아직 등록되지 않은 질문은 정답률에서 분리한다.

두 가지 평가 (main)
    기본       evaluate: CASES 질문마다 BenefitSearchService.search를 4개 계층(LAYERS)으로 실행해 순위를 잰다.
               SQL(A) / PGVECTOR(B) / HYBRID(C) / HYBRID_NEO4J(C + Neo4j 관계 보정). LLM은 부르지 않지만
               B·C 계층은 질문 임베딩(유료)을 호출한다. 지표: top1/top3/top5, MRR, 제외 대상 노출 수 등.
    --answers  evaluate_answers: CardGraphRAG(C 모드)로 REQUIRED_QUESTIONS·CASES를 끝까지 실행(질문 해석·답변 LLM 유료 호출)
               하고 score_answer로 판정한다.
Streamlit 화면과 독립된 오프라인 평가 스크립트이며, 결과는 --out JSON 파일에만 쓴다.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from time import perf_counter

from card_benefit.payment_card.db_pipeline.document_repository import MAPPER_ROOT
from card_benefit.payment_card.db_pipeline.embedding_service import EMBEDDING_LOG_KEYS, OpenAIEmbedder
from common.postgres_db_session import PostgresDbSession
from common.query_log_config import load_project_environment
from common.query_logger import DEFAULT_SENSITIVE_KEYS

from .benefit_search_service import BenefitSearchService
from .card_graphrag import CardGraphRAG, create_llms
from .neo4j_search import connect

ONE_PICK = "ONE PICK 편의점·카페 캐시백"
STYLE = "STYLE 쇼핑·서점/문구·패션 캐시백"
TRANSIT = "ONE MORE 대중교통 캐시백"
PARK = "ONE MORE 놀이공원 현장할인"
CONCIERGE = "Visa 컨시어지"


@dataclass(frozen=True)
class Case:
    question: str
    expected: tuple[str, ...] = ()      # 하나라도 찾으면 정답
    forbidden: tuple[str, ...] = ()     # 질문이 제외 대상을 묻는 경우 상위에 나오면 안 되는 혜택
    verifiable: bool = True             # 정답 혜택이 등록돼 있는지


CASES = (
    Case("편의점 캐시백 되는 카드", (ONE_PICK,)),
    Case("GS25 혜택이 있는 카드", (ONE_PICK,)),
    Case("커피 할인되는 카드", (ONE_PICK,)),
    Case("카페에서 캐시백 받을 수 있어?", (ONE_PICK,)),
    Case("메가커피 자주 가는데 쓸만한 카드", (ONE_PICK,)),
    Case("올리브영 혜택", (STYLE,)),
    Case("서점에서 혜택 받는 카드", (STYLE,)),
    Case("온라인 패션 쇼핑 캐시백", (STYLE,)),
    Case("다이소 캐시백", (STYLE,)),
    Case("놀이공원 할인 혜택", (PARK,)),
    Case("에버랜드 현장할인 카드", (PARK,)),
    Case("롯데월드 반값으로 가는 방법", (PARK,)),
    Case("대중교통 캐시백", (TRANSIT,)),
    Case("지하철 혜택 있는 카드", (TRANSIT,)),
    Case("버스 타면 돈 돌려주는 카드", (TRANSIT,)),
    Case("Visa Signature 컨시어지 서비스", (CONCIERGE,)),
    Case("컨시어지 서비스가 있는 카드", (CONCIERGE,)),
    Case("JADE Classic 공통서비스", (CONCIERGE,)),
    Case("ONE PICK STYLE 카드 혜택", (ONE_PICK, STYLE, TRANSIT, PARK)),
    Case("고속버스 캐시백 되는 카드", forbidden=(TRANSIT,)),
    Case("시외버스 혜택", forbidden=(TRANSIT,)),
    Case("KTX 할인 카드", forbidden=(TRANSIT,)),
    Case("SRT 탈 때 캐시백", forbidden=(TRANSIT,)),
    Case("공항 관련 서비스가 있는 카드", verifiable=False),
    Case("해외여행 혜택이 좋은 카드", verifiable=False),
    Case("호텔 발렛파킹 무료 카드", verifiable=False),
    Case("연회비 면제되는 카드", verifiable=False),
)


REQUIRED_QUESTIONS = (
    Case("ONE PICK STYLE 카드 혜택 알려줘", (ONE_PICK, STYLE, TRANSIT, PARK)),
    Case("GS25에서 캐시백 되는 카드 추천해 줘", (ONE_PICK,)),
    Case("커피 할인되는 체크카드 있어?", (ONE_PICK,)),
    Case("에버랜드 현장할인 되는 카드 알려줘", (PARK,)),
    Case("대중교통 캐시백 혜택 알려줘", (TRANSIT,)),
    Case("고속버스 캐시백 받을 수 있어?", forbidden=(TRANSIT,)),
    Case("KTX도 대중교통 캐시백 돼?", forbidden=(TRANSIT,)),
    Case("Visa Signature 컨시어지 서비스 알려줘", (CONCIERGE,)),
    Case("이 혜택의 전월 실적 조건은?"),
    Case("이 혜택의 공식 PDF 근거는 어디야?"),
    Case("ONE MORE 대중교통 캐시백의 전월 실적 조건은?", (TRANSIT,)),
    Case("ONE MORE 놀이공원 현장할인의 공식 PDF 근거는 어디야?", (PARK,)),
)
LAYERS = (("SQL", "A", False, False), ("PGVECTOR", "B", False, False), ("HYBRID", "C", False, False), ("HYBRID_NEO4J", "C", True, True))


def rank_of(names: list[str], targets: tuple[str, ...]) -> int | None:
    """결과 혜택명 목록에서 targets 중 하나가 처음 나오는 순위(1부터). 없으면 None."""
    return next((rank for rank, name in enumerate(names, 1) if name in targets), None)


def evaluate(sql_only: BenefitSearchService, with_graph: BenefitSearchService, top_k: int = 5) -> dict:
    """SQL, pgvector, SQL+pgvector, 여기에 Neo4j 관계를 더한 결과를 분리해 잰다."""
    rows = []
    for case in CASES:
        for layer, mode, graph, use_graph in LAYERS:
            outcome = (with_graph if graph else sql_only).search(case.question, mode, top_k, use_graph=use_graph)
            names = [hit.bnft_nm for hit in outcome.hits]
            rows.append({"question": case.question, "mode": layer, "engines": outcome.engines, "verifiable": case.verifiable,
                         "expected": list(case.expected), "forbidden": list(case.forbidden), "results": names,
                         "scores": [round(hit.similarity, 3) if hit.similarity is not None else None for hit in outcome.hits],
                         "expected_rank": rank_of(names, case.expected), "forbidden_rank": rank_of(names, case.forbidden),
                         "excluded_flagged": sorted({term for hit in outcome.hits if hit.bnft_nm in case.forbidden for term in hit.excluded_terms}),
                         "target_matched": [hit.bnft_nm for hit in outcome.hits if hit.target_terms],
                         "merged_duplicates": len(outcome.merged_duplicates),
                         "duplicate_names": len(names) - len(set(names)), "unapplied": outcome.warnings,
                         "elapsed_ms": round(outcome.elapsed_ms, 1)})
    return {"rows": rows, "summary": summarize(rows)}


def summarize(rows: list[dict]) -> dict:
    """계층(mode)별로 정답 순위 지표(top1/top3/top5/MRR)와 제외 대상 노출·병합·응답 시간을 집계한다."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["mode"]].append(row)
    summary = {}
    for mode, items in grouped.items():
        scored = [row for row in items if row["expected"]]
        guarded = [row for row in items if row["forbidden"]]
        ranks = [row["expected_rank"] for row in scored]
        count = len(scored)
        summary[mode] = {
            "engines": items[0]["engines"],
            "scored_questions": count,
            "top1": sum(rank == 1 for rank in ranks) / count,
            "top3": sum(rank is not None and rank <= 3 for rank in ranks) / count,
            "top5": sum(rank is not None for rank in ranks) / count,
            "mrr": sum(1 / rank for rank in ranks if rank) / count,
            "exclusion_questions": len(guarded),
            "exclusion_top1": sum(row["forbidden_rank"] == 1 for row in guarded),
            "exclusion_top5": sum(row["forbidden_rank"] is not None for row in guarded),
            "exclusion_flagged": sum(bool(row["excluded_flagged"]) for row in guarded),
            "merged_duplicates": sum(row["merged_duplicates"] for row in items),
            "duplicate_results": sum(row["duplicate_names"] for row in items),
            "avg_ms": sum(row["elapsed_ms"] for row in items) / len(items),
            "unverifiable_questions": sum(not row["verifiable"] for row in items),
        }
    return summary


def score_answer(case: Case, state: dict) -> str:
    """최종 답변 판정. 등록 데이터의 혜택이 선택됐는지와 제외 대상을 적용으로 답하지 않았는지 본다."""
    chosen = set((state.get("search_parameters") or {}).get("benefit_names") or [])
    answered = state["answer"]["status"] in ("ANSWERED", "PARTIAL")
    if not case.verifiable:
        return "UNVERIFIABLE_ANSWERED" if answered else "UNVERIFIABLE_DECLINED"
    if case.forbidden:
        if state.get("exclusions"):
            return "CORRECT_EXCLUDED"
        return "WRONG_FORBIDDEN_ANSWER" if answered and chosen & set(case.forbidden) else "CORRECT_NOT_RECOMMENDED"
    if not case.expected:
        return "NO_REFERENT_ANSWERED" if answered else "NO_REFERENT_DECLINED"
    return "CORRECT" if answered and chosen & set(case.expected) else "WRONG"


def evaluate_answers(pipeline, cases: tuple[Case, ...]) -> list[dict]:
    """실제 LLM까지 실행해 최종 답변을 기록한다."""
    rows = []
    for case in cases:
        started = perf_counter()
        state = pipeline.run(case.question)
        answer = state["answer"]
        rows.append({"question": case.question, "mode": pipeline.search_mode, "score": score_answer(case, state), "path": state["path"],
                     "error": state.get("error"), "candidates": state.get("candidate_search"), "chosen": (state.get("search_parameters") or {}).get("benefit_names"),
                     "trace": state.get("retrieval_trace"), "exclusions": state.get("exclusions"), "status": answer["status"],
                     "conclusion": answer["conclusion"], "points": [point["text"] for point in answer["points"]], "message": answer["message"],
                     "evidence": [{"id": item["evidence_id"], "page": item["page_no"]} for item in state.get("evidence") or []],
                     "uncertain": answer["uncertain"], "unresolved": state.get("unresolved"), "warnings": state.get("warnings"),
                     "cost_usd": sum(call["cost_usd"] or 0 for call in state["llm_calls"]), "elapsed_ms": round((perf_counter() - started) * 1000, 1)})
    return rows


def main(argv: list[str] | None = None) -> int:
    """평가를 실행하고 결과 JSON을 --out에 저장, 요약을 표준출력에 쓴다. DB에는 쓰지 않는다."""
    parser = argparse.ArgumentParser(prog="search_eval", description="검색 모드 비교")
    parser.add_argument("--out", required=True, help="결과 JSON 경로")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--answers", action="store_true", help="실제 LLM으로 최종 답변까지 평가한다. 유료 호출")
    args = parser.parse_args(argv)
    load_project_environment()
    session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none",
                                sensitive_log_keys=(*DEFAULT_SENSITIVE_KEYS, *EMBEDDING_LOG_KEYS))
    graph = connect()
    embedder = OpenAIEmbedder()
    try:
        with_graph = BenefitSearchService(session, embedder, graph)
        if args.answers:
            pipeline = CardGraphRAG(graph, *create_llms(), benefit_search=with_graph, search_mode="C")
            result = {"required": evaluate_answers(pipeline, REQUIRED_QUESTIONS), "cases": evaluate_answers(pipeline, CASES)}
            scores = {name: dict(Counter(row["score"] for row in result[name])) for name in result}
            result["scores"] = scores
            summary = scores
        else:
            result = evaluate(BenefitSearchService(session, embedder), with_graph, args.top_k)
            summary = result["summary"]
    finally:
        graph.driver.close()
        session.database_manager.close()
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
