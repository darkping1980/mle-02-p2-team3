# Step 1 — Basic: Session 직접 호출

## 학습 목적

Service와 Repository 없이 `main.py`에서 `PostgresDbSession`과 `Neo4jDbSession`을 직접 호출합니다. Python 코드에는 쿼리 본문을 넣지 않고 `.sql`과 `.cypher` Mapper를 사용합니다.

## 파일과 실행 흐름

- `main.py`: 설정, Session 생성, 등록·조회·정리 순서를 위에서 아래로 실행합니다.
- `basic_sample.sql`: 일반 데이터와 3차원 벡터 등록·조회·삭제 쿼리입니다.
- `basic_sample.cypher`: 프로젝트·기술 노드, 관계 등록·조회·삭제 쿼리입니다.
- `tests/test_basic.py`: Mapper 범위와 기본 오프라인 실행을 검사합니다.

```text
main.py → PostgresDbSession → basic_sample.sql → PostgreSQL
main.py → Neo4jDbSession → basic_sample.cypher → AuraDB
```

`mapper_root = Path(__file__).resolve().parent`는 실행 디렉터리와 관계없이 이 단계의 Mapper만 불러옵니다. `namespace.statement`에서 namespace는 Mapper 파일명(`basic_sample`), statement는 `-- name:` 또는 `// name:` 뒤의 이름입니다. Python `dict`가 Mapper 파라미터로 전달되고, 조회 결과는 `list[dict]` 또는 `dict | None`으로 반환됩니다.

## 실행

기본 실행은 DB에 연결하거나 쓰지 않습니다.

```powershell
uv run python -m graph_rag_sample.step_01_basic.main
```

실제 두 DB에서 등록·조회·정리까지 진행하려면 `.env` 또는 환경변수를 설정한 뒤 의도적으로 다음 옵션을 줍니다.

```powershell
uv run python -m graph_rag_sample.step_01_basic.main --run-db
```

필요 변수: `DB_URL`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, 선택 `NEO4J_DATABASE`. Aura TLS 인증서는 기존 `Neo4jDbSession` 설정을 사용합니다.

PostgreSQL 임시 테이블과 샘플 데이터는 하나의 `with session.transaction()` 블록 안에서 생성·조회·삭제합니다. 이 테이블은 `ON COMMIT DROP`이므로 Commit 후에는 사라집니다. Neo4j 데이터도 매 실행 고유 `test_run_id`를 부여하고 그 ID가 있는 노드만 삭제합니다. 오류가 발생하면 트랜잭션이 Rollback됩니다.

예상 출력은 아래와 같습니다. 실행 ID와 유사도 소수점은 실행마다 다릅니다.

~~~text
postgres_general: [Python 문서, Neo4j 문서]
postgres_vectors: [Python similarity=1.0, Neo4j similarity≈0.97]
postgres_remaining_general: []
postgres_remaining_vectors: []
neo4j_relationships: [Project A → USES_TECHNOLOGY → Neo4j, Project A → USES_TECHNOLOGY → Python]
neo4j_remaining_nodes: 0
neo4j_remaining_relationships: 0
~~~

## 벡터 실습 주의

`[1.0, 0.0, 0.0]`, `[0.8, 0.2, 0.0]`은 벡터 거리 정렬을 배우기 위한 고정 좌표입니다. 의미를 가진 임베딩이 아니며 OpenAI를 호출하지 않습니다.

오프라인 테스트:

```powershell
uv run python -m unittest discover -s src/graph_rag_sample/step_01_basic/tests -p "test_*.py"
```
