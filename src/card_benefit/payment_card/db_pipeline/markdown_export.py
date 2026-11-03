"""등록된 문서 PDF를 페이지별 Markdown 파일로 저장하는 CLI. 검증용 중간 산출물이다.

- DB는 읽기만 한다(``card_doc`` 메타데이터와 페이지 수). PDF 원본과 DB 데이터는 바꾸지 않는다.
- 청킹·추출 로직은 이 모듈을 쓰지 않는다. 원문 근거 위치의 기준은 계속 ``card_doc_page.page_raw_txt`` 다.
  Markdown은 다단 문서에서 읽기 순서가 바뀔 수 있어 위치 기준으로 쓰지 않는다.
- LLM을 호출하지 않는다. ``pymupdf4llm`` 은 선택 의존성이라 실행할 때만 불러온다.

저장 구조::

    src/card_benefit/data/markdown/
      index.csv                         card_doc_id, 문서 구분, 상대 경로, 연결 관계, 제목, 페이지 수
      common/<card_doc_id>/             공통서비스 문서
      product/<card_doc_id>/            개별 카드 상품 문서
        manifest.json                   문서 메타데이터, PDF 경로·해시, 페이지 파일 목록, 변환기 버전
        page_001.md ...

문서 구분은 DB 연결 관계로 정한다. ``card_common_doc`` 에 있으면 common이다(상품에도 연결된 브랜드 안내서는 한 벌만
common에 두고 상품 연결은 index.csv의 product_links에 남긴다). ``card_product_doc`` 에만 있으면 product다.
어디에도 연결되지 않은 문서는 ``doc_type_cd`` (BRAND_SERVICE→common, 그 외→product)로 정하고 UNLINKED로 표시한다.

실행 예(저장소 루트에서)::

    PYTHONPATH="src;src/card_benefit" python -m payment_card.db_pipeline.markdown_export            # 전체 문서
    PYTHONPATH="src;src/card_benefit" python -m payment_card.db_pipeline.markdown_export --doc-id 20261103_000014
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .document_service import DATA_ROOT

OUTPUT_ROOT = DATA_ROOT.parents[1] / "markdown"          # src/card_benefit/data/markdown
DOC_SQL = """SELECT d.card_doc_id, d.doc_cd, d.doc_title, d.doc_type_cd, d.doc_file_nm, d.doc_sha256,
                    (SELECT count(*) FROM db_pipeline.card_doc_page p WHERE p.card_doc_id = d.card_doc_id) AS page_cnt,
                    (SELECT string_agg(x.card_common_id::text, ';' ORDER BY x.card_common_id)
                     FROM db_pipeline.card_common_doc x WHERE x.card_doc_id = d.card_doc_id) AS common_links,
                    (SELECT string_agg(x.card_id || ':' || x.doc_role_cd, ';' ORDER BY x.card_id)
                     FROM db_pipeline.card_product_doc x WHERE x.card_doc_id = d.card_doc_id) AS product_links
             FROM db_pipeline.card_doc d WHERE (%(doc_id)s::text IS NULL OR d.card_doc_id = %(doc_id)s) ORDER BY d.card_doc_id"""
NOTE = "중간 산출물. 원문 근거 위치는 card_doc_page.page_raw_txt 기준이며 이 Markdown의 문자 위치를 쓰지 않는다."


def doc_class(document: dict) -> tuple[str, str]:
    """``(구분 폴더, 연결 상태)``. 공통서비스 연결이 상품 연결보다 우선한다(같은 파일을 두 벌 만들지 않는다)."""
    if document.get("common_links"):
        return "common", "COMMON_AND_PRODUCT" if document.get("product_links") else "COMMON"
    if document.get("product_links"):
        return "product", "PRODUCT"
    return ("common" if document["doc_type_cd"] == "BRAND_SERVICE" else "product"), "UNLINKED"


def export_document(document: dict, output_root: Path = OUTPUT_ROOT) -> dict:
    """문서 1건을 페이지별 Markdown으로 저장하고 manifest를 반환한다. PDF 해시가 DB와 다르면 저장하지 않는다."""
    import pymupdf4llm

    pdf_path = DATA_ROOT.parent / document["doc_file_nm"]
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if digest != document["doc_sha256"]:
        raise ValueError(f"PDF 해시가 DB와 다릅니다: {document['card_doc_id']}")
    folder = output_root / doc_class(document)[0] / document["card_doc_id"]
    folder.mkdir(parents=True, exist_ok=True)
    chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    pages = []
    for index, chunk in enumerate(chunks, start=1):
        name = f"page_{index:03d}.md"
        (folder / name).write_text(chunk["text"], encoding="utf-8")
        pages.append({"page_no": index, "file": name, "chars": len(chunk["text"])})
    manifest = {
        "card_doc_id": document["card_doc_id"], "doc_cd": document["doc_cd"], "doc_title": document["doc_title"],
        "doc_type_cd": document["doc_type_cd"], "pdf_file": document["doc_file_nm"], "pdf_sha256": digest,
        "db_page_cnt": document["page_cnt"], "markdown_page_cnt": len(pages), "pages": pages,
        "converter": f"pymupdf4llm {pymupdf4llm.__version__}", "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": NOTE,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def write_index(documents: list[dict], output_root: Path = OUTPUT_ROOT) -> Path:
    """저장된 manifest와 DB 연결 관계로 문서 매핑 index.csv를 다시 만든다. 경로는 index.csv 기준 상대 경로다."""
    path = output_root / "index.csv"
    links = {d["card_doc_id"]: d for d in documents}
    manifests = sorted(output_root.glob("*/*/manifest.json"))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["card_doc_id", "doc_class", "link_status", "relative_path", "common_links", "product_links",
                         "doc_type_cd", "doc_cd", "doc_title", "db_page_cnt", "markdown_page_cnt", "pdf_file"])
        for manifest_path in manifests:
            row = json.loads(manifest_path.read_text(encoding="utf-8"))
            document = links.get(row["card_doc_id"], {})
            status = doc_class(document)[1] if document else "NOT_IN_DB"
            writer.writerow([row["card_doc_id"], manifest_path.parent.parent.name, status,
                             manifest_path.parent.relative_to(output_root).as_posix(),
                             document.get("common_links") or "", document.get("product_links") or "",
                             row["doc_type_cd"], row["doc_cd"], row["doc_title"], row["db_page_cnt"],
                             row["markdown_page_cnt"], row["pdf_file"]])
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="등록 문서 PDF → 페이지별 Markdown (읽기 전용, LLM 호출 없음)")
    parser.add_argument("--doc-id", help="card_doc_id. 없으면 등록된 전체 문서")
    args = parser.parse_args(argv)
    from common.query_log_config import load_project_environment
    load_project_environment()
    with psycopg.connect(os.environ["DB_URL"], options="-c default_transaction_read_only=on") as conn, \
            conn.cursor(row_factory=dict_row) as cur:
        cur.execute(DOC_SQL, {"doc_id": None})
        all_documents = cur.fetchall()
        conn.rollback()
    documents = [d for d in all_documents if args.doc_id in (None, d["card_doc_id"])]
    failed = 0
    for document in documents:
        try:
            manifest = export_document(document)
            mismatch = "" if manifest["markdown_page_cnt"] == manifest["db_page_cnt"] else " (페이지 수가 DB와 다름)"
            print(f"OK   {document['card_doc_id']} pages={manifest['markdown_page_cnt']}{mismatch}")
        except (OSError, ValueError) as error:
            failed += 1
            print(f"FAIL {document['card_doc_id']} {type(error).__name__}: {error}")
    print("index", write_index(all_documents))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
