"""Sample canonical PDF pages for a hand-written golden set, without extraction artifacts."""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[6]
TEMPLATE = ROOT / "src/card_benefit/payment_card/file_pipeline/chat/eval/golden_set_template.csv"
INDEX_ROOT = ROOT / "src/card_benefit/data/index"
ISSUERS = {"hana": "하나", "woori": "우리"}


def safe_output(path: str | Path) -> Path:
    out = Path(path).expanduser().resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("출력은 저장소 밖에 있어야 합니다.")
    return out


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pdf_path(file_path: str) -> Path:
    path = Path(file_path)
    return path.resolve() if path.is_absolute() else (ROOT / "src/data" / path).resolve()


def pdf_link(path: Path, page: int) -> str:
    return "file://" + quote(str(path.resolve()), safe="/:#") + f"#page={page}"


def _allocate(groups: dict[tuple[str, str], list], count: int) -> dict[tuple[str, str], int]:
    keys = sorted(groups)
    if count < len(keys):
        raise ValueError(f"요청 페이지 수({count})가 활성 문서 유형 수({len(keys)})보다 적습니다.")
    alloc = {k: 1 for k in keys}
    if sum(alloc.values()) > count:
        raise ValueError("최소 1페이지씩 할당할 수 있는 요청 수가 아닙니다.")
    remaining = count - len(keys)
    while remaining:
        eligible = [k for k in keys if alloc[k] < len(groups[k])]
        if not eligible:
            break
        weights = {k: len(groups[k]) for k in eligible}
        total = sum(weights.values())
        raw = {k: remaining * weights[k] / total for k in eligible}
        floor_add = {k: min(len(groups[k]) - alloc[k], int(raw[k])) for k in eligible}
        added = sum(floor_add.values())
        for k, n in floor_add.items():
            alloc[k] += n
        remaining -= added
        if remaining:
            eligible = [k for k in eligible if alloc[k] < len(groups[k])]
            if not eligible:
                break
            for k in sorted(eligible, key=lambda x: (-(raw.get(x, 0) % 1), x))[:remaining]:
                alloc[k] += 1
            remaining = max(0, count - sum(alloc.values()))
    return alloc


def sample(index_paths: dict[str, Path], count: int = 20, seed: int = 7,
           include_ocr: bool = False, min_chars: int = 50, per_doc_cap: int = 2,
           template_path: Path = TEMPLATE) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    import fitz

    rng = random.Random(seed)
    template_rows = read_csv(template_path)
    headers = list(template_rows[0]) if template_rows else []
    out: list[dict[str, str]] = []
    summaries: list[dict[str, object]] = []
    for issuer, index_path in index_paths.items():
        docs = [r for r in read_csv(index_path) if r.get("canonical") == "Y"
                and (include_ocr or r.get("ocr_needed") == "N")]
        groups: dict[tuple[str, str], list[tuple[dict[str, str], int, int]]] = defaultdict(list)
        too_short = 0
        for doc in docs:
            path = pdf_path(doc["file_path"])
            with fitz.open(path) as pdf:
                for page_no, page in enumerate(pdf, start=1):
                    char_count = len(page.get_text())
                    if char_count < min_chars:
                        too_short += 1
                    else:
                        groups[(issuer, doc.get("doc_role") or "unknown")].append((doc, page_no, char_count))
        if not groups:
            raise ValueError(f"{issuer}: 최소 글자 수 기준을 통과한 페이지가 없습니다.")
        alloc = _allocate(groups, count)
        selected: list[tuple[dict[str, str], int, int, str]] = []
        for group in sorted(groups):
            candidates = list(groups[group])
            rng.shuffle(candidates)
            used_docs: Counter[str] = Counter()
            for doc, page_no, chars in candidates:
                if used_docs[doc["sha256"]] >= per_doc_cap:
                    continue
                selected.append((doc, page_no, chars, group[1]))
                used_docs[doc["sha256"]] += 1
                if used_docs.total() >= alloc[group]:
                    break
        # Fill any quota prevented by a per-document cap from other eligible strata.
        if len(selected) < count:
            seen = {(x[0]["sha256"], x[1]) for x in selected}
            used = Counter(x[0]["sha256"] for x in selected)
            remainder = [(d, p, c, role) for (iss, role), items in groups.items() for d, p, c in items
                         if (d["sha256"], p) not in seen and used[d["sha256"]] < per_doc_cap]
            rng.shuffle(remainder)
            for item in remainder:
                selected.append(item)
                used[item[0]["sha256"]] += 1
                if len(selected) == count:
                    break
        if len(selected) < count:
            raise ValueError(f"{issuer}: per-doc-cap={per_doc_cap}로 {count}개 중 {len(selected)}개만 선택 가능")
        selected.sort(key=lambda x: (x[3], x[0]["file_path"], x[1]))
        for n, (doc, page_no, _chars, _role) in enumerate(selected, 1):
            row = {h: "" for h in headers}
            row.update({"id": f"G-{issuer[0].upper()}-{n:03d}", "카드사": ISSUERS[issuer],
                        "유형": "", "질문": "", "근거문서": Path(doc["file_path"]).name,
                        "근거쪽": str(page_no), "정답없음": "아니오",
                        "이미지문서유래": "예" if doc.get("ocr_needed") == "Y" else "아니오",
                        "문서가 있는 그래프": "", "비고": pdf_link(pdf_path(doc["file_path"]), page_no)})
            out.append(row)
        actual = Counter(x[3] for x in selected)
        for role in sorted(set(actual) | {g[1] for g in groups}):
            summaries.append({"issuer": issuer, "doc_role": role, "pages": actual[role], "excluded_short": too_short})

    slot_count = round(count * len(index_paths) * 0.15)
    slots_per_issuer = Counter(list(index_paths)[i % len(index_paths)] for i in range(slot_count))
    for issuer, nslots in slots_per_issuer.items():
        for n in range(1, nslots + 1):
            row = {h: "" for h in headers}
            row.update({"id": f"G-{issuer[0].upper()}-NA-{n:03d}", "카드사": ISSUERS[issuer], "유형": "",
                        "질문": "", "근거문서": "", "근거쪽": "", "정답없음": "예",
                        "이미지문서유래": "아니오",
                        "비고": "정답 없음 질문: 해당 카드·서비스에 없는 정보를 묻는 질문을 직접 작성"})
            # Keep graph coverage blank until it has been checked.
            row["문서가 있는 그래프"] = ""
            out.append(row)
    return out, summaries


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    headers = list(rows[0]) if rows else list(read_csv(TEMPLATE)[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", choices=("hana", "woori", "both"), default="both")
    parser.add_argument("--count", type=int, default=20, help="페이지 수; both면 카드사별")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", required=True)
    parser.add_argument("--include-ocr", action="store_true")
    parser.add_argument("--min-chars", type=int, default=50)
    parser.add_argument("--per-doc-cap", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        output = safe_output(args.output)
        if args.count < 1 or args.min_chars < 0 or args.per_doc_cap < 1:
            raise ValueError("count와 per-doc-cap은 양수, min-chars는 음수일 수 없습니다.")
        issuers = ("hana", "woori") if args.issuer == "both" else (args.issuer,)
        indexes = {i: INDEX_ROOT / i / "documents.csv" for i in issuers}
        rows, summaries = sample(indexes, args.count, args.seed, args.include_ocr,
                                 args.min_chars, args.per_doc_cap)
        write_csv(output, rows)
    except (ValueError, OSError, KeyError) as e:
        print(str(e), file=sys.stderr)
        return 2
    print("issuer\tdoc_role\tpages\texcluded_short")
    for row in summaries:
        print(f"{row['issuer']}\t{row['doc_role']}\t{row['pages']}\t{row['excluded_short']}")
    print(f"slots\t{sum(r['정답없음'] == '예' for r in rows)}\tseed\t{args.seed}\treproducible\ttrue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
