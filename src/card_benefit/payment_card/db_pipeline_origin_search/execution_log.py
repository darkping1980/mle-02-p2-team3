"""요청별 SQL/Cypher 로그 수집과 app_log 이벤트 저장."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import json
import logging
import os
import sys
from datetime import datetime, timezone

from common.database_manager import DatabaseManager
from common.query_log_config import load_project_environment

LOG = logging.getLogger("card_search.execution_log")
LogEvent = tuple[str, str, datetime]
ACTIVE_QUERY_EVENTS: ContextVar[list[LogEvent] | None] = ContextVar("card_active_query_events", default=None)
_CYPHER_HANDLER_MARK = "card_app_query_capture"


def log_event(log_type: str, message: str) -> LogEvent:
    """이벤트 발생 시각을 UTC로 찍어 DB 저장 지연과 분리한다."""
    return log_type, message, datetime.now(timezone.utc)


def outcome_detail_text(outcome: dict | None) -> str | None:
    """Serialize the complete result data used by the detail section without rerunning retrieval."""
    if not outcome:
        return None
    answer = outcome.get("answer") or {}
    detail = {
        "status": answer.get("status"),
        "fee_rows": answer.get("fee_rows") or [],
        "points": answer.get("points") or [],
        "open_conditions": outcome.get("open_conditions") or [],
        "uncertain": answer.get("uncertain") or [],
        "data_notices": outcome.get("data_notices") or [],
    }
    if not any(detail[key] for key in ("fee_rows", "points", "open_conditions", "uncertain", "data_notices")):
        return None
    try:
        from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import entity_ref

        refs = {}
        for item in outcome.get("retrieved_data") or []:
            context = item.get("context") or {}
            node = context.get("benefit") or {}
            labels, key = context.get("benefit_labels"), node.get("key")
            logical_id = item.get("entity_ref")
            if not logical_id:
                continue
            if not key or not labels or entity_ref(key) != logical_id:
                refs.setdefault(logical_id, []).append(None)
                continue
            ref = {"labels": labels, "key": key, "name": node.get("name")}
            refs.setdefault(logical_id, []).append(ref)
        points = []
        for point in detail["points"]:
            candidates = refs.get(point.get("benefit_id"), []) if point.get("benefit_id") else []
            ref = candidates[0] if candidates and all(candidate == candidates[0] for candidate in candidates) else None
            points.append({**point, "neo4j_ref": ref})
        detail["points"] = points
    except Exception:
        LOG.exception("Detail provenance logging failed")
        try:
            detail["points"] = [{**point, "neo4j_ref": None} for point in detail["points"]]
        except Exception:
            LOG.exception("Detail points logging failed")
            return None
    try:
        return json.dumps(detail, ensure_ascii=False, indent=2, default=str)
    except Exception:
        LOG.exception("Detail logging failed")
        return None


def outcome_pdf_evidence_text(outcome: dict | None) -> str | None:
    """Add graph provenance only at logging time; answer evidence remains unchanged."""
    if not outcome or not outcome.get("evidence"):
        return None
    try:
        from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import source
        result = [dict(item) for item in outcome["evidence"]]
        indexed = {item["evidence_id"]: item for item in result}
        for detail in outcome.get("retrieved_data") or []:
            for row in detail.get("evidence") or []:
                evidence = row.get("evidence") or {}
                target = indexed.get(source(evidence).get("evidence_id"))
                if target is None:
                    continue
                owner = row.get("owner") or {}
                if row.get("owner_labels") and owner:
                    entry = {"labels": row["owner_labels"], "key": owner.get("key"),
                             "name": owner.get("name") or owner.get("product_nm"),
                             "rule_key": row.get("rule_key"), "relationship_type": "dp_supported_by",
                             "relationship_properties": {k: v for k, v in (row.get("diagnostic_link") or row.get("link") or {}).items() if k != "source_json"}}
                    owners = target.setdefault("owners", [])
                    if entry not in owners:
                        owners.append(entry)
                if row.get("evidence_labels"):
                    target["evidence_labels"] = row["evidence_labels"]
                if evidence.get("key") is not None:
                    target["evidence_key"] = evidence["key"]
                chunk_node, page_node, doc_node = (row.get("chunk") or {}, row.get("page") or {}, row.get("document") or {})
                chunk, page, doc = ({**source(node), **node} for node in (chunk_node, page_node, doc_node))
                if chunk or page or doc:
                    location = {"card_doc_id": doc.get("card_doc_id"), "doc_title": doc.get("doc_title"),
                                "doc_file_nm": doc.get("doc_file_nm"), "doc_source_url": doc.get("doc_source_url"),
                                "doc_sha256": doc.get("doc_sha256"), "page_no": page.get("page_no"),
                                "card_doc_chunk_id": chunk.get("card_doc_chunk_id"), "chunk_key": chunk.get("key"),
                                "chunk_seq": chunk.get("chunk_seq"), "chunk_start_pos": chunk.get("chunk_start_pos"),
                                "chunk_end_pos": chunk.get("chunk_end_pos"), "start_pos": evidence.get("start_pos"),
                                "end_pos": evidence.get("end_pos")}
                    locations = target.setdefault("locations", [])
                    if location not in locations:
                        locations.append(location)
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    except Exception:
        LOG.exception("PDF evidence provenance logging failed")
        try:
            return json.dumps(outcome["evidence"], ensure_ascii=False, indent=2, default=str)
        except Exception:
            LOG.exception("PDF evidence logging failed")
            return None


def _summary_value(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def outcome_neo4j_summary(outcome: dict | None) -> str | None:
    """Render only Neo4j provenance already present on the final outcome."""
    try:
        detail_text = outcome_detail_text(outcome)
        if not detail_text:
            return None
        detail = json.loads(detail_text)
        points = detail.get("points") or []
        rendered = []
        if detail.get("status"):
            rendered.append(f"답변 검증: {detail['status']}")
            rendered.append("구조화 값 검증 상태이며 PDF 원문 검증 상태와는 별도입니다.")
            rendered.append("")
        for point in points:
            ref = point.get("neo4j_ref") or {}
            benefit_id = point.get("benefit_id")
            if not ref and not benefit_id:
                continue
            title = point.get("benefit_name") or point.get("text") or benefit_id or "혜택"
            rendered.append(f"혜택: {title}")
            if ref:
                rendered.append(f"노드 Label: {_summary_value(ref.get('labels')) or '확인된 값 없음'}")
                rendered.append(f"노드 Key: {_summary_value(ref.get('key')) or '확인된 값 없음'}")
                rendered.append(f"논리적 혜택 ID: {benefit_id or '확인된 값 없음'}")
            status = point.get("verification_status") or point.get("verification_status_cd")
            if status:
                rendered.append(f"답변 검증: {status}")
            elif point.get("origin") == "PROGRAM_DERIVED":
                rendered.append("답변 검증: 프로그램 계산 결과 (Neo4j 저장값으로 표시하지 않음)")
            if point.get("evidence_ids"):
                rendered.append("근거 관계: dp_supported_by")
                rendered.extend(f"Evidence ID: {evidence_id}" for evidence_id in dict.fromkeys(point["evidence_ids"]))
            rendered.append("")
        if not rendered:
            return None
        header = ["[답변에 연결된 Neo4j 정보]", ""]
        return "\n".join(header + rendered).rstrip()
    except Exception:
        LOG.exception("Neo4j summary logging failed")
        return None


def outcome_pdf_evidence_summary(outcome: dict | None) -> str | None:
    """Summarize cited and uncited PDF evidence without changing source quotes."""
    try:
        raw = outcome_pdf_evidence_text(outcome)
        if not raw:
            return None
        evidence_rows = json.loads(raw)
        if not isinstance(evidence_rows, list):
            return None
        answer = (outcome or {}).get("answer") or {}
        cited = {str(eid) for point in answer.get("points") or []
                 for eid in point.get("evidence_ids") or [] if eid is not None}
        lines = ["[답변에 실제 사용된 PDF 근거]", ""]
        uncited_lines = []
        for item in evidence_rows:
            if not isinstance(item, dict):
                continue
            evidence_id = item.get("evidence_id")
            locations = item.get("locations") or [{}]
            owners = item.get("owners") or [{}]
            target = lines if str(evidence_id) in cited else uncited_lines
            for location in locations:
                if not isinstance(location, dict):
                    continue
                doc_title = location.get("doc_title") or item.get("doc_title")
                file_name = location.get("doc_file_nm") or item.get("doc_file_nm")
                doc_id = location.get("card_doc_id") or item.get("card_doc_id")
                page_no = location.get("page_no") or item.get("page_no")
                chunk_id = location.get("card_doc_chunk_id") or location.get("chunk_key") or item.get("card_doc_chunk_id")
                target.append(f"문서: {doc_title or '확인된 값 없음'}")
                if file_name is not None: target.append(f"원본 파일: {file_name}")
                if doc_id is not None: target.append(f"문서 ID: {doc_id}")
                if page_no is not None: target.append(f"페이지: {page_no}")
                if chunk_id is not None: target.append(f"청크 ID: {chunk_id}")
                if evidence_id is not None: target.append(f"근거 ID: {evidence_id}")
                quote = item.get("quote_txt", item.get("quote"))
                if quote is not None: target.append(f"원문: {json.dumps(quote, ensure_ascii=False)}")
                target.append("")
            for owner in owners:
                if not isinstance(owner, dict):
                    continue
                target.append(f"근거 소유 관계: {owner.get('relationship_type') or '확인된 관계 없음'}")
                if owner.get("labels") is not None: target.append(f"소유 노드 Label: {_summary_value(owner['labels'])}")
                if owner.get("key") is not None: target.append(f"소유 노드 Key: {_summary_value(owner['key'])}")
                target.append("")
        if uncited_lines:
            lines.extend(["[검색되었으나 답변에서 인용하지 않은 근거]", "", *uncited_lines])
        return "\n".join(lines).rstrip() if len(lines) > 2 or uncited_lines else None
    except Exception:
        LOG.exception("PDF evidence summary logging failed")
        return None


def summaries_from_stored_app_log(detail_text: str | None, pdf_evidence_text: str | None) -> tuple[str | None, str | None]:
    """Rebuild display values from historical JSON columns only; performs no retrieval."""
    neo4j_summary = pdf_summary = None
    try:
        detail = json.loads(detail_text) if detail_text else {}
        if not isinstance(detail, dict):
            detail = {}
        retrieved = []
        for point in detail.get("points") or []:
            ref = point.get("neo4j_ref") if isinstance(point, dict) else None
            if not ref:
                continue
            key, labels = ref.get("key"), ref.get("labels")
            if key is None or not labels:
                continue
            try:
                from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import entity_ref
                logical_id = entity_ref(key)
            except Exception:
                continue
            retrieved.append({"entity_ref": logical_id, "context": {
                "benefit": {"key": key, "name": ref.get("name")}, "benefit_labels": labels}})
        neo4j_summary = outcome_neo4j_summary({"answer": detail, "retrieved_data": retrieved})
    except Exception:
        LOG.exception("Historical Neo4j summary reconstruction failed")
    try:
        evidence = json.loads(pdf_evidence_text) if pdf_evidence_text else []
        if not isinstance(evidence, list):
            evidence = []
        points = detail.get("points") if isinstance(detail, dict) else []
        pdf_summary = outcome_pdf_evidence_summary({"answer": {"points": points or []}, "evidence": evidence})
    except Exception:
        LOG.exception("Historical PDF summary reconstruction failed")
    return neo4j_summary, pdf_summary


def app_db_log_enabled() -> bool:
    """APP_DB_LOG_ENABLED 기본값은 ON. 명시적으로 false 계열이면 저장/상세 수집을 끈다."""
    load_project_environment()
    value = os.getenv("APP_DB_LOG_ENABLED", "on").strip().lower()
    return value not in {"0", "false", "no", "off"}


@lru_cache(maxsize=1)
def _log_database_manager() -> DatabaseManager:
    """로그 저장 connection pool을 앱 프로세스에서 한 번만 만든다."""
    return DatabaseManager()


class SQLCaptureHandler(logging.Handler):
    """공통 QueryLogger의 렌더링 SQL을 요청 컨텍스트에 전달한다."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.console = logging.StreamHandler(sys.stderr)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno >= logging.WARNING:
                self.console.emit(record)
                return
            message = record.getMessage()
            if message.startswith("QUERY ["):
                events = ACTIVE_QUERY_EVENTS.get()
                if events is not None:
                    events.append(log_event("QUERY", message))
        except Exception as error:
            LOG.warning("SQL 로그 수집 실패 (%s)", type(error).__name__)

    def close(self) -> None:
        self.console.close()
        super().close()


class CypherCaptureHandler(logging.Handler):
    """Cypher 전문은 요청 중에만 수집하고 warning/error는 stderr로 전달한다."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.console = logging.StreamHandler(sys.stderr)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno >= logging.WARNING:
                self.console.emit(record)
                return
            message = record.getMessage()
            events = ACTIVE_QUERY_EVENTS.get()
            if events is not None and message.startswith("QUERY ["):
                events.append(log_event("QUERY", message))
        except Exception as error:
            LOG.warning("Cypher 로그 수집 실패 (%s)", type(error).__name__)

    def close(self) -> None:
        self.console.close()
        super().close()


def configure_application_logging(db_logging_enabled: bool, cypher_logger_name: str) -> None:
    """상세 공통 SQL/Cypher 콘솔 출력을 끄고 경고 이상은 유지한다."""
    for name in ("car_search_rag.sql", "car_search_rag.neo4j", "card_search_rag",
                 "openai", "httpx", "httpcore", "neo4j", "langchain", "langgraph"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logger = logging.getLogger(cypher_logger_name)
    logger.propagate = False
    handlers = [handler for handler in logger.handlers if getattr(handler, _CYPHER_HANDLER_MARK, False)]
    if not handlers:
        handler = CypherCaptureHandler()
        setattr(handler, _CYPHER_HANDLER_MARK, True)
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if db_logging_enabled else logging.WARNING)


@contextmanager
def capture_request_queries():
    """한 동기식 요청 안의 SQL/Cypher 이벤트를 독립 버퍼에 수집한다."""
    events: list[LogEvent] = []
    token = ACTIVE_QUERY_EVENTS.set(events)
    try:
        yield events
    finally:
        ACTIVE_QUERY_EVENTS.reset(token)


def persist_app_logs(
    session_id: str,
    request_id: str,
    events: list[LogEvent],
    detail_text: str | None = None,
    pdf_evidence_text: str | None = None,
    neo4j_summary: str | None = None,
    pdf_evidence_summary: str | None = None,
) -> None:
    """요청의 이벤트를 요청당 한 행으로 모아 INSERT한다. 저장 예외는 검색으로 전파하지 않는다."""
    if not events:
        return

    ordered_events = sorted(events, key=lambda event: event[2])
    request_events = [message for log_type, message, _ in ordered_events if log_type == "REQUEST"]
    query_events = [message for log_type, message, _ in ordered_events if log_type == "QUERY"]
    response_events = [message for log_type, message, _ in ordered_events if log_type == "RESPONSE"]
    error_events = [message for log_type, message, _ in ordered_events if log_type == "ERROR"]
    request_text = request_events[0] if request_events else ""
    execution_log = "\n\n".join(query_events)
    response_text = "\n\n".join(response_events)
    error_text = "\n\n".join(error_events) or None
    created_at = next(
        (created_at for log_type, _, created_at in ordered_events if log_type == "REQUEST"),
        ordered_events[0][2],
    )

    try:
        manager = _log_database_manager()
        with manager.connect(camel_case_keys=False) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO db_pipeline.app_log
                           (session_id, request_id, client_ip, request_text, execution_log,
                            response_text, detail_text, pdf_evidence_text, neo4j_summary,
                            pdf_evidence_summary, error_text, created_at)
                       VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (session_id, request_id) DO UPDATE SET
                           client_ip = EXCLUDED.client_ip,
                           request_text = EXCLUDED.request_text,
                           execution_log = EXCLUDED.execution_log,
                           response_text = EXCLUDED.response_text,
                           detail_text = EXCLUDED.detail_text,
                           pdf_evidence_text = EXCLUDED.pdf_evidence_text,
                           neo4j_summary = EXCLUDED.neo4j_summary,
                           pdf_evidence_summary = EXCLUDED.pdf_evidence_summary,
                           error_text = EXCLUDED.error_text,
                           created_at = LEAST(db_pipeline.app_log.created_at, EXCLUDED.created_at)""",
                    (session_id, request_id, request_text, execution_log,
                     response_text, detail_text, pdf_evidence_text, neo4j_summary,
                     pdf_evidence_summary, error_text, created_at),
                )
    except Exception as error:
        LOG.warning("검색 로그 저장 실패 (%s); 검색 결과는 유지합니다.", type(error).__name__)


def response_message(outcome: dict) -> str:
    """로그용 최종 사용자 응답만 선택한다. 내부 context/원문 덤프는 저장하지 않는다."""
    answer = outcome.get("answer") or {}
    return str(answer.get("answer_text") or answer.get("conclusion") or answer.get("message") or "")


def error_message(outcome: dict | None) -> str:
    """예외 본문·접속정보 없이 단계와 코드만 로그에 남긴다."""
    if not outcome:
        return "검색 실행 중 처리 오류"
    error = outcome.get("error") or {}
    answer = outcome.get("answer") or {}
    status = answer.get("status")
    if error:
        return f"검색 처리 오류: stage={error.get('stage', 'unknown')} code={error.get('code', 'unknown')}"
    if status == "ERROR":
        return "검색 처리 오류: answer status=ERROR"
    return ""
