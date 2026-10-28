-- =====================================================================
-- recipe 스키마 실데이터 검토 SQL (DBeaver용, 읽기 전용)
--   등록: python -m recipe_recommender.setup.register_recipe_csv  /  조회 CLI: python -m recipe_recommender.search_recipe
--   모든 쿼리는 SELECT만 사용한다. 데이터·DDL을 변경하지 않는다.
--   각 블록은 "-- [ID]" 주석으로 구분되며 DBeaver에서 블록 단위(Ctrl+Enter)로 실행한다.
--
--   식별자 구분
--     rcp_raw_id  : 원본 수집 회차 ID          rcp_raw_seq : 회차 내 원본 행 순번(000001~)
--     rcp_seq     : 식약처 원본 레시피 번호     rcp_id      : 정제 레시피 내부 ID(rcp 단독 PK)
--   목표 모델(2026-10-22): 레시피·요리 분류는 rcp_cat_rel(N:M), 식재료는 ingr_id 단독 PK, 식재료 분류 없음.
-- =====================================================================


-- =====================================================================
-- A. 테이블별 건수와 수집 회차
-- =====================================================================

-- [A1] 11개 테이블 행 수
SELECT 'rcp_raw' AS table_nm, count(*) AS row_count FROM recipe.rcp_raw
UNION ALL SELECT 'rcp_cat', count(*) FROM recipe.rcp_cat
UNION ALL SELECT 'common_code_grp', count(*) FROM recipe.common_code_grp
UNION ALL SELECT 'common_cd', count(*) FROM recipe.common_cd
UNION ALL SELECT 'rcp', count(*) FROM recipe.rcp
UNION ALL SELECT 'rcp_cat_rel', count(*) FROM recipe.rcp_cat_rel
UNION ALL SELECT 'rcp_step', count(*) FROM recipe.rcp_step
UNION ALL SELECT 'ingr', count(*) FROM recipe.ingr
UNION ALL SELECT 'ingr_als', count(*) FROM recipe.ingr_als
UNION ALL SELECT 'rcp_ingr_stg', count(*) FROM recipe.rcp_ingr_stg
UNION ALL SELECT 'rcp_ingr', count(*) FROM recipe.rcp_ingr;

-- [A2] 수집 회차별 원본 행 순번 범위
SELECT
    raw.rcp_raw_id,
    count(*) AS raw_count,
    min(raw.rcp_raw_seq) AS first_raw_seq,
    max(raw.rcp_raw_seq) AS last_raw_seq,
    count(DISTINCT raw.rcp_seq) AS distinct_rcp_seq,
    (SELECT count(*) FROM recipe.rcp AS r WHERE r.rcp_raw_id = raw.rcp_raw_id) AS rcp_count,
    (SELECT count(*) FROM recipe.rcp_ingr_stg AS s WHERE s.rcp_raw_id = raw.rcp_raw_id) AS staging_count
FROM recipe.rcp_raw AS raw
GROUP BY raw.rcp_raw_id
ORDER BY raw.rcp_raw_id;

-- [A3] 원본 행 순번 → 원본 레시피 번호 → 내부 레시피 ID (앞 10행)
SELECT
    raw.rcp_raw_id,
    raw.rcp_raw_seq,
    raw.rcp_seq,
    r.rcp_id,
    raw.rcp_nm
FROM recipe.rcp_raw AS raw
JOIN recipe.rcp AS r ON r.rcp_seq = raw.rcp_seq AND r.rcp_raw_id = raw.rcp_raw_id
ORDER BY raw.rcp_raw_id, raw.rcp_raw_seq
LIMIT 10;


-- =====================================================================
-- B. 요리 분류 / C. 조리 방법(공통코드)
-- =====================================================================

-- [B1] 요리 분류별 레시피 건수 (rcp_cat_rel 기준. 다중 분류 레시피는 각 분류에 한 번씩 센다)
SELECT
    c.rcp_cat_id,
    c.rcp_cat_nm,
    count(rel.rcp_id) AS recipe_count
FROM recipe.rcp_cat AS c
LEFT JOIN recipe.rcp_cat_rel AS rel ON rel.rcp_cat_id = c.rcp_cat_id
GROUP BY c.rcp_cat_id, c.rcp_cat_nm
ORDER BY recipe_count DESC;

-- [B2] 레시피당 요리 분류 수 분포 (현재 데이터는 모두 1)
SELECT category_count, count(*) AS recipe_count
FROM (
    SELECT r.rcp_id, count(rel.rcp_cat_id) AS category_count
    FROM recipe.rcp AS r
    LEFT JOIN recipe.rcp_cat_rel AS rel ON rel.rcp_id = r.rcp_id
    GROUP BY r.rcp_id
) AS d
GROUP BY category_count
ORDER BY category_count;

-- [C1] 공통코드 그룹과 상세 코드
SELECT
    g.common_code_grp_id,
    g.common_code_grp_nm,
    c.common_cd,
    c.common_cd_nm
FROM recipe.common_code_grp AS g
LEFT JOIN recipe.common_cd AS c ON c.common_code_grp_id = g.common_code_grp_id
ORDER BY g.common_code_grp_id, c.common_cd;

-- [C2] 조리 방법별 레시피 건수
SELECT
    c.common_cd AS cook_mthd_cd,
    c.common_cd_nm,
    count(r.rcp_id) AS recipe_count
FROM recipe.common_cd AS c
LEFT JOIN recipe.rcp AS r ON r.cook_mthd_cd = c.common_cd
WHERE c.common_code_grp_id = 'COOK_MTHD'
GROUP BY c.common_cd, c.common_cd_nm
ORDER BY recipe_count DESC;


-- =====================================================================
-- D. 레시피 상세 (RCP_SEQ 28 새우 두부 계란찜)
-- =====================================================================

-- [D1] 원본 번호·내부 ID·요리 분류·조리 방법·영양정보·원본 재료 문자열
SELECT
    r.rcp_seq,
    r.rcp_id,
    r.rcp_nm,
    (SELECT string_agg(c.rcp_cat_nm, ', ' ORDER BY c.rcp_cat_nm)
       FROM recipe.rcp_cat_rel AS rel JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
      WHERE rel.rcp_id = r.rcp_id) AS rcp_cat_nm,
    cd.common_cd_nm AS cook_mthd_nm,
    r.rcp_energy_kcal,
    r.rcp_carbs_g,
    r.rcp_protein_g,
    r.rcp_fat_g,
    r.rcp_sodium_mg,
    r.rcp_nutrition_status,
    raw.rcp_raw_id,
    raw.rcp_raw_seq,
    raw.rcp_parts_dtls AS raw_parts_txt
FROM recipe.rcp AS r
JOIN recipe.common_cd AS cd ON cd.common_code_grp_id = 'COOK_MTHD' AND cd.common_cd = r.cook_mthd_cd
JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = r.rcp_raw_id AND raw.rcp_seq = r.rcp_seq
WHERE r.rcp_seq = '28';

-- [D2] 조리 단계 (원본 단계 번호 그대로)
SELECT
    st.step_no,
    st.rcp_step_instruction_txt,
    st.rcp_step_image_url
FROM recipe.rcp_step AS st
JOIN recipe.rcp AS r ON r.rcp_id = st.rcp_id
WHERE r.rcp_seq = '28'
ORDER BY st.step_no;

-- [D3] 재료 staging 추출 결과와 표준 식재료 매핑
SELECT
    s.rcp_ingr_line_no,
    s.rcp_ingr_stg_id,
    s.rcp_ingr_section_txt,
    s.rcp_ingr_raw_txt,
    s.rcp_ingr_parsed_nm,
    s.rcp_ingr_qty,
    s.rcp_ingr_unit_nm,
    s.rcp_ingr_status,
    i.ingr_id,
    i.ingr_nm
FROM recipe.rcp_ingr_stg AS s
JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
LEFT JOIN recipe.ingr AS i ON i.ingr_id = s.ingr_id
WHERE raw.rcp_seq = '28'
ORDER BY s.rcp_ingr_line_no;

-- [D4] 레시피별 사용 식재료 (최종 N:M 관계)
SELECT
    r.rcp_seq,
    r.rcp_nm,
    i.ingr_id,
    i.ingr_nm
FROM recipe.rcp_ingr AS f
JOIN recipe.rcp AS r ON r.rcp_id = f.rcp_id
JOIN recipe.ingr AS i ON i.ingr_id = f.ingr_id
WHERE r.rcp_seq = '28'
ORDER BY i.ingr_nm;


-- =====================================================================
-- E. 같은 이름 레시피 비교 (양배추롤 298·536, 버섯 리조또 788·919)
-- =====================================================================

-- [E1] 기본 속성과 단계·재료 건수
SELECT
    r.rcp_nm,
    r.rcp_seq,
    r.rcp_id,
    (SELECT string_agg(c.rcp_cat_nm, ', ' ORDER BY c.rcp_cat_nm)
       FROM recipe.rcp_cat_rel AS rel JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
      WHERE rel.rcp_id = r.rcp_id) AS rcp_cat_nm,
    r.cook_mthd_cd,
    r.rcp_energy_kcal,
    (SELECT count(*) FROM recipe.rcp_step AS st WHERE st.rcp_id = r.rcp_id) AS step_count,
    (SELECT count(*) FROM recipe.rcp_ingr AS f WHERE f.rcp_id = r.rcp_id) AS ingredient_count,
    raw.rcp_parts_dtls AS raw_parts_txt
FROM recipe.rcp AS r
JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = r.rcp_raw_id AND raw.rcp_seq = r.rcp_seq
WHERE r.rcp_seq IN ('298', '536', '788', '919')
ORDER BY r.rcp_nm, r.rcp_seq::int;

-- [E2] 같은 이름 쌍의 원문·표준 식재료 비교
SELECT
    a.rcp_nm,
    a.rcp_seq AS rcp_seq_a,
    b.rcp_seq AS rcp_seq_b,
    a.cook_mthd_cd = b.cook_mthd_cd AS same_cook_mthd,
    ra.rcp_parts_dtls = rb.rcp_parts_dtls AS same_parts_txt,
    ra.manual01 = rb.manual01 AS same_manual01,
    (SELECT string_agg(i.ingr_nm, ', ' ORDER BY i.ingr_nm)
       FROM recipe.rcp_ingr AS f JOIN recipe.ingr AS i ON i.ingr_id = f.ingr_id
      WHERE f.rcp_id = a.rcp_id) AS ingredients_a,
    (SELECT string_agg(i.ingr_nm, ', ' ORDER BY i.ingr_nm)
       FROM recipe.rcp_ingr AS f JOIN recipe.ingr AS i ON i.ingr_id = f.ingr_id
      WHERE f.rcp_id = b.rcp_id) AS ingredients_b
FROM recipe.rcp AS a
JOIN recipe.rcp AS b ON b.rcp_nm = a.rcp_nm AND b.rcp_seq::int > a.rcp_seq::int
JOIN recipe.rcp_raw AS ra ON ra.rcp_raw_id = a.rcp_raw_id AND ra.rcp_seq = a.rcp_seq
JOIN recipe.rcp_raw AS rb ON rb.rcp_raw_id = b.rcp_raw_id AND rb.rcp_seq = b.rcp_seq
WHERE a.rcp_seq IN ('298', '536', '788', '919');


-- =====================================================================
-- F. 식재료 마스터와 관계
-- =====================================================================

-- [F1] 표준 식재료·별칭·사용 관계 요약 (식재료 분류는 목표 모델에서 제거)
SELECT
    count(DISTINCT i.ingr_id) AS ingredient_count,
    (SELECT count(*) FROM recipe.ingr_als) AS alias_count,
    (SELECT count(DISTINCT ingr_id) FROM recipe.ingr_als) AS ingredient_with_alias_count,
    count(DISTINCT f.ingr_id) AS used_ingredient_count,
    count(DISTINCT f.rcp_id) AS recipe_with_ingredient_count
FROM recipe.ingr AS i
LEFT JOIN recipe.rcp_ingr AS f ON f.ingr_id = i.ingr_id;

-- [F2] 별칭 목록 (ingr_als_id와 표준 식재료)
SELECT
    i.ingr_id,
    i.ingr_nm,
    a.ingr_als_id,
    a.ingr_als_nm
FROM recipe.ingr_als AS a
JOIN recipe.ingr AS i ON i.ingr_id = a.ingr_id
ORDER BY i.ingr_nm, a.ingr_als_nm;

-- [F3] 많이 쓰이는 표준 식재료 상위 30
SELECT
    i.ingr_id,
    i.ingr_nm,
    count(*) AS recipe_count
FROM recipe.rcp_ingr AS f
JOIN recipe.ingr AS i ON i.ingr_id = f.ingr_id
GROUP BY i.ingr_id, i.ingr_nm
ORDER BY recipe_count DESC
LIMIT 30;

-- [F4] 하나의 재료(칵테일새우)를 공유하는 다른 레시피 — 레시피 28 기준
SELECT
    i.ingr_nm,
    other.rcp_seq,
    other.rcp_nm
FROM recipe.rcp AS base
JOIN recipe.rcp_ingr AS bf ON bf.rcp_id = base.rcp_id
JOIN recipe.ingr AS i ON i.ingr_id = bf.ingr_id
JOIN recipe.rcp_ingr AS f ON f.ingr_id = bf.ingr_id
JOIN recipe.rcp AS other ON other.rcp_id = f.rcp_id
WHERE base.rcp_seq = '28'
  AND i.ingr_nm = '칵테일새우'
  AND other.rcp_seq <> base.rcp_seq
ORDER BY other.rcp_seq::int;

-- [F5] 레시피 28과 공유 식재료가 많은 레시피 상위 10
SELECT
    other.rcp_seq,
    other.rcp_nm,
    count(*) AS shared_ingredient_count,
    string_agg(i.ingr_nm, ', ' ORDER BY i.ingr_nm) AS shared_ingredients
FROM recipe.rcp AS base
JOIN recipe.rcp_ingr AS bf ON bf.rcp_id = base.rcp_id
JOIN recipe.rcp_ingr AS f ON f.ingr_id = bf.ingr_id
JOIN recipe.rcp AS other ON other.rcp_id = f.rcp_id
JOIN recipe.ingr AS i ON i.ingr_id = f.ingr_id
WHERE base.rcp_seq = '28'
  AND other.rcp_seq <> base.rcp_seq
GROUP BY other.rcp_seq, other.rcp_nm
ORDER BY shared_ingredient_count DESC, other.rcp_seq::int
LIMIT 10;

-- [F6] staging 파싱·승인 상태별 건수
SELECT
    split_part(s.rcp_ingr_review_note, ';', 1) AS parse_result,
    s.rcp_ingr_status,
    count(*) AS staging_count
FROM recipe.rcp_ingr_stg AS s
GROUP BY split_part(s.rcp_ingr_review_note, ';', 1), s.rcp_ingr_status
ORDER BY staging_count DESC;

-- [F7] 미분류·검토 보류 후보 재료명 빈도 (식재료 사전 확장 대상)
SELECT
    s.rcp_ingr_parsed_nm,
    split_part(s.rcp_ingr_review_note, ';', 1) AS parse_result,
    count(*) AS occurrence_count,
    count(DISTINCT (s.rcp_raw_id, s.rcp_raw_seq)) AS recipe_count
FROM recipe.rcp_ingr_stg AS s
WHERE s.rcp_ingr_status = 'PENDING_REVIEW'
GROUP BY s.rcp_ingr_parsed_nm, split_part(s.rcp_ingr_review_note, ';', 1)
ORDER BY occurrence_count DESC
LIMIT 100;

-- [F8] 파싱 실패·모호 원문
SELECT
    raw.rcp_seq,
    raw.rcp_nm,
    s.rcp_ingr_line_no,
    s.rcp_ingr_section_txt,
    s.rcp_ingr_raw_txt,
    s.rcp_ingr_review_note
FROM recipe.rcp_ingr_stg AS s
JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
WHERE split_part(s.rcp_ingr_review_note, ';', 1) IN ('parse=FAILED', 'parse=AMBIGUOUS')
ORDER BY raw.rcp_raw_seq, s.rcp_ingr_line_no;

-- [F9] 한 레시피에서 같은 표준 식재료가 여러 번 등장한 staging 사례 (최종 관계는 1건)
SELECT
    raw.rcp_seq,
    raw.rcp_nm,
    i.ingr_nm,
    count(*) AS staging_rows,
    string_agg(coalesce(s.rcp_ingr_section_txt, '(구획 없음)') || ': ' || s.rcp_ingr_raw_txt, ' | '
               ORDER BY s.rcp_ingr_line_no) AS occurrences
FROM recipe.rcp_ingr_stg AS s
JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
JOIN recipe.ingr AS i ON i.ingr_id = s.ingr_id
WHERE s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
GROUP BY raw.rcp_seq, raw.rcp_nm, i.ingr_nm
HAVING count(*) > 1
ORDER BY staging_rows DESC, raw.rcp_seq::int;


-- =====================================================================
-- G. 데이터 정합성 검사 (violation_count가 모두 0이어야 정상)
-- =====================================================================

-- [G1] 항목별 위반 건수
SELECT 'rcp 중 요리 분류 관계 없음' AS check_nm, count(*) AS violation_count
FROM recipe.rcp AS r
WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_cat_rel AS rel WHERE rel.rcp_id = r.rcp_id)
UNION ALL
SELECT 'rcp_cat_rel → rcp 고아', count(*)
FROM recipe.rcp_cat_rel AS rel LEFT JOIN recipe.rcp AS r ON r.rcp_id = rel.rcp_id
WHERE r.rcp_id IS NULL
UNION ALL
SELECT 'rcp_cat_rel → rcp_cat 고아', count(*)
FROM recipe.rcp_cat_rel AS rel LEFT JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
WHERE c.rcp_cat_id IS NULL
UNION ALL
SELECT 'rcp.cook_mthd_cd → common_cd(COOK_MTHD) 누락', count(*)
FROM recipe.rcp AS r LEFT JOIN recipe.common_cd AS c ON c.common_code_grp_id = 'COOK_MTHD' AND c.common_cd = r.cook_mthd_cd
WHERE c.common_cd IS NULL
UNION ALL
SELECT 'common_cd → common_code_grp 고아', count(*)
FROM recipe.common_cd AS c LEFT JOIN recipe.common_code_grp AS g ON g.common_code_grp_id = c.common_code_grp_id
WHERE g.common_code_grp_id IS NULL
UNION ALL
SELECT 'rcp → rcp_raw(같은 회차·원본 번호) 누락', count(*)
FROM recipe.rcp AS r LEFT JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = r.rcp_raw_id AND raw.rcp_seq = r.rcp_seq
WHERE raw.rcp_seq IS NULL
UNION ALL
SELECT 'rcp.rcp_seq 중복', count(*)
FROM (SELECT rcp_seq FROM recipe.rcp GROUP BY rcp_seq HAVING count(*) > 1) AS d
UNION ALL
SELECT 'rcp_raw (rcp_raw_id, rcp_seq) 중복', count(*)
FROM (SELECT rcp_raw_id, rcp_seq FROM recipe.rcp_raw GROUP BY rcp_raw_id, rcp_seq HAVING count(*) > 1) AS d
UNION ALL
SELECT 'rcp_raw 중 rcp 미생성', count(*)
FROM recipe.rcp_raw AS raw LEFT JOIN recipe.rcp AS r ON r.rcp_seq = raw.rcp_seq
WHERE r.rcp_seq IS NULL
UNION ALL
SELECT 'rcp_step → rcp 고아', count(*)
FROM recipe.rcp_step AS st LEFT JOIN recipe.rcp AS r ON r.rcp_id = st.rcp_id
WHERE r.rcp_id IS NULL
UNION ALL
SELECT 'rcp_ingr_stg → rcp_raw 고아', count(*)
FROM recipe.rcp_ingr_stg AS s LEFT JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
WHERE raw.rcp_raw_seq IS NULL
UNION ALL
SELECT 'rcp_ingr_stg.rcp_ingr_stg_id 중복', count(*)
FROM (SELECT rcp_ingr_stg_id FROM recipe.rcp_ingr_stg GROUP BY rcp_ingr_stg_id HAVING count(*) > 1) AS d
UNION ALL
SELECT 'rcp_ingr_stg 지정 식재료 → ingr 고아', count(*)
FROM recipe.rcp_ingr_stg AS s LEFT JOIN recipe.ingr AS i ON i.ingr_id = s.ingr_id
WHERE s.ingr_id IS NOT NULL AND i.ingr_id IS NULL
UNION ALL
SELECT 'ingr_als → ingr 고아', count(*)
FROM recipe.ingr_als AS a LEFT JOIN recipe.ingr AS i ON i.ingr_id = a.ingr_id
WHERE i.ingr_id IS NULL
UNION ALL
SELECT 'ingr_als.ingr_als_id 중복', count(*)
FROM (SELECT ingr_als_id FROM recipe.ingr_als GROUP BY ingr_als_id HAVING count(*) > 1) AS d
UNION ALL
SELECT '표준명·별칭이 둘 이상의 표준 식재료를 가리킴', count(*)
FROM (
    SELECT nm FROM (
        SELECT ingr_nm AS nm, ingr_id FROM recipe.ingr
        UNION SELECT ingr_als_nm, ingr_id FROM recipe.ingr_als
    ) AS n GROUP BY nm HAVING count(DISTINCT ingr_id) > 1
) AS d
UNION ALL
SELECT 'rcp_ingr → rcp/ingr 고아', count(*)
FROM recipe.rcp_ingr AS f
LEFT JOIN recipe.rcp AS r ON r.rcp_id = f.rcp_id
LEFT JOIN recipe.ingr AS i ON i.ingr_id = f.ingr_id
WHERE r.rcp_id IS NULL OR i.ingr_id IS NULL
UNION ALL
SELECT 'rcp_ingr 중 승인 staging 근거 없음', count(*)
FROM recipe.rcp_ingr AS f
JOIN recipe.rcp AS r ON r.rcp_id = f.rcp_id
WHERE NOT EXISTS (
    SELECT 1
    FROM recipe.rcp_ingr_stg AS s
    JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
    WHERE s.rcp_raw_id = f.rcp_raw_id AND raw.rcp_seq = r.rcp_seq
      AND s.ingr_id = f.ingr_id
      AND s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
)
UNION ALL
SELECT '승인 staging 중 rcp_ingr 미생성', count(*)
FROM recipe.rcp_ingr_stg AS s
JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
JOIN recipe.rcp AS r ON r.rcp_seq = raw.rcp_seq AND r.rcp_raw_id = raw.rcp_raw_id
WHERE s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
  AND NOT EXISTS (
      SELECT 1 FROM recipe.rcp_ingr AS f
      WHERE f.ingr_id = s.ingr_id AND f.rcp_id = r.rcp_id
  )
UNION ALL
SELECT 'CSV 행수(1156) 불일치: 최신 회차', abs(1156 - count(*))
FROM recipe.rcp_raw
WHERE rcp_raw_id = (SELECT rcp_raw_id FROM recipe.rcp_raw GROUP BY rcp_raw_id ORDER BY max(create_date) DESC LIMIT 1);

-- [G2] 원본 행 순번 연속성 (회차별 1..N이면 gap_count 0)
SELECT
    rcp_raw_id,
    count(*) AS raw_count,
    max(rcp_raw_seq::int) AS max_seq,
    max(rcp_raw_seq::int) - count(*) AS gap_count
FROM recipe.rcp_raw
GROUP BY rcp_raw_id;

-- [G3] staging 재료 등장 순번 연속성 (원본 행별 1..N이 아닌 경우)
SELECT s.rcp_raw_id, s.rcp_raw_seq, count(*) AS line_count, max(s.rcp_ingr_line_no) AS max_line_no
FROM recipe.rcp_ingr_stg AS s
GROUP BY s.rcp_raw_id, s.rcp_raw_seq
HAVING max(s.rcp_ingr_line_no) <> count(*);

-- [G4] 원본 대비 조리 단계 누락 (원본 설명이 있는데 rcp_step에 없는 단계)
WITH raw_step AS (
    SELECT raw.rcp_raw_id, raw.rcp_seq, step.step_no, step.txt
    FROM recipe.rcp_raw AS raw
    CROSS JOIN LATERAL (VALUES
        (1, raw.manual01), (2, raw.manual02), (3, raw.manual03), (4, raw.manual04), (5, raw.manual05),
        (6, raw.manual06), (7, raw.manual07), (8, raw.manual08), (9, raw.manual09), (10, raw.manual10),
        (11, raw.manual11), (12, raw.manual12), (13, raw.manual13), (14, raw.manual14), (15, raw.manual15),
        (16, raw.manual16), (17, raw.manual17), (18, raw.manual18), (19, raw.manual19), (20, raw.manual20)
    ) AS step(step_no, txt)
    WHERE btrim(step.txt) <> ''
)
SELECT rs.rcp_seq, rs.step_no, left(rs.txt, 60) AS raw_step_txt
FROM raw_step AS rs
JOIN recipe.rcp AS r ON r.rcp_seq = rs.rcp_seq AND r.rcp_raw_id = rs.rcp_raw_id
LEFT JOIN recipe.rcp_step AS st
  ON st.rcp_id = r.rcp_id AND st.step_no = rs.step_no
WHERE st.step_no IS NULL
ORDER BY rs.rcp_seq::int, rs.step_no;

-- [G5] 원본 단계 번호가 연속되지 않는 레시피 / 조리 단계가 없는 레시피
SELECT r.rcp_seq, r.rcp_nm, string_agg(st.step_no::text, ', ' ORDER BY st.step_no) AS step_nos
FROM recipe.rcp AS r
LEFT JOIN recipe.rcp_step AS st ON st.rcp_id = r.rcp_id
GROUP BY r.rcp_seq, r.rcp_nm
HAVING count(st.step_no) = 0 OR max(st.step_no) <> count(st.step_no)
ORDER BY r.rcp_seq::int;

-- [G6] 영양정보 검토 대상
SELECT
    r.rcp_seq,
    r.rcp_nm,
    r.rcp_energy_kcal,
    round(4 * r.rcp_carbs_g + 4 * r.rcp_protein_g + 9 * r.rcp_fat_g, 2) AS estimated_kcal,
    r.rcp_nutrition_review_note
FROM recipe.rcp AS r
WHERE r.rcp_nutrition_status = 'REVIEW_REQUIRED'
ORDER BY r.rcp_seq::int;

-- [G7] PK·UNIQUE 제약 목록
SELECT
    conrelid::regclass AS table_nm,
    conname,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'recipe'::regnamespace
  AND contype IN ('p', 'u')
ORDER BY conrelid::regclass::text, contype, conname;

-- [G8] 물리 FK 수(0이어야 함)와 COMMENT 누락
SELECT
    (SELECT count(*) FROM pg_constraint WHERE connamespace = 'recipe'::regnamespace AND contype = 'f') AS physical_fk_count,
    (SELECT count(*) FROM pg_class AS c
      WHERE c.relnamespace = 'recipe'::regnamespace AND c.relkind = 'r'
        AND obj_description(c.oid, 'pg_class') IS NULL) AS table_without_comment,
    (SELECT count(*) FROM pg_class AS c
       JOIN pg_attribute AS a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
      WHERE c.relnamespace = 'recipe'::regnamespace AND c.relkind = 'r'
        AND col_description(c.oid, a.attnum) IS NULL) AS column_without_comment;
