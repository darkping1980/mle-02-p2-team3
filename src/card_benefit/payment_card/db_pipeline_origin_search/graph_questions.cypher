// Queries for the table-faithful PostgreSQL -> Neo4j dp_ model.

// name: catalog
// 카드 상품(dp_card_product)-혜택 항목(dp_card_product_item) 관계를 따라 BENEFIT 항목만 카탈로그로 반환한다.
// 카드 원본, rule_list, item_cond_expr와 검색 텍스트를 함께 읽어 interpret 후보 설명에 사용한다.
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'BENEFIT'})
RETURN i.key AS key,i.item_nm AS name,i.card_product_item_id AS id,i.verification_status_cd AS status,
       p.source_json AS card_source,i.rule_list AS rule_list,i.item_cond_expr AS item_cond_expr,i.search_text AS search_text,
       i.item_rule_txt AS item_rule_txt,i.item_limit_txt AS item_limit_txt
ORDER BY name,key;

// name: item_catalog
// BENEFIT 이외의 카드 상품 항목(예: TERMS, ANNUAL_FEE)을 읽어 부가 카탈로그를 구성한다.
// dp_has_item 관계로 카드 소유 정보를 연결하고 item_data 등 원장 속성을 함께 반환한다.
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item)
WHERE i.item_type_cd <> 'BENEFIT'
RETURN i.key AS key,i.item_nm AS name,i.card_product_item_id AS id,i.verification_status_cd AS status,
       i.item_type_cd AS item_type,i.card_id AS card_id,i.source_json AS item_source,i.item_data AS item_data,
       i.item_rule_txt AS item_rule_txt,i.item_cd AS item_cd,p.source_json AS card_source
ORDER BY name,key;

// name: common_catalog
// 공통 혜택이 속한 공통 서비스와 적용 카드 목록을 읽는다.
// dp_applies_to는 선택적 관계이므로 아직 적용 카드 연결이 없는 혜택도 카탈로그에 남긴다.
MATCH (b:dp_card_common_bnft)-[:dp_belongs_to]->(s:dp_card_common)
OPTIONAL MATCH (b)-[:dp_applies_to]->(p:dp_card_product)
WITH b,s,collect(DISTINCT p.product_nm) AS cards
RETURN b.key AS key,b.bnft_nm AS name,b.card_common_bnft_id AS id,b.verification_status_cd AS status,
       s.common_nm AS common_nm,cards
ORDER BY name,key;

// name: item_evidence
// 카드 상품 항목 key를 기준으로 해당 항목의 PDF 근거와 문서 위치를 조회한다.
// dp_supported_by → dp_in_chunk → dp_on_page → dp_in_document 경로는 선택적 연결로 따라가며, 관계·원문·페이지 메타데이터를 분리 반환한다.
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {key:$key})
OPTIONAL MATCH (i)-[l:dp_supported_by]->(e:dp_card_source_evidence)
OPTIONAL MATCH (e)-[:dp_in_chunk]->(chunk:dp_card_doc_chunk)-[:dp_on_page]->(page:dp_card_doc_page)-[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(i) AS owner_labels,{key:i.key,card_product_item_id:i.card_product_item_id,item_nm:i.item_nm} AS owner,
       labels(e) AS evidence_labels,{ev_subject_cd:l.ev_subject_cd,source_table:l.source_table,
         ev_item_key:l.ev_item_key,ev_item_cd:l.ev_item_cd} AS link,l.rule_key AS rule_key,
       {key:e.key,evidence_id:e.evidence_id,page_no:e.page_no,quote_txt:e.quote_txt,approval_status_cd:e.approval_status_cd} AS evidence,
       CASE WHEN chunk IS NULL THEN null ELSE {chunk_id:chunk.card_doc_chunk_id,page_no:chunk.page_no} END AS chunk,
       CASE WHEN page IS NULL THEN null ELSE {page_no:page.page_no} END AS page,
       CASE WHEN doc IS NULL THEN null ELSE {card_doc_id:doc.card_doc_id,doc_title:doc.doc_title,doc_file_nm:doc.doc_file_nm,
         doc_source_url:doc.doc_source_url,doc_sha256:doc.doc_sha256} END AS document
ORDER BY e.page_no,e.evidence_id;

// name: list_benefits
// 혜택 이름 부분 문자열 검색을 카드 혜택과 공통 혜택 양쪽에 수행한다.
// UNION ALL 결과는 같은 반환 열 구조로 합치며, 공통 혜택은 dp_applies_to 카드도 함께 반환한다.
MATCH (b:dp_card_product_item)
WHERE b.item_type_cd='BENEFIT' AND toLower(coalesce(b.item_nm,'')) CONTAINS toLower($keyword)
OPTIONAL MATCH (p:dp_card_product)-[:dp_has_item]->(b)
RETURN b.key AS key,b.item_nm AS name,b.card_product_item_id AS id,b.verification_status_cd AS status,b.item_cd AS bnft_cd,
       b.item_subtype_cd AS bnft_type_cd,b.search_text AS search_text,b.item_origin_cd AS origin_cd,
       p.card_id AS card_id,p.product_nm AS product_nm,'CARD_BNFT' AS source
UNION ALL
MATCH (b:dp_card_common_bnft)
WHERE toLower(coalesce(b.bnft_nm,'')) CONTAINS toLower($keyword)
OPTIONAL MATCH (b)-[:dp_applies_to]->(p:dp_card_product)
RETURN b.key AS key,b.bnft_nm AS name,b.card_common_bnft_id AS id,b.verification_status_cd AS status,b.bnft_cd AS bnft_cd,
       b.bnft_type_cd AS bnft_type_cd,b.search_text AS search_text,'COMMON' AS origin_cd,
       p.card_id AS card_id,p.product_nm AS product_nm,'CARD_COMMON_BNFT' AS source
ORDER BY name,key;

// name: candidate_relations
// 검색 후보 ID를 실제 카드 소속 관계로 보강한다. 카드 상품 항목과 공통 혜택을 각각 조회한다.
// 현재 테이블 매핑 모델에서 대상·제외 별도 관계는 만들지 않았으므로 targets/exclusions는 빈 목록으로 반환한다.
MATCH (b:dp_card_product_item)
WHERE b.item_type_cd='BENEFIT' AND b.card_product_item_id IN $ids
OPTIONAL MATCH (p:dp_card_product)-[:dp_has_item]->(b)
RETURN b.key AS key,b.card_product_item_id AS id,collect(DISTINCT p.card_id) AS card_ids,
       [] AS targets,[] AS exclusions
UNION ALL
MATCH (b:dp_card_common_bnft)
WHERE b.card_common_bnft_id IN $ids
OPTIONAL MATCH (b)-[:dp_applies_to]->(p:dp_card_product)
RETURN b.key AS key,b.card_common_bnft_id AS id,collect(DISTINCT p.card_id) AS card_ids,
       [] AS targets,[] AS exclusions;

// name: benefit_relations
// 혜택 노드에 원장 그대로 투영된 relation_list와 item_data를 읽는다.
// 이 조회는 관계 확장 검색이 아니라 원본 연결 메타데이터 확인용이다.
MATCH (b:dp_card_product_item {key:$key})
RETURN b.key AS key,b.relation_list AS relation_list,b.item_data AS item_data;

// name: benefit_context
// key가 카드 혜택 항목 또는 공통 혜택 중 어느 쪽인지 확인하고 하나의 b로 정규화한다.
// 소유 카드·적용 카드·공통 서비스·추출 출처를 모은 뒤 답변에 필요한 각 노드 속성을 투영한다.
OPTIONAL MATCH (item:dp_card_product_item {key:$key})
OPTIONAL MATCH (common_benefit:dp_card_common_bnft {key:$key})
WITH coalesce(item,common_benefit) AS b
WHERE b IS NOT NULL
OPTIONAL MATCH (p:dp_card_product)-[:dp_has_item]->(b)
OPTIONAL MATCH (b)-[:dp_applies_to]->(applied:dp_card_product)
OPTIONAL MATCH (b)-[:dp_belongs_to]->(common:dp_card_common)
WITH b,collect(DISTINCT p) + collect(DISTINCT applied) AS cards,common
WITH b,[c IN cards WHERE c IS NOT NULL] AS cards,common
OPTIONAL MATCH (b)-[:dp_supported_by_extraction]->(stg:dp_card_extr_stg)
WITH b,cards,common,[x IN collect(DISTINCT stg.source_json) WHERE x IS NOT NULL] AS extraction_sources
RETURN head([c IN cards WHERE c:dp_card_product | {card_id:c.card_id,product_nm:c.product_nm,issuer:c.issuer}]) AS card,
       CASE WHEN b:dp_card_product_item THEN {
         key:b.key,card_product_item_id:b.card_product_item_id,card_id:b.card_id,item_type_cd:b.item_type_cd,
         item_nm:b.item_nm,item_cd:b.item_cd,item_subtype_cd:b.item_subtype_cd,verification_status_cd:b.verification_status_cd,
         item_rule_txt:b.item_rule_txt,item_limit_txt:b.item_limit_txt,item_data:b.item_data,rule_list:b.rule_list,
         item_cond_expr:b.item_cond_expr,relation_list:b.relation_list,search_text:b.search_text
       } ELSE {
         key:b.key,card_common_bnft_id:b.card_common_bnft_id,bnft_nm:b.bnft_nm,bnft_cd:b.bnft_cd,bnft_type_cd:b.bnft_type_cd,
         bnft_rule_txt:b.bnft_rule_txt,bnft_limit_txt:b.bnft_limit_txt,verification_status_cd:b.verification_status_cd,
         search_text:b.search_text
       } END AS benefit,
       [c IN cards WHERE c:dp_card_product | {product_nm:c.product_nm,card_id:c.card_id,issuer:c.issuer}] AS card_sources,
       CASE WHEN common IS NULL THEN null ELSE {common_nm:common.common_nm,brand_cd:common.brand_cd,
         service_grade_cd:common.service_grade_cd} END AS common,
       [] AS common_docs,labels(head([c IN cards WHERE c:dp_card_product | c])) AS card_labels,
       labels(b) AS benefit_labels,extraction_sources;

// name: benefit_evidence
// key를 가진 혜택 노드에서 dp_supported_by 관계를 통해 연결된 Evidence를 조회한다.
// Evidence에 문서 계층 관계를 선택적으로 연결하고, 소유 라벨·관계 속성·원문·페이지·청크·문서 정보를 반환한다.
MATCH (owner {key:$key})-[l:dp_supported_by]->(e:dp_card_source_evidence)
OPTIONAL MATCH (e)-[:dp_in_chunk]->(chunk:dp_card_doc_chunk)-[:dp_on_page]->(page:dp_card_doc_page)-[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(owner) AS owner_labels,null AS owner,labels(e) AS evidence_labels,
       l.rule_key AS rule_key,properties(l) AS link,
       {evidence_id:e.evidence_id,page_no:e.page_no,quote_txt:e.quote_txt,approval_status_cd:e.approval_status_cd,source_json:e.source_json} AS evidence,
       CASE WHEN chunk IS NULL THEN null ELSE {chunk_id:chunk.card_doc_chunk_id,page_no:chunk.page_no,source_json:chunk.source_json} END AS chunk,
       CASE WHEN page IS NULL THEN null ELSE {page_no:page.page_no,source_json:page.source_json} END AS page,
       CASE WHEN doc IS NULL THEN null ELSE {source_json:doc.source_json} END AS document
ORDER BY e.page_no,e.evidence_id;

// name: common_benefit_evidence
// 공통 혜택 노드만 대상으로 Evidence 관계를 조회한다.
// Evidence → 청크 → 페이지 → 문서 연결이 없더라도 원문 Evidence는 유지하도록 위치 경로는 OPTIONAL MATCH로 처리한다.
MATCH (owner:dp_card_common_bnft {key:$key})-[l:dp_supported_by]->(e:dp_card_source_evidence)
OPTIONAL MATCH (e)-[:dp_in_chunk]->(chunk:dp_card_doc_chunk)-[:dp_on_page]->(page:dp_card_doc_page)-[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(owner) AS owner_labels,null AS owner,labels(e) AS evidence_labels,
       null AS rule_key,{ev_subject_cd:l.ev_subject_cd,source_table:l.source_table,
         ev_item_key:l.ev_item_key,ev_item_cd:l.ev_item_cd} AS link,
       {key:e.key,evidence_id:e.evidence_id,page_no:e.page_no,quote_txt:e.quote_txt,approval_status_cd:e.approval_status_cd} AS evidence,
       CASE WHEN chunk IS NULL THEN null ELSE {chunk_id:chunk.card_doc_chunk_id,page_no:chunk.page_no} END AS chunk,
       CASE WHEN page IS NULL THEN null ELSE {page_no:page.page_no} END AS page,
       CASE WHEN doc IS NULL THEN null ELSE {card_doc_id:doc.card_doc_id,doc_title:doc.doc_title,doc_file_nm:doc.doc_file_nm,
         doc_source_url:doc.doc_source_url,doc_sha256:doc.doc_sha256} END AS document
ORDER BY e.page_no,e.evidence_id;

// name: hop1_card_benefits
// 평가용 1-hop 조회: 지정 카드 ID에서 dp_has_item으로 연결된 혜택과 규칙·한도 텍스트를 반환한다.
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'BENEFIT'})
WHERE p.card_id IN $card_ids
RETURN p.product_nm AS card,i.item_nm AS benefit,i.key AS key,i.item_rule_txt AS rule_text,i.item_limit_txt AS limit_text
ORDER BY card,benefit;

// name: hop2_card_rules
// 평가용 카드→혜택 2-hop 문맥: 혜택의 rule_list와 item_cond_expr를 원장 JSON 형태로 반환한다.
// 규칙·조건을 별도 RULE/COND 노드로 탐색하지 않고 혜택 항목 속성에서 읽는다.
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'BENEFIT'})
WHERE p.card_id IN $card_ids
RETURN p.product_nm AS card,i.item_nm AS benefit,i.rule_list AS rule_list,i.item_cond_expr AS condition_json,
       i.item_rule_txt AS rule_text,i.item_limit_txt AS limit_text
ORDER BY card,benefit;

// name: hop2_card_common
// 평가용 공통 혜택 조회: 공통 혜택과 dp_applies_to 관계를 따라 지정 카드에 적용되는 항목을 찾는다.
MATCH (b:dp_card_common_bnft)-[:dp_applies_to]->(p:dp_card_product)
WHERE p.card_id IN $card_ids
RETURN p.product_nm AS card,b.bnft_nm AS benefit,b.key AS key,b.bnft_rule_txt AS rule_text,b.bnft_limit_txt AS limit_text
ORDER BY card,benefit;

// name: hop3_card_targets
// 평가·검토용 조회: 지정 카드 혜택의 적용 대상 목록과 item_data를 반환한다.
// 대상은 각 규칙의 target_list JSON에 남아 있으며 별도 target 노드로 분해하지 않는다.
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'BENEFIT'})
WHERE p.card_id IN $card_ids
RETURN p.product_nm AS card,i.item_nm AS benefit,i.rule_list AS rule_list,i.item_data AS item_data
ORDER BY card,benefit;

// name: hop3_common_docs
// 평가·검토용 조회: 공통 서비스에서 dp_has_document 관계로 연결된 문서를 찾는다.
MATCH (c:dp_card_common)-[:dp_has_document]->(d:dp_card_doc)
RETURN c.common_nm AS common,d.doc_title AS document,d.card_doc_id AS document_id
ORDER BY common,document;

// name: hop3_target_cards
// 평가·검토용 역방향 조회: 공통 혜택의 dp_applies_to 관계로 적용 카드 목록을 확인한다.
MATCH (b:dp_card_common_bnft)-[:dp_applies_to]->(p:dp_card_product)
RETURN b.bnft_nm AS benefit,p.product_nm AS card,p.card_id AS card_id
ORDER BY benefit,card;
