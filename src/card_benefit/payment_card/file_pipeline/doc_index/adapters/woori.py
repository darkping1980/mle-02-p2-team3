"""우리카드 manifest.csv(영문 열)를 공통 항목으로 바꾼다."""

from __future__ import annotations

import csv
from pathlib import Path

SLOT_ROLE = {
    "g1": "product_guide",
    "g1New": "product_guide",
    "g2": "brand_service",
    "g3": "brand_service",
    "g11": "brand_service",
    "g12": "brand_service",
}


def _relative_path(file_path: str) -> str:
    """manifest의 경로는 credit/ 기준이다. ../common/x 는 common/x 로 바꾸고 나머지는 credit/ 아래로 본다."""
    if file_path.startswith("../"):
        return file_path[3:]
    return f"credit/{file_path}"


def split_products(name: str, code: str) -> list[tuple[str, str]]:
    """기존 확보본 manifest는 같은 파일을 쓰는 상품 여러 개를 '; '로 이어 한 행에 적어 두었다.

    이름과 상품 코드의 개수가 같으면 짝을 맞춰 상품별로 나눈다. 개수가 다르면 짝을 믿을 수 없으므로
    이름만 나누고 코드는 비운다. 이름 끝의 공백은 지운다.
    """
    names = [n.strip() for n in name.split(";") if n.strip()]
    if not names:
        # 상품을 알 수 없는 파일(예: AK 우리카드)도 인덱스에서 빠지면 안 되므로 빈 이름으로 한 줄 남긴다
        return [("", code.strip())]
    codes = [c.strip() for c in code.split(";") if c.strip()]
    if len(codes) != len(names):
        codes = [""] * len(names)
    return list(zip(names, codes))


def load_entries(issuer_root: Path) -> tuple[list[dict], dict]:
    rows = list(csv.DictReader((issuer_root / "manifest.csv").open(encoding="utf-8-sig", newline="")))
    # 기존 확보본은 같은 해시의 공식 수집본에서 문서 종류를 이어받는다.
    role_by_sha = {
        row["sha256"]: SLOT_ROLE[row["source_slot"]]
        for row in rows
        if row["record_type"] == "OFFICIAL_COLLECTED" and row["sha256"] and row["source_slot"] in SLOT_ROLE
    }
    entries, skipped = [], []
    for row in rows:
        if not row["file_path"]:
            skipped.append(f'{row["product_name"]} ({row["fail_reason"] or row["download_result"]})')
            continue
        official = row["record_type"] == "OFFICIAL_COLLECTED"
        role = SLOT_ROLE.get(row["source_slot"]) if official else role_by_sha.get(row["sha256"])
        reasons = []
        if row["name_in_pdf"] == "False":
            reasons.append("PDF 내 상품명 자동 확인 실패")
        if "체크" in row["verify_note"]:
            reasons.append("카드 구분 확인 필요(상품명에 체크 포함)")
        if row["source_slot"] == "g1New":
            reasons.append("g1/g1New 중 현행본 확인 필요")
        for name, code in split_products(row["product_name"], row["product_code"]):
            entries.append({
                "file_path": _relative_path(row["file_path"]),
                "manifest_sha256": row["sha256"],
                "doc_role": role or "unclassified",
                "origin": "official_download" if official else "existing_unverified",
                "source_url": row["pdf_source_path"],
                "board_date": row["board_date"][:8],
                "product_name": name,
                "product_ids": {"product_code": code} if code else {},
                "review_reasons": reasons,
            })
    return entries, {"skipped_rows": skipped}
