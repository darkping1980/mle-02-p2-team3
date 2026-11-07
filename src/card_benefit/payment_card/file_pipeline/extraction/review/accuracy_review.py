"""Prepare and tally a sampled human precision review of saved extractions."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import re
from typing import Any

VERDICTS = ("맞음", "틀림", "일부 누락")
GROUPS = ("benefits", "conditions", "limits", "targets", "relations")
BINS = (("<=999", 0, 999), ("1000-1999", 1000, 1999),
        ("2000-3999", 2000, 3999), (">=4000", 4000, None))
MARK = re.compile(r"\[\s*(x|X|✓|v| )\s*\]\s*(맞음|틀림|일부 누락)")
# Numeric comparison fields are the numeric-bearing fields in schema.py. Labels,
# descriptions, evidence, and enum classifications are intentionally not audited.
EMPTY_FIELDS = {"benefits": ("name", "rate", "method", "amount"),
                "conditions": ("text", "min_amount", "amount"),
                "limits": ("text", "amount", "period", "unlimited"),
                "targets": ("text", "name")}
NUMERIC_FIELDS = {"benefits": ("rate", "amount"),
                  "conditions": ("min_amount",), "limits": ("amount",)}
_NUMBER = re.compile(
    r"(?<![\d.])(?P<parts>\d[\d,，]*(?:\.\d+)?"
    r"(?:\s*(?:억|천만|백만|만|천|백))?"
    r"(?:\s*\d[\d,，]*(?:\.\d+)?(?:\s*(?:억|천만|백만|만|천|백))?)*?)"
    r"\s*(?:원|회|개월|달|일|%|퍼센트)?(?![\d])"
)
_UNIT = re.compile(r"(?P<number>\d[\d,，]*(?:\.\d+)?)(?:\s*(?P<unit>억|천만|백만|만|천|백))?")
_MULTIPLIERS = {"억": 100_000_000, "천만": 10_000_000, "백만": 1_000_000,
                "만": 10_000, "천": 1_000, "백": 100}
_REPO_ROOT = Path(__file__).resolve().parents[6]


def _load_chunks(directory: Path) -> dict[str, dict[str, Any]]:
    chunks = {}
    for path in sorted(directory.expanduser().glob("*.chunks.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for chunk in data.get("chunks", []):
            if isinstance(chunk, dict) and chunk.get("chunk_id") is not None:
                chunks[str(chunk["chunk_id"])] = chunk
    return chunks


def _load_results(directory: Path) -> dict[str, dict[str, Any]]:
    results = {}
    for path in sorted(directory.expanduser().glob("*.result.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("chunk_id") is not None:
            results[str(data["chunk_id"])] = data
    return results


def _items(extraction: Any, group: str) -> list[dict[str, Any]]:
    if not isinstance(extraction, dict):
        return []
    value = extraction.get(group, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _counts(extraction: Any) -> dict[str, int]:
    return {group: len(_items(extraction, group)) for group in GROUPS}


def _number_value(parts: str) -> float:
    total = 0.0
    for match in _UNIT.finditer(parts):
        number = float(match.group("number").replace(",", "").replace("，", ""))
        unit = match.group("unit")
        total += number * _MULTIPLIERS[unit] if unit else number
    return total


def _numbers(value: str) -> set[float]:
    return {_number_value(match.group("parts")) for match in _NUMBER.finditer(value)}


def auto_check(extraction: Any, source_text: str) -> dict[str, Any]:
    """Mechanically check empty entities and extracted values against chunk text."""
    empty = {group: 0 for group in EMPTY_FIELDS}
    item_total = checked = found = 0
    missing: list[tuple[str, str]] = []
    source_numbers = _numbers(source_text)
    for group, fields in EMPTY_FIELDS.items():
        items = _items(extraction, group)
        item_total += len(items)
        for item in items:
            if not any(item.get(field) is not None and item.get(field) != ""
                       and not (field == "unlimited" and item.get(field) is False) for field in fields):
                empty[group] += 1
            for field in NUMERIC_FIELDS.get(group, ()):
                value = item.get(field)
                if value is None or value == "" or isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    candidates = {float(value)}
                elif isinstance(value, str):
                    candidates = _numbers(value)
                else:
                    continue
                if not candidates:
                    continue
                checked += 1
                if candidates.intersection(source_numbers):
                    found += 1
                else:
                    missing.append((group, field))
    count = len(missing)
    return {"empty_items": {"groups": empty, "total": sum(empty.values()), "item_total": item_total},
            "values_not_in_text": {"checked": checked, "found": found, "missing": count, "items": missing},
            "candidate": "숫자 확인 필요" if count else "숫자 이상 없음"}


def _bin(length: int) -> str:
    for name, low, high in BINS:
        if length >= low and (high is None or length <= high):
            return name
    raise ValueError(f"지원하지 않는 청크 길이: {length}")


def _allocate(populations: dict[str, list[dict[str, Any]]], size: int) -> dict[str, int]:
    total = sum(map(len, populations.values()))
    target = min(size, total)
    active = [name for name, rows in populations.items() if rows]
    minimum_total = sum(min(2, len(populations[name])) for name in active)
    if target < minimum_total:
        raise ValueError("비어 있지 않은 길이 구간마다 최소 2개를 뽑으려면 size를 늘리세요.")
    if target == total:
        return {name: len(rows) for name, rows in populations.items()}
    quotas = {name: target * len(rows) / total for name, rows in populations.items()}
    allocation = {name: min(len(rows), int(quotas[name])) for name, rows in populations.items()}
    for name in active:
        allocation[name] = min(len(populations[name]), max(2, allocation[name]))
    while sum(allocation.values()) > target:
        candidates = [name for name in active if allocation[name] > 2]
        if not candidates:
            raise ValueError("size가 길이 구간별 최소 표본 수보다 작습니다.")
        name = min(candidates, key=lambda key: (quotas[key] - int(quotas[key]), key))
        allocation[name] -= 1
    while sum(allocation.values()) < target:
        candidates = [name for name in populations if allocation[name] < len(populations[name])]
        name = max(candidates, key=lambda key: (quotas[key] - allocation[key], len(populations[key]), key))
        allocation[name] += 1
    return allocation


def _short(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("\n", " ")
    return text if len(text) <= 80 else text[:77] + "..."


def _summary(extraction: Any, source_text: str) -> str:
    specifications = {
        "benefits": ("Benefit", ("name", "rate", "method")),
        "conditions": ("Condition", ("kind", "min_amount", "amount")),
        "limits": ("Limit", ("amount", "period", "unlimited")),
        "targets": ("Target", ("kind", "name")),
        "relations": ("Relation", ("source", "type", "target")),
    }
    lines = ["추출 항목 요약"]
    for group, (label, fields) in specifications.items():
        for item in _items(extraction, group):
            values = [item.get(field) for field in fields]
            if group == "relations":
                line = f"{_short(values[0])} → {_short(values[1])} → {_short(values[2])}"
            else:
                line = ", ".join(f"{field}: {_short(value)}" for field, value in zip(fields, values))
            lines.append(f"- {label}: {line}")
            quotes = _evidence(item)[:1] if group == "relations" else _evidence(item)
            for quote in quotes:
                lines.append(f"    근거({_source_line(quote, source_text)}): \"{_short(quote)}\"")
    if len(lines) == 1:
        lines.append("- 항목 없음")
    return "\n".join(lines)


def _evidence(item: dict[str, Any]) -> list[str]:
    evidence = item.get("evidence", [])
    if not isinstance(evidence, list):
        return []
    return [str(row["text"]) for row in evidence[:2]
            if isinstance(row, dict) and isinstance(row.get("text"), str) and row["text"]]


def _source_line(quote: str, source_text: str) -> str:
    position = source_text.find(quote)
    return f"L{source_text.count(chr(10), 0, position) + 1}" if position >= 0 else "위치 못 찾음"


def prepare(result_dir: str | Path, chunk_dir: str | Path, output_dir: str | Path,
            size: int = 30, seed: int = 20261104, overwrite: bool = False,
            tag: str = "") -> dict[str, Any]:
    """Sample benefit-bearing chunks and write a source-free sheet plus full-text views."""
    if size < 0:
        raise ValueError("size는 0 이상이어야 합니다.")
    output = Path(output_dir).expanduser().resolve()
    if output == _REPO_ROOT or _REPO_ROOT in output.parents:
        raise ValueError("출력은 저장소 밖에 지정하세요. 예: ~/pilot_work/review")
    suffix = f"_{tag}" if tag else ""
    sheet = output / f"accuracy_verdicts{suffix}.md"
    view_dir = output / f"accuracy_view{suffix}"
    existing_views = list(view_dir.glob("[0-9][0-9]_*.txt")) if view_dir.exists() else []
    if (sheet.exists() or existing_views) and not overwrite:
        raise FileExistsError(f"기존 판정표/열람 파일 보호를 위해 중단했습니다: {output} (--overwrite로 허용)")

    chunks = _load_chunks(Path(chunk_dir))
    results = _load_results(Path(result_dir))
    populations: dict[str, list[dict[str, Any]]] = {name: [] for name, _, _ in BINS}
    for chunk_id, result in results.items():
        if chunk_id not in chunks or not _items(result.get("extraction"), "benefits"):
            continue
        chunk = chunks[chunk_id]
        text = str(chunk.get("text", ""))
        row = {"chunk_id": chunk_id, "result": result, "chunk": chunk, "text": text,
               "length": len(text), "counts": _counts(result.get("extraction")),
               "checks": auto_check(result.get("extraction"), text)}
        populations[_bin(row["length"])].append(row)
    for rows in populations.values():
        rows.sort(key=lambda row: row["chunk_id"])
    allocation = _allocate(populations, size)
    rng = random.Random(seed)
    selected = []
    for name, _, _ in BINS:
        selected.extend(rng.sample(populations[name], allocation[name]))

    output.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in existing_views:
            path.unlink()
    view_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Hana 추출 정밀도 판정표", "",
             "판정 의미: 틀림 = 추출된 값이 원문과 다름.",
             "일부 누락 = 원문 혜택 일부가 빠짐.", "맞음 = 빠진 혜택이나 잘못된 값이 없음.",
             "빈 항목은 틀림이 아닙니다. 자동 점검은 힌트일 뿐이며, 빠진 혜택만 원문에서 확인하세요.",
             "메모 칸은 집계에 포함되지 않습니다.", "",
             "| 번호 | chunk_id | page | length | 항목수(b/c/l/t) | 빈 항목 | 미발견 숫자 | 숫자 점검(힌트) | 열람 파일 | 판정(맞음/틀림/일부 누락) | 메모 |",
             "|---:|---|---:|---:|---|---:|---:|---|---|---|---|"]
    views, selected_info = [], []
    for index, row in enumerate(selected, 1):
        chunk_id = row["chunk_id"]
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", chunk_id)
        filename = f"{index:02d}_{safe_id}.txt"
        extraction = row["result"].get("extraction")
        counts = row["counts"]
        checks = row["checks"]
        missing_fields = ", ".join(f"{group}.{field}" for group, field in checks["values_not_in_text"]["items"]) or "없음"
        header = (f"길이: {row['length']}\n항목 수 (benefit/condition/limit/target): "
                  f"{counts['benefits']}/{counts['conditions']}/{counts['limits']}/{counts['targets']}\n"
                  f"빈 항목: {checks['empty_items']['total']}개\n미발견 필드: {missing_fields}\n")
        guide = ("읽는 방법\n1 요약 읽기\n2 근거 문장이 원문에 있는지\n3 값(숫자)이 같은지\n"
                 "4 빠진 혜택이 있는지만 원문에서 확인\n5 판정표에 체크\n\n"
                 "판정 의미\n틀림: 추출 값이 원문과 다름\n일부 누락: 원문 혜택 일부가 빠짐\n"
                 "맞음: 빠진 혜택이나 잘못된 값이 없음\n빈 항목은 틀림이 아닙니다. 자동 점검은 힌트일 뿐입니다.\n\n")
        view = guide + header + "\n" + _summary(extraction, row["text"]) + "\n\n청크 원문 전체\n" + row["text"]
        (view_dir / filename).write_text(view, encoding="utf-8")
        page = row["result"].get("page_no", row["chunk"].get("page_no", "—"))
        values = [str(index), chunk_id, str(page), str(row["length"]),
                  f"{counts['benefits']}/{counts['conditions']}/{counts['limits']}/{counts['targets']}",
                  str(checks["empty_items"]["total"]), str(checks["values_not_in_text"]["missing"]),
                  checks["candidate"], filename, "[ ] 맞음  [ ] 틀림  [ ] 일부 누락", "________________"]
        lines.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in values) + " |")
        views.append(str(view_dir / filename))
        selected_info.append({"chunk_id": chunk_id, "bin": _bin(row["length"])})
    sheet.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"sheet": str(sheet), "views": views, "selected": selected_info,
            "bin_counts": {name: allocation[name] for name, _, _ in BINS}}


def tally(sheet: str | Path) -> dict[str, Any]:
    """Count sheet rows using only the verdict cell; memo contents are ignored."""
    counts = Counter({**{verdict: 0 for verdict in VERDICTS}, "미판정": 0, "중복": 0})
    decisions, wrong = [], []
    lines = Path(sheet).read_text(encoding="utf-8").splitlines()
    header = next(([cell.strip() for cell in line.strip().strip("|").split("|")]
                   for line in lines if line.startswith("|") and "chunk_id" in line and "page" in line), [])
    verdict_index = next((i for i, cell in enumerate(header) if "판정" in cell or "verdict" in cell), 6)
    empty_index = next((i for i, cell in enumerate(header) if "빈 항목" in cell), None)
    item_index = next((i for i, cell in enumerate(header) if "항목수" in cell or "item counts" in cell), None)
    empty_total = item_total = 0
    for line in lines:
        if not line.startswith("|") or re.match(r"\|\s*[-:]+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) <= verdict_index or not cells[0].isdigit():
            continue
        checks = MARK.findall(cells[verdict_index])
        checked = [verdict for mark, verdict in checks if mark.lower() in {"x", "✓", "v"}]
        chunk_id, page = cells[1], cells[2]
        if empty_index is not None and item_index is not None:
            try:
                empty_total += int(cells[empty_index])
                item_total += sum(int(value) for value in cells[item_index].split("/"))
            except (IndexError, ValueError):
                pass
        if len(checked) == 1:
            verdict = checked[0]
            counts[verdict] += 1
            decisions.append({"chunk_id": chunk_id, "verdict": verdict})
            if verdict == "틀림":
                wrong.append((chunk_id, page))
        elif len(checked) > 1:
            counts["중복"] += 1
        else:
            counts["미판정"] += 1
    decided = sum(counts[verdict] for verdict in VERDICTS)
    denominator = counts["맞음"] + counts["틀림"] + counts["일부 누락"]
    precision = counts["맞음"] / denominator if denominator else None
    wrong_list = ", ".join(f"{chunk_id[:16]} p.{page}" for chunk_id, page in wrong) or "없음"
    percent = f"{precision:.1%}" if precision is not None else "계산 불가"
    report = [f"판정 {decided}개: 맞음 {counts['맞음']}, 틀림 {counts['틀림']}, 일부 누락 {counts['일부 누락']}",
              f"틀린 청크: {wrong_list}",
              f"정밀도: {counts['맞음']}/{denominator} = {percent} (미판정 {counts['미판정']}, 중복 {counts['중복']})"]
    result = {"counts": dict(counts), "rows": decisions, "wrong": wrong,
              "precision": precision, "report": report}
    if empty_index is not None and item_index is not None:
        ratio = empty_total / item_total if item_total else None
        result["empty_items"] = {"empty": empty_total, "items": item_total, "ratio": ratio}
        percent = f"{ratio:.1%}" if ratio is not None else "계산 불가"
        report.append(f"빈 항목: {empty_total}개 / 전체 항목 {item_total}개 ({percent})")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prep = subparsers.add_parser("prepare")
    prep.add_argument("--result-dir", required=True)
    prep.add_argument("--chunk-dir", required=True)
    prep.add_argument("--output-dir", required=True)
    prep.add_argument("--size", type=int, default=30)
    prep.add_argument("--seed", type=int, default=20261104)
    prep.add_argument("--overwrite", action="store_true")
    prep.add_argument("--tag", default="")
    agg = subparsers.add_parser("tally")
    agg.add_argument("--sheet", required=True)
    agg.add_argument("--json-out")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare(args.result_dir, args.chunk_dir, args.output_dir, args.size, args.seed,
                         args.overwrite, tag=args.tag)
        print(json.dumps(result, ensure_ascii=False))
    else:
        result = tally(args.sheet)
        if args.json_out:
            path = Path(args.json_out).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result["rows"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for line in result["report"]:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
