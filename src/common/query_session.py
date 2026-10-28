"""DB 종류와 무관한 동기식 쿼리 세션 계약(인터페이스).

``PostgresDbSession`` 과 ``Neo4jDbSession`` 이 이 클래스를 상속해 같은 메서드 이름
(``select_list``, ``select_one``, ``execute``, ``execute_many``, ``transaction``)을 제공한다.
Repository/Service 코드는 이 메서드 이름만 알면 되고, SQL인지 Cypher인지는 세션이 처리한다.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any


# region [Python 설명] ABC와 @abstractmethod
# `ABC`(Abstract Base Class)를 상속하고 `@abstractmethod`를 붙인 메서드는 하위 클래스가 반드시 구현해야 한다.
# 구현하지 않은 추상 메서드가 남아 있으면 객체 생성 시 TypeError가 난다(Java의 abstract class와 비슷).
# Java interface와 달리 Python은 "이 메서드가 있으면 된다"는 duck typing도 허용하지만,
# 여기서는 ABC로 계약을 명시해 실수로 메서드를 빠뜨리는 것을 막는다.
#
# type hint 읽는 법:
#   `Mapping[str, Any] | None` = key가 str인 dict 형태(읽기 전용 Map) 또는 None
#   `Sequence[Mapping[...]]`   = list/tuple처럼 순서와 index가 있는 컬렉션
#   `AbstractContextManager[...]` = `with` 문에 사용할 수 있는 객체
# type hint는 실행 시 검사되지 않는 문서/도구용 정보다.
# endregion
class QuerySession(ABC):
    """DB별 쿼리 세션이 공통으로 제공하는 최소 계약.

    statement ID는 ``namespace.statement`` 형식을 사용한다(예: ``car_manual.select_car``).
    쿼리 문법, 트랜잭션 구현 방식, 변경 쿼리의 반환값 의미는 DB마다 다르다.
    예를 들어 PostgreSQL의 ``execute_many()`` 는 rowcount를, Neo4j는 실행별 결과 list를 반환한다.
    """

    @abstractmethod
    def select_list(
        self,
        statement_id: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """조회 결과의 모든 레코드를 dict 목록으로 반환한다."""

    @abstractmethod
    def select_one(
        self,
        statement_id: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """조회 결과의 첫 레코드를 반환하고, 레코드가 없으면 ``None`` 을 반환한다."""

    @abstractmethod
    def execute(
        self,
        statement_id: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> Any:
        """DB별 statement 하나를 실행하고 해당 DB 고유의 결과를 그대로 반환한다."""

    @abstractmethod
    def execute_many(
        self,
        statement_id: str,
        parameters_list: Sequence[Mapping[str, Any]],
    ) -> Any:
        """같은 statement를 여러 파라미터 묶음에 적용한다."""

    @abstractmethod
    def transaction(self) -> AbstractContextManager["QuerySession"]:
        """블록 전체를 원자적으로 commit 또는 rollback하는 context manager를 반환한다.

        사용 예: ``with session.transaction(): session.execute(...)``
        """
