# Inspecting payment card data in Neo4j Browser

## 샘플로 카드 1~2개 확인하기 (로컬 Neo4j 전용)

기본 점검 대상은 로컬 `graphrag-neo4j` 컨테이너입니다. 이미 9일째 실행 중인 컨테이너를 사용하며 새 컨테이너를 만들지 않습니다. 포트는 Browser `7474`, Bolt `7687`이고 주소는 `bolt://localhost:7687`입니다. 브라우저에서 <http://localhost:7474>를 열어 연결 상태를 확인할 수 있습니다. 로컬 비밀번호는 사용자가 알고 있는 값을 실행 시 직접 입력하며 문서에는 저장하지 않습니다.

`.env`의 `NEO4J_URI`는 팀원 Aura를 가리킬 수 있습니다. 기본 노트북 경로는 `.env`를 읽지 않고 로컬 주소와 입력받은 비밀번호만 사용합니다. 원격 Aura에는 어떤 경우에도 쓰지 않습니다. 원격 읽기가 꼭 필요한 경우에도 `USE_ENV_REMOTE=True`와 `ALLOW_REMOTE=True`가 모두 명시되어야 하고, 원격 쓰기와 삭제는 차단됩니다.

1. 샘플 만들기 (저장소 밖 `/tmp`에 생성):

```bash
cd /home/lee/workspace/mle-02-p2-team3
export UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src:src/card_benefit
uv run --locked --no-sync python -m payment_card.file_pipeline.graph.cypher_export --csv-dir /tmp/fp-check-hana --list-cards 20
uv run --locked --no-sync python -m payment_card.file_pipeline.graph.cypher_export --csv-dir /tmp/fp-check-hana --card-id <카드 id> --output /tmp/fp-sample-hana.cypher
```

2. 브라우저에서 <http://localhost:7474>를 열어 로컬 Neo4j에 직접 로그인합니다. 비밀번호는 문서나 코드에 기록하지 않습니다.
3. 먼저 라벨을 확인합니다. 팀원 `dp_` 그래프가 보여도 이 샘플은 `Fp` 라벨만 쓰지만, 적재 전 구성을 확인하세요.

```cypher
CALL db.labels();
```

4. `/tmp/fp-sample-hana.cypher` 내용을 Neo4j Browser에 붙여 넣고 실행합니다. 생성 스크립트는 `Fp` 라벨과 `FP_` 관계만 사용합니다.
5. `queries.cypher`의 샘플 확인용 질의를 위에서부터 하나씩 실행하고, 카드 노드를 더블클릭해 연결을 펼쳐 봅니다.
6. 확인이 끝나면 **`Fp` 라벨만** 정리합니다. 라벨 없는 전체 삭제는 다른 프로젝트 데이터까지 지우므로 사용하지 않습니다.

```cypher
MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'Fp') DETACH DELETE n;
```

## 1. Convert CSV files to Cypher

`graph/export.py` creates the CSV files in the selected folder.

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.graph.cypher_export --csv-dir /tmp/fp-check-hana --output /tmp/fp-check-hana/load.cypher
```

Keep the generated `load.cypher` outside the repository because it contains data.

## 2. Import data

Open `/tmp/fp-check-hana/load.cypher`, paste its contents into Neo4j Browser, and run it. The script uses constraints and `MERGE`, so rerunning the same data does not create duplicate nodes or relationships. APOC is not required.

String, number, boolean, and null node properties are stored as properties. Lists and objects are stored as JSON in `props_json`. Evidence for relationships is represented by `FpEvidence` nodes with an `edge_id` property. Example queries are in [queries.cypher](queries.cypher).

## 3. Reset this project's data

Only use the following reset, which deletes nodes carrying a label that starts with `Fp`. Never delete everything from the shared database.

```cypher
MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'Fp') DETACH DELETE n
```

## 한국어 표시 속성과 Browser 스타일

내보내기에서 `--lang ko`를 지정하면 기존 영문 속성에 `kind_ko`, `label_ko`, enum별 `*_ko`, `caption_ko`를 추가합니다. 기본 `--lang en` 출력은 기존 형식을 유지합니다. 이미 적재한 Fp 그래프는 `--backfill-ko-out /tmp/fp-backfill-ko.cypher`로 생성한 쿼리를 Browser에서 실행할 수 있습니다. 이 쿼리는 Fp 라벨 노드와 `FP_` 관계만 변경하며 같은 값을 다시 설정해도 안전합니다.

`--grass-out /tmp/fp-korean.grass`는 Browser 스타일 파일을 만듭니다. Browser 창에 파일을 끌어 놓거나 `:style` 화면의 Import로 불러오세요. 두 방법의 지원 여부는 Browser 버전별로 미확인입니다. 관계 캡션의 `{label_ko}` 적용도 Browser 버전별 동작 확인이 필요합니다.

한국어 별칭을 사용하는 읽기 전용 예시는 [queries.cypher](queries.cypher)의 “한국어 보기 쿼리” 절을 참고하세요.

## 주피터 노트북으로 확인

`notebooks/neo4j_sample_check.ipynb`를 열고 셀 0부터 셀 9까지 순서대로 실행합니다. 먼저 셀 3의 기존 `Fp` 라벨을 확인하고 셀 4의 정적 검사 결과가 모두 통과했는지 확인하세요. 실제 적재가 필요할 때만 셀 1에서 `WRITE=True`로 바꾼 뒤 셀 5를 실행합니다. 노트북을 저장하기 전 **Clear All Outputs**를 실행해 출력이 없는 상태로 저장합니다.
