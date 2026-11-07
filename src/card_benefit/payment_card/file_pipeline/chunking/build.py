"""traceability JSON의 쪽 원문을 청크로 자르고, 이어 붙이면 원문과 같은지 검증한다."""

from __future__ import annotations

from .split import split_page, SPLIT_OVER


def check_pieces(page_text: str, spans: list[tuple[int, int]]) -> None:
    """조각을 이어 붙이면 쪽 원문과 한 글자도 다르지 않아야 한다. 글자 없는 쪽은 조각이 없어야 한다."""
    if not page_text.strip():
        if spans:
            raise ValueError("글자 없는 쪽에 청크가 만들어졌습니다.")
        return
    if "".join(page_text[s:e] for s, e in spans) != page_text:
        raise ValueError("청크를 이어 붙인 글이 쪽 원문과 다릅니다.")


def build_page_chunks(doc_id: str, page_no: int, page_text: str, headings: list[tuple[int, str]]) -> list[dict]:
    """쪽 하나를 청크 목록으로 만든다. start_pos, end_pos는 쪽 원문 기준 1부터이고 끝 글자를 포함한다."""
    heading_by_offset = dict(headings)
    spans = split_page(page_text, list(heading_by_offset))
    check_pieces(page_text, spans)
    chunks = []
    for number, (start, end) in enumerate(spans, start=1):
        chunks.append({
            "chunk_id": f"{doc_id}-p{page_no:04d}-c{number:02d}",
            "page_no": page_no,
            "start_pos": start + 1,
            "end_pos": end,
            "heading": heading_by_offset.get(start),
            "text": page_text[start:end],
        })
    return chunks


def build_doc_chunks(row: dict, trace: dict, products: list[dict], find_headings) -> dict:
    """문서 한 개의 청크 JSON을 만든다.

    row는 documents.csv의 한 행, trace는 traceability JSON, products는 이 문서를 쓰는 상품 목록이다.
    find_headings(page_no, page_text)는 제목의 (위치, 글) 목록을 돌려주는 함수다. 4000자 이하 쪽에서는 부르지 않는다.
    """
    if trace["document"]["sha256"] != row["sha256"]:
        raise ValueError("traceability JSON의 해시가 인덱스와 다릅니다.")
    chunks = []
    for page in trace["pages"]:
        text = page["text"]
        long_page = len(text.strip()) > SPLIT_OVER
        headings = find_headings(page["page_no"], text) if long_page else []
        chunks.extend(build_page_chunks(row["doc_id"], page["page_no"], text, headings))
    ids = [c["chunk_id"] for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("청크 id가 겹칩니다.")
    return {
        "schema_version": "chunks-v1",
        "doc_id": row["doc_id"],
        "doc_sha256": row["sha256"],
        "file_path": row["file_path"],
        "products": products,
        "chunks": chunks,
    }
