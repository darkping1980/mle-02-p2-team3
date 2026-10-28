"""PostgreSQL / Neo4j 세션이 함께 쓰는 쿼리 로그 포매터.

``QueryLogger`` 는 DB 연결을 만들거나 SQL/Cypher를 실행하지 않는다. 세션이 넘겨준
쿼리 원문, 파라미터, 반환 데이터, 측정값을 표준 ``logging`` 으로 출력하는 일만 맡는다.

DB별 차이는 세션이 콜백으로 넘긴다.

* PostgreSQL: ``psycopg.ClientCursor.mogrify()`` 로 렌더링한 SQL (``render_combined``)
* Neo4j: ``:param`` 줄을 붙인 Cypher (``render_combined``), Node/Relationship 표 표시
  (``value_formatter``), ``ResultSummary.counters`` 는 세션이 값을 모아 ``log_summary`` 로 전달

로그 포매팅 중 발생한 예외는 WARNING 로그로 남기고 삼킨다. 로그 실패가 DB 실행을
막지 않게 하기 위함이며, 로그용 값은 항상 복사본으로 만들고 원본 파라미터와 반환
데이터는 변경하지 않는다.
"""

from collections.abc import Callable, Collection, Mapping
import logging
from typing import Any, ClassVar
from unicodedata import combining, east_asian_width

LOG_DIVIDER = "=" * 72                                       # SQL/Cypher 본문 위아래에 표시할 구분선
MASKED_VALUE = "<MASKED>"                                    # 민감한 키의 로그 표시값

# 민감한 파라미터 키. 비교 시 소문자로 바꾸고 영숫자 외 문자를 제거한다.
# 6자 이상 항목은 접미사 일치(db_password 등)도 마스킹하고, 짧은 항목은 완전 일치만 본다.
DEFAULT_SENSITIVE_KEYS: tuple[str, ...] = (
    "password", "passwd", "pwd", "secret", "token", "api_key", "access_token",
    "refresh_token", "auth_token", "authorization", "client_secret", "private_key",
    "credential", "credentials",
    # 2026-10-24 로그 검증에서 추가: "token"(5자)은 접미사 규칙 대상이 아니라 api_token 등이 그대로 노출됐다.
    # 판정 규칙은 그대로 두고 자주 쓰는 자격증명 키 이름만 목록에 더한다(6자 이상이라 접미사 일치도 적용됨).
    "api_token", "session_token", "id_token", "secret_key", "secret_access_key", "passphrase",
)


def _normalize_key(key: Any) -> str:
    """민감 키 비교용으로 소문자화하고 영숫자만 남긴다. 예: ``"DB_Password"`` → ``"dbpassword"``."""
    return "".join(char for char in str(key).lower() if char.isalnum())


def is_numeric_sequence(value: Any, min_length: int) -> bool:
    """bool을 제외한 int/float만 담긴 긴 list/tuple인지 확인한다 (벡터 판정 기준)."""
    # region [Python 설명] bool은 int의 하위 타입
    # Python에서 `True`/`False`는 int의 하위 클래스라 `isinstance(True, int)`가 True다.
    # 그래서 `not isinstance(item, bool)`을 함께 검사해 True/False 목록을 벡터로 오인하지 않는다.
    # `all(...)`은 모든 항목이 조건을 만족할 때만 True이며, 하나라도 실패하면 즉시 멈춘다.
    # endregion
    return (
        isinstance(value, (list, tuple))
        and len(value) >= min_length
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    )


class QueryLogger:
    """쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다.

    Args:
        logger: 출력할 표준 logger. 상세 로그는 모두 INFO 레벨이며 logger 레벨 설정을 따른다.
        log_mode: combined, separate, none 중 하나.
        result_log: 반환 데이터를 표로 기록할지 여부. ``log_mode`` 와 독립적이다.
        result_log_limit: 결과 표에 표시할 최대 행 수. 0 이상의 정수.
        mode_option_name: 오류 메시지에 쓸 설정 이름 (``sql_log_mode`` / ``cypher_log_mode``).
        query_label: 경고 메시지에 쓸 쿼리 종류 (``SQL`` / ``Cypher``).
        vector_types: 벡터로 표시할 타입. ``dimensions()`` 와 ``to_list()`` 를 제공해야 한다.
            숫자만 담긴 긴 list/tuple은 이 설정과 무관하게 벡터로 표시한다.
        sensitive_keys: 로그에서 값을 ``<MASKED>`` 로 바꿀 키 목록. ``None`` 이면 마스킹하지 않는다.
        value_formatter: 결과 표 셀의 문자열 변환 함수 (None이 아닌 값에만 호출).
        combined_params_line: combined 렌더링 결과 아래에 ``PARAMS`` 줄을 붙일지 여부.

    Note:
        세션(``PostgresDbSession`` / ``Neo4jDbSession``)이 생성자에서 하나씩 만들어 소유한다.
        이 객체는 DB 연결이나 SQL/Cypher 실행을 하지 않고, 전달받은 값으로 로그 문자열만 만든다.
    """

    # region [Python 설명] Callable 타입 힌트와 함수 객체 전달
    # `Callable[[Any], str]`은 "인자 하나를 받아 str을 반환하는 함수"라는 타입 표기다.
    # Python에서는 함수도 객체이므로 `value_formatter=format_graph_value`처럼 인자로 넘길 수 있다.
    # Java의 `Function<Object, String>` 같은 함수형 인터페이스를 전달하는 것과 비슷하다.
    # endregion

    LOG_MODES: ClassVar[tuple[str, ...]] = ("combined", "separate", "none")  # 허용하는 로그 모드
    RESULT_LOG_COLUMN_WIDTH: ClassVar[int] = 40                              # 표의 컬럼별 최대 표시 폭
    VECTOR_LOG_PREVIEW_COUNT: ClassVar[int] = 6                              # 로그에 표시할 벡터 앞부분 값 개수
    VECTOR_LOG_SEQUENCE_MIN_LENGTH: ClassVar[int] = 32                       # 숫자 시퀀스를 벡터로 취급할 최소 길이
    BATCH_LOG_LIMIT: ClassVar[int] = 100                                     # 배치 로그에 표시할 최대 파라미터 건수
    DEFAULT_SENSITIVE_KEYS: ClassVar[tuple[str, ...]] = DEFAULT_SENSITIVE_KEYS  # 권장 마스킹 키 목록

    def __init__(
        self,
        logger: logging.Logger,
        *,
        log_mode: str = "combined",
        result_log: bool = False,
        result_log_limit: int = 100,
        mode_option_name: str = "log_mode",
        query_label: str = "SQL",
        vector_types: tuple[type, ...] = (),
        sensitive_keys: Collection[str] | None = None,
        value_formatter: Callable[[Any], str] | None = None,
        combined_params_line: bool = True,
    ) -> None:
        """로그 설정을 검증해 보관한다. 잘못된 ``log_mode`` / ``result_log_limit`` 은 ``ValueError``."""
        # `self.log_mode = ...`처럼 property에 대입하면 아래 setter가 호출되어 값이 검증된다.
        self.logger = logger
        self.mode_option_name = mode_option_name
        self.query_label = query_label
        self.vector_types = tuple(vector_types)
        self.value_formatter = value_formatter
        self.combined_params_line = combined_params_line
        self.sensitive_keys = sensitive_keys
        self.log_mode = log_mode                      # setter에서 검증
        self.result_log_limit = result_log_limit      # setter에서 검증
        self.result_log = result_log

    #=========================================================
    # 설정 검증
    #=========================================================
    # region [Python 설명] property로 대입 시 검증하기
    # 실제 값은 밑줄로 시작하는 `_log_mode`에 저장하고, 외부에는 `log_mode` property만 노출한다.
    # 밑줄 접두사는 "내부용"이라는 관례일 뿐 Java의 private처럼 접근을 막지는 않는다.
    # endregion
    @property
    def log_mode(self) -> str:
        """현재 쿼리 로그 모드."""
        return self._log_mode

    @log_mode.setter
    def log_mode(self, value: str) -> None:
        """쿼리 로그 출력 모드를 읽거나 검증해 설정한다."""
        if value not in self.LOG_MODES:
            raise ValueError(f"{self.mode_option_name} must be one of: combined, separate, none")
        self._log_mode = value

    @property
    def result_log_limit(self) -> int:
        """결과 표에 표시할 최대 행 수."""
        return self._result_log_limit

    @result_log_limit.setter
    def result_log_limit(self, value: int) -> None:
        # True/False도 int로 판정되므로 bool을 먼저 거부한다.
        """결과 로그의 최대 행 수를 읽거나 검증해 설정한다."""
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("result_log_limit must be a non-negative integer")
        self._result_log_limit = value

    @property
    def sensitive_keys(self) -> tuple[str, ...]:
        """마스킹할 키 이름 목록(설정한 원래 표기)."""
        return self._sensitive_keys

    @sensitive_keys.setter
    def sensitive_keys(self, value: Collection[str] | None) -> None:
        # 문자열도 문자 단위로 순회 가능한 Collection이라 "password"를 넣으면 글자별 키가 되므로 막는다.
        # 비교에 쓸 정규화 결과(완전 일치용 frozenset, 접미사 비교용 tuple)를 미리 만들어 둔다.
        """로그에서 숨길 매개변수 키 목록을 읽거나 설정한다."""
        if isinstance(value, str):
            raise ValueError("sensitive_keys must be a collection of key names, not a string")
        self._sensitive_keys = tuple(value or ())
        normalized = [_normalize_key(key) for key in self._sensitive_keys]
        self._exact_keys = frozenset(normalized)
        self._suffix_keys = tuple(key for key in normalized if len(key) >= 6)

    def enabled(self) -> bool:
        """상세 로그가 출력되는 레벨인지 확인한다. 꺼져 있으면 렌더링 비용을 쓰지 않는다."""
        return self.logger.isEnabledFor(logging.INFO)

    #=========================================================
    # 로그용 파라미터 표현
    #=========================================================
    def is_sensitive_key(self, key: Any) -> bool:
        """키가 민감 키 목록과 완전 일치하거나, 6자 이상 항목으로 끝나면 True를 반환한다."""
        if not self._exact_keys:
            return False
        normalized = _normalize_key(key)
        # `str.endswith(tuple)`은 tuple의 접미사 중 하나라도 일치하면 True다.
        return normalized in self._exact_keys or normalized.endswith(self._suffix_keys)

    def format_vector_preview(self, values: list | tuple, dimension: int) -> str:
        """벡터 앞부분만 표시할 로그 문자열을 만든다."""
        preview = ", ".join(f"{item:.6f}" for item in values[:self.VECTOR_LOG_PREVIEW_COUNT])
        if dimension > self.VECTOR_LOG_PREVIEW_COUNT:
            preview += ", ..."
        return f"<VECTOR [{preview}] dimension={dimension}>"

    def sanitize(self, value: Any) -> Any:
        """로그용 복사본에서 벡터는 앞부분과 차원만, 민감한 키는 마스킹 값으로 표시한다."""
        # region [Python 설명] 재귀 함수와 dict/list/tuple comprehension
        # dict/list/tuple 안에 또 dict/list가 있을 수 있으므로 자기 자신(`self.sanitize`)을 다시 호출한다.
        # `{key: ... for key, item in value.items()}`는 새 dict를, `[... for item in value]`는 새 list를 만든다.
        # 원본 객체를 고치지 않고 항상 새 컨테이너를 만들기 때문에 DB에 전달할 원본 파라미터는 그대로 유지된다.
        # 문자열·숫자 같은 그 밖의 값은 변경할 수 없는(immutable) 값이라 그대로 반환해도 안전하다.
        # `isinstance(value, self.vector_types)`처럼 두 번째 인자에 tuple을 주면 그중 하나라도 맞으면 True다.
        # endregion
        if self.vector_types and isinstance(value, self.vector_types):
            dimension = value.dimensions()
            try:
                return self.format_vector_preview(value.to_list(), dimension)
            except Exception:
                return f"<VECTOR dimension={dimension}>"
        if isinstance(value, dict):
            return {key: MASKED_VALUE if self.is_sensitive_key(key) else self.sanitize(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            if is_numeric_sequence(value, self.VECTOR_LOG_SEQUENCE_MIN_LENGTH):
                return self.format_vector_preview(value, len(value))
            return [self.sanitize(item) for item in value]
        if isinstance(value, tuple):
            if is_numeric_sequence(value, self.VECTOR_LOG_SEQUENCE_MIN_LENGTH):
                return self.format_vector_preview(value, len(value))
            return tuple(self.sanitize(item) for item in value)
        return value

    def mask(self, value: Any) -> Any:
        """민감한 키만 마스킹한다. 바꿀 키가 없으면 원본 객체를 그대로 돌려준다 (복사 없음)."""
        if not self._exact_keys:
            return value
        # region [Python 설명] `is`와 `==`의 차이
        # `a is b`는 두 변수가 같은 객체를 가리키는지(Java의 `==` 참조 비교),
        # `a == b`는 값이 같은지(Java의 `equals()`)를 비교한다.
        # 하위 항목이 하나도 바뀌지 않았으면(`is`로 모두 같은 객체) 새로 만든 dict 대신 원본을 돌려줘
        # 벡터처럼 큰 값이 포함된 파라미터를 불필요하게 복사하지 않는다.
        # endregion
        if isinstance(value, Mapping):
            masked = {key: MASKED_VALUE if self.is_sensitive_key(key) else self.mask(item)
                      for key, item in value.items()}
            changed = any(masked[key] is not item for key, item in value.items())
            return masked if changed else value
        if isinstance(value, (list, tuple)) and not is_numeric_sequence(value, self.VECTOR_LOG_SEQUENCE_MIN_LENGTH):
            masked_items = [self.mask(item) for item in value]
            if any(new is not old for new, old in zip(masked_items, value)):
                return masked_items if isinstance(value, list) else tuple(masked_items)
        return value

    #=========================================================
    # 쿼리 / 배치 로그
    #=========================================================
    def effective_mode(self, force: bool = False) -> str:
        """``force`` 와 설정 모드를 고려해 이번 로그에 실제로 적용할 모드를 반환한다."""
        # PostgreSQL execute()는 none 모드에서도 QUERY를 combined 형식으로 표시한다(force=True).
        return "combined" if force and self.log_mode == "none" else self.log_mode

    def log_query(
        self,
        statement_id: str,
        query: str,
        parameters: Any,
        *,
        render_combined: Callable[[Any], str] | None = None,
        force: bool = False,
    ) -> None:
        """쿼리 상세 로그를 출력한다.

        ``render_combined`` 는 combined 모드에서만 호출되며, 로그용으로 sanitize된 파라미터를
        받아 렌더링한 쿼리 문자열을 돌려준다. 렌더링이 실패하면 쿼리 원문으로 되돌린다.
        """
        log_mode = self.effective_mode(force)
        if log_mode == "none" or not self.enabled():
            return
        # region [Python 설명] logging의 `%` 지연 포매팅과 `%r`
        # `logger.info("QUERY [%s] ...", statement_id, ...)`처럼 형식 문자열과 값을 따로 넘기면
        # 실제로 출력될 때만 문자열이 조립된다(f-string은 호출 전에 항상 조립됨).
        # `%s`는 `str(값)`, `%r`은 `repr(값)`으로 바꾼다. repr은 문자열에 따옴표가 붙어 값의 타입이 잘 보인다.
        # 바깥 try는 어떤 포매팅 오류도 DB 실행으로 전파되지 않게 하는 마지막 안전장치다.
        # endregion
        try:
            try:
                log_parameters = self.sanitize(parameters or {})
            except Exception as exc:
                # 로그 변환 실패가 실제 쿼리 실행에 영향을 주지 않도록 원본 파라미터를 출력하지 않는다.
                self.logger.warning("%s 로그 파라미터 변환 실패 [%s]: %s", self.query_label, statement_id, type(exc).__name__)
                log_parameters = {}

            if log_mode == "combined" and render_combined is not None:
                try:
                    rendered = render_combined(log_parameters)
                except Exception as exc:
                    # 로그 렌더링만 실패해도 실행에는 영향을 주지 않고 쿼리 원문으로 되돌린다.
                    self.logger.warning("%s 로그 렌더링 실패 [%s]: %s", self.query_label, statement_id, type(exc).__name__)
                else:
                    if self.combined_params_line:
                        self.logger.info("QUERY [%s]\n%s\n%s\n%s\nPARAMS %r",
                                         statement_id, LOG_DIVIDER, rendered, LOG_DIVIDER, log_parameters)
                    else:
                        self.logger.info("QUERY [%s]\n%s\n%s\n%s", statement_id, LOG_DIVIDER, rendered, LOG_DIVIDER)
                    return

            self.logger.info("QUERY [%s]\n%s\n%s\n%s\nPARAMS %r",
                             statement_id, LOG_DIVIDER, query, LOG_DIVIDER, log_parameters)
        except Exception as exc:
            self._log_failure("QUERY", statement_id, exc)

    def log_batch_query(self, statement_id: str, query: str, parameters_list: list, *, force: bool = False) -> None:
        """배치 쿼리와 앞의 최대 ``BATCH_LOG_LIMIT`` 건 로그용 파라미터를 실행 전에 기록한다.

        ``force=True`` 이면 ``log_mode`` 가 none이어도 출력한다 (PostgreSQL 기존 동작).
        """
        if (self.log_mode == "none" and not force) or not self.enabled():
            return
        try:
            # 여러 줄을 list에 모아 마지막에 한 번의 INFO 로그로 출력한다.
            # `parameters_list[:LIMIT]`는 앞쪽 최대 LIMIT 건만 잘라낸 새 list다.
            total = len(parameters_list)
            lines = [
                f"BATCH QUERY [{statement_id}]",
                LOG_DIVIDER,
                query,
                LOG_DIVIDER,
                f"BATCH PARAMS rows={total}",
            ]
            for index, parameters in enumerate(parameters_list[:self.BATCH_LOG_LIMIT], start=1):
                try:
                    log_parameters = repr(self.sanitize(parameters))
                except Exception as exc:
                    # 표시용 변환 오류가 DB 실행을 막지 않도록 원본 파라미터는 로그에도 출력하지 않는다.
                    self.logger.warning("배치 로그 파라미터 변환 실패 [%s] row=%d: %s", statement_id, index, type(exc).__name__)
                    log_parameters = "<PARAMS unavailable>"
                lines.extend(("", f"[{index}/{total}]", log_parameters))

            omitted_count = total - self.BATCH_LOG_LIMIT
            if omitted_count > 0:
                lines.extend(("", "...", f"생략된 배치 파라미터: {omitted_count}건"))

            self.logger.info("%s", "\n".join(lines))
        except Exception as exc:
            self._log_failure("BATCH QUERY", statement_id, exc)

    #=========================================================
    # 실행 결과 / 성능 로그
    #=========================================================
    def log_summary(self, event: str, statement_id: str, **fields: Any) -> None:
        """``EVENT [id] key=value ...`` 한 줄을 출력한다. float는 소수 첫째 자리까지 표시한다.

        값이 ``None`` 인 항목은 측정하지 못한 값으로 보고 출력하지 않는다.
        """
        if not self.enabled():
            return
        # region [Python 설명] `**fields` 가변 키워드 인자
        # `log_summary("DONE", id, rows=3, elapsed_ms=1.2)`처럼 넘긴 이름 있는 인자들이
        # `fields = {"rows": 3, "elapsed_ms": 1.2}` dict로 모인다. dict는 넣은 순서를 유지한다.
        # endregion
        try:
            parts = [f"{event} [{statement_id}]"]
            for name, value in fields.items():
                if value is None:
                    continue
                if isinstance(value, float):
                    parts.append(f"{name}={value:.1f}")
                else:
                    parts.append(f"{name}={value}")
            self.logger.info("%s", " ".join(parts))
        except Exception as exc:
            self._log_failure(event, statement_id, exc)

    def display_width(self, value: str) -> int:
        """터미널 표시 폭을 계산한다. 한글 전각 문자는 두 칸으로 센다."""
        # region [Python 설명] unicodedata로 문자 폭 계산
        # `east_asian_width(char)`가 "F"(Fullwidth) 또는 "W"(Wide)인 한글·한자는 터미널에서 두 칸을 차지한다.
        # `combining(char)`가 0이 아니면 앞 글자에 붙는 결합 문자라 폭을 0으로 센다.
        # `len()`은 글자 수만 세므로, 표의 세로선을 맞추려면 이렇게 표시 폭을 따로 계산해야 한다.
        # endregion
        return sum(0 if combining(char) else 2 if east_asian_width(char) in ("F", "W") else 1 for char in value)

    def format_result_cell(self, value: Any) -> str:
        """표시용 값만 문자열로 바꾸고 긴 값은 컬럼 폭에 맞게 줄인다."""
        try:
            if value is None:
                text = "NULL"
            elif self.value_formatter is not None:
                text = self.value_formatter(value)
            else:
                text = str(value)
        except Exception:
            try:
                text = repr(value)
            except Exception:
                text = f"<{type(value).__name__}>"
        # 줄바꿈·탭이 표 모양을 깨지 않도록 `\n` 같은 두 글자 표기로 바꾼다.
        text = text.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
        if self.display_width(text) <= self.RESULT_LOG_COLUMN_WIDTH:
            return text
        # 폭을 넘으면 "..." 세 칸을 남기고 들어갈 수 있는 글자까지만 자른다.
        width = 0
        shortened = []
        for char in text:
            char_width = self.display_width(char)
            if width + char_width > self.RESULT_LOG_COLUMN_WIDTH - 3:
                break
            shortened.append(char)
            width += char_width
        return "".join(shortened) + "..."

    def format_result_table(self, rows: list) -> str:
        """반환된 행을 원본 변경 없이 한글 표시 폭을 고려한 ASCII 표로 만든다."""
        # dict가 아닌 행(스칼라 등)은 "value" 컬럼 하나짜리 행으로 감싸 같은 방식으로 그린다.
        # region [Python 설명] dict.fromkeys()로 순서를 유지한 중복 제거
        # `key for row in table_rows for key in row`는 이중 for문으로 모든 행의 key를 차례로 꺼낸다.
        # `dict.fromkeys(...)`는 그 key들로 dict를 만들며, dict는 처음 넣은 순서를 유지하고 중복 key를 하나로 합친다.
        # 따라서 "처음 등장한 순서대로 중복 없는 컬럼 목록"을 얻을 수 있다(set은 순서를 보장하지 않음).
        # endregion
        table_rows = rows if all(isinstance(row, dict) for row in rows) else [{"value": row} for row in rows]
        columns = list(dict.fromkeys(key for row in table_rows for key in row))
        if not columns:
            columns = ["value"]
        # 모든 셀을 문자열로 바꾼 뒤, 컬럼마다 헤더와 셀 중 가장 넓은 표시 폭을 컬럼 폭으로 정한다.
        # `(header, *(...))`의 `*`는 generator의 값들을 tuple 안에 펼쳐 넣는 unpacking 문법이다.
        headers = [self.format_result_cell(column) for column in columns]
        cells = [[self.format_result_cell(row.get(column)) for column in columns] for row in table_rows]
        widths = [max(self.display_width(cell) for cell in (header, *(row[index] for row in cells)))
                  for index, header in enumerate(headers)]
        border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

        def table_line(values: list[str]) -> str:
            """셀 문자열 목록을 컬럼 폭에 맞춰 공백으로 채운 ``| a | b |`` 한 줄로 만든다."""
            return "| " + " | ".join(
                value + " " * (width - self.display_width(value))
                for value, width in zip(values, widths)
            ) + " |"

        return "\n".join([border, table_line(headers), border,
                          *(table_line(row) for row in cells), border])

    def log_result_data(self, statement_id: str, result: Any, *, log_scalar: bool = True) -> None:
        """``result_log`` 가 켜진 경우 반환 데이터를 최대 ``result_log_limit`` 행까지 표로 출력한다.

        dict는 한 행, list는 여러 행으로 본다. 그 밖의 값은 ``log_scalar`` 가 True일 때만
        ``repr`` 로 한 줄 출력한다 (PostgreSQL rowcount 등).
        """
        if not self.result_log or not self.enabled() or result is None:
            return
        try:
            if isinstance(result, dict):
                rows = [result]
            elif isinstance(result, list):
                rows = result
            else:
                if log_scalar:
                    self.logger.info("RESULT DATA [%s] %r", statement_id, result)  # rowcount 등 스칼라 반환값
                return
            if not rows:
                self.logger.info("RESULT DATA [%s] no rows", statement_id)
                return
            shown = rows[: self.result_log_limit]
            if shown:
                self.logger.info("RESULT DATA [%s]\n%s", statement_id, self.format_result_table(shown))
            else:
                self.logger.info("RESULT DATA [%s] no rows shown", statement_id)
            if len(rows) > self.result_log_limit:
                self.logger.info(
                    "RESULT DATA truncated: showing %d of %d rows",
                    self.result_log_limit,
                    len(rows),
                )
        except Exception as exc:
            self._log_failure("RESULT DATA", statement_id, exc)

    #=========================================================
    # 트랜잭션 로그
    #=========================================================
    # 트랜잭션 로그는 세션의 상태 정리(try/finally) 바깥에서도 호출되므로, handler/filter 예외가
    # 트랜잭션 상태나 원래 예외 전파를 바꾸지 않도록 여기서 삼킨다.
    def log_transaction(self, event: str) -> None:
        """``TRANSACTION BEGIN`` / ``COMMIT`` / ``ROLLBACK`` 을 출력한다."""
        try:
            self.logger.info("TRANSACTION %s", event)
        except Exception:
            pass

    def log_transaction_failure(self, event: str, exc: BaseException) -> None:
        """commit 실패 등 트랜잭션 단계 실패를 ERROR로 남긴다. 예외 전파는 호출자가 담당한다."""
        try:
            self.logger.error("TRANSACTION %s FAILED: %s", event, type(exc).__name__)
        except Exception:
            pass

    def log_rollback_failure(self, message: str = "TRANSACTION ROLLBACK FAILED") -> None:
        """rollback 실패를 traceback과 함께 남긴다. ``except`` 블록 안에서 호출해야 한다."""
        try:
            self.logger.exception("%s", message)
        except Exception:
            pass

    def _log_failure(self, kind: str, statement_id: str, exc: Exception) -> None:
        """로그 출력 실패를 WARNING으로 남긴다. 이 경고 출력마저 실패하면 조용히 무시한다."""
        try:
            self.logger.warning("%s 로그 출력 실패 [%s]: %s", kind, statement_id, type(exc).__name__)
        except Exception:
            pass
