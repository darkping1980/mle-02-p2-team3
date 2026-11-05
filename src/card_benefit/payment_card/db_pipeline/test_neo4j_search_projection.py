"""검색 투영(공통 혜택 근거·임베딩·동일성 판정 상태) 변환·동기화 테스트. 실제 DB에 접속하지 않는다."""
import copy
import json
import re
import unittest

from card_benefit.payment_card.db_pipeline import neo4j_search_projection_sync as sync
from card_benefit.payment_card.db_pipeline.neo4j_dry_run import (
    COMMON_LINK_SOURCE, EMBEDDING_DIM, GraphValidationError, PROJECTION_PROPS, build, key)
from card_benefit.payment_card.db_pipeline.neo4j_load_draft import CYPHER, prepare, relationship_properties
from card_benefit.payment_card.db_pipeline.neo4j_validate import compare_graph
from card_benefit.payment_card.db_pipeline.test_neo4j_dry_run import COMMON_DOC, fixture

VECTOR = [0.001 * i for i in range(EMBEDDING_DIM)]
RUN = {"card_ai_run_id": "RUN1", "run_model_nm": "text-embedding-3-small"}


def projected(**changes):
    """기본 fixture + 공통 문서 페이지·청크·추출 근거 2건 + 임베딩 2건 + 동일성 판정 1건."""
    data = fixture()
    data["pages"].append({"card_doc_id": COMMON_DOC, "page_no": 1})
    data["chunks"].append({"card_doc_id": COMMON_DOC, "page_no": 1, "card_doc_chunk_id": "cchunk"})
    data["evidence"] += [{"card_doc_id": COMMON_DOC, "page_no": 1, "card_doc_chunk_id": "cchunk", "evidence_id": f"cev{i}",
                          "approval_status_cd": "PENDING", "quote_txt": f"공통 근거 {i}"} for i in (1, 2)]
    data["common_evidence_links"] = [{"card_common_id": 1, "card_common_bnft_id": "C1", "evidence_id": "cev1"},
                                     {"card_common_id": 1, "card_common_bnft_id": "C1", "evidence_id": "cev2"}]
    data["search_projection"] = {"benefits": [{"card_id": 2, "card_bnft_id": "benefit", "embedding": list(VECTOR), "search_text": "혜택명: A"}],
                                 "common_benefits": [{"card_common_id": 1, "card_common_bnft_id": "C1", "embedding": list(VECTOR),
                                                      "search_text": "혜택명: 컨시어지"}]}
    data["embedding_run"] = dict(RUN)
    data["brand_compare"] = [{"card_id": 5, "card_bnft_id": "other", "bnft_cd": "x", "card_common_id": None,
                              "card_common_bnft_id": None, "status": "NO_COMMON", "issues": ["공통 혜택 없음"]}]
    data.update(changes)
    return data


def base_graph():
    """현재 운영과 같은 상태: 투영 없음(근거·속성이 아직 없는 그래프)."""
    data = projected(common_evidence_links=[], search_projection={"benefits": [], "common_benefits": []}, brand_compare=[])
    return prepare(build(data)[0])


def as_found(nodes, edges):
    """기준 그래프를 Neo4j에서 읽은 행 형태로 만든다(적재기와 같은 규칙)."""
    found_nodes = [{"key": n["props"]["key"], "labels": ["dp_node", n["label"]] + (["dp_card_product_item"] if n["label"] == "dp_card_bnft" else []),
                    "props": copy.deepcopy(n["props"])} for n in nodes]
    found_edges = [{"key": e["key"], "type": e["type"], "start": e["start"], "end": e["end"], "source_json": e["source_json"],
                    "props": {"key": e["key"], "source_json": e["source_json"], **relationship_properties(e)}} for e in edges]
    return found_nodes, found_edges


class Record:
    def __init__(self, row): self.row = row
    def data(self): return dict(self.row)


class Result:
    def __init__(self, rows): self.rows = rows
    def __iter__(self): return iter(Record(r) for r in self.rows)
    def single(self, strict=True): return self.rows[0]


class FakeTx:
    """읽기 구문(node_sources·relationship_sources)과 투영 쓰기 구문만 해석하는 메모리 그래프."""

    def __init__(self, nodes, edges):
        self.nodes = {n["key"]: copy.deepcopy(n) for n in nodes}
        self.edges = {e["key"]: copy.deepcopy(e) for e in edges}
        self.writes = []

    def run(self, query, **params):
        if query == CYPHER["neo4j_validation.node_sources"]:
            return Result([copy.deepcopy(n) for n in self.nodes.values()])
        if query == CYPHER["neo4j_validation.relationship_sources"]:
            return Result([copy.deepcopy(e) for e in self.edges.values()])
        name = re.match(r"// projection:(\w+)", query).group(1)
        self.writes.append(name)
        n = 0
        if name == "create_evidence":
            for row in params["rows"]:
                self.nodes[row["props"]["key"]] = {"key": row["props"]["key"], "labels": ["dp_node", "dp_card_source_evidence"],
                                                   "props": dict(row["props"])}; n += 1
        elif name.startswith("merge_"):
            for row in params["rows"]:
                if row["start"] in self.nodes and row["end"] in self.nodes:
                    self.edges[row["key"]] = {"key": row["key"], "type": "dp_" + name[6:], "start": row["start"], "end": row["end"],
                                              "source_json": row["source_json"],
                                              "props": {"key": row["key"], "source_json": row["source_json"], **row["extra"]}}; n += 1
        elif name == "update_links":
            for row in params["rows"]:
                self.edges[row["key"]]["props"] = dict(row["props"]); n += 1
        elif name == "delete_links":
            for k in params["keys"]:
                if self.edges.get(k, {}).get("props", {}).get("link_source") == COMMON_LINK_SOURCE:
                    del self.edges[k]; n += 1
        elif name == "delete_evidence":
            for k in params["keys"]:
                if not any(e["end"] == k and e["type"] == "dp_supported_by" for e in self.edges.values()):
                    del self.nodes[k]; n += 1
                    for ek in [ek for ek, e in self.edges.items() if k in (e["start"], e["end"])]:
                        del self.edges[ek]
        elif name == "set_props":
            for row in params["rows"]:
                props = self.nodes[row["key"]]["props"]
                for field, value in row["props"].items():
                    props.pop(field, None) if value is None else props.__setitem__(field, value)
                n += 1
        return Result([{"n": n}])


class BuildProjectionTests(unittest.TestCase):
    def test_common_evidence_becomes_supported_by_with_source_marker(self):
        graph, stats = build(projected())
        links = [e for e in graph.edges.values() if e["type"] == "dp_supported_by" and "link_source" in e["source_json"]]
        self.assertEqual(len(links), 2)
        source = json.loads(links[0]["source_json"])
        self.assertEqual((source["link_source"], source["ev_subject_cd"], source["ev_item_key"]), (COMMON_LINK_SOURCE, "BNFT", "-"))
        self.assertEqual(links[0]["start"], key("card_common_bnft", 1, "C1"))
        self.assertIn(key("card_source_evidence", "cev1"), graph.nodes)
        self.assertTrue(any(e["type"] == "dp_in_chunk" and e["start"] == key("card_source_evidence", "cev1") for e in graph.edges.values()))
        self.assertEqual(stats["search_projection"]["common_evidence_only_nodes"], 2)
        self.assertEqual(stats["common_benefits_without_direct_evidence"], [])

    def test_existing_linked_evidence_is_reused_not_duplicated(self):
        data = projected(common_evidence_links=[{"card_common_id": 1, "card_common_bnft_id": "C1", "evidence_id": "ev"}])
        graph, _ = build(data)
        self.assertEqual(sum(1 for n in graph.nodes.values() if n["label"] == "dp_card_source_evidence"), 1)

    def test_embedding_and_brand_status_are_separate_from_source_json(self):
        graph, _ = build(projected())
        bnft = graph.nodes[key("card_bnft", 2, "benefit")]
        self.assertEqual(bnft["search"]["embedding"], VECTOR)
        self.assertEqual((bnft["search"]["embedding_model"], bnft["search"]["embedding_run_id"], bnft["search"]["embedding_dim"]),
                         ("text-embedding-3-small", "RUN1", EMBEDDING_DIM))
        self.assertNotIn("embedding", bnft["source_json"])                   # 원본 JSON은 그대로
        other = graph.nodes[key("card_bnft", 5, "other")]["search"]
        self.assertEqual((other["brand_compare_status"], json.loads(other["brand_compare_issues"])), ("NO_COMMON", ["공통 혜택 없음"]))
        self.assertNotIn("brand_compare_common_key", other)
        self.assertTrue(set(bnft["search"]) <= set(PROJECTION_PROPS))

    def test_invalid_projection_is_reported(self):
        cases = [projected(embedding_run=None),
                 projected(search_projection={"benefits": [{"card_id": 2, "card_bnft_id": "benefit", "embedding": [1.0], "search_text": "x"}],
                                              "common_benefits": []}),
                 projected(common_evidence_links=[{"card_common_id": 1, "card_common_bnft_id": "NOPE", "evidence_id": "cev1"}])]
        for data in cases:
            with self.assertRaises(GraphValidationError):
                build(data)

    def test_evidence_without_chunk_is_reported(self):
        data = projected()
        data["chunks"] = data["chunks"][:1]
        with self.assertRaisesRegex(GraphValidationError, "청크 없음"):
            build(data)


class LoaderPropertyTests(unittest.TestCase):
    def test_prepare_carries_search_props_and_link_fields(self):
        nodes, edges = prepare(build(projected())[0])
        bnft = next(n for n in nodes if n["props"]["key"] == key("card_bnft", 2, "benefit"))
        self.assertEqual(bnft["props"]["embedding"], VECTOR)
        link = next(e for e in edges if sync.is_projection_edge(e))
        self.assertEqual(relationship_properties(link)["link_source"], COMMON_LINK_SOURCE)
        apply = next(e for e in edges if e["type"] == "dp_has_common_benefit")
        self.assertNotIn("card_common_id", relationship_properties(apply))     # 기존 관계 속성은 늘지 않는다


class PlanTests(unittest.TestCase):
    def test_first_sync_plans_only_projection_and_simulates_to_zero_difference(self):
        nodes, edges = prepare(build(projected())[0])
        found = as_found(*base_graph())
        p = sync.plan(nodes, edges, *found)
        counts = sync.plan_counts(p)
        self.assertEqual(counts["blocked"], 0)
        self.assertEqual(counts["create_evidence"], 2)
        self.assertEqual(counts["create_edges"], {"dp_in_chunk": 2, "dp_supported_by": 2})
        self.assertEqual(counts["set_props"]["set:embedding"], 2)
        self.assertEqual(counts["set_props"]["set:brand_compare_status"], 1)
        residual = compare_graph(nodes, edges, *sync.simulate(p, *found))
        self.assertFalse(any(residual.values()))

    def test_other_difference_blocks(self):
        nodes, edges = prepare(build(projected())[0])
        found_nodes, found_edges = as_found(*base_graph())
        found_nodes[0]["props"]["source_json"] = "changed"
        p = sync.plan(nodes, edges, found_nodes, found_edges)
        self.assertTrue(any(item[0] == "node_property" and item[2] == "source_json" for item in p["blocked"]))

    def test_removed_ledger_items_are_removed_only_in_projection(self):
        current = as_found(*prepare(build(projected())[0]))
        target_nodes, target_edges = prepare(build(projected(
            common_evidence_links=[{"card_common_id": 1, "card_common_bnft_id": "C1", "evidence_id": "cev1"}],
            search_projection={"benefits": [], "common_benefits": []}))[0])
        p = sync.plan(target_nodes, target_edges, *current)
        counts = sync.plan_counts(p)
        self.assertEqual((counts["delete_links"], counts["delete_evidence"], counts["blocked"]), (1, 1, 0))
        self.assertEqual(counts["set_props"]["remove:embedding"], 2)
        residual = compare_graph(target_nodes, target_edges, *sync.simulate(p, *current))
        self.assertFalse(any(residual.values()))

    def test_card_evidence_link_extra_is_never_deleted(self):
        nodes, edges = base_graph()
        found_nodes, found_edges = as_found(*prepare(build(projected())[0]))
        plain = next(e for e in found_edges if e["type"] == "dp_supported_by" and not sync.is_projection_edge(e))
        p = sync.plan([n for n in nodes], [e for e in edges if e["key"] != plain["key"]], found_nodes, found_edges)
        self.assertIn(("relationship_extra", plain["key"]), p["blocked"])


class AuditOnlyRuleTests(unittest.TestCase):
    """2026-11-05 승인: 공통 혜택 source_json의 update_date만 달라진 경우에 한해 갱신."""

    def test_rule_accepts_only_update_date(self):
        old = json.dumps({"bnft_nm": "라운지", "update_date": "2026-11-02"})
        self.assertTrue(sync.audit_only_change(old, json.dumps({"bnft_nm": "라운지", "update_date": "2026-11-05"})))
        self.assertFalse(sync.audit_only_change(old, json.dumps({"bnft_nm": "공항", "update_date": "2026-11-05"})))   # 업무 속성
        self.assertFalse(sync.audit_only_change(old, json.dumps({"bnft_nm": "라운지", "update_date": "2026-11-05", "x": 1})))  # 구조
        self.assertFalse(sync.audit_only_change(old, json.dumps({"update_date": "2026-11-05"})))                       # 키 삭제
        self.assertFalse(sync.audit_only_change(old, old))                                                            # 차이 없음
        self.assertFalse(sync.audit_only_change("not json", old))

    def plan_with_found_common(self, mutate):
        nodes, edges = prepare(build(projected())[0])
        found_nodes, found_edges = as_found(*base_graph())
        common = next(n for n in found_nodes if n["key"] == key("card_common_bnft", 1, "C1"))
        source = json.loads(common["props"]["source_json"])
        mutate(source)
        common["props"]["source_json"] = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sync.plan(nodes, edges, found_nodes, found_edges), nodes, edges, found_nodes, found_edges

    def test_update_date_only_difference_is_planned_and_simulates_to_zero(self):
        p, nodes, edges, found_nodes, found_edges = self.plan_with_found_common(lambda s: s.update(update_date="2026-11-02"))
        # fixture 공통 혜택에는 update_date가 없으므로 기준 쪽에도 같은 키를 둔다
        self.assertTrue(any(item[0] == "node_property" and item[2] == "source_json" for item in p["blocked"]))
        data = projected()
        data["common_benefits"][0]["update_date"] = "2026-11-05"
        nodes, edges = prepare(build(data)[0])
        p = sync.plan(nodes, edges, found_nodes, found_edges)
        self.assertEqual(p["blocked"], [])
        self.assertEqual(sync.plan_counts(p)["set_props"]["set:source_json"], 1)
        self.assertFalse(any(compare_graph(nodes, edges, *sync.simulate(p, found_nodes, found_edges)).values()))

    def test_business_field_difference_still_blocks(self):
        data = projected()
        data["common_benefits"][0]["update_date"] = "2026-11-05"
        nodes, edges = prepare(build(data)[0])
        found_nodes, found_edges = as_found(*base_graph())
        common = next(n for n in found_nodes if n["key"] == key("card_common_bnft", 1, "C1"))
        source = json.loads(common["props"]["source_json"]); source.update(update_date="2026-11-02", bnft_nm="변경")
        common["props"]["source_json"] = json.dumps(source, ensure_ascii=False)
        p = sync.plan(nodes, edges, found_nodes, found_edges)
        self.assertIn(("node_property", key("card_common_bnft", 1, "C1"), "source_json"), p["blocked"])

    def test_card_benefit_source_json_is_never_audit_updated(self):
        nodes, edges = prepare(build(projected())[0])
        found_nodes, found_edges = as_found(*base_graph())
        bnft = next(n for n in found_nodes if n["key"] == key("card_bnft", 2, "benefit"))
        source = json.loads(bnft["props"]["source_json"]); source["update_date"] = "x"
        bnft["props"]["source_json"] = json.dumps(source)
        p = sync.plan(nodes, edges, found_nodes, found_edges)
        self.assertIn(("node_property", key("card_bnft", 2, "benefit"), "source_json"), p["blocked"])


class ContextContractTests(unittest.TestCase):
    def test_benefit_context_drops_exactly_projection_props(self):
        from card_benefit.payment_card.db_pipeline_origin_search import neo4j_search
        listed = re.search(r"apoc\.map\.removeKeys\(properties\(b\), \[([^\]]*)\]\)", neo4j_search.CONTEXT_QUERY)
        self.assertIsNotNone(listed)
        self.assertEqual(sorted(re.findall(r"'(\w+)'", listed.group(1))), sorted(PROJECTION_PROPS))
        self.assertIn("AS benefit", neo4j_search.CONTEXT_QUERY)


class SyncTransactionTests(unittest.TestCase):
    def test_apply_then_rerun_is_idempotent(self):
        nodes, edges = prepare(build(projected())[0])
        tx = FakeTx(*as_found(*base_graph()))
        approved = sync.plan_counts(sync.plan(nodes, edges, *sync.read_graph(tx)))
        self.assertEqual(sync.sync_transaction(tx, nodes, edges, approved)["applied"], approved)
        tx.writes.clear()
        again = sync.plan_counts(sync.plan(nodes, edges, *sync.read_graph(tx)))
        sync.sync_transaction(tx, nodes, edges, again)
        self.assertEqual(tx.writes, [])                                 # 변경 0건이면 쓰기 구문이 없다
        self.assertEqual(again["create_evidence"] + again["delete_links"] + again["set_prop_nodes"], 0)

    def test_wrong_approval_writes_nothing(self):
        nodes, edges = prepare(build(projected())[0])
        tx = FakeTx(*as_found(*base_graph()))
        with self.assertRaisesRegex(sync.ProjectionSyncError, "승인"):
            sync.sync_transaction(tx, nodes, edges, {"create_evidence": 0})
        self.assertEqual(tx.writes, [])

    def test_blocked_difference_writes_nothing(self):
        nodes, edges = prepare(build(projected())[0])
        found_nodes, found_edges = as_found(*base_graph())
        found_edges.pop()                                               # 기존 관계 하나가 없는 상태
        tx = FakeTx(found_nodes, found_edges)
        with self.assertRaisesRegex(sync.ProjectionSyncError, "허용 범위"):
            sync.sync_transaction(tx, nodes, edges, {})
        self.assertEqual(tx.writes, [])


class SafetyTests(unittest.TestCase):
    def test_write_statements_stay_in_projection_scope(self):
        for query in sync.WRITE_STATEMENTS:
            self.assertNotRegex(query, r"\bfp_|DROP|REMOVE ")
            labels = set(re.findall(r"[(\[]\w*:(\w+)", query))
            self.assertTrue(labels and all(label.startswith("dp_") for label in labels), labels)
        deletes = [q for q in sync.WRITE_STATEMENTS if re.search(r"\bDELETE\b", q)]
        self.assertEqual(set(deletes), {sync.DELETE_LINKS, sync.DELETE_EVIDENCE})
        self.assertIn("link_source = 'COMMON_STG'", sync.DELETE_LINKS)
        self.assertIn("NOT ()-[:dp_supported_by]->(n)", sync.DELETE_EVIDENCE)

    def test_index_statements_are_vector_indexes_with_ledger_dimension(self):
        self.assertEqual(len(sync.INDEX_STATEMENTS), 2)
        for statement in sync.INDEX_STATEMENTS:
            self.assertIn("IF NOT EXISTS", statement)
            self.assertIn(f"`vector.dimensions`: {EMBEDDING_DIM}", statement)
            self.assertIn("'cosine'", statement)


class EmbeddingPlanTests(unittest.TestCase):
    def test_reuse_and_generation_follow_embedding_service_rules(self):
        from card_benefit.payment_card.db_pipeline.benefit_search_text import build_card_bnft_text, build_common_bnft_text
        card_ok = {"card_id": 2, "card_bnft_id": "B1", "bnft_nm": "버스", "bnft_type_nm": None, "rule_list": [], "bnft_cond_expr": None,
                   "bnft_rule_txt": "버스 5%", "has_embedding": True}
        card_ok["bnft_search_txt"] = build_card_bnft_text(card_ok).text
        card_new = {**card_ok, "card_bnft_id": "B2", "bnft_search_txt": None, "has_embedding": False}
        common_changed = {"card_common_id": 1, "card_common_bnft_id": "C1", "bnft_nm": "라운지", "bnft_rule_txt": "무료",
                          "bnft_search_txt": "옛 텍스트", "has_embedding": True, "common_nm": "VISA"}

        class Repo:
            def rows(self, name, IDS=None):
                return [card_ok, card_new] if name == "select_card_bnft_rows" else [common_changed]
        report = sync.embedding_plan(Repo())
        self.assertEqual((report["card_bnft"]["reuse_existing"], report["card_bnft"]["generate"]), (1, 1))
        self.assertEqual((report["card_common_bnft"]["existing_text_changed"], report["card_common_bnft"]["generate"]), (1, 1))
        self.assertGreater(report["total"]["tokens"], 0)
        self.assertNotEqual(build_common_bnft_text(common_changed).text, "옛 텍스트")


if __name__ == "__main__":
    unittest.main()
