# 11단계 file_pipeline 스키마 발견과 매핑 분석

- PC: laptop
- 날짜: 2026-11-04
- 상태: 커밋 전

## 직접 확인

- 사용자가 Supabase SQL Editor에서 실행해 제공한 결과: `information_schema` 조회에서 `file_pipeline`에 `card_ai_call`, `card_doc`, `card_doc_page`가 있고 `doc_sha256` 열 이름을 확인했다. 행 수는 `db_pipeline.card_doc` 23, `db_pipeline.card_doc_page` 55이며 `file_pipeline.card_doc`, `card_doc_page`, `card_ai_call`은 각각 0이다.
- 사용자 제공 객체 목록: `file_pipeline` 테이블 17개(`card_ai_call`, `card_ai_run`, `card_bnft`, `card_common`, `card_common_bnft`, `card_common_bnft_apply`, `card_common_doc`, `card_doc`, `card_doc_chunk`, `card_doc_page`, `card_evidence_link`, `card_extr_stg`, `card_product`, `card_product_doc`, `card_source_evidence`, `common_cd`, `common_code_grp`), 뷰 8개(`v_card_bnft_rel`, `v_card_bnft_rule_effective`, `v_card_brand_opt`, `v_card_cond_atom`, `v_card_integrity_issue`, `v_card_rule`, `v_card_rule_target`, `v_common_cd_usage`).
- 사용자가 `pf_`→`fp_` 마이그레이션을 실행했다고 보고했다. 사용자 보고의 `fp_` 객체 수는 테이블 4, 인덱스 16, 제약 27로 schema.sql 정의에서 센 값과 일치한다.
- 사용자가 Supabase SQL Editor에서 실행한 마이그레이션 검증 결과: 조회 A에서 `public`의 잔여 `pf_` 객체는 0행이었다. 조회 B에서는 `fp_edges`, `fp_evidence`, `fp_load_runs`, `fp_nodes` 4개 테이블 모두 RLS가 `true`였다.
- 사용자가 읽기 전용 겹침 조회로 로컬 문서 SHA-256 206개를 대조한 결과: `db_pipeline`에서 hana/brand_service 15행, hana/product_guide 1행, woori/product_guide 1행이 일치했고 `file_pipeline`에서는 결과 행이 없었다. 쿼리는 `count(*)`를 반환하므로 17은 조인 결과 행 수이며, 고유 해시 수인지는 확인하지 않았다.
- DB 결과는 모두 사용자가 실행해 전달한 것이다. 이 세션에서는 DB에 직접 접속하지 않았다.

## 읽기 전용 DDL·문서 분석

- 지정된 V6 DDL 위치는 `src/card_benefit/sql/db_pipeline_schemaV6_draft.sql`이다. 지정된 V7 파일은 이 작업공간에서 찾지 못했다. V7에서 정책 버전 계층을 제거했고 `card_common*` 4개가 V7 DDL에 없다는 내용은 전달된 분석 사항이며 로컬 파일로 재검증하지 못했다. 해당 `card_common*`는 팀 상태 문서 설명에만 나온다.
- 저장소에서 `db_pipeline`→`file_pipeline` 치환 스크립트를 찾지 못했다. 스키마 생성 경위와 실행 DDL은 미확인이다.
- 역할 요약(DDL 이름·주석 기준): `card_product`는 카드 상품, `card_product_doc`는 상품-문서 연결, `card_doc`·`card_doc_page`·`card_doc_chunk`는 원문 문서·페이지·청크, `card_ai_run`·`card_ai_call`은 AI 실행·호출, `card_extr_stg`는 추출 staging, `card_bnft`는 혜택, `card_source_evidence`는 원천 근거, `card_common*`는 공통 혜택/문서 계약 후보, `common_cd`·`common_code_grp`는 공통 코드로 대응한다.

### 우리 추출 결과 매핑 후보

| 추출 결과 | `file_pipeline` 후보 | 판단 |
|---|---|---|
| 문서·페이지·청크 | `card_doc` / `card_doc_page` / `card_doc_chunk` | 개념 호환 가능, 키·열 변환 필요 |
| AI 실행·호출 | `card_ai_run` / `card_ai_call` | 실행 메타데이터 매핑 후보 |
| 추출 JSON | `card_extr_stg.stg_raw_item` | staging 용도·`stg_kind_cd` 확인 필요 |
| 혜택 및 조건 | `card_bnft` | JSON 구조와 승인·정책 계약 차이로 대규모 변환 필요 |
| 근거 | `card_source_evidence` | 좌표 호환 가능성, 연결 규칙 확인 필요 |
| 공통 브랜드 | `card_common*` | 컬럼 계약·승인 절차 확인 필요 |
| 상품 연결 | `card_product` / `card_product_doc` | 상품 키·문서 ID·승인 정보 변환 필요 |

### 간극과 원칙

- 지금 만들 수 있는 것: 추출 결과의 읽기 전용 매핑 계획과 문서·페이지·청크 3개 테이블 변환기의 출력 계획.
- 사람 승인이 필요한 것: 대상 스키마·테이블 선택, 상품/브랜드 연결, 승인 상태와 적용 근거, 적재 실행.
- 구조 변환이 필요한 것: 문서·페이지·청크 키, 상품 ID, 혜택/조건 JSON, staging 종류, 근거 좌표 및 관계.
- 넣지 말 것: 미검토 추출 후보를 확정 테이블에 넣지 않는다. 승인 상태와 적용 근거를 추측해 채우지 않는다. DDL 변경은 별도 승인 전 진행하지 않는다.

### 방향 비교(작업량은 추정)

| 방향 | 개요 | 작업량 추정 |
|---|---|---:|
| 가 | `public.fp_*`를 샌드박스로 유지하고 챗봇 시험 후 계약 합의 뒤 이관 | 250–500줄 |
| 나 | `file_pipeline`에 문서 계층부터 직접 적재 | 250–450줄 |
| 다 | 추출·혜택·공통 계약까지 한 번에 이관 | 400–700줄 |

추천은 가다. 우선 `public.fp_*`에서 챗봇을 시험하고, 첫 이관은 문서·페이지·청크 3개 테이블 변환기로 제한한다. 변환기는 쓰기 없이 계획 출력부터 만든다.

## 팀원 확인 질문 (사용자 요청으로 보류, 미발송)

1. 이 스키마는 누가, 언제, 어떤 DDL로 만들고 실행했나? V6/V7 중 기준 DDL은 무엇인가?
2. 적재 주체는 누구이며 문서 ID 발급·중복 문서 처리·계정 권한은 어떻게 정하나?
3. `card_extr_stg`의 용도, `stg_kind_cd` 값, 근거 좌표 규칙은 무엇인가?
4. `card_common*` 컬럼 계약과 승인 절차는 무엇인가?
5. 팀 합의 전 `public.fp_*`를 샌드박스로 사용해도 되는가?

우리카드 브랜드 서비스 대표 5개와 중복 8개 정리본은 사용자가 Drive 폴더에 올려 두었다고 알려 주었다. 폴더 이름 외 계정·폴더 ID·링크는 이력에 기록하지 않는다.

## 결정 및 미실행

- 결정: 현재는 사용자 승인 후 단계별로 `public.fp_*`에 하나카드를 적재해 챗봇 시험을 진행한다. `file_pipeline` 이관은 팀원 답변 후 결정한다.
- 확인: 마이그레이션 검증 A·B와 문서 겹침 조회 결과를 사용자에게서 받았다. A는 `pf_` 잔여 0행, B는 `fp_*` 4개 테이블 RLS 활성, 겹침은 `db_pipeline` 조인 결과 17행이며 `file_pipeline` 결과 행은 없었다.
- 미실행: 하나카드 적재 및 실제 DB 접속. 팀원 확인 메시지는 사용자 요청으로 보류했으며 발송하지 않았다.

## 다음 할 일

- 사용자 요청으로 보류 중인 팀원 확인 메시지는 재개 지시 후 발송하고 답변을 확인한다. 겹침 수치는 중복 문서 처리 질문에 참고한다.
- 승인 후 드라이런으로 문서·페이지·청크 변환 계획을 검토하고, 별도 승인 전 쓰지 않는다.
