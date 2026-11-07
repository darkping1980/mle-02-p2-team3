"""Public host integration points for the fp_chat screen."""
from __future__ import annotations

import streamlit as st


_BACKEND_PREPARED = False


def prepare_backend() -> bool:
    """Load backend settings and install the chat adapters once per process."""
    global _BACKEND_PREPARED
    if _BACKEND_PREPARED:
        return True

    import os
    import sys
    from pathlib import Path

    from dotenv import load_dotenv

    here = Path(__file__).resolve().parent
    repo_root = here.parents[4]
    chatbot_dir = repo_root / "src" / "graphrag_chatbot"
    if str(chatbot_dir) not in sys.path:
        sys.path.insert(0, str(chatbot_dir))
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    load_dotenv(os.environ.get("FP_CHAT_ENV_FILE") or repo_root / ".env", override=False)
    # Shell-sourced CRLF values can retain a trailing carriage return.
    for name in ("DB_URL", "FP_DATABASE_URL", "DB_URI", "OPENAI_API_KEY"):
        if os.environ.get(name):
            os.environ[name] = os.environ[name].strip()
    if not os.environ.get("DB_URL"):
        for name in ("FP_DATABASE_URL", "DB_URI"):
            if os.environ.get(name):
                os.environ["DB_URL"] = os.environ[name]
                break

    if not os.environ.get("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY 환경 변수가 필요합니다.")
        return False

    # Keep these as bare-name imports after sys.path setup. The adapters share
    # their module state with the script-style GraphRAG imports.
    from fp_chat_patch import apply
    from openai_llm_patch import install

    install(
        max_cost_usd=float(os.environ.get("FP_MAX_COST_USD", "0.10")),
        sleep=float(os.environ.get("FP_LLM_SLEEP", "0.3")),
    )
    apply()
    _BACKEND_PREPARED = True
    return True


def render(*, key_prefix: str) -> None:
    """Prepare the backend if needed, then render the screen body."""
    if not prepare_backend():
        return

    try:
        from .ui.app_v2 import render as _render
    except ImportError:
        from ui.app_v2 import render as _render

    _render(key_prefix=key_prefix)
