"""하나카드 manifest.csv(한글 열)를 공통 항목으로 바꾼다. 체크카드 폴더(debit/)는 이번 범위가 아니다."""

from __future__ import annotations

import csv
import re
from pathlib import Path

ID_COLUMNS = ["CD_ID", "PC_SEQ", "모바일_CD_NO", "디자인코드"]


def _role(doc_type: str) -> str:
    if doc_type.startswith("상품설명서"):
        return "product_guide"
    if doc_type.startswith("상품상세 웹"):
        return "web_capture"
    if doc_type.startswith("브랜드서비스"):
        return "brand_service"
    if doc_type.startswith("공통약관"):
        return "terms"
    return "unclassified"


def _origin(doc_class: str) -> str:
    if "웹페이지 변환" in doc_class:
        return "web_capture"
    if "URL 추정" in doc_class:
        return "official_url_inferred"
    return "official_download"


def load_entries(issuer_root: Path) -> tuple[list[dict], dict]:
    rows = list(csv.DictReader((issuer_root / "manifest.csv").open(encoding="utf-8-sig", newline="")))
    entries, skipped = [], []
    for row in rows:
        path = row["파일경로"]
        if not path:
            skipped.append(f'{row["카드상품명"]} ({row["실패사유"] or row["다운로드결과"]})')
            continue
        if path.startswith("debit/"):
            continue
        date = re.search(r"_(\d{8})\.pdf$", path)
        reasons = []
        if row["PDF내 상품명확인"] == "False":
            reasons.append("PDF 내 상품명 자동 확인 실패")
        entries.append({
            "file_path": path,
            "manifest_sha256": row["SHA256"],
            "doc_role": _role(row["문서종류"]),
            "origin": _origin(row["문서구분"]),
            "source_url": row["PDF원본URL"] or row["모바일상세URL"],
            "board_date": date.group(1) if date else "",
            "product_name": row["카드상품명"],
            "product_ids": {k: row[k] for k in ID_COLUMNS if row[k]},
            "review_reasons": reasons,
        })
    return entries, {"skipped_rows": skipped}
