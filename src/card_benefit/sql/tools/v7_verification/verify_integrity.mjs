import { PGlite } from '@electric-sql/pglite';
import { fileURLToPath } from 'node:url';
process.chdir(fileURLToPath(new URL('../../../../../', import.meta.url)));
import { readFileSync } from 'node:fs';
const root='src/card_benefit/sql/', db=new PGlite();
for(const f of ['db_pipeline_schemaV7_draft.sql','db_pipeline_common_code_seedV7.sql','db_pipeline_common_code_descV7.sql']) await db.exec(readFileSync(root+f,'utf8'));
await db.exec(readFileSync(root+'db_pipeline_v7_integrity_test.sql','utf8'));
console.log('V7 integrity SQL including rule pool gates: PASS');
await db.close();
