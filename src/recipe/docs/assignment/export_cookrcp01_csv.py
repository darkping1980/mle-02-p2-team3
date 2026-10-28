"""제출용 CSV 재생성 도구 — PostgreSQL ``recipe.rcp_raw`` → ``COOKRCP01`` 형식 CSV (DB 읽기 전용).

과제 제출용 보조 스크립트이며 앱 기능이 아니다. 원본 다운로드 파일 ``COOKRCP01.csv`` 가 없는 환경에서,
원본 55열을 문자열 그대로 보관한 ``rcp_raw`` 로 같은 내용의 CSV를 다시 만든다.

    python docs/assignment/export_cookrcp01_csv.py            (과제 폴더에서 실행)

- 컬럼 순서: 등록 코드의 ``RecipeRegisterService.SOURCE_COLUMNS`` (원본 헤더 55개 순서)
- 행 순서: ``rcp_raw_seq`` (원본 CSV 행 위치 000001~)
- 값: ``rcp_raw`` 는 빈 문자열만 NULL로 저장하므로 NULL → 빈 문자열로 되돌린다. 그 밖의 값은 수정하지 않는다.
- 형식: UTF-8 BOM, 최소 인용(QUOTE_MINIMAL), 줄 끝 CRLF. **원본과 바이트 단위로 같지 않다**
  (원본 크기·SHA-256 기록과 비교해 다름을 확인함). 필드 값 단위로만 원본과 같다.

검증(모두 통과해야 파일을 남긴다):
  1. 1,156행 × 55열, ``rcp_raw_seq`` 가 000001부터 빈틈없이 이어짐
  2. 프로젝트 CSV 검증기 ``RecipeRegisterService.read_csv`` + ``validate_rows`` 통과(헤더·행 수·RCP_SEQ)
  3. 다시 읽은 CSV 값 = ``rcp_raw`` 값(모든 칸), 컬럼별 빈칸 수 동일
"""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.config import load_project_environment, prepare_common_imports  # noqa: E402
from recipe_recommender.setup.recipe_register_service import (  # noqa: E402
    EXPECTED_SOURCE_ROW_COUNT, SOURCE_COLUMNS, RecipeRegisterService,
)

OUTPUT = Path(__file__).resolve().parent / "data" / "COOKRCP01_regenerated_from_rcp_raw.csv"


# region 1. PostgreSQL 원본 행 조회
# =========================================================
# rcp_raw를 읽기 전용 스냅샷으로 조회
# =========================================================

def read_rcp_raw() -> list[dict]:
    """``rcp_raw`` 원본 55열을 READ ONLY 트랜잭션으로 행 순번 순서대로 읽는다(쓰기 없음)."""
    load_project_environment()
    prepare_common_imports()
    from common.database_manager import DatabaseManager

    columns = ", ".join(name.lower() for name in SOURCE_COLUMNS)
    manager = DatabaseManager()
    try:
        with manager.connect(camel_case_keys=False) as conn:
            conn.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                return [dict(row) for row in conn.execute(
                    f"SELECT rcp_raw_seq, {columns} FROM recipe.rcp_raw ORDER BY rcp_raw_seq").fetchall()]
            finally:
                conn.rollback()
    finally:
        manager.close()


# endregion


# region 2. CSV 재생성과 왕복 검증
# =========================================================
# 원본 행의 순서와 필드 값을 확인한 뒤 제출용 파일 생성
# =========================================================

def main() -> int:
    """CSV를 만들고 검증 결과를 출력한다. 검증에 실패하면 파일을 지우고 1을 반환한다."""
    rows = read_rcp_raw()
    sequences = [row["rcp_raw_seq"] for row in rows]
    assert len(rows) == EXPECTED_SOURCE_ROW_COUNT, f"행 수 {len(rows)} != {EXPECTED_SOURCE_ROW_COUNT}"
    assert sequences == [f"{i:06d}" for i in range(1, len(rows) + 1)], "rcp_raw_seq가 연속되지 않음"
    values = [["" if row[name.lower()] is None else row[name.lower()] for name in SOURCE_COLUMNS] for row in rows]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, lineterminator="\r\n")
        writer.writerow(SOURCE_COLUMNS)
        writer.writerows(values)
    try:
        parsed = RecipeRegisterService.read_csv(OUTPUT)          # 프로젝트 검증기: 헤더 55개·BOM·컬럼 수
        errors = RecipeRegisterService.validate_rows(parsed)     # 1,156행·RCP_SEQ 유일·필수 명칭 → 오류 목록
        assert not errors, f"프로젝트 CSV 검증 오류: {errors[:5]}"
        with OUTPUT.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            header = next(reader)
            back = list(reader)
        assert tuple(header) == SOURCE_COLUMNS, "헤더 순서 불일치"
        assert back == values, "다시 읽은 값이 rcp_raw와 다름"
        blanks_db = {name: sum(row[name.lower()] is None for row in rows) for name in SOURCE_COLUMNS}
        blanks_csv = {name: sum(r[i] == "" for r in back) for i, name in enumerate(SOURCE_COLUMNS)}
        assert blanks_db == blanks_csv, "컬럼별 빈칸 수 불일치"
    except Exception:
        OUTPUT.unlink(missing_ok=True)
        raise
    data = OUTPUT.read_bytes()
    print(f"파일: {OUTPUT.relative_to(TASK_DIR).as_posix()}")
    print(f"행 {len(back):,} × 열 {len(header)} / 크기 {len(data):,} bytes / SHA-256 {hashlib.sha256(data).hexdigest()}")
    print("검증: 행 순번 연속 OK · 프로젝트 CSV 검증기 OK · 값 왕복 일치 OK · 컬럼별 빈칸 수 일치 OK")
    print("주의: 원본 다운로드 파일이 아닌 rcp_raw 재생성 파일이며, 원본과 바이트 단위로 같지 않다.")
    return 0


# =========================================================
# 직접 실행 진입점: 이때만 DB 조회와 CSV 파일 생성이 시작된다.
# =========================================================
if __name__ == "__main__":
    raise SystemExit(main())

# endregion
