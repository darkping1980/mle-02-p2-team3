// Queries for the table-faithful PostgreSQL -> Neo4j dp_ model.

// name: catalog
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'BENEFIT'})
RETURN i.key AS key,i.item_nm AS name,i.card_product_item_id AS id,i.verification_status_cd AS status,
       p.source_json AS card_source,[] AS targets,[] AS payment_min_amounts
ORDER BY name,key;

// name: item_catalog
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item)
WHERE i.item_type_cd <> 'BENEFIT'
RETURN i.key AS key,i.item_nm AS name,i.card_product_item_id AS id,i.verification_status_cd AS status,
       i.item_type_cd AS item_type,i.source_json AS item_source,p.source_json AS card_source
ORDER BY name,key;

// name: common_catalog
MATCH (b:dp_card_common_bnft)-[:dp_belongs_to]->(s:dp_card_common)
OPTIONAL MATCH (b)-[:dp_applies_to]->(p:dp_card_product)
WITH b,s,collect(DISTINCT p.product_nm) AS cards
RETURN b.key AS key,b.bnft_nm AS name,b.card_common_bnft_id AS id,b.verification_status_cd AS status,
       s.common_nm AS common_nm,cards
ORDER BY name,key;

// name: item_evidence
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {key:$key})
OPTIONAL MATCH (i)-[l:dp_supported_by]->(e:dp_card_source_evidence)
OPTIONAL MATCH (e)-[:dp_in_chunk]->(chunk:dp_card_doc_chunk)-[:dp_on_page]->(page:dp_card_doc_page)-[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(i) AS owner_labels,properties(i) AS owner,labels(e) AS evidence_labels,properties(l) AS link,
       properties(e) AS evidence,properties(chunk) AS chunk,properties(page) AS page,properties(doc) AS document
ORDER BY e.page_no,e.evidence_id;

// name: list_benefits
MATCH (b:dp_card_product_item)
WHERE b.item_type_cd='BENEFIT' AND toLower(coalesce(b.item_nm,'')) CONTAINS toLower($keyword)
OPTIONAL MATCH (p:dp_card_product)-[:dp_has_item]->(b)
RETURN b.key AS key,b.item_nm AS name,b.card_product_item_id AS id,b.item_cd AS bnft_cd,
       b.item_subtype_cd AS bnft_type_cd,b.search_text AS search_text,b.item_origin_cd AS origin_cd,
       p.card_id AS card_id,p.product_nm AS product_nm,'CARD_BNFT' AS source
UNION ALL
MATCH (b:dp_card_common_bnft)
WHERE toLower(coalesce(b.bnft_nm,'')) CONTAINS toLower($keyword)
OPTIONAL MATCH (b)-[:dp_applies_to]->(p:dp_card_product)
RETURN b.key AS key,b.bnft_nm AS name,b.card_common_bnft_id AS id,b.bnft_cd AS bnft_cd,
       b.bnft_type_cd AS bnft_type_cd,b.search_text AS search_text,'COMMON' AS origin_cd,
       p.card_id AS card_id,p.product_nm AS product_nm,'CARD_COMMON_BNFT' AS source
ORDER BY name,key;

// name: candidate_relations
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
MATCH (b:dp_card_product_item {key:$key})
RETURN b.key AS key,b.relation_list AS relation_list,b.item_data AS item_data;

// name: benefit_context
MATCH (b)
WHERE b.key=$key AND (b:dp_card_product_item OR b:dp_card_common_bnft)
OPTIONAL MATCH (p:dp_card_product)-[:dp_has_item]->(b)
OPTIONAL MATCH (b)-[:dp_applies_to]->(applied:dp_card_product)
OPTIONAL MATCH (b)-[:dp_belongs_to]->(common:dp_card_common)
WITH b,collect(DISTINCT p) + collect(DISTINCT applied) AS cards,common
WITH b,[c IN cards WHERE c IS NOT NULL] AS cards,common
OPTIONAL MATCH (b)-[:dp_supported_by_extraction]->(stg:dp_card_extr_stg)
WITH b,cards,common,[x IN collect(DISTINCT stg.source_json) WHERE x IS NOT NULL] AS extraction_sources
RETURN head([c IN cards WHERE c:dp_card_product | properties(c)]) AS card,
       properties(b) AS benefit,
       [c IN cards WHERE c:dp_card_product | c.source_json] AS card_sources,
       CASE WHEN common IS NULL THEN null ELSE properties(common) END AS common,
       [] AS common_docs,labels(head([c IN cards WHERE c:dp_card_product | c])) AS card_labels,
       labels(b) AS benefit_labels,extraction_sources;

// name: benefit_rules
// Rule lists remain JSON on card_product_item; no rule nodes are created.
MATCH (b:dp_card_product_item {key:$key})
RETURN [] AS rule,[] AS labels,[] AS targets LIMIT 0;

// name: benefit_conditions
// Condition expressions remain JSON on their PostgreSQL owner row.
MATCH (b:dp_card_product_item {key:$key})
RETURN null AS owner_cd,null AS rule_key,null AS expression,null AS branch_no,null AS atom,[] AS labels LIMIT 0;

// name: benefit_limits
MATCH (b)
WHERE b.key=$key AND (b:dp_card_product_item OR b:dp_card_common_bnft)
RETURN coalesce(b.item_limit_txt,b.bnft_limit_txt) AS limit_text;

// name: benefit_evidence
MATCH (owner {key:$key})-[l:dp_supported_by]->(e:dp_card_source_evidence)
OPTIONAL MATCH (e)-[:dp_in_chunk]->(chunk:dp_card_doc_chunk)-[:dp_on_page]->(page:dp_card_doc_page)-[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(owner) AS owner_labels,properties(owner) AS owner,labels(e) AS evidence_labels,
       l.rule_key AS rule_key,properties(l) AS link,properties(e) AS evidence,
       properties(chunk) AS chunk,properties(page) AS page,properties(doc) AS document
ORDER BY e.page_no,e.evidence_id;

// name: common_benefit_evidence
MATCH (owner:dp_card_common_bnft {key:$key})-[l:dp_supported_by]->(e:dp_card_source_evidence)
OPTIONAL MATCH (e)-[:dp_in_chunk]->(chunk:dp_card_doc_chunk)-[:dp_on_page]->(page:dp_card_doc_page)-[:dp_in_document]->(doc:dp_card_doc)
RETURN labels(owner) AS owner_labels,properties(owner) AS owner,labels(e) AS evidence_labels,
       null AS rule_key,properties(l) AS link,properties(e) AS evidence,
       properties(chunk) AS chunk,properties(page) AS page,properties(doc) AS document
ORDER BY e.page_no,e.evidence_id;

// name: hop1_card_benefits
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'BENEFIT'})
WHERE p.card_id IN $card_ids
RETURN p.product_nm AS card,i.item_nm AS benefit,i.key AS key,i.item_rule_txt AS rule_text,i.item_limit_txt AS limit_text
ORDER BY card,benefit;

// name: hop2_card_rules
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'BENEFIT'})
WHERE p.card_id IN $card_ids
RETURN p.product_nm AS card,i.item_nm AS benefit,i.rule_list AS rule_list,i.item_cond_expr AS condition_json,
       i.item_rule_txt AS rule_text,i.item_limit_txt AS limit_text
ORDER BY card,benefit;

// name: hop2_card_common
MATCH (b:dp_card_common_bnft)-[:dp_applies_to]->(p:dp_card_product)
WHERE p.card_id IN $card_ids
RETURN p.product_nm AS card,b.bnft_nm AS benefit,b.key AS key,b.bnft_rule_txt AS rule_text,b.bnft_limit_txt AS limit_text
ORDER BY card,benefit;

// name: hop3_card_targets
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'BENEFIT'})
WHERE p.card_id IN $card_ids
RETURN p.product_nm AS card,i.item_nm AS benefit,i.rule_list AS rule_list,i.item_data AS item_data
ORDER BY card,benefit;

// name: hop3_common_docs
MATCH (c:dp_card_common)-[:dp_has_document]->(d:dp_card_doc)
RETURN c.common_nm AS common,d.doc_title AS document,d.card_doc_id AS document_id
ORDER BY common,document;

// name: hop3_target_cards
MATCH (b:dp_card_common_bnft)-[:dp_applies_to]->(p:dp_card_product)
RETURN b.bnft_nm AS benefit,p.product_nm AS card,p.card_id AS card_id
ORDER BY benefit,card;
