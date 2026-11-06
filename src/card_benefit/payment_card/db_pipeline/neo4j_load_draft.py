"""Replace only this project's dp_ graph with the PostgreSQL relational read model."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from common.neo4j_connection import create_neo4j_driver
from .neo4j_relational_model import PREFIX, build, load_snapshot

EXPECTED_DB = "6ac1f0f8"
EXPECTED_POSTGRES_DB = "postgres"
CONFIRM = "APPROVED_DP_POSTGRES_REBUILD"
BACKUP_PATH = Path("tmp/neo4j_dp_backup_20261106.json.gz")
BACKUP_SHA256 = "2d639a26cce270aa679b418b401b45c245ce7681675dffb92740cf3648102189"


def _ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"unsafe schema identifier {name!r}")
    return "`" + name + "`"


def prepare(snapshot: dict) -> dict:
    return build(snapshot)


def _make_constraints(session, model: dict):
    session.run("CREATE CONSTRAINT dp_node_key IF NOT EXISTS FOR (n:dp_node) REQUIRE n.key IS UNIQUE").consume()
    included = {node["table"] for node in model["nodes"]}
    for table_name, table in sorted(model["table_map"].items()):
        if table_name not in included:
            continue
        label = _ident(PREFIX + table_name)
        name = _ident("dp_" + table_name + "_pk")
        fields = ",".join("n." + _ident(field) for field in table["pk"])
        session.run(f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE ({fields}) IS NODE KEY").consume()


def _create_indexes(session, model: dict):
    session.run("CREATE FULLTEXT INDEX dp_card_product_item_text IF NOT EXISTS FOR (n:dp_card_product_item) "
                "ON EACH [n.item_nm,n.item_rule_txt,n.item_limit_txt,n.item_search_txt]").consume()
    session.run("CREATE FULLTEXT INDEX dp_card_common_bnft_text IF NOT EXISTS FOR (n:dp_card_common_bnft) "
                "ON EACH [n.bnft_nm,n.bnft_rule_txt,n.bnft_limit_txt]").consume()
    dimensions = set()
    for node in model["nodes"]:
        embedding = node["props"].get("embedding")
        if embedding is not None:
            dimensions.add(len(embedding))
    if dimensions and dimensions != {1536}:
        raise ValueError(f"expected reusable 1536-dimensional source embeddings; found {sorted(dimensions)}")
    for table, prop in (("card_product_item", "embedding"), ("card_common_bnft", "embedding")):
        if not any(node["table"] == table and node["props"].get(prop) is not None for node in model["nodes"]):
            continue
        if len(dimensions) != 1:
            raise ValueError(f"embedding dimensions are inconsistent: {sorted(dimensions)}")
        name, label = _ident(f"dp_{table}_embedding"), _ident(PREFIX + table)
        prop_ident = _ident(prop)
        dimension = next(iter(dimensions))
        session.run(f"CREATE VECTOR INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{prop_ident}) "
                    f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}").consume()


def _write_nodes(tx, label: str, nodes: list[dict]):
    result = tx.run(f"UNWIND $rows AS row MERGE (n:dp_node:{_ident(label)} {{key:row.key}}) "
                    "SET n += row.props RETURN count(n) AS n", rows=[{"key": n["key"], "props": n["props"]} for n in nodes]).single(strict=True)
    if result["n"] != len(nodes):
        raise ValueError(f"node count mismatch for {label}: {result['n']} != {len(nodes)}")
    return result["n"]


def _write_relationships(tx, rel_type: str, edges: list[dict]):
    result = tx.run(f"UNWIND $rows AS row MATCH (a:dp_node {{key:row.start}}),(b:dp_node {{key:row.end}}) "
                    f"MERGE (a)-[r:{_ident(rel_type)} {{key:row.key}}]->(b) SET r += row.props RETURN count(r) AS n",
                    rows=[{"key": e["key"], "start": e["start"], "end": e["end"], "props": e["props"]} for e in edges]).single(strict=True)
    if result["n"] != len(edges):
        raise ValueError(f"relationship endpoint/count mismatch for {rel_type}: {result['n']} != {len(edges)}")
    return result["n"]


def write_transaction(tx, model: dict):
    node_counts = {}
    by_label = {}
    for node in model["nodes"]:
        by_label.setdefault(PREFIX + node["table"], []).append(node)
    for label, nodes in sorted(by_label.items()):
        node_counts[label] = _write_nodes(tx, label, nodes)
    rel_counts = {}
    by_type = {}
    for edge in model["relationships"]:
        by_type.setdefault(edge["type"], []).append(edge)
    for rel_type, edges in sorted(by_type.items()):
        rel_counts[rel_type] = _write_relationships(tx, rel_type, edges)
    actual_nodes = tx.run("MATCH (n:dp_node) RETURN count(n) AS n").single(strict=True)["n"]
    actual_rels = tx.run("MATCH (:dp_node)-[r]->(:dp_node) WHERE type(r) STARTS WITH 'dp_' RETURN count(r) AS n").single(strict=True)["n"]
    if actual_nodes != len(model["nodes"]) or actual_rels != len(model["relationships"]):
        raise ValueError(f"postcondition mismatch nodes={actual_nodes}/{len(model['nodes'])}, rels={actual_rels}/{len(model['relationships'])}")
    return {"nodes": actual_nodes, "relationships": actual_rels,
            "node_counts": node_counts, "relationship_counts": rel_counts}


def _backup_matches():
    if not BACKUP_PATH.is_file():
        raise SystemExit(f"recovery backup missing: {BACKUP_PATH}")
    digest = hashlib.sha256(BACKUP_PATH.read_bytes()).hexdigest()
    if digest != BACKUP_SHA256:
        raise SystemExit(f"recovery backup checksum verification failed: {digest}")
    with gzip.open(BACKUP_PATH, "rt", encoding="utf-8") as stream:
        backup = json.load(stream)
    if (backup.get("database") != EXPECTED_DB or len(backup.get("nodes", [])) != 1635
            or len(backup.get("relationships", [])) != 2702
            or len(backup.get("constraints", [])) != 15 or len(backup.get("indexes", [])) != 19):
        raise SystemExit("recovery backup identity/count verification failed")
    return {"sha256": digest, "nodes": len(backup["nodes"]), "relationships": len(backup["relationships"]),
            "constraints": len(backup.get("constraints", [])), "indexes": len(backup.get("indexes", []))}


def _safe_clear(session) -> dict:
    database = os.getenv("NEO4J_DATABASE")
    if database != EXPECTED_DB:
        raise SystemExit(f"unexpected Neo4j database: {database!r}")
    outside = session.run("""MATCH (n)-[r]-(m)
        WHERE any(label IN labels(n) WHERE label STARTS WITH 'dp_')
          AND none(label IN labels(m) WHERE label STARTS WITH 'dp_')
        RETURN count(r) AS n""").single(strict=True)["n"]
    if outside:
        raise SystemExit(f"dp_ graph has relationships outside project scope: {outside}")
    before = session.run("""MATCH (n) WHERE any(label IN labels(n) WHERE label STARTS WITH 'dp_')
        WITH count(n) AS nodes MATCH ()-[r]->() WHERE type(r) STARTS WITH 'dp_'
        RETURN nodes,count(r) AS relationships""").single(strict=True)
    constraints = [r["name"] for r in session.run("SHOW CONSTRAINTS YIELD name RETURN name") if r["name"].startswith("dp_")]
    indexes = [r["name"] for r in session.run("SHOW INDEXES YIELD name RETURN name") if r["name"].startswith("dp_")]
    for name in constraints:
        session.run(f"DROP CONSTRAINT {_ident(name)} IF EXISTS").consume()
    for name in indexes:
        session.run(f"DROP INDEX {_ident(name)} IF EXISTS").consume()
    session.run("MATCH (n) WHERE any(label IN labels(n) WHERE label STARTS WITH 'dp_') DETACH DELETE n").consume()
    remaining_nodes = session.run("MATCH (n) WHERE any(label IN labels(n) WHERE label STARTS WITH 'dp_') RETURN count(n) AS n").single(strict=True)["n"]
    remaining_rels = session.run("MATCH ()-[r]->() WHERE type(r) STARTS WITH 'dp_' RETURN count(r) AS n").single(strict=True)["n"]
    if remaining_nodes or remaining_rels:
        raise ValueError(f"dp_ clear incomplete: nodes={remaining_nodes}, relationships={remaining_rels}")
    return {"before_nodes": before["nodes"], "before_relationships": before["relationships"],
            "dropped_constraints": constraints, "dropped_indexes": indexes, "outside_relationships": outside}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="drop and rebuild only dp_ objects")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
        snapshot = load_snapshot(conn)
    if snapshot["identity"]["database"] != EXPECTED_POSTGRES_DB:
        raise SystemExit(f"unexpected PostgreSQL database: {snapshot['identity']['database']}")
    model = prepare(snapshot)
    if not args.apply:
        print(json.dumps({"mode": "PREVIEW", "postgres": snapshot["identity"], "expected_neo4j": EXPECTED_DB,
                          "backup": str(BACKUP_PATH), "backup_counts": _backup_matches(), **model["stats"]},
                         ensure_ascii=False, default=str, indent=2))
        return
    if args.confirm != CONFIRM or os.getenv("NEO4J_DATABASE") != EXPECTED_DB:
        raise SystemExit("explicit confirmation token and exact project database are required")
    _backup_matches()
    with create_neo4j_driver() as driver, driver.session(database=EXPECTED_DB) as session:
        identity_row = session.run("CALL db.info() YIELD name,id RETURN name,id").single(strict=True)
        identity = identity_row["name"]
        if identity != EXPECTED_DB:
            raise SystemExit(f"unexpected Neo4j identity: {identity_row}")
        cleared = _safe_clear(session)
        _make_constraints(session, model)
        result = session.execute_write(write_transaction, model)
        _create_indexes(session, model)
        from .neo4j_validate import validate_live
        validation = validate_live(model, session)
        if not validation["ok"]:
            print(json.dumps({"mode": "APPLY_VALIDATION_FAILED", "database": identity,
                              "clear": cleared, "load": result, "validation": validation},
                             ensure_ascii=False, default=str, indent=2))
            raise SystemExit(1)
        print(json.dumps({"mode": "APPLIED", "database": identity, "clear": cleared,
                          "load": result, "validation": {"ok": validation["ok"], "actual": validation["actual"],
                          "constraints_ok": validation["constraints_ok"], "indexes_ok": validation["indexes_ok"]}},
                         ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
