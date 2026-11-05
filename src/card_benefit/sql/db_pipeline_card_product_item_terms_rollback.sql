-- =====================================================================================================
-- card_product_item TERMS 도입: 되돌리기
-- 생성: 2026-11-05, 운영 DB 정의를 읽어 생성(gen_terms_ddl.py). 변경 내용은 다음 세 가지뿐이다.
--   1) card_product_item_type_ck(고정 허용값 CHECK) 삭제
--   2) fn_valid_item_data: BENEFIT·ANNUAL_FEE 분기 원문 유지, TERMS_V1 분기 추가, 그 밖의 유형은 JSON 객체만 요구
--   3) v_card_integrity_issue: evidence_subject_orphan에 ITEM 근거의 항목 존재 분기만 추가
-- 다른 제약(subtype_ck, nonbnft_ck, cond/rule/rel/data_ck, PK, UNIQUE)과 업무 뷰는 바꾸지 않는다.
-- =====================================================================================================

-- TERMS 행이 하나라도 있으면 고정 허용값 CHECK를 다시 만들 수 없으므로 중단한다(TERMS 행 처리는 별도 결정).
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM db_pipeline.card_product_item WHERE item_type_cd NOT IN ('BENEFIT', 'ANNUAL_FEE')) THEN
        RAISE EXCEPTION 'BENEFIT·ANNUAL_FEE 외 항목이 있어 되돌릴 수 없습니다';
    END IF;
END $$;

CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_item_data(p_type text, p_data jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_line jsonb;
    v_keys text[] := '{}';
    v_basic numeric; v_aff numeric; v_total numeric;
BEGIN
    IF p_data IS NULL OR jsonb_typeof(p_data) <> 'object' THEN
        RETURN false;
    END IF;
    IF p_type = 'BENEFIT' THEN
        RETURN NOT (p_data ? 'schema_ver') OR p_data->>'schema_ver' = 'BENEFIT_V1';
    END IF;
    IF p_type = 'ANNUAL_FEE' THEN
        IF p_data->>'schema_ver' IS DISTINCT FROM 'ANNUAL_FEE_V1'
           OR jsonb_typeof(p_data->'fee_lines') IS DISTINCT FROM 'array'
           OR jsonb_array_length(p_data->'fee_lines') = 0 THEN
            RETURN false;
        END IF;
        FOR v_line IN SELECT value FROM jsonb_array_elements(p_data->'fee_lines') LOOP
            IF jsonb_typeof(v_line) <> 'object'
               OR coalesce(v_line->>'line_key', '') = ''
               OR (v_line->>'line_key') = ANY (v_keys)
               OR coalesce(v_line->>'holder_type_cd', '') NOT IN ('PRINCIPAL', 'FAMILY') THEN
                RETURN false;
            END IF;
            v_keys := v_keys || (v_line->>'line_key');
            -- 금액은 없거나 0 이상 정수
            IF EXISTS (SELECT 1 FROM unnest(ARRAY['basic_fee_amt', 'affiliate_fee_amt', 'total_fee_amt']) AS f(k)
                       WHERE v_line ? f.k AND jsonb_typeof(v_line->f.k) <> 'null'
                         AND (jsonb_typeof(v_line->f.k) <> 'number' OR (v_line->>f.k)::numeric < 0
                              OR (v_line->>f.k)::numeric <> trunc((v_line->>f.k)::numeric))) THEN
                RETURN false;
            END IF;
            v_basic := (v_line->>'basic_fee_amt')::numeric;
            v_aff := (v_line->>'affiliate_fee_amt')::numeric;
            v_total := (v_line->>'total_fee_amt')::numeric;
            IF v_basic IS NOT NULL AND v_aff IS NOT NULL AND v_total IS NOT NULL AND v_basic + v_aff <> v_total THEN
                RETURN false;
            END IF;
            -- 브랜드 옵션: null(전 브랜드) 또는 비어 있지 않은 문자열 배열
            IF v_line ? 'brand_opt_cds' AND jsonb_typeof(v_line->'brand_opt_cds') <> 'null'
               AND (jsonb_typeof(v_line->'brand_opt_cds') <> 'array' OR jsonb_array_length(v_line->'brand_opt_cds') = 0
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements(v_line->'brand_opt_cds') b WHERE jsonb_typeof(b) <> 'string')) THEN
                RETURN false;
            END IF;
        END LOOP;
        RETURN true;
    END IF;
    RETURN false;   -- 아직 지원하지 않는 유형
END;
$function$;

CREATE OR REPLACE VIEW db_pipeline.v_card_integrity_issue AS
 WITH atoms AS (
         SELECT v_card_cond_atom.owner_cd,
            v_card_cond_atom.card_id,
            v_card_cond_atom.card_product_item_id AS card_bnft_id,
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
            v_card_cond_atom.excl_raw_txt,
            v_card_cond_atom.cond_raw_txt,
            v_card_cond_atom.cond_status_cd
           FROM db_pipeline.v_card_cond_atom
        ), fallback AS (
         SELECT v_card_bnft_rel.card_id,
            v_card_bnft_rel.from_bnft_id,
            v_card_bnft_rel.to_bnft_id
           FROM db_pipeline.v_card_bnft_rel
          WHERE ((v_card_bnft_rel.rel_type_cd = 'FALLBACK_AFTER_CAP'::text) AND (NOT v_card_bnft_rel.reverse_yn))
        ), cycle AS (
         WITH RECURSIVE walk(card_id, start_id, cur_id, path) AS (
                 SELECT fallback.card_id,
                    fallback.from_bnft_id,
                    fallback.to_bnft_id,
                    ARRAY[fallback.from_bnft_id, (fallback.to_bnft_id)::character varying] AS "array"
                   FROM fallback
                UNION ALL
                 SELECT w.card_id,
                    w.start_id,
                    f.to_bnft_id,
                    (w.path || (f.to_bnft_id)::character varying)
                   FROM (walk w
                     JOIN fallback f ON (((f.card_id = w.card_id) AND ((f.from_bnft_id)::text = w.cur_id))))
                  WHERE (NOT (f.to_bnft_id = ANY ((w.path[2:])::text[])))
                )
         SELECT DISTINCT walk.card_id,
            walk.start_id
           FROM walk
          WHERE (walk.cur_id = (walk.start_id)::text)
        )
 SELECT 'bnft_without_product'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_bnft_id)::text) AS issue_key
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) x
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE (p.card_id = x.card_id))))
UNION ALL
 SELECT 'local_confirmed_without_rule'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_bnft_id)::text) AS issue_key
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) x
  WHERE (((x.verification_status_cd)::text = 'CONFIRMED'::text) AND (jsonb_array_length(x.rule_list) = 0))
UNION ALL
 SELECT 'bnft_txt_without_evidence'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_bnft_id)::text) AS issue_key
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) x
  WHERE (((x.bnft_rule_txt IS NOT NULL) OR (x.bnft_limit_txt IS NOT NULL)) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE ((l.card_id = x.card_id) AND ((l.card_product_item_id)::text = (x.card_bnft_id)::text) AND ((l.ev_subject_cd)::text = 'BNFT'::text) AND ((l.ev_item_cd)::text = 'SELF'::text))))))
UNION ALL
 SELECT 'rel_to_bnft_orphan'::text AS gate_cd,
    ((x.card_id || '/'::text) || x.relation_key) AS issue_key
   FROM db_pipeline.v_card_bnft_rel x
  WHERE ((NOT x.reverse_yn) AND (NOT (EXISTS ( SELECT 1
           FROM ( SELECT card_product_item.card_id,
                    card_product_item.card_product_item_id AS card_bnft_id,
                    card_product_item.item_cd AS bnft_cd,
                    card_product_item.item_nm AS bnft_nm,
                    card_product_item.item_subtype_cd AS bnft_type_cd,
                    card_product_item.item_origin_cd AS bnft_origin_cd,
                    card_product_item.item_scope_cd AS bnft_scope_cd,
                    card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
                    card_product_item.item_cond_expr AS bnft_cond_expr,
                    card_product_item.rule_list,
                    card_product_item.relation_list,
                    card_product_item.verification_status_cd,
                    card_product_item.item_valid_from AS bnft_valid_from,
                    card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
                    card_product_item.item_rule_txt AS bnft_rule_txt,
                    card_product_item.item_limit_txt AS bnft_limit_txt,
                    card_product_item.item_search_txt AS bnft_search_txt,
                    card_product_item.item_embedding AS bnft_embedding
                   FROM db_pipeline.card_product_item
                  WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) b
          WHERE ((b.card_id = x.card_id) AND ((b.card_bnft_id)::text = x.to_bnft_id))))))
UNION ALL
 SELECT 'rel_mutual_stored_twice'::text AS gate_cd,
    ((((a.card_id || '/'::text) || (a.from_bnft_id)::text) || '/'::text) || a.to_bnft_id) AS issue_key
   FROM (db_pipeline.v_card_bnft_rel a
     JOIN db_pipeline.v_card_bnft_rel b ON (((a.card_id = b.card_id) AND ((a.from_bnft_id)::text = b.to_bnft_id) AND (a.to_bnft_id = (b.from_bnft_id)::text) AND (a.rel_type_cd = b.rel_type_cd))))
  WHERE ((NOT a.reverse_yn) AND (NOT b.reverse_yn) AND (a.rel_type_cd = 'MUTUALLY_EXCLUSIVE'::text) AND ((a.from_bnft_id)::text < a.to_bnft_id))
UNION ALL
 SELECT 'rel_fallback_cycle'::text AS gate_cd,
    ((c.card_id || '/'::text) || (c.start_id)::text) AS issue_key
   FROM cycle c
UNION ALL
 SELECT 'product_doc_without_product'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_doc_id)::text) AS issue_key
   FROM db_pipeline.card_product_doc x
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE (p.card_id = x.card_id))))
UNION ALL
 SELECT 'product_doc_orphan'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_doc_id)::text) AS issue_key
   FROM db_pipeline.card_product_doc x
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_doc d
          WHERE ((d.card_doc_id)::text = (x.card_doc_id)::text))))
UNION ALL
 SELECT 'bnft_brand_opt_unknown'::text AS gate_cd,
    ((((b.card_id || '/'::text) || (b.card_bnft_id)::text) || '/'::text) || o.cd) AS issue_key
   FROM (( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd))
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.v_card_brand_opt v
          WHERE ((v.card_id = b.card_id) AND (v.brand_opt_cd = o.cd)))))
UNION ALL
 SELECT 'doc_brand_opt_unknown'::text AS gate_cd,
    ((((d.card_id || '/'::text) || (d.card_doc_id)::text) || '/'::text) || o.cd) AS issue_key
   FROM (db_pipeline.card_product_doc d
     CROSS JOIN LATERAL unnest(d.brand_opt_cds) o(cd))
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.v_card_brand_opt v
          WHERE ((v.card_id = d.card_id) AND (v.brand_opt_cd = o.cd)))))
UNION ALL
 SELECT 'evidence_source_orphan'::text AS gate_cd,
    e.evidence_id AS issue_key
   FROM db_pipeline.card_source_evidence e
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_doc_chunk c
          WHERE (((c.card_doc_id)::text = (e.card_doc_id)::text) AND (c.page_no = e.page_no) AND ((c.card_doc_chunk_id)::text = (e.card_doc_chunk_id)::text)))))
UNION ALL
 SELECT 'evidence_doc_not_linked'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM (db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id))
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc d
          WHERE ((d.card_id = l.card_id) AND ((d.card_doc_id)::text = (e.card_doc_id)::text)))))
UNION ALL
 SELECT 'evidence_not_approved'::text AS gate_cd,
    l.evidence_id AS issue_key
   FROM (( SELECT DISTINCT card_evidence_link.evidence_id
           FROM db_pipeline.card_evidence_link) l
     LEFT JOIN db_pipeline.card_source_evidence e USING (evidence_id))
  WHERE ((e.evidence_id IS NULL) OR ((e.approval_status_cd)::text <> 'APPROVED'::text))
UNION ALL
 SELECT 'evidence_subject_orphan'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE (NOT
        CASE l.ev_subject_cd
            WHEN 'CARD'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.card_product p
              WHERE (p.card_id = l.card_id)))
            WHEN 'BNFT'::text THEN (EXISTS ( SELECT 1
               FROM ( SELECT card_product_item.card_id,
                        card_product_item.card_product_item_id AS card_bnft_id,
                        card_product_item.item_cd AS bnft_cd,
                        card_product_item.item_nm AS bnft_nm,
                        card_product_item.item_subtype_cd AS bnft_type_cd,
                        card_product_item.item_origin_cd AS bnft_origin_cd,
                        card_product_item.item_scope_cd AS bnft_scope_cd,
                        card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
                        card_product_item.item_cond_expr AS bnft_cond_expr,
                        card_product_item.rule_list,
                        card_product_item.relation_list,
                        card_product_item.verification_status_cd,
                        card_product_item.item_valid_from AS bnft_valid_from,
                        card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
                        card_product_item.item_rule_txt AS bnft_rule_txt,
                        card_product_item.item_limit_txt AS bnft_limit_txt,
                        card_product_item.item_search_txt AS bnft_search_txt,
                        card_product_item.item_embedding AS bnft_embedding
                       FROM db_pipeline.card_product_item
                      WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) b
              WHERE ((b.card_id = l.card_id) AND ((b.card_bnft_id)::text = (l.card_product_item_id)::text))))
            WHEN 'RULE'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule r
              WHERE ((r.card_id = l.card_id) AND ((r.card_product_item_id)::text = (l.card_product_item_id)::text) AND (r.rule_key = (l.rule_key)::text))))
            WHEN 'REL'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_bnft_rel r
              WHERE ((NOT r.reverse_yn) AND (r.card_id = l.card_id) AND ((r.from_bnft_id)::text = (l.card_product_item_id)::text) AND (r.relation_key = (l.relation_key)::text))))
            ELSE false
        END)
UNION ALL
 SELECT 'evidence_item_key_missing'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE (((l.ev_item_cd)::text <> 'SELF'::text) AND (NOT
        CASE l.ev_item_cd
            WHEN 'COND'::text THEN (EXISTS ( SELECT 1
               FROM atoms a
              WHERE ((a.card_id = l.card_id) AND (a.atom_key = (l.ev_item_key)::text) AND (NOT ((a.card_bnft_id)::text IS DISTINCT FROM (l.card_product_item_id)::text)) AND (NOT (a.rule_key IS DISTINCT FROM (l.rule_key)::text)))))
            WHEN 'TARGET'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule_target t
              WHERE ((t.card_id = l.card_id) AND ((t.card_product_item_id)::text = (l.card_product_item_id)::text) AND (t.rule_key = (l.rule_key)::text) AND (t.target_key = (l.ev_item_key)::text))))
            ELSE false
        END))
UNION ALL
 SELECT 'product_doc_role_type_mismatch'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_doc_id)::text) AS issue_key
   FROM (db_pipeline.card_product_doc x
     JOIN db_pipeline.card_doc d ON (((d.card_doc_id)::text = (x.card_doc_id)::text)))
  WHERE (((x.doc_role_cd)::text = 'BRAND_SERVICE'::text) AND ((d.doc_type_cd)::text <> 'BRAND_SERVICE'::text))
UNION ALL
 SELECT 'brand_doc_option_conflict'::text AS gate_cd,
    z.card_doc_id AS issue_key
   FROM ( SELECT x.card_doc_id
           FROM ((db_pipeline.card_product_doc x
             CROSS JOIN LATERAL unnest(x.brand_opt_cds) o(cd))
             JOIN db_pipeline.v_card_brand_opt v ON (((v.card_id = x.card_id) AND (v.brand_opt_cd = o.cd))))
          WHERE ((x.doc_role_cd)::text = 'BRAND_SERVICE'::text)
          GROUP BY x.card_doc_id
         HAVING (count(DISTINCT ROW(v.brand_cd, v.service_grade_cd, v.service_type_cd)) > 1)) z
UNION ALL
 SELECT 'brand_bnft_doc_not_linked'::text AS gate_cd,
    ((((b.card_id || '/'::text) || (b.card_bnft_id)::text) || '/'::text) || o.cd) AS issue_key
   FROM (( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd))
  WHERE (((b.bnft_origin_cd)::text = 'BRAND_SERVICE'::text) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE ((x.card_id = b.card_id) AND ((x.doc_role_cd)::text = 'BRAND_SERVICE'::text) AND (o.cd = ANY (x.brand_opt_cds)))))))
UNION ALL
 SELECT 'brand_bnft_confirmed_without_evidence'::text AS gate_cd,
    ((b.card_id || '/'::text) || (b.card_bnft_id)::text) AS issue_key
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) b
  WHERE (((b.bnft_origin_cd)::text = 'BRAND_SERVICE'::text) AND ((b.verification_status_cd)::text = 'CONFIRMED'::text) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE ((l.card_id = b.card_id) AND ((l.card_product_item_id)::text = (b.card_bnft_id)::text))))))
UNION ALL
 SELECT 'evidence_brand_opt_mismatch'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM (((db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id))
     JOIN ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE ((card_product_item.item_type_cd)::text = 'BENEFIT'::text)) b ON (((b.card_id = l.card_id) AND ((b.card_bnft_id)::text = (l.card_product_item_id)::text))))
     JOIN db_pipeline.card_product_doc x ON (((x.card_id = l.card_id) AND ((x.card_doc_id)::text = (e.card_doc_id)::text))))
  WHERE (((x.doc_role_cd)::text = 'BRAND_SERVICE'::text) AND (NOT (COALESCE(b.bnft_brand_opt_cds, '{}'::text[]) && x.brand_opt_cds)))
UNION ALL
 SELECT 'stg_card_not_linked'::text AS gate_cd,
    s.card_extr_stg_id AS issue_key
   FROM db_pipeline.card_extr_stg s
  WHERE ((s.card_id IS NOT NULL) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE ((x.card_id = s.card_id) AND ((x.card_doc_id)::text = (s.card_doc_id)::text))))))
UNION ALL
 SELECT 'common_cd_invalid'::text AS gate_cd,
    ((u.source_nm || '='::text) || u.cd_value) AS issue_key
   FROM db_pipeline.v_common_cd_usage u
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_cd c
          WHERE (((c.common_code_grp_id)::text = (u.common_code_grp_id)::text) AND ((c.common_cd)::text = u.cd_value)))))
UNION ALL
 SELECT 'common_cd_group_orphan'::text AS gate_cd,
    (((c.common_code_grp_id)::text || '/'::text) || (c.common_cd)::text) AS issue_key
   FROM db_pipeline.common_cd c
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_code_grp g
          WHERE ((g.common_code_grp_id)::text = (c.common_code_grp_id)::text))))
UNION ALL
 SELECT 'common_code_grp_empty'::text AS gate_cd,
    g.common_code_grp_id AS issue_key
   FROM db_pipeline.common_code_grp g
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_cd c
          WHERE ((c.common_code_grp_id)::text = (g.common_code_grp_id)::text))));

ALTER TABLE db_pipeline.card_product_item ADD CONSTRAINT card_product_item_type_ck CHECK (((item_type_cd)::text = ANY ((ARRAY['BENEFIT'::character varying, 'ANNUAL_FEE'::character varying])::text[])));

COMMENT ON COLUMN db_pipeline.card_product_item.item_type_cd IS '항목 유형(ITEM_TYPE): BENEFIT, ANNUAL_FEE. TERMS/FEE/ETC는 코드만 예약';

COMMIT;
