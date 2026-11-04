"""상품설명서 원문에서 확인한 연회비를 card_product_item(ANNUAL_FEE)으로 등록한다.

금액·구분은 사람이 원문 표를 읽어 아래 SEED에 적었다. 등록할 때 인용문을 청크 원문에서 다시 찾아 위치를 계산하고,
못 찾으면 등록하지 않는다. 브랜드는 상품 brand_opt_list에 같은 옵션이 있을 때만 brand_opt_cds로 연결하고,
없으면 줄을 REVIEW로 둔다(PDF의 브랜드 표기가 현재 발급 가능하다는 뜻은 아니다).

실행(저장소 루트):  .venv/Scripts/python -m card_benefit.payment_card.db_pipeline.annual_fee_register [--apply]
--apply 없이는 계획만 출력한다. 이미 같은 item_cd가 있으면 건너뛴다(덮어쓰지 않음).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

USER = "ANNUAL_FEE_SEED"

# 인용문은 청크 원문과 글자 그대로 같아야 한다. role: SELF(항목 전체 근거) 또는 줄 key 목록(FEE_LINE 근거).
SEED = [
    {"card_id": 2, "card_doc_id": "20261101_000002", "page_no": 1, "chunk_id": "20261101_000012",
     "quotes": [{"text": "[연회비] 없음", "lines": ["PRINCIPAL_ALL"]}],
     "lines": [{"line_key": "PRINCIPAL_ALL", "holder_type_cd": "PRINCIPAL", "brand_txt": None, "brand_cds": None,
                "brand_opts": None, "basic_fee_amt": None, "affiliate_fee_amt": None, "total_fee_amt": 0}],
     "note": "체크카드. 원문 '[연회비] 없음'. 가족카드 언급 없음"},
    {"card_id": 5, "card_doc_id": "20261102_000003", "page_no": 5, "chunk_id": "20261102_000018",
     "quotes": [
         {"text": "연회비 청구기준 : 카드별(본인/가족) 카드 발급일(발급 첫해에는 \n\t 카드사용등록일)이 속한 카드이용기간의 첫 결제일에 청구되며, \n\t 카드별 발급 시점을 기준으로 1년 단위로 청구됩니다.", "lines": "SELF"},
         {"text": "구분\n본인\n가족\n기본\n제휴\n총 연회비\n기본\n제휴\n총 연회비", "lines": "SELF"},
         {"text": "국내외겸용 \n(Visa, Mastercard,\nAmex)\n20,000\n100,000\n120,000\n20,000\n10,000\n30,000",
          "lines": ["PRINCIPAL_VISA_MC_AMEX", "FAMILY_VISA_MC_AMEX"]},
         {"text": "국내외겸용 \n(UPI)\n20,000\n95,000\n115,000\n20,000\n5,000\n25,000", "lines": ["PRINCIPAL_UPI", "FAMILY_UPI"]},
         {"text": "국내전용\n20,000\n95,000\n115,000\n20,000\n5,000\n25,000", "lines": ["PRINCIPAL_LOCAL", "FAMILY_LOCAL"]}],
     "lines": [
         {"line_key": "PRINCIPAL_VISA_MC_AMEX", "holder_type_cd": "PRINCIPAL", "brand_txt": "국내외겸용 (Visa, Mastercard, Amex)",
          "brand_cds": ["VISA", "MASTERCARD", "AMEX"], "brand_opts": ["VISA", "MASTERCARD", "AMEX"],
          "basic_fee_amt": 20000, "affiliate_fee_amt": 100000, "total_fee_amt": 120000},
         {"line_key": "FAMILY_VISA_MC_AMEX", "holder_type_cd": "FAMILY", "brand_txt": "국내외겸용 (Visa, Mastercard, Amex)",
          "brand_cds": ["VISA", "MASTERCARD", "AMEX"], "brand_opts": ["VISA", "MASTERCARD", "AMEX"],
          "basic_fee_amt": 20000, "affiliate_fee_amt": 10000, "total_fee_amt": 30000},
         {"line_key": "PRINCIPAL_UPI", "holder_type_cd": "PRINCIPAL", "brand_txt": "국내외겸용 (UPI)", "brand_cds": ["UPI"],
          "brand_opts": ["UPI"], "basic_fee_amt": 20000, "affiliate_fee_amt": 95000, "total_fee_amt": 115000},
         {"line_key": "FAMILY_UPI", "holder_type_cd": "FAMILY", "brand_txt": "국내외겸용 (UPI)", "brand_cds": ["UPI"],
          "brand_opts": ["UPI"], "basic_fee_amt": 20000, "affiliate_fee_amt": 5000, "total_fee_amt": 25000},
         {"line_key": "PRINCIPAL_LOCAL", "holder_type_cd": "PRINCIPAL", "brand_txt": "국내전용", "brand_cds": ["LOCAL"],
          "brand_opts": ["LOCAL"], "basic_fee_amt": 20000, "affiliate_fee_amt": 95000, "total_fee_amt": 115000},
         {"line_key": "FAMILY_LOCAL", "holder_type_cd": "FAMILY", "brand_txt": "국내전용", "brand_cds": ["LOCAL"],
          "brand_opts": ["LOCAL"], "basic_fee_amt": 20000, "affiliate_fee_amt": 5000, "total_fee_amt": 25000}],
     "note": "p5 연회비 표(본인·가족 × 기본·제휴·총). 가족카드 연회비는 상품별 부과 기준을 따른다"},
    {"card_id": 6, "card_doc_id": "20261104_000023", "page_no": 5, "chunk_id": "20261104_000082",
     "quotes": [
         {"text": "• 연회비는 카드발급시점을 기준으로 1년 단위로 청구됩니다.", "lines": "SELF"},
         {"text": "• 연회비(기본 연회비＋제휴 연회비)는 카드별로 청구됩니다.", "lines": "SELF"},
         {"text": "해외겸용  \n(Mastercard, VISA) \n12,000원  \n(기본 연회비 5,000원 + 제휴 연회비 7,000원)", "lines": ["PRINCIPAL_MC_VISA"]},
         {"text": "국내전용 (UnionPay) \n10,000원  \n(기본 연회비 5,000원 + 제휴 연회비 5,000원)", "lines": ["PRINCIPAL_UPI"]},
         {"text": "• 가족카드 연회비는 청구하지 않습니다.", "lines": ["FAMILY_ALL"]}],
     "lines": [
         {"line_key": "PRINCIPAL_MC_VISA", "holder_type_cd": "PRINCIPAL", "brand_txt": "해외겸용 (Mastercard, VISA)",
          "brand_cds": ["MASTERCARD", "VISA"], "brand_opts": ["MASTERCARD", "VISA"],
          "basic_fee_amt": 5000, "affiliate_fee_amt": 7000, "total_fee_amt": 12000},
         {"line_key": "PRINCIPAL_UPI", "holder_type_cd": "PRINCIPAL", "brand_txt": "국내전용 (UnionPay)", "brand_cds": ["UPI"],
          "brand_opts": ["UPI"], "basic_fee_amt": 5000, "affiliate_fee_amt": 5000, "total_fee_amt": 10000},
         {"line_key": "FAMILY_ALL", "holder_type_cd": "FAMILY", "brand_txt": None, "brand_cds": None, "brand_opts": None,
          "basic_fee_amt": None, "affiliate_fee_amt": None, "total_fee_amt": 0,
          # 같은 사실이 기존 혜택(가족카드 연회비 면제)으로도 등록돼 있다. 답변에서 두 번 세지 않도록 서로 가리킨다.
          "same_fact_item_ref": "card_product_item:6:20261104_000023"}],
     "note": "p5 연회비 안내. 가족카드 연회비 0원은 기존 혜택 '가족카드 연회비 면제'와 같은 사실"},
]


def brand_options(product, wanted):
    """상품 brand_opt_list에서 브랜드 코드가 같은 옵션을 찾는다. 모두 찾으면 옵션 코드, 하나라도 없으면 None."""
    if wanted is None:
        return None, None
    options = product["brand_opt_list"] or []
    found = []
    for brand in wanted:
        codes = [o["brand_opt_cd"] for o in options if o.get("brand_cd") == brand and o.get("brand_opt_status_cd", "ACTIVE") == "ACTIVE"]
        if not codes:
            return None, f"상품 브랜드 옵션에 {brand}가 없음(brand_opt_list {len(options)}건). 원문 표기만으로 발급 가능 브랜드로 확정하지 않음"
        found.extend(codes)
    return found, None


def build(cur, seed):
    product = cur.execute("SELECT card_id, product_nm, brand_opt_list FROM db_pipeline.card_product WHERE card_id=%s",
                          (seed["card_id"],)).fetchone()
    chunk = cur.execute("""SELECT chunk_raw_txt FROM db_pipeline.card_doc_chunk
                           WHERE card_doc_id=%s AND page_no=%s AND card_doc_chunk_id=%s""",
                        (seed["card_doc_id"], seed["page_no"], seed["chunk_id"])).fetchone()
    if product is None or chunk is None:
        raise ValueError(f"상품 또는 청크 없음: {seed['card_id']} {seed['chunk_id']}")
    text = chunk["chunk_raw_txt"]
    quotes = []
    for quote in seed["quotes"]:
        index = text.find(quote["text"])
        if index < 0 or text.find(quote["text"], index + 1) >= 0:
            raise ValueError(f"인용문 위치를 하나로 특정할 수 없음: {quote['text'][:30]!r}")
        quotes.append({**quote, "start_pos": index + 1, "end_pos": index + len(quote["text"])})
    lines = []
    for line in seed["lines"]:
        opts, problem = brand_options(product, line["brand_opts"])
        item = {k: v for k, v in line.items() if k != "brand_opts" and v is not None}
        if opts:
            item["brand_opt_cds"] = opts
        item["line_status_cd"] = "REVIEW" if problem else "DRAFT"
        if problem:
            item["review_note"] = problem
        lines.append(item)
    data = {"schema_ver": "ANNUAL_FEE_V1", "currency_cd": "KRW", "source_note": seed["note"], "fee_lines": lines}
    rule_txt = " / ".join(" ".join(q["text"].split()) for q in quotes)
    return product, quotes, data, rule_txt


def register(conn, apply: bool):
    report = []
    with conn.cursor(row_factory=dict_row) as cur:
        for seed in SEED:
            item_cd = f"ANNUAL_FEE@{seed['card_doc_id']}"
            existing = cur.execute("SELECT card_product_item_id FROM db_pipeline.card_product_item WHERE card_id=%s AND item_cd=%s",
                                   (seed["card_id"], item_cd)).fetchone()
            product, quotes, data, rule_txt = build(cur, seed)
            entry = {"card_id": seed["card_id"], "product_nm": product["product_nm"], "item_cd": item_cd,
                     "lines": [(l["line_key"], l.get("total_fee_amt"), l["line_status_cd"]) for l in data["fee_lines"]]}
            if existing:
                report.append({**entry, "status": "UNCHANGED", "card_product_item_id": existing["card_product_item_id"]})
                continue
            if not apply:
                report.append({**entry, "status": "PLAN", "quotes": len(quotes)})
                continue
            item_id = cur.execute("""
                INSERT INTO db_pipeline.card_product_item (card_id, item_type_cd, item_cd, item_nm, item_data, item_rule_txt,
                       create_user_id, update_user_id)
                VALUES (%s, 'ANNUAL_FEE', %s, '연회비', %s, %s, %s, %s) RETURNING card_product_item_id""",
                (seed["card_id"], item_cd, Jsonb(data), rule_txt, USER, USER)).fetchone()["card_product_item_id"]
            links = 0
            for quote in quotes:
                evidence_id = cur.execute("""
                    INSERT INTO db_pipeline.card_source_evidence (card_doc_id, page_no, card_doc_chunk_id, quote_txt, start_pos, end_pos,
                           approval_status_cd)
                    VALUES (%s, %s, %s, %s, %s, %s, 'PENDING') RETURNING evidence_id""",
                    (seed["card_doc_id"], seed["page_no"], seed["chunk_id"], quote["text"], quote["start_pos"], quote["end_pos"])
                ).fetchone()["evidence_id"]
                targets = [("SELF", "-")] if quote["lines"] == "SELF" else [("FEE_LINE", key) for key in quote["lines"]]
                for item_cd_value, item_key in targets:
                    cur.execute("""
                        INSERT INTO db_pipeline.card_evidence_link (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id,
                               ev_subject_cd, card_product_item_id, ev_item_cd, ev_item_key)
                        VALUES (%s, %s, %s, %s, %s, 'ITEM', %s, %s, %s)""",
                        (seed["card_doc_id"], seed["page_no"], seed["chunk_id"], evidence_id, seed["card_id"], item_id,
                         item_cd_value, item_key))
                    links += 1
            # 같은 사실을 가진 기존 혜택에도 연회비 줄을 가리키게 한다(혜택 내용·원문은 바꾸지 않고 item_data만).
            for line in data["fee_lines"]:
                ref = line.get("same_fact_item_ref")
                if ref:
                    _, card_id, benefit_id = ref.split(":")
                    cur.execute("""
                        UPDATE db_pipeline.card_product_item
                        SET item_data = jsonb_build_object('schema_ver', 'BENEFIT_V1', 'same_fact',
                                jsonb_build_object('item_ref', %s::text, 'line_key', %s::text,
                                                   'note', '같은 사실을 연회비 항목 줄로도 보관. 답변에서 한 번만 센다')),
                            update_date = now(), update_user_id = %s
                        WHERE card_id = %s AND card_product_item_id = %s AND item_type_cd = 'BENEFIT'""",
                        (f"card_product_item:{seed['card_id']}:{item_id}", line["line_key"], USER, int(card_id), benefit_id))
            report.append({**entry, "status": "INSERTED", "card_product_item_id": item_id, "evidence": len(quotes), "links": links})
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"]) as conn:
        report = register(conn, args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
