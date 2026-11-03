-- =====================================================================================================
-- [제안 / 승인 전 실행 금지] 정합성 뷰 보강: 근거 연결의 승계 상위키 불일치 게이트
-- 검토서: CARD_EVIDENCE_LINK_PK_INHERITANCE_REVIEW_20261103.md 10절
-- 되돌리기: db_pipeline_v_card_integrity_issue_link_key_gate_proposal_rollback.sql
--
-- 추가 게이트: evidence_link_key_mismatch
--   card_evidence_link의 (card_doc_id, page_no, card_doc_chunk_id, evidence_id) 조합이 card_source_evidence에 없으면 1행.
--   issue_key는 기존 근거 연결 게이트와 같은 형식인 card_id || '/' || evidence_link_id.
--   물리 FK를 두지 않는 대신 승인 전 게이트로 잡는다. 원문 근거가 아예 없는 연결은 기존 evidence_not_approved도 잡지만,
--   원문은 있는데 문서·페이지·청크가 다른 연결은 지금까지 잡는 게이트가 없었다.
-- 현재 데이터의 해당 행: 0 (사후 검증 P08). 따라서 적용해도 기존 게이트 결과와 등록 프로그램 판정은 바뀌지 않는다.
-- 등록 프로그램(product_benefit_service.register_run)은 정합성 오류가 새로 생기면 롤백하므로, 이후 이 불일치를 만드는 등록은 막힌다.
--
-- 처리 (한 트랜잭션): 뷰 잠금 → 이미 게이트가 있으면 변경 없음 → 뷰에 의존하는 객체가 있으면 중단 → 현재 정의를 읽어
-- 맨 끝에 UNION ALL로 게이트 추가(CREATE OR REPLACE, 소유자·권한·주석 유지) → 기존 게이트 결과 동일, 새 게이트 건수 = 직접 계산 건수 확인.
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog;

LOCK TABLE db_pipeline.v_card_integrity_issue IN ACCESS EXCLUSIVE MODE;

DO $gate$
DECLARE
    c_gate CONSTANT text := 'evidence_link_key_mismatch';
    c_part CONSTANT text := $part$
UNION ALL
 SELECT 'evidence_link_key_mismatch'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_source_evidence e
          WHERE (((e.card_doc_id)::text = (l.card_doc_id)::text) AND (e.page_no = l.page_no)
            AND ((e.card_doc_chunk_id)::text = (l.card_doc_chunk_id)::text) AND ((e.evidence_id)::text = (l.evidence_id)::text)))))$part$;
    v_view    regclass := 'db_pipeline.v_card_integrity_issue'::regclass;
    v_def     text;
    v_meta    text;
    v_before  text;
    v_after   text;
    v_expect  bigint;
    v_actual  bigint;
BEGIN
    v_def := pg_get_viewdef(v_view);
    IF position('''' || c_gate || '''::text' IN v_def) > 0 THEN
        RAISE NOTICE '게이트 %가 이미 있습니다. 아무것도 바꾸지 않습니다.', c_gate;
        RETURN;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid
               WHERE d.refobjid = v_view AND r.ev_class <> v_view) THEN
        RAISE EXCEPTION '정합성 뷰에 의존하는 객체가 있어 중단합니다.';
    END IF;
    IF to_regclass('db_pipeline.card_evidence_link') IS NULL OR NOT EXISTS (
        SELECT 1 FROM pg_attribute WHERE attrelid = 'db_pipeline.card_evidence_link'::regclass AND attname = 'card_doc_chunk_id' AND NOT attisdropped) THEN
        RAISE EXCEPTION '근거 연결 테이블이 PK 승계 구조가 아니라 중단합니다.';
    END IF;

    SELECT pg_get_userbyid(relowner) || '|' || coalesce(relacl::text, '-') || '|' || coalesce(obj_description(oid, 'pg_class'), '-') INTO v_meta
    FROM pg_class WHERE oid = v_view;
    SELECT md5(coalesce(string_agg(t::text, E'\n' ORDER BY t::text), '')) INTO v_before FROM db_pipeline.v_card_integrity_issue t;

    EXECUTE format('CREATE OR REPLACE VIEW db_pipeline.v_card_integrity_issue AS %s%s', rtrim(v_def, E'; \n'), c_part);

    -- 검증: 기존 게이트 결과 동일, 새 게이트 건수 = 직접 계산, 소유자·권한·주석 동일
    SELECT md5(coalesce(string_agg(t::text, E'\n' ORDER BY t::text), '')) INTO v_after
    FROM db_pipeline.v_card_integrity_issue t WHERE t.gate_cd <> c_gate;
    IF v_after IS DISTINCT FROM v_before THEN RAISE EXCEPTION '검증 실패: 기존 게이트 결과가 달라졌습니다.'; END IF;
    SELECT count(*) INTO v_expect FROM db_pipeline.card_evidence_link l
    WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e
                      WHERE (e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.evidence_id) = (l.card_doc_id, l.page_no, l.card_doc_chunk_id, l.evidence_id));
    SELECT count(*) INTO v_actual FROM db_pipeline.v_card_integrity_issue WHERE gate_cd = c_gate;
    IF v_actual <> v_expect THEN RAISE EXCEPTION '검증 실패: 새 게이트 % 건, 직접 계산 % 건', v_actual, v_expect; END IF;
    IF (SELECT pg_get_userbyid(relowner) || '|' || coalesce(relacl::text, '-') || '|' || coalesce(obj_description(oid, 'pg_class'), '-')
        FROM pg_class WHERE oid = v_view) IS DISTINCT FROM v_meta THEN
        RAISE EXCEPTION '검증 실패: 뷰 소유자·권한·주석이 달라졌습니다.';
    END IF;
    RAISE NOTICE '게이트 % 추가 완료. 현재 해당 %건, 기존 게이트 결과 동일', c_gate, v_actual;
END
$gate$;

COMMIT;
