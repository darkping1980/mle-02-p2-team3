import ast
import json
import re
from pathlib import Path


NOTEBOOK = Path(__file__).resolve().parents[1] / "file_pipeline" / "notebooks" / "neo4j_sample_check.ipynb"


def _cells():
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


def _code_cells():
    return ["".join(cell["source"]) for cell in _cells() if cell["cell_type"] == "code"]


def _static_check_function():
    for source in _code_cells():
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "inspect_cypher":
                namespace = {
                    "re": re,
                    "node_labels": ["FpIssuer", "FpCard", "FpBenefit", "FpCondition", "FpLimit", "FpTarget", "FpEvidence"],
                    "allowed_relationships": {
                        "FP_OFFERS", "FP_HAS_CONDITION", "FP_HAS_LIMIT", "FP_APPLIES_TO",
                        "FP_EXCLUDES", "FP_MUTUALLY_EXCLUSIVE", "FP_HAS_EVIDENCE",
                    },
                }
                exec(compile(ast.Module(body=[node], type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
                return namespace[node.name]
    raise AssertionError("inspect_cypher 함수가 없습니다")


def test_notebook_is_unexecuted_and_safe_by_default():
    cells = _cells()
    code_cells = _code_cells()
    full = "\n".join(code_cells)
    assert all(not cell["outputs"] and cell["execution_count"] is None for cell in cells if cell["cell_type"] == "code")
    for setting in ("WRITE", "ALLOW_REMOTE", "CONFIRM_DELETE", "USE_ENV_REMOTE"):
        assert re.search(rf"\b{setting}\s*=\s*False", full)
    assert "LOCAL_URI = 'bolt://localhost:7687'" in full or 'LOCAL_URI = "bolt://localhost:7687"' in full
    assert "LOCAL_USERNAME = 'neo4j'" in full or 'LOCAL_USERNAME = "neo4j"' in full
    assert "getpass.getpass" in full
    assert "dotenv" in full and "load_dotenv" in full
    assert full.count("DETACH DELETE") == 1
    delete_cell = next(source for source in code_cells if "DETACH DELETE" in source)
    assert "CONFIRM_DELETE" in delete_cell and "is_local" in delete_cell
    assert "DETACH DELETE" not in "\n".join(source for source in code_cells if source != delete_cell)
    assert re.search(r"if\s+USE_ENV_REMOTE\s*:", full)
    connection = next(source for source in code_cells if "getpass.getpass" in source)
    remote_branch = connection.split("if USE_ENV_REMOTE:", 1)[1].split("else:", 1)[0]
    for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"):
        assert name in remote_branch
        assert name not in connection.split("else:", 1)[1]
    assert re.search(r"not is_local", full) and "writes_allowed" in full
    assert "remote_host or not is_local" in full
    for source in code_cells:
        assert not re.search(r"\b(?:print|display)\s*\([^\n]*(?:NEO4J_PASSWORD|NEO4J_URI|NEO4J_USERNAME|password|_uri|_username)", source, re.I)
        compile(source, str(NOTEBOOK), "exec")
    assert not re.search(r"\bMATCH\s*\(\s*n\s*\)", "\n".join(source for source in code_cells if "DETACH DELETE" not in source))
    assert not re.search(r"\bimport\s+pyvis|\bfrom\s+pyvis", full)


def test_static_checker_accepts_generated_relationships_and_rejects_unsafe_samples():
    inspect_cypher = _static_check_function()
    hana = "MERGE (source:FpCard {id: row.source_id})-[r:FP_OFFERS {id: row.id}]->(target:FpBenefit {id: row.target_id})"
    woori = "MERGE (n:FpCard {id: row.id})\nMERGE (n)-[:FP_HAS_EVIDENCE]->(e:FpEvidence {id: row.id})"
    assert inspect_cypher(hana)["금지 패턴"] == []
    assert inspect_cypher(woori)["금지 패턴"] == []
    assert "유형 없는 관계" in inspect_cypher("MATCH (a:FpCard)-[r]->(b:FpBenefit)")["금지 패턴"]
    assert "유형 없는 관계" in inspect_cypher("MATCH (a:FpCard)-[]->(b:FpBenefit)")["금지 패턴"]
    assert "DELETE" in inspect_cypher("MATCH (n:FpCard) DELETE n")["금지 패턴"]


def _run_static_check_cell(tmp_path, statements):
    """노트북의 설정 셀과 정적 검사 셀을 Neo4j 접속 없이 실제로 실행해 static_check_ok 를 돌려준다."""
    import json
    import pandas as pd

    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cells = ["".join(cell["source"]) for cell in notebook["cells"]]
    sample = tmp_path / "sample.cypher"
    sample.write_text(statements, encoding="utf-8")
    namespace = {"display": lambda *_args, **_kwargs: None}
    exec(cells[2], namespace)  # 설정 셀: 경로·옵션·허용 라벨 목록
    namespace["SAMPLE_FILES"] = [sample]
    exec("import pandas as pd\n" + cells[8], namespace)  # 정적 검사 셀
    return namespace["static_check_ok"]


def test_static_check_cell_passes_clean_sample_and_blocks_delete(tmp_path):
    clean = (
        "CREATE CONSTRAINT fp_card_id_unique IF NOT EXISTS FOR (n:FpCard) REQUIRE n.id IS UNIQUE;\n"
        "MERGE (n:FpCard {id: 'card:x'}) SET n.name = 'x';\n"
        "MATCH (a:FpBenefit {id: 'b1'}), (e:FpEvidence {id: 'e1'}) MERGE (a)-[:FP_HAS_EVIDENCE]->(e);\n"
    )
    assert _run_static_check_cell(tmp_path, clean) is True
    dangerous = clean + "MATCH (n:FpCard) DETACH DELETE n;\n"
    assert _run_static_check_cell(tmp_path, dangerous) is False
