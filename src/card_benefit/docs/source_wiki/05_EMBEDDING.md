# 5. 검색 텍스트와 임베딩

[목차](README.md) · [혜택 등록](03_BENEFIT_REGISTRATION.md)

<details><summary>▼ 5.1 진입점과 파이프라인</summary>

별도 CLI [`embedding_main.py`](../../payment_card/db_pipeline/embedding_main.py)가 [`EmbeddingService.sync()`](../../payment_card/db_pipeline/embedding_service.py)를 호출한다. 혜택 등록 서비스는 성공 commit 뒤 `embed_new()`를 선택적으로 호출할 수 있다. 임베딩 실패는 이미 완료된 혜택 등록을 되돌리지 않으며 별도 CLI로 복구한다.

<details><summary>▼ 5.1.1 계획·텍스트 저장·벡터 생성</summary>

- `sync(table, ids, force, text_only, apply)`: 대상은 `card_bnft`(실제 저장 테이블 `card_product_item`) 또는 `card_common_bnft`. 먼저 Mapper로 기존 행을 읽고 텍스트 빌더를 적용한다.
- dry-run(`apply=False`)은 처리 계획과 보고만 반환한다. apply이면 바뀐 검색 텍스트를 저장한다. `text_only`이거나 임베딩 대상이 없으면 API 단계에서 끝난다.
- 임베딩 필요 시 client를 확인하고 마지막 embedding run의 모델을 검사한다. 모델 불일치는 `force` 없이 허용하지 않는다.
- 최대 64개 단위로 임베딩을 호출하고 결과 순서/1536차원을 확인해 벡터를 저장한다. 배치 재시도·오류는 report와 run status에 반영된다.
- 실패가 없으면 `SUCCEEDED`, 일부면 `PARTIAL`, 전부 실패면 `FAILED`. 예외 발생은 run을 `FAILED`로 마감하고 다시 전파한다.
- `embed_new()`는 오류를 잡아 로그만 남기고 `None` 반환. 등록 transaction 바깥 복구 경로다.
- 소스: [`embedding_service.py`](../../payment_card/db_pipeline/embedding_service.py), [sync GitHub](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/embedding_service.py#L141), [`embedding_main.py`](../../payment_card/db_pipeline/embedding_main.py).
</details>
</details>

<details><summary>▼ 5.2 텍스트·모델·Mapper</summary>

검색 텍스트는 [`benefit_search_text.py`](../../payment_card/db_pipeline/benefit_search_text.py)에서 상품 혜택/공통 혜택별로 만든다. 기본 모델 `text-embedding-3-small`, 벡터 크기 1536, batch 64. 실제 OpenAI 호출은 `OpenAIEmbedder.embed()`이며 이번 정적 조사에서 호출하지 않았다.

[`embedding_repository.sql`](../../payment_card/db_pipeline/embedding_repository.sql)은 대상 조회, `card_product_item.item_search_txt`/`item_embedding`, `card_common_bnft.bnft_search_txt`/`bnft_embedding` 저장, `card_ai_run` 실행 이력, 상태 조회 및 cosine distance 후보 검색을 정의한다. Repository facade는 `EmbeddingRepository` in [`embedding_service.py`](../../payment_card/db_pipeline/embedding_service.py).
</details>

<details><summary>▼ 5.3 조회 B/C 모드 연결</summary>

검색 모드 B는 벡터 후보, C는 문자열과 벡터 후보 결합 경로를 `BenefitSearchService`가 제공한다. 후보 선정에 유사도를 쓰며, 상세 조건과 근거는 Neo4j 또는 PostgreSQL fallback에서 재조회한다. 검색 구현은 [8장](08_GRAPHRAG_QUERY.md).
</details>

[PostgreSQL 스키마 →](06_POSTGRESQL_SCHEMA.md) · [조회 →](08_GRAPHRAG_QUERY.md)

