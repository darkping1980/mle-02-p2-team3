"""Read-only PostgreSQL-to-Neo4j full-model comparison."""
from __future__ import annotations

import json
import os
from collections import Counter

import psycopg
from dotenv import load_dotenv
from neo4j import READ_ACCESS

from common.neo4j_connection import create_neo4j_driver
from .neo4j_load_draft import EXPECTED_DB
from .neo4j_relational_model import PREFIX, build, load_snapshot


def compare_graph(model: dict, graph_nodes: list[dict], graph_edges: list[dict]) -> dict:
    expected_nodes = {item["key"]: item for item in model["nodes"]}
    actual_nodes = {item["key"]: item for item in graph_nodes}
    expected_edges = {item["key"]: item for item in model["relationships"]}
    actual_edges = {item["key"]: item for item in graph_edges}
    node_missing = sorted(set(expected_nodes) - set(actual_nodes))
    node_extra = sorted(set(actual_nodes) - set(expected_nodes))
    edge_missing = sorted(set(expected_edges) - set(actual_edges))
    edge_extra = sorted(set(actual_edges) - set(expected_edges))
    node_differences, edge_differences = [], []
    for key in sorted(set(expected_nodes) & set(actual_nodes)):
        expected, actual = expected_nodes[key], actual_nodes[key]
        if set(actual.get("labels", [])) != {"dp_node", expected["label"]}:
            node_differences.append({"key": key, "field": "labels", "expected": sorted({"dp_node", expected["label"]}),
                                     "actual": sorted(actual.get("labels", []))})
        for field, value in expected["props"].items():
            if actual.get("props", {}).get(field) != value:
                node_differences.append({"key": key, "field": field, "expected": value,
                                         "actual": actual.get("props", {}).get(field)})
    for key in sorted(set(expected_edges) & set(actual_edges)):
        expected, actual = expected_edges[key], actual_edges[key]
        fields = {"type": expected["type"], "start": expected["start"], "end": expected["end"], **expected["props"]}
        actual_values = {**actual.get("props", {}), "type": actual.get("type"),
                         "start": actual.get("start"), "end": actual.get("end")}
        for field, value in fields.items():
            if actual_values.get(field) != value:
                edge_differences.append({"key": key, "field": field, "expected": value, "actual": actual_values.get(field)})
    return {"nodes_missing": node_missing, "nodes_extra": node_extra, "relationships_missing": edge_missing,
            "relationships_extra": edge_extra, "node_property_differences": node_differences,
            "relationship_property_differences": edge_differences,
            "node_counts_by_table": dict(Counter(n["table"] for n in model["nodes"])),
            "relationship_counts_by_source": model["stats"]["relationship_counts"]}


def read_graph(session) -> tuple[list[dict], list[dict]]:
    nodes = [record.data() for record in session.run("""MATCH (n:dp_node)
      RETURN n.key AS key,labels(n) AS labels,properties(n) AS props ORDER BY n.key""")]
    edges = [record.data() for record in session.run("""MATCH (a:dp_node)-[r]->(b:dp_node)
      WHERE type(r) STARTS WITH 'dp_'
      RETURN r.key AS key,type(r) AS type,a.key AS start,b.key AS end,properties(r) AS props ORDER BY r.key""")]
    return nodes, edges


def validate_live(model: dict, session) -> dict:
    graph_nodes, graph_edges = read_graph(session)
    differences = compare_graph(model, graph_nodes, graph_edges)
    isolated = session.run("""MATCH (n:dp_node) WHERE NOT (n)--() RETURN count(n) AS n""").single(strict=True)["n"]
    external = session.run("""MATCH (n)-[r]-(m) WHERE any(l IN labels(n) WHERE l STARTS WITH 'dp_')
      AND none(l IN labels(m) WHERE l STARTS WITH 'dp_') RETURN count(r) AS n""").single(strict=True)["n"]
    labels = [r.data() for r in session.run("MATCH (n:dp_node) UNWIND labels(n) AS label WITH label,count(*) AS n RETURN label,n ORDER BY label")]
    relationships = [r.data() for r in session.run("MATCH (:dp_node)-[r]->(:dp_node) WHERE type(r) STARTS WITH 'dp_' RETURN type(r) AS type,count(*) AS n ORDER BY type")]
    indexes = [r.data() for r in session.run("SHOW INDEXES YIELD name,type,state,labelsOrTypes,properties,options RETURN name,type,state,labelsOrTypes,properties,options") if r["name"].startswith("dp_")]
    constraints = [r.data() for r in session.run("SHOW CONSTRAINTS YIELD name,type,entityType,labelsOrTypes,properties RETURN name,type,entityType,labelsOrTypes,properties") if r["name"].startswith("dp_")]
    required_nodes = {n["table"] for n in model["nodes"]}
    names = {index["name"] for index in indexes}
    required_indexes = {"dp_card_product_item_text", "dp_card_common_bnft_text"}
    vector_tables = {n["table"] for n in model["nodes"] if n["props"].get("embedding") is not None}
    vector_expected = {f"dp_{table}_embedding" for table in vector_tables}
    vector_indexes = {index["name"]: index for index in indexes if index["type"] == "VECTOR"}
    required_constraints = {"dp_node_key", *(f"dp_{table}_pk" for table in required_nodes)}
    online = all(index["state"] == "ONLINE" for index in indexes)
    constraints_ok = required_constraints <= {c["name"] for c in constraints}
    vector_ok = vector_expected == set(vector_indexes) and all(
        index["state"] == "ONLINE"
        and index.get("options", {}).get("indexConfig", {}).get("vector.dimensions") == 1536
        and index.get("options", {}).get("indexConfig", {}).get("vector.similarity_function", "COSINE").upper() == "COSINE"
        for index in vector_indexes.values())
    index_ok = required_indexes <= names and online and vector_ok
    exact = not any(differences[k] for k in ("nodes_missing", "nodes_extra", "relationships_missing", "relationships_extra",
                                               "node_property_differences", "relationship_property_differences"))
    return {"expected": {"nodes": len(model["nodes"]), "relationships": len(model["relationships"])},
            "actual": {"nodes": len(graph_nodes), "relationships": len(graph_edges)},
            "labels": labels, "relationships_by_type": relationships, "constraints": constraints, "indexes": indexes,
            "isolated_nodes": isolated, "external_relationships": external, "exact_source_match": exact,
            "constraints_ok": constraints_ok, "indexes_ok": index_ok, "differences": differences,
            "ok": exact and constraints_ok and index_ok and external == 0}


def run() -> dict:
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
        snapshot = load_snapshot(conn)
    if snapshot["identity"]["database"] != "postgres":
        raise SystemExit(f"unexpected PostgreSQL database {snapshot['identity']['database']}")
    model = build(snapshot)
    if os.getenv("NEO4J_DATABASE") != EXPECTED_DB:
        raise SystemExit(f"unexpected Neo4j database {os.getenv('NEO4J_DATABASE')!r}")
    with create_neo4j_driver() as driver, driver.session(database=EXPECTED_DB, default_access_mode=READ_ACCESS) as session:
        return validate_live(model, session)


def main():
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
