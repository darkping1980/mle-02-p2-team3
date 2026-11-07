"""청크 한 개의 LLM 추출과 인용문 위치 변환을 수행한다."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from .evidence import locate_quote
from .prompt import build_prompt
from .schema import Extraction

LLMCall = Callable[[str], str]


def run_chunk(chunk: dict, doc_sha256: str, llm_call: LLMCall) -> dict[str, Any]:
    """청크 하나를 처리하고 추출 내용 및 구조화된 실패를 반환한다."""
    result: dict[str, Any] = {
        "doc_sha256": doc_sha256,
        "page_no": chunk["page_no"],
        "chunk_id": chunk.get("chunk_id"),
        "chunk_length": len(chunk["text"]),
        "extraction": None,
        "failures": [],
        "notes": [],
    }
    response = llm_call(build_prompt(chunk))
    if isinstance(response, str):
        fenced = re.fullmatch(r"\s*```json\s*\n(.*?)\n```\s*", response, flags=re.DOTALL)
        if fenced is not None:
            response = fenced.group(1)
            result["notes"].append("JSON 응답의 코드 펜스를 벗기고 파싱했습니다.")
    try:
        data = json.loads(response)
    except (TypeError, json.JSONDecodeError) as error:
        result["failures"].append(_failure("json_parse_failure", str(error)))
        return result

    try:
        extraction = Extraction.model_validate(data)
    except (ValidationError, TypeError, ValueError) as error:
        result["failures"].append(_failure("schema_validation_failure", str(error)))
        return result

    result["extraction"] = extraction.model_dump(mode="json")
    if not any((extraction.benefits, extraction.conditions, extraction.limits,
                extraction.targets, extraction.relations)):
        result["failures"].append(_failure("empty_result", "추출 항목이 없습니다."))

    for group_name in ("benefits", "conditions", "limits", "targets", "relations"):
        for item_index, item in enumerate(result["extraction"][group_name]):
            for quote_index, quote in enumerate(item["evidence"]):
                path = f"{group_name}[{item_index}].evidence[{quote_index}]"
                try:
                    located = locate_quote(chunk["text"], chunk["start_pos"], quote["text"])
                except ValueError as error:
                    located = None
                    result["failures"].append(_failure("quote_location_failure", str(error), path, quote["text"]))
                if located is None:
                    quote["location"] = None
                    if not any(f["code"] == "quote_location_failure" and f.get("path") == path
                               for f in result["failures"]):
                        result["failures"].append(_failure("quote_location_failure", "인용문을 원문에서 찾지 못했습니다.", path, quote["text"]))
                elif located.occurrences > 1:
                    quote["location"] = None
                    result["failures"].append(_failure(
                        "quote_location_ambiguous", "인용문이 청크에서 여러 번 나타납니다.",
                        path, quote["text"], occurrences=located.occurrences,
                    ))
                else:
                    quote["location"] = {
                        "doc_sha256": doc_sha256,
                        "page_no": chunk["page_no"],
                        "start_pos": located.start_pos,
                        "end_pos": located.end_pos,
                    }
    return result


def _failure(code: str, message: str, path: str | None = None,
             quote: str | None = None, **details: Any) -> dict[str, Any]:
    failure: dict[str, Any] = {"code": code, "message": message}
    if path is not None:
        failure["path"] = path
    if quote is not None:
        failure["quote"] = quote
    failure.update(details)
    return failure
