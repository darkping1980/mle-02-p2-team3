"""file_pipeline 장부 매핑 사양과 오프라인 SQL 드라이런.

매핑(입력 -> file_pipeline 열):
* documents.csv(canonical=Y): doc_id/hash/title/path/url/pages -> card_doc.doc_sha256,
  doc_title, doc_file_nm, doc_source_url, doc_page_cnt; doc_id는 고정 키가 아니므로
  ID scheme으로 card_doc_id와 doc_cd를 만든다. role은 DOC_TYPE 시드 코드로 변환한다.
* traceability JSON pages[].text와 quality -> card_doc_page의 raw text, 길이,
  텍스트 SHA-256, 레이어, 추출기명/버전. 페이지 번호는 1-based.
* chunks JSON chunks[].text/start_pos/end_pos/heading -> card_doc_chunk의 원문,
  1-based inclusive 위치, 순번 및 절 이름.
* AI run/call: 미구현. 필요한 입력은 run 단위 stage/method/model/prompt 버전과 전문,
  시작/종료시각/상태/파라미터 및 chunk별 입력 해시, 응답/상태, 토큰, 지연시간.
* 다음 단계: 추출 결과는 card_extr_stg의 stg_raw_item/stg_kind_cd/stg_status 등에
  대기 상태로만 매핑한다. card_source_evidence.quote_txt와 위치/승인 상태를 검토한다.
  현재 그래프 quote_status(locate/missing/ambiguous 등)에 대응하는 전용 열은 없다.
  확정 테이블 적재는 이 도구 범위 밖이다.

기본 ID 제안: sha256 기반 D/C 접두 + 16 hex (문서는 PDF 해시, 청크는 doc hash와
위치/순번/내용 해시 조합); doc_cd는 같은 문서 해시 기반 DOC- + 16 hex. 대안은
입력 doc_id 및 chunk_id에 각각 D-/C- 접두를 붙인 정규화 문자열이다. 길이/충돌
조건 때문에 기본 ID가 결정적이며 ID scheme 인자로 선택한다.

doc_version_no=1은 V6 DDL DEFAULT 1에 근거한다. doc_status=ACTIVE,
chunk_type_cd=BODY, chunk_status=RAW는 코드 시드 및 DDL 기본값에 근거한다.
사용자 확정이 필요한 값은 --create-user-id와 --collected-at이며, 수집 일시가
CSV 열에 있으면 그것을 우선한다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
SEED_CODES = {
    "DOC_TYPE": {"PRODUCT_GUIDE", "TERMS", "BRAND_SERVICE", "ETC"},
    "DOC_STATUS": {"ACTIVE", "SUPERSEDED", "EXCLUDED"},
    "PAGE_LAYER": {"TEXT", "IMAGE", "MIXED", "UNKNOWN"},
    "CHUNK_TYPE": {"BODY", "TABLE", "NOTICE", "HEADER_FOOTER", "ETC"},
    "CHUNK_STATUS": {"RAW", "CLEANED", "EXCLUDED"},
}
ROLE_CODES = {"product_guide": "PRODUCT_GUIDE", "terms": "TERMS", "brand_service": "BRAND_SERVICE", "web_capture": "ETC"}
DOC_COLUMNS = ("card_doc_id", "doc_cd", "doc_type_cd", "doc_title", "doc_source_url", "doc_file_nm", "doc_file_size", "doc_sha256", "doc_page_cnt", "doc_collect_date", "doc_version_no", "doc_status", "create_date", "create_user_id", "update_date", "update_user_id")
PAGE_COLUMNS = ("card_doc_id", "page_no", "page_raw_txt", "page_char_cnt", "page_txt_sha256", "page_layer_cd", "page_extractor_nm", "page_extractor_ver", "create_date", "create_user_id", "update_date", "update_user_id")
CHUNK_COLUMNS = ("card_doc_id", "page_no", "card_doc_chunk_id", "chunk_seq", "chunk_section_nm", "chunk_type_cd", "chunk_start_pos", "chunk_end_pos", "chunk_raw_txt", "chunk_clean_txt", "chunk_status", "chunk_split_rule_ver", "create_date", "create_user_id", "update_date", "update_user_id")
MAX_INSERT_BYTES = 1_000_000


def schema_check_sql() -> str:
    """SQL Editor에서 실행할 읽기 전용 컬럼·제약·코드표 집계 조회."""
    return """-- 읽기 전용: SQL Editor에서 실행
SELECT table_name, column_name, ordinal_position, data_type, character_maximum_length,
       is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='file_pipeline' AND table_name IN ('card_doc','card_doc_page','card_doc_chunk')
ORDER BY table_name, ordinal_position;
SELECT c.relname AS table_name, con.conname, con.contype, pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='file_pipeline' AND c.relname IN ('card_doc','card_doc_page','card_doc_chunk')
ORDER BY c.relname, con.conname;
SELECT 'common_code_grp' AS table_name, count(*) AS row_count FROM file_pipeline.common_code_grp
UNION ALL SELECT 'common_cd', count(*) FROM file_pipeline.common_cd;
"""


def compare_schema_csv(rows: list[dict], expected: dict[str, set[str]]) -> list[str]:
    """Compare synthetic/exported information_schema CSV rows with expected table columns."""
    actual: dict[str, set[str]] = {}
    for row in rows:
        actual.setdefault(row["table_name"], set()).add(row["column_name"])
    diffs = []
    for table, columns in expected.items():
        missing = sorted(columns - actual.get(table, set()))
        extra = sorted(actual.get(table, set()) - columns)
        if missing or extra:
            diffs.append(f"{table}: missing={missing}, extra={extra}")
    return diffs


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _id(prefix: str, payload: str, scheme: str, fallback: str) -> str:
    if scheme == "sha256":
        return prefix + _sha(payload)[:16]
    safe = re.sub(r"[^A-Za-z0-9_.:-]+", "-", fallback).strip("-")
    return (prefix + safe)[:20]


def _literal(value):
    if value is None:
        return "NULL"
    text = str(value)
    if "\x00" in text:
        raise ValueError("PostgreSQL text cannot contain NUL characters")
    # PostgreSQL E strings safely preserve quotes and backslashes.
    escaped = text.replace("\\", "\\\\").replace("'", "''")
    return "E'" + escaped + "'"


def _json_sql(value):
    return _literal(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _dollar_quote(text: str) -> str:
    if "\x00" in text:
        raise ValueError("PostgreSQL text cannot contain NUL characters")
    tag = "$ledger$"
    n = 0
    while tag in text:
        n += 1
        tag = f"$ledger{n}$"
    return f"{tag}{text}{tag}"


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _find_doc_file(directory: Path, doc_id: str, suffix: str) -> Path | None:
    direct = directory / f"{doc_id}{suffix}"
    if direct.is_file():
        return direct
    matches = list(directory.rglob(f"{doc_id}{suffix}")) if directory.is_dir() else []
    return matches[0] if len(matches) == 1 else None


def build_plan(index_csv: Path, trace_dir: Path, chunk_dir: Path, issuer: str,
               create_user_id: str, collected_at: str | None, id_scheme: str = "sha256",
               include_ocr: bool = False) -> dict:
    indexed = [r for r in _rows(index_csv) if r.get("issuer") == issuer and r.get("canonical") == "Y"]
    excluded_ocr = [r for r in indexed if r.get("ocr_needed") == "Y"]
    docs = indexed if include_ocr else [r for r in indexed if r.get("ocr_needed") != "Y"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    errors: list[str] = []
    planned_docs, pages, chunks = [], [], []
    seen_sha, seen_doc_ids = set(), set()
    source_page_counts = {}
    for row in docs:
        sha = row.get("sha256", "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha): errors.append(f"문서 {row.get('doc_id')}: doc_sha256 형식")
        if sha in seen_sha: errors.append(f"중복 doc_sha256: {sha[:8]}")
        seen_sha.add(sha)
        role = row.get("doc_role", "")
        doc_type = ROLE_CODES.get(role)
        if doc_type not in SEED_CODES["DOC_TYPE"]: errors.append(f"DOC_TYPE 매핑 불가: {role}")
        card_doc_id = _id("D", sha, id_scheme, row.get("doc_id", ""))
        doc_cd = "DOC-" + _sha(sha)[:16] if id_scheme == "sha256" else ("DOC-" + row.get("doc_id", ""))[:50]
        if card_doc_id in seen_doc_ids: errors.append(f"중복 card_doc_id: {card_doc_id}")
        seen_doc_ids.add(card_doc_id)
        missing = [k for k in ("doc_id", "sha256", "file_path", "pages") if not row.get(k)]
        if missing: errors.append(f"문서 {row.get('doc_id')}: 필수 인덱스 필드 {','.join(missing)}")
        collect = row.get("collected_at") or row.get("doc_collect_date") or collected_at
        if not collect: errors.append(f"문서 {row.get('doc_id')}: --collected-at 필요")
        try: page_count = int(row.get("pages", ""))
        except ValueError: page_count = None; errors.append(f"문서 {row.get('doc_id')}: pages 숫자 아님")
        trace_path = _find_doc_file(trace_dir, row.get("doc_id", ""), ".json")
        chunk_path = _find_doc_file(chunk_dir, row.get("doc_id", ""), ".chunks.json")
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path else None
        chunk_doc = json.loads(chunk_path.read_text(encoding="utf-8")) if chunk_path else None
        if trace is None: errors.append(f"쪽 JSON 없음: {row.get('doc_id')}")
        if chunk_doc is None: errors.append(f"청크 JSON 없음: {row.get('doc_id')}")
        trace_pages = (trace or {}).get("pages", [])
        if page_count is not None and len(trace_pages) != page_count:
            errors.append(f"쪽 수 불일치 {row.get('doc_id')}: index={page_count}, json={len(trace_pages)}")
        source_page_counts[row.get("doc_id", "")] = len(trace_pages)
        planned_docs.append({"row": row, "card_doc_id": card_doc_id, "doc_cd": doc_cd,
                             "doc_type_cd": doc_type, "collect": collect, "page_count": page_count,
                             "file_size": int(row["file_size"]) if row.get("file_size") else None, "now": now})
        if trace:
            for p in trace_pages:
                text = p.get("text")
                if not isinstance(text, str): errors.append(f"페이지 원문 문자열 아님: {row.get('doc_id')} p{p.get('page_no')}"); continue
                quality = p.get("quality") or {}
                has_visual = bool(quality.get("has_visual"))
                chars = len(text)
                layer = "MIXED" if has_visual and chars else "IMAGE" if has_visual else "TEXT" if chars else "UNKNOWN"
                pages.append({"doc": planned_docs[-1], "page_no": int(p.get("page_no", 0)), "text": text,
                              "char_count": chars, "sha": _sha(text), "layer": layer,
                              "extractor": quality.get("extractor") or "PyMuPDF",
                              "extractor_ver": quality.get("extractor_ver"), "now": now})
        if chunk_doc:
            for seq, c in enumerate(chunk_doc.get("chunks", []), start=1):
                start, end, page_no, text = c.get("start_pos"), c.get("end_pos"), c.get("page_no"), c.get("text")
                if not isinstance(text, str) or not isinstance(start, int) or not isinstance(end, int) or not isinstance(page_no, int):
                    errors.append(f"청크 필드 누락/형식: {row.get('doc_id')} #{seq}"); continue
                page = next((p for p in pages if p["doc"] is planned_docs[-1] and p["page_no"] == page_no), None)
                if page is None or start < 1 or end < start or end > (page["char_count"] if page else 0):
                    errors.append(f"청크 위치 범위 오류: {row.get('doc_id')} p{page_no} #{seq}")
                payload = f"{sha}:{page_no}:{start}:{end}:{seq}:{_sha(text)}"
                chunk_id = _id("C", payload, id_scheme, c.get("chunk_id", ""))
                chunks.append({"doc": planned_docs[-1], "page_no": page_no, "chunk_id": chunk_id,
                               "seq": seq, "heading": c.get("heading"), "start": start, "end": end,
                               "text": text, "now": now})
    errors.extend(f"사용자 ID 누락: --create-user-id" for _ in [0] if not create_user_id)
    # Estimate serialized INSERT payload sizes without retaining/reporting text.
    estimated = sum(len(json.dumps(x, ensure_ascii=False).encode("utf-8")) for x in pages + chunks)
    estimated += sum(len(json.dumps({k: v for k, v in x.items() if k != "row"}, ensure_ascii=False).encode("utf-8")) for x in planned_docs)
    return {"docs": planned_docs, "pages": pages, "chunks": chunks, "errors": errors,
            "excluded_ocr_docs": len(excluded_ocr),
            "source_page_counts": source_page_counts, "estimated_bytes": estimated, "create_user_id": create_user_id}


def _insert(table: str, columns: tuple[str, ...], values: list[str]) -> str:
    statement = f"INSERT INTO file_pipeline.{table} ({', '.join(columns)}) VALUES\n  (" + ", ".join(values) + ")\nON CONFLICT DO NOTHING;\n"
    if len(statement.encode("utf-8")) > MAX_INSERT_BYTES:
        raise ValueError(f"단일 행 INSERT가 {MAX_INSERT_BYTES} bytes 제한을 넘습니다: {table}")
    return statement


def sql_text(plan: dict) -> str:
    user = plan["create_user_id"]
    statements = ["-- 드라이런 출력. 검토 후 사용자가 별도 실행합니다.\nBEGIN;\n"]
    for d in plan["docs"]:
        r, now = d["row"], d["now"]
        vals = [ _literal(d["card_doc_id"]), _literal(d["doc_cd"]), _literal(d["doc_type_cd"]), _literal(r.get("title") or r.get("doc_title") or Path(r.get("file_path", "document")).stem), _literal(r.get("source_url") or r.get("doc_source_url") or None), _literal(Path(r["file_path"]).name), str(d["file_size"]) if d["file_size"] is not None else "NULL", _literal(r["sha256"].lower()), str(d["page_count"] or "NULL"), _literal(d["collect"]), "1", _literal("ACTIVE"), _literal(now), _literal(user), _literal(now), _literal(user)]
        # Chunk/doc text uses tagged dollar quoting to minimize quoting errors.
        statements.append(_insert("card_doc", DOC_COLUMNS, vals))
        for p in (x for x in plan["pages"] if x["doc"] is d):
            vals = [_literal(d["card_doc_id"]), str(p["page_no"]), _dollar_quote(p["text"]), str(p["char_count"]), _literal(p["sha"]), _literal(p["layer"]), _literal(p["extractor"]), _literal(p["extractor_ver"]), _literal(p["now"]), _literal(user), _literal(p["now"]), _literal(user)]
            statements.append(_insert("card_doc_page", PAGE_COLUMNS, vals))
        for c in (x for x in plan["chunks"] if x["doc"] is d):
            vals = [_literal(d["card_doc_id"]), str(c["page_no"]), _literal(c["chunk_id"]), str(c["seq"]), _literal(c["heading"]), _literal("BODY"), str(c["start"]), str(c["end"]), _dollar_quote(c["text"]), "NULL", _literal("RAW"), _literal("chunks-v1"), _literal(c["now"]), _literal(user), _literal(c["now"]), _literal(user)]
            statements.append(_insert("card_doc_chunk", CHUNK_COLUMNS, vals))
    hashes = ", ".join(_literal(d["row"].get("sha256", "")) for d in plan["docs"])
    statements.append("-- 적재 후 확인용 집계\nSELECT 'card_doc' AS table_name, count(*) FROM file_pipeline.card_doc WHERE doc_sha256 IN (" + (hashes or "NULL") + ")\nUNION ALL SELECT 'card_doc_page', count(*) FROM file_pipeline.card_doc_page p JOIN file_pipeline.card_doc d USING(card_doc_id) WHERE d.doc_sha256 IN (" + (hashes or "NULL") + ")\nUNION ALL SELECT 'card_doc_chunk', count(*) FROM file_pipeline.card_doc_chunk p JOIN file_pipeline.card_doc d USING(card_doc_id) WHERE d.doc_sha256 IN (" + (hashes or "NULL") + ");\n")
    statements.append("-- 사용자가 검토 후 실행할 되돌리기 문장(대상 doc_sha256 한정)\n-- DELETE 순서: chunk -> page -> doc\nDELETE FROM file_pipeline.card_doc_chunk WHERE card_doc_id IN (SELECT card_doc_id FROM file_pipeline.card_doc WHERE doc_sha256 IN (" + (hashes or "NULL") + "));\nDELETE FROM file_pipeline.card_doc_page WHERE card_doc_id IN (SELECT card_doc_id FROM file_pipeline.card_doc WHERE doc_sha256 IN (" + (hashes or "NULL") + "));\nDELETE FROM file_pipeline.card_doc WHERE doc_sha256 IN (" + (hashes or "NULL") + ");\nCOMMIT;\n")
    return "".join(statements)


def render(plan: dict, issuer: str) -> None:
    print(f"{issuer} file_pipeline 드라이런")
    print("항목 | 건수/바이트")
    print(f"문서 | {len(plan['docs'])}")
    print(f"OCR 필요로 제외한 대표 문서 | {plan['excluded_ocr_docs']}")
    print(f"쪽 | {len(plan['pages'])}")
    print(f"청크 | {len(plan['chunks'])}")
    print(f"NOT NULL·코드·중복·범위 위반 후보 | {len(plan['errors'])}")
    print(f"예상 입력 데이터 크기 | {plan['estimated_bytes']} bytes")
    counts = Counter(plan["source_page_counts"].values())
    if counts: print("쪽 JSON 분포 | " + ", ".join(f"{n}쪽:{c}문서" for n, c in sorted(counts.items())))
    for error in plan["errors"][:30]: print("오류 후보 | " + error)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True, choices=["hana", "woori"])
    parser.add_argument("--index", type=Path, required=True, help="documents.csv 또는 index 루트")
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--chunk-dir", type=Path, required=True)
    parser.add_argument("--create-user-id", required=True)
    parser.add_argument("--collected-at", help="CSV 수집 일시 열이 없을 때 필수 (ISO-8601)")
    parser.add_argument("--id-scheme", choices=["sha256", "source"], default="sha256")
    parser.add_argument("--include-ocr-needed", action="store_true", help="OCR 필요 문서도 포함(기본 제외)")
    parser.add_argument("--sql-out", type=Path)
    parser.add_argument("--schema-sql-out", type=Path, help="읽기 전용 스키마 확인 SQL 출력")
    args = parser.parse_args(argv)
    for out in (args.sql_out, args.schema_sql_out):
        if out:
            resolved = out.expanduser().resolve()
            if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
                parser.error("출력 경로는 저장소 밖이어야 합니다")
    index = args.index / args.issuer / "documents.csv" if args.index.is_dir() else args.index
    plan = build_plan(index, args.trace_dir, args.chunk_dir, args.issuer, args.create_user_id, args.collected_at, args.id_scheme, args.include_ocr_needed)
    render(plan, args.issuer)
    if args.sql_out:
        Path(args.sql_out).expanduser().write_text(sql_text(plan), encoding="utf-8")
    if args.schema_sql_out:
        Path(args.schema_sql_out).expanduser().write_text(schema_check_sql(), encoding="utf-8")
    return 2 if plan["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
