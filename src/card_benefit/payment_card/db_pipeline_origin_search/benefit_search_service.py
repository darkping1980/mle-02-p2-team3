"""혜택 후보 검색. A 문자열·그래프, B 임베딩, C 둘을 합친 하이브리드를 같은 결과 형식으로 돌려준다.

유사도는 후보를 찾는 데만 쓴다. 공통 혜택의 카드 적용 여부는 ``card_common_bnft_apply`` 로만 판단하고,
적용 관계가 없는 공통 혜택은 ``applied=False`` 로 표시한다. 실제 조건 검증은 원본 조건과 원문 근거로 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from time import perf_counter

from card_benefit.payment_card.db_pipeline.benefit_search_text import exclusion_tokens
from card_benefit.payment_card.db_pipeline.common_benefit_service import CommonBenefitService
from card_benefit.payment_card.db_pipeline.embedding_service import EmbeddingRepository, vector_literal

from .neo4j_search import entity_ref

MODES = ("A", "B", "C")
MODE_LABELS = {"A": "기존 검색", "B": "임베딩 검색", "C": "하이브리드"}
FETCH_PER_TABLE = 20
RRF_K = 60                  # Reciprocal Rank Fusion 표준값
PARTICLES = re.compile(r"(이|가|은|는|을|를|의|에|에서|으로|로|도|만|과|와)$")
STOPWORDS = frozenset({"카드", "혜택", "있는", "되는", "좋은", "무엇", "어떤", "있어", "알려줘", "있나요", "서비스가"})


@dataclass
class SearchHit:
    """통합 검색 결과 1건. ``key`` 는 테이블과 복합 PK로 만든 내부 식별자다."""
    source: str             # CARD_BNFT 또는 CARD_COMMON_BNFT
    key: str
    benefit_id: str
    bnft_cd: str
    bnft_nm: str
    bnft_type_cd: str | None
    cards: list[dict]
    applied: bool
    search_txt: str | None = None
    similarity: float | None = None
    keyword_score: int = 0
    origin: str | None = None
    channels: list[str] = field(default_factory=list)
    graph_targets: list[str] = field(default_factory=list)      # Neo4j에서 찾은 적용 대상
    target_terms: list[str] = field(default_factory=list)       # 질문 낱말 중 적용 대상과 맞은 것
    excluded_terms: list[str] = field(default_factory=list)     # 질문 낱말 중 제외 문구에 있는 것


@dataclass
class SearchOutcome:
    mode: str
    hits: list[SearchHit]
    elapsed_ms: float
    merged_duplicates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)            # 실제로 사용한 검색 엔진


def search_terms(question: str) -> list[str]:
    """문자열 검색어를 만든다. 조사만 떼고 동의어를 추정하지 않는다."""
    terms = []
    for word in re.findall(r"[0-9A-Za-z가-힣]+", question):
        word = PARTICLES.sub("", word) if len(word) > 2 else word
        if len(word) >= 2 and word not in STOPWORDS and word not in terms:
            terms.append(word)
    return terms


def card_hit(row: dict) -> SearchHit:
    return SearchHit("CARD_BNFT", f"pg:CARD_BNFT:{row['card_id']}:{row['card_bnft_id']}", row["card_bnft_id"],
                     row["bnft_cd"], row["bnft_nm"], row["bnft_type_cd"],
                     [{"card_id": row["card_id"], "product_nm": row["product_nm"]}], True,
                     row.get("bnft_search_txt"), row.get("similarity"), row.get("keyword_score", 0), row.get("bnft_origin_cd"))


def common_hit(row: dict) -> SearchHit:
    cards = row["apply_cards"]
    return SearchHit("CARD_COMMON_BNFT", f"pg:CARD_COMMON_BNFT:{row['card_common_id']}:{row['card_common_bnft_id']}",
                     row["card_common_bnft_id"], row["bnft_cd"], row["bnft_nm"], row["bnft_type_cd"], cards, bool(cards),
                     row.get("bnft_search_txt"), row.get("similarity"), row.get("keyword_score", 0), "COMMON")


def merge_duplicates(hits: list[SearchHit], confirmed: set[tuple[str, str]]) -> tuple[list[SearchHit], list[str]]:
    """동일성이 확인된 ``(카드 혜택 참조, 공통 혜택 참조)`` 쌍만 합친다. 나머지는 둘 다 결과에 남긴다.

    참조는 ``entity_ref`` 형식(종류:소유자:ID)이다. ID 문자열만 같은 다른 혜택은 합치지 않는다.
    """
    commons = {entity_ref(hit.key) for hit in hits if hit.source == "CARD_COMMON_BNFT"}
    kept, merged = [], []
    for hit in hits:
        if hit.source == "CARD_BNFT" and any(card == entity_ref(hit.key) and common in commons for card, common in confirmed):
            merged.append(hit.key)
        else:
            kept.append(hit)
    return kept, merged


class BenefitSearchService:
    """검색 모드를 실행한다. Neo4j는 없어도 동작하며, 있으면 A 경로의 혜택명 검색에 함께 쓴다."""

    def __init__(self, sql_session, embedder=None, neo4j_search=None):
        self.repository = EmbeddingRepository(sql_session)
        self.common_service = CommonBenefitService(sql_session)
        self.embedder = embedder
        self.neo4j_search = neo4j_search

    def search(self, question: str, mode: str = "C", top_k: int = 5, use_graph: bool = False) -> SearchOutcome:
        if mode not in MODES:
            raise ValueError(f"검색 모드가 아닙니다: {mode}")
        started = perf_counter()
        warnings: list[str] = []
        keyword = self._keyword(question, warnings) if mode in ("A", "C") else []
        vector = self._vector(question) if mode in ("B", "C") else []
        hits = keyword if mode == "A" else vector if mode == "B" else self._fuse(keyword, vector)
        hits, merged = merge_duplicates(hits, self._confirmed_duplicates(hits, warnings))
        engines = [*(["sql"] if mode in ("A", "C") else []), *(["pgvector"] if mode in ("B", "C") else [])]
        if self.neo4j_search is not None and mode in ("A", "C"):
            engines.append("neo4j_name")
        if use_graph and self.neo4j_search is not None:
            hits = self._rank_with_graph(question, hits, warnings)
            engines.append("neo4j_relations")
        unapplied = [hit.bnft_nm for hit in hits[:top_k] if not hit.applied]
        if unapplied:
            warnings.append(f"카드 적용 관계가 없는 공통 혜택: {unapplied}")
        return SearchOutcome(mode, hits[:top_k], (perf_counter() - started) * 1000, merged, warnings, engines)

    def _rank_with_graph(self, question: str, hits: list[SearchHit], warnings: list[str]) -> list[SearchHit]:
        """관계로 후보를 보강한다. 대상이 맞으면 앞으로, 제외 낱말이 맞으면 뒤로 보낸다. 적용 판단은 하지 않는다."""
        terms = [term.casefold() for term in search_terms(question)]
        try:
            relations = self.neo4j_search.candidate_relations([hit.benefit_id for hit in hits])
        except Exception as error:
            warnings.append(f"Neo4j 관계 조회 실패: {type(error).__name__}")
            return hits
        for hit in hits:
            row = relations.get(entity_ref(hit.key))      # ID만 같은 다른 혜택의 대상·제외 문구를 쓰지 않는다.
            if row is None:
                continue
            hit.graph_targets = row["targets"]
            names = [name.casefold() for name in row["targets"]]
            excluded = set().union(*(exclusion_tokens(text) for text in row["exclusions"])) if row["exclusions"] else set()
            hit.target_terms = [term for term in terms if any(term in name for name in names)]
            hit.excluded_terms = [term for term in terms if term in excluded and term not in names]
        return sorted(hits, key=lambda hit: (bool(hit.excluded_terms), not hit.target_terms))

    def _confirmed_duplicates(self, hits: list[SearchHit], warnings: list[str]) -> set[tuple[str, str]]:
        """결과에 기존 BRAND_SERVICE 행과 공통 혜택이 함께 있을 때만 동일성 판정을 읽는다."""
        if not any(hit.origin == "BRAND_SERVICE" for hit in hits) or not any(hit.source == "CARD_COMMON_BNFT" for hit in hits):
            return set()
        confirmed = set()
        for row in self.common_service.compare_brand_benefits():
            if row["status"] == "SAME" and row.get("card_common_id") is not None:
                confirmed.add((f"card_product_item:{row['card_id']}:{row['card_bnft_id']}",
                               f"card_common_bnft:{row['card_common_id']}:{row['card_common_bnft_id']}"))
            elif row["status"] == "SAME":
                warnings.append(f"공통 혜택 소유자를 확인하지 못해 병합하지 않음: {row['card_bnft_id']}")
            else:
                warnings.append(f"동일성 미확정, 병합하지 않음: {row['card_bnft_id']} {row['issues']}")
        return confirmed

    def _keyword(self, question: str, warnings: list[str]) -> list[SearchHit]:
        terms = search_terms(question)
        if not terms:
            return []
        rows = [card_hit(row) for row in self.repository.rows("keyword_card_bnft", TERMS=terms)]
        rows += [common_hit(row) for row in self.repository.rows("keyword_common_bnft", TERMS=terms)]
        scores = {entity_ref(hit.key): hit.keyword_score for hit in rows}      # 카드·공통 혜택 점수를 따로 센다.
        if self.neo4j_search is not None:
            try:
                for term in terms:
                    for row in self.neo4j_search.list_benefits(term):
                        ref = entity_ref(row["key"], row["id"])
                        if ref in scores:
                            scores[ref] += 1
            except Exception as error:      # 그래프 장애가 SQL 결과를 막지 않게 한다.
                warnings.append(f"Neo4j 혜택명 검색 실패: {type(error).__name__}")
        for hit in rows:
            hit.keyword_score = scores[entity_ref(hit.key)]
            hit.channels = ["keyword"]
        return sorted((hit for hit in rows if hit.keyword_score), key=lambda hit: (-hit.keyword_score, hit.bnft_nm))

    def _vector(self, question: str) -> list[SearchHit]:
        if self.embedder is None:
            raise ValueError("임베딩 클라이언트가 없습니다")
        last = self.repository.one("select_last_embedding_run")
        if last and last["run_model_nm"] != self.embedder.model_nm:
            raise ValueError(f"저장된 벡터의 모델({last['run_model_nm']})과 질문 모델({self.embedder.model_nm})이 다릅니다")
        vector = vector_literal(self.embedder.embed([question])[0])
        rows = [card_hit(row) for row in self.repository.rows("search_card_bnft", QUERY_EMBEDDING=vector, TOP_K=FETCH_PER_TABLE)]
        rows += [common_hit(row) for row in self.repository.rows("search_common_bnft", QUERY_EMBEDDING=vector, TOP_K=FETCH_PER_TABLE)]
        for hit in rows:
            hit.channels = ["vector"]
        return sorted(rows, key=lambda hit: -hit.similarity)

    @staticmethod
    def _fuse(keyword: list[SearchHit], vector: list[SearchHit]) -> list[SearchHit]:
        """두 순위를 RRF로 합친다. 유사도와 문자열 점수는 척도가 달라 직접 더하지 않는다."""
        scores: dict[str, float] = {}
        merged: dict[str, SearchHit] = {}
        for ranking in (keyword, vector):
            for rank, hit in enumerate(ranking, 1):
                scores[hit.key] = scores.get(hit.key, 0.0) + 1 / (RRF_K + rank)
                current = merged.setdefault(hit.key, hit)
                if current is not hit:
                    current.similarity = current.similarity if current.similarity is not None else hit.similarity
                    current.keyword_score = max(current.keyword_score, hit.keyword_score)
                    current.channels = [*current.channels, *hit.channels]
        return sorted(merged.values(), key=lambda hit: -scores[hit.key])

    def catalog_rows(self, question: str, mode: str, graph_catalog: list[dict], top_k: int = 8) -> tuple[list[dict], SearchOutcome]:
        """검색 결과를 질문 해석용 혜택 목록으로 바꾼다. 그래프에 있는 혜택은 그래프 상세를 쓴다."""
        graph = {entity_ref(row["key"], row["id"]): row for row in graph_catalog}   # 종류·소유자 포함 참조로 그래프 항목을 찾는다.
        outcome = self.search(question, mode, top_k, use_graph=True)
        rows = []
        for hit in outcome.hits:
            known = graph.get(entity_ref(hit.key))
            target = (hit.search_txt or "").splitlines()
            rows.append(known if known else {
                "key": hit.key, "id": hit.benefit_id, "name": hit.bnft_nm, "status": None,  # 그래프에 없으면 pg: 키로 상세를 읽는다.
                "card": ", ".join(card["product_nm"] for card in hit.cards) or "적용 카드 미확인",
                "targets": [line.split(": ", 1)[1] for line in target if line.startswith(("이용처", "서비스 대상"))],
                "payment_min_amounts": []})
        return rows, outcome

    def get_detail(self, key: str, sections: tuple[str, ...]) -> dict | None:
        """PostgreSQL 혜택 상세를 Neo4j 조회와 같은 구조로 돌려준다."""
        _, table, owner, bnft_id = key.split(":", 3)
        if table == "CARD_BNFT":
            row = self.repository.one("select_card_bnft_detail", CARD_ID=int(owner), BNFT_ID=bnft_id)
            evidence = self.repository.rows("select_card_bnft_evidence", CARD_ID=int(owner), BNFT_ID=bnft_id)
            card_nm = row and row["product_nm"]
        else:
            row = self.repository.one("select_common_bnft_detail", COMMON_ID=int(owner), BNFT_ID=bnft_id)
            evidence = self.repository.rows("select_common_bnft_evidence", COMMON_ID=int(owner), BNFT_ID=bnft_id)
            card_nm = row and (", ".join(row["apply_cards"]) or "적용 카드 미확인")
        if row is None:
            return None
        benefit = {"card_bnft_id": bnft_id, "bnft_nm": row["bnft_nm"], "bnft_type_cd": row["bnft_type_cd"],
                   "verification_status_cd": row.get("verification_status_cd", "PENDING_REVIEW"),
                   "bnft_rule_txt": row.get("bnft_rule_txt")}
        detail = {"context": {"card": {"source_json": json.dumps({"product_nm": card_nm}, ensure_ascii=False)},
                              "benefit": {"name": row["bnft_nm"], "source_json": json.dumps(benefit, ensure_ascii=False)}},
                  "rules": [], "conditions": [], "limits": [], "evidence": []}
        if "rules" in sections:
            detail["rules"] = [{"rule": {"rule_key": rule["rule_key"], "source_json": json.dumps(rule, ensure_ascii=False)},
                                "targets": [t["target_nm"] for t in rule.get("target_list") or []]}
                               for rule in row.get("rule_list") or [] if rule.get("rule_status_cd") != "RETIRED"]
        if "conditions" in sections:
            detail["conditions"] = self._conditions(row)
        if "limits" in sections and row.get("bnft_limit_txt"):
            detail["limits"] = [{"limit_text": row["bnft_limit_txt"]}]
        if "evidence" in sections:
            detail["evidence"] = [
                {"link": {"ev_subject_cd": item["ev_subject_cd"], "ev_item_key": item["ev_item_key"]},
                 "rule_key": item["rule_key"],
                 "evidence": {"source_json": json.dumps({key: item[key] for key in ("evidence_id", "page_no", "quote_txt", "approval_status_cd")},
                                                        ensure_ascii=False)}}
                for item in evidence]
        return detail

    @staticmethod
    def _conditions(row: dict) -> list[dict]:
        owners = [("CARD", None, row.get("card_cond_expr")), ("BNFT", None, row.get("bnft_cond_expr"))]
        owners += [("RULE", rule["rule_key"], rule.get("cond_expr")) for rule in row.get("rule_list") or []]
        conditions = []
        for owner_cd, rule_key, expression in owners:
            for branch in (expression or {}).get("branches", []):
                for atom in branch["atoms"]:
                    conditions.append({"owner_cd": owner_cd, "rule_key": rule_key, "branch_no": branch["branch_no"],
                                       "expression": {"key": f"{owner_cd}:{rule_key}"},
                                       "atom": {"key_name": atom["atom_key"], "source_json": json.dumps(atom, ensure_ascii=False)}})
        return conditions
