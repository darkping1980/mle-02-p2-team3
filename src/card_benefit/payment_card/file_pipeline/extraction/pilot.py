"""오프라인 시범 청크 선정과 프롬프트 크기 추정을 제공한다."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import random
import re
from typing import Any


RULE_KEYWORDS = ("택1", "제외", "통합 한도")


def select_pilot_chunks(index_csv: Path | str, chunk_dir: Path | str, count: int = 10,
                        seed: int = 17) -> list[str]:
    """하나카드 텍스트 PDF 대표 문서에서 길이·문서가 분산된 청크 id를 고른다.

    표와 규칙 키워드 집계는 문자 패턴 기반의 거친 선정용 신호이며 실제 의미 판정이 아니다.
    길이 구간은 짧음(<1000자), 중간(1000~4000자), 긴 청크(>4000자)다.
    """
    if count < 0:
        raise ValueError("count는 0 이상이어야 합니다.")
    with Path(index_csv).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    docs = {row["doc_id"]: row for row in rows
            if row.get("issuer") == "hana" and row.get("canonical") == "Y"
            and row.get("doc_role") == "product_guide" and row.get("ocr_needed") != "Y"
            and row.get("card_type") != "common"}

    candidates: list[dict[str, Any]] = []
    for doc_id, row in docs.items():
        path = Path(chunk_dir) / f"{doc_id}.chunks.json"
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for chunk in document.get("chunks", []):
            text = chunk.get("text", "")
            length = len(text)
            size_bin = "short" if length < 1000 else "medium" if length <= 4000 else "long"
            candidates.append({
                "id": chunk["chunk_id"], "doc_id": doc_id, "bin": size_bin,
                "table": bool(re.search(r"\|.{0,80}\|", text) or re.search(r"\s{2,}\S+\s{2,}\S+", text)),
                "rule": any(word in text for word in RULE_KEYWORDS),
            })
    if count == 0 or not candidates:
        return []

    rng = random.Random(seed)
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in ("short", "medium", "long")}
    for item in candidates:
        groups[item["bin"]].append(item)
    for group in groups.values():
        rng.shuffle(group)

    # 구간을 순환하고 이미 뽑은 문서는 우선 피해서 문서와 길이 분포를 분산한다.
    chosen: list[dict[str, Any]] = []
    remaining = candidates.copy()
    while remaining and len(chosen) < count:
        progressed = False
        for key in ("short", "medium", "long"):
            options = [item for item in groups[key] if item in remaining]
            if not options:
                continue
            docs_used = {item["doc_id"] for item in chosen}
            distinct = [item for item in options if item["doc_id"] not in docs_used]
            pick = rng.choice(distinct or options)
            chosen.append(pick)
            remaining.remove(pick)
            progressed = True
            if len(chosen) >= count:
                break
        if not progressed:
            break

    # 표/규칙 신호가 있다면 표본의 일부 슬롯에 한 건씩 반영한다.
    for predicate in ("table", "rule"):
        if len(chosen) >= count or any(item[predicate] for item in chosen):
            continue
        options = [item for item in candidates if item[predicate] and item not in chosen]
        if options:
            replacement = rng.choice(options)
            chosen[-1] = replacement
    return [item["id"] for item in chosen]


def estimate_prompt_size(chunk_ids: list[str], chunk_dir: Path | str) -> dict[str, int]:
    """선정 청크의 실제 프롬프트 문자 수와 문자 수/2 토큰 추정치를 합산한다.

    토큰 수는 tokenizer를 쓰지 않은 거친 근사치이며 과금 예측값으로 보장되지 않는다.
    """
    from .prompt import build_prompt

    wanted = set(chunk_ids)
    total_chars = total_chunks = 0
    for path in sorted(Path(chunk_dir).glob("*.chunks.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for chunk in document.get("chunks", []):
            if chunk.get("chunk_id") in wanted:
                total_chars += len(build_prompt(chunk))
                total_chunks += 1
    return {"chunks": total_chunks, "prompt_characters": total_chars,
            "estimated_tokens": (total_chars + 1) // 2}
