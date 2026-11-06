// Read-only validation queries for the PostgreSQL-row dp_ model.

// Node counts by source table
MATCH (n:dp_node)
UNWIND labels(n) AS label
WITH label,count(*) AS rows
WHERE label STARTS WITH 'dp_' AND label <> 'dp_node'
RETURN label,rows ORDER BY label;

// Relationship counts by source table and mapped relationship
MATCH (:dp_node)-[r]->(:dp_node)
WHERE type(r) STARTS WITH 'dp_'
RETURN type(r) AS relationship,r.source_table AS source_table,count(*) AS rows
ORDER BY source_table,relationship;

// Nodes carrying original PostgreSQL row snapshots
MATCH (n:dp_node)
WHERE n.source_table IS NULL OR n.source_json IS NULL OR n.null_columns_json IS NULL
RETURN n.key AS key,labels(n) AS labels,n.source_table AS source_table LIMIT 100;

// Project graph must not connect to nodes outside dp_
MATCH (n)-[r]-(m)
WHERE any(label IN labels(n) WHERE label STARTS WITH 'dp_')
  AND none(label IN labels(m) WHERE label STARTS WITH 'dp_')
RETURN count(r) AS external_relationships;

// Benefit rows remain table-faithful; old decomposed rule labels are absent
MATCH (n)
WHERE any(label IN labels(n) WHERE label IN
  ['dp_card_bnft','dp_bnft_rule','dp_cond_expr','dp_cond_branch','dp_cond_atom','dp_rule_target'])
RETURN labels(n) AS labels,count(*) AS rows;

// PDF evidence directly resolves to chunk, page and document
MATCH (e:dp_card_source_evidence)-[:dp_in_chunk]->(c:dp_card_doc_chunk)
      -[:dp_on_page]->(p:dp_card_doc_page)-[:dp_in_document]->(d:dp_card_doc)
RETURN e.evidence_id AS evidence_id,e.card_doc_id AS document_id,
       e.page_no AS page_no,c.card_doc_chunk_id AS chunk_id,d.doc_title AS title
ORDER BY document_id,page_no,evidence_id LIMIT 100;

// Evidence-to-extraction ownership, and the staging source used for explicit tier keys
MATCH (owner)-[:dp_supported_by_extraction]->(stg:dp_card_extr_stg)
WHERE owner:dp_card_product_item OR owner:dp_card_common_bnft
RETURN labels(owner) AS owner_labels,owner.key AS owner_key,stg.card_extr_stg_id AS extraction_id,
       stg.stg_sql_check_cd AS review_status,stg.stg_raw_item AS original_extraction
ORDER BY extraction_id LIMIT 50;

// Embedding dimensionality present on source-aligned benefits
MATCH (b:dp_card_product_item {item_type_cd:'BENEFIT'})
WHERE b.embedding IS NOT NULL
RETURN count(b) AS embedded_benefits,min(size(b.embedding)) AS min_dimensions,
       max(size(b.embedding)) AS max_dimensions;
