"""Bounded concurrent chunk execution with classified retries and fail-fast."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import sys
import time
from typing import Any, Callable

from .runner import run_chunk


class ChunkResults(list):
    def __init__(self, values, *, stopped_reason=None, started=0):
        super().__init__(values)
        self.stopped_reason = stopped_reason
        self.started = started


def process_chunks(chunks: list[dict], doc_sha256: str, llm_call: Callable[[str], str],
                   workers: int = 1, retries: int = 2,
                   progress: Callable[[int, int], None] | None = None,
                   on_result: Callable[[int, dict[str, Any]], None] | None = None,
                   fail_fast: bool = True, fail_fast_threshold: int = 3) -> list[dict[str, Any]]:
    workers = max(1, min(16, workers))
    if retries < 0 or fail_fast_threshold < 1:
        raise ValueError("retries must be non-negative and fail_fast_threshold positive")

    def execute(chunk):
        for attempt in range(retries + 1):
            try:
                result = run_chunk(chunk, doc_sha256, llm_call)
                if not any(f.get("code") == "llm_call_failure" for f in result.get("failures", [])) or attempt == retries:
                    return result
            except Exception as error:
                retryable = getattr(error, "retryable", True)
                if retryable and attempt < retries:
                    time.sleep(0.25 * (2 ** attempt))
                    continue
                return {"doc_sha256": doc_sha256, "page_no": chunk["page_no"],
                        "chunk_id": chunk.get("chunk_id"), "chunk_length": len(chunk["text"]),
                        "extraction": None, "failures": [{"code": "llm_call_failure",
                        "message": str(error), "exception_type": type(error).__name__,
                        "status_code": getattr(error, "status_code", None),
                        "error_code": getattr(error, "error_code", None),
                        "retryable": retryable}], "notes": []}

    results = [None] * len(chunks)
    done = started = next_index = 0
    streak_code = None
    streak = 0
    stopped_reason = None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        while next_index < len(chunks) and len(active) < workers:
            active[pool.submit(execute, chunks[next_index])] = next_index
            next_index += 1
            started += 1
        while active:
            finished, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in finished:
                idx = active.pop(future)
                result = future.result()
                results[idx] = result
                if on_result:
                    on_result(idx, result)
                done += 1
                if progress:
                    progress(done, len(chunks))
                failure = next((f for f in result.get("failures", []) if f.get("code") == "llm_call_failure"), None)
                code = failure.get("error_code") if failure and failure.get("retryable") is False else None
                if code and code == streak_code:
                    streak += 1
                elif code:
                    streak_code, streak = code, 1
                else:
                    streak_code, streak = None, 0
                if fail_fast and code and streak >= fail_fast_threshold:
                    stopped_reason = f"non-retryable error repeated {streak} times (code={code})"
            while stopped_reason is None and next_index < len(chunks) and len(active) < workers:
                active[pool.submit(execute, chunks[next_index])] = next_index
                next_index += 1
                started += 1
    if stopped_reason:
        print(f"fail-fast: {stopped_reason}; started={started}, unstarted={len(chunks)-started}", file=sys.stderr, flush=True)
    return ChunkResults(results, stopped_reason=stopped_reason, started=started)


def stderr_progress(done: int, total: int) -> None:
    print(f"{done}/{total}", file=sys.stderr, flush=True)
