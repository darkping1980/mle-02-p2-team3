-- =====================================================================================================
-- 계산 구조 정리 복구. db_pipeline_calc_structure_cleanup.sql 실행 전 상태로 되돌린다.
-- 정의와 값은 정리 전 실제 DB에서 추출했다(docs/schema_cleanup/pre_cleanup_catalog.json, pre_cleanup_data.json).
-- 복구한 컬럼(card_bnft.rule_select_cd, card_extr_stg.card_excl_item_id)은 테이블 맨 뒤에 추가된다(값은 정리 전에도 모두 NULL).
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = pg_catalog;

DROP VIEW db_pipeline.v_card_integrity_issue;
DROP VIEW db_pipeline.v_common_cd_usage;
DROP VIEW db_pipeline.v_card_rule_target;
DROP VIEW db_pipeline.v_card_cond_atom;
DROP VIEW db_pipeline.v_card_rule;

-- 1. 함수(정리 전 정의)
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_cond_expr(p_expr jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_branch jsonb;
    v_atom jsonb;
    v_branch_nos integer[] := '{}';
    v_atom_keys text[] := '{}';
    v_atom_seqs integer[];
    v_branch_no integer;
    v_atom_seq integer;
    v_key text;
    v_type text;
BEGIN
    IF p_expr IS NULL THEN
        RETURN true;
    END IF;
    IF jsonb_typeof(p_expr) <> 'object'
       OR coalesce(p_expr->>'expr_status_cd', '') = ''
       OR jsonb_typeof(p_expr->'branches') IS DISTINCT FROM 'array'
       OR jsonb_array_length(p_expr->'branches') = 0 THEN
        RETURN false;
    END IF;

    FOR v_branch IN SELECT value FROM jsonb_array_elements(p_expr->'branches') LOOP
        IF jsonb_typeof(v_branch) <> 'object'
           OR jsonb_typeof(v_branch->'branch_no') IS DISTINCT FROM 'number'
           OR jsonb_typeof(v_branch->'atoms') IS DISTINCT FROM 'array'
           OR jsonb_array_length(v_branch->'atoms') = 0 THEN
            RETURN false;
        END IF;
        v_branch_no := (v_branch->>'branch_no')::integer;
        IF v_branch_no < 1 OR v_branch_no = ANY (v_branch_nos) THEN
            RETURN false;
        END IF;
        v_branch_nos := v_branch_nos || v_branch_no;
        v_atom_seqs := '{}';

        FOR v_atom IN SELECT value FROM jsonb_array_elements(v_branch->'atoms') LOOP
            IF jsonb_typeof(v_atom) <> 'object'
               OR jsonb_typeof(v_atom->'atom_seq') IS DISTINCT FROM 'number'
               OR jsonb_typeof(v_atom->'negate_yn') IS DISTINCT FROM 'boolean' THEN
                RETURN false;
            END IF;
            v_atom_seq := (v_atom->>'atom_seq')::integer;
            v_key := v_atom->>'atom_key';
            v_type := v_atom->>'cond_type_cd';
            IF v_atom_seq < 1 OR v_atom_seq = ANY (v_atom_seqs)
               OR coalesce(v_key, '') !~ '^[A-Za-z0-9_.:-]{1,40}$'
               OR coalesce(v_type, '') = ''
               OR coalesce(v_atom->>'cond_status_cd', '') = '' THEN
                RETURN false;
            END IF;
            v_atom_seqs := v_atom_seqs || v_atom_seq;

            -- 같은 atom_key를 여러 branch에서 다시 쓰는 것은 금지. 근거 연결 키가 모호해지기 때문
            IF v_key = ANY (v_atom_keys) THEN
                RETURN false;
            END IF;
            v_atom_keys := v_atom_keys || v_key;

            IF jsonb_typeof(v_atom->'cond_min_amt') NOT IN ('number','null')
               OR jsonb_typeof(v_atom->'cond_max_amt_excl') NOT IN ('number','null') THEN
                RETURN false;
            END IF;
            IF (v_atom->>'cond_min_amt')::numeric < 0
               OR (v_atom->>'cond_max_amt_excl')::numeric <= (v_atom->>'cond_min_amt')::numeric THEN
                RETURN false;
            END IF;
            IF v_type = 'SPEND_REQ' AND coalesce(v_atom->>'cond_basis_cd', '') = '' THEN
                RETURN false;
            END IF;
            IF v_type IN ('SPEND_EXCL','BNFT_EXCL')
               AND coalesce(v_atom->>'card_excl_item_id', v_atom->>'excl_raw_txt', '') = '' THEN
                RETURN false;
            END IF;
            -- 술어 방법 코드와 버전은 짝으로 저장
            IF (v_atom->>'predicate_method_cd' IS NULL) <> (v_atom->>'predicate_method_ver' IS NULL) THEN
                RETURN false;
            END IF;
            IF jsonb_typeof(v_atom->'predicate_method_ver') NOT IN ('number','null') THEN
                RETURN false;
            END IF;
            IF (v_atom->>'predicate_method_ver')::integer < 1 THEN
                RETURN false;
            END IF;
            IF jsonb_typeof(v_atom->'cond_params') NOT IN ('object','null') THEN
                RETURN false;
            END IF;
        END LOOP;
    END LOOP;
    RETURN true;
END;
$function$;
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_rule jsonb;
    v_keys text[] := '{}';
    v_state text;
BEGIN
    IF jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN
        RETURN false;
    END IF;
    FOR v_rule IN SELECT value FROM jsonb_array_elements(p_list) LOOP
        IF jsonb_typeof(v_rule) <> 'object'
           OR coalesce(v_rule->>'rule_key', '') !~ '^[A-Za-z0-9_.:-]{1,40}$'
           OR v_rule->>'rule_key' = ANY (v_keys)
           OR coalesce(v_rule->>'calc_method_cd', '') = ''
           OR coalesce(v_rule->>'payout_unit_cd', '') = ''
           OR coalesce(v_rule->>'rule_status_cd', '') = ''
           OR jsonb_typeof(v_rule->'method_ver') IS DISTINCT FROM 'number'
           OR (v_rule->>'method_ver')::integer < 1 THEN
            RETURN false;
        END IF;
        v_keys := v_keys || (v_rule->>'rule_key');

        IF coalesce(jsonb_typeof(v_rule->'value_num'), 'null') NOT IN ('number','null')
           OR coalesce(jsonb_typeof(v_rule->'basis_amt'), 'null') NOT IN ('number','null')
           OR coalesce(jsonb_typeof(v_rule->'rule_priority'), 'null') NOT IN ('number','null')
           OR coalesce(jsonb_typeof(v_rule->'calc_params'), 'null') NOT IN ('object','null') THEN
            RETURN false;
        END IF;
        IF coalesce((v_rule->>'value_num')::numeric, 0) < 0
           OR coalesce((v_rule->>'basis_amt')::numeric, 0) < 0 THEN
            RETURN false;
        END IF;

        v_state := v_rule->>'predicate_state_cd';
        IF NOT db_pipeline.fn_valid_cond_expr(nullif(v_rule->'cond_expr', 'null'::jsonb)) THEN
            RETURN false;
        END IF;
        IF v_state = 'CONDITIONAL' AND coalesce(jsonb_typeof(v_rule->'cond_expr'), 'null') = 'null' THEN
            RETURN false;
        END IF;
        IF v_state = 'VERIFIED_UNCONDITIONAL' AND coalesce(jsonb_typeof(v_rule->'cond_expr'), 'null') <> 'null' THEN
            RETURN false;
        END IF;
        IF coalesce(v_state, '') = '' THEN
            RETURN false;
        END IF;

        IF NOT db_pipeline.fn_valid_target_list(coalesce(v_rule->'target_list', '[]'::jsonb)) THEN
            RETURN false;
        END IF;
        IF v_rule->>'rule_status_cd' = 'CONFIRMED'
           AND coalesce(jsonb_array_length(v_rule->'target_list'), 0) = 0 THEN
            RETURN false;
        END IF;

        IF p_owner IS DISTINCT FROM 'LOCAL' OR v_rule ? 'pool_refs' THEN
            RETURN false;
        END IF;
    END LOOP;
    RETURN true;
END;
$function$;
CREATE OR REPLACE FUNCTION db_pipeline.fn_cond_spend_bound(p_expr jsonb, p_bound text)
 RETURNS numeric
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
    SELECT CASE WHEN count(*) = 1 THEN max((a.value->>p_bound)::numeric) END
    FROM jsonb_array_elements(p_expr->'branches') AS b(value)
    CROSS JOIN LATERAL jsonb_array_elements(b.value->'atoms') AS a(value)
    WHERE jsonb_array_length(p_expr->'branches') = 1
      AND a.value->>'cond_type_cd' = 'SPEND_REQ'
      AND a.value->>'cond_basis_cd' = 'PREV_MONTH_SPEND'
      AND (a.value->>'negate_yn')::boolean = false
$function$;
COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(jsonb, text) IS '계산 규칙 목록 JSONB 계약 검증. 최종 규칙에는 pool_refs를 허용하지 않는다. p_owner는 LOCAL만 허용';
COMMENT ON FUNCTION db_pipeline.fn_valid_cond_expr(jsonb) IS '조건식 JSONB 계약 검증. branch 사이 OR, branch 안 atom AND, negate_yn=NOT';
COMMENT ON FUNCTION db_pipeline.fn_cond_spend_bound(jsonb, text) IS '단일 branch의 전월 실적 구간 값 추출. OR식이나 구간 atom이 둘 이상이면 NULL을 반환하고 v_card_cond_atom으로 조회';
ALTER FUNCTION db_pipeline.fn_cond_spend_bound(jsonb, text) OWNER TO postgres;

-- 2. 테이블·컬럼
CREATE TABLE db_pipeline.card_excl_item (
    card_excl_item_id character varying(20) NOT NULL DEFAULT db_pipeline.fn_get_biz_id('card_excl_item'::text),
    issuer text NOT NULL,
    excl_item_nm text NOT NULL,
    excl_concept_cd character varying(50),
    excl_item_desc text,
    excl_alias_nms text[] NOT NULL DEFAULT '{}'::text[],
    create_date timestamp with time zone NOT NULL DEFAULT now(),
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone NOT NULL DEFAULT now(),
    update_user_id character varying(50) NOT NULL
);
ALTER TABLE db_pipeline.card_excl_item ADD CONSTRAINT card_excl_item_pkey PRIMARY KEY (card_excl_item_id);
ALTER TABLE db_pipeline.card_excl_item ADD CONSTRAINT card_excl_item_issuer_excl_item_nm_key UNIQUE (issuer, excl_item_nm);
CREATE INDEX ix_card_excl_item_alias_gin ON db_pipeline.card_excl_item USING gin (excl_alias_nms);
CREATE INDEX ix_card_excl_item_concept_key ON db_pipeline.card_excl_item USING btree (excl_concept_cd);
COMMENT ON TABLE db_pipeline.card_excl_item IS '제외 항목 사전(검토중 일단 보류)';
COMMENT ON COLUMN db_pipeline.card_excl_item.card_excl_item_id IS '제외 항목 아이디';
COMMENT ON COLUMN db_pipeline.card_excl_item.issuer IS '카드사';
COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_nm IS '제외 항목명';
COMMENT ON COLUMN db_pipeline.card_excl_item.excl_concept_cd IS '제외 분류 개념';
COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_desc IS '제외 항목 설명';
COMMENT ON COLUMN db_pipeline.card_excl_item.excl_alias_nms IS '제외 항목 별칭';
COMMENT ON COLUMN db_pipeline.card_excl_item.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_excl_item.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_excl_item.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_excl_item.update_user_id IS '수정 사용자 아이디';
ALTER TABLE db_pipeline.card_excl_item OWNER TO postgres;
ALTER TABLE db_pipeline.card_bnft ADD COLUMN rule_select_cd character varying(30);
COMMENT ON COLUMN db_pipeline.card_bnft.rule_select_cd IS '규칙 선택 방식';
ALTER TABLE db_pipeline.card_extr_stg ADD COLUMN card_excl_item_id character varying(20);
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_excl_item_id IS '제외 항목 아이디';
CREATE INDEX ix_card_extr_stg_excl_item_key ON db_pipeline.card_extr_stg USING btree (card_excl_item_id);

-- 3. 데이터(정리 전 JSON 원본)
UPDATE db_pipeline.card_bnft SET rule_list = '[{"rule_key": "one_pick_100", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_one_pick_100", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 3000, "cond_raw_txt": "결제 건당\n3천원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 100, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "CU", "target_key": "CU", "target_type_cd": "MERCHANT"}, {"target_nm": "GS25", "target_key": "GS25", "target_type_cd": "MERCHANT"}, {"target_nm": "세븐일레븐", "target_key": "세븐일레븐", "target_type_cd": "MERCHANT"}, {"target_nm": "메가MGC커피", "target_key": "메가MGC커피", "target_type_cd": "MERCHANT"}, {"target_nm": "이디야커피", "target_key": "이디야커피", "target_type_cd": "MERCHANT"}, {"target_nm": "컴포즈커피", "target_key": "컴포즈커피", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}, {"rule_key": "one_pick_500", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_one_pick_500", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 10000, "cond_raw_txt": "결제 건당\n1만원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 500, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "CU", "target_key": "CU", "target_type_cd": "MERCHANT"}, {"target_nm": "GS25", "target_key": "GS25", "target_type_cd": "MERCHANT"}, {"target_nm": "세븐일레븐", "target_key": "세븐일레븐", "target_type_cd": "MERCHANT"}, {"target_nm": "메가MGC커피", "target_key": "메가MGC커피", "target_type_cd": "MERCHANT"}, {"target_nm": "이디야커피", "target_key": "이디야커피", "target_type_cd": "MERCHANT"}, {"target_nm": "컴포즈커피", "target_key": "컴포즈커피", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}]'::jsonb, bnft_cond_expr = NULL WHERE card_id = 2 AND card_bnft_id = '20261101_000001';
UPDATE db_pipeline.card_bnft SET rule_list = '[{"rule_key": "style_100", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_style_100", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 3000, "cond_raw_txt": "결제 건당\n3천원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 100, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "다이소", "target_key": "다이소", "target_type_cd": "MERCHANT"}, {"target_nm": "올리브영", "target_key": "올리브영", "target_type_cd": "MERCHANT"}, {"target_nm": "교보문고", "target_key": "교보문고", "target_type_cd": "MERCHANT"}, {"target_nm": "영풍문고", "target_key": "영풍문고", "target_type_cd": "MERCHANT"}, {"target_nm": "알라딘", "target_key": "알라딘", "target_type_cd": "MERCHANT"}, {"target_nm": "yes24", "target_key": "yes24", "target_type_cd": "MERCHANT"}, {"target_nm": "아트박스", "target_key": "아트박스", "target_type_cd": "MERCHANT"}, {"target_nm": "무신사", "target_key": "무신사", "target_type_cd": "MERCHANT"}, {"target_nm": "에이블리", "target_key": "에이블리", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}, {"rule_key": "style_500", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_style_500", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 10000, "cond_raw_txt": "결제 건당\n1만원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 500, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "다이소", "target_key": "다이소", "target_type_cd": "MERCHANT"}, {"target_nm": "올리브영", "target_key": "올리브영", "target_type_cd": "MERCHANT"}, {"target_nm": "교보문고", "target_key": "교보문고", "target_type_cd": "MERCHANT"}, {"target_nm": "영풍문고", "target_key": "영풍문고", "target_type_cd": "MERCHANT"}, {"target_nm": "알라딘", "target_key": "알라딘", "target_type_cd": "MERCHANT"}, {"target_nm": "yes24", "target_key": "yes24", "target_type_cd": "MERCHANT"}, {"target_nm": "아트박스", "target_key": "아트박스", "target_type_cd": "MERCHANT"}, {"target_nm": "무신사", "target_key": "무신사", "target_type_cd": "MERCHANT"}, {"target_nm": "에이블리", "target_key": "에이블리", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}]'::jsonb, bnft_cond_expr = NULL WHERE card_id = 2 AND card_bnft_id = '20261101_000002';
UPDATE db_pipeline.card_bnft SET rule_list = '[{"rule_key": "transit_rate", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "transit_exclusions", "atom_seq": 1, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 5, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "버스", "target_key": "버스", "target_type_cd": "SERVICE"}, {"target_nm": "지하철", "target_key": "지하철", "target_type_cd": "SERVICE"}], "rule_priority": null, "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}]'::jsonb, bnft_cond_expr = '{"branches": [{"atoms": [{"atom_key": "transit_spend", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 100000, "cond_raw_txt": "- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\n ONE MORE 서비스 제공", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "spend_exclusions", "atom_seq": 2, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}, {"atoms": [{"atom_key": "transit_grace", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공", "cond_type_cd": "GRACE", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 2}], "expr_status_cd": "DRAFT"}'::jsonb WHERE card_id = 2 AND card_bnft_id = '20261101_000003';
UPDATE db_pipeline.card_bnft SET rule_list = '[{"rule_key": "amusement_rate", "basis_amt": null, "cond_expr": null, "value_num": 50, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "에버랜드", "target_key": "에버랜드", "target_type_cd": "MERCHANT"}, {"target_nm": "롯데월드", "target_key": "롯데월드", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "PENDING_REVIEW"}]'::jsonb, bnft_cond_expr = '{"branches": [{"atoms": [{"atom_key": "amusement_spend", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 200000, "cond_raw_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "amusement_first_month", "atom_seq": 2, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "최초 발급 월에는\n서비스 미제공", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "최초 발급 월에는\n서비스 미제공", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "spend_exclusions", "atom_seq": 3, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "amusement_per_person", "atom_seq": 4, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "1인 1매", "cond_type_cd": "ETC", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}'::jsonb WHERE card_id = 2 AND card_bnft_id = '20261101_000004';
UPDATE db_pipeline.card_bnft SET rule_list = '[]'::jsonb, bnft_cond_expr = NULL WHERE card_id = 5 AND card_bnft_id = '20261102_000008';
UPDATE db_pipeline.card_product SET card_cond_expr = '{"branches": [{"atoms": [{"atom_key": "common_service_exclusion", "atom_seq": 1, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "common_channel", "atom_seq": 2, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "PAYMENT_METHOD", "excl_raw_txt": "배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "merchant_classification", "atom_seq": 3, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공", "cond_type_cd": "MERCHANT_RULE", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}'::jsonb WHERE card_id = 2;

-- 4. 뷰(정리 전 정의)
CREATE VIEW db_pipeline.v_card_rule AS
 SELECT b.card_id,
    b.card_bnft_id,
    r.value ->> 'rule_key'::text AS rule_key,
    r.ord AS rule_seq,
    NULLIF(r.value -> 'cond_expr'::text, 'null'::jsonb) AS cond_expr,
    db_pipeline.fn_cond_spend_bound(NULLIF(r.value -> 'cond_expr'::text, 'null'::jsonb), 'cond_min_amt'::text)::numeric(18,2) AS spend_min_amt,
    db_pipeline.fn_cond_spend_bound(NULLIF(r.value -> 'cond_expr'::text, 'null'::jsonb), 'cond_max_amt_excl'::text)::numeric(18,2) AS spend_max_amt_excl,
    COALESCE(r.value -> 'target_list'::text, '[]'::jsonb) AS target_list,
    r.value ->> 'predicate_state_cd'::text AS predicate_state_cd,
    r.value ->> 'calc_method_cd'::text AS calc_method_cd,
    (r.value ->> 'method_ver'::text)::integer AS method_ver,
    ((r.value ->> 'value_num'::text))::numeric(18,4) AS value_num,
    r.value ->> 'value_unit_cd'::text AS value_unit_cd,
    r.value ->> 'payout_unit_cd'::text AS payout_unit_cd,
    ((r.value ->> 'basis_amt'::text))::numeric(18,2) AS basis_amt,
    NULLIF(r.value -> 'calc_params'::text, 'null'::jsonb) AS calc_params,
    (r.value ->> 'rule_priority'::text)::integer AS rule_priority,
    r.value ->> 'rule_status_cd'::text AS rule_status_cd
   FROM db_pipeline.card_bnft b
     CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value, ord);
CREATE VIEW db_pipeline.v_card_bnft_rule_effective AS
 SELECT b.card_id,
    b.card_bnft_id,
    b.bnft_nm,
    b.bnft_origin_cd,
    b.bnft_scope_cd,
    b.bnft_brand_opt_cds,
    b.bnft_valid_from,
    b.bnft_valid_to_excl,
    r.rule_key,
    r.calc_method_cd,
    r.method_ver,
    r.value_num,
    r.value_unit_cd,
    r.payout_unit_cd,
    r.basis_amt,
    r.calc_params,
    r.predicate_state_cd,
    r.target_list,
    b.bnft_cond_expr,
    r.cond_expr AS rule_cond_expr,
    r.rule_status_cd
   FROM db_pipeline.card_bnft b
     JOIN db_pipeline.v_card_rule r ON r.card_id = b.card_id AND r.card_bnft_id::text = b.card_bnft_id::text;
CREATE VIEW db_pipeline.v_card_cond_atom AS
 WITH src AS (
         SELECT 'CARD'::text AS owner_cd,
            p.card_id,
            NULL::character varying AS card_bnft_id,
            NULL::text AS rule_key,
            p.card_cond_expr AS expr
           FROM db_pipeline.card_product p
          WHERE p.card_cond_expr IS NOT NULL
        UNION ALL
         SELECT 'BNFT'::text,
            b_1.card_id,
            b_1.card_bnft_id,
            NULL::text,
            b_1.bnft_cond_expr
           FROM db_pipeline.card_bnft b_1
          WHERE b_1.bnft_cond_expr IS NOT NULL
        UNION ALL
         SELECT 'RULE'::text,
            r.card_id,
            r.card_bnft_id,
            r.rule_key,
            r.cond_expr
           FROM db_pipeline.v_card_rule r
          WHERE r.cond_expr IS NOT NULL
        )
 SELECT s.owner_cd,
    s.card_id,
    s.card_bnft_id,
    s.rule_key,
    s.expr ->> 'expr_status_cd'::text AS expr_status_cd,
    (b.value ->> 'branch_no'::text)::integer AS branch_no,
    (a.value ->> 'atom_seq'::text)::integer AS atom_seq,
    a.value ->> 'atom_key'::text AS atom_key,
    (a.value ->> 'negate_yn'::text)::boolean AS negate_yn,
    a.value ->> 'cond_type_cd'::text AS cond_type_cd,
    a.value ->> 'cond_basis_cd'::text AS cond_basis_cd,
    ((a.value ->> 'cond_min_amt'::text))::numeric(18,2) AS cond_min_amt,
    ((a.value ->> 'cond_max_amt_excl'::text))::numeric(18,2) AS cond_max_amt_excl,
    a.value ->> 'predicate_method_cd'::text AS predicate_method_cd,
    (a.value ->> 'predicate_method_ver'::text)::integer AS predicate_method_ver,
    a.value -> 'cond_params'::text AS cond_params,
    a.value ->> 'card_excl_item_id'::text AS card_excl_item_id,
    a.value ->> 'excl_raw_txt'::text AS excl_raw_txt,
    a.value ->> 'cond_raw_txt'::text AS cond_raw_txt,
    a.value ->> 'link_role_cd'::text AS link_role_cd,
    a.value ->> 'cond_status_cd'::text AS cond_status_cd
   FROM src s
     CROSS JOIN LATERAL jsonb_array_elements(s.expr -> 'branches'::text) b(value)
     CROSS JOIN LATERAL jsonb_array_elements(b.value -> 'atoms'::text) a(value);
CREATE VIEW db_pipeline.v_card_rule_target AS
 SELECT r.card_id,
    r.card_bnft_id,
    r.rule_key,
    t.value ->> 'target_type_cd'::text AS target_type_cd,
    t.value ->> 'target_key'::text AS target_key,
    t.value ->> 'target_nm'::text AS target_nm
   FROM db_pipeline.v_card_rule r
     CROSS JOIN LATERAL jsonb_array_elements(r.target_list) t(value);
CREATE VIEW db_pipeline.v_common_cd_usage AS
 SELECT 'card_product.card_kind_cd'::text AS source_nm,
    'CARD_KIND'::character varying(20) AS common_code_grp_id,
    card_product.card_kind_cd::text AS cd_value
   FROM db_pipeline.card_product
  WHERE card_product.card_kind_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.product_status_cd'::text AS source_nm,
    'PRODUCT_STATUS'::character varying(20) AS common_code_grp_id,
    card_product.product_status_cd::text AS cd_value
   FROM db_pipeline.card_product
  WHERE card_product.product_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.card_cond_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying(20) AS common_code_grp_id,
    card_product.card_cond_status_cd::text AS cd_value
   FROM db_pipeline.card_product
  WHERE card_product.card_cond_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_product_doc.doc_role_cd'::text AS source_nm,
    'DOC_ROLE'::character varying(20) AS common_code_grp_id,
    card_product_doc.doc_role_cd::text AS cd_value
   FROM db_pipeline.card_product_doc
  WHERE card_product_doc.doc_role_cd IS NOT NULL
UNION ALL
 SELECT 'card_product_doc.approval_status_cd'::text AS source_nm,
    'APPROVAL_STATUS'::character varying(20) AS common_code_grp_id,
    card_product_doc.approval_status_cd::text AS cd_value
   FROM db_pipeline.card_product_doc
  WHERE card_product_doc.approval_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.bnft_type_cd'::text AS source_nm,
    'BNFT_TYPE'::character varying(20) AS common_code_grp_id,
    card_bnft.bnft_type_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.bnft_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.bnft_origin_cd'::text AS source_nm,
    'BNFT_ORIGIN'::character varying(20) AS common_code_grp_id,
    card_bnft.bnft_origin_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.bnft_origin_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.bnft_scope_cd'::text AS source_nm,
    'BNFT_SCOPE'::character varying(20) AS common_code_grp_id,
    card_bnft.bnft_scope_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.bnft_scope_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_select_cd'::text AS source_nm,
    'RULE_SELECT'::character varying(20) AS common_code_grp_id,
    card_bnft.rule_select_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.rule_select_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.verification_status_cd'::text AS source_nm,
    'VERIFY_STATUS'::character varying(20) AS common_code_grp_id,
    card_bnft.verification_status_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.verification_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_source_evidence.approval_status_cd'::text AS source_nm,
    'APPROVAL_STATUS'::character varying(20) AS common_code_grp_id,
    card_source_evidence.approval_status_cd::text AS cd_value
   FROM db_pipeline.card_source_evidence
  WHERE card_source_evidence.approval_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_evidence_link.ev_subject_cd'::text AS source_nm,
    'EV_SUBJECT'::character varying(20) AS common_code_grp_id,
    card_evidence_link.ev_subject_cd::text AS cd_value
   FROM db_pipeline.card_evidence_link
  WHERE card_evidence_link.ev_subject_cd IS NOT NULL
UNION ALL
 SELECT 'card_evidence_link.ev_item_cd'::text AS source_nm,
    'EV_ITEM'::character varying(20) AS common_code_grp_id,
    card_evidence_link.ev_item_cd::text AS cd_value
   FROM db_pipeline.card_evidence_link
  WHERE card_evidence_link.ev_item_cd IS NOT NULL
UNION ALL
 SELECT 'card_doc.doc_type_cd'::text AS source_nm,
    'DOC_TYPE'::character varying(20) AS common_code_grp_id,
    card_doc.doc_type_cd::text AS cd_value
   FROM db_pipeline.card_doc
  WHERE card_doc.doc_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_doc.doc_status'::text AS source_nm,
    'DOC_STATUS'::character varying(20) AS common_code_grp_id,
    card_doc.doc_status::text AS cd_value
   FROM db_pipeline.card_doc
  WHERE card_doc.doc_status IS NOT NULL
UNION ALL
 SELECT 'card_doc_page.page_layer_cd'::text AS source_nm,
    'PAGE_LAYER'::character varying(20) AS common_code_grp_id,
    card_doc_page.page_layer_cd::text AS cd_value
   FROM db_pipeline.card_doc_page
  WHERE card_doc_page.page_layer_cd IS NOT NULL
UNION ALL
 SELECT 'card_doc_chunk.chunk_type_cd'::text AS source_nm,
    'CHUNK_TYPE'::character varying(20) AS common_code_grp_id,
    card_doc_chunk.chunk_type_cd::text AS cd_value
   FROM db_pipeline.card_doc_chunk
  WHERE card_doc_chunk.chunk_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_doc_chunk.chunk_status'::text AS source_nm,
    'CHUNK_STATUS'::character varying(20) AS common_code_grp_id,
    card_doc_chunk.chunk_status::text AS cd_value
   FROM db_pipeline.card_doc_chunk
  WHERE card_doc_chunk.chunk_status IS NOT NULL
UNION ALL
 SELECT 'card_ai_run.run_stage_cd'::text AS source_nm,
    'RUN_STAGE'::character varying(20) AS common_code_grp_id,
    card_ai_run.run_stage_cd::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE card_ai_run.run_stage_cd IS NOT NULL
UNION ALL
 SELECT 'card_ai_run.run_call_mthd_cd'::text AS source_nm,
    'RUN_CALL_METHOD'::character varying(20) AS common_code_grp_id,
    card_ai_run.run_call_mthd_cd::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE card_ai_run.run_call_mthd_cd IS NOT NULL
UNION ALL
 SELECT 'card_ai_run.run_status'::text AS source_nm,
    'RUN_STATUS'::character varying(20) AS common_code_grp_id,
    card_ai_run.run_status::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE card_ai_run.run_status IS NOT NULL
UNION ALL
 SELECT 'card_ai_call.call_status'::text AS source_nm,
    'CALL_STATUS'::character varying(20) AS common_code_grp_id,
    card_ai_call.call_status::text AS cd_value
   FROM db_pipeline.card_ai_call
  WHERE card_ai_call.call_status IS NOT NULL
UNION ALL
 SELECT 'card_extr_stg.stg_kind_cd'::text AS source_nm,
    'STG_KIND'::character varying(20) AS common_code_grp_id,
    card_extr_stg.stg_kind_cd::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE card_extr_stg.stg_kind_cd IS NOT NULL
UNION ALL
 SELECT 'card_extr_stg.stg_status'::text AS source_nm,
    'STG_STATUS'::character varying(20) AS common_code_grp_id,
    card_extr_stg.stg_status::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE card_extr_stg.stg_status IS NOT NULL
UNION ALL
 SELECT 'card_extr_stg.stg_ai_vrfy_cd'::text AS source_nm,
    'STG_AI_VRFY'::character varying(20) AS common_code_grp_id,
    card_extr_stg.stg_ai_vrfy_cd::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE card_extr_stg.stg_ai_vrfy_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.brand_opt_list[].brand_cd'::text AS source_nm,
    'BRAND'::character varying AS common_code_grp_id,
    v_card_brand_opt.brand_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE v_card_brand_opt.brand_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.brand_opt_list[].service_grade_cd'::text AS source_nm,
    'SERVICE_GRADE'::character varying AS common_code_grp_id,
    v_card_brand_opt.service_grade_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE v_card_brand_opt.service_grade_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.brand_opt_list[].service_type_cd'::text AS source_nm,
    'SERVICE_TYPE'::character varying AS common_code_grp_id,
    v_card_brand_opt.service_type_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE v_card_brand_opt.service_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.brand_opt_list[].brand_opt_status_cd'::text AS source_nm,
    'PRODUCT_STATUS'::character varying AS common_code_grp_id,
    v_card_brand_opt.brand_opt_status_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE v_card_brand_opt.brand_opt_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].predicate_state_cd'::text AS source_nm,
    'PREDICATE_STATE'::character varying AS common_code_grp_id,
    v_card_rule.predicate_state_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.predicate_state_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].calc_method_cd'::text AS source_nm,
    'CALC_METHOD'::character varying AS common_code_grp_id,
    v_card_rule.calc_method_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.calc_method_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].value_unit_cd'::text AS source_nm,
    'VALUE_UNIT'::character varying AS common_code_grp_id,
    v_card_rule.value_unit_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.value_unit_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].payout_unit_cd'::text AS source_nm,
    'PAYOUT_UNIT'::character varying AS common_code_grp_id,
    v_card_rule.payout_unit_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.payout_unit_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].rule_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_rule.rule_status_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.rule_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.relation_list[].rel_type_cd'::text AS source_nm,
    'REL_TYPE'::character varying AS common_code_grp_id,
    v_card_bnft_rel.rel_type_cd AS cd_value
   FROM db_pipeline.v_card_bnft_rel
  WHERE v_card_bnft_rel.rel_type_cd IS NOT NULL AND NOT v_card_bnft_rel.reverse_yn
UNION ALL
 SELECT 'rule_list[].target_list[].target_type_cd'::text AS source_nm,
    'TARGET_TYPE'::character varying AS common_code_grp_id,
    v_card_rule_target.target_type_cd AS cd_value
   FROM db_pipeline.v_card_rule_target
  WHERE v_card_rule_target.target_type_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr atom cond_type_cd'::text AS source_nm,
    'COND_TYPE'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_type_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.cond_type_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr atom cond_basis_cd'::text AS source_nm,
    'COND_BASIS'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_basis_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.cond_basis_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr atom predicate_method_cd'::text AS source_nm,
    'PREDICATE_METHOD'::character varying AS common_code_grp_id,
    v_card_cond_atom.predicate_method_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.predicate_method_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr atom cond_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_status_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.cond_status_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr.expr_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_cond_atom.expr_status_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.expr_status_cd IS NOT NULL;
CREATE VIEW db_pipeline.v_card_integrity_issue AS
 WITH atoms AS (
         SELECT v_card_cond_atom.owner_cd,
            v_card_cond_atom.card_id,
            v_card_cond_atom.card_bnft_id,
            v_card_cond_atom.rule_key,
            v_card_cond_atom.expr_status_cd,
            v_card_cond_atom.branch_no,
            v_card_cond_atom.atom_seq,
            v_card_cond_atom.atom_key,
            v_card_cond_atom.negate_yn,
            v_card_cond_atom.cond_type_cd,
            v_card_cond_atom.cond_basis_cd,
            v_card_cond_atom.cond_min_amt,
            v_card_cond_atom.cond_max_amt_excl,
            v_card_cond_atom.predicate_method_cd,
            v_card_cond_atom.predicate_method_ver,
            v_card_cond_atom.cond_params,
            v_card_cond_atom.card_excl_item_id,
            v_card_cond_atom.excl_raw_txt,
            v_card_cond_atom.cond_raw_txt,
            v_card_cond_atom.link_role_cd,
            v_card_cond_atom.cond_status_cd
           FROM db_pipeline.v_card_cond_atom
        ), rule_value_gap AS (
         SELECT r.card_id,
            r.card_bnft_id,
            r.rule_key,
            r.rule_status_cd = 'CONFIRMED'::text OR b.verification_status_cd::text = 'CONFIRMED'::text AS final_yn
           FROM db_pipeline.v_card_rule r
             JOIN db_pipeline.card_bnft b ON b.card_id = r.card_id AND b.card_bnft_id::text = r.card_bnft_id::text
          WHERE r.rule_status_cd <> 'RETIRED'::text AND ((r.calc_method_cd = ANY (ARRAY['PERCENT_OF_TXN'::text, 'FIXED_PER_TXN'::text, 'UNITS_PER_AMOUNT'::text, 'MULTIPLY_EXTERNAL_POINTS'::text])) AND r.value_num IS NULL OR r.calc_method_cd = 'UNITS_PER_AMOUNT'::text AND r.basis_amt IS NULL OR r.calc_method_cd = 'PERCENT_OF_TXN'::text AND r.value_unit_cd IS DISTINCT FROM 'PERCENT'::text OR r.calc_method_cd = 'MULTIPLY_EXTERNAL_POINTS'::text AND r.value_unit_cd IS DISTINCT FROM 'MULTIPLIER'::text OR (r.calc_method_cd = ANY (ARRAY['FIXED_PER_TXN'::text, 'UNITS_PER_AMOUNT'::text])) AND (r.value_unit_cd = ANY (ARRAY['PERCENT'::text, 'MULTIPLIER'::text])))
        ), predicate_param_gap AS (
         SELECT a.owner_cd,
            a.card_id,
            a.atom_key,
            a.cond_status_cd = 'CONFIRMED'::text OR a.expr_status_cd = 'CONFIRMED'::text AS final_yn
           FROM atoms a
          WHERE a.cond_status_cd <> 'RETIRED'::text AND (a.predicate_method_cd = 'EVERY_MONTH_MIN_SPEND'::text AND (a.cond_min_amt IS NULL OR jsonb_typeof(a.cond_params -> 'window_months'::text) IS DISTINCT FROM 'number'::text) OR a.predicate_method_cd = 'MONTH_IN'::text AND
                CASE
                    WHEN jsonb_typeof(a.cond_params -> 'months'::text) = 'array'::text THEN jsonb_array_length(a.cond_params -> 'months'::text) = 0
                    ELSE true
                END)
        ), fallback AS (
         SELECT v_card_bnft_rel.card_id,
            v_card_bnft_rel.from_bnft_id,
            v_card_bnft_rel.to_bnft_id
           FROM db_pipeline.v_card_bnft_rel
          WHERE v_card_bnft_rel.rel_type_cd = 'FALLBACK_AFTER_CAP'::text AND NOT v_card_bnft_rel.reverse_yn
        ), cycle AS (
         WITH RECURSIVE walk(card_id, start_id, cur_id, path) AS (
                 SELECT fallback.card_id,
                    fallback.from_bnft_id,
                    fallback.to_bnft_id,
                    ARRAY[fallback.from_bnft_id, fallback.to_bnft_id::character varying] AS "array"
                   FROM fallback
                UNION ALL
                 SELECT w.card_id,
                    w.start_id,
                    f.to_bnft_id,
                    w.path || f.to_bnft_id::character varying
                   FROM walk w
                     JOIN fallback f ON f.card_id = w.card_id AND f.from_bnft_id::text = w.cur_id
                  WHERE NOT (f.to_bnft_id = ANY (w.path[2:]::text[]))
                )
         SELECT DISTINCT walk.card_id,
            walk.start_id
           FROM walk
          WHERE walk.cur_id = walk.start_id::text
        )
 SELECT 'bnft_without_product'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_bnft_id::text AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE p.card_id = x.card_id))
UNION ALL
 SELECT 'local_confirmed_without_rule'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_bnft_id::text AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE x.verification_status_cd::text = 'CONFIRMED'::text AND jsonb_array_length(x.rule_list) = 0
UNION ALL
 SELECT 'bnft_txt_without_evidence'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_bnft_id::text AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE (x.bnft_rule_txt IS NOT NULL OR x.bnft_limit_txt IS NOT NULL) AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE l.card_id = x.card_id AND l.card_bnft_id::text = x.card_bnft_id::text AND l.ev_subject_cd::text = 'BNFT'::text AND l.ev_item_cd::text = 'SELF'::text))
UNION ALL
 SELECT 'rel_to_bnft_orphan'::text AS gate_cd,
    (x.card_id || '/'::text) || x.relation_key AS issue_key
   FROM db_pipeline.v_card_bnft_rel x
  WHERE NOT x.reverse_yn AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_bnft b
          WHERE b.card_id = x.card_id AND b.card_bnft_id::text = x.to_bnft_id))
UNION ALL
 SELECT 'rel_mutual_stored_twice'::text AS gate_cd,
    (((a.card_id || '/'::text) || a.from_bnft_id::text) || '/'::text) || a.to_bnft_id AS issue_key
   FROM db_pipeline.v_card_bnft_rel a
     JOIN db_pipeline.v_card_bnft_rel b ON a.card_id = b.card_id AND a.from_bnft_id::text = b.to_bnft_id AND a.to_bnft_id = b.from_bnft_id::text AND a.rel_type_cd = b.rel_type_cd
  WHERE NOT a.reverse_yn AND NOT b.reverse_yn AND a.rel_type_cd = 'MUTUALLY_EXCLUSIVE'::text AND a.from_bnft_id::text < a.to_bnft_id
UNION ALL
 SELECT 'rel_fallback_cycle'::text AS gate_cd,
    (c.card_id || '/'::text) || c.start_id::text AS issue_key
   FROM cycle c
UNION ALL
 SELECT 'product_doc_without_product'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_doc_id::text AS issue_key
   FROM db_pipeline.card_product_doc x
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE p.card_id = x.card_id))
UNION ALL
 SELECT 'product_doc_orphan'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_doc_id::text AS issue_key
   FROM db_pipeline.card_product_doc x
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_doc d
          WHERE d.card_doc_id::text = x.card_doc_id::text))
UNION ALL
 SELECT 'bnft_brand_opt_unknown'::text AS gate_cd,
    (((b.card_id || '/'::text) || b.card_bnft_id::text) || '/'::text) || o.cd AS issue_key
   FROM db_pipeline.card_bnft b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd)
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.v_card_brand_opt v
          WHERE v.card_id = b.card_id AND v.brand_opt_cd = o.cd))
UNION ALL
 SELECT 'doc_brand_opt_unknown'::text AS gate_cd,
    (((d.card_id || '/'::text) || d.card_doc_id::text) || '/'::text) || o.cd AS issue_key
   FROM db_pipeline.card_product_doc d
     CROSS JOIN LATERAL unnest(d.brand_opt_cds) o(cd)
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.v_card_brand_opt v
          WHERE v.card_id = d.card_id AND v.brand_opt_cd = o.cd))
UNION ALL
 SELECT
        CASE
            WHEN g.final_yn THEN 'rule_method_value_missing'::text
            ELSE 'rule_method_value_pending'::text
        END AS gate_cd,
    (((g.card_id || '/'::text) || g.card_bnft_id::text) || '/'::text) || g.rule_key AS issue_key
   FROM rule_value_gap g
UNION ALL
 SELECT
        CASE
            WHEN g.final_yn THEN 'predicate_params_missing'::text
            ELSE 'predicate_params_pending'::text
        END AS gate_cd,
    (((g.owner_cd || '/'::text) || g.card_id) || '/'::text) || g.atom_key AS issue_key
   FROM predicate_param_gap g
UNION ALL
 SELECT 'excl_item_unknown'::text AS gate_cd,
    (a.owner_cd || '/'::text) || a.atom_key AS issue_key
   FROM atoms a
  WHERE a.card_excl_item_id IS NOT NULL AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_excl_item i
          WHERE i.card_excl_item_id::text = a.card_excl_item_id))
UNION ALL
 SELECT 'evidence_source_orphan'::text AS gate_cd,
    e.evidence_id AS issue_key
   FROM db_pipeline.card_source_evidence e
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_doc_chunk c
          WHERE c.card_doc_id::text = e.card_doc_id::text AND c.page_no = e.page_no AND c.card_doc_chunk_id::text = e.card_doc_chunk_id::text))
UNION ALL
 SELECT 'evidence_doc_not_linked'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id)
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc d
          WHERE d.card_id = l.card_id AND d.card_doc_id::text = e.card_doc_id::text))
UNION ALL
 SELECT 'evidence_not_approved'::text AS gate_cd,
    l.evidence_id AS issue_key
   FROM ( SELECT DISTINCT card_evidence_link.evidence_id
           FROM db_pipeline.card_evidence_link) l
     LEFT JOIN db_pipeline.card_source_evidence e USING (evidence_id)
  WHERE e.evidence_id IS NULL OR e.approval_status_cd::text <> 'APPROVED'::text
UNION ALL
 SELECT 'evidence_subject_orphan'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE NOT
        CASE l.ev_subject_cd
            WHEN 'CARD'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.card_product p
              WHERE p.card_id = l.card_id))
            WHEN 'BNFT'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.card_bnft b
              WHERE b.card_id = l.card_id AND b.card_bnft_id::text = l.card_bnft_id::text))
            WHEN 'RULE'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule r
              WHERE r.card_id = l.card_id AND r.card_bnft_id::text = l.card_bnft_id::text AND r.rule_key = l.rule_key::text))
            WHEN 'REL'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_bnft_rel r
              WHERE NOT r.reverse_yn AND r.card_id = l.card_id AND r.from_bnft_id::text = l.card_bnft_id::text AND r.relation_key = l.relation_key::text))
            ELSE false
        END
UNION ALL
 SELECT 'evidence_item_key_missing'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE l.ev_item_cd::text <> 'SELF'::text AND NOT
        CASE l.ev_item_cd
            WHEN 'COND'::text THEN (EXISTS ( SELECT 1
               FROM atoms a
              WHERE a.card_id = l.card_id AND a.atom_key = l.ev_item_key::text AND NOT a.card_bnft_id::text IS DISTINCT FROM l.card_bnft_id::text AND NOT a.rule_key IS DISTINCT FROM l.rule_key::text))
            WHEN 'TARGET'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule_target t
              WHERE t.card_id = l.card_id AND t.card_bnft_id::text = l.card_bnft_id::text AND t.rule_key = l.rule_key::text AND t.target_key = l.ev_item_key::text))
            ELSE false
        END
UNION ALL
 SELECT 'product_doc_role_type_mismatch'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_doc_id::text AS issue_key
   FROM db_pipeline.card_product_doc x
     JOIN db_pipeline.card_doc d ON d.card_doc_id::text = x.card_doc_id::text
  WHERE x.doc_role_cd::text = 'BRAND_SERVICE'::text AND d.doc_type_cd::text <> 'BRAND_SERVICE'::text
UNION ALL
 SELECT 'brand_doc_option_conflict'::text AS gate_cd,
    z.card_doc_id AS issue_key
   FROM ( SELECT x.card_doc_id
           FROM db_pipeline.card_product_doc x
             CROSS JOIN LATERAL unnest(x.brand_opt_cds) o(cd)
             JOIN db_pipeline.v_card_brand_opt v ON v.card_id = x.card_id AND v.brand_opt_cd = o.cd
          WHERE x.doc_role_cd::text = 'BRAND_SERVICE'::text
          GROUP BY x.card_doc_id
         HAVING count(DISTINCT ROW(v.brand_cd, v.service_grade_cd, v.service_type_cd)) > 1) z
UNION ALL
 SELECT 'brand_bnft_doc_not_linked'::text AS gate_cd,
    (((b.card_id || '/'::text) || b.card_bnft_id::text) || '/'::text) || o.cd AS issue_key
   FROM db_pipeline.card_bnft b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd)
  WHERE b.bnft_origin_cd::text = 'BRAND_SERVICE'::text AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE x.card_id = b.card_id AND x.doc_role_cd::text = 'BRAND_SERVICE'::text AND (o.cd = ANY (x.brand_opt_cds))))
UNION ALL
 SELECT 'brand_bnft_confirmed_without_evidence'::text AS gate_cd,
    (b.card_id || '/'::text) || b.card_bnft_id::text AS issue_key
   FROM db_pipeline.card_bnft b
  WHERE b.bnft_origin_cd::text = 'BRAND_SERVICE'::text AND b.verification_status_cd::text = 'CONFIRMED'::text AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE l.card_id = b.card_id AND l.card_bnft_id::text = b.card_bnft_id::text))
UNION ALL
 SELECT 'evidence_brand_opt_mismatch'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id)
     JOIN db_pipeline.card_bnft b ON b.card_id = l.card_id AND b.card_bnft_id::text = l.card_bnft_id::text
     JOIN db_pipeline.card_product_doc x ON x.card_id = l.card_id AND x.card_doc_id::text = e.card_doc_id::text
  WHERE x.doc_role_cd::text = 'BRAND_SERVICE'::text AND NOT COALESCE(b.bnft_brand_opt_cds, '{}'::text[]) && x.brand_opt_cds
UNION ALL
 SELECT 'stg_card_not_linked'::text AS gate_cd,
    s.card_extr_stg_id AS issue_key
   FROM db_pipeline.card_extr_stg s
  WHERE s.card_id IS NOT NULL AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE x.card_id = s.card_id AND x.card_doc_id::text = s.card_doc_id::text))
UNION ALL
 SELECT 'common_cd_invalid'::text AS gate_cd,
    (u.source_nm || '='::text) || u.cd_value AS issue_key
   FROM db_pipeline.v_common_cd_usage u
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_cd c
          WHERE c.common_code_grp_id::text = u.common_code_grp_id::text AND c.common_cd::text = u.cd_value))
UNION ALL
 SELECT 'common_cd_group_orphan'::text AS gate_cd,
    (c.common_code_grp_id::text || '/'::text) || c.common_cd::text AS issue_key
   FROM db_pipeline.common_cd c
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_code_grp g
          WHERE g.common_code_grp_id::text = c.common_code_grp_id::text))
UNION ALL
 SELECT 'common_code_grp_empty'::text AS gate_cd,
    g.common_code_grp_id AS issue_key
   FROM db_pipeline.common_code_grp g
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_cd c
          WHERE c.common_code_grp_id::text = g.common_code_grp_id::text));
COMMENT ON VIEW db_pipeline.v_card_rule IS '상품 계산 규칙을 행으로 복원. V5 card_bnft_rule 조회 대체';
COMMENT ON VIEW db_pipeline.v_card_bnft_rule_effective IS '혜택과 계산 규칙의 단일 출력. 제공 기간은 걸러내지 않으므로 조회 기준일로 판정. 값은 정책 후보이며 거래별 보상액이 아님';
COMMENT ON VIEW db_pipeline.v_card_cond_atom IS '모든 조건식의 atom을 소유자와 함께 행으로 복원';
COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원';
COMMENT ON VIEW db_pipeline.v_common_cd_usage IS '모든 공통코드 사용처(물리 컬럼·JSONB 키)와 소속 그룹. 공통코드 정합성 검증의 기준';
COMMENT ON VIEW db_pipeline.v_card_integrity_issue IS '승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음. *_pending은 확정 전 항목의 값 누락(검토 대기)이고 나머지는 무결성 위반';
ALTER VIEW db_pipeline.v_card_rule OWNER TO postgres;
ALTER VIEW db_pipeline.v_card_bnft_rule_effective OWNER TO postgres;
ALTER VIEW db_pipeline.v_card_cond_atom OWNER TO postgres;
ALTER VIEW db_pipeline.v_card_rule_target OWNER TO postgres;
ALTER VIEW db_pipeline.v_common_cd_usage OWNER TO postgres;
ALTER VIEW db_pipeline.v_card_integrity_issue OWNER TO postgres;

-- 5. 공통코드
INSERT INTO db_pipeline.common_code_grp (common_code_grp_id, common_code_grp_nm, create_date, create_user_id, update_date, update_user_id, common_code_grp_desc) VALUES
    ('CALC_METHOD', '계산 방법', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-11-02 07:58:57.468697+00:00', 'V7_MIGRATION', '규칙이 한 거래의 후보 보상을 어떤 방식으로 산출하는지 구분하는 공통코드. rule_list[].calc_method_cd에서 사용하고, 코드별 value_num의 의미가 정해져 있다. 조건 판정 방법인 PREDICATE_METHOD와 구분된다. 규칙의 method_ver는 표현 계약 버전으로 현재 1이며 계산 실행 엔진의 버전을 뜻하지 않는다.'),
    ('LIMIT_AGG', '한도 집계 기준', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-11-02 07:58:57.468697+00:00', 'V7_MIGRATION', '한도 사용액을 어떤 주체 단위로 합산할지 구분하는 공통코드. card_limit_pool.aggregation_key_cd에서 사용한다. 어떤 혜택을 묶는지를 나타내는 LIMIT_SCOPE와 달리 누구의 사용분을 합칠지를 나타낸다.'),
    ('LIMIT_PERIOD', '한도 기간', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-11-02 07:58:57.468697+00:00', 'V7_MIGRATION', '한도가 누적되는 시간 단위를 구분하는 공통코드. card_limit_pool.period_cd에서 사용한다. 한도를 묶는 혜택 범위인 LIMIT_SCOPE, 한도의 단위인 LIMIT_UNIT과 함께 한도 하나를 정의한다.'),
    ('LIMIT_SCOPE', '한도 범위', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '한도 풀이 어느 범위의 혜택을 묶어 누적하는지 구분하는 공통코드. card_limit_pool.pool_scope_cd에서 사용한다. 한도의 시간 범위인 LIMIT_PERIOD, 누적 주체인 LIMIT_AGG와 구분되며, 같은 금액의 한도라도 범위가 다르면 다른 풀이다.'),
    ('LIMIT_UNIT', '한도 단위', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-11-02 07:58:57.468697+00:00', 'V7_MIGRATION', '한도 수치 limit_num이 어떤 단위인지 구분하는 공통코드. card_limit_pool.cap_unit_cd에서 사용한다. 보상 지급 단위인 PAYOUT_UNIT과 달리 금액뿐 아니라 이용 횟수도 포함한다.'),
    ('PAYOUT_UNIT', '보상 단위', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '고객이 혜택으로 실제 받는 보상의 단위를 구분하는 공통코드. rule_list[].payout_unit_cd에서 사용한다. 계산 입력값의 단위인 VALUE_UNIT, 누적 한도의 단위인 LIMIT_UNIT과 구분된다.'),
    ('POOL_ROLE', '규칙에서 한도 역할', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '계산 규칙이 연결된 한도 풀을 어떤 역할로 소비하는지 구분하는 공통코드. card_bnft_rule_pool.pool_role_cd에서 사용한다. 한 규칙이 영역 한도와 카드 통합 한도를 동시에 소비하는 구조를 표현하기 위한 값이며, 풀 자체의 범위는 LIMIT_SCOPE가 정한다.'),
    ('PREDICATE_METHOD', '술어 방법', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-11-02 07:58:57.468697+00:00', 'V7_MIGRATION', '금액 구간만으로 표현되지 않는 조건을 판정하는 방법을 구분하는 공통코드. 조건 atom의 predicate_method_cd에서 사용하며 세부 값은 cond_params에 둔다. 보상 금액을 산출하는 CALC_METHOD와 달리 조건의 참·거짓만 판정한다. predicate_method_ver는 표현 계약 버전으로 현재 1이며 실행 엔진의 버전을 뜻하지 않는다.'),
    ('PREDICATE_STATE', '조건 판정 상태', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-11-02 07:58:57.468697+00:00', 'V7_MIGRATION', '규칙이나 한도 구간의 적용 여부를 조건식으로 어떻게 판정할지 구분하는 공통코드. card_bnft.rule_list[].predicate_state_cd와 card_limit_pool.tier_list[].predicate_state_cd에서 사용한다. 조건식이 없다는 사실만으로 무조건 적용으로 해석하지 않도록, 원문으로 확인된 무조건과 미검토를 구분한다.'),
    ('RULE_SELECT', '혜택 내 규칙 선택 방식', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '한 혜택 안에서 같은 거래에 여러 계산 규칙이 해당할 때 어떤 규칙을 적용할지 정하는 공통코드. card_bnft.rule_select_cd에서 사용하고, 값이 NULL이면 선택 방식이 아직 확정되지 않은 상태다. 혜택과 혜택 사이의 관계를 다루는 REL_TYPE과 달리 한 혜택 내부의 규칙 선택만 다룬다.');
INSERT INTO db_pipeline.common_cd (common_code_grp_id, common_cd, common_cd_nm, create_date, create_user_id, update_date, update_user_id, common_cd_desc) VALUES
    ('CALC_METHOD', 'FIXED_PER_TXN', '건당 정액', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-11-02 07:58:57.468697+00:00', 'V7_MIGRATION', '조건을 충족한 결제 1건마다 정해진 금액이나 포인트·마일리지를 제공하는 방식. value_num은 건당 수량이며 ONE PICK의 100원, 500원 캐시백이 해당한다. 결제금액에 비례하는 PERCENT_OF_TXN, 금액 구간마다 적립하는 UNITS_PER_AMOUNT와 구분된다.'),
    ('CALC_METHOD', 'FREE_SERVICE', '무상 서비스 제공', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '결제금액으로 보상을 계산하지 않고 공항 라운지나 발렛파킹 같은 서비스 이용을 무상으로 제공하는 방식. 금액이나 포인트를 산출하는 다른 계산 방법과 구분된다.'),
    ('CALC_METHOD', 'MULTIPLY_EXTERNAL_POINTS', '외부 포인트 배수', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '결제금액이 아니라 외부 제휴사가 적립한 포인트에 배수를 곱해 보상을 산출하는 방식. CJ ONE 적립 포인트의 2배 캐시백이 해당하며 value_num은 배수, value_unit_cd는 MULTIPLIER다. 외부 포인트 값이 없으면 산출할 수 없다.'),
    ('CALC_METHOD', 'PERCENT_OF_TXN', '결제금액 정률', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '결제금액에 고정 비율을 곱해 보상을 산출하는 방식. value_num은 퍼센트 수치이며(1.5는 1.5%) value_unit_cd는 PERCENT를 쓴다. 결제금액과 무관하게 일정액을 주는 FIXED_PER_TXN과 구분된다.'),
    ('CALC_METHOD', 'UNITS_PER_AMOUNT', '금액당 단위 적립', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '결제금액을 basis_amt 단위로 나누어 단위마다 value_num만큼 적립하는 방식. 1,500원당 45 UniMile이 해당하며 value_num=45, basis_amt=1500으로 저장한다. 비율로 계산하는 PERCENT_OF_TXN과 달리 기준금액 단위로 계산한다.'),
    ('LIMIT_AGG', 'CARD_MEMBER', '회원 카드 단위(가족카드 합산)', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '회원의 카드 단위로 누적하면서 가족카드 사용분을 합산하는 기준. 원문의 본인카드와 가족카드의 실적 및 적립/할인한도는 합산이 해당한다. 현재 추출기가 일괄 입력하는 기본값이므로 이 값이 있다고 해당 상품의 원문이 확인된 것은 아니다.'),
    ('LIMIT_PERIOD', 'DAY', '일', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '하루 단위로 누적하는 한도. ONE PICK의 일 1회 제공이 해당한다. 월 한도와 동시에 걸리면 별도의 풀로 둔다.'),
    ('LIMIT_PERIOD', 'MONTH', '월', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '한 달 단위로 누적하는 한도. ONE PICK의 월 30회, 월 5천원이 해당하며 전월 실적에 따라 구간별로 금액이 달라지는 한도도 이 기간을 쓴다.'),
    ('LIMIT_PERIOD', 'TXN', '건당', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '결제 1건마다 적용되는 한도. 기간 동안 누적되지 않고 건별로 판단한다는 점에서 DAY, MONTH, YEAR와 구분된다.'),
    ('LIMIT_PERIOD', 'YEAR', '연', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '1년 단위로 누적하는 한도. 놀이공원의 연 2회 제공이 해당한다. 월 1회처럼 다른 기간의 한도와 동시에 걸리면 별도의 풀로 둔다.'),
    ('LIMIT_SCOPE', 'AREA', '서비스 영역', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '쇼핑, 교통처럼 특정 서비스 영역 안의 혜택이 함께 소비하는 한도. 달달 체크카드의 영역별 2천, 4천, 6천원 한도가 해당한다. 모든 영역을 합치는 CARD와 달리 영역마다 별도의 풀이다.'),
    ('LIMIT_SCOPE', 'BENEFIT', '혜택 단일', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '혜택 하나의 규칙만 소비하는 한도. 같은 혜택 안의 두 규칙이 같은 풀을 써도 다른 혜택과는 공유하지 않는다. 현재 추출기는 원문에 공유 표현이 없으면 이 값을 부여한다.'),
    ('LIMIT_SCOPE', 'BENEFIT_GROUP', '혜택군 통합', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '원문이 여러 혜택의 공유를 명시해 묶어 누적하는 한도. 추출기는 공유 표현 shared_scope_txt가 있을 때 이 값을 부여하며, 금액이 같다는 이유만으로 공유로 판단하지 않는다.'),
    ('LIMIT_SCOPE', 'CARD', '카드 전체 통합', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '카드의 모든 서비스 영역을 합쳐 누적하는 통합 한도. 달달 체크카드의 월 통합 1만, 2만, 3만원 한도가 해당한다. 영역 한도와 함께 있으면 한 결제가 두 풀을 모두 소비한다.'),
    ('LIMIT_UNIT', 'COUNT', '횟수', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '한도를 혜택 제공 횟수로 관리하는 단위. 일 1회, 월 30회, 연 2회가 해당한다. limit_num이 금액이 아니라 횟수이며 금액 한도와는 별도의 풀로 둔다.'),
    ('LIMIT_UNIT', 'HANAMONEY', '하나머니', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '한도를 하나머니 적립량으로 관리하는 단위. JADE Classic의 월 통합 10만 하나머니가 해당한다. 원화로 환산하지 않고 원문의 단위대로 저장한다.'),
    ('LIMIT_UNIT', 'KRW', '원', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '한도를 원화 금액으로 관리하는 단위. 월 5천원, 월 통합 10만원이 해당한다. 혜택 제공 횟수를 세는 COUNT와 구분된다.'),
    ('PAYOUT_UNIT', 'HANAMONEY', '하나머니', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '보상을 하나머니 포인트로 받는 경우. JADE Classic의 특별 적립이 해당한다. 원화로 지급하는 KRW, 마일리지인 UNIMILE과 구분된다.'),
    ('PAYOUT_UNIT', 'KRW', '원', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '보상을 원화로 받는 경우. 할인과 캐시백이 해당하며, 계산 입력값이 퍼센트여도 실제 보상이 원이면 이 값을 쓴다.'),
    ('PAYOUT_UNIT', 'SERVICE', '서비스 제공', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '보상이 금전이나 포인트가 아니라 서비스 이용 자체로 제공되는 경우. 공항 라운지, 발렛파킹처럼 지급 수량으로 환산하지 않는 혜택에 쓴다.'),
    ('PAYOUT_UNIT', 'UNIMILE', 'UniMile', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '보상을 UniMile로 받는 경우. Mile1 카드의 마일리지 적립이 해당한다. 원문의 1,500원당 45 UniMile은 UNITS_PER_AMOUNT 규칙으로 표현한다.'),
    ('PAYOUT_UNIT', 'WALLET_POINT', '월렛 포인트', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '보상을 월렛 포인트로 받는 경우. Visa 브랜드 서비스의 Booking.com 월렛포인트 캐시백이 해당한다. 원화나 하나머니가 아닌 별도 포인트로 지급될 때 쓴다.'),
    ('POOL_ROLE', 'CONSUME', '해당 규칙군 한도 소비', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '규칙이 자기 규칙군에 속한 한도 풀을 소비하는 역할. 달달 체크카드의 쇼핑 규칙이 쇼핑 영역 한도를 쓰는 경우다. 현재 추출기는 규칙의 한도 참조를 모두 이 값으로 만든다.'),
    ('POOL_ROLE', 'SHARED', '카드 통합 한도 동시 소비', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '규칙이 자기 규칙군의 한도와 함께 카드 통합 한도도 동시에 소비하는 역할. 달달 체크카드의 규칙이 쇼핑 영역 풀(CONSUME)과 모든 영역 통합 풀(SHARED)을 함께 소비하는 경우다.'),
    ('PREDICATE_METHOD', 'EVERY_MONTH_MIN_SPEND', '기간 내 매월 최소 실적', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '지정한 기간의 모든 달이 각각 최소 실적을 충족하는지 판정하는 방법. 최근 3개월 매월 10만원 이상처럼 합계가 아니라 월별 충족을 보며, 최소 금액은 cond_min_amt, 기간은 cond_params에 둔다. cond_basis_cd는 ROLLING_MONTHS를 쓴다.'),
    ('PREDICATE_METHOD', 'MONTH_IN', '지정 월 해당', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '기준 월이 지정한 월 목록에 속하는지 판정하는 방법. 2, 3, 8, 9월에 매입된 거래처럼 금액이 아닌 달력 조건에 쓰며 월 목록과 기준은 cond_params에 둔다.'),
    ('PREDICATE_STATE', 'CONDITIONAL', '조건식 평가 필요', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '조건식을 평가해야 적용 여부가 결정되는 상태. 이 값이면 cond_expr가 반드시 있어야 하며, 없으면 fn_valid_* 검증에서 거부된다.'),
    ('PREDICATE_STATE', 'PENDING_REVIEW', '검토 대기', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '조건 유무나 조건식의 완전성이 아직 검토되지 않은 상태. 추출 규칙에 조건이 없을 때 부여하는 값이고 cond_expr가 있어도 허용된다. 조건식이 없어도 무조건 적용으로 해석하면 안 된다.'),
    ('PREDICATE_STATE', 'VERIFIED_UNCONDITIONAL', '원문 확인된 무조건', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '원문을 확인한 결과 조건 없이 적용되는 상태. 이 값이면 cond_expr가 없어야 한다. 조건식이 비어 있을 때 무조건으로 해석할 수 있는 유일한 값으로, 조건이 아직 파악되지 않은 PENDING_REVIEW와 구분된다.'),
    ('RULE_SELECT', 'EXCLUSIVE_BY_SCOPE', '범위가 겹치지 않음', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '규칙들의 적용 범위가 서로 겹치지 않아 한 거래에 하나의 규칙만 해당하는 방식. 전월 실적 40만원 미만 1%, 이상 2%처럼 구간이 배타적인 경우다. 겹침을 해소하는 PRIORITY, MAX_BENEFIT_VALUE와 달리 애초에 겹침이 없음을 뜻한다.'),
    ('RULE_SELECT', 'MAX_BENEFIT_VALUE', '보상이 큰 규칙 적용', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '규칙이 겹칠 때 보상이 큰 규칙 하나를 적용하는 방식. 원문이 적립금액이 큰 서비스 우선 적용으로 명시한 경우에 쓴다. 한 혜택 안의 규칙을 고른다는 점에서 혜택 간 관계인 REL_TYPE.HIGHER_VALUE_WINS와 구분된다.'),
    ('RULE_SELECT', 'PRIORITY', '우선순위 적용', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '2026-10-31 07:48:44.634115+00:00', 'SEED_TEST', '규칙이 겹칠 때 rule_priority로 적용 순서를 정하는 방식. 원문에 우선 규칙이 명시된 경우에만 쓰며, 근거가 없으면 임의로 우선순위를 만들지 않는다. 보상 크기로 고르는 MAX_BENEFIT_VALUE와 구분된다.');

COMMIT;
