# 11단계 file_pipeline 장부 적재 드라이런

- PC: laptop
- 날짜: 2026-11-05
- 상태: 커밋 전

## 목적과 범위

Supabase 참고 명세 `file_pipeline`의 문서 사실 계층을 대상으로 DB 접속 없이 계획·SQL 생성·검증 도구를 만들었다. SQL은 `/tmp`에만 생성했다. 실제 DB 실행, 추출 대기실(`card_extr_stg`)과 확정 테이블 적재는 하지 않았다.

## 매핑 요약

| 입력 | 장부 | 규칙 |
|---|---|---|
| `documents.csv`의 `canonical=Y` 대표 문서 | `card_doc` | 해시·제목(인덱스에 제목 열이 없어 파일명 stem 사용)·파일명·출처 URL·쪽 수. 문서 유형은 role 코드 대응, 수집 시각/생성·수정 사용자 인자 필요 |
| `traceability` 페이지 JSON | `card_doc_page` | `text`의 UTF-8 SHA-256·문자 수, `quality`의 추출기명/버전. `has_visual`과 텍스트 유무로 `TEXT/IMAGE/MIXED/UNKNOWN` 판정 |
| `.chunks.json` | `card_doc_chunk` | 페이지별 순번·제목·원문, `start_pos/end_pos`는 1-based 끝 포함 |
| 추출 runner 결과 | `card_ai_run`, `card_ai_call` | 미구현. run 단계/호출 방식/모델/프롬프트 버전·전문/파라미터/상태/시각과 chunk별 호출 입력 해시·응답·토큰·지연시간 필요 |
| 추출 결과와 인용 근거 | `card_extr_stg`, `card_source_evidence` | 다음 단계. 추출 결과는 승인 전 `PENDING_REVIEW` staging으로만 다룬다. 그래프 `quote_status`에 직접 대응하는 전용 열이 없어 매핑 합의가 필요하다 |

코드값 허용 집합은 `db_pipeline_common_code_seedV6.sql`의 `SEED_TEST` 코드에서 가져왔다. `product_guide→PRODUCT_GUIDE`, `terms→TERMS`, `brand_service→BRAND_SERVICE`, `web_capture→ETC`로 매핑한다. 페이지 레이어는 시드의 네 값, 청크 유형·상태는 `BODY`·`RAW`, 문서 상태는 `ACTIVE`를 쓴다. `doc_version_no=1`은 V6 DDL 기본값 근거다. 코드와 DDL의 `SEED_TEST` 표시는 시험용일 수 있어 확정 여부는 사용자 결정 사항이다.

기본 ID는 SHA-256 기반 결정적 ID(`D`/`C` 접두사와 16 hex), 문서 코드는 `DOC-`와 16 hex다. 대안 `--id-scheme source`는 입력 `doc_id`/`chunk_id`를 이용한다. 사용자 결정값을 임의로 넣지 않도록 `--create-user-id`는 필수이며, CSV에 수집 시각 열이 없으므로 `--collected-at`도 필수다. ID 정책과 파일명 stem을 제목으로 쓸지 확정해야 한다.

## 드라이런

입력은 인덱스 CSV, `~/pilot_work/trace/{hana,woori}` 및 청크 디렉터리의 로컬 JSON이었다. OCR 필요 대표 문서는 기본 제외했다.

| 카드사 | 대표 문서 | OCR 필요 제외 | 쪽 | 청크 | 위반 후보 | 예상 입력 크기 |
|---|---:|---:|---:|---:|---:|---:|
| 하나 | 98 | 2 | 383 | 543 | 9 | 4,275,444 bytes |
| 우리 | 118 | 45 | 456 | 489 | 21 | 4,883,366 bytes |

위반 후보는 누락된 페이지/청크 JSON과 쪽 수 불일치가 포함된다. 하나는 페이지 JSON/청크 JSON 누락 3문서, 우리는 7문서가 확인되었다(각각 문서 ID 해시 앞 8자로만 출력). 따라서 생성된 SQL은 검토용일 뿐이며 누락 문서의 페이지 사실 데이터가 완전하지 않다. 추정 용량은 직렬화된 계획 데이터 기준이며 SQL 파일의 실제 크기와 다르다.

생성 결과(실제 문장 내용은 보고에서 제외): `/tmp/ledger-hana.sql` 3,909,261 bytes(INSERT 1,024개, 전체 SQL 문장 1,030개), `/tmp/ledger-woori.sql` 4,466,215 bytes(INSERT 1,063개, 전체 SQL 문장 1,069개), `/tmp/ledger-schema-check.sql` 835 bytes. 문서→쪽→청크 순서, 문서 단위 INSERT, `ON CONFLICT DO NOTHING`, 하나의 트랜잭션, 대상 해시로 한정한 검증 SELECT와 역순 DELETE를 출력한다. 쪽·청크 본문은 달러 인용 태그 충돌 회피로 이스케이프하며 단일 INSERT 1,000,000 bytes 제한을 둔다. PostgreSQL에서 실행하지 않았다.

## 검증과 한계

- 합성 데이터 테스트와 지정 추출·그래프·노트북 커버리지 테스트: 223 passed.
- 코드 시드 열거는 V6 `SEED_TEST` 행을 기준으로 하며 운영 코드라는 팀 확인이 없다.
- DB의 실제 스키마/제약과 SQL 호환성은 읽기 전용 확인 SQL을 사용자가 SQL Editor에서 실행해 결과를 돌려줘야 검증할 수 있다. 스키마 확인 SQL은 컬럼 메타데이터, 제약, 코드 그룹/코드표 행 수를 조회한다.
- `card_doc.doc_file_size`는 인덱스 입력에 없어서 NULL로 둔다. 문서 제목도 인덱스에 없어 파일명 stem으로 둔다. 사용자가 정한 수집 일시와 생성·수정 사용자 ID 값이 실제 SQL에 들어가야 한다.
- `card_ai_run/card_ai_call`의 필요한 입력 계약이 부족해 구현하지 않았다. 실제 결과를 staging에 넣을 때 실행/호출 관계와 근거 `quote_status` 처리부터 합의해야 한다.
- 저장소 출력 경로, DB 접속·환경 키 사용은 코드에서 차단/사용하지 않으며, `.env`는 읽지 않았다.

## 다음 단계

1. ID 발급 규칙, `create_user_id`, 수집 일시, `SEED_TEST` 코드의 운영 사용 여부, 제목/파일 크기 매핑을 확정한다.
2. 누락된 로컬 trace/chunk JSON을 확인하고 계획기 재실행으로 위반 후보를 0으로 만든다.
3. 사용자가 스키마 확인 SQL을 실행해 컬럼/제약/코드표를 로컬 DDL과 대조한다.
4. 별도 승인 뒤에만 추출 결과를 승인 대기(`card_extr_stg`)에 적재하고, `quote_status` 대응안을 정한다. 확정 테이블은 별도 승인이 있기 전까지 대상이 아니다.
5. 작업 검토 후 사용자가 커밋한다.

## 재현 명령

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.ledger.plan --issuer hana --index src/card_benefit/data/index --trace-dir ~/pilot_work/trace/hana --chunk-dir ~/pilot_work/chunks/hana --create-user-id <사용자ID> --collected-at <ISO-8601> --sql-out /tmp/ledger-hana.sql --schema-sql-out /tmp/ledger-schema-check.sql
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.ledger.plan --issuer woori --index src/card_benefit/data/index --trace-dir ~/pilot_work/trace/woori/woori --chunk-dir ~/pilot_work/chunks/woori/woori --create-user-id <사용자ID> --collected-at <ISO-8601> --sql-out /tmp/ledger-woori.sql
```
