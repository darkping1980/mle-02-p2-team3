# db_pipeline DF/PF 구조 조사

- PC: laptop
- 날짜: 2026-11-04
- 상태: 커밋 전

## 조사 범위

사용자 요청으로 원격 main의 `db_pipeline` README, PROJECT_STATUS, NEO4J_DF_PF_DESIGN 문서만 읽기 전용 확인한 내용을 기록한다. 코드·SQL·DB는 열지 않았다. 이 세션에서는 db_pipeline 경로를 다시 읽지 않았으며, 아래 수치는 요청에 제공된 조사 결과다.

## 조사 결과

- PostgreSQL `db_pipeline` 스키마는 테이블 21개와 뷰 13개를 둔다. 최종 그래프는 Neo4j Aura이며 `df_` 레이블 108노드/189관계, namespace `df_one_pick_style`, 공통 레이블 `df_node`, 제약 `df_node_key`를 사용한다.
- 로컬 브랜치에는 `db_pipeline`이 없고, 원격 main에는 46개 파일과 약 8,800줄이 있다(요청에 제공된 조사 결과).
- `file_pipeline` 스키마는 우리 구현 몫으로 예약됐고 현재 테이블은 0개다. `pf_` 이름은 `pf_node`, `pf_node_key`, namespace `pf_*`로 예약됐다. PF 제약은 PF 모델과 키가 확정된 뒤 팀원이 만든다는 결정이 기록되어 있다(6개 결정).
- 우리 쪽 `pf_*` 범용 테이블 3개는 `public` 스키마에 이미 실행되어 총 4개 테이블이 있고 RLS가 켜져 있다.

### 개념 대응 후보

아래 연결은 원문 문서의 직접 명시가 아니라 두 구조를 비교해 만든 **추정**이다.

| 우리 파일 파이프라인 개념 | PF 이름 후보 |
|---|---|
| Card | `pf_card_product` |
| Benefit | `pf_card_bnft` |
| Limit | `pf_card_limit_pool` |
| Target | `pf_rule_target` |
| Condition | `pf_cond_atom` |
| Evidence | `pf_card_source_evidence` |

`policy_version`, `bnft_rule`, `cond_expr`, `cond_branch`에 대응되는 우리 계층은 없다. 억지로 대응 구조를 만들지 않는다.

### 차이와 중복 기준별 규모

- 그래프 위치는 팀 구조에서 Neo4j Aura 최종이고, 우리 기존 계획은 Supabase/PostgreSQL 1차 적재였다.
- 스키마 위치는 팀 구조에서 PostgreSQL `db_pipeline`, PF 예약은 `file_pipeline` 스키마지만 우리 테이블은 `public`에 실행되어 있다.
- 라벨 표기 역시 `Pf`+CamelCase와 `pf_` snake_case로 다르다.
- 하나카드 혜택 노드 1,474개 기준 중복 제거 후보 효과는 다음과 같다.

| 기준 | 남는 노드 | 제거 수 |
|---|---:|---:|
| 같은 카드 안에서 이름·율·방식 동일 | 1,410 | 64 |
| 카드 간 동일 | 1,074 | 400 |
| 이름만 동일 | 951 | 523 |

같은 이름이지만 율/방식이 다른 항목은 88개다.

## 확인 질문 및 보류

팀원에게 다음을 확인한다.

1. 최종 그래프 저장 위치와 챗봇이 실제 질의할 DB는 Neo4j Aura인가?
2. 우리 `file_pipeline`이 예약된 PostgreSQL 스키마를 사용할 필요가 있는가?
3. PF key와 namespace의 구체 규칙은 무엇인가?
4. 중복 제거는 같은 카드 안, 카드 간, 이름만 동일 중 어느 수준까지 적용할 것인가?
5. 우리 쪽에 없는 policy/rule/condition 계층은 어떻게 다룰 것인가?

Supabase 실제 적재(`--execute`)는 저장 위치와 계약이 확정될 때까지 보류한다.

## 못 한 것

- `db_pipeline` 코드·SQL·DB는 이번 작업에서 읽거나 접속하지 않았다.
- Neo4j Aura와 Supabase 중 실제 적재·챗봇 질의 위치를 확정하지 못했다.

## 다음 할 일

- 팀원 답변을 받은 뒤 그래프 저장소·스키마 위치·PF 키 규칙을 정리한다.
- 결정 전에 DB 쓰기나 실제 적재를 하지 않는다.
