"""Deprecated legacy relationship-only sync entry point.

The table-faithful graph is rebuilt atomically from the PostgreSQL snapshot by
``neo4j_load_draft``. Incremental legacy relationship synchronization could
reintroduce edges to removed rule nodes, so it now fails closed.
"""

def main():
    raise SystemExit("legacy relationship sync is disabled; use neo4j_load_draft --dry-run")


if __name__ == "__main__":
    main()
