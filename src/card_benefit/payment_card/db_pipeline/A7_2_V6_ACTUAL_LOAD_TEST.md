# A7-2 ONE PICK STYLE 실제 적재 검증

## 현재 상태: 초기화·재등록 및 DRAFT 시험 완료

사용자의 초기화 승인 후 19개 테이블을 비우고 상품·문서·AI 후보와 V6 업무 테이블을 재등록했다. **V6 업무 테이블에 실제 저장됐으나 정책은 DRAFT, 혜택은 PENDING_REVIEW이고 미확정 원문 의미·시험 가정이 있다.** 원문 승인 완료나 Neo4j 운영 변환 준비 완료로 판단하지 않는다. V6 DDL·공통코드·다른 스키마·Storage는 변경하지 않았다.

## 1. 대상과 초기화 전 확인

- 기존 프로젝트 `.env` 설정으로 개발 Supabase PostgreSQL에 연결했고 DB `postgres`, 스키마 `db_pipeline`, 역할 `postgres`를 확인했다. DB의 식별 정보는 백업 manifest에만 두고 접속 비밀정보는 기록하지 않는다.
- 실제 테이블 21개. `card_product`·`card_doc`·`card_product_doc` 각 1건, `card_doc_page`·`card_doc_chunk` 각 2건, `card_ai_run`·`card_ai_call` 각 1건, `card_extr_stg` 8건, `card_source_evidence` 30건이다. 확정 정책·혜택·한도·방법 카탈로그와 공통 혜택 테이블은 0건이다.
- 상품·문서·AI 실행은 ONE PICK STYLE 한 건씩으로 조회됐다. 기존 LLM 응답 원문과 파싱 JSON이 모두 존재하고, 근거 30건의 위치가 존재한다. 관계 `PENDING`, 추출 `PENDING_REVIEW`, evidence `PENDING`을 보존한다.
- `common_code_grp` 44건, `common_cd` 162건. 로컬 V6 Seed의 코드 **키** 162개와 DB 키가 일치한다. 코드 설명·생성자 등 모든 값의 동등성은 전수 확인하지 않았다.
- 카탈로그 기반 외부 스키마 FK 및 일반 의존성 조회에서 대상 테이블을 참조하는 외부 객체는 발견되지 않았다. FK나 카탈로그에 드러나지 않는 외부 서비스의 논리적 의존성까지 없다는 뜻은 아니다. [역할 문서](../../docs/development_roles.md)는 `db_pipeline`과 `file_pipeline`을 독립 처리 경로로 설명한다. 다른 스키마와 Storage는 삭제 대상이 아니다.

## 2. 승인된 초기화 범위와 결과

사용자 승인 후 아래 19개 테이블에 대해 명시적 트랜잭션에서 `TRUNCATE ... RESTRICT`를 실행했다. 실행 전 21개 테이블의 현재 COPY 해시와 백업이 일치하고 시퀀스 13개 상태가 일치함을 확인했다. 19개 테이블의 0건, 공통코드 162/44건 확인 후 COMMIT했다. 스키마·함수·뷰·인덱스와 다른 스키마는 유지했다.

```sql
-- 실행된 대상 구조. 재실행은 별도 승인 필요.
BEGIN;
TRUNCATE TABLE
 db_pipeline.card_ai_call, db_pipeline.card_ai_run,
 db_pipeline.card_bnft, db_pipeline.card_bnft_common,
 db_pipeline.card_common_bnft, db_pipeline.card_common_policy_version,
 db_pipeline.card_common_rule_evidence,
 db_pipeline.card_doc, db_pipeline.card_doc_chunk, db_pipeline.card_doc_page,
 db_pipeline.card_excl_item, db_pipeline.card_extr_stg,
 db_pipeline.card_limit_pool, db_pipeline.card_method_catalog,
 db_pipeline.card_policy_evidence, db_pipeline.card_policy_version,
 db_pipeline.card_product, db_pipeline.card_product_doc,
 db_pipeline.card_source_evidence
 RESTRICT;
-- 성공 검증 후 COMMIT 실행됨.
```

초기화 전 행이 있던 대상은 9개 테이블, 총 47행이었다. `common_code_grp`와 `common_cd` 206행은 보존했고 Seed를 재등록하지 않았다. 사용자 지시에 따라 초기화 COMMIT 후 기존 파이프라인으로 재등록했다. 다른 스키마를 CASCADE하지 않았다.

초기화 시 시퀀스 13개를 초기화·재설정하지 않았다. 재등록은 DEFAULT 발급으로 새 ID를 사용했으므로 사용한 시퀀스 값은 증가했다. DEFAULT 시퀀스 증가는 ROLLBACK되지 않는다.

## 3. 백업과 복원 계획

로컬 백업: `src/data/backup/a72_pre_reset_20261101/manifest.json` 및 21개 테이블의 CSV. 별도 임시 사본도 존재한다. 백업에는 원문·LLM 응답이 포함되므로 팀원과 공유하거나 Git에 포함하기 전에 내용을 검토한다. 프로젝트 `.env`의 주요 비밀값이 파일에 그대로 포함돼 있지 않은지 자동 검사했으나, 이것이 모든 민감정보 부재를 보증하지는 않는다.

- PostgreSQL `REPEATABLE READ READ ONLY` 스냅샷에서 각 테이블을 `COPY ... TO STDOUT` CSV로 내보냈다. 헤더, 행수와 파일 SHA-256을 manifest에 기록했고 21개 파일의 해시를 재확인했다. 생성 컬럼은 복원 가능한 입력 컬럼에서 제외하고 그 목록을 manifest에 남겼다.
- 원본 `card_ai_call.call_resp_raw`와 `call_resp_json`의 JSON을 로컬에서 파싱해 1쪽, 혜택 4개·카드 조건 4개를 확인했다. staging 8건, evidence 30건, 페이지·청크 각 2건을 백업에서 재확인했다.
- 로컬 원본 PDF SHA-256이 DB 문서 해시와 일치했다. Storage PDF 삭제는 계획에 없다.
- **CSV 전체 DB 복원 실행은 시험하지 않았다.** 사용자 지시에 따라 일괄 복원하지 않았으며 CSV는 비상 백업으로 보관한다.

기존 PDF 등록 `RegisterService`를 사용해 문서·페이지·청크를 새로 등록했다. AI는 백업의 실제 응답 원문과 기존 토큰 수를 기존 `TerraClient` 주입 인터페이스의 Mock 응답으로 재생했다. 신규 유료 호출은 없었고 실행 모델은 `REPLAY:gpt-6.1-terra`로 명시했다. 새 call의 원문이 백업과 정확히 일치함을 DB에서 확인했다. 기록된 6,794/6,815토큰은 **원래 실측의 사용량을 재생한 값**이며 이번 재생의 신규 사용량이나 신규 청구액이 아니다.

## 4. 실제 등록 및 검증 결과

| 대상 | 실제 결과 |
|---|---|
| 상품 / 문서 / 연결 | 각 1건. 새 `card_id=2`, `card_doc_id=20261101_000002`; 관계 PENDING |
| 원문 | 페이지 2건, PAGE_V1 청크 2건. 기존 등록 서비스의 검증 통과 |
| AI 후보 | 재생 실행 `20261101_000002`, `PARTIAL`; call 1건, staging 혜택 4건·카드 조건 4건, evidence 30건 |
| 정책·혜택 | 정책 1건 `20261101_000001` DRAFT, 혜택 4건 모두 PENDING_REVIEW. DRAFT rule 총 6건 |
| 한도 | 혜택별 9개 풀: ONE PICK 3, STYLE 3, 교통 1, 놀이공원 2. 1인 1매는 풀로 위장하지 않고 원문 조건 텍스트로만 보존 |
| 방법·근거 관계 | 방법 2건 `UNEXECUTABLE`, 정책 근거 관계 40건. source evidence 30건 모두 PENDING |

**시험 가정:** 실제 정책 적용 시작일은 확인되지 않았다. `valid_from=2026-03-30`은 NOT NULL 구조 시험을 위한 가정값일 뿐이며 출시일이 정책 시작일이라는 주장이나 승인값이 아니다. 9개 풀의 `aggregation_key_cd=CARD_MEMBER`도 현행 필수 코드 구조를 시험하기 위한 미확인 가정이며 원문에서 가족카드 합산을 확인하지 못했다. 이 값은 서비스용 데이터로 사용하면 안 된다. 방법 계약의 `handler_key=TEST_NOT_IMPLEMENTED`, `method_status_cd=UNEXECUTABLE`은 실행되지 않는 테스트 자리표시다. `param_schema`의 object는 검증된 방법별 계약이 아니다.

대중교통 `bnft_cond_expr`는 branch 1 `[transit_spend, spend_exclusions]` OR branch 2 `[transit_grace]`로 저장하고, 교통 제외는 규칙 조건에 별도로 두었다. 조건과 rule JSON 함수는 통과했으나 제외 술어의 의미·NOT 방향과 유예 날짜의 기계적 평가는 아직 검증되지 않았다. `rule_select_cd`는 NULL로 두어 100원·500원 규칙의 우선순위를 임의 확정하지 않았다.

재생한 `card_extr_stg.stg_normalized_item`은 기존 추출 서비스가 다시 생성한 후보이므로 대중교통의 **잘못된 단일 AND branch가 그대로 남아 있다.** 위 OR는 별도 V6 DRAFT 매핑에만 적용했다. staging을 승인하거나 자동 적재 원본으로 사용하면 안 된다.

## 5. SQL 게이트·오류와 해결

- 정책 등록 직후 게이트 0건. 4개 혜택과 9개 풀 등록 후 **`method_not_in_catalog` 2건**이 실제 검출됐다. 방법 카탈로그에 설명용 `UNEXECUTABLE` 2건을 등록하자 0건이 됐다. 이는 코드·버전 존재 검사일 뿐 handler 동작·파라미터 의미를 검증하지 않는다.
- 근거 관계 40건 등록 후 **`evidence_not_approved` 30건**이 실제 검출됐다. source evidence를 승인하지 않았으므로 정상적으로 남긴다. 최종 `pool_ref_orphan` 및 `method_not_in_catalog`는 조회상 없다.
- 오류 주입을 SAVEPOINT로 격리했다. 존재하지 않는 풀 ID를 임시로 넣었을 때 `pool_ref_orphan` 1건, 없는 공통코드를 임시로 넣었을 때 `common_cd_invalid` 1건을 실제 확인하고 각각 ROLLBACK했다. 중복 규칙 키를 `fn_valid_rule_list`에 SELECT로 전달한 결과 false였다. 추가 SQL 오류를 임의로 만들거나 해결했다고 보고하지 않는다.
- 4개 혜택의 `fn_valid_cond_expr`·`fn_valid_rule_list`, 9개 풀의 `fn_valid_tier_list`는 모두 true였다. **형식 통과는 PDF 표 연결, 100/500원 선택, 집계 범위나 날짜 의미의 정확성을 증명하지 않는다.**
- `v_card_bnft_rule_effective`의 LOCAL 경로는 DRAFT 정책·PENDING 혜택을 자동으로 필터링하지 않는다. 향후 조회·그래프 변환은 정책 승인과 혜택 검증 상태를 명시적으로 제한해야 한다.
- 기존 예산 조회는 모델명 `gpt-6.1-terra`만 집계하므로 `REPLAY:gpt-6.1-terra` 행은 제외된다. 과거 실제 호출 비용 $0.040869는 백업 원본에 보존됐고 향후 다른 실측 예산 계산 시 별도로 포함해야 한다. 재생 토큰을 신규 청구로 중복 합산하지 않는다.

## 6. 남은 사항과 Neo4j 준비 여부

`valid_from`과 풀 집계는 위 테스트 가정이며 100원/500원 선택, 1인 1매, 예외·NOT 의미, 원문 표 셀 및 근거 승인이 미완료다. 2쪽은 PDF 원문을 보유하나 LLM 추출하지 않았다. 현재 데이터는 **개발용 DRAFT 사례이며 Neo4j 확정 데이터 변환 준비 완료가 아니다.** DDL 변경 없이 구조·게이트를 시험했으나 날짜 미상과 handler 필수 제약의 MVP 적합성은 개선 후보로 남긴다. V6 설계 변경은 수행하지 않았다.

## 7. A7-4 후속 결과

위 건수는 A7-2 당시 이력이다. 2쪽 부가서비스 유지·변경·고지의 763자를 기존 페이지·청크에서 가져와 PENDING evidence `20261101_000061` 및 POLICY 연결 `20261101_000041`을 추가했다. 커밋 전 원문 부분문자열 일치와 DRAFT 상태를 확인했다. 현재 source evidence 31건, 정책 근거 연결 41건이며 게이트는 `evidence_not_approved` 31건이다. [구조 비교](POSTGRESQL_TO_NEO4J_STRUCTURE_COMPARISON.md)에 실제 SELECT 및 미해결 사항을 기록했다. 이 추가만으로 2쪽 전체 조항의 구조화나 업무 승인을 완료한 것은 아니다.
