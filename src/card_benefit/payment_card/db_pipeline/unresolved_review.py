"""Human-reviewed links from page-level unresolved extraction output.

The registry is append-only curation data, separate from card_ai_call and
card_extr_stg. Only APPROVED links can contribute LIMIT evidence at registration.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .extraction_service import compact


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "review" / "unresolved_links.json"
APPROVED = "APPROVED"
PENDING = "PENDING_REVIEW"


def load_registry(path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("reviews"), list):
        raise ValueError("unresolved review registry version/shape is invalid")
    for review in data["reviews"]:
        if review.get("review_status") not in (APPROVED, PENDING, "REJECTED"):
            raise ValueError(f"invalid review status: {review.get('review_status')}")
        if not review.get("run_id") or not review.get("card_doc_id") or not review.get("review_id"):
            raise ValueError("review_id, run_id and card_doc_id are required")
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
