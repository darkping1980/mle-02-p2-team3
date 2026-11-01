// 카드 GraphRAG가 쓰는 읽기 전용 조회. 모두 MATCH/RETURN만 쓴다.
// neo4j_search.py가 공통 Neo4jDbSession의 mapper로 읽고, 실행은 Neo4jSearch._query가 맡는다.
// 값은 항상 파라미터로 전달한다. $ns는 _query가 넣는 이름공간이다.
//
// statement             Python 함수                       호출 위치
// catalog               Neo4jSearch.list_catalog          interpret 노드
// list_benefits         Neo4jSearch.list_benefits         테스트, 진단
// benefit_context       Neo4jSearch.get_detail            retrieve 노드
// benefit_rules         get_detail(sections=rules)        retrieve 노드
// benefit_conditions    get_detail(sections=conditions)   retrieve 노드
// benefit_limits        get_detail(sections=limits)       retrieve 노드
// benefit_evidence      get_detail(sections=evidence)     retrieve 노드

// name: catalog
MATCH (c:df_card_product {namespace:$ns})-[:df_has_policy]->(p:df_card_policy_version {namespace:$ns})
      -[:df_has_benefit]->(b:df_card_bnft {namespace:$ns})
OPTIONAL MATCH (b)-[:df_has_rule]->(r:df_bnft_rule {namespace:$ns})
OPTIONAL MATCH (r)-[:df_targets]->(t:df_rule_target {namespace:$ns})
OPTIONAL MATCH (r)-[:df_has_expr]->(:df_cond_expr {namespace:$ns})-[:df_has_branch]->(:df_cond_branch {namespace:$ns})
      -[:df_has_atom]->(a:df_cond_atom {namespace:$ns,kind:'SPEND_REQ'})
RETURN b.key AS key, b.name AS name, b.card_bnft_id AS id, b.verification_status AS status,
       c.source_json AS card_source, collect(DISTINCT t.target_nm) AS targets,
       collect(DISTINCT a.min_amt) AS payment_min_amounts
ORDER BY name

// name: list_benefits
MATCH (c:df_card_product {namespace:$ns})-[:df_has_policy]->(p:df_card_policy_version {namespace:$ns})
      -[:df_has_benefit]->(b:df_card_bnft {namespace:$ns})
WHERE toLower(coalesce(b.name,'')) CONTAINS toLower($keyword)
RETURN b.key AS key, b.name AS name, b.card_bnft_id AS id,
       b.verification_status AS status ORDER BY b.name

// name: benefit_context
MATCH (c:df_card_product {namespace:$ns})-[:df_has_policy]->(p:df_card_policy_version {namespace:$ns})
      -[:df_has_benefit]->(b:df_card_bnft {namespace:$ns,key:$key})
RETURN properties(c) AS card, properties(p) AS policy, properties(b) AS benefit,
       labels(c) AS card_labels, labels(p) AS policy_labels, labels(b) AS benefit_labels

// name: benefit_rules
MATCH (b:df_card_bnft {namespace:$ns,key:$key})-[:df_has_rule]->(r:df_bnft_rule {namespace:$ns})
OPTIONAL MATCH (r)-[:df_targets]->(t:df_rule_target {namespace:$ns})
RETURN properties(r) AS rule, labels(r) AS labels, collect(DISTINCT t.target_nm) AS targets
ORDER BY rule.rule_key

// name: benefit_conditions
MATCH (p:df_card_policy_version {namespace:$ns})-[:df_has_benefit]->(b:df_card_bnft {namespace:$ns,key:$key})
OPTIONAL MATCH (b)-[:df_has_rule]->(r:df_bnft_rule {namespace:$ns})
WITH p,b,collect(DISTINCT r) AS rules
UNWIND [p,b] + rules AS owner
MATCH (owner)-[:df_has_expr]->(x:df_cond_expr {namespace:$ns})
      -[:df_has_branch]->(branch:df_cond_branch {namespace:$ns})
      -[:df_has_atom]->(a:df_cond_atom {namespace:$ns})
// owner_cd는 레이블 이름과 무관하다. 코드 순서 BNFT, POLICY, RULE이 조건 표시 순서다.
RETURN CASE WHEN owner:df_card_policy_version THEN 'POLICY' WHEN owner:df_bnft_rule THEN 'RULE' ELSE 'BNFT' END AS owner_cd,
       owner.rule_key AS rule_key,
       properties(x) AS expression, branch.branch_no AS branch_no,
       properties(a) AS atom, labels(a) AS labels
ORDER BY owner_cd, rule_key, branch_no, a.atom_seq

// name: benefit_limits
MATCH (b:df_card_bnft {namespace:$ns,key:$key})-[:df_has_rule]->(r:df_bnft_rule {namespace:$ns})
      -[:df_consumes]->(pool:df_card_limit_pool {namespace:$ns})
RETURN properties(pool) AS pool, labels(pool) AS labels,
       collect(DISTINCT r.rule_key) AS rule_keys ORDER BY pool.pool_id

// name: benefit_evidence
MATCH (policy:df_card_policy_version {namespace:$ns})-[:df_has_benefit]->(b:df_card_bnft {namespace:$ns,key:$key})
OPTIONAL MATCH (b)-[:df_has_rule]->(rule:df_bnft_rule {namespace:$ns})
WITH policy,b,collect(DISTINCT rule) AS rules
OPTIONAL MATCH (b)-[:df_has_rule]->(:df_bnft_rule {namespace:$ns})-[:df_consumes]->(pool:df_card_limit_pool {namespace:$ns})
WITH policy,b,rules,collect(DISTINCT pool) AS pools
UNWIND [policy,b] + pools + rules AS owner
MATCH (owner)-[link:df_supported_by]->(e:df_card_source_evidence {namespace:$ns})
      -[:df_in_chunk]->(chunk:df_card_doc_chunk {namespace:$ns})
      -[:df_on_page]->(page:df_card_doc_page {namespace:$ns})
      -[:df_in_document]->(doc:df_card_doc {namespace:$ns})
RETURN labels(owner) AS owner_labels, owner.pool_id AS pool_id, owner.rule_key AS rule_key,
       properties(link) AS link, properties(e) AS evidence,
       properties(chunk) AS chunk, properties(page) AS page, properties(doc) AS document
ORDER BY page.page_no, e.start_pos, e.evidence_id
