"""PostgreSQL 스냅샷과 Neo4j를 대조하는 CLI 진입점.

기본 실행은 사전 점검만 한다. --verify-only는 기존 그래프의 키·건수와 대표
조회까지 검사하며, --apply만 제약조건 생성과 배치 적재를 수행한다.
"""

from __future__ import annotations

import argparse
import json
import sys

if __package__ in (None, ""):
    # 파일 경로로 직접 실행할 때도 상위 폴더의 recipe_recommender 패키지를 찾게 한다.
    # python -m recipe_recommender.setup.load_recipe_graph 방식이면 이 분기는 실행되지 않는다.
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from recipe_recommender.config import load_project_environment
from recipe_recommender.setup.recipe_graph_load_service import RecipeGraphLoadService
from recipe_recommender.recipe_graph_repository import RecipeGraphRepository
from recipe_recommender.setup.recipe_graph_source_repository import RecipeGraphSourceRepository
from recipe_recommender.tools._connection_util import safe_error


# region 1. 원천 검증·그래프 적재 CLI
# =========================================================
# PostgreSQL Source Repository → 적재 Service → Neo4j Repository
# =========================================================
def main(argv: list[str] | None = None) -> int:
    """CLI 인자를 해석해 Source/Graph Repository를 Service에 주입하고 보고서를 반환한다.

    argv=None이면 argparse가 sys.argv[1:]을 읽는다. 반환 정수는 프로세스 종료 코드다.
    """
    parser = argparse.ArgumentParser(description="Validate or load the recipe Neo4j graph")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Create only recipe graph schema objects and MERGE graph data")
    mode.add_argument("--verify-only", action="store_true", help="Read-only graph/source verification")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    if args.batch_size < 1 or args.batch_size > 1000:
        parser.error("--batch-size must be between 1 and 1000")
    load_project_environment()
    graph = None
    try:
        graph = RecipeGraphRepository()
        service = RecipeGraphLoadService(RecipeGraphSourceRepository(), graph)
        prepared = service.prepare()
        inspection = service.preflight_graph(prepared)
        report = {
            "mode": "apply" if args.apply else ("verify-only" if args.verify_only else "dry-run"),
            "postgres": {
                "database": prepared.source.database, "role": prepared.source.role,
                "snapshot_at": prepared.source.observed_at.isoformat(),
                "expected": prepared.expected_counts,
                "stage_status": prepared.source.stage_status,
            },
            "neo4j": {
                "database": inspection["database"], "version": inspection["version"],
                "before_total_nodes": inspection["total_nodes"],
                "before_total_relationships": inspection["total_relationships"],
                "before_constraints": len(inspection["constraints"]),
                "before_indexes": len(inspection["indexes"]),
            },
        }
        if args.apply:
            report["first_pass"] = service.apply(prepared, args.batch_size)
            # 동일한 PostgreSQL 스냅샷으로 재적재하여 MERGE의 중복 방지 효과를 확인한다.
            report["second_pass"] = service.apply(prepared, args.batch_size)
            if report["first_pass"]["verified"] != report["second_pass"]["verified"]:
                raise ValueError("Idempotence failed: graph counts differ after second pass")
            report["representative_examples"] = service.verify_examples(prepared)
            report["query_examples"] = service.verify_query_examples(prepared)
            report["search_scenarios"] = service.verify_search_scenarios(prepared)
            report["after_schema"] = {
                "constraints": len(graph.inspect()["constraints"]),
                "indexes": len(graph.inspect()["indexes"]),
            }
        elif args.verify_only:
            report["verified"] = service.verify(prepared)
            report["representative_examples"] = service.verify_examples(prepared)
            report["query_examples"] = service.verify_query_examples(prepared)
            report["search_scenarios"] = service.verify_search_scenarios(prepared)
        print(json.dumps(report, ensure_ascii=True, default=str, indent=2))
        return 0
    except Exception as error:
        print(f"ERROR {type(error).__name__}: {safe_error(error)}", file=sys.stderr)
        return 1
    finally:
        if graph is not None:
            graph.close()


# endregion
# region 2. 직접 실행 진입점
# =========================================================
# import 시에는 적재하지 않고 CLI 실행 시에만 main 호출
# =========================================================
if __name__ == "__main__":
    # import될 때는 main()을 실행하지 않는다. Java의 main 진입 조건과 유사하다.
    raise SystemExit(main())

# endregion
