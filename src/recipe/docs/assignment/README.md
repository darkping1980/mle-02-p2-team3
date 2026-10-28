# 34-과제 제출 자료 — 식약처 레시피 그래프

## 제출할 파일 (2026-10-25)

| 파일 | 내용 |
| --- | --- |
| [김병주_34과제.ipynb](김병주_34과제.ipynb) | 제출 노트북(과제 여섯 단계, 실행 결과 포함) |
| [COOKRCP01.csv](COOKRCP01.csv) | 사용한 CSV — 받은 원본 그대로(1,739,442 bytes, SHA-256 `3f58fd2f…20305d3`, 저장소 `src/data/COOKRCP01.csv`와 같음) |

노트북은 1단계에서 같은 폴더의 `COOKRCP01.csv`를 읽습니다. 두 파일을 Google Drive `공유 문서함 / graph_rag / 0_과제제출 / 34_과제` 한 폴더에 올립니다.
아래 나머지 문서·도구·재생성 CSV와 Streamlit 앱은 제출하지 않습니다.

## 과제 폴더 문서

| 문서 | 내용 |
| --- | --- |
| [김병주_34과제.ipynb](김병주_34과제.ipynb) | 제출용 노트북(과제 여섯 단계, 실행 결과 포함). 아래 두 그림을 노트북 안에 첨부로 넣었고, 개요 다음 셀에 [Streamlit 시연 링크](https://graph-rag-2mxd3ncwawqtganwvqxykr.streamlit.app/)가 있음 |
| [레시피_일반DB_ERD.png](레시피_일반DB_ERD.png) | 그림 1 원본 — PostgreSQL `recipe` 스키마 ERD(보조 설계 자료) |
| [레시피 GraphRAG Neo4j 구조도_최종.png](<레시피 GraphRAG Neo4j 구조도_최종.png>) | 그림 2 원본 — Neo4j 최종 구조도(노드 4종 · 관계 3종, 노드 8,154 · 관계 18,301, 2026-10-25 운영 AuraDB 읽기 전용 조회 기준) |
| [graph_questions.md](graph_questions.md) | 1·2·3-hop 질문지 5개(목적·경로·hop 판정·검증 방법) |
| [query_results.md](query_results.md) | 질문별 Cypher와 실제 조회 결과 표·해석 |
| [test_report.md](test_report.md) | 자동 테스트·노트북 실행·현재 앱 확인 결과, 실패·미검증 사항, 배포 후 브라우저 테스트 항목 |
| [data/COOKRCP01_regenerated_from_rcp_raw.csv](data/COOKRCP01_regenerated_from_rcp_raw.csv) | (제출하지 않음) PostgreSQL `rcp_raw`에서 다시 만든 CSV. 원본과 칸 안 줄바꿈(CRLF↔LF)만 다름 |
| [export_cookrcp01_csv.py](export_cookrcp01_csv.py) | 위 재생성 CSV를 PostgreSQL `recipe.rcp_raw`에서 다시 만드는 도구(DB 읽기 전용, 검증 포함) |

과제 원본: [34-과제_공공데이터로-그래프-만들기_배포용.ipynb](../../34-과제_공공데이터로-그래프-만들기_배포용.ipynb)(이 PC에는 `(1)`·`(2)`가 붙은 파일이 없습니다). 아래 표는 그 노트북의 과제 안내·채점 기준·"내기 전에 확인하기"를 기준으로 했습니다.

## 요구사항 충족 현황

| 요구사항 | 상태 | 근거 |
| --- | --- | --- |
| 데이터 출처 · 이용 조건 | 완료 | 식품안전나라 COOKRCP01 공식 페이지·공공데이터포털(이용허락범위 제한 없음)을 2026-10-24에 확인해 노트북 맨 위에 기록 |
| 수집일 | 기록(구분 표기) | 실제 최초 다운로드 일시는 확인 불가. 확인 가능한 가장 이른 근거 = 원본 `src/data/COOKRCP01.csv` 최초 Git 커밋 2026-10-21 16:02 KST(`b3a7848`), 다운로드는 그 이전 |
| 원본 분석(줄 수·열·빈칸·한 줄의 뜻) | 완료 | 노트북 1단계: 1,156줄 × 55열, 빈칸 집계, "한 줄 = 레시피 하나" |
| 정제 전후 건수 | 완료 | 노트북 3단계: 재료 13,080줄 → 10,428 관계, 조리 과정 23,120칸 → 6,717 단계, 분류 6 |
| 그래프로 답할 질문 3~5개 | 완료 | 5개 — [질문지](graph_questions.md) |
| 노드 2종 이상 · 관계 2종 이상 | 완료 | 노드 4종(`rcp`·`ingr`·`rcp_cat`·`rcp_step`), 관계 3종 |
| 관계를 두 번 이상 건너는 질문 | 완료 | Q2·Q4(2-hop), Q3(3-hop, 추가 시연 목표) |
| 질문별 Cypher · 결과 표 · 해석 | 완료 | 노트북 5단계, [query_results.md](query_results.md) |
| pandas 교차 검증 | 완료 | Q4(상위 50 완전 일치), Q3(일치) |
| `MERGE` 재실행 시 중복 없음 | 완료(테스트 DB) | "두 번 넣어도 같은가: True" — 별도 로컬 Neo4j에서 실행. 운영 AuraDB에는 쓰지 않음 |
| 재실행 가능한 노트북 | 완료(이 PC) | 2026-10-24 위에서부터 실행 45셀·오류 0. 2026-10-25 원본 CSV로 바꾼 1단계 셀만 다시 실행. 다른 환경은 프로젝트 코드·`.env`·테스트 Neo4j가 필요(노트북 맨 위 "실행 조건과 한계") |
| 다른 데이터에 영향 없는 정리 | 완료 | 테스트 DB의 4개 라벨·제약·인덱스만 삭제, 운영 주소면 실행 차단 |
| 사용한 CSV 함께 제출 | 완료(원본) | `COOKRCP01.csv`(노트북과 같은 폴더) 1,156행 × 55열, 받은 원본 그대로. 노트북 1단계가 이 CSV를 읽고 칸 안 줄바꿈만 LF로 맞춘 뒤 `rcp_raw`와 모든 칸이 같음(True) |
| 제출 파일명 `이름_34과제.ipynb` | 완료 | `김병주_34과제.ipynb` |

## 데이터 출처와 제출 CSV

| 항목 | 내용 (2026-10-24 확인) |
| --- | --- |
| 데이터 | 식품의약품안전처 「조리식품의 레시피 DB」, 식품안전나라 Open API 서비스 ID `COOKRCP01` |
| 공식 서비스 | <https://www.foodsafetykorea.go.kr/api/openApiInfo.do?menu_grp=MENU_GRP31&menu_no=661&show_cnt=10&start_idx=1&svc_no=COOKRCP01> — OPEN API, CSV 다운로드 제공. 파일 요청 형식 `http://openapi.foodsafetykorea.go.kr/api/{인증키}/COOKRCP01/file`. 최초 개방 2017-12-19, 최종 수정 2021-08-03, 업데이트 주기 상시, 분류 식품영양정보 |
| 공공데이터포털 | 「식품의약품안전처_조리식품의 레시피 DB」 <https://www.data.go.kr/data/15060073/openapi.do> — API 유형 LINK(식품안전나라로 연결), **이용허락범위 제한 없음**, 비용 무료, 관리부서 데이터혁신기획팀, 포털 등록 2020-05-25·수정 2025-08-27 |
| 수집일 | **실제 최초 다운로드 일시: 확인 불가.** 확인 가능한 가장 이른 근거는 원본 `src/data/COOKRCP01.csv`(1,739,442 bytes, UTF-8 BOM, SHA-256 `3f58fd2f16869553248df5990b41be9828c5313a2041cb82395644edb20305d3`)의 최초 Git 커밋 2026-10-21 16:02 KST(`b3a7848`)이며 다운로드는 그 이전. 받은 경로(CSV 다운로드/API) 기록도 없음. 2026-10-22 06:26 UTC에 PostgreSQL `rcp_raw`에 등록됨 |
| 제출 CSV | `COOKRCP01.csv`(노트북과 같은 폴더) — 위 원본을 그대로 복사(SHA-256 같음, 2026-10-25 확인) |
| 재생성 CSV(제출 안 함) | `data/COOKRCP01_regenerated_from_rcp_raw.csv` — 1,733,702 bytes, SHA-256 `aa9eb1507d65dd03bd696a977d94442ddc0ba0e0d95558f70edef19f9225b2b9`. 원본과 행·열·값이 같고 칸 안 줄바꿈만 원본 CRLF → LF(3,276칸)로 다름(2026-10-25 확인) |

> 2026-10-24에는 원본 파일이 이 PC에 없다고 보고 아래처럼 재생성 CSV를 만들었습니다. 2026-10-25 저장소 `src/data/COOKRCP01.csv`에서 원본을 확인해 제출 CSV를 원본으로 바꿨습니다.

재생성 CSV: `rcp_raw`는 원본 55열을 문자열 그대로(빈 문자열만 NULL) 보관하므로
NULL을 빈 문자열로 되돌리고 원본 헤더 순서(`RecipeRegisterService.SOURCE_COLUMNS`)·원본 행 순서(`rcp_raw_seq`)로 썼습니다.
UTF-8 BOM·최소 인용·CRLF로 여러 형식을 시험했지만 원본 크기·SHA-256과 일치하는 형식은 없었습니다. 따라서 **필드 값만 같고 파일 바이트는 다릅니다.**

| 검증 | 결과 |
| --- | --- |
| 행 수 · 열 수 | 1,156 × 55, `rcp_raw_seq` 000001~001156 연속 |
| 컬럼 순서 | 원본 헤더 55개 순서와 같음 |
| 값 누락 | 다시 읽은 CSV의 모든 칸 = `rcp_raw` 값, 컬럼별 빈칸 수 동일 |
| 프로젝트 CSV 검증기 | `RecipeRegisterService.read_csv`·`validate_rows` 오류 0 |
| 등록 CLI dry-run | `register_recipe_csv --csv <제출 CSV> --dry-run`(DB 변경 없음): 레시피 1,156 · 분류 관계 1,156 · 조리 단계 6,717 · 재료 줄 13,080 — 현재 DB와 같음 |

다시 만들기: 과제 폴더에서 `python docs/assignment/export_cookrcp01_csv.py`(검증에 실패하면 파일을 남기지 않음).

## 시연(Streamlit)

- 모드 A **냉장고 재료 추천**: 기존 기능 그대로.
- 모드 B **그래프 관계 탐색**(신규): Q1~Q5를 고르고 대상을 정해 조회. 질문 유형·hop·관계 경로·Neo4j 조회 결과를 보여 주며 LLM을 쓰지 않습니다. 실행 Cypher는 화면에 표시하지 않고 이 문서들과 노트북에 있습니다(로컬 실행 시 터미널 로그에 출력). 상세는 [개발자 가이드](../guide/details/06_graph_questions.md).
- 배포 반영은 아직입니다(Push 전). 반영 후 확인할 항목은 [test_report.md 6절](test_report.md#6-배포-후-브라우저-테스트-항목).

## 노트북 실행 준비

0. 제출 CSV `COOKRCP01.csv`가 노트북과 같은 폴더(`docs/assignment/`)에 있어야 합니다(1단계가 작업 폴더 기준 상대경로로 읽음).
1. 저장소 루트 `.env`에 `DB_URL`, `NEO4J_URI`·`NEO4J_USERNAME`·`NEO4J_PASSWORD`·`NEO4J_DATABASE`(운영, 읽기 전용으로만 사용).
2. 쓰기 검증용 별도 Neo4j(예: 로컬 Neo4j Community)를 띄우고 `ASSIGNMENT_NEO4J_URI`·`ASSIGNMENT_NEO4J_USERNAME`·`ASSIGNMENT_NEO4J_PASSWORD`(선택 `ASSIGNMENT_NEO4J_DATABASE`, 기본 `neo4j`)를 환경변수나 `.env`에 둡니다. 운영 AuraDB 주소를 넣으면 4단계에서 멈춥니다.
3. 저장소 루트 `.venv`의 Python 커널로 위에서부터 실행합니다. 이 PC에서는 `jupyter nbconvert --to notebook --execute --inplace 이름_34과제.ipynb`(현재 `김병주_34과제.ipynb`)로 실행했습니다.
