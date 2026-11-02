"""참고용 도구. V6 원본에 V7 변경을 순서대로 적용한 기록이다. 설계의 기준이 아니다.

설계의 기준은 src/card_benefit/sql/의 최종 V7 SQL 파일이다. 이 스크립트가 그 파일을 대체하지 않는다.
V7 파일을 고친 뒤에는 이 스크립트의 출력과 달라지며, 그때는 V7 파일이 맞다. 구조 변경 이력을 읽는 용도로 쓴다.
--out은 필수이고 최종 SQL 폴더에는 쓰지 않는다. 실제 DB에 접속하지 않고 V6 파일은 읽기만 한다.
"""
import argparse
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
SQL = pathlib.Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", required=True, type=pathlib.Path, help="출력 폴더. 최종 SQL 폴더는 거부한다")
OUT = parser.parse_args().out.resolve()
if OUT == SQL:
    raise SystemExit("최종 V7 SQL 폴더에는 쓰지 않습니다")
OUT.mkdir(parents=True, exist_ok=True)
V6 = (SQL / "db_pipeline_schemaV6_draft.sql").read_text(encoding="utf-8")


def rep(text, old, new, count=1):
    found = text.count(old)
    if found != count:
        raise SystemExit(f"expected {count}, found {found}: {old[:90]!r}")
    return text.replace(old, new)


def cut(text, start, end, new=""):
    """Replace text from start up to (not including) end."""
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + new + text[j:]


# ---------------------------------------------------------------- DDL
d = V6
d = rep(d, """-- V6 draft integrated creation for an EMPTY db_pipeline schema.
-- No DROP and no physical foreign keys. Apply only after target/row/dependency checks.
-- This file does not replace V5 until the design review is finished.
-- Load db_pipeline_common_code_seedV6.sql after this file, then db_pipeline_common_code_descV6.sql.
""", """-- V7 draft integrated creation for an EMPTY db_pipeline schema.
-- No DROP and no physical foreign keys. Apply only after target/row/dependency checks.
-- V7 removes the card policy version layer: benefits, limits and evidence attach directly to card_product.
-- card_common_policy_version (common benefit versions) is a separate concept and is kept.
-- An existing V6 database moves with db_pipeline_migration_V6_to_V7.sql, not with this file.
-- Load db_pipeline_common_code_seedV7.sql after this file, then db_pipeline_common_code_descV7.sql.
""")
d = rep(d, "--   source_doc_list  [{\"card_doc_id\",\"source_role_cd\"}]\n", "")
d = rep(d, "-- Effective condition: policy_cond_expr AND bnft_cond_expr AND rule cond_expr (LOCAL or COMMON).",
        "-- Effective condition: card_cond_expr AND bnft_cond_expr AND rule cond_expr (LOCAL or COMMON).")
d = rep(d, "카드 상품 중심 V6 공통코드·반정규화 스키마(초안)", "카드 상품 중심 V7 공통코드·반정규화 스키마(초안)")
d = cut(d, "CREATE FUNCTION db_pipeline.fn_valid_doc_ref_list", "-- ---------------------------------------------------------------------------\n-- 시퀀스")
d = rep(d, """CREATE SEQUENCE db_pipeline.seq_card_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_policy_version IS 'card_policy_version.policy_ver_id 로컬 업무 ID 발급';

""", "")
d = rep(d, "CREATE SEQUENCE db_pipeline.seq_card_policy_evidence INCREMENT", "CREATE SEQUENCE db_pipeline.seq_card_evidence_link INCREMENT")
d = rep(d, "COMMENT ON SEQUENCE db_pipeline.seq_card_policy_evidence IS 'card_policy_evidence.ev_link_id 로컬 업무 ID 발급';",
        "COMMENT ON SEQUENCE db_pipeline.seq_card_evidence_link IS 'card_evidence_link.ev_link_id 로컬 업무 ID 발급';")
d = rep(d, "-- 상품·정책 영역\n", "-- 상품 영역\n")

# card_product
d = rep(d, """    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_pkey PRIMARY KEY (card_id),""", """    update_user_id varchar(50) NOT NULL,
    card_cond_expr jsonb,
    card_cond_status_cd varchar(20) NOT NULL DEFAULT 'DRAFT',
    CONSTRAINT card_product_pkey PRIMARY KEY (card_id),""")
d = rep(d, """    CONSTRAINT card_product_brand_opt_list_check CHECK (db_pipeline.fn_valid_brand_opt_list(brand_opt_list))
);""", """    CONSTRAINT card_product_brand_opt_list_check CHECK (db_pipeline.fn_valid_brand_opt_list(brand_opt_list)),
    CONSTRAINT card_product_card_cond_expr_check CHECK (db_pipeline.fn_valid_cond_expr(card_cond_expr))
);""")
d = rep(d, "COMMENT ON COLUMN db_pipeline.card_product.update_user_id IS '수정 사용자 아이디';\n",
        "COMMENT ON COLUMN db_pipeline.card_product.update_user_id IS '수정 사용자 아이디';\n"
        "COMMENT ON COLUMN db_pipeline.card_product.card_cond_expr IS '카드 공통 조건';\n"
        "COMMENT ON COLUMN db_pipeline.card_product.card_cond_status_cd IS '카드 공통 조건 상태';\n")

# card_policy_version
d = cut(d, "CREATE TABLE db_pipeline.card_policy_version (", "CREATE TABLE db_pipeline.card_product_doc (")

# card_product_doc
d = rep(d, "    effective_from date,\n    effective_to_excl date,\n", "")
d = rep(d, """    CONSTRAINT card_product_doc_period_check CHECK
        (effective_to_excl IS NULL OR
         (effective_from IS NOT NULL AND effective_to_excl > effective_from)),
    CONSTRAINT card_product_doc_approved_check CHECK
        (approval_status_cd <> 'APPROVED' OR
         (effective_from IS NOT NULL AND length(trim(applicability_basis_txt)) > 0))
""", """    CONSTRAINT card_product_doc_approved_check CHECK
        (approval_status_cd <> 'APPROVED' OR length(trim(applicability_basis_txt)) > 0)
""")
d = rep(d, """COMMENT ON COLUMN db_pipeline.card_product_doc.effective_from IS '문서 적용 시작일';
COMMENT ON COLUMN db_pipeline.card_product_doc.effective_to_excl IS '문서 적용 종료일';
""", "")

# card_bnft
d = rep(d, """    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft') NOT NULL,""",
        """    card_id bigint NOT NULL,
    card_bnft_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft') NOT NULL,""")
d = rep(d, """    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id),
    UNIQUE (card_id, policy_ver_id, bnft_cd),""", """    PRIMARY KEY (card_id, card_bnft_id),
    UNIQUE (card_id, bnft_cd),""")
d = rep(d, "COMMENT ON COLUMN db_pipeline.card_bnft.policy_ver_id IS '정책 버전 아이디';\n", "")

# card_limit_pool
d = rep(d, """    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    pool_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_limit_pool') NOT NULL,""",
        """    card_id bigint NOT NULL,
    pool_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_limit_pool') NOT NULL,""")
d = rep(d, "    PRIMARY KEY (card_id, policy_ver_id, pool_id),\n", "    PRIMARY KEY (card_id, pool_id),\n")
d = rep(d, "COMMENT ON COLUMN db_pipeline.card_limit_pool.policy_ver_id IS '정책 버전 아이디';\n", "")

# card_bnft_common
d = rep(d, """    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    common_bnft_id varchar(20) NOT NULL,""", """    card_id bigint NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    common_bnft_id varchar(20) NOT NULL,""")
d = rep(d, "    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, common_bnft_id, common_ver_id)\n",
        "    PRIMARY KEY (card_id, card_bnft_id, common_bnft_id, common_ver_id)\n")
d = rep(d, "COMMENT ON COLUMN db_pipeline.card_bnft_common.policy_ver_id IS '정책 버전 아이디';\n", "")

# card_policy_evidence -> card_evidence_link
d = rep(d, """    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    ev_link_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_policy_evidence') NOT NULL,""",
        """    card_id bigint NOT NULL,
    ev_link_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link') NOT NULL,""")
d = rep(d, "    PRIMARY KEY (card_id, policy_ver_id, ev_link_id),\n", "    PRIMARY KEY (card_id, ev_link_id),\n")
d = rep(d, """    CONSTRAINT card_policy_evidence_natural_key UNIQUE NULLS NOT DISTINCT
        (card_id, policy_ver_id, ev_subject_cd,""", """    CONSTRAINT card_policy_evidence_natural_key UNIQUE NULLS NOT DISTINCT
        (card_id, ev_subject_cd,""")
d = rep(d, "            WHEN 'POLICY' THEN num_nonnulls(card_bnft_id, rule_key, relation_key, pool_id) = 0",
        "            WHEN 'CARD' THEN num_nonnulls(card_bnft_id, rule_key, relation_key, pool_id) = 0")
d = rep(d, "COMMENT ON TABLE db_pipeline.card_policy_evidence IS '정책 근거 관계';", "COMMENT ON TABLE db_pipeline.card_policy_evidence IS '카드 근거 관계';")
d = rep(d, "COMMENT ON COLUMN db_pipeline.card_policy_evidence.policy_ver_id IS '정책 버전 아이디';\n", "")

# indexes
d = rep(d, """CREATE INDEX card_product_doc_current_idx
    ON db_pipeline.card_product_doc (card_id, effective_from, effective_to_excl)
    WHERE approval_status_cd = 'APPROVED';

""", "")
d = rep(d, """CREATE INDEX ix_card_policy_version_lookup ON db_pipeline.card_policy_version (card_id, policy_status_cd, valid_from, valid_to_excl);

CREATE INDEX ix_card_policy_version_doc_gin ON db_pipeline.card_policy_version USING gin (source_doc_list jsonb_path_ops);

""", "")
d = rep(d, "CREATE INDEX ix_card_policy_evidence_subject ON db_pipeline.card_policy_evidence (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, rule_key);",
        "CREATE INDEX ix_card_policy_evidence_subject ON db_pipeline.card_policy_evidence (card_id, ev_subject_cd, card_bnft_id, rule_key);")

# views
d = cut(d, "CREATE VIEW db_pipeline.v_card_policy_doc AS", "CREATE VIEW db_pipeline.v_card_rule AS")
d = rep(d, "'LOCAL'::text AS rule_source_cd, r.card_id, r.policy_ver_id, r.card_bnft_id, r.rule_key,\n       NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id,\n       t.value",
        "'LOCAL'::text AS rule_source_cd, r.card_id, r.card_bnft_id, r.rule_key,\n       NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id,\n       t.value")
d = rep(d, "SELECT 'COMMON', NULL, NULL, NULL, r.rule_key, r.common_bnft_id", "SELECT 'COMMON', NULL, NULL, r.rule_key, r.common_bnft_id")
d = cut(d, "WITH src AS (", "SELECT s.owner_cd, s.card_id,", """WITH src AS (
    SELECT 'CARD'::text AS owner_cd, p.card_id, NULL::varchar AS card_bnft_id,
           NULL::text AS rule_key, NULL::varchar AS pool_id, NULL::text AS item_key,
           NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id,
           p.card_cond_expr AS expr
    FROM db_pipeline.card_product p WHERE p.card_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'BNFT', b.card_id, b.card_bnft_id, NULL, NULL, NULL, NULL, NULL, b.bnft_cond_expr
    FROM db_pipeline.card_bnft b WHERE b.bnft_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'RULE', r.card_id, r.card_bnft_id, r.rule_key, NULL, NULL, NULL, NULL, r.cond_expr
    FROM db_pipeline.v_card_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'POOL_TIER', t.card_id, NULL, NULL, t.pool_id, t.tier_key, NULL, NULL, t.cond_expr
    FROM db_pipeline.v_card_limit_tier t WHERE t.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'COMMON_RULE', NULL, NULL, r.rule_key, NULL, NULL, r.common_bnft_id, r.common_ver_id, r.cond_expr
    FROM db_pipeline.v_card_common_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'COMMON_LIMIT', NULL, NULL, l.rule_key, NULL, l.limit_key, l.common_bnft_id, l.common_ver_id, l.cond_expr
    FROM db_pipeline.v_card_common_limit l WHERE l.cond_expr IS NOT NULL
)
""")
d = rep(d, """SELECT 'card_policy_version.policy_status_cd'::text AS source_nm, 'POLICY_STATUS'::varchar(20) AS common_code_grp_id, policy_status_cd::text AS cd_value
FROM db_pipeline.card_policy_version WHERE policy_status_cd IS NOT NULL
UNION ALL
""", "")
d = rep(d, """FROM db_pipeline.card_product WHERE product_status_cd IS NOT NULL
UNION ALL
""", """FROM db_pipeline.card_product WHERE product_status_cd IS NOT NULL
UNION ALL
SELECT 'card_product.card_cond_status_cd'::text AS source_nm, 'ITEM_STATUS'::varchar(20) AS common_code_grp_id, card_cond_status_cd::text AS cd_value
FROM db_pipeline.card_product WHERE card_cond_status_cd IS NOT NULL
UNION ALL
""")
d = rep(d, """SELECT 'card_policy_version.source_doc_list[].source_role_cd', 'DOC_ROLE', source_role_cd::text
FROM db_pipeline.v_card_policy_doc WHERE source_role_cd IS NOT NULL
UNION ALL
""", "")

# integrity gates
d = rep(d, """SELECT 'policy_without_product' AS gate_cd, x.card_id || '/' || x.policy_ver_id AS issue_key
FROM db_pipeline.card_policy_version x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'bnft_without_policy', x.card_id || '/' || x.policy_ver_id || '/' || x.card_bnft_id
FROM db_pipeline.card_bnft x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
""", """SELECT 'bnft_without_product' AS gate_cd, x.card_id || '/' || x.card_bnft_id AS issue_key
FROM db_pipeline.card_bnft x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
""")
d = rep(d, """SELECT 'pool_without_policy', x.card_id || '/' || x.policy_ver_id || '/' || x.pool_id
FROM db_pipeline.card_limit_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
""", """SELECT 'pool_without_product', x.card_id || '/' || x.pool_id
FROM db_pipeline.card_limit_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
""")
d = rep(d, """SELECT 'policy_period_overlap', a.card_id || '/' || a.policy_ver_id || '/' || b.policy_ver_id
FROM db_pipeline.card_policy_version a
JOIN db_pipeline.card_policy_version b ON a.card_id = b.card_id AND a.policy_ver_id < b.policy_ver_id
WHERE a.policy_status_cd = 'APPROVED' AND b.policy_status_cd = 'APPROVED'
  AND daterange(a.valid_from, a.valid_to_excl, '[)') && daterange(b.valid_from, b.valid_to_excl, '[)')
UNION ALL
SELECT 'policy_doc_orphan', x.card_id || '/' || x.policy_ver_id || '/' || x.card_doc_id
FROM db_pipeline.v_card_policy_doc x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc d WHERE d.card_doc_id = x.card_doc_id)
""", """SELECT 'product_doc_without_product', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'product_doc_orphan', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc d WHERE d.card_doc_id = x.card_doc_id)
""")
d = rep(d, """UNION ALL
SELECT 'evidence_not_approved', l.evidence_id
""", """UNION ALL
SELECT 'evidence_doc_not_linked', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_policy_evidence l
JOIN db_pipeline.card_source_evidence e USING (evidence_id)
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc d WHERE (d.card_id, d.card_doc_id) = (l.card_id, e.card_doc_id))
UNION ALL
SELECT 'evidence_not_approved', l.evidence_id
""")
d = rep(d, "    WHEN 'POLICY' THEN EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (l.card_id, l.policy_ver_id))\n",
        "    WHEN 'CARD' THEN EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = l.card_id)\n")

# 남은 policy_ver_id는 모두 키 목록·조인 조건 안에 있다. 뷰 영역에서만 지운다.
head, tail = d.split("CREATE VIEW db_pipeline.v_card_brand_opt AS", 1)
tail = re.sub(r"\b\w+\.policy_ver_id,\s*", "", tail)
tail = re.sub(r"\bpolicy_ver_id,\s*", "", tail)
tail = re.sub(r",\s*\w+\.policy_ver_id\)", ")", tail)
tail = re.sub(r" \|\| '/' \|\| \w+\.policy_ver_id", "", tail)
tail = re.sub(r"\((\w+)\.card_id\) = \((\w+)\.card_id\)", r"\1.card_id = \2.card_id", tail)
d = head + "CREATE VIEW db_pipeline.v_card_brand_opt AS" + tail
d = d.replace("seq_card_evidence_link", "@@SEQ@@")
d = d.replace("ix_card_policy_evidence_", "ix_card_evidence_link_")
d = d.replace("card_policy_evidence_", "card_evidence_link_")
d = d.replace("card_policy_evidence", "card_evidence_link")
d = d.replace("@@SEQ@@", "seq_card_evidence_link")
for bad in ("policy_ver_id", "card_policy_version", "card_policy_evidence", "policy_cond_expr", "source_doc_list",
            "effective_from", "effective_to_excl", "v_card_policy_doc", "fn_valid_doc_ref_list"):
    if bad in d:
        line = next(x for x in d.splitlines() if bad in x)
        raise SystemExit(f"left over {bad}: {line[:120]}")

# ---------------------------------------------------------------- 2차: 공통 혜택 구조 제거
d = rep(d, "-- card_common_policy_version (common benefit versions) is a separate concept and is kept.\n",
        "-- V7 also removes the common benefit tables: a brand benefit is stored per card in card_bnft, while the\n"
        "-- brand PDF, its AI extraction and its source evidence are stored once and shared by evidence links.\n")
d = rep(d, '--                     common policy version uses "limit_list" instead of "pool_refs".\n', "")
d = rep(d, '''--   limit_list       [{"limit_key","pool_key","period_cd","cap_unit_cd","aggregation_key_cd",
--                      "predicate_state_cd","limit_num","cond_expr"}]
''', "")
d = rep(d, "AND rule cond_expr (LOCAL or COMMON).", "AND rule cond_expr.")
d = cut(d, "CREATE FUNCTION db_pipeline.fn_valid_limit_list", "CREATE FUNCTION db_pipeline.fn_valid_brand_opt_list")
d = rep(d, """        ELSIF p_owner = 'COMMON' THEN
            IF v_rule ? 'pool_refs'
               OR NOT db_pipeline.fn_valid_limit_list(coalesce(v_rule->'limit_list', '[]'::jsonb)) THEN
                RETURN false;
            END IF;
        ELSE
""", "        ELSE\n")
d = rep(d, "IF v_rule ? 'limit_list' OR jsonb_typeof(coalesce(v_rule->'pool_refs', '[]'::jsonb)) <> 'array' THEN",
        "IF jsonb_typeof(coalesce(v_rule->'pool_refs', '[]'::jsonb)) <> 'array' THEN")
d = rep(d, "'계산 규칙 목록 JSONB 계약 검증. rule_key 중복, 금액 타입, 조건 상태, 대상, pool_refs(LOCAL), limit_list(COMMON) 검사'",
        "'계산 규칙 목록 JSONB 계약 검증. rule_key 중복, 금액 타입, 조건 상태, 대상, pool_refs 검사. p_owner는 LOCAL만 허용'")
d = rep(d, """CREATE SEQUENCE db_pipeline.seq_card_common_bnft INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_bnft IS 'card_common_bnft.common_bnft_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_policy_version IS 'card_common_policy_version.common_ver_id 로컬 업무 ID 발급';

""", "")
d = rep(d, """    verification_status_cd varchar(25) NOT NULL,
    PRIMARY KEY (card_id, card_bnft_id),""", """    verification_status_cd varchar(25) NOT NULL,
    bnft_valid_from date,
    bnft_valid_to_excl date,
    PRIMARY KEY (card_id, card_bnft_id),""")
d = rep(d, "    CONSTRAINT card_bnft_ck_5 CHECK (bnft_origin_cd <> 'COMMON_LINK' OR jsonb_array_length(rule_list) = 0)\n",
        "    CONSTRAINT card_bnft_ck_5 CHECK (bnft_origin_cd <> 'BRAND_SERVICE' OR bnft_scope_cd = 'BRAND'),\n"
        "    CONSTRAINT card_bnft_ck_6 CHECK\n"
        "        (bnft_valid_to_excl IS NULL OR bnft_valid_from IS NULL OR bnft_valid_to_excl > bnft_valid_from)\n")
d = rep(d, "COMMENT ON COLUMN db_pipeline.card_bnft.verification_status_cd IS '혜택 검증 상태';\n",
        "COMMENT ON COLUMN db_pipeline.card_bnft.verification_status_cd IS '혜택 검증 상태';\n"
        "COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_from IS '혜택 제공 시작일';\n"
        "COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_to_excl IS '혜택 제공 종료일(미포함)';\n")
d = cut(d, "-- ---------------------------------------------------------------------------\n-- 공통 혜택 영역.",
        "-- ---------------------------------------------------------------------------\n-- 근거 연결 영역")
d = cut(d, "CREATE TABLE db_pipeline.card_common_rule_evidence (",
        "-- ---------------------------------------------------------------------------\n-- 계산 방법·원천 문서")
d = rep(d, "    stg_item_seq smallint NOT NULL,\n    card_id bigint NOT NULL,\n", "    stg_item_seq smallint NOT NULL,\n    card_id bigint,\n")
d = rep(d, "COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디';",
        "COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디(NULL이면 특정 카드에 연결되지 않은 후보)';")
for line in ("CREATE INDEX ix_card_bnft_common_lookup ON db_pipeline.card_bnft_common (common_bnft_id, common_ver_id);\n\n",
             "CREATE INDEX ix_card_common_policy_version_lookup ON db_pipeline.card_common_policy_version (common_bnft_id, policy_status_cd, valid_from, valid_to_excl);\n\n",
             "CREATE INDEX ix_card_common_rule_list_gin ON db_pipeline.card_common_policy_version USING gin (rule_list jsonb_path_ops);\n\n",
             "CREATE INDEX ix_card_common_bnft_service ON db_pipeline.card_common_bnft (provider_cd, service_grade_cd, service_type_cd);\n\n",
             "CREATE INDEX ix_card_common_rule_evidence_evidence ON db_pipeline.card_common_rule_evidence (evidence_id);\n\n"):
    d = rep(d, line, "")
d = cut(d, "CREATE VIEW db_pipeline.v_card_common_rule AS", "CREATE VIEW db_pipeline.v_card_rule_pool AS")
d = cut(d, "CREATE VIEW db_pipeline.v_card_common_limit AS", "CREATE VIEW db_pipeline.v_card_cond_atom AS")
d = cut(d, "CREATE VIEW db_pipeline.v_card_rule_target AS", "CREATE VIEW db_pipeline.v_card_limit_tier AS", """CREATE VIEW db_pipeline.v_card_rule_target AS
SELECT r.card_id, r.card_bnft_id, r.rule_key,
       t.value->>'target_type_cd' AS target_type_cd,
       t.value->>'target_key' AS target_key,
       t.value->>'target_nm' AS target_nm
FROM db_pipeline.v_card_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.target_list) AS t(value);

COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원';

""")
d = cut(d, "WITH src AS (", "SELECT s.owner_cd, s.card_id,", """WITH src AS (
    SELECT 'CARD'::text AS owner_cd, p.card_id, NULL::varchar AS card_bnft_id,
           NULL::text AS rule_key, NULL::varchar AS pool_id, NULL::text AS item_key,
           p.card_cond_expr AS expr
    FROM db_pipeline.card_product p WHERE p.card_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'BNFT', b.card_id, b.card_bnft_id, NULL, NULL, NULL, b.bnft_cond_expr
    FROM db_pipeline.card_bnft b WHERE b.bnft_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'RULE', r.card_id, r.card_bnft_id, r.rule_key, NULL, NULL, r.cond_expr
    FROM db_pipeline.v_card_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'POOL_TIER', t.card_id, NULL, NULL, t.pool_id, t.tier_key, t.cond_expr
    FROM db_pipeline.v_card_limit_tier t WHERE t.cond_expr IS NOT NULL
)
""")
d = rep(d, "SELECT s.owner_cd, s.card_id, s.card_bnft_id, s.rule_key, s.pool_id, s.item_key,\n       s.common_bnft_id, s.common_ver_id,\n",
        "SELECT s.owner_cd, s.card_id, s.card_bnft_id, s.rule_key, s.pool_id, s.item_key,\n")
d = cut(d, "CREATE VIEW db_pipeline.v_card_bnft_rule_effective AS", "CREATE VIEW db_pipeline.v_common_cd_usage AS", """CREATE VIEW db_pipeline.v_card_bnft_rule_effective AS
SELECT b.card_id, b.card_bnft_id, b.bnft_nm, b.bnft_origin_cd, b.bnft_scope_cd, b.bnft_brand_opt_cds,
       b.bnft_valid_from, b.bnft_valid_to_excl, r.rule_key,
       r.calc_method_cd, r.method_ver, r.value_num, r.value_unit_cd, r.payout_unit_cd, r.basis_amt,
       r.calc_params, r.predicate_state_cd, r.target_list,
       b.bnft_cond_expr, r.cond_expr AS rule_cond_expr, r.rule_status_cd
FROM db_pipeline.card_bnft b
JOIN db_pipeline.v_card_rule r
  ON (r.card_id, r.card_bnft_id) = (b.card_id, b.card_bnft_id);

COMMENT ON VIEW db_pipeline.v_card_bnft_rule_effective IS '혜택과 계산 규칙의 단일 출력. 제공 기간은 걸러내지 않으므로 조회 기준일로 판정. 값은 정책 후보이며 거래별 보상액이 아님';

""")


def filter_union(text, view, drop):
    """뷰 본문을 UNION ALL 단위로 나눠 drop(part)가 참인 부분을 뺀다."""
    start = text.index(f"CREATE VIEW db_pipeline.{view} AS")
    end = text.index(f"COMMENT ON VIEW db_pipeline.{view} IS")
    parts = text[start:end].split("UNION ALL\n")
    kept = [p for p in parts if not drop(p)]
    return text[:start] + "UNION ALL\n".join(kept) + text[end:], len(parts) - len(kept)


d, n = filter_union(d, "v_common_cd_usage", lambda p: "card_common" in p or "card_bnft_common" in p)
assert n == 15, n
COMMON_GATES = ("common_link_orphan", "common_link_without_link", "common_link_multi_approved_same_period",
                "common_pool_key_conflict", "common_evidence_subject_orphan", "common_evidence_item_key_missing")
d, n = filter_union(d, "v_card_integrity_issue", lambda p: p.lstrip().startswith(tuple(f"SELECT '{g}'" for g in COMMON_GATES)))
assert n == 6, n
d = rep(d, "WHERE x.bnft_origin_cd = 'LOCAL' AND x.verification_status_cd = 'CONFIRMED' AND jsonb_array_length(x.rule_list) = 0",
        "WHERE x.verification_status_cd = 'CONFIRMED' AND jsonb_array_length(x.rule_list) = 0")
d = rep(d, """FROM (SELECT calc_method_cd, method_ver FROM db_pipeline.v_card_rule
      UNION SELECT calc_method_cd, method_ver FROM db_pipeline.v_card_common_rule) m
""", "FROM (SELECT DISTINCT calc_method_cd, method_ver FROM db_pipeline.v_card_rule) m\n")
d = rep(d, """FROM (SELECT evidence_id FROM db_pipeline.card_evidence_link
      UNION SELECT evidence_id FROM db_pipeline.card_common_rule_evidence) l
""", "FROM (SELECT DISTINCT evidence_id FROM db_pipeline.card_evidence_link) l\n")
NEW_GATES = """SELECT 'product_doc_role_type_mismatch', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
JOIN db_pipeline.card_doc d ON d.card_doc_id = x.card_doc_id
WHERE x.doc_role_cd = 'BRAND_SERVICE' AND d.doc_type_cd <> 'BRAND_SERVICE'
UNION ALL
SELECT 'shared_doc_bound_to_card', d.card_doc_id
FROM db_pipeline.card_doc d
WHERE d.card_id IS NOT NULL AND d.doc_type_cd IN ('BRAND_SERVICE', 'TERMS')
UNION ALL
SELECT 'brand_doc_option_conflict', z.card_doc_id
FROM (SELECT x.card_doc_id
      FROM db_pipeline.card_product_doc x
      CROSS JOIN LATERAL unnest(x.brand_opt_cds) AS o(cd)
      JOIN db_pipeline.v_card_brand_opt v ON (v.card_id, v.brand_opt_cd) = (x.card_id, o.cd)
      WHERE x.doc_role_cd = 'BRAND_SERVICE'
      GROUP BY 1 HAVING count(DISTINCT (v.brand_cd, v.service_grade_cd, v.service_type_cd)) > 1) z
UNION ALL
SELECT 'brand_bnft_doc_not_linked', b.card_id || '/' || b.card_bnft_id || '/' || o.cd
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) AS o(cd)
WHERE b.bnft_origin_cd = 'BRAND_SERVICE'
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc x
                  WHERE x.card_id = b.card_id AND x.doc_role_cd = 'BRAND_SERVICE' AND o.cd = ANY (x.brand_opt_cds))
UNION ALL
SELECT 'brand_bnft_confirmed_without_evidence', b.card_id || '/' || b.card_bnft_id
FROM db_pipeline.card_bnft b
WHERE b.bnft_origin_cd = 'BRAND_SERVICE' AND b.verification_status_cd = 'CONFIRMED'
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link l
                  WHERE (l.card_id, l.card_bnft_id) = (b.card_id, b.card_bnft_id))
UNION ALL
SELECT 'evidence_brand_opt_mismatch', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e USING (evidence_id)
JOIN db_pipeline.card_bnft b ON (b.card_id, b.card_bnft_id) = (l.card_id, l.card_bnft_id)
JOIN db_pipeline.card_product_doc x ON (x.card_id, x.card_doc_id) = (l.card_id, e.card_doc_id)
WHERE x.doc_role_cd = 'BRAND_SERVICE' AND NOT (coalesce(b.bnft_brand_opt_cds, '{}') && x.brand_opt_cds)
UNION ALL
SELECT 'stg_card_not_linked', s.card_extr_stg_id
FROM db_pipeline.card_extr_stg s
WHERE s.card_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc x WHERE (x.card_id, x.card_doc_id) = (s.card_id, s.card_doc_id))
UNION ALL
SELECT 'common_cd_invalid',"""
d = rep(d, "SELECT 'common_cd_invalid',", NEW_GATES)

# ---------------------------------------------------------------- 3차: card_method_catalog 제거
d = rep(d, "-- Effective condition: card_cond_expr AND bnft_cond_expr AND rule cond_expr.",
        "-- method_ver and predicate_method_ver are representation contract versions, currently 1. V7 has no calculation\n"
        "-- engine or method catalog, so nothing checks them against an executable handler.\n"
        "-- Effective condition: card_cond_expr AND bnft_cond_expr AND rule cond_expr.")
d = cut(d, "CREATE TABLE db_pipeline.card_method_catalog (", "CREATE TABLE db_pipeline.card_doc (")
d = rep(d, "-- 계산 방법·원천 문서·AI 파싱·근거 영역.", "-- 원천 문서·AI 파싱·근거 영역.")
d, n = filter_union(d, "v_common_cd_usage", lambda p: "card_method_catalog" in p)
assert n == 2, n
d, n = filter_union(d, "v_card_integrity_issue", lambda p: p.lstrip().startswith(("SELECT 'method_not_in_catalog'", "SELECT 'catalog_method_not_in_code'")))
assert n == 2, n
d = rep(d, "WITH atoms AS (SELECT * FROM db_pipeline.v_card_cond_atom),\nfallback AS (", """WITH atoms AS (SELECT * FROM db_pipeline.v_card_cond_atom),
-- 방식별 필수값. 지급 단위는 포인트·마일리지일 수 있어 정액·금액당 방식의 단위를 특정 값으로 제한하지 않는다.
-- final_yn이 true면 확정 데이터의 무결성 위반, false면 확정 전 값 누락이다. 값을 보완하지 않고 구분만 한다.
rule_value_gap AS (
    SELECT r.card_id, r.card_bnft_id, r.rule_key,
           (r.rule_status_cd = 'CONFIRMED' OR b.verification_status_cd = 'CONFIRMED') AS final_yn
    FROM db_pipeline.v_card_rule r
    JOIN db_pipeline.card_bnft b ON (b.card_id, b.card_bnft_id) = (r.card_id, r.card_bnft_id)
    WHERE r.rule_status_cd <> 'RETIRED'
      AND ((r.calc_method_cd IN ('PERCENT_OF_TXN', 'FIXED_PER_TXN', 'UNITS_PER_AMOUNT', 'MULTIPLY_EXTERNAL_POINTS') AND r.value_num IS NULL)
           OR (r.calc_method_cd = 'UNITS_PER_AMOUNT' AND r.basis_amt IS NULL)
           OR (r.calc_method_cd = 'PERCENT_OF_TXN' AND r.value_unit_cd IS DISTINCT FROM 'PERCENT')
           OR (r.calc_method_cd = 'MULTIPLY_EXTERNAL_POINTS' AND r.value_unit_cd IS DISTINCT FROM 'MULTIPLIER')
           OR (r.calc_method_cd IN ('FIXED_PER_TXN', 'UNITS_PER_AMOUNT') AND r.value_unit_cd IN ('PERCENT', 'MULTIPLIER')))
),
-- 필수 파라미터가 정해진 판정 방식만 검사한다. cond_params를 모든 조건에 강제하지 않는다.
predicate_param_gap AS (
    SELECT a.owner_cd, a.card_id, a.atom_key,
           (a.cond_status_cd = 'CONFIRMED' OR a.expr_status_cd = 'CONFIRMED') AS final_yn
    FROM atoms a
    WHERE a.cond_status_cd <> 'RETIRED'
      AND ((a.predicate_method_cd = 'EVERY_MONTH_MIN_SPEND'
            AND (a.cond_min_amt IS NULL OR jsonb_typeof(a.cond_params->'window_months') IS DISTINCT FROM 'number'))
           OR (a.predicate_method_cd = 'MONTH_IN'
               AND CASE WHEN jsonb_typeof(a.cond_params->'months') = 'array'
                        THEN jsonb_array_length(a.cond_params->'months') = 0 ELSE true END))
),
fallback AS (""")
d = rep(d, "SELECT 'excl_item_unknown',", """SELECT CASE WHEN g.final_yn THEN 'rule_method_value_missing' ELSE 'rule_method_value_pending' END,
       g.card_id || '/' || g.card_bnft_id || '/' || g.rule_key
FROM rule_value_gap g
UNION ALL
SELECT CASE WHEN g.final_yn THEN 'predicate_params_missing' ELSE 'predicate_params_pending' END,
       g.owner_cd || '/' || g.card_id || '/' || g.atom_key
FROM predicate_param_gap g
UNION ALL
SELECT 'excl_item_unknown',""")
d = rep(d, "'승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음'",
        "'승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음. *_pending은 확정 전 항목의 값 누락(검토 대기)이고 나머지는 무결성 위반'")
for bad in ("card_method_catalog", "method_not_in_catalog", "catalog_method_not_in_code", "handler_key", "param_schema", "method_status_cd", "method_kind_cd", "METHOD_KIND", "METHOD_STATUS"):
    if bad in d:
        raise SystemExit(f"stage3 left over {bad}: " + next(x for x in d.splitlines() if bad in x)[:120])
for bad in ("card_common", "card_bnft_common", "common_bnft_id", "common_ver_id", "COMMON_LINK", "fn_valid_limit_list", "limit_list", "POLICY_STATUS", "'COMMON'"):
    if bad in d:
        raise SystemExit(f"stage2 left over {bad}: " + next(x for x in d.splitlines() if bad in x)[:120])
(OUT / "db_pipeline_schemaV7_draft.sql").write_text(d, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------- seed
s = (SQL / "db_pipeline_common_code_seedV6.sql").read_text(encoding="utf-8")
s = rep(s, "-- V6 공통코드 초기 데이터. db_pipeline_schemaV6_draft.sql 실행 후 적용한다.",
        "-- V7 공통코드 초기 데이터. db_pipeline_schemaV7_draft.sql 실행 후 적용한다.")
s = rep(s, "-- V5 CHECK, V5 설계 문서, PDF에서 확인한 코드만 포함한다.\n",
        "-- V5 CHECK, V5 설계 문서, PDF에서 확인한 코드만 포함한다.\n"
        "-- V6과 다른 점: EV_SUBJECT.POLICY를 CARD로, BNFT_ORIGIN.COMMON_LINK를 BRAND_SERVICE로 교체하고\n"
        "-- 사용처가 없어진 POLICY_STATUS 그룹과 EV_ITEM.LIMIT을 뺐다. 나머지 코드는 V6과 같다.\n")
s = rep(s, "('EV_SUBJECT', 'POLICY', '정책판', 'SEED_TEST', 'SEED_TEST')", "('EV_SUBJECT', 'CARD', '카드', 'SEED_TEST', 'SEED_TEST')")
s = rep(s, "('BNFT_ORIGIN', 'LOCAL', '상품 고유 규칙', 'SEED_TEST', 'SEED_TEST')", "('BNFT_ORIGIN', 'LOCAL', '상품 고유 혜택', 'SEED_TEST', 'SEED_TEST')")
s = rep(s, "('BNFT_ORIGIN', 'COMMON_LINK', '공통 정책 연결', 'SEED_TEST', 'SEED_TEST')", "('BNFT_ORIGIN', 'BRAND_SERVICE', '브랜드 공통 서비스', 'SEED_TEST', 'SEED_TEST')")
s = rep(s, "    ('POLICY_STATUS', '정책판 상태', 'SEED_TEST', 'SEED_TEST'),\n", "")
s = rep(s, "    ('POLICY_STATUS', 'DRAFT', '작성 중', 'SEED_TEST', 'SEED_TEST'),\n    ('POLICY_STATUS', 'APPROVED', '승인', 'SEED_TEST', 'SEED_TEST'),\n    ('POLICY_STATUS', 'RETIRED', '폐기', 'SEED_TEST', 'SEED_TEST'),\n", "")
s = rep(s, "    ('EV_ITEM', 'LIMIT', '공통 한도', 'SEED_TEST', 'SEED_TEST'),\n", "")
s = rep(s, "-- 사용처가 없어진 POLICY_STATUS 그룹과 EV_ITEM.LIMIT을 뺐다. 나머지 코드는 V6과 같다.\n",
        "-- 사용처가 없어진 POLICY_STATUS, METHOD_KIND, METHOD_STATUS 그룹과 EV_ITEM.LIMIT을 뺐다. 나머지 코드는 V6과 같다.\n")
s = rep(s, "    ('METHOD_KIND', '방법 종류', 'SEED_TEST', 'SEED_TEST'),\n    ('METHOD_STATUS', '방법 실행 상태', 'SEED_TEST', 'SEED_TEST'),\n", "")
s = rep(s, """    ('METHOD_KIND', 'CALC', '계산 방법', 'SEED_TEST', 'SEED_TEST'),
    ('METHOD_KIND', 'PREDICATE', '술어 방법', 'SEED_TEST', 'SEED_TEST'),
    ('METHOD_STATUS', 'ACTIVE', '실행 가능', 'SEED_TEST', 'SEED_TEST'),
    ('METHOD_STATUS', 'UNEXECUTABLE', '핸들러 미배포', 'SEED_TEST', 'SEED_TEST'),
""", "")
(OUT / "db_pipeline_common_code_seedV7.sql").write_text(s, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------- descriptions
DESC_GRP = {
    "DOC_ROLE": '원천 문서가 특정 상품에서 어떤 역할을 하는지 구분하는 공통코드. card_product_doc.doc_role_cd에서 사용한다. 문서 자체의 종류를 나타내는 DOC_TYPE과 달리 상품과의 관계에 붙는 값이므로 같은 문서라도 연결 상품에 따라 역할을 따로 기록한다.',
    "POLICY_STATUS": '공통 혜택 정책판의 생명주기를 구분하는 공통코드. card_common_policy_version.policy_status_cd에서 사용한다. 개별 규칙·조건이 아니라 적용 기간을 가진 공통 정책판 단위의 상태이며, 규칙·조건과 카드 공통 조건의 상태는 ITEM_STATUS로, 관계·근거의 승인은 APPROVAL_STATUS로 관리한다.',
    "ITEM_STATUS": '계산 규칙, 조건식, 카드 공통 조건이 작성 중인지 확정되었는지를 구분하는 공통코드. JSONB 안의 rule_status_cd, cond_status_cd, expr_status_cd와 card_product.card_cond_status_cd에서 사용한다. 공통 정책판 단위의 POLICY_STATUS보다 작은 규칙·조건 단위의 상태이고, 혜택 단위 검증을 나타내는 VERIFY_STATUS와도 구분된다.',
    "COND_TYPE": '조건식 atom의 업무 유형을 분류하는 공통코드. 조건식 atom의 cond_type_cd에서 사용하고 카드 공통, 혜택, 규칙, 한도 구간의 조건에 모두 적용된다. 금액을 어떤 기준으로 비교하는지는 COND_BASIS가, 금액 구간으로 표현되지 않는 판정법은 PREDICATE_METHOD가 맡는다.',
    "EV_SUBJECT": '원문 근거가 어떤 카드 대상을 뒷받침하는지 구분하는 공통코드. card_evidence_link.ev_subject_cd에서 사용하며 값에 따라 card_bnft_id, rule_key, relation_key, pool_id 중 채워야 할 컬럼이 CHECK로 고정된다. 대상 안의 세부 항목은 EV_ITEM이 구분한다.',
    "EV_ITEM": '근거가 대상 전체를 가리키는지 대상 안의 JSONB 항목을 가리키는지 구분하는 공통코드. card_evidence_link.ev_item_cd와 card_common_rule_evidence.ev_item_cd에서 사용하고 ev_item_key와 짝을 이룬다. 대상의 종류를 나타내는 EV_SUBJECT보다 한 단계 아래를 가리킨다.',
    "DOC_STATUS": '수집된 원천 문서를 파이프라인에서 사용할지 구분하는 공통코드. card_doc.doc_status에서 사용하며 AI 입력 대상은 ACTIVE 문서로 제한된다. 상품별 적용 여부는 이 값이 아니라 승인된 문서 관계로 판정하며, 판매 상태를 나타내는 PRODUCT_STATUS와도 구분된다.',
}
DESC_CD = {
    ("APPROVAL_STATUS", "APPROVED"): '대상 데이터가 해당 업무의 검증 기준을 충족해 사용 승인을 받은 상태. 문서 연결은 적용 근거가 있어야 승인할 수 있고(card_product_doc_approved_check), 공통 혜택 적용은 이 값일 때만 v_card_bnft_rule_effective에 포함된다. 승인 대상과 범위는 사용하는 테이블에 따라 결정된다.',
    ("POLICY_STATUS", "DRAFT"): '공통 정책판을 작성하거나 검토하는 중인 상태. 내용과 적용 기간이 아직 확정되지 않았으므로 확정 정책으로 사용하면 안 된다. 개별 규칙의 작성 상태는 ITEM_STATUS.DRAFT로 따로 관리한다.',
    ("POLICY_STATUS", "APPROVED"): '공통 정책판이 승인되어 적용 기간 동안 유효한 상태. 공통 정책판은 이 값일 때만 v_card_bnft_rule_effective에 포함된다. 관계·근거 승인 APPROVAL_STATUS.APPROVED와는 관리 단위가 다르다.',
    ("POLICY_STATUS", "RETIRED"): '공통 정책판을 더 이상 적용하지 않기로 폐기한 상태. APPROVED 정책판을 찾는 조회에서 제외되며, 작성이 끝나지 않은 DRAFT와 달리 사용을 종료한 정책판을 나타낸다.',
    ("ITEM_STATUS", "DRAFT"): '규칙 또는 조건이 작성 중이라 아직 확정되지 않은 상태. AI 추출 결과를 정규화할 때 부여하는 초기값이며 card_product.card_cond_status_cd의 기본값이다. 공통 정책판 전체가 아니라 규칙·조건 단위의 상태다.',
    ("BNFT_ORIGIN", "LOCAL"): '상품의 card_bnft.rule_list에 계산 규칙을 직접 가진 혜택. 상품 고유 혜택이 해당하고 현재 추출기는 모든 혜택을 이 값으로 정규화한다. 공통 정책판을 참조하는 COMMON_LINK와 달리 규칙이 상품에 귀속된다.',
    ("COND_TYPE", "MERCHANT_RULE"): '가맹점이나 업종의 분류 기준에 관한 조건. 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공한다는 카드 공통 조건이 해당한다. 개별 대상 가맹점은 target_list에 두고 이 유형은 판정 기준을 담는다.',
    ("EV_ITEM", "COND"): '근거가 조건식의 atom 하나를 가리키는 경우. ev_item_key에 atom_key를 저장하며 카드 근거와 공통 규칙 근거 양쪽에서 쓴다.',
    ("EV_ITEM", "TARGET"): '근거가 규칙 대상 하나를 가리키는 경우. ev_item_key에 target_key를 저장하며 카드 근거와 공통 규칙 근거 양쪽에서 쓴다.',
    ("EV_ITEM", "TIER"): '근거가 상품 한도 풀의 구간 하나를 가리키는 경우. ev_item_key에 tier_key를 저장하며 card_evidence_link에서만 인정된다. 공통 규칙의 한도는 LIMIT을 쓴다.',
}
CARD_DESC = '근거가 카드 공통 조건이나 상품 전체를 뒷받침하는 경우. 특정 혜택에 속하지 않는 내용에 쓰며 혜택, 규칙, 관계, 풀 컬럼은 모두 비워야 한다.'
BRAND_ORIGIN_DESC = '국제 브랜드 서비스 안내서에 근거해 카드별로 등록한 혜택. 계산 규칙은 카드의 rule_list에 직접 두고 원문 근거는 공통 PDF의 근거를 공유한다. bnft_scope_cd가 BRAND여야 하고(card_bnft_ck_5), 적용 선택지에 BRAND_SERVICE 문서 연결이 없으면 게이트 brand_bnft_doc_not_linked에서 검출된다.'

# 2차: 공통 혜택 구조 제거로 달라진 설명
del DESC_GRP["POLICY_STATUS"]
for key in (("POLICY_STATUS", "DRAFT"), ("POLICY_STATUS", "APPROVED"), ("POLICY_STATUS", "RETIRED")):
    del DESC_CD[key]
DESC_GRP.update({
    "APPROVAL_STATUS": '문서 연결과 원문 근거처럼 검토·승인이 필요한 관계·근거 데이터의 처리 상태를 구분하는 공통코드. card_product_doc.approval_status_cd, card_source_evidence.approval_status_cd에서 사용하며 실제 승인 대상은 사용하는 테이블에 따라 달라진다. 규칙·조건을 다루는 ITEM_STATUS, AI 추출 항목을 다루는 STG_STATUS와 관리 대상이 다르다.',
    "ITEM_STATUS": '계산 규칙, 조건식, 카드 공통 조건이 작성 중인지 확정되었는지를 구분하는 공통코드. JSONB 안의 rule_status_cd, cond_status_cd, expr_status_cd와 card_product.card_cond_status_cd에서 사용한다. 혜택 단위 검증을 나타내는 VERIFY_STATUS보다 작은 규칙·조건 단위의 상태다.',
    "BNFT_ORIGIN": '혜택의 원천을 구분하는 공통코드. card_bnft.bnft_origin_cd에서 사용한다. 출처와 관계없이 계산 규칙은 모두 card_bnft.rule_list에 있으며, 혜택이 어느 브랜드 선택지에 적용되는지를 나타내는 BNFT_SCOPE와는 별개의 축이다.',
    "PREDICATE_STATE": '규칙이나 한도 구간의 적용 여부를 조건식으로 어떻게 판정할지 구분하는 공통코드. card_bnft.rule_list[].predicate_state_cd와 card_limit_pool.tier_list[].predicate_state_cd에서 사용한다. 조건식이 없다는 사실만으로 무조건 적용으로 해석하지 않도록, 원문으로 확인된 무조건과 미검토를 구분한다.',
    "LIMIT_PERIOD": '한도가 누적되는 시간 단위를 구분하는 공통코드. card_limit_pool.period_cd에서 사용한다. 한도를 묶는 혜택 범위인 LIMIT_SCOPE, 한도의 단위인 LIMIT_UNIT과 함께 한도 하나를 정의한다.',
    "LIMIT_UNIT": '한도 수치 limit_num이 어떤 단위인지 구분하는 공통코드. card_limit_pool.cap_unit_cd에서 사용한다. 보상 지급 단위인 PAYOUT_UNIT과 달리 금액뿐 아니라 이용 횟수도 포함한다.',
    "LIMIT_AGG": '한도 사용액을 어떤 주체 단위로 합산할지 구분하는 공통코드. card_limit_pool.aggregation_key_cd에서 사용한다. 어떤 혜택을 묶는지를 나타내는 LIMIT_SCOPE와 달리 누구의 사용분을 합칠지를 나타낸다.',
    "BRAND": '카드 상품의 브랜드 선택지를 구분하는 공통코드. card_product.brand_opt_list[].brand_cd에서 사용한다. 그룹명은 국제 브랜드이지만 국내전용 선택지를 함께 포함하며, 브랜드 안의 등급은 SERVICE_GRADE, 선택서비스 유형은 SERVICE_TYPE이 구분한다.',
    "SERVICE_GRADE": '국제 브랜드 서비스의 등급을 구분하는 공통코드. card_product.brand_opt_list[].service_grade_cd에서 사용한다. BRAND와 조합해야 의미가 정해지며, 등급 안의 공통·선택서비스 구분은 SERVICE_TYPE이 맡는다.',
    "SERVICE_TYPE": '같은 브랜드와 등급 안에서 제공되는 서비스 묶음의 유형을 구분하는 공통코드. card_product.brand_opt_list[].service_type_cd에서 사용한다. 번호 코드는 BRAND, SERVICE_GRADE와 조합할 때만 의미가 정해지며 어떤 상품이 어떤 유형인지는 브랜드 서비스 안내서의 대상카드 표를 따른다.',
    "EV_ITEM": '근거가 대상 전체를 가리키는지 대상 안의 JSONB 항목을 가리키는지 구분하는 공통코드. card_evidence_link.ev_item_cd에서 사용하고 ev_item_key와 짝을 이룬다. 대상의 종류를 나타내는 EV_SUBJECT보다 한 단계 아래를 가리킨다.',
})
DESC_CD.update({
    ("APPROVAL_STATUS", "PENDING"): '대상 문서 연결 또는 원문 근거의 정확성과 적용 여부에 대한 검토가 끝나지 않은 상태. 업무 사용 승인 전 단계이며 card_product_doc의 기본값이다. 이 상태의 근거가 카드 항목에 연결되어 있으면 게이트 evidence_not_approved에서 검출된다.',
    ("APPROVAL_STATUS", "APPROVED"): '대상 데이터가 해당 업무의 검증 기준을 충족해 사용 승인을 받은 상태. 문서 연결은 적용 근거가 있어야 승인할 수 있고(card_product_doc_approved_check), 근거는 이 값일 때만 게이트 evidence_not_approved를 통과한다. 승인 대상과 범위는 사용하는 테이블에 따라 결정된다.',
    ("ITEM_STATUS", "DRAFT"): '규칙 또는 조건이 작성 중이라 아직 확정되지 않은 상태. AI 추출 결과를 정규화할 때 부여하는 초기값이며 card_product.card_cond_status_cd의 기본값이다. 혜택 전체가 아니라 규칙·조건 단위의 상태다.',
    ("BNFT_ORIGIN", "LOCAL"): '해당 상품 고유의 혜택. 상품설명서 등 상품 문서에 근거하며 현재 추출기는 모든 혜택을 이 값으로 정규화한다. 브랜드 서비스 안내서에 근거한 BRAND_SERVICE와 구분된다.',
    ("SERVICE_GRADE", "NONE"): '브랜드 서비스 등급이 없거나 해당하지 않는 경우. 등급 정보가 없는 브랜드 선택지에 쓴다. 등급을 확인하지 못했다는 뜻이 아니라 적용할 등급이 없다는 뜻이다.',
    ("SERVICE_TYPE", "NONE"): '브랜드 서비스 유형 구분이 없거나 해당하지 않는 경우. 공통 서비스와 선택서비스 어느 쪽도 아닐 때 쓴다.',
    ("EV_ITEM", "COND"): '근거가 조건식의 atom 하나를 가리키는 경우. ev_item_key에 atom_key를 저장한다.',
    ("EV_ITEM", "TARGET"): '근거가 규칙 대상 하나를 가리키는 경우. ev_item_key에 target_key를 저장한다.',
    ("EV_ITEM", "TIER"): '근거가 상품 한도 풀의 구간 하나를 가리키는 경우. ev_item_key에 tier_key를 저장한다.',
    ("DOC_TYPE", "BRAND_SERVICE"): '국제 브랜드의 등급별 서비스를 안내하는 문서. Visa, Mastercard, AMEX, JCB, UnionPay 안내서가 해당하며 여러 카드가 공유하는 문서로 한 번만 등록한다.',
})

# 3차: card_method_catalog 제거로 달라진 설명
DESC_GRP.update({
    "PRODUCT_STATUS": '카드 상품과 상품 안의 브랜드 선택지가 현재 판매되는지를 구분하는 공통코드. card_product.product_status_cd와 card_product.brand_opt_list[].brand_opt_status_cd에서 사용한다. 데이터 처리 상태가 아니라 판매 사실을 나타낸다는 점에서 문서 상태 DOC_STATUS의 같은 값 ACTIVE와 구분된다.',
    "CALC_METHOD": '규칙이 한 거래의 후보 보상을 어떤 방식으로 산출하는지 구분하는 공통코드. rule_list[].calc_method_cd에서 사용하고, 코드별 value_num의 의미가 정해져 있다. 조건 판정 방법인 PREDICATE_METHOD와 구분된다. 규칙의 method_ver는 표현 계약 버전으로 현재 1이며 계산 실행 엔진의 버전을 뜻하지 않는다.',
    "PREDICATE_METHOD": '금액 구간만으로 표현되지 않는 조건을 판정하는 방법을 구분하는 공통코드. 조건 atom의 predicate_method_cd에서 사용하며 세부 값은 cond_params에 둔다. 보상 금액을 산출하는 CALC_METHOD와 달리 조건의 참·거짓만 판정한다. predicate_method_ver는 표현 계약 버전으로 현재 1이며 실행 엔진의 버전을 뜻하지 않는다.',
})
DESC_CD.update({
    ("PRODUCT_STATUS", "ACTIVE"): '상품 또는 브랜드 선택지가 판매 중인 상태. 상품 등록의 기본값이다. 데이터 사용 가능 여부가 아닌 판매 사실을 나타내므로 DOC_STATUS.ACTIVE(문서 사용 중)와 의미가 다르다.',
    ("CALC_METHOD", "FIXED_PER_TXN"): '조건을 충족한 결제 1건마다 정해진 금액이나 포인트·마일리지를 제공하는 방식. value_num은 건당 수량이며 ONE PICK의 100원, 500원 캐시백이 해당한다. 결제금액에 비례하는 PERCENT_OF_TXN, 금액 구간마다 적립하는 UNITS_PER_AMOUNT와 구분된다.',
})

t = (SQL / "db_pipeline_common_code_descV6.sql").read_text(encoding="utf-8")
t, n = re.subn(r"^    \('POLICY_STATUS', .*\n", "", t, flags=re.M)
assert n == 4, n
t, n = re.subn(r"^    \('EV_ITEM', 'LIMIT', .*\n", "", t, flags=re.M)
assert n == 1, n
t, n = re.subn(r"^    \('METHOD_(KIND|STATUS)', .*\n", "", t, flags=re.M)
assert n == 6, n
t, n = re.subn(r"^    \('BNFT_ORIGIN', 'COMMON_LINK', '.*'\)([,;])$", lambda m: f"    ('BNFT_ORIGIN', 'BRAND_SERVICE', '{BRAND_ORIGIN_DESC}'){m.group(1)}", t, flags=re.M)
assert n == 1, n
t = rep(t, "-- V6 공통코드 상세 설명 등록. db_pipeline_common_code_seedV6.sql 실행 후 적용한다.",
        "-- V7 공통코드 상세 설명 등록. db_pipeline_common_code_seedV7.sql 실행 후 적용한다.")
t = rep(t, "-- 근거: V6 DDL과 뷰, db_pipeline Python 로직, V5 설계 문서, 수집 PDF 원문.",
        "-- V6 설명을 기준으로 구조 변경에 따라 달라진 항목만 고쳤고 삭제된 코드의 설명을 뺐다. 보류 2건은 그대로 NULL이다.\n-- 근거: V7 DDL과 뷰, db_pipeline Python 로직, V5 설계 문서, 수집 PDF 원문.")
for gid, text in DESC_GRP.items():
    t, n = re.subn(rf"^    \('{gid}', '[^A-Z0-9].*'\)([,;])$", lambda m: f"    ('{gid}', '{text}'){m.group(1)}", t, flags=re.M)
    if n != 1:
        raise SystemExit(f"group {gid}: {n}")
for (gid, cd), text in DESC_CD.items():
    t, n = re.subn(rf"^    \('{gid}', '{cd}', '.*'\)([,;])$", lambda m: f"    ('{gid}', '{cd}', '{text}'){m.group(1)}", t, flags=re.M)
    if n != 1:
        raise SystemExit(f"code {gid}.{cd}: {n}")
t, n = re.subn(r"^    \('EV_SUBJECT', 'POLICY', '.*'\)([,;])$", lambda m: f"    ('EV_SUBJECT', 'CARD', '{CARD_DESC}'){m.group(1)}", t, flags=re.M)
assert n == 1
for bad in ("card_policy_evidence", "card_policy_version", "policy_period_overlap", "source_doc_list", "적용 시작일",
            "card_common", "card_bnft_common", "COMMON_LINK", "POLICY_STATUS", "limit_list", "provider_cd", "정책판", "공통 규칙",
            "card_method_catalog", "METHOD_STATUS", "METHOD_KIND", "핸들러", "UNEXECUTABLE"):
    if bad in t:
        raise SystemExit(f"desc left over: {bad}: " + next(x for x in t.splitlines() if bad in x)[:110])
(OUT / "db_pipeline_common_code_descV7.sql").write_text(t, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------- DBML (CRLF 유지)
b = (SQL / "db_pipeline_schemaV6_draft.dbml").read_bytes().decode("utf-8").replace("\r\n", "\n")
b = rep(b, "// V6 draft physical-column mirror of db_pipeline_schemaV6_draft.sql. Generated from the executed DDL catalog.",
        "// V7 draft physical-column mirror of db_pipeline_schemaV7_draft.sql.")
b = rep(b, "//   card_policy_version.source_doc_list[].card_doc_id -> card_doc.card_doc_id\n", "")
b = cut(b, "Table db_pipeline.card_policy_version [", "Table db_pipeline.card_bnft [")
b = rep(b, "  effective_from date [note: '문서 적용 시작일']\n  effective_to_excl date [note: '문서 적용 종료일']\n", "")
b = rep(b, "  policy_ver_id varchar(20) [not null, note: '정책 버전 아이디']\n", "", count=4)
b = rep(b, "    (card_id, policy_ver_id, card_bnft_id) [pk]\n    (card_id, policy_ver_id, bnft_cd) [unique]\n",
        "    (card_id, card_bnft_id) [pk]\n    (card_id, bnft_cd) [unique]\n")
b = rep(b, "    (card_id, policy_ver_id, pool_id) [pk]\n", "    (card_id, pool_id) [pk]\n")
b = rep(b, "    (card_id, policy_ver_id, card_bnft_id, common_bnft_id, common_ver_id) [pk]\n",
        "    (card_id, card_bnft_id, common_bnft_id, common_ver_id) [pk]\n")
b = rep(b, "    (card_id, policy_ver_id, ev_link_id) [pk]\n", "    (card_id, ev_link_id) [pk]\n")
b = rep(b, "    (card_id, policy_ver_id, ev_subject_cd, card_bnft_id,", "    (card_id, ev_subject_cd, card_bnft_id,")
b = rep(b, "Table db_pipeline.card_policy_evidence [note: '정책 근거 관계']", "Table db_pipeline.card_evidence_link [note: '카드 근거 관계']")
m = re.search(r"Table db_pipeline\.card_product \[.*?\n  update_user_id [^\n]*\n", b, re.S)
b = b[:m.end()] + "  card_cond_expr jsonb [note: '카드 공통 조건']\n  card_cond_status_cd varchar(20) [not null, default: 'DRAFT', note: '카드 공통 조건 상태']\n" + b[m.end():]
b = rep(b, "Ref: db_pipeline.card_product.card_id < db_pipeline.card_policy_version.card_id\n",
        "Ref: db_pipeline.card_product.card_id < db_pipeline.card_bnft.card_id\n"
        "Ref: db_pipeline.card_product.card_id < db_pipeline.card_limit_pool.card_id\n"
        "Ref: db_pipeline.card_product.card_id < db_pipeline.card_evidence_link.card_id\n")
b = rep(b, "Ref: db_pipeline.card_policy_version.(card_id, policy_ver_id) < db_pipeline.card_bnft.(card_id, policy_ver_id)\n", "")
b = rep(b, "Ref: db_pipeline.card_policy_version.(card_id, policy_ver_id) < db_pipeline.card_limit_pool.(card_id, policy_ver_id)\n", "")
b = rep(b, "Ref: db_pipeline.card_policy_version.(card_id, policy_ver_id) < db_pipeline.card_policy_evidence.(card_id, policy_ver_id)\n", "")
b = rep(b, "Ref: db_pipeline.card_bnft.(card_id, policy_ver_id, card_bnft_id) < db_pipeline.card_bnft_common.(card_id, policy_ver_id, card_bnft_id)\n",
        "Ref: db_pipeline.card_bnft.(card_id, card_bnft_id) < db_pipeline.card_bnft_common.(card_id, card_bnft_id)\n")
b = rep(b, "Ref: db_pipeline.card_bnft.(card_id, policy_ver_id, card_bnft_id) < db_pipeline.card_policy_evidence.(card_id, policy_ver_id, card_bnft_id)\n",
        "Ref: db_pipeline.card_bnft.(card_id, card_bnft_id) < db_pipeline.card_evidence_link.(card_id, card_bnft_id)\n")
b = rep(b, "Ref: db_pipeline.card_limit_pool.(card_id, policy_ver_id, pool_id) < db_pipeline.card_policy_evidence.(card_id, policy_ver_id, pool_id)\n",
        "Ref: db_pipeline.card_limit_pool.(card_id, pool_id) < db_pipeline.card_evidence_link.(card_id, pool_id)\n")
b = rep(b, "TableGroup product_policy {", "TableGroup product {")
b = rep(b, "  db_pipeline.card_policy_version\n", "")
b = b.replace("card_policy_evidence", "card_evidence_link")
# 2차: 공통 혜택 구조 제거
for table in ("card_common_bnft", "card_common_policy_version", "card_bnft_common", "card_common_rule_evidence"):
    b, n = re.subn(rf"Table db_pipeline\.{table} \[.*?\n\}}\n\n", "", b, flags=re.S)
    assert n == 1, table
b, n = re.subn(r"^Ref: .*(card_common_|card_bnft_common).*\n", "", b, flags=re.M)
assert n >= 3, n
b, n = re.subn(r"^//   card_common_rule_evidence\.rule_key.*\n", "", b, flags=re.M)
assert n == 1
b, n = re.subn(r"TableGroup common_benefit \{.*?\n\}\n\n", "", b, flags=re.S)
assert n == 1
b = rep(b, "  db_pipeline.card_common_rule_evidence\n", "")
b = rep(b, "  verification_status_cd varchar(25) [not null, note: '혜택 검증 상태']\n",
        "  verification_status_cd varchar(25) [not null, note: '혜택 검증 상태']\n"
        "  bnft_valid_from date [note: '혜택 제공 시작일']\n  bnft_valid_to_excl date [note: '혜택 제공 종료일(미포함)']\n")
m = re.search(r"Table db_pipeline\.card_extr_stg \[.*?\n  card_id bigint \[not null, note: '카드 아이디'\]\n", b, re.S)
b = b[:m.start()] + m.group(0).replace("  card_id bigint [not null, note: '카드 아이디']\n", "  card_id bigint [note: '카드 아이디(NULL이면 특정 카드에 연결되지 않은 후보)']\n") + b[m.end():]
# 3차: card_method_catalog 제거
b, n = re.subn(r"Table db_pipeline\.card_method_catalog \[.*?\n\}\n\n", "", b, flags=re.S)
assert n == 1
b = rep(b, "//   rule_list[].(calc_method_cd, method_ver)         -> card_method_catalog.(method_cd, method_ver)\n",
        "//   rule_list[].calc_method_cd                       -> common_cd (CALC_METHOD)\n"
        "// method_ver and predicate_method_ver are representation contract versions, currently 1. Nothing checks them against an engine.\n")
b = rep(b, "  db_pipeline.card_method_catalog\n", "")
for bad in ("policy_ver_id", "card_policy_version", "effective_", "card_common", "card_bnft_common", "common_bnft_id", "card_method_catalog"):
    if bad in b:
        raise SystemExit(f"dbml left over {bad}: " + next(x for x in b.splitlines() if bad in x))
(OUT / "db_pipeline_schemaV7_draft.dbml").write_bytes(b.replace("\n", "\r\n").encode("utf-8"))

# ---------------------------------------------------------------- migration
RECREATE = ["v_card_rule", "v_card_rule_pool", "v_card_bnft_rel", "v_card_rule_target", "v_card_limit_tier",
            "v_card_cond_atom", "v_card_bnft_rule_effective", "v_common_cd_usage", "v_card_integrity_issue"]


def view_block(src, name):
    m = re.search(rf"CREATE VIEW db_pipeline\.{name} AS\n.*?\nCOMMENT ON VIEW db_pipeline\.{name} IS .*?;\n", src, re.S)
    if not m:
        raise SystemExit(f"view missing {name}")
    return m.group(0)


drop_views = "\n".join(f"DROP VIEW db_pipeline.{v};" for v in reversed(["v_card_policy_doc"] + RECREATE))
v7_views = "\n".join(view_block(d, v) for v in RECREATE)


def q(text):
    return "'" + text.replace("'", "''") + "'"


desc_updates = "\n".join(
    [f"UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = {q(v)}, update_date = now(), update_user_id = 'V7_MIGRATION'\nWHERE common_code_grp_id = {q(k)};"
     for k, v in DESC_GRP.items()]
    + [f"UPDATE db_pipeline.common_cd SET common_cd_desc = {q(v)}, update_date = now(), update_user_id = 'V7_MIGRATION'\nWHERE common_code_grp_id = {q(k[0])} AND common_cd = {q(k[1])};"
       for k, v in DESC_CD.items()])

MIG = f"""-- V6 -> V7: 카드 정책 버전 계층 제거와 card_product_doc 간소화.
-- 실행 전 사용자 승인이 필요하다. card_policy_version을 삭제하고 policy_ver_id 컬럼을 지운다.
-- 전체가 한 트랜잭션이다. 사전 검사나 사후 검사가 실패하면 아무것도 바뀌지 않는다.
-- 삭제 대상과 복구용 값은 db_pipeline_v6_backup 스키마에 남긴다. 복구는 db_pipeline_migration_V7_to_V6_rollback.sql을 쓴다.
-- 대상은 V6 스키마다. card_product_doc의 effective_* 컬럼이 이미 없는 실제 DB와 파일 그대로의 V6 모두 처리한다.
-- 카드별 정책판이 2건 이상이면 자동 병합하지 않고 중단한다.

BEGIN;

SET LOCAL lock_timeout = '10s';

-- ---------------------------------------------------------------------------
-- 1. 사전 검사
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_bad text;
BEGIN
    IF to_regclass('db_pipeline.card_policy_version') IS NULL THEN
        RAISE EXCEPTION 'V6 스키마가 아닙니다: card_policy_version이 없습니다';
    END IF;
    IF to_regnamespace('db_pipeline_v6_backup') IS NOT NULL THEN
        RAISE EXCEPTION '백업 스키마 db_pipeline_v6_backup이 이미 있습니다';
    END IF;

    SELECT string_agg(card_id::text, ', ') INTO v_bad FROM (
        SELECT card_id FROM db_pipeline.card_policy_version GROUP BY card_id HAVING count(*) > 1) x;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '정책판이 2건 이상인 카드가 있어 자동 병합하지 않습니다: %', v_bad;
    END IF;

    SELECT string_agg(src, ', ') INTO v_bad FROM (
        SELECT 'card_bnft' AS src FROM db_pipeline.card_bnft x
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
        UNION
        SELECT 'card_limit_pool' FROM db_pipeline.card_limit_pool x
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
        UNION
        SELECT 'card_bnft_common' FROM db_pipeline.card_bnft_common x
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
        UNION
        SELECT 'card_policy_evidence' FROM db_pipeline.card_policy_evidence x
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
    ) x;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '정책판을 찾을 수 없는 행이 있습니다: %', v_bad;
    END IF;

    -- source_doc_list는 card_product_doc으로 대체되므로 빠지는 문서가 없어야 한다.
    SELECT string_agg(v.card_id || '/' || (d.value->>'card_doc_id'), ', ') INTO v_bad
    FROM db_pipeline.card_policy_version v
    CROSS JOIN LATERAL jsonb_array_elements(v.source_doc_list) AS d(value)
    WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc x
                      WHERE (x.card_id, x.card_doc_id, x.doc_role_cd) = (v.card_id, d.value->>'card_doc_id', d.value->>'source_role_cd'));
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION 'card_product_doc에 없는 정책 문서가 있습니다: %', v_bad;
    END IF;

    -- 복구된 APPROVED 근거 CHECK를 위반하는 행이 있으면 먼저 알린다.
    SELECT string_agg(card_id || '/' || card_doc_id, ', ') INTO v_bad
    FROM db_pipeline.card_product_doc
    WHERE approval_status_cd = 'APPROVED' AND length(trim(applicability_basis_txt)) = 0;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '적용 근거 없는 승인 문서 관계가 있습니다: %', v_bad;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. 복구용 백업 (삭제되는 값만)
-- ---------------------------------------------------------------------------
CREATE SCHEMA db_pipeline_v6_backup;
COMMENT ON SCHEMA db_pipeline_v6_backup IS 'V6->V7 이관 때 삭제한 정책판 값. 롤백 기간이 끝나면 삭제한다';

CREATE TABLE db_pipeline_v6_backup.card_policy_version AS TABLE db_pipeline.card_policy_version;
CREATE TABLE db_pipeline_v6_backup.ev_subject_policy_row AS
    SELECT common_code_grp_id, common_cd, common_cd_nm, common_cd_desc, update_date, update_user_id
    FROM db_pipeline.common_cd WHERE common_code_grp_id = 'EV_SUBJECT' AND common_cd = 'POLICY';
CREATE TABLE db_pipeline_v6_backup.common_code_grp_desc AS
    SELECT common_code_grp_id, common_code_grp_desc, update_date, update_user_id FROM db_pipeline.common_code_grp;
CREATE TABLE db_pipeline_v6_backup.common_cd_desc AS
    SELECT common_code_grp_id, common_cd, common_cd_desc, update_date, update_user_id FROM db_pipeline.common_cd;
CREATE TABLE db_pipeline_v6_backup.seq_card_policy_version AS
    SELECT last_value, is_called FROM db_pipeline.seq_card_policy_version;
CREATE TABLE db_pipeline_v6_backup.row_counts AS
    SELECT (SELECT count(*) FROM db_pipeline.card_product) AS card_product,
           (SELECT count(*) FROM db_pipeline.card_bnft) AS card_bnft,
           (SELECT count(*) FROM db_pipeline.card_limit_pool) AS card_limit_pool,
           (SELECT count(*) FROM db_pipeline.card_bnft_common) AS card_bnft_common,
           (SELECT count(*) FROM db_pipeline.card_policy_evidence) AS card_evidence_link,
           (SELECT count(*) FROM db_pipeline.card_source_evidence) AS card_source_evidence;

-- ---------------------------------------------------------------------------
-- 3. 뷰 제거
-- ---------------------------------------------------------------------------
{drop_views}

-- ---------------------------------------------------------------------------
-- 4. card_product: 카드 공통 조건 이관
-- ---------------------------------------------------------------------------
ALTER TABLE db_pipeline.card_product ADD COLUMN card_cond_expr jsonb;
ALTER TABLE db_pipeline.card_product ADD COLUMN card_cond_status_cd varchar(20) NOT NULL DEFAULT 'DRAFT';
ALTER TABLE db_pipeline.card_product
    ADD CONSTRAINT card_product_card_cond_expr_check CHECK (db_pipeline.fn_valid_cond_expr(card_cond_expr));
COMMENT ON COLUMN db_pipeline.card_product.card_cond_expr IS '카드 공통 조건';
COMMENT ON COLUMN db_pipeline.card_product.card_cond_status_cd IS '카드 공통 조건 상태';

-- policy_status_cd는 POLICY_STATUS, card_cond_status_cd는 ITEM_STATUS다. 값을 올리지 않고 같은 단계로 옮긴다.
UPDATE db_pipeline.card_product p
SET card_cond_expr = v.policy_cond_expr,
    card_cond_status_cd = CASE v.policy_status_cd
        WHEN 'DRAFT' THEN 'DRAFT'
        WHEN 'APPROVED' THEN 'CONFIRMED'
        WHEN 'RETIRED' THEN 'RETIRED'
    END
FROM db_pipeline.card_policy_version v
WHERE v.card_id = p.card_id;

-- ---------------------------------------------------------------------------
-- 5. card_product_doc 간소화 (이미 지워졌으면 건너뛴다)
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS db_pipeline.card_product_doc_current_idx;
ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT IF EXISTS card_product_doc_period_check;
ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT IF EXISTS card_product_doc_approved_check;
ALTER TABLE db_pipeline.card_product_doc DROP COLUMN IF EXISTS effective_from;
ALTER TABLE db_pipeline.card_product_doc DROP COLUMN IF EXISTS effective_to_excl;
ALTER TABLE db_pipeline.card_product_doc ADD CONSTRAINT card_product_doc_approved_check CHECK
    (approval_status_cd <> 'APPROVED' OR length(trim(applicability_basis_txt)) > 0);

-- ---------------------------------------------------------------------------
-- 6. policy_ver_id 제거와 키 변경
-- ---------------------------------------------------------------------------
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_pkey;
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_card_id_policy_ver_id_bnft_cd_key;
ALTER TABLE db_pipeline.card_bnft DROP COLUMN policy_ver_id;
ALTER TABLE db_pipeline.card_bnft ADD PRIMARY KEY (card_id, card_bnft_id);
ALTER TABLE db_pipeline.card_bnft ADD UNIQUE (card_id, bnft_cd);

ALTER TABLE db_pipeline.card_limit_pool DROP CONSTRAINT card_limit_pool_pkey;
ALTER TABLE db_pipeline.card_limit_pool DROP COLUMN policy_ver_id;
ALTER TABLE db_pipeline.card_limit_pool ADD PRIMARY KEY (card_id, pool_id);

ALTER TABLE db_pipeline.card_bnft_common DROP CONSTRAINT card_bnft_common_pkey;
ALTER TABLE db_pipeline.card_bnft_common DROP COLUMN policy_ver_id;
ALTER TABLE db_pipeline.card_bnft_common ADD PRIMARY KEY (card_id, card_bnft_id, common_bnft_id, common_ver_id);

-- ---------------------------------------------------------------------------
-- 7. card_policy_evidence -> card_evidence_link
-- ---------------------------------------------------------------------------
ALTER TABLE db_pipeline.card_policy_evidence DROP CONSTRAINT card_policy_evidence_pkey;
ALTER TABLE db_pipeline.card_policy_evidence DROP CONSTRAINT card_policy_evidence_natural_key;
ALTER TABLE db_pipeline.card_policy_evidence DROP CONSTRAINT card_policy_evidence_ck_2;
DROP INDEX db_pipeline.ix_card_policy_evidence_subject;
ALTER TABLE db_pipeline.card_policy_evidence DROP COLUMN policy_ver_id;

UPDATE db_pipeline.card_policy_evidence SET ev_subject_cd = 'CARD' WHERE ev_subject_cd = 'POLICY';

ALTER TABLE db_pipeline.card_policy_evidence RENAME TO card_evidence_link;
ALTER TABLE db_pipeline.card_evidence_link RENAME CONSTRAINT card_policy_evidence_ck_1 TO card_evidence_link_ck_1;
ALTER INDEX db_pipeline.ix_card_policy_evidence_evidence RENAME TO ix_card_evidence_link_evidence;
ALTER SEQUENCE db_pipeline.seq_card_policy_evidence RENAME TO seq_card_evidence_link;
COMMENT ON SEQUENCE db_pipeline.seq_card_evidence_link IS 'card_evidence_link.ev_link_id 로컬 업무 ID 발급';

ALTER TABLE db_pipeline.card_evidence_link
    ALTER COLUMN ev_link_id SET DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link');
ALTER TABLE db_pipeline.card_evidence_link ADD PRIMARY KEY (card_id, ev_link_id);
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_natural_key UNIQUE NULLS NOT DISTINCT
    (card_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, pool_id, ev_item_cd, ev_item_key, evidence_id);
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_ck_2 CHECK (
    CASE ev_subject_cd
        WHEN 'CARD' THEN num_nonnulls(card_bnft_id, rule_key, relation_key, pool_id) = 0
        WHEN 'BNFT' THEN card_bnft_id IS NOT NULL AND num_nonnulls(rule_key, relation_key, pool_id) = 0
        WHEN 'RULE' THEN card_bnft_id IS NOT NULL AND rule_key IS NOT NULL
                         AND num_nonnulls(relation_key, pool_id) = 0
        WHEN 'POOL' THEN pool_id IS NOT NULL AND num_nonnulls(card_bnft_id, rule_key, relation_key) = 0
        WHEN 'REL' THEN card_bnft_id IS NOT NULL AND relation_key IS NOT NULL
                        AND num_nonnulls(rule_key, pool_id) = 0
        ELSE false
    END);
CREATE INDEX ix_card_evidence_link_subject ON db_pipeline.card_evidence_link (card_id, ev_subject_cd, card_bnft_id, rule_key);
COMMENT ON TABLE db_pipeline.card_evidence_link IS '카드 근거 관계';

-- ---------------------------------------------------------------------------
-- 8. card_policy_version 제거
-- ---------------------------------------------------------------------------
DROP TABLE db_pipeline.card_policy_version;
DROP SEQUENCE db_pipeline.seq_card_policy_version;
DROP FUNCTION db_pipeline.fn_valid_doc_ref_list(jsonb);

-- ---------------------------------------------------------------------------
-- 9. 공통코드: EV_SUBJECT.POLICY -> CARD, 달라진 설명만 갱신 (보류 2건은 건드리지 않는다)
-- ---------------------------------------------------------------------------
UPDATE db_pipeline.common_cd
SET common_cd = 'CARD', common_cd_nm = '카드', common_cd_desc = {q(CARD_DESC)},
    update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'EV_SUBJECT' AND common_cd = 'POLICY';

{desc_updates}

-- ---------------------------------------------------------------------------
-- 10. 뷰 재생성
-- ---------------------------------------------------------------------------
{v7_views}
COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V7 공통코드·반정규화 스키마(초안)';

-- ---------------------------------------------------------------------------
-- 11. 사후 검사
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    c db_pipeline_v6_backup.row_counts%ROWTYPE;
    v_bad text;
BEGIN
    SELECT * INTO c FROM db_pipeline_v6_backup.row_counts;
    IF c.card_product <> (SELECT count(*) FROM db_pipeline.card_product)
       OR c.card_bnft <> (SELECT count(*) FROM db_pipeline.card_bnft)
       OR c.card_limit_pool <> (SELECT count(*) FROM db_pipeline.card_limit_pool)
       OR c.card_bnft_common <> (SELECT count(*) FROM db_pipeline.card_bnft_common)
       OR c.card_evidence_link <> (SELECT count(*) FROM db_pipeline.card_evidence_link)
       OR c.card_source_evidence <> (SELECT count(*) FROM db_pipeline.card_source_evidence) THEN
        RAISE EXCEPTION '이관 전후 행 수가 다릅니다';
    END IF;

    IF EXISTS (SELECT 1 FROM db_pipeline_v6_backup.card_policy_version v
               JOIN db_pipeline.card_product p USING (card_id)
               WHERE p.card_cond_expr IS DISTINCT FROM v.policy_cond_expr) THEN
        RAISE EXCEPTION '카드 공통 조건이 원본과 다릅니다';
    END IF;

    SELECT string_agg(DISTINCT gate_cd, ', ') INTO v_bad
    FROM db_pipeline.v_card_integrity_issue WHERE gate_cd <> 'evidence_not_approved';
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '정합성 게이트 위반: %', v_bad;
    END IF;
END;
$$;

COMMIT;
"""

# ---- 2차: 이관 SQL에 공통 혜택 구조 제거 추가
MIG = rep(MIG, "-- V6 -> V7: 카드 정책 버전 계층 제거와 card_product_doc 간소화.\n",
          "-- V6 -> V7: 카드 정책 버전 계층 제거, 공통 혜택 구조 제거, 방법 카탈로그 제거, card_product_doc 간소화.\n")
MIG = rep(MIG, "    -- 복구된 APPROVED 근거 CHECK를 위반하는 행이 있으면 먼저 알린다.\n", """    -- 실행 가능한 방법 계약이 등록되어 있으면 지우지 않고 멈춘다. 시험용 UNEXECUTABLE 행만 삭제 대상이다.
    IF EXISTS (SELECT 1 FROM db_pipeline.card_method_catalog WHERE method_status_cd <> 'UNEXECUTABLE') THEN
        RAISE EXCEPTION '실행 가능한 방법 계약이 있어 card_method_catalog를 삭제하지 않습니다';
    END IF;

    -- 복구된 APPROVED 근거 CHECK를 위반하는 행이 있으면 먼저 알린다.
""")
MIG = rep(MIG, "CREATE TABLE db_pipeline_v6_backup.card_policy_version AS TABLE db_pipeline.card_policy_version;\n",
          "CREATE TABLE db_pipeline_v6_backup.card_policy_version AS TABLE db_pipeline.card_policy_version;\n"
          "CREATE TABLE db_pipeline_v6_backup.card_method_catalog AS TABLE db_pipeline.card_method_catalog;\n")
MIG = rep(MIG, "DROP TABLE db_pipeline.card_policy_version;\n", "DROP TABLE db_pipeline.card_policy_version;\nDROP TABLE db_pipeline.card_method_catalog;\n")
MIG = rep(MIG, "FROM db_pipeline.v_card_integrity_issue WHERE gate_cd <> 'evidence_not_approved';",
          "FROM db_pipeline.v_card_integrity_issue\n    WHERE gate_cd NOT IN ('evidence_not_approved', 'rule_method_value_pending', 'predicate_params_pending');")
MIG = rep(MIG, "-- 카드별 정책판이 2건 이상이면 자동 병합하지 않고 중단한다.\n",
          "-- 카드별 정책판이 2건 이상이거나 공통 혜택 4개 테이블에 행이 있으면 자동 변환하지 않고 중단한다.\n")
MIG = rep(MIG, """        UNION
        SELECT 'card_bnft_common' FROM db_pipeline.card_bnft_common x
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
""", "")
MIG = rep(MIG, "    -- source_doc_list는 card_product_doc으로 대체되므로 빠지는 문서가 없어야 한다.\n", """    -- 공통 혜택 데이터의 카드별 변환 규칙은 정의하지 않았다. 행이 있으면 지우지 않고 멈춘다.
    SELECT string_agg(src, ', ') INTO v_bad FROM (
        SELECT 'card_common_bnft' AS src WHERE EXISTS (SELECT 1 FROM db_pipeline.card_common_bnft)
        UNION ALL SELECT 'card_common_policy_version' WHERE EXISTS (SELECT 1 FROM db_pipeline.card_common_policy_version)
        UNION ALL SELECT 'card_bnft_common' WHERE EXISTS (SELECT 1 FROM db_pipeline.card_bnft_common)
        UNION ALL SELECT 'card_common_rule_evidence' WHERE EXISTS (SELECT 1 FROM db_pipeline.card_common_rule_evidence)
        UNION ALL SELECT 'card_bnft.COMMON_LINK' WHERE EXISTS (SELECT 1 FROM db_pipeline.card_bnft WHERE bnft_origin_cd = 'COMMON_LINK')
    ) x;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '공통 혜택 데이터가 있어 삭제하지 않습니다: %', v_bad;
    END IF;

    -- source_doc_list는 card_product_doc으로 대체되므로 빠지는 문서가 없어야 한다.
""")
MIG = cut(MIG, "CREATE TABLE db_pipeline_v6_backup.ev_subject_policy_row AS", "CREATE TABLE db_pipeline_v6_backup.row_counts AS", """CREATE TABLE db_pipeline_v6_backup.common_code_grp AS TABLE db_pipeline.common_code_grp;
CREATE TABLE db_pipeline_v6_backup.common_cd AS TABLE db_pipeline.common_cd;
CREATE TABLE db_pipeline_v6_backup.seq_state AS
    SELECT 'seq_card_policy_version'::text AS seq_nm, last_value, is_called FROM db_pipeline.seq_card_policy_version
    UNION ALL SELECT 'seq_card_common_bnft', last_value, is_called FROM db_pipeline.seq_card_common_bnft
    UNION ALL SELECT 'seq_card_common_policy_version', last_value, is_called FROM db_pipeline.seq_card_common_policy_version;
""")
MIG = rep(MIG, "           (SELECT count(*) FROM db_pipeline.card_bnft_common) AS card_bnft_common,\n", "")
MIG = rep(MIG, "       OR c.card_bnft_common <> (SELECT count(*) FROM db_pipeline.card_bnft_common)\n", "")
MIG = rep(MIG, drop_views + "\n", drop_views + "\nDROP VIEW db_pipeline.v_card_common_limit;\nDROP VIEW db_pipeline.v_card_common_rule;\n")
MIG = rep(MIG, """ALTER TABLE db_pipeline.card_bnft_common DROP CONSTRAINT card_bnft_common_pkey;
ALTER TABLE db_pipeline.card_bnft_common DROP COLUMN policy_ver_id;
ALTER TABLE db_pipeline.card_bnft_common ADD PRIMARY KEY (card_id, card_bnft_id, common_bnft_id, common_ver_id);

""", "")
fn_rule_v7 = re.search(r"CREATE FUNCTION db_pipeline\.fn_valid_rule_list.*?\n\$_\$;\n", d, re.S).group(0).replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
fn_rule_cmt = next(x for x in d.splitlines() if x.startswith("COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list"))
MIG = rep(MIG, """DROP FUNCTION db_pipeline.fn_valid_doc_ref_list(jsonb);
""", f"""DROP FUNCTION db_pipeline.fn_valid_doc_ref_list(jsonb);

-- ---------------------------------------------------------------------------
-- 8-1. 공통 혜택 구조 제거. 브랜드 혜택은 카드별 card_bnft에 저장하고 문서·근거를 공유한다
-- ---------------------------------------------------------------------------
DROP TABLE db_pipeline.card_common_rule_evidence;
DROP TABLE db_pipeline.card_bnft_common;
DROP TABLE db_pipeline.card_common_policy_version;
DROP TABLE db_pipeline.card_common_bnft;
DROP SEQUENCE db_pipeline.seq_card_common_policy_version;
DROP SEQUENCE db_pipeline.seq_card_common_bnft;

-- 호출부(extraction_repository.sql)가 있어 2인자 시그니처를 유지한다. COMMON 분기만 없앤다.
{fn_rule_v7}
{fn_rule_cmt}
DROP FUNCTION db_pipeline.fn_valid_limit_list(jsonb);

ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_ck_5;
ALTER TABLE db_pipeline.card_bnft ADD CONSTRAINT card_bnft_ck_5 CHECK (bnft_origin_cd <> 'BRAND_SERVICE' OR bnft_scope_cd = 'BRAND');
ALTER TABLE db_pipeline.card_bnft ADD COLUMN bnft_valid_from date;
ALTER TABLE db_pipeline.card_bnft ADD COLUMN bnft_valid_to_excl date;
ALTER TABLE db_pipeline.card_bnft ADD CONSTRAINT card_bnft_ck_6 CHECK
    (bnft_valid_to_excl IS NULL OR bnft_valid_from IS NULL OR bnft_valid_to_excl > bnft_valid_from);
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_from IS '혜택 제공 시작일';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_to_excl IS '혜택 제공 종료일(미포함)';

-- 공통 PDF는 카드 등록 전에도 추출한다. NULL은 카드 미연결 후보이며 공통 혜택 확정을 뜻하지 않는다.
ALTER TABLE db_pipeline.card_extr_stg ALTER COLUMN card_id DROP NOT NULL;
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디(NULL이면 특정 카드에 연결되지 않은 후보)';
""")
MIG = rep(MIG, "-- 9. 공통코드: EV_SUBJECT.POLICY -> CARD, 달라진 설명만 갱신 (보류 2건은 건드리지 않는다)\n",
          "-- 9. 공통코드: 코드 교체와 삭제, 달라진 설명만 갱신 (보류 2건은 건드리지 않는다)\n")
MIG = rep(MIG, f"\n{desc_updates}\n", f"""
UPDATE db_pipeline.common_cd
SET common_cd = 'BRAND_SERVICE', common_cd_nm = '브랜드 공통 서비스', common_cd_desc = {q(BRAND_ORIGIN_DESC)},
    update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'BNFT_ORIGIN' AND common_cd = 'COMMON_LINK';
UPDATE db_pipeline.common_cd SET common_cd_nm = '상품 고유 혜택', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'BNFT_ORIGIN' AND common_cd = 'LOCAL';

-- 사용처가 없어진 코드만 삭제한다. 원본은 db_pipeline_v6_backup에 있다.
DELETE FROM db_pipeline.common_cd WHERE common_code_grp_id = 'POLICY_STATUS';
DELETE FROM db_pipeline.common_code_grp WHERE common_code_grp_id = 'POLICY_STATUS';
DELETE FROM db_pipeline.common_cd WHERE common_code_grp_id = 'EV_ITEM' AND common_cd = 'LIMIT';
DELETE FROM db_pipeline.common_cd WHERE common_code_grp_id IN ('METHOD_KIND', 'METHOD_STATUS');
DELETE FROM db_pipeline.common_code_grp WHERE common_code_grp_id IN ('METHOD_KIND', 'METHOD_STATUS');

{desc_updates}
""")
(OUT / "db_pipeline_migration_V6_to_V7.sql").write_text(MIG, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------- rollback
fn = re.search(r"CREATE FUNCTION db_pipeline\.fn_valid_doc_ref_list.*?COMMENT ON FUNCTION db_pipeline\.fn_valid_doc_ref_list[^\n]*\n", V6, re.S).group(0)
v6_views = "\n".join(view_block(V6, v) for v in ["v_card_rule", "v_card_rule_pool", "v_card_bnft_rel", "v_card_rule_target",
                                                 "v_card_limit_tier", "v_card_policy_doc", "v_card_cond_atom",
                                                 "v_card_bnft_rule_effective", "v_common_cd_usage", "v_card_integrity_issue"])
tbl = re.search(r"CREATE TABLE db_pipeline\.card_policy_version \(.*?\n\);\n", V6, re.S).group(0)
tbl_comments = "\n".join(x for x in V6.splitlines() if re.match(r"COMMENT ON (TABLE|COLUMN) db_pipeline\.card_policy_version\b", x))
ROLL = f"""-- V7 -> V6 복구. db_pipeline_migration_V6_to_V7.sql 실행 직후의 상태를 이관 전 상태로 되돌린다.
-- db_pipeline_v6_backup 스키마가 필요하다. 이관 이후 새로 등록한 혜택·한도·근거가 있으면 실행하지 말고 먼저 검토한다.
-- 되돌린 뒤 policy_ver_id 컬럼의 물리 위치는 테이블 끝이 된다. 값과 키, 제약조건은 이관 전과 같다.
-- card_product_doc의 effective_* 컬럼은 이관 전 실제 DB에도 없었으므로 되살리지 않는다.

BEGIN;

SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
    IF to_regclass('db_pipeline_v6_backup.card_policy_version') IS NULL THEN
        RAISE EXCEPTION '백업 스키마 db_pipeline_v6_backup이 없습니다';
    END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft x
               WHERE NOT EXISTS (SELECT 1 FROM db_pipeline_v6_backup.card_policy_version v WHERE v.card_id = x.card_id)) THEN
        RAISE EXCEPTION '이관 후 정책판이 없는 카드의 혜택이 추가되었습니다';
    END IF;
END;
$$;

{chr(10).join(f"DROP VIEW db_pipeline.{v};" for v in reversed(RECREATE))}

CREATE SEQUENCE db_pipeline.seq_card_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
COMMENT ON SEQUENCE db_pipeline.seq_card_policy_version IS 'card_policy_version.policy_ver_id 로컬 업무 ID 발급';
SELECT setval('db_pipeline.seq_card_policy_version', last_value, is_called) FROM db_pipeline_v6_backup.seq_card_policy_version;

{fn}
{tbl}
{tbl_comments}

CREATE INDEX ix_card_policy_version_lookup ON db_pipeline.card_policy_version (card_id, policy_status_cd, valid_from, valid_to_excl);
CREATE INDEX ix_card_policy_version_doc_gin ON db_pipeline.card_policy_version USING gin (source_doc_list jsonb_path_ops);

INSERT INTO db_pipeline.card_policy_version SELECT * FROM db_pipeline_v6_backup.card_policy_version;

ALTER TABLE db_pipeline.card_bnft ADD COLUMN policy_ver_id varchar(20);
UPDATE db_pipeline.card_bnft x SET policy_ver_id = v.policy_ver_id FROM db_pipeline.card_policy_version v WHERE v.card_id = x.card_id;
ALTER TABLE db_pipeline.card_bnft ALTER COLUMN policy_ver_id SET NOT NULL;
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_pkey;
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_card_id_bnft_cd_key;
ALTER TABLE db_pipeline.card_bnft ADD PRIMARY KEY (card_id, policy_ver_id, card_bnft_id);
ALTER TABLE db_pipeline.card_bnft ADD UNIQUE (card_id, policy_ver_id, bnft_cd);
COMMENT ON COLUMN db_pipeline.card_bnft.policy_ver_id IS '정책 버전 아이디';

ALTER TABLE db_pipeline.card_limit_pool ADD COLUMN policy_ver_id varchar(20);
UPDATE db_pipeline.card_limit_pool x SET policy_ver_id = v.policy_ver_id FROM db_pipeline.card_policy_version v WHERE v.card_id = x.card_id;
ALTER TABLE db_pipeline.card_limit_pool ALTER COLUMN policy_ver_id SET NOT NULL;
ALTER TABLE db_pipeline.card_limit_pool DROP CONSTRAINT card_limit_pool_pkey;
ALTER TABLE db_pipeline.card_limit_pool ADD PRIMARY KEY (card_id, policy_ver_id, pool_id);
COMMENT ON COLUMN db_pipeline.card_limit_pool.policy_ver_id IS '정책 버전 아이디';

ALTER TABLE db_pipeline.card_bnft_common ADD COLUMN policy_ver_id varchar(20);
UPDATE db_pipeline.card_bnft_common x SET policy_ver_id = v.policy_ver_id FROM db_pipeline.card_policy_version v WHERE v.card_id = x.card_id;
ALTER TABLE db_pipeline.card_bnft_common ALTER COLUMN policy_ver_id SET NOT NULL;
ALTER TABLE db_pipeline.card_bnft_common DROP CONSTRAINT card_bnft_common_pkey;
ALTER TABLE db_pipeline.card_bnft_common ADD PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, common_bnft_id, common_ver_id);
COMMENT ON COLUMN db_pipeline.card_bnft_common.policy_ver_id IS '정책 버전 아이디';

ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT card_evidence_link_pkey;
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT card_evidence_link_natural_key;
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT card_evidence_link_ck_2;
DROP INDEX db_pipeline.ix_card_evidence_link_subject;
ALTER TABLE db_pipeline.card_evidence_link RENAME TO card_policy_evidence;
ALTER TABLE db_pipeline.card_policy_evidence RENAME CONSTRAINT card_evidence_link_ck_1 TO card_policy_evidence_ck_1;
ALTER INDEX db_pipeline.ix_card_evidence_link_evidence RENAME TO ix_card_policy_evidence_evidence;
ALTER SEQUENCE db_pipeline.seq_card_evidence_link RENAME TO seq_card_policy_evidence;
COMMENT ON SEQUENCE db_pipeline.seq_card_policy_evidence IS 'card_policy_evidence.ev_link_id 로컬 업무 ID 발급';
ALTER TABLE db_pipeline.card_policy_evidence
    ALTER COLUMN ev_link_id SET DEFAULT db_pipeline.fn_get_biz_id('card_policy_evidence');
ALTER TABLE db_pipeline.card_policy_evidence ADD COLUMN policy_ver_id varchar(20);
UPDATE db_pipeline.card_policy_evidence x SET policy_ver_id = v.policy_ver_id FROM db_pipeline.card_policy_version v WHERE v.card_id = x.card_id;
ALTER TABLE db_pipeline.card_policy_evidence ALTER COLUMN policy_ver_id SET NOT NULL;
UPDATE db_pipeline.card_policy_evidence SET ev_subject_cd = 'POLICY' WHERE ev_subject_cd = 'CARD';
ALTER TABLE db_pipeline.card_policy_evidence ADD PRIMARY KEY (card_id, policy_ver_id, ev_link_id);
ALTER TABLE db_pipeline.card_policy_evidence ADD CONSTRAINT card_policy_evidence_natural_key UNIQUE NULLS NOT DISTINCT
    (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, pool_id, ev_item_cd, ev_item_key, evidence_id);
ALTER TABLE db_pipeline.card_policy_evidence ADD CONSTRAINT card_policy_evidence_ck_2 CHECK (
    CASE ev_subject_cd
        WHEN 'POLICY' THEN num_nonnulls(card_bnft_id, rule_key, relation_key, pool_id) = 0
        WHEN 'BNFT' THEN card_bnft_id IS NOT NULL AND num_nonnulls(rule_key, relation_key, pool_id) = 0
        WHEN 'RULE' THEN card_bnft_id IS NOT NULL AND rule_key IS NOT NULL
                         AND num_nonnulls(relation_key, pool_id) = 0
        WHEN 'POOL' THEN pool_id IS NOT NULL AND num_nonnulls(card_bnft_id, rule_key, relation_key) = 0
        WHEN 'REL' THEN card_bnft_id IS NOT NULL AND relation_key IS NOT NULL
                        AND num_nonnulls(rule_key, pool_id) = 0
        ELSE false
    END);
CREATE INDEX ix_card_policy_evidence_subject ON db_pipeline.card_policy_evidence (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, rule_key);
COMMENT ON TABLE db_pipeline.card_policy_evidence IS '정책 근거 관계';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.policy_ver_id IS '정책 버전 아이디';

ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT card_product_doc_approved_check;

ALTER TABLE db_pipeline.card_product DROP CONSTRAINT card_product_card_cond_expr_check;
ALTER TABLE db_pipeline.card_product DROP COLUMN card_cond_expr;
ALTER TABLE db_pipeline.card_product DROP COLUMN card_cond_status_cd;

UPDATE db_pipeline.common_cd c
SET common_cd = b.common_cd, common_cd_nm = b.common_cd_nm
FROM db_pipeline_v6_backup.ev_subject_policy_row b
WHERE c.common_code_grp_id = 'EV_SUBJECT' AND c.common_cd = 'CARD';
UPDATE db_pipeline.common_code_grp g
SET common_code_grp_desc = b.common_code_grp_desc, update_date = b.update_date, update_user_id = b.update_user_id
FROM db_pipeline_v6_backup.common_code_grp_desc b
WHERE b.common_code_grp_id = g.common_code_grp_id;
UPDATE db_pipeline.common_cd c
SET common_cd_desc = b.common_cd_desc, update_date = b.update_date, update_user_id = b.update_user_id
FROM db_pipeline_v6_backup.common_cd_desc b
WHERE (b.common_code_grp_id, b.common_cd) = (c.common_code_grp_id, c.common_cd);

{v6_views}
COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V6 공통코드·반정규화 스키마(초안)';

DROP SCHEMA db_pipeline_v6_backup CASCADE;

COMMIT;
"""

# ---- 2차: 롤백에 공통 혜택 구조 복구 추가
ROLL = rep(ROLL, "-- db_pipeline_v6_backup 스키마가 필요하다. 이관 이후 새로 등록한 혜택·한도·근거가 있으면 실행하지 말고 먼저 검토한다.\n",
           "-- db_pipeline_v6_backup 스키마가 필요하다. 이관 이후 새로 등록한 혜택·한도·근거가 있으면 실행하지 말고 먼저 검토한다.\n"
           "-- 브랜드 혜택, 혜택 제공 기간, 카드 미연결 추출 항목은 V6에 담을 수 없으므로 있으면 중단한다.\n")
ROLL = rep(ROLL, """        RAISE EXCEPTION '이관 후 정책판이 없는 카드의 혜택이 추가되었습니다';
    END IF;
""", """        RAISE EXCEPTION '이관 후 정책판이 없는 카드의 혜택이 추가되었습니다';
    END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft
               WHERE bnft_origin_cd = 'BRAND_SERVICE' OR bnft_valid_from IS NOT NULL OR bnft_valid_to_excl IS NOT NULL) THEN
        RAISE EXCEPTION 'V6에 담을 수 없는 브랜드 혜택 또는 제공 기간이 있습니다';
    END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_extr_stg WHERE card_id IS NULL) THEN
        RAISE EXCEPTION 'V6에 담을 수 없는 카드 미연결 추출 항목이 있습니다';
    END IF;
""")


def v6_seq(name):
    return "\n".join(x for x in V6.splitlines() if f"seq_{name} " in x and x.startswith(("CREATE SEQUENCE", "COMMENT ON SEQUENCE")))


def v6_block(pattern):
    return re.search(pattern, V6, re.S).group(0)


common_tables = []
for table in ("card_common_bnft", "card_common_policy_version", "card_bnft_common", "card_common_rule_evidence"):
    common_tables.append(v6_block(rf"CREATE TABLE db_pipeline\.{table} \(.*?\n\);\n"))
    common_tables.append("\n".join(x for x in V6.splitlines() if re.match(rf"COMMENT ON (TABLE|COLUMN) db_pipeline\.{table}\b", x)) + "\n")
common_tables.append(v6_block(r"CREATE TABLE db_pipeline\.card_method_catalog \(.*?\n\);\n"))
common_tables.append("\n".join(x for x in V6.splitlines() if re.match(r"COMMENT ON (TABLE|COLUMN) db_pipeline\.card_method_catalog\b", x)) + "\n")
common_tables.append("INSERT INTO db_pipeline.card_method_catalog SELECT * FROM db_pipeline_v6_backup.card_method_catalog;\n")
common_idx = "\n".join(x for x in V6.splitlines() if x.startswith("CREATE INDEX ix_card_") and
                       re.search(r"ON db_pipeline\.(card_common_|card_bnft_common)", x))
fn_limit_v6 = v6_block(r"CREATE FUNCTION db_pipeline\.fn_valid_limit_list.*?COMMENT ON FUNCTION db_pipeline\.fn_valid_limit_list[^\n]*\n")
fn_rule_v6 = v6_block(r"CREATE FUNCTION db_pipeline\.fn_valid_rule_list.*?COMMENT ON FUNCTION db_pipeline\.fn_valid_rule_list[^\n]*\n").replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
ROLL = rep(ROLL, "CREATE SEQUENCE db_pipeline.seq_card_policy_version INCREMENT", f"""{v6_seq('card_common_bnft')}
{v6_seq('card_common_policy_version')}
CREATE SEQUENCE db_pipeline.seq_card_policy_version INCREMENT""")
ROLL = rep(ROLL, "SELECT setval('db_pipeline.seq_card_policy_version', last_value, is_called) FROM db_pipeline_v6_backup.seq_card_policy_version;\n",
           "SELECT setval('db_pipeline.' || seq_nm, last_value, is_called) FROM db_pipeline_v6_backup.seq_state;\n")
ROLL = rep(ROLL, fn, fn + "\n" + fn_limit_v6 + "\n" + fn_rule_v6)
ROLL = cut(ROLL, "ALTER TABLE db_pipeline.card_bnft_common ADD COLUMN policy_ver_id", "ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT card_evidence_link_pkey;",
           "\n".join(common_tables) + "\n" + common_idx + "\n\n"
           "ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_ck_6;\n"
           "ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_ck_5;\n"
           "ALTER TABLE db_pipeline.card_bnft ADD CONSTRAINT card_bnft_ck_5 CHECK (bnft_origin_cd <> 'COMMON_LINK' OR jsonb_array_length(rule_list) = 0);\n"
           "ALTER TABLE db_pipeline.card_bnft DROP COLUMN bnft_valid_from;\n"
           "ALTER TABLE db_pipeline.card_bnft DROP COLUMN bnft_valid_to_excl;\n\n"
           "ALTER TABLE db_pipeline.card_extr_stg ALTER COLUMN card_id SET NOT NULL;\n"
           "COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디';\n\n")
ROLL = cut(ROLL, "UPDATE db_pipeline.common_cd c\nSET common_cd = b.common_cd", v6_views[:40], """DELETE FROM db_pipeline.common_cd;
DELETE FROM db_pipeline.common_code_grp;
INSERT INTO db_pipeline.common_code_grp SELECT * FROM db_pipeline_v6_backup.common_code_grp;
INSERT INTO db_pipeline.common_cd SELECT * FROM db_pipeline_v6_backup.common_cd;

""")
v6_views_full = "\n".join(view_block(V6, v) for v in ["v_card_policy_doc", "v_card_rule", "v_card_common_rule", "v_card_rule_pool", "v_card_bnft_rel",
                                                      "v_card_rule_target", "v_card_limit_tier", "v_card_common_limit", "v_card_cond_atom",
                                                      "v_card_bnft_rule_effective", "v_common_cd_usage", "v_card_integrity_issue"])
ROLL = rep(ROLL, v6_views, v6_views_full)
for bad in ("db_pipeline_v6_backup.ev_subject_policy_row", "db_pipeline_v6_backup.common_cd_desc"):
    if bad in ROLL:
        raise SystemExit(f"rollback left over {bad}")
(OUT / "db_pipeline_migration_V7_to_V6_rollback.sql").write_text(ROLL, encoding="utf-8", newline="\n")
print("generated")
