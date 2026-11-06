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

-- name: common_evidence_links
-- GraphRAG의 공통 혜택 근거 대체 조회(embedding_repository.select_common_bnft_evidence)와 같은 경로. 공통 혜택·근거 쌍마다 1행.
SELECT DISTINCT b.card_common_id, b.card_common_bnft_id, e.evidence_id, 'BNFT' AS ev_subject_cd, '-' AS ev_item_key
FROM db_pipeline.card_common_bnft b
JOIN db_pipeline.card_common_doc d ON d.card_common_id = b.card_common_id
JOIN db_pipeline.card_extr_stg s
  ON s.card_doc_id = d.card_doc_id AND s.stg_kind_cd = 'BENEFIT' AND s.stg_raw_item->>'bnft_nm' = b.bnft_nm
 AND s.stg_sql_check_cd IS NOT NULL AND s.stg_parent_card_extr_stg_id IS NULL
JOIN db_pipeline.card_source_evidence e ON e.card_extr_stg_id = s.card_extr_stg_id;

-- name: common_applies
SELECT card_common_id, card_common_bnft_id, card_id FROM db_pipeline.card_common_bnft_apply;

-- name: rule_targets
SELECT card_id, card_product_item_id AS card_bnft_id, rule_key, target_type_cd, target_key, target_nm FROM db_pipeline.v_card_rule_target;

-- name: source_columns
-- 2026-11-06 P2: 스냅샷 SELECT와 독립된 원천 컬럼 목록. neo4j_dry_run.column_coverage가 분류 누락을 검사한다.
SELECT table_name, column_name FROM information_schema.columns
WHERE table_schema = 'db_pipeline' AND table_name IN ('card_product_item', 'card_evidence_link')
ORDER BY table_name, ordinal_position;

-- name: benefit_item_data
-- 2026-11-06 P2: 혜택 item_data를 스냅샷 함수를 거치지 않고 직접 읽는다. Neo4j 혜택 노드 source_json의 item_data와 대조한다.
SELECT card_id, card_product_item_id AS card_bnft_id, item_data FROM db_pipeline.card_product_item WHERE item_type_cd = 'BENEFIT';
