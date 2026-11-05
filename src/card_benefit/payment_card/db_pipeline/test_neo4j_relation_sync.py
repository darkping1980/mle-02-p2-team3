"""neo4j_relation_sync 시나리오 테스트. 실제 Neo4j·PostgreSQL에 접속하지 않는다.

FakeGraph는 모듈의 ``// rel_sync:이름`` 구문만 해석하는 메모리 그래프다. 쓰기 구문이 실제로 어떤 행을 바꿨는지
노드·관계 상태로 확인한다.
"""
import copy
import json
import re
import unittest

from card_benefit.payment_card.db_pipeline import neo4j_relation_sync as sync
from card_benefit.payment_card.db_pipeline.neo4j_dry_run import Preview
from card_benefit.payment_card.db_pipeline.neo4j_load_draft import prepare


class Record:
    def __init__(self, row): self.row = row
    def data(self): return dict(self.row)


class Result:
    def __init__(self, rows): self.rows = rows
    def __iter__(self): return iter(Record(r) for r in self.rows)
    def single(self, strict=True):
        assert len(self.rows) == 1
        return self.rows[0]


class FakeGraph:
    """노드 {key: {labels, props}}, 관계 [{id, type, start, end, props}]."""

    def __init__(self, nodes, rels):
        self.nodes = copy.deepcopy(nodes)
        self.rels = copy.deepcopy(rels)
        self.next_id = 1000
        self.writes = []

    def run(self, query, **params):
        name = re.match(r"// rel_sync:(\w+)", query).group(1)
        if name == "read_related":
            return Result([{"id": r["id"], "start": r["start"], "end": r["end"], "in_scope": True, "props": dict(r["props"])}
                           for r in self.rels if r["type"] == sync.REL_TYPE])
        if name == "read_nodes":
            return Result([{"key": k, "labels": list(v["labels"]), "props": dict(v["props"])} for k, v in self.nodes.items()])
        if name == "read_other_rels":
            return Result([{"type": r["type"], "start": r["start"], "end": r["end"], "props": dict(r["props"])}
                           for r in self.rels if r["type"].startswith("dp_") and r["type"] != sync.REL_TYPE])
        self.writes.append(name)
        if name == "delete_related":
            before = len(self.rels)
            self.rels = [r for r in self.rels if not (r["type"] == sync.REL_TYPE and r["id"] in params["ids"])]
            return Result([{"n": before - len(self.rels)}])
        if name == "update_related":
            n = 0
            for row in params["rows"]:
                for r in self.rels:
                    if r["type"] == sync.REL_TYPE and r["id"] == row["id"]:
                        r["props"] = dict(row["props"]); n += 1
            return Result([{"n": n}])
        if name == "merge_related":
            n = 0
            for row in params["rows"]:
                if row["start"] not in self.nodes or row["end"] not in self.nodes:
                    continue
                match = [r for r in self.rels if r["type"] == sync.REL_TYPE and r["start"] == row["start"]
                         and r["end"] == row["end"] and r["props"].get("relation_key") == row["relation_key"]]
                if match:
                    match[0]["props"] = dict(row["props"])
                else:
                    self.next_id += 1
                    self.rels.append({"id": f"r{self.next_id}", "type": sync.REL_TYPE, "start": row["start"], "end": row["end"],
                                      "props": dict(row["props"])})
                n += 1
            return Result([{"n": n}])
        raise AssertionError(name)


RELATIONS_179 = [{"to_bnft_id": "178", "rel_type_cd": "FALLBACK_AFTER_CAP", "rel_priority": None, "relation_key": "fixed_fallback"},
                 {"to_bnft_id": "178", "rel_type_cd": "OVERRIDES", "rel_priority": None, "relation_key": "special_over_basic"},
                 {"to_bnft_id": "178", "rel_type_cd": "MUTUALLY_EXCLUSIVE", "rel_priority": None, "relation_key": "special_basic_exclusive"}]
RELATIONS_180 = [{**RELATIONS_179[0], "relation_key": "recurring_fallback"}, RELATIONS_179[1], RELATIONS_179[2]]


def ledger_graph(relations=None):
    """운영과 같은 모양: 카드 42의 혜택 178·179·180, 179·180에서 178로 관계 3종씩."""
    relations = relations if relations is not None else {"179": RELATIONS_179, "180": RELATIONS_180}
    g = Preview()
    product = g.node("card_product", [42], {"card_id": 42})
    keys = {}
    for bnft in ("178", "179", "180"):
        keys[bnft] = g.node("card_bnft", [42, bnft], {"card_id": 42, "card_bnft_id": bnft, "relation_list": relations.get(bnft, [])})
        g.edge("has_benefit", product, keys[bnft], {})
    for bnft, items in relations.items():
        for rel in items:
            g.edge("related_to", keys[bnft], keys[rel["to_bnft_id"]], rel)
    return prepare(g)


def fake_from(nodes, edges, include_related=False):
    """기대 그래프를 Neo4j에 적재된 상태처럼 만든다(관계 key 속성은 적재기와 같은 규칙)."""
    from card_benefit.payment_card.db_pipeline.neo4j_load_draft import relationship_properties
    labels = {n["props"]["key"]: ["dp_node", n["label"]] + (["dp_card_product_item"] if n["label"] == "dp_card_bnft" else [])
              for n in nodes}
    graph_nodes = {n["props"]["key"]: {"labels": labels[n["props"]["key"]], "props": dict(n["props"])} for n in nodes}
    rels = [{"id": f"e{i}", "type": e["type"], "start": e["start"], "end": e["end"],
             "props": {"key": e["key"], "source_json": e["source_json"], **relationship_properties(e)}}
            for i, e in enumerate(edges) if include_related or e["type"] != sync.REL_TYPE]
    return FakeGraph(graph_nodes, rels)


def related(fake):
    return sorted((r["start"], r["end"], r["props"]["relation_key"], r["props"]["rel_type_cd"], r["props"].get("rel_priority"), r["id"])
                  for r in fake.rels if r["type"] == sync.REL_TYPE)


class LedgerIdentityTests(unittest.TestCase):
    def test_same_pair_with_three_types_is_three_relations(self):
        nodes, edges = ledger_graph()
        ledger = sync.ledger_relations(nodes, edges)
        self.assertEqual(len(ledger), 6)
        pairs = {(v["start"], v["end"]) for v in ledger.values()}
        self.assertEqual(len(pairs), 2)                      # 출발·대상 쌍은 2개지만 관계는 6개

    def test_duplicate_relation_key_in_ledger_is_refused(self):
        nodes, edges = ledger_graph({"179": [RELATIONS_179[0], {**RELATIONS_179[1], "relation_key": "fixed_fallback"}]})
        with self.assertRaisesRegex(sync.RelationSyncError, "relation_key 중복"):
            sync.ledger_relations(nodes, edges)

    def test_duplicate_target_and_type_in_ledger_is_refused(self):
        nodes, edges = ledger_graph({"179": [RELATIONS_179[0], {**RELATIONS_179[0], "relation_key": "other"}]})
        with self.assertRaisesRegex(sync.RelationSyncError, "rel_type_cd\\) 중복"):
            sync.ledger_relations(nodes, edges)

    def test_priority_is_not_part_of_identity(self):
        a = sync.ledger_relations(*ledger_graph())
        b = sync.ledger_relations(*ledger_graph({"179": [{**RELATIONS_179[0], "rel_priority": 3}, *RELATIONS_179[1:]], "180": RELATIONS_180}))
        self.assertEqual(set(a), set(b))


class SyncScenarioTests(unittest.TestCase):
    def apply(self, fake, nodes, edges, expected=None):
        return sync.sync_transaction(fake, sync.ledger_relations(nodes, edges), expected)

    def test_first_run_creates_six_and_leaves_other_types(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        others = copy.deepcopy([r for r in fake.rels])
        result = self.apply(fake, nodes, edges, {"create": 6})
        self.assertEqual(result["applied"], {"create": 6, "update": 0, "replace": 0, "delete": 0})
        self.assertEqual(len(related(fake)), 6)
        self.assertEqual([r for r in fake.rels if r["type"] != sync.REL_TYPE], others)

    def test_rerun_with_same_input_changes_nothing(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        self.apply(fake, nodes, edges)
        fake.writes.clear()
        snapshot = copy.deepcopy(fake.rels)
        result = self.apply(fake, nodes, edges, {"create": 0})
        self.assertEqual(result["applied"], {"create": 0, "update": 0, "replace": 0, "delete": 0})
        self.assertEqual(fake.writes, [])                   # 쓰기 구문 자체를 보내지 않는다
        self.assertEqual(fake.rels, snapshot)

    def test_priority_change_updates_same_relationship(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        self.apply(fake, nodes, edges)
        before_ids = {r[2]: r[5] for r in related(fake) if r[0].endswith('"179"]')}
        changed = ledger_graph({"179": [{**RELATIONS_179[0], "rel_priority": 1}, *RELATIONS_179[1:]], "180": RELATIONS_180})
        result = self.apply(fake, *changed, {"update": 1})
        self.assertEqual(result["applied"], {"create": 0, "update": 1, "replace": 0, "delete": 0})
        rows = {r[2]: r for r in related(fake) if r[0].endswith('"179"]')}
        self.assertEqual(rows["fixed_fallback"][4], 1)
        self.assertEqual(rows["fixed_fallback"][5], before_ids["fixed_fallback"])   # 같은 관계(id 유지)
        self.assertEqual(len(related(fake)), 6)
        # 갱신된 key 속성은 적재기(prepare)가 만드는 값과 같다 → neo4j_validate 비교와 호환
        expected_key = next(e["key"] for e in changed[1] if e["type"] == sync.REL_TYPE and '"rel_priority":1' in e["source_json"])
        self.assertIn(expected_key, {r["props"]["key"] for r in fake.rels})

    def test_priority_back_to_null_removes_property(self):
        nodes, edges = ledger_graph({"179": [{**RELATIONS_179[0], "rel_priority": 1}, *RELATIONS_179[1:]], "180": RELATIONS_180})
        fake = fake_from(nodes, edges)
        self.apply(fake, nodes, edges)
        self.apply(fake, *ledger_graph(), {"update": 1})
        props = next(r["props"] for r in fake.rels if r["type"] == sync.REL_TYPE and r["props"]["relation_key"] == "fixed_fallback"
                     and r["start"].endswith('"179"]'))
        self.assertNotIn("rel_priority", props)

    def test_type_change_with_same_relation_key_updates_in_place(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        self.apply(fake, nodes, edges)
        # special_basic_exclusive: MUTUALLY_EXCLUSIVE → HIGHER_VALUE_WINS (relation_key·대상 동일)
        changed = ledger_graph({"179": [*RELATIONS_179[:2], {**RELATIONS_179[2], "rel_type_cd": "HIGHER_VALUE_WINS"}], "180": RELATIONS_180})
        result = self.apply(fake, *changed, {"update": 1})
        self.assertEqual(result["applied"]["update"], 1)
        types = sorted(r[3] for r in related(fake) if r[0].endswith('"179"]'))
        self.assertEqual(types, ["FALLBACK_AFTER_CAP", "HIGHER_VALUE_WINS", "OVERRIDES"])

    def test_type_change_with_new_relation_key_is_delete_plus_create(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        self.apply(fake, nodes, edges)
        changed = ledger_graph({"179": [*RELATIONS_179[:2], {**RELATIONS_179[2], "rel_type_cd": "HIGHER_VALUE_WINS",
                                                              "relation_key": "special_higher"}], "180": RELATIONS_180})
        result = self.apply(fake, *changed, {"create": 1, "delete": 1})
        self.assertEqual(result["applied"], {"create": 1, "update": 0, "replace": 0, "delete": 1})
        self.assertEqual(len(related(fake)), 6)

    def test_target_change_replaces_only_that_relationship(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        self.apply(fake, nodes, edges)
        changed = ledger_graph({"179": [{**RELATIONS_179[0], "to_bnft_id": "180"}, *RELATIONS_179[1:]], "180": RELATIONS_180})
        result = self.apply(fake, *changed, {"replace": 1})
        self.assertEqual(result["applied"], {"create": 0, "update": 0, "replace": 1, "delete": 0})
        moved = [r for r in related(fake) if r[2] == "fixed_fallback"]
        self.assertTrue(moved[0][1].endswith('"180"]'))

    def test_ledger_deletion_removes_only_that_related_to(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        self.apply(fake, nodes, edges)
        others = copy.deepcopy([r for r in fake.rels if r["type"] != sync.REL_TYPE])
        changed = ledger_graph({"179": RELATIONS_179[:2], "180": RELATIONS_180})
        result = self.apply(fake, *changed, {"delete": 1})
        self.assertEqual(result["applied"], {"create": 0, "update": 0, "replace": 0, "delete": 1})
        keys = {(r[0][-6:], r[2]) for r in related(fake)}
        self.assertNotIn(('"179"]', "special_basic_exclusive"), keys)
        self.assertIn(('"180"]', "special_basic_exclusive"), keys)      # 같은 relation_key의 다른 출발 관계는 유지
        self.assertEqual([r for r in fake.rels if r["type"] != sync.REL_TYPE], others)

    def test_same_pair_different_types_all_kept(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        self.apply(fake, nodes, edges)
        by_pair = {}
        for start, end, _, kind, _, _ in related(fake):
            by_pair.setdefault((start, end), set()).add(kind)
        self.assertEqual(list(by_pair.values()), [{"FALLBACK_AFTER_CAP", "OVERRIDES", "MUTUALLY_EXCLUSIVE"}] * 2)

    def test_approved_counts_mismatch_aborts_before_any_write(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        with self.assertRaisesRegex(sync.RelationSyncError, "승인한 변경 건수"):
            self.apply(fake, nodes, edges, {"create": 5})
        self.assertEqual(fake.writes, [])

    def test_other_relationship_change_inside_transaction_aborts(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        original = fake.run

        def tamper(query, **params):
            result = original(query, **params)
            if query.startswith("// rel_sync:merge_related"):
                fake.rels[0]["props"]["source_json"] = "tampered"     # 다른 유형 관계가 바뀐 상황
            return result
        fake.run = tamper
        with self.assertRaisesRegex(sync.RelationSyncError, "dp_related_to 외"):
            self.apply(fake, nodes, edges)

    def test_ambiguous_existing_duplicates_are_not_guessed(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges, include_related=True)
        dup = copy.deepcopy(next(r for r in fake.rels if r["type"] == sync.REL_TYPE))
        dup["id"] = "dup"
        fake.rels.append(dup)
        with self.assertRaisesRegex(sync.RelationSyncError, "여러 개"):
            self.apply(fake, nodes, edges)
        self.assertEqual(fake.writes, [])

    def test_legacy_relationship_without_relation_key_is_refused(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        fake.rels.append({"id": "legacy", "type": sync.REL_TYPE, "start": nodes[1]["props"]["key"], "end": nodes[2]["props"]["key"], "props": {}})
        with self.assertRaisesRegex(sync.RelationSyncError, "relation_key 없는"):
            self.apply(fake, nodes, edges)


def loader_merge(fake, edges):
    """neo4j_load_draft.write_transaction의 관계 처리(:135-139)와 사후 key 검사(:144-145)를 그대로 흉내 낸다.

    MERGE (a)-[r:유형 {key:$key}]->(b) SET r.source_json=$source_json, r += $extra
    Returns: (새로 만든 관계 수, 사후 key 검사 통과 여부). 실패면 실제 적재기는 ValueError로 rollback한다.
    """
    from card_benefit.payment_card.db_pipeline.neo4j_load_draft import relationship_properties
    created = 0
    for e in edges:
        match = [r for r in fake.rels if r["type"] == e["type"] and r["start"] == e["start"] and r["end"] == e["end"]
                 and r["props"].get("key") == e["key"]]
        if match:
            match[0]["props"].update({"source_json": e["source_json"], **relationship_properties(e)})
        else:
            fake.next_id += 1; created += 1
            fake.rels.append({"id": f"l{fake.next_id}", "type": e["type"], "start": e["start"], "end": e["end"],
                              "props": {"key": e["key"], "source_json": e["source_json"], **relationship_properties(e)}})
    found = [r["props"]["key"] for r in fake.rels if r["type"].startswith("dp_")]
    return created, len(found) == len(edges) and set(found) == {e["key"] for e in edges}


class LoaderCompatibilityTests(unittest.TestCase):
    """동기화 모듈이 저장한 관계를 기존 변환기·적재기·검증기가 같은 관계로 보는지."""

    def test_sync_key_and_properties_equal_converter_and_validator_expectation(self):
        from card_benefit.payment_card.db_pipeline.neo4j_load_draft import relationship_properties
        nodes, edges = ledger_graph()
        ledger = sync.ledger_relations(nodes, edges)
        for e in (e for e in edges if e["type"] == sync.REL_TYPE):
            identity = (e["start"], json.loads(e["source_json"])["relation_key"])
            # neo4j_validate.compare_graph가 기대하는 관계 속성과 같다
            self.assertEqual(ledger[identity]["props"], {"key": e["key"], "source_json": e["source_json"], **relationship_properties(e)})

    def test_full_loader_after_sync_creates_no_duplicate(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        sync.sync_transaction(fake, sync.ledger_relations(nodes, edges))
        before = copy.deepcopy(fake.rels)
        self.assertEqual(loader_merge(fake, edges), (0, True))
        self.assertEqual(fake.rels, before)                  # 속성까지 그대로

    def test_sync_after_loader_changes_nothing(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        loader_merge(fake, edges)                            # 기존 전체 적재기로 먼저 6건을 만든 경우
        result = sync.sync_transaction(fake, sync.ledger_relations(nodes, edges), {"create": 0})
        self.assertEqual(result["applied"], {"create": 0, "update": 0, "replace": 0, "delete": 0})

    def test_loader_after_priority_change_without_sync_is_rejected_not_duplicated(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        sync.sync_transaction(fake, sync.ledger_relations(nodes, edges))
        _, changed = ledger_graph({"179": [{**RELATIONS_179[0], "rel_priority": 1}, *RELATIONS_179[1:]], "180": RELATIONS_180})
        created, postcondition_ok = loader_merge(fake, changed)
        # key가 원본 JSON 해시라 적재기는 같은 업무 관계를 새 관계로 MERGE한다. 사후 key 검사가 실패해 rollback되므로
        # 중복이 commit되지는 않지만, 적재기 단독으로는 이 변경을 반영할 수 없다 → 관계 변경 책임은 동기화 모듈.
        self.assertEqual((created, postcondition_ok), (1, False))

    def test_sync_after_priority_change_then_loader_is_consistent(self):
        nodes, edges = ledger_graph()
        fake = fake_from(nodes, edges)
        sync.sync_transaction(fake, sync.ledger_relations(nodes, edges))
        changed = ledger_graph({"179": [{**RELATIONS_179[0], "rel_priority": 1}, *RELATIONS_179[1:]], "180": RELATIONS_180})
        sync.sync_transaction(fake, sync.ledger_relations(*changed), {"update": 1})
        self.assertEqual(loader_merge(fake, changed[1]), (0, True))   # 동기화가 key도 새 값으로 맞춘다

    def test_loader_additive_set_cannot_remove_cleared_priority(self):
        nodes, edges = ledger_graph({"179": [{**RELATIONS_179[0], "rel_priority": 1}, *RELATIONS_179[1:]], "180": RELATIONS_180})
        fake = fake_from(nodes, edges)
        loader_merge(fake, edges)
        cleared = ledger_graph()
        target = next(r for r in fake.rels if r["type"] == sync.REL_TYPE and r["props"]["relation_key"] == "fixed_fallback"
                      and r["start"].endswith('"179"]'))
        new_edge = next(e for e in cleared[1] if e["type"] == sync.REL_TYPE and e["start"] == target["start"]
                        and '"fixed_fallback"' in e["source_json"])
        target["props"]["key"] = new_edge["key"]             # 같은 key로 맞춰도
        loader_merge(fake, [new_edge])
        self.assertEqual(target["props"].get("rel_priority"), 1)      # r += extra는 사라진 속성을 지우지 못한다
        sync.sync_transaction(fake, sync.ledger_relations(*cleared))
        self.assertNotIn("rel_priority", target["props"] if target in fake.rels else
                         next(r for r in fake.rels if r["id"] == target["id"])["props"])


class SafetyTests(unittest.TestCase):
    def test_write_statements_touch_only_dp_related_to(self):
        for query in sync.WRITE_STATEMENTS:
            self.assertIn("dp_related_to", query)
            self.assertNotRegex(query, r"(?i)DETACH|REMOVE|DROP|CREATE\s")
            self.assertNotRegex(query, r"\bfp_")
        self.assertNotRegex(sync.DELETE_RELATED + sync.UPDATE_RELATED + sync.MERGE_RELATED, r"\(n\)|MATCH \(n")
        deletes = [q for q in sync.WRITE_STATEMENTS if re.search(r"\bDELETE\b", q)]
        self.assertEqual(deletes, [sync.DELETE_RELATED])
        self.assertIn("[r:dp_related_to]", sync.DELETE_RELATED)

    def test_read_statements_have_no_write_clause(self):
        for query in (sync.READ_RELATED, sync.READ_NODES, sync.READ_OTHER_RELS):
            self.assertNotRegex(query.upper(), r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b")

    def test_fingerprint_ignores_label_and_row_order(self):
        rows = [{"key": "a", "labels": ["dp_node", "dp_card_bnft", "dp_card_product_item"], "props": {"x": 1, "y": 2}},
                {"key": "b", "labels": ["dp_node", "dp_card_doc"], "props": {}}]
        shuffled = [{"key": "b", "labels": ["dp_card_doc", "dp_node"], "props": {}},
                    {"key": "a", "labels": ["dp_card_product_item", "dp_node", "dp_card_bnft"], "props": {"y": 2, "x": 1}}]
        self.assertEqual(sync.fingerprint(rows, []), sync.fingerprint(shuffled, []))

    def test_orphan_classification_separates_source_from_load(self):
        expected = [{"type": "dp_in_document", "start": "page", "end": "doc"}]
        same = sync.classify_orphans(["doc"], expected, list(expected))
        self.assertEqual(same, {"source_preexisting": ["doc"], "load_mismatch": []})
        lost = sync.classify_orphans(["doc"], expected + [{"type": "dp_has_document", "start": "p", "end": "doc"}], expected)
        self.assertEqual(lost, {"source_preexisting": [], "load_mismatch": ["doc"]})


if __name__ == "__main__":
    unittest.main()
