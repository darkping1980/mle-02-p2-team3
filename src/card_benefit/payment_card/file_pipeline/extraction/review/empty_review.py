"""Prepare and tally human review of chunks empty in two saved extraction runs."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

from ..report.table_density_report import classify_density, density_score

SIGNALS = ("%", "할인", "적립", "캐시백", "원", "포인트", "면제")
VERDICTS = ("정상", "놓침", "애매")
MARK_RE = re.compile(r"\[\s*(x|X|✓|v| )\s*\]\s*(정상|놓침|애매)")
_REPO_ROOT = Path(__file__).resolve().parents[6]


def _empty(row: dict[str, Any]) -> bool:
    extraction = row.get("extraction")
    return isinstance(extraction, dict) and not any(extraction.get(key) for key in
        ("benefits", "conditions", "limits", "targets", "relations"))


def _load_run(directory: Path) -> dict[str, dict[str, Any]]:
    rows = {}
    for path in sorted(directory.expanduser().glob("*.result.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("chunk_id") is not None:
            rows[str(data["chunk_id"])] = data
    return rows


def _load_chunks(directory: Path) -> dict[str, dict[str, Any]]:
    chunks = {}
    for path in sorted(directory.expanduser().glob("*.chunks.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for chunk in data.get("chunks", []):
            if isinstance(chunk, dict) and chunk.get("chunk_id") is not None:
                chunks[str(chunk["chunk_id"])] = chunk
    return chunks


def _signal_count(text: str) -> int:
    return sum(text.count(term) for term in SIGNALS)


def prepare(result_a: str | Path, result_b: str | Path, chunk_dir: str | Path,
            output_dir: str | Path, top: int = 8, overwrite: bool = False) -> dict[str, Any]:
    """Write a source-free verdict sheet and source-bearing views outside the repository."""
    output = Path(output_dir).expanduser().resolve()
    if output == _REPO_ROOT or _REPO_ROOT in output.parents:
        raise ValueError("출력은 저장소 밖에 지정하세요. 예: ~/pilot_work/review")
    if top < 0:
        raise ValueError("top은 0 이상이어야 합니다.")
    sheet = output / "empty_verdicts.md"
    if sheet.exists() and not overwrite:
        raise FileExistsError(f"기존 판정표 보호를 위해 중단했습니다: {sheet} (--overwrite로 허용)")

    run_a, run_b = _load_run(Path(result_a)), _load_run(Path(result_b))
    chunks = _load_chunks(Path(chunk_dir))
    common = set(run_a) & set(run_b) & chunks.keys()
    empty_ids = [cid for cid in common if _empty(run_a[cid]) and _empty(run_b[cid])]
    all_ids = sorted(chunks)
    density_labels = dict(zip(all_ids, classify_density([density_score(str(chunks[cid].get("text", ""))) for cid in all_ids])))
    rows = []
    for cid in empty_ids:
        chunk = chunks[cid]
        text = str(chunk.get("text", ""))
        rows.append({"chunk_id": cid, "text": text, "length": len(text),
                     "density": density_labels.get(cid, "—"), "signals": _signal_count(text),
                     "page": run_a[cid].get("page_no", chunk.get("page_no", "—"))})
    rows.sort(key=lambda row: (-row["signals"], row["chunk_id"]))
    selected = rows[:top]
    output.mkdir(parents=True, exist_ok=True)
    view_dir = output / "empty_view"
    existing_views = list(view_dir.glob("[0-9][0-9]_*.txt")) if view_dir.exists() else []
    if existing_views and not overwrite:
        raise FileExistsError(f"기존 열람 파일 보호를 위해 중단했습니다: {view_dir} (--overwrite로 허용)")
    if overwrite:
        for path in existing_views:
            path.unlink()
    view_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# 양쪽 실행에서 비어 있는 청크 판정표", "",
             "각 청크 원문은 열람 파일을 저장소 밖에서 직접 확인한 뒤 하나만 체크하세요. 메모에는 판정 근거를 한 줄로 남기세요.", "",
             "| N | chunk_id | 길이 | 표 밀도 구간 | 신호 수 | page | 열람 파일명 | 판정 | 메모(이유 한 줄) |",
             "|---:|---|---:|---|---:|---:|---|---|---|"]
    for index, row in enumerate(selected, 1):
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", row["chunk_id"])
        filename = f"{index:02d}_{safe_id}.txt"
        view = (f"길이: {row['length']}\n표 밀도 구간: {row['density']}\n신호 수: {row['signals']}\n"
                f"page: {row['page']}\n상태: empty in both out8 and out9\n\n{row['text']}")
        (view_dir / filename).write_text(view, encoding="utf-8")
        marks = " [ ] 정상  [ ] 놓침  [ ] 애매 "
        cells = [str(index), row["chunk_id"], str(row["length"]), row["density"], str(row["signals"]),
                 str(row["page"]), filename, marks, "________________"]
        lines.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    sheet.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"sheet": str(sheet), "views": [str(view_dir / f"{i:02d}_{re.sub(r'[^A-Za-z0-9_-]', '_', r['chunk_id'])}.txt") for i, r in enumerate(selected, 1)],
            "selected": [{key: row[key] for key in ("chunk_id", "signals")} for row in selected]}


def tally(sheet: str | Path) -> dict[str, Any]:
    counts = Counter({**{verdict: 0 for verdict in VERDICTS}, "미판정": 0, "중복": 0})
    marked_rows = []
    decisions = []
    for line in Path(sheet).read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or re.match(r"\|\s*[-:]+", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 9 or not cells[0].isdigit():
            continue
        chunk_id, page = cells[1], cells[5]
        checks = MARK_RE.findall("|".join(cells[7:8]))
        checked = [verdict for mark, verdict in checks if mark.lower() in {"x", "✓", "v"}]
        if len(checked) == 1:
            counts[checked[0]] += 1
            decisions.append({"chunk_id": chunk_id, "verdict": checked[0]})
            if checked[0] == "놓침":
                marked_rows.append((chunk_id, page, cells[8]))
        elif len(checked) > 1:
            counts["중복"] += 1
        else:
            counts["미판정"] += 1
    missed = ", ".join(f"{cid[:16]} p.{page}" for cid, page, _ in marked_rows) or "없음"
    reasons = "; ".join(f"{cid[:16]}: {memo}" for cid, _, memo in marked_rows if memo and memo != "________________") or "없음"
    return {"counts": dict(counts), "rows": decisions, "report": [f"{sum(counts[v] for v in VERDICTS)}개 중: 정상 {counts['정상']}, 놓침 {counts['놓침']}, 애매 {counts['애매']}",
            f"놓침 청크: {missed}", f"놓친 이유(메모): {reasons}"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prep = subparsers.add_parser("prepare")
    prep.add_argument("--result-a", required=True); prep.add_argument("--result-b", required=True)
    prep.add_argument("--chunk-dir", required=True); prep.add_argument("--output-dir", required=True)
    prep.add_argument("--top", type=int, default=8); prep.add_argument("--overwrite", action="store_true")
    agg = subparsers.add_parser("tally")
    agg.add_argument("--sheet", required=True); agg.add_argument("--json-out")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare(args.result_a, args.result_b, args.chunk_dir, args.output_dir, args.top, args.overwrite)
        print(json.dumps({"sheet": result["sheet"], "views": result["views"], "selected": result["selected"]}, ensure_ascii=False))
    else:
        result = tally(args.sheet)
        if args.json_out:
            Path(args.json_out).expanduser().write_text(json.dumps(result["rows"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for line in result["report"]:
            print(line)
        print(f"미판정: {result['counts']['미판정']}, 중복: {result['counts']['중복']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
