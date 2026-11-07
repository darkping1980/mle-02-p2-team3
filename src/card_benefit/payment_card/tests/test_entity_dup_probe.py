from payment_card.file_pipeline.chat.eval.entity_dup_probe import evaluate_question
from payment_card.file_pipeline.chat.eval.retrieval_eval import uuidish


class _FixedMatcher:
    def select(self, question, n=3, threshold=0.15):
        return ["Synthetic Card"]


def _fixture(include_second_member):
    card = uuidish("probe-card")
    first = uuidish("probe-benefit-a")
    second = uuidish("probe-benefit-b")
    nodes = [
        {"id": card, "name": "Synthetic Card", "label": "Card", "props": {}},
        {"id": first, "name": "Synthetic benefit", "label": "Benefit", "props": {}},
    ]
    edges = [{"source": card, "target": first, "type": "OFFERS", "_fp_id": "edge-a"}]
    evidence = [{"node_id": "probe-benefit-a", "edge_id": "", "doc_sha256": "sha-a", "page_no": "1", "quote_status": "located"}]
    if include_second_member:
        nodes.append({"id": second, "name": "Synthetic benefit", "label": "Benefit", "props": {}})
        edges.append({"source": card, "target": second, "type": "OFFERS", "_fp_id": "edge-b"})
        evidence.append({"node_id": "probe-benefit-b", "edge_id": "", "doc_sha256": "sha-b", "page_no": "1", "quote_status": "located"})
    return nodes, edges, evidence, {second: first}, {"g1": {first, second}}


def test_probe_reduces_duplicate_group_and_preserves_evidence():
    nodes, edges, evidence, mapping, groups = _fixture(include_second_member=True)
    row = evaluate_question({"id": "SYN-1", "question": "Synthetic Card", "evidence_page": 1},
                            nodes, edges, evidence, _FixedMatcher(), mapping, groups)

    assert row["nodes_reduced"] == 1
    assert row["duplicate_groups_present"] == 1
    assert row["evidence_count_before"] == row["evidence_count_after"] == 2
    assert row["evidence_preservation_violation"] == 0


def test_probe_does_not_change_single_group_member_subgraph():
    nodes, edges, evidence, mapping, groups = _fixture(include_second_member=False)
    row = evaluate_question({"id": "SYN-2", "question": "Synthetic Card", "evidence_page": 1},
                            nodes, edges, evidence, _FixedMatcher(), mapping, groups)

    assert row["nodes_reduced"] == 0
    assert row["duplicate_groups_present"] == 0
    assert row["evidence_count_before"] == row["evidence_count_after"] == 1
    assert row["evidence_preservation_violation"] == 0
