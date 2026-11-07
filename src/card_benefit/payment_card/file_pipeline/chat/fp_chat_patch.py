"""Opt-in adapter for running the team's GraphRAG chatbot against fp_chat views."""
from __future__ import annotations

import copy
from contextvars import ContextVar
import json
from pathlib import Path
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata

try:
    from .db_pool import PoolQueryRunner
except ImportError:  # Script-style imports from this directory.
    from db_pool import PoolQueryRunner

_CHATBOT_DIR = Path(__file__).resolve().parents[4] / "graphrag_chatbot"
_CURRENT_QUESTION: ContextVar[str] = ContextVar("fp_chat_question", default="")
_ORIGINAL_ANSWER = None
_ORIGINAL_LIST_ENTITIES = None
_ORIGINAL_ANALYZE = None
_ORIGINAL_EXPLORE = None
_ORIGINAL_GENERATE_STREAM = None
_ORIGINAL_ANSWER_SYSTEM = None
_ORIGINAL_LLM_STREAM = None
_ORIGINAL_RUN_QUERY = None
_POOL_RUN_QUERY = None
_PATCHED_DB = None
_ANSWER_CAPTURE: ContextVar[dict | None] = ContextVar("fp_chat_answer_capture", default=None)
_SOURCE_LABEL_SYSTEM: ContextVar[str | None] = ContextVar("fp_chat_source_label_system", default=None)
_ANALYSIS_CACHE: dict[str, dict] = {}
_ANALYSIS_CACHE_FILE: str | None = None
_ANALYSIS_CACHE_READY = False
_ANALYSIS_CACHE_LOCK = threading.RLock()


def _analysis_cache_enabled() -> bool:
    return os.environ.get("FP_ANALYSIS_CACHE", "").strip().lower() in {"1", "true", "yes", "on"}


def _analysis_cache_key(question: str) -> str | None:
    if not isinstance(question, str):
        return None
    normalized = unicodedata.normalize("NFKC", question)
    return re.sub(r"\s+", " ", normalized).strip()


def _analysis_cache_record(value) -> dict | None:
    try:
        entities = list(value.entities or [])
        hops = value.hops
        intent = value.intent
    except (AttributeError, TypeError):
        return None
    if not entities or any(not isinstance(name, str) for name in entities):
        return None
    if isinstance(hops, bool) or not isinstance(hops, int) or not isinstance(intent, str):
        return None
    return {"entities": entities, "hops": hops, "intent": intent}


def _valid_analysis_cache_record(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    entities = value.get("entities")
    hops = value.get("hops")
    intent = value.get("intent")
    if (not isinstance(entities, list) or not entities
            or any(not isinstance(name, str) for name in entities)
            or isinstance(hops, bool) or not isinstance(hops, int)
            or not isinstance(intent, str)):
        return None
    return {"entities": list(entities), "hops": hops, "intent": intent}


def _analysis_cache_path() -> str | None:
    configured = os.environ.get("FP_ANALYSIS_CACHE_FILE", "").strip()
    return str(Path(configured).expanduser()) if configured else None


def _save_analysis_cache_locked() -> None:
    if not _ANALYSIS_CACHE_FILE:
        return
    path = Path(_ANALYSIS_CACHE_FILE)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump({"version": 1, "entries": _ANALYSIS_CACHE}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except Exception:
                pass


def _prepare_analysis_cache() -> None:
    global _ANALYSIS_CACHE, _ANALYSIS_CACHE_FILE, _ANALYSIS_CACHE_READY
    configured_path = _analysis_cache_path()
    with _ANALYSIS_CACHE_LOCK:
        if configured_path != _ANALYSIS_CACHE_FILE:
            _ANALYSIS_CACHE = {}
            _ANALYSIS_CACHE_FILE = configured_path
            _ANALYSIS_CACHE_READY = False
        if _ANALYSIS_CACHE_READY:
            return
        if configured_path:
            try:
                payload = json.loads(Path(configured_path).read_text(encoding="utf-8"))
                entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
                if isinstance(entries, dict):
                    for question, value in entries.items():
                        key = _analysis_cache_key(question)
                        record = _valid_analysis_cache_record(value)
                        if key is not None and record:
                            _ANALYSIS_CACHE[key] = record
            except Exception:
                pass
        _ANALYSIS_CACHE_READY = True


def _restore_analysis(record: dict, original_analyze):
    analysis_type = getattr(original_analyze, "__globals__", {}).get("Analysis")
    if not callable(analysis_type):
        return None
    try:
        return analysis_type(
            entities=list(record["entities"]), hops=record["hops"], intent=record["intent"]
        )
    except Exception:
        return None


def _cached_analysis(key: str, original_analyze):
    _prepare_analysis_cache()
    with _ANALYSIS_CACHE_LOCK:
        record = _ANALYSIS_CACHE.get(key)
        return _restore_analysis(record, original_analyze) if record is not None else None


def _store_analysis(key: str, value) -> None:
    record = _analysis_cache_record(value)
    if record is None:
        return
    _prepare_analysis_cache()
    with _ANALYSIS_CACHE_LOCK:
        if _ANALYSIS_CACHE.get(key) == record:
            return
        _ANALYSIS_CACHE[key] = record
        _save_analysis_cache_locked()


def _source_label_enabled() -> bool:
    return os.environ.get("FP_SOURCE_LABEL", "").strip().lower() in {"1", "true", "yes", "on"}


def _annotate_source_labels(db, subgraph: dict) -> dict:
    """Enrich retrieved Benefit nodes from one evidence lookup; fail open."""
    try:
        try:
            from .retrieval.source_label import annotate_subgraph, load_document_labels
        except ImportError:
            from retrieval.source_label import annotate_subgraph, load_document_labels
        nodes = (subgraph or {}).get("nodes") or []
        ids = list(dict.fromkeys(
            str(node.get("props", {}).get("fp_id")) for node in nodes
            if node.get("label") == "Benefit" and node.get("props", {}).get("fp_id")
            and not str(node["props"]["fp_id"]).startswith("doc:")
        ))
        if not ids:
            return subgraph
        evidence = db.run_query(
            "select node_id, doc_sha256 from public.fp_evidence where node_id = any(%(node_ids)s)",
            {"node_ids": ids},
        )
        node_doc_shas: dict[str, list[str]] = {}
        for row in evidence:
            node_doc_shas.setdefault(str(row["node_id"]), []).append(str(row["doc_sha256"]))
        index_root = Path(os.environ.get("FP_DOC_INDEX_DIR") or
                          (Path(__file__).resolve().parents[3] / "data" / "index"))
        if index_root.name == "documents.csv":
            index_dirs = [index_root]
        else:
            index_dirs = [path.parent for path in sorted(index_root.glob("*/documents.csv"))]
        labels = load_document_labels(index_dirs)
        return annotate_subgraph(subgraph, node_doc_shas, labels)
    except Exception:
        return subgraph


def _load_modules():
    if str(_CHATBOT_DIR) not in sys.path:
        sys.path.insert(0, str(_CHATBOT_DIR))
    # db.py calls load_dotenv() at import time. Keep this adapter environment-only:
    # importing it must not open a repository .env file.
    import dotenv  # noqa: PLC0415
    original_loader = dotenv.load_dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False
    try:
        import db  # noqa: PLC0415
    finally:
        dotenv.load_dotenv = original_loader
    return db


def _rank_candidates(rows, tokens, limit: int = 500) -> dict:
    """일치 행을 질문 단어 일치 점수 순으로 정렬해 최대 limit 개를 돌려준다(결정적)."""
    import math  # noqa: PLC0415
    names: dict[str, str] = {}
    for row in rows:
        names.setdefault(row["name"], row["label"])
    lowered = [token.lower() for token in tokens]
    df = {t: sum(1 for name in names if t in name.lower()) for t in lowered}
    priority = {"Card": 0, "Benefit": 1}
    scored = []
    for name, label in names.items():
        low = name.lower()
        score = sum(min(len(t), 6) / math.log(2 + df[t]) for t in lowered if df[t] and t in low)
        scored.append((-score, priority.get(label, 2), name, label))
    scored.sort()
    return {name: {"name": name, "label": label} for _, _, name, label in scored[:limit]}


def _selected_benefit_ids(subgraph, selected_entities):
    """Resolve selected Card/Benefit names to Benefit ids in the retrieved graph."""
    nodes = list((subgraph or {}).get("nodes") or [])
    selected = {str(item) for item in (selected_entities or [])}
    starts = [node for node in nodes if str(node.get("name", "")) in selected
              and node.get("label") in {"Card", "Benefit"}]
    benefit_ids = {str(node.get("id")) for node in starts if node.get("label") == "Benefit"
                   and node.get("id") is not None}
    card_ids = {str(node.get("id")) for node in starts if node.get("label") == "Card"
                and node.get("id") is not None}
    for edge in (subgraph or {}).get("edges") or []:
        if edge.get("type") == "OFFERS" and str(edge.get("source")) in card_ids:
            target = str(edge.get("target"))
            if any(str(node.get("id")) == target and node.get("label") == "Benefit" for node in nodes):
                benefit_ids.add(target)
    return benefit_ids


def _make_list_entities(db, schema: str):
    def list_entities(question: str | None = None) -> list[dict]:
        q = question if question is not None else _CURRENT_QUESTION.get()
        tokens = []
        for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", q):
            if token not in tokens:
                tokens.append(token)
            if len(tokens) == 12:
                break
        patterns = [f"%{token}%" for token in tokens]
        # 이름순 상한(300)은 흔한 단어가 많이 걸리면 정답 엔티티를 잘라 낸다(실측: 하나카드 12문항 중 3개).
        # 일치한 행을 모두 가져와(안전 상한 5000) 파이썬에서 단어 중요도(흔한 단어는 낮게) 순으로 정렬한다.
        matched = db.run_query(
            f"select name, label from {schema}.nodes "
            "where label <> 'Document' and name ilike any(%(patterns)s) limit 5000",
            {"patterns": patterns},
        ) if patterns else []
        unique = _rank_candidates(matched, tokens)
        remaining = max(0, 500 - len(unique))
        if remaining:
            supplemental = db.run_query(
                f"select name, label from {schema}.nodes "
                "where label in ('Card', 'Benefit') and not (name = any(%(names)s)) "
                "order by case label when 'Card' then 0 else 1 end, name limit %(limit)s",
                {"names": list(unique), "limit": remaining},
            )
            for row in supplemental:
                unique.setdefault(row["name"], {"name": row["name"], "label": row["label"]})
                if len(unique) == 500:
                    break
        return list(unique.values())
    return list_entities


def _dedupe_retrieved_subgraph(subgraph: dict) -> dict:
    """Apply only validated within-card links when the opt-in flag is enabled."""
    enabled = os.environ.get("FP_ENTITY_DEDUPE", "").strip().lower() in {"1", "true", "yes", "on"}
    mapping_path = os.environ.get("FP_ENTITY_LINKS_CSV")
    if not enabled or not mapping_path:
        return subgraph
    try:
        from ..graph.entity_links_loader import validate_links
        from .retrieval.entity_dedupe import dedupe_subgraph
    except ImportError:  # Script-style imports from this directory.
        from retrieval.entity_dedupe import dedupe_subgraph
        from payment_card.file_pipeline.graph.entity_links_loader import validate_links
    report = validate_links(within_csv=Path(mapping_path).expanduser())
    if report["errors"]:
        raise ValueError("invalid FP_ENTITY_LINKS_CSV: " + "; ".join(report["errors"]))
    return dedupe_subgraph(subgraph, report["merge_mapping"])


def apply(schema: str = "fp_chat"):
    """Configure chatbot db/rag modules for a validated PostgreSQL schema (opt in)."""
    if not isinstance(schema, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("schema must match [A-Za-z_][A-Za-z0-9_]*")
    global _ORIGINAL_ANSWER, _ORIGINAL_LIST_ENTITIES, _ORIGINAL_ANALYZE
    global _ORIGINAL_EXPLORE, _ORIGINAL_GENERATE_STREAM, _ORIGINAL_ANSWER_SYSTEM, _ORIGINAL_LLM_STREAM
    global _ORIGINAL_RUN_QUERY, _POOL_RUN_QUERY, _PATCHED_DB
    db = _load_modules()
    if _ORIGINAL_RUN_QUERY is None:
        _ORIGINAL_RUN_QUERY = db.run_query
        _PATCHED_DB = db
    if __import__("os").environ.get("FP_DB_POOL") == "0":
        db.run_query = _ORIGINAL_RUN_QUERY
    else:
        if _POOL_RUN_QUERY is None:
            _POOL_RUN_QUERY = PoolQueryRunner(_ORIGINAL_RUN_QUERY)
        db.run_query = _POOL_RUN_QUERY
    db.SCHEMA = schema
    db.NODES = f"{schema}.nodes"
    db.EDGES = f"{schema}.edges"
    import rag  # noqa: PLC0415
    importlib = __import__("importlib")
    importlib.reload(rag)  # REACH_SQL is constructed from db constants at import time.
    if _ORIGINAL_ANSWER is None:
        _ORIGINAL_ANSWER = rag.answer
        _ORIGINAL_LIST_ENTITIES = getattr(rag, "list_entities", None)
        _ORIGINAL_ANALYZE = getattr(rag, "analyze", None)
        _ORIGINAL_EXPLORE = getattr(rag, "explore", None)
        _ORIGINAL_GENERATE_STREAM = getattr(rag, "generate_stream", None)
    if _ORIGINAL_ANSWER_SYSTEM is None:
        _ORIGINAL_ANSWER_SYSTEM = getattr(rag, "ANSWER_SYSTEM", "")
    try:
        from .answer.answer_format import get_answer_format_version, select_answer_system
    except ImportError:
        from answer.answer_format import get_answer_format_version, select_answer_system
    legacy = os.environ.get("FP_ANSWER_FORMAT", "v2").strip().lower() == "legacy"
    selected_answer_format_version = "legacy" if legacy else get_answer_format_version()
    rag.ANSWER_SYSTEM = _ORIGINAL_ANSWER_SYSTEM if legacy else select_answer_system()
    rag.list_entities = _make_list_entities(db, schema)
    original_answer = _ORIGINAL_ANSWER
    original_analyze = _ORIGINAL_ANALYZE
    original_explore = _ORIGINAL_EXPLORE
    original_generate_stream = _ORIGINAL_GENERATE_STREAM
    if (_source_label_enabled() and getattr(rag, "llm", None) is not None
            and callable(getattr(rag.llm, "stream", None))):
        if _ORIGINAL_LLM_STREAM is None:
            _ORIGINAL_LLM_STREAM = rag.llm.stream
        original_llm_stream = _ORIGINAL_LLM_STREAM

        def source_aware_llm_stream(system_prompt, messages, *args, **kwargs):
            prompt = _SOURCE_LABEL_SYSTEM.get()
            return original_llm_stream(prompt if prompt is not None else system_prompt, messages, *args, **kwargs)

        rag.llm.stream = source_aware_llm_stream

    def list_entities(question: str | None = None):
        capture = _ANSWER_CAPTURE.get()
        started = time.perf_counter()
        try:
            return _make_list_entities(db, schema)(question)
        finally:
            if capture is not None:
                capture["latency_ms"]["entities_db"] = (time.perf_counter() - started) * 1000

    rag.list_entities = list_entities

    def answer(question: str, history=None):
        token = _CURRENT_QUESTION.set(question)
        if not os.environ.get("FP_QA_LOG"):
            try:
                return original_answer(question, history)
            finally:
                _CURRENT_QUESTION.reset(token)
        capture = {"latency_ms": {}, "selected_entities": []}
        capture_token = _ANSWER_CAPTURE.set(capture)
        usage_module = sys.modules.get("llm")
        usage_before = None
        try:
            if usage_module is not None and callable(getattr(usage_module, "usage_totals", None)):
                usage_before = usage_module.usage_totals()
        except Exception:
            usage_before = None
        started = time.perf_counter()
        try:
            result = original_answer(question, history)
            if not isinstance(result, dict):
                return result
            result["selected_entities"] = list(capture["selected_entities"])
            try:
                from .answer import answer_eval
                from . import qa_log
            except ImportError:
                from answer import answer_eval
                import qa_log
            stages = capture["latency_ms"]
            stages["total"] = (time.perf_counter() - started) * 1000
            usage_after = None
            try:
                if usage_module is not None and callable(getattr(usage_module, "usage_totals", None)):
                    usage_after = usage_module.usage_totals()
            except Exception:
                usage_after = None
            usage = None
            if usage_after is not None:
                usage = {key: max(0, usage_after.get(key, 0) - (usage_before or {}).get(key, 0))
                         for key in ("prompt_tokens", "completion_tokens", "cost_usd")}
            subgraph = result.get("subgraph") or {}
            try:
                try:
                    from .answer.answer_check import check_answer_numbers
                except ImportError:
                    from answer.answer_check import check_answer_numbers
                seed_benefit_ids = _selected_benefit_ids(subgraph, capture["selected_entities"])
                number_check = check_answer_numbers(
                    str(result.get("answer", "")), subgraph, seed_benefit_ids=seed_benefit_ids,
                )
            except Exception:
                number_check = {"error": "check_failed"}
                print("FP_NUMBER_CHECK_ERROR:check_failed", file=sys.stderr)
            refs, evidence_error = [], None
            fp_ids = [str(n.get("props", {}).get("fp_id")) for n in subgraph.get("nodes", [])
                      if n.get("props", {}).get("fp_id") and not str(n["props"]["fp_id"]).startswith("doc:")]
            try:
                # 문서 전체 근거를 끌어오지 않는다: 검색된 노드에 직접 붙은 근거와,
                # 양 끝 노드가 모두 검색된 엣지의 근거만 출처로 기록한다.
                refs = db.run_query(
                    "select distinct e.node_id, e.edge_id, e.doc_sha256, e.page_no, e.start_pos, e.end_pos, e.quote_status "
                    "from public.fp_evidence e left join public.fp_edges edge on edge.id = e.edge_id "
                    "where e.node_id = any(%(node_ids)s) "
                    "or (edge.source_id = any(%(node_ids)s) and edge.target_id = any(%(node_ids)s)) "
                    "order by e.doc_sha256, e.page_no, e.start_pos limit 1000",
                    {"node_ids": fp_ids},
                )
            except Exception:
                refs, evidence_error = [], "source_refs_query_error"
            try:
                record = qa_log.build_record(
                    question=question, answer=result.get("answer", ""), result=result,
                    model=getattr(usage_module, "MODEL", None), usage=usage,
                    latency_ms=stages, answer_format_version=selected_answer_format_version,
                    graph_schema=schema, source_refs=refs, evidence_error=evidence_error,
                    app_version=os.environ.get("GIT_COMMIT") or os.environ.get("GITHUB_SHA"),
                    number_check=number_check,
                )
                record["refusal"] = answer_eval._refusal(str(result.get("answer", "")))
                qa_log.write_record(record)
            except Exception:
                print("FP_QA_LOG_ERROR:record_error", file=sys.stderr)
            return result
        finally:
            _ANSWER_CAPTURE.reset(capture_token)
            _CURRENT_QUESTION.reset(token)

    rag.answer = answer
    if original_analyze is not None:
        def analyze(question: str, entities: list[dict]):
            # app.py calls analyze(question, list_entities()) directly; retrieve keyword candidates there too.
            if not _CURRENT_QUESTION.get():
                entities = rag.list_entities(question)
            capture = _ANSWER_CAPTURE.get()
            started = time.perf_counter()
            if _analysis_cache_enabled():
                key = _analysis_cache_key(question)
                value = _cached_analysis(key, original_analyze) if key is not None else None
                if value is None:
                    value = original_analyze(question, entities)
                    if key is not None:
                        _store_analysis(key, value)
                    value = copy.deepcopy(value)
            else:
                value = original_analyze(question, entities)
            if os.environ.get("FP_SEED_UNION", "").strip().lower() in {"1", "true", "yes", "on"}:
                try:
                    value._fp_seed_candidates = list(entities or [])
                except (AttributeError, TypeError):
                    pass
            if capture is not None:
                capture["latency_ms"]["analyze_llm"] = (time.perf_counter() - started) * 1000
                capture["selected_entities"] = list(getattr(value, "entities", []) or [])
            return value
        rag.analyze = analyze

    def explore(analysis):
        capture = _ANSWER_CAPTURE.get()
        started = time.perf_counter()
        try:
            if os.environ.get("FP_SEED_UNION", "").strip().lower() in {"1", "true", "yes", "on"}:
                try:
                    from .retrieval.seed_union import union_seed_names
                except ImportError:
                    from retrieval.seed_union import union_seed_names
                analysis.entities = union_seed_names(
                    _CURRENT_QUESTION.get(), getattr(analysis, "_fp_seed_candidates", []),
                    getattr(analysis, "entities", []) or [],
                )
                if capture is not None:
                    capture["selected_entities"] = list(analysis.entities)
            subgraph = _dedupe_retrieved_subgraph(original_explore(analysis))
            return _annotate_source_labels(db, subgraph) if _source_label_enabled() else subgraph
        finally:
            if capture is not None:
                capture["latency_ms"]["explore_db"] = (time.perf_counter() - started) * 1000

    def generate_stream(question, sub, history=None):
        capture = _ANSWER_CAPTURE.get()
        started = time.perf_counter()
        first = None
        source_prompt_token = None
        try:
            if _source_label_enabled():
                try:
                    from .answer.answer_format import with_source_label_rule
                except ImportError:
                    from answer.answer_format import with_source_label_rule
                source_prompt_token = _SOURCE_LABEL_SYSTEM.set(
                    with_source_label_rule(rag.ANSWER_SYSTEM, sub)
                )
            for chunk in original_generate_stream(question, sub, history):
                if first is None:
                    first = time.perf_counter()
                    if capture is not None:
                        capture["latency_ms"]["first_token"] = (first - started) * 1000
                yield chunk
        finally:
            if source_prompt_token is not None:
                _SOURCE_LABEL_SYSTEM.reset(source_prompt_token)
            if capture is not None and first is None:
                capture["latency_ms"]["first_token"] = None

    rag.explore = explore
    rag.generate_stream = generate_stream
    return rag


def restore():
    """Restore the team DB query function and the original answer prompt."""
    global _PATCHED_DB
    if _PATCHED_DB is not None and _ORIGINAL_RUN_QUERY is not None:
        _PATCHED_DB.run_query = _ORIGINAL_RUN_QUERY
    rag = sys.modules.get("rag")
    if rag is not None and _ORIGINAL_ANSWER_SYSTEM is not None:
        rag.ANSWER_SYSTEM = _ORIGINAL_ANSWER_SYSTEM
    if rag is not None and _ORIGINAL_LLM_STREAM is not None and getattr(rag, "llm", None) is not None:
        rag.llm.stream = _ORIGINAL_LLM_STREAM
