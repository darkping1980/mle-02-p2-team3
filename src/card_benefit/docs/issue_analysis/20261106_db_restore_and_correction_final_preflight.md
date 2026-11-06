# DB 복원 검증 및 기존 데이터 보정 최종 사전 검증

작성일: 2026-11-06  
목적: PostgreSQL 기존 데이터 보정과 Neo4j 재적재 직전까지의 준비 상태를 정리한다. 이 문서는 운영 적용 승인이 아니며, 이번 작업에서 어떠한 DB 쓰기도 하지 않았다.

> 이 문서는 [이전 사전 검증 문서](20261106_db_correction_preflight_result.md)의 카드 23/100 보류 판단을 사용자 제공 공식 상품설명서 내용으로 갱신한다. 기존 P0·P1·P2 코드와 전체 회귀는 다시 분석·실행하지 않았다.

## 1. 최종 판단

| 항목 | 최종 판단 | 실행 준비 상태 |
|---|---|---|
| PostgreSQL 기존 백업 | JSON 데이터 + 카탈로그 기반 DDL. 데이터 대조는 성공했으나 실제 빈 테스트 DB 복원은 하지 않음 | 복원 리허설 차단: 격리 DB, 복원 도구, 역할·확장 준비가 확인되지 않음 |
| 카드 22/099 | 월 실적 30만~80만원 미만 10,000원, 80만원 이상 15,000원 | JSON 패치와 근거 연결 준비 가능 |
| 카드 20/092 | 누적 기본 100,000원 + 추가 100,000원 | 누적 구조 그대로 JSON 패치와 근거 연결 준비 가능 |
| 카드 23/100 | 특별·추가 적립 공유 월 한도 10,000원 / 20,000원 / 50,000원, 기본 적립 한도 제한 없음 | 원본 `limits`/`rule_limits` 패치와 근거 연결 준비 가능. B2 런타임 해석은 별도 구현·검증 필요 |
| 운영 DB/Neo4j 변경 | 수행하지 않음 | 실제 쓰기·재적재는 별도 승인 필요 |

현재 저장소의 `limit_struct_backfill.py`는 `--dry-run`만 허용하고 UPDATE/INSERT 코드를 포함하지 않는다. 따라서 아래 payload를 승인 후 운영에 적용하려면 별도로 승인된 트랜잭션 실행기가 필요하다.

## 2. PostgreSQL 백업 복원 검증

### 2.1 확인한 백업과 실제 복원 가능성

기존 백업 위치:

```text
src/data/backup/pre_calc_cleanup_20261106_140723/
  postgres_db_pipeline.json
  catalog.json
  schema_ddl.sql
```

백업은 PostgreSQL **17.11**에서 `db_pipeline` 테이블 20개와 행 4,864건을 읽어 만든 JSON 스냅샷이다. catalog에는 77개 제약, 62개 인덱스, 8개 view, 7개 function, 13개 sequence가 기록돼 있다. 행과 카탈로그를 현재 DB와 읽기 전용으로 대조한 결과는 `VERIFY OK`였다.

그러나 이 결과는 **백업 파일과 현재 DB가 같은 상태임을 확인한 것**이지, 빈 DB에 실제 복원했다는 뜻은 아니다.

- `postgres_db_pipeline.json`은 행 데이터를 포함하지만 PostgreSQL custom/tar dump가 아니다. `pg_restore` 입력으로 바로 쓸 수 없다.
- `schema_ddl.sql`은 schema·sequence·function·table·constraint·index·view 등을 재생성하기 위한 DDL이며 행 데이터 INSERT/COPY를 포함하지 않는다.
- `backup_db_pipeline.py`의 `--verify`는 현재 테이블을 읽어 백업과 비교할 뿐, restore 명령이나 범용 행 로더를 제공하지 않는다.
- 확인 가능한 환경에는 `psql`, `pg_restore`, `pg_dump`, Docker 명령과 PostgreSQL 격리 서비스가 없었다. `.env.example`도 단일 `DB_URL`만 정의하며 test DB 프로파일은 제공하지 않는다. 실제 `.env` 값은 출력하거나 사용하지 않았다.
- catalog는 `vector 0.8.2`를 포함한 extension 목록을 기록한다. 복원 환경은 PostgreSQL 17 호환성, pgvector 등 필요한 extension과 권한을 별도로 준비해야 한다. role/ACL의 완전한 재현 여부도 현재 복원 도구에서 검증되지 않았다.

**결론: 실제 복원 리허설은 차단 상태이며 시도하지 않았다.** 격리된 PostgreSQL 17 테스트 인스턴스, 필요한 extension과 역할/권한, JSON 행 로더 또는 native dump, 빈 target 확인이 준비되면 리허설할 수 있다. `schema_ddl.sql`만 실행하거나 운영 DB에서 임시 schema를 만들면 안 된다.

### 2.2 복원 리허설에 필요한 검증

격리 DB에만 다음 검증을 수행해야 한다.

1. DDL 실행 후 20개 테이블, 77개 constraint, 62개 index, 8개 view, 7개 function, 13개 sequence의 생성 여부와 정의를 catalog와 비교한다.
2. 백업 행을 FK 의존성 순서로 적재하고 sequence 상태를 복원한다. 모든 PK/unique/FK/check가 생성되고 검증된 상태인지 검사한다.
3. 테이블별 행 수를 백업의 fingerprint와 비교하고, 대상 세 항목의 `item_data` 및 `card_evidence_link` 전 행을 비교한다.
4. 이 백업 시점에는 대상 `item_data`가 `{}`다. 따라서 복원 확인은 `{}` preimage와 기존 근거 연결을 확인해야 하며, 보정 후 payload는 별도 보정 승인/실행 로그로 추적한다.
5. 복원 데이터로 재생성된 schema의 `item_data`, 근거 link 행, 관련 FK/sequence를 확인한 뒤에만 복구 절차를 검증 완료로 본다.

## 3. Neo4j 백업·복원 준비

### 3.1 현재 가진 백업과 격리 복원 가능성

- 프로젝트의 Neo4j 연결 코드는 검증 TLS(`neo4j+s`)를 지원하고, 이전 문서는 DB ID `6ac1f0f8`을 사용한 것으로 기록한다. `.env.example`은 Aura 호스트 형식을 예시로 보여 주지만, 이 환경에서 실제 Aura instance tier, 상태, snapshot 권한을 확인하지 않았다.
- 이전 결과 문서가 언급한 `src/data/backup/neo4j_dp_pre_reload_20261103/neo4j_dp_graph.json`은 현재 워크스페이스에서 찾지 못했다.
- 현재 발견한 `a10_3_pre_neo4j_resync_20261101`은 manifest상 노드 108개·관계 168개이고, 현 기준 그래프 1,635/2,702보다 오래되고 작다. 최신 Neo4j 전체 백업으로 사용할 수 없다.
- `neo4j_recipe_a8_20261101_111009`은 다른 그래프의 JSONL export이며 본 카드 그래프 복원 자료가 아니다.
- `neo4j_isolated_test.py`는 공유 Aura DB의 `df_v7_test` namespace에 실제 쓰고 삭제하는 명시적 플래그가 필요하다. 이는 빈 복제 DB에 백업을 복원하는 도구가 아니므로 이번 복원 검증에 사용하지 않았다.

따라서 **현재 시점 복원 가능한 Neo4j 백업은 확인되지 않았다.** 운영 DB에는 접근해 snapshot을 생성하거나 쓰기 쿼리를 실행하지 않았다.

### 3.2 안전한 백업 방식과 보존 범위

저장소의 연결 설정과 이전 기록은 Aura 사용을 시사하므로, 우선 Aura Console에서 대상 인스턴스/DB ID를 확인하고 적용 가능한 공식 snapshot/backup을 사용해야 한다. Aura 문서는 단일 데이터베이스 snapshot이 user DB와 `system` DB를 포함한다고 설명하며, 복원은 대상 인스턴스 내용을 덮어쓴다. 따라서 안전한 검증은 `Completed`이면서 사용 가능한 snapshot으로 **새 격리 인스턴스를 생성/clone**하는 흐름을 우선해야 한다. tier별 snapshot/export 가능 기간은 다르므로 현재 instance tier와 해당 snapshot의 exportable/restorable 상태를 Console에서 먼저 확인해야 한다. [Aura 백업·복원 안내](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)

Neo4j Aura가 아닌 self-managed Enterprise라면 온라인 `neo4j-admin database backup`/restore는 별도 백업 서비스 설정이 필요하며 Aura에서는 해당 명령을 지원하지 않는다. [Neo4j 온라인 백업 안내](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/), [백업 복원 안내](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/)

격리 복원 검증에서 보존·대조할 대상:

- 모든 `dp_node.key`, 노드 라벨, `source_json`, 노드 속성 및 속성 자료형
- 모든 `dp_` 관계의 key, 타입, 시작/종료 노드 key, `source_json` 및 관계 속성
- 혜택 노드 검색 projection: `embedding` 벡터 값, 1536 차원, 모델명, embedding run ID, `search_text`
- 제약과 인덱스 정의, 특히 vector index의 정의·상태(`ONLINE`) 및 검색 결과 기본 확인
- 노드·관계 총수와 라벨·관계 유형별 수, duplicate key/orphan 검사

native database backup은 database 복구에 사용하되, vector index가 사용 가능해질 때까지 population을 기다리고 위 항목을 별도 대조해야 한다. 앱 그래프 속성의 벡터 값과 인덱스의 가용 상태는 서로 다른 확인 항목으로 기록한다.

### 3.3 전체 MERGE 실패 시 복구와 사후 검증

`neo4j_load_draft.py`는 `session.execute_write(write_transaction, ...)` 안에서 노드 MERGE, 관계 MERGE, 노드/관계 key 집합의 사후 검증을 수행한다. 그 트랜잭션이 예외를 내면 해당 데이터 write는 rollback 대상이다. 다만 `prepare_schema()`의 `CREATE CONSTRAINT IF NOT EXISTS`는 데이터 트랜잭션보다 먼저 실행되므로, 적재가 실패해도 새 제약은 남을 수 있다.

MERGE가 이미 commit된 뒤 잘못된 결과를 발견하면 앱 코드의 트랜잭션 rollback만으로 이전 상태를 되돌릴 수 없다. 이때는 직전의 검증된 Aura backup으로 **격리 인스턴스에서 우선 복원 검증**해야 한다. 운영 인스턴스에 snapshot을 복원하면 현재 데이터가 덮어써지므로, 그 복원 자체는 별도 승인과 유지보수 계획이 필요하다. commit 결과가 불확실한 네트워크 오류에서는 즉시 재시도하지 말고 READ_ACCESS 세션의 노드/관계 key, item_data와 embedding 검증으로 실제 상태부터 판정해야 한다.

재적재 전/후 점검은 다음과 같다.

1. PostgreSQL 전체 snapshot의 dry-run에서 기대 node/relationship key 집합, `item_data`, stale key, duplicate key, endpoint 누락, label/type별 건수와 embedding key·차원·모델·run ID·hash를 승인한다.
2. 재적재 후 `neo4j_validate`로 node/relationship key 집합, 라벨, properties, relation endpoints/source JSON, `item_data` 전체 차이를 확인한다.
3. embeddings는 count, null, 차원, 모델/run ID와 정렬한 key별 값 hash를 비교하고 vector index 상태가 ONLINE인지 확인한다.
4. 추가 근거 8건의 owner→evidence→chunk→page→document 경로 및 link 속성을 PostgreSQL 원천과 대조한다.
5. 모든 검증 결과와 사용한 snapshot ID를 기록하기 전에는 재적재 성공으로 선언하지 않는다.

## 4. 카드 23/100 공식 한도 범위와 B2 검토

사용자가 제공한 공식 카드의정석 POINT II 상품설명서 3페이지 내용으로 다음 업무 사실을 확정한다.

- 전월 실적 30만원 이상: 특별·추가 적립 통합 월 한도 10,000원
- 전월 실적 60만원 이상: 특별·추가 적립 통합 월 한도 20,000원
- 전월 실적 120만원 이상: 특별·추가 적립 통합 월 한도 50,000원
- 기본 적립 한도는 제한 없음
- 이는 간편결제 추가 적립 단독 한도가 아니라 특별 적립과 추가 적립이 공유하는 한도다.

이 사실은 DB 추출값의 `limits[].shared_scope_txt="특별/추가 적립"`과 일치한다. 기존 원문 추출에는 세 한도 근거 002739/002740/002741이 각각 존재하고, 공유 표현 근거 002742가 카드 혜택에 이미 연결돼 있다. `applies_to_benefit_nms`가 빈 배열이므로, DB에 등록된 혜택명 외의 공유 구성원 이름을 임의로 만들지는 않는다. 기본 적립 한도 무제한은 별도 상한이 아니므로 10k/20k/50k의 `limits`에 섞거나 숫자 한도로 저장하지 않는다.

### B2 권고: 원문 조건은 그대로, 최상위 충족 구간 선택은 시스템 규칙으로

B2를 **시스템의 파생 선택 정책**으로 구현하는 것은 가능하다. 보정 시 `rule_list` 원본의 `cond_min_amt`는 300,000 / 600,000 / 1,200,000으로 유지하고 `cond_max_amt_excl`는 계속 `null`로 둔다. 실행 시 전월 실적 `S`에 대해 `cond_min_amt <= S`인 실적 규칙 중 최소값이 가장 큰 규칙 하나를 선택하고, 그 규칙의 `rule_limits`에 매핑된 cap을 가져온다.

```text
if S < 300,000: 특별·추가 적립 구간 한도 미충족 (기본 적립은 별도, 한도 제한 없음)
300,000 <= S < 600,000: r1 / 10,000원
600,000 <= S < 1,200,000: r2 / 20,000원
1,200,000 <= S: r3 / 50,000원
```

구간 상한은 **계산 시점의 투영값**이며 원문 필드나 원본 `rule_list`에 기록하지 않는다. 데이터에 남길 원본은 하한, `null` 상한, 각 규칙-한도 매핑과 근거뿐이다. 정책을 `limit_tiers`에 저장한다면 `source`를 원문 추출로 표시하지 말고 `SYSTEM_DERIVED` 같은 별도 표식과 `max_basis="NEXT_TIER_MIN"`, `selection_policy="HIGHEST_QUALIFYING_MINIMUM"`을 같이 보존해야 한다.

**현재 구현 상태:** P2의 `limit_tiers_from_extraction()`은 상한이 없는 여러 구간을 겹치는 규칙으로 취급해 23/100에 `limit_tiers`를 생성하지 않는다. GraphRAG의 기존 limit-tier view/검증은 명시적으로 저장된 tiers를 읽고 한도 문장 쌍을 검사하지만, 23/100의 `rule_limits`를 이용해 전월 실적에서 최고 하한을 선택하는 전용 cap selector는 확인되지 않았다. 따라서 B2는 데이터 원문을 변경하지 않고 구현할 수 있는 타당한 방안이나, **현재 런타임에서 동작하는 완료 기능은 아니다.** 정책 적용 코드를 구현하고 30만·60만·120만원 경계 직전/정확 경계/초과, 기본 적립과 특별·추가 공유 한도, 잘못된 tier/cap 연결을 검증한 다음 제품 결과에 반영해야 한다. 이번 범위에서는 코드를 수정하지 않았다.

## 5. 세 건의 변경 전후 JSON과 근거

아래 `before`는 2026-11-06 PostgreSQL snapshot에서 확인한 실제 `item_data`이며 세 건 모두 `{}`다. `after`는 같은 날짜의 읽기 전용 fixture/live-row dry-run payload다. 날짜 필드, 감사 사용자, DB 발급 link PK는 보정 writer가 별도로 처리해야 하며 여기서 가상값을 만들지 않았다.

### 5.1 카드 22/099 — 월 실적별 10,000원 / 15,000원

업무 확정 내용: 실적 구간 30만~80만원 미만 및 80만원 이상, 월 할인 한도 10,000원 및 15,000원. 기존 rule/condition 값은 보정하지 않는다. `limit_tiers`는 원문에 실제 상한이 있는 r1만 800,000으로 기록하고 r2는 상한이 없다.

신규 RULE/COND link 3건:

| 규칙 / 조건 | evidence ID | 문서 / 페이지 / 청크 / 원문 위치 |
|---|---|---|
| r1 / c1 | `20261105_002685` | `20261105_000042` / 1 / `20261105_000173` / 3727–3741 |
| r2 / c2 | `20261105_002686` | `20261105_000042` / 1 / `20261105_000173` / 3743–3757 |
| r3 / c3 | `20261105_002687` | `20261105_000042` / 1 / `20261105_000173` / 3182–3223 |

기존 BNFT 근거 link `20261105_000460`–`000463`가 limit values `002681`–`002684`에 연결돼 있다. 신규 condition link의 `evidence_link_id`는 PostgreSQL이 발급하므로 적용 전 알 수 없다.

```json
{
  "before": {},
  "after": {
    "schema_ver": "BENEFIT_V1",
    "limits": [
      {"limit_key":"l1","limit_num":10000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"10,000원","shared_scope_txt":"횟수 제한 없이 월 할인 한도 내에서 합산 할인","applies_to_benefit_nms":["월납 요금 청구할인"],"evidence_ids":["20261105_002681"]},
      {"limit_key":"l2","limit_num":15000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"15,000원","shared_scope_txt":"횟수 제한 없이 월 할인 한도 내에서 합산 할인","applies_to_benefit_nms":["월납 요금 청구할인"],"evidence_ids":["20261105_002682"]}
    ],
    "rule_limits":{"r1":["l1"],"r2":["l2"],"r3":["l1","l2"]},
    "limit_tiers":{
      "schema_ver":"LIMIT_TIERS_V1","source":"EXTRACTION","basis_cd":"PREV_MONTH_SPEND",
      "tiers":[
        {"tier_key":"r1","rule_key":"r1","label":"30만원 이상 80만원 미만","min_amt":300000,"max_amt_excl":800000,"evidence_ids":["20261105_002685"]},
        {"tier_key":"r2","rule_key":"r2","label":"80만원 이상","min_amt":800000,"max_amt_excl":null,"evidence_ids":["20261105_002686"]}
      ],
      "own":{"column":"월 한도","column_source":"PERIOD_CD","merged_cell":false,"caps":{
        "r1":{"raw":"10,000원","amount":10000,"limit_key":"l1"},
        "r2":{"raw":"15,000원","amount":15000,"limit_key":"l2"}
      }},
      "shared":[]
    }
  }
}
```

예상 PostgreSQL 영향: `card_product_item` 1행 update, RULE/COND link 3행 insert. `rule_list`, 검색 텍스트·임베딩은 변경하지 않는다.

### 5.2 카드 20/092 — 누적형 기본 100,000원 + 추가 100,000원

업무 확정 내용: 기본 보너스 할인 한도 100,000원과 “추가 제공” 100,000원. 누적형 의미를 보존하며 200,000원 단일 cap 또는 배타 구간으로 바꾸지 않는다. 추출 기간 값 `UNKNOWN`도 임의로 월/연 기간으로 보정하지 않는다.

신규 RULE/COND link 2건:

| 규칙 / 조건 | evidence ID | 문서 / 페이지 / 청크 / 원문 위치 |
|---|---|---|
| `bonus_base_discount` / `bonus_spend_24m` | `20261105_002453` | `20261105_000040` / 3 / `20261105_000159` / 684–710 |
| `bonus_additional_cap_discount` / `bonus_spend_36m` | `20261105_002454` | `20261105_000040` / 3 / `20261105_000159` / 733–747 |

기존 BNFT 근거 link에는 `20261105_000427`→`002447`, `000428`→`002448`이 포함돼 있어 두 cap 표현의 근거가 기존 연결에도 있다.

```json
{
  "before": {},
  "after": {
    "schema_ver": "BENEFIT_V1",
    "limits": [
      {"limit_key":"bonus_base_cap","limit_num":100000,"cap_unit_cd":"KRW","period_cd":"UNKNOWN","limit_raw_txt":"보너스 할인 한도 10만원 제공","shared_scope_txt":null,"applies_to_benefit_nms":["골프/프리미엄 아울렛 50% 청구 할인"],"evidence_ids":["20261105_002447"]},
      {"limit_key":"bonus_additional_cap","limit_num":100000,"cap_unit_cd":"KRW","period_cd":"UNKNOWN","limit_raw_txt":"보너스 할인 한도 10만원 추가 제공","shared_scope_txt":null,"applies_to_benefit_nms":["골프/프리미엄 아울렛 50% 청구 할인"],"evidence_ids":["20261105_002448"]}
    ],
    "rule_limits":{"bonus_base_discount":["bonus_base_cap"],"bonus_additional_cap_discount":["bonus_additional_cap"]}
  }
}
```

예상 PostgreSQL 영향: `card_product_item` 1행 update, RULE/COND link 2행 insert. `limit_tiers`를 생성하지 않는다.

### 5.3 카드 23/100 — 특별·추가 적립 공유 월 한도

공식 문서로 확정된 공유 범위: 특별 적립과 추가 적립이 같은 실적 구간별 월 한도를 공유한다. 기본 적립은 한도 제한 없음. `shared_scope_txt`의 추출값 `특별/추가 적립`을 유지한다. 다른 적용 혜택의 정확한 이름을 추측해 `applies_to_benefit_nms`에 쓰지 않는다.

신규 RULE/COND link 3건:

| 규칙 / 조건 | evidence ID | 문서 / 페이지 / 청크 / 원문 위치 |
|---|---|---|
| r1 / c1 | `20261105_002744` | `20261105_000043` / 3 / `20261105_000176` / 362–383 |
| r2 / c2 | `20261105_002745` | `20261105_000043` / 3 / `20261105_000176` / 419–440 |
| r3 / c3 | `20261105_002746` | `20261105_000043` / 3 / `20261105_000176` / 476–498 |

한도/공유 표현 근거는 이미 혜택 자체 BNFT로 연결돼 있다: `000469`→`002739`, `000470`→`002740`, `000471`→`002741`, `000472`→`002742`(통합 월 적립 한도), `000473`→`002743`. 추가할 것은 위 세 조건 연결뿐이다.

```json
{
  "before": {},
  "after": {
    "schema_ver": "BENEFIT_V1",
    "limits": [
      {"limit_key":"l1","limit_num":10000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"1만원","shared_scope_txt":"특별/추가 적립","applies_to_benefit_nms":[],"evidence_ids":["20261105_002739"]},
      {"limit_key":"l2","limit_num":20000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"2만원","shared_scope_txt":"특별/추가 적립","applies_to_benefit_nms":[],"evidence_ids":["20261105_002740"]},
      {"limit_key":"l3","limit_num":50000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"5만원","shared_scope_txt":"특별/추가 적립","applies_to_benefit_nms":[],"evidence_ids":["20261105_002741"]}
    ],
    "rule_limits":{"r1":["l1"],"r2":["l2"],"r3":["l3"]}
  }
}
```

위 패치는 원본 조건의 `cond_max_amt_excl=null`을 그대로 둔다. 30만/60만/120만원에 따라 cap을 구분해 답하려면 B2의 최상위 충족 구간 선택기를 먼저 구현하고 검증해야 한다. 기본 적립 제한 없음은 이 `limits` 배열에 숫자 cap으로 추가하지 않는다.

예상 PostgreSQL 영향: `card_product_item` 1행 update, RULE/COND link 3행 insert. 한도 관련 BNFT 근거 link는 이미 있으므로 새로 insert하지 않는다.

## 6. 합산 영향과 승인 조건

세 행을 모두 적용할 때의 계획량은 PostgreSQL `item_data` UPDATE **3행**, `card_evidence_link` RULE/COND INSERT **8행**이다. 8개 evidence ID가 현재 어떤 link에도 붙지 않은 것을 dry-run에서 확인했다. 현재 행의 `rule_list`, `item_search_txt`, embedding은 보존한다. `evidence_link_id`는 적용 시 DB sequence가 발급하며 미리 추정하지 않는다.

기존 읽기 전용 Neo4j 검증 결과 1,635 노드/2,702 관계를 기준으로, 여덟 연결이 전부 신규라면 dry-run graph 예상 증분은 조건부 **+8 evidence node / +16 relationships**(`supported_by` 8, `in_chunk` 8)다. 23의 기존 BNFT 한도 근거는 이미 연결돼 있으므로 이 증분에 다시 세지 않는다. 기존 count는 이전 검증 시점 값이며, 실제 재적재 전 재조회·전체 그래프 dry-run을 해야 한다.

현재 JSON patch 준비는 가능하지만 실제 실행 전 다음 승인이 필요하다.

1. 카드 22의 두 limit과 r1/r2 mapping, r3가 두 cap을 참조하는 구조 확인.
2. 카드 20의 “추가 100,000원”을 별도 추가 cap으로 보존하고 기간 `UNKNOWN`을 유지하는 확인.
3. 카드 23의 특별·추가 적립 공유 한도라는 공식 범위 및 기본 적립 무제한의 분리 확인.
4. B2를 시스템 유도 정책으로 구현할지 승인. 승인 시 원본 rule 조건은 유지하고 selection policy, derived boundary의 provenance를 별도 표기하며 경계 테스트를 추가한다.
5. 격리 PostgreSQL 17 복원 환경·loader·extension/권한과 복원 증빙 준비.
6. 운영용 PostgreSQL writer의 별도 검토/승인, 실행 직전 전체 백업·preimage 확인, 트랜잭션 후 검증 및 조건부 rollback 절차.
7. 최신 Aura snapshot의 완료·복원 가능 상태와 tier 확인, 새 격리 Neo4j instance에서 restore rehearsal 및 vector/index 검증.
8. PostgreSQL 보정과 Neo4j 재적재 각각의 별도 실행 승인.

## 7. 이번 작업에서 수행하지 않은 사항

PostgreSQL 실제 복원/UPDATE/INSERT/DELETE/DDL 0건, Neo4j snapshot 생성/restore/write query 0건, 배포 0건, Git commit/push 0건. 전체 회귀 테스트는 다시 실행하지 않았다. 기존 미커밋 소스와 테스트 파일은 보존했다.
## 8. 이번 환경 확인 결과 (2026-11-06)

### 8.1 PostgreSQL 백업 재검증과 격리 restore 차단 사유

운영 PostgreSQL에 대한 한 번의 버전 조회는 강제 read-only 트랜잭션에서 수행했고 `server_version=17.11`, `transaction_read_only=on`을 확인했다. 기존 백업의 `server_version`도 17.11이다.

기존 JSON+DDL 백업의 `backup_db_pipeline.py --verify`를 승인된 권한 상승 환경에서 다시 실행했다. 출력은 20 tables / 4,864 rows, catalog 8 views / 7 functions / 77 constraints / 62 indexes / 13 sequences, `VERIFY OK`였다. 세부 테이블 건수는 `app_log=127`, `app_log_event_archive=97`, `card_evidence_link=250`, `card_product_item=51`, `card_source_evidence=2959` 등이며 파일의 row/fingerprint/schema와 현재 원본이 일치한다. 접속은 검증 동안 read-only로 유지됐다.

그러나 실제 복원 리허설은 수행할 수 없었다. 해당 PC에서 `docker`, `psql`, `pg_restore`, `pg_dump`, `postgres`, `initdb` 실행 파일이 확인되지 않았고 PostgreSQL Windows 서비스 및 `127.0.0.1:5432` listener도 없었다. 백업은 `pg_restore`가 바로 읽는 native archive가 아닌 JSON+DDL이며, 저장소에 데이터 적재용 restore tool도 없다. 따라서 운영 DB 연결은 버전·verify 읽기에만 사용했고 복원 대상이나 쓰기 연결을 만들지 않았다.

격리 리허설 준비: 별도 VM 또는 Docker/로컬 PostgreSQL 17 인스턴스, 운영과 다른 DB 이름·계정·비밀번호, host-local 네트워크 바인딩, extension `vector 0.8.2`와 DDL 의존 extension/role, JSON snapshot 전용 loader가 필요하다. 빈 DB가 격리 상태인지 확인한 후에만 DDL → FK 의존성 순서의 row load → sequence restore를 진행한다. 성공 기준은 테이블 20개 및 4,864행, PK/unique/FK/check 77개 검증, index 62개, 특정 `item_data` JSON과 evidence link 행 비교, sequence 및 row fingerprint 일치다. 이 환경이 준비되기 전까지 restore status는 **미검증/차단**이다.

### 8.2 Aura 콘솔 접근 확인

로컬 UI inventory에는 Chrome 창이 있었으나 browser access host가 사용 불가했고 브라우저 탭 목록도 제공되지 않았다. Neo4j Aura 로그인 세션, 실제 instance tier 또는 snapshot 권한/상태를 읽을 수 없어 이 항목은 **미확인**이다. 운영 DB에는 연결하거나 쿼리하지 않았다.

사용자 또는 Aura 관리자 확인 경로:

1. Neo4j Aura Console에서 대상 프로젝트와 instance를 열고, 이전 기록의 DB ID `6ac1f0f8` 및 연결 endpoint와 일치하는지 확인한다.
2. Instance details에서 tier/type(Free/Professional/Business Critical/VDC 등), running/paused 상태, Neo4j version을 기록한다.
3. Inspect/instance actions의 **Snapshots** 또는 **Backups** 탭에서 최근 snapshot의 timestamp, `Completed` 상태, restore 가능 기간, exportable/clone 가능 여부를 확인한다. 다중 DB instance이면 대상 user database의 backup을 확인한다.
4. 운영 instance를 덮어쓰지 않고 snapshot에서 **별도 새 instance를 생성/clone**할 수 있는 tier인지 확인한다. 새 instance ID/URI와 복원 후 연결 테스트 권한을 기록한다.
5. 사용 가능한 snapshot이 없다면 snapshot/backup 권한과 승인된 생성 시점을 운영 담당자가 별도 계획한다. 이번 작업에서 스냅샷을 만들지 않았다.

Aura 공식 안내는 snapshot/backup 복원이 기존 instance 데이터를 덮어쓴다고 설명하고, 완료·exportable 상태 및 tier별 기간 제한이 있으므로 이 확인이 끝나기 전 운영 복원은 금지한다. [Aura backup/restore 문서](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)

### 8.3 B2 정책 경계 테스트 설계

아래는 정책 선택기의 설계 기준이며, 구현/실행한 테스트가 아니다. 전월 실적 `S`에 대해 eligible condition 중 `cond_min_amt`가 가장 큰 규칙 하나를 고른다. 원본 rule 값은 `300000/600000/1200000`, `cond_max_amt_excl=null`을 계속 보존한다.

| 전월 실적 | 기대 선택 | 특별·추가 공유 월 한도 |
|---:|---|---:|
| 299,999 | 없음 | 특별·추가 구간 한도 미충족. 기본 적립 한도는 별도 무제한 |
| 300,000 | r1 | 10,000원 |
| 599,999 | r1 | 10,000원 |
| 600,000 | r2 | 20,000원 |
| 1,199,999 | r2 | 20,000원 |
| 1,200,000 | r3 | 50,000원 |
| 1,200,001 이상 | r3 | 50,000원 |

추가 회귀 조건: 30만원 이상에서 r1+r2+r3 모두 선택하지 않고 최고 하한 하나만 선택, 경계 바로 아래/같은 값에서 전환, 규칙→`rule_limits`→cap ID 연결, 원문 `cond_max_amt_excl` 불변, 특별 적립과 추가 적립이 같은 월 cap bucket을 공유(각각 별도 cap으로 중복 적용하지 않음), 기본 적립에 이 cap을 적용하지 않음, 실적 값 null/음수/비수치일 때 임의 tier를 고르지 않음. 현재 코드에는 이 selector가 없으므로 테스트를 통과하기 전에는 B2 운용 준비 완료로 보지 않는다.

### 8.4 Git 및 백업 파일 점검

이번 점검 시점 상태:

```text
branch: main
HEAD: 9283c55132ae47b513911b856cb765cf8625f052
modified tracked files: 0
untracked: src/card_benefit/docs/issue_analysis/20261106_db_restore_and_correction_final_preflight.md
```

앞서 진행된 소스 변경은 현재 HEAD에 포함된 상태로 보이며, 이번 턴에서 소스 파일은 수정하지 않았다. 향후 별도 승인이 있어 커밋한다면 이번 작업에 대한 안전한 후보는 위 Markdown 결과 문서뿐이다. 이번에는 commit/push를 하지 않는다.

`src/data/backup/pre_calc_cleanup_20261106_140723/`는 `.gitignore`의 `/src/data/backup/pre_calc_cleanup_*/` 규칙으로 무시되며, 이번 snapshot 파일은 tracked/별도 untracked 목록에 없다. 대형 row snapshot과 schema data는 Git에 추가하지 않는다. 기존 Git에는 일부 예전 `src/data/backup` 산출물(manifest, CSV/JSONL 등)이 이미 tracked되어 있으므로, 새 변경을 stage할 때 `git add src/data/backup` 또는 광범위한 `git add -A`는 피하고 해당 기존 파일을 이번 수정에서 재-staging/갱신하지 않는다.

## 9. 최종 안전 상태

- PostgreSQL version 및 기존 백업의 원본 대조: **확인 성공** (17.11, read-only, 20 tables/4,864 rows, `VERIFY OK`).
- PostgreSQL 빈 격리 DB 실제 복원, PK/FK after-restore, `item_data`/근거 데이터 복원: **실행하지 못함** (격리 서비스와 restore loader 부재).
- Neo4j Aura instance type/snapshot eligibility 및 별도 clone 복원: **미확인** (Aura Console read-only 접근 불가, 현재 기준 native backup 미발견).
- 23/100 B2 정책: **설계 가능, 미구현·미검증**. 경계별 선택 방식은 위 테스트 기준에 따른다.
- 운영 PostgreSQL/Neo4j 쓰기, 복원, 재적재, 배포, Git commit/push: **0건**.

실제 데이터 보정을 시작하기 전의 선행 조건은 (1) 격리 PostgreSQL 17 복원 리허설 성공, (2) Aura tier와 완료/복원 가능한 snapshot 확인 및 새 instance 복원 검증, (3) B2 selector와 공유 cap 테스트 구현/통과, (4) 최신 preimage와 별도 백업 확보, (5) 세 row·8 condition link에 대한 승인된 write 실행기와 rollback plan, (6) PostgreSQL 변경과 Neo4j 재적재 각각의 별도 승나다.


## 10. 카드 23/100 B2 선택 정책 구현 후속 기록

2026-11-06 사용자 지시에 따라 B2를 원본 상품 조건을 수정하지 않는 GraphRAG 런타임 파생 정책으로 구현했다. 이 항목은 문서 앞부분의 이전 “미구현” 상태를 갱신한다. 데이터 복원 리허설과 운영 데이터 변경은 이번 작업 범위가 아니다.

- 적용 대상은 `card_product_item:23:20261105_000100` 하나다. 카드 22/099, 카드 20/092, 다른 카드 및 누적형 한도에는 이 정책을 적용하지 않는다.
- 공식 원문 하한과 cap은 300,000원→10,000원, 600,000원→20,000원, 1,200,000원→50,000원이다. 여러 하한을 만족하면 가장 높은 하한 하나를 선택한다.
- 원본 `cond_max_amt_excl`은 계속 `null`이다. 다음 tier의 하한으로 산출한 `derived_max_amt_excl`은 `max_basis=NEXT_TIER_MIN`, `source=PROGRAM_DERIVED`로 표시해 원문과 구분한다. 임의 rule key 또는 현재 조회에서 확인되지 않은 근거 ID는 생성하지 않는다.
- 질문에 명시된 전월 실적만 별도로 파싱한다. 전월 실적이 없거나 유효하지 않으면 tier를 선택하지 않는다. 결제 금액 파서는 변경하지 않는다.
- 선택 cap은 특별·추가 적립 통합 월 한도에만 적용한다. 기본 적립에는 cap을 적용하지 않는다. 답변 검증은 이 파생 tier를 포함하여 하한과 cap의 잘못된 조합을 검사한다.

| 전월 실적 | 선택 결과 |
| ---: | --- |
| 299,999원 | 해당 구간 없음 |
| 300,000원 | 300,000원 하한 / 10,000원 |
| 599,999원 | 300,000원 하한 / 10,000원 |
| 600,000원 | 600,000원 하한 / 20,000원 |
| 1,199,999원 | 600,000원 하한 / 20,000원 |
| 1,200,000원 | 1,200,000원 하한 / 50,000원 |

추가 테스트는 정확한 혜택 ID gating, 카드 20/092 및 22/099 적용 제외, 원본 max 조건 불변, 60만원에서 2만원 조합 허용·1만원 조합 거부, 전월 실적 parser와 결제 금액의 분리를 확인한다.

실행한 관련 테스트(작업 디렉터리 `src/card_benefit`):

```text
..\\..\\.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider payment_card/tests/test_p2_limit_tiers.py payment_card/tests/test_tier_null_payout.py payment_card/tests/test_limit_struct.py payment_card/tests/test_limit_struct_backfill.py
54 passed, 1 skipped
```

저장소 루트에서 한 차례 실행한 명령은 `payment_card` import 경로가 없어 두 모듈 수집 단계에서 실패했다. 올바른 `src/card_benefit` 작업 디렉터리에서 위 네 모듈을 재실행해 최종 결과를 확인했다. PostgreSQL, Neo4j, 스키마, 배포는 변경하지 않았고 Commit/Push도 하지 않았다.
