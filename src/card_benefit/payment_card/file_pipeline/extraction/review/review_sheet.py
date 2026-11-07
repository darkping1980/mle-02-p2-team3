"""Create an offline, human-readable comparison sheet for saved extractions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
from urllib.parse import quote
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[6]
_SEED = 20261103
_GROUPS = ("benefits", "conditions", "limits", "targets", "relations")


def _load_chunks(chunk_dir: Path) -> dict[str, tuple[str, dict[str, Any]]]:
    found = {}
    for path in sorted(chunk_dir.glob("*.chunks.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc_id = str(doc["doc_id"])
        for chunk in doc["chunks"]:
            chunk_id = chunk.get("chunk_id")
            if isinstance(chunk_id, str):
                found[chunk_id] = (doc_id, chunk)
    return found


def _item_count(extraction: Any) -> int:
    if not isinstance(extraction, dict):
        return 0
    return sum(len(extraction.get(group, [])) for group in _GROUPS)


def _select(results: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    eligible = [r for r in results if _item_count(r.get("extraction")) > 0]
    eligible.sort(key=lambda r: (int(r.get("chunk_length", 0)), str(r.get("chunk_id", ""))))
    if count >= len(eligible):
        return eligible
    # Pick evenly spaced ranks over the length-sorted population, then use a fixed
    # seeded tie-break shuffle when several ranks map to the same rounded slot.
    rng = random.Random(_SEED)
    if count == 0:
        return []
    if count == 1:
        return [eligible[len(eligible) // 2]]
    slots = [round(i * (len(eligible) - 1) / (count - 1)) for i in range(count)]
    selected = [eligible[i] for i in slots]
    rng.shuffle(selected)
    return selected


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _evidence_rows(group: str, items: list[dict[str, Any]], chunk: dict[str, Any], ambiguous: set[str]) -> list[str]:
    headers = {
        "benefits": ("이름", "방법", "비율", "금액"),
        "conditions": ("텍스트", "종류", "최소 금액"),
        "limits": ("텍스트", "기간", "금액", "무제한", "공유"),
        "targets": ("텍스트", "종류"),
        "relations": ("source → type → target",),
    }[group]
    out = [f"### {group}\n", "| " + " | ".join(headers + ("인용문", "위치", "위치 확인용 청크 부분", "대조") ) + " |",
           "|" + "|".join(["---"] * (len(headers) + 4)) + "|"]
    for i, item in enumerate(items):
        fields = {
            "benefits": (item.get("name"), item.get("method"), item.get("rate"), item.get("amount")),
            "conditions": (item.get("text"), item.get("kind"), item.get("min_amount")),
            "limits": (item.get("text"), item.get("period"), item.get("amount"), item.get("unlimited"), item.get("shared")),
            "targets": (item.get("text"), item.get("kind")),
            "relations": (f"{item.get('source')} → {item.get('type')} → {item.get('target')}",),
        }[group]
        for j, evidence in enumerate(item.get("evidence", [])):
            path = f"{group}[{i}].evidence[{j}]"
            location = evidence.get("location")
            chunk_text = str(chunk.get("text", ""))
            start = chunk.get("start_pos")
            if location is None or not isinstance(start, int):
                pos, excerpt = "위치 없음", "위치 없음"
            elif path in ambiguous:
                pos, excerpt = "모호", "모호"
            else:
                a = location.get("start_pos")
                b = location.get("end_pos")
                if not isinstance(a, int) or not isinstance(b, int):
                    pos, excerpt = "위치 없음", "위치 없음"
                else:
                    pos = f"{a}~{b}"
                    offset_a, offset_b = a - start, b - start + 1
                    excerpt = chunk_text[offset_a:offset_b] if 0 <= offset_a <= offset_b <= len(chunk_text) else "범위 밖"
            out.append("| " + " | ".join(_cell(v) for v in fields + (evidence.get("text"), pos, excerpt,
                "[ ] 원문과 일치 [ ] 값 오류 [ ] 누락 있음 [ ] 환각<br>메모: __________")) + " |")
    if not items:
        out.append("| 항목 없음 |" + " |" * (len(headers) + 3))
    return out


def generate_review_sheet(result_dir: str | Path, chunk_dir: str | Path, output: str | Path,
                          count: int = 5) -> dict[str, Any]:
    """Generate the review sheet and return non-sensitive selection statistics."""
    if count < 0:
        raise ValueError("count는 0 이상이어야 합니다.")
    output_path = Path(output).expanduser().resolve()
    if output_path == _REPO_ROOT or _REPO_ROOT in output_path.parents:
        raise ValueError("대조표는 저장소 밖에 지정해야 합니다.")
    chunks = _load_chunks(Path(chunk_dir).expanduser())
    results = []
    for path in sorted(Path(result_dir).expanduser().glob("*.result.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            results.append(data)
    selected = _select(results, count)
    lines = ["# 추출 결과 대조표", "", "> 경고: PDF 원문 텍스트가 포함되어 있습니다. 이 파일을 저장소나 메신저에 업로드하지 마세요.", ""]
    counts = {}
    ids = []
    for result in selected:
        chunk_id = str(result.get("chunk_id", ""))
        if chunk_id not in chunks:
            continue
        doc_id, chunk = chunks[chunk_id]
        extraction = result.get("extraction") or {}
        text = str(chunk.get("text", ""))
        ids.append(chunk_id)
        counts[chunk_id] = _item_count(extraction)
        lines += [f"## 청크 {chunk_id}", "", f"- 문서 ID: {doc_id}",
                  f"- 페이지: {result.get('page_no', chunk.get('page_no', '—'))}",
                  f"- 길이: {result.get('chunk_length', len(text))}", "", "### 원문", "", "```text", text, "```", ""]
        ambiguous = {f.get("path") for f in result.get("failures", [])
                     if f.get("code") == "quote_location_ambiguous"}
        for group in _GROUPS:
            lines.extend(_evidence_rows(group, extraction.get(group, []), chunk, ambiguous))
            lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"path": str(output_path), "chunk_ids": ids, "item_counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description="저장된 추출 결과 대조표 생성")
    parser.add_argument("--result-dir", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()
    generate_review_sheet(args.result_dir, args.chunk_dir, args.output, args.count)


if __name__ == "__main__":
    main()
