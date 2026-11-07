"""근거 하위 그래프를 pyvis HTML로 그립니다."""
import json

import streamlit as st
from pyvis.network import Network

# 노드 타입별 (배경색, 테두리색). 새 타입을 쓰면 여기에 추가하세요.
STYLE = {
    "Service": ("#dbeafe", "#1e5a96"),
    "Team": ("#dcf3e4", "#1f7a45"),
    "Document": ("#fdf0d0", "#8a5a00"),
}
DEFAULT_STYLE = ("#eceef3", "#5b6070")
SEED_BORDER = "#d62f2f"  # 질문에서 찾은 엔티티

OPTIONS = {
    "physics": {"solver": "forceAtlas2Based", "stabilization": {"iterations": 150}},
    "interaction": {"hover": True, "tooltipDelay": 100},
    "edges": {"smooth": {"type": "dynamic"}},
}


def _clean(value) -> str:
    """그래프 데이터는 DB(문서에서 추출한 값 포함)에서 오므로, 스크립트 태그를 만들 수 있는
    < > 문자를 전각 문자로 바꿉니다. 이 HTML은 JavaScript가 실행되는 iframe에 들어갑니다."""
    return str(value).replace("<", "＜").replace(">", "＞")


@st.cache_data(show_spinner=False)
def build_html(subgraph_json: str) -> str:
    sub = json.loads(subgraph_json)
    seeds = set(sub.get("seeds", []))
    net = Network(
        height="400px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#262730",
        cdn_resources="remote",
    )
    for n in sub["nodes"]:
        bg, border = STYLE.get(n["label"], DEFAULT_STYLE)
        is_seed = n["id"] in seeds
        tooltip = " · ".join([n["label"]] + [f"{k}: {v}" for k, v in n["props"].items()])
        net.add_node(
            _clean(n["id"]),
            label=_clean(f"{n['name']}\n({n['label']})"),
            title=_clean(tooltip),
            shape="box",
            color={"background": bg, "border": SEED_BORDER if is_seed else border},
            borderWidth=3 if is_seed else 1.5,
            font={"size": 14, "color": "#262730"},
        )
    for e in sub["edges"]:
        net.add_edge(
            _clean(e["source"]),
            _clean(e["target"]),
            label=_clean(e["type"]),
            arrows="to",
            color="#5b6070",
            font={"size": 11, "strokeWidth": 4, "strokeColor": "#ffffff"},
        )
    net.set_options(json.dumps(OPTIONS))
    return net.generate_html()
