"""상품설명서의 할인 제공 유의사항·제외 목록을 card_product_item(TERMS)으로 등록한다.

[등록 파이프라인에서의 위치] 혜택 등록(3단계) 뒤의 보완 단계. LLM을 호출하지 않는다.
입력은 사람이 검토한 TERMS SEED(docs/identity_registry/terms/*.json)다. SEED의 원문은 DB의 페이지 원문에서 잘라 낸
문자열 그대로이며, 이 프로그램은 그 원문이 실제 청크 원문 위치에 있는지 다시 확인한 뒤에만 등록한다.

원칙
    - 원문을 고치지 않는다. source(본문 1구간), entries(목록 항목), footnotes(각주)는 각각 자기 위치를 가진다.
      서로 떨어진 구간(예: 할인 제외 목록과 공공요금 각주)을 한 문자열로 합치지 않는다.
    - 위치가 하나로 정해지지 않거나 원문이 다르면 등록하지 않는다(REVIEW).
    - 기존 행은 UPDATE·DELETE하지 않는다. 같은 item_cd가 있으면 내용이 같을 때 UNCHANGED, 다르면 CHANGE_REVIEW로 멈춘다.
    - 항목 유형값(item_type_cd)의 허용 여부는 검사하지 않는다. 원문·구조·근거·적용 범위만 검사한다.

처리 순서(카드 SEED마다, 전체를 한 트랜잭션으로)
    1. 카드·상품설명서 연결(card_product_doc) 확인, 페이지별 청크 원문 조회
    2. TERMS마다 source·footnotes·entries 위치 확정 → 위치 문자열 = 원문 확인
    3. 적용 범위 확인: NAMED_ITEMS는 같은 카드의 BENEFIT 항목만 허용
    4. item_cd = TERMS@{card_doc_id}@{terms_kind_cd}@{원문 해시 12자}. 이미 있으면 비교만 한다
    5. 근거: 같은 위치·같은 인용의 card_source_evidence가 있으면 재사용, 없으면 PENDING으로 추가
    6. card_product_item INSERT(item_type_cd='TERMS') → card_evidence_link INSERT(ev_subject_cd='ITEM', SELF)
    7. 등록 직후 같은 트랜잭션에서 위치·근거·범위를 다시 검증하고, 정합성 게이트 신규 위반이 있으면 전체 ROLLBACK

실행 예(저장소 루트에서):
    uv run python -m payment_card.db_pipeline.terms_register --seed src/card_benefit/docs/identity_registry/terms/WOORI_CARD2_SIMPLE.json
    (기본은 검증 후 ROLLBACK. --commit은 card_product_item_type_ck가 제거된 DB에서만 동작한다. DDL은 실행하지 않는다.)
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

USER = "TERMS_SEED"
SCHEMA_VER = "TERMS_V1"
SCOPES = ("ALL_BENEFITS", "PERFORMANCE", "NAMED_ITEMS")
# common_benefit_repository.integrity_errors와 같은 기준(승인 대기 근거 게이트는 등록 전후 비교에서 제외)
INTEGRITY_SQL = ("SELECT gate_cd, issue_key FROM db_pipeline.v_card_integrity_issue "
                 "WHERE gate_cd <> 'evidence_not_approved'")


class TermsError(ValueError):
    """이 TERMS를 등록할 수 없는 사유. 해당 TERMS만 REVIEW가 된다."""


@dataclass
class Span:
    """원문 한 구간. 위치는 청크 원문 기준 1부터, 종료 포함(card_source_evidence와 같은 규칙)."""
    txt: str
    card_doc_id: str
    page_no: int
    card_doc_chunk_id: str
    start_pos: int
    end_pos: int

    def as_json(self) -> dict:
        return {"txt": self.txt, "card_doc_id": self.card_doc_id, "page_no": self.page_no,
                "card_doc_chunk_id": self.card_doc_chunk_id, "start_pos": self.start_pos, "end_pos": self.end_pos}


@dataclass
class TermsResult:
    terms_key: str
    status: str
    reason: str = ""
    item_cd: str | None = None
    card_product_item_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    entries: int = 0
    footnotes: int = 0


# region 순수 함수(DB 미사용)
def compact(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value or "").split())


def terms_item_cd(card_doc_id: str, kind: str, source_txt: str) -> str:
    """같은 문서·종류·원문이면 같은 코드(재실행 중복 방지). 원문 비교는 공백·유니코드 정규화 후 해시."""
    digest = hashlib.sha256(compact(source_txt).encode("utf-8")).hexdigest()[:12].upper()
    return f"TERMS@{card_doc_id}@{kind}@{digest}"


def find_all(text: str, needle: str) -> list[int]:
    """needle이 나오는 모든 위치(0부터)."""
    found, start = [], 0
    while needle and (i := text.find(needle, start)) >= 0:
        found.append(i)
        start = i + 1
    return found


def split_list_entries(source_txt: str, prefix: str) -> list[tuple[str, int]]:
    """'접두어 : 항목, 항목(…, …), …' 목록을 괄호 밖 쉼표로 나눈다. (원문 그대로의 항목, source 안 0부터 위치).

    항목 앞뒤 공백·줄바꿈만 빼고 글자는 바꾸지 않는다. 접두어가 정확히 한 번 있어야 한다.
    """
    hits = find_all(source_txt, prefix)
    if len(hits) != 1:
        raise TermsError(f"목록 접두어가 {len(hits)}번 나옵니다: {prefix!r}")
    body_start = hits[0] + len(prefix)
    pieces, depth, start = [], 0, body_start
    for i in range(body_start, len(source_txt) + 1):
        ch = source_txt[i] if i < len(source_txt) else ","
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            raw = source_txt[start:i]
            lead = len(raw) - len(raw.lstrip())
            piece = raw.strip()
            if piece:
                pieces.append((piece, start + lead))
            start = i + 1
    if not pieces:
        raise TermsError("목록 항목이 없습니다")
    return pieces


def locate(chunks: list[dict], txt: str, *, after: tuple[str, int] | None = None) -> tuple[dict, int]:
    """구간 원문의 청크와 시작 위치(0부터). after가 없으면 페이지 전체에서 정확히 한 번 나와야 한다.

    after=(청크 ID, 위치)면 그 청크에서 그 위치 뒤 첫 번째(각주처럼 본문 바로 뒤에 오는 구간).
    """
    if after is not None:
        chunk = next((c for c in chunks if c["card_doc_chunk_id"] == after[0]), None)
        hits = [i for i in find_all(chunk["chunk_raw_txt"], txt) if i >= after[1]] if chunk else []
        if not hits:
            raise TermsError("본문 뒤에서 각주 원문을 찾지 못했습니다")
        return chunk, hits[0]
    hits = [(c, i) for c in chunks for i in find_all(c["chunk_raw_txt"], txt)]
    if len(hits) != 1:
        raise TermsError(f"원문 위치가 하나로 정해지지 않습니다({len(hits)}곳)")
    return hits[0]


def make_span(chunk: dict, start0: int, txt: str) -> Span:
    """청크 위치(0부터)의 구간. 잘라 낸 문자열이 원문과 다르면 오류."""
    if chunk["chunk_raw_txt"][start0:start0 + len(txt)] != txt:
        raise TermsError("위치의 원문이 SEED 원문과 다릅니다")
    return Span(txt, chunk["card_doc_id"], chunk["page_no"], chunk["card_doc_chunk_id"], start0 + 1, start0 + len(txt))


def build_terms(seed_terms: dict, chunks_by_page: dict[int, list[dict]]) -> tuple[dict, Span, list[Span], list[Span]]:
    """SEED 1건 → (item_data 초안, source, entries, footnotes). 모든 구간을 청크 원문 위치에서 각각 확인한다."""
    src = seed_terms["source"]
    chunks = chunks_by_page.get(src["page_no"]) or []
    if not src.get("txt"):
        raise TermsError("본문 원문이 비어 있습니다")
    chunk, at = locate(chunks, src["txt"])
    source = make_span(chunk, at, src["txt"])
    source_review = reviewed_fields(source.txt, src)
    entries, entry_reviews = [], []
    mode = (seed_terms.get("entries") or {}).get("mode", "NONE")
    if mode == "LIST_AFTER_PREFIX":
        pieces = split_list_entries(source.txt, seed_terms["entries"]["prefix"])
        for (piece, offset), fixes in zip(pieces, entry_fixes(source.txt, src.get("ocr_fixes") or [], pieces)):
            entries.append(make_span(chunk, at + offset, piece))
            entry_reviews.append(reviewed_fields(piece, {"ocr_fixes": fixes}))
    elif mode != "NONE":
        raise TermsError(f"알 수 없는 entries 방식: {mode}")
    footnotes = []
    for note in seed_terms.get("footnotes", []):
        note_chunks = chunks_by_page.get(note["page_no"]) or []
        if note.get("locate") == "FIRST_AFTER_SOURCE" and note["page_no"] == source.page_no:
            f_chunk, f_at = locate(note_chunks, note["txt"], after=(source.card_doc_chunk_id, source.end_pos))
        else:
            f_chunk, f_at = locate(note_chunks, note["txt"])
        footnotes.append(make_span(f_chunk, f_at, note["txt"]))
    footnote_reviews = [reviewed_fields(span.txt, note) for note, span in zip(seed_terms.get("footnotes", []), footnotes)]
    scope = seed_terms.get("scope") or {}
    if scope.get("scope_cd") not in SCOPES:
        raise TermsError(f"적용 범위가 올바르지 않습니다: {scope.get('scope_cd')}")
    if (scope["scope_cd"] == "NAMED_ITEMS") != bool(scope.get("item_ids")):
        raise TermsError("NAMED_ITEMS일 때만 대상 항목 ID가 있어야 합니다")
    scope_json = {"scope_cd": scope["scope_cd"], "item_ids": list(scope.get("item_ids") or [])}
    if scope.get("item_cds"):
        scope_json["item_cds"] = list(scope["item_cds"])
    # 원문(txt)은 그대로 두고, 사람이 확인한 OCR 정정 표기는 reviewed_txt·ocr_fixes로 구간마다 따로 둔다.
    data = {
        "schema_ver": SCHEMA_VER, "terms_kind_cd": seed_terms["terms_kind_cd"],
        "scope": scope_json,
        "source": {**source.as_json(), **source_review},
        "entries": [{"entry_key": f"e{n:02d}", **span.as_json(), **review}
                    for n, (span, review) in enumerate(zip(entries, entry_reviews), 1)],
        "footnotes": [{"footnote_key": note["footnote_key"], "marker": note["marker"], **span.as_json(), **review}
                      for note, span, review in zip(seed_terms.get("footnotes", []), footnotes, footnote_reviews)],
        "provenance_stg_ids": list(seed_terms.get("provenance_stg_ids") or []),
        "seed_terms_key": seed_terms["terms_key"],
    }
    return data, source, entries, footnotes


def apply_ocr_fixes(txt: str, fixes: list[dict]) -> str:
    """사람이 확인한 OCR 정정(from → to)을 원문 사본에 적용한 검토 표기(reviewed_txt). 원문(txt)은 바꾸지 않는다.

    from은 원문에 정확히 한 번 있어야 하고, 정정끼리 겹치면 안 된다.
    """
    marks = []
    for fix in fixes:
        source, target = fix.get("from") or "", fix.get("to") or ""
        if not source or not target or source == target:
            raise TermsError(f"OCR 정정 형식 오류: {fix}")
        hits = find_all(txt, source)
        if len(hits) != 1:
            raise TermsError(f"OCR 정정 대상이 원문에 {len(hits)}번 나옵니다: {source!r}")
        marks.append((hits[0], source, target))
    marks.sort()
    for (a, src, _), (b, _, _) in zip(marks, marks[1:]):
        if a + len(src) > b:
            raise TermsError("OCR 정정 구간이 겹칩니다")
    out, cursor = [], 0
    for at, src, target in marks:
        out += [txt[cursor:at], target]
        cursor = at + len(src)
    return "".join(out + [txt[cursor:]])


def reviewed_fields(txt: str, spec: dict) -> dict:
    """SEED 구간의 ocr_fixes·reviewed_txt를 검사해 item_data 구간에 붙일 필드를 만든다. 정정이 없으면 빈 dict."""
    fixes = spec.get("ocr_fixes") or []
    if not fixes:
        if spec.get("reviewed_txt"):
            raise TermsError("reviewed_txt에는 ocr_fixes가 필요합니다")
        return {}
    reviewed = apply_ocr_fixes(txt, fixes)
    if spec.get("reviewed_txt") is not None and spec["reviewed_txt"] != reviewed:
        raise TermsError("reviewed_txt가 OCR 정정 결과와 다릅니다")
    return {"reviewed_txt": reviewed, "ocr_fixes": [{"from": f["from"], "to": f["to"]} for f in fixes]}


def entry_fixes(source_txt: str, fixes: list[dict], entry_offsets: list[tuple[str, int]]) -> list[list[dict]]:
    """본문 정정을 목록 항목별로 나눈다. 정정이 항목 경계에 걸치면 오류(항목 밖 정정은 어느 항목에도 넣지 않음)."""
    out = [[] for _ in entry_offsets]
    for fix in fixes:
        at = find_all(source_txt, fix["from"])[0]
        end = at + len(fix["from"])
        for n, (piece, offset) in enumerate(entry_offsets):
            inside = offset <= at and end <= offset + len(piece)
            overlap = at < offset + len(piece) and offset < end
            if inside:
                out[n].append(fix)
            elif overlap:
                raise TermsError(f"OCR 정정이 목록 항목 경계에 걸칩니다: {fix['from']!r}")
    return out


def strip_evidence_ids(data: dict) -> dict:
    """멱등 비교용: 등록 때 붙는 evidence_id를 뺀 item_data."""
    out = json.loads(json.dumps(data))
    out.get("source", {}).pop("evidence_id", None)
    for note in out.get("footnotes", []):
        note.pop("evidence_id", None)
    return out
# endregion


# region DB 처리
def chunks_by_page(cur, card_doc_id: str) -> dict[int, list[dict]]:
    rows = cur.execute("""SELECT card_doc_id, page_no, card_doc_chunk_id, chunk_raw_txt FROM db_pipeline.card_doc_chunk
                          WHERE card_doc_id = %s ORDER BY page_no, card_doc_chunk_id""", (card_doc_id,)).fetchall()
    out: dict[int, list[dict]] = {}
    for row in rows:
        out.setdefault(row["page_no"], []).append(row)
    return out


def integrity_counter(cur) -> Counter:
    return Counter((r["gate_cd"], r["issue_key"]) for r in cur.execute(INTEGRITY_SQL).fetchall())


def evidence_for(cur, span: Span, stg_id: str | None) -> tuple[str, bool]:
    """같은 위치·같은 인용의 근거가 있으면 재사용, 없으면 PENDING으로 추가. (evidence_id, 새로 추가 여부)."""
    row = cur.execute("""SELECT evidence_id FROM db_pipeline.card_source_evidence
                         WHERE card_doc_id = %s AND page_no = %s AND card_doc_chunk_id = %s AND start_pos = %s AND end_pos = %s
                           AND quote_txt = %s AND approval_status_cd IN ('PENDING', 'APPROVED')
                         ORDER BY evidence_id LIMIT 1""",
                      (span.card_doc_id, span.page_no, span.card_doc_chunk_id, span.start_pos, span.end_pos, span.txt)).fetchone()
    if row:
        return row["evidence_id"], False
    row = cur.execute("""INSERT INTO db_pipeline.card_source_evidence
                         (card_doc_id, page_no, card_doc_chunk_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING') RETURNING evidence_id""",
                      (span.card_doc_id, span.page_no, span.card_doc_chunk_id, stg_id, span.txt, span.start_pos, span.end_pos)).fetchone()
    return row["evidence_id"], True


def verify_registered(cur, card_id: int, item_id: str) -> list[str]:
    """등록한 TERMS를 DB에서 다시 읽어 원문 위치·근거 연결·범위를 확인한다. 문제 목록(비면 정상)."""
    item = cur.execute("""SELECT item_type_cd, item_cd, item_data, item_rule_txt FROM db_pipeline.card_product_item
                          WHERE card_id = %s AND card_product_item_id = %s""", (card_id, item_id)).fetchone()
    problems = []
    data = item["item_data"]
    spans = [data["source"], *data["entries"], *data["footnotes"]]
    for span in spans:
        row = cur.execute("""SELECT substring(chunk_raw_txt FROM %s FOR %s) AS txt FROM db_pipeline.card_doc_chunk
                             WHERE card_doc_id = %s AND page_no = %s AND card_doc_chunk_id = %s""",
                          (span["start_pos"], span["end_pos"] - span["start_pos"] + 1, span["card_doc_id"], span["page_no"],
                           span["card_doc_chunk_id"])).fetchone()
        if not row or row["txt"] != span["txt"]:
            problems.append(f"원문 위치 불일치: {span['txt'][:30]!r}")
    if item["item_rule_txt"] != data["source"]["txt"]:
        problems.append("item_rule_txt가 본문 원문과 다릅니다")
    linked = {r["evidence_id"] for r in cur.execute(
        """SELECT evidence_id FROM db_pipeline.card_evidence_link
           WHERE card_id = %s AND card_product_item_id = %s AND ev_subject_cd = 'ITEM' AND ev_item_cd = 'SELF'""",
        (card_id, item_id)).fetchall()}
    for span in [data["source"], *data["footnotes"]]:
        if span.get("evidence_id") not in linked:
            problems.append(f"근거 연결 누락: {span['txt'][:30]!r}")
        ev = cur.execute("""SELECT card_doc_id, page_no, card_doc_chunk_id, start_pos, end_pos, quote_txt
                            FROM db_pipeline.card_source_evidence WHERE evidence_id = %s""", (span.get("evidence_id"),)).fetchone()
        if not ev or (ev["card_doc_id"], ev["page_no"], ev["card_doc_chunk_id"], ev["start_pos"], ev["end_pos"], ev["quote_txt"]) != \
                (span["card_doc_id"], span["page_no"], span["card_doc_chunk_id"], span["start_pos"], span["end_pos"], span["txt"]):
            problems.append(f"근거 행이 구간과 다릅니다: {span['txt'][:30]!r}")
    for target in data["scope"]["item_ids"]:
        if not cur.execute("""SELECT 1 FROM db_pipeline.card_product_item WHERE card_id = %s AND card_product_item_id = %s
                              AND item_type_cd = 'BENEFIT'""", (card_id, target)).fetchone():
            problems.append(f"적용 대상 혜택 없음: {target}")
    return problems


def resolve_scope(cur, card_id: int, seed: dict) -> dict:
    """SEED 적용 범위의 item_cds(혜택 코드)를 같은 카드의 BENEFIT 항목 ID(item_ids)로 바꾼 사본. 하나라도 없으면 TermsError."""
    scope = seed.get("scope") or {}
    if not scope.get("item_cds"):
        return seed
    if scope.get("item_ids"):
        raise TermsError("item_cds와 item_ids를 함께 쓸 수 없습니다")
    ids = []
    for code in scope["item_cds"]:
        row = cur.execute("""SELECT card_product_item_id FROM db_pipeline.card_product_item
                             WHERE card_id = %s AND item_cd = %s AND item_type_cd = 'BENEFIT'""", (card_id, code)).fetchone()
        if not row:
            raise TermsError(f"적용 대상 혜택이 이 카드에 아직 등록되지 않았습니다: {code}")
        ids.append(row["card_product_item_id"])
    return {**seed, "scope": {**scope, "item_ids": ids}}


def register_seed(cur, ledger: dict) -> list[TermsResult]:
    """카드 SEED 1개를 등록한다. 호출자가 트랜잭션을 연다. 개별 TERMS 문제는 REVIEW로 남기고 계속한다."""
    card_id, card_doc_id = ledger["card_id"], ledger["card_doc_id"]
    if not cur.execute("SELECT 1 FROM db_pipeline.card_product WHERE card_id = %s", (card_id,)).fetchone():
        raise TermsError(f"card_product가 없습니다: {card_id}")
    if not cur.execute("""SELECT 1 FROM db_pipeline.card_product_doc WHERE card_id = %s AND card_doc_id = %s
                          AND doc_role_cd = 'PRODUCT_GUIDE'""", (card_id, card_doc_id)).fetchone():
        raise TermsError("카드와 상품설명서 연결(card_product_doc)이 없습니다")
    chunks = chunks_by_page(cur, card_doc_id)
    results = []
    for seed in ledger["terms"]:
        key = seed["terms_key"]
        if seed.get("status", "REGISTER") != "REGISTER":
            results.append(TermsResult(key, "HELD", seed.get("held_reason", "SEED 보류")))
            continue
        try:
            seed = resolve_scope(cur, card_id, seed)
            data, source, entries, footnotes = build_terms(seed, chunks)
            for target in data["scope"]["item_ids"]:
                if not cur.execute("""SELECT 1 FROM db_pipeline.card_product_item WHERE card_id = %s
                                      AND card_product_item_id = %s AND item_type_cd = 'BENEFIT'""", (card_id, target)).fetchone():
                    raise TermsError(f"적용 대상 혜택이 이 카드에 없습니다: {target}")
        except TermsError as error:
            results.append(TermsResult(key, "REVIEW", str(error)))
            continue
        item_cd = terms_item_cd(card_doc_id, seed["terms_kind_cd"], source.txt)
        existing = cur.execute("""SELECT card_product_item_id, item_type_cd, item_data FROM db_pipeline.card_product_item
                                  WHERE card_id = %s AND item_cd = %s""", (card_id, item_cd)).fetchone()
        if existing:
            same = existing["item_type_cd"] == "TERMS" and strip_evidence_ids(existing["item_data"]) == strip_evidence_ids(data)
            results.append(TermsResult(key, "UNCHANGED" if same else "CHANGE_REVIEW",
                                       "등록된 TERMS와 같습니다" if same else "같은 코드의 다른 항목이 있어 수정하지 않습니다",
                                       item_cd, existing["card_product_item_id"]))
            continue
        stg_id = next(iter(seed.get("provenance_stg_ids") or []), None)
        source_ev, _ = evidence_for(cur, source, stg_id)
        data["source"]["evidence_id"] = source_ev
        evidence_ids = [source_ev]
        for note, span in zip(data["footnotes"], footnotes):
            note["evidence_id"], _ = evidence_for(cur, span, stg_id)
            evidence_ids.append(note["evidence_id"])
        item_id = cur.execute("""INSERT INTO db_pipeline.card_product_item
                                 (card_id, item_type_cd, item_cd, item_nm, item_data, item_rule_txt, create_user_id, update_user_id)
                                 VALUES (%s, 'TERMS', %s, %s, %s, %s, %s, %s) RETURNING card_product_item_id""",
                              (card_id, item_cd, seed["item_nm"], json.dumps(data, ensure_ascii=False), source.txt, USER, USER)
                              ).fetchone()["card_product_item_id"]
        for evidence_id in dict.fromkeys(evidence_ids):
            cur.execute("""INSERT INTO db_pipeline.card_evidence_link
                           (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, ev_subject_cd, card_product_item_id, ev_item_cd, ev_item_key)
                           SELECT e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.evidence_id, %s, 'ITEM', %s, 'SELF', '-'
                           FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = %s
                           ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING""", (card_id, item_id, evidence_id))
        problems = verify_registered(cur, card_id, item_id)
        if problems:
            raise TermsError(f"{key} 등록 직후 검증 실패: {problems}")
        results.append(TermsResult(key, "INSERTED", "검토 대기", item_cd, item_id, evidence_ids, len(entries), len(footnotes)))
    return results


def register(conn, ledgers: list[dict], commit: bool = False) -> list[dict]:
    """SEED 여러 개를 한 트랜잭션으로 등록한다. commit=False면 항상 ROLLBACK. 신규 정합성 위반이 있으면 예외(ROLLBACK)."""
    report = []
    with conn.cursor() as cur:
        before = integrity_counter(cur)
        for ledger in ledgers:
            report.append({"card_id": ledger["card_id"], "card_doc_id": ledger["card_doc_id"],
                           "results": [vars(r) for r in register_seed(cur, ledger)]})
        new = integrity_counter(cur) - before
        if new:
            raise TermsError("신규 정합성 위반으로 ROLLBACK합니다: " + ", ".join(sorted({g for g, _ in new})))
    return report
# endregion


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="TERMS(할인 제공 유의사항) 등록. 기본은 검증 후 ROLLBACK")
    ap.add_argument("--seed", action="append", required=True, help="TERMS SEED JSON 경로")
    ap.add_argument("--commit", action="store_true", help="실제 등록. card_product_item_type_ck가 없는 DB에서만 허용")
    args = ap.parse_args(argv)
    from dotenv import load_dotenv
    import psycopg
    from psycopg.rows import dict_row
    load_dotenv(".env")
    ledgers = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.seed]
    with psycopg.connect(os.environ["DB_URL"], row_factory=dict_row) as conn:
        if args.commit and conn.execute("SELECT 1 FROM pg_constraint WHERE conname = 'card_product_item_type_ck'").fetchone():
            print("등록 불가: card_product_item_type_ck가 아직 있습니다(DDL 미적용). DDL은 이 프로그램이 실행하지 않습니다.")
            return 1
        try:
            report = register(conn, ledgers, args.commit)
        except TermsError as error:
            conn.rollback()
            print(f"ROLLBACK: {error}")
            return 1
        if args.commit:
            conn.commit()
        else:
            conn.rollback()
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("COMMIT" if args.commit else "ROLLBACK(검증만)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
