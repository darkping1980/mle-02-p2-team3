"""개발 DB 등록 흐름 시험. 모든 변경은 트랜잭션 안에서 하고 ROLLBACK한다. 시퀀스 번호만 소비된다.

실행: RUN_DB_INTEGRATION=1 uv run pytest src/card_benefit/payment_card/tests/test_live_registration.py
실제 임베딩 API도 호출한다.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re

from psycopg.types.json import Jsonb
import pytest

from card_benefit.payment_card.db_pipeline.common_benefit_service import CommonBenefitService
from card_benefit.payment_card.db_pipeline.document_repository import MAPPER_ROOT
from card_benefit.payment_card.db_pipeline.embedding_service import EMBEDDING_LOG_KEYS, EmbeddingService, OpenAIEmbedder
from card_benefit.payment_card.db_pipeline.product_benefit_service import ProductBenefitService
from card_benefit.payment_card.db_pipeline.register_service import CommonDocLink, ProductDocLink, RegisterService
from common.postgres_db_session import PostgresDbSession
from common.query_log_config import load_project_environment

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_INTEGRATION") != "1", reason="개발 DB 시험")

PRODUCT_PDF = "credit/신용_JADEPrime_상품설명서(공식PDF)_14997_20250703.pdf"
COMMON_PDF = "common/공통_VISA브랜드서비스_VP001_20260317.pdf"
SQL_ROOT = Path(__file__).resolve().parents[2] / "sql"


class Rollback(Exception):
    pass


class OuterSession(PostgresDbSession):
    """서비스의 트랜잭션을 바깥 시험 트랜잭션에 합친다."""

    @contextmanager
    def transaction(self):
        if self._active_connection is not None:
            yield self
        else:
            with super().transaction():
                yield self


@pytest.fixture
def session():
    load_project_environment()
    item = OuterSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none",
                        sensitive_log_keys=EMBEDDING_LOG_KEYS)
    yield item
    item.database_manager.close()


def raw(session, sql, *params):
    return session._active_connection.execute(sql, params).fetchall()


def counts(session):
    tables = ("card_doc", "card_product_doc", "card_common", "card_common_doc", "card_common_bnft",
              "card_common_bnft_apply", "card_bnft", "card_evidence_link", "card_extr_stg", "card_source_evidence")
    with session.database_manager.connect(camel_case_keys=False) as connection:
        return {name: connection.execute(f"select count(*) AS n from db_pipeline.{name}").fetchone()["n"] for name in tables}


def sample_stg(session, card_doc_id, card_id, run_id, item, quote, seq):
    """실제 페이지 문구로 추출 후보 1건을 만든다."""
    chunk = raw(session, """select page_no, card_doc_chunk_id, chunk_raw_txt from db_pipeline.card_doc_chunk
                            where card_doc_id=%s and position(%s in chunk_raw_txt) > 0 order by chunk_seq limit 1""",
                card_doc_id, quote)[0]
    page_no, chunk_id, text = chunk["page_no"], chunk["card_doc_chunk_id"], chunk["chunk_raw_txt"]
    start = text.index(quote) + 1
    call = raw(session, """insert into db_pipeline.card_ai_call (card_ai_run_id,card_doc_id,page_no,card_doc_chunk_id,call_seq,
                call_input_sha256,call_status,call_resp_json,create_user_id,update_user_id)
                values (%s,%s,%s,%s,%s,%s,'SUCCEEDED','{}'::jsonb,'TEST','TEST')
                on conflict do nothing returning call_seq""", run_id, card_doc_id, page_no, chunk_id, seq, "0" * 64)
    assert call
    stg = raw(session, """insert into db_pipeline.card_extr_stg (card_ai_run_id,card_doc_id,page_no,card_doc_chunk_id,call_seq,stg_item_seq,
                card_id,stg_kind_cd,stg_raw_item,stg_evidence_txt,stg_sql_check_cd,create_user_id,update_user_id)
                values (%s,%s,%s,%s,%s,1,%s,'BENEFIT',%s,%s,'OK','TEST','TEST') returning card_extr_stg_id""",
              run_id, card_doc_id, page_no, chunk_id, seq, card_id, Jsonb(item["raw"]), quote)   # 정제본 컬럼 없음(원본에서 재생성)[0]["card_extr_stg_id"]
    raw(session, """insert into db_pipeline.card_source_evidence (card_doc_id,page_no,card_doc_chunk_id,card_extr_stg_id,quote_txt,
                    start_pos,end_pos,approval_status_cd) values (%s,%s,%s,%s,%s,%s,%s,'PENDING') returning evidence_id""",
        card_doc_id, page_no, chunk_id, stg, quote, start, start + len(quote) - 1)
    return stg


def norm(name, rules):
    return {"bnft_cd": "BNFT_LIVE_SAMPLE", "bnft_nm": name, "bnft_type_cd": "DISCOUNT", "relation_list": [], "limit_list": [],
            "bnft_cond_expr": None, "rule_list": rules, "checks": {"value_check_cd": "OK"},
            "merge": {"source_refs": [{"page_no": 1}]}}


def test_new_documents_benefits_and_embedding_roll_back(session):
    before = counts(session)
    embedding = EmbeddingService(session, OpenAIEmbedder())
    with pytest.raises(Rollback):
        with session.transaction():
            register = RegisterService(session)
            product = register.register(PRODUCT_PDF, apply=True, product_link=ProductDocLink(5, "시험"))
            assert product.status == "REGISTERED" and product.linked == "card_product_doc card_id=5"
            again = register.register(PRODUCT_PDF, apply=True, product_link=ProductDocLink(5, "시험"))
            assert again.status == "ALREADY_REGISTERED"
            assert len(raw(session, "select 1 from db_pipeline.card_product_doc where card_doc_id=%s", product.card_doc_id)) == 1

            link = CommonDocLink("TEST_VISA_PLATINUM", "시험 Visa Platinum", "VISA", "PLATINUM")
            common_doc = register.register(COMMON_PDF, apply=True, common_link=link)
            assert common_doc.status == "REGISTERED" and "card_common_doc" in common_doc.linked
            register.register(COMMON_PDF, apply=True, common_link=link)
            assert len(raw(session, "select 1 from db_pipeline.card_common_doc where card_doc_id=%s", common_doc.card_doc_id)) == 1

            # 공통 혜택 샘플: 등록·임베딩은 되고, Platinum 선택지가 없는 카드에는 연결되지 않는다.
            run_id = raw(session, """insert into db_pipeline.card_ai_run (run_stage_cd,run_call_mthd_cd,run_model_nm,run_prompt_ver,run_prompt_txt,
                                     run_status,run_target_card_doc_id,create_user_id,update_user_id)
                                     values ('EXTRACT','PYTHON_RELAY','TEST','TEST','TEST','SUCCEEDED',%s,'TEST','TEST')
                                     returning card_ai_run_id""", common_doc.card_doc_id)[0]["card_ai_run_id"]
            page = raw(session, "select chunk_raw_txt from db_pipeline.card_doc_chunk where card_doc_id=%s order by chunk_seq limit 1",
                       common_doc.card_doc_id)[0]["chunk_raw_txt"]
            quote = next(line.strip() for line in page.splitlines() if "할인" in line)
            stg = sample_stg(session, common_doc.card_doc_id, None, run_id, {
                "raw": {"brand_txt": "Visa", "service_grade_txt": "Platinum", "selection_service_txt": None, "applicable_cards": [],
                        "excluded_cards": [], "validity_period_txt": None, "evidence": [{"supports": "BNFT", "quote_txt": quote}]},
                "norm": norm("시험 공통 할인", [])}, quote, 1)
            service = CommonBenefitService(session, embedding_service=embedding)
            decision = service.register_run(run_id, {stg: "TEST_SAMPLE"})[0]
            assert decision.status == "INSERTED", decision
            assert service.register_run(run_id, {stg: "TEST_SAMPLE"})[0].status == "UNCHANGED"
            row = raw(session, """select bnft_search_txt, extensions.vector_dims(bnft_embedding) AS dims from db_pipeline.card_common_bnft
                                  where card_common_bnft_id=%s""", decision.card_common_bnft_id)[0]
            assert row["dims"] == 1536 and "공통서비스: 시험 Visa Platinum" in row["bnft_search_txt"]
            assert "JADE" not in row["bnft_search_txt"]
            applied = service.apply_run(5, run_id, {stg: "TEST_SAMPLE"})[0]
            assert applied.status == "REVIEW", applied
            assert not raw(session, "select 1 from db_pipeline.card_common_bnft_apply where card_common_bnft_id=%s", decision.card_common_bnft_id)

            # 상품 혜택: 기존 4건은 그대로, 새 후보만 등록된다.
            run = "20261101_000002"
            existing = ProductBenefitService(session).register_run(2, run)
            assert [item.status for item in existing] == ["UNCHANGED"] * 4
            guide = "20261101_000002"
            text = raw(session, "select chunk_raw_txt from db_pipeline.card_doc_chunk where card_doc_id=%s order by chunk_seq limit 1", guide)[0]["chunk_raw_txt"]
            quote = "5%\n캐시백" if "5%\n캐시백" in text else re.search(r"\d+%", text).group(0)
            rule = {"rule_key": "sample", "rule_status_cd": "DRAFT", "value_num": 5, "value_unit_cd": "PERCENT", "cond_expr": None,
                    "target_list": [{"target_nm": "시험대상", "target_key": "시험대상", "target_type_cd": "SERVICE"}]}
            stg = sample_stg(session, guide, 2, run, {
                "raw": {"evidence": [{"supports": "BNFT", "quote_txt": quote}, {"supports": "RULE", "support_key": "sample", "quote_txt": quote}]},
                "norm": norm("시험 상품 혜택", [rule])}, quote, 99)
            results = ProductBenefitService(session, embedding).register_run(2, run)
            added = [item for item in results if item.status == "INSERTED"]
            assert len(added) == 1, results
            row = raw(session, """select bnft_search_txt, extensions.vector_dims(bnft_embedding) AS dims,
                                  (select count(*) from db_pipeline.card_evidence_link l where l.card_id=2 and l.card_bnft_id=b.card_bnft_id) AS links
                                  from db_pipeline.card_bnft b where card_id=2 and card_bnft_id=%s""", added[0].card_bnft_id)[0]
            assert row["dims"] == 1536 and row["links"] >= 2 and "서비스 대상: 시험대상" in row["bnft_search_txt"]
            assert [item.status for item in ProductBenefitService(session).register_run(2, run)].count("INSERTED") == 0
            raise Rollback
    assert counts(session) == before


def test_transfer_proposal_loses_nothing_and_rolls_back(session):
    """이관안을 실제 행으로 실행해 대응 관계와 근거 보존을 확인한다."""
    before = counts(session)
    backup = json.loads((SQL_ROOT.parents[1] / "data" / "backup" / "pre_common_transfer_20261103.json").read_text(encoding="utf-8"))
    legacy = backup["card_bnft"][0]
    original_evidence = {row["evidence_id"] for row in backup["card_evidence_link"]}
    table = (SQL_ROOT / "db_pipeline_proposal_common_evidence_link.sql").read_text(encoding="utf-8")
    table = table.replace("BEGIN;", "").replace("COMMIT;", "")
    text = (SQL_ROOT / "db_pipeline_proposal_brand_service_bnft_transfer.sql").read_text(encoding="utf-8")
    step = text.split("-- 2.", 1)[1]
    statements = "\n".join(line[3:] for line in step.splitlines() if line.startswith("-- ") and line[3:] not in ("BEGIN;", "COMMIT;"))
    assert all(row["status"] == "SAME" for row in CommonBenefitService(session).compare_brand_benefits())
    with pytest.raises(Rollback):
        with session.transaction():
            connection = session._active_connection
            connection.execute(table)
            connection.execute(statements)
            mapped = raw(session, """select b.bnft_cd, b.bnft_nm, l.evidence_id, a.card_id
                                     from db_pipeline.card_common_evidence_link l
                                     join db_pipeline.card_common_bnft b using (card_common_id, card_common_bnft_id)
                                     join db_pipeline.card_common_bnft_apply a using (card_common_id, card_common_bnft_id)""")
            assert {row["evidence_id"] for row in mapped} == original_evidence
            assert {row["bnft_cd"] for row in mapped} == {legacy["bnft_cd"]} and {row["card_id"] for row in mapped} == {legacy["card_id"]}
            assert not raw(session, "select 1 from db_pipeline.card_bnft where bnft_origin_cd='BRAND_SERVICE'")
            kept = raw(session, "select count(*) AS n from db_pipeline.card_source_evidence where evidence_id = any(%s)", list(original_evidence))
            assert kept[0]["n"] == len(original_evidence)
            gates = raw(session, "select gate_cd, count(*) AS n from db_pipeline.v_card_integrity_issue group by 1")
            assert {row["gate_cd"] for row in gates} <= {"evidence_not_approved"}
            raise Rollback
    assert counts(session) == before
