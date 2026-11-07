"""공통 인덱스의 열 이름과 허용 값."""

DOCUMENT_COLUMNS = [
    "issuer", "doc_id", "sha256", "file_path", "card_type", "doc_role",
    "canonical", "duplicate_of", "pages", "text_chars", "ocr_needed",
    "source_url", "origin", "board_date", "needs_review", "review_reason",
]
PRODUCT_DOC_COLUMNS = [
    "issuer", "product_name", "product_ids", "card_type", "doc_id",
    "file_path", "relation",
]

DOC_ROLES = {"product_guide", "web_capture", "brand_service", "terms", "other", "unclassified"}
ORIGINS = {"official_download", "official_url_inferred", "web_capture", "existing_unverified"}
# 대표 파일을 고를 때 앞설수록 우선한다.
ORIGIN_RANK = {
    "official_download": 0,
    "official_url_inferred": 1,
    "web_capture": 2,
    "existing_unverified": 3,
}
# 쪽당 평균 추출 글자 수가 이 값보다 작으면 OCR이 필요하다고 표시한다.
OCR_MIN_CHARS_PER_PAGE = 50
