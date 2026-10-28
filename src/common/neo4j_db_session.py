"""외부에서 주입한 Neo4j 공식 드라이버로 Cypher를 실행하는 ``QuerySession`` 구현 모듈.

이 모듈은 import 시점에 ``neo4j`` 패키지를 필요로 하지 않는다(로그 표시용 타입만 필요할 때 지연 import).
드라이버는 애플리케이션 조립 코드에서 ``neo4j.GraphDatabase.driver(...)`` 로 만들어 주입하며,
이 클래스는 환경변수의 접속 정보를 읽거나 서버 연결을 직접 열지 않는다.

호출 흐름(조회):
    Repository → ``select_list("graph.find_x", {...})`` → ``_query()`` 로 Cypher 조회
    → ``driver.session()`` 또는 활성 트랜잭션에서 ``run(query, parameters)``
    → 레코드를 dict list로 변환 → 로그 출력 후 반환
"""

from collections.abc import Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
import datetime as _dt
from functools import lru_cache
import logging
import math
from pathlib import Path
import re
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from .query_logger import DEFAULT_SENSITIVE_KEYS, QueryLogger, is_numeric_sequence
from .query_session import QuerySession


logger = logging.getLogger("car_search_rag.neo4j")
# region [Python 설명] 모듈 수준 정규식 상수
# `_STATEMENT_HEADER`는 `.cypher` 파일에서 "// name: 이름" 형식의 선언 줄을 찾는다.
# `re.MULTILINE`이면 `^`/`$`가 파일 전체가 아니라 각 줄의 시작/끝에 일치한다.
# `([A-Za-z_][A-Za-z0-9_]*)` 괄호 부분이 group(1)로 잡히는 statement 이름이다.
# 이름 앞의 `_`는 "모듈 내부용"이라는 Python 관례다.
# endregion
_STATEMENT_HEADER = re.compile(r"^\s*//\s*name:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", re.MULTILINE)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# neo4j.SummaryCounters가 제공하는 counter 속성 이름(드라이버 5.x/6.x 기준).
SUMMARY_COUNTER_NAMES: tuple[str, ...] = (
    "nodes_created", "nodes_deleted", "relationships_created", "relationships_deleted",
    "properties_set", "labels_added", "labels_removed", "indexes_added", "indexes_removed",
    "constraints_added", "constraints_removed", "system_updates",
)


#=========================================================
# 로그 전용 도우미 (실행할 Cypher를 만드는 데는 사용하지 않음)
#=========================================================
# region [Python 설명] @lru_cache와 지연 import
# `@lru_cache(maxsize=1)`은 함수 결과를 기억해 두는 decorator다. 인자가 없는 이 함수는
# 처음 한 번만 본문을 실행하고, 이후 호출에는 저장된 결과를 바로 돌려준다.
# 본문의 `from neo4j... import`는 이 함수가 처음 호출될 때 실행되므로,
# neo4j 패키지가 없는 환경에서도 이 모듈 자체는 import할 수 있다.
# 패키지가 없으면 빈 tuple `()`을 넣어 두는데, `isinstance(x, ())`는 항상 False라서
# 아래 isinstance 검사들이 예외 없이 "해당 타입 아님"으로 처리된다.
# `SimpleNamespace(Node=...)`는 `types.Node`처럼 속성으로 꺼내 쓰는 간단한 객체다.
# endregion
@lru_cache(maxsize=1)
def _driver_types() -> SimpleNamespace:
    """로그 표시에 필요한 드라이버 값 타입을 지연 import해 반환한다. neo4j가 없으면 빈 tuple로 채운다."""
    try:
        from neo4j.graph import Node, Path as GraphPath, Relationship
        from neo4j.spatial import Point
        from neo4j.time import Date, DateTime, Duration, Time
    except ImportError:
        return SimpleNamespace(Node=(), GraphPath=(), Relationship=(), Point=(),
                               Date=(), DateTime=(), Duration=(), Time=())
    return SimpleNamespace(Node=Node, GraphPath=GraphPath, Relationship=Relationship, Point=Point,
                           Date=Date, DateTime=DateTime, Duration=Duration, Time=Time)


class _NotCypherLiteral(Exception):
    """파라미터 값을 정확한 Cypher 리터럴로 표현할 수 없을 때 내부적으로 사용하는 예외."""


def _cypher_name(key: Any) -> str:
    """식별자 규칙에 맞지 않는 이름을 백틱으로 감싼다. 예: ``a b`` → ```a b```."""
    text = str(key)
    return text if _IDENTIFIER.fullmatch(text) else "`" + text.replace("`", "``") + "`"


def _cypher_string(text: str) -> str:
    """Python 문자열을 작은따옴표 Cypher 문자열 리터럴로 이스케이프한다(로그 표시용)."""
    # region [Python 설명] 문자열 안의 역슬래시
    # Python 소스의 `"\\\\"`는 실제 역슬래시 두 개, `"\\'"`는 역슬래시+작은따옴표를 뜻한다.
    # 즉 원래 문자 하나를 Cypher가 읽을 수 있는 이스케이프 표기로 바꿔 list에 모은다.
    # `f"\\u{ord(char):04x}"`는 제어 문자를 `\u0001` 같은 4자리 16진수 표기로 만든다.
    # endregion
    escaped = []
    for char in text:
        if char == "\\":
            escaped.append("\\\\")
        elif char == "'":
            escaped.append("\\'")
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif ord(char) < 0x20:
            escaped.append(f"\\u{ord(char):04x}")
        else:
            escaped.append(char)
    return "'" + "".join(escaped) + "'"


def _cypher_literal(value: Any, vector_min_length: int) -> str:
    """드라이버 파라미터 값을 ``:param`` 줄에 쓸 Cypher 표현식 문자열로 바꾼다.

    Cypher 표현이 명확한 타입(null, bool, 숫자, 문자열, 날짜·시간, Point, list, map)만 변환한다.
    그 밖의 값(벡터로 보이는 긴 숫자 list, bytes, 알 수 없는 객체)은 ``_NotCypherLiteral`` 을 발생시켜
    호출자가 해당 줄을 "재현 불가"로 표시하게 한다.
    """
    # isinstance 검사 순서가 중요하다: bool은 int의 하위 타입이고, datetime은 date의 하위 타입이므로
    # 더 구체적인 타입을 먼저 검사한다. list/map은 원소마다 이 함수를 재귀 호출한다.
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "0.0 / 0.0"
        if math.isinf(value):
            return "1.0 / 0.0" if value > 0 else "-1.0 / 0.0"
        return repr(value).replace("e+", "e")
    if isinstance(value, str):
        return _cypher_string(value)
    types = _driver_types()
    if isinstance(value, types.Point):
        if value.srid is None:
            raise _NotCypherLiteral("point without srid")
        axes = ("x", "y", "z")
        fields = [f"srid: {value.srid}", *(f"{axis}: {_cypher_literal(float(coord), vector_min_length)}"
                                         for axis, coord in zip(axes, value))]
        return "point({" + ", ".join(fields) + "})"
    if isinstance(value, types.Duration):
        return f"duration({_cypher_string(value.iso_format())})"
    if isinstance(value, types.DateTime):
        function = "localdatetime" if value.tzinfo is None else "datetime"
        return f"{function}({_cypher_string(value.iso_format())})"
    if isinstance(value, types.Date):
        return f"date({_cypher_string(value.iso_format())})"
    if isinstance(value, types.Time):
        function = "localtime" if value.tzinfo is None else "time"
        return f"{function}({_cypher_string(value.iso_format())})"
    if isinstance(value, _dt.datetime):
        function = "localdatetime" if value.tzinfo is None else "datetime"
        return f"{function}({_cypher_string(value.isoformat())})"
    if isinstance(value, _dt.date):
        return f"date({_cypher_string(value.isoformat())})"
    if isinstance(value, _dt.time):
        function = "localtime" if value.tzinfo is None else "time"
        return f"{function}({_cypher_string(value.isoformat())})"
    if isinstance(value, _dt.timedelta):
        return (f"duration({{days: {value.days}, seconds: {value.seconds}, "
                f"microseconds: {value.microseconds}}})")
    if isinstance(value, (list, tuple)):
        if is_numeric_sequence(value, vector_min_length):
            raise _NotCypherLiteral("vector preview")
        return "[" + ", ".join(_cypher_literal(item, vector_min_length) for item in value) + "]"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{_cypher_name(key)}: {_cypher_literal(item, vector_min_length)}"
                               for key, item in value.items()) + "}"
    raise _NotCypherLiteral(type(value).__name__)


def render_cypher_params(query_logger: QueryLogger, query: str, parameters: Mapping[str, Any]) -> str:
    """로그 출력용으로 ``query`` 앞에 Neo4j Browser의 ``:param`` 줄을 붙인 문자열을 만든다.

    psycopg ``mogrify()`` 같은 드라이버 기능이 아니다. 드라이버는 Cypher와 파라미터를 따로 보내며,
    이 문자열은 Browser에서 수동 재현할 때 참고하기 위한 근사치다. 정확한 리터럴이 없는 값
    (벡터, bytes, 알 수 없는 객체)은 미리보기와 함께 ``//`` 주석 줄로 쓴다.
    민감 키는 ``query_logger.mask()`` 로 먼저 가린다.
    """
    # region [DB 설명] Cypher 파라미터와 :param
    # Cypher의 `$brand`는 파라미터 자리이며, 드라이버가 `session.run(query, {"brand": ...})`로 값을 따로 전달한다.
    # SQL의 바인딩 변수처럼 쿼리 문자열에 값을 이어 붙이지 않으므로 injection을 막고 쿼리 계획을 재사용할 수 있다.
    # Neo4j Browser에서는 `:param brand => 'HYUNDAI';`로 파라미터를 미리 정한 뒤 같은 쿼리를 실행할 수 있다.
    # 이 표현이 모든 Browser 버전에서 같은 타입으로 해석되는지는 검증하지 않았다.
    # endregion
    if not parameters:
        return query
    shown = query_logger.mask(parameters)
    lines = []
    for key, value in shown.items():
        name = _cypher_name(key)
        try:
            lines.append(f":param {name} => {_cypher_literal(value, query_logger.VECTOR_LOG_SEQUENCE_MIN_LENGTH)};")
        except _NotCypherLiteral:
            preview = query_logger.sanitize(value)
            preview = preview if isinstance(preview, str) else repr(preview)
            lines.append(f"// :param {name} => {preview}; (not reproducible as a literal)")
    return "\n".join(lines) + "\n\n" + query


class _CypherScanError(Exception):
    """로그용 스캐너가 Cypher 텍스트를 끝까지 해석하지 못했을 때(닫히지 않은 문자열·주석 등)."""


def _cypher_parameter_tokens(query: str) -> list[tuple[int, int, str]]:
    """Cypher 어휘 규칙으로 실제 파라미터 토큰 ``$name`` 의 위치를 찾는다(로그 전용, 실행에는 쓰지 않음).

    정규식 치환 대신 앞에서부터 한 글자씩 읽으며 다음 영역을 건너뛴다.
    작은따옴표·큰따옴표 문자열(역슬래시 이스케이프), 백틱 식별자(````` 두 번 = 백틱 한 글자),
    ``//`` 줄 주석, ``/* */`` 블록 주석. 그 밖에서 만난 ``$`` 만 파라미터로 본다.
    이름은 식별자 문자를 끝까지 읽어(``$id`` 와 ``$id2`` 구분) 정하고, ``$`이름``` 과 숫자 ``$0`` 도 처리한다.
    ``$(`` (동적 라벨 등)처럼 이름이 이어지지 않는 ``$`` 는 파라미터가 아니다.

    Returns:
        ``(시작 위치, 끝 위치, 파라미터 이름)`` 목록. 끝 위치는 토큰 바로 다음 글자.

    Raises:
        _CypherScanError: 문자열·백틱·블록 주석이 닫히지 않은 경우.
    """
    tokens: list[tuple[int, int, str]] = []
    index, length = 0, len(query)
    while index < length:
        char = query[index]
        if char in ("'", '"'):
            index += 1
            while index < length and query[index] != char:
                index += 2 if query[index] == "\\" else 1
            if index >= length:
                raise _CypherScanError("unterminated string literal")
            index += 1
        elif char == "`":
            index += 1
            while True:
                end = query.find("`", index)
                if end < 0:
                    raise _CypherScanError("unterminated backtick identifier")
                if end + 1 < length and query[end + 1] == "`":
                    index = end + 2                      # 백틱 두 개 = 이름 안의 백틱 한 글자
                    continue
                index = end + 1
                break
        elif query.startswith("//", index):
            end = query.find("\n", index)
            index = length if end < 0 else end + 1
        elif query.startswith("/*", index):
            end = query.find("*/", index + 2)
            if end < 0:
                raise _CypherScanError("unterminated block comment")
            index = end + 2
        elif char == "$":
            start, index = index, index + 1
            if index < length and query[index] == "`":
                name_chars, index = [], index + 1
                while True:
                    if index >= length:
                        raise _CypherScanError("unterminated backtick parameter name")
                    if query[index] == "`":
                        if index + 1 < length and query[index + 1] == "`":
                            name_chars.append("`")
                            index += 2
                            continue
                        index += 1
                        break
                    name_chars.append(query[index])
                    index += 1
                tokens.append((start, index, "".join(name_chars)))
            elif index < length and (query[index].isalnum() or query[index] == "_"):
                end = index
                while end < length and (query[end].isalnum() or query[end] == "_"):
                    end += 1
                tokens.append((start, end, query[index:end]))
                index = end
        else:
            index += 1
    return tokens


def _inline_literal(value: Any, vector_min_length: int) -> str:
    """인라인 위치에 넣을 Cypher 리터럴. 연산자가 포함된 표현(음수, NaN·Infinity)은 괄호로 감싼다.

    map·list·문자열·함수 호출(``date('...')``)은 괄호 없이 둔다. 패턴의 속성 자리 ``(n $props)`` 는
    map 리터럴만 허용하고 괄호식은 허용하지 않기 때문이다.
    """
    literal = _cypher_literal(value, vector_min_length)
    return f"({literal})" if literal.startswith("-") or " / " in literal else literal


def render_cypher_inline(query_logger: QueryLogger, query: str, parameters: Mapping[str, Any]) -> tuple[str | None, str]:
    """로그 출력용으로 ``$name`` 자리에 값 리터럴을 넣은 Cypher 한 덩어리를 만든다(실행에는 쓰지 않음).

    안전하게 만들 수 없으면 ``(None, 사유)`` 를 돌려주고, 호출자는 ``:param`` 방식으로 대체한다.
    대체하는 경우: 텍스트를 끝까지 해석하지 못함, 쿼리가 쓰는 파라미터가 없음, 정확한 리터럴이 없는 값
    (벡터 미리보기·bytes·알 수 없는 객체), 민감 키 마스킹이 적용됨(마스킹 값으로는 실행 결과를 재현할 수 없음).

    Returns:
        ``(인라인 Cypher 또는 None, 대체 사유 또는 빈 문자열)``.
    """
    try:
        tokens = _cypher_parameter_tokens(query)
    except _CypherScanError as exc:
        return None, f"cannot scan Cypher text ({exc})"
    if not tokens:
        return query, ""
    shown = query_logger.mask(parameters or {})
    if shown is not parameters and parameters:
        return None, "masked parameters"
    missing = sorted({name for _, _, name in tokens if name not in (parameters or {})})
    if missing:
        return None, f"parameters not provided: {', '.join(missing)}"
    literals: dict[str, str] = {}
    try:
        for _, _, name in tokens:
            if name not in literals:
                literals[name] = _inline_literal(parameters[name], query_logger.VECTOR_LOG_SEQUENCE_MIN_LENGTH)
    except _NotCypherLiteral as exc:
        return None, f"no exact literal for ${_cypher_name(name)} ({exc})"
    parts, cursor = [], 0
    for start, end, name in tokens:
        parts.append(query[cursor:start])
        parts.append(literals[name])
        cursor = end
    parts.append(query[cursor:])
    return "".join(parts), ""


def render_cypher_log(query_logger: QueryLogger, query: str, parameters: Mapping[str, Any]) -> str:
    """combined 로그 본문. 가능하면 값이 들어간 인라인 Cypher, 아니면 기존 ``:param`` 줄 + 원문과 재현 제한 주석."""
    inline, reason = render_cypher_inline(query_logger, query, parameters)
    if inline is not None:
        if inline is query:
            return query
        return "// inline parameter values for log only (the driver executed this query with bound parameters)\n" + inline
    warning = ("// NOT REPRODUCIBLE AS-IS: masked values differ from the executed values"
               if reason == "masked parameters" else "// inline rendering skipped")
    return f"{warning} ({reason}); showing :param lines instead\n" + render_cypher_params(query_logger, query, parameters)


def format_graph_value(value: Any) -> str:
    """결과 표 로그용으로 그래프 값을 짧은 문자열로 만든다. 반환 데이터 자체는 바꾸지 않는다.

    예: Node → ``(:Vehicle {brand: 'HYUNDAI'})``, Relationship → ``[:MADE_BY {since: 2020}]``,
    Path → ``(:A)-[:R]->(:B)`` (관계 방향이 반대면 ``<-[:R]-``).
    """
    # region [DB 설명] Neo4j Node / Relationship / Path
    # Node는 label 집합(`labels`)과 속성(`items()`)을 가진 그래프의 점이다(RDB의 행과 비슷).
    # Relationship은 type(`type`)과 속성, 시작/끝 Node를 가진 방향 있는 연결선이다(RDB의 FK/조인 테이블 역할).
    # Path는 Node와 Relationship이 번갈아 이어진 경로이며 `nodes`, `relationships`로 구성 요소를 읽는다.
    # 드라이버가 돌려준 이 객체들은 `select_list()` 결과에 그대로 남고, 여기서는 로그 문자열만 만든다.
    # endregion
    types = _driver_types()
    if isinstance(value, types.Node):
        labels = "".join(f":{_cypher_name(label)}" for label in sorted(value.labels))
        properties = dict(value.items())
        return f"({labels} {format_graph_value(properties)})" if properties else f"({labels})"
    if isinstance(value, types.Relationship):
        properties = dict(value.items())
        body = f":{_cypher_name(value.type)}" + (f" {format_graph_value(properties)}" if properties else "")
        return f"[{body}]"
    if isinstance(value, types.GraphPath):
        previous = value.start_node
        parts = [format_graph_value(previous)]
        for relationship, node in zip(value.relationships, value.nodes[1:]):
            start = relationship.start_node
            forward = start is None or start.element_id == previous.element_id
            text = format_graph_value(relationship)
            parts.append(f"-{text}->" if forward else f"<-{text}-")
            parts.append(format_graph_value(node))
            previous = node
        return "".join(parts)
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{key}: {format_graph_value(item)}" for key, item in value.items()) + "}"
    if isinstance(value, (list, tuple)) and not isinstance(value, str):
        if isinstance(value, types.Point):
            return repr(value)
        return "[" + ", ".join(format_graph_value(item) for item in value) + "]"
    if isinstance(value, str):
        return repr(value)
    return str(value)


def _format_result_cell(value: Any) -> str:
    """결과 표 셀 변환 함수. 최상위 문자열은 PostgreSQL 표와 같게 따옴표 없이 둔다."""
    return value if isinstance(value, str) else format_graph_value(value)


def summary_counters(summary: Any) -> dict[str, int]:
    """드라이버 ``ResultSummary.counters`` 중 0이 아닌 정수 값만 dict로 반환한다.

    드라이버가 실제로 보고한 값만 담고 새로운 수치를 계산하지 않는다.
    읽는 중 오류가 나면 빈 dict를 반환한다(Mock 객체 등에서도 안전).
    """
    # region [DB 설명] ResultSummary와 counters
    # Neo4j는 쿼리 실행이 끝나면 `result.consume()`으로 ResultSummary를 돌려준다.
    # `summary.counters`에는 nodes_created, properties_set처럼 이번 실행이 바꾼 그래프 요소 수가 들어 있다.
    # PostgreSQL의 rowcount(영향받은 행 수)와는 의미가 다르므로 별도 항목으로 기록한다.
    # endregion
    found = {}
    try:
        counters = getattr(summary, "counters", None)
        for name in SUMMARY_COUNTER_NAMES:
            value = getattr(counters, name, None)
            if isinstance(value, int) and not isinstance(value, bool) and value:
                found[name] = value
    except Exception:
        return {}
    return found


def _format_counters(counters: Mapping[str, int]) -> str:
    """counter dict를 ``{nodes_created: 1, properties_set: 2}`` 형식 문자열로 만든다."""
    return "{" + ", ".join(f"{name}: {value}" for name, value in counters.items()) + "}"


def _server_ms(summary: Any, name: str) -> int | None:
    """summary의 서버 측 시간 속성(ms)을 정수일 때만 반환하고, 없으면 ``None`` 을 반환한다."""
    value = getattr(summary, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class Neo4jDbSession(QuerySession):
    """``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다.

    ``mapper_root`` 아래의 ``*.cypher`` 파일을 재귀적으로 찾는다. 파일 이름(stem)이 namespace이고,
    파일 안의 ``// name: statement`` 선언 줄이 statement의 시작이다.
    드라이버는 이 클래스가 소유하거나 닫지 않는다(생성·종료는 주입한 쪽 책임).

    로그(logger ``car_search_rag.neo4j``, INFO 레벨):

    * ``cypher_log_mode`` - ``combined`` 는 Cypher 위에 Neo4j Browser ``:param`` 줄을,
      ``separate`` 는 Cypher와 ``PARAMS`` 줄을 출력한다. ``none`` 은 모든 메서드의
      QUERY / BATCH QUERY 로그를 끈다. PostgreSQL ``execute()`` 와 달리 none 모드에서
      강제로 쿼리 로그를 남기는 메서드는 없다.
      RESULT / DONE / BATCH DONE / TRANSACTION 줄은 모드와 관계없이 항상 출력한다.
    * ``result_log`` / ``result_log_limit`` - 결과 표 로그. PostgreSQL과 같다.
    * ``sensitive_log_keys`` - 로그에서만 ``<MASKED>`` 로 가릴 파라미터 키.
      기본값은 ``DEFAULT_SENSITIVE_KEYS`` 이며 ``None`` 이면 마스킹하지 않는다.

    Python ``perf_counter`` 로 측정하는 시간 항목(밀리초):
    ``session_ms`` (``driver.session()`` 진입 시간. 드라이버는 연결을 실제 실행 시점에 빌리므로
    연결 시간이 아니며, 트랜잭션 안에서는 거의 0), ``cypher_log_ms`` (QUERY 로그 렌더링),
    ``query_fetch_ms`` (``run()`` + 레코드 읽기 + ``consume()``), ``total_ms`` (결과 로그 포함).
    ``server_available_after_ms`` / ``server_consumed_after_ms`` 는 드라이버가 보고한
    ``ResultSummary.result_available_after`` / ``result_consumed_after`` 값이며,
    서버가 보고하지 않으면 생략한다.

    Note:
        ``_active_session`` / ``_active_transaction`` 으로 트랜잭션 상태를 인스턴스에 보관하므로
        한 인스턴스를 여러 thread가 동시에 트랜잭션에 사용하면 안 된다.
    """

    # region [DB 설명] Neo4j Driver / Session / Transaction
    # Driver: 애플리케이션 전체에서 하나를 만들어 공유하는 객체로, 내부에 연결 pool을 가진다(DataSource와 비슷).
    # Session: `driver.session(database=...)`로 만드는 가벼운 작업 단위. 쿼리를 실행할 때 pool에서 연결을 빌린다.
    #   `session.run(query, params)`는 쿼리 하나짜리 auto-commit 트랜잭션으로 실행된다.
    # Transaction: `session.begin_transaction()`으로 시작하며, 여러 `tx.run()`을 하나로 묶어
    #   `commit()` 또는 `rollback()`한다(JDBC에서 autoCommit=false 후 commit/rollback하는 것과 비슷).
    # 이 클래스는 트랜잭션 밖에서는 호출마다 새 Session을, `transaction()` 안에서는 같은 Transaction을 사용한다.
    # endregion

    def __init__(
        self,
        *,
        mapper_root: str | Path,
        driver=None,
        database: str | None = None,
        cypher_log_mode: str = "combined",
        result_log: bool = False,
        result_log_limit: int = 100,
        sensitive_log_keys: Collection[str] | None = DEFAULT_SENSITIVE_KEYS,
    ):
        """드라이버와 로그 설정을 보관하고 Cypher mapper를 등록한다.

        모든 인자는 keyword로만 전달한다(``*`` 뒤 인자). ``driver`` 없이 만들 수 있지만
        그 경우 쿼리 실행 메서드는 ``RuntimeError`` 를 낸다(mapper 확인용 테스트 등에 사용).
        """
        self.driver = driver
        self.mapper_root = Path(mapper_root)
        self.database = database
        self.query_logger = QueryLogger(
            logger,
            log_mode=cypher_log_mode,
            result_log=result_log,
            result_log_limit=result_log_limit,
            mode_option_name="cypher_log_mode",
            query_label="Cypher",
            sensitive_keys=sensitive_log_keys,
            value_formatter=_format_result_cell,
            combined_params_line=False,   # :param 줄이 이미 파라미터를 보여주므로 PARAMS 줄은 생략
        )
        self.mappers: dict[str, str] = {}
        self.mapper_paths: dict[str, Path] = {}
        self._active_session = None
        self._active_transaction = None
        self.register_mappers()

    # 아래 property들은 값을 QueryLogger에 위임한다(PostgresDbSession의 property 설명 참고).
    @property
    def cypher_log_mode(self) -> str:
        """현재 Cypher 상세 로그 모드(combined / separate / none)."""
        return self.query_logger.log_mode

    @cypher_log_mode.setter
    def cypher_log_mode(self, value: str) -> None:
        """Cypher 로그 출력 방식을 QueryLogger에 위임한다."""
        self.query_logger.log_mode = value

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
        """결과 표 로그에 표시할 최대 행 수."""
        return self.query_logger.result_log_limit

    @result_log_limit.setter
    def result_log_limit(self, value: int) -> None:
        """로그에 표시할 조회 결과 건수 제한을 QueryLogger에 위임한다."""
        self.query_logger.result_log_limit = value

    def register_mappers(self) -> dict[str, str]:
        """``*.cypher`` mapper 파일에서 이름 붙은 쿼리 블록을 읽어 ``self.mappers`` 에 등록한다.

        Returns:
            ``{"namespace.statement": Cypher 문자열}`` dict(``self.mappers`` 자체).

        Raises:
            FileNotFoundError / NotADirectoryError: ``mapper_root`` 가 없거나 디렉터리가 아닌 경우.
            ValueError: 선언이 없는 파일, 잘못된 namespace, 빈 statement, 중복 statement가 있는 경우.

        Note:
            각 statement의 Cypher는 "선언 줄 끝 ~ 다음 선언 줄 시작" 사이의 텍스트를 ``strip()`` 한 것이다.
            따라서 statement 사이에 둔 ``//`` 주석도 앞 statement의 Cypher 텍스트에 포함된다.
            첫 선언 줄보다 앞의 텍스트(파일 머리 주석)만 어떤 statement에도 포함되지 않는다.
        """
        if not self.mapper_root.exists():
            raise FileNotFoundError(f"Cypher mapper root does not exist: {self.mapper_root}")
        if not self.mapper_root.is_dir():
            raise NotADirectoryError(f"Cypher mapper root is not a directory: {self.mapper_root}")
        for path in sorted(self.mapper_root.rglob("*.cypher")):
            text = path.read_text(encoding="utf-8-sig")
            headers = list(_STATEMENT_HEADER.finditer(text))
            if not headers:
                raise ValueError(f"No '// name: statement' declarations found in '{path}'")
            namespace = path.stem
            if not _IDENTIFIER.fullmatch(namespace):
                raise ValueError(f"Invalid Cypher mapper namespace {namespace!r} in {path!r}")
            # 선언 줄 위치(match 객체)를 기준으로 파일 텍스트를 statement별로 잘라낸다.
            # region [Python 설명] re.Match의 start()/end()와 문자열 slicing
            # `header.end()`는 선언 줄이 끝나는 문자 위치, `headers[index + 1].start()`는 다음 선언 줄의 시작 위치다.
            # `text[a:b]`는 a부터 b 직전까지의 부분 문자열이며, 마지막 statement는 파일 끝(`len(text)`)까지 사용한다.
            # `.strip()`은 앞뒤 공백·빈 줄을 제거한다.
            # endregion
            for index, header in enumerate(headers):
                statement = header.group(1)
                statement_id = f"{namespace}.{statement}"
                end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
                query = text[header.end():end].strip()
                if not query:
                    raise ValueError(f"Empty Cypher statement '{statement_id}' in '{path}'")
                if statement_id in self.mappers:
                    raise ValueError(
                        f"Duplicate Cypher statement '{statement_id}' in "
                        f"'{self.mapper_paths[statement_id]}' and '{path}'"
                    )
                self.mappers[statement_id] = query
                self.mapper_paths[statement_id] = path
        return self.mappers

    def _query(self, statement_id: str) -> str:
        """``namespace.statement`` ID를 검증하고 등록된 Cypher 문자열을 반환한다.

        Raises:
            ValueError: 점이 정확히 하나가 아니거나 식별자 규칙에 맞지 않는 경우.
            LookupError: 등록되지 않은 statement인 경우(원래 KeyError는 ``__cause__`` 로 연결).
        """
        # region [Python 설명] raise ... from exc
        # `raise LookupError(...) from exc`는 새 예외를 던지면서 원인 예외(KeyError)를 연결해 둔다.
        # traceback에 "The above exception was the direct cause..."로 두 예외가 함께 표시된다(Java의 cause와 비슷).
        # endregion
        if not isinstance(statement_id, str) or statement_id.count(".") != 1:
            raise ValueError("statement_id must use namespace.statement format")
        namespace, statement = statement_id.split(".", 1)
        if not _IDENTIFIER.fullmatch(namespace) or not _IDENTIFIER.fullmatch(statement):
            raise ValueError("statement_id must contain valid namespace and statement identifiers")
        try:
            return self.mappers[statement_id]
        except KeyError as exc:
            raise LookupError(f"Cypher statement '{statement_id}' was not found") from exc

    def _require_driver(self):
        """주입된 드라이버를 반환한다. 없으면 ``RuntimeError`` 를 낸다."""
        if self.driver is None:
            raise RuntimeError("Neo4j driver is required to execute Cypher; inject an official driver")
        return self.driver

    def _session_options(self) -> dict[str, Any]:
        """``driver.session(**옵션)`` 에 넘길 인자. database가 없으면 서버 기본 DB를 사용한다."""
        return {"database": self.database} if self.database else {}

    def _log_query(self, statement_id: str, query: str, parameters: Mapping[str, Any]) -> None:
        """QUERY 로그를 출력한다. combined 모드의 렌더링 함수로 ``render_cypher_log`` 를 넘긴다.

        로그 본문만 인라인 Cypher(또는 ``:param`` 대체)로 만들고, 실제 실행은 ``_consume()`` 의
        ``runner.run(query, bound_parameters)`` 바인딩 방식 그대로다.
        """
        # region [Python 설명] lambda
        # `lambda _: render_cypher_params(...)`는 인자 하나(`_`, 사용하지 않음)를 받는 이름 없는 함수다.
        # QueryLogger가 combined 모드에서만 이 함수를 호출하므로, 다른 모드에서는 렌더링 비용이 없다.
        # endregion
        self.query_logger.log_query(
            statement_id, query, parameters,
            render_combined=lambda _: render_cypher_log(self.query_logger, query, parameters),
        )

    def _consume(self, runner, statement_id: str, query: str, bound_parameters: dict, log_query: bool, timings: dict):
        """``runner`` (Session 또는 Transaction)로 Cypher를 한 번 실행하고 결과를 모두 읽는다.

        Returns:
            ``(컬럼 이름 목록, Record list, ResultSummary)`` tuple.
            측정한 시간은 전달받은 ``timings`` dict에 기록한다.
        """
        log_started = perf_counter()
        if log_query:
            self._log_query(statement_id, query, bound_parameters)
        fetch_started = perf_counter()
        timings["cypher_log_ms"] = (fetch_started - log_started) * 1000

        # 쿼리는 한 번만 실행하며, 아래 레코드와 summary는 모두 이 하나의 result에서 나온다.
        # region [DB 설명] Result 읽기 순서: keys() → 레코드 순회 → consume()
        # `result.keys()`는 RETURN 절의 컬럼 이름이다. 쓰기 전용 쿼리(RETURN 없음)는 빈 목록이다.
        # `list(result)`는 결과 레코드를 모두 받아 메모리에 담는다. result는 한 번만 순회할 수 있다.
        # `result.consume()`은 남은 결과를 버리고 실행 통계(ResultSummary)를 반환한다.
        # Session이 닫히면 result를 더 읽을 수 없으므로, with 블록 안에서 모두 읽어 둔다.
        # endregion
        result = runner.run(query, bound_parameters)
        columns = result.keys()
        records = list(result)
        summary = result.consume()
        timings["query_fetch_ms"] = (perf_counter() - fetch_started) * 1000
        return columns, records, summary

    def _run_and_consume(
        self,
        statement_id: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        log_query: bool = True,
        timings: dict | None = None,
    ):
        """statement를 한 번 실행하고 ``(컬럼, 레코드 list, summary)`` 를 반환한다.

        트랜잭션 안이면 활성 Transaction으로, 밖이면 새 Session의 auto-commit 실행으로 수행한다.

        Args:
            log_query: False면 QUERY 로그를 생략한다(``execute_many()`` 의 행별 실행).
            timings: 시간 측정값을 기록할 dict. 호출자가 넘기면 같은 dict에 채운다.
        """
        query = self._query(statement_id)
        # 호출자의 원본 Mapping을 바꾸지 않도록 드라이버에는 새 dict 복사본을 넘긴다.
        bound_parameters = dict(parameters or {})
        timings = {} if timings is None else timings
        started = perf_counter()
        if self._active_transaction is not None:
            timings["session_ms"] = (perf_counter() - started) * 1000
            return self._consume(self._active_transaction, statement_id, query, bound_parameters, log_query, timings)

        # 트랜잭션 밖: 호출마다 Session을 열고, with 블록이 끝나면 Session을 닫는다(드라이버는 닫지 않음).
        driver = self._require_driver()
        with driver.session(**self._session_options()) as session:
            timings["session_ms"] = (perf_counter() - started) * 1000
            return self._consume(session, statement_id, query, bound_parameters, log_query, timings)

    def _log_done(self, event: str, statement_id: str, records: list, summary: Any, timings: dict, started: float) -> None:
        """``RESULT`` / ``DONE`` 요약 줄(행 수, counters, 시간)을 출력한다. 값 변환 실패는 경고만 남긴다."""
        if not self.query_logger.enabled():
            return
        try:
            counters = _format_counters(summary_counters(summary))
            available = _server_ms(summary, "result_available_after")
            consumed = _server_ms(summary, "result_consumed_after")
        except Exception as exc:
            logger.warning("Neo4j summary 로그 변환 실패 [%s]: %s", statement_id, type(exc).__name__)
            counters, available, consumed = None, None, None
        self.query_logger.log_summary(
            event, statement_id,
            rows=len(records),
            counters=counters,
            session_ms=timings.get("session_ms"),
            cypher_log_ms=timings.get("cypher_log_ms"),
            query_fetch_ms=timings.get("query_fetch_ms"),
            total_ms=(perf_counter() - started) * 1000,
            server_available_after_ms=available,
            server_consumed_after_ms=consumed,
        )

    def select_list(self, statement_id: str, parameters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """Neo4j 레코드를 dict 목록으로 반환한다. Node 등 드라이버 그래프 객체는 그대로 유지한다.

        Returns:
            ``[{RETURN 컬럼명: 값, ...}, ...]``. 결과가 없으면 빈 list.
        """
        started = perf_counter()
        timings: dict = {}
        # `_`는 사용하지 않는 첫 번째 반환값(컬럼 목록)을 받는 관례적인 변수 이름이다.
        _, records, summary = self._run_and_consume(statement_id, parameters, timings=timings)
        # 드라이버 Record는 Mapping처럼 동작하므로 `dict(record)`로 일반 dict로 바꾼다.
        rows = [dict(record) for record in records]
        self.query_logger.log_result_data(statement_id, rows)
        self._log_done("RESULT", statement_id, rows, summary, timings, started)
        return rows

    def select_one(self, statement_id: str, parameters: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        """첫 레코드를 반환하고, 결과가 없으면 ``None`` 을 반환한다(LIMIT를 자동 추가하지 않음)."""
        records = self.select_list(statement_id, parameters)
        return records[0] if records else None

    def _execute(self, statement_id: str, parameters: Mapping[str, Any] | None, *, batch: bool):
        """``execute()`` 공통 구현. ``(반환값, summary)`` 를 돌려준다.

        ``batch=True`` (``execute_many()`` 에서 호출)이면 행별 QUERY / RESULT DATA / DONE 로그를 생략한다.
        """
        started = perf_counter()
        timings: dict = {}
        columns, records, summary = self._run_and_consume(
            statement_id, parameters, log_query=not batch, timings=timings
        )
        result = [dict(record) for record in records] if columns else summary
        if not batch:
            if columns:
                self.query_logger.log_result_data(statement_id, result)
            self._log_done("DONE", statement_id, records, summary, timings, started)
        return result, summary

    def execute(self, statement_id: str, parameters: Mapping[str, Any] | None = None) -> Any:
        """Cypher를 한 번 실행한다. 결과 컬럼이 있으면 레코드를, 없으면 드라이버 summary를 반환한다.

        ``RETURN`` 이 있는 쿼리는 ``list[dict]`` (0건이면 빈 list)를, RETURN이 없는 명령은
        공식 드라이버의 ``ResultSummary`` 를 반환한다. 이 의미는 Neo4j 전용이며
        PostgreSQL의 rowcount와 같은 의미로 취급하지 않는다.
        """
        result, _ = self._execute(statement_id, parameters, batch=False)
        return result

    def execute_many(
        self,
        statement_id: str,
        parameters_list: Sequence[Mapping[str, Any]],
    ) -> list[Any]:
        """같은 Cypher를 파라미터 묶음마다 반복 실행하며, 전체를 하나의 트랜잭션으로 처리한다.

        의도적으로 ``UNWIND`` 한 번의 실행으로 바꾸지 않는다. 이미 트랜잭션 안에서 호출하면
        그 트랜잭션을 재사용하고, 밖에서 호출하면 모든 실행을 함께 commit하거나 함께 rollback한다.

        Returns:
            실행별 ``execute()`` 와 같은 형태의 결과 list(RETURN 있으면 ``list[dict]``, 없으면 summary).
            빈 목록이면 실행하지 않고 빈 list를 반환한다.

        Note:
            실행 전 ``BATCH QUERY`` 로그(최대 100건 파라미터)와 실행 후 counters 합계가 담긴
            ``BATCH DONE`` 로그를 한 번씩 출력하고, 행별 QUERY / DONE 로그는 중복을 막기 위해 생략한다.
        """
        if not parameters_list:
            return []
        self._require_driver()
        query = self._query(statement_id)
        started = perf_counter()

        # 활성 트랜잭션이 있으면 아무 일도 하지 않는 context를, 없으면 새 트랜잭션 context를 사용한다.
        # region [Python 설명] nullcontext와 조건부 with
        # `contextlib.nullcontext(value)`는 진입 시 value를 돌려주고 종료 시 아무것도 하지 않는 context manager다.
        # 두 경우 모두 `with scope:` 한 줄로 쓸 수 있어, 트랜잭션 유무에 따라 코드를 두 벌 만들지 않아도 된다.
        # 새 트랜잭션이면 with 블록이 정상 종료될 때 commit, 예외가 나면 rollback된다.
        # endregion
        scope = nullcontext(self) if self._active_transaction is not None else self.transaction()
        with scope:
            self.query_logger.log_batch_query(statement_id, query, parameters_list)
            results = []
            totals: dict[str, int] = {}
            # 실행마다 결과를 모으고, counter 값은 이름별로 합산한다(`totals.get(name, 0)`은 처음이면 0).
            for parameters in parameters_list:
                result, summary = self._execute(statement_id, parameters, batch=True)
                results.append(result)
                for name, value in summary_counters(summary).items():
                    totals[name] = totals.get(name, 0) + value

        # commit까지 성공해 with 블록을 빠져나온 경우에만 BATCH DONE을 기록한다.
        self.query_logger.log_summary(
            "BATCH DONE", statement_id,
            rows=len(results),   # 실제 실행 건수. len()이 없는 iterable을 받아도 안전하다.
            counters=_format_counters(totals),
            elapsed_ms=(perf_counter() - started) * 1000,
        )
        return results

    @contextmanager
    def transaction(self) -> Iterator["Neo4jDbSession"]:
        """Neo4j Session 하나와 Transaction 하나를 열고, 블록 종료 시 commit 또는 rollback한다.

        사용 예::

            with session.transaction():
                session.execute("graph.create_a", {...})
                session.execute("graph.create_b", {...})

        Raises:
            RuntimeError: 이미 트랜잭션이 활성화된 상태에서 다시 호출한 경우(중첩 미지원).

        Note:
            ``commit()`` 이 실패하면 ``TRANSACTION COMMIT FAILED`` 로 기록하고(COMMIT으로 기록하지 않음),
            commit 결과를 단정하지 않은 채 rollback을 시도한 뒤 commit 예외를 다시 던진다.
            rollback이 실패하면 traceback과 함께 기록하고 원래 예외를 다시 던진다.
            블록 안에서 예외를 직접 처리해 삼키면 정상 종료로 보고 commit한다.
        """
        if self._active_transaction is not None:
            raise RuntimeError("Nested transactions are not supported")
        driver = self._require_driver()
        with driver.session(**self._session_options()) as session:
            # 트랜잭션을 시작하고, 블록 안의 select/execute가 이 Transaction을 쓰도록 인스턴스에 보관한다.
            transaction = session.begin_transaction()
            self._active_session = session
            self._active_transaction = transaction
            self.query_logger.log_transaction("BEGIN")
            # region [Python 설명] contextmanager 안의 중첩 try
            # 안쪽 첫 번째 try: with 블록에서 예외가 나면(`yield` 위치에서 발생) rollback 후 다시 던진다.
            # 안쪽 두 번째 try: 블록이 정상 종료되면 commit하고, commit 실패 시 rollback을 시도한 뒤 다시 던진다.
            # 바깥 try/finally: 어떤 경우든 활성 트랜잭션 상태를 None으로 되돌려 다음 트랜잭션을 허용한다.
            # endregion
            try:
                try:
                    yield self
                except BaseException:
                    self._rollback(transaction)
                    raise
                try:
                    transaction.commit()
                except BaseException as exc:
                    self.query_logger.log_transaction_failure("COMMIT", exc)
                    self._rollback(transaction, after_commit_failure=True)
                    raise
                self.query_logger.log_transaction("COMMIT")
            finally:
                self._active_transaction = None
                self._active_session = None

    def _rollback(self, transaction, *, after_commit_failure: bool = False) -> None:
        """rollback을 시도하고 결과를 로그로 남긴다. rollback 예외는 전파하지 않는다(원래 예외를 보존)."""
        # commit()이 실패한 뒤에는 서버가 이미 commit했을 수 있고(예: IncompleteCommit),
        # 드라이버가 트랜잭션을 닫으므로 rollback은 "시도"로만 기록하고 성공을 단정하지 않는다.
        try:
            transaction.rollback()
        except Exception:
            self.query_logger.log_rollback_failure(
                "TRANSACTION ROLLBACK FAILED AFTER COMMIT FAILURE (commit outcome unknown)"
                if after_commit_failure else "TRANSACTION ROLLBACK FAILED"
            )
        else:
            self.query_logger.log_transaction(
                "ROLLBACK ATTEMPTED AFTER COMMIT FAILURE (commit outcome unknown)"
                if after_commit_failure else "ROLLBACK"
            )
