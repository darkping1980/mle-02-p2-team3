from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = Path("src/card_benefit/payment_card/db_pipeline_origin_search/streamlit_app.py")
QUESTION = "카드의정석 POINT II에서 전월 실적이 60만원이면 특별·추가 적립의 통합 월 한도는 얼마야?"

at = AppTest.from_file(str(APP), default_timeout=60).run(timeout=60)
if at.exception:
    raise RuntimeError("initial app run failed: " + "; ".join(str(x.message) for x in at.exception))

at.text_area(key="question").set_value(QUESTION).run(timeout=60)
if at.exception:
    raise RuntimeError("question input rerun failed: " + "; ".join(str(x.message) for x in at.exception))

at.button[0].click().run(timeout=180)
if at.exception:
    raise RuntimeError("submitted app failed: " + "; ".join(str(x.message) for x in at.exception))

outcome = at.session_state.get("outcome")
if not outcome:
    raise RuntimeError("no outcome in Streamlit session state")

print("BUTTON", at.button[0].label)
print("QUESTION", outcome.get("question"))
print("ANSWER", outcome.get("answer", {}).get("answer_text"), outcome.get("answer", {}).get("status"))
print("SEARCH_ENGINES", outcome.get("candidate_search", {}).get("engines"))
print("EVIDENCE", [(x.get("evidence_id"), x.get("page_no"), x.get("quote")) for x in outcome.get("pdf_evidence", [])])
print("ERRORS", [x.value for x in at.error])
