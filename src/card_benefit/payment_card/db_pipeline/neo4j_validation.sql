-- neo4j_validate.py가 neo4j_validation.cypher의 같은 이름 조회와 비교하는 읽기 전용 SQL.
-- DBeaver에서 바로 실행할 수 있도록 값을 고정한다. 대상은 card_id=2 상품 한 건이다.

-- name: condition_structure
SELECT owner_cd, card_bnft_id, rule_key, branch_no, atom_seq, atom_key, cond_type_cd, negate_yn, cond_min_amt, cond_raw_txt
FROM db_pipeline.v_card_cond_atom
WHERE card_id = 2;

-- name: evidence_links
SELECT l.ev_link_id, l.ev_subject_cd, l.rule_key, l.pool_id, l.ev_item_cd, l.ev_item_key,
       l.evidence_id, e.start_pos, e.end_pos
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id
WHERE l.card_id = 2;
