"""레시피 조회 CLI 진입점 (읽기 전용).

과제 폴더(``recipe_recommender`` 와 ``common`` 이 있는 폴더)에서 실행한다:
    python -m recipe_recommender.search_recipe --rcp-seq 28            # 원본 번호로 상세(단계·사용 식재료)
    python -m recipe_recommender.search_recipe --rcp-id 20261022_000001 # 내부 레시피 ID로 상세
    python -m recipe_recommender.search_recipe --name "양배추롤"         # 레시피명 부분 일치
    python -m recipe_recommender.search_recipe --category 반찬 --cook-method 찌기 --page 2
    python -m recipe_recommender.search_recipe --ingredient "칵테일새우"  # 식재료(별칭 가능) 사용 레시피

이 파일은 옵션 파싱·Service 호출·결과 출력만 한다. 조회는 ``RecipeSearchService`` 가 담당한다.
"""

from __future__ import annotations

import argparse
import logging

from .database import create_recipe_sql_session
from .recipe_search_service import DEFAULT_PAGE_SIZE, RecipeSearchError, RecipeSearchService


# region 1. CLI 인수와 조회 결과 출력
# =========================================================
# 조회 대상 선택 및 화면 출력
# =========================================================

def parse_args(argv=None) -> argparse.Namespace:
    """CLI 조회 조건과 출력 옵션을 파싱한다."""
    parser = argparse.ArgumentParser(description="recipe 스키마 레시피 조회")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--rcp-seq", help="식약처 원본 레시피 번호로 상세 조회")
    target.add_argument("--rcp-id", help="내부 레시피 ID로 상세 조회")
    target.add_argument("--name", help="레시피명 부분 일치 검색")
    target.add_argument("--category", help="요리 분류명 검색(예: 반찬)")
    target.add_argument("--cook-method", help="조리 방법 검색: COOK_MTHD 코드(예: 000004) 또는 명칭(예: 찌기)")
    target.add_argument("--ingredient", help="표준 식재료명 또는 별칭으로 사용 레시피 검색")
    parser.add_argument("--and-category", dest="filter_category", help="--name/--cook-method와 함께 쓸 요리 종류 조건")
    parser.add_argument("--and-cook-method", dest="filter_cook_method", help="--name/--category와 함께 쓸 조리 방법 조건(코드 또는 명칭)")
    parser.add_argument("--schema", help="대상 스키마(기본: 환경변수 RECIPE_DB_SCHEMA 또는 recipe)")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    return parser.parse_args(argv)


def _print_rows(rows: list[dict], columns: list[str]) -> None:
    """조회 행에서 요청한 컬럼만 골라 콘솔에 출력한다."""
    for row in rows:
        print("  " + " | ".join(f"{row.get(column)}" for column in columns))


def print_detail(detail: dict) -> None:
    """레시피 상세와 단계·재료 목록을 콘솔에 출력한다."""
    recipe = detail["recipe"]
    print(f"[레시피] RCP_SEQ={recipe['rcpSeq']}  rcp_id={recipe['rcpId']}  {recipe['rcpNm']}")
    print(f"  요리 분류 {recipe['rcpCatNm']}({recipe['rcpCatIds']}) · 조리 방법 {recipe['cookMthdNm']}"
          f" · {recipe['rcpEnergyKcal']}kcal 탄{recipe['rcpCarbsG']} 단{recipe['rcpProteinG']}"
          f" 지{recipe['rcpFatG']} 나트륨{recipe['rcpSodiumMg']} ({recipe['rcpNutritionStatus']})")
    print(f"  원본 회차 {recipe['rcpRawId']} 행 {recipe['rcpRawSeq']}")
    print(f"[조리 단계] {len(detail['steps'])}")
    _print_rows(detail["steps"], ["stepNo", "rcpStepInstructionTxt"])
    print(f"[사용 식재료] {len(detail['ingredients'])}")
    _print_rows(detail["ingredients"], ["ingrId", "ingrNm", "occurrenceCount", "rawTexts"])
    print(f"[표준 식재료 미연결 원문] {len(detail['unmatchedIngredients'])}")
    _print_rows(detail["unmatchedIngredients"], ["rcpIngrLineNo", "rcpIngrRawTxt", "rcpIngrStatus"])


def print_page(result: dict, columns: list[str]) -> None:
    """페이지형 조회 결과의 행과 건수 정보를 출력한다."""
    print(f"[검색 결과] 전체 {result['totalCount']}건 · page {result['page']} (size {result['pageSize']})")
    _print_rows(result["items"], columns)


# endregion


# region 2. PostgreSQL 조회 실행 및 종료
# =========================================================
# CLI 요청을 RecipeSearchService 호출로 전달
# =========================================================

def main(argv=None) -> int:
    """조회 세션과 Service를 만들고 CLI 요청을 실행한 뒤 종료 코드를 반환한다."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    sql_session = create_recipe_sql_session(schema=args.schema)
    service = RecipeSearchService(sql_session=sql_session)
    try:
        if args.rcp_seq or args.rcp_id:
            detail = service.get_recipe_detail(rcp_seq=args.rcp_seq, rcp_id=args.rcp_id)
            if detail is None:
                print("레시피가 없습니다.")
                return 3
            print_detail(detail)
        elif args.ingredient:
            result = service.search_recipes_by_ingredient(args.ingredient, args.page, args.page_size)
            if result is None:
                print(f"'{args.ingredient}' 에 해당하는 표준 식재료가 없습니다(검토 보류 원문일 수 있음).")
                return 3
            ingredient = result["ingredient"]
            aliases = ", ".join(alias["ingrAlsNm"] for alias in result["aliases"]) or "-"
            print(f"[표준 식재료] {ingredient['ingrNm']} ({ingredient['ingrId']}) "
                  f"일치={ingredient['matchedBy']} 별칭={aliases}")
            print_page(result, ["rcpSeq", "rcpId", "rcpNm", "rcpCatNm", "cookMthdCd", "cookMthdNm"])
        else:
            result = service.search_recipes(
                name=args.name,
                category=args.category or args.filter_category,
                cook_method=args.cook_method or args.filter_cook_method,
                page=args.page,
                page_size=args.page_size,
            )
            print_page(result, ["rcpSeq", "rcpId", "rcpNm", "rcpCatNm", "cookMthdCd", "cookMthdNm", "ingredientCount"])
    except RecipeSearchError as error:
        print(f"[조회 조건 오류] {error}")
        return 1
    finally:
        sql_session.database_manager.close()
    return 0


# =========================================================
# 직접 실행 진입점: Service와 DB 세션은 main() 호출 시 생성한다.
# =========================================================
if __name__ == "__main__":
    raise SystemExit(main())

# endregion
