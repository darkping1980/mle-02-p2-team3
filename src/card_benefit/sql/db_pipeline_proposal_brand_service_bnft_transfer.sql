-- [제안, 미적용] CARD_BNFT의 BRAND_SERVICE 행 정리안. 사용자 승인 전 실행하지 않는다.
-- 대상(2026-11-03): 1건. card_id=5, card_bnft_id=20261102_000008, Visa 컨시어지, PENDING_REVIEW
--   함께 걸린 데이터: CARD_EVIDENCE_LINK BNFT 3건(근거 063~065), CARD_PRODUCT_DOC BRAND_SERVICE 1건(문서 20261102_000004)
-- 원래 식별자: sha256('HANA_VS002' + NUL + 'VISA_SIGNATURE_CONCIERGE')가 bnft_cd 전체와 일치한다. 공통 혜택도 같은 bnft_cd로 등록돼 있다.
-- 이관 전 원본과 근거·문서 연결은 src/data/backup/pre_common_transfer_20261103.json에 보존했다.
-- 실행 전 benefit_main brand-compare 결과가 SAME인 행만 대상이다. REVIEW·NO_COMMON 행은 사람이 판단하고 이관하지 않는다.
-- 근거 원본(CARD_SOURCE_EVIDENCE)과 문서 연결(CARD_PRODUCT_DOC)은 지우지 않는다. 대응 관계는 bnft_cd로 유지된다.

-- 1. 이전 전 점검: card_bnft 행마다 같은 bnft_cd의 공통 혜택과 적용 관계가 있어야 한다.
SELECT b.card_id, b.card_bnft_id, b.bnft_cd, b.bnft_nm, cb.card_common_bnft_id, a.card_id AS apply_card_id,
       (SELECT count(*) FROM db_pipeline.card_evidence_link l
        WHERE l.card_id = b.card_id AND l.card_bnft_id = b.card_bnft_id) AS evidence_link_cnt
FROM db_pipeline.card_bnft b
LEFT JOIN db_pipeline.card_common_bnft cb ON cb.bnft_cd = b.bnft_cd
LEFT JOIN db_pipeline.card_common_bnft_apply a
       ON a.card_common_id = cb.card_common_id
      AND a.card_common_bnft_id = cb.card_common_bnft_id
      AND a.card_id = b.card_id
WHERE b.bnft_origin_cd = 'BRAND_SERVICE';

-- 2. 정리. 공통 근거 연결 테이블(db_pipeline_proposal_common_evidence_link.sql)을 먼저 적용하고 주석을 푼다.
-- BEGIN;
-- INSERT INTO db_pipeline.card_common_evidence_link (card_common_id, card_common_bnft_id, evidence_id, create_user_id)
-- SELECT cb.card_common_id, cb.card_common_bnft_id, l.evidence_id, 'SYSTEM'
-- FROM db_pipeline.card_bnft b
-- JOIN db_pipeline.card_common_bnft cb ON cb.bnft_cd = b.bnft_cd
-- JOIN db_pipeline.card_evidence_link l ON l.card_id = b.card_id AND l.card_bnft_id = b.card_bnft_id
-- WHERE b.bnft_origin_cd = 'BRAND_SERVICE'
-- ON CONFLICT DO NOTHING;
-- DELETE FROM db_pipeline.card_evidence_link l USING db_pipeline.card_bnft b
-- WHERE l.card_id = b.card_id AND l.card_bnft_id = b.card_bnft_id AND b.bnft_origin_cd = 'BRAND_SERVICE';
-- DELETE FROM db_pipeline.card_bnft WHERE bnft_origin_cd = 'BRAND_SERVICE';
-- COMMIT;
