"""Create page-level traceability JSON from indexed image PDFs using Tesseract."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

TESSERACT_EXECUTABLE = "tesseract"
OCR_LANGUAGE = "kor+eng"
OCR_PSM = 6
OCR_DPI = 300
LOW_CONFIDENCE_THRESHOLD = 70.0
MIN_WORDS_PER_PAGE = 3
REPO_ROOT = Path(__file__).resolve().parents[5]
NUMBER_PATTERN = re.compile(r"(?<![\w])\d[\d,]*(?:\.\d+)?\s*(?:천원|만원|억원|원|%|회|개월|일|주|년|시간|분)(?!\w)")


def parse_tsv(tsv: str) -> list[dict]:
    # tesseract TSV 는 따옴표 규칙이 없다. 기본 quotechar 를 쓰면 인식된 '"' 글자 뒤의 행들이 한 칸으로 합쳐져 쪽 텍스트가 부풀고 좌표가 숫자로 섞인다.
    rows = csv.DictReader(tsv.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE)
    words = []
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row.get("conf", "-1"))
        except (TypeError, ValueError):
            confidence = -1.0
        if confidence >= 0:
            words.append({"text": text, "confidence": confidence})
    return words


def page_statistics(text: str, words: list[dict]) -> dict:
    return {
        "word_count": len(words),
        "char_count": len(text),
        "hangul_count": sum("가" <= char <= "힣" for char in text),
        "digit_count": sum(char.isdigit() for char in text),
        "mean_confidence": round(sum(w["confidence"] for w in words) / len(words), 2) if words else None,
        "low_confidence_ratio": round(sum(w["confidence"] < LOW_CONFIDENCE_THRESHOLD for w in words) / len(words), 4) if words else 0.0,
    }


def build_page_result(page_no: int, text: str, words: list[dict]) -> dict:
    stats = page_statistics(text, words)
    page_text = text if len(words) >= MIN_WORDS_PER_PAGE else ""
    quality = {
        "page_no": page_no,
        "extractor": "Tesseract",
        "extractor_ver": None,
        "char_count": stats["char_count"],
        "hangul_count": stats["hangul_count"],
        "digit_count": stats["digit_count"],
        "suspect_count": 0,
        "has_visual": True,
        "status": "OCR_REVIEW",
        **stats,
    }
    return {
        "page_no": page_no,
        "text": page_text,
        "text_sha256": hashlib.sha256(page_text.encode("utf-8")).hexdigest(),
        "quality": quality,
        "chunk_status": "NO_TEXT" if not page_text.strip() else "HAS_CHUNK",
        "excluded_reason": "OCR 단어가 3개 미만입니다." if not page_text.strip() else None,
    }


def run_tesseract(image: bytes, lang: str = OCR_LANGUAGE, psm: int = OCR_PSM,
                  executable: str = TESSERACT_EXECUTABLE) -> str:
    if not shutil.which(executable):
        raise FileNotFoundError(f"Tesseract 실행 파일을 찾지 못했습니다: {executable}. Tesseract와 {lang} 언어 데이터를 설치하세요.")
    result = subprocess.run(
        [executable, "stdin", "stdout", "-l", lang, "--psm", str(psm), "tsv"],
        input=image, capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or "Tesseract 실행 실패")
    return result.stdout.decode("utf-8-sig", "replace")


def create_ocr_trace(pdf_path: str | Path, expected_sha256: str | None = None,
                     dpi: int = OCR_DPI, lang: str = OCR_LANGUAGE, psm: int = OCR_PSM,
                     run_tesseract=None) -> dict:
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("입력 파일은 PDF여야 합니다.")
    pdf_bytes = pdf_path.read_bytes()
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError(f"SHA-256이 다릅니다: {digest}")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("올바른 PDF 파일이 아닙니다.")
    ocr_fn = run_tesseract or globals()["run_tesseract"]
    pages, sidecar_pages = [], []
    with pymupdf.open(pdf_path) as document:
        for page_no, page in enumerate(document, 1):
            image = page.get_pixmap(dpi=dpi).tobytes("png")
            tsv = ocr_fn(image, lang, psm, TESSERACT_EXECUTABLE)
            words = parse_tsv(tsv)
            text = "\n".join(" ".join(w["text"] for w in words).splitlines())
            result = build_page_result(page_no, text, words)
            result["quality"]["extractor_ver"] = _tesseract_version()
            pages.append(result)
            sidecar_pages.append({"page_no": page_no, **page_statistics(text, words), "words": words})
    trace = {
        "schema_version": "traceability-v1",
        "document": {"filename": pdf_path.name, "size_bytes": len(pdf_bytes), "sha256": digest, "page_count": len(pages)},
        "pages": pages,
        "chunks": [{"chunk_id": f"p{p['page_no']:04d}", "page_no": p["page_no"], "start_pos": 1,
                    "end_pos": len(p["text"]), "text": p["text"]} for p in pages if p["text"].strip()],
    }
    trace["_ocr_sidecar"] = {"document": {"engine": "tesseract", "version": _tesseract_version(),
                      "lang": lang, "psm": psm, "dpi": dpi,
                      "generated_at": datetime.now(timezone.utc).isoformat()}, "pages": sidecar_pages}
    return trace


def _tesseract_version() -> str | None:
    if not shutil.which(TESSERACT_EXECUTABLE):
        return None
    result = subprocess.run([TESSERACT_EXECUTABLE, "--version"], capture_output=True, check=False, text=True)
    return result.stdout.splitlines()[0].removeprefix("tesseract ") if result.stdout else None


def ensure_external_output(output_dir: str | Path) -> Path:
    output = Path(output_dir).expanduser().resolve()
    repo = REPO_ROOT.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("출력 폴더는 저장소 안에 둘 수 없습니다.")
    return output


def read_index(index_csv: str | Path) -> list[dict]:
    with Path(index_csv).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def run_index(index_csv: str | Path, doc_ids: list[str] | None, output_dir: str | Path,
              data_root: str | Path = "src/data", execute: bool = False, all_ocr: bool = False,
              dpi: int = OCR_DPI, lang: str = OCR_LANGUAGE, psm: int = OCR_PSM,
              run_tesseract=None, report_csv: str | Path | None = None) -> dict:
    output = ensure_external_output(output_dir)
    rows = read_index(index_csv)
    if all_ocr:
        targets = [r for r in rows if r.get("canonical") == "Y" and r.get("ocr_needed") == "Y"]
    elif doc_ids:
        wanted = set(doc_ids)
        targets = [r for r in rows if r.get("doc_id") in wanted]
        found = {r.get("doc_id") for r in targets}
        if wanted - found:
            raise ValueError(f"인덱스에 없는 doc_id: {', '.join(sorted(wanted - found))}")
    else:
        raise ValueError("doc_id 목록 또는 --all-ocr가 필요합니다.")
    planned = [{"doc_id": r["doc_id"], "pages": int(r.get("pages") or 0)} for r in targets]
    if not execute:
        return {"planned": planned, "done": [], "failed": []}
    output.mkdir(parents=True, exist_ok=True)
    done, failed, all_tokens = [], [], []
    for row in targets:
        pdf_path = Path(data_root) / row["file_path"]
        try:
            trace = create_ocr_trace(pdf_path, row.get("sha256"), dpi, lang, psm, run_tesseract)
            sidecar = trace.pop("_ocr_sidecar")
            (output / f'{row["doc_id"]}.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (output / f'{row["doc_id"]}.ocr.json').write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            for page in sidecar["pages"]:
                all_tokens.extend(extract_numeric_tokens(trace["pages"][page["page_no"] - 1]["text"], page["words"], row["doc_id"], page["page_no"]))
            done.append({"doc_id": row["doc_id"], "pages": trace["document"]["page_count"],
                         "stats": [{k: p[k] for k in ("word_count", "char_count", "hangul_count", "digit_count", "mean_confidence", "low_confidence_ratio")} for p in sidecar["pages"]]})
        except (FileNotFoundError, OSError, ValueError, RuntimeError) as error:
            failed.append({"doc_id": row.get("doc_id"), "error": str(error)})
    if report_csv:
        write_numeric_report(all_tokens, report_csv)
    return {"planned": planned, "done": done, "failed": failed}


def extract_numeric_tokens(text: str, words: list[dict], doc_id: str, page_no: int) -> list[dict]:
    records = []
    for match in NUMBER_PATTERN.finditer(text):
        token = match.group().strip()
        matching = [word for word in words if token in word["text"] or word["text"] in token]
        confidence = min((w["confidence"] for w in matching), default=None)
        records.append({"doc_id": doc_id, "page_no": page_no, "token": token,
                        "confidence": confidence, "context": text[max(0, match.start()-10):min(len(text), match.end()+10)]})
    return records


def write_numeric_report(records: list[dict], path: str | Path, low_n: int = 20) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["doc_id", "page_no", "token", "confidence", "context", "low_confidence_rank"]
    low = {id(row): rank for rank, row in enumerate(sorted(records, key=lambda r: (r["confidence"] is not None, r["confidence"] if r["confidence"] is not None else -1))[:low_n], 1)}
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({**row, "low_confidence_rank": low.get(id(row), "")})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", required=True, type=Path, help="documents.csv")
    parser.add_argument("--doc-id", action="append", help="대상 문서 id (반복 가능)")
    parser.add_argument("--all-ocr", action="store_true", help="canonical=Y, ocr_needed=Y 전체 대상")
    parser.add_argument("--data-root", type=Path, default=Path("src/data"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dpi", type=int, default=OCR_DPI)
    parser.add_argument("--lang", default=OCR_LANGUAGE)
    parser.add_argument("--psm", type=int, default=OCR_PSM)
    parser.add_argument("--report-csv", type=Path)
    parser.add_argument("--execute", action="store_true", help="OCR 및 결과 저장")
    args = parser.parse_args()
    try:
        result = run_index(args.documents, args.doc_id, args.output_dir, args.data_root, args.execute,
                           args.all_ocr, args.dpi, args.lang, args.psm, report_csv=args.report_csv)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
