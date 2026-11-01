"""Read-only V6 -> isolated in-memory graph preview; never connects to Neo4j."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

NS = "ONE_PICK_STYLE_A8"
CARD_ID = 2
POLICY_ID = "20261101_000001"
DOC_ID = "20261101_000002"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def key(label, *parts):
    # JSON array encoding avoids separator collisions and retains component boundaries.
    return canonical([NS, label, *parts])


class Preview:
    def __init__(self):
        self.nodes = {}
        self.edges = {}

    def node(self, label, parts, data):
        k = key(label, *parts)
        entry = {"label": "A8" + label, "key": k, "namespace": NS,
                 "source_json": canonical(data), "test_only": True}
        if k in self.nodes and self.nodes[k] != entry:
            raise ValueError(f"conflicting node: {k}")
        self.nodes[k] = entry
        return k

    def edge(self, kind, start, end, source):
        k = key("relationship", kind, start, end, source)
        if k in self.edges:
            raise ValueError(f"duplicate edge: {k}")
        self.edges[k] = {"type": "A8_" + kind, "start": start, "end": end,
                         "source_json": canonical(source), "namespace": NS}

    def validate(self):
        dangling = [k for k, e in self.edges.items()
                    if e["start"] not in self.nodes or e["end"] not in self.nodes]
        if dangling:
            raise ValueError(f"dangling edges: {len(dangling)}")
        return {"nodes": dict(sorted(Counter(n["label"] for n in self.nodes.values()).items())),
                "relationships": dict(sorted(Counter(e["type"] for e in self.edges.values()).items())),
                "node_total": len(self.nodes), "relationship_total": len(self.edges),
                "dangling_edges": len(dangling)}


def load_snapshot(conn):
    # One read-only REPEATABLE READ snapshot; only explicitly scoped source rows.
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        out = {}
        queries = {
            "product": ("SELECT * FROM db_pipeline.card_product WHERE card_id=%s", (CARD_ID,)),
            "policy": ("SELECT * FROM db_pipeline.card_policy_version WHERE card_id=%s AND policy_ver_id=%s", (CARD_ID, POLICY_ID)),
            "product_doc": ("SELECT * FROM db_pipeline.card_product_doc WHERE card_id=%s AND card_doc_id=%s", (CARD_ID, DOC_ID)),
            "benefits": ("SELECT * FROM db_pipeline.card_bnft WHERE card_id=%s AND policy_ver_id=%s ORDER BY card_bnft_id", (CARD_ID, POLICY_ID)),
            "pools": ("SELECT * FROM db_pipeline.card_limit_pool WHERE card_id=%s AND policy_ver_id=%s ORDER BY pool_id", (CARD_ID, POLICY_ID)),
            "links": ("SELECT * FROM db_pipeline.card_policy_evidence WHERE card_id=%s AND policy_ver_id=%s ORDER BY ev_link_id", (CARD_ID, POLICY_ID)),
            "evidence": ("SELECT * FROM db_pipeline.card_source_evidence WHERE card_doc_id=%s ORDER BY evidence_id", (DOC_ID,)),
            "chunks": ("SELECT * FROM db_pipeline.card_doc_chunk WHERE card_doc_id=%s ORDER BY page_no,card_doc_chunk_id", (DOC_ID,)),
            "pages": ("SELECT * FROM db_pipeline.card_doc_page WHERE card_doc_id=%s ORDER BY page_no", (DOC_ID,)),
            "document": ("SELECT * FROM db_pipeline.card_doc WHERE card_doc_id=%s", (DOC_ID,)),
        }
        for name, (sql, params) in queries.items():
            cur.execute(sql, params)
            out[name] = cur.fetchall()
        return out


def one(rows, name):
    if len(rows) != 1:
        raise ValueError(f"expected one {name}, got {len(rows)}")
    return rows[0]


def build(snapshot):
    g = Preview()
    product = one(snapshot["product"], "product")
    policy = one(snapshot["policy"], "policy")
    product_doc = one(snapshot["product_doc"], "product_doc")
    document = one(snapshot["document"], "document")
    if policy["policy_status_cd"] != "DRAFT":
        raise ValueError("expected DRAFT policy")
    c = g.node("Card", [CARD_ID], product)
    p = g.node("Policy", [CARD_ID, POLICY_ID], {"source": policy, "valid_from_is_assumption": True, "product_doc": product_doc})
    g.edge("HAS_POLICY", c, p, {})
    doc = g.node("Document", [DOC_ID], document)
    pages, chunks, evidence, pools, benefits, rules = {}, {}, {}, {}, {}, {}
    for row in snapshot["pages"]:
        pg = g.node("Page", [DOC_ID, row["page_no"]], row); pages[row["page_no"]] = pg
        g.edge("IN_DOCUMENT", pg, doc, {})
    for row in snapshot["chunks"]:
        k = row["card_doc_chunk_id"]
        chunk = g.node("Chunk", [DOC_ID, row["page_no"], k], row); chunks[k] = chunk
        g.edge("ON_PAGE", chunk, pages[row["page_no"]], {})
    for row in snapshot["evidence"]:
        match = [x for x in snapshot["chunks"] if x["card_doc_chunk_id"] == row["card_doc_chunk_id"]
                 and x["card_doc_id"] == row["card_doc_id"] and x["page_no"] == row["page_no"]]
        if len(match) != 1:
            raise ValueError("evidence references missing or mismatched chunk")
        ev = g.node("Evidence", [row["evidence_id"]], row); evidence[row["evidence_id"]] = ev
        g.edge("IN_CHUNK", ev, chunks[row["card_doc_chunk_id"]], {})
    for row in snapshot["pools"]:
        pools[row["pool_id"]] = g.node("LimitPool", [CARD_ID, POLICY_ID, row["pool_id"]], {"source": row, "aggregation_is_assumption": True})

    def expression(owner, owner_key, expr):
        if expr is None:
            return
        ex = g.node("Expression", [*owner_key], expr); g.edge("HAS_EXPR", owner, ex, {})
        for branch in expr["branches"]:
            bk = [*owner_key, branch["branch_no"]]
            b = g.node("Branch", bk, branch); g.edge("HAS_BRANCH", ex, b, {})
            for atom in branch["atoms"]:
                a = g.node("Condition", [*bk, atom["atom_key"]], atom)
                g.edge("HAS_ATOM", b, a, {"atom_seq": atom["atom_seq"]})

    expression(p, ["policy", CARD_ID, POLICY_ID], policy["policy_cond_expr"])
    for row in snapshot["benefits"]:
        bid = row["card_bnft_id"]
        b = g.node("Benefit", [CARD_ID, POLICY_ID, bid], row); benefits[bid] = b
        g.edge("HAS_BENEFIT", p, b, {})
        expression(b, ["benefit", CARD_ID, POLICY_ID, bid], row["bnft_cond_expr"])
        for rule in row["rule_list"]:
            rk = rule["rule_key"]
            r = g.node("Rule", [CARD_ID, POLICY_ID, bid, rk], rule); g.edge("HAS_RULE", b, r, {})
            rules[(bid, rk)] = r
            expression(r, ["rule", CARD_ID, POLICY_ID, bid, rk], rule.get("cond_expr"))
            for target in rule["target_list"]:
                t = g.node("Target", [CARD_ID, POLICY_ID, target["target_type_cd"], target["target_nm"]],
                           {"target_type_cd": target["target_type_cd"], "target_nm": target["target_nm"]})
                g.edge("TARGETS", r, t, target)
            for ref in rule["pool_refs"]:
                g.edge("CONSUMES", r, pools[ref["pool_id"]], ref)
    for link in snapshot["links"]:
        subject = link["ev_subject_cd"]
        if subject == "POLICY": owner = p
        elif subject == "BNFT": owner = benefits[link["card_bnft_id"]]
        elif subject == "RULE": owner = rules[(link["card_bnft_id"], link["rule_key"])]
        elif subject == "POOL": owner = pools[link["pool_id"]]
        else: raise ValueError(f"unsupported evidence subject: {subject}")
        g.edge("SUPPORTED_BY", owner, evidence[link["evidence_id"]], link)
    stats = g.validate()
    # Check source/preview coverage independently of expected historic counts.
    for label, rows in (("Evidence", snapshot["evidence"]), ("LimitPool", snapshot["pools"]),
                        ("Benefit", snapshot["benefits"])):
        if stats["nodes"].get("A8" + label, 0) != len(rows):
            raise ValueError(f"source count mismatch: {label}")
    if stats["relationships"].get("A8_SUPPORTED_BY", 0) != len(snapshot["links"]):
        raise ValueError("source count mismatch: evidence links")
    for row in snapshot["benefits"]:
        for rule in row["rule_list"]:
            rk = key("Rule", CARD_ID, POLICY_ID, row["card_bnft_id"], rule["rule_key"])
            if json.loads(g.nodes[rk]["source_json"]) != rule:
                raise ValueError("rule JSON mismatch")
    for row in snapshot["benefits"]:
        for owner_key, expr in [(["benefit", CARD_ID, POLICY_ID, row["card_bnft_id"]], row["bnft_cond_expr"])]:
            if expr is not None and json.loads(g.nodes[key("Expression", *owner_key)]["source_json"]) != expr:
                raise ValueError("benefit condition JSON mismatch")
    return g, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args()
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
        snapshot = load_snapshot(conn)
        graph, stats = build(snapshot)
    stats["snapshot_sha256"] = hashlib.sha256(canonical(snapshot).encode()).hexdigest()
    stats["source"] = {"card_id": CARD_ID, "policy_ver_id": POLICY_ID, "card_doc_id": DOC_ID}
    stats["neo4j_writes"] = 0
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
