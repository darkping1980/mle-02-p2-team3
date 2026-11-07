import json

from payment_card.file_pipeline.extraction.eval.consensus import build_consensus, _without_locations
from payment_card.file_pipeline.extraction.eval.eval_runs import compare_groups, run_metrics, summarize_group, within_range
from payment_card.file_pipeline.extraction.report.table_density_report import classify_density
from payment_card.file_pipeline.extraction.schema import Extraction


def _run(chunk_id, benefits, relations):
    return {"chunk_id": chunk_id, "extraction": {
        "schema_ver": "ONTOLOGY_V1", "benefits": benefits, "conditions": [], "limits": [],
        "targets": [], "relations": relations}, "failures": [], "notes": []}


def _benefit(id_, name):
    return {"id": id_, "name": name, "evidence": [{"text": "근거", "location": {"start_pos": 1}}]}


def test_consensus_keeps_k_items_and_reconnects_only_supported_relations(tmp_path):
    condition = lambda id_: {"id": id_, "text": "조건", "kind": "SPEND_REQ", "evidence": [{"text": "조건 근거"}]}
    a = _run("c1", [_benefit("a1", "Alpha"), _benefit("only-a", "Only A")], [])
    a["extraction"]["conditions"] = [condition("ac")]
    b = _run("c1", [_benefit("b1", "alpha")], [])
    b["extraction"]["conditions"] = [condition("bc")]
    c = _run("c1", [_benefit("c1", "ALPHA")], [])
    c["extraction"]["conditions"] = [condition("cc")]
    rel = {"source": "a1", "target": "ac", "type": "HAS_CONDITION", "evidence": [{"text": "관계"}]}
    a["extraction"]["relations"] = [rel]
    b["extraction"]["relations"] = [{**rel, "source": "b1", "target": "bc"}]
    original = json.dumps(a, ensure_ascii=False)
    result = build_consensus([[a], [b], [c]], k=2)
    extracted = result["rows"][0]["extraction"]
    assert [item["id"] for item in extracted["benefits"]] == ["a1"]
    assert extracted["relations"][0]["source"] == extracted["benefits"][0]["id"]
    assert isinstance(Extraction.model_validate(_without_locations(extracted)), Extraction)
    assert json.dumps(a, ensure_ascii=False) == original


def test_eval_summary_and_variation_range():
    assert summarize_group([1, 3]) == {"mean": 2, "stdev": 1.4142, "min": 1, "max": 3}
    assert summarize_group([2])["stdev"] is None
    assert within_range(2, [1, 3]) is True
    assert within_range(4, [1, 3]) is False
    report = compare_groups({"repeat": [[], []], "single": [[]]})
    assert report["single_run_comparison"]["single"]["repeat"]["chunks"]["within_repeated_run_range"] is True
    row = {"extraction": {"benefits": [], "conditions": [], "limits": [], "targets": [], "relations": []}}
    metrics = run_metrics([row, {"extraction": None}])
    assert (metrics["success_chunks"], metrics["failure_chunks"], metrics["empty_chunks"]) == (0, 1, 1)


def test_density_classifier_returns_low_middle_high():
    assert classify_density([0, 1, 2, 3, 4, 5]) == ["low", "low", "middle", "middle", "high", "high"]
