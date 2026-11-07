"""Validate graph CSVs and optionally insert them into the fixed fp_ allowlist."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter
from pathlib import Path
import sys

from .export import ALLOWED_ENDPOINTS, CSV_COLUMNS

WRITE_TABLES = ("fp_load_runs", "fp_nodes", "fp_edges", "fp_evidence")
_INSERT_COLUMNS = {
    "fp_load_runs": CSV_COLUMNS["fp_load_runs"],
    "fp_nodes": CSV_COLUMNS["fp_nodes"],
    "fp_edges": CSV_COLUMNS["fp_edges"],
    # DB identity column is generated, so the CSV's seven columns are all inserted.
    "fp_evidence": CSV_COLUMNS["fp_evidence"],
}
_BATCH_SIZE = 1000


class DuplicateRunError(ValueError):
    pass


class ExistingNodeConflictError(ValueError):
    pass


class DatabaseOperationError(RuntimeError):
    def __init__(self, exception_class, sqlstate=None):
        self.exception_class = exception_class
        self.sqlstate = sqlstate
        message = f"Database operation failed ({exception_class})"
        if sqlstate:
            message += f" SQLSTATE={sqlstate}"
        super().__init__(message)


class DriverUnavailableError(RuntimeError):
    pass


class CSVValidationError(ValueError):
    def __init__(self, errors):
        self.errors = dict(errors)
        super().__init__(f"CSV validation failed: {self.errors}")


def _read(path, table):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != CSV_COLUMNS[table]:
            raise ValueError(f"Unexpected columns in {path.name}")
        return list(reader)


def validate_csvs(csv_dir):
    csv_dir = Path(csv_dir).expanduser().resolve()
    unexpected = sorted(p.name for p in csv_dir.glob("*.csv") if p.stem not in WRITE_TABLES)
    if unexpected:
        raise ValueError("CSV directory contains files outside the fp_ write allowlist")
    rows = {table: _read(csv_dir / f"{table}.csv", table) for table in WRITE_TABLES}
    errors = Counter()
    runs = rows["fp_load_runs"]
    if len(runs) != 1 or not runs[0].get("run_id"):
        errors["invalid_run_count"] += 1
    run_id = runs[0].get("run_id", "") if runs else ""
    if any(r.get("run_id") != run_id for table in ("fp_nodes", "fp_edges") for r in rows[table]):
        errors["run_id_mismatch"] += 1
    if runs:
        try:
            if int(runs[0]["node_count"]) != len(rows["fp_nodes"]) or int(runs[0]["edge_count"]) != len(rows["fp_edges"]):
                errors["run_count_mismatch"] += 1
        except (KeyError, TypeError, ValueError):
            errors["invalid_run_counts"] += 1
    nodes = rows["fp_nodes"]
    by_id = {}
    for row in nodes:
        if not row["id"] or row["id"] in by_id:
            errors["duplicate_node_id"] += 1
        by_id[row["id"]] = row
        if row["node_type"] not in {"Issuer", "Card", "Benefit", "Condition", "Limit", "Target"}:
            errors["invalid_node_type"] += 1
        try:
            if not isinstance(json.loads(row["props"]), dict):
                raise ValueError
        except (TypeError, ValueError):
            errors["invalid_props"] += 1
    edges = rows["fp_edges"]
    edge_ids = set()
    edge_keys = set()
    for row in edges:
        if not row["id"] or row["id"] in edge_ids:
            errors["duplicate_edge_id"] += 1
        edge_ids.add(row["id"])
        source, target = by_id.get(row["source_id"]), by_id.get(row["target_id"])
        if source is None or target is None:
            errors["missing_endpoint"] += 1
            continue
        expected = ALLOWED_ENDPOINTS.get(row["edge_type"])
        if not expected or (source["node_type"], target["node_type"]) != expected or (row["edge_type"] == "MUTUALLY_EXCLUSIVE" and row["source_id"] == row["target_id"]):
            errors["invalid_endpoint_types"] += 1
        edge_key = (row["source_id"], row["target_id"], row["edge_type"])
        if edge_key in edge_keys:
            errors["duplicate_edge_relation"] += 1
        edge_keys.add(edge_key)
    for row in rows["fp_evidence"]:
        if bool(row["node_id"]) == bool(row["edge_id"]):
            errors["invalid_evidence_target"] += 1
        elif row["node_id"] and row["node_id"] not in by_id or row["edge_id"] and row["edge_id"] not in edge_ids:
            errors["invalid_evidence_target"] += 1
        status = row["quote_status"]
        if status not in ("located", "ambiguous", "missing"):
            errors["invalid_quote_status"] += 1
            continue
        try:
            if not re.fullmatch(r"[0-9a-fA-F]{64}", row["doc_sha256"]):
                raise ValueError
            if status != "located":
                if any(row[k] for k in ("page_no", "start_pos", "end_pos")):
                    raise ValueError
            elif int(row["page_no"]) < 1 or int(row["start_pos"]) < 1 or int(row["end_pos"]) < int(row["start_pos"]):
                raise ValueError
        except (ValueError, TypeError):
            errors["invalid_evidence_position"] += 1
    if errors:
        raise CSVValidationError(errors)
    return rows


def _connect(database_url):
    try:
        import psycopg
    except ImportError as exc:
        raise DriverUnavailableError("PostgreSQL driver psycopg is unavailable; install psycopg[binary,pool].") from exc
    return psycopg.connect(database_url)


def _table_for_sql(sql):
    match = re.match(r"INSERT INTO public\.(fp_[a-z_]+) ", sql)
    return match.group(1) if match else None


def _insert_sql(table):
    if table not in WRITE_TABLES:
        raise ValueError("table is not allowed")
    columns = _INSERT_COLUMNS[table]
    return f"INSERT INTO public.{table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"


def _jsonb(value):
    try:
        from psycopg.types.json import Jsonb
    except ImportError:
        return value
    return Jsonb(value)


def load_csvs(csv_dir, *, execute=False, skip_existing_nodes=False):
    rows = validate_csvs(csv_dir)
    counts = {table: len(rows[table]) for table in WRITE_TABLES}
    if not execute:
        result = {"mode": "dry_run", "counts": counts}
        if skip_existing_nodes:
            result["skip_existing_nodes_note"] = "Skip targets will be determined by DB lookup at execution time."
        return result
    database_url = os.environ.get("FP_DATABASE_URL")
    if not database_url:
        raise RuntimeError("FP_DATABASE_URL is required for --execute")
    conn = None
    try:
        conn = _connect(database_url)
        with conn.cursor() as cursor:
            run_id = rows["fp_load_runs"][0]["run_id"]
            cursor.execute("SELECT 1 FROM public.fp_load_runs WHERE run_id = %s", (run_id,))
            if cursor.fetchone():
                raise DuplicateRunError("run_id already exists")
            skipped_ids = set()
            if skip_existing_nodes:
                node_ids = [row["id"] for row in rows["fp_nodes"]]
                cursor.execute(
                    "SELECT id, node_type FROM public.fp_nodes WHERE id = ANY(%s)",
                    (node_ids,),
                )
                existing_nodes = cursor.fetchall()
                csv_nodes = {row["id"]: row for row in rows["fp_nodes"]}
                conflicts = [
                    node_id for node_id, node_type in existing_nodes
                    if node_type != csv_nodes[node_id]["node_type"] or node_type != "Card"
                ]
                if conflicts:
                    raise ExistingNodeConflictError(
                        f"Existing nodes must match CSV Card nodes: {conflicts}"
                    )
                skipped_ids = {node_id for node_id, _ in existing_nodes}
            for table in WRITE_TABLES:
                sql = _insert_sql(table)
                batch = []
                for row in rows[table]:
                    if table == "fp_nodes" and row["id"] in skipped_ids:
                        continue
                    values = []
                    for column in _INSERT_COLUMNS[table]:
                        value = row[column]
                        if table == "fp_nodes" and column == "props":
                            value = _jsonb(json.loads(value))
                        elif table == "fp_evidence" and column in ("page_no", "start_pos", "end_pos"):
                            value = int(value) if value else None
                        elif (table == "fp_evidence" and column in ("node_id", "edge_id")) or (table == "fp_nodes" and column == "chunk_id"):
                            # CSV 빈 칸은 NULL 이어야 한다. '' 로 들어가면 fp_evidence_exactly_one_target 체크에 걸린다.
                            value = value or None
                        elif table == "fp_load_runs" and column in ("node_count", "edge_count"):
                            value = int(value)
                        values.append(value)
                    batch.append(tuple(values))
                    if len(batch) == _BATCH_SIZE:
                        # executemany keeps psycopg3's pipeline batching while avoiding COPY-specific adaptation risks.
                        cursor.executemany(sql, batch)
                        batch = []
                if batch:
                    cursor.executemany(sql, batch)
        conn.commit()
        result = {"mode": "execute", "counts": counts}
        if skip_existing_nodes:
            result.update({
                "csv_node_count": len(rows["fp_nodes"]),
                "actual_new_run_node_count": len(rows["fp_nodes"]) - len(skipped_ids),
                "skipped_existing_node_count": len(skipped_ids),
                "skipped_existing_node_ids": [row["id"] for row in rows["fp_nodes"] if row["id"] in skipped_ids][:5],
            })
        return result
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        if isinstance(exc, (DuplicateRunError, ExistingNodeConflictError, DriverUnavailableError)):
            raise
        state = getattr(exc, "sqlstate", None)
        raise DatabaseOperationError(type(exc).__name__, str(state) if state else None) from None
    finally:
        if conn is not None:
            conn.close()


_DELETE_COUNT_SQL = {
    "fp_evidence": "SELECT COUNT(*) FROM public.fp_evidence WHERE node_id IN (SELECT id FROM public.fp_nodes WHERE run_id = %s) OR edge_id IN (SELECT id FROM public.fp_edges WHERE run_id = %s)",
    "fp_edges": "SELECT COUNT(*) FROM public.fp_edges WHERE run_id = %s",
    "fp_nodes": "SELECT COUNT(*) FROM public.fp_nodes WHERE run_id = %s",
    "fp_load_runs": "SELECT COUNT(*) FROM public.fp_load_runs WHERE run_id = %s",
}
_DELETE_SQL = {
    "fp_evidence": "DELETE FROM public.fp_evidence WHERE node_id IN (SELECT id FROM public.fp_nodes WHERE run_id = %s) OR edge_id IN (SELECT id FROM public.fp_edges WHERE run_id = %s)",
    "fp_edges": "DELETE FROM public.fp_edges WHERE run_id = %s",
    "fp_nodes": "DELETE FROM public.fp_nodes WHERE run_id = %s",
    "fp_load_runs": "DELETE FROM public.fp_load_runs WHERE run_id = %s",
}


def delete_run(run_id, *, execute=False):
    """Report or delete rows belonging to one graph load run."""
    database_url = os.environ.get("FP_DATABASE_URL")
    if not database_url:
        raise RuntimeError("FP_DATABASE_URL is required for --delete-run")
    conn = None
    try:
        conn = _connect(database_url)
        counts = {}
        with conn.cursor() as cursor:
            for table, sql in _DELETE_COUNT_SQL.items():
                params = (run_id, run_id) if table == "fp_evidence" else (run_id,)
                cursor.execute(sql, params)
                counts[table] = int(cursor.fetchone()[0])
            if execute:
                for table, sql in _DELETE_SQL.items():
                    params = (run_id, run_id) if table == "fp_evidence" else (run_id,)
                    cursor.execute(sql, params)
        if execute:
            conn.commit()
            mode = "execute"
        else:
            mode = "dry_run"
        return {"mode": mode, "counts": counts}
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        if isinstance(exc, (DuplicateRunError, DriverUnavailableError)):
            raise
        state = getattr(exc, "sqlstate", None)
        raise DatabaseOperationError(type(exc).__name__, str(state) if state else None) from None
    finally:
        if conn is not None:
            conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--skip-existing-nodes", action="store_true")
    parser.add_argument("--delete-run")
    args = parser.parse_args(argv)
    try:
        if args.delete_run is not None:
            result = delete_run(args.delete_run, execute=args.execute)
        else:
            if not args.csv_dir:
                parser.error("--csv-dir is required unless --delete-run is used")
            result = load_csvs(args.csv_dir, execute=args.execute, skip_existing_nodes=args.skip_existing_nodes)
    except Exception as exc:
        # Never serialize exception text or connection details.
        state = getattr(exc, "sqlstate", None)
        detail = {"error": getattr(exc, "exception_class", type(exc).__name__)}
        if state:
            detail["sqlstate"] = str(state)
        if isinstance(exc, DriverUnavailableError):
            detail["hint"] = "Install psycopg[binary,pool]."
        print(json.dumps(detail), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
