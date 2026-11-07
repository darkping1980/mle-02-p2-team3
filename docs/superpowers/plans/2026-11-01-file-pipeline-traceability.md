# File Pipeline Traceability Implementation Plan

> **For agentic workers:** Execute inline in this workspace.

**Goal:** Create a minimal file-based PDF traceability flow for the approved one-document Hana pilot.

**Architecture:** Reuse `common.document_reader` to extract one-based page text. Emit page records and one whole-page chunk per non-empty page to a user-selected JSON file; do not connect to a database or extract benefits.

**Tech Stack:** Python standard library, existing PyMuPDF and pypdf project dependencies.

**Spec:** User work order in conversation, narrowed to the agreed file-pipeline pilot.

## Global Constraints

- Preserve the source ZIP, existing manifests, and user changes.
- Do not access DB credentials or connect to Supabase.
- Do not install dependencies without user approval.
- Preserve page text verbatim; positions are one-based and end-inclusive.
- Do not commit or write generated PDF text unless an explicit output path is supplied.

## Review Focus

- Hash/page expectation mismatch must stop before writing output.
- Empty pages remain recorded but receive no chunk.
- Chunk offsets must slice the corresponding page text exactly.
- Existing output files must not be overwritten by default.
- CLI output must not print extracted source text.

### Task 1: Traceability extractor and JSON output

**Files:**
- Create: `src/card_benefit/payment_card/file_pipeline/__init__.py`
- Create: `src/card_benefit/payment_card/file_pipeline/doc_index/traceability.py`
- Create: `src/card_benefit/payment_card/tests/test_file_pipeline_traceability.py`
- Modify: `src/card_benefit/payment_card/file_pipeline/README.md`

- [ ] Add unit coverage for extraction records, hash/page mismatch, exact chunk spans, and output overwrite protection.
- [ ] Implement a small CLI that calls `DocumentReader`, validates optional expected hash/page count, and writes JSON only to an explicit path.
- [ ] Run focused tests and inspect the final diff.

### Task 2: Hana pilot execution

**Files:**
- Input: the approved Hana PDF extracted temporarily from the existing source ZIP.
- Output: JSON at an explicit caller-selected path.

- [ ] Execute only after the user's preconditions are met, PDF dependencies are available without unapproved installation, and the judgment rules are approved.
- [ ] Record whether the PDF extraction and page-to-chunk checks pass; do not connect to Supabase.
