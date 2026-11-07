import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

from payment_card.file_pipeline.graph.cypher_export import export_cypher, list_cards


def _write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _inputs(folder, count=1):
    folder.mkdir(parents=True)
    _write_csv(folder / "fp_load_runs.csv", ["run_id", "input_folder_name", "model_name", "started_at", "node_count", "edge_count"], [])
    _write_csv(folder / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"], [
        {"id": f"n{i}", "node_type": "Benefit", "props": json.dumps({"name": "O'Reilly\\path\nnext", "active": True, "tags": ["a"], "nested": {"k": 1}}, ensure_ascii=False), "chunk_id": "c", "run_id": "r"}
        for i in range(count)
    ])
    _write_csv(folder / "fp_edges.csv", ["id", "source_id", "target_id", "edge_type", "run_id"], [])
    _write_csv(folder / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"], [])


def test_exports_escaped_flat_properties_and_nested_json(tmp_path):
    source = tmp_path / "csv"
    _inputs(source)
    output = tmp_path / "load.cypher"
    export_cypher(source, output)
    text = output.read_text(encoding="utf-8")
    assert "O\\'Reilly\\\\path\\nnext" in text
    assert "active: true" in text
    assert 'props_json: \'{"tags":["a"],"nested":{"k":1}}\'' in text
    assert "quote" not in text.lower()
    assert ":FpBenefit" in text
    assert "CREATE CONSTRAINT fp_benefit_id_unique" in text
    assert ":Benefit" not in text


def test_default_english_output_matches_prechange_golden_bytes(tmp_path):
    source = tmp_path / "csv"
    _inputs(source)
    output = tmp_path / "english.cypher"
    export_cypher(source, output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert digest == "4c5e65fdc118449ffb92b64ba4ab33c5547ecaca2f411f3d9c2007707f5143e6"


def test_batches_are_split_at_500_rows(tmp_path):
    source = tmp_path / "csv"
    _inputs(source, count=501)
    output = tmp_path / "load.cypher"
    export_cypher(source, output)
    text = output.read_text(encoding="utf-8")
    assert text.count("UNWIND [") == 2
    assert text.count("MERGE (n:FpBenefit") == 2


def test_rejects_output_inside_repository(tmp_path):
    source = tmp_path / "csv"
    _inputs(source)
    repo = Path(__file__).resolve().parents[4]
    with pytest.raises(ValueError, match="저장소 밖"):
        export_cypher(source, repo / "generated.cypher")


def test_rejects_label_injection(tmp_path):
    source = tmp_path / "csv"
    _inputs(source)
    nodes = source / "fp_nodes.csv"
    rows = list(csv.DictReader(nodes.open(encoding="utf-8", newline="")))
    rows[0]["node_type"] = "Benefit) DETACH DELETE n //"
    _write_csv(nodes, list(rows[0]), rows)
    with pytest.raises(ValueError, match="node_type"):
        export_cypher(source, tmp_path / "load.cypher")


def _graph_csv(folder, cards, benefits, edges):
    folder.mkdir()
    _write_csv(folder / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"], [
        {"id": cid, "node_type": "Card", "props": json.dumps({"product_name": name}), "chunk_id": "", "run_id": "r"} for cid, name in cards
    ] + [
        {"id": bid, "node_type": "Benefit", "props": json.dumps({"name": bid}), "chunk_id": "", "run_id": "r"} for bid in benefits
    ] + [
        {"id": nid, "node_type": typ, "props": "{}", "chunk_id": "", "run_id": "r"} for nid, typ in (("cond", "Condition"), ("lim", "Limit"), ("tar", "Target"))
    ])
    _write_csv(folder / "fp_edges.csv", ["id", "source_id", "target_id", "edge_type", "run_id"], [dict(id=eid, source_id=s, target_id=t, edge_type=typ, run_id="r") for eid, s, t, typ in edges])
    _write_csv(folder / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"], [])


def test_list_cards_sorts_benefit_count_then_id(tmp_path):
    source = tmp_path / "csv"
    _graph_csv(source, [("c2", "Second"), ("c1", "First")], ["b1", "b2"], [
        ("e1", "c2", "b1", "OFFERS"), ("e2", "c1", "b2", "OFFERS"),
    ])
    result = list_cards(source, 10)
    assert [(r["card_id"], r["product_name"], r["benefits"]) for r in result] == [("c1", "First", 1), ("c2", "Second", 1)]


def test_sample_filter_cuts_benefits_and_shared_card_edges(tmp_path):
    source = tmp_path / "csv"
    _graph_csv(source, [("c1", "One"), ("c2", "Two")], ["b1", "b2", "shared"], [
        ("o1", "c1", "b1", "OFFERS"), ("o2", "c1", "b2", "OFFERS"),
        ("o3", "c1", "shared", "OFFERS"), ("o4", "c2", "shared", "OFFERS"),
        ("d1", "b1", "cond", "HAS_CONDITION"), ("d2", "b1", "lim", "HAS_LIMIT"),
        ("d3", "b1", "tar", "APPLIES_TO"),
    ])
    output = tmp_path / "sample.cypher"
    counts = export_cypher(source, output, ["c1"], max_benefits=2)
    script = output.read_text(encoding="utf-8")
    assert counts["cut_benefits"] == 1
    assert counts["nodes"] == 6
    assert "'c2'" not in script
    assert "'o4'" not in script
    assert "잘린 혜택 1" in script


def test_full_export_remains_unmarked_and_keeps_all_input_rows(tmp_path):
    source = tmp_path / "csv"
    _graph_csv(source, [("c", "Card")], ["b"], [("o", "c", "b", "OFFERS")])
    output = tmp_path / "all.cypher"
    counts = export_cypher(source, output)
    assert counts == {"nodes": 5, "edges": 1, "evidence": 0}
    assert "샘플 스크립트" not in output.read_text(encoding="utf-8")


def test_readme_and_queries_have_only_scoped_delete_and_prefixed_patterns():
    root = Path(__file__).resolve().parents[1] / "file_pipeline" / "graph" / "cypher"
    readme = (root / "README.md").read_text(encoding="utf-8")
    queries = (root / "queries.cypher").read_text(encoding="utf-8")
    assert "MATCH (n) DETACH DELETE n" not in readme + queries
    assert "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'Fp') DETACH DELETE n" in readme
    assert "MATCH (n)" not in queries
    assert ":Card" not in queries and ":Benefit" not in queries


def test_evidence_ids_captions_and_labeled_matches(tmp_path):
    source = tmp_path / "csv"
    _graph_csv(source, [("c", "Card")], ["b"], [("o", "c", "b", "OFFERS")])
    evidence_path = source / "fp_evidence.csv"
    _write_csv(evidence_path, ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"], [
        {"node_id": "c", "edge_id": "", "doc_sha256": "a" * 64, "page_no": "2", "start_pos": "3", "end_pos": "8", "quote_status": "exact"},
        {"node_id": "c", "edge_id": "", "doc_sha256": "a" * 64, "page_no": "2", "start_pos": "3", "end_pos": "8", "quote_status": "exact"},
    ])
    output = tmp_path / "all.cypher"
    counts = export_cypher(source, output)
    text = output.read_text(encoding="utf-8")
    assert counts == {"nodes": 5, "edges": 1, "evidence": 1}
    assert text.count("evidence:") >= 1
    assert "name: 'Card'" in text and "name: 'b'" in text and "exact p.2" in text
    assert "MATCH (source:FpCard {id: row.source_id}), (target:FpBenefit {id: row.target_id})" in text
    assert "MATCH (n {" not in text and "OPTIONAL MATCH (n {" not in text
    assert "MERGE (e:FpEvidence {id: row.id})" in text


def test_content_based_evidence_ids_are_stable_and_disjoint(tmp_path):
    import re

    outputs = []
    for i, digest in enumerate(("a" * 64, "b" * 64)):
        source = tmp_path / f"csv{i}"
        _graph_csv(source, [(f"c{i}", f"Card{i}")], [f"b{i}"], [])
        _write_csv(source / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"], [
            {"node_id": f"c{i}", "edge_id": "", "doc_sha256": digest, "page_no": "1", "start_pos": "2", "end_pos": "4", "quote_status": "exact"}
        ])
        output = tmp_path / f"out{i}.cypher"
        export_cypher(source, output)
        outputs.append(set(re.findall(r"evidence:[0-9a-f]{20}", output.read_text(encoding="utf-8"))))
    assert len(outputs[0]) == len(outputs[1]) == 1
    assert outputs[0].isdisjoint(outputs[1])


def test_korean_properties_and_sidecar_files(tmp_path):
    source = tmp_path / "ko-csv"
    source.mkdir()
    _write_csv(source / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"], [
        {"id": "c", "node_type": "Card", "props": json.dumps({"product_name": "하나"}), "chunk_id": "", "run_id": "r"},
        {"id": "b", "node_type": "Benefit", "props": json.dumps({"name": "혜택", "method": "DISCOUNT"}), "chunk_id": "x", "run_id": "r"},
        {"id": "d", "node_type": "Condition", "props": json.dumps({"kind": "SPEND_REQ"}), "chunk_id": "x", "run_id": "r"},
        {"id": "l", "node_type": "Limit", "props": json.dumps({"period": "MONTH"}), "chunk_id": "x", "run_id": "r"},
        {"id": "t", "node_type": "Target", "props": json.dumps({"kind": "MERCHANT"}), "chunk_id": "x", "run_id": "r"},
    ])
    _write_csv(source / "fp_edges.csv", ["id", "source_id", "target_id", "edge_type", "run_id"], [{"id":"e", "source_id":"c", "target_id":"b", "edge_type":"OFFERS", "run_id":"r"}, {"id":"e2", "source_id":"b", "target_id":"d", "edge_type":"HAS_CONDITION", "run_id":"r"}])
    _write_csv(source / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"], [])
    en, ko, grass, backfill = [tmp_path / name for name in ("en.cypher", "ko.cypher", "style.grass", "backfill.cypher")]
    export_cypher(source, en)
    explicit_en = tmp_path / "explicit-en.cypher"
    export_cypher(source, explicit_en, lang="en")
    assert en.read_bytes() == explicit_en.read_bytes()
    export_cypher(source, ko, lang="ko", grass_out=grass, backfill_ko_out=backfill)
    english, korean = en.read_text(), ko.read_text()
    assert "kind_ko" not in english and "label_ko" not in english
    assert "kind_ko: '혜택'" in korean and "method_ko: '할인'" in korean
    assert "cond_kind_ko: '이용 실적'" in korean and "period_ko: '월별'" in korean
    assert "target_kind_ko: '가맹점'" in korean and "label_ko: '제공'" in korean
    assert "caption_ko: '[혜택] 혜택'" in korean
    assert "caption: \"{caption_ko}\"" in grass.read_text()
    assert all(f"node.Fp{label} {{" in grass.read_text() for label in ("Issuer", "Card", "Benefit", "Condition", "Limit", "Target", "Evidence"))
    assert all(f"relationship.FP_{rel} {{" in grass.read_text() for rel in ("OFFERS", "HAS_CONDITION", "HAS_LIMIT", "APPLIES_TO", "EXCLUDES", "MUTUALLY_EXCLUSIVE", "HAS_EVIDENCE"))
    query = backfill.read_text()
    assert "any(l IN labels(n) WHERE l STARTS WITH 'Fp')" in query
    assert "type(r) STARTS WITH 'FP_'" in query
    assert not re.search(r"\[\s*r?\s*\]", query)
    assert "DETACH DELETE" not in query
    assert not re.search(r"(?m)^MATCH\s*\(n\)\s*(?:$|;)", query)


def test_unknown_enum_is_copied_and_reported_once(tmp_path, capsys):
    source = tmp_path / "unknown-csv"
    _graph_csv(source, [("c", "Card")], ["b"], [])
    nodes = list(csv.DictReader((source / "fp_nodes.csv").open(encoding="utf-8", newline="")))
    nodes[1]["props"] = json.dumps({"name": "Benefit", "method": "NEW_METHOD"})
    _write_csv(source / "fp_nodes.csv", list(nodes[0]), nodes)
    export_cypher(source, tmp_path / "ko.cypher", lang="ko")
    assert "method_ko: 'NEW_METHOD'" in (tmp_path / "ko.cypher").read_text()
    assert capsys.readouterr().err.count("NEW_METHOD") == 1


def test_korean_caption_is_limited_and_escaped(tmp_path):
    source = tmp_path / "caption-csv"
    _graph_csv(source, [("c", "Card")], ["b"], [])
    nodes = list(csv.DictReader((source / "fp_nodes.csv").open(encoding="utf-8", newline="")))
    nodes[1]["props"] = json.dumps({"name": "O'Reilly\\path\n" + "가" * 100})
    _write_csv(source / "fp_nodes.csv", list(nodes[0]), nodes)
    output = tmp_path / "ko.cypher"
    export_cypher(source, output, lang="ko")
    text = output.read_text(encoding="utf-8")
    assert "O\\'Reilly\\\\path\\n" in text
    encoded = next(value for value in re.findall(r"caption_ko: '((?:\\.|[^'])*)'", text) if value.startswith("[혜택]"))
    assert len(encoded.replace("\\'", "'").replace("\\\\", "\\").replace("\\n", "\n")) == 80
