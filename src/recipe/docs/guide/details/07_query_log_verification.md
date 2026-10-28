# PostgreSQL · Neo4j 쿼리 로그 검증 보고서

[메인](../README.md) · [Neo4j Repository](04_neo4j_repository.md) · API: [query_logger](../api/common/query_logger.md), [postgres_db_session](../api/common/postgres_db_session.md), [neo4j_db_session](../api/common/neo4j_db_session.md)

검증일 2026-10-24. 대상: [common/query_logger.py](../../../common/query_logger.py), [common/postgres_db_session.py](../../../common/postgres_db_session.py), [common/neo4j_db_session.py](../../../common/neo4j_db_session.py).
목적: 로그에 찍힌 SQL/Cypher를 복사해 DB 도구에서 실행하면 프로그램 결과와 같은지 확인한다.

## 1. 결론

| 항목 | 결과 |
| --- | --- |
| PostgreSQL `combined` 로그(`ClientCursor.mogrify()`) 복사 재실행 | **성공** — 실제 mapper SELECT 7건 모두 프로그램 결과와 같음 |
| PostgreSQL 타입별 렌더링(타입이 정해진 문맥) | 21종 모두 바인딩 실행 결과와 같음 |
| Neo4j `:param` 로그 복사 재실행(드라이버) | **성공** — 실제 mapper 쿼리 10건 모두 `:param` 식 평가값 = 원본 파라미터, 재실행 결과 = 프로그램 결과(순서까지) |
| Neo4j 실제 쿼리 도구(`cypher-shell` 2026.06.0) | **성공** — 로그 텍스트를 그대로 저장한 파일 10개를 `-f`로 실행, 행 수·첫 행이 프로그램 결과와 같음. `:param` 리터럴 39종을 바인딩과 같은 `valueType`으로 해석 |
| Neo4j 타입별 리터럴 | 42종 중 40종 값·타입 일치, 2종(숫자 32개 이상 목록, bytes)은 의도대로 "재현 불가" 주석 |
| 모드 combined / separate / none | 문서화된 동작과 같음(아래 4절) |
| 원본 파라미터 불변 | 모든 실행에서 실행 전 deepcopy와 같음 |
| 로그 실패 격리 | 렌더링 강제 실패 시 경고 1줄 + 원문 대체, 조회 결과 동일 |
| 민감정보 마스킹 | **문제 1건 발견·수정**: 기본 목록이 `api_token` 등을 가리지 못함 → 목록에 키 6개 추가 |
| 인라인 파라미터 렌더링(Neo4j) | 처음에는 도입하지 않았으나(6절), 추가 요구에 따라 **Cypher 전용 스캐너로 구현**하고 안전하지 않으면 `:param`으로 대체(11절) |

## 2. 검증 방법

- **운영 DB는 읽기 전용으로만** 사용했다. PostgreSQL은 `BEGIN TRANSACTION READ ONLY` 연결에서 복사한 SQL을 실행했고, Neo4j AuraDB는 `READ_ACCESS` 세션과 `cypher-shell --access-mode read`로만 실행했다. INSERT·UPDATE·DELETE·CREATE·MERGE는 운영 DB에서 실행하지 않았다.
- 타입 행렬 중 Neo4j 부분은 로컬 테스트 Neo4j Community 2026.06.0(127.0.0.1, 읽기 쿼리만)에서 실행했다.
- 로그는 실제 세션 코드로 만들었다: PostgreSQL `create_recipe_sql_session(sql_log=True)`(combined), Neo4j `RecipeGraphRepository().mapper`의 `cypher_log_mode`를 검증 스크립트 안에서만 `combined`로 바꿨다(소스의 기본값 `none`은 그대로).
- 복사·재실행 절차: 로그의 구분선(`=====`) 사이 본문을 그대로 꺼냄 → PostgreSQL은 파라미터 없이 실행, Neo4j는 `:param` 줄의 식을 `RETURN 식`으로 평가한 값으로 본문을 실행(드라이버) / 본문 전체를 파일로 저장해 `cypher-shell -f`로 실행(도구).
- 검증 스크립트는 저장소에 넣지 않았다(접속이 필요한 일회성 점검). 재현 가능한 부분은 단위 테스트로 남겼다(7절).
- DBeaver·Neo4j Browser GUI와 psql은 이 PC에서 실행하지 못했다. PostgreSQL 복사 실행은 psycopg로 SQL 텍스트를 파라미터 없이 그대로 보내는 방식(도구가 텍스트를 보내는 것과 같은 경로)으로 확인했다.

## 3. PostgreSQL

### 3-1. 렌더링 방식

`select_list`·`execute`는 `QueryLogger.log_query`에 `render_combined` 콜백을 넘기고, combined 모드에서만 `psycopg.ClientCursor(connection).mogrify(sql, params)`로 값이 채워진 SQL을 만든다. 실행은 별도로 aiosql 함수가 원본 파라미터로 서버 바인딩한다(로그 문자열을 실행하지 않음).
`select_list`는 `full_vector_sql=True`라 원본 파라미터(민감 키만 가린 복사본)로 렌더링하고, `execute`는 sanitize된 로그용 복사본(벡터는 미리보기)으로 렌더링한다. 렌더링 SQL 아래에 `PARAMS` 줄(sanitize된 값의 repr)을 붙인다.

### 3-2. 실제 출력 로그 예시 (`recipe.list_recipes`, 민감정보 없음)

```text
QUERY [recipe.list_recipes]
========================================================================
SELECT
    r.rcp_id,
    ...
FROM recipe.rcp AS r
WHERE (CAST('두부' AS text) IS NULL OR strpos(lower(r.rcp_nm), lower('두부')) > 0)
  AND (CAST(NULL AS text) IS NULL OR EXISTS (
        ...
          AND c.rcp_cat_nm = NULL))
  AND (CAST('찌기' AS text) IS NULL OR r.cook_mthd_cd = '찌기' OR EXISTS (
        ...
          AND cd.common_cd_nm = '찌기'))
ORDER BY r.rcp_nm, length(r.rcp_seq), r.rcp_seq
LIMIT 20 OFFSET 0;
========================================================================
PARAMS {'RCP_NM': '두부', 'RCP_CAT_NM': None, 'COOK_MTHD_CD': '찌기', 'LIMIT': 20, 'OFFSET': 0}
RESULT [recipe.list_recipes] rows=10 connect_ms=... sql_log_ms=... query_fetch_ms=... total_ms=...
```

### 3-3. 실제 mapper SELECT 복사 재실행

| statement | 파라미터 특징 | 프로그램 행 | 복사 SQL 행 | 결과 동일 |
| --- | --- | ---: | ---: | --- |
| `recipe.list_recipes` | 한글, NULL, 코드명, LIMIT/OFFSET | 10 | 10 | 예 |
| `recipe.list_recipes` | 분류명 `국&찌개`, OFFSET 10 | 5 | 5 | 예 |
| `recipe.count_recipes` | 한글, 6자리 코드 문자열 | 1 | 1 | 예 |
| `recipe.find_recipe_detail` | 문자열 + NULL | 1 | 1 | 예 |
| `recipe.find_ingredient_by_name` | 별칭 `계란` | 1 | 1 | 예 |
| `recipe.list_recipes` | 작은따옴표 `O'Brien` → `'O''Brien'` | 0 | 0 | 예 |
| `recipe.list_recipes_by_ingredient` | 식재료 ID, LIMIT | 7 | 7 | 예 |

모든 경우 렌더링 SQL에 `%(...)s`가 남지 않았고, 원본 파라미터 dict는 실행 전과 같았다.

### 3-4. 타입별 렌더링 (타입이 정해진 문맥: CAST, 컬럼 비교, LIMIT)

| 타입 | 렌더링 예 | 바인딩 결과와 동일 |
| --- | --- | --- |
| 한글 · 이모지 · 빈 문자열 | `'된장 두부찌개'`, `'두부🍲'`, `''` | 예 |
| 작은따옴표 · 큰따옴표 | `'O''Brien''s "quoted"'` | 예 |
| 역슬래시 | `E'C:\\path\\x'` | 예 |
| 줄바꿈 · 탭 | 리터럴 안에 실제 줄바꿈 | 예 |
| `%` · `:` 포함 문자열 | `'100% 두부'`, `'a:b ::c :RCP_ID'` | 예 |
| NULL(text / integer 문맥) | `NULL` | 예 |
| 문자열 배열(따옴표·NULL·쉼표·중괄호 포함) | `'{두부,O''Brien,NULL,"a,b","{x}"}'` | 예 |
| 빈 배열 | `'{}'` | 예 |
| float(컬럼 비교) · float(CAST) | `3.14159`, `0.1` | 예 |
| numeric(Decimal) | `277.10` | 예 |
| 정수(LIMIT) | `3` | 예 |
| Jsonb(한글·따옴표 포함) | `E'{"\\uc774...": ...}'::jsonb` | 예 |
| pgvector `Vector`(`select_list` 경로) | `'[0.10000000149011612,...]'::vector` | 예 |

추가로 확인한 타입(타입 미지정 문맥 `SELECT %(v)s`): bool, date, timestamp, timestamptz, time, interval, uuid, bytea, int 배열, NaN/Infinity는 값과 PostgreSQL 타입까지 같았다.

## 4. 모드별 출력

| 모드 | PostgreSQL `select_list` | PostgreSQL `execute` | Neo4j `select_list`·`execute` |
| --- | --- | --- | --- |
| `combined` | 렌더링 SQL + `PARAMS` + `RESULT` | 렌더링 SQL + `PARAMS` + `DONE` | `:param` 줄 + Cypher + `RESULT`/`DONE` (`PARAMS` 줄 없음) |
| `separate` | 원문 SQL(`%(NAME)s`) + `PARAMS` | 원문 SQL + `PARAMS` | 원문 Cypher(`$name`) + `PARAMS` |
| `none` | `RESULT` 요약만 | **QUERY를 combined로 강제 출력** + `DONE` | `RESULT`/`DONE` 요약만 |

배치(`execute_many`)는 두 DB 모두 원문 쿼리와 앞 100건 파라미터 repr(`BATCH QUERY`)만 출력한다. PostgreSQL 배치는 `none`에서도 출력한다. 배치 로그는 렌더링하지 않으므로 그대로 복사 실행할 수 없다(쓰기 쿼리이기도 해 운영 DB에서 재실행하지 않았다).

앱의 기본값: 환경변수 `RECIPE_QUERY_LOG`가 없으면 Neo4j 세션은 `cypher_log_mode="none"`, PostgreSQL 세션은 `none`이고 INFO 출력 handler도 붙지 않는다. 등록 CLI는 `--sql-log`가 없으면 SQL logger를 WARNING으로 올린다. 즉 운영 화면(Streamlit Cloud)은 쿼리 본문을 로그에 남기지 않는다. 로컬에서 켜는 방법은 10절.

## 5. Neo4j

### 5-1. 렌더링 방식

`render_cypher_params()`가 파라미터마다 `:param 이름 => Cypher 리터럴;` 줄을 만들고 빈 줄 뒤에 원문 Cypher를 붙인다(로그 전용, 드라이버 기능이 아님). 실제 실행은 `runner.run(query, bound_parameters)`로 원본 값의 복사 dict를 바인딩한다. 정확한 리터럴이 없는 값은 `// :param 이름 => 미리보기; (not reproducible as a literal)` 주석 줄이 된다. 민감 키는 `QueryLogger.mask()`로 먼저 가린다.

### 5-2. 실제 출력 로그 예시

```text
QUERY [recipe_graph_queries.find_recipe_by_name]
========================================================================
:param rcp_nm => 'O\'Brien "두부" \\ 테스트';

// $rcp_nm 예: 사용자가 입력한 레시피 이름
MATCH (r:rcp {rcp_nm: $rcp_nm})
RETURN r.rcp_id AS rcp_id, r.rcp_seq AS rcp_seq, r.rcp_nm AS rcp_nm
ORDER BY r.rcp_id;
========================================================================
RESULT [recipe_graph_queries.find_recipe_by_name] rows=0 counters={} session_ms=... cypher_log_ms=... query_fetch_ms=...
```

### 5-3. 실제 mapper 쿼리 복사 재실행 (운영 AuraDB, 읽기 전용)

| statement | `:param` 줄 | 프로그램 행 | 드라이버 재실행 | cypher-shell |
| --- | --- | ---: | --- | --- |
| `recipe_graph_queries.ingredient_name_candidates` | `term_norm => '계란'` | 1 | 같음 | 1행, 같음 |
| `recipe_graph_queries.recipes_by_ingredient_term` | `term_norm => '두부'` | 110 | 같음 | 110행 |
| `recipe_graph_queries.similar_recipes` | `rcp_id => '20261022_000020'` | 20 | 같음 | 20행 |
| `recipe_graph_queries.recipe_steps` | `rcp_ids => ['20261022_000020']` | 3 | 같음 | 3행 |
| `recipe_graph_queries.recipes_with_all_ingredients` | `terms_norm => ['계란', '두부']` | 18 | 같음 | 18행 |
| `recipe_graph_queries.recipes_using_ingredient` | `ingr_id => '...'`, `exclude_rcp_id => null` | 30 | 같음 | 30행 |
| `pantry_graphrag.pantry_recommendations_by_coverage` | 목록 + `limit => 20` | 20 | 같음 | 20행(1행 두부해물완자) |
| `graph_questions.similar_recipe_categories` | `rcp_id`, `min_common => 3` | 5 | 같음 | 5행(1행 국&찌개 26) |
| `graph_questions.category_ingredients` | `rcp_cat_nm => '반찬'`, `limit => 10` | 10 | 같음 | 10행(1행 양파 227) |
| `recipe_graph_queries.find_recipe_by_name` | 따옴표·큰따옴표·역슬래시 | 0 | 같음 | 0행 |

"같음"은 `:param` 식을 READ 세션에서 평가한 값이 원본 파라미터와 같고, 본문 재실행 결과가 프로그램 결과와 행 순서까지 같다는 뜻이다. `cypher-shell`은 `-a <URI> -u <user> -d <db> --access-mode read --format plain -f <로그 파일>`로 실행했다(접속 정보는 환경변수로만 전달).
`cypher-shell` 2026.06.0은 `:param 이름 => 식;`을 받아 내부적으로 `RETURN {이름: 식}`으로 평가한다.

### 5-4. 타입별 리터럴 (로컬 테스트 DB, `RETURN $v` 바인딩 vs `RETURN <리터럴>`)

| 타입 | `:param` 리터럴 | 값·`valueType` 일치 |
| --- | --- | --- |
| 한글 · 이모지 · 빈 문자열 | `'된장 두부찌개'`, `'두부🍲'`, `''` | 예 |
| 작은따옴표 · 큰따옴표 · 역슬래시 | `'O\'Brien'`, `'say "두부"'`, `'C:\\path\\x'` | 예 |
| 줄바꿈·탭·CR · 제어 문자 | `'a\nb\tc\rd'`, `'x\u0001y\u001fz'` | 예 |
| `$`·중괄호·백틱이 든 문자열 | `'$term {x} \`y\`'` | 예 |
| null · true · false | `null`, `true`, `false` | 예 |
| 정수(음수, int64 최대) | `-7`, `9223372036854775807` | 예 |
| 실수(작은 값, 큰 값, -0.0) | `1e-12`, `1.5e300`, `-0.0` | 예 |
| NaN · ±Infinity | `0.0 / 0.0`, `1.0 / 0.0`, `-1.0 / 0.0` | 예 |
| 혼합 목록 · 빈 목록 · 중첩 목록 · tuple | `[1, '두부', null, true, 2.5]`, `[]` | 예 |
| map(한글 키) · 특수 키 · map 목록 | ``{`이름`: '두부', ...}``, ``{`a b`: 1, `x``y`: 2}`` | 예 |
| date · localdatetime · datetime(오프셋) · localtime | `date('2026-10-24')` 등 | 예 |
| `timedelta` · 드라이버 `Duration` | `duration({days: 1, seconds: 3600, microseconds: 5})`, `duration('P1M2DT3.000000004S')` | 예 |
| 나노초 `DateTime` | `localdatetime('2026-10-24T09:30:01.123456789')` | 예 |
| Point(WGS84, Cartesian 3D) | `point({srid: 4326, x: 126.97, y: 37.56})` | 예 |
| 숫자 31개 목록 | 그대로 나열 | 예 |
| 숫자 32개 이상 목록 | `// :param v => <VECTOR [...] dimension=32>; (not reproducible...)` | **재현 불가(의도)** |
| bytes | `// :param v => b'\x00\x01'; (not reproducible...)` | **재현 불가(의도)** |
| 이름 있는 시간대(`ZoneInfo("Asia/Seoul")`) | `datetime('2026-10-24T09:30:00+09:00')` | 값·타입 같음(아래 제한 참고) |

`cypher-shell`로 같은 리터럴 39종(숫자 31개 목록 제외)을 `:param`으로 넣고 `valueType($v)`를 출력하면 드라이버 바인딩 타입과 모두 같았다.

## 6. 인라인 파라미터 렌더링 검토 (Neo4j)

처음 검증(1~9절 작성 시점)에서는 `$name` 치환에 Cypher 어휘 분석이 필요하고 모든 타입의 리터럴을 보장할 수 없다는 이유로 도입하지 않았다.
이후 "쿼리 하나만 복사해 실행" 요구가 확정되어, 정규식 치환이 아닌 **Cypher 전용 스캐너**와 기존 `_cypher_literal`로 구현했다.
안전하게 만들 수 없는 경우(리터럴 없는 값, 마스킹, 해석 실패, 누락 파라미터)는 인라인을 만들지 않고 기존 `:param` 방식으로 대체한다. 상세는 11절.

## 7. 발견한 문제와 수정

| # | 내용 | 영향 | 조치 |
| --- | --- | --- | --- |
| 1 | 기본 마스킹 목록(`DEFAULT_SENSITIVE_KEYS`)이 `api_token`·`session_token`·`id_token`·`secret_key`·`aws_secret_access_key`·`passphrase`를 가리지 못함. `token`(5자)은 접미사 규칙(6자 이상) 대상이 아니라 완전 일치만 검사하기 때문. 검증 중 `api_token` 값이 Neo4j `:param` 줄에 그대로 출력됨 | 현재 앱 쿼리에는 이런 키가 없음(잠재 위험). Neo4j는 기본 마스킹이 켜져 있고 PostgreSQL은 opt-in | [query_logger.py](../../../common/query_logger.py) 목록에 키 6개 추가(판정 규칙·다른 코드 변경 없음). 재검증: `:param api_token => '<MASKED>';`, 비밀값 노출 0 |
| 2 | 공통 로그 테스트 [test_query_logger.py](../../../common/tests/test_query_logger.py)가 `from pgvector.utils import Vector`로 import 실패 → 51건이 실행되지 않고 있었음(설치된 pgvector 0.5.1에는 `utils` 모듈 없음, 소스는 `from pgvector import Vector`) | 로그 회귀 테스트가 돌지 않음 | 테스트 import 한 줄을 소스와 같은 경로로 수정 |

추가 테스트 `SensitiveKeyCoverageTests` 3건: 흔한 자격증명 키 마스킹, 일반 키(`token_count`, `tokenizer`, `term_norm` 등) 비마스킹, `api_token`이 `:param` 줄에 나오지 않고 원본 파라미터가 그대로인지.

## 8. 테스트 결과

| 묶음 | 결과 |
| --- | --- |
| `common/tests` (`python -m unittest discover -s common/tests -t .`) | **65 통과 / 0 실패** (기존 62 + 신규 3. 수정 전에는 import 오류로 11건만 실행) |
| `recipe_recommender/tests` (DB INSERT 테스트 2건 제외 정책) | **190 통과 / 0 실패 / 0 건너뜀** |
| 실제 DB 재현(검증 스크립트) | PostgreSQL mapper 7/7, 타입 21/21(+ 미지정 문맥 10종) · Neo4j mapper 10/10(드라이버), 10/10(cypher-shell), 타입 40/42(2종 의도된 재현 불가), cypher-shell 타입 39/39 |

## 9. 재현할 수 없는 경우와 제한 사항

- **PostgreSQL**
  - `execute`·배치 경로의 pgvector 값은 `<VECTOR [...] dimension=N>` 미리보기로 렌더링되어 그대로 실행하면 형식 오류가 난다(조회 `select_list`는 전체 벡터를 렌더링).
  - 마스킹을 켠 경우 가린 값은 `'<MASKED>'`로 렌더링된다(의도된 차이).
  - Python float는 `3.14159`처럼 numeric 리터럴로, 작은 정수는 integer 리터럴로 렌더링된다. 타입이 정해진 문맥(컬럼 비교, CAST, LIMIT)에서는 결과가 같지만, `SELECT %(v)s`처럼 타입이 없는 문맥에서는 `pg_typeof`가 바인딩(double precision·smallint)과 다르다.
  - `Jsonb`로 감싸지 않은 dict 등 psycopg가 적응하지 못하는 값은 렌더링이 실패한다 → `SQL 로그 렌더링 실패` 경고와 원문 SQL·`PARAMS`로 대체(이 값은 실제 실행도 실패한다).
  - 배치 로그(`BATCH QUERY`)는 렌더링하지 않는다.
  - DBeaver는 SQL 편집기에서 `:이름`을 파라미터로 인식할 수 있다. 렌더링 SQL에서 `:`는 문자열 리터럴 안에만 나오지만, DBeaver에서의 실제 동작은 확인하지 못했다.
- **Neo4j**
  - bytes, 숫자 32개 이상 목록(벡터로 간주), 알 수 없는 객체, srid 없는 Point는 주석 줄(재현 불가)로 남는다. 숫자 ID 목록이 32개 이상이어도 벡터로 간주된다.
  - 이름 있는 시간대(`Asia/Seoul`)는 오프셋(`+09:00`)으로 렌더링된다. `valueType`과 `=` 비교는 같았지만 시간대 ID 자체는 보존되지 않는다.
  - 마스킹된 값은 `'<MASKED>'`가 되어 다른 결과가 나온다(의도).
  - `collect()` 결과 목록의 원소 순서는 실행마다 다를 수 있다(로그와 무관한 Cypher 특성).
  - `:param 이름 => 식;` 구문은 `cypher-shell` 2026.06.0에서 확인했다. Neo4j Browser·Aura Query 화면·DBeaver Cypher 편집기에서는 실행해 보지 못했다.
  - 배치 로그(`BATCH QUERY`)는 `:param`으로 렌더링하지 않는다.
- **공통**: 로그는 `car_search_rag.sql` / `car_search_rag.neo4j` logger의 INFO 레벨에서만 만들어진다. 레벨이 꺼져 있으면 렌더링 자체를 하지 않는다.

## 10. 로컬 개발 터미널 로그 (`RECIPE_QUERY_LOG`)

2026-10-24 추가. 로컬에서 Streamlit 앱을 실행하고 버튼을 누르면 실행한 터미널(VS Code Terminal)에 실제 Cypher와 바인딩 값이 출력되게 했다. 기존 `QueryLogger`·DB 실행 방식은 바꾸지 않고 로깅 설정만 더했다.

- `cypher_log_mode="none"`이었던 이유: 2026-10-22 그래프 적재 구현(`e7dfc2e`) 때 들어갔고 커밋·문서에 이유는 남아 있지 않다. 당시 이 Repository는 적재 CLI 전용이었고 적재 쿼리의 `$rows`(배치당 최대 1,000행)가 `combined` 로그로 매우 길게 찍히기 때문으로 **추정**한다. 이후 Streamlit이 같은 Repository를 재사용하면서 화면 쪽 로그도 꺼진 상태가 되었다.
- 스위치: [config.py](../../../recipe_recommender/config.py)의 `query_log_enabled(default)`(환경변수 `RECIPE_QUERY_LOG`에 값이 있으면 그 값 — `1`·`true`·`yes`·`on`만 켜짐 —, 없으면 `default`) / `configure_query_logging(default)`(켜질 때만 `car_search_rag.neo4j`·`car_search_rag.sql` logger를 INFO + stderr handler 1개, 중복 방지).
- 기본값(11절 추가 요구 반영): Streamlit 앱은 `default=local_dev_query_log_default()` = 소스 설정값 `LOCAL_DEV_QUERY_LOG_DEFAULT = True` **그리고** 저장소 루트 `.env` 존재. 로컬 개발 PC에서는 일반 `python -m streamlit run .\streamlit_app.py`만으로 켜지고, `.env`가 없는(`.gitignore` 대상) Streamlit Cloud에서는 꺼진다. CLI는 기본 꺼짐(환경변수로만 켬).
- 적용 위치: `streamlit_app.py` 시작, `RecipeGraphRepository.__init__`(켜지면 `cypher_log_mode="combined"`), `create_recipe_sql_session(sql_log=None)`(켜지면 `sql_log_mode="combined"`, 명시값 우선).
- 화면: 모드 B의 "실행 Cypher와 파라미터" 펼침 영역을 없앴다. 관계 경로·hop·결과 표는 그대로다. 과제용 Cypher는 [docs/assignment](../../assignment/README.md) 문서와 노트북에 있다.
- 운영: Streamlit Cloud에는 `.env`가 없어 기본 꺼짐이다. Secrets에 `RECIPE_QUERY_LOG`를 넣지 않는다(Streamlit은 최상위 Secrets를 환경변수로도 노출하므로 넣으면 켜진다).
- 모드 A의 추천 자체는 Neo4j 결과를 사용한다. 로그 ON에서는 첫 추천 레시피의 PostgreSQL 상세를 추가 SELECT하여 SQL 4개를 같은 터미널에 남기되 화면에는 사용하지 않는다. 로그 OFF의 모드 A와 모드 B는 이 추가 조회를 하지 않는다.
- 로그 모드는 Repository를 만들 때 정해진다(`st.cache_resource`). 스위치를 바꾸면 Streamlit을 다시 시작한다.
- 켜 둔 채 그래프 적재 CLI(`load_recipe_graph --apply`)를 실행하면 `$rows` 전체가 `:param` 줄로 출력되므로 적재할 때는 끈다.

### 10-1. 실행 방법 (과제 폴더에서)

```powershell
# 로컬 개발 PC(저장소 루트 .env 있음): 아무 설정 없이 실행하면 터미널 로그가 켜진다
python -m streamlit run .\streamlit_app.py

# 로컬에서 끄기 / 강제로 켜기
$env:RECIPE_QUERY_LOG = "0"      # 끄기
$env:RECIPE_QUERY_LOG = "1"      # 켜기(CLI도 출력)
Remove-Item Env:RECIPE_QUERY_LOG # 소스 기본값으로 돌아감
```

소스에서 로컬 기본값을 끄려면 `config.LOCAL_DEV_QUERY_LOG_DEFAULT = False`. 저장소 루트 `.env`에 `RECIPE_QUERY_LOG=0` 또는 `1`을 넣어도 된다(이미 설정된 프로세스 환경변수가 우선). PostgreSQL 예: `$env:RECIPE_QUERY_LOG="1"; python -m recipe_recommender.search_recipe --name 두부 --and-cook-method 찌기 --page-size 3`.

### 10-2. 통합 검증 (2026-10-24, 실제 AuraDB 읽기, LLM 미사용)

실제 `streamlit_app.py`를 AppTest로 실행해 모드 A **레시피 추천** 버튼, 모드 B **그래프 조회** 버튼(Q1·Q3·Q5)을 눌렀다. 프로세스의 stderr(터미널)를 캡처했다.

| 조건 | 모드 A 추천 클릭 | 모드 B 조회 클릭 | 터미널의 `QUERY` 블록 |
| --- | --- | --- | --- |
| 환경변수 없음 + 로컬 `.env`(현재 기본) | 추천 시 Neo4j 10개와 PostgreSQL 4개 | Q1·Q3·Q5 조회 시 Neo4j 5개 | Neo4j 15개 + PostgreSQL 4개 |
| `RECIPE_QUERY_LOG=0` | 같은 결과 | 같은 결과 | **0개** |
| `RECIPE_QUERY_LOG=1` | `ingredient_name_candidates` ×3 → `pantry_recommendations_by_coverage` → `graphrag_context` ×5 → `recipe_steps`(Neo4j 10개), 이후 PostgreSQL 상세 SELECT 4개 | Q1 `ingredient_name_candidates`·`recipes_by_ingredient_term` / Q3 `recipe_options`·`similar_recipe_categories` / Q5 `recipe_steps`(Neo4j 5개) | Neo4j 15개 + PostgreSQL 4개 |
| 미설정(10절 작성 시점, 로컬 기본값 도입 전) | 같은 결과(추천 5건) | 같은 결과(110 / 5 / 3행) | **0개** |

화면에는 두 경우 모두 "실행 Cypher와 파라미터" 영역이 없었다. PostgreSQL: `search_recipe --name 두부 --and-cook-method 찌기` 실행 시 켜면 `QUERY` 2개(`count_recipes`, `list_recipes`, 값이 채워진 SQL), 끄면 0개.

### 10-3. 실제 터미널 로그 예시

모드 B Q1(두부) 조회 버튼(10절 작성 시점의 `:param` 형식 — 11절 이후에는 인라인 형식으로 출력):

```text
2026-10-24 20:44:45,652 INFO car_search_rag.neo4j QUERY [recipe_graph_queries.recipes_by_ingredient_term]
========================================================================
:param term_norm => '두부';

// '계란이 들어가는 레시피는?' — 입력어($term_norm, 양끝 공백 제거·소문자화)를 표준명 또는 별칭으로 해석한다.
// 별칭 '계란'은 표준 식재료 '달걀'로 매핑된다. 유사 이름(두부/연두부)은 합치지 않는다.
MATCH (i:ingr)
WHERE i.ingr_nm_norm = $term_norm OR $term_norm IN coalesce(i.alias_names_norm, [])
MATCH (r:rcp)-[:RCP_USES]->(i)
RETURN i.ingr_id AS ingr_id, i.ingr_nm AS ingredient,
       r.rcp_id AS rcp_id, r.rcp_seq AS rcp_seq, r.rcp_nm AS rcp_nm
ORDER BY r.rcp_nm, r.rcp_id;
========================================================================
2026-10-24 20:44:45,861 INFO car_search_rag.neo4j RESULT [recipe_graph_queries.recipes_by_ingredient_term] rows=110 counters={} session_ms=0.0 cypher_log_ms=0.1 query_fetch_ms=208.9 total_ms=209.8 server_available_after_ms=0 server_consumed_after_ms=1
```

PostgreSQL(`search_recipe`, 값이 채워진 SQL — 일부 줄 생략):

```text
2026-10-24 20:45:18,408 INFO car_search_rag.sql QUERY [recipe.list_recipes]
========================================================================
SELECT
    ...
WHERE (CAST('두부' AS text) IS NULL OR strpos(lower(r.rcp_nm), lower('두부')) > 0)
    ...
ORDER BY r.rcp_nm, length(r.rcp_seq), r.rcp_seq
LIMIT 3 OFFSET 0;
========================================================================
PARAMS {'RCP_NM': '두부', 'RCP_CAT_NM': None, 'COOK_MTHD_CD': '찌기', 'LIMIT': 3, 'OFFSET': 0}
2026-10-24 20:45:18,638 INFO car_search_rag.sql RESULT [recipe.list_recipes] rows=3 connect_ms=0.0 sql_log_ms=0.3 query_fetch_ms=172.0 total_ms=230.0
```

로그 블록의 구분선 사이 텍스트를 그대로 복사해 `cypher-shell -f` 또는 PostgreSQL 클라이언트에서 실행할 수 있다(5-3·3-3절에서 같은 형식으로 재현 확인).

### 10-4. 테스트

[test_query_log_config.py](../../../recipe_recommender/tests/test_query_log_config.py) 7건: 기본 꺼짐, 켜기/끄기 값, logger 설정 멱등성(handler 1개·INFO·전파 없음), Neo4j/PostgreSQL 세션 모드 선택(PostgreSQL 명시값 우선) — Mock 5건. 실제 앱 버튼 클릭 시 켜면 모드 A·B Cypher가 `:param` 줄과 함께 기록되고 끄면 기록되지 않음 — 실제 AuraDB 2건.

## 11. DB별 파라미터 렌더링 분리 (추가 요구, 2026-10-24)

### 11-1. 구조

| 구분 | 담당 | 파라미터 문법 | 렌더링 방법 |
| --- | --- | --- | --- |
| 공통 | `QueryLogger.log_query(..., render_combined=콜백)` | — | 모드 판단, 로그 형식, 실패 격리, 마스킹·sanitize 복사본. DB 문법은 모른다 |
| PostgreSQL | `PostgresDbSession._log_query` | mapper `:NAME` → aiosql이 `%(NAME)s`로 변환(실행과 같은 SQL) | **기존 그대로** psycopg `ClientCursor.mogrify()`. 마스킹·벡터 미리보기처럼 실행 값과 다를 때만 `-- NOT REPRODUCIBLE AS-IS: ...` 주석 추가(`_render_notes`) |
| Neo4j | `Neo4jDbSession._log_query` → `render_cypher_log` | `$name`, `$`이름``, `$0` | Cypher 전용 스캐너 `_cypher_parameter_tokens` + 기존 `_cypher_literal`로 인라인. 안전하지 않으면 기존 `render_cypher_params`(`:param` 줄)로 대체 |

두 DB의 치환 규칙을 하나의 함수로 합치지 않았다. 실제 실행은 두 DB 모두 기존 바인딩(PostgreSQL aiosql 함수/`executemany`, Neo4j `runner.run(query, bound_parameters)`) 그대로이며 인라인 문자열은 로그에만 쓴다.

### 11-2. 치환 주의 사항별 처리

| 경우 | PostgreSQL | Neo4j |
| --- | --- | --- |
| 문자열 리터럴 안의 변수 표기 | aiosql이 `':id 문자열'`을 바꾸지 않음(확인). 단 `E'...\'...'` 이스케이프 문자열·`$$...$$` 달러 인용 안의 `:id`는 aiosql이 바꾼다 — **실행 SQL에도 같은 변환**이 일어나는 라이브러리 한계(현재 mapper에는 없음) | 스캐너가 `'...'`·`"..."`(역슬래시 이스케이프 포함) 안은 건너뜀 |
| 주석 안의 변수 표기 | 머리·블록 주석은 aiosql이 실행 SQL에서 제거. 줄 끝 `-- :id2`는 aiosql이 `%(id2)s`로 바꾸고 mogrify가 값을 넣지만 주석이라 결과 영향 없음(실행 SQL과 동일) | `//`·`/* */` 안은 건너뜀(로그에서 주석 속 `$min_common`이 그대로 남는 것을 실제 로그로 확인) |
| `::type` 캐스팅 | aiosql이 `::`를 파라미터로 보지 않음, `:id2::int` → `%(id2)s::int` | 해당 없음 |
| 부분 일치 `$id` / `$id2` | aiosql이 이름 전체로 구분(확인) | 식별자 문자를 끝까지 읽어 구분 |
| 백틱 식별자 | 해당 없음(큰따옴표 식별자 `"col:id"`는 aiosql이 그대로 둠) | `` `$id` `` 식별자·`` {`$id`: 1}.`$id` `` 안은 건너뜀, `$`odd name``은 파라미터로 처리 |
| `%` 문자 | psycopg 규칙상 mapper에 `%%`로 써야 함(실행·mogrify 동일) | 해당 없음 |
| 한글·특수문자·이스케이프 | psycopg 리터럴(`'O''Brien'`, `E'...\\...'`) | `_cypher_string`(`\'`, `\\`, `\n`, `\uXXXX`) |
| NULL·Boolean·숫자·날짜·List·Map | psycopg 어댑터(3-4절) | `_cypher_literal`; 음수·NaN·Infinity는 괄호로 감쌈 `(-7)`, `(0.0 / 0.0)`. map은 감싸지 않음(`(n $props)` 자리) |
| 리터럴로 정확히 못 쓰는 값 | dict(Jsonb 아님)는 mogrify 실패 → 기존 대체(원문 SQL + PARAMS) | bytes·숫자 32개 이상 목록·알 수 없는 객체 → `// inline rendering skipped (...)` + `:param` 대체 |
| 마스킹 | 렌더링 SQL에 `'<MASKED>'` + `-- NOT REPRODUCIBLE AS-IS: masked values ...` | 인라인하지 않고 `// NOT REPRODUCIBLE AS-IS: masked values ...` + `:param` 대체 |
| execute 경로의 벡터 | `<VECTOR ...>` 미리보기 + `-- NOT REPRODUCIBLE AS-IS: vector values ...` | (`:param` 주석 처리) |
| 해석 실패·누락 파라미터 | — | 닫히지 않은 문자열·주석 → `cannot scan`, 쿼리가 쓰는데 없는 파라미터 → `parameters not provided` → `:param` 대체 |

### 11-3. 실제 로그 예시 (모드 B Q3 조회 버튼, 환경변수 없이 로컬 실행)

```text
2026-10-24 21:08:09,419 INFO car_search_rag.neo4j QUERY [graph_questions.similar_recipe_categories]
========================================================================
// inline parameter values for log only (the driver executed this query with bound parameters)
// Q3 (3-hop) '기준 레시피와 공통 재료를 쓰는 다른 레시피들은 어떤 요리 분류에 속하는가?'
// 경로: (base:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(other:rcp)-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat)
// 공통 재료가 여러 개여도 다른 레시피는 count(DISTINCT shared)로 한 번만 센다.
// $min_common: 공통 재료 최소 개수(1이면 재료 하나만 겹쳐도 포함). 분류별 레시피 수 내림차순, 분류명 순.
// sample_recipes는 공통 재료가 많은 순(같으면 이름·ID 순) 최대 5개다.
MATCH (base:rcp {rcp_id: '20261022_000020'})-[:RCP_USES]->(shared:ingr)<-[:RCP_USES]-(other:rcp)
WHERE other <> base
WITH other, count(DISTINCT shared) AS common_count
WHERE common_count >= 3
MATCH (other)-[:RCP_IN_RECIPE_CATEGORY]->(c:rcp_cat)
WITH c, other, common_count
ORDER BY common_count DESC, other.rcp_nm, other.rcp_id
RETURN c.rcp_cat_nm AS rcp_cat_nm, count(DISTINCT other) AS recipe_count,
       max(common_count) AS max_common_count, collect(other.rcp_nm)[0..5] AS sample_recipes
ORDER BY recipe_count DESC, rcp_cat_nm;
========================================================================
2026-10-24 21:08:09,535 INFO car_search_rag.neo4j RESULT [graph_questions.similar_recipe_categories] rows=5 counters={} session_ms=0.1 cypher_log_ms=1.4 query_fetch_ms=114.5 total_ms=115.9 server_available_after_ms=13 server_consumed_after_ms=1
```

주석 줄의 `$min_common`은 그대로 남고, 실제 사용 위치만 `'20261022_000020'`, `3`으로 바뀌었다.

### 11-4. 실제 읽기 전용 재실행 비교

| 대상 | 방법 | 결과 |
| --- | --- | --- |
| Neo4j 실제 mapper 7개(`LiveInlineReplayTests`) | 인라인 로그 텍스트를 READ 세션에서 **파라미터 없이** 실행 | 7/7 프로그램 결과와 같음, 텍스트에 `:param` 없음 |
| Neo4j 까다로운 토큰(같은 테스트) | 주석·문자열·백틱 안의 `$id`/`$id2`, `$`odd name``, map·list·음수·실수·false·null·date | 재실행 결과 = 바인딩 실행 결과, `'$id literal'`이 그대로 반환 |
| 앱 버튼 클릭 터미널 로그 15블록 | 로그 블록을 파일로 저장해 `cypher-shell --access-mode read -f`(운영 AuraDB) | 15/15 정상 종료, 행 수 일치(14개 인라인, 파라미터 없는 `recipe_options` 1개는 원문) |
| PostgreSQL 까다로운 mapper(같은 테스트) | `:id`·`:id2`·`:id2::text`·`':id 문자열'`·`"col:id"`·`'50%%'`·줄 끝 주석 `:id2`·NULL·bool·date·text[]·`\`·`:`가 든 문자열 | mogrify SQL을 READ ONLY로 파라미터 없이 실행 = 프로그램 결과 |
| PostgreSQL 실제 mapper `recipe.list_recipes` | 같은 방법 | 같음 |

### 11-5. 테스트

- `common/tests`: 73건 통과(신규 `CypherInlineRenderTests` 5건 — 토큰 위치, 타입별 인라인 값, 문자열·주석 보존, 대체 조건, 로그 표시 / `PostgresRenderNotesTests` 3건 — 일반 값 무표시, 마스킹 표시, execute 경로 벡터 표시·실행은 원본). 기존 Neo4j combined 로그 테스트는 마스킹 대체 형식으로 기대값 갱신.
- 이 절 작성 시점의 `recipe_recommender/tests`: 200건 통과. 이후 인수인계 검증으로 추가한 테스트와 전체 결과는 12절을 따른다.

### 11-6. 제한 사항(추가)

- 인라인 Cypher는 값 리터럴을 넣은 근사 재현이다. 이름 있는 시간대는 오프셋으로, 매우 큰 목록·map도 그대로 펼쳐져 로그가 길어진다(적재 CLI의 `$rows`). 쿼리 계획은 바인딩 실행과 다를 수 있다.
- aiosql의 `E''`·`$$` 문자열 처리 한계와 `%` 규칙은 실행 SQL 자체의 성질이므로 로그만 따로 고치지 않았다.
- Neo4j Browser·Aura Query·DBeaver에서의 인라인 텍스트 실행은 확인하지 못했다(`cypher-shell`과 드라이버로 확인).

## 12. 인수인계 최종 검증

Claude의 미커밋 구현을 유지한 상태에서 실제 소스와 테스트를 다시 확인했다. 추천 버튼 한 번의 로그 건수는 PostgreSQL **4건**, Neo4j **10건**이었다. 인수인계 보고의 Neo4j 14건은 이 실행에서 재현되지 않았다. 10건은 `ingredient_name_candidates` 3건 → `pantry_recommendations_by_coverage` 1건 → `graphrag_context` 5건 → `recipe_steps` 1건이다. 앞 절의 Neo4j 15건은 **모드 A 10건과 모드 B Q1·Q3·Q5 5건을 합한 수**이며 추천 버튼 한 번의 수가 아니다.

### 12-1. PostgreSQL 로그 복사·재실행

실제 `RecipeSearchService.get_recipe_detail` 경로에서 아래 Named SQL 4개를 바인딩 실행하고 `car_search_rag.sql`의 `mogrify()` 렌더링 결과를 각각 복사했다. 동일한 SQL을 **추가 파라미터 없이** PostgreSQL `BEGIN TRANSACTION READ ONLY` 안에서 재실행했다. 네 쿼리 모두 바인딩 실행 결과와 재실행 결과가 일치했다. 로그에는 실제 레시피 ID 리터럴이 들어 있었고 `%(NAME)s` 바인딩 자리표시는 남지 않았다. 검증 기록에는 DB URL·자격증명·전체 레시피 행을 싣지 않는다.

| 순서 | Named SQL | 처리 | 복사 SQL과 바인딩 결과 |
| --- | --- | --- | --- |
| 1 | `recipe.find_recipe_detail` | 첫 추천의 상세 1행 조회 | 일치 |
| 2 | `recipe.list_recipe_steps` | 조리 단계 목록 조회 | 일치 |
| 3 | `recipe.list_recipe_ingredients` | 등록된 재료 목록 조회 | 일치 |
| 4 | `recipe.list_recipe_unmatched_stagings` | 미등록 재료 목록 조회 | 일치 |

이는 일반 리터럴의 재실행 검증이다. 마스킹된 값이나 벡터 미리보기에는 `NOT REPRODUCIBLE AS-IS` 표시가 붙으므로 그대로 재현할 수 없다. 실제 DB 호출은 계속 파라미터 바인딩을 사용하며, 인라인 SQL은 로그에만 쓴다. Neo4j도 기존 실제 mapper 7건과 특수 토큰 인라인 재실행 테스트가 통과했다.

### 12-2. 추천 버튼의 ON/OFF 및 장애 격리

`streamlit.testing.v1.AppTest`와 Mock 세션에서 다음을 확인했다.

| 조건 | PostgreSQL 검증 조회 | 추천 결과 |
| --- | --- | --- |
| 로그 명시 ON | 첫 추천 ID로 `RecipeSearchService` 상세 조회, `select_one` 1회와 `select_list` 3회 | Neo4j 추천 유지 |
| 로컬 `.env` 기본 ON, `RECIPE_QUERY_LOG` 미설정 | 같은 SELECT 4회 | 유지 |
| 로그 명시 OFF 또는 `.env` 없는 Cloud 기본 OFF | 세션 생성·추가 조회 없음 | 유지 |
| PostgreSQL 조회 예외 | 경고 로그만 기록 | 유지 |

같은 프로세스에서 ON 뒤 `RECIPE_QUERY_LOG=0`으로 바뀌었을 때 활성 플래그도 False로 되돌려 추가 조회를 멈추는 회귀 테스트를 추가했다. 실제 Streamlit Cloud 배포 환경은 실행하지 않았고, Cloud 기본 조건은 `.env` 부재로 재현했다.

### 12-3. 전체 테스트 결과

| 테스트 묶음 | 수집 | 통과 | 실패 | 건너뜀 |
| --- | ---: | ---: | ---: | ---: |
| `recipe_recommender/tests` | 209 | 174 | 0 | 35 |
| `common/tests` | 73 | 73 | 0 | 0 |

추천 묶음의 건너뜀은 DB 환경변수나 외부 서비스가 필요한 테스트를 전체 실행에서 제외한 것이다. 읽기 전용 라이브 검증인 추천 버튼의 PostgreSQL 4건·Neo4j 10건 로그 확인과 PostgreSQL 4건 복사·재실행 비교는 별도 대상 테스트로 실제 DB에 연결해 통과했다. 전체 실행 중 등록 CLI 검사에는 `--dry-run`을 사용했으며 DB 변경은 실행하지 않았다.
