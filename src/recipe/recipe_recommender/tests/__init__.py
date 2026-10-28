"""Tests for the recipe project scaffold."""

import os

# 테스트는 로컬 .env 유무와 무관하게 SQL/Cypher 상세 로그를 끈 상태에서 시작한다(이미 값이 있으면 그 값을 쓴다).
# 로그 스위치 자체를 검사하는 테스트(test_query_log_config.py)는 환경변수를 직접 지정한다.
os.environ.setdefault("RECIPE_QUERY_LOG", "0")
