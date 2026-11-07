# 지식그래프 CSV 변환·적재 스크립트

- PC: laptop

## 한 일

- `graph/export.py`에 추출 결과 JSON과 청크·인덱스 연결, 네 종류 `pf_*.csv` 생성, 행 검증 및 숫자 요약을 추가했다.
- `graph/load.py`에 기본 드라이런과 `PF_DATABASE_URL`을 통한 명시적 실행 경로를 추가했다. 실행 경로의 쓰기 허용 목록은 `pf_load_runs`, `pf_nodes`, `pf_edges`, `pf_evidence`로 고정했다.
- CSV 테스트 두 파일을 추가하고 README의 폴더 구성과 작업이력 인덱스를 갱신했다.

## 검증

- 직접 확인: `/etc/machine-id` 앞 8자는 `a6629f64`였다.
- 직접 확인: 샘플 디렉터리에 결과 20개와 청크 JSON 95개가 있었다. 내용은 구조만 확인했고 인용문은 기록하지 않았다.
- 테스트: 지정한 추출·그래프 테스트 61개 통과.
- 실제 export: `/tmp/graph_csv`에 생성. 청크 20, 노드 198, 간선 220, 근거 343, 건너뜀 1, 제외 행 0. quote 상태는 located 328, ambiguous 13, missing 2.
- 지정한 `~/pilot_work/graph_csv` 출력은 읽기 전용 파일시스템 오류로 실패했고 `/tmp/graph_csv` 대체 출력은 성공했다. CSV에는 인용문 문자열이 없다.
- load는 드라이런만 수행하며 DB에는 접속하지 않는다.

## 직접 확인과 추측

- 직접 확인: 스키마 초안은 `OFFERS`의 Card→Benefit 연결과 제시한 관계 타입별 끝점 조합을 정의한다.
- 직접 확인: `product_docs.csv`의 `product_ids`에는 CD_ID 등 복수 상품 키가 있을 수 있다.
- 직접 확인: `pyproject.toml`에 `psycopg[binary,pool]`이 이미 선언되어 있어 의존성을 추가하지 않았다.
- 추측/기본값: Card ID는 issuer와 우선순위가 가장 높은 상품 키(CD_ID, PC_SEQ, 디자인코드, 모바일_CD_NO 순)를 조합한다. 이 키의 팀 표준 확정이 필요하다.
- 추측/기본값: `run_id` 기본값은 결과 폴더 이름과 UTC 실행 시각을 결합한다.

## 못 한 것

- 실제 Supabase 적재 및 DB 연결은 수행하지 않았다.
- Issuer→Card 관계 유형은 스키마에 없어 만들지 않았다.
- 스키마 초안에서 발견한 불일치는 없다.

## 다음 할 일

- 팀에서 Issuer 관계 유형, PostgreSQL 드라이버 의존성, `pf_` 접두사 충돌 여부와 Card 상품 키를 합의한다.
- 합의 후 별도 승인된 환경에서 실제 적재 계정과 RLS 접근 정책을 검토한다.
