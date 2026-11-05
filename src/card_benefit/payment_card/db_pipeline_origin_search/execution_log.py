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
from uuid import uuid4

from card_benefit.payment_card.db_pipeline.embedding_service import EMBEDDING_LOG_KEYS
from card_benefit.payment_card.db_pipeline.document_repository import MAPPER_ROOT
from card_benefit.payment_card.db_pipeline_origin_search.benefit_search_service import BenefitSearchService
from common.database_manager import DatabaseManager
from common.postgres_db_session import PostgresDbSession
from common.query_logger import DEFAULT_SENSITIVE_KEYS
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
    return json.dumps(detail, ensure_ascii=False, indent=2, default=str)


def outcome_pdf_evidence_text(outcome: dict | None) -> str | None:
    """Serialize every PDF evidence item exactly from the final GraphRAG state."""
    if not outcome or not outcome.get("evidence"):
        return None
    return json.dumps(outcome["evidence"], ensure_ascii=False, indent=2, default=str)


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


def request_pipeline(base_pipeline, search_mode: str):
    """B/C 검색에서만 요청 전용 PostgreSQL 세션을 사용해 쿼리 로그를 분리한다."""
    if (search_mode == "A" or base_pipeline.benefit_search is None
            or not isinstance(base_pipeline.benefit_search, BenefitSearchService)):   # N은 PostgreSQL 세션이 없다
        return base_pipeline, lambda: None

    logger = logging.Logger(f"card_search.sql.capture.{uuid4().hex}", level=logging.INFO)
    logger.propagate = False
    handler = SQLCaptureHandler()
    logger.addHandler(handler)
    session = None
    original = base_pipeline.benefit_search
    try:
        session = PostgresDbSession(
            mapper_root=MAPPER_ROOT,
            camel_case_keys=False,
            database_manager=original.repository.sql_session.database_manager,
            sql_log_mode="combined",
            sensitive_log_keys=(*DEFAULT_SENSITIVE_KEYS, *EMBEDDING_LOG_KEYS),
        )
        session.query_logger.logger = logger
        benefit_search = BenefitSearchService(session, original.embedder, original.neo4j_search)
        pipeline = base_pipeline.__class__(
            base_pipeline.search,
            base_pipeline.interpret_llm,
            base_pipeline.answer_llm,
            benefit_search=benefit_search,
            search_mode=search_mode,
        )
    except Exception as error:
        logger.removeHandler(handler)
        handler.close()
        LOG.warning("요청별 SQL 수집기 준비 실패 (%s); 기존 검색 경로를 사용합니다.", type(error).__name__)
        return base_pipeline, lambda: None

    def cleanup() -> None:
        logger.removeHandler(handler)
        handler.close()

    return pipeline, cleanup


def persist_app_logs(
    session_id: str,
    request_id: str,
    events: list[LogEvent],
    detail_text: str | None = None,
    pdf_evidence_text: str | None = None,
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
                            response_text, detail_text, pdf_evidence_text, error_text, created_at)
                       VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (session_id, request_id) DO UPDATE SET
                           client_ip = EXCLUDED.client_ip,
                           request_text = EXCLUDED.request_text,
                           execution_log = EXCLUDED.execution_log,
                           response_text = EXCLUDED.response_text,
                           detail_text = EXCLUDED.detail_text,
                           pdf_evidence_text = EXCLUDED.pdf_evidence_text,
                           error_text = EXCLUDED.error_text,
                           created_at = LEAST(db_pipeline.app_log.created_at, EXCLUDED.created_at)""",
                    (session_id, request_id, request_text, execution_log,
                     response_text, detail_text, pdf_evidence_text, error_text, created_at),
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
