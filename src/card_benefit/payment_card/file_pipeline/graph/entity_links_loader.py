"""Validate entity-link CSVs and optionally render a manual INSERT script."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _read_rows(path: Path) -> list[dict[str, str]]:
    with Path(path).expanduser().open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _truth(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def validate_links(
    within_csv: Path | None = None,
    across_csv: Path | None = None,
    nodes_csv: Path | None = None,
) -> dict:
    """Return counts, validation errors and within-card-only merge mappings."""
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    errors: list[str] = []
    rows: list[dict[str, str]] = []
    for path, default_scope, default_type in (
        (within_csv, "within_card", "SAME_AS_STRONG"),
        (across_csv, "across_cards", "SIMILAR"),
    ):
        if path is None:
            continue
        for row_number, raw in enumerate(_read_rows(Path(path)), start=2):
            row = dict(raw)
            row["scope"] = (row.get("scope") or default_scope).strip()
            row["link_type"] = (row.get("link_type") or default_type).strip()
            row["merge_target"] = (row.get("merge_target") or ("true" if row["scope"] == "within_card" else "false")).strip().lower()
            row["_source"] = f"{path}:{row_number}"
            rows.append(row)
            if row["scope"] not in {"within_card", "across_cards"}:
                errors.append(f"{row['_source']}: invalid scope {row['scope']!r}")
            if row["link_type"] not in {"SAME_AS_STRONG", "SIMILAR"}:
                errors.append(f"{row['_source']}: invalid link_type {row['link_type']!r}")
            if row["scope"] == "across_cards" and (row["link_type"] != "SIMILAR" or _truth(row["merge_target"])):
                errors.append(f"{row['_source']}: across_cards links must be SIMILAR and not merge targets")
            if row["scope"] == "within_card" and (row["link_type"] != "SAME_AS_STRONG" or not _truth(row["merge_target"])):
                errors.append(f"{row['_source']}: within_card links must be SAME_AS_STRONG merge targets")
            grouped.setdefault((row["scope"], row.get("group_id", "")), []).append(row)

    member_group: dict[tuple[str, str], str] = {}
    valid_mapping: dict[str, str] = {}
    for (scope, group_id), members in grouped.items():
        member_ids = [r.get("member_node_id", "") for r in members]
        canonical_ids = {r.get("canonical_node_id", "") for r in members}
        if not group_id:
            errors.append(f"{scope}: missing group_id")
        if not all(member_ids) or not all(canonical_ids) or len(canonical_ids) != 1:
            errors.append(f"{scope}/{group_id}: missing or inconsistent canonical/member IDs")
            continue
        canonical = next(iter(canonical_ids))
        if canonical not in member_ids:
            errors.append(f"{scope}/{group_id}: canonical is not included among members")
        if len(member_ids) != len(set(member_ids)):
            errors.append(f"{scope}/{group_id}: duplicate member row")
        for member in member_ids:
            key = (scope, member)
            prior = member_group.get(key)
            if prior is not None and prior != group_id:
                errors.append(f"{scope}/{member}: member belongs to more than one group ({prior}, {group_id})")
            member_group[key] = group_id
            if scope == "within_card" and all(r["link_type"] == "SAME_AS_STRONG" and _truth(r["merge_target"]) for r in members):
                if member != canonical:
                    valid_mapping[member] = canonical

    if nodes_csv is not None:
        node_ids = {row.get("id", "") for row in _read_rows(Path(nodes_csv))}
        for row in rows:
            for column in ("canonical_node_id", "member_node_id"):
                node_id = row.get(column, "")
                if node_id and node_id not in node_ids:
                    errors.append(f"{row['_source']}: {column} {node_id!r} is not present in --nodes-csv")

    return {
        "groups": len(grouped),
        "members": len({(row["scope"], row.get("member_node_id", "")) for row in rows}),
        "rows": len(rows),
        "merge_mapping": valid_mapping,
        "errors": errors,
    }


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_insert(rows: list[dict[str, str]], run_id: str) -> str:
    """Render a SQL file for manual execution; this module never connects to a DB."""
    values = []
    for row in rows:
        scope = row["scope"]
        link_type = row["link_type"]
        values.append("(" + ", ".join((
            _sql_literal(run_id), _sql_literal(row["group_id"]), _sql_literal(scope),
            _sql_literal(link_type), _sql_literal(row.get("kind", "")),
            _sql_literal(row["canonical_node_id"]), _sql_literal(row["member_node_id"]),
            "true" if _truth(row.get("same_props", "false")) else "false",
            str(int(row.get("distinct_pages") or 0)),
        )) + ")")
    return (
        "-- Manual review only. This file is not executed by the loader.\n"
        "insert into public.fp_entity_links "
        "(run_id, group_id, scope, link_type, kind, canonical_node_id, member_node_id, same_props, distinct_pages)\n"
        "values\n  " + ",\n  ".join(values) + ";\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--within-csv", type=Path)
    parser.add_argument("--across-csv", type=Path)
    parser.add_argument("--nodes-csv", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--output-sql", type=Path, help="write manual INSERT SQL; default is validation only")
    args = parser.parse_args(argv)
    report = validate_links(args.within_csv, args.across_csv, args.nodes_csv)
    print(f"groups={report['groups']} members={report['members']} rows={report['rows']}")
    print(f"validation_errors={len(report['errors'])}")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    if args.output_sql:
        if not args.run_id:
            parser.error("--run-id is required with --output-sql")
        if report["errors"]:
            parser.error("cannot write SQL when validation errors exist")
        rows = []
        for path, scope, link_type in ((args.within_csv, "within_card", "SAME_AS_STRONG"), (args.across_csv, "across_cards", "SIMILAR")):
            if path:
                for row in _read_rows(path):
                    row["scope"] = row.get("scope") or scope
                    row["link_type"] = row.get("link_type") or link_type
                    rows.append(row)
        args.output_sql.parent.mkdir(parents=True, exist_ok=True)
        args.output_sql.write_text(render_insert(rows, args.run_id), encoding="utf-8")
        print(f"sql_written={args.output_sql}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
