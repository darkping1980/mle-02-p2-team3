import { PGlite } from '@electric-sql/pglite';
import { fileURLToPath } from 'node:url';
process.chdir(fileURLToPath(new URL('../../../../../', import.meta.url)));
import { readFileSync } from 'node:fs';
const root='src/card_benefit/sql/';
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
for(const file of ['db_pipeline_schemaV7_draft.sql','db_pipeline_common_code_seedV7.sql','db_pipeline_common_code_descV7.sql']) await fresh.exec(readFileSync(root+file,'utf8'));
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
await db.close();
