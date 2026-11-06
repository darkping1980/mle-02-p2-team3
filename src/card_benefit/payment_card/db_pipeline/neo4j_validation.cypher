// dp_ 그래프 검증용 읽기 전용 조회. 쓰기 구문이 없다.
// neo4j_load_draft.py는 적재 전후 키 확인에, neo4j_validate.py는 PostgreSQL 대조에 쓴다.
// 노드·관계 MERGE는 라벨과 관계 유형이 동적이므로 neo4j_load_draft.py에 둔다.

// name: card_constraints
SHOW CONSTRAINTS YIELD name,type,labelsOrTypes,properties RETURN name,type,labelsOrTypes,properties

// name: existing_node_keys
MATCH (n:dp_node) RETURN collect(n.key) AS keys

// name: node_keys
MATCH (n:dp_node) RETURN n.key AS key

// name: relationship_keys
MATCH (a:dp_node)-[r]->(b:dp_node) WHERE type(r) STARTS WITH 'dp_' RETURN r.key AS key

// name: label_counts
MATCH (n:dp_node)
UNWIND labels(n) AS label
WITH n, label ORDER BY label
WITH n, collect(label) AS labels
RETURN labels, count(*) AS n ORDER BY labels

// name: relationship_counts
MATCH (a:dp_node)-[r]->(b:dp_node) WHERE type(r) STARTS WITH 'dp_'
UNWIND labels(a) AS label
WITH r, label ORDER BY label
WITH r, collect(label) AS start_labels
RETURN type(r) AS type, start_labels, count(*) AS n
ORDER BY type, start_labels

// name: node_sources
MATCH (n:dp_node)
RETURN n.key AS key, labels(n) AS labels, properties(n) AS props

// name: relationship_sources
MATCH (a:dp_node)-[r]->(b:dp_node) WHERE type(r) STARTS WITH 'dp_'
RETURN r.key AS key, type(r) AS type, a.key AS start, b.key AS end, r.source_json AS source_json, properties(r) AS props

// name: outside_scope_counts
// dp_ 경계 위반만 센다. 정상은 모두 0이다. fp_ 등 다른 프로젝트 데이터는 위반이 아니다.
// outside_nodes: dp_node 없이 dp_ 라벨만 있는 노드.
// outside_relationships: dp_ 유형인데 양끝이 dp_node가 아니거나, dp_node끼리 다른 유형으로 연결된 관계.
OPTIONAL MATCH (other)
WHERE NOT other:dp_node AND any(l IN labels(other) WHERE l STARTS WITH 'dp_')
WITH count(other) AS outside_nodes
OPTIONAL MATCH (a)-[r]->(b)
WHERE (type(r) STARTS WITH 'dp_' AND NOT (a:dp_node AND b:dp_node))
   OR (a:dp_node AND b:dp_node AND NOT type(r) STARTS WITH 'dp_')
RETURN outside_nodes, count(r) AS outside_relationships

// name: other_graph_counts
// 판정에 넣지 않고 건수만 보고한다. fp_는 다른 프로젝트 데이터다.
OPTIONAL MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'fp_')
WITH count(n) AS fp_nodes
OPTIONAL MATCH ()-[r]->() WHERE type(r) STARTS WITH 'fp_'
RETURN fp_nodes, count(r) AS fp_relationships

// name: orphan_nodes
// 있어야 할 상위 관계가 없는 노드. 정상은 0건이다.
MATCH (n:dp_node)
WHERE (n:dp_card_bnft AND NOT (:dp_card_product)-[:dp_has_benefit]->(n))
   OR (n:dp_bnft_rule AND NOT (:dp_card_bnft)-[:dp_has_rule]->(n))
   OR (n:dp_cond_expr AND NOT ()-[:dp_has_expr]->(n))
   OR (n:dp_cond_branch AND NOT (:dp_cond_expr)-[:dp_has_branch]->(n))
   OR (n:dp_cond_atom AND NOT (:dp_cond_branch)-[:dp_has_atom]->(n))
   OR (n:dp_rule_target AND NOT (:dp_bnft_rule)-[:dp_targets]->(n))
   OR (n:dp_card_source_evidence AND (NOT (n)-[:dp_in_chunk]->(:dp_card_doc_chunk) OR NOT ()-[:dp_supported_by]->(n)))
   OR (n:dp_card_doc_chunk AND NOT (n)-[:dp_on_page]->(:dp_card_doc_page))
   OR (n:dp_card_doc_page AND NOT (n)-[:dp_in_document]->(:dp_card_doc))
   OR (n:dp_card_doc AND NOT ()-[:dp_has_document]->(n))
   OR (n:dp_card_common_bnft AND NOT (n)-[:dp_belongs_to]->(:dp_card_common))
   OR (n:dp_card_product_item AND NOT n:dp_card_bnft AND NOT (:dp_card_product)-[:dp_has_item]->(n))
RETURN n.key AS key

// name: condition_structure
// 조건식의 소유자, 분기(OR), 조건(AND), NOT을 PostgreSQL v_card_cond_atom과 비교한다.
MATCH (owner:dp_node)-[:dp_has_expr]->(:dp_cond_expr)-[:dp_has_branch]->(br:dp_cond_branch)-[:dp_has_atom]->(a:dp_cond_atom)
RETURN CASE WHEN owner:dp_card_product THEN 'CARD' WHEN owner:dp_bnft_rule THEN 'RULE' ELSE 'BNFT' END AS owner_cd,
       owner.card_id AS card_id, owner.card_bnft_id AS card_bnft_id, owner.rule_key AS rule_key, br.branch_no AS branch_no,
       a.atom_seq AS atom_seq, a.key_name AS atom_key, a.kind AS cond_type_cd, a.negate AS negate_yn,
       a.min_amt AS cond_min_amt, a.raw_text AS cond_raw_txt

// name: evidence_links
// 근거 연결을 PostgreSQL card_evidence_link와 비교한다. 연결 행 하나가 관계 하나다.
// 공통 혜택 근거(검색 투영, link_source 있음)는 card_evidence_link 행이 아니므로 common_evidence_links에서 따로 비교한다.
MATCH (owner:dp_node)-[l:dp_supported_by]->(e:dp_card_source_evidence)
WHERE l.link_source IS NULL
RETURN l.ev_link_id AS ev_link_id, l.ev_subject_cd AS ev_subject_cd, owner.rule_key AS rule_key,
       l.ev_item_cd AS ev_item_cd, l.ev_item_key AS ev_item_key, e.evidence_id AS evidence_id, e.start_pos AS start_pos, e.end_pos AS end_pos

// name: common_evidence_links
// 공통 혜택 근거(검색 투영)를 PostgreSQL 추출 경로(neo4j_validation.sql 같은 이름)와 비교한다.
MATCH (c:dp_card_common_bnft)-[l:dp_supported_by {link_source: 'COMMON_STG'}]->(e:dp_card_source_evidence)
RETURN c.card_common_id AS card_common_id, c.card_common_bnft_id AS card_common_bnft_id, e.evidence_id AS evidence_id,
       l.ev_subject_cd AS ev_subject_cd, l.ev_item_key AS ev_item_key

// name: common_applies
// 공통 혜택 적용 관계를 PostgreSQL card_common_bnft_apply와 비교한다.
MATCH (c:dp_card_product)-[:dp_has_common_benefit]->(b:dp_card_common_bnft)
RETURN b.card_common_id AS card_common_id, b.card_common_bnft_id AS card_common_bnft_id, c.card_id AS card_id

// name: rule_targets
// 규칙 대상을 PostgreSQL v_card_rule_target과 비교한다.
MATCH (r:dp_bnft_rule)-[:dp_targets]->(t:dp_rule_target)
RETURN r.card_id AS card_id, r.card_bnft_id AS card_bnft_id, r.rule_key AS rule_key,
       t.target_type_cd AS target_type_cd, t.target_key AS target_key, t.target_nm AS target_nm

// name: benefit_item_data
// 2026-11-06 P2: 혜택 노드 source_json의 item_data. 키가 없으면 has_item_data=false(NULL 값과 구분한다).
MATCH (b:dp_card_bnft)
WITH b, apoc.convert.fromJsonMap(b.source_json) AS src
RETURN b.card_id AS card_id, b.card_bnft_id AS card_bnft_id, 'item_data' IN keys(src) AS has_item_data, src.item_data AS item_data
