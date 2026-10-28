"""레시피 PostgreSQL 목표 모델 재구축 도구(백업 → 복원 시험 → 격리 리허설 → 전환 → 복구).

기본 동작은 읽기 전용 점검이다. 쓰기 명령은 모두 ``--confirm-db <host>/<dbname>`` 이 실제 연결 대상과
같아야 실행되고, 각 명령이 요구하는 확인 플래그가 따로 있다. ``DROP SCHEMA ... CASCADE`` 는 사용하지 않는다.

    python -m recipe_recommender.tools.recipe_rebuild inspect
    python -m recipe_recommender.tools.recipe_rebuild backup --source recipe --out <폴더>
    python -m recipe_recommender.tools.recipe_rebuild verify-backup --dir <폴더> [--live]
    python -m recipe_recommender.tools.recipe_rebuild restore-test --dir <폴더> --schema recipe_restore_chk --confirm-db H/D
    python -m recipe_recommender.tools.recipe_rebuild build --source recipe --target recipe_v2 --confirm-db H/D
    python -m recipe_recommender.tools.recipe_rebuild validate --source recipe --target recipe_v2
    python -m recipe_recommender.tools.recipe_rebuild drop-schema --schema recipe_v2 --confirm-schema recipe_v2 --confirm-db H/D
    python -m recipe_recommender.tools.recipe_rebuild cutover --legacy-schema recipe_legacy_20261022 \
        --backup-dir <폴더> --confirm-cutover --confirm-db H/D
    python -m recipe_recommender.tools.recipe_rebuild rollback-cutover --legacy-schema recipe_legacy_20261022 \
        --confirm-rollback --confirm-db H/D

트랜잭션:
    build / cutover 는 스키마 생성·DDL·이관·구조 검사·데이터 검증을 한 트랜잭션에서 실행하고, 검사가 하나라도
    실패하면 ROLLBACK한다. 원본 스키마는 SHARE 잠금으로 이관 중 쓰기를 막고 SELECT만 한다.
    restore-test 는 백업 파일을 임시 스키마에 COPY로 복원해 원본과 같은지 확인한 뒤 항상 ROLLBACK한다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.config import load_project_environment, project_root  # noqa: E402
from recipe_recommender.sql_schema import DEFAULT_SCHEMA, render_schema_sql, validate_schema_name  # noqa: E402
from recipe_recommender.tools._connection_util import safe_error  # noqa: E402

# region 1. 재구축 경로와 목표 모델 기준
DOCS_DB = TASK_DIR / "docs" / "db"
TARGET_DDL_PATH = DOCS_DB / "recipe_target_schema.sql"
MIGRATION_SQL_PATH = DOCS_DB / "recipe_target_migration.sql"
VALIDATION_SQL_PATH = DOCS_DB / "recipe_target_validation.sql"
LEGACY_DDL_PATH = DOCS_DB / "recipe_schema_review.sql"
SOURCE_CSV_PATH = project_root() / "src" / "data" / "COOKRCP01.csv"
SEED_DIR = TASK_DIR / "recipe_recommender" / "data"

SCHEMA_MARKER = "recipe-rebuild"            # 이 도구가 만든 스키마의 COMMENT 접두어(삭제·복구 대상 확인용)

LEGACY_PKS = {
    "rcp_raw": ["rcp_raw_id", "rcp_raw_seq"],
    "rcp_cat": ["rcp_cat_id"],
    "common_code_grp": ["common_code_grp_id"],
    "common_cd": ["common_code_grp_id", "common_cd"],
    "rcp": ["rcp_cat_id", "rcp_id"],
    "rcp_step": ["rcp_cat_id", "rcp_id", "step_no"],
    "ingr_cat": ["ingr_cat_id"],
    "ingr": ["ingr_cat_id", "ingr_id"],
    "ingr_als": ["ingr_cat_id", "ingr_id", "ingr_als_id"],
    "rcp_ingr_stg": ["rcp_raw_id", "rcp_raw_seq", "rcp_ingr_stg_id"],
    "rcp_ingr": ["ingr_cat_id", "ingr_id", "rcp_cat_id", "rcp_id"],
}
TARGET_PKS = {
    "rcp_raw": ["rcp_raw_id", "rcp_raw_seq"],
    "rcp_cat": ["rcp_cat_id"],
    "rcp_cat_rel": ["rcp_id", "rcp_cat_id"],
    "common_code_grp": ["common_code_grp_id"],
    "common_cd": ["common_code_grp_id", "common_cd"],
    "rcp": ["rcp_id"],
    "rcp_step": ["rcp_id", "step_no"],
    "ingr": ["ingr_id"],
    "ingr_als": ["ingr_id", "ingr_als_id"],
    "rcp_ingr_stg": ["rcp_raw_id", "rcp_raw_seq", "rcp_ingr_stg_id"],
    "rcp_ingr": ["rcp_id", "ingr_id"],
}
TARGET_SEQUENCES = {"seq_rcp_cat", "seq_rcp", "seq_ingr", "seq_ingr_als", "seq_import_batch", "seq_rcp_ingr_stg"}
TARGET_INDEXES = {"ix_rcp_cat_rel_cat_key", "ix_rcp_ingr_ingr_key", "ix_rcp_ingr_stg_ingr_key"}
# 원본(기존 모델)에서 제거되는 컬럼. 나머지 공통 컬럼은 형식·NULL 허용이 같아야 한다.
DROPPED_COLUMNS = {
    ("rcp", "rcp_cat_id"), ("rcp_step", "rcp_cat_id"),
    ("ingr", "ingr_cat_id"), ("ingr_als", "ingr_cat_id"), ("rcp_ingr_stg", "ingr_cat_id"),
    ("rcp_ingr", "ingr_cat_id"), ("rcp_ingr", "rcp_cat_id"),
}
# 2026-10-22 기존 DB 기준 건수(cnt_* 검증 기대값). --no-baseline 이면 원본·대상 집합 비교만 한다.
BASELINE = {
    "cnt_rcp_raw": 1156, "cnt_rcp_cat": 6, "cnt_common_code_grp": 1, "cnt_common_cd": 6,
    "cnt_rcp": 1156, "cnt_rcp_cat_rel": 1156, "cnt_rcp_step": 6717,
    "cnt_ingr": 275, "cnt_ingr_als": 71, "cnt_rcp_ingr_stg": 13080,
    "cnt_stg_auto_approved": 10611, "cnt_stg_manual_approved": 0, "cnt_stg_pending": 2469, "cnt_stg_rejected": 0,
    "cnt_rcp_ingr": 10428, "cnt_approved_minus_relation": 183,
}


class RebuildError(Exception):
    """재구축을 중단해야 하는 사전 조건·검증 실패."""


# endregion
# region 2. 연결 및 실행 대상 확인
# =========================================================
# 연결 / 대상 확인
# =========================================================
def connect():
    """``DB_URL`` 로 단독 연결을 연다(pool 미사용, 자동 prepared statement 끔: pooler 호환)."""
    import psycopg
    from psycopg.rows import dict_row

    load_project_environment()
    url = os.getenv("DB_URL")
    if not url:
        raise RebuildError("DB_URL is not configured")
    # autocommit: 읽기 전용 블록(read_only)과 쓰기 트랜잭션(connection.transaction())을 명시적으로만 연다.
    return psycopg.connect(url, row_factory=dict_row, prepare_threshold=None, autocommit=True)


@contextmanager
def read_only(connection):
    """하나의 스냅샷으로 읽는 READ ONLY 트랜잭션. 끝나면 항상 ROLLBACK한다."""
    connection.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    try:
        yield connection
    finally:
        connection.execute("ROLLBACK")


def describe_target(connection) -> dict:
    """비밀번호를 제외한 실제 연결 대상."""
    row = connection.execute(
        "SELECT current_database() AS dbname, current_user AS db_user, "
        "inet_server_port() AS server_port, split_part(version(), ' ', 2) AS server_version"
    ).fetchone()
    return {"host": connection.info.host, "port": connection.info.port, **row}


def target_label(target: dict) -> str:
    """DB 식별 정보를 사람이 확인할 대상 문자열로 표현한다."""
    return f"{target['host']}/{target['dbname']}"


def require_confirmed_db(connection, confirm_db: str | None) -> dict:
    """``--confirm-db`` 가 실제 ``host/dbname`` 과 정확히 같을 때만 쓰기를 허용한다."""
    target = describe_target(connection)
    print(f"[대상 DB] host={target['host']} port={target['port']} db={target['dbname']} "
          f"user={target['db_user']} server={target['server_version']}")
    if confirm_db != target_label(target):
        raise RebuildError(f"--confirm-db '{confirm_db}' != 실제 연결 대상 '{target_label(target)}' — 실행하지 않음")
    return target


# endregion
# region 3. 카탈로그 조회와 구조 검증
# =========================================================
# 카탈로그 조회 (읽기 전용)
# =========================================================
def schema_exists(connection, schema: str) -> bool:
    """지정한 PostgreSQL 스키마의 존재 여부를 카탈로그에서 조회한다."""
    return connection.execute("SELECT to_regnamespace(%s) IS NOT NULL AS ok", (schema,)).fetchone()["ok"]


def schema_comment(connection, schema: str) -> str | None:
    """스키마의 소유 표식으로 쓰는 COMMENT를 조회한다."""
    return connection.execute(
        "SELECT obj_description(oid, 'pg_namespace') AS c FROM pg_namespace WHERE nspname = %s", (schema,)
    ).fetchone()["c"] if schema_exists(connection, schema) else None


def catalog_pks(connection, schema: str) -> dict[str, list[str]]:
    """카탈로그에서 테이블별 기본 키 컬럼을 읽는다."""
    rows = connection.execute(
        "SELECT t.relname AS table_name, a.attname AS column_name "
        "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = t.relnamespace "
        "JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
        "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum "
        "WHERE n.nspname = %s AND c.contype = 'p' ORDER BY t.relname, k.ord", (schema,)
    ).fetchall()
    pks: dict[str, list[str]] = {}
    for row in rows:
        pks.setdefault(row["table_name"], []).append(row["column_name"])
    return pks


def catalog_tables(connection, schema: str) -> list[str]:
    """스키마의 테이블 이름을 카탈로그에서 읽는다."""
    return [row["relname"] for row in connection.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relkind IN ('r', 'p') ORDER BY c.relname", (schema,))]


def catalog_objects(connection, schema: str) -> list[dict]:
    """스키마 안의 테이블·시퀀스·뷰 등 관계 객체(인덱스 제외)와 함수."""
    rows = connection.execute(
        "SELECT c.relname AS name, c.relkind::text AS kind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relkind NOT IN ('i', 'I') "
        "UNION ALL SELECT p.oid::regprocedure::text, 'function' FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = %s UNION ALL SELECT t.typname, 'type' FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = %s AND t.typtype IN ('d', 'e') ORDER BY 2, 1", (schema, schema, schema)).fetchall()
    return [dict(row) for row in rows]


def catalog_columns(connection, schema: str) -> dict[tuple[str, str], tuple[str, bool]]:
    """스키마 컬럼의 타입과 NULL 허용 여부를 읽는다."""
    rows = connection.execute(
        "SELECT t.relname AS table_name, a.attname AS column_name, "
        "format_type(a.atttypid, a.atttypmod) AS data_type, a.attnotnull AS not_null "
        "FROM pg_class t JOIN pg_namespace n ON n.oid = t.relnamespace JOIN pg_attribute a ON a.attrelid = t.oid "
        "WHERE n.nspname = %s AND t.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped", (schema,)).fetchall()
    return {(row["table_name"], row["column_name"]): (row["data_type"], row["not_null"]) for row in rows}


def table_fingerprints(connection, schema: str, pks: dict[str, list[str]]) -> dict[str, dict]:
    """테이블별 행 수와 PK 순서 행 텍스트의 md5(같은 세션 설정에서 비교용)."""
    result = {}
    for table in sorted(pks):
        order = ", ".join(pks[table])
        row = connection.execute(
            f"SELECT count(*) AS n, md5(coalesce(string_agg(t::text, E'\\n' ORDER BY {order}), '')) AS h "
            f"FROM {schema}.{table} AS t").fetchone()
        result[table] = {"rows": row["n"], "md5": row["h"]}
    return result


def check_legacy_source(connection, source: str) -> None:
    """이전 모델 원천의 구조가 전환 조건을 만족하는지 검증한다."""
    pks = catalog_pks(connection, source)
    if pks != LEGACY_PKS:
        raise RebuildError(f"원본 스키마 {source} 가 기존 11개 테이블 모델과 다름: {sorted(pks)}")


def check_target_structure(connection, target: str, source: str) -> list[str]:
    """대상 스키마가 목표 설계(PK·테이블·시퀀스·인덱스·컬럼·COMMENT)대로 만들어졌는지 검사한다."""
    problems = []
    pks = catalog_pks(connection, target)
    if pks != TARGET_PKS:
        problems.append(f"PK 정의 불일치: {pks}")
    objects = catalog_objects(connection, target)
    sequences = {item["name"] for item in objects if item["kind"] == "S"}
    if sequences != TARGET_SEQUENCES:
        problems.append(f"시퀀스 불일치: {sorted(sequences)}")
    if {item["kind"] for item in objects} - {"r", "S", "function"}:
        problems.append(f"예상하지 않은 객체: {objects}")
    if [item["name"] for item in objects if item["kind"] == "function"] != [f"{target}.fn_get_biz_id(text)"]:
        problems.append("업무 ID 함수 누락 또는 추가 함수 존재")
    indexes = {row["relname"] for row in connection.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_index i ON i.indexrelid = c.oid WHERE n.nspname = %s AND NOT i.indisprimary AND NOT i.indisunique",
        (target,))}
    if indexes != TARGET_INDEXES:
        problems.append(f"보조 인덱스 불일치: {sorted(indexes)}")
    columns = catalog_columns(connection, target)
    if "ingr_cat" in {table for table, _ in columns}:
        problems.append("ingr_cat 테이블이 남아 있음")
    leaked = sorted(key for key in columns
                    if key[1] == "ingr_cat_id" or (key[1] == "rcp_cat_id" and key[0] not in ("rcp_cat", "rcp_cat_rel")))
    if leaked:
        problems.append(f"제거 대상 분류 컬럼 잔존: {leaked}")
    for key, definition in catalog_columns(connection, source).items():
        if key[0] == "ingr_cat" or key in DROPPED_COLUMNS:
            continue
        if columns.get(key) != definition:
            problems.append(f"이관 컬럼 형식 불일치 {key}: 원본 {definition} / 대상 {columns.get(key)}")
    uncommented = connection.execute(
        "SELECT count(*) AS n FROM pg_class t JOIN pg_namespace n ON n.oid = t.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = t.oid WHERE n.nspname = %s AND t.relkind = 'r' "
        "AND a.attnum > 0 AND NOT a.attisdropped AND col_description(t.oid, a.attnum) IS NULL", (target,)
    ).fetchone()["n"]
    uncommented += connection.execute(
        "SELECT count(*) AS n FROM pg_class t JOIN pg_namespace n ON n.oid = t.relnamespace "
        "WHERE n.nspname = %s AND t.relkind = 'r' AND obj_description(t.oid, 'pg_class') IS NULL", (target,)
    ).fetchone()["n"]
    if uncommented:
        problems.append(f"COMMENT 누락 {uncommented}건")
    return problems


def run_validation(connection, source: str, target: str, *, baseline: bool = True) -> list[dict]:
    """검증 SQL 결과를 기대값과 비교한다. cnt_* 는 기준 건수(baseline=False면 원본 건수), 나머지는 0."""
    sql = render_schema_sql(VALIDATION_SQL_PATH.read_text(encoding="utf-8"), target, source)
    results = []
    for row in connection.execute(sql).fetchall():
        name, actual = row["check_nm"], row["actual"]
        if name.startswith("cnt_"):
            expected = BASELINE[name] if baseline else None     # 원본 대비 일치는 diff_* 가 보장한다.
        else:
            expected = 0
        results.append({"check": name, "actual": actual, "expected": expected,
                        "ok": expected is None or actual == expected})
    return results


def print_validation(results: list[dict]) -> bool:
    """검증 항목과 실패 여부를 콘솔에 출력한다."""
    failed = [item for item in results if not item["ok"]]
    for item in results:
        mark = "OK  " if item["ok"] else "FAIL"
        expected = "-" if item["expected"] is None else item["expected"]
        print(f"  {mark} {item['check']:<44} actual={item['actual']:<8} expected={expected}")
    print(f"[검증] {len(results) - len(failed)}/{len(results)} 통과")
    return not failed


# endregion
# region 4. 백업·검증·복원 시험
# =========================================================
# 백업 / 백업 검증 / 복원 시험
# =========================================================
def _sha256(path: Path) -> str:
    """백업 파일의 SHA-256 해시를 계산한다."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(connection, source: str, out_dir: Path) -> dict:
    """원본 스키마 전체(전 테이블 행, 시퀀스 상태, 정의·COMMENT)를 한 스냅샷으로 파일에 남긴다(읽기 전용)."""
    validate_schema_name(source)
    out_dir.mkdir(parents=True, exist_ok=False)          # 기존 백업 폴더를 덮어쓰지 않는다.
    with read_only(connection):
        pks = catalog_pks(connection, source)
        tables = catalog_tables(connection, source)
        if sorted(pks) != tables:
            raise RebuildError(f"PK 없는 테이블이 있어 정렬 백업 불가: {sorted(set(tables) - set(pks))}")
        snapshot = connection.execute(
            "SELECT now() AS snapshot_at, pg_current_snapshot()::text AS snapshot").fetchone()
        files = {}
        for table in tables:
            path = out_dir / f"{table}.csv"
            order = ", ".join(pks[table])
            with path.open("wb") as file, connection.cursor().copy(
                    f"COPY (SELECT * FROM {source}.{table} ORDER BY {order}) "
                    f"TO STDOUT WITH (FORMAT csv, HEADER true, FORCE_QUOTE *)") as copy:
                for data in copy:
                    file.write(data)
            files[path.name] = {"table": table, "sha256": _sha256(path)}
        fingerprints = table_fingerprints(connection, source, pks)
        for item in files.values():
            item.update(fingerprints[item["table"]])
        sequences = []
        for row in connection.execute(
                "SELECT sequencename, start_value, min_value, max_value, increment_by, cycle, cache_size "
                "FROM pg_sequences WHERE schemaname = %s ORDER BY sequencename", (source,)).fetchall():
            state = connection.execute(f"SELECT last_value, is_called FROM {source}.{row['sequencename']}").fetchone()
            sequences.append({**row, **state})
        catalog = {
            "pks": pks,
            "columns": [dict(r) for r in connection.execute(
                "SELECT table_name, ordinal_position, column_name, data_type, character_maximum_length, "
                "numeric_precision, numeric_scale, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (source,))],
            "constraints": [dict(r) for r in connection.execute(
                "SELECT conrelid::regclass::text AS table_name, conname, pg_get_constraintdef(oid) AS definition "
                "FROM pg_constraint WHERE connamespace = to_regnamespace(%s) ORDER BY 1, 2", (source,))],
            "indexes": [dict(r) for r in connection.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s ORDER BY 1", (source,))],
            "comments": [dict(r) for r in connection.execute(
                "SELECT t.relname AS table_name, a.attname AS column_name, "
                "coalesce(col_description(t.oid, a.attnum), '') AS column_comment, "
                "coalesce(obj_description(t.oid, 'pg_class'), '') AS table_comment "
                "FROM pg_class t JOIN pg_attribute a ON a.attrelid = t.oid "
                "WHERE t.relnamespace = to_regnamespace(%s) AND t.relkind = 'r' AND a.attnum > 0 "
                "AND NOT a.attisdropped ORDER BY 1, a.attnum", (source,))],
            "functions": [dict(r) for r in connection.execute(
                "SELECT p.oid::regprocedure::text AS signature, pg_get_functiondef(p.oid) AS definition "
                "FROM pg_proc p WHERE p.pronamespace = to_regnamespace(%s)", (source,))],
            "objects": catalog_objects(connection, source),
            "sequences": sequences,
        }
        target = describe_target(connection)
    references = {}
    for path in (SOURCE_CSV_PATH, *sorted(SEED_DIR.glob("*.csv")), LEGACY_DDL_PATH):
        if path.is_file():
            references[str(path.relative_to(project_root())).replace("\\", "/")] = _sha256(path)
    catalog_path = out_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    manifest = {
        "format": "recipe-rebuild-backup/1",
        "source_schema": source,
        "database": target,
        "snapshot_at": str(snapshot["snapshot_at"]),
        "snapshot": snapshot["snapshot"],
        "files": files,
        "catalog_sha256": _sha256(catalog_path),
        "reference_files": references,
        "restore": "restore-test --dir <이 폴더>: recipe_schema_review.sql(기존 모델 DDL) + COPY FROM으로 복원",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
                                           encoding="utf-8")
    return manifest


def load_manifest(backup_dir: Path) -> dict:
    """백업 폴더의 manifest를 읽어 복원 검증에 전달한다."""
    path = backup_dir / "manifest.json"
    if not path.is_file():
        raise RebuildError(f"백업 manifest 없음: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_backup_files(backup_dir: Path) -> list[str]:
    """파일 해시와 CSV 레코드 수가 manifest와 같은지 확인한다(DB 불필요). Returns 문제 목록."""
    manifest = load_manifest(backup_dir)
    problems = []
    if set(item["table"] for item in manifest["files"].values()) != set(LEGACY_PKS):
        problems.append("백업 테이블 목록이 기존 11개 테이블과 다름")
    if _sha256(backup_dir / "catalog.json") != manifest["catalog_sha256"]:
        problems.append("catalog.json 해시 불일치")
    for name, item in manifest["files"].items():
        path = backup_dir / name
        if not path.is_file():
            problems.append(f"{name} 없음")
            continue
        if _sha256(path) != item["sha256"]:
            problems.append(f"{name} 해시 불일치")
        with path.open(encoding="utf-8", newline="") as file:
            records = sum(1 for _ in csv.reader(file)) - 1
        if records != item["rows"]:
            problems.append(f"{name} 레코드 {records} != {item['rows']}")
    return problems


def verify_backup_live(connection, backup_dir: Path) -> list[str]:
    """백업 이후 원본 스키마가 바뀌지 않았는지(행 수·행 md5) 확인한다(읽기 전용)."""
    manifest = load_manifest(backup_dir)
    source = manifest["source_schema"]
    target = describe_target(connection)
    problems = []
    if (target["host"], target["dbname"]) != (manifest["database"]["host"], manifest["database"]["dbname"]):
        problems.append("백업한 DB와 현재 연결 대상이 다름")
    with read_only(connection):
        live = table_fingerprints(connection, source, catalog_pks(connection, source))
    for item in manifest["files"].values():
        if live.get(item["table"]) != {"rows": item["rows"], "md5": item["md5"]}:
            problems.append(f"{source}.{item['table']} 이 백업 이후 변경됨")
    return problems


def restore_test(connection, backup_dir: Path, schema: str, *, keep: bool = False) -> list[str]:
    """백업 파일을 기존 모델 DDL로 만든 임시 스키마에 COPY로 복원해 원본 md5와 비교한다.

    ``keep=False`` 면 결과와 관계없이 ROLLBACK한다(DB에 아무것도 남기지 않음).
    """
    manifest = load_manifest(backup_dir)
    validate_schema_name(schema)
    if schema in (DEFAULT_SCHEMA, manifest["source_schema"]):
        raise RebuildError("복원 시험 스키마는 운영·원본 스키마와 달라야 함")
    problems = verify_backup_files(backup_dir)
    if problems:
        return problems
    catalog = json.loads((backup_dir / "catalog.json").read_text(encoding="utf-8"))
    from psycopg import Rollback

    with connection.transaction():
        connection.execute(f"CREATE SCHEMA {schema}")
        connection.execute(f"COMMENT ON SCHEMA {schema} IS '{SCHEMA_MARKER}:restore-test'")
        connection.execute(render_schema_sql(LEGACY_DDL_PATH.read_text(encoding="utf-8"), schema))
        for name, item in manifest["files"].items():
            with (backup_dir / name).open("rb") as file, connection.cursor().copy(
                    f"COPY {schema}.{item['table']} FROM STDIN WITH (FORMAT csv, HEADER true)") as copy:
                for chunk in iter(lambda: file.read(1 << 20), b""):
                    copy.write(chunk)
        for sequence in catalog["sequences"]:
            connection.execute(f"SELECT setval('{schema}.{sequence['sequencename']}', %s, %s)",
                               (sequence["last_value"], sequence["is_called"]))
        restored = table_fingerprints(connection, schema, catalog_pks(connection, schema))
        for item in manifest["files"].values():
            if restored.get(item["table"]) != {"rows": item["rows"], "md5": item["md5"]}:
                problems.append(f"{item['table']} 복원 결과가 백업 시점 원본과 다름: {restored.get(item['table'])}")
        for sequence in catalog["sequences"]:
            state = connection.execute(
                f"SELECT last_value, is_called FROM {schema}.{sequence['sequencename']}").fetchone()
            if (state["last_value"], state["is_called"]) != (sequence["last_value"], sequence["is_called"]):
                problems.append(f"{sequence['sequencename']} 시퀀스 복원 불일치")
        if catalog_pks(connection, schema) != catalog["pks"]:
            problems.append("복원 스키마 PK 정의가 백업과 다름")
        if not keep or problems:
            raise Rollback()
    return problems


# endregion
# region 5. 목표 스키마 구축과 전환·복구
# =========================================================
# 목표 스키마 구축 / 검증 / 전환 / 복구
# =========================================================
def _lock_source(connection, source: str, mode: str) -> None:
    """전환 도중 원천 스키마의 동시 변경을 막도록 잠근다."""
    for table in sorted(LEGACY_PKS):
        connection.execute(f"LOCK TABLE {source}.{table} IN {mode} MODE")


def build_target(connection, source: str, target: str, *, baseline: bool, marker: str) -> list[dict]:
    """열린 트랜잭션 안에서 대상 스키마 생성 → DDL → 이관 → 구조·데이터 검증. 실패 시 RebuildError."""
    validate_schema_name(source)
    validate_schema_name(target)
    if source == target:
        raise RebuildError("원본과 대상 스키마가 같음")
    check_legacy_source(connection, source)
    if schema_exists(connection, target):
        raise RebuildError(f"대상 스키마 {target} 가 이미 있음 — 덮어쓰지 않음")
    _lock_source(connection, source, "SHARE")
    connection.execute(f"CREATE SCHEMA {target}")
    connection.execute(f"COMMENT ON SCHEMA {target} IS '{SCHEMA_MARKER}:{marker}:source={source}'")
    connection.execute(render_schema_sql(TARGET_DDL_PATH.read_text(encoding="utf-8"), target))
    connection.execute(render_schema_sql(MIGRATION_SQL_PATH.read_text(encoding="utf-8"), target, source))
    problems = check_target_structure(connection, target, source)
    results = run_validation(connection, source, target, baseline=baseline)
    print(f"[구조 검사] {'OK' if not problems else problems}")
    passed = print_validation(results)
    if problems or not passed:
        raise RebuildError("구조 또는 데이터 검증 실패 — ROLLBACK")
    return results


def build(connection, source: str, target: str, *, baseline: bool) -> None:
    """목표 스키마를 구축하고 검증 결과를 확인한다."""
    if target == DEFAULT_SCHEMA:
        raise RebuildError("build 는 격리 스키마 전용 — 운영 스키마 전환은 cutover 명령을 사용")
    with connection.transaction():
        build_target(connection, source, target, baseline=baseline, marker="rehearsal")
    print(f"[COMMIT] {source} → {target} 구축·이관·검증 완료")


def validate(connection, source: str, target: str, *, baseline: bool) -> bool:
    """원천과 목표 스키마의 데이터 정합성을 검사한다."""
    with read_only(connection):
        problems = check_target_structure(connection, target, source)
        print(f"[구조 검사] {'OK' if not problems else problems}")
        passed = print_validation(run_validation(connection, source, target, baseline=baseline))
    return passed and not problems


def drop_schema(connection, schema: str) -> None:
    """이 도구가 만든 리허설·복원 시험 스키마만 개별 객체 DROP 후 DROP SCHEMA RESTRICT로 지운다."""
    validate_schema_name(schema)
    comment = schema_comment(connection, schema) or ""
    if schema == DEFAULT_SCHEMA or not comment.startswith(f"{SCHEMA_MARKER}:rehearsal") and \
            not comment.startswith(f"{SCHEMA_MARKER}:restore-test"):
        raise RebuildError(f"{schema} 는 이 도구가 만든 리허설/복원 시험 스키마가 아님 — 삭제하지 않음")
    with connection.transaction():
        objects = catalog_objects(connection, schema)
        unexpected = [item for item in objects if item["kind"] not in ("r", "S", "function")]
        if unexpected:
            raise RebuildError(f"예상하지 않은 객체가 있어 삭제하지 않음: {unexpected}")
        for item in objects:
            if item["kind"] == "r":
                connection.execute(f"DROP TABLE {schema}.{item['name']} RESTRICT")
        for item in objects:
            if item["kind"] == "S":
                connection.execute(f"DROP SEQUENCE {schema}.{item['name']} RESTRICT")
            elif item["kind"] == "function":
                connection.execute(f"DROP FUNCTION {item['name']} RESTRICT")
        connection.execute(f"DROP SCHEMA {schema} RESTRICT")
    print(f"[COMMIT] {schema} 삭제")


def cutover(connection, legacy_schema: str, backup_dir: Path, *, baseline: bool) -> None:
    """운영 ``recipe`` 를 ``legacy_schema`` 로 이름만 바꿔 보존하고, 그 데이터로 새 ``recipe`` 를 만든다.

    이름 변경·생성·이관·검증이 한 트랜잭션이라 검증 실패 시 이름 변경까지 ROLLBACK된다. 기존 행은 삭제하지 않는다.
    """
    validate_schema_name(legacy_schema)
    if schema_exists(connection, legacy_schema):
        raise RebuildError(f"보존 스키마 이름 {legacy_schema} 가 이미 있음")
    manifest = load_manifest(backup_dir)
    if manifest["source_schema"] != DEFAULT_SCHEMA:
        raise RebuildError("전환 전 백업은 recipe 스키마 백업이어야 함")
    problems = verify_backup_files(backup_dir) + verify_backup_live(connection, backup_dir)
    if problems:
        raise RebuildError(f"백업 검증 실패 — 전환하지 않음: {problems}")
    print(f"[백업 확인] {backup_dir} 파일·해시·현재 데이터 일치")
    with connection.transaction():
        check_legacy_source(connection, DEFAULT_SCHEMA)
        _lock_source(connection, DEFAULT_SCHEMA, "ACCESS EXCLUSIVE")     # 전환 중 기존 모델 읽기·쓰기 차단
        connection.execute(f"ALTER SCHEMA {DEFAULT_SCHEMA} RENAME TO {legacy_schema}")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        connection.execute(f"COMMENT ON SCHEMA {legacy_schema} IS "
                           f"'{SCHEMA_MARKER}:legacy:기존 모델 보존(전환 {stamp}, 백업 {backup_dir.name})'")
        build_target(connection, legacy_schema, DEFAULT_SCHEMA, baseline=baseline, marker="cutover")
        connection.execute(f"COMMENT ON SCHEMA {DEFAULT_SCHEMA} IS "
                           f"'식약처 레시피 GraphRAG 목표 모델(전환 {stamp}, 원본 보존 {legacy_schema})'")
    print(f"[COMMIT] 전환 완료: {DEFAULT_SCHEMA}(목표 모델), 기존 모델 보존 {legacy_schema}")


def rollback_cutover(connection, legacy_schema: str) -> str:
    """전환을 되돌린다: 새 ``recipe`` 를 ``recipe_failed_<시각>`` 으로, 보존 스키마를 ``recipe`` 로 이름만 바꾼다."""
    validate_schema_name(legacy_schema)
    if not (schema_comment(connection, legacy_schema) or "").startswith(f"{SCHEMA_MARKER}:legacy"):
        raise RebuildError(f"{legacy_schema} 는 cutover가 남긴 보존 스키마가 아님")
    failed = f"{DEFAULT_SCHEMA}_failed_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    with connection.transaction():
        check_legacy_source(connection, legacy_schema)
        connection.execute(f"ALTER SCHEMA {DEFAULT_SCHEMA} RENAME TO {failed}")
        connection.execute(f"COMMENT ON SCHEMA {failed} IS '{SCHEMA_MARKER}:rehearsal:rolled-back target'")
        connection.execute(f"ALTER SCHEMA {legacy_schema} RENAME TO {DEFAULT_SCHEMA}")
        connection.execute(f"COMMENT ON SCHEMA {DEFAULT_SCHEMA} IS NULL")
    print(f"[COMMIT] 복구 완료: {DEFAULT_SCHEMA}=기존 모델, 실패한 목표 모델은 {failed} 로 보존")
    return failed


# endregion
# region 6. CLI 옵션과 명령 분기
# =========================================================
# 명령별 확인 플래그를 검사한 뒤 해당 작업에만 진입
# =========================================================
def parse_args(argv=None) -> argparse.Namespace:
    """백업·구축·전환·복구 명령과 필수 확인 인자를 파싱한다."""
    parser = argparse.ArgumentParser(description="레시피 PostgreSQL 목표 모델 재구축")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("inspect", help="연결 대상과 스키마 상태 출력(읽기 전용, 기본)")
    p = sub.add_parser("backup", help="원본 스키마를 파일로 백업(읽기 전용)")
    p.add_argument("--source", default=DEFAULT_SCHEMA)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("verify-backup", help="백업 파일 해시·건수 확인, --live면 현재 DB와도 비교")
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--live", action="store_true")
    p = sub.add_parser("restore-test", help="백업을 임시 스키마에 복원·비교 후 ROLLBACK")
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--schema", default="recipe_restore_chk")
    p.add_argument("--confirm-db")
    p = sub.add_parser("build", help="격리 스키마에 목표 모델 구축·이관·검증(한 트랜잭션)")
    p.add_argument("--source", default=DEFAULT_SCHEMA)
    p.add_argument("--target", required=True)
    p.add_argument("--confirm-db")
    p.add_argument("--no-baseline", action="store_true")
    p = sub.add_parser("validate", help="원본·대상 비교 검증(읽기 전용)")
    p.add_argument("--source", required=True)
    p.add_argument("--target", default=DEFAULT_SCHEMA)
    p.add_argument("--no-baseline", action="store_true")
    p = sub.add_parser("drop-schema", help="이 도구가 만든 리허설 스키마 삭제")
    p.add_argument("--schema", required=True)
    p.add_argument("--confirm-schema", required=True)
    p.add_argument("--confirm-db")
    p = sub.add_parser("cutover", help="recipe → 보존 스키마 이름 변경 + 새 recipe 구축(한 트랜잭션)")
    p.add_argument("--legacy-schema", required=True)
    p.add_argument("--backup-dir", type=Path, required=True)
    p.add_argument("--confirm-cutover", action="store_true")
    p.add_argument("--confirm-db")
    p.add_argument("--no-baseline", action="store_true")
    p = sub.add_parser("rollback-cutover", help="전환 되돌리기(이름 변경만, 삭제 없음)")
    p.add_argument("--legacy-schema", required=True)
    p.add_argument("--confirm-rollback", action="store_true")
    p.add_argument("--confirm-db")
    args = parser.parse_args(argv)
    args.command = args.command or "inspect"
    return args


def inspect(connection) -> None:
    """대상 DB와 스키마 상태를 변경 없이 출력한다."""
    target = describe_target(connection)
    print(f"[대상 DB] {target_label(target)} port={target['port']} user={target['db_user']} "
          f"server={target['server_version']}")
    for row in connection.execute(
            "SELECT nspname, obj_description(oid, 'pg_namespace') AS c FROM pg_namespace "
            "WHERE nspname LIKE 'recipe%%' ORDER BY 1").fetchall():
        pks = catalog_pks(connection, row["nspname"])
        model = "legacy" if pks == LEGACY_PKS else "target" if pks == TARGET_PKS else "other"
        print(f"  schema {row['nspname']:<28} model={model:<7} tables={len(pks)} comment={row['c']}")


def main(argv=None) -> int:
    """선택한 재구축 명령을 실행하고 성공 또는 실패 종료 코드를 반환한다."""
    args = parse_args(argv)
    try:
        if args.command == "verify-backup" and not args.live:
            problems = verify_backup_files(args.dir)
            print("[백업 파일] " + ("OK" if not problems else str(problems)))
            return 0 if not problems else 1
        with connect() as connection:
            if args.command == "inspect":
                inspect(connection)
            elif args.command == "backup":
                manifest = backup(connection, args.source, args.out)
                print(f"[백업 완료] {args.out} snapshot={manifest['snapshot_at']}")
                for name, item in manifest["files"].items():
                    print(f"  {name:<24} rows={item['rows']:<7} sha256={item['sha256'][:16]}…")
            elif args.command == "verify-backup":
                problems = verify_backup_files(args.dir) + verify_backup_live(connection, args.dir)
                print("[백업 검증] " + ("OK (파일·해시·현재 데이터 일치)" if not problems else str(problems)))
                return 0 if not problems else 1
            elif args.command == "restore-test":
                require_confirmed_db(connection, args.confirm_db)
                problems = restore_test(connection, args.dir, args.schema)
                print("[복원 시험] " + ("OK (전 테이블 행 md5·시퀀스·PK 일치, ROLLBACK)" if not problems else str(problems)))
                return 0 if not problems else 1
            elif args.command == "build":
                require_confirmed_db(connection, args.confirm_db)
                build(connection, args.source, args.target, baseline=not args.no_baseline)
            elif args.command == "validate":
                return 0 if validate(connection, args.source, args.target, baseline=not args.no_baseline) else 1
            elif args.command == "drop-schema":
                if args.schema != args.confirm_schema:
                    raise RebuildError("--confirm-schema 가 --schema 와 다름")
                require_confirmed_db(connection, args.confirm_db)
                drop_schema(connection, args.schema)
            elif args.command == "cutover":
                if not args.confirm_cutover:
                    raise RebuildError("--confirm-cutover 가 없어 전환하지 않음")
                require_confirmed_db(connection, args.confirm_db)
                cutover(connection, args.legacy_schema, args.backup_dir, baseline=not args.no_baseline)
            elif args.command == "rollback-cutover":
                if not args.confirm_rollback:
                    raise RebuildError("--confirm-rollback 이 없어 복구하지 않음")
                require_confirmed_db(connection, args.confirm_db)
                rollback_cutover(connection, args.legacy_schema)
        return 0
    except RebuildError as error:
        print(f"[중단] {error}")
        return 1
    except Exception as error:
        print(f"[중단] {type(error).__name__}: {safe_error(error)}")
        return 2


# endregion
# region 7. 직접 실행 진입점
if __name__ == "__main__":
    raise SystemExit(main())

# endregion
