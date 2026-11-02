-- V7 참조 무결성 시험. 항상 ROLLBACK한다.
-- 앞부분은 공통 PDF 공유 구조가 실제로 등록되는지 확인하는 양성 시험이다(card_id 999101~999103, S- 접두 ID).
-- 뒷부분은 일부러 잘못된 행을 넣어 게이트와 CHECK가 잡는지 확인하는 음성 시험이다(card_id 999001, 999002, T- 접두 ID).
-- 검사를 지워서 0건이 되는 일을 막기 위한 파일이다.
-- 샘플 데이터 유무와 관계없이 V7 스키마와 공통코드 시드가 있으면 실행할 수 있다.

BEGIN;

-- ---------------------------------------------------------------------------
-- 양성: 공통 PDF 1건을 카드 등록 전에 추출하고, 카드 2장이 문서와 근거를 공유한다
-- ---------------------------------------------------------------------------
INSERT INTO db_pipeline.card_doc (card_doc_id, card_id, doc_cd, doc_type_cd, doc_title, doc_file_nm, doc_sha256, doc_collect_date, create_user_id, update_user_id)
VALUES ('S-DOC', NULL, 'S_VISA_PLATINUM_01', 'BRAND_SERVICE', '시험 Visa Platinum 01', 's.pdf', repeat('a', 64), now(), 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_doc_page (card_doc_id, page_no, page_raw_txt, page_char_cnt, page_txt_sha256, page_extractor_nm, create_user_id, update_user_id)
VALUES ('S-DOC', 1, '시험 원문', 5, repeat('b', 64), 'test', 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_doc_chunk (card_doc_id, page_no, card_doc_chunk_id, chunk_seq, chunk_start_pos, chunk_end_pos, chunk_raw_txt, chunk_split_rule_ver, create_user_id, update_user_id)
VALUES ('S-DOC', 1, 'S-CHUNK', 1, 1, 5, '시험 원문', 'TEST', 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_ai_run (card_ai_run_id, run_stage_cd, run_call_mthd_cd, run_model_nm, run_prompt_ver, run_prompt_txt, run_target_card_doc_id, create_user_id, update_user_id)
VALUES ('S-RUN', 'EXTRACT', 'PYTHON_RELAY', 'test', 'TEST', '시험', 'S-DOC', 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_ai_call (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_input_sha256, call_status, create_user_id, update_user_id)
VALUES ('S-RUN', 'S-DOC', 1, 'S-CHUNK', repeat('c', 64), 'FAILED', 'V7_TEST', 'V7_TEST');
-- 카드가 정해지지 않은 후보. NULL은 공통 혜택 확정이 아니라 미연결 상태다.
INSERT INTO db_pipeline.card_extr_stg (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id, stg_item_seq, card_id, stg_kind_cd, stg_raw_item, stg_evidence_txt, create_user_id, update_user_id)
VALUES ('S-RUN', 'S-DOC', 1, 'S-CHUNK', 1, 'S-STG', 1, NULL, 'BENEFIT', '{}', '시험 원문', 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_source_evidence (evidence_id, card_doc_id, page_no, card_doc_chunk_id, card_extr_stg_id, quote_txt, approval_status_cd)
VALUES ('S-EV', 'S-DOC', 1, 'S-CHUNK', 'S-STG', '시험 원문', 'APPROVED');

INSERT INTO db_pipeline.card_product (card_id, product_cd, product_nm, issuer, card_kind_cd, brand_opt_list, create_user_id, update_user_id)
SELECT c.card_id, 'S-PRODUCT-' || c.card_id, '시험 상품', '시험', 'CREDIT',
       jsonb_build_array(jsonb_build_object('brand_opt_cd', c.opt, 'brand_opt_nm', c.opt, 'brand_cd', c.brand,
                                            'service_grade_cd', 'PLATINUM', 'service_type_cd', c.stype, 'brand_opt_status_cd', 'ACTIVE')),
       'V7_TEST', 'V7_TEST'
FROM (VALUES (999101, 'VISA_P01', 'VISA', '01'), (999102, 'VISA_P01', 'VISA', '01'), (999103, 'MC_P01', 'MASTERCARD', '01')) AS c(card_id, opt, brand, stype);

INSERT INTO db_pipeline.card_product_doc (card_id, card_doc_id, doc_role_cd, brand_opt_cds, applicability_basis_txt, create_user_id, update_user_id)
VALUES (999101, 'S-DOC', 'BRAND_SERVICE', ARRAY['VISA_P01'], '대상카드 표에 상품명 기재', 'V7_TEST', 'V7_TEST'),
       (999102, 'S-DOC', 'BRAND_SERVICE', ARRAY['VISA_P01'], '대상카드 표에 상품명 기재', 'V7_TEST', 'V7_TEST');

-- 같은 혜택 코드를 카드별로 등록한다. 규칙은 각 카드 행이 가진다. 카드 B만 제외 조건이 있고 기간은 원문의 ~27.6.30이다.
INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds, bnft_cond_expr, rule_list, verification_status_cd, bnft_valid_from, bnft_valid_to_excl)
SELECT c.card_id, c.bnft_id, 'S_VISA_HOTEL', '시험 호텔 할인', 'DISCOUNT', 'BRAND_SERVICE', 'BRAND', ARRAY['VISA_P01'], c.cond::jsonb,
       '[{"rule_key":"R1","calc_method_cd":"PERCENT_OF_TXN","value_num":8,"value_unit_cd":"PERCENT","payout_unit_cd":"KRW","rule_status_cd":"DRAFT","method_ver":1,
          "predicate_state_cd":"PENDING_REVIEW","target_list":[]}]'::jsonb,
       'CONFIRMED', NULL::date, DATE '2027-07-01'
FROM (VALUES (999101, 'S-B-A', NULL),
             (999102, 'S-B-B', '{"expr_status_cd":"DRAFT","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"s_excl","negate_yn":true,
               "cond_type_cd":"BNFT_EXCL","excl_raw_txt":"시험 제외","cond_status_cd":"DRAFT","cond_min_amt":null,"cond_max_amt_excl":null,
               "predicate_method_cd":null,"predicate_method_ver":null,"cond_params":null}]}]}')) AS c(card_id, bnft_id, cond);

-- 근거 1건을 두 카드의 혜택이 함께 참조한다.
INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, card_bnft_id, evidence_id)
VALUES (999101, 'S-L-A', 'BNFT', 'S-B-A', 'S-EV'), (999102, 'S-L-B', 'BNFT', 'S-B-B', 'S-EV');

DO $$
DECLARE
    v_issue text;
BEGIN
    SELECT string_agg(i.gate_cd || '=' || i.issue_key, ', ') INTO v_issue
    FROM db_pipeline.v_card_integrity_issue i
    WHERE i.issue_key LIKE '%99910%' OR i.issue_key LIKE 'S-%';
    IF v_issue IS NOT NULL THEN
        RAISE EXCEPTION '정상 공유 구조가 게이트에 걸렸습니다: %', v_issue;
    END IF;
    IF (SELECT count(*) FROM db_pipeline.card_evidence_link WHERE evidence_id = 'S-EV') <> 2
       OR (SELECT count(*) FROM db_pipeline.card_source_evidence WHERE evidence_id = 'S-EV') <> 1 THEN
        RAISE EXCEPTION '근거 공유 구조가 아닙니다';
    END IF;
    IF (SELECT count(*) FROM db_pipeline.v_card_bnft_rule_effective
        WHERE card_id IN (999101, 999102) AND (bnft_valid_to_excl IS NULL OR bnft_valid_to_excl > DATE '2027-06-30')) <> 2
       OR (SELECT count(*) FROM db_pipeline.v_card_bnft_rule_effective
           WHERE card_id IN (999101, 999102) AND bnft_valid_to_excl > DATE '2027-07-01') <> 0 THEN
        RAISE EXCEPTION '제공 기간으로 현재 혜택을 구분할 수 없습니다';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 음성: 대상이 아닌 카드의 브랜드 혜택과 잘못된 문서 연결
-- ---------------------------------------------------------------------------
-- 카드 C는 Mastercard만 있는데 Visa 혜택을 등록하고 Visa 문서의 근거를 연결한다.
INSERT INTO db_pipeline.card_product_doc (card_id, card_doc_id, doc_role_cd, brand_opt_cds, applicability_basis_txt, create_user_id, update_user_id)
VALUES (999103, 'S-DOC', 'BRAND_SERVICE', ARRAY['MC_P01'], '시험', 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds, verification_status_cd)
VALUES (999103, 'S-B-C', 'S_VISA_HOTEL', '시험 호텔 할인', 'DISCOUNT', 'BRAND_SERVICE', 'BRAND', ARRAY['VISA_P01'], 'CONFIRMED');
INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, card_bnft_id, evidence_id)
VALUES (999103, 'S-L-C', 'BNFT', 'S-B-C', 'S-EV');
-- 근거가 없는 확정 브랜드 혜택
INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds, rule_list, verification_status_cd)
VALUES (999101, 'S-B-NOEV', 'S_NOEV', '시험', 'DISCOUNT', 'BRAND_SERVICE', 'BRAND', ARRAY['VISA_P01'],
        '[{"rule_key":"R1","calc_method_cd":"FIXED_PER_TXN","payout_unit_cd":"KRW","rule_status_cd":"DRAFT","method_ver":1,"predicate_state_cd":"PENDING_REVIEW","target_list":[]}]',
        'CONFIRMED');
-- 브랜드 역할로 상품설명서를 연결하고, 공통 문서를 특정 카드에 고정하고, 문서에 연결되지 않은 카드로 추출 항목을 저장한다.
INSERT INTO db_pipeline.card_doc (card_doc_id, doc_cd, doc_type_cd, doc_title, doc_file_nm, doc_sha256, doc_collect_date, create_user_id, update_user_id)
VALUES ('S-DOC-G', 'S_GUIDE', 'PRODUCT_GUIDE', '시험', 'g.pdf', repeat('d', 64), now(), 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_doc (card_doc_id, card_id, doc_cd, doc_type_cd, doc_title, doc_file_nm, doc_sha256, doc_collect_date, create_user_id, update_user_id)
VALUES ('S-DOC-T', 999101, 'S_TERMS', 'TERMS', '시험', 't.pdf', repeat('e', 64), now(), 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_product_doc (card_id, card_doc_id, doc_role_cd, brand_opt_cds, applicability_basis_txt, create_user_id, update_user_id)
VALUES (999101, 'S-DOC-G', 'BRAND_SERVICE', ARRAY['VISA_P01'], '시험', 'V7_TEST', 'V7_TEST');
INSERT INTO db_pipeline.card_extr_stg (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id, stg_item_seq, card_id, stg_kind_cd, stg_raw_item, stg_evidence_txt, create_user_id, update_user_id)
VALUES ('S-RUN', 'S-DOC-G', 1, 'S-CHUNK', 1, 'S-STG-X', 2, 999102, 'BENEFIT', '{}', '시험 원문', 'V7_TEST', 'V7_TEST');
-- 없어진 코드는 게이트에서 걸러진다.
INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, verification_status_cd)
VALUES (999101, 'S-B-OLD', 'S_OLD', '시험', 'DISCOUNT', 'COMMON_LINK', 'PRODUCT', 'PENDING_REVIEW');

DO $$
DECLARE
    v_gate text;
    v_key text;
    v_pair text[];
BEGIN
    FOREACH v_pair SLICE 1 IN ARRAY ARRAY[
        ['brand_bnft_doc_not_linked', '999103/S-B-C/VISA_P01'],
        ['evidence_brand_opt_mismatch', '999103/S-L-C'],
        ['brand_bnft_confirmed_without_evidence', '999101/S-B-NOEV'],
        ['brand_doc_option_conflict', 'S-DOC'],
        ['product_doc_role_type_mismatch', '999101/S-DOC-G'],
        ['shared_doc_bound_to_card', 'S-DOC-T'],
        ['stg_card_not_linked', 'S-STG-X'],
        ['local_confirmed_without_rule', '999103/S-B-C'],
        ['common_cd_invalid', 'card_bnft.bnft_origin_cd=COMMON_LINK']] LOOP
        v_gate := v_pair[1];
        v_key := v_pair[2];
        IF NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_integrity_issue i WHERE i.gate_cd = v_gate AND i.issue_key = v_key) THEN
            RAISE EXCEPTION '게이트가 위반을 찾지 못했습니다: % %', v_gate, v_key;
        END IF;
    END LOOP;
    -- 카드 미연결 후보는 위반이 아니다.
    IF EXISTS (SELECT 1 FROM db_pipeline.v_card_integrity_issue i WHERE i.issue_key = 'S-STG') THEN
        RAISE EXCEPTION 'card_id NULL 후보가 위반으로 처리되었습니다';
    END IF;
END;
$$;

INSERT INTO db_pipeline.card_product
    (card_id, product_cd, product_nm, issuer, card_kind_cd, card_cond_status_cd, create_user_id, update_user_id)
VALUES (999001, 'T-PRODUCT', '시험 상품', '시험', 'DEBIT', 'BAD_STATUS', 'V7_TEST', 'V7_TEST');

-- 카드가 없는 혜택·한도·문서 연결
INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, verification_status_cd)
VALUES (999002, 'T-B-NOCARD', 'T-B-NOCARD', '시험', 'DISCOUNT', 'LOCAL', 'PRODUCT', 'PENDING_REVIEW');
INSERT INTO db_pipeline.card_limit_pool (card_id, pool_id, pool_scope_cd, period_cd, cap_unit_cd, aggregation_key_cd, tier_list)
VALUES (999002, 'T-P-NOCARD', 'BENEFIT', 'MONTH', 'KRW', 'CARD_MEMBER',
        '[{"tier_key":"T1","predicate_state_cd":"PENDING_REVIEW","limit_num":1}]');
INSERT INTO db_pipeline.card_product_doc (card_id, card_doc_id, doc_role_cd, applicability_basis_txt, create_user_id, update_user_id)
VALUES (999002, 'T-D-NONE', 'PRODUCT_GUIDE', '시험', 'V7_TEST', 'V7_TEST');

-- 없는 한도를 참조하는 규칙
INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, rule_list, verification_status_cd)
VALUES (999001, 'T-B-RULE', 'T-B-RULE', '시험', 'DISCOUNT', 'LOCAL', 'PRODUCT',
        '[{"rule_key":"R1","calc_method_cd":"FIXED_PER_TXN","payout_unit_cd":"KRW","rule_status_cd":"DRAFT","method_ver":1,
           "predicate_state_cd":"PENDING_REVIEW","target_list":[]}]',
        'PENDING_REVIEW');
INSERT INTO db_pipeline.card_bnft_rule_pool (card_id,card_bnft_id,rule_key,pool_id,pool_role_cd)
VALUES (999001,'T-B-RULE','R1','T-P-NONE','CONSUME'),
       (999002,'T-B-NONE','R-NONE','T-P-NOCARD','BAD_ROLE');

-- 청크와 상품 연결이 없는 문서의 근거, 승인되지 않은 근거, 대상이 없는 근거 연결
INSERT INTO db_pipeline.card_source_evidence (evidence_id, card_doc_id, page_no, card_doc_chunk_id, quote_txt, approval_status_cd)
VALUES ('T-E-1', 'T-D-OTHER', 1, 'T-C-NONE', '시험 인용', 'PENDING');
INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, evidence_id)
VALUES (999002, 'T-L-1', 'CARD', 'T-E-1');
INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, ev_item_cd, ev_item_key, evidence_id)
VALUES (999001, 'T-L-2', 'CARD', 'COND', 'no_such_atom', 'T-E-1');
INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, card_bnft_id, evidence_id)
VALUES (999001, 'T-L-3', 'BNFT', 'T-B-NONE', 'T-E-1');
INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, evidence_id)
VALUES (999001, 'T-L-4', 'CARD', 'T-E-MISSING');

DO $$
DECLARE
    v_gate text;
    v_found boolean;
    v_rejected boolean;
BEGIN
    -- 대체된 게이트와 유지된 게이트가 시험 행을 실제로 잡아야 한다.
    FOREACH v_gate IN ARRAY ARRAY[
        'bnft_without_product', 'pool_without_product', 'product_doc_without_product', 'product_doc_orphan',
        'pool_ref_orphan', 'rule_pool_product_orphan', 'rule_pool_benefit_orphan', 'rule_pool_rule_orphan', 'evidence_source_orphan', 'evidence_doc_not_linked', 'evidence_not_approved',
        'evidence_subject_orphan', 'evidence_item_key_missing', 'common_cd_invalid'] LOOP
        SELECT EXISTS (SELECT 1 FROM db_pipeline.v_card_integrity_issue i
                       WHERE i.gate_cd = v_gate
                         AND (i.issue_key LIKE '%999001%' OR i.issue_key LIKE '%999002%' OR i.issue_key LIKE 'T-%'
                              OR i.issue_key LIKE '%BAD_STATUS%')) INTO v_found;
        IF NOT v_found THEN
            RAISE EXCEPTION '게이트가 위반을 찾지 못했습니다: %', v_gate;
        END IF;
    END LOOP;

    -- 없어진 값과 구조는 입력 단계에서 거부되어야 한다.
    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, evidence_id)
        VALUES (999001, 'T-L-5', 'POLICY', 'T-E-1');
    EXCEPTION WHEN check_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION 'POLICY 대상이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, card_bnft_id, evidence_id)
        VALUES (999001, 'T-L-6', 'CARD', 'T-B-RULE', 'T-E-1');
    EXCEPTION WHEN check_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION 'CARD 대상의 혜택 컬럼이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        UPDATE db_pipeline.card_product SET card_cond_expr = '{"branches":[]}' WHERE card_id = 999001;
    EXCEPTION WHEN check_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '잘못된 카드 공통 조건이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_product_doc (card_id, card_doc_id, doc_role_cd, approval_status_cd, applicability_basis_txt, create_user_id, update_user_id)
        VALUES (999001, 'T-D-2', 'PRODUCT_GUIDE', 'APPROVED', '   ', 'V7_TEST', 'V7_TEST');
    EXCEPTION WHEN check_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '적용 근거 없는 승인이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_product_doc (card_id, card_doc_id, doc_role_cd, applicability_basis_txt, create_user_id, update_user_id)
        VALUES (999001, 'T-D-3', 'BRAND_SERVICE', '시험', 'V7_TEST', 'V7_TEST');
    EXCEPTION WHEN check_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '선택지 없는 브랜드 문서가 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, verification_status_cd)
        VALUES (999001, 'T-B-RULE', 'T-B-DUP', '시험', 'DISCOUNT', 'LOCAL', 'PRODUCT', 'PENDING_REVIEW');
    EXCEPTION WHEN unique_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '혜택 PK 중복이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, verification_status_cd)
        VALUES (999001, 'T-B-DUP2', 'T-B-RULE', '시험', 'DISCOUNT', 'LOCAL', 'PRODUCT', 'PENDING_REVIEW');
    EXCEPTION WHEN unique_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '혜택 코드 중복이 거부되지 않았습니다'; END IF;

    -- 최종 혜택은 반드시 카드에 속한다.
    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, verification_status_cd)
        VALUES (NULL, 'T-B-NULL', 'T-B-NULL', '시험', 'DISCOUNT', 'LOCAL', 'PRODUCT', 'PENDING_REVIEW');
    EXCEPTION WHEN not_null_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION 'card_bnft.card_id NULL이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, verification_status_cd)
        VALUES (999001, 'T-B-BRAND', 'T-B-BRAND', '시험', 'DISCOUNT', 'BRAND_SERVICE', 'PRODUCT', 'PENDING_REVIEW');
    EXCEPTION WHEN check_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '상품 전체 범위의 브랜드 혜택이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, verification_status_cd, bnft_valid_from, bnft_valid_to_excl)
        VALUES (999001, 'T-B-DATE', 'T-B-DATE', '시험', 'DISCOUNT', 'LOCAL', 'PRODUCT', 'PENDING_REVIEW', DATE '2027-01-01', DATE '2026-01-01');
    EXCEPTION WHEN check_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '뒤집힌 제공 기간이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_doc (card_doc_id, doc_cd, doc_title, doc_file_nm, doc_sha256, doc_collect_date, create_user_id, update_user_id)
        VALUES ('T-DOC-DUP', 'T_DOC_DUP', '시험', 'x.pdf', repeat('a', 64), now(), 'V7_TEST', 'V7_TEST');
    EXCEPTION WHEN unique_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '같은 해시의 문서 중복 등록이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, card_bnft_id, evidence_id)
        VALUES (999101, 'S-L-A2', 'BNFT', 'S-B-A', 'S-EV');
    EXCEPTION WHEN unique_violation THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '같은 카드의 같은 근거 연결 중복이 거부되지 않았습니다'; END IF;

    v_rejected := false;
    BEGIN
        PERFORM 'db_pipeline.card_bnft_common'::regclass;
    EXCEPTION WHEN undefined_table THEN v_rejected := true;
    END;
    IF NOT v_rejected THEN RAISE EXCEPTION '공통 혜택 테이블이 남아 있습니다'; END IF;

    RAISE NOTICE 'V7 integrity test passed';
END;
$$;

-- ---------------------------------------------------------------------------
-- 방식별 필수값 게이트. 확정 데이터 위반(*_missing)과 확정 전 값 누락(*_pending)을 구분한다
-- ---------------------------------------------------------------------------
INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, rule_list, verification_status_cd)
VALUES (999001, 'M-OK-PCT', 'M-OK-PCT', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"PERCENT_OF_TXN","payout_unit_cd":"HANAMONEY","rule_status_cd":"CONFIRMED","method_ver":1,"value_num":1.5,"value_unit_cd":"PERCENT","predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'CONFIRMED'),
       (999001, 'M-OK-FIX-P', 'M-OK-FIX-P', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"FIXED_PER_TXN","payout_unit_cd":"HANAMONEY","rule_status_cd":"CONFIRMED","method_ver":1,"value_num":100,"predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'CONFIRMED'),
       (999001, 'M-OK-FIX-M', 'M-OK-FIX-M', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"FIXED_PER_TXN","payout_unit_cd":"UNIMILE","rule_status_cd":"CONFIRMED","method_ver":1,"value_num":50,"value_unit_cd":"UNIMILE","predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'CONFIRMED'),
       (999001, 'M-OK-UNIT', 'M-OK-UNIT', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"UNITS_PER_AMOUNT","payout_unit_cd":"UNIMILE","rule_status_cd":"CONFIRMED","method_ver":1,"value_num":45,"value_unit_cd":"UNIMILE","basis_amt":1500,"predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'CONFIRMED'),
       (999001, 'M-OK-MUL', 'M-OK-MUL', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"MULTIPLY_EXTERNAL_POINTS","payout_unit_cd":"KRW","rule_status_cd":"CONFIRMED","method_ver":1,"value_num":2,"value_unit_cd":"MULTIPLIER","predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'CONFIRMED'),
       (999001, 'M-OK-FREE', 'M-OK-FREE', '시험', 'SERVICE', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"FREE_SERVICE","payout_unit_cd":"SERVICE","rule_status_cd":"CONFIRMED","method_ver":1,"predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'CONFIRMED'),
       (999001, 'M-DRAFT', 'M-DRAFT', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"FIXED_PER_TXN","payout_unit_cd":"KRW","rule_status_cd":"DRAFT","method_ver":1,"predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'PENDING_REVIEW'),
       (999001, 'M-RETIRED', 'M-RETIRED', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"UNITS_PER_AMOUNT","payout_unit_cd":"UNIMILE","rule_status_cd":"RETIRED","method_ver":1,"value_num":45,"predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'PENDING_REVIEW'),
       (999001, 'M-BAD-CONF', 'M-BAD-CONF', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"UNITS_PER_AMOUNT","payout_unit_cd":"UNIMILE","rule_status_cd":"CONFIRMED","method_ver":1,"value_num":45,"value_unit_cd":"UNIMILE","predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'CONFIRMED'),
       (999001, 'M-BAD-BNFT', 'M-BAD-BNFT', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"PERCENT_OF_TXN","payout_unit_cd":"KRW","rule_status_cd":"DRAFT","method_ver":1,"predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'CONFIRMED'),
       (999001, 'M-BAD-UNIT', 'M-BAD-UNIT', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"FIXED_PER_TXN","payout_unit_cd":"KRW","rule_status_cd":"CONFIRMED","method_ver":1,"value_num":5,"value_unit_cd":"PERCENT","predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'PENDING_REVIEW'),
       (999001, 'M-BAD-MUL', 'M-BAD-MUL', '시험', 'POINT', 'LOCAL', 'PRODUCT', '[{"rule_key":"R1","calc_method_cd":"MULTIPLY_EXTERNAL_POINTS","payout_unit_cd":"KRW","rule_status_cd":"CONFIRMED","method_ver":1,"value_num":2,"value_unit_cd":"KRW","predicate_state_cd":"PENDING_REVIEW","target_list":[{"target_type_cd":"MERCHANT","target_key":"T","target_nm":"T"}]}]', 'PENDING_REVIEW');

INSERT INTO db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_cond_expr, verification_status_cd)
VALUES (999001, 'P-OK-NONE', 'P-OK-NONE', '시험', 'POINT', 'LOCAL', 'PRODUCT', '{"expr_status_cd":"CONFIRMED","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"p_none","negate_yn":false,"cond_type_cd":"ETC","cond_status_cd":"CONFIRMED","cond_min_amt":null,"cond_max_amt_excl":null,"predicate_method_cd":null,"predicate_method_ver":null,"cond_params":null}]}]}', 'PENDING_REVIEW'),
       (999001, 'P-OK-MONTH', 'P-OK-MONTH', '시험', 'POINT', 'LOCAL', 'PRODUCT', '{"expr_status_cd":"CONFIRMED","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"p_month","negate_yn":false,"cond_type_cd":"ETC","cond_status_cd":"CONFIRMED","cond_min_amt":null,"cond_max_amt_excl":null,"predicate_method_cd":"MONTH_IN","predicate_method_ver":1,"cond_params":{"months":[2,3,8,9]}}]}]}', 'PENDING_REVIEW'),
       (999001, 'P-OK-EVERY', 'P-OK-EVERY', '시험', 'POINT', 'LOCAL', 'PRODUCT', '{"expr_status_cd":"CONFIRMED","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"p_every","negate_yn":false,"cond_type_cd":"ETC","cond_status_cd":"CONFIRMED","cond_min_amt":100000,"cond_max_amt_excl":null,"predicate_method_cd":"EVERY_MONTH_MIN_SPEND","predicate_method_ver":1,"cond_params":{"window_months":3}}]}]}', 'PENDING_REVIEW'),
       (999001, 'P-DRAFT', 'P-DRAFT', '시험', 'POINT', 'LOCAL', 'PRODUCT', '{"expr_status_cd":"DRAFT","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"p_draft","negate_yn":false,"cond_type_cd":"ETC","cond_status_cd":"DRAFT","cond_min_amt":null,"cond_max_amt_excl":null,"predicate_method_cd":"MONTH_IN","predicate_method_ver":1,"cond_params":null}]}]}', 'PENDING_REVIEW'),
       (999001, 'P-BAD-MONTH', 'P-BAD-MONTH', '시험', 'POINT', 'LOCAL', 'PRODUCT', '{"expr_status_cd":"CONFIRMED","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"p_bad_month","negate_yn":false,"cond_type_cd":"ETC","cond_status_cd":"CONFIRMED","cond_min_amt":null,"cond_max_amt_excl":null,"predicate_method_cd":"MONTH_IN","predicate_method_ver":1,"cond_params":{"months":[]}}]}]}', 'PENDING_REVIEW'),
       (999001, 'P-BAD-TYPE', 'P-BAD-TYPE', '시험', 'POINT', 'LOCAL', 'PRODUCT', '{"expr_status_cd":"CONFIRMED","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"p_bad_type","negate_yn":false,"cond_type_cd":"ETC","cond_status_cd":"CONFIRMED","cond_min_amt":null,"cond_max_amt_excl":null,"predicate_method_cd":"MONTH_IN","predicate_method_ver":1,"cond_params":{"months":"2월"}}]}]}', 'PENDING_REVIEW'),
       (999001, 'P-BAD-EVERY', 'P-BAD-EVERY', '시험', 'POINT', 'LOCAL', 'PRODUCT', '{"expr_status_cd":"CONFIRMED","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"p_bad_every","negate_yn":false,"cond_type_cd":"ETC","cond_status_cd":"CONFIRMED","cond_min_amt":null,"cond_max_amt_excl":null,"predicate_method_cd":"EVERY_MONTH_MIN_SPEND","predicate_method_ver":1,"cond_params":{"window_months":3}}]}]}', 'PENDING_REVIEW');

DO $$
DECLARE
    v_pair text[];
    v_bad text;
BEGIN
    FOREACH v_pair SLICE 1 IN ARRAY ARRAY[
        ['rule_method_value_missing', '999001/M-BAD-CONF/R1'],
        ['rule_method_value_missing', '999001/M-BAD-BNFT/R1'],
        ['rule_method_value_missing', '999001/M-BAD-UNIT/R1'],
        ['rule_method_value_missing', '999001/M-BAD-MUL/R1'],
        ['rule_method_value_pending', '999001/M-DRAFT/R1'],
        ['predicate_params_missing', 'BNFT/999001/p_bad_month'],
        ['predicate_params_missing', 'BNFT/999001/p_bad_type'],
        ['predicate_params_missing', 'BNFT/999001/p_bad_every'],
        ['predicate_params_pending', 'BNFT/999001/p_draft']] LOOP
        IF NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_integrity_issue i WHERE i.gate_cd = v_pair[1] AND i.issue_key = v_pair[2]) THEN
            RAISE EXCEPTION '게이트가 찾지 못했습니다: % %', v_pair[1], v_pair[2];
        END IF;
    END LOOP;

    -- 포인트·마일리지·무상 서비스, 필수 파라미터가 없는 조건, 폐기 항목은 걸리면 안 된다.
    SELECT string_agg(i.gate_cd || '=' || i.issue_key, ', ') INTO v_bad
    FROM db_pipeline.v_card_integrity_issue i
    WHERE i.gate_cd IN ('rule_method_value_missing', 'rule_method_value_pending', 'predicate_params_missing', 'predicate_params_pending')
      AND (i.issue_key LIKE '%/M-OK-%' OR i.issue_key LIKE '%/M-RETIRED/%' OR i.issue_key LIKE '%/p_none'
           OR i.issue_key LIKE '%/p_month' OR i.issue_key LIKE '%/p_every');
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '정상 항목이 게이트에 걸렸습니다: %', v_bad;
    END IF;

    -- 값 누락은 드러내기만 한다. 자동으로 채우지 않는다.
    IF (SELECT rule_list->0 ? 'value_num' FROM db_pipeline.card_bnft WHERE card_id = 999001 AND card_bnft_id = 'M-DRAFT') THEN
        RAISE EXCEPTION '누락 값이 채워졌습니다';
    END IF;

    IF to_regclass('db_pipeline.card_method_catalog') IS NOT NULL THEN
        RAISE EXCEPTION '방법 카탈로그가 남아 있습니다';
    END IF;
END;
$$;

ROLLBACK;
