"""항목(entry) 목록에서 documents / product_docs 행을 만든다. 카드사 이름을 알지 못한다.

흐름: group_by_path -> measure_files -> apply_card_type_overrides -> pick_canonical
      -> drop_superseded_web_captures -> build_product_docs / finish_documents
build_index가 이 함수들을 순서대로 부르기만 한다. (apply_review_decisions는 사람이 확인한 결과를 반영한다.)

docs는 {원본 경로: 문서 한 줄(dict)}이다. 문서 한 줄에 넣지 않는 임시 값(상품 이름들, 검토 사유)은
extra라는 따로 만든 dict에 둔다. extra의 키는 문서 한 줄의 file_path 값이다.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import ORIGIN_RANK, OCR_MIN_CHARS_PER_PAGE


def _folder_card_type(rel_path: str) -> str:
    folder = rel_path.split("/", 1)[0]
    return folder if folder in ("credit", "debit", "common") else "unknown"


def _rank_key(doc: dict) -> tuple:
    """대표 선정 순서: 출처 신뢰도, 게시일이 최신, 파일명이 짧음, 경로 순."""
    board = int(doc["board_date"]) if doc["board_date"].isdigit() else 0
    name = doc["file_path"].rsplit("/", 1)[-1]
    return (ORIGIN_RANK[doc["origin"]], -board, len(name), doc["file_path"])


def group_by_path(entries: list[dict]) -> dict[str, list[dict]]:
    """같은 파일을 가리키는 항목을 묶는다. 상품 여러 개가 한 파일을 쓸 수 있기 때문이다."""
    by_path: dict[str, list[dict]] = {}
    for entry in entries:
        by_path.setdefault(entry["file_path"], []).append(entry)
    return by_path


def _collect_reasons(group: list[dict], info: dict) -> list[str]:
    reasons = []
    for entry in group:
        reasons.extend(entry.get("review_reasons", []))
    if info.get("error"):
        reasons.append(info["error"])
    manifest_sha = {e["manifest_sha256"] for e in group if e.get("manifest_sha256")}
    if manifest_sha and info["sha256"] not in manifest_sha:
        reasons.append("manifest 해시와 파일 해시가 다름")
    return list(dict.fromkeys(reasons))


def measure_files(issuer: str, issuer_root: Path, by_path: dict, measure) -> tuple[dict, dict, list]:
    """파일을 열어 해시·쪽수·글자 수를 재고 문서 한 줄씩 만든다. 없는 파일은 missing에 모은다."""
    docs, extra, missing = {}, {}, []
    for path, group in by_path.items():
        info = measure(issuer_root / path)
        if not info.get("exists"):
            missing.append(path)
            continue
        first = group[0]
        pages, chars = info.get("pages"), info.get("text_chars")
        # 쪽당 글자가 너무 적으면 이미지 PDF로 보고 OCR이 필요하다고 표시한다.
        ocr = bool(pages) and chars is not None and chars / pages < OCR_MIN_CHARS_PER_PAGE
        doc = {
            "issuer": issuer,
            "doc_id": info["sha256"][:16],
            "sha256": info["sha256"],
            "file_path": f"{issuer}_all/{path}",
            "card_type": _folder_card_type(path),
            "doc_role": first["doc_role"],
            "canonical": "N",
            "duplicate_of": "",
            "pages": "" if pages is None else pages,
            "text_chars": "" if chars is None else chars,
            "ocr_needed": "Y" if ocr else "N",
            "source_url": first.get("source_url", ""),
            "origin": first["origin"],
            "board_date": first.get("board_date", ""),
        }
        docs[path] = doc
        extra[doc["file_path"]] = {
            "products": {e["product_name"] for e in group},
            "reasons": _collect_reasons(group, info),
        }
    return docs, extra, missing


def apply_card_type_overrides(docs: dict, extra: dict, overrides: dict) -> None:
    """사람이 확인한 카드 구분을 반영한다. 문서의 상품이 모두 목록에 있을 때만 적용한다."""
    for doc in docs.values():
        item = extra[doc["file_path"]]
        types = {overrides.get(name) for name in item["products"]}
        if len(types) == 1 and None not in types:
            doc["card_type"] = types.pop()
            item["reasons"] = [r for r in item["reasons"] if not r.startswith("카드 구분 확인 필요")]


NAME_CHECK_REASON = "PDF 내 상품명 자동 확인 실패"


def apply_review_decisions(docs: dict, extra: dict, decisions: dict) -> None:
    """확인 결과({doc_id: 결정})를 반영한다.

    name_ok이면 상품명 자동 확인 실패 사유를 지우고, content_image이면 혜택 내용이 그림이라는 뜻이므로
    OCR 필요(Y)로 바꾼다. 같은 내용(doc_id)의 파일에는 모두 적용된다.
    """
    for doc in docs.values():
        decision = decisions.get(doc["doc_id"])
        if decision is None:
            continue
        if decision["name_ok"]:
            item = extra[doc["file_path"]]
            item["reasons"] = [r for r in item["reasons"] if not r.startswith(NAME_CHECK_REASON)]
        if decision["content_image"]:
            doc["ocr_needed"] = "Y"


def pick_canonical(docs: dict) -> dict[str, list[dict]]:
    """같은 해시(내용이 같은) 파일끼리 대표 1개를 고르고, 나머지는 대표 경로를 duplicate_of에 적는다.

    해시별 묶음을 돌려준다. 뒤 단계(연결 표, 요약)에서 다시 쓴다.
    """
    groups: dict[str, list[dict]] = {}
    for doc in docs.values():
        groups.setdefault(doc["sha256"], []).append(doc)
    for members in groups.values():
        members.sort(key=_rank_key)
        winner = members[0]
        winner["canonical"] = "Y"
        for other in members[1:]:
            other["duplicate_of"] = winner["file_path"]
    return groups


def drop_superseded_web_captures(docs: dict, extra: dict) -> None:
    """공식 상품설명서가 있는 카드의 웹 변환본은 대표에서 뺀다. 변환본뿐이면 검토 대상으로 남긴다."""
    official_products = set()
    for doc in docs.values():
        if doc["doc_role"] == "product_guide":
            official_products |= extra[doc["file_path"]]["products"]
    for doc in docs.values():
        if doc["doc_role"] != "web_capture" or doc["canonical"] != "Y":
            continue
        item = extra[doc["file_path"]]
        if item["products"] <= official_products:
            doc["canonical"] = "N"
        else:
            item["reasons"].append("공식 상품설명서 없이 웹 변환본만 존재")


def _relation(role: str, shared: bool) -> str:
    if role in ("product_guide", "web_capture"):
        return "shared_guide" if shared else "primary_guide"
    if role == "brand_service":
        return "brand"
    if role == "terms":
        return "terms"
    return role


def build_product_docs(issuer: str, entries: list[dict], docs: dict, groups: dict, extra: dict) -> list[dict]:
    """상품과 문서의 연결 행을 만든다.

    같은 내용(해시)을 상품 둘 이상이 쓰면 shared_guide다. 공유 문서는 경로가 달라도 해시가 같은 파일로 들어온다.
    """
    products_by_sha = {}
    for sha, members in groups.items():
        names = set()
        for member in members:
            names |= extra[member["file_path"]]["products"]
        products_by_sha[sha] = names

    links, seen = [], set()
    for entry in entries:
        doc = docs.get(entry["file_path"])
        key = (entry["product_name"], entry["file_path"])
        if doc is None or key in seen:
            continue
        seen.add(key)
        shared = len(products_by_sha[doc["sha256"]]) > 1
        links.append({
            "issuer": issuer,
            "product_name": entry["product_name"],
            "product_ids": json.dumps(entry.get("product_ids", {}), ensure_ascii=False, sort_keys=True),
            "card_type": doc["card_type"],
            "doc_id": doc["doc_id"],
            "file_path": doc["file_path"],
            "relation": _relation(doc["doc_role"], shared),
        })
    return links


def finish_documents(docs: dict, extra: dict) -> list[dict]:
    """검토 사유를 합쳐 needs_review, review_reason을 채운 최종 행을 만든다."""
    documents = []
    for doc in sorted(docs.values(), key=lambda d: d["file_path"]):
        reasons = extra[doc["file_path"]]["reasons"]
        if doc["doc_role"] == "unclassified":
            reasons.append("문서 종류를 규칙으로 판정하지 못함")
        reasons = list(dict.fromkeys(reasons))
        row = dict(doc)
        row["needs_review"] = "Y" if reasons else "N"
        row["review_reason"] = "; ".join(reasons)
        documents.append(row)
    return documents


def _bad_canonical_groups(groups: dict) -> list[str]:
    """대표가 둘 이상이거나, 웹 변환본만의 묶음이 아닌데 대표가 없는 해시 묶음을 찾는다."""
    bad = []
    for sha, members in groups.items():
        count = sum(d["canonical"] == "Y" for d in members)
        only_web = all(d["doc_role"] == "web_capture" for d in members)
        if count > 1 or (count == 0 and not only_web):
            bad.append(sha)
    return bad


def make_summary(entries: list[dict], documents: list[dict], groups: dict, missing: list) -> dict:
    return {
        "entries": len(entries),
        "files": len(documents),
        "missing_files": missing,
        "ocr_needed": sum(d["ocr_needed"] == "Y" for d in documents),
        "needs_review": sum(d["needs_review"] == "Y" for d in documents),
        "unclassified": sum(d["doc_role"] == "unclassified" for d in documents),
        "duplicate_groups": sum(1 for m in groups.values() if len(m) > 1),
        "bad_canonical_groups": _bad_canonical_groups(groups),
    }


def build_index(
    issuer: str, issuer_root: Path, entries: list[dict], measure,
    card_type_overrides: dict | None = None, review_decisions: dict | None = None,
) -> tuple[list[dict], list[dict], dict]:
    """entries는 어댑터가 만든 항목이고, measure는 measure_pdf와 같은 모양의 함수다.

    card_type_overrides는 사람이 확인한 {상품명: 카드 구분}, review_decisions는 {doc_id: 확인 결과}이다.
    반환: (documents 행, product_docs 행, 점검 요약)
    """
    by_path = group_by_path(entries)
    docs, extra, missing = measure_files(issuer, issuer_root, by_path, measure)
    apply_card_type_overrides(docs, extra, card_type_overrides or {})
    apply_review_decisions(docs, extra, review_decisions or {})
    groups = pick_canonical(docs)
    drop_superseded_web_captures(docs, extra)
    product_docs = build_product_docs(issuer, entries, docs, groups, extra)
    documents = finish_documents(docs, extra)
    return documents, product_docs, make_summary(entries, documents, groups, missing)
