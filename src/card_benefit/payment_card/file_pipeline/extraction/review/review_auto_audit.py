"""Offline mechanical checks for reviewed extraction sheets.

The result contains no quoted text or extracted values. Passing checks confirms
text and coordinates only; it does not establish semantic correctness.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from .review_tally import LABEL_MAP, MARK
from ..schema import ALLOWED_RELATIONS
from ..verify import _numbers

_REPO_ROOT = Path(__file__).resolve().parents[6]
_GROUPS = ("benefits", "conditions", "limits", "targets", "relations")
_VALUE_COLUMNS = {"benefits": 4, "conditions": 3, "limits": 5, "targets": 2, "relations": 1}
_VALUE_NUMBER_COLUMNS = {"benefits": (2, 3), "conditions": (2,), "limits": (2,)}
_CUES = {
    "discount": re.compile(r"할인|캐시백|청구할인|즉시할인"),
    "point": re.compile(r"적립|포인트|마일리지"),
    "service": re.compile(r"무료|면제|제공|이용권|바우처|라운지"),
}
_ENTITY_TYPE = {"benefits": "Benefit", "conditions": "Condition", "limits": "Limit", "targets": "Target"}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(c for c in text if not c.isspace() and ord(c) >= 32 and c not in "\u200b\u200c\u200d\ufeff")


def _split_cells(line: str) -> list[str]:
    sentinel = "\u0000"
    line = line.replace("\\|", sentinel).strip().strip("|")
    return [part.replace(sentinel, "|").strip() for part in line.split("|")]


def _read_sheet(path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    sources: dict[str, str] = {}
    row_counts: Counter[tuple[str, str]] = Counter()
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^## 청크 )", text, flags=re.MULTILINE)
    for block in blocks:
        heading = re.match(r"## 청크 (.+)$", block, re.MULTILINE)
        if not heading:
            continue
        chunk_id = heading.group(1).strip()
        source_match = re.search(r"^### 원문\s*\n+```[^\n]*\n(.*?)\n```", block, re.MULTILINE | re.DOTALL)
        if source_match:
            sources[chunk_id] = source_match.group(1)
        for section in _GROUPS:
            section_match = re.search(rf"^### {section}\s*\n(.*?)(?=^### |\Z)", block, re.MULTILINE | re.DOTALL)
            if not section_match:
                continue
            table_rows = [line for line in section_match.group(1).splitlines() if line.startswith("|")]
            header_found = False
            for line in table_rows:
                cells = _split_cells(line)
                if not cells or all(re.fullmatch(r":?-{2,}:?", x) for x in cells):
                    continue
                if not header_found:
                    header_found = True
                    continue
                field_count = _VALUE_COLUMNS[section]
                if len(cells) < field_count + 4:
                    continue
                values = cells[:field_count]
                quote, pos, excerpt = cells[field_count:field_count + 3]
                if values and values[0] == "항목 없음":
                    continue
                selected = [LABEL_MAP[label] for mark, label in MARK.findall(cells[-1]) if mark == "x"]
                label = selected[0] if len(selected) == 1 else ("ambiguous" if len(selected) > 1 else "unchecked")
                row_counts[(chunk_id, section)] += 1
                rows.append({
                    "chunk_id": chunk_id, "section": section,
                    "row_no": row_counts[(chunk_id, section)],
                    "values": values, "quote": quote.replace("<br>", "\n"),
                    "position": pos, "excerpt": excerpt.replace("<br>", "\n"),
                    "human_label": label,
                })
    return rows, sources


def _load_chunks(directory: Path) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    result = {}
    for path in sorted(directory.glob("*.chunks.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for chunk in document.get("chunks", []):
            result[str(chunk.get("chunk_id"))] = (document, chunk)
    return result


def _get_page(trace_dir: Path, doc_id: str, page_no: int) -> str | None:
    path = trace_dir / f"{doc_id}.json"
    if not path.is_file():
        return None
    pages = json.loads(path.read_text(encoding="utf-8")).get("pages", [])
    for page in pages:
        if page.get("page_no") == page_no:
            return str(page.get("text", ""))
    return None


def _location(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d+)\s*~\s*(\d+)\s*", value)
    return (int(match[1]), int(match[2])) if match else None


def _pdf_quote_status(document: dict[str, Any], page_no: int, quote: str, pdf_root: Path,
                     page_cache: dict[tuple[str, int], tuple[str, str]]) -> str:
    path = pdf_root / str(document.get("file_path", ""))
    if not path.is_file():
        return "not_checked"
    key = (str(path.resolve()), page_no)
    if key not in page_cache:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            if page_no < 1 or page_no > len(reader.pages):
                page_cache[key] = ("pdf_page_missing", "")
            else:
                page_cache[key] = ("ok", reader.pages[page_no - 1].extract_text() or "")
        except Exception:
            page_cache[key] = ("pdf_text_unavailable", "")
    status, page_text = page_cache[key]
    if status != "ok":
        return status
    return "quote_found" if _norm(quote) and _norm(quote) in _norm(page_text) else "quote_not_found_in_pdf_text"


def _uncovered_cues(chunk_text: str, start_pos: int, spans: list[tuple[int, int]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    position = start_pos
    for line in chunk_text.splitlines():
        first, last = position, position + len(line) - 1
        position += len(line) + 1
        if not line.strip() or any(a <= last and b >= first for a, b in spans):
            continue
        for label, pattern in _CUES.items():
            if pattern.search(line):
                counts[label] += 1
    return dict(counts)


def _load_results(result_dir: Path | None) -> dict[str, dict[str, Any]]:
    if result_dir is None:
        return {}
    results = {}
    for path in sorted(result_dir.glob("*.result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("chunk_id") is not None:
            results[str(result["chunk_id"])] = result
    return results


def _relation_flags(row: dict[str, Any], result: dict[str, Any] | None) -> set[str]:
    if row["section"] != "relations" or result is None:
        return set()
    parts = [part.strip() for part in row["values"][0].split("→")]
    if len(parts) != 3:
        return {"relation_row_unparseable"}
    source_id, rel_type, target_id = parts
    extraction = result.get("extraction") or {}
    entities = {
        str(item.get("id")): _ENTITY_TYPE[group]
        for group in _ENTITY_TYPE
        for item in extraction.get(group, []) or []
        if item.get("id") is not None
    }
    flags = set()
    if source_id not in entities:
        flags.add("relation_source_missing")
    if target_id not in entities:
        flags.add("relation_target_missing")
    allowed = ALLOWED_RELATIONS.get(rel_type)
    if allowed is None:
        flags.add("relation_type_unknown")
    elif source_id in entities and target_id in entities and (entities[source_id], entities[target_id]) != allowed:
        flags.add("relation_endpoint_type_mismatch")
    return flags


def audit_review_sheet(sheet: str | Path, chunk_dir: str | Path, trace_dir: str | Path,
                       pdf_root: str | Path | None = None,
                       result_dir: str | Path | None = None) -> dict[str, Any]:
    """Check sheet quotes, quoted spans, numeric support, and uncovered benefit cues."""
    rows, sheet_sources = _read_sheet(Path(sheet).expanduser())
    chunks = _load_chunks(Path(chunk_dir).expanduser())
    trace_path = Path(trace_dir).expanduser()
    source_root = Path(pdf_root).expanduser() if pdf_root else _REPO_ROOT / "src" / "data"
    results = _load_results(Path(result_dir).expanduser() if result_dir else None)
    report_rows = []
    spans_by_chunk: dict[str, list[tuple[int, int]]] = {}
    chunks_seen: dict[str, tuple[dict[str, Any], dict[str, Any], str]] = {}
    pdf_page_cache: dict[tuple[str, int], tuple[str, str]] = {}

    for row in rows:
        chunk_id = row["chunk_id"]
        flags: set[str] = set()
        loaded = chunks.get(chunk_id)
        if loaded is None:
            document, chunk, page_text = {}, {}, None
            flags.add("chunk_metadata_missing")
        else:
            document, chunk = loaded
            doc_id = str(document.get("doc_id", ""))
            page_no = int(chunk.get("page_no", 0) or 0)
            page_text = _get_page(trace_path, doc_id, page_no)
            chunks_seen[chunk_id] = (document, chunk, page_text or "")
            chunk_text = str(chunk.get("text", ""))
            if sheet_sources.get(chunk_id) != chunk_text:
                flags.add("sheet_source_differs_from_chunk")
            if page_text is None:
                flags.add("page_trace_missing")
            else:
                start = int(chunk.get("start_pos", 1) or 1)
                end = int(chunk.get("end_pos", start + len(chunk_text) - 1) or 0)
                if _norm(page_text[start - 1:end]) != _norm(chunk_text):
                    flags.add("chunk_span_differs_from_page_trace")

        quote = row["quote"]
        quote_key = _norm(quote)
        if page_text is not None and quote_key not in _norm(page_text):
            flags.add("quote_not_in_page_trace")
        chunk_text = str(chunk.get("text", ""))
        if loaded is not None and quote_key not in _norm(chunk_text):
            flags.add("quote_not_in_chunk")
        if quote_key != _norm(row["excerpt"]):
            flags.add("quote_excerpt_mismatch")
        pos = _location(row["position"])
        if pos is None:
            flags.add("position_unavailable_or_ambiguous")
        elif page_text is not None:
            start, end = pos
            if start < 1 or end < start or end > len(page_text) or _norm(page_text[start - 1:end]) != quote_key:
                flags.add("position_quote_mismatch")
            else:
                spans_by_chunk.setdefault(chunk_id, []).append(pos)
        elif pos:
            flags.add("page_text_unavailable_for_position")

        pdf_status = "not_checked"
        if loaded is not None and quote:
            pdf_status = _pdf_quote_status(document, int(chunk.get("page_no", 0) or 0), quote, source_root, pdf_page_cache)
            if pdf_status in {"quote_not_found_in_pdf_text", "pdf_text_unavailable", "pdf_page_missing"}:
                flags.add("pdf_text_needs_human_check")

        numeric_values: set[tuple[float, bool]] = set()
        for index in _VALUE_NUMBER_COLUMNS.get(row["section"], ()):
            numeric_values.update(_numbers(row["values"][index]))
        if numeric_values and not numeric_values.issubset(_numbers(quote)):
            flags.add("numeric_value_not_in_quote")
        if row["section"] == "benefits" and row["values"][1] in {"", "—"}:
            flags.add("benefit_method_unspecified")
        if row["section"] == "relations" and result_dir is not None:
            if chunk_id not in results:
                flags.add("result_json_missing")
            else:
                flags.update(_relation_flags(row, results[chunk_id]))
        objective_flags = flags - {"pdf_text_needs_human_check"}

        report_rows.append({
            "chunk_id": chunk_id, "section": row["section"], "row_no": row["row_no"],
            "human_label": row["human_label"], "automated_flags": sorted(flags),
            "objective_flags": sorted(objective_flags), "pdf_text_status": pdf_status,
            "mechanical_checks_passed": not objective_flags,
            "semantic_correctness_verified": False,
        })

    uncovered = {}
    for chunk_id, (_, chunk, _) in chunks_seen.items():
        cues = _uncovered_cues(str(chunk.get("text", "")), int(chunk.get("start_pos", 1) or 1), spans_by_chunk.get(chunk_id, []))
        if cues:
            uncovered[chunk_id] = cues

    matrix: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    visual_pages: dict[tuple[str, int], dict[str, Any]] = {}
    for row in report_rows:
        objective_flags = row["objective_flags"]
        flag_counts.update(objective_flags)
        if row["pdf_text_status"] in {"quote_not_found_in_pdf_text", "pdf_text_unavailable", "pdf_page_missing"}:
            loaded = chunks.get(row["chunk_id"])
            if loaded:
                document, chunk = loaded
                key = (str(document.get("doc_id", "")), int(chunk.get("page_no", 0) or 0))
                page_info = visual_pages.setdefault(key, {"doc_id": key[0], "page_no": key[1], "chunk_ids": []})
                if row["chunk_id"] not in page_info["chunk_ids"]:
                    page_info["chunk_ids"].append(row["chunk_id"])
        if row["human_label"] in {"unchecked", "ambiguous"}:
            continue
        human_error = row["human_label"] != "match"
        machine_flag = bool(objective_flags)
        key = "true_positive" if human_error and machine_flag else "false_negative" if human_error else "false_positive" if machine_flag else "true_negative"
        matrix[key] += 1

    return {
        "checks_are_mechanical_not_semantic": True,
        "summary": {
            "chunk_count": len({row["chunk_id"] for row in report_rows}),
            "rows": len(report_rows),
            "mechanically_supported": sum(row["mechanical_checks_passed"] for row in report_rows),
            "human_confirmation_rows": sum(row["human_label"] in {"unchecked", "ambiguous"} for row in report_rows),
            "flagged_unreviewed_rows": sum(bool(row["objective_flags"]) and row["human_label"] in {"unchecked", "ambiguous"} for row in report_rows),
            "unflagged_unreviewed_rows": sum(not row["objective_flags"] and row["human_label"] in {"unchecked", "ambiguous"} for row in report_rows),
            "human_labeled_rows": sum(row["human_label"] not in {"unchecked", "ambiguous"} for row in report_rows),
            "uncovered_cue_lines": sum(sum(counts.values()) for counts in uncovered.values()),
            "pdf_pages_needing_visual_review": len(visual_pages),
            "flags_by_code": dict(sorted(flag_counts.items())),
        },
        "human_comparison": {key: matrix[key] for key in ("true_positive", "false_positive", "false_negative", "true_negative")},
        "pdf_pages_needing_visual_review": list(visual_pages.values()),
        "uncovered_cues_by_chunk": uncovered,
        "rows": report_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--pdf-root", help="기본값: 저장소 src/data")
    parser.add_argument("--result-dir", help="관계 끝점 무결성 검사에 쓸 *.result.json 폴더")
    parser.add_argument("--output", required=True, help="저장소 밖 JSON 경로")
    args = parser.parse_args(argv)
    output = Path(args.output).expanduser().resolve()
    if output == _REPO_ROOT or _REPO_ROOT in output.parents:
        parser.error("검토 보고서는 저장소 밖에 지정해야 합니다.")
    report = audit_review_sheet(args.sheet, args.chunk_dir, args.trace_dir, args.pdf_root, args.result_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"] | {"human_comparison": report["human_comparison"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
