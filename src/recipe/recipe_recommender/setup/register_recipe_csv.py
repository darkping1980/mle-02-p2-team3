"""식약처 레시피 CSV 등록 CLI 진입점.

과제 폴더(``recipe_recommender`` 와 ``common`` 이 있는 폴더)에서 실행한다:
    python -m recipe_recommender.setup.register_recipe_csv                    # 기본: --dry-run (DB 변경 없음)
    python -m recipe_recommender.setup.register_recipe_csv --limit 10         # 앞 10건 실제 적재
    python -m recipe_recommender.setup.register_recipe_csv --full             # 전체 적재
    python -m recipe_recommender.setup.register_recipe_csv --full --dry-run   # 전체를 검사만
    python -m recipe_recommender.setup.register_recipe_csv --full --rehearse  # 전체를 실제처럼 쓰고 검증 후 ROLLBACK
    python -m recipe_recommender.setup.register_recipe_csv --full --schema recipe_v2   # 격리 스키마 대상

이 파일은 옵션 파싱·Service 호출·결과 출력만 한다. 검증·매핑·트랜잭션은 ``RecipeRegisterService`` 가,
SQL 호출은 ``RecipeRepository`` → ``recipe.sql`` → ``PostgresDbSession`` 이 담당한다.
테이블 삭제·재생성은 하지 않는다(목표 모델 재구축은 ``tools/recipe_rebuild.py`` 전용).
대상 스키마가 목표 모델(rcp_cat_rel 있음, ingr_cat 없음)이 아니면 dry-run을 포함해 중단한다.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..config import load_project_environment, project_root
from ..database import create_recipe_sql_session
from .recipe_register_service import RecipeLoadError, RecipeLoadResult, RecipeRegisterService

DEFAULT_CSV_PATH = project_root() / "src" / "data" / "COOKRCP01.csv"
TABLE_ORDER = ("rcpRaw", "rcpCat", "commonCodeGrp", "commonCd", "rcp", "rcpCatRel", "rcpStep",
               "ingr", "ingrAls", "rcpIngrStg", "rcpIngr")


# region 1. CLI 옵션과 결과 표시
def parse_args(argv=None) -> argparse.Namespace:
    """CSV 경로와 적재·리허설 옵션을 CLI에서 읽는다."""
    parser = argparse.ArgumentParser(description="COOKRCP01.csv → Supabase recipe 스키마 적재")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help=f"CSV 경로 (기본: {DEFAULT_CSV_PATH})")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--limit", type=int, metavar="N", help="앞에서부터 N건 적재")
    scope.add_argument("--full", action="store_true", help="CSV 전체 적재")
    parser.add_argument("--dry-run", action="store_true", help="검사와 매핑만 수행하고 DB를 변경하지 않음")
    parser.add_argument("--rehearse", action="store_true",
                        help="실제와 같이 쓰고 집계·정합성까지 확인한 뒤 전체 ROLLBACK(--limit/--full 필요)")
    parser.add_argument("--schema", help="대상 스키마(기본: 환경변수 RECIPE_DB_SCHEMA 또는 recipe)")
    parser.add_argument("--sql-log", action="store_true", help="SQL 상세 로그 출력(대량 적재 시 느려짐)")
    parser.add_argument("--show", type=int, default=10, metavar="N", help="검토 목록 표시 건수 (기본 10)")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.rehearse and (args.dry_run or (args.limit is None and not args.full)):
        parser.error("--rehearse needs --limit or --full and cannot be combined with --dry-run")
    # 범위(--limit/--full)를 지정하지 않으면 안전하게 dry-run으로 동작한다.
    if args.limit is None and not args.full:
        args.dry_run = True
    return args


def _print_list(title: str, items: list[str], show: int) -> None:
    """검토 항목의 제목과 지정한 개수만큼의 예시를 출력한다."""
    print(f"  {title}: {len(items)}")
    for item in items[:show]:
        print(f"    - {item}")
    if len(items) > show:
        print(f"    ... ({len(items) - show}건 더)")


def print_report(result: RecipeLoadResult, show: int) -> None:
    """검증 계획과 등록 결과의 건수·오류를 콘솔에 출력한다."""
    plan = result.plan
    print("=" * 72)
    mode = "DRY-RUN (DB 변경 없음)" if result.dry_run else "REHEARSAL (ROLLBACK됨)" if result.rolled_back else "LOAD"
    print(f"[레시피 CSV 적재 결과] mode={mode}")
    if result.rcp_raw_id:
        print(f"  rcp_raw_id={result.rcp_raw_id} ({result.batch_mode})")
    written = result.written
    print("-" * 72)
    print(f"  CSV 원본 건수(적재 대상)       : {plan.source_row_count}")
    print(f"  rcp_cat / common_code_grp / common_cd 등록: "
          f"{written.get('rcp_cat', '-')} / {written.get('common_code_grp', '-')} / {written.get('common_cd', '-')}")
    print(f"  rcp_raw 후보 / 이번 등록       : {len(plan.raw_rows)} / {written.get('rcp_raw', '-')}")
    print(f"  rcp 후보 / 신규 등록 / 갱신    : {len(plan.recipes)} / {written.get('rcp_insert', '-')} / {written.get('rcp_update', '-')}")
    print(f"  rcp_cat_rel 후보 / 이번 등록   : {len(plan.category_relations)} / {written.get('rcp_cat_rel', '-')}")
    print(f"  rcp_step 후보 / 등록·갱신      : {len(plan.steps)} / {written.get('rcp_step', '-')}")
    print(f"  rcp_ingr_stg 후보 / 이번 등록  : {len(plan.stagings)} / {written.get('rcp_ingr_stg', '-')}")
    print(f"  ingr / ingr_als 등록           : "
          f"{written.get('ingr', '-')} / {written.get('ingr_als', '-')} (검토된 식재료 사전)")
    print(f"  staging 자동 승인 건수         : {written.get('rcp_ingr_stg_auto_approved', '-')} (표준명·별칭 정확 일치만)")
    print(f"  rcp_ingr 등록·갱신 건수        : {written.get('rcp_ingr', '-')} (승인된 staging만, 레시피별 중복 제거)")
    print(f"  재료 파싱 상태별 건수          : {plan.parse_status_counts}")
    print(f"  검토 보류 건수                 : 영양 {len(plan.nutrition_reviews)}, 분류충돌 {len(plan.category_conflicts)}, "
          f"단계 {len(plan.step_issues)}, 식재료 사전충돌 {len(result.ingredient_conflicts)}")
    print(f"  오류 건수                      : {len(plan.blocking_errors)}")
    print("-" * 72)
    _print_list("영양정보 REVIEW_REQUIRED", plan.nutrition_reviews, show)
    _print_list("요리 분류 변경(관계 미변경)", plan.category_conflicts, show)
    _print_list("식재료 사전 충돌(미갱신)", result.ingredient_conflicts, show)
    _print_list("조리 단계 특이사항", plan.step_issues, show)
    _print_list("DB에만 있는 단계(삭제 안 함)", result.stale_steps, show)
    _print_list("재료 원문 없음", plan.recipes_without_parts, show)
    if result.batch_counts:
        print("-" * 72)
        print(f"  회차 {result.rcp_raw_id} 기준 건수: {result.batch_counts}")
    if result.table_counts_before:
        print("-" * 72)
        print("  테이블       적재 전  →  적재 후")
        for key in TABLE_ORDER:
            after = result.table_counts_after[key] if result.table_counts_after else "-"
            print(f"  {key:<12} {result.table_counts_before[key]:>7}  →  {after:>7}")
    if result.integrity:
        print("-" * 72)
        violations = {key: value for key, value in result.integrity.items() if value}
        print(f"  정합성 검사: {'OK (모든 항목 0건)' if not violations else violations}")
    print("=" * 72)


# endregion
# region 2. 식약처 CSV 등록 실행
# =========================================================
# 기본 dry-run → RecipeRegisterService → 결과·종료 코드
# =========================================================
def main(argv=None) -> int:
    """CSV 적재 Service를 실행하고 결과에 따른 종료 코드를 반환한다."""
    args = parse_args(argv)
    load_project_environment()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not args.sql_log:
        # execute()/execute_many()는 sql_log_mode=none이어도 SQL 로그를 강제 출력하므로 logger 수준으로 끈다.
        logging.getLogger("car_search_rag.sql").setLevel(logging.WARNING)
    logging.getLogger("car_search_rag.database").setLevel(logging.WARNING)

    sql_session = create_recipe_sql_session(sql_log=args.sql_log, schema=args.schema)
    print(f"[대상 스키마] {sql_session.recipe_schema}")
    service = RecipeRegisterService(sql_session=sql_session)
    try:
        result = service.register(args.csv, limit=args.limit, dry_run=args.dry_run, rehearse=args.rehearse)
    except RecipeLoadError as error:
        print(f"[중단] 데이터 검증 실패 — DB는 변경되지 않았습니다(트랜잭션 ROLLBACK 또는 미시작).\n  {error}")
        return 1
    except Exception as error:  # DB 오류: transaction()이 이미 ROLLBACK했다.
        print(f"[중단] DB 처리 오류 — 트랜잭션 ROLLBACK.\n  {type(error).__name__}: {error}")
        return 2
    finally:
        sql_session.database_manager.close()
    print_report(result, args.show)
    if result.rolled_back:
        print("ROLLBACK 완료(리허설: DB 변경 없음)")
    elif not result.dry_run:
        print("COMMIT 완료")
    violations = {key: value for key, value in (result.integrity or {}).items() if value}
    return 3 if violations else 0


# endregion
# region 3. 직접 실행 진입점
# import만 할 때는 DB 등록을 시작하지 않는다.
if __name__ == "__main__":
    raise SystemExit(main())

# endregion
