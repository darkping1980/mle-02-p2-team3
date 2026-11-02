import { PGlite } from '@electric-sql/pglite';
import { fileURLToPath } from 'node:url';
process.chdir(fileURLToPath(new URL('../../../../../', import.meta.url)));
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
const root='src/card_benefit/sql/';
// V6 -> V7 이관 파일은 TEXT 단순화 직전 V7에서 멈춘다. 그 시점 DDL과 비교하고, 끝에서 단순화까지 이어서 시험한다.
const BASE='bdb94bc';
const baseDdl=spawnSync('git',['show',`${BASE}:src/card_benefit/sql/db_pipeline_schemaV7_draft.sql`],{encoding:'utf8',maxBuffer:1<<26});
if(baseDdl.status!==0) throw Error(baseDdl.stderr);
const db=new PGlite();
for(const file of ['db_pipeline_schemaV6_draft.sql','db_pipeline_common_code_seedV6.sql','db_pipeline_common_code_descV6.sql']) await db.exec(readFileSync(root+file,'utf8'));
await db.exec(`DROP INDEX db_pipeline.card_product_doc_current_idx;
ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT card_product_doc_period_check;
ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT card_product_doc_approved_check;
ALTER TABLE db_pipeline.card_product_doc DROP COLUMN effective_from;
ALTER TABLE db_pipeline.card_product_doc DROP COLUMN effective_to_excl;`);
await db.exec(`INSERT INTO db_pipeline.card_product(card_id,product_cd,product_nm,issuer,card_kind_cd,create_user_id,update_user_id) VALUES(91,'T','test','issuer','CREDIT','T','T');
INSERT INTO db_pipeline.card_policy_version(card_id,policy_ver_id,policy_ver_no,valid_from,policy_status_cd) VALUES(91,'V1',1,'2026-01-01','DRAFT');
INSERT INTO db_pipeline.card_limit_pool(card_id,policy_ver_id,pool_id,pool_scope_cd,period_cd,cap_unit_cd,aggregation_key_cd,tier_list)
VALUES(91,'V1','P1','BENEFIT','MONTH','COUNT','CARD_MEMBER','[{"tier_key":"T","predicate_state_cd":"PENDING_REVIEW","limit_num":1}]');`);
const rule=(key,refs)=>({rule_key:key,calc_method_cd:'FREE_SERVICE',payout_unit_cd:'SERVICE',rule_status_cd:'DRAFT',method_ver:1,predicate_state_cd:'PENDING_REVIEW',target_list:[],pool_refs:refs});
const original=[rule('R2',[{pool_id:'P1',pool_role_cd:'SHARED'}]),rule('R1',[{pool_id:'P1',pool_role_cd:'CONSUME'}])];
await db.query(`INSERT INTO db_pipeline.card_bnft(card_id,policy_ver_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,rule_list,verification_status_cd) VALUES(91,'V1','B1','B1','benefit','SERVICE','LOCAL','PRODUCT',$1,'PENDING_REVIEW')`,[JSON.stringify(original)]);
await db.exec(readFileSync(root+'db_pipeline_migration_V6_to_V7.sql','utf8'));
const fresh=new PGlite();
await fresh.exec(baseDdl.stdout);
for(const file of ['db_pipeline_common_code_seedV7.sql','db_pipeline_common_code_descV7.sql']) await fresh.exec(readFileSync(root+file,'utf8'));
const catalogQueries={
 columns:`select table_name,column_name,data_type,character_maximum_length,is_nullable,column_default from information_schema.columns where table_schema='db_pipeline' order by 1,2`,
 constraints:`select c.relname,con.conname,contype::text,pg_get_constraintdef(con.oid) def from pg_constraint con join pg_class c on c.oid=con.conrelid where con.connamespace='db_pipeline'::regnamespace order by 1,2`,
 indexes:`select tablename,indexname,indexdef from pg_indexes where schemaname='db_pipeline' order by 1,2`,
 views:`select viewname,definition from pg_views where schemaname='db_pipeline' order by 1`,
 functions:`select proname,pg_get_function_identity_arguments(oid) args,prosrc from pg_proc where pronamespace='db_pipeline'::regnamespace order by 1,2`,
 sequences:`select relname from pg_class where relnamespace='db_pipeline'::regnamespace and relkind='S' order by 1`,
};
for(const [name,query] of Object.entries(catalogQueries)) {
 const left=(await db.query(query)).rows, right=(await fresh.query(query)).rows;
 if(JSON.stringify(left)!==JSON.stringify(right)) {
   const changes=left.filter((x,i)=>JSON.stringify(x)!==JSON.stringify(right[i])).map(x=>x.proname||x.table_name||x.viewname||x.relname||x.indexname);
   if(name==='functions') {const a=left.find(x=>x.proname==='fn_valid_rule_list').prosrc.split('\n');const b=right.find(x=>x.proname==='fn_valid_rule_list').prosrc.split('\n'); console.log('source delta',a.filter((x,i)=>x!==b[i]).slice(0,8),b.filter((x,i)=>x!==a[i]).slice(0,8));}
   throw Error('fresh/migrated catalog differs: '+name+' '+JSON.stringify(changes));
 }
}
await fresh.close();
console.log('fresh V7 vs migrated catalog: PASS');
const rel=(await db.query('select * from db_pipeline.card_bnft_rule_pool order by rule_key')).rows;
if(rel.length!==2) throw Error('V6->V7 lost refs');
await db.exec(readFileSync(root+'db_pipeline_migration_V7_to_V6_rollback.sql','utf8'));
const same=(await db.query("select rule_list=$1::jsonb AS ok from db_pipeline.card_bnft where card_id=91 and card_bnft_id='B1'",[JSON.stringify(original)])).rows[0].ok;
if(!same) throw Error('V6 rollback differs');
await db.exec(readFileSync(root+'db_pipeline_migration_V6_to_V7.sql','utf8'));
if((await db.query('select count(*)::int n from db_pipeline.card_bnft_rule_pool')).rows[0].n!==2) throw Error('re-migration');
console.log('isolated V6 -> revised V7 -> V6 exact JSON restore -> revised V7: PASS');
// V7 이후 TEXT 단순화까지 이어서 적용하면 최종 DDL과 같아야 하고, 복구하면 V6 복구 경로로 돌아갈 수 있어야 한다.
await db.exec(`ALTER TABLE db_pipeline.card_bnft ADD COLUMN bnft_rule_txt text; ALTER TABLE db_pipeline.card_bnft ADD COLUMN bnft_limit_txt text;
UPDATE db_pipeline.card_limit_pool SET tier_list='[{"tier_key":"T","predicate_state_cd":"PENDING_REVIEW","limit_num":1}]';
UPDATE db_pipeline.card_bnft SET bnft_rule_txt='무료', bnft_limit_txt='월 1회';
INSERT INTO db_pipeline.card_doc(card_doc_id,doc_cd,doc_title,doc_file_nm,doc_sha256,doc_collect_date,create_user_id,update_user_id) VALUES('D1','D1','t','x.pdf',repeat('a',64),now(),'T','T');
INSERT INTO db_pipeline.card_product_doc(card_id,card_doc_id,doc_role_cd,applicability_basis_txt,create_user_id,update_user_id) VALUES(91,'D1','PRODUCT_GUIDE','x','T','T');
INSERT INTO db_pipeline.card_doc_chunk(card_doc_id,page_no,card_doc_chunk_id,chunk_seq,chunk_start_pos,chunk_end_pos,chunk_raw_txt,chunk_split_rule_ver,create_user_id,update_user_id) VALUES('D1',1,'C1',1,1,8,'무료 월 1회','V','T','T');
INSERT INTO db_pipeline.card_source_evidence(evidence_id,card_doc_id,page_no,card_doc_chunk_id,quote_txt,approval_status_cd) VALUES('E1','D1',1,'C1','무료 월 1회','PENDING');
INSERT INTO db_pipeline.card_evidence_link(card_id,ev_link_id,ev_subject_cd,card_bnft_id,evidence_id) VALUES(91,'L1','BNFT','B1','E1');
INSERT INTO db_pipeline.card_evidence_link(card_id,ev_link_id,ev_subject_cd,pool_id,evidence_id) VALUES(91,'L2','POOL','P1','E1');
CREATE SCHEMA db_pipeline_backup;
CREATE TABLE db_pipeline_backup.card_limit_pool_20261102 AS SELECT * FROM db_pipeline.card_limit_pool;
CREATE TABLE db_pipeline_backup.card_bnft_rule_pool_20261102 AS SELECT * FROM db_pipeline.card_bnft_rule_pool;
CREATE TABLE db_pipeline_backup.card_evidence_link_pre_simplify_20261102 AS SELECT * FROM db_pipeline.card_evidence_link;
CREATE TABLE db_pipeline_backup.card_bnft_pre_simplify_20261102 AS SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline.card_bnft;`);
await db.exec(readFileSync(root+'db_pipeline_migration_v7_bnft_text.sql','utf8'));
const finalDb=new PGlite();
for(const file of ['db_pipeline_schemaV7_draft.sql','db_pipeline_common_code_seedV7.sql','db_pipeline_common_code_descV7.sql']) await finalDb.exec(readFileSync(root+file,'utf8'));
for(const [name,query] of Object.entries(catalogQueries)) {
 const left=(await db.query(query)).rows, right=(await finalDb.query(query)).rows;
 if(JSON.stringify(left)!==JSON.stringify(right)) throw Error('final catalog differs: '+name);
}
await finalDb.close();
await db.exec(readFileSync(root+'db_pipeline_migration_v7_bnft_text_rollback.sql','utf8'));
console.log('isolated V6 -> V7 -> TEXT simplify equals final DDL, then TEXT rollback: PASS');
await db.close();
