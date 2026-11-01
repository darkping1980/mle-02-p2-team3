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
MATCH (c:A8Card {namespace:$ns})-[:A8_HAS_POLICY]->(p:A8Policy {namespace:$ns})
      -[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns})
OPTIONAL MATCH (b)-[:A8_HAS_RULE]->(r:A8Rule {namespace:$ns})
OPTIONAL MATCH (r)-[:A8_TARGETS]->(t:A8Target {namespace:$ns})
OPTIONAL MATCH (r)-[:A8_HAS_EXPR]->(:A8Expression {namespace:$ns})-[:A8_HAS_BRANCH]->(:A8Branch {namespace:$ns})
      -[:A8_HAS_ATOM]->(a:A8Condition {namespace:$ns,kind:'SPEND_REQ'})
RETURN b.key AS key, b.name AS name, b.card_bnft_id AS id, b.verification_status AS status,
       c.source_json AS card_source, collect(DISTINCT t.target_nm) AS targets,
       collect(DISTINCT a.min_amt) AS payment_min_amounts
ORDER BY name

// name: list_benefits
MATCH (c:A8Card {namespace:$ns})-[:A8_HAS_POLICY]->(p:A8Policy {namespace:$ns})
      -[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns})
WHERE toLower(coalesce(b.name,'')) CONTAINS toLower($keyword)
RETURN b.key AS key, b.name AS name, b.card_bnft_id AS id,
       b.verification_status AS status ORDER BY b.name

// name: benefit_context
MATCH (c:A8Card {namespace:$ns})-[:A8_HAS_POLICY]->(p:A8Policy {namespace:$ns})
      -[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns,key:$key})
RETURN properties(c) AS card, properties(p) AS policy, properties(b) AS benefit,
       labels(c) AS card_labels, labels(p) AS policy_labels, labels(b) AS benefit_labels

// name: benefit_rules
MATCH (b:A8Benefit {namespace:$ns,key:$key})-[:A8_HAS_RULE]->(r:A8Rule {namespace:$ns})
OPTIONAL MATCH (r)-[:A8_TARGETS]->(t:A8Target {namespace:$ns})
RETURN properties(r) AS rule, labels(r) AS labels, collect(DISTINCT t.target_nm) AS targets
ORDER BY rule.rule_key

// name: benefit_conditions
MATCH (p:A8Policy {namespace:$ns})-[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns,key:$key})
OPTIONAL MATCH (b)-[:A8_HAS_RULE]->(r:A8Rule {namespace:$ns})
WITH p,b,collect(DISTINCT r) AS rules
UNWIND [p,b] + rules AS owner
MATCH (owner)-[:A8_HAS_EXPR]->(x:A8Expression {namespace:$ns})
      -[:A8_HAS_BRANCH]->(branch:A8Branch {namespace:$ns})
      -[:A8_HAS_ATOM]->(a:A8Condition {namespace:$ns})
RETURN labels(owner) AS owner_labels, owner.rule_key AS rule_key,
       properties(x) AS expression, branch.branch_no AS branch_no,
       properties(a) AS atom, labels(a) AS labels
ORDER BY owner_labels, rule_key, branch_no, a.atom_seq

// name: benefit_limits
MATCH (b:A8Benefit {namespace:$ns,key:$key})-[:A8_HAS_RULE]->(r:A8Rule {namespace:$ns})
      -[:A8_CONSUMES]->(pool:A8LimitPool {namespace:$ns})
RETURN properties(pool) AS pool, labels(pool) AS labels,
       collect(DISTINCT r.rule_key) AS rule_keys ORDER BY pool.pool_id

// name: benefit_evidence
MATCH (policy:A8Policy {namespace:$ns})-[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns,key:$key})
OPTIONAL MATCH (b)-[:A8_HAS_RULE]->(rule:A8Rule {namespace:$ns})
WITH policy,b,collect(DISTINCT rule) AS rules
OPTIONAL MATCH (b)-[:A8_HAS_RULE]->(:A8Rule)-[:A8_CONSUMES]->(pool:A8LimitPool {namespace:$ns})
WITH policy,b,rules,collect(DISTINCT pool) AS pools
UNWIND [policy,b] + pools + rules AS owner
MATCH (owner)-[link:A8_SUPPORTED_BY]->(e:A8Evidence {namespace:$ns})
      -[:A8_IN_CHUNK]->(chunk:A8Chunk {namespace:$ns})
      -[:A8_ON_PAGE]->(page:A8Page {namespace:$ns})
      -[:A8_IN_DOCUMENT]->(doc:A8Document {namespace:$ns})
RETURN labels(owner) AS owner_labels, owner.pool_id AS pool_id, owner.rule_key AS rule_key,
       properties(link) AS link, properties(e) AS evidence,
       properties(chunk) AS chunk, properties(page) AS page, properties(doc) AS document
ORDER BY page.page_no, e.start_pos, e.evidence_id
