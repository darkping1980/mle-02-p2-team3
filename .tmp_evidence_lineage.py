import json, os
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
load_dotenv(".env")
ids=[f"20261105_{i:06d}" for i in range(2740,2746)]
with psycopg.connect(os.environ["DB_URL"],connect_timeout=10) as conn, conn.cursor(row_factory=dict_row) as cur:
    cur.execute("""SELECT l.card_id,l.card_product_item_id,l.ev_subject_cd,l.rule_key,l.relation_key,l.ev_item_cd,l.ev_item_key,
                         l.evidence_id,l.card_doc_id,l.page_no,l.card_doc_chunk_id
                  FROM db_pipeline.card_evidence_link l
                  WHERE l.card_id=23 AND l.card_product_item_id='20261105_000100' AND l.evidence_id=ANY(%s)
                  ORDER BY l.evidence_id,l.ev_subject_cd,l.rule_key""",(ids,))
    links=cur.fetchall()
    cur.execute("""SELECT e.evidence_id,e.card_doc_id,e.page_no,e.card_doc_chunk_id,e.card_extr_stg_id,e.quote_txt,
                         s.stg_kind_cd,s.stg_raw_item->>'bnft_nm' AS staged_benefit_name,
                         s.stg_sql_check_cd,s.stg_parent_card_extr_stg_id
                  FROM db_pipeline.card_source_evidence e
                  LEFT JOIN db_pipeline.card_extr_stg s ON s.card_extr_stg_id=e.card_extr_stg_id
                  WHERE e.evidence_id=ANY(%s) ORDER BY e.evidence_id""",(ids,))
    evidence=cur.fetchall()
    cur.execute("SELECT card_product_item_id,item_nm,item_cond_expr,rule_list,item_data,item_limit_txt FROM db_pipeline.card_product_item WHERE card_id=23 AND card_product_item_id='20261105_000100'")
    benefit=cur.fetchone()
    print(json.dumps({"links":links,"evidence":evidence,"benefit":{k:benefit[k] for k in ("card_product_item_id","item_nm","item_limit_txt")}},ensure_ascii=True,default=str,indent=2))
