import csv
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
import sys
import types
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[4]  # 저장소 루트(src/card_benefit/payment_card/tests 기준)
CHAT = ROOT / "src/card_benefit/payment_card/file_pipeline/chat"
spec = importlib.util.spec_from_file_location("fp_eval_questions", CHAT / "eval" / "eval_questions.py")
eq = importlib.util.module_from_spec(spec); sys.modules[spec.name] = eq; spec.loader.exec_module(eq)
spec2 = importlib.util.spec_from_file_location("fp_run_eval", CHAT / "eval" / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec2); sys.modules[spec2.name] = run_eval; spec2.loader.exec_module(run_eval)
spec3 = importlib.util.spec_from_file_location("fp_patch", CHAT / "fp_chat_patch.py")
patch = importlib.util.module_from_spec(spec3); sys.modules[spec3.name] = patch; spec3.loader.exec_module(patch)


@dataclass
class Analysis:
    entities: list[str]
    hops: int
    intent: str


def write_csv(path, cols, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)


def sample_dir(path, *, duplicate=False):
    path.mkdir()
    ns=[
      {"id":"c1","node_type":"Card","props":json.dumps({"product_name":"가나다 카드"})},
      {"id":"b1","node_type":"Benefit","props":json.dumps({"name":"커피 할인"})},
      {"id":"l1","node_type":"Limit","props":json.dumps({"period":"월","amount":20000})},
      {"id":"t1","node_type":"Target","props":json.dumps({"text":"해외 가맹점"})},
      {"id":"x1","node_type":"Target","props":json.dumps({"text":"상품권 구매"})},
      {"id":"k1","node_type":"Condition","props":json.dumps({"text":"전월 30만원"})},
    ]
    if duplicate: ns.append({"id":"b2","node_type":"Benefit","props":json.dumps({"name":"커피 할인"})})
    write_csv(path/"fp_nodes.csv",["id","node_type","props"],ns)
    es=[{"id":"e1","source_id":"c1","target_id":"b1","edge_type":"OFFERS"},{"id":"e2","source_id":"b1","target_id":"l1","edge_type":"HAS_LIMIT"},{"id":"e3","source_id":"b1","target_id":"t1","edge_type":"APPLIES_TO"},{"id":"e4","source_id":"b1","target_id":"x1","edge_type":"EXCLUDES"},{"id":"e5","source_id":"b1","target_id":"k1","edge_type":"HAS_CONDITION"}]
    write_csv(path/"fp_edges.csv",["id","source_id","target_id","edge_type"],es)
    write_csv(path/"fp_evidence.csv",["node_id","edge_id","doc_sha256","quote_status"],[{"node_id":"b1","edge_id":"","doc_sha256":"a"*64,"quote_status":"located"}])


def test_apply_schema_validation_and_opt_in(monkeypatch):
    import importlib
    import types
    fake_db=types.SimpleNamespace(SCHEMA="graphrag",NODES="graphrag.nodes",EDGES="graphrag.edges",run_query=lambda *a: [])
    fake_rag=types.ModuleType("rag"); fake_rag.answer=lambda *a,**k: {"answer":"", "subgraph":{"nodes":[]}}
    monkeypatch.setattr(patch,"_load_modules",lambda:fake_db)
    monkeypatch.setitem(sys.modules,"rag",fake_rag)
    monkeypatch.setattr(importlib,"reload",lambda module: module)
    assert (fake_db.NODES,fake_db.EDGES)==("graphrag.nodes","graphrag.edges")
    try: patch.apply("bad.schema")
    except ValueError: pass
    else: assert False
    assert patch.apply("fp_chat") is fake_rag
    assert fake_db.NODES=="fp_chat.nodes" and fake_db.EDGES=="fp_chat.edges"


def test_list_entities_two_queries_binding_cap_and_dedupe(monkeypatch):
    calls=[]
    def query(q,p=None):
        calls.append((q,p))
        if len(calls)==1:
            return [{"name":"커피 할인","label":"Benefit"},{"name":"커피 할인","label":"Benefit"}]
        return [{"name":"우리 카드","label":"Card"}]
    fake_db=type("DB",(),{"run_query":staticmethod(query)})
    rows=patch._make_list_entities(fake_db,"fp_chat")("커피 혜택")
    assert [r["name"] for r in rows]==["커피 할인","우리 카드"]
    assert len(calls)==2 and "ilike any(%(patterns)s)" in calls[0][0]
    assert calls[0][1]=={"patterns":["%커피%","%혜택%"]}
    assert "%(limit)s" in calls[1][0] and calls[1][1]["limit"]==499
    assert len(rows)<=500



def test_list_entities_never_exceeds_500():
    seen=[]
    def query(sql, params=None):
        seen.append((sql, params))
        return [{"name":f"Benefit {i}","label":"Benefit"} for i in range(650)]
    fake_db=type("DB",(),{"run_query":staticmethod(query)})
    result=patch._make_list_entities(fake_db,"fp_chat")("Benefit")
    assert len(result)==500 and len(seen)==1

def test_eval_questions_determinism_ambiguity_and_output_guard(tmp_path):
    folder=tmp_path/"csv"; sample_dir(folder)
    a, skipped=eq.generate([folder],per_type=10,seed=17)
    b,_=eq.generate([folder],per_type=10,seed=17)
    assert a==b and len(a)>=6 and all("원문" not in q["question"] for q in a)
    dup=tmp_path/"dup"; sample_dir(dup,duplicate=True)
    _, skipped_dup=eq.generate([dup],per_type=10,seed=17)
    assert skipped_dup["card_benefits"]>0
    try: eq.write_questions([folder],ROOT/"blocked.json")
    except ValueError: pass
    else: assert False


def test_eval_metrics():
    records=[{"question":{"expected":["월","20000"],"expected_node_names":["커피 할인"]},"result":{"answer":"월 20000원","sources":[{}],"subgraph":{"nodes":[{"name":"커피 할인"}]}},"elapsed_seconds":2}]
    m=run_eval.metrics(records)
    assert m["retrieval_hit_rate"]==1 and m["answer_inclusion_rate"]==1 and m["source_rate"]==1 and m["average_seconds"]==2


def test_dry_run_does_not_call_db_or_llm(tmp_path, monkeypatch, capsys):
    qfile=tmp_path/"q.json"; qfile.write_text(json.dumps({"questions":[{"id":"q1","question":"Q","expected":["A"]}]}))
    monkeypatch.setattr(sys,"argv",["run_eval",str(qfile)])
    # outside /tmp rejected; place under /tmp per interface
    qfile=Path("/tmp/fp-dry-run-test.json"); qfile.write_text(json.dumps({"questions":[{"id":"q1","question":"Q","expected":["A"]}]}))
    monkeypatch.setattr(sys,"argv",["run_eval",str(qfile)])
    assert run_eval.main()==0
    out=json.loads(capsys.readouterr().out)
    assert out["mode"]=="dry-run" and out["question_count"]==1 and out["llm_call_estimate"]==2
    qfile.unlink()


def test_rank_candidates_prefers_rare_matching_words_over_name_order():
    """흔한 단어('할인')가 많이 걸려도 드문 단어('소노')까지 맞는 이름이 이름순 잘림에 밀리지 않아야 한다."""
    rows=[{"name":f"가{i} 할인","label":"Benefit"} for i in range(40)]
    rows+= [{"name":"소노 청구할인","label":"Benefit"},{"name":"소노카드","label":"Card"}]
    ranked=patch._rank_candidates(rows,["소노","할인"],limit=5)
    assert "소노 청구할인" in ranked and "소노카드" in ranked
    assert list(patch._rank_candidates(rows,["소노","할인"],limit=5))==list(ranked)  # 결정적
    assert len(patch._rank_candidates(rows,["소노","할인"],limit=500))==42


def _install_cache_test_rag(monkeypatch, analyzer):
    import importlib

    monkeypatch.setenv("FP_CHAT_ENV_FILE", "/tmp/nonexistent.env")
    monkeypatch.setenv("FP_DB_POOL", "0")
    monkeypatch.delenv("FP_QA_LOG", raising=False)
    monkeypatch.delenv("FP_ANALYSIS_CACHE", raising=False)
    monkeypatch.delenv("FP_ANALYSIS_CACHE_FILE", raising=False)
    monkeypatch.syspath_prepend(str(CHAT))
    for name in (
        "_ORIGINAL_ANSWER", "_ORIGINAL_LIST_ENTITIES", "_ORIGINAL_ANALYZE",
        "_ORIGINAL_EXPLORE", "_ORIGINAL_GENERATE_STREAM", "_ORIGINAL_ANSWER_SYSTEM",
        "_ORIGINAL_RUN_QUERY", "_POOL_RUN_QUERY", "_PATCHED_DB",
    ):
        monkeypatch.setattr(patch, name, None)
    monkeypatch.setattr(patch, "_ANALYSIS_CACHE", {})
    monkeypatch.setattr(patch, "_ANALYSIS_CACHE_FILE", None)
    monkeypatch.setattr(patch, "_ANALYSIS_CACHE_READY", False)

    fake_db = types.SimpleNamespace(
        SCHEMA="graphrag", NODES="graphrag.nodes", EDGES="graphrag.edges",
        run_query=lambda *args, **kwargs: [],
    )
    fake_rag = types.ModuleType("rag")
    fake_rag.answer = lambda *args, **kwargs: {"answer": ""}
    fake_rag.analyze = analyzer
    monkeypatch.setattr(patch, "_load_modules", lambda: fake_db)
    monkeypatch.setattr(importlib, "reload", lambda module: module)
    monkeypatch.setitem(sys.modules, "rag", fake_rag)
    patch.apply("fp_chat")
    return fake_rag


def test_analysis_cache_disabled_calls_original_for_each_question(monkeypatch):
    calls = []

    def original_analyze(question, entities):
        calls.append((question, entities))
        return Analysis([question], 2, "원본")

    rag = _install_cache_test_rag(monkeypatch, original_analyze)
    first = rag.analyze("같은 질문", [])
    second = rag.analyze("같은 질문", [])

    assert len(calls) == 2
    assert first.entities == second.entities == ["같은 질문"]


def test_analysis_cache_normalizes_questions_and_separates_other_keys(monkeypatch):
    calls = []

    def original_analyze(question, entities):
        calls.append(question)
        return Analysis([f"선택 {len(calls)}"], 3, "의도")

    rag = _install_cache_test_rag(monkeypatch, original_analyze)
    monkeypatch.setenv("FP_ANALYSIS_CACHE", " YeS ")
    first = rag.analyze("  카드   혜택 ", [])
    normalized_hit = rag.analyze("카드　혜택", [])
    separate = rag.analyze("카드 다른 혜택", [])

    assert calls == ["  카드   혜택 ", "카드 다른 혜택"]
    assert first == normalized_hit
    assert separate.entities == ["선택 2"]


def test_analysis_cache_does_not_store_empty_entity_results(monkeypatch):
    calls = []

    def original_analyze(question, entities):
        calls.append(question)
        return Analysis([], 1, "")

    rag = _install_cache_test_rag(monkeypatch, original_analyze)
    monkeypatch.setenv("FP_ANALYSIS_CACHE", "1")
    rag.analyze("대상 없음", [])
    rag.analyze("대상 없음", [])

    assert len(calls) == 2
    assert patch._ANALYSIS_CACHE == {}


def test_analysis_cache_returns_independent_analysis_objects(monkeypatch):
    calls = []

    def original_analyze(question, entities):
        calls.append(question)
        return Analysis(["커피 할인"], 2, "혜택 조회")

    rag = _install_cache_test_rag(monkeypatch, original_analyze)
    monkeypatch.setenv("FP_ANALYSIS_CACHE", "on")
    first = rag.analyze("커피 혜택", [])
    first.entities.append("오염")
    first.hops = 99
    second = rag.analyze("커피 혜택", [])

    assert len(calls) == 1
    assert type(second) is Analysis
    assert second.entities == ["커피 할인"] and second.hops == 2


def test_analysis_cache_file_round_trip_and_broken_file(monkeypatch, tmp_path):
    calls = []

    def original_analyze(question, entities):
        calls.append(question)
        return Analysis(["하나 카드"], 4, "카드 조회")

    cache_file = tmp_path / "analysis-cache.json"
    rag = _install_cache_test_rag(monkeypatch, original_analyze)
    monkeypatch.setenv("FP_ANALYSIS_CACHE", "true")
    monkeypatch.setenv("FP_ANALYSIS_CACHE_FILE", str(cache_file))
    first = rag.analyze("하나 카드 혜택", [])
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload == {
        "version": 1,
        "entries": {
            "하나 카드 혜택": {"entities": ["하나 카드"], "hops": 4, "intent": "카드 조회"}
        },
    }

    monkeypatch.setattr(patch, "_ANALYSIS_CACHE", {})
    monkeypatch.setattr(patch, "_ANALYSIS_CACHE_FILE", None)
    monkeypatch.setattr(patch, "_ANALYSIS_CACHE_READY", False)
    restarted_calls = []

    def restarted_analyze(question, entities):
        restarted_calls.append(question)
        return Analysis(["새 결과"], 1, "")

    rag = _install_cache_test_rag(monkeypatch, restarted_analyze)
    monkeypatch.setenv("FP_ANALYSIS_CACHE", "1")
    monkeypatch.setenv("FP_ANALYSIS_CACHE_FILE", str(cache_file))
    restored = rag.analyze("하나 카드 혜택", [])
    assert not restarted_calls
    assert type(restored) is Analysis and restored == first

    broken_file = tmp_path / "broken-cache.json"
    broken_file.write_text("{깨진 json", encoding="utf-8")
    broken_calls = []

    def after_broken_file(question, entities):
        broken_calls.append(question)
        return Analysis(["정상 복구"], 1, "")

    rag = _install_cache_test_rag(monkeypatch, after_broken_file)
    monkeypatch.setenv("FP_ANALYSIS_CACHE", "1")
    monkeypatch.setenv("FP_ANALYSIS_CACHE_FILE", str(broken_file))
    result = rag.analyze("깨진 파일 질문", [])
    cached = rag.analyze("깨진 파일 질문", [])
    assert len(broken_calls) == 1
    assert result == cached == Analysis(["정상 복구"], 1, "")


def test_analysis_cache_propagates_analyzer_exception_without_storing(monkeypatch):
    calls = []

    def original_analyze(question, entities):
        calls.append(question)
        raise RuntimeError("analyze failed")

    rag = _install_cache_test_rag(monkeypatch, original_analyze)
    monkeypatch.setenv("FP_ANALYSIS_CACHE", "1")
    for _ in range(2):
        try:
            rag.analyze("예외 질문", [])
        except RuntimeError as exc:
            assert str(exc) == "analyze failed"
        else:
            assert False, "원본 예외가 전파되어야 함"

    assert len(calls) == 2
    assert patch._ANALYSIS_CACHE == {}
