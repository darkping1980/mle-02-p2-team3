"""Local-only Streamlit viewer for the A8 development graph."""
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import QUERIES, connect, source

st.set_page_config(page_title="카드 혜택 GraphRAG", layout="wide")
st.title("카드 혜택 GraphRAG — Neo4j 조회 테스트")
st.warning("개발용 DRAFT·미승인 데이터입니다. 상품의 현재 혜택이나 확정 조건으로 사용하지 마세요.")
st.caption("대중교통 제외의 NOT·범위, 100원/500원 선택, CARD_MEMBER, 정책 시작일, 1인 1매는 검토 중입니다.")

keyword = st.text_input("혜택 검색", placeholder="ONE PICK, STYLE, 대중교통, 놀이공원, 캐시백")
search = None
try:
    search = connect()
    benefits = search.list_benefits(keyword)
    if not benefits:
        st.info("일치하는 혜택이 없습니다.")
    else:
        st.caption(f"혜택 {len(benefits)}건 · 이름 기준 부분 검색")
        selected = st.selectbox("혜택 선택", benefits, format_func=lambda x: x["name"])
        detail = search.get_detail(selected["key"])
        if detail is None:
            st.info("선택한 혜택이 더 이상 존재하지 않습니다.")
        else:
            context = detail["context"]
            card = source(context["card"])
            policy = source(context["policy"])
            benefit = source(context["benefit"])
            st.subheader(selected["name"])
            st.write(f"카드: {card.get('product_nm', '미확인')} · 혜택 검증: {selected.get('status')}")
            st.write(f"정책: {policy.get('source', {}).get('policy_status_cd', '미확인')} · 시작일은 시험 가정")
            st.write(f"혜택 유형: {benefit.get('bnft_type_cd', '미확인')} · 규칙 선택: {benefit.get('rule_select_cd') or '미확정'}")
            with st.expander(f"계산 규칙·적용 대상 ({len(detail['rules'])})", expanded=True):
                for item in detail["rules"]:
                    rule = source(item["rule"])
                    st.write(f"**{rule.get('rule_key')}** · {rule.get('value_num')} {rule.get('value_unit_cd')} · {rule.get('calc_method_cd')} · {rule.get('rule_status_cd')}")
                    st.write("대상: " + (", ".join(item["targets"]) or "미확인"))
            with st.expander(f"적용 조건 ({len(detail['conditions'])})", expanded=True):
                st.caption("조건식 내 분기 사이 OR · 같은 분기의 조건 사이 AND · NOT은 별도 표시")
                for item in detail["conditions"]:
                    atom = source(item["atom"])
                    scope = item["rule_key"] or ("카드 공통" if "A8Policy" in item["owner_labels"] else "혜택")
                    st.write(f"**{scope} / 분기 {item['branch_no']} / {atom.get('atom_key')}** · NOT={atom.get('negate_yn')}")
                    st.write(atom.get("cond_raw_txt") or atom.get("excl_raw_txt") or "원문 조건 미확인")
            with st.expander(f"한도 ({len(detail['limits'])})", expanded=True):
                for item in detail["limits"]:
                    pool = item["pool"]
                    st.write(f"{pool.get('period')} · {pool.get('value')} {pool.get('unit')} · 적용 규칙: {', '.join(item['rule_keys'])}")
                    st.caption("집계 기준 CARD_MEMBER는 시험 가정입니다.")
            with st.expander(f"PDF 원문 근거 ({len(detail['evidence'])})"):
                for item in detail["evidence"]:
                    ev = source(item["evidence"])
                    st.write(f"**{ev.get('page_no')}쪽 · {ev.get('approval_status_cd')} · {ev.get('evidence_id')}**")
                    st.write(ev.get("quote_txt", ""))
            with st.expander("개발자 정보 · 원본 데이터와 Cypher"):
                st.json(detail, expanded=False)
                st.json({"namespace": "ONE_PICK_STYLE_A8", "key": selected["key"]})
                for name, query in QUERIES.items():
                    st.caption(name)
                    st.code(query, language="cypher")
except Exception:
    st.error("Neo4j 조회에 실패했습니다. 연결 설정과 네트워크를 확인하세요.")
finally:
    if search is not None:
        search.driver.close()
