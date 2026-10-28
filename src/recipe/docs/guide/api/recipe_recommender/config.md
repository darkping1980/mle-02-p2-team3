# config 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.config`
- **소스:** [recipe_recommender/config.py](../../../../recipe_recommender/config.py)
- **역할:** 과제 경로와 환경변수 로딩을 준비하는 공통 설정 도우미.
- **주요 호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **정의:** 클래스 0개, 모듈 함수 9개

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [project_root](#function-project_root) | `Path` | 현재 작업 디렉터리와 무관하게 .git 또는 .env가 있는 저장소 루트를 찾는다. |
| [prepare_imports](#function-prepare_imports) | `None` | 과제 폴더를 import 경로에 넣어 같은 수준의 ``common``을 찾게 한다. |
| [prepare_common_imports](#function-prepare_common_imports) | `None` | ``common`` import를 준비하고 pgvector의 이전 import 경로를 보완한다. |
| [load_project_environment](#function-load_project_environment) | `None` | 저장소의 .env를 읽되 이미 설정된 프로세스 환경변수는 덮어쓰지 않는다. |
| [is_local_dev](#function-is_local_dev) | `bool` | 저장소 루트에 ``.env`` 가 있으면 로컬 개발 환경으로 본다(``.env`` 는 커밋하지 않으므로 Cloud에는 없다). |
| [local_dev_query_log_default](#function-local_dev_query_log_default) | `bool` | Streamlit 앱이 쓰는 기본값: 로컬 개발이고 소스 설정값이 켜져 있을 때만 True. |
| [query_logging_active](#function-query_logging_active) | `bool` | 현재 프로세스에서 상세 로그가 활성 상태인지 반환한다. |
| [query_log_enabled](#function-query_log_enabled) | `bool` | 개발용 SQL/Cypher 상세 로그를 켤지 판단한다(환경변수 값 우선, 없으면 `default`). |
| [configure_query_logging](#function-configure_query_logging) | `bool` | 켜져 있으면 공통 SQL/Cypher logger를 INFO 레벨로 터미널(stderr)에 출력한다. |

상수: `QUERY_LOG_ENV = "RECIPE_QUERY_LOG"`, `QUERY_LOG_ON_VALUES = {"1", "true", "yes", "on"}`(대소문자·앞뒤 공백 무시),
`QUERY_LOGGER_NAMES = ("car_search_rag.sql", "car_search_rag.neo4j")`, `QUERY_LOG_FORMAT`,
`LOCAL_DEV_QUERY_LOG_DEFAULT = True`(소스 설정값: 로컬 개발 Streamlit 기본 켜짐), `_query_log_active`(이 프로세스에서 켰는지).

## Function project_root

```python
def project_root() -> Path:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `Path`. 현재 작업 디렉터리와 무관하게 .git 또는 .env가 있는 저장소 루트를 찾는다.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (28행)

## Function prepare_imports

```python
def prepare_imports() -> None:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `None`. 과제 폴더를 import 경로에 넣어 같은 수준의 ``common``을 찾게 한다.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (36행)

## Function prepare_common_imports

```python
def prepare_common_imports() -> None:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `None`. ``common`` import를 준비하고 pgvector의 이전 import 경로를 보완한다.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (43행)

## Function load_project_environment

```python
def load_project_environment() -> None:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `None`. 저장소의 .env를 읽되 이미 설정된 프로세스 환경변수는 덮어쓰지 않는다.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (66행)

## Function is_local_dev

```python
def is_local_dev() -> bool:
```

- **호출자:** `local_dev_query_log_default`
- **반환:** `bool`. `project_root()/.env`가 있으면 True. `.env`는 `.gitignore` 대상이라 Streamlit Cloud에는 없다.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (75행)

## Function local_dev_query_log_default

```python
def local_dev_query_log_default() -> bool:
```

- **호출자:** `streamlit_app` 최상위(`configure_query_logging(default=...)`)
- **반환:** `bool`. `LOCAL_DEV_QUERY_LOG_DEFAULT and is_local_dev()`.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (80행)

## Function query_logging_active

```python
def query_logging_active() -> bool:
```

- **호출자:** `streamlit_app.run_postgres_log_check`.
- **반환:** `bool`. 현재 프로세스에서 `configure_query_logging()`이 마지막으로 켠 로그 검증 모드의 활성 상태. 명시적으로 OFF로 바꾸면 `False`가 된다.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (85행)

## Function query_log_enabled

```python
def query_log_enabled(default: bool = False) -> bool:
```

- **호출자:** `configure_query_logging`
- **반환:** `bool`. `RECIPE_QUERY_LOG`에 값이 있으면 그 값(`1`·`true`·`yes`·`on`만 켜짐, `0` 등은 꺼짐), 비어 있으면 `default`.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (85행)

## Function configure_query_logging

```python
def configure_query_logging(default: bool = False) -> bool:
```

- **호출자:** `streamlit_app` 최상위(`default=local_dev_query_log_default()`), `RecipeGraphRepository.__init__`·`database.create_recipe_sql_session`(`sql_log=None`, 기본값 False — 이미 이 프로세스에서 켰다면 같은 결정을 따름)
- **반환:** `bool`. 켰으면 True. 꺼져 있으면 활성 상태를 False로 되돌리고 logger 설정은 건드리지 않는다. CLI는 기본값 False라 환경변수를 켜야 출력한다.
- **원본:** [config.py](../../../../recipe_recommender/config.py) (98행)

**처리 흐름:** `QUERY_LOGGER_NAMES`의 logger마다 레벨 INFO, `StreamHandler(sys.stderr)` 1개(표시 속성 `recipe_query_log`로 중복 방지), `propagate=False`. 로그 형식·DB 실행은 공통 `QueryLogger`가 그대로 맡는다.

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
