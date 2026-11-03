"""db_pipeline 스키마 전체(정의·데이터)를 읽기 전용으로 백업하고, 백업 파일을 실DB와 행 단위로 대조한다.

사용법(프로젝트 루트 어디서든):
    python src/card_benefit/docs/schema_cleanup/tools/backup_db_pipeline.py            # 백업 + 대조
    python src/card_benefit/docs/schema_cleanup/tools/backup_db_pipeline.py --verify DIR  # 기존 백업 대조만

결과: src/data/backup/pre_calc_cleanup_<YYYYMMDD_HHMMSS>/ (Git 제외)
    postgres_db_pipeline.json   테이블별 컬럼·행, 시퀀스, 지문(건수·md5)
    catalog.json                컬럼·제약·인덱스·뷰·함수·시퀀스·트리거·주석·소유자·권한
    schema_ddl.sql              catalog.json으로 만든 재생성 DDL(읽기용·복구용)
    restore_stg_normalized_item.sql  정제본 값 복구(컬럼 복구 후 실행)
접속 정보는 출력하지 않는다. 모든 조회는 READ ONLY 트랜잭션에서 실행한다.
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

sys.stdout.reconfigure(encoding="utf-8")
PROJECT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
BACKUP_ROOT = PROJECT / "src" / "data" / "backup"
SCHEMA = "db_pipeline"


def connect():
    load_dotenv(PROJECT / ".env")
    conn = psycopg.connect(os.environ["DB_URL"], connect_timeout=15, row_factory=dict_row)
    conn.read_only = True
    conn.execute("SET statement_timeout = '120s'")
    return conn


def q(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def fingerprint_sql(table, cols):
    row = f"row({', '.join(cols)})::text"
    return f"SELECT count(*)::int AS n, md5(coalesce(string_agg(md5({row}), ',' ORDER BY md5({row}) COLLATE \"C\"), '')) AS f FROM {SCHEMA}.{table}"


STG_FP = (f"SELECT count(*)::int AS n, md5(coalesce(string_agg(card_extr_stg_id || ':' || stg_normalized_item::text, ',' "
          f"ORDER BY card_extr_stg_id COLLATE \"C\"), '')) AS f FROM {SCHEMA}.card_extr_stg WHERE stg_normalized_item IS NOT NULL")


def catalog(cur):
    c = {}
    c["tables"] = [r["relname"] for r in q(cur, "SELECT relname FROM pg_class WHERE relnamespace=%s::regnamespace AND relkind='r' ORDER BY 1", (SCHEMA,))]
    c["columns"] = q(cur, """SELECT c.relname AS table, a.attnum AS pos, a.attname AS col, format_type(a.atttypid, a.atttypmod) AS type,
                                    a.attnotnull AS notnull, pg_get_expr(d.adbin, d.adrelid) AS default, col_description(c.oid, a.attnum) AS comment
                             FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
                             LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
                             WHERE c.relnamespace=%s::regnamespace AND c.relkind IN ('r','v') ORDER BY 1,2""", (SCHEMA,))
    c["constraints"] = q(cur, """SELECT conrelid::regclass::text AS table, conname AS name, contype::text AS type, pg_get_constraintdef(oid) AS def
                                 FROM pg_constraint WHERE connamespace=%s::regnamespace AND conrelid<>0 ORDER BY 1, contype<>'p', 2""", (SCHEMA,))
    c["indexes"] = q(cur, """SELECT i.tablename AS table, i.indexname AS name, i.indexdef AS def,
                                    EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid=(quote_ident(i.schemaname)||'.'||quote_ident(i.indexname))::regclass) AS by_constraint
                             FROM pg_indexes i WHERE schemaname=%s ORDER BY 1,2""", (SCHEMA,))
    c["views"] = q(cur, """SELECT c.relname AS name, pg_get_viewdef(c.oid) AS def, obj_description(c.oid,'pg_class') AS comment, pg_get_userbyid(c.relowner) AS owner
                           FROM pg_class c WHERE relnamespace=%s::regnamespace AND relkind='v' ORDER BY 1""", (SCHEMA,))
    # 뷰 의존 순서(다른 뷰에 의존하지 않는 것부터)
    deps = q(cur, """SELECT DISTINCT v.relname AS view, r.relname AS ref FROM pg_depend d JOIN pg_rewrite w ON w.oid=d.objid
                     JOIN pg_class v ON v.oid=w.ev_class JOIN pg_class r ON r.oid=d.refobjid
                     WHERE v.relnamespace=%s::regnamespace AND v.relkind='v' AND r.relkind='v' AND r.oid<>v.oid""", (SCHEMA,))
    order, pending = [], [v["name"] for v in c["views"]]
    while pending:
        ready = [v for v in pending if all(d["ref"] in order for d in deps if d["view"] == v)]
        if not ready:
            raise SystemExit("뷰 의존 순서를 정할 수 없음")
        order += ready
        pending = [v for v in pending if v not in ready]
    c["view_order"] = order
    c["functions"] = q(cur, """SELECT p.proname AS name, pg_get_function_identity_arguments(p.oid) AS args, pg_get_functiondef(p.oid) AS def,
                                      obj_description(p.oid,'pg_proc') AS comment, pg_get_userbyid(p.proowner) AS owner
                               FROM pg_proc p WHERE pronamespace=%s::regnamespace ORDER BY 1,2""", (SCHEMA,))
    c["sequences"] = q(cur, """SELECT sequencename AS name, data_type::text AS type, start_value, min_value, max_value, increment_by, cycle, cache_size, last_value
                               FROM pg_sequences WHERE schemaname=%s ORDER BY 1""", (SCHEMA,))
    c["triggers"] = q(cur, """SELECT tgrelid::regclass::text AS table, tgname AS name, pg_get_triggerdef(oid) AS def FROM pg_trigger
                              WHERE NOT tgisinternal AND tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace=%s::regnamespace) ORDER BY 1,2""", (SCHEMA,))
    c["table_meta"] = q(cur, """SELECT c.relname AS name, obj_description(c.oid,'pg_class') AS comment, pg_get_userbyid(c.relowner) AS owner, c.relacl::text AS acl
                                FROM pg_class c WHERE relnamespace=%s::regnamespace AND relkind IN ('r','v','S') ORDER BY 1""", (SCHEMA,))
    c["sequence_comments"] = q(cur, """SELECT c.relname AS name, obj_description(c.oid,'pg_class') AS comment FROM pg_class c
                                       WHERE relnamespace=%s::regnamespace AND relkind='S' ORDER BY 1""", (SCHEMA,))
    c["extensions"] = q(cur, "SELECT extname, extversion, extnamespace::regnamespace::text AS schema FROM pg_extension ORDER BY 1")
    return c


def lit(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def ddl(c):
    out = [f"-- db_pipeline 재생성 DDL (실DB 카탈로그에서 생성). 데이터는 postgres_db_pipeline.json", f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};", ""]
    for s in c["sequences"]:
        out.append(f"CREATE SEQUENCE {SCHEMA}.{s['name']} AS {s['type']} START {s['start_value']} INCREMENT {s['increment_by']} "
                   f"MINVALUE {s['min_value']} MAXVALUE {s['max_value']} CACHE {s['cache_size']}{' CYCLE' if s['cycle'] else ''};")
    fns = [f for f in c["functions"]]
    # 함수는 테이블 기본값·CHECK에서 쓰이므로 테이블보다 먼저 만든다
    for f in fns:
        out.append(f["def"].rstrip() + ";")
    for t in c["tables"]:
        cols = [x for x in c["columns"] if x["table"] == t]
        body = [f"    {x['col']} {x['type']}{' DEFAULT ' + x['default'] if x['default'] else ''}{' NOT NULL' if x['notnull'] else ''}" for x in cols]
        out.append(f"CREATE TABLE {SCHEMA}.{t} (\n" + ",\n".join(body) + "\n);")
    for k in c["constraints"]:
        out.append(f"ALTER TABLE {k['table']} ADD CONSTRAINT {k['name']} {k['def']};")
    for i in c["indexes"]:
        if not i["by_constraint"]:
            out.append(i["def"] + ";")
    by_name = {v["name"]: v for v in c["views"]}
    for name in c["view_order"]:
        out.append(f"CREATE VIEW {SCHEMA}.{name} AS\n{by_name[name]['def'].rstrip().rstrip(';')};")
    for tr in c["triggers"]:
        out.append(tr["def"] + ";")
    for m in c["table_meta"]:
        if m["comment"] is not None:
            kind = "VIEW" if m["name"] in by_name else "SEQUENCE" if any(s["name"] == m["name"] for s in c["sequences"]) else "TABLE"
            out.append(f"COMMENT ON {kind} {SCHEMA}.{m['name']} IS {lit(m['comment'])};")
    for x in c["columns"]:
        if x["comment"] is not None:
            out.append(f"COMMENT ON COLUMN {SCHEMA}.{x['table']}.{x['col']} IS {lit(x['comment'])};")
    for f in fns:
        if f["comment"] is not None:
            out.append(f"COMMENT ON FUNCTION {SCHEMA}.{f['name']}({f['args']}) IS {lit(f['comment'])};")
    for s in c["sequences"]:
        if s["last_value"] is not None:
            out.append(f"SELECT setval('{SCHEMA}.{s['name']}', {s['last_value']}, true);")
    return "\n".join(out) + "\n"


def restore_stg_sql(rows, fp):
    vals = [r for r in rows if r.get("stg_normalized_item") is not None]
    lines = [
        "-- card_extr_stg.stg_normalized_item 값 복구. sql/db_pipeline_calc_structure_cleanup_rollback.sql(컬럼·NOT VALID CHECK 복구) 다음에 실행한다.",
        "-- 백업 시점 지문과 같아야 COMMIT된다. 이 파일은 추출 데이터를 담으므로 Git에 올리지 않는다.",
        "BEGIN;",
        "SET LOCAL lock_timeout = '5s';",
        "CREATE TEMP TABLE stg_norm_restore (card_extr_stg_id varchar(20) PRIMARY KEY, v jsonb NOT NULL) ON COMMIT DROP;",
    ]
    for i in range(0, len(vals), 50):
        chunk = vals[i:i + 50]
        lines.append("INSERT INTO stg_norm_restore VALUES\n    " + ",\n    ".join(
            f"({lit(r['card_extr_stg_id'])}, {lit(json.dumps(r['stg_normalized_item'], ensure_ascii=False))}::jsonb)" for r in chunk) + ";")
    lines += [
        f"UPDATE {SCHEMA}.card_extr_stg s SET stg_normalized_item = r.v FROM stg_norm_restore r WHERE r.card_extr_stg_id = s.card_extr_stg_id;",
        "DO $chk$",
        "DECLARE v_n int; v_f text; v_missing int;",
        "BEGIN",
        "    SELECT count(*) INTO v_missing FROM stg_norm_restore r WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_extr_stg s WHERE s.card_extr_stg_id = r.card_extr_stg_id);",
        "    IF v_missing > 0 THEN RAISE EXCEPTION '복구 대상 행 % 건이 card_extr_stg에 없음', v_missing; END IF;",
        f"    SELECT n, f INTO v_n, v_f FROM ({STG_FP}) x;",
        f"    IF v_n <> {fp['n']} OR v_f <> {lit(fp['f'])} THEN RAISE EXCEPTION '정제본 지문 불일치: % / %', v_n, v_f; END IF;",
        "    RAISE NOTICE '정제본 % 건 복구, 지문 일치', v_n;",
        "END",
        "$chk$;",
        "-- 값이 돌아온 뒤 원래 CHECK(승인 행은 정제본 필수)를 검증 상태로 되돌린다",
        f"ALTER TABLE {SCHEMA}.card_extr_stg VALIDATE CONSTRAINT card_extr_stg_check1;",
        "COMMIT;",
    ]
    return "\n".join(lines) + "\n"


def export(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=False)
    with connect() as conn, conn.cursor() as cur:
        conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")   # 한 시점의 스냅샷
        cat = catalog(cur)
        data = {"exported_at": datetime.datetime.now().astimezone().isoformat(), "schema": SCHEMA,
                "server_version": q(cur, "SHOW server_version")[0]["server_version"], "tables": {}, "fingerprints": {}}
        for t in cat["tables"]:
            cols = [x["col"] for x in cat["columns"] if x["table"] == t]
            rows = [r["j"] for r in q(cur, f"SELECT to_jsonb(t) AS j FROM {SCHEMA}.{t} t")]
            data["tables"][t] = {"columns": cols, "rows": rows}
            data["fingerprints"][t] = q(cur, fingerprint_sql(t, cols))[0]
        data["fingerprints"]["card_extr_stg.stg_normalized_item"] = q(cur, STG_FP)[0]
        data["sequences"] = {s["name"]: s["last_value"] for s in cat["sequences"]}
        conn.rollback()
    (out_dir / "postgres_db_pipeline.json").write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "catalog.json").write_text(json.dumps(cat, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / "schema_ddl.sql").write_text(ddl(cat), encoding="utf-8", newline="\n")
    (out_dir / "restore_stg_normalized_item.sql").write_text(
        restore_stg_sql(data["tables"]["card_extr_stg"]["rows"], data["fingerprints"]["card_extr_stg.stg_normalized_item"]), encoding="utf-8", newline="\n")
    print("backup:", out_dir.relative_to(PROJECT))
    return out_dir


def verify(out_dir: Path):
    """백업 JSON을 실DB에 대입해 행 단위로 같은지 확인한다(READ ONLY, 실DB 변경 없음)."""
    data = json.loads((out_dir / "postgres_db_pipeline.json").read_text(encoding="utf-8"))
    cat = json.loads((out_dir / "catalog.json").read_text(encoding="utf-8"))
    problems, report = [], {}
    with connect() as conn, conn.cursor() as cur:
        conn.execute("BEGIN READ ONLY")
        live_tables = [r["relname"] for r in q(cur, "SELECT relname FROM pg_class WHERE relnamespace=%s::regnamespace AND relkind='r' ORDER BY 1", (SCHEMA,))]
        if live_tables != cat["tables"]:
            problems.append(f"테이블 목록 불일치: {set(live_tables) ^ set(cat['tables'])}")
        for t, v in data["tables"].items():
            live_fp = q(cur, fingerprint_sql(t, v["columns"]))[0]
            # 백업 행을 테이블 타입으로 되살려 실DB와 양방향 EXCEPT ALL 비교
            diff = q(cur, f"""WITH b AS (SELECT * FROM jsonb_populate_recordset(NULL::{SCHEMA}.{t}, %s::jsonb))
                              SELECT (SELECT count(*) FROM (SELECT * FROM b EXCEPT ALL SELECT * FROM {SCHEMA}.{t}) x)::int AS only_backup,
                                     (SELECT count(*) FROM (SELECT * FROM {SCHEMA}.{t} EXCEPT ALL SELECT * FROM b) y)::int AS only_live""",
                     (json.dumps(v["rows"], ensure_ascii=False),))[0]
            ok = len(v["rows"]) == live_fp["n"] and live_fp == data["fingerprints"][t] and diff["only_backup"] == 0 and diff["only_live"] == 0
            report[t] = len(v["rows"])
            if not ok:
                problems.append(f"{t}: backup={len(v['rows'])} live={live_fp} diff={diff}")
        stg = q(cur, STG_FP)[0]
        if stg != data["fingerprints"]["card_extr_stg.stg_normalized_item"]:
            problems.append(f"정제본 지문 불일치 {stg}")
        live_cat = catalog(cur)
        for key in ("columns", "constraints", "indexes", "views", "functions", "triggers"):
            if json.dumps(live_cat[key], default=str, sort_keys=True) != json.dumps(cat[key], default=str, sort_keys=True):
                problems.append(f"catalog.{key} 불일치")
        conn.rollback()
    restore = (out_dir / "restore_stg_normalized_item.sql").read_text(encoding="utf-8")
    n_restore = restore.count("::jsonb)")
    if n_restore != stg["n"]:
        problems.append(f"복구 SQL 행 수 {n_restore} != {stg['n']}")
    print("tables", len(report), "rows", sum(report.values()), report)
    print("stg_normalized_item non-null", stg["n"], "md5", stg["f"], "| restore rows", n_restore)
    print("catalog: views", len(cat["views"]), "functions", len(cat["functions"]), "constraints", len(cat["constraints"]),
          "indexes", len(cat["indexes"]), "triggers", len(cat["triggers"]), "sequences", len(cat["sequences"]))
    print("VERIFY", "OK" if not problems else "FAIL", *problems, sep="\n  " if problems else " ")
    return not problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", type=Path, help="기존 백업 폴더 대조만 한다")
    ap.add_argument("--rebuild-restore", type=Path, help="백업 JSON에서 restore_stg_normalized_item.sql만 다시 만든다(DB 접속 없음)")
    a = ap.parse_args()
    if a.rebuild_restore:
        d = json.loads((a.rebuild_restore / "postgres_db_pipeline.json").read_text(encoding="utf-8"))
        (a.rebuild_restore / "restore_stg_normalized_item.sql").write_text(
            restore_stg_sql(d["tables"]["card_extr_stg"]["rows"], d["fingerprints"]["card_extr_stg.stg_normalized_item"]), encoding="utf-8", newline="\n")
        sys.exit(0)
    target = a.verify or export(BACKUP_ROOT / f"pre_calc_cleanup_{datetime.datetime.now():%Y%m%d_%H%M%S}")
    sys.exit(0 if verify(target) else 1)
