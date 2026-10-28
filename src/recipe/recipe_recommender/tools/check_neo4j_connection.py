"""기존 환경변수로 Neo4j 연결과 읽기 쿼리를 확인하는 단독 실행 도구."""

from __future__ import annotations

import os
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.tools._connection_util import initialize, safe_error


QUERY = "RETURN 1 AS value"


# region 1. Neo4j 연결 및 읽기 쿼리 점검
# =========================================================
# 연결 확인 후 RETURN 1 결과 검사
# =========================================================

def main() -> int:
    """Neo4j에 연결해 읽기 쿼리 한 건으로 연결 상태를 확인한다."""
    initialize()
    print("[Neo4j Connection Test]")
    required = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print("Configuration : NOT TESTED (missing " + ", ".join(missing) + ")")
        print("Connection    : NOT TESTED")
        print(f"Query         : {QUERY}")
        print("Status        : NOT TESTED")
        return 2

    print("Configuration : OK")
    driver = None
    try:
        from recipe_recommender.neo4j_connection import create_neo4j_driver

        driver = create_neo4j_driver()      # TLS 인증서 검증 유지, 신뢰 CA 번들 명시
        driver.verify_connectivity()
        print("Connection    : OK")
        database = os.getenv("NEO4J_DATABASE") or None
        with driver.session(database=database) as session:
            record = session.run(QUERY).single(strict=True)
            value = record["value"]
        print(f"Query         : {QUERY}")
        print(f"Result        : {value}")
        status = value == 1
        print("Status        : " + ("SUCCESS" if status else "FAILED"))
        return 0 if status else 1
    except Exception as error:
        print("Connection    : FAILED")
        print(f"Query         : {QUERY}")
        print(f"Error         : {type(error).__name__}: {safe_error(error)}")
        print("Status        : FAILED")
        return 1
    finally:
        if driver is not None:
            driver.close()


# =========================================================
# 직접 실행 진입점
# =========================================================
if __name__ == "__main__":
    raise SystemExit(main())

# endregion

