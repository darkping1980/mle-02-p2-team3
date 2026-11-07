"""질문 1건의 구간별 소요 시간을 JSON 한 줄로 기록합니다. 동작은 바꾸지 않고, 기록에 실패해도 앱은 계속 돌아갑니다.

구간: entities_db(엔티티 목록 조회) / analyze_llm(질의 분석 LLM) / explore_db(그래프 탐색 DB) /
      first_token(답변 요청부터 첫 글자까지) / stream(첫 글자부터 끝까지) / total(질문 시작부터 끝까지)
저장 위치: 기본은 이 파일 옆의 errors/timing.jsonl. 바꾸려면 환경 변수 TIMING_LOG_DIR.
질문 원문은 앞 40자까지만 남깁니다. 비밀번호·키·접속 문자열은 기록하지 않습니다.
"""
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_local = threading.local()


def _log_path() -> Path:
    base = os.getenv("TIMING_LOG_DIR") or str(Path(__file__).resolve().parent / "errors")
    return Path(base) / "timing.jsonl"


def start(question: str) -> None:
    """질문 처리를 시작할 때 한 번 부릅니다."""
    _local.trace = {
        "t0": time.perf_counter(),
        "question": question[:40],
        "question_len": len(question),
        "stages_ms": {},
    }


def active() -> bool:
    return getattr(_local, "trace", None) is not None


@contextmanager
def stage(name: str):
    """with timing.stage("explore_db"): ... 형태로 구간을 잽니다. start()를 안 불렀으면 아무것도 하지 않습니다."""
    trace = getattr(_local, "trace", None)
    t = time.perf_counter()
    try:
        yield
    finally:
        if trace is not None:
            ms = (time.perf_counter() - t) * 1000
            trace["stages_ms"][name] = round(trace["stages_ms"].get(name, 0) + ms, 1)


def mark(name: str, ms: float) -> None:
    trace = getattr(_local, "trace", None)
    if trace is not None:
        trace["stages_ms"][name] = round(ms, 1)


def since_start_ms() -> float:
    trace = getattr(_local, "trace", None)
    return 0.0 if trace is None else (time.perf_counter() - trace["t0"]) * 1000


def finish(**extra) -> dict | None:
    """합계를 계산해 파일에 한 줄 추가합니다. 쓰기에 실패해도 예외를 내지 않습니다."""
    trace = getattr(_local, "trace", None)
    if trace is None:
        return None
    _local.trace = None
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": trace["question"],
        "question_len": trace["question_len"],
        "stages_ms": trace["stages_ms"],
        "total_ms": round((time.perf_counter() - trace["t0"]) * 1000, 1),
        **extra,
    }
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return record
