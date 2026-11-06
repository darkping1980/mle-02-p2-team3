"""Read-only preview of the PostgreSQL-table-faithful ``dp_`` graph."""
from __future__ import annotations

import argparse
import json
import os

import psycopg
from dotenv import load_dotenv

from .neo4j_relational_model import EXCLUDED_TABLES, PREFIX, build, inspect_schema, load_snapshot


class GraphValidationError(ValueError):
    """A source row or FK could not be mapped without loss."""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="required; never writes Neo4j")
    parser.add_argument("--schema-only", action="store_true", help="show actual PostgreSQL mapping metadata")
    args = parser.parse_args()
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
        if args.schema_only:
            schema = inspect_schema(conn)
            output = {"identity": schema["identity"],
                      "tables": [{"name": t["name"], "type": t["type"], "pk": t["pk"],
                                  "columns": [{"name": c["column_name"], "type": c["udt_name"], "nullable": c["is_nullable"]}
                                              for c in t["columns"]], "fks": t["fks"]} for t in schema["tables"]]}
            print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
            return
        if not args.dry_run:
            parser.error("--dry-run is required; use neo4j_load_draft.py for an explicit apply")
        snapshot = load_snapshot(conn)
    model = build(snapshot)
    print(json.dumps({"mode": "DRY_RUN", "postgres": snapshot["identity"],
                      "base_table_count": sum(t["type"] == "BASE TABLE" for t in snapshot["tables"]),
                      "views_excluded": [t["name"] for t in snapshot["views"]],
                      "tables_excluded": snapshot["excluded"],
                      "tables_included": sorted(snapshot["rows"]), **model["stats"],
                      "pk_fk_mapping": {name: {"pk": table["pk"], "fks": table["fks"]}
                                        for name, table in model["table_map"].items() if name in snapshot["rows"]}},
                     ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
