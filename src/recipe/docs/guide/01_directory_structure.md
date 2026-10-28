# 01. 디렉터리 구조

[메인](README.md) · [파일 구조](02_file_structure.md) · [실행 흐름](04_execution_flow.md)

```text
과제_공공데이터로-그래프-만들기_금요일까지/
├── streamlit_app.py                 화면 진입점
├── recipe_recommender/
│   ├── pantry_graphrag.py          LangGraph 실행
│   ├── pantry_recommend_service.py 추천
│   ├── recipe_search_service.py    일반 조회
│   ├── search_recipe.py            조회 CLI
│   ├── recipe_repository.py        등록·조회 공용 PostgreSQL Repository
│   ├── recipe_graph_repository.py  추천·적재 공용 Neo4j Repository
│   ├── name_normalization.py       추천·적재 공용 이름 정규화
│   ├── config.py, database.py, neo4j_connection.py, sql_schema.py
│   ├── *.sql, *.cypher             Repository의 명명 mapper
│   ├── setup/                      초기 구축·재적재·정합성 검증
│   │   ├── register_recipe_csv.py, recipe_register_service.py
│   │   ├── recipe_ingredient_parser.py
│   │   ├── load_recipe_graph.py, recipe_graph_load_service.py
│   │   └── recipe_graph_source_repository.py
│   ├── data/                       등록 seed CSV
│   ├── sql/                        수동 DDL
│   ├── tools/                      점검·스키마 재구축 운영 CLI
│   └── tests/
├── common/                          공용 DB 세션·mapper·로그
├── docs/guide/                     현재 소스 기준 개발자 가이드
├── docs/study/, docs/db/, docs/neo4j/, docs/handoff/
└── README_recipe.md
```

`setup/`의 등록 Service는 최상위 `RecipeRepository`와 `recipe.sql`을 사용한다. 그래프 적재 Service는 `setup/`의 PostgreSQL 스냅샷 Repository와 최상위 `RecipeGraphRepository`를 사용한다. 추천 경로는 `setup/`에 의존하지 않는다. `normalize_name`은 [name_normalization.py](../../recipe_recommender/name_normalization.py)에 있어 추천과 적재가 함께 사용한다.

`recipe_graph_constraints.cypher`, `recipe_graph_load.cypher`, `recipe_graph_validation.cypher`는 최상위 Repository의 `mapper_root` 아래에 둔다. `Neo4jDbSession`이 그 위치에서 재귀 탐색하므로 파일 이동 없이 명명 질의 ID를 유지한다. `data/` seed 경로는 이동한 Service에서 패키지 최상위 폴더를 기준으로 계산한다.

작업 폴더 루트와 [config.project_root()](../../recipe_recommender/config.py)가 반환하는 Git 저장소 루트는 다르다. 기본 원본 CSV는 Git 루트의 `src/data/COOKRCP01.csv`이다.
