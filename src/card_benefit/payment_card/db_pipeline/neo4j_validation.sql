-- Read-only PostgreSQL source checks for the table-faithful dp_ rebuild.
-- The Python loader uses one REPEATABLE READ, READ ONLY transaction and SELECT *.

-- name: source_relations
SELECT table_name,table_type
FROM information_schema.tables
WHERE table_schema='db_pipeline'
ORDER BY table_type,table_name;

-- name: source_columns_and_nullability
SELECT table_name,column_name,ordinal_position,data_type,udt_name,is_nullable
FROM information_schema.columns
WHERE table_schema='db_pipeline'
ORDER BY table_name,ordinal_position;

-- name: source_primary_keys
SELECT tc.table_name,kcu.column_name,kcu.ordinal_position
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_catalog=kcu.constraint_catalog
 AND tc.constraint_schema=kcu.constraint_schema
 AND tc.constraint_name=kcu.constraint_name
 AND tc.table_name=kcu.table_name
WHERE tc.table_schema='db_pipeline' AND tc.constraint_type='PRIMARY KEY'
ORDER BY tc.table_name,kcu.ordinal_position;

-- name: source_foreign_keys
SELECT child.relname AS table_name,con.conname AS constraint_name,
       child_att.attname AS column_name,parent.relname AS ref_table,
       parent_att.attname AS ref_column,child_key.ord AS ordinal_position
FROM pg_constraint con
JOIN pg_class child ON child.oid=con.conrelid
JOIN pg_namespace child_ns ON child_ns.oid=child.relnamespace
JOIN pg_class parent ON parent.oid=con.confrelid
JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS child_key(attnum,ord) ON true
JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS parent_key(attnum,ord) ON parent_key.ord=child_key.ord
JOIN pg_attribute child_att ON child_att.attrelid=child.oid AND child_att.attnum=child_key.attnum
JOIN pg_attribute parent_att ON parent_att.attrelid=parent.oid AND parent_att.attnum=parent_key.attnum
WHERE child_ns.nspname='db_pipeline' AND con.contype='f'
ORDER BY child.relname,con.conname,child_key.ord;

-- name: source_row_counts
SELECT schemaname,tablename,n_live_tup::bigint AS estimated_rows
FROM pg_stat_user_tables
WHERE schemaname='db_pipeline'
ORDER BY tablename;

-- name: benefit_source_rows
SELECT card_id,card_product_item_id,item_type_cd,item_nm,item_rule_txt,item_limit_txt,
       item_search_txt,item_cond_expr,rule_list,relation_list,item_data,item_embedding
FROM db_pipeline.card_product_item
ORDER BY card_id,card_product_item_id;

-- name: common_benefit_source_rows
SELECT card_common_id,card_common_bnft_id,bnft_nm,bnft_rule_txt,bnft_limit_txt,bnft_embedding
FROM db_pipeline.card_common_bnft
ORDER BY card_common_id,card_common_bnft_id;

-- name: evidence_link_rows
SELECT * FROM db_pipeline.card_evidence_link
ORDER BY card_doc_id,page_no,card_doc_chunk_id,evidence_id,card_id,evidence_link_id;

-- name: common_evidence_source_lineage
SELECT b.card_common_id,b.card_common_bnft_id,b.bnft_nm,d.card_doc_id,
       s.card_extr_stg_id,e.evidence_id,e.page_no,e.card_doc_chunk_id,e.quote_txt
FROM db_pipeline.card_common_bnft b
JOIN db_pipeline.card_common_doc d ON d.card_common_id=b.card_common_id
JOIN db_pipeline.card_extr_stg s
  ON s.card_doc_id=d.card_doc_id
 AND s.stg_kind_cd='BENEFIT'
 AND s.stg_raw_item->>'bnft_nm'=b.bnft_nm
 AND s.stg_sql_check_cd IS NOT NULL
 AND s.stg_parent_card_extr_stg_id IS NULL
JOIN db_pipeline.card_source_evidence e ON e.card_extr_stg_id=s.card_extr_stg_id
ORDER BY b.card_common_id,b.card_common_bnft_id,e.page_no,e.evidence_id;
