"""OpenAI adapter for the team's chatbot; importing this module never calls an API."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import types

MODEL = "gpt-6-luna"
INPUT_USD_PER_MILLION = 0.10
OUTPUT_USD_PER_MILLION = 0.50
_ORIGINALS = None
_USAGE = {"prompt_tokens": 0, "completion_tokens": 0}
_API_CALLS = 0
_MAX_COST_USD = 0.10
_SLEEP = 0.3
_LOCK = threading.Lock()
# gpt-6-luna 는 추론 토큰이 max_completion_tokens 를 함께 쓰는 것으로 보인다(추정): 팀 코드의 기본 400 이면
# 생각만 하다 출력이 비어 이름 선택이 실패한다. 최소 예산을 두어 완화한다(비용 영향은 호출당 약 $0.001).
MIN_COMPLETION_TOKENS = 2000
_MIN_COMPLETION = MIN_COMPLETION_TOKENS


class CostLimitExceeded(BaseException):
    """Raised after recording usage that takes cumulative spend over the limit."""


def _cost(prompt_tokens: int, completion_tokens: int) -> float:
    return prompt_tokens * INPUT_USD_PER_MILLION / 1_000_000 + completion_tokens * OUTPUT_USD_PER_MILLION / 1_000_000


def usage_totals() -> dict:
    with _LOCK:
        prompt = _USAGE["prompt_tokens"]
        completion = _USAGE["completion_tokens"]
    return {"prompt_tokens": prompt, "completion_tokens": completion, "cost_usd": _cost(prompt, completion)}


def reset_usage() -> None:
    global _API_CALLS
    with _LOCK:
        _USAGE.update(prompt_tokens=0, completion_tokens=0)
        _API_CALLS = 0


def _record(response) -> None:
    usage = getattr(response, "usage", None)
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    with _LOCK:
        _USAGE["prompt_tokens"] += prompt
        _USAGE["completion_tokens"] += completion
        total = _cost(_USAGE["prompt_tokens"], _USAGE["completion_tokens"])
        limit = _MAX_COST_USD
    if total > limit:
        raise CostLimitExceeded("누적 OpenAI 비용 상한을 초과했습니다.")


_LABEL_SUFFIX = re.compile(r"\((?:Issuer|Card|Benefit|Condition|Limit|Target|Evidence|Document)\)\s*$")


def normalize_entities(text: str) -> str:
    """이름 선택 응답의 entities 항목 끝에 붙은 '(라벨)'을 뗀다.

    후보 목록이 '이름(라벨)' 형식이라 gpt-6-luna 가 그대로 따라 쓰는데, 팀 rag.analyze 는 라벨 없는 이름과
    정확히 일치해야 인정한다. 이름 속 괄호는 라벨 단어가 정확히 일치할 때만 뗀다. 그 밖의 응답은 그대로 둔다.
    """
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return text
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return text
    entities = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(entities, list):
        return text
    data["entities"] = [_LABEL_SUFFIX.sub("", e).strip() if isinstance(e, str) else e for e in entities]
    return json.dumps(data, ensure_ascii=False)


def _log_call(kind: str, response, requested: int) -> None:
    """FP_LLM_CALL_LOG(/tmp 아래 경로)가 설정된 때만 호출별 진단 기록(키·프롬프트 미포함)을 남긴다."""
    path = os.environ.get("FP_LLM_CALL_LOG")
    if not path:
        return
    from pathlib import Path
    target = Path(path).expanduser().resolve()
    if Path("/tmp").resolve() not in target.parents:
        return
    usage = getattr(response, "usage", None)
    details = getattr(usage, "completion_tokens_details", None)
    choice = response.choices[0]
    content = getattr(choice.message, "content", None) or ""
    record = {"kind": kind, "requested_max": requested, "finish_reason": getattr(choice, "finish_reason", None),
              "completion_tokens": getattr(usage, "completion_tokens", None),
              "reasoning_tokens": getattr(details, "reasoning_tokens", None),
              "content_len": len(content), "content_head": content[:400]}
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _before_call() -> None:
    global _API_CALLS
    totals = usage_totals()
    if totals["cost_usd"] > _MAX_COST_USD:
        raise CostLimitExceeded("누적 OpenAI 비용 상한에 도달했습니다.")
    with _LOCK:
        previous_calls = _API_CALLS
        _API_CALLS += 1
    if previous_calls and _SLEEP:
        time.sleep(_SLEEP)


def install(model: str | None = None, client=None, *, max_cost_usd: float = 0.10, sleep: float = 0.3,
            min_completion_tokens: int = MIN_COMPLETION_TOKENS):
    """Inject an OpenAI-backed ``llm`` module before rag imports team's Anthropic llm.py."""
    global _ORIGINALS, _MAX_COST_USD, _SLEEP
    if max_cost_usd < 0 or sleep < 0:
        raise ValueError("max_cost_usd and sleep must be non-negative")
    selected = model or MODEL
    if client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY environment variable is required")
        from openai import OpenAI
        client = OpenAI(api_key=key)
    existing = sys.modules.get("llm")
    if existing is not None and not hasattr(existing, "__dict__"):
        raise TypeError("llm module replacement target is invalid")
    if existing is not None and _ORIGINALS is None:
        _ORIGINALS = (getattr(existing, "complete", None), getattr(existing, "stream", None))
    llm = existing if existing is not None else types.ModuleType("llm")
    _MAX_COST_USD, _SLEEP = float(max_cost_usd), float(sleep)
    global _MIN_COMPLETION
    _MIN_COMPLETION = int(min_completion_tokens)

    def complete(system: str, user: str, max_tokens: int = 400) -> str:
        _before_call()
        budget = max(int(max_tokens), _MIN_COMPLETION)
        response = client.chat.completions.create(
            model=selected,
            max_completion_tokens=budget,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        _record(response)
        _log_call("complete", response, budget)
        return normalize_entities(response.choices[0].message.content or "")

    def stream(system: str, messages: list[dict], max_tokens: int = 800):
        _before_call()
        max_tokens = max(int(max_tokens), _MIN_COMPLETION)
        request = {"model": selected, "max_completion_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system}, *messages], "stream": True,
                   "stream_options": {"include_usage": True}}
        chunks = []
        try:
            response = client.chat.completions.create(**request)
            for event in response:
                usage = getattr(event, "usage", None)
                if usage is not None:
                    _record(types.SimpleNamespace(usage=usage))
                choices = getattr(event, "choices", []) or []
                if choices:
                    delta = getattr(choices[0].delta, "content", None)
                    if delta:
                        chunks.append(delta)
            if chunks:
                yield from chunks
            return
        except CostLimitExceeded:
            raise
        except Exception:
            # Some compatible endpoints reject stream_options. Retry once without streaming.
            fallback = {"model": selected, "max_completion_tokens": max_tokens,
                        "messages": request["messages"]}
            response = client.chat.completions.create(**fallback)
            _record(response)
            text = response.choices[0].message.content or ""
            if text:
                yield text

    llm.complete = complete
    llm.stream = stream
    sys.modules["llm"] = llm
    return llm


apply = install


def estimate(questions=60, input_tokens=1200, output_tokens=400):
    calls = questions * 2
    inp, out = calls * input_tokens, calls * output_tokens
    return {"label": "estimate", "questions": questions, "calls": calls,
            "input_tokens": inp, "output_tokens": out,
            "estimated_cost_usd": _cost(inp, out)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--questions", type=int, default=60)
    parser.add_argument("--input-tokens-per-call", type=int, default=1200)
    parser.add_argument("--output-tokens-per-call", type=int, default=400)
    parser.add_argument("--max-cost-usd", type=float, default=0.10)
    parser.add_argument("--sleep", type=float, default=0.3)
    args = parser.parse_args(argv)
    if not args.estimate:
        parser.error("use --estimate; install() is called by the harness")
    print(json.dumps(estimate(args.questions, args.input_tokens_per_call, args.output_tokens_per_call)))


if __name__ == "__main__":
    main()
