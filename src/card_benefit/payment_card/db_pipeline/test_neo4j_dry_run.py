from .neo4j_dry_run import GraphValidationError
from .neo4j_relational_model import build
from .test_neo4j_relational_model import snapshot


def test_dry_run_model_is_table_faithful_and_does_not_decompose_rules():
    model = build(snapshot())
    assert model["stats"]["node_count"] == 3
    assert model["stats"]["relationship_count"] == 2
    assert {node["label"] for node in model["nodes"]} == {
        "dp_card_product", "dp_card_product_item", "dp_card_doc"
    }
    assert "dp_card_bnft" not in {node["label"] for node in model["nodes"]}
    assert issubclass(GraphValidationError, ValueError)
