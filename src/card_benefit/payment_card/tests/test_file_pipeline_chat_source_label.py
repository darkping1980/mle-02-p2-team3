import importlib.util
from pathlib import Path
import sys
import types

CHAT = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"


def load(name):
    sys.path.insert(0, str(CHAT))
    spec = importlib.util.spec_from_file_location(f"source_label_test_{name}", next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_filename_labels_table():
    labels = load("source_label")
    cases = [
        ("woori_all/common/국제브랜드서비스안내장_MC_P.T.pdf", "brand_service", "국제브랜드 공통 안내장(Mastercard)"),
        ("woori_all/common/국제브랜드서비스안내장_VISA-P.pdf", "brand_service", "국제브랜드 공통 안내장(VISA)"),
        ("hana_all/common/공통_체크카드약관.pdf", "terms", "공통 안내장"),
        ("cards/card_001.pdf", "product", None),
    ]
    assert [(labels.label_for_document(path, role)) for path, role, _ in cases] == [expected for _, _, expected in cases]


def test_load_document_labels_synthetic_csv(tmp_path):
    labels = load("source_label")
    csv_path = tmp_path / "documents.csv"
    csv_path.write_text(
        "issuer,doc_id,sha256,file_path,doc_role\n"
        "woori,d1,sha1,woori/common/공통_국제브랜드서비스안내장_VISA-P.pdf,brand_service\n"
        "woori,d2,sha2,woori/card/card.pdf,product\n",
        encoding="utf-8",
    )
    assert labels.load_document_labels([tmp_path]) == {"sha1": "국제브랜드 공통 안내장(VISA)"}


def test_annotate_benefits_labeled_unlabeled_multi_and_card_specific():
    labels = load("source_label")
    sub = {"nodes": [
        {"id": "b1", "label": "Benefit", "props": {"rate": "5%", "keep": "x"}},
        {"id": "b2", "label": "Benefit", "props": {"rate": "1%"}},
        {"id": "b3", "label": "Benefit", "props": {"rate": "2%"}},
        {"id": "c1", "label": "Card", "props": {"name": "카드"}},
    ], "edges": []}
    result = labels.annotate_subgraph(
        sub, {"b1": ["s1", "s2", "s1"], "b2": ["s3"], "b3": ["s4"]},
        {"s1": "공통 안내장", "s2": "국제브랜드 공통 안내장(VISA)", "s4": "카드 전용 문서"},
    )
    assert result["nodes"][0]["props"] == {"rate": "5%", "keep": "x", "출처문서": "공통 안내장, 국제브랜드 공통 안내장(VISA)"}
    assert "출처문서" not in result["nodes"][1]["props"]
    assert result["nodes"][2]["props"]["출처문서"] == "카드 전용 문서"
    assert "출처문서" not in result["nodes"][3]["props"]
    assert "출처문서" not in sub["nodes"][0]["props"]


def test_prompt_rule_is_conditional_and_preserves_v2_v3():
    fmt = load("answer_format")
    v2, v3 = fmt.ANSWER_SYSTEM_V2, fmt.ANSWER_SYSTEM_V3
    assert fmt.with_source_label_rule(v2, {"nodes": [{"props": {}}]}) == v2
    assert fmt.with_source_label_rule(v3, {"nodes": [{"props": {}}]}) == v3
    assert fmt.with_source_label_rule(v2, {"nodes": [{"props": {"출처문서": "공통 안내장"}}]}).endswith(fmt.SOURCE_LABEL_RULE)
    assert fmt.ANSWER_SYSTEM_V2 == v2 and fmt.ANSWER_SYSTEM_V3 == v3


def test_source_label_wiring_off_and_query_failure_return_original(monkeypatch):
    patch = load("fp_chat_patch")
    query_calls = []
    db = types.SimpleNamespace(run_query=lambda *args, **kwargs: query_calls.append(args) or [])
    base = {"nodes": [{"id": "n1", "label": "Benefit", "props": {"fp_id": "f1"}}], "edges": []}
    rag = types.SimpleNamespace(
        ANSWER_SYSTEM="합성 system", llm=types.SimpleNamespace(stream=lambda prompt, messages: [prompt]),
        answer=lambda *_: {}, explore=lambda _: base,
        generate_stream=lambda q, sub, hist=None: iter([rag.llm.stream(rag.ANSWER_SYSTEM, [])][0]),
    )
    monkeypatch.setitem(sys.modules, "db", db)
    monkeypatch.setitem(sys.modules, "rag", rag)
    monkeypatch.setattr(patch, "_load_modules", lambda: db)
    monkeypatch.setattr("importlib.reload", lambda module: module)
    monkeypatch.setenv("FP_DB_POOL", "0")
    monkeypatch.delenv("FP_ENTITY_DEDUPE", raising=False)
    monkeypatch.delenv("FP_SOURCE_LABEL", raising=False)
    patched = patch.apply()
    assert patched.explore(None) is base
    assert list(patched.generate_stream("q", base)) == [patched.ANSWER_SYSTEM]
    assert query_calls == []
    monkeypatch.setenv("FP_SOURCE_LABEL", "1")
    db.run_query = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic failure"))
    assert patch._annotate_source_labels(db, base) is base
    assert patched.explore(None) is base
    patch.restore()
