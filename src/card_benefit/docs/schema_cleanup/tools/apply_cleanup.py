"""계산 구조 정리(+ stg_normalized_item 제거)를 실DB db_pipeline에 점검·리허설·적용한다. psql 없이 psycopg로 실행한다.

    python apply_cleanup.py precheck  [백업 폴더]   읽기 전용: 정리 SQL의 사전 조건만 실행
    python apply_cleanup.py rehearse  [백업 폴더]   한 트랜잭션: 정리 → 소스 SQL 호환 → 복구 → 백업과 전체 대조 → 항상 ROLLBACK
    python apply_cleanup.py apply --yes [백업 폴더] 정리 SQL을 COMMIT(사전·사후 검증 실패 시 SQL 안에서 ROLLBACK)
    python apply_cleanup.py postcheck [백업 폴더]   읽기 전용: 적용 후 상태를 백업과 대조(정리 대상 외 보존 확인)

백업 폴더를 생략하면 src/data/backup/pre_calc_cleanup_* 중 최신을 쓴다. 다른 스키마는 건드리지 않는다.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

sys.stdout.reconfigure(encoding="utf-8")
CARD = Path(__file__).resolve().parents[3]                      # src/card_benefit
PROJECT = CARD.parents[1]
SQL = CARD / "sql"
CLEANUP = SQL / "db_pipeline_calc_structure_cleanup.sql"
ROLLBACK = SQL / "db_pipeline_calc_structure_cleanup_rollback.sql"
MAPPERS = sorted((CARD / "payment_card" / "db_pipeline").glob("*_repository.sql")) + [CARD / "payment_card" / "db_pipeline" / "neo4j_validation.sql"]
# 정리로 바뀌는 것(이 목록 밖의 차이는 실패)
CHANGED_COLS = {"card_bnft": {"rule_list", "bnft_cond_expr", "rule_select_cd"}, "card_product": {"card_cond_expr"},
                "card_extr_stg": {"stg_normalized_item", "card_excl_item_id"}}
DROPPED_TABLES = {"card_excl_item"}
CODE_GROUPS = {"PREDICATE_STATE", "PREDICATE_METHOD", "RULE_SELECT", "LIMIT_PERIOD", "LIMIT_UNIT", "LIMIT_SCOPE", "LIMIT_AGG", "POOL_ROLE", "CALC_METHOD", "PAYOUT_UNIT"}
results = []
APP_SEARCH_PATH = '"$user", public, extensions'     # Supabase 기본(프로그램 접속 경로)


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  :: ' + str(detail)[:400] if detail else ''}", flush=True)


def connect(read_only):
    load_dotenv(PROJECT / ".env")
    conn = psycopg.connect(os.environ["DB_URL"], connect_timeout=15, row_factory=dict_row, autocommit=True)
    conn.add_notice_handler(lambda d: print("  NOTICE:", d.message_primary, flush=True))
    conn.execute("SET statement_timeout = '300s'")
    if read_only:
        conn.execute("SET default_transaction_read_only = on")
    return conn


def body(path: Path) -> str:
    """파일의 BEGIN;/COMMIT;을 떼어 바깥 트랜잭션 안에서 실행할 수 있게 한다."""
    text = path.read_text(encoding="utf-8")
    text, n1 = re.subn(r"^BEGIN;\s*$", "", text, count=1, flags=re.M)
    text, n2 = re.subn(r"^COMMIT;\s*$", "", text, flags=re.M)
    if (n1, n2) != (1, 1):
        raise SystemExit(f"{path.name}: BEGIN/COMMIT 형식이 다름 {n1},{n2}")
    # 달러 인용 본문(DO·함수)과 주석을 뺀 최상위 문장에 트랜잭션 종료 문장이 없어야 한다(리허설 중 실제 COMMIT 방지)
    top = re.sub(r"'(?:[^']|'')*'", "''", re.sub(r"--[^\n]*", "", re.sub(r"(\$\w*\$).*?\1", "", text, flags=re.S)))
    first_words = [st.split()[0].upper() for st in top.split(";") if st.split()]
    bad = [w for w in first_words if w in ("COMMIT", "END", "ROLLBACK", "BEGIN", "ABORT", "START", "PREPARE")]
    if bad:
        raise SystemExit(f"{path.name}: 바깥 트랜잭션을 끝낼 수 있는 문장이 있음 {bad}")
    return text


def assert_in_rehearsal(conn, cur, step):
    """리허설 트랜잭션이 살아 있는지(중간 COMMIT 없음) 확인한다. 아니면 즉시 중단."""
    alive = conn.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS and \
        q(cur, "SELECT to_regclass('pg_temp.rehearsal_marker') IS NOT NULL AS ok")[0]["ok"]
    if not alive:
        raise SystemExit(f"리허설 트랜잭션이 끊김({step}) — 즉시 중단")


def statements():
    out = {}
    for f in MAPPERS:
        for block in re.split(r"^-- name: ", f.read_text(encoding="utf-8"), flags=re.M)[1:]:
            name = re.sub(r"[!<>*$#^]+$", "", block.split()[0])
            sql = block[block.index("\n") + 1:].strip().rstrip(";")
            sql = re.sub(r"(?<![:\w]):([A-Za-z_]\w*)", "NULL", sql)       # :PARAM → NULL (::cast는 유지)
            out[f"{f.stem}.{name}"] = sql
    return out


def explain_all(cur):
    """mapper의 모든 문장을 EXPLAIN(실행하지 않음)해 컬럼·객체 해석 오류를 찾는다."""
    errs = {}
    for name, sql in statements().items():
        cur.execute("SAVEPOINT sp_explain")
        cur.execute(f"SET LOCAL search_path = {APP_SEARCH_PATH}")   # 프로그램 접속과 같은 경로(SAVEPOINT 되돌림으로 원복)
        try:
            cur.execute("EXPLAIN " + sql)
        except psycopg.Error as e:
            errs[name] = e.diag.message_primary
        cur.execute("ROLLBACK TO SAVEPOINT sp_explain")
    return errs


def table_diff(cur, backup, ignore_changed):
    """백업 JSON을 테이블 타입으로 되살려 실DB와 양방향 EXCEPT ALL 비교(컬럼 이름 기준)."""
    bad = {}
    live = {r["relname"] for r in q(cur, "SELECT relname FROM pg_class WHERE relnamespace='db_pipeline'::regnamespace AND relkind='r'")}
    for t, v in backup["tables"].items():
        if t not in live:
            if not (ignore_changed and t in DROPPED_TABLES):
                bad[t] = "테이블 없음"
            continue
        live_cols = {r["attname"] for r in q(cur, "SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped", (f"db_pipeline.{t}",))}
        cols = [c for c in v["columns"] if c in live_cols and not (ignore_changed and c in CHANGED_COLS.get(t, set()))]
        missing = [c for c in v["columns"] if c not in live_cols and not (ignore_changed and c in CHANGED_COLS.get(t, set()))]
        if missing:
            bad[t] = f"컬럼 없음 {missing}"
            continue
        rows = v["rows"]
        if ignore_changed and t == "common_cd":
            rows = [r for r in rows if r["common_code_grp_id"] not in CODE_GROUPS]
        if ignore_changed and t == "common_code_grp":
            rows = [r for r in rows if r["common_code_grp_id"] not in CODE_GROUPS]
        cl = ", ".join(cols)
        d = q(cur, f"""WITH b AS (SELECT {cl} FROM jsonb_populate_recordset(NULL::db_pipeline.{t}, %s::jsonb)), l AS (SELECT {cl} FROM db_pipeline.{t})
                       SELECT (SELECT count(*) FROM (SELECT * FROM b EXCEPT ALL SELECT * FROM l) x)::int AS only_backup,
                              (SELECT count(*) FROM (SELECT * FROM l EXCEPT ALL SELECT * FROM b) y)::int AS only_live""",
              (json.dumps(rows, ensure_ascii=False),))[0]
        if d["only_backup"] or d["only_live"]:
            bad[t] = d
    return bad


def catalog_sets(cur):
    return {
        "constraints": {(r["t"], r["n"], r["d"]) for r in q(cur, "SELECT conrelid::regclass::text t, conname n, pg_get_constraintdef(oid) d FROM pg_constraint WHERE connamespace='db_pipeline'::regnamespace AND conrelid<>0")},
        "indexes": {(r["n"], r["d"]) for r in q(cur, "SELECT indexname n, indexdef d FROM pg_indexes WHERE schemaname='db_pipeline'")},
        "views": {(r["n"], r["d"], r["c"]) for r in q(cur, "SELECT c.relname n, pg_get_viewdef(c.oid) d, obj_description(c.oid,'pg_class') c FROM pg_class c WHERE relnamespace='db_pipeline'::regnamespace AND relkind='v'")},
        "functions": {(r["n"], r["d"], r["c"]) for r in q(cur, "SELECT proname n, pg_get_functiondef(oid) d, obj_description(oid,'pg_proc') c FROM pg_proc WHERE pronamespace='db_pipeline'::regnamespace")},
        "columns": {(r["t"], r["c"], r["ty"], r["nn"], r["cm"]) for r in q(cur, """SELECT c.relname t, a.attname c, format_type(a.atttypid,a.atttypmod) ty, a.attnotnull nn, col_description(c.oid,a.attnum) cm
                     FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped WHERE c.relnamespace='db_pipeline'::regnamespace AND c.relkind='r'""")},
        # 정의만 비교한다. last_value는 SAVEPOINT 안 등록 시험의 ID 발급으로 늘고 ROLLBACK으로 돌아가지 않는다(별도 보고).
        "sequences": {tuple(r.values()) for r in q(cur, """SELECT sequencename, data_type::text, start_value, min_value, max_value, increment_by, cycle, cache_size,
                     obj_description(('db_pipeline.'||sequencename)::regclass,'pg_class') cm FROM pg_sequences WHERE schemaname='db_pipeline'""")},
        "invalid_constraints":{r["n"] for r in q(cur, "SELECT conname n FROM pg_constraint WHERE connamespace='db_pipeline'::regnamespace AND NOT convalidated")},
    }


def other_schemas(cur):
    """다른 스키마 객체 정의 지문(변경 없음 확인용)."""
    return q(cur, """SELECT md5(string_agg(n.nspname||'.'||c.relname||':'||c.relkind::text||':'||coalesce((SELECT string_agg(a.attname||' '||format_type(a.atttypid,a.atttypmod), ',' ORDER BY a.attnum)
                     FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),''), '|' ORDER BY n.nspname, c.relname)) f, count(*)::int n
                     FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE n.nspname NOT IN ('db_pipeline','pg_catalog','information_schema','pg_toast') AND n.nspname NOT LIKE 'pg_temp%%' AND n.nspname NOT LIKE 'pg_toast_temp%%'""")[0]


def q(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall() if cur.description else []


def latest_backup(arg):
    d = Path(arg) if arg else max((CARD.parent / "data" / "backup").glob("pre_calc_cleanup_*/postgres_db_pipeline.json")).parent
    return d, json.loads((d / "postgres_db_pipeline.json").read_text(encoding="utf-8"))


def precheck(cur):
    pre = re.search(r"^DO \$pre\$.*?^\$pre\$;", CLEANUP.read_text(encoding="utf-8"), flags=re.S | re.M).group(0)
    cur.execute("BEGIN READ ONLY")
    try:
        cur.execute(pre)
        check("사전 조건(정제본 지문·의존 객체·CHECK 정의·삭제 대상 값 없음·뷰 의존)", True)
    except psycopg.Error as e:
        check("사전 조건", False, e.diag.message_primary)
    finally:
        cur.execute("ROLLBACK")


EXPECTED_DROPPED_VIEWS = {"v_card_bnft_rule_effective"}
EXPECTED_REPLACED_VIEWS = {"v_card_rule", "v_card_cond_atom", "v_card_rule_target", "v_common_cd_usage", "v_card_integrity_issue"}
EXPECTED_DROPPED_FUNCS = {"fn_cond_spend_bound"}
EXPECTED_REPLACED_FUNCS = {"fn_valid_rule_list", "fn_valid_cond_expr"}
EXPECTED_DROPPED_COLS = {("card_bnft", "rule_select_cd"), ("card_extr_stg", "stg_normalized_item"), ("card_extr_stg", "card_excl_item_id")}
REMOVED_VIEW_COLS = {"spend_min_amt", "spend_max_amt_excl", "predicate_state_cd", "method_ver", "calc_params", "rule_priority", "calc_method_cd",
                     "payout_unit_cd", "basis_amt", "predicate_method_cd", "predicate_method_ver", "cond_params", "card_excl_item_id", "link_role_cd"}


def view_columns(cur, name):
    return {r["attname"] for r in q(cur, "SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0", (f"db_pipeline.{name}",))}


def own_locks_outside(cur):
    """이 트랜잭션이 잠근 db_pipeline·pg_catalog·임시 스키마 밖의 객체(다른 스키마를 건드렸는지)."""
    return q(cur, """SELECT DISTINCT n.nspname||'.'||c.relname AS obj, l.mode FROM pg_locks l JOIN pg_class c ON c.oid=l.relation
                     JOIN pg_namespace n ON n.oid=c.relnamespace
                     WHERE l.pid=pg_backend_pid() AND n.nspname NOT IN ('db_pipeline','pg_catalog','information_schema','pg_toast')
                       AND n.nspname NOT LIKE 'pg_temp%%' AND n.nspname NOT LIKE 'pg_toast_temp%%'""")


def cleanup_catalog_ok(before, after):
    """정리 전후 카탈로그 차이가 계획한 변경과 정확히 같은지 본다. 계획 밖 차이는 모두 실패다."""
    problems = []
    gone = lambda k: {x for x in before[k] - after[k]}          # noqa: E731
    new = lambda k: {x for x in after[k] - before[k]}           # noqa: E731
    # 제약: card_excl_item PK·UNIQUE와 옛 check1이 빠지고 새 check1만 생긴다
    exp_gone_con = {x for x in before["constraints"] if x[0] == "db_pipeline.card_excl_item" or x[1] == "card_extr_stg_check1"}
    if gone("constraints") != exp_gone_con or {x[1] for x in new("constraints")} != {"card_extr_stg_check1"}:
        problems.append(("constraints", sorted(gone("constraints") ^ exp_gone_con), sorted(new("constraints"))))
    exp_gone_idx = {x for x in before["indexes"] if x[0] in ("ix_card_extr_stg_excl_item_key",) or " db_pipeline.card_excl_item " in x[1]}
    if gone("indexes") != exp_gone_idx or new("indexes"):
        problems.append(("indexes", sorted(gone("indexes") ^ exp_gone_idx), sorted(new("indexes"))))
    vg, vn = {x[0] for x in gone("views")}, {x[0] for x in new("views")}
    if vg - EXPECTED_REPLACED_VIEWS != EXPECTED_DROPPED_VIEWS or not vn <= EXPECTED_REPLACED_VIEWS:
        problems.append(("views", sorted(vg), sorted(vn)))
    fg, fn = {x[0] for x in gone("functions")}, {x[0] for x in new("functions")}
    if fg - EXPECTED_REPLACED_FUNCS != EXPECTED_DROPPED_FUNCS or not fn <= EXPECTED_REPLACED_FUNCS:
        problems.append(("functions", sorted(fg), sorted(fn)))
    cg = {(x[0], x[1]) for x in gone("columns")}
    exp_cols = EXPECTED_DROPPED_COLS | {x[:2] for x in before["columns"] if x[0] == "card_excl_item"}
    if cg != exp_cols or new("columns"):
        problems.append(("columns", sorted(cg ^ exp_cols), sorted(new("columns"))))
    if {x[0] for x in gone("sequences")} != {"seq_card_excl_item"} or new("sequences"):
        problems.append(("sequences", sorted(gone("sequences")), sorted(new("sequences"))))
    if after["invalid_constraints"]:
        problems.append(("invalid_constraints", sorted(after["invalid_constraints"])))
    return problems


def run_verified(conn, cur, backup_dir, backup, commit):
    """한 트랜잭션: 정리 → 계획 대비 전체 검증 → SAVEPOINT 안 복구 실증 → 되돌림 → 재확인 → (commit이고 전부 통과면) COMMIT, 아니면 ROLLBACK."""
    restore = backup_dir / "restore_stg_normalized_item.sql"
    bodies = {"cleanup": body(CLEANUP), "rollback": body(ROLLBACK), "restore": body(restore)}   # 실행 전에 세 파일 모두 검사
    start = len(results)
    cur.execute("BEGIN")
    cur.execute("SET LOCAL search_path = pg_catalog")              # 카탈로그 출력(format_type·viewdef)이 search_path에 따라 달라지므로 고정
    cur.execute("CREATE TEMP TABLE rehearsal_marker (x int) ON COMMIT DROP")   # 중간 COMMIT이 생기면 사라진다
    committed = False
    try:
        before_cat = catalog_sets(cur)
        before_other = other_schemas(cur)
        before_sql = explain_all(cur)
        before_codes = q(cur, "SELECT (SELECT count(*)::int FROM db_pipeline.common_cd) cd, (SELECT count(*)::int FROM db_pipeline.common_code_grp) grp")[0]
        check("정리 전 mapper SQL EXPLAIN", not before_sql, f"{len(statements())}개 중 오류 {len(before_sql)} {before_sql}")
        # ---- 정리 ----
        cur.execute(bodies["cleanup"])
        assert_in_rehearsal(conn, cur, "정리 후")
        cur.execute("SET LOCAL search_path = pg_catalog")          # 비교 기준 고정(정리 SQL과 같은 값)
        check("정리 SQL 실행(SQL 내부 사전·사후 검증 포함)", True)
        after_cat = catalog_sets(cur)
        problems = cleanup_catalog_ok(before_cat, after_cat)
        check("정리 후 카탈로그 차이 = 계획한 변경만(제약·인덱스·뷰·함수·컬럼·시퀀스)", not problems, problems)
        for v in ("v_card_bnft_rel", "v_card_brand_opt"):
            check(f"미대상 뷰 {v} 정의 불변", {x for x in before_cat["views"] if x[0] == v} == {x for x in after_cat["views"] if x[0] == v})
        left = {v: sorted(view_columns(cur, v) & REMOVED_VIEW_COLS) for v in EXPECTED_REPLACED_VIEWS}
        check("교체 뷰에 계산 열 없음", not any(left.values()), left)
        rule_cols = view_columns(cur, "v_card_rule")
        check("v_card_rule 값·단위·대상·조건·상태 열 유지", {"value_num", "value_unit_cd", "target_list", "cond_expr", "rule_status_cd"} <= rule_cols, sorted(rule_cols))
        after_sql = explain_all(cur)
        check("정리 후 mapper SQL 84개 EXPLAIN 오류 없음", not after_sql and len(statements()) == 84, after_sql or f"{len(statements())}개")
        diff = table_diff(cur, backup, ignore_changed=True)
        check("보존 데이터 백업과 동일(원문·페이지·청크·근거·추출 원본·병합·실행 이력·공통서비스·상품)", not diff, diff)
        codes = q(cur, "SELECT (SELECT count(*)::int FROM db_pipeline.common_cd) cd, (SELECT count(*)::int FROM db_pipeline.common_code_grp) grp")[0]
        check("공통코드 10그룹·32코드만 삭제", codes == {"cd": before_codes["cd"] - 32, "grp": before_codes["grp"] - 10}, codes)
        n = q(cur, "SELECT count(*)::int n, count(*) FILTER (WHERE stg_raw_item IS NULL)::int nul FROM db_pipeline.card_extr_stg")[0]
        check("card_extr_stg 375행·stg_raw_item 누락 0", n == {"n": 375, "nul": 0}, n)
        bad = q(cur, "SELECT count(*)::int n FROM db_pipeline.card_bnft WHERE NOT (db_pipeline.fn_valid_rule_list(rule_list,'LOCAL') AND db_pipeline.fn_valid_cond_expr(bnft_cond_expr))")[0]["n"]
        check("card_bnft 5행 전부 새 계약 통과", bad == 0, bad)
        cur.execute("SAVEPOINT sp_insert")
        try:
            ins = re.search(r"^-- name: insert_local_benefit\n(.*?);", (CARD / "payment_card/db_pipeline/common_benefit_repository.sql").read_text(encoding="utf-8"), re.S | re.M).group(1)
            vals = {"CARD_ID": "2", "BNFT_CD": "'BNFT_TEST_CLEANUP'", "BNFT_NM": "'시험'", "BNFT_TYPE": "'DISCOUNT'", "COND": "NULL", "RULE_TXT": "'원문'", "LIMIT_TXT": "'USD 30 한도'",
                    "RULES": """'[{"rule_key":"r1","cond_expr":null,"target_list":[{"target_nm":"호텔","target_key":"hotel","target_type_cd":"MERCHANT"}],"value_num":8,"value_unit_cd":"PERCENT","rule_status_cd":"DRAFT"}]'::jsonb"""}
            cur.execute(re.sub(r"(?<![:\w]):([A-Z_]+)", lambda m: vals[m.group(1)], ins))
            check("등록 mapper insert_local_benefit: 계산 방법 없는 규칙 저장 가능(SAVEPOINT 되돌림)", True)
        except psycopg.Error as e:
            check("등록 mapper insert_local_benefit: 계산 방법 없는 규칙 저장 가능(SAVEPOINT 되돌림)", False, e.diag.message_primary)
        cur.execute("ROLLBACK TO SAVEPOINT sp_insert")
        cur.execute("SAVEPOINT sp_approve")
        try:
            cur.execute("UPDATE db_pipeline.card_extr_stg SET stg_status='AUTO_APPROVED' WHERE card_extr_stg_id = (SELECT min(card_extr_stg_id) FROM db_pipeline.card_extr_stg WHERE stg_sql_check_cd IS DISTINCT FROM 'OK')")
            check("새 CHECK: 검증 OK가 아닌 행 승인 거부", False, "승인됨")
        except psycopg.errors.CheckViolation:
            check("새 CHECK: 검증 OK가 아닌 행 승인 거부", True)
        cur.execute("ROLLBACK TO SAVEPOINT sp_approve")
        locks = own_locks_outside(cur)
        check("다른 스키마: 이 트랜잭션이 잠근 객체 없음", not locks, locks)
        check("다른 스키마: 객체 정의 지문 불변(같은 search_path 기준)", other_schemas(cur) == before_other)
        assert_in_rehearsal(conn, cur, "정리 검증 후")
        # ---- 복구 절차 실증(SAVEPOINT 안에서 실행 후 되돌림) ----
        cur.execute("SAVEPOINT sp_recovery")
        cur.execute(bodies["rollback"])
        cur.execute(bodies["restore"])
        assert_in_rehearsal(conn, cur, "복구 실증 후")
        cur.execute("SET LOCAL search_path = pg_catalog")
        check("복구 SQL + 정제본 350건 복구 실행(지문 확인·CHECK VALIDATE)", True)
        diff = table_diff(cur, backup, ignore_changed=False)
        check("복구 실증: 전체 데이터 백업과 동일(정제본 350건 포함)", not diff, diff)
        rec_cat = catalog_sets(cur)
        cat_diff = {k: (sorted(before_cat[k] - rec_cat[k])[:3], sorted(rec_cat[k] - before_cat[k])[:3]) for k in before_cat if before_cat[k] != rec_cat[k]}
        check("복구 실증: 제약·인덱스·뷰·함수·컬럼·시퀀스·주석 정의 정리 전과 동일", not cat_diff, cat_diff)
        check("복구 실증: mapper SQL EXPLAIN 정리 전과 동일", explain_all(cur) == before_sql)
        cur.execute("ROLLBACK TO SAVEPOINT sp_recovery")
        cur.execute("SET LOCAL search_path = pg_catalog")
        check("복구 실증 되돌림 후 정리 상태 그대로", catalog_sets(cur) == after_cat and not table_diff(cur, backup, ignore_changed=True))
        check("최종: 다른 스키마 잠금 없음·지문 불변", not own_locks_outside(cur) and other_schemas(cur) == before_other)
        assert_in_rehearsal(conn, cur, "COMMIT 직전")
        ok = all(r[1] for r in results[start:])
        if commit and ok:
            cur.execute("COMMIT")
            committed = True
            print(">>> 모든 검증 통과 → COMMIT 완료")
        else:
            print(">>> " + ("검증 실패" if not ok else "commit 지정 안 함") + " → ROLLBACK")
    except psycopg.Error as e:
        check("실행 중 오류", False, f"{e.diag.message_primary} / {e.diag.context or ''}"[:600])
    finally:
        if not committed:
            cur.execute("ROLLBACK")
            print("트랜잭션 ROLLBACK 완료")
    return committed


def postcheck(cur, backup):
    cur.execute("BEGIN READ ONLY")
    try:
        cols = {r["attname"] for r in q(cur, "SELECT attname FROM pg_attribute WHERE attrelid='db_pipeline.card_extr_stg'::regclass AND attnum>0 AND NOT attisdropped")}
        check("stg_normalized_item·card_excl_item_id 제거됨", not ({"stg_normalized_item", "card_excl_item_id"} & cols))
        check("card_excl_item·v_card_bnft_rule_effective 제거됨",
              q(cur, "SELECT to_regclass('db_pipeline.card_excl_item') a, to_regclass('db_pipeline.v_card_bnft_rule_effective') b")[0] == {"a": None, "b": None})
        diff = table_diff(cur, backup, ignore_changed=True)
        check("보존 데이터 백업과 동일(정리 대상 제외)", not diff, diff)
        con = q(cur, "SELECT pg_get_constraintdef(oid) d FROM pg_constraint WHERE conrelid='db_pipeline.card_extr_stg'::regclass AND conname='card_extr_stg_check1'")
        check("새 card_extr_stg_check1(정제본 조건 없음)", con and "stg_normalized_item" not in con[0]["d"] and "stg_sql_check_cd" in con[0]["d"], con)
        errs = explain_all(cur)
        check("mapper SQL EXPLAIN 오류 없음", not errs, errs)
        rows = q(cur, "SELECT count(*)::int n FROM db_pipeline.card_bnft WHERE NOT (db_pipeline.fn_valid_rule_list(rule_list,'LOCAL') AND db_pipeline.fn_valid_cond_expr(bnft_cond_expr))")[0]["n"]
        check("card_bnft 전부 새 계약 통과", rows == 0, rows)
    finally:
        cur.execute("ROLLBACK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["precheck", "rehearse", "apply", "postcheck"])
    ap.add_argument("backup", nargs="?")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    backup_dir, backup = latest_backup(a.backup)
    print("backup:", backup_dir.name, backup["exported_at"])
    with connect(read_only=a.mode in ("precheck", "postcheck")) as conn, conn.cursor() as cur:
        if a.mode == "precheck":
            precheck(cur)
        elif a.mode == "rehearse":
            precheck(cur)
            run_verified(conn, cur, backup_dir, backup, commit=False)
        elif a.mode == "postcheck":
            postcheck(cur, backup)
        else:
            if not a.yes:
                raise SystemExit("apply는 --yes가 필요하다(사용자 승인 후)")
            precheck(cur)
            if not all(ok for _, ok, _ in results):
                raise SystemExit("사전 조건 실패로 중단")
            seq0 = {r["sequencename"]: r["last_value"] for r in q(cur, "SELECT sequencename, last_value FROM pg_sequences WHERE schemaname='db_pipeline'")}
            run_verified(conn, cur, backup_dir, backup, commit=True)
            seq1 = {r["sequencename"]: r["last_value"] for r in q(cur, "SELECT sequencename, last_value FROM pg_sequences WHERE schemaname='db_pipeline'")}
            print("시퀀스 소비(등록 시험 ID 발급):", {k: (seq0.get(k), v) for k, v in seq1.items() if seq0.get(k) != v})
    print(f"TOTAL {len(results)} PASS {sum(ok for _, ok, _ in results)}")
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)


if __name__ == "__main__":
    main()
