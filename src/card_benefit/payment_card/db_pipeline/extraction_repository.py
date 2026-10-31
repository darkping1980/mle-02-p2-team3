"""AI 추출용 SQL mapper(``extraction_repository.sql``)를 호출하는 DB 접근 클래스."""

from __future__ import annotations

from common.postgres_db_session import PostgresDbSession
from psycopg.types.json import Jsonb

SYSTEM_USER_ID = "SYSTEM"   # 생성·수정 사용자 컬럼에 기록할 시스템 사용자 ID
RAW_RESPONSE_LOG_KEYS = (   # SQL 로그에서 가릴 프롬프트·응답·원문 파라미터
    "RUN_PROMPT_TXT", "CALL_RESP_RAW", "CALL_RESP_JSON", "STG_RAW_ITEM", "STG_NORMALIZED_ITEM",
    "STG_EVIDENCE_TXT", "QUOTE_TXT",
)


def _jsonb(value):
    """dict는 JSONB로 감싸고 ``None`` 은 SQL NULL로 둔다."""
    return None if value is None else Jsonb(value)


class ExtractionRepository:
    """``extraction_repository.*`` statement를 실행한다.

    DB 연결과 트랜잭션은 주입받은 ``sql_session`` 이 관리한다.
    조회 결과 key를 컬럼명 그대로 받도록 ``camel_case_keys=False`` 세션을 전달한다.
    """

    def __init__(self, sql_session: PostgresDbSession):
        self.sql_session = sql_session

    def select_card_product(self, card_id: int) -> dict | None:
        """카드 상품을 조회한다."""
        return self.sql_session.select_one("extraction_repository.select_card_product", {"CARD_ID": card_id})

    def select_doc(self, card_doc_id: str) -> dict | None:
        """추출 대상 문서를 조회한다."""
        return self.sql_session.select_one("extraction_repository.select_doc", {"CARD_DOC_ID": card_doc_id})

    def select_ai_input_chunks(self, card_doc_id: str) -> list[dict]:
        """AI 입력 청크를 조회한다. OCR 검토 대기와 제외 청크는 포함하지 않는다."""
        return self.sql_session.select_list(
            "extraction_repository.select_ai_input_chunks", {"CARD_DOC_ID": card_doc_id},
        )

    def select_blocked_pages(self, card_doc_id: str) -> list[int]:
        """내용이 있지만 AI 입력에서 제외된 페이지 번호를 반환한다."""
        rows = self.sql_session.select_list(
            "extraction_repository.select_blocked_pages", {"CARD_DOC_ID": card_doc_id},
        )
        return [row["page_no"] for row in rows]

    def insert_run(self, model_nm: str, prompt_ver: str, prompt_txt: str, run_param: dict, card_doc_id: str) -> str:
        """AI 실행을 등록하고 ``card_ai_run_id`` 를 반환한다."""
        rows = self.sql_session.execute(
            "extraction_repository.insert_run",
            {
                "RUN_MODEL_NM": model_nm,
                "RUN_PROMPT_VER": prompt_ver,
                "RUN_PROMPT_TXT": prompt_txt,
                "RUN_PARAM": _jsonb(run_param),
                "RUN_TARGET_CARD_DOC_ID": card_doc_id,
                "USER_ID": SYSTEM_USER_ID,
            },
        )
        return rows[0]["card_ai_run_id"]

    def finish_run(self, card_ai_run_id: str, status: str, note: str | None) -> None:
        """실행을 종료 상태로 바꾼다."""
        self.sql_session.execute(
            "extraction_repository.finish_run",
            {"CARD_AI_RUN_ID": card_ai_run_id, "RUN_STATUS": status, "RUN_NOTE": note, "USER_ID": SYSTEM_USER_ID},
        )

    def insert_call(self, call: dict) -> None:
        """LLM 호출 1건을 기록한다. ``call`` 의 ``CALL_RESP_JSON`` 은 dict 또는 ``None`` 이다."""
        self.sql_session.execute(
            "extraction_repository.insert_call",
            {**call, "CALL_RESP_JSON": _jsonb(call["CALL_RESP_JSON"]), "USER_ID": SYSTEM_USER_ID},
        )

    def insert_stg(self, item: dict) -> str:
        """추출 항목을 등록하고 ``card_extr_stg_id`` 를 반환한다."""
        rows = self.sql_session.execute(
            "extraction_repository.insert_stg",
            {**item, "STG_RAW_ITEM": _jsonb(item["STG_RAW_ITEM"]), "USER_ID": SYSTEM_USER_ID},
        )
        return rows[0]["card_extr_stg_id"]

    def insert_evidence(self, evidence_list: list[dict]) -> int:
        """원문 근거를 일괄 등록하고 등록 건수를 반환한다."""
        return self.sql_session.execute_many("extraction_repository.insert_evidence", evidence_list)

    def update_stg_merge(self, card_extr_stg_id: str, normalized: dict | None, parent_id: str | None, check_cd: str) -> None:
        """문서 단위 통합 결과를 항목에 기록한다."""
        self.sql_session.execute(
            "extraction_repository.update_stg_merge",
            {
                "CARD_EXTR_STG_ID": card_extr_stg_id,
                "STG_NORMALIZED_ITEM": _jsonb(normalized),
                "STG_PARENT_CARD_EXTR_STG_ID": parent_id,
                "STG_SQL_CHECK_CD": check_cd,
                "USER_ID": SYSTEM_USER_ID,
            },
        )

    def select_run_calls(self, card_ai_run_id: str) -> list[dict]:
        """실행의 호출 이력을 반환한다."""
        return self.sql_session.select_list(
            "extraction_repository.select_run_calls", {"CARD_AI_RUN_ID": card_ai_run_id},
        )

    def select_review_queue(self, card_ai_run_id: str) -> list[dict]:
        """실행의 항목을 검증 결과별로 집계한다."""
        return self.sql_session.select_list(
            "extraction_repository.select_review_queue", {"CARD_AI_RUN_ID": card_ai_run_id},
        )

    def select_contract_check(self, card_ai_run_id: str) -> list[dict]:
        """정제본을 V6 JSONB 계약 함수로 검사한 결과를 반환한다."""
        return self.sql_session.select_list(
            "extraction_repository.select_contract_check", {"CARD_AI_RUN_ID": card_ai_run_id},
        )

    def select_run_compare(self, old_run_id: str, new_run_id: str) -> list[dict]:
        """두 실행의 혜택 차이를 반환한다."""
        return self.sql_session.select_list(
            "extraction_repository.select_run_compare", {"OLD_RUN_ID": old_run_id, "NEW_RUN_ID": new_run_id},
        )
