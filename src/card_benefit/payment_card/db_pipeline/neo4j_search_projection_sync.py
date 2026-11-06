"""Deprecated legacy projection sync entry point.

Search text and vectors are projected while building each PostgreSQL source-row
node. The former incremental sync targeted the retired ``dp_card_bnft`` model
and is intentionally disabled.
"""

def main():
    raise SystemExit("legacy projection sync is disabled; use neo4j_load_draft --dry-run")


if __name__ == "__main__":
    main()
