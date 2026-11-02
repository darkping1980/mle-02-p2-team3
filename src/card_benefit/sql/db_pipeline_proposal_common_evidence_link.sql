-- [제안, 미적용] 공통 혜택의 원문 근거 연결.
-- 문제: CARD_EVIDENCE_LINK는 card_id가 PK의 일부(NOT NULL)이고 주체가 CARD/BNFT/RULE/REL뿐이며,
--       evidence_subject_orphan 게이트가 card_bnft_id를 CARD_BNFT에서 찾는다. 카드에 속하지 않는 공통 혜택은 연결할 수 없다.
-- 현재 대안: CARD_COMMON_DOC → CARD_EXTR_STG(bnft_nm 일치) → CARD_SOURCE_EVIDENCE 경로로 조회한다
--           (embedding_repository.select_common_bnft_evidence). 이름 일치에 의존하므로 혜택명이 바뀌면 끊긴다.
-- 최소 변경: 기존 테이블·제약을 건드리지 않는 N:M 관계 테이블 1개. 부모 PK를 상속하고 물리 FK는 두지 않는다.
BEGIN;

CREATE TABLE db_pipeline.card_common_evidence_link (
    card_common_id bigint NOT NULL,
    card_common_bnft_id character varying(20) NOT NULL,
    evidence_id character varying(20) NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    CONSTRAINT card_common_evidence_link_pkey PRIMARY KEY (card_common_id, card_common_bnft_id, evidence_id)
);

COMMENT ON TABLE db_pipeline.card_common_evidence_link IS '공통 혜택 원문 근거 관계';

COMMIT;
