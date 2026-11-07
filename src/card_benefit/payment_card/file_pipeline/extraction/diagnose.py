"""빈 추출 결과를 제목·길이·혜택 키워드 수로 분류한다.

키워드 수는 혜택 가능성을 살피는 거친 신호이며, 원문 내용의 판정은 아니다.
PDF 청크 원문은 결과 파일에 쓰지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
BENEFIT_KEYWORDS = ("할인", "적립", "캐시백", "한도", "%", "원", "면제", "무료", "할인율", "포인트")


def diagnose_empty_results(
    results_dir: Path | str, chunk_dir: Path | str, output_dir: Path | str,
) -> dict:
    """빈 결과 청크를 분류하고, 원문 없이 메타데이터 JSON을 저장한다."""
    output = Path(output_dir).expanduser().resolve()
    if output == _REPO_ROOT or _REPO_ROOT in output.parents:
        raise ValueError("출력 폴더는 저장소 밖에 지정해야 합니다.")

    results_by_id = {}
    for result_path in sorted(Path(results_dir).expanduser().glob("*.result.json")):
        data = json.loads(result_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("chunk_id"), str):
            results_by_id[data["chunk_id"]] = data

    classified = []
    for chunk_path in sorted(Path(chunk_dir).expanduser().glob("*.chunks.json")):
        document = json.loads(chunk_path.read_text(encoding="utf-8"))
        for chunk in document.get("chunks", []):
            result = results_by_id.get(chunk.get("chunk_id"))
            if result is None or not any(failure.get("code") == "empty_result"
                                         for failure in result.get("failures", [])):
                continue
            raw_text = chunk.get("text", "")
            if not isinstance(raw_text, str):
                raw_text = ""
            title = next((chunk[key] for key in ("title", "heading")
                          if isinstance(chunk.get(key), str)), None)
            classified.append({
                "chunk_id": chunk.get("chunk_id"),
                "title": title,
                "length": len(raw_text),
                "keyword_counts": {word: raw_text.count(word) for word in BENEFIT_KEYWORDS},
            })

    output.mkdir(parents=True, exist_ok=True)
    destination = output / "empty_result_diagnosis.json"
    destination.write_text(json.dumps(classified, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"count": len(classified), "items": classified, "output": str(destination)}
