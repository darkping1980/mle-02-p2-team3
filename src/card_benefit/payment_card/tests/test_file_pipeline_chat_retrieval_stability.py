import json
from types import SimpleNamespace

from payment_card.file_pipeline.chat.eval import retrieval_stability as stability


def test_aggregate_question_identical_repeats_have_full_stability():
    rows = [
        {"selected_entities": ["Hotel"], "node_ids": ["a", "b"], "benefits": [{"name": "Stay", "rate": "15%"}]},
        {"selected_entities": ["Hotel"], "node_ids": ["b", "a"], "benefits": [{"name": "Stay", "rate": "15%"}]},
    ]
    result = stability.aggregate_question(rows)
    assert result["distinct_entity_selections"] == 1
    assert result["mean_pairwise_node_jaccard"] == 1.0
    assert result["common_node_fraction"] == 1.0
    assert result["nodes_in_some_repeats_only"] == 0
    assert result["benefit_value_sets_differ"] is False


def test_aggregate_question_reports_selection_and_node_instability():
    rows = [
        {"selected_entities": ["Hotel"], "node_ids": ["a", "b"]},
        {"selected_entities": ["hotel"], "node_ids": ["b", "c"]},
        {"selected_entities": ["Other"], "node_ids": ["b", "d"]},
    ]
    result = stability.aggregate_question(rows)
    assert result["distinct_entity_selections"] == 2
    assert result["mean_pairwise_node_jaccard"] == 1 / 3
    assert result["common_node_fraction"] == 1 / 4
    assert result["nodes_in_some_repeats_only"] == 3


def test_aggregate_question_detects_benefit_value_difference_after_normalization():
    rows = [
        {"benefits": [{"name": "Stay Benefit", "rate": "15 %"}]},
        {"benefits": [{"name": "stay-benefit", "rate": "20%"}]},
    ]
    assert stability.aggregate_question(rows)["benefit_value_sets_differ"] is True


def test_aggregate_records_groups_question_ids():
    rows = [
        {"question_id": "q1", "node_ids": ["a"]},
        {"question_id": "q1", "node_ids": ["a", "b"]},
        {"question_id": "q2", "node_ids": ["z"]},
    ]
    result = stability.aggregate_records(rows)
    assert [item["question_id"] for item in result] == ["q1", "q2"]
    assert result[0]["nodes_in_some_repeats_only"] == 1
    assert stability.aggregate_all(rows)["questions_with_benefit_value_differences"] == 0


def test_aggregate_all_counts_questions_with_differing_benefit_sets():
    rows = [
        {"question_id": "q1", "benefits": [{"name": "Stay", "rate": "15%"}]},
        {"question_id": "q1", "benefits": [{"name": "Stay", "rate": "20%"}]},
        {"question_id": "q2", "benefits": [{"name": "Dining", "rate": "10%"}]},
    ]
    assert stability.aggregate_all(rows)["questions_with_benefit_value_differences"] == 1


def test_repeated_run_uses_fake_analyze_and_explore_without_answer(tmp_path):
    calls = []

    class FakeRag:
        def list_entities(self, question):
            calls.append(("entities", question))
            return [{"name": "Hotel", "label": "Benefit"}]

        def analyze(self, question, entities):
            calls.append(("analyze", question, entities))
            return SimpleNamespace(entities=["Hotel"])

        def explore(self, analysis):
            calls.append(("explore", analysis.entities))
            return {"nodes": [
                {"id": "node-1", "name": "Hotel perk", "label": "Benefit", "props": {"rate": "15%", "page_no": 47}},
                {"id": "node-2", "name": "Card", "label": "Card", "props": {}},
            ]}

        def answer(self, *_args):
            raise AssertionError("answer generation must not run")

    output = tmp_path / "retrieval.jsonl"
    # Exercise run logic while redirecting the safety boundary to a temporary file under /tmp.
    real_safe_tmp = stability.safe_tmp
    stability.safe_tmp = lambda _path: output
    try:
        assert stability.run_repeated([{"id": "hotel", "question": "synthetic question"}], 2, FakeRag(), output) == 0
    finally:
        stability.safe_tmp = real_safe_tmp
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert records[0]["selected_entities"] == ["Hotel"]
    assert records[0]["subgraph_node_count"] == 2
    assert records[0]["node_ids"] == ["node-1", "node-2"]
    assert records[0]["benefits"] == [{"name": "Hotel perk", "rate": "15%", "amount": None, "page_number": 47}]
    assert [call[0] for call in calls] == ["entities", "analyze", "explore"] * 2
    assert {row["mode"] for row in records} == {"llm"}


def test_freeze_command_selects_most_common_entities_per_question(tmp_path):
    source = tmp_path / "input.jsonl"
    output = tmp_path / "frozen.json"
    source.write_text("\n".join(json.dumps(row) for row in [
        {"question_index": 0, "selected_entities": ["A"]},
        {"question_index": 1, "selected_entities": ["C"]},
        {"question_index": 0, "selected_entities": ["B"]},
        {"question_index": 0, "selected_entities": ["A"]},
    ]), encoding="utf-8")

    assert stability.main(["freeze", "--input", str(source), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {"0": ["A"], "1": ["C"]}


def test_frozen_repeats_skip_analyze_and_report_db_nondeterminism(tmp_path, capsys):
    class FakeRag:
        def __init__(self):
            self.explorations = 0

        def list_entities(self, *_args):
            raise AssertionError("frozen mode must not list or analyze entities")

        def analyze(self, *_args):
            raise AssertionError("frozen mode must not call analyze")

        def explore(self, analysis):
            self.explorations += 1
            return {"nodes": [{"id": f"node-{self.explorations}"}]}

    output = tmp_path / "frozen.jsonl"
    real_safe_tmp = stability.safe_tmp
    stability.safe_tmp = lambda _path: output
    try:
        assert stability.run_repeated(
            [{"question": "synthetic question"}], 2, FakeRag(), output,
            freeze_entities={"0": ["Hotel"]},
        ) == 0
    finally:
        stability.safe_tmp = real_safe_tmp
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["mode"] for row in records] == ["frozen", "frozen"]
    assert [row["selected_entities"] for row in records] == [["Hotel"], ["Hotel"]]
    assert stability._print_summary(output) == 0
    assert "탐색 비결정성(DB 쪽) 의심" in capsys.readouterr().out


def test_frozen_deterministic_repeats_attribute_instability_to_llm(capsys, tmp_path):
    class FakeRag:
        def analyze(self, *_args):
            raise AssertionError("frozen mode must not call analyze")

        def explore(self, analysis):
            assert analysis.entities == ["Hotel"]
            return {"nodes": [{"id": "same-node"}]}

    output = tmp_path / "frozen.jsonl"
    real_safe_tmp = stability.safe_tmp
    stability.safe_tmp = lambda _path: output
    try:
        stability.run_repeated([{"question": "synthetic question"}], 2, FakeRag(), output, {"0": ["Hotel"]})
    finally:
        stability.safe_tmp = real_safe_tmp
    assert stability._print_summary(output) == 0
    assert "LLM 시작 엔티티 변동이 원인" in capsys.readouterr().out
