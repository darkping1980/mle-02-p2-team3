# Neo4j 목표 모델 전환 실행 기록 (2026-10-22)

> **기록 문서.** 아래 라벨·제약조건 이름은 2026-10-22 당시 이름이다. 2026-10-23 노드 라벨을 PostgreSQL 테이블명으로 통일했다
> (`RcpRecipe`→`rcp`, `RcpIngredient`→`ingr`, `RcpRecipeCategory`→`rcp_cat`): `neo4j_label_rename_20261023.md`.

## 결론

AuraDB 인스턴스 `6ac1f0f8`의 DB `6ac1f0f8`를 사용자 승인에 따라 **전체 초기화한 뒤 PostgreSQL `recipe` 목표 모델에서 새로 적재**했다.
최종 그래프는 노드 **1,437**, 관계 **11,584**이며 PostgreSQL과 업무 ID·관계 집합·속성이 일치한다.

선택적 정리(`neo4j_legacy_cleanup.cypher`) 대신 전체 초기화를 택했다. 기존 Rcp 데이터는 PostgreSQL에서 모두 재현할 수 있고,
다른 실습 데이터 보존 제한이 해제되었으며, 빈 DB에서 적재 프로그램 전체 경로(스키마 생성·배치 적재·검증)를 처음부터 검증할 수 있기 때문이다.

## 실행 순서

| 단계 | 내용 | 결과 |
|---|---|---|
| 대상 확인 | `db.info()` 이름, 연결 호스트 | DB `6ac1f0f8`, 호스트 `6ac1f0f8.databases.neo4j.io`, Neo4j `5.27-aura` |
| 초기화 전 내보내기(읽기 전용) | 전체 노드·관계·속성, 제약·인덱스 생성문, SHA-256 manifest | `graph-rag-db-backups\neo4j_20261022_pre_reset_full\` (노드 1,456, 관계 11,859) |
| 초기화 | 내보내기 시점 건수와 DB 이름 재확인 → 사용자 생성 제약 11개·일반 인덱스 2개 삭제 → 관계·노드 5,000건 배치 삭제 | 노드 0, 관계 0. Neo4j 기본 LOOKUP 인덱스 2개만 유지 |
| 적재 dry-run | `python -m recipe_recommender.setup.load_recipe_graph` | 사전 점검 통과 |
| 적재 1회차 | `--apply` (내부에서 같은 스냅샷 2회 MERGE 후 검증) | 1·2패스 모두 노드 1,437, 관계 11,584 |
| 적재 2회차(별도 실행) | `--apply` 재실행 | 실행 전 1,437 / 11,584 → 실행 후 1,437 / 11,584 (중복 생성 0) |
| 독립 검증 | `--verify-only` + 읽기 전용 대조 스크립트 | 아래 표 |

삭제한 제약조건: 이전 레시피 모델 5개(`rcp_recipe_composite_key`, `rcp_ingredient_composite_key`, `rcp_ingredient_category_key`,
`rcp_recipe_category_key`, `rcp_recipe_source_seq`), 다른 실습 6개(`article_id`, `case_id`, `law_name`, `movie_title`, `person_name`, `rule_name`).
다른 실습 노드는 초기화 전에도 0개였다. 기존 백업 폴더 2개(`recipe_20261022_pre_target_model`, `neo4j_20261022_legacy_rcp_objects`)는 그대로 보존했다.

## 최종 그래프

| 대상 | 건수 |
|---|---:|
| `RcpRecipe` | 1,156 |
| `RcpIngredient` | 275 (별칭 71개, 별칭 있는 식재료 55개) |
| `RcpRecipeCategory` | 6 |
| `RCP_USES` | 10,428 |
| `RCP_IN_RECIPE_CATEGORY` | 1,156 (현재 레시피당 1개, 다중 분류 구조) |

제약조건 4개: `rcp_recipe_key`(rcp_id), `rcp_ingredient_key`(ingr_id), `rcp_recipe_category_key`(rcp_cat_id), `rcp_recipe_source_seq`(rcp_seq).
인덱스: 제약 소유 RANGE 4개 + `rcp_recipe_name_idx`, `rcp_ingredient_name_norm_idx` + Neo4j 기본 LOOKUP 2개.
실제 구조 상세: `neo4j_actual_schema.json`.

## PostgreSQL 정합성 검증

| 대상 | PostgreSQL | Neo4j | 누락 / 초과 / 중복 |
|---|---:|---:|---|
| 레시피 `rcp_id` | 1,156 | 1,156 | 0 / 0 / 0 |
| 표준 식재료 `ingr_id` | 275 | 275 | 0 / 0 / 0 |
| 요리 분류 `rcp_cat_id` | 6 | 6 | 0 / 0 / 0 |
| `RCP_IN_RECIPE_CATEGORY` ↔ `rcp_cat_rel` | 1,156 | 1,156 | 0 / 0 / 0 |
| `RCP_USES` ↔ `rcp_ingr` | 10,428 | 10,428 | 0 / 0 / 0 |

- 레시피 속성(원본 번호·이름·조리 방법·열량·영양 상태·이미지) 불일치 0, 식재료 이름·별칭·정규화 목록 불일치 0
- 분류 없는 레시피 0, 재료 없는 레시피 8(원천과 동일), 알 수 없는 Rcp 라벨·관계 0, 이전 모델 객체·속성 0
- 대표 레시피 28(재료 7), 298/536(5/17), 788/919(각 9), 칵테일새우(17) 일치, 기존 명명 질의 8개 정상

## Cypher 검색 검증 (적재 후 실제 실행)

| 질문 | 결과 |
|---|---|
| 계란이 들어가는 레시피 | 별칭 `계란` → 표준 `달걀`, **186** |
| 두부가 들어가는 레시피 | **110** (`연두부`는 별도 식재료) |
| 계란과 두부 모두 | **18** |
| 계란·두부·양파 보유 시 추천 | 후보 616, 부족 재료 적은 순 상위 20 (일치·부족 수가 원천과 일치) |
| 반찬 분류 레시피 | **574** |

명명 질의(`recipes_by_ingredient_term`, `recipes_with_all_ingredients`, `pantry_recommendations`, `recipes_in_category`)와
`neo4j_user_verification.md`의 DBeaver용 질의를 모두 실행해 같은 결과를 확인했다.

## 실행 환경 메모

- 이 PC의 Python(uv cpython 3.12)은 OS 인증서 저장소로 AuraDB 인증서 체인을 검증하지 못한다(`CERTIFICATE_VERIFY_FAILED`; openssl 검증은 정상).
  초기화·재적재 당시에는 `SSL_CERT_FILE`을 certifi 번들로 지정해 실행했다.
- 이후 정식 해결: `recipe_recommender/neo4j_connection.py`의 `create_neo4j_driver()`가 `neo4j+s://`를 같은 의미의
  `neo4j://` + `encrypted=True` + `TrustCustomCAs(<CA 번들>)`로 만든다. **인증서 검증은 유지**되고, 검증을 끄는 `+ssc` 스킴은 거부한다.
  CA 번들은 `NEO4J_TRUSTED_CA_FILE`(선택, PEM 경로) 또는 프로젝트 의존성 `certifi`. 적재 CLI와 `tools/check_neo4j_connection.py`가 이 함수를 쓰며,
  `SSL_CERT_FILE` 없이 연결·`--verify-only`가 통과함을 확인했다.
- Neo4j 연결 정보는 저장소 루트 `.env`의 `NEO4J_*`.
