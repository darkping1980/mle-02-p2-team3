// 카드 시험 그래프 검증용 읽기 전용 조회. 쓰기 구문이 없다.
// neo4j_load_draft.py는 적재 전후 키 확인에, neo4j_validate.py는 PostgreSQL 대조에 쓴다.
// 노드·관계 MERGE는 라벨과 관계 유형이 동적이므로 neo4j_load_draft.py에 둔다.

// name: card_constraints
SHOW CONSTRAINTS YIELD type,labelsOrTypes,properties RETURN type,labelsOrTypes,properties

// name: existing_node_keys
MATCH (n:A8Test {namespace:$ns}) RETURN collect(n.key) AS keys

// name: node_keys
MATCH (n:A8Test {namespace:$ns}) RETURN n.key AS key

// name: relationship_keys
MATCH (a:A8Test {namespace:$ns})-[r]->(b:A8Test {namespace:$ns}) WHERE r.namespace=$ns RETURN r.key AS key

// name: label_counts
MATCH (n:A8Test {namespace:$ns})
RETURN [l IN labels(n) WHERE l <> 'A8Test'][0] AS label, count(*) AS n ORDER BY label

// name: relationship_counts
MATCH (a:A8Test {namespace:$ns})-[r]->(b:A8Test {namespace:$ns})
RETURN type(r) AS type, [l IN labels(a) WHERE l <> 'A8Test'][0] AS start_label, count(*) AS n
ORDER BY type, start_label

// name: node_sources
MATCH (n:A8Test {namespace:$ns})
RETURN n.key AS key, [l IN labels(n) WHERE l <> 'A8Test'][0] AS label, n.source_json AS source_json

// name: relationship_sources
MATCH (a:A8Test {namespace:$ns})-[r]->(b:A8Test {namespace:$ns})
RETURN r.key AS key, type(r) AS type, a.key AS start, b.key AS end, r.source_json AS source_json

// name: outside_scope_counts
// 이름공간 밖 노드와, 시험 노드에 붙은 범위 밖 관계. 정상은 모두 0이다.
OPTIONAL MATCH (other) WHERE NOT other:A8Test OR other.namespace <> $ns
WITH count(other) AS outside_nodes
OPTIONAL MATCH (a:A8Test {namespace:$ns})-[r]-(b)
WHERE NOT b:A8Test OR b.namespace <> $ns OR r.namespace IS NULL OR r.namespace <> $ns
RETURN outside_nodes, count(r) AS outside_relationships

// name: orphan_nodes
// 있어야 할 상위 관계가 없는 노드. 정상은 0건이다.
MATCH (n:A8Test {namespace:$ns})
WHERE (n:A8Policy AND NOT (:A8Card)-[:A8_HAS_POLICY]->(n))
   OR (n:A8Benefit AND NOT (:A8Policy)-[:A8_HAS_BENEFIT]->(n))
   OR (n:A8Rule AND NOT (:A8Benefit)-[:A8_HAS_RULE]->(n))
   OR (n:A8Expression AND NOT ()-[:A8_HAS_EXPR]->(n))
   OR (n:A8Branch AND NOT (:A8Expression)-[:A8_HAS_BRANCH]->(n))
   OR (n:A8Condition AND NOT (:A8Branch)-[:A8_HAS_ATOM]->(n))
   OR (n:A8Target AND NOT (:A8Rule)-[:A8_TARGETS]->(n))
   OR (n:A8LimitPool AND NOT (:A8Rule)-[:A8_CONSUMES]->(n))
   OR (n:A8Evidence AND (NOT (n)-[:A8_IN_CHUNK]->(:A8Chunk) OR NOT ()-[:A8_SUPPORTED_BY]->(n)))
   OR (n:A8Chunk AND NOT (n)-[:A8_ON_PAGE]->(:A8Page))
   OR (n:A8Page AND NOT (n)-[:A8_IN_DOCUMENT]->(:A8Document))
RETURN n.key AS key

// name: condition_structure
// 조건식의 소유자, 분기(OR), 조건(AND), NOT을 PostgreSQL v_card_cond_atom과 비교한다.
MATCH (owner:A8Test {namespace:$ns})-[:A8_HAS_EXPR]->(:A8Expression)-[:A8_HAS_BRANCH]->(br:A8Branch)-[:A8_HAS_ATOM]->(a:A8Condition)
RETURN CASE WHEN owner:A8Policy THEN 'POLICY' WHEN owner:A8Rule THEN 'RULE' ELSE 'BNFT' END AS owner_cd,
       owner.card_bnft_id AS card_bnft_id, owner.rule_key AS rule_key, br.branch_no AS branch_no, a.atom_seq AS atom_seq,
       a.key_name AS atom_key, a.kind AS cond_type_cd, a.negate AS negate_yn, a.min_amt AS cond_min_amt, a.raw_text AS cond_raw_txt

// name: evidence_links
// 근거 연결을 PostgreSQL card_policy_evidence와 비교한다. 연결 행 하나가 관계 하나다.
MATCH (owner:A8Test {namespace:$ns})-[l:A8_SUPPORTED_BY]->(e:A8Evidence)
RETURN l.ev_link_id AS ev_link_id, l.ev_subject_cd AS ev_subject_cd, owner.rule_key AS rule_key, owner.pool_id AS pool_id,
       l.ev_item_cd AS ev_item_cd, l.ev_item_key AS ev_item_key, e.evidence_id AS evidence_id, e.start_pos AS start_pos, e.end_pos AS end_pos
