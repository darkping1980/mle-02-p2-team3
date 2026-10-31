# 카드 혜택 DB 모델링: 컬럼·행 설계 검토

작성일: 2026-10-31. **분석 전용**. DB·DDL·기존 소스 변경 및 LLM 호출 없음. PDF 원문 판독 결과와 현재 PostgreSQL 카탈로그 조회 결과를 별도로 표기한다. 아래 예시 ID와 행은 설계 설명을 위한 가상 식별자이며 DB 적재 결과가 아니다.

## 1. 범위, 선정, 근거의 한계

`src/card_benefit/data/raw/hana_all`에는 신용 107개, 체크 70개, 공통 19개의 PDF가 있었다. 요청에서 상품명을 지정하지 않았으므로, 정식 상품설명서 중 실적 구간·공유 한도·정액/정률·적립·예외의 차이를 보여 주는 신용 4종과 체크 4종을 선정했다. 웹페이지 변환본을 공식 상품설명서의 대체물로 사용하지 않았다. 파일명에 `URL추정확인`이 들어간 2종은 **파일 존재와 내용은 확인**, 원본 URL의 공식성은 이 분석에서 재검증하지 않았다. 페이지 번호는 PDF 뷰어의 1부터 시작하는 번호다.

| ID | 종류 | 실제 분석 PDF (`src/card_benefit/data/raw/hana_all/` 아래) | 쪽 |
|---|---|---|---:|
| C1 | 신용 | `credit/신용_K-패스하나신용카드_상품설명서(공식PDF)_14472_20251224.pdf` | 1 |
| C2 | 신용 | `credit/신용_더심플하나카드_상품설명서(공식PDF)_14527_20260929.pdf` | 1 |
| C3 | 신용 | `credit/신용_에너지더블카드_상품설명서(공식PDF)_14422_20251224.pdf` | 1 |
| C4 | 신용 | `credit/신용_JADEClassic_상품설명서(공식PDF)_14955_20260609.pdf` | 1~6 |
| D1 | 체크 | `debit/체크_K-패스하나체크카드_상품설명서(공식PDF)_14474_20251224.pdf` | 1 |
| D2 | 체크 | `debit/체크_더심플체크카드_상품설명서(공식PDF)_15245_20250703.pdf` | 1 |
| D3 | 체크 | `debit/체크_ONEPICKSTYLE하나체크카드_상품설명서(공식PDF,URL추정확인)_15650_20260429.pdf` | 1~2 |
| D4 | 체크 | `debit/체크_ONEPICKPLAY하나체크카드_상품설명서(공식PDF,URL추정확인)_15651_20260429.pdf` | 1~2 |

PDF는 페이지 텍스트를 추출하고 주요 표가 있는 C1~C3, C4 3쪽, D1~D4의 렌더링을 육안 대조했다. C4의 1쪽은 텍스트가 224자뿐인 표지에 가깝다. 다단 편집 PDF의 일반 텍스트 추출은 열이 섞이므로, 수치·적용 범위는 렌더링된 표를 우선했다. 아래 인용은 긴 원문을 발췌한 것으로, 인접 표의 열 제목과 주석을 함께 해석했다.

## 2. PDF별 혜택·조건과 원문 근거

| PDF | 페이지·원문 근거(발췌) | 확인된 해석과 모델링 함의 |
|---|---|---|
| C1 | 1쪽 표: `대중교통 / 버스, 지하철 / 10% / 50만원 이상 100만원 미만 / 월 1만원`, 다음 행 `100만원 이상 / 월 2만원`; 주석 `대중교통 : 시외버스, 고속버스, 티머니/캐시비 등 교통카드 충전금액은 서비스 제외` | 청구할인. 같은 대상·10%에 실적 구간별 **한도만** 달라진다. 교통 제외는 해당 혜택의 적용 제외다. 드럭스토어(다이소·올리브영)와 커피(스타벅스·커피빈)도 각각 10%지만 대상과 한도는 다르므로 할인율만으로 혜택을 합치면 안 된다. |
| C2 | 1쪽 표: `월납 요금 대상 가맹점 자동납부 시 / 30만원 이상 80만원 미만 / 10,000원`, `80만원 이상 / 15,000원`; 주석 `횟수 제한 없이 월 할인 한도 내에서 합산 할인`; 실적 제외 `월납 요금 할인 서비스 적용된 매출 전체 금액` | 통신·렌탈·기타 월납 가맹점이 하나의 월납 할인 한도를 공유한다. 실적 제외는 할인된 금액만이 아니라 **서비스 적용 매출 전체**다. 자동납부와 가맹점 대상이 동시에 필요하다. 표에 할인율은 명시되지 않아 정률 100%로 추정해서는 안 된다. |
| C3 | 1쪽 표: `아파트 관리비/전기요금/도시가스요금 자동이체 가맹점 / 40만원 이상 80만원 미만 / 10% / 5천원 / 1만원`, 다음 행 `80만원 이상 / 1만원 / 2만원`; 주석 `더블 할인은 ... 2월/3월/8월/9월 ... 매입되는 시점 기준`; 별도 표 `일상생활 청구할인 ... 40만원 이상 ... 5%` | 에너지 공과금 10%는 실적 두 구간 × 일반/더블 달의 네 한도가 필요하다. 3개 공과금 대상은 같은 정책을 공유한다. 일상생활은 별도 5% 혜택이며 온라인 결제 제외 등 자체 주석이 있다. `할인받은 매출 전체 금액`은 카드의 실적 제외다. |
| C4 | 3쪽 `특별 적립 / 영역별 1.5%~1.2% ... 지난달 실적 50만원 이상, 월 통합 적립 한도 10만 하나머니`; 표에서 해외·항공·면세·여행 1.5%, 쇼핑·마트·주유 1.2%; `기본 적립 ... 1% ... 지난달 실적 조건 없음, 적립 한도 제한 없음`; 3쪽 라운지 `본인/가족/동반자 통합 연 3회, 일 3회`; 4쪽 `디지털 컨텐츠 50% ... 월 적립 한도 1만 하나머니` | 특별 적립의 여러 영역은 **합산 월 10만 하나머니**를 공유하며 대상별 적립률이 다르다. 1.5/1.2%는 실적 구간 차이가 아니라 **대상 영역 차이**다. 기본 적립은 실적 무관. 라운지는 연·일 횟수와 본인/가족/동반자 합산 범위가 있다. 컨텐츠 적립은 자동납부 등 자체 조건과 별도 월 한도를 가진다. |
| D1 | 1쪽 표: `대중교통 / 버스, 지하철 / 10% / 30만원 이상 60만원 미만 / 월 3천원`, `60만원 이상 / 월 6천원`; `드럭스토어 / 다이소, 올리브영 / 1%`, `커피 / 스타벅스, 커피빈 / 1%` | 같은 K-패스라도 C1과 실적 경계·한도가 다르다. 체크 상품 정책을 신용 상품과 공용 조건 행으로 합치면 오류다. |
| D2 | 1쪽 표: `통신 ... 30만원 이상 / 5,000원 / 월 한도 5,000원 / 건당 1만원 이상 결제`, `커피 ... 5% / 2,000원`; 주석 `통신 ... 자동이체 요금으로 청구된 경우에 한하여 제공`; `횟수 제한 없이 월 캐시백 한도 내` | 정액 통신 캐시백과 정률 커피 캐시백이 공존한다. 통신은 자동이체 **AND** 건당 금액 기준이 필요하고, 커피는 여러 브랜드·결제 채널 예외가 있다. |
| D3 | 1쪽 표: `ONE PICK ... 결제 건당 3천원 이상 시 100원 / 일 1회·월 30회 / 월 5천원`; STYLE `결제 건당 1만원 이상 시 500원 / 일 1회·월 10회 / 월 5천원`; ONE MORE `대중교통 ... 5% ... 월 1천원 ... 10만원`, `놀이공원 ... 50% ... 월 1회·월 2회 ... 20만원`; 오른쪽 `공통 : 상품권 및 기프트카드 구매 ... 제외` | 실적 없는 ONE PICK·STYLE과 실적 있는 ONE MORE를 분리해야 한다. 편의점·카페 및 쇼핑 대상은 각각 여러 가맹점이지만 혜택별 정액·횟수·월 한도를 공유한다. 오른쪽 공통 서비스 제외를 실적 제외와 동일시하면 안 된다. 놀이공원 표의 `월 1회 / 연 2회`로 판독되므로 연간 횟수도 필요하다. |
| D4 | 1쪽 표: ONE PICK `결제 건당 3천원 이상 시 100원 / 일 1회·월 30회 / 월 5천원`; PLAY `결제 건당 1만원 이상 시 500원 / 일 1회·월 10회 / 월 5천원`; ONE MORE `대중교통 5% ... 10만원`, `놀이공원 50% ... 20만원`; 실적 제외 `ONE PICK PLAY 하나 체크카드로 서비스 적용 받은 매출 제외` | D3와 공통 모듈 형태가 유사해도 **문서별 정책 인스턴스**를 유지한다. D4의 서비스 적용 매출은 실적에서 빠진다. ONE PICK과 PLAY에는 전월 실적 조건이 없다. 공통 제외와 대중교통 전용 제외는 범위가 다르다. |

추가 원문 범위: C1 1쪽 `[실적 제외 대상]`에 상품권·기프트카드 구매 및 선불카드/선불전자지급수단 충전이 있고, 같은 쪽 대중교통 주석에는 시외버스 등이 **할인 적용 제외**로 나온다. C3 1쪽 `일상생활 청구할인 서비스 제외 대상`은 대형마트의 상품권 구매, 파리바게뜨/뚜레쥬르의 대형시설 입점점포, 버스/지하철의 시외버스 등 **혜택별 범위**로 나뉜다. D3·D4 1쪽 `공통`은 상품권과 배달·예약앱, 대형시설 입점 점포를 서비스에서 제외하지만, `대중교통`은 시외버스·고속버스·철도를 별도로 제외한다. 같은 원문 단어도 `SPEND_EXCL`과 `BNFT_EXCL`의 의미·대상 혜택을 따로 보존해야 한다.

**발견 판정.** 정률 할인·적립, 정액 캐시백, 전월 실적 기준·실적 제외, 서비스 제외, 월/일/연 한도, 횟수 제한, 구간별 **한도** 변화, 카드 공통·혜택 개별 조건, 통합 한도, 자동납부 AND 건당 금액, 가맹점/채널 OR, 신규 등록 유예, 계절·매입 시점 특수 조건은 확인됐다. **전월 실적 구간에 따라 할인율 자체가 바뀌는 사례는 선정한 8종에서 확인하지 못했다.** JADE의 1.5%/1.2%는 영역 차이고 K-패스·에너지 더블의 구간은 한도 차이다. 전체 하나카드 PDF에 없다는 주장도 아니다. 원문에 적립률이나 정액 할인액이 없는 혜택은 수치를 만들어 넣지 않는다.

## 3. 현재 DB와 최신 백업: 사실 확인

`.env`의 `DB_URL`을 프로세스 안에서만 사용해 현재 Supabase PostgreSQL에 접속했다. 접속 문자열과 비밀번호는 출력·저장하지 않았다. `SET TRANSACTION READ ONLY` 및 서버의 `transaction_read_only=on`을 확인했다. 조회 시점 DB는 PostgreSQL 17.11, `db_pipeline` 일반 테이블은 **11개**다. 최신으로 확인한 파일은 `src/data/backup/dump-postgres-202610311136.sql`이며 헤더의 백업 시작 시각은 **2026-10-31 11:36:11**이다. 파일 존재를 확인했고, 카탈로그와 백업의 테이블 11개, 컬럼 이름·자료형 187개, 제약 이름 64개, 인덱스 이름 40개, 테이블/컬럼 COMMENT 대상 194개의 집합을 대조해 차이가 없었다. 이는 정의 대상·타입·이름 비교이며 모든 COMMENT 본문이나 CHECK 수식의 바이트 단위 동등성까지 검증했다는 뜻은 아니다.

| 실제 테이블 | 주요 컬럼·자료형 | PK / 핵심 제약·인덱스 / 역할 |
|---|---|---|
| `card_doc` | `card_doc_id varchar`, `card_id bigint`, `doc_sha256 varchar`, `doc_version_no smallint`, `doc_status varchar` | PK `card_doc_id`; 문서 해시 UNIQUE, `(card_id,doc_type_cd,doc_version_no)` UNIQUE, 활성 문서 부분 UNIQUE `uq_card_doc_active`; 버전 원천 |
| `card_doc_page` | `card_doc_id varchar`, `page_no smallint`, `page_raw_txt text`, `page_txt_sha256 varchar` | PK `(card_doc_id,page_no)`; 원문 페이지 |
| `card_doc_chunk` | `card_doc_id varchar`, `page_no smallint`, `card_doc_chunk_id varchar`, `chunk_raw_txt text`, `chunk_clean_txt text` | PK `(card_doc_id,page_no,card_doc_chunk_id)`; 청크 원문·정제 |
| `card_ai_run` | `card_ai_run_id varchar`, `run_stage_cd varchar`, `run_call_mthd_cd varchar`, `run_model_nm varchar` | PK `card_ai_run_id`; 추출·검증 실행 |
| `card_ai_call` | 실행·문서·쪽·청크·호출순번, `call_resp_json jsonb` | 5열 복합 PK; 청크별 호출 응답 |
| `card_excl_item` | `card_excl_item_id varchar`, `issuer text`, `excl_item_nm text`, `excl_concept_cd varchar` | PK ID, `(issuer,excl_item_nm)` UNIQUE; 제외 대상 개념. **정책 자체가 아님** |
| `card_excl_item_als` | `card_excl_item_id varchar`, `card_excl_item_als_id varchar`, `excl_item_als_nm text` | 복합 PK, 대상별 별칭 UNIQUE |
| `card_extr_stg` | `card_extr_stg_id varchar`, `stg_raw_item jsonb`, `stg_normalized_item jsonb`, `stg_status varchar`, 원문 위치 | 실행·문서·쪽·청크·호출·후보 ID의 복합 PK; 후보·검증·승인 |
| `card_bnft` | `card_doc_id varchar`, `card_bnft_id varchar`, `bnft_type_cd varchar`, `bnft_rate numeric`, `bnft_amt numeric`, `bnft_target_txt text` | PK `(card_doc_id,card_bnft_id)`; `(card_doc_id,bnft_nm)` UNIQUE; 확정 혜택 |
| `card_cond` | `cond_type_cd varchar`, `cond_apply_lvl_cd varchar`, `card_bnft_id varchar?`, `cond_min_amt/cond_max_amt/cond_rate/cond_amt/cond_limit_amt numeric`, `cond_limit_cnt integer`, `cond_rule_json jsonb` | PK `(card_doc_id,card_cond_id)`; 자연키·후보 ID UNIQUE; 유형/기간/기준/상태 CHECK; 확정 조건 |
| `card_bnft_cond` | `card_doc_id varchar`, `card_bnft_id varchar`, `card_cond_id varchar` | PK `(card_doc_id,card_bnft_id,card_cond_id)`, 역방향 인덱스 `(card_doc_id,card_cond_id,card_bnft_id)`; **혜택↔조건 N:M 논리 연결** |

11개 테이블 모두 테이블 COMMENT가 있고, 187개 컬럼 중 183개에 컬럼 COMMENT가 있다. 이 COMMENT 대상 집합은 백업과 맞았다. 특히 `card_bnft_cond`의 테이블 COMMENT는 `카드 혜택과 적용 조건 간 N:M 논리 관계. Neo4j Benefit-Condition 관계 생성 기준`이다. `card_cond`의 `SPEND_EXCL`/`BNFT_EXCL`은 대상 항목 ID와 원문 표기를 요구하는 CHECK가 있고, `cond_apply_lvl_cd='CARD'`는 `card_bnft_id IS NULL`, `'BENEFIT'`은 `card_bnft_id IS NOT NULL`을 요구한다. `cond_rule_json`은 NOT NULL이다. 물리 FK는 없다. `card_bnft` 혜택 유형 CHECK는 DISCOUNT/CASHBACK/POINT/FEE_WAIVER/SERVICE/INSTALLMENT/ETC를 허용한다. 따라서 새 혜택마다 컬럼을 반드시 늘려야 하는 상태는 이미 아니다.

**관련 구조의 현재 상태:** `to_regnamespace('card_benefit')`와 `to_regclass('card_benefit.card_product')`는 둘 다 NULL이었다. 즉 이 접속 DB에는 `card_benefit.card_product` 자체가 없다. `src/card_benefit/sql/schema.sql`은 `card_id BIGINT IDENTITY PK`, `issuer`, `card_name`, `card_type CHECK (CREDIT,DEBIT)`, `created_at`을 정의하지만 **설계 파일이지 현재 DB의 존재 증거는 아니다**. 현재 `card_doc.card_id`는 그 테이블을 논리 참조한다는 COMMENT만 있다. 따라서 본 보고서의 카드 ID 연결 검증은 현재 DB에서 성공한다고 가정하지 않는다.

`src/card_benefit/sql/db_pipeline_schema.sql` 및 `db_pipeline_schemaV2.sql`은 각각 10개의 `CREATE TABLE`만 포함하고 `card_bnft_cond` 생성·COMMENT·역방향 인덱스가 없다. V2는 주석상 컬럼 배치 기준이 다르며 둘 다 관리용 DDL이다. **분석 기준은 현재 DB와 위 최신 백업**이다. 과거 10/11 차이는 이미 백업으로 정리된 이력이며 미해결 스키마 불일치로 취급하지 않는다. 다만 과거 DDL만 단독 실행하면 현재의 관계 테이블을 재현하지 못한다는 파일 수준의 사실은 남는다.

## 4. 현재 컬럼으로의 매핑과 의미 손실

| 원문 항목·실제 값 | 현재 저장 대상 | 가능성·적합 방식 | 손실/오연결 위험과 최소 보완 |
|---|---|---|---|
| C1 대중교통 10%, C3 공과금 10% | `card_bnft.bnft_rate`, 이름/유형; `card_cond` TIER | 단일 핵심 컬럼 + 구간 다중 행 가능 | `bnft_rate`에 하나의 대표율을 두되 구간률이 실제로 달라지는 상품에서는 구간 행의 `cond_rate`를 우선하도록 규칙 명시. 같은 10%라는 이유로 대상·한도를 합치지 않음. |
| D3 편의점 CU·GS25·세븐일레븐과 카페 다수, 공통 100원 | `bnft_target_txt`, `cond_target_txt` | 텍스트 가능, 다중 대상은 행이 적합 | 문자열만으로 대상별 검색·제외·Neo4j 변환이 불안정. `card_bnft_target`의 대상별 행을 추가. |
| C2 통신·렌탈·기타 월납이 공유하는 월 1만/1.5만원 | `card_cond` LIMIT/TIER + `card_bnft_cond` | 관계 테이블·구간 행으로 조건부 가능 | LIMIT를 대상별로 복제하면 한도를 각각 쓰는 것으로 오해. 단일 조건 ID가 여러 대상/혜택을 가리키고 `SHARED` 집계 범위를 표시. |
| C3 40~80만/80만 이상 × 일반/2·3·8·9월 한도 | `cond_min_amt`, `cond_max_amt`, `cond_limit_amt`, `cond_rule_json` | 다중 TIER 행 적합 | 경계 포함/제외와 **매입월**을 JSON/검증 규칙에 명시. `cond_rate=10`은 모든 구간 동일. |
| D3 ONE PICK 실적 없음, ONE MORE 교통 10만·놀이공원 20만 | `card_cond` SPEND_REQ, `card_bnft_cond` | 혜택별 연결 가능 | 카드 공통 실적 조건을 모든 혜택에 자동 전파하면 잘못 적용. 명시적 연결만 유효하도록 함. |
| C1 상품권 실적 제외 vs D3 상품권 서비스 제외 | `card_cond` SPEND_EXCL/BNFT_EXCL + `card_excl_item` + `card_bnft_cond` | 각각 별도 조건 행·관계 | 표준 제외 개념을 공유해도 정책 ID와 범위는 문서·혜택별로 분리. 동일 개념 ID를 동일 정책으로 간주하지 않음. |
| D2 통신 자동이체 AND 건당 1만원, D3 공식 사이트 OR 오프라인 | `card_cond` USAGE_REQ/MERCHANT_RULE, `cond_rule_json`, 관계 | 복수 조건 행 + 식 JSON | 단순 연결만으로 AND/OR 우선순위가 명확하지 않음. `cond_rule_json`에 그룹 연산자·자식 조건 ID와 원문을 명시하고 검증. 복잡도가 늘 때 별도 그룹 테이블 검토. |
| C4 월 통합 10만 하나머니, 라운지 통합 연 3회·일 3회 | `card_cond` LIMIT의 금액/횟수·기간, `card_bnft_cond` | 공유 LIMIT 행 가능 | 월 통합·본인/가족/동반자 합산을 행별 개별 한도로 오인할 수 있음. 한도 공유 범위·단위·집계 대상을 `cond_rule_json`의 필수 키로 규정. |
| C2 할인 적용 매출 전체 실적 제외 | `card_cond` SPEND_EXCL, `cond_excl_raw_txt`, `cond_rule_json` | 조건 행 가능 | `할인액만 제외`와 혼동 위험. 제외 단위를 `WHOLE_TXN`으로 표준화하고 원문을 유지. |
| 신규 할인/적립/면제 유형 | `bnft_type_cd` CHECK, `bnft_value_txt`, `cond_rule_json` | 기존 유형 내 신규 사례는 가능 | 진짜 새 유형 코드는 CHECK 변경이 필요하지만 매번 수치 컬럼을 증설하는 방식보다 영향이 작다. 미지원 타입은 ETC+원문으로 임시 보존 후 검토. |

**중요한 현재 구조상의 마찰:** `card_bnft_cond`가 이미 N:M을 제공하지만 `card_cond.card_bnft_id`와 `cond_apply_lvl_cd` CHECK는 혜택 조건을 한 혜택에 고정한다. 공유 조건을 `CARD`로 올리면 원문상 카드 공통인지 단지 여러 혜택이 공유하는지 구별이 흐려진다. `card_bnft_id`와 관계 테이블의 혜택 ID가 달라도 물리 제약이 막지 못한다. 이 부분이 대규모 재설계보다 우선할 개선점이다.

## 5. 세 설계의 비교와 선택

| 관점 | A 컬럼 중심 | B 순수 EAV(항목 코드·값 행) | C 핵심 컬럼 + 대상·구간·관계 행 |
|---|---|---|---|
| SQL 조회·검증 | 단순한 정률 조회·CHECK 우수. 구간·공유 한도는 반복 컬럼/복잡한 피벗 | 속성마다 조인/피벗·문자형 캐스팅 필요 | 기본 혜택은 간단; 복합 조건만 조인. 숫자형 CHECK 가능 |
| 무결성·중복 | 고정 타입 강함. 다중 대상/조건 복제 위험 | 허용 코드·단위·값 타입을 별도 메타데이터/검증에 의존 | PK·UNIQUE·타입 컬럼 유지, 공유 조건은 한 행과 N:M 링크 |
| 원문 의미 | 계절×구간, 카드/혜택 범위, AND/OR 보존이 어려움 | 원자 속성은 남지만 속성 간 묶음·원문 조항 범위가 흩어짐 | 조건 행의 근거와 관계, 식 JSON에 범위·연산자를 함께 남김 |
| 새 유형 확장 | 새 고정 컬럼·CHECK 변경 가능성 | 코드 추가 용이 | 새 대상/조건 행은 쉬움; 핵심 새 유형은 CHECK 변경 또는 ETC 검수 |
| 정규식·LLM 후보 저장 | 빈 컬럼/불완전 후보 처리 어려움 | 후보 다양성 수용 쉬움 | 이미 `card_extr_stg` JSON 후보와 확정 정형 테이블을 분리함 |
| Neo4j 변환 | 문자열 대상/반복 컬럼 파싱 필요 | 행을 노드화하기 쉽지만 의미 있는 연결 재구성 필요 | `card_bnft_cond`가 Benefit–Condition 엣지, 대상 행이 Target 노드/엣지로 직결 |
| 구현·유지보수 | 초기 쉬움, 예외 늘수록 어려움 | 초기 유연, 검증·쿼리·운영 복잡 | 현재 11테이블을 활용해 변경 폭이 작고 복합 규칙의 검증 설계는 필요 |

**권장: C 혼합형의 점진 보완.** 현재 DB는 이미 순수 컬럼형이 아니라 `card_cond` 다중 행·JSON과 `card_bnft_cond` 관계를 가진 혼합형에 가깝다. PDF에서 실적에 따라 달라지는 것은 주로 한도이며, 대상 수와 공유 범위가 다양하다. 따라서 수치 핵심 컬럼은 유지하고 대상·구간·연결을 명시적으로 관리한다. A는 단순 혜택에 빠르고 타입 검증이 좋지만 C3의 4개 조합과 C4의 공유 한도를 열로 늘리기 어렵다. B는 예측 못 한 후보를 담기 쉽지만 수치 단위, 그룹 한도, 조건식의 정합성 검증이 더 어렵고 이미 존재하는 정형 스키마를 버릴 이유가 없다.

## 6. 권장 모델: 유지·최소 수정·추가·삭제 후보

| 조치 | 대상 | 이유·권장 의미 |
|---|---|---|
| 유지 | `card_doc`, `card_doc_page`, `card_doc_chunk`, `card_extr_stg`, `card_ai_run`, `card_ai_call` | 페이지→청크→실행/호출→후보→확정의 추적 골격이 존재. 원문 위치·해시 유지. |
| 유지 | `card_bnft`, `card_cond`, `card_bnft_cond`, `card_excl_item`, `card_excl_item_als` | 혜택 핵심 수치와 제외 개념, N:M 관계를 이미 지원. 특히 `card_bnft_cond`를 삭제하거나 중복 생성하지 않음. |
| 추가 후보 | `card_bnft_target(card_doc_id,card_bnft_id,target_seq,target_type_cd,target_nm,role_cd,target_rate,source_chunk_id,evidence_txt,...)` | 편의점·커피·공과금·특별 적립 영역을 검색 가능한 대상별 행으로 보존. 대상별 적립률은 필요할 때만 `target_rate numeric`에 기록. `(card_doc_id,card_bnft_id,target_seq)` PK; 원문 순서/표기와 혜택 버전 유지. |
| 제한적 수정 후보 | `card_cond` 적용 범위 `SHARED` 허용 또는 별도 `cond_scope_cd` 추가 | 카드 전체 원칙과 특정 여러 혜택의 공유를 구분. `card_bnft_cond`를 실효 적용 범위의 기준으로 삼고, 기존 `card_bnft_id`가 있으면 링크와 일치하는지 검증. 한도 공유 표시는 `cond_rule_json`의 `aggregation_scope='SHARED'`, `pool_key`, `unit` 등으로 시작. |
| 제한적 수정 후보 | 후보 출처 구분 | 현재 `card_extr_stg`는 AI 실행·호출 키가 필수라 정규식/수작업 후보를 자연스럽게 담기 어렵다. `run_call_mthd_cd`에 REGEX/MANUAL을 허용하고 AI 전용 호출과 구별하거나, 별도 범용 추출 실행 키를 둔다. 가짜 LLM 실행으로 기록하지 않는다. |
| 조건부 추가 후보 | `card_cond_group` 또는 한도 풀 테이블 | 중첩 AND/OR와 여러 구간의 공유 한도를 JSON 규칙만으로 검증하기 어려운 사례가 누적될 때 도입. 이번 8종만으로 즉시 필수라고 단정하지 않음. |
| 삭제 후보 | 없음 | 실데이터·사용 코드 영향 조사 없이 기존 테이블/컬럼 제거하지 않음. `card_cond.card_bnft_id`는 관계와 중복되어 장기 검토 대상이지만 현 단계 삭제 권장 아님. |

제안하는 **논리적 저장 규칙**: `card_bnft`는 고객에게 설명할 혜택 단위, `card_bnft_target`은 대상별 다중 행, `card_cond`는 문서 버전 내 정책 인스턴스, `card_bnft_cond`는 실효 적용 관계다. TIER 행은 `[min,max)` 경계를 기본으로 하되 원문의 `이상/미만`을 별도 기록한다. 같은 혜택의 일반/계절 한도는 구간×기간별 조건 행으로 두고 `cond_rule_json`에 `month_basis='ACQUISITION'`, `months=[2,3,8,9]` 등을 기록한다. `cond_rule_json`의 표준 키, 단위와 집계 방식은 추후 제약·검증 SQL로 관리한다. 실적 산정 제외와 혜택 적용 제외는 서로 다른 `cond_type_cd`의 별도 행으로 만든다. 동일 문구가 다른 문서에 있어도 문서별 정책 ID를 재사용하지 않는다.

## 7. 실제 PDF 값을 넣은 **설계 예시** 3건

아래는 확정 적재가 아닌 논리 행 예시다. `C3`, `C4`, `D3`은 1절의 PDF ID이고, `B-*`, `K-*`는 가상 키다. 중략된 대상·제외 목록은 이 샘플에 저장되지 않았다는 뜻이므로 완전한 데이터 적재 예시가 아니다.

### 사례 1 — 에너지 더블 공과금 10%: 구간 × 계절

| 논리 테이블 | 키 | 주요 값 | 근거 |
|---|---|---|---|
| `card_bnft` | B-C3-UTILITY | `DISCOUNT`, `bnft_rate=10`, 에너지 공과금 청구할인 | C3 1쪽 공과금 표 |
| `card_bnft_target` | B-C3-UTILITY/1~3 | 아파트 관리비, 전기요금, 도시가스요금; 자동이체 조건 | C3 1쪽 대상 가맹점 |
| `card_cond` TIER | K-C3-1 | `PREV_MONTH_SPEND`, `[400000,800000)`, `cond_limit_amt=5000`, 일반월 | C3 1쪽 표 |
| `card_cond` TIER | K-C3-2 | `[400000,800000)`, `cond_limit_amt=10000`, 매입월 ∈ {2,3,8,9} | C3 1쪽 표·주석 |
| `card_cond` TIER | K-C3-3 | `[800000,∞)`, `cond_limit_amt=10000`, 일반월 | C3 1쪽 표 |
| `card_cond` TIER | K-C3-4 | `[800000,∞)`, `cond_limit_amt=20000`, 매입월 ∈ {2,3,8,9} | C3 1쪽 표·주석 |
| `card_bnft_cond` | 4행 | B-C3-UTILITY ↔ K-C3-1..4 | 네 구간 중 한 행만 적용하도록 배타성 검증 |

표의 `월 통합 할인한도`는 세 공과금 대상 각각의 별도 한도가 아니라 합산 한도다. `cond_rule_json`에 `aggregation_scope=SHARED_BY_BENEFIT`, `period=MONTH`, `amount_unit=KRW`, 매입월 기준을 명시한다. 원문에서 한도 적용 달이 **매입 시점**이라는 점을 결제 승인월과 바꾸지 않는다.

### 사례 2 — JADE Classic 특별 적립: 대상별 비율 + 월 통합 한도

| 논리 테이블 | 키 | 주요 값 | 근거 |
|---|---|---|---|
| `card_bnft` | B-C4-SPECIAL | `POINT`, `bnft_rate=NULL` 또는 대표율 미설정 | C4 3쪽 영역별 1.5~1.2% |
| `card_bnft_target` | B-C4-SPECIAL/1~N | 해외·항공·면세·여행 `target_rate=1.5`; 온라인쇼핑·백화점/아울렛·마트·주유 `target_rate=1.2`의 대상별 행 | C4 3쪽 표; 실제 세부 가맹점은 원문별 행으로 확장 |
| `card_cond` SPEND_REQ | K-C4-SPEND | `cond_min_amt=500000`, 지난달 실적 | C4 3쪽 특별 적립 제목 |
| `card_cond` LIMIT | K-C4-POOL | `cond_limit_amt=100000`, 월, 하나머니, `aggregation_scope=SHARED`, `pool_key=C4_SPECIAL_MONTH` | C4 3쪽 `월 통합 적립 한도 10만 하나머니` |
| `card_bnft_cond` | 2행 | B-C4-SPECIAL ↔ K-C4-SPEND/K-C4-POOL | 혜택-조건 관계 |

`card_bnft_target`에 대상별 비율을 두는 것은 **추가 테이블 제안의 열 설계**다. 동일 혜택 행 하나에 1.5와 1.2를 동시에 `bnft_rate`로 넣을 수 없다. 대상별 비율을 `card_cond` MERCHANT_RULE 행으로 표현하는 대안도 가능하지만, 대상과 수치를 함께 조회할 때 명시적 대상 행이 간결하다. 라운지의 연 3회·일 3회와 디지털 컨텐츠 50%/월 1만 하나머니는 **별도 혜택·조건**이다. 이 특별 적립 한도에 합치지 않는다.

### 사례 3 — ONE PICK STYLE: 실적 없는 정액 혜택과 실적 있는 ONE MORE

| 논리 테이블 | 키 | 주요 값 | 근거 |
|---|---|---|---|
| `card_bnft` | B-D3-PICK | `CASHBACK`, `bnft_amt=100`, 편의점·카페 | D3 1쪽 ONE PICK 표 |
| `card_bnft_target` | B-D3-PICK/1~6 | CU·GS25·세븐일레븐·메가MGC커피·이디야커피·컴포즈커피 | D3 1쪽 대상 가맹점 |
| `card_cond` + 링크 | K-D3-PICK | 거래 3,000원 이상, 일 1회·월 30회, **공유 월 5,000원**, 전월 실적 없음 | D3 1쪽 표 |
| `card_bnft` | B-D3-TRANSIT | `CASHBACK`, `bnft_rate=5`, 버스·지하철 | D3 1쪽 ONE MORE 표 |
| `card_cond` + 링크 | K-D3-TRANSIT | 지난달 100,000원 이상, 월 한도 1,000원 | D3 1쪽 표 |
| `card_bnft` | B-D3-PARK | `CASHBACK`, `bnft_rate=50`, 에버랜드·롯데월드 | D3 1쪽 ONE MORE 표 |
| `card_cond` + 링크 | K-D3-PARK | 지난달 200,000원 이상, 월 1회·연 2회 | D3 1쪽 표 |

공통 `BNFT_EXCL`(상품권·충전 등)은 적용되는 혜택과만 연결한다. 대중교통 전용 `BNFT_EXCL`(시외버스·고속버스·철도)은 B-D3-TRANSIT에 연결한다. K-D3-TRANSIT/PARK를 B-D3-PICK에 연결하지 않는다. `CARD`로 기록된 실적 산정 제외의 **존재**가 실적 요구가 없는 혜택에 자동으로 실적 기준을 부여하지 않는다.

## 8. 후보→확정 추적과 물리 FK 없는 검증

현재 골격은 `card_doc(doc_sha256,version)` → `card_doc_page(page_no,page_txt_sha256)` → `card_doc_chunk(start/end,raw/clean)` → `card_ai_run/card_ai_call` → `card_extr_stg(raw,normalized,evidence,review,status)` → `card_bnft/card_cond(card_extr_stg_id,evidence)` → `card_bnft_cond`이다. 정규식·수작업도 후보 원문·추출 방법·규칙 버전·검수자·승인 시각을 남기고 **승인된 후보만 확정 테이블**로 보내야 한다. 수작업 검증 결과를 AI 검증으로 오기하지 않는다. 페이지/청크 위치는 실제 추출된 문자열의 오프셋과 비교하고, 이미지 기반 표 판독은 원본 쪽과 판독 방법을 기록한다. 수정된 상품설명서는 새 `card_doc` 버전으로 다루며 과거 판을 덮어쓰지 않는다.

물리 FK를 만들지 않는 원칙은 유지한다. 대신 적재 전/후 읽기 전용 SQL로 **존재·문서 버전·카드 ID·조건 범위·중복·근거 위치**를 검사하고 실패 행을 승인하지 않는다. `card_bnft_cond`의 세 ID가 같은 문서 버전의 부모에 존재하는지, `card_cond.card_bnft_id`가 있을 때 링크의 혜택과 맞는지, SHARED/LIMIT 행이 의도한 혜택 집합에 한 번만 연결되는지 확인한다. DB에 `card_benefit.card_product`가 현재 없으므로 상품 마스터 연계 검사도 별도 배포·접속 대상 확인 전에는 통과했다고 주장하지 않는다.

### SELECT 예시 1 — 현재 DB에서 대표 혜택의 조건 확인

```sql
-- 읽기 전용. :doc_id는 확인된 card_doc_id로 바꾼다. 행이 없으면 미적재일 수 있다.
SELECT b.card_doc_id, b.card_bnft_id, b.bnft_nm, b.bnft_type_cd,
       b.bnft_rate, b.bnft_amt, c.card_cond_id, c.cond_type_cd,
       c.cond_apply_lvl_cd, c.cond_min_amt, c.cond_max_amt,
       c.cond_rate, c.cond_limit_amt, c.cond_limit_cnt,
       c.cond_period_cd, c.cond_rule_json, c.cond_evidence_txt
FROM db_pipeline.card_bnft AS b
LEFT JOIN db_pipeline.card_bnft_cond AS bc
  ON (bc.card_doc_id, bc.card_bnft_id) = (b.card_doc_id, b.card_bnft_id)
LEFT JOIN db_pipeline.card_cond AS c
  ON (c.card_doc_id, c.card_cond_id) = (bc.card_doc_id, bc.card_cond_id)
WHERE b.card_doc_id = :doc_id
  AND b.bnft_status = 'CONFIRMED'
ORDER BY b.bnft_nm, c.cond_type_cd, c.cond_min_amt;
```

### SELECT 예시 2 — 물리 FK 없는 관계의 고아·앵커 불일치

```sql
SELECT bc.card_doc_id, bc.card_bnft_id, bc.card_cond_id,
       CASE WHEN b.card_bnft_id IS NULL THEN 'MISSING_BENEFIT'
            WHEN c.card_cond_id IS NULL THEN 'MISSING_CONDITION'
            WHEN b.card_id <> c.card_id THEN 'CARD_ID_MISMATCH'
            WHEN c.card_bnft_id IS NOT NULL
                 AND c.card_bnft_id <> bc.card_bnft_id THEN 'ANCHOR_MISMATCH'
       END AS issue
FROM db_pipeline.card_bnft_cond AS bc
LEFT JOIN db_pipeline.card_bnft AS b
  ON (b.card_doc_id, b.card_bnft_id) = (bc.card_doc_id, bc.card_bnft_id)
LEFT JOIN db_pipeline.card_cond AS c
  ON (c.card_doc_id, c.card_cond_id) = (bc.card_doc_id, bc.card_cond_id)
WHERE b.card_bnft_id IS NULL OR c.card_cond_id IS NULL
   OR b.card_id <> c.card_id
   OR (c.card_bnft_id IS NOT NULL AND c.card_bnft_id <> bc.card_bnft_id);
```

### SELECT 예시 3 — C3 유형의 구간 겹침·빠진 연결 후보

```sql
-- 같은 혜택의 TIER 구간이 겹치는 경우를 먼저 찾는다.
-- 일반월/더블월처럼 기간 집합이 다른 행은 cond_rule_json의 months를
-- 추가 비교해야 하므로 아래 결과는 검토 후보이지 확정 오류가 아니다.
SELECT a.card_doc_id, a.card_bnft_id, a.card_cond_id AS tier_a,
       z.card_cond_id AS tier_b,
       a.cond_min_amt, a.cond_max_amt, z.cond_min_amt, z.cond_max_amt
FROM db_pipeline.card_cond AS a
JOIN db_pipeline.card_cond AS z
  ON z.card_doc_id = a.card_doc_id
 AND z.card_bnft_id = a.card_bnft_id
 AND z.card_cond_id > a.card_cond_id
WHERE a.cond_type_cd = 'TIER' AND z.cond_type_cd = 'TIER'
  AND a.cond_min_amt < COALESCE(z.cond_max_amt, 1e30)
  AND z.cond_min_amt < COALESCE(a.cond_max_amt, 1e30);
```

새 `card_bnft_target`가 승인되면 대상 중복, 빈 대상명, 혜택/문서 불일치도 같은 방식으로 검사한다. 공유 한도는 동일 `card_cond_id`를 여러 혜택이 참조하는지를 조회하고 `cond_rule_json.aggregation_scope` 및 `pool_key`가 일치하는지 검증한다. SQL 결과만으로 PDF의 실제 해석이 맞다는 보증은 되지 않으므로 표·주석 수작업 검수를 유지한다.

## 9. 미확정 사항과 다음 원문 확인

1. 8종은 요청에서 특정되지 않아 대표 표본으로 선정했다. 실제 프로젝트의 최종 대상 카드가 따로 정해지면 그 목록으로 재대조해야 한다.
2. `URL추정확인` D3·D4의 원본 URL·수집 시점·파일 해시와 문서 현행성은 이 작업에서 확인하지 않았다. 저장소 PDF 내용만 근거로 사용했다.
3. C4의 세부 대상 가맹점 전체, 실적 예외·라운지 사용조건의 모든 문장을 이 보고서의 샘플 행에 전사하지 않았다. 실제 적재 전 C4 3~5쪽 표·각주를 문장 단위로 검수해야 한다.
4. D3·D4의 `월 1회/연 2회` 같은 작은 표 글씨 및 공통 예외의 정확한 적용 범위는 적재 전 원본 확대 렌더링과 카드사 최신 설명서로 재검수한다. D3·D4의 공통 문구가 동일하더라도 정책 인스턴스의 공동 변경을 추정하지 않는다.
5. 실적 구간별 **할인율** 변경은 이번 표본에 없었다. 이 유형을 설계 검증하려면 별도의 원문 사례를 확보해야 한다. 현재 설계는 `cond_rate` 구간 행으로 수용 가능하나 실증 사례로 기재하지 않는다.
6. 현재 접속 DB에는 `card_benefit` 스키마와 `card_product`가 없었다. 실제 상품 마스터의 배포 DB·스키마·연계 키는 별도 확인이 필요하다. 이 보고서에서는 물리 FK나 마스터 적재를 제안·실행하지 않는다.

## 부록. 조회된 전체 컬럼·제약·인덱스 목록

아래는 위 읽기 전용 카탈로그 조회의 요약 전사다. `!`는 NOT NULL, `?`는 NULL 허용이다. 길이/정밀도와 모든 기본값은 최신 백업의 원문 정의를 참조한다. COMMENT는 각 테이블·컬럼에 있는지 대조했으며 본문은 백업 SQL에 있다.

### `card_ai_call`

컬럼: `card_ai_run_id varchar!`, `card_doc_id varchar!`, `page_no smallint!`, `card_doc_chunk_id varchar!`, `call_seq smallint!`, `call_input_sha256 varchar!`, `call_status varchar!`, `call_resp_raw text?`, `call_resp_json jsonb?`, `call_error_msg text?`, `call_input_token_cnt integer?`, `call_output_token_cnt integer?`, `call_latency_ms integer?`, `call_req_date timestamptz!`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_ai_call_call_seq_check` (CHECK), `card_ai_call_call_status_check` (CHECK), `card_ai_call_check` (CHECK), `card_ai_call_pkey` (PK).

인덱스: `card_ai_call_pkey`, `ix_card_ai_call_chunk_key`, `ix_card_ai_call_doc_chunk_key`.

COMMENT 대상: 19개(테이블 1, 컬럼 18).

### `card_ai_run`

컬럼: `card_ai_run_id varchar!`, `run_stage_cd varchar!`, `run_call_mthd_cd varchar!`, `run_model_nm varchar!`, `run_prompt_ver varchar!`, `run_prompt_txt text!`, `run_param jsonb?`, `run_target_card_doc_id varchar?`, `run_status varchar!`, `run_start_date timestamptz!`, `run_end_date timestamptz?`, `run_note text?`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_ai_run_check` (CHECK), `card_ai_run_pkey` (PK), `card_ai_run_run_call_mthd_cd_check` (CHECK), `card_ai_run_run_stage_cd_check` (CHECK), `card_ai_run_run_status_check` (CHECK).

인덱스: `card_ai_run_pkey`, `ix_card_ai_run_doc_key`.

COMMENT 대상: 17개(테이블 1, 컬럼 16).

### `card_bnft`

컬럼: `card_doc_id varchar!`, `card_bnft_id varchar!`, `card_id bigint!`, `bnft_nm text!`, `bnft_grp_nm text?`, `bnft_type_cd varchar!`, `bnft_target_txt text?`, `bnft_rate numeric?`, `bnft_amt numeric?`, `bnft_value_txt text?`, `card_doc_chunk_id varchar!`, `bnft_evidence_txt text!`, `bnft_evidence_start_pos integer!`, `bnft_evidence_end_pos integer!`, `card_extr_stg_id varchar!`, `bnft_status varchar!`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_bnft_bnft_status_check` (CHECK), `card_bnft_bnft_type_cd_check` (CHECK), `card_bnft_card_bnft_id_key` (UNIQUE), `card_bnft_card_doc_id_bnft_nm_key` (UNIQUE), `card_bnft_card_extr_stg_id_key` (UNIQUE), `card_bnft_check` (CHECK), `card_bnft_pkey` (PK).

인덱스: `card_bnft_card_bnft_id_key`, `card_bnft_card_doc_id_bnft_nm_key`, `card_bnft_card_extr_stg_id_key`, `card_bnft_pkey`, `ix_card_bnft_card_key`.

COMMENT 대상: 21개(테이블 1, 컬럼 20).

### `card_bnft_cond`

컬럼: `card_doc_id varchar!`, `card_bnft_id varchar!`, `card_cond_id varchar!`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_bnft_cond_pkey` (PK).

인덱스: `card_bnft_cond_pkey`, `ix_card_bnft_cond_cond_key`.

COMMENT 대상: 4개(테이블 1, 컬럼 3).

### `card_cond`

컬럼: `card_doc_id varchar!`, `card_cond_id varchar!`, `card_id bigint!`, `card_bnft_id varchar?`, `cond_apply_lvl_cd varchar!`, `cond_type_cd varchar!`, `card_excl_item_id varchar?`, `cond_excl_raw_txt text?`, `cond_basis_cd varchar!`, `cond_min_amt numeric?`, `cond_max_amt numeric?`, `cond_rate numeric?`, `cond_amt numeric?`, `cond_limit_amt numeric?`, `cond_limit_cnt integer?`, `cond_period_cd varchar!`, `cond_modality_cd varchar!`, `cond_value_txt text?`, `cond_target_txt text?`, `cond_natural_key varchar!`, `cond_policy_cand_key varchar?`, `card_doc_chunk_id varchar!`, `cond_evidence_txt text!`, `cond_evidence_start_pos integer!`, `cond_evidence_end_pos integer!`, `card_extr_stg_id varchar!`, `cond_status varchar!`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`, `cond_rule_json jsonb!`.

제약: `card_cond_card_cond_id_key` (UNIQUE), `card_cond_card_doc_id_cond_natural_key_key` (UNIQUE), `card_cond_card_extr_stg_id_key` (UNIQUE), `card_cond_check` (CHECK), `card_cond_check1` (CHECK), `card_cond_check2` (CHECK), `card_cond_check3` (CHECK), `card_cond_cond_basis_cd_check` (CHECK), `card_cond_cond_modality_cd_check` (CHECK), `card_cond_cond_period_cd_check` (CHECK), `card_cond_cond_status_check` (CHECK), `card_cond_cond_type_cd_check` (CHECK), `card_cond_pkey` (PK).

인덱스: `card_cond_card_cond_id_key`, `card_cond_card_doc_id_cond_natural_key_key`, `card_cond_card_extr_stg_id_key`, `card_cond_pkey`, `ix_card_cond_bnft_key`, `ix_card_cond_card_key`, `ix_card_cond_excl_item_key`, `ix_card_cond_policy_key`.

COMMENT 대상: 33개(테이블 1, 컬럼 32).

### `card_doc`

컬럼: `card_doc_id varchar!`, `card_id bigint!`, `doc_cd varchar!`, `doc_type_cd varchar!`, `doc_title text!`, `doc_source_url text?`, `doc_file_nm text!`, `doc_file_size bigint?`, `doc_sha256 varchar!`, `doc_page_cnt smallint?`, `doc_review_no text?`, `doc_review_date date?`, `doc_release_date date?`, `doc_collect_date timestamptz!`, `doc_version_no smallint!`, `doc_status varchar!`, `doc_note text?`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_doc_card_id_doc_type_cd_doc_version_no_key` (UNIQUE), `card_doc_doc_cd_key` (UNIQUE), `card_doc_doc_page_cnt_check` (CHECK), `card_doc_doc_sha256_check` (CHECK), `card_doc_doc_sha256_key` (UNIQUE), `card_doc_doc_status_check` (CHECK), `card_doc_doc_type_cd_check` (CHECK), `card_doc_doc_version_no_check` (CHECK), `card_doc_pkey` (PK).

인덱스: `card_doc_card_id_doc_type_cd_doc_version_no_key`, `card_doc_doc_cd_key`, `card_doc_doc_sha256_key`, `card_doc_pkey`, `uq_card_doc_active`.

COMMENT 대상: 22개(테이블 1, 컬럼 21).

### `card_doc_chunk`

컬럼: `card_doc_id varchar!`, `page_no smallint!`, `card_doc_chunk_id varchar!`, `chunk_seq integer!`, `chunk_section_nm text?`, `chunk_type_cd varchar!`, `chunk_start_pos integer!`, `chunk_end_pos integer!`, `chunk_raw_txt text!`, `chunk_clean_txt text?`, `chunk_status varchar!`, `chunk_split_rule_ver varchar!`, `chunk_clean_rule_ver varchar?`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_doc_chunk_card_doc_chunk_id_key` (UNIQUE), `card_doc_chunk_card_doc_id_chunk_seq_key` (UNIQUE), `card_doc_chunk_check` (CHECK), `card_doc_chunk_check1` (CHECK), `card_doc_chunk_chunk_seq_check` (CHECK), `card_doc_chunk_chunk_status_check` (CHECK), `card_doc_chunk_chunk_type_cd_check` (CHECK), `card_doc_chunk_pkey` (PK).

인덱스: `card_doc_chunk_card_doc_chunk_id_key`, `card_doc_chunk_card_doc_id_chunk_seq_key`, `card_doc_chunk_pkey`.

COMMENT 대상: 18개(테이블 1, 컬럼 17).

### `card_doc_page`

컬럼: `card_doc_id varchar!`, `page_no smallint!`, `page_raw_txt text!`, `page_char_cnt integer!`, `page_txt_sha256 varchar!`, `page_layer_cd varchar!`, `page_extractor_nm varchar!`, `page_extractor_ver varchar?`, `page_note text?`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_doc_page_page_char_cnt_check` (CHECK), `card_doc_page_page_layer_cd_check` (CHECK), `card_doc_page_page_no_check` (CHECK), `card_doc_page_pkey` (PK).

인덱스: `card_doc_page_pkey`.

COMMENT 대상: 14개(테이블 1, 컬럼 13).

### `card_excl_item`

컬럼: `card_excl_item_id varchar!`, `issuer text!`, `excl_item_nm text!`, `excl_concept_cd varchar?`, `excl_item_desc text?`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_excl_item_issuer_excl_item_nm_key` (UNIQUE), `card_excl_item_pkey` (PK).

인덱스: `card_excl_item_issuer_excl_item_nm_key`, `card_excl_item_pkey`, `ix_card_excl_item_concept_key`.

COMMENT 대상: 10개(테이블 1, 컬럼 9).

### `card_excl_item_als`

컬럼: `card_excl_item_id varchar!`, `card_excl_item_als_id varchar!`, `excl_item_als_nm text!`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_excl_item_als_card_excl_item_id_excl_item_als_nm_key` (UNIQUE), `card_excl_item_als_pkey` (PK).

인덱스: `card_excl_item_als_card_excl_item_id_excl_item_als_nm_key`, `card_excl_item_als_pkey`.

COMMENT 대상: 8개(테이블 1, 컬럼 7).

### `card_extr_stg`

컬럼: `card_ai_run_id varchar!`, `card_doc_id varchar!`, `page_no smallint!`, `card_doc_chunk_id varchar!`, `call_seq smallint!`, `card_extr_stg_id varchar!`, `stg_item_seq smallint!`, `card_id bigint!`, `stg_kind_cd varchar!`, `stg_parent_card_extr_stg_id varchar?`, `stg_raw_item jsonb!`, `stg_normalized_item jsonb?`, `stg_evidence_txt text!`, `stg_evidence_start_pos integer?`, `stg_evidence_end_pos integer?`, `card_excl_item_id varchar?`, `stg_sql_check_cd varchar?`, `stg_ai_vrfy_cd varchar?`, `stg_ai_vrfy_card_ai_run_id varchar?`, `stg_status varchar!`, `stg_review_note text?`, `stg_approved_date timestamptz?`, `stg_approved_user_id varchar?`, `create_date timestamptz!`, `create_user_id varchar!`, `update_date timestamptz!`, `update_user_id varchar!`.

제약: `card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key` (UNIQUE), `card_extr_stg_card_extr_stg_id_key` (UNIQUE), `card_extr_stg_check` (CHECK), `card_extr_stg_check1` (CHECK), `card_extr_stg_pkey` (PK), `card_extr_stg_stg_ai_vrfy_cd_check` (CHECK), `card_extr_stg_stg_item_seq_check` (CHECK), `card_extr_stg_stg_kind_cd_check` (CHECK), `card_extr_stg_stg_status_check` (CHECK).

인덱스: `card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key`, `card_extr_stg_card_extr_stg_id_key`, `card_extr_stg_pkey`, `ix_card_extr_stg_chunk_key`, `ix_card_extr_stg_excl_item_key`, `ix_card_extr_stg_status_key`.

COMMENT 대상: 28개(테이블 1, 컬럼 27).
