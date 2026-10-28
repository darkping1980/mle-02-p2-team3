# 조리방법 공통코드 체계 전환 실행 기록 (2026-10-23)

## 결론

`COOK_MTHD` 공통코드의 코드와 명칭을 분리했다. 이전에는 식약처 원본 `RCP_WAY2`(한글)를 `common_cd`·`common_cd_nm`·
`rcp.cook_mthd_cd`에 그대로 저장했다. 이제 코드는 6자리 문자열이고, 명칭은 `common_cd_nm`에만 있다.
PK·관계·다른 공통코드 그룹·테이블 구조는 바꾸지 않았다(컬럼은 `varchar(20)` 유지).

| 이전 `common_cd` (= 명칭) | 현재 `common_cd` | `common_cd_nm` | 레시피 수 |
|---|---|---|---:|
| 굽기 | `000001` | 굽기 | 259 |
| 끓이기 | `000002` | 끓이기 | 326 |
| 볶기 | `000003` | 볶기 | 108 |
| 찌기 | `000004` | 찌기 | 82 |
| 튀기기 | `000005` | 튀기기 | 71 |
| 기타 | `000006` | 기타 | 310 |

합계 1,156건. 등록 규칙은 `recipe_table_definition.md`의 "공통코드 등록 규칙"을 따른다.

## ETL 변경

- 확정 코드표 `recipe_recommender/data/cook_mthd_cd_seed.csv`를 추가했다. 적재기는 이 코드표만 `common_cd`에 등록한다.
  CSV 값으로 코드를 만들던 로직(코드값 = 명칭)은 제거했다.
- `RCP_WAY2`는 `common_cd_nm`으로 코드를 찾아 `rcp.cook_mthd_cd`에 저장한다. 코드표에 없는 명칭은 검증 오류다.
- DB 코드가 코드표와 다른 명칭이거나, 6자리 형식이 아니거나(이전 한글 코드), 한 명칭이 두 코드에 걸리면 쓰기 전에 중단한다.
  전환 전 DB에서 새 적재기 dry-run이 이 검사로 중단되는 것을 확인했다.
- 정합성 검사에 `invalid_cook_method_code`를 추가했다. 그래프 적재기는 6자리가 아닌 `cook_mthd_cd`를 거부한다.
- 레시피 조회의 조리 방법 조건이 코드와 명칭을 모두 받는다. 목록 결과에 `cook_mthd_nm`을 추가했다.

## 실행 순서

1. 조사: `COOK_MTHD` 6개 모두 코드 = 명칭, 레시피 1,156건, 원본 `RCP_WAY2`와 `cook_mthd_cd` 1:1 일치. FK·트리거·뷰 참조 없음.
2. 백업: `C:\Users\Playdata\recipe-cook-mthd-backup-20261023\before\cook_mthd_backup.json`
   (`common_code_grp`, `common_cd`, `rcp` 전체 행·전체 컬럼, Neo4j `rcp` 조리방법 속성 1,156개, 노드·관계 수).
   복원 `restore_cook_mthd.py`, 전환 `migrate_cook_mthd.py`.
3. 전환 리허설: 같은 트랜잭션 안에서 실행·검증한 뒤 ROLLBACK.
4. 전환 적용(단일 트랜잭션): `common_cd` PK를 제자리 UPDATE(6행), `rcp.cook_mthd_cd` 변환(1,156행). 트랜잭션 안에서
   백업과 행 단위 대조를 통과한 뒤 COMMIT했다.
5. 복구 경로 확인: 적용 후 `restore_cook_mthd.py --rehearse` 결과가 백업과 행 단위로 일치했고, 그 뒤 ROLLBACK했다.
6. Neo4j 동기화: `load_recipe_graph --apply`(같은 스냅샷으로 MERGE·SET 2회). 바뀐 속성은 `rcp.cook_mthd_cd` 1,156개뿐이다.

생성·수정 이력 컬럼(`create_date`, `create_user_id`, `update_date`, `update_user_id`)은 `common_cd`·`rcp` 모두 바꾸지 않았다.
의미가 같은 표현 전환이라 이력을 덮어쓰지 않았고, 근거는 이 기록과 백업에 남겼다.

## 검증

| 항목 | 결과 |
|---|---|
| 코드 매핑 | 6개 명칭 → `000001`~`000006` 정확히 일치 |
| 의미 보존 | `rcp_raw.rcp_way2` = 코드명 1,156 / 1,156 |
| 유효하지 않은 코드 | 참조 누락 0, 6자리 형식 위반 0, 다른 그룹 변경 0 |
| 업무 ID·이력 | `rcp` 1,156행의 `cook_mthd_cd` 외 모든 컬럼이 백업과 같음. `common_cd`의 명칭·생성·수정 이력도 같음 |
| CSV 반복 적재 | `register_recipe_csv --full`: 같은 회차 재실행, 신규 0·갱신 0·공통코드 등록 0, 정합성 OK. 실행 전후 행이 같음(한글로 되돌아가지 않음) |
| Neo4j | `cook_mthd_cd`·`cook_mthd_nm`이 PostgreSQL과 1,156 / 1,156 일치. 노드 1,437·관계 11,584, elementId·라벨·관계·제약·인덱스 그대로 |
| 조회 | `--cook-method 찌기`와 `--cook-method 000004` 모두 82건. GraphRAG 컨텍스트 등 명명 Cypher 질의 검증 통과 |
| 테스트 | `recipe_recommender/tests` 115개 통과 |

## 되돌리기

1. `python restore_cook_mthd.py before\cook_mthd_backup.json --apply`: PostgreSQL을 백업 상태로 되돌리고 행 단위로 대조한 뒤 COMMIT.
2. Neo4j: `python -m recipe_recommender.setup.load_recipe_graph --apply`로 PostgreSQL 값에 다시 맞춘다.
3. 단, 되돌린 DB에서 새 적재기는 한글 코드를 거부한다. 코드도 이 변경 이전 커밋으로 함께 되돌려야 한다.
