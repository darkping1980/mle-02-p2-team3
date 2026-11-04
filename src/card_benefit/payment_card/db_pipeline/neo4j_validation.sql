-- neo4j_validate.py가 neo4j_validation.cypher의 같은 이름 조회와 비교하는 읽기 전용 SQL.
-- 현재 등록된 전체 상품을 대상으로 한다.

-- name: condition_structure
-- Neo4j 혜택·규칙 노드 속성은 card_bnft_id를 유지한다(기존 key 보존). PostgreSQL 뷰 컬럼은 card_product_item_id다.
SELECT owner_cd, card_id, card_product_item_id AS card_bnft_id, rule_key, branch_no, atom_seq, atom_key, cond_type_cd, negate_yn, cond_min_amt, cond_raw_txt
FROM db_pipeline.v_card_cond_atom;

-- name: evidence_links
-- Neo4j 관계 속성 이름은 ev_link_id를 유지한다(재적재 전까지). PostgreSQL 컬럼은 evidence_link_id다.
SELECT l.evidence_link_id AS ev_link_id, l.ev_subject_cd, l.rule_key, l.ev_item_cd, l.ev_item_key,
       l.evidence_id, e.start_pos, e.end_pos
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id;

-- name: common_applies
SELECT card_common_id, card_common_bnft_id, card_id FROM db_pipeline.card_common_bnft_apply;

-- name: rule_targets
SELECT card_id, card_product_item_id AS card_bnft_id, rule_key, target_type_cd, target_key, target_nm FROM db_pipeline.v_card_rule_target;
