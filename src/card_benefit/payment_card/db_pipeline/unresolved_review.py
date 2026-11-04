"""Human-reviewed links from page-level unresolved extraction output.

The registry is append-only curation data, separate from card_ai_call and
card_extr_stg. Only APPROVED links can contribute LIMIT evidence at registration.

[한국어 요약] LLM 응답의 ``unresolved`` (판단 보류 문구)에 대해 사람이 내린 검토 결과를 JSON 파일
(``data/review/unresolved_links.json``)에서 읽어 등록 후보에 붙이는 모듈이다. DB에 쓰지 않는다.

사용 위치 (3단계 등록)
    CommonBenefitRepository.attach_normalized → load_registry / verified_reviews_for_run / links_for_candidate
    ProductBenefitService._register → 검토 상태로 등록 차단 여부 판단
    ProductBenefitService._materialize_reviewed_evidence → validate_review_sources(인용 위치 재확인)

등록에 미치는 효과 (ProductBenefitService 기준. CommonBenefitService는 검토 연결을 붙이기만 하고 판정에 쓰지 않는다)
    APPROVED                             : 검토 근거를 LIMIT 근거로 추가하고 등록 진행
    PENDING_REVIEW + PENDING_SCOPE_NOTE   : 등록은 진행, 미해결 범위 메모를 한도 TEXT에 남김
    그 밖(PENDING_REVIEW + BLOCK, REJECTED): 연결된 혜택을 REVIEW로 두고 등록하지 않음
검토 기록이 가리키는 unresolved 항목이 현재 응답에 모두 남아 있지 않으면 APPROVED도 PENDING_REVIEW로 낮춘다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .extraction_service import compact


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "review" / "unresolved_links.json"
APPROVED = "APPROVED"
PENDING = "PENDING_REVIEW"
BLOCK_REGISTRATION = "BLOCK"
PENDING_SCOPE_NOTE = "PENDING_SCOPE_NOTE"


def load_registry(path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    """검토 기록 JSON을 읽고 형식(version=1, 상태값, 필수 키, 승인 근거)을 검증해 reviews 목록을 반환한다.

    Raises:
        ValueError: 형식이 맞지 않는 경우. 파일이 없으면 FileNotFoundError가 그대로 전파된다.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("reviews"), list):
        raise ValueError("unresolved review registry version/shape is invalid")
    for review in data["reviews"]:
        if review.get("review_status") not in (APPROVED, PENDING, "REJECTED"):
            raise ValueError(f"invalid review status: {review.get('review_status')}")
        if not review.get("run_id") or not review.get("card_doc_id") or not review.get("review_id"):
            raise ValueError("review_id, run_id and card_doc_id are required")
        effect = review.get("registration_effect", BLOCK_REGISTRATION)
        if effect not in (BLOCK_REGISTRATION, PENDING_SCOPE_NOTE):
            raise ValueError(f"invalid review registration_effect: {effect}")
        if effect == PENDING_SCOPE_NOTE and review["review_status"] != PENDING:
            raise ValueError("non-blocking scope notes must remain PENDING_REVIEW")
        for target in review.get("targets", []):
            if not target.get("benefit_nm"):
                raise ValueError("review target benefit_nm is required")
            if review["review_status"] == APPROVED and not target.get("evidence"):
                raise ValueError("approved review targets require located source evidence")
    return data["reviews"]


def unresolved_queue(rows: list[dict], reviews: list[dict] | None = None) -> list[dict]:
    """Join the immutable call-response unresolved array to separate review records."""
    reviews = reviews if reviews is not None else load_registry()
    verified = []
    for run_id in {row["card_ai_run_id"] for row in rows}:
        verified.extend(verified_reviews_for_run(run_id, rows, reviews))
    reviews = verified
    result = []
    for row in rows:
        source = (row["card_ai_run_id"], row["card_doc_id"], row["page_no"],
                  row["card_doc_chunk_id"], row["unresolved_ordinal"], row["raw_txt"])
        matched = []
        for review in reviews:
            for ref in review.get("unresolved_refs", []):
                key = (review["run_id"], review["card_doc_id"], ref["page_no"],
                       ref["card_doc_chunk_id"], ref["ordinal"], ref["raw_txt"])
                if key == source:
                    matched.append((review, ref))
        status = matched[0][0]["review_status"] if matched else PENDING
        targets = [name for review, ref in matched
                   for name in ref.get("target_benefit_nms", [target["benefit_nm"] for target in review.get("targets", [])])]
        result.append({**row, "review_status": status, "review_ids": [r[0]["review_id"] for r in matched],
                       "registration_effects": list(dict.fromkeys(
                           r[0].get("registration_effect", BLOCK_REGISTRATION) for r in matched)),
                       "target_benefit_nms": list(dict.fromkeys(targets))})
    return result


def verified_reviews_for_run(run_id: str, rows: list[dict], reviews: list[dict]) -> list[dict]:
    """Downgrade stale/partial approvals to pending unless every unresolved reference still matches."""
    present = {(row["card_ai_run_id"], row["card_doc_id"], row["page_no"],
                row["card_doc_chunk_id"], row["unresolved_ordinal"], row["raw_txt"]) for row in rows}
    output = []
    for review in reviews:
        if review["run_id"] != run_id:
            continue
        matches_all = bool(review.get("unresolved_refs")) and all(
            (run_id, review["card_doc_id"], ref["page_no"], ref["card_doc_chunk_id"],
             ref["ordinal"], ref["raw_txt"]) in present
            for ref in review["unresolved_refs"])
        output.append({**review, "review_status": review["review_status"] if matches_all else PENDING})
    return output


def links_for_candidate(run_id: str, card_doc_id: str, benefit_nm: str,
                        reviews: list[dict] | None = None) -> list[dict]:
    """Return only exact document/run/name matches; unresolved entries are never auto-promoted."""
    reviews = reviews if reviews is not None else load_registry()
    links = []
    for review in reviews:
        if (review["run_id"], review["card_doc_id"]) != (run_id, card_doc_id):
            continue
        for target in review.get("targets", []):
            if target["benefit_nm"] == benefit_nm:
                links.append({**target, "review_id": review["review_id"],
                              "review_status": review["review_status"],
                          "registration_effect": review.get("registration_effect", BLOCK_REGISTRATION),
                              "review_note": review.get("review_note", "")})
    return links


def validate_review_sources(link: dict, card_doc_id: str, source_texts: dict[tuple[str, int, str], str]) -> list[dict]:
    """Require exact quote presence in the cited document chunk before creating evidence."""
    if link["review_status"] != APPROVED:
        raise ValueError("unresolved link is not approved")
    located = []
    for source in link.get("evidence", []):
        if source["card_doc_id"] != card_doc_id:
            raise ValueError("review evidence document does not match benefit document")
        key = (source["card_doc_id"], source["page_no"], source["card_doc_chunk_id"])
        text = source_texts.get(key)
        if text is None:
            raise ValueError("review evidence chunk was not found")
        quote = source["quote_txt"]
        compact_text, compact_quote = compact(text), compact(quote)
        start = compact_text.find(compact_quote)
        if start < 0:
            raise ValueError("review evidence quote is not present in source chunk")
        # Reuse the exact position locator so persisted positions point into the original chunk.
        from .extraction_service import locate_quote
        span = locate_quote(text, quote)
        if span is None:
            raise ValueError("review evidence quote location could not be resolved")
        located.append({**source, "start_pos": span[0], "end_pos": span[1], "source_txt": quote})
    if not located:
        raise ValueError("approved review link has no evidence")
    return located
