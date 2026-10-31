--=========================================================
-- document_repository SQL mapper
--   파일 이름(document_repository)이 namespace이며, Python에서는 "document_repository.쿼리이름"으로 호출한다.
--   테이블 앞의 db_pipeline은 namespace가 아니라 DB 스키마다.
--   테이블은 db_pipeline_schemaV6_draft.sql로 만들어 둔다(이 mapper는 DDL을 실행하지 않는다).
--   청크는 PAGE_V1 규칙으로 페이지당 1건이고, 위치는 페이지 원문 기준 1부터이며 종료 위치의 문자를 포함한다.
--   조회문은 DBeaver에서 그대로 실행할 수 있고, 콜론으로 시작하는 파라미터는 실행할 때 입력한다.
--=========================================================

-- name: select_doc_by_sha256_or_cd
-- 같은 파일이거나 같은 문서 코드인 문서를 찾는다.
SELECT card_doc_id, doc_cd, doc_sha256, doc_status
FROM db_pipeline.card_doc
WHERE doc_sha256 = :DOC_SHA256
   OR doc_cd = :DOC_CD
;

-- name: insert_doc
-- 문서를 등록한다. card_doc_id는 기본값 fn_get_biz_id가 발급하고, 상품 연결은 이후 단계이므로 card_id는 비워 둔다.
-- 같은 계열의 문서가 이미 있으면 다음 버전 번호를 사용한다.
INSERT INTO db_pipeline.card_doc (
    doc_cd,
    doc_family_cd,
    doc_type_cd,
    doc_title,
    doc_source_url,
    doc_file_nm,
    doc_file_size,
    doc_sha256,
    doc_page_cnt,
    doc_review_no,
    doc_review_date,
    doc_collect_date,
    doc_version_no,
    doc_note,
    create_user_id,
    update_user_id
) VALUES (
    :DOC_CD,
    CAST(:DOC_FAMILY_CD AS text),
    :DOC_TYPE_CD,
    :DOC_TITLE,
    :DOC_SOURCE_URL,
    :DOC_FILE_NM,
    :DOC_FILE_SIZE,
    :DOC_SHA256,
    :DOC_PAGE_CNT,
    :DOC_REVIEW_NO,
    :DOC_REVIEW_DATE,
    :DOC_COLLECT_DATE,
    (SELECT COALESCE(MAX(d.doc_version_no), 0) + 1
     FROM db_pipeline.card_doc d
     WHERE d.doc_family_cd = CAST(:DOC_FAMILY_CD AS text)),
    :DOC_NOTE,
    :USER_ID,
    :USER_ID
)
RETURNING card_doc_id;

-- name: insert_doc_page!
-- 페이지 원문을 등록한다. execute_many()가 페이지 수만큼 반복 실행한다.
INSERT INTO db_pipeline.card_doc_page (
    card_doc_id,
    page_no,
    page_raw_txt,
    page_char_cnt,
    page_txt_sha256,
    page_layer_cd,
    page_extractor_nm,
    page_extractor_ver,
    page_note,
    create_user_id,
    update_user_id
) VALUES (
    :CARD_DOC_ID,
    :PAGE_NO,
    :PAGE_RAW_TXT,
    :PAGE_CHAR_CNT,
    :PAGE_TXT_SHA256,
    :PAGE_LAYER_CD,
    :PAGE_EXTRACTOR_NM,
    :PAGE_EXTRACTOR_VER,
    :PAGE_NOTE,
    :USER_ID,
    :USER_ID
);

-- name: insert_doc_chunk!
-- 청크를 등록한다. card_doc_chunk_id는 기본값 fn_get_biz_id가 발급한다.
-- OCR 검토 대상 페이지의 청크는 chunk_status를 EXCLUDED로 넣어 AI 입력에서 뺀다.
INSERT INTO db_pipeline.card_doc_chunk (
    card_doc_id,
    page_no,
    chunk_seq,
    chunk_start_pos,
    chunk_end_pos,
    chunk_raw_txt,
    chunk_status,
    chunk_split_rule_ver,
    create_user_id,
    update_user_id
) VALUES (
    :CARD_DOC_ID,
    :PAGE_NO,
    :CHUNK_SEQ,
    :CHUNK_START_POS,
    :CHUNK_END_POS,
    :CHUNK_RAW_TXT,
    :CHUNK_STATUS,
    :CHUNK_SPLIT_RULE_VER,
    :USER_ID,
    :USER_ID
);

-- name: select_page_hashes
-- PDF를 다시 추출한 결과와 대조할 페이지 해시를 조회한다.
SELECT page_no, page_txt_sha256
FROM db_pipeline.card_doc_page
WHERE card_doc_id = :CARD_DOC_ID
ORDER BY page_no
;

-- name: select_table_counts
-- 문서 한 건의 테이블별 등록 건수를 조회한다.
SELECT
    (SELECT COUNT(*) FROM db_pipeline.card_doc WHERE card_doc_id = :CARD_DOC_ID) AS doc_cnt,
    (SELECT COUNT(*) FROM db_pipeline.card_doc_page WHERE card_doc_id = :CARD_DOC_ID) AS page_cnt,
    (SELECT COUNT(*) FROM db_pipeline.card_doc_chunk WHERE card_doc_id = :CARD_DOC_ID) AS chunk_cnt
;

-- name: select_review_pages
-- OCR 검토를 기다리는 페이지를 조회한다. page_note가 'OCR_REVIEW '로 시작하면 검토 대상이다.
SELECT
    p.page_no,
    p.page_extractor_nm,
    p.page_layer_cd,
    p.page_note,
    (SELECT COUNT(*)
     FROM db_pipeline.card_doc_chunk c
     WHERE c.card_doc_id = p.card_doc_id
       AND c.page_no = p.page_no
       AND c.chunk_status = 'EXCLUDED') AS excluded_chunk_cnt
FROM db_pipeline.card_doc_page p
WHERE p.card_doc_id = :CARD_DOC_ID
  AND left(p.page_note, 11) = 'OCR_REVIEW '
ORDER BY p.page_no
;

-- name: approve_review_page
-- 사람이 원문과 대조한 OCR 페이지를 AI 추출 대상으로 전환한다. page_note를 OCR_CONFIRMED로 바꾸고 청크를 RAW로 되돌린다.
-- OCR 문구 자체를 고쳐야 하는 페이지는 이 SQL을 쓰지 않는다. 청크 위치가 달라지므로 다시 나눠야 한다.
WITH page AS (
    UPDATE db_pipeline.card_doc_page
    SET page_note = 'OCR_CONFIRMED by=' || CAST(:USER_ID AS text) || ' / ' || page_note,
        update_date = now(),
        update_user_id = CAST(:USER_ID AS text)
    WHERE card_doc_id = :CARD_DOC_ID
      AND page_no = :PAGE_NO
      AND left(page_note, 11) = 'OCR_REVIEW '
    RETURNING card_doc_id, page_no
)
UPDATE db_pipeline.card_doc_chunk c
SET chunk_status = 'RAW',
    update_date = now(),
    update_user_id = CAST(:USER_ID AS text)
FROM page p
WHERE c.card_doc_id = p.card_doc_id
  AND c.page_no = p.page_no
  AND c.chunk_status = 'EXCLUDED'
RETURNING c.card_doc_chunk_id;

-- name: select_ai_target_chunks
-- AI 추출에 넘길 청크를 조회한다. 제외된 청크와 사용 중이 아닌 문서는 포함하지 않는다.
SELECT c.card_doc_id, c.page_no, c.card_doc_chunk_id, c.chunk_seq, c.chunk_status
FROM db_pipeline.card_doc_chunk c
JOIN db_pipeline.card_doc d ON d.card_doc_id = c.card_doc_id
WHERE c.card_doc_id = :CARD_DOC_ID
  AND c.chunk_status IN ('RAW', 'CLEANED')
  AND d.doc_status = 'ACTIVE'
ORDER BY c.chunk_seq
;

-- name: select_doc_chunks
-- 청크 위치와 앞부분을 페이지 원문에서 잘라 저장값과 함께 확인한다.
SELECT
    c.chunk_seq,
    c.page_no,
    c.chunk_start_pos,
    c.chunk_end_pos,
    c.chunk_end_pos - c.chunk_start_pos + 1 AS chunk_len,
    substr(p.page_raw_txt, c.chunk_start_pos, c.chunk_end_pos - c.chunk_start_pos + 1) = c.chunk_raw_txt AS source_match,
    left(c.chunk_raw_txt, 50) AS chunk_head
FROM db_pipeline.card_doc_chunk c
JOIN db_pipeline.card_doc_page p
  ON p.card_doc_id = c.card_doc_id
 AND p.page_no = c.page_no
WHERE c.card_doc_id = :CARD_DOC_ID
ORDER BY c.chunk_seq
;

-- name: verify_doc
-- 문서 한 건을 항목별로 검증한다. issue_cnt가 0이면 통과다. ERROR는 등록을 막고 WARN은 확인 대상이다.
--   PAGE_COUNT       doc_page_cnt와 페이지 행 수, 1부터 빠짐없는 페이지 번호
--   PAGE_CHAR_CNT    저장한 문자 수와 페이지 원문 길이
--   PAGE_HASH        저장한 해시와 페이지 원문에서 다시 계산한 해시
--   PAGE_BLANK       공백만 있는 페이지
--   CHUNK_ORPHAN     페이지 행이 없는 청크
--   CHUNK_POSITION   위치로 페이지 원문을 잘라낸 값과 청크 원문
--   CHUNK_SEQ        페이지·위치 순서와 문서 내 1부터의 순번
--   CHUNK_DUP_POS    같은 위치의 청크
--   CHUNK_DUP_TXT    같은 원문의 청크. 페이지 내용이 같은 문서에서 나타날 수 있다.
--   CHUNK_GAP        어떤 청크에도 포함되지 않은 공백 외 문자가 있는 구간
--   CHUNK_EXCLUDED   OCR 검토가 끝나지 않아 AI 입력에서 제외된 청크
--   REVIEW_OPEN      OCR 검토 대상 페이지인데 AI 입력에서 제외되지 않은 청크
--   CODE_VALUE       공통코드에 없는 코드값
--   INTEGRITY_GATE   v_card_integrity_issue 전체 건수. 이 문서 외의 행도 포함한다.
WITH doc AS (
    SELECT * FROM db_pipeline.card_doc WHERE card_doc_id = :CARD_DOC_ID
),
page AS (
    SELECT p.* FROM db_pipeline.card_doc_page p JOIN doc d ON d.card_doc_id = p.card_doc_id
),
chunk AS (
    SELECT c.* FROM db_pipeline.card_doc_chunk c JOIN doc d ON d.card_doc_id = c.card_doc_id
),
ordered AS (
    SELECT c.*,
           ROW_NUMBER() OVER (ORDER BY c.page_no, c.chunk_start_pos, c.chunk_end_pos) AS expected_seq,
           COALESCE(MAX(c.chunk_end_pos) OVER (
               PARTITION BY c.page_no ORDER BY c.chunk_start_pos, c.chunk_end_pos
               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS covered_end
    FROM chunk c
),
gap AS (
    SELECT o.page_no, o.covered_end + 1 AS gap_start, o.chunk_start_pos - 1 AS gap_end
    FROM ordered o
    WHERE o.chunk_start_pos > o.covered_end + 1
    UNION ALL
    SELECT p.page_no, COALESCE(MAX(c.chunk_end_pos), 0) + 1, p.page_char_cnt
    FROM page p
    LEFT JOIN chunk c ON c.page_no = p.page_no
    GROUP BY p.page_no, p.page_char_cnt
),
code AS (
    SELECT 'DOC_TYPE' AS grp, doc_type_cd AS cd FROM doc
    UNION ALL SELECT 'DOC_STATUS', doc_status FROM doc
    UNION ALL SELECT 'PAGE_LAYER', page_layer_cd FROM page
    UNION ALL SELECT 'CHUNK_TYPE', chunk_type_cd FROM chunk
    UNION ALL SELECT 'CHUNK_STATUS', chunk_status FROM chunk
)
SELECT 'PAGE_COUNT' AS check_cd, 'ERROR' AS severity,
       (SELECT COUNT(*) FROM doc d
        WHERE d.doc_page_cnt IS DISTINCT FROM (SELECT COUNT(*) FROM page)
           OR d.doc_page_cnt IS DISTINCT FROM (SELECT MAX(page_no) FROM page)) AS issue_cnt
UNION ALL
SELECT 'PAGE_CHAR_CNT', 'ERROR',
       (SELECT COUNT(*) FROM page WHERE page_char_cnt <> char_length(page_raw_txt))
UNION ALL
SELECT 'PAGE_HASH', 'ERROR',
       (SELECT COUNT(*) FROM page
        WHERE page_txt_sha256 <> encode(sha256(convert_to(page_raw_txt, 'UTF8')), 'hex'))
UNION ALL
SELECT 'PAGE_BLANK', 'WARN',
       (SELECT COUNT(*) FROM page WHERE page_raw_txt !~ '\S')
UNION ALL
SELECT 'CHUNK_ORPHAN', 'ERROR',
       (SELECT COUNT(*) FROM chunk c WHERE NOT EXISTS (SELECT 1 FROM page p WHERE p.page_no = c.page_no))
UNION ALL
SELECT 'CHUNK_POSITION', 'ERROR',
       (SELECT COUNT(*) FROM chunk c JOIN page p ON p.page_no = c.page_no
        WHERE c.chunk_end_pos > p.page_char_cnt
           OR substr(p.page_raw_txt, c.chunk_start_pos, c.chunk_end_pos - c.chunk_start_pos + 1) <> c.chunk_raw_txt)
UNION ALL
SELECT 'CHUNK_SEQ', 'ERROR',
       (SELECT COUNT(*) FROM ordered WHERE chunk_seq <> expected_seq)
UNION ALL
SELECT 'CHUNK_DUP_POS', 'ERROR',
       (SELECT COUNT(*) FROM (
            SELECT 1 FROM chunk GROUP BY page_no, chunk_start_pos, chunk_end_pos HAVING COUNT(*) > 1) x)
UNION ALL
SELECT 'CHUNK_DUP_TXT', 'WARN',
       (SELECT COUNT(*) FROM (SELECT 1 FROM chunk GROUP BY chunk_raw_txt HAVING COUNT(*) > 1) x)
UNION ALL
SELECT 'CHUNK_GAP', 'ERROR',
       (SELECT COUNT(*) FROM gap g JOIN page p ON p.page_no = g.page_no
        WHERE g.gap_end >= g.gap_start
          AND substr(p.page_raw_txt, g.gap_start, g.gap_end - g.gap_start + 1) ~ '\S')
UNION ALL
SELECT 'CHUNK_EXCLUDED', 'WARN',
       (SELECT COUNT(*) FROM chunk WHERE chunk_status = 'EXCLUDED')
UNION ALL
SELECT 'REVIEW_OPEN', 'ERROR',
       (SELECT COUNT(*) FROM chunk c JOIN page p ON p.page_no = c.page_no
        WHERE left(p.page_note, 11) = 'OCR_REVIEW ' AND c.chunk_status <> 'EXCLUDED')
UNION ALL
SELECT 'CODE_VALUE', 'ERROR',
       (SELECT COUNT(*) FROM code c
        WHERE NOT EXISTS (
            SELECT 1 FROM db_pipeline.common_cd x
            WHERE x.common_code_grp_id = c.grp AND x.common_cd = c.cd))
UNION ALL
SELECT 'INTEGRITY_GATE', 'WARN',
       (SELECT COUNT(*) FROM db_pipeline.v_card_integrity_issue)
;
