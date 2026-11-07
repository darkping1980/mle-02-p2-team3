"""Streamlit entrypoint for the opt-in fp_chat adapter."""
import os
from pathlib import Path
import runpy
import sys

import streamlit as st
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
CHATBOT_DIR = HERE.parents[3] / "graphrag_chatbot"
if str(CHATBOT_DIR) not in sys.path:
    sys.path.insert(0, str(CHATBOT_DIR))
from fp_chat_patch import apply

# 팀 llm.py는 Anthropic을 쓰므로, 팀 코드가 import되기 전에 OpenAI 어댑터를 먼저 끼운다(D2, D3).
# 키는 환경 변수 또는 저장소 루트의 .env에서 받는다(이미 export한 값이 우선). AI는 .env를 열지 않는다(D4).
# 시험용으로 FP_CHAT_ENV_FILE로 .env 위치를 바꿀 수 있다.
load_dotenv(os.environ.get("FP_CHAT_ENV_FILE") or HERE.parents[4] / ".env", override=False)
# 셸 source 로 .env(CRLF)를 읽은 터미널에서는 값 끝에 '\r' 이 남아 DB 이름이 'postgres\r' 이 된다. 앞뒤 공백·줄바꿈을 제거한다.
for _name in ("DB_URL", "FP_DATABASE_URL", "DB_URI", "OPENAI_API_KEY"):
    if os.environ.get(_name):
        os.environ[_name] = os.environ[_name].strip()
# 팀 코드는 DB_URL을 읽는다. 없으면 FP_DATABASE_URL, 그것도 없으면 DB_URI(사용자 .env의 Supabase 접속 문자열) 순으로 넘겨 준다.
if not os.environ.get("DB_URL"):
    for _name in ("FP_DATABASE_URL", "DB_URI"):
        if os.environ.get(_name):
            os.environ["DB_URL"] = os.environ[_name]
            break
if not os.environ.get("OPENAI_API_KEY"):
    st.set_page_config(page_title="GraphRAG 챗봇")
    st.error("OPENAI_API_KEY 환경 변수가 필요합니다. 터미널에서 export 한 뒤 다시 실행하세요.")
    st.stop()
from openai_llm_patch import install

install()
apply()
original_set_page_config = st.set_page_config

def _set_page_config_with_mode(*args, **kwargs):
    original_set_page_config(*args, **kwargs)
    st.set_page_config = original_set_page_config
    st.info("우리 카드 데이터(fp_chat) 모드")

st.set_page_config = _set_page_config_with_mode
runpy.run_path(str(CHATBOT_DIR / "app.py"), run_name="__main__")
st.set_page_config = original_set_page_config
