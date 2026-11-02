-- V6 공통코드 상세 설명 등록. db_pipeline_common_code_seedV6.sql 실행 후 적용한다.
-- 컬럼 추가와 설명 UPDATE만 수행하며 코드값, 코드명, 등록·수정 정보는 바꾸지 않는다. 반복 실행해도 결과가 같다.
-- 설명 대상 키가 DB에 없으면 예외로 전체를 롤백한다. 시드에 없는 코드를 만들지 않는다.
-- 근거: V6 DDL과 뷰, db_pipeline Python 로직, V5 설계 문서, 수집 PDF 원문.
--
-- 의미 미확정으로 설명을 등록하지 않은 코드(common_cd_desc NULL 유지):
--   REL_TYPE.OVERRIDES       적용 사례가 없고 HIGHER_VALUE_WINS와의 구별 기준이 없음. 설계안은 trigger_pool_id를
--                            필수로 보지만 fn_valid_relation_list는 FALLBACK_AFTER_CAP에만 강제함.
--   SERVICE_GRADE.PRESTIGE   JCB 안내서 JP002가 JCB Platinum과 JCB Prestige를 같은 문서에서 혼용함.
--                            독립 등급인지 PLATINUM의 다른 표기인지 확인되지 않음.

BEGIN;

ALTER TABLE db_pipeline.common_code_grp ADD COLUMN IF NOT EXISTS common_code_grp_desc text;
ALTER TABLE db_pipeline.common_cd ADD COLUMN IF NOT EXISTS common_cd_desc text;

COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_desc IS '공통코드 그룹 상세 설명(목적, 사용 범위, 업무 의미)';
COMMENT ON COLUMN db_pipeline.common_cd.common_cd_desc IS '공통코드 상세 설명(업무 의미, 적용 기준)';

CREATE TEMP TABLE tmp_common_code_grp_desc (
    common_code_grp_id varchar(20) PRIMARY KEY,
    common_code_grp_desc text NOT NULL
) ON COMMIT DROP;

CREATE TEMP TABLE tmp_common_cd_desc (
    common_code_grp_id varchar(20) NOT NULL,
    common_cd varchar(40) NOT NULL,
    common_cd_desc text NOT NULL,
    PRIMARY KEY (common_code_grp_id, common_cd)
) ON COMMIT DROP;

INSERT INTO tmp_common_code_grp_desc (common_code_grp_id, common_code_grp_desc) VALUES
    ('CARD_KIND', '카드 상품의 결제 성격을 신용카드와 체크카드로 구분하는 공통코드. card_product.card_kind_cd에서 사용하며 상품 조회와 필터의 기준이 된다. 상품의 판매 상태를 나타내는 PRODUCT_STATUS, 국제 브랜드를 나타내는 BRAND와는 별개의 축이다.'),
    ('PRODUCT_STATUS', '카드 상품과 상품 안의 브랜드 선택지가 현재 판매되는지를 구분하는 공통코드. card_product.product_status_cd와 card_product.brand_opt_list[].brand_opt_status_cd에서 사용한다. 데이터 처리 상태가 아니라 판매 사실을 나타낸다는 점에서 문서 상태 DOC_STATUS, 방법 실행 상태 METHOD_STATUS의 같은 값 ACTIVE와 구분된다.'),
    ('DOC_ROLE', '원천 문서가 특정 상품이나 정책판에서 어떤 역할을 하는지 구분하는 공통코드. card_product_doc.doc_role_cd와 card_policy_version.source_doc_list[].source_role_cd에서 사용한다. 문서 자체의 종류를 나타내는 DOC_TYPE과 달리 상품·정책과의 관계에 붙는 값이므로 같은 문서라도 연결 대상에 따라 역할을 따로 기록한다.'),
    ('APPROVAL_STATUS', '문서 연결, 공통 혜택 적용, 원문 근거처럼 검토·승인이 필요한 관계·근거 데이터의 처리 상태를 구분하는 공통코드. card_product_doc.approval_status_cd, card_bnft_common.apply_status_cd, card_source_evidence.approval_status_cd에서 사용하며 실제 승인 대상은 사용하는 테이블에 따라 달라진다. 정책판 전체를 다루는 POLICY_STATUS, 규칙·조건을 다루는 ITEM_STATUS, AI 추출 항목을 다루는 STG_STATUS와 관리 대상이 다르다.'),
    ('POLICY_STATUS', '상품 정책판과 공통 혜택 정책판의 생명주기를 구분하는 공통코드. card_policy_version.policy_status_cd와 card_common_policy_version.policy_status_cd에서 사용한다. 개별 규칙·조건이 아니라 적용 기간을 가진 정책판 단위의 상태이며, 개별 항목의 상태는 ITEM_STATUS로, 관계·근거의 승인은 APPROVAL_STATUS로 관리한다.'),
    ('ITEM_STATUS', '계산 규칙과 조건식이 작성 중인지 확정되었는지를 구분하는 공통코드. JSONB 안의 rule_status_cd, cond_status_cd, expr_status_cd에서 사용한다. 정책판 단위의 POLICY_STATUS보다 작은 규칙·조건 단위의 상태이고, 혜택 단위 검증을 나타내는 VERIFY_STATUS와도 구분된다.'),
    ('VERIFY_STATUS', '혜택 내용이 원문과 대조되어 검증되었는지를 구분하는 공통코드. card_bnft.verification_status_cd에서 사용한다. 혜택 1건 단위의 검증 여부만 나타내며, 그 안의 규칙·조건 확정은 ITEM_STATUS, AI 추출 단계의 승인은 STG_STATUS가 맡는다.'),
    ('BNFT_TYPE', '혜택이 고객에게 제공되는 형태를 분류하는 공통코드. card_bnft.bnft_type_cd에서 사용하며 AI 추출 스키마의 혜택 유형 값도 이 그룹을 따른다. 보상 계산법을 나타내는 CALC_METHOD나 지급 단위를 나타내는 PAYOUT_UNIT과 달리 혜택의 업무상 종류를 나타낸다.'),
    ('BNFT_ORIGIN', '혜택의 계산 규칙이 어디에 있는지를 구분하는 공통코드. card_bnft.bnft_origin_cd에서 사용하며 v_card_bnft_rule_effective가 규칙을 읽어올 경로를 이 값으로 결정한다. 혜택이 어느 브랜드 선택지에 적용되는지를 나타내는 BNFT_SCOPE와는 별개의 축이다.'),
    ('BNFT_SCOPE', '혜택이 상품 전체에 적용되는지 일부 브랜드 선택지에만 적용되는지를 구분하는 공통코드. card_bnft.bnft_scope_cd에서 사용하며 bnft_brand_opt_cds의 필수 여부를 결정한다. 규칙의 출처를 나타내는 BNFT_ORIGIN과 달리 혜택을 받을 수 있는 상품 선택지의 범위를 나타낸다.'),
    ('RULE_SELECT', '한 혜택 안에서 같은 거래에 여러 계산 규칙이 해당할 때 어떤 규칙을 적용할지 정하는 공통코드. card_bnft.rule_select_cd에서 사용하고, 값이 NULL이면 선택 방식이 아직 확정되지 않은 상태다. 혜택과 혜택 사이의 관계를 다루는 REL_TYPE과 달리 한 혜택 내부의 규칙 선택만 다룬다.'),
    ('PREDICATE_STATE', '규칙이나 한도 구간의 적용 여부를 조건식으로 어떻게 판정할지 구분하는 공통코드. rule_list[]와 limit_list[]의 predicate_state_cd, card_limit_pool.tier_list[].predicate_state_cd에서 사용한다. 조건식이 없다는 사실만으로 무조건 적용으로 해석하지 않도록, 원문으로 확인된 무조건과 미검토를 구분한다.'),
    ('METHOD_KIND', 'card_method_catalog에 등록된 방법이 보상 계산용인지 조건 판정용인지 구분하는 공통코드. card_method_catalog.method_kind_cd에서 사용하며 method_cd가 속할 코드 그룹(CALC_METHOD 또는 PREDICATE_METHOD)을 결정한다.'),
    ('METHOD_STATUS', '방법 카탈로그의 버전별 실행 계약이 실제로 실행 가능한지를 구분하는 공통코드. card_method_catalog.method_status_cd에서 사용한다. 정책을 표현할 수 있는지와 거래별 계산을 실행할 수 있는지는 별개라는 설계 원칙을 나타내는 값이며, 업무 승인 상태가 아니다.'),
    ('CALC_METHOD', '규칙이 한 거래의 후보 보상을 어떤 방식으로 산출하는지 구분하는 공통코드. rule_list[].calc_method_cd와 card_method_catalog.method_cd(CALC)에서 사용하고, 코드별 value_num의 의미가 정해져 있다. 조건 판정 방법인 PREDICATE_METHOD와 구분되며, 버전별 파라미터와 핸들러는 card_method_catalog에서 관리한다.'),
    ('PREDICATE_METHOD', '금액 구간만으로 표현되지 않는 조건을 판정하는 방법을 구분하는 공통코드. 조건 atom의 predicate_method_cd와 card_method_catalog.method_cd(PREDICATE)에서 사용하며 세부 값은 cond_params에 둔다. 보상 금액을 산출하는 CALC_METHOD와 달리 조건의 참·거짓만 판정한다.'),
    ('VALUE_UNIT', '계산 규칙의 입력값 value_num이 어떤 단위인지 구분하는 공통코드. rule_list[].value_unit_cd에서 사용한다. 고객이 실제로 받는 단위를 나타내는 PAYOUT_UNIT, 한도의 단위를 나타내는 LIMIT_UNIT과 구분되며, 예를 들어 값은 PERCENT이고 보상은 KRW일 수 있다.'),
    ('PAYOUT_UNIT', '고객이 혜택으로 실제 받는 보상의 단위를 구분하는 공통코드. rule_list[].payout_unit_cd에서 사용한다. 계산 입력값의 단위인 VALUE_UNIT, 누적 한도의 단위인 LIMIT_UNIT과 구분된다.'),
    ('LIMIT_SCOPE', '한도 풀이 어느 범위의 혜택을 묶어 누적하는지 구분하는 공통코드. card_limit_pool.pool_scope_cd에서 사용한다. 한도의 시간 범위인 LIMIT_PERIOD, 누적 주체인 LIMIT_AGG와 구분되며, 같은 금액의 한도라도 범위가 다르면 다른 풀이다.'),
    ('LIMIT_PERIOD', '한도가 누적되는 시간 단위를 구분하는 공통코드. card_limit_pool.period_cd와 공통 규칙의 limit_list[].period_cd에서 사용한다. 한도를 묶는 혜택 범위인 LIMIT_SCOPE, 한도의 단위인 LIMIT_UNIT과 함께 한도 하나를 정의한다.'),
    ('LIMIT_UNIT', '한도 수치 limit_num이 어떤 단위인지 구분하는 공통코드. card_limit_pool.cap_unit_cd와 공통 규칙의 limit_list[].cap_unit_cd에서 사용한다. 보상 지급 단위인 PAYOUT_UNIT과 달리 금액뿐 아니라 이용 횟수도 포함한다.'),
    ('LIMIT_AGG', '한도 사용액을 어떤 주체 단위로 합산할지 구분하는 공통코드. card_limit_pool.aggregation_key_cd와 공통 규칙의 limit_list[].aggregation_key_cd에서 사용한다. 어떤 혜택을 묶는지를 나타내는 LIMIT_SCOPE와 달리 누구의 사용분을 합칠지를 나타낸다.'),
    ('POOL_ROLE', '계산 규칙이 연결된 한도 풀을 어떤 역할로 소비하는지 구분하는 공통코드. card_bnft.rule_list[].pool_refs[].pool_role_cd에서 사용한다. 한 규칙이 영역 한도와 카드 통합 한도를 동시에 소비하는 구조를 표현하기 위한 값이며, 풀 자체의 범위는 LIMIT_SCOPE가 정한다.'),
    ('REL_TYPE', '서로 다른 혜택 사이의 적용 관계를 구분하는 공통코드. card_bnft.relation_list[].rel_type_cd에서 사용하며 v_card_bnft_rel로 조회한다. 한 혜택 내부의 규칙 선택을 다루는 RULE_SELECT와 달리 혜택 간 배타, 우선, 대체를 다룬다.'),
    ('COND_TYPE', '조건식 atom의 업무 유형을 분류하는 공통코드. 조건식 atom의 cond_type_cd에서 사용하고 정책, 혜택, 규칙, 한도 구간의 조건에 모두 적용된다. 금액을 어떤 기준으로 비교하는지는 COND_BASIS가, 금액 구간으로 표현되지 않는 판정법은 PREDICATE_METHOD가 맡는다.'),
    ('COND_BASIS', '조건의 금액 구간이 어떤 금액을 기준으로 비교되는지 구분하는 공통코드. 조건식 atom의 cond_basis_cd에서 사용하며, 실적 요건 SPEND_REQ에서는 필수다. 조건의 유형을 나타내는 COND_TYPE과 달리 비교 대상 금액의 정의만 나타낸다.'),
    ('TARGET_TYPE', '계산 규칙의 혜택 대상이 어떤 종류인지 구분하는 공통코드. rule_list[].target_list[].target_type_cd에서 사용하고 AI 추출 스키마의 대상 유형도 이 그룹을 따른다. 대상별 비율은 두지 않으며, 비율이 다르면 규칙을 나눈다.'),
    ('BRAND', '카드 상품의 브랜드 선택지와 공통 혜택 제공 주체를 구분하는 공통코드. card_product.brand_opt_list[].brand_cd와 card_common_bnft.provider_cd에서 사용한다. 그룹명은 국제 브랜드이지만 국내전용 선택지를 함께 포함하며, 브랜드 안의 등급은 SERVICE_GRADE, 선택서비스 유형은 SERVICE_TYPE이 구분한다.'),
    ('SERVICE_GRADE', '국제 브랜드 서비스의 등급을 구분하는 공통코드. card_product.brand_opt_list[].service_grade_cd와 card_common_bnft.service_grade_cd에서 사용한다. BRAND와 조합해야 의미가 정해지며, 등급 안의 공통·선택서비스 구분은 SERVICE_TYPE이 맡는다.'),
    ('SERVICE_TYPE', '같은 브랜드와 등급 안에서 제공되는 서비스 묶음의 유형을 구분하는 공통코드. card_product.brand_opt_list[].service_type_cd와 card_common_bnft.service_type_cd에서 사용한다. 번호 코드는 BRAND, SERVICE_GRADE와 조합할 때만 의미가 정해지며 어떤 상품이 어떤 유형인지는 브랜드 서비스 안내서의 대상카드 표를 따른다.'),
    ('EV_SUBJECT', '원문 근거가 어떤 정책 대상을 뒷받침하는지 구분하는 공통코드. card_policy_evidence.ev_subject_cd에서 사용하며 값에 따라 card_bnft_id, rule_key, relation_key, pool_id 중 채워야 할 컬럼이 CHECK로 고정된다. 대상 안의 세부 항목은 EV_ITEM이 구분한다.'),
    ('EV_ITEM', '근거가 대상 전체를 가리키는지 대상 안의 JSONB 항목을 가리키는지 구분하는 공통코드. card_policy_evidence.ev_item_cd와 card_common_rule_evidence.ev_item_cd에서 사용하고 ev_item_key와 짝을 이룬다. 대상의 종류를 나타내는 EV_SUBJECT보다 한 단계 아래를 가리킨다.'),
    ('DOC_TYPE', '원천 문서 자체의 종류를 구분하는 공통코드. card_doc.doc_type_cd에서 사용한다. 상품·정책과의 관계에서 부여되는 DOC_ROLE과 달리 문서 파일의 성격을 나타내며, 현재 문서 등록 프로그램은 상품설명서를 등록한다.'),
    ('DOC_STATUS', '수집된 원천 문서를 파이프라인에서 사용할지 구분하는 공통코드. card_doc.doc_status에서 사용하며 AI 입력 대상은 ACTIVE 문서로 제한된다. 상품별 현재 적용 여부는 이 값이 아니라 승인된 문서 관계의 기간으로 판정하며, 판매 상태를 나타내는 PRODUCT_STATUS와도 구분된다.'),
    ('PAGE_LAYER', 'PDF 페이지의 텍스트 레이어 상태를 구분하는 공통코드. card_doc_page.page_layer_cd에서 사용하며 문서 등록 프로그램이 텍스트와 시각 요소의 존재 여부로 판정한다. 페이지 추출 결과의 신뢰도를 판단하는 정보이고, 청크의 내용 분류인 CHUNK_TYPE과 구분된다.'),
    ('CHUNK_TYPE', '문서 청크의 내용 형식을 구분하는 공통코드. card_doc_chunk.chunk_type_cd에서 사용한다. 처리 단계를 나타내는 CHUNK_STATUS와 구분되며, 현재 프로그램은 페이지 전체를 청크 1건으로 나누므로 기본값 BODY로 등록한다.'),
    ('CHUNK_STATUS', '문서 청크의 처리 단계와 AI 입력 가능 여부를 구분하는 공통코드. card_doc_chunk.chunk_status에서 사용하며 RAW와 CLEANED만 AI 입력 대상이 된다. 내용 형식을 나타내는 CHUNK_TYPE, 문서 전체 사용 여부를 나타내는 DOC_STATUS와 구분된다.'),
    ('RUN_STAGE', 'AI 실행 회차가 어느 처리 단계인지 구분하는 공통코드. card_ai_run.run_stage_cd에서 사용한다. 실행 결과를 나타내는 RUN_STATUS와 구분되며, 추출과 의미 검증을 서로 다른 실행 이력으로 남기기 위한 값이다.'),
    ('RUN_CALL_METHOD', 'AI 모델을 어떤 기술 경로로 호출했는지 구분하는 공통코드. card_ai_run.run_call_mthd_cd에서 사용한다. 호출 방식이 설계 단계에서 확정되지 않아 후보를 값으로 기록하도록 만들어졌으며, 실행 단계를 나타내는 RUN_STAGE와 구분된다.'),
    ('RUN_STATUS', 'AI 실행 회차 전체의 진행과 결과를 구분하는 공통코드. card_ai_run.run_status에서 사용한다. 페이지·청크 1건의 호출 결과를 나타내는 CALL_STATUS를 모은 실행 단위 상태이며, 문서 통합 저장 여부와 AI 입력 제외 페이지까지 반영한다.'),
    ('CALL_STATUS', 'AI 호출 1건의 결과를 구분하는 공통코드. card_ai_call.call_status에서 사용한다. 실행 회차 전체의 결과인 RUN_STATUS보다 작은 단위이며, 추출 내용이 맞는지가 아니라 응답을 받아 구조화하는 데 성공했는지만 나타낸다.'),
    ('STG_KIND', 'AI 추출 staging 항목의 종류를 구분하는 공통코드. card_extr_stg.stg_kind_cd에서 사용한다. 추출 단계의 항목 구분이며, 확정 혜택의 종류를 나타내는 BNFT_TYPE이나 조건 유형 COND_TYPE과 구분된다.'),
    ('STG_STATUS', 'AI 추출 항목의 검토·승인 결과를 구분하는 공통코드. card_extr_stg.stg_status에서 사용한다. 항목의 최종 처리 상태이며 원문 검증 결과 stg_sql_check_cd, AI 의미 검증 결과 STG_AI_VRFY와 분리해서 기록한다. 관계·근거의 승인을 다루는 APPROVAL_STATUS와도 구분된다.'),
    ('STG_AI_VRFY', 'AI가 추출 항목의 의미를 원문과 대조해 판정한 결과를 구분하는 공통코드. card_extr_stg.stg_ai_vrfy_cd에서 사용하며 NULL이면 의미 검증을 실행하지 않은 상태다. 형식·근거 위치를 확인하는 stg_sql_check_cd와 분리해 기록하고, 최종 승인 여부인 STG_STATUS를 대신하지 않는다.');

INSERT INTO tmp_common_cd_desc (common_code_grp_id, common_cd, common_cd_desc) VALUES
    ('CARD_KIND', 'CREDIT', '이용대금을 나중에 결제하는 신용카드 상품. 신용카드 개인회원 표준약관을 적용받는다는 점에서 체크카드 약관을 적용받는 DEBIT와 구분된다.'),
    ('CARD_KIND', 'DEBIT', '결제 계좌 잔액 범위에서 이용하는 체크카드 상품. 원문의 상품명에 체크카드로 표기되고 신용카드 약관이 아닌 체크카드 약관을 적용받는다는 점에서 CREDIT와 구분된다.'),
    ('PRODUCT_STATUS', 'ACTIVE', '상품 또는 브랜드 선택지가 판매 중인 상태. 상품 등록의 기본값이다. 데이터 사용 가능 여부가 아닌 판매 사실을 나타내므로 DOC_STATUS.ACTIVE(문서 사용 중), METHOD_STATUS.ACTIVE(실행 가능)와 의미가 다르다.'),
    ('PRODUCT_STATUS', 'DISCONTINUED', '상품 또는 브랜드 선택지의 판매가 중단된 상태. 상품에서는 discontinued_on에 중단일을 기록한다. 판매 사실만 나타내므로 정책이나 문서의 사용 가능 여부는 각자의 상태 코드로 판단한다.'),
    ('DOC_ROLE', 'PRODUCT_GUIDE', '문서가 해당 상품의 혜택과 조건을 설명하는 상품설명서 역할을 하는 경우. 상품별 혜택 추출의 기본 원천이며, 여러 상품에 공통 적용되는 COMMON_TERMS와 달리 해당 상품을 직접 설명한다.'),
    ('DOC_ROLE', 'COMMON_TERMS', '여러 상품에 공통으로 적용되는 약관이 해당 상품에 연결되는 경우. 신용카드 개인회원 표준약관, 체크카드 개인회원 약관처럼 특정 상품의 혜택표가 아니라 공통 이용 조건을 규정한다. 관계 코드이며 문서 자체의 종류는 DOC_TYPE.TERMS로 기록한다.'),
    ('DOC_ROLE', 'BRAND_SERVICE', '국제 브랜드 서비스 안내서가 상품의 특정 브랜드 선택지에 적용되는 경우. card_product_doc에서 이 역할은 brand_opt_cds가 필수이므로(card_product_doc_brand_check) 어느 선택지에 적용되는 문서인지 지정해야 한다.'),
    ('DOC_ROLE', 'OTHER', '상품설명서, 공통 약관, 브랜드 서비스 안내 어디에도 해당하지 않는 문서 역할. 역할을 판단하지 못한 경우가 아니라 정의된 세 역할 밖의 문서를 연결할 때 사용한다. DOC_TYPE의 기타 코드는 ETC로 값이 다르다.'),
    ('APPROVAL_STATUS', 'PENDING', '대상 문서 연결, 공통 혜택 적용 또는 원문 근거의 정확성과 적용 여부에 대한 검토가 끝나지 않은 상태. 업무 사용 승인 전 단계이며 card_product_doc의 기본값이다. 이 상태의 근거가 정책에 연결되어 있으면 게이트 evidence_not_approved에서 검출된다.'),
    ('APPROVAL_STATUS', 'APPROVED', '대상 데이터가 해당 업무의 검증 기준을 충족해 사용 승인을 받은 상태. 문서 연결은 적용 시작일과 적용 근거가 있어야 승인할 수 있고, 공통 혜택 적용은 이 값일 때만 v_card_bnft_rule_effective에 포함된다. 승인 대상과 범위는 사용하는 테이블에 따라 결정된다.'),
    ('APPROVAL_STATUS', 'REJECTED', '대상 데이터가 검증 기준을 충족하지 못하거나 근거가 부적절해 승인을 거부한 상태. 검토를 마쳤다는 점에서 PENDING과 다르며, APPROVED만 인정하는 조회와 근거 게이트를 통과하지 못한다.'),
    ('POLICY_STATUS', 'DRAFT', '정책판을 작성하거나 검토하는 중인 상태. 내용과 적용 기간이 아직 확정되지 않았으므로 확정 정책으로 사용하면 안 된다. 개별 규칙의 작성 상태는 ITEM_STATUS.DRAFT로 따로 관리한다.'),
    ('POLICY_STATUS', 'APPROVED', '정책판이 승인되어 적용 기간 동안 유효한 상태. 같은 상품의 승인 정책은 기간이 겹치면 게이트 policy_period_overlap에서 검출되고, 공통 정책판은 이 값일 때만 v_card_bnft_rule_effective에 포함된다. 관계·근거 승인 APPROVAL_STATUS.APPROVED와는 관리 단위가 다르다.'),
    ('POLICY_STATUS', 'RETIRED', '정책판을 더 이상 적용하지 않기로 폐기한 상태. APPROVED 정책판을 찾는 조회에서 제외되며, 작성이 끝나지 않은 DRAFT와 달리 사용을 종료한 정책판을 나타낸다.'),
    ('ITEM_STATUS', 'DRAFT', '규칙 또는 조건이 작성 중이라 아직 확정되지 않은 상태. AI 추출 결과를 정규화할 때 부여하는 초기값이다. 정책판 전체가 아니라 JSONB 안의 항목 단위 상태다.'),
    ('ITEM_STATUS', 'CONFIRMED', '규칙 또는 조건의 내용이 확정된 상태. 규칙은 이 값이면 target_list가 비어 있을 수 없고(fn_valid_rule_list), 현재 적용 규칙 조회의 대상이 된다. 혜택 단위 검증 완료인 VERIFY_STATUS.CONFIRMED와는 관리 단위가 다르다.'),
    ('ITEM_STATUS', 'RETIRED', '규칙 또는 조건을 더 이상 사용하지 않기로 폐기한 상태. 문서 개정 등으로 대체되어 사용이 끝난 항목을 이력으로 남길 때 쓴다. 아직 확정 전인 DRAFT와 구분된다.'),
    ('VERIFY_STATUS', 'PENDING_REVIEW', '혜택이 등록되었지만 원문 대조 검증이 끝나지 않은 상태. AI 추출 결과를 정규화할 때 부여하는 초기값이다. 같은 코드값을 쓰는 PREDICATE_STATE, STG_STATUS와 달리 card_bnft 혜택 행의 검증 상태만 나타낸다.'),
    ('VERIFY_STATUS', 'CONFIRMED', '혜택 내용이 원문과 대조되어 검증을 마친 상태. LOCAL 혜택이 이 값인데 규칙이 없으면 게이트 local_confirmed_without_rule에서 검출된다. 규칙·조건 단위의 ITEM_STATUS.CONFIRMED와는 관리 단위가 다르다.'),
    ('BNFT_TYPE', 'DISCOUNT', '결제금액을 현장 또는 청구 단계에서 낮춰 주는 혜택. 놀이공원 현장할인, 청구할인이 해당한다. 원문이 할인으로 정의한 경우에 쓰며, 결제 후 돌려받는 CASHBACK이나 포인트로 쌓이는 POINT와 구분된다.'),
    ('BNFT_TYPE', 'CASHBACK', '결제 후 금전으로 돌려주는 혜택. 원문이 캐시백으로 정의한 ONE PICK, 대중교통 캐시백이 해당한다. 결제금액 자체를 낮추는 DISCOUNT, 포인트로 지급하는 POINT와 구분된다.'),
    ('BNFT_TYPE', 'POINT', '이용금액에 따라 하나머니나 UniMile 같은 포인트·마일리지를 적립해 주는 혜택. 실제 지급 단위는 규칙의 payout_unit_cd에 기록한다. 금전으로 지급하는 CASHBACK과 구분된다.'),
    ('BNFT_TYPE', 'FEE_WAIVER', '연회비나 수수료 같은 비용을 면제해 주는 혜택. 결제금액에 대한 보상이 아니라 카드 이용에 드는 비용을 없앤다는 점에서 DISCOUNT와 구분된다.'),
    ('BNFT_TYPE', 'SERVICE', '공항 라운지, 발렛파킹처럼 금전 보상이 아니라 서비스 이용 자체를 제공하는 혜택. 결제금액을 낮추는 DISCOUNT나 금전·포인트를 지급하는 CASHBACK, POINT와 구분된다.'),
    ('BNFT_TYPE', 'INSTALLMENT', '할부 이자를 받지 않는 무이자 할부 혜택. 할부 결제 조건을 바꾸는 혜택으로, 수수료·연회비 면제인 FEE_WAIVER와 별도로 분류한다.'),
    ('BNFT_TYPE', 'ETC', '정의된 혜택 유형 어디에도 해당하지 않는 혜택. 추출 단계의 UNKNOWN은 유형을 판단하지 못한 임시값이고 이 코드는 유형을 판단한 결과이므로 구분해서 쓴다.'),
    ('BNFT_ORIGIN', 'LOCAL', '상품 정책판의 card_bnft.rule_list에 계산 규칙을 직접 가진 혜택. 상품 고유 혜택이 해당하고 현재 추출기는 모든 혜택을 이 값으로 정규화한다. 공통 정책판을 참조하는 COMMON_LINK와 달리 규칙이 상품에 귀속된다.'),
    ('BNFT_ORIGIN', 'COMMON_LINK', '자체 규칙 없이 card_bnft_common으로 공통 혜택 정책판의 규칙을 사용하는 혜택. rule_list가 비어 있어야 하고(card_bnft_ck_5), 연결이 없으면 게이트 common_link_without_link에서 검출된다. 브랜드 서비스처럼 여러 상품이 같은 규칙을 공유할 때 쓴다.'),
    ('BNFT_SCOPE', 'PRODUCT', '상품의 모든 브랜드 선택지에 적용되는 혜택. 이 값이면 bnft_brand_opt_cds는 NULL이어야 한다(card_bnft_ck_1). 현재 추출기가 부여하는 기본값이다.'),
    ('BNFT_SCOPE', 'BRAND', 'bnft_brand_opt_cds에 지정한 브랜드 선택지에만 적용되는 혜택. 지정 선택지가 1개 이상 있어야 하며(card_bnft_ck_1), 같은 상품이라도 브랜드나 서비스 유형에 따라 제공 여부가 달라질 때 쓴다. 코드값이 같은 BRAND 그룹과는 다른 의미다.'),
    ('RULE_SELECT', 'EXCLUSIVE_BY_SCOPE', '규칙들의 적용 범위가 서로 겹치지 않아 한 거래에 하나의 규칙만 해당하는 방식. 전월 실적 40만원 미만 1%, 이상 2%처럼 구간이 배타적인 경우다. 겹침을 해소하는 PRIORITY, MAX_BENEFIT_VALUE와 달리 애초에 겹침이 없음을 뜻한다.'),
    ('RULE_SELECT', 'PRIORITY', '규칙이 겹칠 때 rule_priority로 적용 순서를 정하는 방식. 원문에 우선 규칙이 명시된 경우에만 쓰며, 근거가 없으면 임의로 우선순위를 만들지 않는다. 보상 크기로 고르는 MAX_BENEFIT_VALUE와 구분된다.'),
    ('RULE_SELECT', 'MAX_BENEFIT_VALUE', '규칙이 겹칠 때 보상이 큰 규칙 하나를 적용하는 방식. 원문이 적립금액이 큰 서비스 우선 적용으로 명시한 경우에 쓴다. 한 혜택 안의 규칙을 고른다는 점에서 혜택 간 관계인 REL_TYPE.HIGHER_VALUE_WINS와 구분된다.'),
    ('PREDICATE_STATE', 'CONDITIONAL', '조건식을 평가해야 적용 여부가 결정되는 상태. 이 값이면 cond_expr가 반드시 있어야 하며, 없으면 fn_valid_* 검증에서 거부된다.'),
    ('PREDICATE_STATE', 'VERIFIED_UNCONDITIONAL', '원문을 확인한 결과 조건 없이 적용되는 상태. 이 값이면 cond_expr가 없어야 한다. 조건식이 비어 있을 때 무조건으로 해석할 수 있는 유일한 값으로, 조건이 아직 파악되지 않은 PENDING_REVIEW와 구분된다.'),
    ('PREDICATE_STATE', 'PENDING_REVIEW', '조건 유무나 조건식의 완전성이 아직 검토되지 않은 상태. 추출 규칙에 조건이 없을 때 부여하는 값이고 cond_expr가 있어도 허용된다. 조건식이 없어도 무조건 적용으로 해석하면 안 된다.'),
    ('METHOD_KIND', 'CALC', '거래의 후보 보상을 산출하는 계산 방법. method_cd가 CALC_METHOD 그룹에 속해야 하며 규칙의 calc_method_cd와 버전이 이 행과 연결된다.'),
    ('METHOD_KIND', 'PREDICATE', '조건의 참·거짓을 판정하는 술어 방법. method_cd가 PREDICATE_METHOD 그룹에 속해야 하며 조건 atom의 predicate_method_cd와 버전이 이 행과 연결된다. 보상을 산출하지 않는다는 점에서 CALC와 구분된다.'),
    ('METHOD_STATUS', 'ACTIVE', '해당 버전의 실행 핸들러가 배포되어 거래별 계산이나 판정을 실행할 수 있는 상태. 코드가 존재한다는 뜻이 아니라 handler_key의 구현이 준비되었다는 뜻이며, 판매 상태 PRODUCT_STATUS.ACTIVE와 의미가 다르다.'),
    ('METHOD_STATUS', 'UNEXECUTABLE', '방법 코드와 정책값은 저장할 수 있지만 실행 핸들러가 배포되지 않아 계산이나 판정을 실행할 수 없는 상태. 설명용으로 조회할 수는 있어도 확정 계산 가능 상태로 간주하지 않는다.'),
    ('CALC_METHOD', 'PERCENT_OF_TXN', '결제금액에 고정 비율을 곱해 보상을 산출하는 방식. value_num은 퍼센트 수치이며(1.5는 1.5%) value_unit_cd는 PERCENT를 쓴다. 결제금액과 무관하게 일정액을 주는 FIXED_PER_TXN과 구분된다.'),
    ('CALC_METHOD', 'FIXED_PER_TXN', '조건을 충족한 결제 1건마다 정해진 금액을 제공하는 방식. value_num은 건당 금액이며 ONE PICK의 100원, 500원 캐시백이 해당한다. 결제금액에 비례하는 PERCENT_OF_TXN, 금액 구간마다 적립하는 UNITS_PER_AMOUNT와 구분된다.'),
    ('CALC_METHOD', 'UNITS_PER_AMOUNT', '결제금액을 basis_amt 단위로 나누어 단위마다 value_num만큼 적립하는 방식. 1,500원당 45 UniMile이 해당하며 value_num=45, basis_amt=1500으로 저장한다. 비율로 계산하는 PERCENT_OF_TXN과 달리 기준금액 단위로 계산한다.'),
    ('CALC_METHOD', 'MULTIPLY_EXTERNAL_POINTS', '결제금액이 아니라 외부 제휴사가 적립한 포인트에 배수를 곱해 보상을 산출하는 방식. CJ ONE 적립 포인트의 2배 캐시백이 해당하며 value_num은 배수, value_unit_cd는 MULTIPLIER다. 외부 포인트 값이 없으면 산출할 수 없다.'),
    ('CALC_METHOD', 'FREE_SERVICE', '결제금액으로 보상을 계산하지 않고 공항 라운지나 발렛파킹 같은 서비스 이용을 무상으로 제공하는 방식. 금액이나 포인트를 산출하는 다른 계산 방법과 구분된다.'),
    ('PREDICATE_METHOD', 'EVERY_MONTH_MIN_SPEND', '지정한 기간의 모든 달이 각각 최소 실적을 충족하는지 판정하는 방법. 최근 3개월 매월 10만원 이상처럼 합계가 아니라 월별 충족을 보며, 최소 금액은 cond_min_amt, 기간은 cond_params에 둔다. cond_basis_cd는 ROLLING_MONTHS를 쓴다.'),
    ('PREDICATE_METHOD', 'MONTH_IN', '기준 월이 지정한 월 목록에 속하는지 판정하는 방법. 2, 3, 8, 9월에 매입된 거래처럼 금액이 아닌 달력 조건에 쓰며 월 목록과 기준은 cond_params에 둔다.'),
    ('VALUE_UNIT', 'PERCENT', 'value_num이 퍼센트 수치임을 나타내는 단위. 5는 5%를 뜻하며 PERCENT_OF_TXN과 함께 쓴다. 고객이 받는 단위는 PAYOUT_UNIT에 별도로 기록한다.'),
    ('VALUE_UNIT', 'KRW', 'value_num이 원화 금액임을 나타내는 단위. FIXED_PER_TXN의 건당 100원처럼 입력값 자체가 금액인 경우에 쓴다. 지급 단위 PAYOUT_UNIT.KRW, 한도 단위 LIMIT_UNIT.KRW와 코드값만 같고 사용 위치가 다르다.'),
    ('VALUE_UNIT', 'UNIMILE', 'value_num이 UniMile 수량임을 나타내는 단위. 1,500원당 45 UniMile의 45처럼 입력값이 마일 수량인 경우에 쓴다. 고객이 받는 단위를 나타내는 PAYOUT_UNIT.UNIMILE과 구분된다.'),
    ('VALUE_UNIT', 'MULTIPLIER', 'value_num이 곱할 배수임을 나타내는 단위. CJ ONE 포인트 2배의 2처럼 금액이나 비율이 아닌 배수를 저장할 때 쓴다. MULTIPLY_EXTERNAL_POINTS와 함께 쓴다.'),
    ('PAYOUT_UNIT', 'KRW', '보상을 원화로 받는 경우. 할인과 캐시백이 해당하며, 계산 입력값이 퍼센트여도 실제 보상이 원이면 이 값을 쓴다.'),
    ('PAYOUT_UNIT', 'HANAMONEY', '보상을 하나머니 포인트로 받는 경우. JADE Classic의 특별 적립이 해당한다. 원화로 지급하는 KRW, 마일리지인 UNIMILE과 구분된다.'),
    ('PAYOUT_UNIT', 'UNIMILE', '보상을 UniMile로 받는 경우. Mile1 카드의 마일리지 적립이 해당한다. 원문의 1,500원당 45 UniMile은 UNITS_PER_AMOUNT 규칙으로 표현한다.'),
    ('PAYOUT_UNIT', 'WALLET_POINT', '보상을 월렛 포인트로 받는 경우. Visa 브랜드 서비스의 Booking.com 월렛포인트 캐시백이 해당한다. 원화나 하나머니가 아닌 별도 포인트로 지급될 때 쓴다.'),
    ('PAYOUT_UNIT', 'SERVICE', '보상이 금전이나 포인트가 아니라 서비스 이용 자체로 제공되는 경우. 공항 라운지, 발렛파킹처럼 지급 수량으로 환산하지 않는 혜택에 쓴다.'),
    ('LIMIT_SCOPE', 'BENEFIT', '혜택 하나의 규칙만 소비하는 한도. 같은 혜택 안의 두 규칙이 같은 풀을 써도 다른 혜택과는 공유하지 않는다. 현재 추출기는 원문에 공유 표현이 없으면 이 값을 부여한다.'),
    ('LIMIT_SCOPE', 'BENEFIT_GROUP', '원문이 여러 혜택의 공유를 명시해 묶어 누적하는 한도. 추출기는 공유 표현 shared_scope_txt가 있을 때 이 값을 부여하며, 금액이 같다는 이유만으로 공유로 판단하지 않는다.'),
    ('LIMIT_SCOPE', 'AREA', '쇼핑, 교통처럼 특정 서비스 영역 안의 혜택이 함께 소비하는 한도. 달달 체크카드의 영역별 2천, 4천, 6천원 한도가 해당한다. 모든 영역을 합치는 CARD와 달리 영역마다 별도의 풀이다.'),
    ('LIMIT_SCOPE', 'CARD', '카드의 모든 서비스 영역을 합쳐 누적하는 통합 한도. 달달 체크카드의 월 통합 1만, 2만, 3만원 한도가 해당한다. 영역 한도와 함께 있으면 한 결제가 두 풀을 모두 소비한다.'),
    ('LIMIT_PERIOD', 'TXN', '결제 1건마다 적용되는 한도. 기간 동안 누적되지 않고 건별로 판단한다는 점에서 DAY, MONTH, YEAR와 구분된다.'),
    ('LIMIT_PERIOD', 'DAY', '하루 단위로 누적하는 한도. ONE PICK의 일 1회 제공이 해당한다. 월 한도와 동시에 걸리면 별도의 풀로 둔다.'),
    ('LIMIT_PERIOD', 'MONTH', '한 달 단위로 누적하는 한도. ONE PICK의 월 30회, 월 5천원이 해당하며 전월 실적에 따라 구간별로 금액이 달라지는 한도도 이 기간을 쓴다.'),
    ('LIMIT_PERIOD', 'YEAR', '1년 단위로 누적하는 한도. 놀이공원의 연 2회 제공이 해당한다. 월 1회처럼 다른 기간의 한도와 동시에 걸리면 별도의 풀로 둔다.'),
    ('LIMIT_UNIT', 'KRW', '한도를 원화 금액으로 관리하는 단위. 월 5천원, 월 통합 10만원이 해당한다. 혜택 제공 횟수를 세는 COUNT와 구분된다.'),
    ('LIMIT_UNIT', 'HANAMONEY', '한도를 하나머니 적립량으로 관리하는 단위. JADE Classic의 월 통합 10만 하나머니가 해당한다. 원화로 환산하지 않고 원문의 단위대로 저장한다.'),
    ('LIMIT_UNIT', 'COUNT', '한도를 혜택 제공 횟수로 관리하는 단위. 일 1회, 월 30회, 연 2회가 해당한다. limit_num이 금액이 아니라 횟수이며 금액 한도와는 별도의 풀로 둔다.'),
    ('LIMIT_AGG', 'CARD_MEMBER', '회원의 카드 단위로 누적하면서 가족카드 사용분을 합산하는 기준. 원문의 본인카드와 가족카드의 실적 및 적립/할인한도는 합산이 해당한다. 현재 추출기가 일괄 입력하는 기본값이므로 이 값이 있다고 해당 상품의 원문이 확인된 것은 아니다.'),
    ('POOL_ROLE', 'CONSUME', '규칙이 자기 규칙군에 속한 한도 풀을 소비하는 역할. 달달 체크카드의 쇼핑 규칙이 쇼핑 영역 한도를 쓰는 경우다. 현재 추출기는 규칙의 한도 참조를 모두 이 값으로 만든다.'),
    ('POOL_ROLE', 'SHARED', '규칙이 자기 규칙군의 한도와 함께 카드 통합 한도도 동시에 소비하는 역할. 달달 체크카드의 규칙이 쇼핑 영역 풀(CONSUME)과 모든 영역 통합 풀(SHARED)을 함께 소비하는 경우다.'),
    ('REL_TYPE', 'MUTUALLY_EXCLUSIVE', '두 혜택을 한 거래에 함께 제공하지 않는 관계. 원문의 특별 적립과 기본 적립은 중복 제공되지 않음이 해당한다. 방향이 없어 한쪽 혜택에만 저장하고 v_card_bnft_rel이 양방향으로 복원하며, 양쪽에 저장하면 게이트 rel_mutual_stored_twice에서 검출된다.'),
    ('REL_TYPE', 'HIGHER_VALUE_WINS', '여러 혜택이 해당할 때 보상이 큰 혜택을 적용하는 관계. 원문의 적립 대상이 중복되면 적립률이 높은 서비스가 우선 적용이 해당한다. 혜택 사이의 관계라는 점에서 한 혜택 안의 RULE_SELECT.MAX_BENEFIT_VALUE와 구분된다.'),
    ('REL_TYPE', 'FALLBACK_AFTER_CAP', '시작 혜택의 한도를 소진한 뒤 추가 거래에 대상 혜택을 적용하는 관계. 원문의 월 적립 한도 소진 후 발생하는 추가 매출은 기본적립 제공이 해당한다. 어느 한도의 소진인지 trigger_pool_id가 필수이고, 대체 순환은 게이트 rel_fallback_cycle에서 검출된다.'),
    ('COND_TYPE', 'SPEND_REQ', '금액 기준을 충족해야 하는 실적 요건. 지난달 실적 10만원 이상, 결제 건당 3천원 이상이 해당하며 cond_basis_cd가 필수다. 규칙의 건당 최소 금액도 추출기가 TXN_AMT 기준의 이 유형으로 만든다.'),
    ('COND_TYPE', 'SPEND_EXCL', '특정 이용금액을 실적 산정에서 제외하는 조건. 국세, 공과금 등 실적 제외 항목이 해당하며 card_excl_item_id나 excl_raw_txt가 필수다. 혜택 제공에서 빼는 BNFT_EXCL과 같은 항목을 다뤄도 별도 조건으로 저장한다.'),
    ('COND_TYPE', 'BNFT_EXCL', '특정 거래나 상황을 혜택 제공에서 제외하는 조건. 상품권 구매 제외, 시외버스 제외, 최초 발급 월 미제공이 해당하며 card_excl_item_id나 excl_raw_txt가 필수다. 실적 계산에서 빼는 SPEND_EXCL과 구분된다.'),
    ('COND_TYPE', 'USAGE_REQ', '혜택을 받기 위해 거래나 이용 행위가 갖춰야 하는 이용 요건. 설계상 건당 이용 요건과 자동이체 이용처럼 실적 구간이 아닌 이용 행위에 걸린 조건을 담는다. 금액 기준 요건을 나타내는 SPEND_REQ와 구분된다.'),
    ('COND_TYPE', 'PAYMENT_METHOD', '결제가 이루어지는 방식이나 경로에 걸린 조건. 대상 가맹점의 공식 홈페이지와 오프라인 결제 시에만 제공되고 배달 앱 결제는 해당하지 않는 경우가 이에 속한다. 가맹점 분류 기준인 MERCHANT_RULE과 구분된다.'),
    ('COND_TYPE', 'MERCHANT_RULE', '가맹점이나 업종의 분류 기준에 관한 조건. 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공한다는 정책 조건이 해당한다. 개별 대상 가맹점은 target_list에 두고 이 유형은 판정 기준을 담는다.'),
    ('COND_TYPE', 'GRACE', '요건을 일시적으로 완화해 미충족이어도 혜택을 제공하는 유예 조건. 최초 카드 사용 등록일부터 다음 달 말일까지 실적 10만원 미만이어도 서비스를 제공하는 경우다. 제공을 막는 제한은 유예가 아니므로 BNFT_EXCL로 표현한다.'),
    ('COND_TYPE', 'ETC', '정의된 조건 유형에 해당하지 않아 원문으로 보존하는 조건. 놀이공원의 1인 1매가 해당하며 정형 판정이 아니라 cond_raw_txt로 내용을 유지한다. 추출 단계의 UNKNOWN과 달리 유형을 판단한 결과다.'),
    ('COND_BASIS', 'PREV_MONTH_SPEND', '전월 실적을 비교 기준으로 쓰는 값. 원문의 지난달 1일부터 말일까지 이용금액이 해당한다. v_card_rule의 실적 구간은 이 기준의 금액을 추출한다.'),
    ('COND_BASIS', 'PREV_YEAR_SPEND', '직전 1년의 실적을 비교 기준으로 쓰는 값. 1개월 기준인 PREV_MONTH_SPEND, 월별로 각각 판정하는 ROLLING_MONTHS와 달리 1년 동안의 실적을 하나의 금액으로 본다.'),
    ('COND_BASIS', 'TXN_AMT', '결제 1건의 금액을 비교 기준으로 쓰는 값. 결제 건당 3천원 이상, 1만원 이상이 해당한다. 기간 누적이 아니라 거래별로 판정한다는 점에서 실적 기준 코드들과 구분된다.'),
    ('COND_BASIS', 'MONTH_USAGE', '혜택 판정이 이루어지는 달의 이용금액을 비교 기준으로 쓰는 값. 원문의 이번달 합산 이용금액 10만원 이상이 해당한다. 지난달 기준인 PREV_MONTH_SPEND와 구분된다.'),
    ('COND_BASIS', 'ROLLING_MONTHS', '최근 N개월의 각 월 실적을 비교 기준으로 쓰는 값. 합계가 아니라 월별로 각각 판정하며 최근 3개월 매월 10만원 이상이 해당한다. PREDICATE_METHOD.EVERY_MONTH_MIN_SPEND와 함께 쓴다.'),
    ('TARGET_TYPE', 'MERCHANT', '혜택 대상이 특정 가맹점이나 브랜드인 경우. CU, GS25, 에버랜드처럼 대상의 이름을 지정할 수 있을 때 쓴다. 범주 전체를 가리키는 INDUSTRY와 구분된다.'),
    ('TARGET_TYPE', 'INDUSTRY', '혜택 대상이 개별 가맹점이 아니라 업종 전체인 경우. 원문이 가맹점 이름 대신 업종 범주로 대상을 정의할 때 쓰며 MERCHANT와 구분된다.'),
    ('TARGET_TYPE', 'CHANNEL', '혜택 대상이 결제 채널이나 지역 범위로 정해지는 경우. 토스뱅크 Wide의 국내/해외 가맹점처럼 특정 가맹점을 나열하지 않고 범위 전체를 대상으로 할 때 쓴다.'),
    ('TARGET_TYPE', 'SERVICE', '혜택 대상이 가맹점이 아니라 이용하는 서비스 자체인 경우. ONE MORE 대중교통의 버스, 지하철이 해당한다.'),
    ('BRAND', 'VISA', 'Visa 브랜드 선택지 또는 Visa가 제공하는 공통 서비스. Visa Platinum, Signature, Infinite 등급의 브랜드 서비스 안내서가 있다.'),
    ('BRAND', 'MASTERCARD', 'Mastercard 브랜드 선택지 또는 Mastercard가 제공하는 공통 서비스. Platinum, World 등급의 브랜드 서비스 안내서가 있다.'),
    ('BRAND', 'AMEX', 'American Express 브랜드 선택지 또는 AMEX가 제공하는 공통 서비스. Platinum, Platinum Elite 등급의 브랜드 서비스 안내서가 있다.'),
    ('BRAND', 'JCB', 'JCB 브랜드 선택지 또는 JCB가 제공하는 공통 서비스. 수집 문서에는 JCB 브랜드 서비스 안내서 JP002가 있다.'),
    ('BRAND', 'UPI', 'UnionPay 브랜드 선택지 또는 UnionPay가 제공하는 공통 서비스. 원문에는 UnionPay, UPI, 유니온페이로 표기되며 Platinum, Diamond 등급의 안내서가 있다.'),
    ('BRAND', 'LOCAL', '국제 브랜드 없이 국내에서 이용하는 국내전용 선택지. 원문의 국내전용(Local) 발급 구분이 해당한다. 코드값은 같지만 혜택 출처 BNFT_ORIGIN.LOCAL과는 무관하다.'),
    ('SERVICE_GRADE', 'NONE', '브랜드 서비스 등급이 없거나 해당하지 않는 경우. card_common_bnft의 기본값이며 등급 정보가 없는 브랜드 선택지에 쓴다. 등급을 확인하지 못했다는 뜻이 아니라 적용할 등급이 없다는 뜻이다.'),
    ('SERVICE_GRADE', 'PLATINUM', '브랜드 서비스의 Platinum 등급. Visa, Mastercard, AMEX, UnionPay 안내서에서 사용되며 브랜드마다 서비스 내용이 다르므로 BRAND와 함께 해석한다.'),
    ('SERVICE_GRADE', 'PLATINUM_ELITE', 'AMEX 브랜드 서비스의 Platinum Elite 등급. 안내서 AE001이 해당하며 AMEX Platinum 등급과는 별도의 공통·선택서비스를 가진다.'),
    ('SERVICE_GRADE', 'SIGNATURE', 'Visa 브랜드 서비스의 Signature 등급. 안내서 VS002가 해당한다.'),
    ('SERVICE_GRADE', 'WORLD', 'Mastercard 브랜드 서비스의 World 등급. 안내서 MW002, MW003이 해당한다.'),
    ('SERVICE_GRADE', 'INFINITE', 'Visa 브랜드 서비스의 Infinite 등급. 안내서 VI001이 해당하며 Signature와는 별도의 공통·선택서비스를 가진다.'),
    ('SERVICE_GRADE', 'DIAMOND', 'UnionPay 브랜드 서비스의 Diamond 등급. 안내서 UD001, UD002가 해당하며 UnionPay Platinum과는 별도의 서비스를 가진다.'),
    ('SERVICE_TYPE', 'NONE', '브랜드 서비스 유형 구분이 없거나 해당하지 않는 경우. card_common_bnft의 기본값이며 공통 서비스와 선택서비스 어느 쪽도 아닐 때 쓴다.'),
    ('SERVICE_TYPE', 'COMMON', '해당 등급의 카드 소지자에게 공통으로 제공되는 서비스. 안내서의 공통서비스 항목이 해당하며, 대상 카드에 따라 달라지는 번호 유형과 구분된다.'),
    ('SERVICE_TYPE', '01', '브랜드·등급별 선택서비스의 01 유형. Visa Platinum 01 선택서비스가 해당한다. 번호는 브랜드·등급과 조합해야 의미가 정해지며 대상 카드는 안내서의 대상카드 표를 따른다.'),
    ('SERVICE_TYPE', '02', '브랜드·등급별 선택서비스의 02 유형. Mastercard World 02, Visa Signature 02 선택서비스가 해당하며 Mastercard World 02의 대상카드에는 CLUB Leaders 계열이 있다.'),
    ('SERVICE_TYPE', '03', '브랜드·등급별 선택서비스의 03 유형. Mastercard World 03 선택서비스가 해당하며 JADE Classic이 대상카드다. 같은 번호라도 브랜드와 등급이 다르면 다른 서비스 묶음이다.'),
    ('SERVICE_TYPE', '04', '브랜드·등급별 선택서비스의 04 유형. Mastercard 안내서 MP004의 상품유형 Mastercard World Platinum04가 해당한다.'),
    ('EV_SUBJECT', 'POLICY', '근거가 정책판 전체를 뒷받침하는 경우. 카드 전체 조건처럼 특정 혜택에 속하지 않는 내용에 쓰며 혜택, 규칙, 관계, 풀 컬럼은 모두 비워야 한다.'),
    ('EV_SUBJECT', 'BNFT', '근거가 혜택 하나를 뒷받침하는 경우. card_bnft_id가 필수이고 규칙, 관계, 풀 컬럼은 비운다. 규칙 수준의 근거는 RULE을 쓴다.'),
    ('EV_SUBJECT', 'RULE', '근거가 혜택 안의 계산 규칙을 뒷받침하는 경우. card_bnft_id와 rule_key가 필수다. rule_key가 바뀌면 근거 연결이 끊어지므로 게이트 evidence_subject_orphan으로 검증한다.'),
    ('EV_SUBJECT', 'POOL', '근거가 한도 풀을 뒷받침하는 경우. pool_id가 필수이고 혜택, 규칙, 관계 컬럼은 비운다. 여러 혜택이 공유할 수 있는 한도라서 혜택 대신 풀에 연결한다.'),
    ('EV_SUBJECT', 'REL', '근거가 혜택 간 관계를 뒷받침하는 경우. card_bnft_id와 relation_key가 필수다. 배타, 우선, 대체 같은 관계의 원문 문장을 연결할 때 쓴다.'),
    ('EV_ITEM', 'SELF', '근거가 대상 전체를 가리키는 경우. 기본값이며 이 값일 때만 ev_item_key가 하이픈(-)이다. 대상 안의 특정 항목을 가리키는 다른 코드와 구분된다.'),
    ('EV_ITEM', 'COND', '근거가 조건식의 atom 하나를 가리키는 경우. ev_item_key에 atom_key를 저장하며 정책 근거와 공통 규칙 근거 양쪽에서 쓴다.'),
    ('EV_ITEM', 'TARGET', '근거가 규칙 대상 하나를 가리키는 경우. ev_item_key에 target_key를 저장하며 정책 근거와 공통 규칙 근거 양쪽에서 쓴다.'),
    ('EV_ITEM', 'TIER', '근거가 상품 한도 풀의 구간 하나를 가리키는 경우. ev_item_key에 tier_key를 저장하며 card_policy_evidence에서만 인정된다. 공통 규칙의 한도는 LIMIT을 쓴다.'),
    ('EV_ITEM', 'LIMIT', '근거가 공통 규칙에 내장된 한도 하나를 가리키는 경우. ev_item_key에 limit_key를 저장하며 card_common_rule_evidence에서만 인정된다. 상품 한도 풀의 구간은 TIER를 쓴다.'),
    ('DOC_TYPE', 'PRODUCT_GUIDE', '개별 카드 상품의 혜택과 유의사항을 설명하는 상품설명서. card_doc의 기본값이며 혜택 추출의 주 원천이다.'),
    ('DOC_TYPE', 'TERMS', '카드 이용 조건을 규정하는 약관 문서. 신용카드 개인회원 표준약관, 체크카드 개인회원 약관이 해당한다. 상품과의 관계에서는 DOC_ROLE.COMMON_TERMS로 연결한다.'),
    ('DOC_TYPE', 'BRAND_SERVICE', '국제 브랜드의 등급별 서비스를 안내하는 문서. Visa, Mastercard, AMEX, JCB, UnionPay 안내서가 해당하며 공통 혜택의 원천이 된다.'),
    ('DOC_TYPE', 'ETC', '상품설명서, 약관, 브랜드 서비스 안내에 해당하지 않는 문서. 정의된 유형 밖의 자료에 쓰며, DOC_ROLE의 기타 코드는 OTHER로 값이 다르다.'),
    ('DOC_STATUS', 'ACTIVE', '문서를 파이프라인에서 사용 중인 상태. 기본값이며 AI 입력은 이 상태의 문서만 대상이다. 문서가 사용 가능하다는 뜻일 뿐 특정 상품에 현재 적용된다는 뜻은 아니다.'),
    ('DOC_STATUS', 'SUPERSEDED', '같은 문서 계열의 새 판으로 대체된 상태. 문서 행은 남아 있지만 AI 입력 대상에서는 빠진다. 문서 자체를 쓰지 않기로 한 EXCLUDED와 구분된다.'),
    ('DOC_STATUS', 'EXCLUDED', '문서를 파이프라인 처리 대상에서 제외한 상태. 판이 바뀐 SUPERSEDED와 달리 문서 자체를 쓰지 않기로 한 경우다. 페이지·청크 단위 제외는 CHUNK_STATUS.EXCLUDED가 맡는다.'),
    ('PAGE_LAYER', 'TEXT', '추출된 텍스트가 있고 이미지 같은 시각 요소가 없는 페이지. 프로그램이 텍스트만으로 페이지 내용을 읽을 수 있다고 판정한 경우다.'),
    ('PAGE_LAYER', 'IMAGE', '추출된 텍스트가 없고 시각 요소만 있는 페이지. 스캔본처럼 내용이 이미지에 있어 OCR 등 별도 처리가 필요하다.'),
    ('PAGE_LAYER', 'MIXED', '추출된 텍스트와 시각 요소가 함께 있는 페이지. 표가 이미지로 들어 있으면 그 안의 글자는 텍스트로 추출되지 않았을 수 있어 TEXT와 구분한다.'),
    ('PAGE_LAYER', 'UNKNOWN', '추출된 텍스트도 시각 요소도 확인되지 않은 페이지. card_doc_page의 기본값이며 페이지 내용을 판정할 수 없는 경우다.'),
    ('CHUNK_TYPE', 'BODY', '본문 성격의 청크. card_doc_chunk의 기본값이며 현재 프로그램은 페이지 전체 청크를 모두 이 값으로 등록한다.'),
    ('CHUNK_TYPE', 'TABLE', '표 내용이 중심인 청크. 혜택과 한도가 행과 열로 정리된 부분을 본문과 구분해 다룰 때 쓴다.'),
    ('CHUNK_TYPE', 'NOTICE', '유의사항이 중심인 청크. 혜택 표와 떨어져 있는 제외 조건과 안내 문구를 구분할 때 쓴다.'),
    ('CHUNK_TYPE', 'HEADER_FOOTER', '페이지 머리말·꼬리말 청크. 페이지마다 반복되는 문구처럼 혜택 내용이 아닌 부분을 구분할 때 쓴다.'),
    ('CHUNK_TYPE', 'ETC', '본문, 표, 유의사항, 머리말·꼬리말에 해당하지 않는 청크.'),
    ('CHUNK_STATUS', 'RAW', '문서에서 분리만 된 청크. 정제 전 상태이며 기본값이다. CLEANED와 함께 AI 입력 대상이다.'),
    ('CHUNK_STATUS', 'CLEANED', '정제가 끝난 청크. 이 값이면 chunk_clean_txt와 chunk_clean_rule_ver가 필수다(card_doc_chunk_check1). RAW와 함께 AI 입력 대상이다.'),
    ('CHUNK_STATUS', 'EXCLUDED', 'AI 추출 대상에서 제외한 청크. OCR 검토 대상 페이지의 청크가 여기에 해당하며 검토를 통과하면 RAW로 되돌린다. 문서 전체의 제외인 DOC_STATUS.EXCLUDED와 구분된다.'),
    ('RUN_STAGE', 'EXTRACT', '문서에서 혜택과 조건을 추출하는 단계의 실행. 현재 추출 파이프라인이 등록하는 값이며 결과는 card_ai_call과 card_extr_stg에 남는다.'),
    ('RUN_STAGE', 'VERIFY', '추출된 항목의 의미를 AI로 검증하는 단계의 실행. 결과는 stg_ai_vrfy_cd와 stg_ai_vrfy_card_ai_run_id에 기록하며, 추출과 다른 실행 이력으로 남긴다.'),
    ('RUN_CALL_METHOD', 'PYTHON_RELAY', 'Python 프로그램이 LLM 호출을 중계하는 방식. 현재 추출 파이프라인의 실행 이력에 고정으로 기록되는 값이다.'),
    ('RUN_CALL_METHOD', 'PGAI', 'pgai 등 PostgreSQL 확장으로 DB에서 AI를 호출하는 방식. 아키텍처 문서의 호출 방식 후보로, 현재 프로그램은 이 방식을 사용하지 않는다.'),
    ('RUN_CALL_METHOD', 'EDGE_FUNCTION', 'Supabase Edge Functions로 AI를 호출하는 방식. 아키텍처 문서의 호출 방식 후보로, 현재 프로그램은 이 방식을 사용하지 않는다.'),
    ('RUN_CALL_METHOD', 'ETC', 'Python 중계, pgai, Edge Functions에 해당하지 않는 AI 호출 방식.'),
    ('RUN_STATUS', 'RUNNING', '실행이 시작되어 아직 끝나지 않은 상태. 기본값이며 정상 종료나 오류 시 다른 값으로 바뀐다. 오래 남아 있으면 비정상 중단을 의심한다.'),
    ('RUN_STATUS', 'SUCCEEDED', '대상 페이지를 모두 처리하고 문서 통합 저장까지 끝났으며 AI 입력에서 제외된 페이지도 없는 실행.'),
    ('RUN_STATUS', 'PARTIAL', '일부 결과는 있지만 완전하지 않은 실행. 실패한 페이지나 AI 입력 제외 페이지가 있거나 문서 통합 저장이 실패한 경우다. 실패 페이지가 있으면 문서 통합을 하지 않는다.'),
    ('RUN_STATUS', 'FAILED', '성공한 페이지가 없거나 처리 중 오류로 중단된 실행. 일부 결과가 남는 PARTIAL과 구분된다.'),
    ('CALL_STATUS', 'SUCCEEDED', 'AI 응답을 받아 JSON 구조 해석과 페이지 번호 검증을 통과한 호출. call_resp_json이 필수다. 호출이 성공했다는 뜻이며 추출 내용이 맞다는 뜻은 아니다.'),
    ('CALL_STATUS', 'FAILED', 'AI 호출 자체가 실패해 응답을 받지 못한 경우. 오류 유형을 call_error_msg에 남긴다. 응답은 받았지만 해석하지 못한 PARSE_ERROR와 구분된다.'),
    ('CALL_STATUS', 'PARSE_ERROR', '응답은 받았지만 요구한 구조로 해석하지 못하거나 페이지 번호가 일치하지 않는 경우. 재검토를 위해 응답 원문을 call_resp_raw에 보존한다.'),
    ('STG_KIND', 'BENEFIT', '혜택 1건을 담는 추출 항목. 문서 통합 결과가 stg_normalized_item에 V6 혜택 구조로 저장된다.'),
    ('STG_KIND', 'CONDITION', '조건 1건을 담는 추출 항목. stg_parent_card_extr_stg_id로 조건이 걸린 혜택 항목을 가리키고, 값이 NULL이면 카드 전체 조건이다.'),
    ('STG_STATUS', 'PENDING_REVIEW', '추출 항목이 저장되었지만 검토가 끝나지 않은 상태. 기본값이다. 승인 전이므로 업무 데이터의 근거로 확정해서는 안 된다.'),
    ('STG_STATUS', 'AUTO_APPROVED', '사람의 개별 검토 없이 자동 기준으로 승인된 상태. stg_sql_check_cd가 OK이고 정제 항목, 근거 문장, 근거 위치가 모두 있어야 한다(card_extr_stg_check1).'),
    ('STG_STATUS', 'MANUAL_APPROVED', '사람이 검토해 승인한 상태. AUTO_APPROVED와 같은 CHECK 요건을 지켜야 하며, 의미가 모호해 자동 승인이 어려운 항목을 처리할 때 쓴다.'),
    ('STG_STATUS', 'REJECTED', '검토 결과 업무 데이터로 쓰지 않기로 거부한 추출 항목. 관계·근거의 반려 APPROVAL_STATUS.REJECTED와 달리 AI 추출 항목에 대한 판정이다.'),
    ('STG_AI_VRFY', 'MATCH', 'AI 의미 검증에서 추출 항목이 원문 의미와 일치한다고 판정한 결과. 최종 승인이 아니라 승인 판단의 참고 정보다.'),
    ('STG_AI_VRFY', 'MISMATCH', 'AI 의미 검증에서 추출 항목이 원문 의미와 다르다고 판정한 결과. 판정이 불가능한 UNCERTAIN과 달리 불일치를 명시적으로 판단한 경우다.'),
    ('STG_AI_VRFY', 'UNCERTAIN', 'AI 의미 검증에서 일치 여부를 판정하지 못한 결과. 사람의 검토가 필요하며, 검증을 실행하지 않은 NULL과 구분된다.');

UPDATE db_pipeline.common_code_grp AS g
SET common_code_grp_desc = v.common_code_grp_desc
FROM tmp_common_code_grp_desc AS v
WHERE g.common_code_grp_id = v.common_code_grp_id
  AND g.common_code_grp_desc IS DISTINCT FROM v.common_code_grp_desc;

UPDATE db_pipeline.common_cd AS c
SET common_cd_desc = v.common_cd_desc
FROM tmp_common_cd_desc AS v
WHERE (c.common_code_grp_id, c.common_cd) = (v.common_code_grp_id, v.common_cd)
  AND c.common_cd_desc IS DISTINCT FROM v.common_cd_desc;

DO $$
DECLARE
    v_missing text;
BEGIN
    SELECT string_agg(v.common_code_grp_id, ', ') INTO v_missing
    FROM tmp_common_code_grp_desc AS v
    WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_code_grp g
                      WHERE g.common_code_grp_id = v.common_code_grp_id);
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION '설명 대상 그룹이 없습니다: %', v_missing;
    END IF;

    SELECT string_agg(v.common_code_grp_id || '.' || v.common_cd, ', ') INTO v_missing
    FROM tmp_common_cd_desc AS v
    WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd c
                      WHERE (c.common_code_grp_id, c.common_cd) = (v.common_code_grp_id, v.common_cd));
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION '설명 대상 코드가 없습니다: %', v_missing;
    END IF;
END;
$$;

COMMIT;
