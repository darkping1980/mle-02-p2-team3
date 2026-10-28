--=========================================================
-- Step 1 PostgreSQL 실습 mapper (namespace: basic_sample)
--   모든 테이블은 TEMP TABLE ... ON COMMIT DROP이므로 트랜잭션이 끝나면 자동으로 삭제된다.
--   따라서 Python에서는 생성부터 삭제까지 하나의 transaction() 안에서 호출한다.
--   이름 끝 느낌표(!)는 결과 행이 없는 명령, 접미사 없음은 결과 행을 돌려주는 SQL이다.
--   INSERT ... RETURNING은 등록한 행의 값을 결과 행으로 돌려주므로 접미사 없이 선언했다.
--   find_similar_vectors:
--     pgvector 연산자 <=> 는 cosine 거리이며 ORDER BY로 가까운 순 정렬한다.
--     similarity = 1 - cosine 거리. 거리가 같으면 item_id 순으로 정렬해 결과 순서를 고정한다.
--     VECTOR(3)은 3차원 벡터 컬럼이며, 넣는 값도 3차원이어야 한다.
--=========================================================

-- name: create_general_table!
CREATE TEMP TABLE graph_rag_basic_general (
    test_run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (test_run_id, item_id)
) ON COMMIT DROP;

-- name: create_vector_table!
CREATE TEMP TABLE graph_rag_basic_vectors (
    test_run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    item_name TEXT NOT NULL,
    embedding VECTOR(3) NOT NULL,
    PRIMARY KEY (test_run_id, item_id)
) ON COMMIT DROP;

-- name: insert_general_item
INSERT INTO graph_rag_basic_general (test_run_id, item_id, content)
VALUES (:test_run_id, :item_id, :content)
RETURNING item_id, content;

-- name: find_general_items
SELECT item_id, content
FROM graph_rag_basic_general
WHERE test_run_id = :test_run_id
ORDER BY item_id;

-- name: insert_vector_item
INSERT INTO graph_rag_basic_vectors (test_run_id, item_id, item_name, embedding)
VALUES (:test_run_id, :item_id, :item_name, :embedding)
RETURNING item_id, item_name;

-- name: find_similar_vectors
SELECT item_id,
       item_name,
       1 - (embedding <=> :query_embedding) AS similarity
FROM graph_rag_basic_vectors
WHERE test_run_id = :test_run_id
ORDER BY embedding <=> :query_embedding, item_id
LIMIT :limit;

-- name: delete_general_items!
DELETE FROM graph_rag_basic_general WHERE test_run_id = :test_run_id;

-- name: delete_vector_items!
DELETE FROM graph_rag_basic_vectors WHERE test_run_id = :test_run_id;
