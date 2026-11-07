"""Aggregate enum-only details from schema failures without emitting source text."""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

_SAFE_TOKEN = re.compile(r"^[A-Z][A-Z0-9_ -]{0,39}$")
_INPUT = re.compile(r"input_value=(.*?), input_type=", re.DOTALL)
_ALLOWED = re.compile(r"Input should be (.*?) \[type=literal_error", re.DOTALL)
_QUOTED = re.compile(r"'((?:[^'\\]|\\.)*)'")
_ENUMS = {
    "kind": ["SPEND_REQ", "EXCLUDE", "USAGE", "PAYMENT", "MERCHANT", "OTHER"],
    "period": ["TXN", "DAY", "MONTH", "YEAR", "UNKNOWN"],
    "type": ["HAS_CONDITION", "HAS_LIMIT", "APPLIES_TO", "EXCLUDES", "MUTUALLY_EXCLUSIVE"],
    "method": ["DISCOUNT", "CASHBACK", "POINT"],
}


def _read_input(message: str) -> Any:
    match = _INPUT.search(message)
    if not match:
        return None
    raw = match.group(1).strip()
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None


def _parse_violation(message: str) -> tuple[str, Any, list[str]] | None:
    if "type=literal_error" not in message:
        return None
    input_match = _INPUT.search(message)
    allowed_match = _ALLOWED.search(message)
    if not input_match or not allowed_match:
        return None
    before = message[:input_match.start()]
    lines = [line.strip() for line in before.splitlines() if line.strip()]
    lines = [line for line in lines if "Input should" not in line]
    path = lines[-1].lstrip("- ") if lines else "unknown"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\[\]-]*", path):
        path_match = re.search(r"([A-Za-z_][A-Za-z0-9_.\[\]-]*)\s*$", before)
        path = path_match.group(1) if path_match else "unknown"
    value = _read_input(message)
    allowed = [bytes(v, "utf-8").decode("unicode_escape") for v in _QUOTED.findall(allowed_match.group(1))]
    if not allowed:
        allowed = _ENUMS.get(path.rsplit(".", 1)[-1], [])
    return path, value, allowed


def analyze_runs(runs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    field_counts: Counter[str] = Counter()
    value_counts: Counter[str] = Counter()
    allowed_by_field: dict[str, list[str]] = {}
    non_ascii = 0
    run_counts: dict[str, Any] = {}
    for name, rows in runs.items():
        per_field: Counter[str] = Counter()
        per_value: Counter[str] = Counter()
        run_non_ascii = 0
        violations = 0
        for row in rows:
            for failure in row.get("failures", []):
                if failure.get("code") != "schema_validation_failure":
                    continue
                parsed = _parse_violation(str(failure.get("message", "")))
                if not parsed:
                    continue
                path, value, allowed = parsed
                violations += 1
                field_counts[path] += 1
                per_field[path] += 1
                allowed_by_field.setdefault(path, allowed)
                if isinstance(value, str) and not value.isascii():
                    non_ascii += 1
                    run_non_ascii += 1
                elif isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
                    value_counts[value] += 1
                    per_value[value] += 1
        run_counts[name] = {"violations": violations, "non_ascii_values": run_non_ascii,
                            "field_counts": dict(sorted(per_field.items())),
                            "value_counts": dict(sorted(per_value.items()))}
    return {"field_counts": dict(sorted(field_counts.items())),
            "value_counts": dict(sorted(value_counts.items())),
            "allowed_values": {k: allowed_by_field[k] for k in sorted(allowed_by_field)},
            "non_ascii_values": non_ascii, "run_counts": run_counts}


def _load_run(directory: str | Path) -> list[dict[str, Any]]:
    path = Path(directory)
    aggregate = path / "result.json"
    if aggregate.is_file():
        data = json.loads(aggregate.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        for key in ("results", "chunks", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError(f"Unsupported aggregate format: {aggregate}")
    rows = []
    for item_path in sorted(path.glob("*.result.json")):
        rows.append(json.loads(item_path.read_text(encoding="utf-8")))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("out3", "out4", "out5a", "out5b", "out6"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--output", required=True, help="JSON path outside the repository")
    args = parser.parse_args()
    runs = {name: _load_run(getattr(args, name)) for name in ("out3", "out4", "out5a", "out5b", "out6")}
    report = analyze_runs(runs)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
