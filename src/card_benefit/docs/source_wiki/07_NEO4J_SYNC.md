# 7. Neo4j 동기화

[목차](README.md) · [PostgreSQL 스키마](06_POSTGRESQL_SCHEMA.md)

<details><summary>▼ 7.1 적재 방향과 실행 코드</summary>

조회 대상 그래프는 `dp_` prefix의 노드/관계다. 저장소 구현은 [`neo4j_load_draft.py`](../../payment_card/db_pipeline/neo4j_load_draft.py)와 관련 dry-run/validation 스크립트에 있다. 그래프는 PostgreSQL 데이터를 소스로 구성하는 적재 경로이며, 이번 문서 작성 작업은 적재를 실행하지 않았다.

적재와 조회는 별도다. 조회는 [`neo4j_search.py`](../../payment_card/db_pipeline_origin_search/neo4j_search.py)의 Cypher mapper를 읽기 전용으로 실행한다. `graph_questions.cypher` 상단 주석은 statement 이름과 조회 함수 대응을 설명한다.

<details><summary>▼ 7.1.1 Cypher statement 등록·읽기 전용 실행</summary>

- `Neo4jDbSession(mapper_root=...)`가 `// name:` statement를 mapper로 구성한다.
- `Neo4jSearch._query()`는 parameterized query를 `READ_ACCESS` 세션의 `execute_read()`에서 실행한다. 공개 조회 API의 값을 문자열에 직접 붙이지 않는다.
- catalog, list, relation, context, rules, conditions, limits, evidence statement가 있다. `hop*` 쿼리는 테스트/검증용이며 기본 GraphRAG retrieve 경로가 호출하지 않는다는 모듈 주석을 따른다.
- 소스: [`neo4j_search.py`](../../payment_card/db_pipeline_origin_search/neo4j_search.py), [`graph_questions.cypher`](../../payment_card/db_pipeline_origin_search/graph_questions.cypher), [`Neo4jDbSession`](../../../common/neo4j_db_session.py).
</details>
</details>

<details><summary>▼ 7.2 PostgreSQL → 그래프 데이터 의미</summary>

그래프 조회에서 사용하는 주요 타입은 `dp_card_product`, `dp_card_bnft`, `dp_card_product_item`, `dp_card_common_bnft`, `dp_bnft_rule`, `dp_rule_target`, `dp_cond_expr`, `dp_cond_branch`, `dp_cond_atom`, `dp_card_source_evidence`, `dp_card_doc_chunk`, `dp_card_doc_page`, `dp_card_doc` 등이다. 구체적인 노드 label/관계는 [`graph_questions.cypher`](../../payment_card/db_pipeline_origin_search/graph_questions.cypher)의 실제 MATCH 패턴을 기준으로 한다.

그래프 적재 DDL/검증 자료에는 [`neo4j_validation.cypher`](../../payment_card/db_pipeline/neo4j_validation.cypher), [`neo4j_validation.sql`](../../payment_card/db_pipeline/neo4j_validation.sql), [`neo4j_load_draft.py`](../../payment_card/db_pipeline/neo4j_load_draft.py)가 있다. 이들 파일은 저장소 구현/검증 계획이며 운영 Neo4j 반영 상태는 미확인이다.
</details>

<details><summary>▼ 7.3 Neo4j 실패와 응답</summary>

Cypher driver 예외는 `_query()` 밖으로 전파되고 GraphRAG의 노드 단위 처리/실패 분류에 도달한다. 모든 공개 조회는 읽기 전용이다. 이 경로에서 Neo4j 쓰기/commit을 수행하지 않는다. 조회 실패 때의 사용자 결과는 [8장](08_GRAPHRAG_QUERY.md)과 [9장](09_ANSWER_VALIDATION.md).
</details>

[GraphRAG 조회 →](08_GRAPHRAG_QUERY.md)

