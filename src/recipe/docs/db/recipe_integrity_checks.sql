-- Read-only logical integrity checks for the recipe target model (docs/db/recipe_target_schema.sql).
-- Each query lists violating rows and is expected to return zero rows.
-- The schema intentionally has no physical FOREIGN KEY constraints.
-- A one-row summary of the same checks: docs/db/recipe_data_review.sql [G1].

-- Every recipe must belong to at least one recipe category (rcp_cat_rel, N:M).
SELECT r.*
FROM recipe.rcp AS r
WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_cat_rel AS rel WHERE rel.rcp_id = r.rcp_id);

-- Recipe-category relations must reference an existing recipe and category.
SELECT rel.*
FROM recipe.rcp_cat_rel AS rel
LEFT JOIN recipe.rcp AS r ON r.rcp_id = rel.rcp_id
LEFT JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
WHERE r.rcp_id IS NULL OR c.rcp_cat_id IS NULL;

-- Cooking method is a general attribute and must exist in the COOK_MTHD code group.
SELECT r.*
FROM recipe.rcp AS r
LEFT JOIN recipe.common_cd AS c
  ON c.common_code_grp_id = 'COOK_MTHD'
 AND c.common_cd = r.cook_mthd_cd
WHERE c.common_cd IS NULL;

-- Common codes must belong to an existing code group.
SELECT c.*
FROM recipe.common_cd AS c
LEFT JOIN recipe.common_code_grp AS g ON g.common_code_grp_id = c.common_code_grp_id
WHERE g.common_code_grp_id IS NULL;

-- The recipe's collection round must contain the same source recipe number.
SELECT r.*
FROM recipe.rcp AS r
LEFT JOIN recipe.rcp_raw AS raw
  ON raw.rcp_raw_id = r.rcp_raw_id
 AND raw.rcp_seq = r.rcp_seq
WHERE raw.rcp_seq IS NULL;

-- Source recipe numbers are globally unique (rcp_id is the PK).
SELECT 'rcp_seq' AS key_nm, rcp_seq AS key_value, count(*) AS row_count
FROM recipe.rcp GROUP BY rcp_seq HAVING count(*) > 1;

-- Recipe steps must reference an existing recipe.
SELECT st.*
FROM recipe.rcp_step AS st
LEFT JOIN recipe.rcp AS r ON r.rcp_id = st.rcp_id
WHERE r.rcp_id IS NULL;

-- Aliases must reference an existing ingredient.
SELECT a.*
FROM recipe.ingr_als AS a
LEFT JOIN recipe.ingr AS i ON i.ingr_id = a.ingr_id
WHERE i.ingr_id IS NULL;

-- A standard name or alias must not point to more than one ingredient.
SELECT nm, array_agg(DISTINCT ingr_id) AS ingr_ids
FROM (
    SELECT ingr_nm AS nm, ingr_id FROM recipe.ingr
    UNION
    SELECT ingr_als_nm, ingr_id FROM recipe.ingr_als
) AS n
GROUP BY nm
HAVING count(DISTINCT ingr_id) > 1;

-- Staging rows must reference an existing raw source row (rcp_raw_id, rcp_raw_seq).
SELECT s.*
FROM recipe.rcp_ingr_stg AS s
LEFT JOIN recipe.rcp_raw AS raw
  ON raw.rcp_raw_id = s.rcp_raw_id
 AND raw.rcp_raw_seq = s.rcp_raw_seq
WHERE raw.rcp_raw_seq IS NULL;

-- Assigned staging ingredient IDs must reference an existing ingredient.
SELECT s.*
FROM recipe.rcp_ingr_stg AS s
LEFT JOIN recipe.ingr AS i ON i.ingr_id = s.ingr_id
WHERE s.ingr_id IS NOT NULL
  AND i.ingr_id IS NULL;

-- Final relations must reference an existing recipe and ingredient.
SELECT f.*
FROM recipe.rcp_ingr AS f
LEFT JOIN recipe.rcp AS r ON r.rcp_id = f.rcp_id
LEFT JOIN recipe.ingr AS i ON i.ingr_id = f.ingr_id
WHERE r.rcp_id IS NULL OR i.ingr_id IS NULL;

-- Every final relation needs an approved staging row from the same collection round.
SELECT f.*
FROM recipe.rcp_ingr AS f
JOIN recipe.rcp AS r ON r.rcp_id = f.rcp_id
WHERE NOT EXISTS (
    SELECT 1
    FROM recipe.rcp_ingr_stg AS s
    JOIN recipe.rcp_raw AS raw
      ON raw.rcp_raw_id = s.rcp_raw_id
     AND raw.rcp_raw_seq = s.rcp_raw_seq
    WHERE s.rcp_raw_id = f.rcp_raw_id
      AND raw.rcp_seq = r.rcp_seq
      AND s.ingr_id = f.ingr_id
      AND s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
);
