--=========================================================
-- GraphRAG 샘플 PostgreSQL mapper (namespace: graph_rag_sample, Step 2/3 공통 내용)
--   Python 호출: GraphRagSamplePostgresRepository
--   두 테이블 모두 TEMP TABLE ... ON COMMIT DROP이라 트랜잭션 종료 시 자동 삭제되므로
--   테이블 생성부터 정리까지 하나의 transaction() 안에서 호출해야 한다.
--   find_keyword_items:
--     position(찾을 문자열 in 대상) > 0 은 부분 문자열 포함 여부, lower()로 대소문자를 무시한다.
--     'keyword' AS source는 결과 행에 검색 출처 표시 컬럼을 고정값으로 붙인다.
--   find_similar_vectors:
--     pgvector <=> 는 cosine 거리. similarity = 1 - 거리. 같은 거리면 item_name 순으로 결과 순서를 고정한다.
--   INSERT ... RETURNING은 결과 행을 돌려주므로 이름에 느낌표(!)를 붙이지 않았다.
--=========================================================

-- name: create_general_temp_table!
CREATE TEMP TABLE graph_rag_sample_general (
    test_run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (test_run_id, item_id)
) ON COMMIT DROP;

-- name: insert_general_item
INSERT INTO graph_rag_sample_general (test_run_id, item_id, content)
VALUES (:test_run_id, :item_id, :content)
RETURNING test_run_id, item_id, content;

-- name: find_general_items
SELECT test_run_id, item_id, content
FROM graph_rag_sample_general
WHERE test_run_id = :test_run_id
ORDER BY content;

-- name: find_keyword_items
SELECT test_run_id, item_id, content, 'keyword' AS source
FROM graph_rag_sample_general
WHERE test_run_id = :test_run_id
  AND position(lower(:keyword) in lower(content)) > 0
ORDER BY item_id;

-- name: delete_general_items!
DELETE FROM graph_rag_sample_general
WHERE test_run_id = :test_run_id;

-- name: create_vector_temp_table!
CREATE TEMP TABLE graph_rag_sample_vectors (
    test_run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    item_name TEXT NOT NULL,
    embedding VECTOR(3) NOT NULL,
    PRIMARY KEY (test_run_id, item_id)
) ON COMMIT DROP;

-- name: insert_vector_item
INSERT INTO graph_rag_sample_vectors (test_run_id, item_id, item_name, embedding)
VALUES (:test_run_id, :item_id, :item_name, :embedding)
RETURNING test_run_id, item_id, item_name;

-- name: find_similar_vectors
SELECT test_run_id,
       item_id,
       item_name,
       1 - (embedding <=> :query_embedding) AS similarity
FROM graph_rag_sample_vectors
WHERE test_run_id = :test_run_id
ORDER BY embedding <=> :query_embedding, item_name
LIMIT :limit;

-- name: delete_vector_items!
DELETE FROM graph_rag_sample_vectors
WHERE test_run_id = :test_run_id;
