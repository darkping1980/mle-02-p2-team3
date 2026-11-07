"""DB 접근 모듈. 연결과 읽기 전용 조회만 맡고, 그래프 로직은 rag.py가 맡습니다.

그래프 테이블은 전용 스키마 graphrag 아래에 있습니다. (supabase_schema.sql 참고)
스키마 이름을 바꿔야 하면 SCHEMA 한 곳만 고치세요. 쿼리는 NODES / EDGES 상수를 씁니다.
"""
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()

SCHEMA = "graphrag"
NODES = f"{SCHEMA}.nodes"
EDGES = f"{SCHEMA}.edges"


def run_query(query: str, params: dict | None = None) -> list[dict]:
    """읽기 전용 조회. 호출마다 연결을 열고 닫아서 끊긴 연결 문제가 없습니다."""
    url = os.getenv("DB_URL")
    if not url:
        raise RuntimeError("DB_URL 환경 변수가 없습니다. .env 파일을 확인하세요.")
    # prepare_threshold=None: Supabase 트랜잭션 풀러(pgbouncer)는 prepared statement를 지원하지 않습니다.
    with psycopg.connect(
        url,
        autocommit=True,
        row_factory=dict_row,
        prepare_threshold=None,
        connect_timeout=10,
    ) as conn:
        return conn.execute(query, params or {}).fetchall()
