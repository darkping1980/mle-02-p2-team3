// 카드 GraphRAG가 쓰는 읽기 전용 조회. 모두 MATCH/RETURN만 쓴다. 대상은 dp_ 라벨뿐이다.
// neo4j_search.py가 공통 Neo4jDbSession의 mapper로 읽고, 실행은 Neo4jSearch._query가 맡는다.
// 값은 항상 파라미터로 전달한다.
//
// statement                Python 함수                       호출 위치
// catalog                  Neo4jSearch.list_catalog          interpret 노드
// common_catalog           Neo4jSearch.list_catalog          interpret 노드
// list_benefits            Neo4jSearch.list_benefits         문자열 검색 보조
// candidate_relations      Neo4jSearch.candidate_relations   검색 후보 관계 확인
// benefit_context          Neo4jSearch.get_detail            retrieve 노드
// benefit_rules            get_detail(sections=rules)        retrieve 노드
// benefit_conditions       get_detail(sections=conditions)   retrieve 노드
// benefit_limits           get_detail(sections=limits)       retrieve 노드
// benefit_evidence         get_detail(sections=evidence)     retrieve 노드
// common_benefit_evidence  get_detail(sections=evidence)     retrieve 노드. 공통 혜택
// hop1_*, hop2_*, hop3_*   Neo4jSearch.hop                   다중 홉 검증

// name: catalog
// 동일성이 확인된 기존 행은 공통 혜택으로 표시하므로 목록에서 뺀다.
MATCH (c:dp_card_product)-[:dp_has_benefit]->(b:dp_card_bnft)
WHERE NOT (b)-[:dp_same_as]->(:dp_card_common_bnft)
OPTIONAL MATCH (b)-[:dp_has_rule]->(r:dp_bnft_rule)
OPTIONAL MATCH (r)-[:dp_targets]->(t:dp_rule_target)
// 결제 금액 기준: 규칙의 SPEND_REQ와, 결제 건당 금액(cond_basis_cd TXN_AMT)으로 등록된 USAGE_REQ(예: 매출 건당 3만원 이상).
// cond_basis_cd는 노드 속성이 아니라 source_json(정렬·공백 없는 JSON)에만 있어 문자열로 확인한다.
OPTIONAL MATCH (r)-[:dp_has_expr]->(:dp_cond_expr)-[:dp_has_branch]->(:dp_cond_branch)-[:dp_has_atom]->(a:dp_cond_atom)
WHERE a.kind = 'SPEND_REQ' OR (a.kind = 'USAGE_REQ' AND a.source_json CONTAINS '"cond_basis_cd":"TXN_AMT"')
RETURN b.key AS key, b.name AS name, b.card_bnft_id AS id, b.verification_status AS status,
       c.source_json AS card_source, collect(DISTINCT t.target_nm) AS targets,
       collect(DISTINCT a.min_amt) AS payment_min_amounts
ORDER BY name

// name: item_catalog
// 혜택이 아닌 카드 상품 항목(연회비 등). 금액 등 상세는 source_json의 item_data에 있다.
// TERMS(할인 제공 유의사항)는 선택 후보가 아니라 선택된 혜택에 붙는 근거라 여기서 뺀다(2026-11-05).
MATCH (c:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item)
WHERE i.item_type_cd <> 'BENEFIT' AND i.item_type_cd <> 'TERMS'
RETURN i.key AS key, i.name AS name, i.card_product_item_id AS id, i.verification_status AS status,
       i.item_type_cd AS item_type, i.source_json AS item_source, c.source_json AS card_source
ORDER BY c.card_id, i.card_product_item_id

// name: common_catalog
// 적용 관계가 없는 공통 혜택은 cards가 빈 목록이다. 임의로 카드를 붙이지 않는다.
MATCH (b:dp_card_common_bnft)-[:dp_belongs_to]->(s:dp_card_common)
OPTIONAL MATCH (c:dp_card_product)-[:dp_has_common_benefit]->(b)
RETURN b.key AS key, b.name AS name, b.card_common_bnft_id AS id, null AS status,
       s.common_nm AS common_nm, collect(c.product_nm) AS cards
ORDER BY name

// name: list_benefits
MATCH (b:dp_node)
WHERE (b:dp_card_bnft OR b:dp_card_common_bnft) AND NOT (b)-[:dp_same_as]->(:dp_card_common_bnft)
  AND toLower(coalesce(b.name,'')) CONTAINS toLower($keyword)
RETURN b.key AS key, b.name AS name, coalesce(b.card_bnft_id, b.card_common_bnft_id) AS id,
       b.verification_status AS status ORDER BY b.name

// name: candidate_relations
// 검색 후보의 카드, 대상, 혜택 적용 제외 문구, 공통서비스를 관계로 찾는다.
MATCH (b:dp_node)
WHERE (b:dp_card_bnft OR b:dp_card_common_bnft) AND coalesce(b.card_bnft_id, b.card_common_bnft_id) IN $ids
OPTIONAL MATCH (c:dp_card_product)-[:dp_has_benefit|dp_has_common_benefit]->(b)
OPTIONAL MATCH (b)-[:dp_has_rule]->(:dp_bnft_rule)-[:dp_targets]->(t:dp_rule_target)
OPTIONAL MATCH (b)-[:dp_has_rule*0..1]->(owner)-[:dp_has_expr]->(:dp_cond_expr)-[:dp_has_branch]->(:dp_cond_branch)
      -[:dp_has_atom]->(a:dp_cond_atom {kind:'BNFT_EXCL'})
OPTIONAL MATCH (b)-[:dp_belongs_to]->(s:dp_card_common)
// 노드 key로 묶는다. ID 문자열만 같은 카드 혜택과 공통 혜택의 대상·제외 문구를 한 행으로 합치지 않는다.
RETURN b.key AS key, coalesce(b.card_bnft_id, b.card_common_bnft_id) AS id, collect(DISTINCT c.product_nm) AS cards,
       collect(DISTINCT t.target_nm) AS targets, collect(DISTINCT a.excl_raw_txt) AS exclusions, s.common_nm AS common_nm

// name: benefit_relations
// 명시적 조회 전용. 기존 후보 점수·답변 문맥에는 자동으로 포함하지 않는다.
MATCH (b:dp_card_bnft {key:$key})-[r:dp_related_to]->(target:dp_card_bnft)
RETURN b.key AS source_key, target.key AS target_key, target.card_bnft_id AS target_id,
       target.name AS target_name, r.relation_key AS relation_key, r.rel_type_cd AS rel_type_cd,
       r.rel_priority AS rel_priority, r.source_json AS source_json
ORDER BY relation_key, target_id

// name: benefit_context
MATCH (b:dp_node {key:$key})
WHERE b:dp_card_bnft OR b:dp_card_common_bnft OR b:dp_card_product_item
OPTIONAL MATCH (c:dp_card_product)-[:dp_has_benefit|dp_has_common_benefit|dp_has_item]->(b)
OPTIONAL MATCH (b)-[:dp_belongs_to]->(s:dp_card_common)
OPTIONAL MATCH (s)-[:dp_has_document]->(d:dp_card_doc)
WITH b, s, collect(DISTINCT c) AS cards, collect(DISTINCT d.doc_title) AS common_docs
// 검색 투영 속성(임베딩 1536차원 등)은 답변 문맥에 쓰지 않으므로 빼고 돌려준다. 기존 응답 계약(투영 전 속성)을 유지한다.
// 목록은 neo4j_dry_run.PROJECTION_PROPS와 같아야 한다(test_neo4j_search_projection이 대조).
RETURN properties(head(cards)) AS card,
       apoc.map.removeKeys(properties(b), ['embedding', 'embedding_dim', 'embedding_model', 'embedding_run_id', 'search_text',
                                           'brand_compare_status', 'brand_compare_issues', 'brand_compare_common_key']) AS benefit,
       [x IN cards | x.source_json] AS card_sources,
       CASE WHEN s IS NULL THEN null ELSE properties(s) END AS common, common_docs,
       labels(head(cards)) AS card_labels, labels(b) AS benefit_labels

// name: benefit_rules
MATCH (b:dp_card_bnft {key:$key})-[:dp_has_rule]->(r:dp_bnft_rule)
OPTIONAL MATCH (r)-[:dp_targets]->(t:dp_rule_target)
RETURN properties(r) AS rule, labels(r) AS labels, collect(DISTINCT t.target_nm) AS targets
ORDER BY rule.rule_key

// name: benefit_conditions
MATCH (c:dp_card_product)-[:dp_has_benefit]->(b:dp_card_bnft {key:$key})
OPTIONAL MATCH (b)-[:dp_has_rule]->(r:dp_bnft_rule)
WITH c,b,collect(DISTINCT r) AS rules
UNWIND [c,b] + rules AS owner
MATCH (owner)-[:dp_has_expr]->(x:dp_cond_expr)
      -[:dp_has_branch]->(branch:dp_cond_branch)
      -[:dp_has_atom]->(a:dp_cond_atom)
// owner_cd는 레이블 이름과 무관하다. 코드 순서 BNFT, CARD, RULE이 조건 표시 순서다.
RETURN CASE WHEN owner:dp_card_product THEN 'CARD' WHEN owner:dp_bnft_rule THEN 'RULE' ELSE 'BNFT' END AS owner_cd,
       owner.rule_key AS rule_key,
       properties(x) AS expression, branch.branch_no AS branch_no,
       properties(a) AS atom, labels(a) AS labels
ORDER BY owner_cd, rule_key, branch_no, a.atom_seq

// name: benefit_limits
// 한도는 혜택의 원문 TEXT다. 값이 없으면 행이 없고, 한도 없음이 아니라 미확인을 뜻한다.
MATCH (b:dp_node {key:$key})
WHERE (b:dp_card_bnft OR b:dp_card_common_bnft) AND b.limit_text IS NOT NULL
RETURN b.limit_text AS limit_text

// name: benefit_evidence
MATCH (card:dp_card_product)-[:dp_has_benefit]->(b:dp_card_bnft {key:$key})
OPTIONAL MATCH (b)-[:dp_has_rule]->(rule:dp_bnft_rule)
WITH card,b,collect(DISTINCT rule) AS rules
UNWIND [card,b] + rules AS owner
MATCH (owner)-[link:dp_supported_by]->(e:dp_card_source_evidence)
      -[:dp_in_chunk]->(chunk:dp_card_doc_chunk)
      -[:dp_on_page]->(page:dp_card_doc_page)
      -[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(owner) AS owner_labels, owner.rule_key AS rule_key,
       properties(link) AS link, properties(e) AS evidence,
       properties(chunk) AS chunk, properties(page) AS page, properties(doc) AS document
ORDER BY page.page_no, e.start_pos, e.evidence_id

// name: item_evidence
// 혜택이 아닌 카드 상품 항목(연회비 등)의 근거. 줄 단위 근거는 link.ev_item_cd='FEE_LINE', ev_item_key=줄 key다.
MATCH (card:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {key:$key})
      -[link:dp_supported_by]->(e:dp_card_source_evidence)
      -[:dp_in_chunk]->(chunk:dp_card_doc_chunk)
      -[:dp_on_page]->(page:dp_card_doc_page)
      -[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(i) AS owner_labels, null AS rule_key,
       properties(link) AS link, properties(e) AS evidence,
       properties(chunk) AS chunk, properties(page) AS page, properties(doc) AS document
ORDER BY page.page_no, e.start_pos, e.evidence_id

// name: common_benefit_evidence
// 공통 혜택에는 근거 직접 연결이 없다. 동일성 SAME으로 확인된 기존 행의 근거만 읽고, 없으면 0건이다.
MATCH (common:dp_card_common_bnft {key:$key})<-[:dp_same_as]-(b:dp_card_bnft)
      -[link:dp_supported_by]->(e:dp_card_source_evidence)
      -[:dp_in_chunk]->(chunk:dp_card_doc_chunk)
      -[:dp_on_page]->(page:dp_card_doc_page)
      -[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(b) AS owner_labels, null AS rule_key,
       properties(link) AS link, properties(e) AS evidence,
       properties(chunk) AS chunk, properties(page) AS page, properties(doc) AS document
ORDER BY page.page_no, e.start_pos, e.evidence_id

// name: hop1_card_benefits
// 1홉: 카드 → 혜택
MATCH path = (c:dp_card_product)-[:dp_has_benefit]->(b:dp_card_bnft)
WHERE c.product_nm CONTAINS $card_nm
RETURN c.product_nm AS card, b.name AS benefit, length(path) AS hops ORDER BY benefit

// name: hop2_card_rules
// 2홉: 카드 → 혜택 → 계산 규칙
MATCH path = (c:dp_card_product)-[:dp_has_benefit]->(b:dp_card_bnft)-[:dp_has_rule]->(r:dp_bnft_rule)
WHERE c.product_nm CONTAINS $card_nm
RETURN c.product_nm AS card, b.name AS benefit, r.rule_key AS rule_key, r.value_num AS value_num, length(path) AS hops
ORDER BY benefit, rule_key

// name: hop2_card_common
// 2홉: 카드 → 공통 혜택 → 공통서비스
MATCH path = (c:dp_card_product)-[:dp_has_common_benefit]->(b:dp_card_common_bnft)-[:dp_belongs_to]->(s:dp_card_common)
WHERE c.product_nm CONTAINS $card_nm
RETURN c.product_nm AS card, b.name AS benefit, s.common_nm AS common, s.brand_cd AS brand, s.service_grade_cd AS grade,
       b.bnft_valid_from AS valid_from, b.bnft_valid_to_excl AS valid_to_excl, length(path) AS hops

// name: hop3_card_targets
// 3홉: 카드 → 혜택 → 규칙 → 적용 대상
MATCH path = (c:dp_card_product)-[:dp_has_benefit]->(b:dp_card_bnft)-[:dp_has_rule]->(r:dp_bnft_rule)-[:dp_targets]->(t:dp_rule_target)
WHERE c.product_nm CONTAINS $card_nm
RETURN c.product_nm AS card, b.name AS benefit, r.rule_key AS rule_key, t.target_nm AS target, length(path) AS hops
ORDER BY benefit, rule_key, target

// name: hop3_common_docs
// 3홉: 카드 → 공통 혜택 → 공통서비스 → 원천 문서
MATCH path = (c:dp_card_product)-[:dp_has_common_benefit]->(b:dp_card_common_bnft)-[:dp_belongs_to]->(s:dp_card_common)
      -[:dp_has_document]->(d:dp_card_doc)
WHERE c.product_nm CONTAINS $card_nm
RETURN c.product_nm AS card, b.name AS benefit, s.common_nm AS common, d.doc_title AS document, d.card_doc_id AS doc_id, length(path) AS hops

// name: hop3_target_cards
// 3홉 역방향: 이용처 → 규칙 → 혜택 → 카드
MATCH path = (t:dp_rule_target)<-[:dp_targets]-(r:dp_bnft_rule)<-[:dp_has_rule]-(b:dp_card_bnft)<-[:dp_has_benefit]-(c:dp_card_product)
WHERE toLower(t.target_nm) CONTAINS toLower($target_nm)
RETURN t.target_nm AS target, b.name AS benefit, c.product_nm AS card, count(r) AS rules, length(path) AS hops
ORDER BY card, benefit
