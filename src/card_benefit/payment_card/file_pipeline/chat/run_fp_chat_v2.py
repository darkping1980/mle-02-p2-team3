"""Launch the v2 fp_chat screen with the existing OpenAI and graph adapters."""
from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
PACKAGE_ROOT = REPO_ROOT / "src" / "card_benefit"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from payment_card.file_pipeline.chat.panel import prepare_backend, render

st.set_page_config(page_title="카드 혜택 챗봇", layout="centered")
if prepare_backend():
    render(key_prefix="v2")
