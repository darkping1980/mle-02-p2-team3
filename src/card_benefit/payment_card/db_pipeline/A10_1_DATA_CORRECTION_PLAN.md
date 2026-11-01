# A10-1·A10-2 PostgreSQL V6 데이터 보정

기준: 2026-11-01. 대상: `card_id=2`, `policy_ver_id=20261101_000001`. 분석 근거는 `A10_V6_NEO4J_STRUCTURE_ANALYSIS.md`.

**현재 상태:** 근거 037, P1·P2·P3, 조건 근거 8건을 PostgreSQL에 반영했고 Neo4j를 재동기화했다. 두 DB의 차이는 0이다. P4·P5는 보류다. DDL, 공통코드, staging, AI 호출 원본은 변경하지 않았고 유료 LLM도 호출하지 않았다.

아래 A10-3 절이 최신이다. A10-2 절의 "현재 차이"와 "재동기화 절차"는 당시 기준이다. "A10-1 기록" 이후의 P1~P5 내용은 당시 제안이며, P5의 `approved_at` 방식은 철회했다.

# A10-3 실행 결과

## 조건 근거 보완

A10-2 13절에서 제안한 8건을 연결했다. 별도 지시 문서를 받지 못해 이 8건을 승인 범위로 해석했다.

| 연결 ID | 대상 | 조건 | 근거 |
|---|---|---|---:|
| 055 | 대중교통 | `transit_grace` | 049 |
| 056, 057 | 놀이공원 | `amusement_spend` | 054, 048 |
| 058 | 놀이공원 | `amusement_first_month` | 055 |
| 059 | 놀이공원 | `amusement_per_person` | 052 |
| 060 | 정책 | `common_service_exclusion` | 056 |
| 061 | 정책 | `common_channel` | 057 |
| 062 | 정책 | `merchant_classification` | 059 |

연결은 54에서 62건이 됐고, 조건 atom 15개 모두 조건 단위 근거를 갖는다. 기존 연결 54건과 혜택·근거·풀·정책·staging은 해시로 불변을 확인했다. 게이트는 `evidence_not_approved` 31건 그대로다.

백업은 `src/data/backup/a10_3_pre_condition_links_20261101/`(복구 SQL 포함)이다.

## Neo4j 재동기화

| 항목 | 전 | 후 |
|---|---:|---:|
| 노드 | 108 | 108 |
| 관계 | 168 | **189** |
| `A8_SUPPORTED_BY` | 41 | **62** |
| 삭제 | - | 0 |

`neo4j_load_draft --apply`의 `MERGE`로 갱신했다. 이름공간 삭제, DDL, 다른 데이터 변경은 없다. 적재 전 상태는 `src/data/backup/a10_3_pre_neo4j_resync_20261101/`에 JSONL로 있다.

| 재동기화 후 대조 (`neo4j_validate`) | 결과 |
|---|---|
| 노드 키·라벨·`source_json` | 차이 0 |
| 관계 키·유형·끝점·`source_json` | 차이 0 |
| 조건 SQL·Cypher | 15 / 15 일치 |
| 근거 연결 SQL·Cypher | 62 / 62 일치 |
| 고아 노드, 범위 밖 노드·관계 | 0 |
| 근거 037 | `start_pos=2270` |

# A10-2 실행 결과

## 1. 원문 전체 보존 검증

### PostgreSQL

| 검증 | 1쪽 | 2쪽 |
|---|---:|---:|
| 저장 길이 / `page_char_cnt` | 2,482 / 2,482 | 3,181 / 3,181 |
| PDF 재추출 텍스트와 완전 일치 | 예 | 예 |
| `page_txt_sha256` 재계산 일치 | 예 | 예 |
| 청크 수, `chunk_raw_txt`=페이지 원문 | 1, 예 | 1, 예 |
| 청크 범위 | 1~2482 | 1~3181 |

| 문서 검증 | 결과 |
|---|---|
| 파일 SHA-256 | `6ec9641c...c6d2`, `card_doc.doc_sha256`과 일치 |
| 파일 크기·쪽수 | 360,659바이트, 2쪽, 컬럼값과 일치 |
| 문서·페이지·청크 연결 | 정상 |

**판정: PDF 2쪽의 추출 텍스트는 잘림 없이 전문 보존됐다.** PyMuPDF 1.28.2로 재추출한 값과 글자 단위로 같다.

구분할 점:

| 항목 | 저장 여부 |
|---|---|
| 추출 텍스트 | PostgreSQL 저장 |
| PDF 파일 자체 | DB에 없음. 경로·해시·URL만 저장, 파일은 `src/card_benefit/data/raw/hana_all/debit/` |
| 정제 텍스트 | `chunk_clean_txt` 비어 있음, `chunk_status=RAW` |
| 1쪽 이미지 1개(919×1064) | 텍스트 미포함. 렌더링 확인 결과 카드 그림으로 약관성 내용 없음 |
| 상품 약관 전체 | **없음.** 이 문서는 2쪽 상품설명서다. PDF 메타데이터 제목은 "상품약관"이지만 2쪽은 "상품설명서 및 상품 약관을 반드시 확인"이라고 별도 문서로 안내한다 |
| 웹 상품 상세 PDF | 파일만 있고 미적재 |
| 출처 | `doc_note`: "URL 추정으로 찾은 문서. 공식 출처 미확정" |

### Neo4j

| 노드 | 전문 저장 | PostgreSQL 일치 | 검색 속성 |
|---|---|---|---|
| `A8Page` 2 | `source_json.page_raw_txt` | 완전 일치, 해시 일치 | `page_no`만 |
| `A8Chunk` 2 | `source_json.chunk_raw_txt` | 완전 일치 | `page_no`만 |
| `A8Document` 1 | 전문 없음, 메타데이터와 해시 | 일치 | 없음 |
| `A8Evidence` 31 | 인용만, 전문 0건 | 31/31 일치 | 위치·상태 |

**판정: Neo4j는 참조만 하는 것이 아니라 전문을 보유한다.** 다만 텍스트 속성이 아니라 `source_json` 문자열 안에 있다. Page와 Chunk에 같은 전문이 있어 쪽당 2벌이며, PAGE_V1이라 청크가 곧 페이지이기 때문이다. **추가 노드나 속성은 만들지 않았고 권장하지 않는다.** 근거는 `Evidence→Chunk→Page` 경로로 전문까지 닿는다.

## 2. 근거 31건 위치 검증

인용 문자열은 저장 위치와 31/31 일치한다. 문자 위치를 PDF 좌표로 변환해 표 행과 문단을 대조했다.

| 영역 | 근거 | 소유자 | 판정 |
|---|---|---|---|
| 표1 ONE PICK 행 | 032, 033, 036, 037 | ONE PICK, 풀 001~003 | 일치 |
| 표1 STYLE 행 | 039, 042, 043 | STYLE, 풀 004~006 | 일치 |
| 표1 병합 셀 | 034, 035, 040, 041 | ONE PICK, STYLE | 일치 |
| 표1 제목 | 031, 038 | ONE PICK, STYLE | 일치 |
| 표2 대중교통 행 | 044, 045, 046, 047 | 대중교통, 풀 007 | 일치 |
| 표2 놀이공원 행 | 051, 052, 053, 055 | 놀이공원, 풀 008·009 | 일치 |
| 우측 서비스 제외 | 050, 056, 057 | 대중교통, 정책 | 일치 |
| 우측 실적 | 048, 049, 054, 058 | 대중교통, 놀이공원 | 일치 |
| 우측 제공 방법 | 059, 060 | 정책 | 일치 |
| 2쪽 | 061 | 정책 | 일치 |

**다른 표 행을 잘못 참조한 사례는 037 외에 없다.** 위치가 같은 근거 묶음은 병합 셀, 표 제목, 동일 행 중복(044·047)이며 오류가 아니다.

## 3. P1 놀이공원 조건 유형: 반영

**진리표.** 평가 규칙은 branch OR, atom AND, `negate_yn`=NOT이다.

| 실적 20만원 충족 | 최초 발급 월 | 원문 의도 | 변경 전 | 변경 후 |
|---|---|---|---|---|
| 예 | 아님 | 제공 | 제공 | 제공 |
| 예 | 맞음 | 미제공 | 미제공 | 미제공 |
| 아니오 | 아님 | 미제공 | 미제공 | 미제공 |
| 아니오 | 맞음 | 미제공 | 미제공 | 미제공 |

실적 제외 해당 없음, 1인 1매 충족을 전제로 한 표다. atom 4개의 전체 조합 16가지도 변경 전후가 모두 같다.

| 검증 | 결과 |
|---|---|
| 달라진 값 | `cond_type_cd`만 `GRACE`→`BNFT_EXCL` |
| branch, seq, `negate_yn`, `atom_key` | 불변 |
| 근거 참조 | 불변. 조건 키가 같음 |
| 유형별 코드 분기 | 없음. 형식 검사만 있고 `excl_raw_txt`도 있음 |
| GraphRAG | 영향 없음. `atom_key`로 미확정을 찾고 금액 판정은 `SPEND_REQ`만 사용 |

규약: `BNFT_EXCL` 술어는 "제외 대상이다"로 정의하고, `NOT`은 "제외 대상이 아니다"로 읽는다. 기존 `common_service_exclusion`, `transit_exclusions`와 같다. "최초 발급 월"의 기준일은 여전히 미확정이다.

## 4. P2 대중교통 실적 원문: 반영

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| `cond_raw_txt` | `지난달 실적\n대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원` | `- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\n ONE MORE 서비스 제공` |
| 출처 | 표 머리글+행 (2335~2371) | 근거 048 인용 그대로 (435~504) |
| `cond_min_amt`, `cond_basis_cd` | 100000, PREV_MONTH_SPEND | 불변 |
| 조건식 논리 | - | 전체 조합 동일 |

조건 근거 2건을 추가했다. `transit_spend`→044(표의 10만원), 048(실적 정의). 기존 SELF 연결은 유지했다.

원본 추적: `card_extr_stg`, `card_ai_call`은 해시로 불변을 확인했다. 변경 전후는 `src/data/backup/a10_2_pre_p1_p3_20261101/changelog.json`에 있다.

## 5. P3 규칙별 근거: 반영 (안 A)

V6의 표현은 `ev_subject_cd=RULE`, `card_bnft_id`, `rule_key`다. 새 근거는 만들지 않았고, 연결 대상의 금액·최소 금액·제외 문구가 인용 안에 있음을 검증했다. 기존 연결과 중복은 0이다.

| 연결 ID | 규칙 | 항목 | 근거 |
|---|---|---|---|
| 044, 045 | `one_pick_100` | SELF, `MIN_one_pick_100` | 034 |
| 046, 047 | `one_pick_500` | SELF, `MIN_one_pick_500` | 035 |
| 048, 049 | `style_100` | SELF, `MIN_style_100` | 040 |
| 050, 051 | `style_500` | SELF, `MIN_style_500` | 041 |
| 052, 053 | `transit_rate` | SELF, `transit_exclusions` | 045, 050 |
| 054 | `amusement_rate` | SELF | 052 |

P2 연결은 042, 043이다. 034~041은 병합 셀 전체를 인용하므로 한 근거에 두 구간이 함께 있다. 규칙별로 구분되는 것은 연결이고 인용 범위는 아니다.

## 6. 변경 전후 데이터

| 항목 | 변경 전 | 변경 후 |
|---|---:|---:|
| `card_bnft` 행 | 4 | 4 (2행의 `bnft_cond_expr`만 변경) |
| `card_policy_evidence` | 41 | **54** |
| BNFT SELF / COND | 25 / 2 | 25 / **4** |
| RULE SELF / COND | 0 / 0 | **6 / 5** |
| POLICY, POOL | 5, 9 | 5, 9 |
| `card_source_evidence` | 31 | 31 |
| 조건 atom | 15 | 15 |
| `GRACE` atom | 2 | **1** (`transit_grace`) |
| `BNFT_EXCL` atom | 2 | **3** |

| 사후 검증 | 결과 |
|---|---|
| 게이트 | `evidence_not_approved` 31건만, 동일. `evidence_item_key_missing` 0 |
| 인용 일치 | 31/31 |
| 기존 연결 41행, 근거 31행 | 불변 |
| 페이지·청크·풀·정책·staging·AI 호출 | 해시 불변 |

백업: `src/data/backup/a10_2_pre_p1_p3_20261101/`. 복구는 `restore_p1_p3.sql`이다.

## 7. Neo4j 변환기 수정

**새 라벨과 관계 유형은 필요 없다.** 기존 `A8_SUPPORTED_BY`의 시작점으로 `A8Rule`을 허용했다.

| 파일 | 변경 |
|---|---|
| `neo4j_dry_run.py` | `rules` 사전 추가, `RULE` 분기 1줄 |
| `neo4j_load_draft.py` | 108·168 고정을 `EXPECTED_NODES=108`, `EXPECTED_RELATIONSHIPS=181` 상수로 변경 |
| `test_neo4j_dry_run.py` | 규칙 근거, 없는 규칙 거부, 혜택 범위, 미지원 주체 거부 |
| `test_neo4j_load_draft.py` | 규칙 근거 관계의 허용 목록과 항목 키 보존 |

드라이런은 PostgreSQL 변경 전 메모리 시나리오와 변경 후 실제 스냅샷에서 모두 수행했다.

| 항목 | 현재 Neo4j | 드라이런 |
|---|---:|---:|
| 노드 / 라벨 | 108 / 13 | 108 / 13 |
| 관계 / 유형 | 168 / 12 | **181** / 12 |
| `A8_SUPPORTED_BY` | 41 | **54** (Policy 5, Benefit 29, Rule 11, Pool 9) |

`neo4j_load_draft`는 이제 108·181만 허용하므로 PREVIEW가 181을 출력한다. 재적재 전까지 Neo4j의 168과 다르다.

## 8. 현재 PostgreSQL·Neo4j 차이

| 항목 | 결과 |
|---|---|
| 노드 키 집합 | 108개 동일 |
| `source_json`이 다른 노드 | **9개** |
| Neo4j에 없는 관계 | **13개** (P2 2, P3 11) |
| Neo4j에만 있는 관계 | 0 |
| 이름공간 외부 노드·관계 | 0 |

9개 노드는 Evidence 037, 대중교통의 Benefit·Expression·Branch·Condition 4개, 놀이공원의 같은 4개다. 재적재 전까지 그래프의 `kind`는 `GRACE`, 대중교통 원문은 이전 값이다. 답변의 금액·논리에는 영향이 없다. Neo4j를 직접 고치지 않는다.

## 9. Neo4j 재동기화 절차 (미승인)

키 집합이 같으므로 **삭제 없이 기존 로더로 끝난다.** 코드 추가 수정은 필요 없다.

1. `.env`의 `NEO4J_DATABASE=6ac1f0f8` 확인.
2. PREVIEW 확인: `{"nodes": 108, "relationships": 181}`.

```powershell
.\.venv\Scripts\python.exe -m src.card_benefit.payment_card.db_pipeline.neo4j_load_draft
```

3. 승인 후 실행.

```powershell
.\.venv\Scripts\python.exe -m src.card_benefit.payment_card.db_pipeline.neo4j_load_draft --apply --confirm APPROVED_ONE_PICK_STYLE_A8
```

| 예상 효과 | 값 |
|---|---|
| 노드 갱신 | 108건 `MERGE`·`SET`, 실제 값 변경 9건 |
| 관계 생성 | 13건 |
| 삭제 | 0 |
| 트랜잭션 | 단일. 사후 조건이 다르면 롤백 |

4. 검증: 차이 비교 재실행(다른 노드 0, 없는 관계 0), 근거 037 `start_pos=2270`, `RUN_NEO4J_INTEGRATION=1` 테스트.

주의: 로더는 관계를 지우지 않는다. 재적재 후 PostgreSQL을 되돌리면 13개 관계가 남아 사후 조건이 실패한다. 되돌릴 때는 이름공간 교체 절차가 필요하다.

## 10. P4 국내 일시불: 보류, DB 미변경

원문은 "서비스 제공 방법" 절의 "매출 접수된 국내 일시불 이용금액에 따라 캐시백 혜택을 제공하며, 매출 취소 시 취소가 접수된 월에서 실적 및 캐시백 제공 금액 차감 반영"이다.

| 혜택 | 판단 | 이유 |
|---|---|---|
| ONE PICK | 문맥상 적용 | 캐시백 혜택 |
| STYLE | 문맥상 적용 | 캐시백 혜택 |
| 대중교통 | **불명확** | 캐시백이지만 다음 줄에 후불교통 무승인 거래를 별도로 설명 |
| 놀이공원 | 적용 근거 없음 | 현장할인이며 캐시백이 아님 |

**보류 이유:** "이용금액에 따라"가 적용 자격 조건인지, 금액 산정 기준인지 원문으로 구분되지 않는다. 정액 캐시백에는 자격 조건으로, 정률 캐시백에는 산정 기준으로도 읽힌다.

자격 조건으로 확정될 경우의 구조 영향:

| 규칙 | 현재 | 추가 후 |
|---|---|---|
| `one_pick_*`, `style_*` | `[MIN]` | `[MIN AND 국내 일시불]` |
| `transit_rate` | `[NOT 대중교통 제외]` | `[NOT 대중교통 제외 AND 국내 일시불]` |
| 혜택의 OR 조건식 | `[실적 AND NOT 실적 제외] OR [유예]` | 불변 |

새 OR 분기는 없다. 정책 조건에 넣으면 놀이공원까지 적용되므로 하지 않는다. 메모리 시험 결과 Condition은 20개가 되고, 근거 포함 시 노드 114가 된다. 노드 키가 바뀌어 이름공간 교체가 필요하다.

## 11. P5 시험 가정 관리: 제안, DB 미변경

**`approved_at`은 쓰지 않는다.** 정책 승인과 시작일 검증은 다른 사실이다. `card_product_doc.effective_from`도 부적합하다. 문서 개정일(2026-04-29)과 출시일(2026-03-30)이 다르므로 문서 적용일이 곧 정책 시작일이 아니다.

### 정책 시작일

| 안 | 방법 | DDL | 판정 |
|---|---|---|---|
| **A (권장)** | `source_doc_list[]`에 `valid_from_verified_yn` 키 추가 | 불필요. `fn_valid_doc_ref_list`가 추가 키 허용 | 문서가 시작일을 뒷받침한다는 뜻과 맞음 |
| B | `valid_from_status_cd` 컬럼 | 필요 | 명확하지만 금지 범위 |
| C | `approved_at` | 불필요 | 의미가 달라 철회 |

변환기는 `not any(d.get("valid_from_verified_yn") for d in policy["source_doc_list"])`로 읽는다. **키가 없으면 가정으로 남으므로 지금 데이터를 바꾸지 않아도 결과가 같다.** 안전한 기본값이며 변환기만 먼저 바꿀 수 있다.

### 한도 집계

`CARD_MEMBER`의 코드명은 "회원 카드 단위(가족카드 합산)"다. 즉 **값 자체가 확인되지 않은 사실을 주장한다.** 체크카드인 이 상품의 PDF에는 가족카드 언급이 없다.

| 안 | 방법 | 영향 | 판정 |
|---|---|---|---|
| **A (권장)** | `LIMIT_AGG`에 `UNCONFIRMED` 추가, 풀 9행 변경 | 공통코드 1행, seed 파일, `extraction_service.py:537`, GraphRAG 문구 | 값이 사실대로 됨. SQL만으로 상태 조회 |
| B | `tier_list[]`에 검증 키 추가, 코드는 유지 | JSON 규약 | 틀린 의미의 값이 남음 |

`UNCONFIRMED`는 집계 단위가 아니라 상태 값이라는 점이 단점이다. 그래도 필수 컬럼에 거짓 값을 두는 것보다 낫다. `extraction_service.py:537`을 함께 고치지 않으면 재적재 때 `CARD_MEMBER`가 되돌아온다. 변환기 전환과 데이터 변경은 같은 단계에서 해야 한다.

## 12. 역할과 복잡도

| 계층 | 맡는 일 | 맡지 않는 일 |
|---|---|---|
| PostgreSQL | 원문, 정제 데이터, 상태, 형식 검증의 원본 | 관계 탐색 최적화 |
| Neo4j | 혜택·조건·한도·근거 탐색, 파생 사본 | 값 수정, 상태 판단 |
| Python GraphRAG | 질문 해석, 조회 조합, 답변 검증 | 업무 값 보관 |

| 복잡도 | A10-1 | A10-2 후 | 증가 |
|---|---:|---:|---:|
| PostgreSQL 테이블 / 컬럼 | 21 / 동일 | 21 / 동일 | 0 |
| 근거 행 | 31 | 31 | 0 |
| 노드 라벨 / 관계 유형 | 13 / 12 | 13 / 12 | 0 |
| 노드 | 108 | 108 | 0 |
| 관계 | 168 | 181 | 13 (연결 추가) |

**같은 업무 의미가 여러 계층에 있는 곳:**

| 의미 | 위치 | 권장 |
|---|---|---|
| 시험 가정 | `neo4j_dry_run.py` 99·118행 | P5로 PostgreSQL로 이동 |
| 미확정 조건 | `card_graphrag.py`의 `UNRESOLVED_ATOMS` | `cond_status_cd` 활용 검토 |
| 집계 기본값 | `extraction_service.py:537` | P5와 함께 정리 |
| 결제 기준 판별 | `CATALOG_QUERY`, `rule_conflicts`의 `SPEND_REQ` | `cond_basis_cd` 속성 승격 후 사용 |

## 13. 원문 검증에서 발견한 신규 사항

| 항목 | 내용 | 조치 |
|---|---|---|
| 놀이공원 실적 정의 근거 누락 | 048은 10만원/20만원을 함께 정의하는데 대중교통에만 연결됨 | 다음 보정 후보 |
| 조건 근거 연결 잔여 | atom 15개 중 8개만 COND 연결. 미연결: `transit_grace`(049), `amusement_spend`(054), `amusement_first_month`(055), `amusement_per_person`(052), 정책 3개 | 다음 보정 후보, 약 7건 |
| GraphRAG 근거 경로 | `EVIDENCE_QUERY`가 Rule 경로를 읽지 않음. 같은 근거가 혜택 경로로 조회되어 답변 영향은 없음 | 재적재 후 판단 |
| 정제 텍스트 | `chunk_clean_txt` 비어 있음 | 현재 영향 없음 |
| 근거 위치 게이트 | 표 행 일치를 자동 검사하지 못함. 이번 대조는 임시 스크립트 | 필요 시 시험 코드화 |
| 복구 SQL | 작성 시 줄바꿈 이스케이프 오류를 발견해 수정, 백업값 일치 확인 | 완료 |

## 14. 남은 업무 미확정

100·500원 적용 방식, 한도 집계 단위, 최초 발급 월 기준일, 1인 1매 범위, 국내 일시불의 성격과 대중교통 적용, 정책 시작일, 근거 31건 승인. 상품 약관 또는 카드사 확인이 필요하다.

# A10-1 기록

실행한 변경은 근거 037의 위치 정정 1건이었다. 이 절 2절 이후의 SQL은 당시 제안이다.

## 1. 실행 완료: 근거 037 위치

### 원문 검증

같은 문구 `월 5천원`이 두 곳에 있으므로 네 단계로 확인했다.

| 단계 | 결과 |
|---|---|
| 저장 텍스트와 PDF 대조 | `chunk_raw_txt`, `page_raw_txt`, PDF 추출 스트림이 2,482자 전체 일치 |
| 문자 위치→PDF 좌표 | 위치 1622~1626 → y=299~308, 위치 2270~2274 → y=226~235 |
| 표 구분선 | ONE PICK 행 y=204~271, STYLE 행 y=271~348. 금액 한도 열 구분선 확인 |
| 표 이미지 | ONE PICK 행의 `월 5천원`은 `일 1회 / 월 30회` 옆 칸, STYLE 행과 구분선으로 분리 |

위치 앞 문맥도 일치한다. 2270 앞은 `일 1회\n/ 월 30회\n`, 1622 앞은 `일 1회\n/ 월 10회\n`이다.

### 변경 전후

| 컬럼 | 변경 전 | 변경 후 |
|---|---|---|
| `evidence_id` | `20261101_000037` | 동일 |
| `start_pos` | 1622 | **2270** |
| `end_pos` | 1626 | **2274** |
| `quote_txt` | `월 5천원` | 동일 |
| `approval_status_cd` | PENDING | 동일 |

```sql
-- 실제 실행. 조건을 모두 만족할 때만 1행 변경
UPDATE db_pipeline.card_source_evidence
SET start_pos=2270, end_pos=2274
WHERE evidence_id='20261101_000037' AND start_pos=1622 AND end_pos=1626
  AND quote_txt='월 5천원' AND card_doc_chunk_id='20261101_000012';
```

```sql
-- 변경 후 확인
SELECT pe.ev_link_id, pe.ev_subject_cd, pe.card_bnft_id, pe.pool_id, e.start_pos, e.end_pos
FROM db_pipeline.card_policy_evidence pe
JOIN db_pipeline.card_source_evidence e USING (evidence_id)
WHERE e.quote_txt='월 5천원' ORDER BY e.evidence_id, pe.ev_link_id;
```

| 연결 | 대상 | 위치 | 행 |
|---|---|---|---|
| `...007` | 혜택 ONE PICK | 2270~2274 | ONE PICK |
| `...034` | 풀 `...003` | 2270~2274 | ONE PICK |
| `...013` | 혜택 STYLE | 1622~1626 | STYLE |
| `...037` | 풀 `...006` | 1622~1626 | STYLE |

### 안전 절차와 사후 검증

| 항목 | 결과 |
|---|---|
| 백업 | `src/data/backup/a10_1_pre_evidence037_20261101/`. 근거 31행, 연결 41행, 해시, 복구 SQL |
| 범위 | 31행 중 1행, 2개 컬럼. 연결 41행 불변. 트랜잭션 안에서 확인 |
| 인용 일치 | 31/31 |
| 게이트 | `evidence_not_approved` 31건만, 이전과 동일 |
| 변환 | 메모리 변환 108·168, 고아 0. 로더 PREVIEW 정상 |
| 테스트 | 변환기·로더 8개 통과 |

## 2. 항목별 분류

| 항목 | 원문으로 확정된 오류 | V6로 보정 가능 | 표현 규약 필요 | 업무 확인 필요 |
|---|---|---|---|---|
| 근거 037 | 예 | **완료** | 아니요 | 아니요 |
| 놀이공원 GRACE | 예, 유형이 원문과 반대 방향 | 예 | `BNFT_EXCL` 규약 확인 | 발급 월 기준 |
| 대중교통 실적 | 수치는 정확, 원문 표현만 문제 | 예 | 예 | 아니요 |
| 규칙별 근거 | 오류가 아니라 누락 | 예, 변환기 수정 동반 | 예 | 아니요 |
| 국내 일시불 | 조건 누락 | 예 | 예, 위치가 논리식에 영향 | 적용 범위 |
| 100·500원 선택 | 아님 | 확인 후 가능 | 아니요 | **예, 보류** |
| 한도 집계 단위 | 아님 | 확인 후 가능 | 아니요 | **예, 보류** |
| 1인 1매 | 아님 | 현 상태 유지 | 아니요 | **예, 보류** |
| 정책 시작일 | 아님 | 확인 후 가능 | 아니요 | **예, 보류** |

## 3. 제안 P1: 놀이공원 최초 발급 월 유형

### 대조

| 관점 | 내용 |
|---|---|
| PDF | 놀이공원 행 지난달 실적 칸 "20만원 / 최초 발급 월에는 서비스 미제공". 위치 2425~2441 |
| 현재 | `amusement_first_month`, `GRACE`, `negate_yn=true`, `cond_basis_cd=NULL`, branch 1 seq 2 |
| 제안 | `cond_type_cd`만 `BNFT_EXCL`로 변경 |

### 의미 변화 검토

```text
변경 전: 실적 AND NOT(최초 발급 월) AND NOT(실적 제외) AND 1인 1매   [유형 GRACE]
변경 후: 실적 AND NOT(최초 발급 월) AND NOT(실적 제외) AND 1인 1매   [유형 BNFT_EXCL]
```

- **논리식은 그대로다.** branch, seq, `negate_yn`, `atom_key`, 원문이 모두 유지된다.
- **조건 키가 그대로라** 근거 연결과 Neo4j 노드 키에 영향이 없다.
- **코드가 유형으로 분기하지 않는다.** `GRACE`로 동작이 달라지는 코드는 없고, `extraction_service`는 형식만 검사한다. `SPEND_EXCL·BNFT_EXCL`은 `excl_raw_txt`가 필수인데 이미 값이 있다.
- `fn_valid_cond_expr` 사전 검증 결과 true다.

전제가 하나 있다. `BNFT_EXCL`의 술어를 "제외 대상이다"로 정의해야 `NOT`이 "제외 대상이 아니다"가 된다. 기존 `common_service_exclusion`, `transit_exclusions`도 같은 패턴이다. 이 규약을 함께 확정해야 한다. 원문의 "서비스 제외 대상" 목록에는 없는 항목이 같은 유형으로 묶이는 점은 수용이 필요하다.

"최초 발급 월"의 기준일은 이 변경으로 정해지지 않는다.

```sql
-- 미실행
UPDATE db_pipeline.card_bnft
SET bnft_cond_expr = jsonb_set(bnft_cond_expr, '{branches,0,atoms,1,cond_type_cd}', '"BNFT_EXCL"')
WHERE card_id=2 AND policy_ver_id='20261101_000001' AND card_bnft_id='20261101_000004'
  AND bnft_cond_expr #>> '{branches,0,atoms,1,atom_key}'='amusement_first_month'
  AND bnft_cond_expr #>> '{branches,0,atoms,1,cond_type_cd}'='GRACE';
```

검증: 1행 변경, 조건 atom 15개 유지, `v_card_cond_atom`에서 해당 atom만 유형 변경, 게이트 동일.

## 4. 제안 P2: 대중교통 실적 조건

### 대조

| 관점 | 내용 |
|---|---|
| PDF | 표 "지난달 실적 10만원", 문구 "지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시 ONE MORE 서비스 제공" |
| 구조화 값 | `cond_min_amt=100000`, `cond_basis_cd=PREV_MONTH_SPEND`. **정확** |
| 원문 값 | `'지난달 실적\n대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원'`. 추출 스트림 2335~2371에 연속으로 있으나 표 머리글과 행 전체가 섞여 조건 문장이 아니다 |
| 근거 연결 | 혜택 SELF로 044, 048. `transit_spend` 조건에 직접 연결되지 않음 |

### 제안

```sql
-- 미실행. 수치·논리 불변, 원문 텍스트만 교체
UPDATE db_pipeline.card_bnft
SET bnft_cond_expr = jsonb_set(bnft_cond_expr, '{branches,0,atoms,0,cond_raw_txt}',
    to_jsonb((SELECT quote_txt FROM db_pipeline.card_source_evidence WHERE evidence_id='20261101_000048')))
WHERE card_id=2 AND policy_ver_id='20261101_000001' AND card_bnft_id='20261101_000003'
  AND bnft_cond_expr #>> '{branches,0,atoms,0,atom_key}'='transit_spend';

-- 미실행. 수치 근거와 실적 정의 근거를 조건에 직접 연결
INSERT INTO db_pipeline.card_policy_evidence
  (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, ev_item_cd, ev_item_key, evidence_id)
VALUES (2,'20261101_000001','BNFT','20261101_000003','COND','transit_spend','20261101_000044'),
       (2,'20261101_000001','BNFT','20261101_000003','COND','transit_spend','20261101_000048');
```

규약안: `cond_raw_txt`는 `card_source_evidence` 인용 하나와 같아야 하고, 금액은 구조화 컬럼이 담는다. 실적 정의("국내외 일시불, 승인 시점")는 `cond_params` 규약을 새로 만들지 않고 근거 연결로 표현한다.

`spend_exclusions`의 위치 변경은 논리식 변경이므로 제안하지 않는다. 현재 구조를 유지하고 "실적 계산 범위를 정의하는 atom"으로 문서화한다.

사전 검증: `fn_valid_cond_expr` true. `fn_cond_spend_bound`는 OR 조건식이라 설계대로 NULL을 반환한다.

## 5. 제안 P3: 규칙별 원문 근거

V6는 이미 지원한다(`ev_subject_cd=RULE`, `ev_item_cd=COND`). 현재 RULE 연결은 0건이다.

**선택지:**

| 안 | 내용 | 신규 근거 | 장단점 |
|---|---|---|---|
| A (권장) | 기존 근거 재사용, 규칙 연결 11건 추가 | 0 | 행 추가 최소. 인용이 두 구간을 함께 담음 |
| B | 구간별 좁은 근거 4건 신규 | 4 | 정밀. 행 증가 |
| C | 기존 034·035·040·041 위치 축소 | 0 | 정밀하지만 **`validate_answer`의 금액 구간 근거 탐색이 실패한다.** 프로그램 수정 필요 |

병합 셀이므로 ONE PICK과 STYLE이 같은 원문 위치를 쓰는 것은 정상이다. 100원 구간은 1565~1584, 500원 구간은 1588~1607이다.

안 A의 연결:

| 규칙 | SELF | COND |
|---|---|---|
| `one_pick_100` | 034 | `MIN_one_pick_100` 034 |
| `one_pick_500` | 035 | `MIN_one_pick_500` 035 |
| `style_100` | 040 | `MIN_style_100` 040 |
| `style_500` | 041 | `MIN_style_500` 041 |
| `transit_rate` | 045 | `transit_exclusions` 050 |
| `amusement_rate` | 052 | 없음 |

```sql
-- 미실행 (안 A)
INSERT INTO db_pipeline.card_policy_evidence
  (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, rule_key, ev_item_cd, ev_item_key, evidence_id)
SELECT 2, '20261101_000001', 'RULE', v.bnft, v.rule_key, v.item_cd, v.item_key, v.ev
FROM (VALUES
 ('20261101_000001','one_pick_100','SELF','-','20261101_000034'),
 ('20261101_000001','one_pick_100','COND','MIN_one_pick_100','20261101_000034'),
 ('20261101_000001','one_pick_500','SELF','-','20261101_000035'),
 ('20261101_000001','one_pick_500','COND','MIN_one_pick_500','20261101_000035'),
 ('20261101_000002','style_100','SELF','-','20261101_000040'),
 ('20261101_000002','style_100','COND','MIN_style_100','20261101_000040'),
 ('20261101_000002','style_500','SELF','-','20261101_000041'),
 ('20261101_000002','style_500','COND','MIN_style_500','20261101_000041'),
 ('20261101_000003','transit_rate','SELF','-','20261101_000045'),
 ('20261101_000003','transit_rate','COND','transit_exclusions','20261101_000050'),
 ('20261101_000004','amusement_rate','SELF','-','20261101_000052')
) v(bnft, rule_key, item_cd, item_key, ev);
```

기존 BNFT 연결은 삭제하지 않는다. GraphRAG `EVIDENCE_QUERY`는 Rule 경로를 읽지 않지만 같은 근거가 혜택 경로로 조회되므로 답변 영향은 없다.

**변환기 수정이 선행 조건이다.** `neo4j_dry_run.py`는 RULE을 `unsupported evidence subject`로 거부한다. 사전 시험에서 실제로 예외가 났다. 약 3줄의 분기 추가가 필요하고, `neo4j_load_draft.py`의 108·168 고정 검사도 고쳐야 한다.

## 6. 제안 P4: 국내 일시불 이용 조건

### 대조

| 관점 | 내용 |
|---|---|
| PDF | "매출 접수된 국내 일시불 이용금액에 따라 캐시백 혜택을 제공하며...". 위치 997~1029 |
| 현재 | atom 없음, 근거 없음 |
| 범위 | 문구상 **캐시백**. 놀이공원은 현장할인이라 문구 범위 밖으로 읽힌다 |
| 구분 | 실적은 "국내외 일시불", 캐시백 대상은 "국내 일시불"로 **서로 다르다** |

### 위치 선택

| 위치 | 결과 | 판정 |
|---|---|---|
| 정책 `policy_cond_expr` | 놀이공원에도 AND 적용 | 문구 범위를 넘음 |
| 혜택 `bnft_cond_expr` | 대중교통은 OR 2개 분기 모두 복제 필요, `atom_key` 중복 금지 위반 | 부적합 |
| **규칙 `cond_expr` (권장)** | 캐시백 규칙 5개에 atom 1개씩. 조건식이 이미 있고 AND로 결합 | 논리상 깔끔. 행은 조건 5개 증가 |

```json
{"atom_seq": 2, "atom_key": "domestic_lump_sum", "negate_yn": false,
 "cond_type_cd": "PAYMENT_METHOD", "cond_basis_cd": null, "cond_min_amt": null,
 "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null,
 "cond_params": null, "card_excl_item_id": null, "excl_raw_txt": null,
 "cond_raw_txt": "매출 접수된 국내 일시불 이용금액에 따라 캐시백 혜택을 제공",
 "link_role_cd": null, "cond_status_cd": "DRAFT"}
```

```sql
-- 미실행. 논리식 변경이므로 사용자 확인 필수
UPDATE db_pipeline.card_bnft b
SET rule_list = (
  SELECT jsonb_agg(jsonb_set(r.value, '{cond_expr,branches,0,atoms}',
           (r.value #> '{cond_expr,branches,0,atoms}') || :'atom'::jsonb) ORDER BY r.ord)
  FROM jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value, ord))
WHERE b.card_id=2 AND b.policy_ver_id='20261101_000001' AND b.bnft_type_cd='CASHBACK';
```

근거는 `card_source_evidence` 1건(997~1029)과 규칙별 COND 연결 5건을 추가한다.

사전 검증: `fn_valid_rule_list` 3건 모두 true. 메모리 변환 결과 Condition 20, 노드 113, 관계 173. 근거 추가 전 수치다.

업무 확인 사항: 대중교통이 "매출 접수 국내 일시불"에 해당하는 방식(후불교통 무승인 거래 포함)과 놀이공원 제외 해석이다.

## 7. 제안 P5: 가정값 관리

현재 `neo4j_dry_run.py` 99행과 118행이 `True`를 고정한다. 값이 확정돼도 Neo4j는 계속 가정으로 표시한다.

**DDL 변경 없이 해결할 수 있다.**

| 가정 | PostgreSQL 관리 방법 | 변환기 | 변경 종류 |
|---|---|---|---|
| 정책 시작일 | 기존 `approved_at IS NULL`을 사용 | `policy["approved_at"] is None` | 코드만 |
| 한도 집계 | `LIMIT_AGG`에 `UNCONFIRMED` 추가, 풀 9건 변경 | `row["aggregation_key_cd"] == "UNCONFIRMED"` | 공통코드 1행 + 데이터 9행 + 코드 |

```sql
-- 미실행. 공통코드는 DDL이 아니나 코드 체계 결정이므로 승인 필요
INSERT INTO db_pipeline.common_cd (common_code_grp_id, common_cd, common_cd_nm, create_user_id, update_user_id)
VALUES ('LIMIT_AGG','UNCONFIRMED','집계 기준 미확정','A10_1','A10_1');

UPDATE db_pipeline.card_limit_pool SET aggregation_key_cd='UNCONFIRMED'
WHERE card_id=2 AND policy_ver_id='20261101_000001' AND aggregation_key_cd='CARD_MEMBER';
```

| 항목 | 내용 |
|---|---|
| 장점 | 원본이 상태를 소유. SQL로 조회 가능. 확정 시 UPDATE 한 번으로 Neo4j까지 반영 |
| 영향 | `db_pipeline_common_code_seedV6.sql` 동기화, GraphRAG `find_unresolved` 문구, 변환기 테스트 |
| 기각한 안 | `tier_list`에 JSON 키 추가: 조회가 번거롭고 규약이 늘어남. `predicate_state_cd` 재사용: 조건 판정 상태라 의미가 다름. 신규 컬럼: 필수 근거 없음 |

`approved_at` 방식은 승인 시 시작일도 검증된다는 전제가 있다. 승인 절차에 이 확인을 포함해야 한다.

## 8. 데이터 모델 변경 필요 여부

**DDL 변경은 불필요하다. 21개 테이블, 신규 컬럼 0, 신규 노드 라벨 0, 신규 관계 유형 0.**

| 변경 | 필요 여부 |
|---|---|
| 테이블·컬럼 DDL | 불필요 |
| 공통코드 | P5 채택 시 1행 |
| JSONB 계약 | 불필요, 규약 문서화만 |
| 변환기·로더 | 필요(RULE 분기, 건수 검사, 가정 표시, `basis` 등 속성) |
| 게이트 뷰 | 선택. 규칙 겹침 검사는 별도 판단 |

## 9. Neo4j 재적재 계획 (미승인)

### 현재 상태

읽기 조회로 확인했다.

| 비교 | 결과 |
|---|---|
| 노드 키 집합 | 108개 동일 |
| 관계 키 집합 | 168개 동일 |
| `source_json`이 다른 노드 | **`...000037` 1건** (Neo4j 1622~1626, PostgreSQL 2270~2274) |

재적재 전까지 Neo4j의 근거 037 위치는 정정 전 값이다. 답변 내용에는 영향이 없고 위치 추적만 다르다. Neo4j를 직접 고치지 않는다.

### 단계별 예상 변화

| 단계 | 노드 | 관계 | 키 집합 | 재적재 방식 |
|---|---|---|---|---|
| 현재 | 108 | 168 | - | - |
| 037 | 108 | 168 | 동일 | 방식 A |
| + P1 | 108 | 168 | 동일 | 방식 A |
| + P2 | 108 | 170 | 관계 추가 | 방식 A, 건수 검사 수정 |
| + P3 | 108 | 181 | 관계 추가 | 방식 A, RULE 분기·건수 수정 |
| + P4 | 114 | 192 | 노드 추가 | **방식 B** |
| + P5 | 114 | 192 | 동일 | 속성만 변경 |

P4의 증가분은 Condition 5, Evidence 1, HAS_ATOM 5, IN_CHUNK 1, SUPPORTED_BY 5다. 새 라벨과 관계 유형은 없다.

### 방식 A: 키 유지 재실행

로더는 키 집합이 같으면 `MERGE`와 `SET`으로 갱신한다. 삭제가 없다.

```powershell
# 미승인. NEO4J_DATABASE=6ac1f0f8 확인 필요
.\.venv\Scripts\python.exe -m src.card_benefit.payment_card.db_pipeline.neo4j_load_draft --apply --confirm APPROVED_ONE_PICK_STYLE_A8
```

037만 반영할 때는 코드 변경 없이 이 명령으로 끝난다. 단일 트랜잭션이고 사후 조건이 다르면 롤백된다.

### 방식 B: 이름공간 교체

키 집합이 바뀌면 로더가 `namespace differs from snapshot`으로 거부한다. 의도된 안전장치다.

1. 사전 확인: 노드·관계 건수, 이름공간 외부 관계 0건.
2. 이름공간 노드·관계를 JSONL로 백업.
3. 로더에 명시적 교체 옵션과 별도 확인 문자열 추가.
4. 한 트랜잭션에서 `A8Test` 이름공간만 삭제하고 적재.
5. 건수, 키, `source_json` 전수 대조.
6. 레시피 등 다른 라벨을 건드리지 않음을 확인. 현재 그래프에 다른 데이터가 없어도 조건을 유지한다.

새 이름공간 병행은 권장하지 않는다. `NS`가 변환기와 `neo4j_search.py`에 고정돼 있고, 시험 데이터 두 벌을 관리해야 한다. 이 그래프는 PostgreSQL에서 다시 만들 수 있다.

### 재적재 후 검증

- SQL·Cypher 조건 atom과 근거 연결 대조(A10 스크립트 재사용).
- `test_neo4j_origin_search`, `test_card_graphrag`의 실제 Neo4j 읽기 테스트.
- 근거 037의 `start_pos=2270`.

## 10. 권장 실행 순서

1. 사용자 결정(아래 표).
2. 전체 백업과 실행 스크립트 준비.
3. P1, P2 조건 보정.
4. P4 조건 추가(승인 시).
5. P3 규칙 근거 연결.
6. P5 가정값 이관.
7. 게이트, 인용 일치, 사람 검토.
8. 변환기 수정과 테스트.
9. Neo4j 재적재와 대조.
10. GraphRAG Mock 회귀.

| 결정 | 권장 |
|---|---|
| P1 `BNFT_EXCL` 변경과 술어 규약 | 승인 |
| P2 원문 교체와 COND 연결 | 승인 |
| P3 근거 연결 방식 | 안 A |
| P4 추가 여부와 규칙 위치 | 규칙 위치로 승인, 단 범위 해석 확인 |
| P5 `UNCONFIRMED` 코드 | 승인 |

## 11. 남은 업무 미확정 항목

| 항목 | 상태 | 필요한 확인 |
|---|---|---|
| 100·500원 적용 방식 | 미확정 | 약관 또는 카드사 |
| 한도 집계 단위 | 미확정 | 약관 또는 카드사 |
| 최초 발급 월 기준일 | 미확정 | 약관 또는 카드사 |
| 1인 1매 범위 | 미확정 | 약관 또는 카드사 |
| 정책 시작일 | 시험 가정 | 정책 승인 절차 |
| 국내 일시불의 대중교통·놀이공원 적용 | 해석 필요 | 약관 또는 카드사 |
| 근거 승인 | 31건 PENDING | 사람 검토 |
