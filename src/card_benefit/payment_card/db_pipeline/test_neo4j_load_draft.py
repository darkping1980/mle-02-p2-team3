from .neo4j_load_draft import prepare, write_transaction
from .test_neo4j_relational_model import snapshot


class Result:
    def __init__(self, value):
        self.value = value

    def single(self, strict=False):
        return self.value


class FakeTx:
    def __init__(self):
        self.nodes = {}
        self.edges = {}

    def run(self, query, **params):
        if "MERGE (n:dp_node" in query:
            rows = params["rows"]
            self.nodes.update((row["key"], row) for row in rows)
            return Result({"n": len(rows)})
        if "MERGE (a)-[r:" in query:
            rows = params["rows"]
            self.edges.update((row["key"], row) for row in rows)
            return Result({"n": len(rows)})
        if "MATCH (n:dp_node) RETURN count(n)" in query:
            return Result({"n": len(self.nodes)})
        if "RETURN count(r) AS n" in query:
            return Result({"n": len(self.edges)})
        raise AssertionError(query)


def test_prepare_and_write_all_source_rows_and_relationships():
    model = prepare(snapshot())
    tx = FakeTx()
    result = write_transaction(tx, model)
    assert result["nodes"] == 3
    assert result["relationships"] == 2
    assert len(tx.nodes) == 3 and len(tx.edges) == 2
