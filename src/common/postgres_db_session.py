"""PostgreSQL용 ``QuerySession`` 구현 모듈.

``*.sql`` mapper 파일의 named query를 aiosql로 등록하고, ``"namespace.statement"`` ID로
SELECT/변경 SQL/배치 SQL을 실행한다. 연결은 ``DatabaseManager`` pool에서 빌리고,
SQL·결과·실행 시간 로그는 ``QueryLogger`` 가 출력한다.

호출 흐름(조회):
    Repository → ``select_list("car_manual.select_car", {...})``
    → ``_query()`` 로 aiosql 함수 조회 → ``_connection()`` 으로 연결 확보
    → ``_log_query()`` 로그 → aiosql 함수 실행 → 결과 list 반환
"""

from collections.abc import Iterator                                                                                         # aiosql의 지연 조회(Iterator/Generator) 결과 여부 확인용
from contextlib import contextmanager                                                                                        # 트랜잭션과 DB 연결 사용 범위를 관리
import logging                                                                                                               # SQL 실행 내용을 표준 로그로 출력
from pathlib import Path                                                                                                     # 기능별 SQL 파일 경로 처리용
from time import perf_counter                                                                                                # 쿼리 실행 시간을 측정
from collections.abc import Collection
from typing import TYPE_CHECKING, ClassVar, Self                                                                                         # 공유 클래스 속성과 검증 메서드 반환 타입
import aiosql                                                                                                                # .sql 파일에 정의된 named query를 Python 함수 형태로 로드하는 라이브러리
from aiosql.queries import Queries                                                                                           # aiosql이 SQL 파일에서 생성하는 쿼리 모음 타입
from aiosql.utils import SQLLoadException                                                                                    # 같은 SQL 이름을 중복 등록할 때 나는 aiosql 예외

import psycopg                                                                                                               # PostgreSQL 연결 및 트랜잭션 처리용 드라이버
try:                                                                                                                         # pgvector>=0.4는 최상위, 0.3.x는 utils 모듈에 Vector가 있다
    from pgvector import Vector                                                                                              # SQL 로그에서 벡터 일부 값과 차원을 표시할 타입
except ImportError:                                                                                                          # pgvector 0.3.x(langchain-postgres 사용 환경)
    from pgvector.utils import Vector
from .database_manager import DatabaseManager                                                                                # SQL 실행에 사용할 DB 연결 관리자
from .query_logger import LOG_DIVIDER, QueryLogger, is_numeric_sequence                                                                          # SQL/결과/배치/트랜잭션 공통 로그 포매터
from .query_session import QuerySession
from collections.abc import Generator                                                                                        # Generator 타입의 지연 조회 결과 여부 확인용
import os
if TYPE_CHECKING:                                                                                                            # PGEngine은 get_pg_engine()에서만 쓰므로 타입 검사 때만 import
    from langchain_postgres import PGEngine                                                                                  # LangChain에서 PostgreSQL/PGVector 연결 및 테이블 관리를 위한 엔진
from sqlalchemy.engine import make_url                                                                                       # PostgreSQL 연결 문자열을 SQLAlchemy URL 객체로 변환

sql_logger = logging.getLogger("car_search_rag.sql")                                                                           # SQL 로그만 구분해서 설정할 수 있는 이름
SQL_LOG_DIVIDER = LOG_DIVIDER                                                                                                 # SQL 본문 위아래에 표시할 구분선 (기존 이름 유지)


#=========================================================
# DB 연결 위임, SQL 문 및 트랜잭션 관리 
#=========================================================
class PostgresDbSession(QuerySession):
    """SQL mapper를 등록하고 statement ID로 동기식 쿼리를 실행한다.

    생성 시 ``mapper_root`` 아래의 ``*.sql`` 파일을 재귀적으로
    찾아 aiosql의 psycopg 어댑터로 등록한다. 파일명이 namespace, SQL 파일의
    ``-- name:`` 값이 statement 이름이다. 조회와 실행은 ``DatabaseManager`` 가
    만든 연결을 사용하며, ``transaction()`` 안에서는 연결 하나를 재사용한다.

    Args:
        camel_case_keys: 조회 결과의 키를 camelCase로 변환할지 여부.
            기본값은 ``True`` 다.
        database_manager: 연결 관리자. 생략하면 ``DatabaseManager`` 를 만든다.
        sql_log_mode: SQL 상세 로그 형식. combined, separate, none 중 선택한다.
        result_log: 반환 데이터를 표로 기록할지 여부. 기본값은 ``False`` 다.
        result_log_limit: 상세 로그에 표시할 최대 행 수. 기본값은 ``100`` 이다.
        sensitive_log_keys: 로그에서 값을 ``<MASKED>`` 로 가릴 파라미터 키 목록.
            기본값 ``None`` 은 기존처럼 마스킹하지 않는다.
            예: ``sensitive_log_keys=QueryLogger.DEFAULT_SENSITIVE_KEYS``.

    Attributes:
        camel_case_keys: 기본값 ``True``. 조회 결과 dict의 snake_case 컬럼명을
            camelCase 키로 만든다. ``False`` 이면 원래 컬럼명을 유지한다.
        database_manager: 연결 생성에 사용할 관리자. 기본 생성되며 주입도 가능하다.
        sql_log_mode: 인스턴스별 SQL 상세 로그 형식. 기본값은 combined다.
        result_log: SQL 상세 로그 모드와 독립적인 결과 표 로그 설정.
        result_log_limit: 상세 로그의 최대 표시 행 수.
        mappers: SQL 파일명(namespace)별 aiosql ``Queries`` 객체.
        mapper_paths: namespace별 원본 SQL 파일 경로.
        mapper_root: mapper 파일 검색의 시작 경로(생성자 인자로 받은 인스턴스 속성).
        query_logger: SQL/결과/배치/트랜잭션 로그를 출력하는 공통 ``QueryLogger``.

    Example:
        .. code-block:: python

            session = PostgresDbSession(mapper_root=Path(__file__).resolve().parent)
            rows = session.select_list(
                "cff_caps.select_by_brand", {"brand": "NESPRESSO"}
            )

            original_keys = PostgresDbSession(mapper_root=Path(__file__).resolve().parent, camel_case_keys=False)
            rows = original_keys.select_list("cff_caps.count_by_brand")

    Note:
        생성할 때 mapper를 등록하지만 DB 연결은 쿼리 실행 시 만든다.
        ``_active_connection`` 으로 트랜잭션 상태를 인스턴스에 보관하므로
        한 인스턴스를 여러 thread가 동시에 트랜잭션에 사용하면 안 된다.
    """

    # region [Python 설명] ClassVar와 인스턴스 속성 선언
    # `ClassVar[...]`로 표시한 값은 모든 인스턴스가 공유하는 클래스 속성이다(Java의 static 필드와 비슷).
    # 그 아래 `camel_case_keys: bool`처럼 값 없이 타입만 적은 줄은 인스턴스 속성의 타입 선언이며,
    # 실제 값은 `__init__`에서 `self.camel_case_keys = ...`로 대입할 때 만들어진다.
    # endregion
    # 클래스 공통 속성
    # 로그 표시 기준은 QueryLogger와 같은 값을 기존 이름으로도 노출한다.
    SQL_LOG_MODES: ClassVar[tuple[str, ...]] = QueryLogger.LOG_MODES                                   # 허용하는 SQL 로그 모드
    RESULT_LOG_COLUMN_WIDTH: ClassVar[int] = QueryLogger.RESULT_LOG_COLUMN_WIDTH                       # 표의 컬럼별 최대 표시 폭
    VECTOR_LOG_PREVIEW_COUNT: ClassVar[int] = QueryLogger.VECTOR_LOG_PREVIEW_COUNT                     # 로그에 표시할 벡터 앞부분 값 개수
    VECTOR_LOG_SEQUENCE_MIN_LENGTH: ClassVar[int] = QueryLogger.VECTOR_LOG_SEQUENCE_MIN_LENGTH         # 숫자 시퀀스를 벡터로 취급할 최소 길이

    # 인스턴스 속성
    camel_case_keys: bool                           # 조회 결과 camelCase 변환 여부
    database_manager: DatabaseManager               # DB 연결 관리자
    query_logger: QueryLogger                       # SQL/결과 로그 설정과 출력 (result_log 등은 property로 위임)
    mappers: dict[str, Queries]                     # namespace별 SQL mapper
    mapper_paths: dict[str, Path]                   # namespace별 SQL 파일 경로
    _active_connection: psycopg.Connection | None   # 트랜잭션 중 재사용할 연결
    _pg_engine: "PGEngine | None"                   # PGVector 엔진 지연 생성 캐시

    #=========================================================
    # 생성자
    #=========================================================
    def __init__(
        self,
        camel_case_keys: bool = True,
        database_manager: DatabaseManager | None = None,
        sql_log_mode: str = "combined",
        result_log: bool = False,
        result_log_limit: int = 100,
        *,
        mapper_root: str | Path,
        sensitive_log_keys: Collection[str] | None = None,
    ) -> None:
        """연결 관리자와 SQL/결과 로그 옵션을 설정하고 mapper를 등록한다.

        ``result_log`` 는 ``sql_log_mode`` 와 독립적으로 동작한다.
        ``result_log_limit`` 는 0 이상이며, 0이면 행 상세를 출력하지 않는다.

        Raises:
            ValueError: 로그 설정 값이 잘못되었거나 mapper namespace/statement가 중복된 경우.
            FileNotFoundError: ``mapper_root`` 가 없거나 디렉터리가 아닌 경우.
        """
        # region [Python 설명] 기본값 인자, `*` 키워드 전용 인자, 조건 표현식
        # `camel_case_keys=True`처럼 기본값이 있는 인자는 호출 시 생략할 수 있다(Java overloading 대신 사용).
        # 인자 목록의 `*` 뒤에 있는 `mapper_root`, `sensitive_log_keys`는 반드시 이름을 붙여 전달해야 한다.
        #   PostgresDbSession(mapper_root=path)      → 가능
        #   PostgresDbSession(True, None, ..., path) → 불가(위치 인자로 전달할 수 없음)
        # `A if 조건 else B`는 Java의 삼항 연산자 `조건 ? A : B`와 같다.
        # `database_manager`를 주입받지 않았을 때만 새 DatabaseManager를 만든다.
        # endregion
        self.camel_case_keys = camel_case_keys                                                                                  # 조회 결과 컬럼명 변환 여부
        self.database_manager = database_manager if database_manager is not None else DatabaseManager()                         # DB 연결 관리자
        self.mapper_root = Path(mapper_root)
        self.mappers: dict[str, Queries] = {}                                                                                   # namespace별 SQL mapper
        self.mapper_paths: dict[str, Path] = {}                                                                                 # namespace별 SQL 파일 경로
        self._active_connection: psycopg.Connection | None = None                                                               # 트랜잭션 중 재사용할 연결
        self._pg_engine: "PGEngine | None" = None                                                                                 # PGVector 엔진 지연 생성 캐시
        # 로그 모드 → result_log_limit 순서로 검증하고 실패 시 ValueError를 낸다.
        self.query_logger = QueryLogger(
            sql_logger,
            log_mode=sql_log_mode,
            result_log=result_log,                       # SQL 상세 로그와 독립적으로 결과 데이터 출력
            result_log_limit=result_log_limit,           # 출력할 최대 행 수
            mode_option_name="sql_log_mode",
            query_label="SQL",
            vector_types=(Vector,),
            sensitive_keys=sensitive_log_keys,
        )
        self.register_mappers()                                                                                                # SQL mapper를 명시적으로 등록

    #=========================================================
    # SQL 로그 모드 조회
    #=========================================================
    # region [Python 설명] @property와 setter
    # `@property`를 붙인 메서드는 괄호 없이 속성처럼 읽는다: `session.sql_log_mode`
    # `@sql_log_mode.setter`는 대입 시 호출된다: `session.sql_log_mode = "none"`
    # Java의 getter/setter와 같은 역할이지만 호출 코드는 일반 필드 접근처럼 보인다.
    # 여기서는 실제 값을 QueryLogger에 보관하고, 세션은 기존 속성 이름을 유지하는 창구 역할만 한다.
    # endregion
    @property
    def sql_log_mode(self) -> str:
        """현재 SQL 상세 로그 모드(combined / separate / none)."""
        return self.query_logger.log_mode

    #=========================================================
    # SQL 로그 모드 설정 및 검증
    #=========================================================
    @sql_log_mode.setter
    def sql_log_mode(self, value: str) -> None:
        """SQL 로그 출력 방식을 QueryLogger에 위임한다."""
        self.query_logger.log_mode = value              # 허용하지 않는 값이면 ValueError

    #=========================================================
    # 결과 로그 옵션 (QueryLogger에 위임)
    #=========================================================
    @property
    def result_log(self) -> bool:
        """조회/실행 결과를 표 형태로 로그에 남길지 여부."""
        return self.query_logger.result_log

    @result_log.setter
    def result_log(self, value: bool) -> None:
        """조회 결과 로깅 설정을 QueryLogger에 위임한다."""
        self.query_logger.result_log = value

    @property
    def result_log_limit(self) -> int:
        """결과 표 로그에 표시할 최대 행 수. 0 이상의 정수만 허용한다."""
        return self.query_logger.result_log_limit

    @result_log_limit.setter
    def result_log_limit(self, value: int) -> None:
        """로그에 표시할 조회 결과 건수 제한을 QueryLogger에 위임한다."""
        self.query_logger.result_log_limit = value

    #=========================================================
    # SQL 상세 로그 출력 (PostgreSQL 전용 mogrify 렌더링)
    #=========================================================
    def _log_query(self, statement_id: str, sql: str, parameters, connection: psycopg.Connection, *, force: bool = False, full_vector_sql: bool = False) -> None:
        """실행과 별개로 SQL 상세 로그를 출력한다. 형식과 모드 판단은 QueryLogger가 맡는다.

        Args:
            statement_id: 로그에 표시할 ``namespace.statement`` ID.
            sql: aiosql이 변환한 SQL(``%(name)s`` 형식 placeholder).
            parameters: 실제 실행에 쓰는 원본 파라미터 dict.
            connection: ``mogrify()`` 렌더링에 사용할 현재 연결. 이 메서드는 SQL을 실행하지 않는다.
            force: True면 ``sql_log_mode="none"`` 이어도 combined 형식으로 출력한다(``execute()`` 기존 정책).
            full_vector_sql: True면 QUERY 본문에 벡터 전체를 렌더링한다(``select_list()`` 전용).
        """

        # region [Python 설명] 내부 함수를 callback으로 넘기기
        # `render_sql`은 이 메서드 안에서만 쓰는 함수이며 바깥의 `parameters`, `connection`,
        # `full_vector_sql`, `sql`을 그대로 참조한다(closure).
        # QueryLogger는 combined 모드이고 INFO 로그가 켜져 있을 때만 이 함수를 호출하므로,
        # 로그가 꺼져 있으면 mogrify 렌더링 비용이 들지 않는다.
        # endregion
        # region [DB 설명] ClientCursor.mogrify()
        # psycopg 기본 커서는 SQL과 파라미터를 서버에 따로 보내므로(server-side binding) 완성된 SQL 문자열이 없다.
        # `ClientCursor.mogrify(sql, params)`는 실행하지 않고 "값이 채워진 SQL 문자열"만 만들어 준다.
        # 로그 확인용이며, 실제 실행은 aiosql 함수가 원본 파라미터로 따로 수행한다.
        # endregion
        def render_sql(log_parameters) -> str:
            # select_list()만 full_vector_sql=True로 호출해 실제 embedding 전체를 QUERY에 남긴다.
            # 복사 가능한 SQL로 EXPLAIN 등을 확인하기 위함이며 PARAMS는 기존 sanitize 미리보기를 유지한다.
            # execute()/execute_many()는 이 옵션을 쓰지 않아 변경/배치 SQL 로그에 영향이 없다.
            # sensitive_log_keys를 지정한 경우에만 원본 대신 민감 키를 가린 복사본으로 렌더링한다.
            """바인딩 매개변수를 포함한 SQL을 로깅용 문자열로 표현한다."""
            render_parameters = self.query_logger.mask(parameters) if full_vector_sql else log_parameters
            with psycopg.ClientCursor(connection) as cursor:
                rendered = cursor.mogrify(sql, render_parameters or None)
            # 렌더링 값이 실행 값과 다른 경우(마스킹, 벡터 미리보기)는 그대로 재실행해도 같지 않다고 SQL 주석으로 밝힌다.
            notes = self._render_notes(parameters, full_vector_sql)
            return "\n".join([*notes, rendered]) if notes else rendered

        self.query_logger.log_query(statement_id, sql, parameters, render_combined=render_sql, force=force)

    def _render_notes(self, parameters, full_vector_sql: bool) -> list[str]:
        """mogrify 결과가 실제 실행 값과 달라지는 경우의 ``--`` 주석 줄 목록(로그 전용).

        - 민감 키가 ``<MASKED>`` 로 바뀐 경우
        - ``full_vector_sql=False`` (``execute()``)에서 벡터가 ``<VECTOR ...>`` 미리보기로 렌더링된 경우
        """
        values = parameters or {}
        notes = []
        if values and self.query_logger.mask(values) is not values:
            notes.append("-- NOT REPRODUCIBLE AS-IS: masked values ('<MASKED>') differ from the executed values")
        if not full_vector_sql and self._contains_vector(values):
            notes.append("-- NOT REPRODUCIBLE AS-IS: vector values are shown as previews, not the executed values")
        return notes

    def _contains_vector(self, value) -> bool:
        """로그에서 미리보기로 바뀌는 값(pgvector 타입, 긴 숫자 list/tuple)이 들어 있는지 재귀로 확인한다."""
        logger = self.query_logger
        if logger.vector_types and isinstance(value, logger.vector_types):
            return True
        if isinstance(value, dict):
            return any(self._contains_vector(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return is_numeric_sequence(value, logger.VECTOR_LOG_SEQUENCE_MIN_LENGTH) or any(
                self._contains_vector(item) for item in value)
        return False

    #=========================================================
    # 검색 범위의 SQL mapper 파일을 현재 세션에 등록한다.
    #=========================================================
    def register_mappers(self) -> Self:                                                                                       # mapper SQL 파일을 찾아 인스턴스 필드에 등록
        """검색 범위의 SQL mapper 파일을 현재 세션에 등록한다.

        ``mapper_root`` 아래의 ``*.sql`` 파일을 재귀적으로 검색한다.
        파일 stem을 namespace로 삼고 UTF-8 SQL을
        ``aiosql.from_path(..., "psycopg")`` 로 로드한다.
        ``PostgresDbSession.__init__()`` 에서 필드를 초기화한 뒤 명시적으로 호출한다.

        Returns:
            mapper 등록을 마친 현재 ``PostgresDbSession`` 인스턴스.

        Raises:
            ValueError: namespace가 중복되거나 SQLLoadException이 발생한 경우.
                오류 메시지에 관련 SQL 파일 경로를 포함한다.

        Example:
            .. code-block:: python

                session = PostgresDbSession(mapper_root=Path(__file__).resolve().parent)
                mapper = session.mappers["cff_caps"]

        Note:
            기존 mapper를 지우지 않으므로 같은 세션에서 다시 호출하면 등록된
            namespace와 충돌할 수 있다.
        """
        if not self.mapper_root.exists() or not self.mapper_root.is_dir():
            raise FileNotFoundError(f"SQL mapper root does not exist or is not a directory: {self.mapper_root}")
        # named query 선언이 있는 파일만 mapper로 등록하고, 수동 실행용 SQL 스크립트는 건너뛴다.
        # region [Python 설명] rglob()와 generator expression, sorted()
        # `Path.rglob("*.sql")`은 하위 디렉터리까지 재귀적으로 `.sql` 파일을 찾는 iterator다.
        # `sorted(path for path in ... if 조건)`은 조건을 만족하는 경로만 골라 정렬된 list로 만든다.
        # 정렬하면 OS마다 다를 수 있는 탐색 순서와 무관하게 등록 순서와 중복 오류 메시지가 일정해진다.
        # `encoding="utf-8-sig"`는 파일 앞의 UTF-8 BOM이 있으면 제거하고 읽는다.
        # endregion
        # region [DB 설명] aiosql named query
        # aiosql은 SQL 파일에서 `-- name: 이름` 줄로 구분된 쿼리를 읽어 Python 함수로 만든다(MyBatis mapper와 비슷).
        # 이름 끝의 `!`는 변경 SQL, `^`는 단일 행 조회 등 실행 방식을 뜻하고, 없으면 여러 행 조회다.
        # SQL의 `:CAR_ID` 같은 named parameter는 psycopg 형식 `%(CAR_ID)s`로 바뀌어
        # 실행 시 DB 드라이버가 값을 바인딩한다(문자열 연결이 아니므로 SQL injection에 안전).
        # 쿼리 사이의 `--` 주석 줄은 실행 SQL에 포함되지 않고 쿼리 설명(doc)으로 분리된다.
        # endregion
        mapper_files = sorted(
            path for path in self.mapper_root.rglob("*.sql")
            if "-- name:" in path.read_text(encoding="utf-8-sig")
        )                                                                # mapper_root 아래 모든 하위 폴더의 SQL mapper 파일 조회
        for path in mapper_files:                                                                                             # 찾은 SQL 파일을 하나씩 등록
            namespace = path.stem                                                                                             # document.sql → document
            if namespace in self.mappers:                                                                                     # 서로 다른 파일의 이름이 같으면 충돌
                raise ValueError(                                                                                             # 충돌한 두 파일 경로를 함께 알림
                    f"Duplicate SQL mapper namespace '{namespace}': "
                    f"'{self.mapper_paths[namespace]}' and '{path}'"
                )
            try:                                                                                                              # SQL 파일 안의 -- name: 정의를 aiosql 함수로 변환
                self.mappers[namespace] = aiosql.from_path(                                                                   # namespace로 등록
                    path, "psycopg", mandatory_parameters=False, encoding="utf-8"
                )
            except SQLLoadException as exc:                                                                                   # 같은 파일 안의 statement 이름 중복 등
                raise ValueError(f"Duplicate or conflicting SQL statement in '{path}': {exc}") from exc                       # 파일 정보 추가
            self.mapper_paths[namespace] = path                                                                               # 오류 메시지에서 사용할 원본 경로 저장
        return self                                                                                                           # 등록을 마친 세션 반환

    #=========================================================
    # statement ID로 실행할 SQL 함수 찾기
    #=========================================================
    def _query(self, statement_id: str):                                                                                      # namespace.statement 이름을 실행 함수로 변환
        """``namespace.statement`` ID에 해당하는 aiosql 함수를 찾는다.

        Args:
            statement_id: 예: ``"document.select_documents"``.

        Returns:
            등록된 aiosql 쿼리 함수.

        Raises:
            ValueError: ID 형식이 잘못된 경우.
            LookupError: namespace 또는 statement가 없는 경우.
        """
        # 'document.select_documents' 문자열을 namespace('document'), separator('.'), query_id('select_documents')로 분할
        # region [Python 설명] str.partition()과 tuple unpacking
        # `partition(".")`은 첫 번째 "."을 기준으로 `(앞, ".", 뒤)` 세 값의 tuple을 반환한다.
        # "."이 없으면 `(전체 문자열, "", "")`이므로 separator가 빈 문자열인지로 형식 오류를 판단한다.
        # 왼쪽의 변수 세 개가 tuple의 세 값을 순서대로 받는다(tuple unpacking).
        # endregion
        namespace, separator, query_id = statement_id.partition(".")                                                          # 첫 번째 점을 기준으로 분리
        
        # 구분자가 없거나, 네임스페이스/쿼리ID가 비어있거나, 쿼리ID 내에 점(.)이 더 포함된 경우 검증 오류 처리
        if not separator or not namespace or not query_id or "." in query_id:                                                 # 정확히 두 부분인지 확인
            raise ValueError("statement_id must be 'namespace.query_id'")                                                     # 잘못된 호출 형식 알림
        
        mapper = self.mappers.get(namespace)                                                                                  # 파일명에 해당하는 mapper 찾기
        if mapper is None:                                                                                                    # 해당 이름의 SQL 파일이 없는 경우
            raise LookupError(f"SQL mapper namespace '{namespace}' not found for '{statement_id}'")                           # 누락 파일명 알림
        if query_id not in mapper.available_queries:                                                                          # SQL 파일에 -- name: 정의가 없는 경우
            raise LookupError(                                                                                                # 어떤 파일에서 어떤 statement를 못 찾았는지 알림
                f"SQL statement '{query_id}' not found in mapper '{namespace}' "
                f"({self.mapper_paths[namespace]})"
            )
        # region [Python 설명] getattr()로 이름이 문자열인 속성 꺼내기
        # `getattr(mapper, "select_documents")`는 `mapper.select_documents`와 같다.
        # 쿼리 이름이 실행 시점의 문자열이므로 Java의 reflection처럼 이름으로 속성을 조회한다.
        # endregion
        return getattr(mapper, query_id)                                                                                      # aiosql이 만든 실행 함수를 반환

    #=========================================================
    # 트랜잭션 중이면 기존 연결, 아니면 새 연결 제공
    #=========================================================
    # _connection()은 SQL 실행부의 단일 진입점이다.
    # 트랜잭션 중이면 이미 빌린 연결을 내주고, 그 외에는 DatabaseManager.connect()를 통해 pool에서 대여한다.
    # 후자의 with 블록 종료는 physical connection close가 아니라 pool 반환이다.
    # region [Python 설명] @contextmanager와 yield
    # `@contextmanager`를 붙인 generator 함수는 `with self._connection() as connection:` 형태로 사용한다.
    # with 블록에 들어갈 때 `yield` 직전까지 실행되고, `yield`한 값이 `as` 뒤 변수에 들어간다.
    # with 블록이 끝나면 `yield` 다음 코드(여기서는 안쪽 with 블록의 종료 처리)가 실행된다.
    # 반환 타입 `Generator[psycopg.Connection]`은 "Connection을 yield하는 generator"라는 뜻이다.
    # endregion
    @contextmanager                                                                                                           # with 블록 안의 연결 사용 방식을 공통 처리
    def _connection(self) -> Generator[psycopg.Connection]:                                                                   # 트랜잭션 연결 또는 독립 연결 제공
        """트랜잭션 중이면 그 연결을, 아니면 pool에서 새로 빌린 연결을 with 블록에 제공한다."""
        if self._active_connection is not None:                                                                              # 활성 트랜잭션이면 그 연결을 그대로 공유
            yield self._active_connection                                                                                     # 같은 연결을 재사용하고 여기서 닫지 않음
        else:                                                                                                                 # 트랜잭션 밖에서는
            with self.database_manager.connect(camel_case_keys=self.camel_case_keys) as connection:  # pool 대여 후 블록 종료 시 반환
                yield connection                                                                                              # 사용 후 연결 컨텍스트가 정리

    # 사용법: 여러 mapper 쿼리를 같은 작업으로 묶는다(아래 transaction_demo는 예시 이름이다).
    # sql_session = PostgresDbSession(mapper_root=Path(__file__).resolve().parent)
    # with sql_session.transaction():
    #     sql_session.execute("transaction_demo.create_temp_table")
    #     sql_session.execute("transaction_demo.insert_item", {"item_id": 1, "item_name": "첫 항목"})
    #     rows = sql_session.select_list("transaction_demo.select_items")
    # with 블록을 정상적으로 나오면 COMMIT, 예외가 밖으로 나가면 ROLLBACK한다.
    # 오류를 처리할 때는 try/except를 with 바깥에 둔다. 블록 안에서 오류를 삼키면 COMMIT된다.
    # SQL 이름은 'mapper 파일명.쿼리 이름'이며, _connection()은 내부에서 자동 호출된다.
    # 전체 실행 예제: src/car_search_rag/docs/examples/transaction_sample.py
    # (현재 저장소에는 이 예제가 import하는 transaction_sample_service 모듈과 transaction_demo SQL mapper가 없다.)
    # region [Python 설명] try / except / else / finally
    # `try` 블록에서 예외가 나면 `except`가, 예외가 없으면 `else`가 실행된다.
    # `finally`는 두 경우 모두 마지막에 항상 실행되어 `_active_connection`을 초기화한다.
    # `except BaseException`은 Exception뿐 아니라 KeyboardInterrupt 등까지 잡아 rollback한 뒤
    # 맨 끝의 `raise`로 같은 예외를 그대로 다시 던진다(예외를 삼키지 않음).
    # contextmanager에서 with 블록 안의 예외는 `yield self` 위치에서 발생한 것처럼 전달된다.
    # endregion
    @contextmanager                                                                                                           # with sql_session.transaction() 형태 지원
    def transaction(self) -> Generator[Self]:                                                                                 # 여러 SQL을 하나의 연결과 작업 단위로 실행
        """여러 mapper 호출을 하나의 PostgreSQL 트랜잭션으로 묶는다.

        블록 진입 때 pool에서 연결 하나를 대여하고 블록 안의 ``select_list()``,
        ``select_one()``, ``execute()``가 같은 연결을 공유한다. 정상 종료는 commit,
        예외는 rollback하며, 마지막에는 physical connection을 닫지 않고 pool에 반환한다.

        Yields:
            현재 ``PostgresDbSession`` 인스턴스.

        Raises:
            RuntimeError: 같은 세션에서 이미 트랜잭션이 활성화된 경우.
            BaseException: 블록에서 발생한 예외를 rollback 후 다시 전파한다.

        Example:
            .. code-block:: python

                session = PostgresDbSession(mapper_root=Path(__file__).resolve().parent)
                with session.transaction():
                    session.execute("transaction_demo.create_temp_table")
                    session.execute(
                        "transaction_demo.insert_item",
                        {"item_id": 1, "item_name": "첫 항목"},
                    )

        Note:
            중첩 트랜잭션과 SAVEPOINT는 제공하지 않는다. 블록 내부에서 예외를
            처리하고 정상 종료하면 commit된다. ``camel_case_keys`` 옵션은 이
            트랜잭션 연결의 row factory에도 적용된다.
        """
        if self._active_connection is not None:                                                                               # 중첩 트랜잭션은 지원하지 않음
            raise RuntimeError("이미 Transaction이 실행 중입니다.")                                                               # 중첩 사용을 명확히 알림
        # transaction 전체가 하나의 pool lease 안에 있어 중간에 connection이 바뀌지 않는다.
        # 이 context 종료가 pool 반환을 담당하므로 여기서 connection.close()를 직접 호출하지 않는다.
        with self.database_manager.connect(camel_case_keys=self.camel_case_keys) as connection:
            self._active_connection = connection
            # psycopg는 BEGIN을 첫 SQL 실행 때 암묵적으로 보내므로, 이 로그는 트랜잭션 연결을 확보한 시점이다.
            self.query_logger.log_transaction("BEGIN")
            try:
                try:
                    yield self
                except BaseException:
                    # 실패한 작업은 되돌리고 예외는 호출자에게 전파한 뒤 pool context가 연결을 반환한다.
                    try:
                        connection.rollback()
                    except BaseException:
                        # 기존 동작대로 rollback 예외가 전파된다(원래 예외는 __context__로 연결됨). 로그만 추가한다.
                        self.query_logger.log_rollback_failure()
                        raise
                    self.query_logger.log_transaction("ROLLBACK")
                    raise
                else:
                    # 모든 SQL이 성공한 경우에만 확정하고, 다음으로 바깥 pool context가 연결을 반환한다.
                    try:
                        connection.commit()
                    except BaseException as exc:
                        # commit 실패를 COMMIT으로 기록하지 않는다. 예외 전파는 기존과 같다.
                        self.query_logger.log_transaction_failure("COMMIT", exc)
                        raise
                    self.query_logger.log_transaction("COMMIT")
            finally:
                self._active_connection = None

    #=========================================================
    # SELECT 결과를 리스트로 반환
    #=========================================================
    def select_list(self, statement_id: str, parameters=None) -> list[dict]:                                                   
        """mapper SELECT를 실행하고 모든 결과 행을 dict 목록으로 반환한다.

        트랜잭션 밖에서는 DatabaseManager pool에서 연결을 빌려 전체 fetch 후 반환한다.
        트랜잭션 안에서는 이미 대여한 연결을 재사용한다. 성능 로그는 연결 대여,
        SQL 로그 렌더링, 실제 실행 및 fetch, 전체 시간을 구분한다.

        full_vector_sql=True는 이 SELECT 로그에만 적용되어 QUERY 본문에 원본
        embedding 전체를 렌더링하고, PARAMS에는 기존 축약 미리보기를 남긴다.
        변경 SQL과 배치 SQL의 로그 방식은 그대로 유지한다.
        """
        query = self._query(statement_id)                                                                                     # 실행할 쿼리 매핑 함수 조회
        started = perf_counter()  # select_list 진입부터 결과 로깅까지의 기존 전체 시간
        with self._connection() as connection:  # transaction 연결 또는 pool 대여 연결
            connected = perf_counter()
            # pool warm-up 이후에는 대개 준비된 연결을 빌리는 시간이며, SQL 로그/조회는 아직 포함하지 않는다.
            connect_ms = (connected - started) * 1000
            sql_log_started = connected
            # 조회 본문에만 원본 embedding을 렌더링해 전체 벡터를 남긴다.
            # PARAMS는 기존 sanitize 미리보기이며, 변경/배치 SQL의 로깅 동작에는 적용하지 않는다.
            self._log_query(statement_id, query.sql, parameters, connection, full_vector_sql=True)                                # 조회 QUERY는 원본 바인딩으로 렌더링
            # SQL과 파라미터의 로그용 렌더링(mogrify 포함) 시간만 측정한다.
            sql_log_ms = (perf_counter() - sql_log_started) * 1000
            # 커넥션이 열려 있는 상태에서 지연 조회(Iterator) 결과를 list로 완전히 평가(eval)하여 객체로 확정
            query_fetch_started = perf_counter()
            # 서버 실행, 왕복/전송, psycopg decode, aiosql 처리와 모든 결과 fetch를 포함한다.
            # region [Python 설명] `**dict` 인자 전개와 list(iterator)
            # `query(connection, **{"CAR_ID": 1})`은 `query(connection, CAR_ID=1)`과 같다.
            # dict의 key/value가 이름 있는 인자로 펼쳐져 aiosql의 SQL 파라미터에 전달된다.
            # `parameters or {}`는 parameters가 None일 때 빈 dict를 사용한다.
            # aiosql 조회 함수는 결과를 한 행씩 읽는 iterator를 반환할 수 있으므로,
            # 연결이 pool로 반환되기 전에 `list(...)`로 모든 행을 읽어 둔다.
            # endregion
            rows = list(query(connection, **(parameters or {})))                                                            # 연결이 닫히기 전에 결과를 모두 읽음
            query_fetch_ms = (perf_counter() - query_fetch_started) * 1000
        self.query_logger.log_result_data(statement_id, rows)  # 설정된 경우 조회 결과를 표로 출력
        # result_log 출력도 포함해 select_list의 기존 elapsed_ms 의미를 유지한다.
        total_ms = (perf_counter() - started) * 1000
        self.query_logger.log_summary(
            "RESULT", statement_id, rows=len(rows), connect_ms=connect_ms, sql_log_ms=sql_log_ms,
            query_fetch_ms=query_fetch_ms, total_ms=total_ms,
        )
        return rows                                                                                                          # 조회 결과 반환

    
    #=========================================================
    # SELECT 결과의 첫 행 반환 1건 조회용
    #=========================================================
    def select_one(self, statement_id: str, parameters=None) -> dict | None:                                                  
        """mapper 조회 결과의 첫 행 또는 ``None`` 을 반환한다.

        ``select_list()`` 를 호출하므로 쿼리의 모든 행을 읽은 뒤 첫 행을 고른다.

        Args:
            statement_id: ``namespace.statement`` 형식의 mapper ID.
            parameters: SQL에 전달할 이름 있는 파라미터의 매핑. ``None`` 이면
                빈 매핑을 전달한다.

        Returns:
            첫 행의 dict 또는 조회 결과가 없을 때 ``None``. dict 키는
            ``camel_case_keys`` 설정을 따른다.

        Raises:
            ValueError: statement ID 형식이 잘못된 경우.
            LookupError: namespace 또는 statement가 없는 경우.
            Exception: 연결 또는 SQL 실행 중 발생한 예외를 전파한다.

        Example:
            .. code-block:: python

                row = session.select_one(
                    "cff_caps.select_by_brand", {"brand": "NESPRESSO"}
                )

        Note:
            데이터베이스에 ``LIMIT 1`` 을 자동 추가하지 않는다.
        """
        rows = self.select_list(statement_id, parameters)                                                                     # select_list를 재활용하여 전체 결과 수집
        return rows[0] if rows else None                                                                                      # 결과 리스트에 행이 존재하면 첫번째 행 반환, 없으면 None 반환


    #=========================================================
    # INSERT, UPDATE, DELETE 등 변경 SQL 실행
    #=========================================================
    def execute(self, statement_id: str, parameters=None):                                                                    
        """mapper의 변경 SQL 또는 기타 SQL 명령을 실행한다.

        aiosql이 지연 ``Iterator`` 를 반환하면 연결이 열려 있을 때 목록으로
        모두 읽는다. 그 밖의 결과는 aiosql의 반환값을 그대로 돌려준다.

        ``result_log=True`` 이면 반환 dict/list는 최대 ``result_log_limit`` 행까지 표로 출력한다.

        Args:
            statement_id: ``namespace.statement`` 형식의 mapper ID.
                변경 명령은 SQL 파일에서 ``-- name: insert_item!`` 처럼 정의한다.
            parameters: SQL에 전달할 이름 있는 파라미터의 매핑. ``None`` 이면
                빈 매핑을 전달한다.

        Returns:
            지연 ``Iterator`` 이면 list, 그 외에는 aiosql이 반환한 값.

        Raises:
            ValueError: statement ID 형식이 잘못된 경우.
            LookupError: namespace 또는 statement가 없는 경우.
            Exception: 연결 또는 SQL 실행 중 발생한 예외를 전파한다.

        Example:
            .. code-block:: python

                with session.transaction():
                    session.execute("transaction_demo.create_temp_table")
                    session.execute(
                        "transaction_demo.insert_item",
                        {"item_id": 1, "item_name": "첫 항목"},
                    )

        Note:
            트랜잭션 밖에서는 호출마다 별도 연결을 사용한다. 결과 dict가
            반환되는 SQL이라면 키는 연결의 ``camel_case_keys`` 설정을 따른다.
        """
        query = self._query(statement_id)                                                                                     # 실행할 쿼리 매핑 함수 조회
        started = perf_counter()                                                                                              # DB 연결과 명령 실행 시간 측정 시작
        with self._connection() as connection:                                                                                # 트랜잭션 안에서는 같은 연결 재사용
            self._log_query(statement_id, query.sql, parameters, connection, force=True)                                          # none 모드에서도 변경 SQL 로그를 표시하고 바인딩 실행은 유지
            result = query(connection, **(parameters or {}))                                                                  # SQL 명령 실행
            
            # RETURNING 구문 등으로 인해 결과가 Iterator(지연 결과)로 반환된 경우,
            # 커넥션이 닫히기 전에 list로 소진(consume)하여 반환하고, 일반 반환값은 그대로 반환
            # region [Python 설명] isinstance()와 Iterator
            # `isinstance(result, Iterator)`는 result가 "next()로 하나씩 꺼내는 객체"인지 확인한다.
            # aiosql 변경 SQL(`!`)은 보통 rowcount 같은 값을 바로 반환하고,
            # 결과 행을 돌려주는 SQL은 iterator를 반환할 수 있어 두 경우를 나누어 처리한다.
            # endregion
            result = list(result) if isinstance(result, Iterator) else result                                                # 지연 결과만 리스트로 변환
        self.query_logger.log_result_data(statement_id, result)  # 반환 데이터가 있으면 타입에 맞게 출력
        self.query_logger.log_summary("DONE", statement_id, elapsed_ms=(perf_counter() - started) * 1000)                    # 완료 시간 기록
        return result                                                                                                         # SQL 실행 결과 반환


    #=========================================================
    # INSERT, UPDATE, DELETE Batch 실행
    #=========================================================
    def execute_many(self, statement_id: str, parameters_list: list[dict]):
        """같은 변경 SQL을 여러 파라미터에 적용해 배치 실행한다.

        ``execute()`` 는 파라미터 한 건으로 SQL을 한 번 실행하고,
        ``execute_many()`` 는 INSERT·UPDATE·DELETE 등에 같은 SQL을 여러 건 적용한다.
        빈 목록이면 연결을 열지 않고 0을 반환한다. 그 외에는
        ``cursor.executemany(query.sql, parameters_list)`` 로 실행한다.

        Args:
            statement_id: ``namespace.statement`` 형식의 mapper ID.
                예: ``"coffee_search.insert_machine_detail"``.
            parameters_list: SQL의 이름 있는 파라미터에 대응하는 dict 목록.
                각 dict가 한 번의 SQL 실행에 사용할 값이다.

        Returns:
            빈 목록이면 0, 그 외에는 ``cursor.rowcount`` 값.
            psycopg 3의 ``executemany()`` 는 모든 실행에서 영향받은 행 수를 합산해 ``rowcount`` 에 둔다.

        Raises:
            ValueError: statement ID 형식이 잘못된 경우.
            LookupError: namespace 또는 statement가 없는 경우.
            Exception: 연결 또는 배치 SQL 실행 중 발생한 예외를 전파한다.

        Example:
            .. code-block:: python

                parameters_list = [
                    {
                        "CFF_MACH_ID": machine_id,
                        "PAGE_NO": "1",
                        "TEXT": "첫 번째 내용",
                        "EMBEDDING": Vector(embeddings[0]),
                        "USER_ID": user_id,
                    },
                    {
                        "CFF_MACH_ID": machine_id,
                        "PAGE_NO": "2",
                        "TEXT": "두 번째 내용",
                        "EMBEDDING": Vector(embeddings[1]),
                        "USER_ID": user_id,
                    },
                ]

                with session.transaction():
                    session.execute_many(
                        "coffee_search.insert_machine_detail",
                        parameters_list,
                    )

        Note:
            ``transaction()`` 안에서는 기존 연결을 재사용하고 정상 종료 시 COMMIT,
            예외가 전파되면 ROLLBACK한다. 블록 밖에서는 일반 연결 처리 방식을 따른다.
            INFO 로그가 활성화되면 실행 전에 ``BATCH QUERY`` 와 앞의 최대 100건
            ``BATCH PARAMS`` 를, 실행 후 ``BATCH DONE`` 건수·시간을 기록한다.
            Vector 값은 로그에서만 앞부분으로 축약하며 DB에는 원본
            ``parameters_list`` 를 그대로 전달한다.
        """

        # 실행할 SQL mapper 조회
        query = self._query(statement_id)

        # Batch 데이터가 없으면 실행하지 않음
        if not parameters_list:
            return 0

        started = perf_counter()

        # Transaction 안이면 기존 Connection 재사용
        with self._connection() as connection:

            # 실제 Batch 실행
            # region [DB 설명] cursor.executemany()와 aiosql query.sql
            # aiosql 함수를 반복 호출하지 않고, aiosql이 변환해 둔 SQL 문자열(`query.sql`)을
            # psycopg 커서의 `executemany()`에 직접 넘겨 같은 SQL을 파라미터 목록만큼 실행한다.
            # 각 dict의 key가 SQL의 `%(KEY)s` placeholder에 바인딩된다.
            # psycopg는 가능하면 pipeline 모드로 여러 실행을 묶어 보내 왕복 횟수를 줄인다.
            # endregion
            with connection.cursor() as cursor:

                # 원본과 분리한 표시용 파라미터 최대 100건 로그. 기존처럼 sql_log_mode=none이어도 출력한다.
                self.query_logger.log_batch_query(statement_id, query.sql, parameters_list, force=True)

                cursor.executemany(
                    query.sql,
                    parameters_list
                )

                row_count = cursor.rowcount

        self.query_logger.log_summary(
            "BATCH DONE", statement_id,
            rows=len(parameters_list),
            elapsed_ms=(perf_counter() - started) * 1000,
        )

        return row_count
    
    
    #=========================================================
    # PGVector용 DB 엔진 생성 및 반환
    #=========================================================
    def get_pg_engine(self) -> "PGEngine":
        """``DB_URL`` 로 PGVector용 ``PGEngine`` 을 지연 생성하고 재사용한다.

        URL의 드라이버를 ``postgresql+asyncpg`` 로 바꿔 엔진을 만든다. 생성한
        엔진은 세션의 ``_pg_engine`` 에 보관해 다음 호출부터 같은 객체를 돌려준다.

        Returns:
            현재 세션에서 재사용하는 ``langchain_postgres.PGEngine``.

        Raises:
            ValueError: ``DB_URL`` 환경변수가 비어 있는 경우.
            ModuleNotFoundError: ``langchain-postgres`` 가 설치되지 않은 경우.

        Example:
            .. code-block:: python

                session = PostgresDbSession(mapper_root=Path(__file__).resolve().parent)
                engine = session.get_pg_engine()

        Note:
            이 엔진은 psycopg ``DatabaseManager`` 연결과 별개로 만든다.
            ``camel_case_keys`` row factory 설정은 이 엔진에 적용되지 않는다.
        """
        # 처음 호출될 때만 엔진을 만들고(지연 생성), 이후에는 보관한 객체를 돌려준다.
        if self._pg_engine is None:
            # langchain-postgres는 PGVector를 쓰는 이 메서드에서만 필요하므로 여기서 import한다.
            # (graph-rag 의존성 pgvector>=0.5와 langchain-postgres의 pgvector<0.4 요구가 충돌해 기본 설치에서 빠질 수 있다.)
            try:
                from langchain_postgres import PGEngine
            except ModuleNotFoundError as error:
                raise ModuleNotFoundError(
                    "get_pg_engine() requires langchain-postgres (and asyncpg); install them in an environment "
                    "whose pgvector version they support"
                ) from error
            db_url = os.getenv("DB_URL")
            if not db_url:
                raise ValueError("DB_URL is required to create a PGEngine")
            # region [DB 설명] SQLAlchemy URL의 driver 교체
            # SQLAlchemy URL은 `postgresql+드라이버://user:pw@host/db` 형식이다.
            # `make_url(...).set(drivername="postgresql+asyncpg")`는 접속 정보는 그대로 두고
            # 드라이버 부분만 비동기 드라이버(asyncpg)로 바꾼 새 URL 객체를 만든다.
            # PGEngine(langchain_postgres)은 비동기 SQLAlchemy 엔진을 사용하므로 async 드라이버가 필요하다.
            # endregion
            async_url = make_url(db_url).set(drivername="postgresql+asyncpg")
            self._pg_engine = PGEngine.from_connection_string(async_url)
        return self._pg_engine
