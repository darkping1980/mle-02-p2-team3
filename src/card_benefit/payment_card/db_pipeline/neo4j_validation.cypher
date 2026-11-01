// DF 그래프 검증용 읽기 전용 조회. 쓰기 구문이 없다.
// neo4j_load_draft.py는 적재 전후 키 확인에, neo4j_validate.py는 PostgreSQL 대조에 쓴다.
// 노드·관계 MERGE는 라벨과 관계 유형이 동적이므로 neo4j_load_draft.py에 둔다.

// name: card_constraints
SHOW CONSTRAINTS YIELD type,labelsOrTypes,properties RETURN type,labelsOrTypes,properties

// name: existing_node_keys
MATCH (n:df_node {namespace:$ns}) RETURN collect(n.key) AS keys

// name: node_keys
MATCH (n:df_node {namespace:$ns}) RETURN n.key AS key

// name: relationship_keys
MATCH (a:df_node {namespace:$ns})-[r]->(b:df_node {namespace:$ns}) WHERE r.namespace=$ns RETURN r.key AS key

// name: label_counts
MATCH (n:df_node {namespace:$ns})
RETURN [l IN labels(n) WHERE l <> 'df_node'][0] AS label, count(*) AS n ORDER BY label

// name: relationship_counts
MATCH (a:df_node {namespace:$ns})-[r]->(b:df_node {namespace:$ns})
RETURN type(r) AS type, [l IN labels(a) WHERE l <> 'df_node'][0] AS start_label, count(*) AS n
ORDER BY type, start_label

// name: node_sources
MATCH (n:df_node {namespace:$ns})
RETURN n.key AS key, [l IN labels(n) WHERE l <> 'df_node'][0] AS label, n.source_json AS source_json

// name: relationship_sources
MATCH (a:df_node {namespace:$ns})-[r]->(b:df_node {namespace:$ns})
RETURN r.key AS key, type(r) AS type, a.key AS start, b.key AS end, r.source_json AS source_json

// name: outside_scope_counts
// DF 경계 위반만 센다. 정상은 모두 0이다. DF와 무관한 A8·PF 데이터는 위반이 아니다.
// outside_nodes: namespace가 다른 df_node, df_node 레이블이 없는 df_ 노드.
// outside_relationships: df_node에 닿거나 df_ 유형인 관계 중 양끝·유형·namespace가 모두 DF가 아닌 것(DF–PF 연결 포함).
OPTIONAL MATCH (other)
WHERE (other:df_node AND coalesce(other.namespace,'') <> $ns)
   OR (NOT other:df_node AND any(l IN labels(other) WHERE l STARTS WITH 'df_'))
WITH count(other) AS outside_nodes
OPTIONAL MATCH (a)-[r]->(b)
WHERE (a:df_node OR b:df_node OR type(r) STARTS WITH 'df_')
  AND NOT (a:df_node AND b:df_node AND type(r) STARTS WITH 'df_' AND coalesce(r.namespace,'') = $ns)
RETURN outside_nodes, count(r) AS outside_relationships

// name: other_graph_counts
// DF 판정에 넣지 않고 건수만 보고한다. A8은 DF 전환 검증 중 공존하고 PF는 팀원이 따로 적재한다.
OPTIONAL MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'pf_')
WITH count(n) AS pf_nodes
OPTIONAL MATCH ()-[r]->() WHERE type(r) STARTS WITH 'pf_'
WITH pf_nodes, count(r) AS pf_relationships
OPTIONAL MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'A8')
WITH pf_nodes, pf_relationships, count(n) AS a8_nodes
OPTIONAL MATCH ()-[r]->() WHERE type(r) STARTS WITH 'A8_'
RETURN pf_nodes, pf_relationships, a8_nodes, count(r) AS a8_relationships

// name: orphan_nodes
// 있어야 할 상위 관계가 없는 노드. 정상은 0건이다.
MATCH (n:df_node {namespace:$ns})
WHERE (n:df_card_policy_version AND NOT (:df_card_product)-[:df_has_policy]->(n))
   OR (n:df_card_bnft AND NOT (:df_card_policy_version)-[:df_has_benefit]->(n))
   OR (n:df_bnft_rule AND NOT (:df_card_bnft)-[:df_has_rule]->(n))
   OR (n:df_cond_expr AND NOT ()-[:df_has_expr]->(n))
   OR (n:df_cond_branch AND NOT (:df_cond_expr)-[:df_has_branch]->(n))
   OR (n:df_cond_atom AND NOT (:df_cond_branch)-[:df_has_atom]->(n))
   OR (n:df_rule_target AND NOT (:df_bnft_rule)-[:df_targets]->(n))
   OR (n:df_card_limit_pool AND NOT (:df_bnft_rule)-[:df_consumes]->(n))
   OR (n:df_card_source_evidence AND (NOT (n)-[:df_in_chunk]->(:df_card_doc_chunk) OR NOT ()-[:df_supported_by]->(n)))
   OR (n:df_card_doc_chunk AND NOT (n)-[:df_on_page]->(:df_card_doc_page))
   OR (n:df_card_doc_page AND NOT (n)-[:df_in_document]->(:df_card_doc))
RETURN n.key AS key

// name: condition_structure
// 조건식의 소유자, 분기(OR), 조건(AND), NOT을 PostgreSQL v_card_cond_atom과 비교한다.
MATCH (owner:df_node {namespace:$ns})-[:df_has_expr]->(:df_cond_expr {namespace:$ns})-[:df_has_branch]->(br:df_cond_branch {namespace:$ns})-[:df_has_atom]->(a:df_cond_atom {namespace:$ns})
RETURN CASE WHEN owner:df_card_policy_version THEN 'POLICY' WHEN owner:df_bnft_rule THEN 'RULE' ELSE 'BNFT' END AS owner_cd,
       owner.card_bnft_id AS card_bnft_id, owner.rule_key AS rule_key, br.branch_no AS branch_no, a.atom_seq AS atom_seq,
       a.key_name AS atom_key, a.kind AS cond_type_cd, a.negate AS negate_yn, a.min_amt AS cond_min_amt, a.raw_text AS cond_raw_txt

// name: evidence_links
// 근거 연결을 PostgreSQL card_policy_evidence와 비교한다. 연결 행 하나가 관계 하나다.
MATCH (owner:df_node {namespace:$ns})-[l:df_supported_by]->(e:df_card_source_evidence {namespace:$ns})
RETURN l.ev_link_id AS ev_link_id, l.ev_subject_cd AS ev_subject_cd, owner.rule_key AS rule_key, owner.pool_id AS pool_id,
       l.ev_item_cd AS ev_item_cd, l.ev_item_key AS ev_item_key, e.evidence_id AS evidence_id, e.start_pos AS start_pos, e.end_pos AS end_pos
