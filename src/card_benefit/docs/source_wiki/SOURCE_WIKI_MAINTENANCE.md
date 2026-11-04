# Source Wiki 유지보수·확장 가이드

> **문서 목적:** 하나·우리카드 GraphRAG 프로젝트의 `source_wiki`를 앞으로 수정·확장할 때, 기존 계층형 Markdown 디자인과 VS Code 로컬 소스 탐색 기능을 일관되게 유지하기 위한 작업 규약입니다.  
> **정리 기준일:** 2026-11-04  
> **소스 분석 기준 커밋:** `7b37de03b17a9671d703f183ec83b386c78d98f7` (기존 소스 위키의 분석 기준; 이후 로컬 소스는 달라질 수 있음)  
> **상태 표기:** 아래 구현 결과 및 검사 수치는 Codex 작업 보고를 바탕으로 한 것으로, 이 문서 자체가 재검증을 수행한 것은 아닙니다.

## 1. 이 위키를 만든 이유

- 목적은 단순한 개발 소개가 아니라 **프로세스 → 실행 단계 → 파일 → 클래스 → 메서드 → Repository → SQL/Cypher → DB 스키마·검증**을 따라가면서 실제 소스를 학습하는 것입니다.
- 데이터베이스 구조를 이미 이해한 학습자가 Python / LangGraph 실행 흐름을 역추적할 수 있도록 합니다.
- 전체 흐름을 설명하는 다이어그램은 보조적으로 쓰고, 탐색은 **나무위키식 계층형 접기/펼치기**를 기본으로 합니다.
- 운영 DB에 연결해 확인하지 않은 스키마나 데이터 상태를 **검증 완료로 기록하지 않습니다.**

## 2. 디렉터리와 파일 역할

프로젝트 루트: `D:\Bootcamp\vscode\workspace\mle-02-p2-team3`

```text
src/card_benefit/docs/source_wiki/
├── README.md                         # 전체 목차 / 탐색 시작점
├── 01_PDF_REGISTRATION.md            # PDF 등록
├── 02_AI_EXTRACTION.md               # AI 추출
├── 03_BENEFIT_REGISTRATION.md        # 혜택 등록
├── 04_EVIDENCE_VALIDATION.md         # 근거 검증
├── 05_EMBEDDING.md                   # 임베딩
├── 06_POSTGRESQL_SCHEMA.md           # PostgreSQL 스키마 / 제약
├── 07_NEO4J_SYNC.md                  # Neo4j 동기화
├── 08_GRAPHRAG_QUERY.md              # GraphRAG 조회
├── 09_ANSWER_VALIDATION.md           # 답변 검증
├── 10_EXECUTION_REFERENCE.md         # 실행 참조
├── source_wiki.css                   # VS Code Markdown Preview 스타일
└── SOURCE_WIKI_MAINTENANCE.md        # 이 관리 가이드
```

- **기존 `README.md`는 위키 목차**로 유지합니다. 이 파일은 작성·수정 규칙을 관리하므로 역할이 다릅니다.
- 문서가 추가되면 `README.md`의 목차에도 링크를 추가합니다.
- 기존 `docs/guide` 등 다른 가이드 문서와 분석 대상 Python·SQL 파일은 별도 관리합니다.

## 3. 화면 구성 원칙

### 3.1 기본 Markdown Preview만 사용

- VS Code에서 문서를 연 뒤 `Ctrl + Shift + V`로 미리보기를 엽니다.
- 별도 MkDocs, 웹서버, 브라우저, 추가 확장 프로그램을 **필수 구성요소로 사용하지 않습니다.**
- 접기/펼치기는 HTML `<details>` / `<summary>`를 사용합니다.
- 카드형 배경·테두리·여백·타이포그래피는 `source_wiki.css`에서 통합 관리합니다.
- CSS는 VS Code 테마 색상 변수를 사용해 밝은/어두운 테마에 대응하도록 작성합니다. **다크 테마는 별도 화면 검증이 필요합니다.**

### 3.2 계층 구조

1. 프로세스
2. 실행 단계 또는 모듈(파일)
3. 클래스 / 함수 / 메서드
4. 내부 분기 및 호출 관계
5. SQL·Cypher statement / 관련 테이블 / 스키마 / 트랜잭션 / 검증

접힌 상태에서는 제목만 보고 전체를 훑을 수 있어야 하고, 펼친 상태에서는 실제 실행 경로를 따라갈 수 있어야 합니다. 상세 설명은 하위에 배치하고 상위 제목은 길지 않게 유지합니다.

### 3.3 접기 블록 예시

````markdown
<details>
<summary>1. PDF 등록 프로세스</summary>

<details>
<summary>1.1 RegisterService.register()</summary>

- 역할: PDF 중복 조회 및 등록 분기
- 로컬 소스: [register()](../../payment_card/db_pipeline/register_service.py#L88)
- 관련 SQL: [insert_doc](../../payment_card/db_pipeline/document_repository.sql#L20)
- 관련 테이블: `db_pipeline.card_doc`

</details>

</details>
````

**주의:** 예시는 형식 설명용으로, 줄 번호는 실제 소스 갱신 시 다시 확인해야 합니다. HTML 블록 안의 Markdown 렌더링은 VS Code 미리보기에서 실제로 시험합니다. `<summary>`에 `▶`, `▼` 같은 **수동 화살표를 넣지 않습니다.** 접기 아이콘은 브라우저 기본 표시 및 CSS가 관리해야 하며, 수동 표시를 넣으면 이중 화살표가 생깁니다.

## 4. VS Code 로컬 소스 링크 규칙

### 4.1 상대 경로 + 줄 번호

위키 폴더에서 대상 파일까지의 **상대 경로**를 이용합니다.

```markdown
[RegisterService.register()](../../payment_card/db_pipeline/register_service.py#L88)
[DocRepository.insert_doc()](../../payment_card/db_pipeline/document_repository.py#L52)
[SQL insert_doc](../../payment_card/db_pipeline/document_repository.sql#L20)
```

- `#L88`은 **VS Code 기본 Markdown 링크 처리기의 소스 위치 fragment** 방식입니다.
- 클릭하면 현재 로컬 작업 트리의 파일을 열도록 의도합니다.
- 새 코드를 추가하거나 수정한 후에는 **선언의 실제 줄 번호를 다시 계산**합니다.
- 파일이 열렸다는 사실과 **정확한 정의 줄로 이동했다는 사실**은 구분해서 확인합니다.
- 코드 위치가 변경되면 파일·함수·SQL statement의 로컬 링크를 함께 갱신합니다.

관련 VS Code 구현 참고:  
<https://github.com/microsoft/vscode/blob/main/extensions/markdown-language-features/src/util/openDocumentLink.ts>

### 4.2 GitHub 링크도 별도로 유지

- 학습용 기본 링크: **로컬 소스 링크**
- 기준 소스 확인용 보조 링크: **GitHub 기준 커밋 링크**
- 로컬 작업 트리와 분석 기준 커밋 사이에 줄 번호나 내용 차이가 있을 수 있습니다. 두 링크가 언제나 동일한 줄을 나타낸다고 가정하지 않습니다.
- GitHub 링크는 기준 커밋 SHA를 사용하는 편이 변경 가능한 `main` 링크보다 재현성이 높습니다.

### 4.3 SQL / Cypher / DDL 연결

- Python 호출 이름 → Repository 메서드 → 실제 Mapper의 `-- name:` / Cypher statement → 사용하는 테이블·노드·관계로 연결합니다.
- SQL Mapper에서는 **statement 이름과 선언 위치**를 확인합니다.
- DDL 초안 / 마이그레이션 / 실제 운영 DB 구조는 **서로 다른 근거**로 구분합니다.
- 운영 DB를 직접 확인하지 않았다면 `운영 DB 적용 여부 미확인`을 유지합니다.

## 5. VS Code 로컬 설정

프로젝트 루트의 `.vscode/settings.json`에서 기존 설정을 보존하고 다음 설정을 확인합니다.

```json
{
  "markdown.styles": [
    "src/card_benefit/docs/source_wiki/source_wiki.css"
  ],
  "markdown.links.openLocation": "beside"
}
```

- `markdown.styles`: Markdown Preview에 CSS를 로드합니다. **이 설정은 위키만이 아니라 같은 Workspace의 다른 Markdown 미리보기에도 영향을 줄 수 있습니다.**
- `markdown.links.openLocation: "beside"`: 로컬 링크를 옆 편집기 그룹에서 열도록 시도합니다. 이미 열려 있는 파일의 탭·그룹은 재사용될 수 있습니다.
- 설정값은 **예시**입니다. 기존 `.vscode/settings.json`이 있다면 파일 전체를 덮어쓰지 말고 해당 키를 병합합니다.
- 이 저장소는 `.vscode/`를 Git에서 무시하고 있으므로, 다른 PC에서 Clone한 경우 **설정 파일을 다시 구성해야 합니다.**
- CSS 파일을 수정해도 미리보기에 반영되지 않으면 미리보기를 닫고 다시 엽니다.

## 6. 방문 기록 뒤로가기

- 위키 내부의 `목차`, `이전 문서`, `다음 문서` 링크는 **고정 목적지로 이동**하는 링크입니다.
- 링크를 따라 이동한 **실제 순서를 역순으로 되돌리는 기능**은 Markdown 내부에서 구현하지 않습니다.
- VS Code 상단의 **뒤로가기 / 앞으로가기 탐색 버튼**을 사용합니다.
- 이 탐색 기록은 VS Code 편집기 위치 기반이므로, 브라우저의 페이지 방문 기록과 완전히 같지 않습니다. Markdown 내부의 접기/펼치기 상태까지 기억하지는 않습니다.

## 7. 새로운 소스·프로세스를 문서에 추가할 때

1. **현재 코드 확인:** 호출자, 클래스, 메서드, Repository, Mapper, 테이블/그래프 관계를 추적합니다.
2. **문서 위치 결정:** 기존 주제 문서에 새 `<details>` 항목을 추가하거나 필요한 경우 새 주제 문서를 만듭니다.
3. **계층 구성:** 프로세스 개요는 짧게, 함수별 구현/검증/트랜잭션은 하위에 배치합니다.
4. **링크 추가:** 실제 선언 줄의 로컬 상대 링크를 먼저, 기준 커밋 GitHub 링크를 보조로 제공합니다.
5. **DB 설명:** 소스상 참조 테이블과 실제 DB 적용 확인 여부를 구분합니다.
6. **목차 연결:** `README.md`와 관련 문서의 상호 링크를 갱신합니다.
7. **프리뷰 확인:** 중첩 접기, CSS, 화살표 중복, 한글·코드 블록 렌더링을 확인합니다.
8. **줄 이동 시험:** Python 클래스 1개, 메서드 1개, SQL statement 1개 이상을 직접 클릭합니다.
9. **정적 검사:** 상대 경로 존재, `#L` 범위, Python 선언, SQL/Cypher statement 정의 여부를 점검합니다.
10. **변경 범위 확인:** 새 문서와 CSS/설정 외에 애플리케이션 파일이 수정되지 않았는지 확인합니다.

## 8. 기존 작업 결과 요약 (Codex 보고 기준)

| 구분 | 보고 내용 | 주의 |
|---|---|---|
| 위키 문서 | README + 주제별 10개 문서 | 이후 별도 유지보수 가이드 추가 가능 |
| Python 코드 정의 링크 | 21개 | 정확한 클릭 이동은 환경별 확인 |
| PostgreSQL statement | 고유 21개, 로컬 링크 22개 | 중복 링크 포함 |
| Cypher statement | 4개 | 정의 위치 정적 검사 |
| `<summary>` 수동 화살표 | 49곳 제거 | 이중 화살표 방지 |
| Markdown 상대 링크 검사 | 183개, 대상 누락 0건 | 해당 작업 시점의 검사 결과 |
| 줄 번호 범위 검사 | 범위 밖 앵커 0건 | 코드가 바뀌면 재검증 |
| 디자인 | VS Code 밝은 테마에서 카드형 표시 확인 보고 | 다크 테마 미확인 |
| 소스 / DB 변경 | 변경하지 않았다고 보고 | Git diff와 실제 환경은 별도 확인 |

## 9. 향후 개선을 위한 체크리스트

- [ ] Markdown Preview에서 프로세스별 카드형 스타일이 유지되는가?
- [ ] `▶ ▼` 등 접기 아이콘이 중복되지 않는가?
- [ ] 로컬 Python 클래스·메서드 링크가 **정확한 선언 줄**로 이동하는가?
- [ ] SQL Mapper의 `-- name:` 위치로 이동하는가?
- [ ] Cypher/DDL 링크와 문서 간 링크가 유효한가?
- [ ] 새 코드를 반영했을 때 로컬 링크의 줄 번호를 갱신했는가?
- [ ] DDL 초안 / 마이그레이션 / 운영 DB 검증 여부가 구분되어 있는가?
- [ ] README 목차에 새 문서가 빠짐없이 연결되었는가?
- [ ] 다크 테마에서도 링크·테두리·배경 대비가 충분한가?
- [ ] 다른 PC에서 사용할 `.vscode/settings.json` 복원 방법이 안내되어 있는가?
- [ ] Python·SQL·DDL·데이터 및 Git 이력이 의도치 않게 변경되지 않았는가?

## 10. 향후 Codex 수정 작업에 붙일 공통 지시

> `src/card_benefit/docs/source_wiki/`를 개선하되, 이 `SOURCE_WIKI_MAINTENANCE.md`의 문서 구조·스타일·링크·검증 규칙을 먼저 읽으세요. **기존 분석 내용과 로컬 소스 `#L` 링크, 기준 커밋 GitHub 링크를 보존**하고, 새로운 메서드나 SQL을 추가할 때 실제 파일과 선언 줄을 확인하세요. `source_wiki.css`는 공통 디자인 파일이며, `<summary>` 수동 화살표는 금지합니다. 실제 운영 DB를 확인하지 않은 항목은 미확인으로 남기세요. Python·SQL·DDL·DB는 수정하지 말고, Git 커밋과 Push도 하지 마세요. 작업 후 수정 파일과 링크·Preview 검증 결과를 보고하세요.

---

**운영 원칙:** 위키는 코드 이해를 돕는 **소스 탐색 지도**입니다. 외형보다 정확한 호출 관계·근거·링크를 우선하며, 디자인 개선은 이 정확성을 훼손하지 않는 범위에서 진행합니다.
