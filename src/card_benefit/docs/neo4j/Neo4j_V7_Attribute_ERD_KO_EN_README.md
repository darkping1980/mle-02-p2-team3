# 하나카드 GraphRAG Neo4j 영문·한글 병기 ERD

- 기준: 사용자가 제공한 Neo4j Cypher 1~6 결과(124 nodes, 196 relationships) 및 2026-11-03 PostgreSQL DDL.
- 13개의 개별 노드 라벨과 14개 관계 타입(19개 출발·도착 조합)을 표시했습니다. `dp_node`는 124개 전체 노드에 붙는 공통 라벨이므로 추가 노드로 표시하지 않았습니다.
- 노드 제목: `dp_card_common_bnft` + `공통서비스 혜택` 같은 2행 병기.
- 속성: `card_common_bnft_id` + `공통 혜택 아이디` 같은 별도 열 병기.
- 관계: `dp_belongs_to` + `공통서비스에 속함` 같은 2행 병기.
- 한글 열은 PostgreSQL DDL의 COMMENT를 우선하고, `dp_cond_*` 등 그래프 전용 객체는 변환 결과의 의미에 따라 보충했습니다.
- S / I / B는 실제 Neo4j에서 관측된 String / Integer / Boolean 타입이며 DB NOT NULL 의미가 아닙니다. `●`는 NODE KEY.
- Neo4j `dp_supported_by.ev_link_id`는 PostgreSQL 최신 `evidence_link_id`와 아직 이름이 다릅니다. 실제 구조 그대로 표기했습니다.
- `dp_card_source_evidence`는 Neo4j NODE KEY `evidence_id`, PostgreSQL은 4컬럼 PK이며 현재 불일치는 그대로 설명합니다.
- 최신 PostgreSQL 신규 문서 14건은 현재 제공된 Neo4j 실측 124/196에 반영되지 않았습니다.

## 파일
- `...All_Attributes...svg/png`: 전체 13노드 속성·관계 지도
- `...Business...svg/png`: 카드/혜택/조건 확대본
- `...Document_Evidence...svg/png`: 문서/근거 확대본
- `.drawio`: 편집 가능한 노드, 속성 및 관계선
- `.pptx`: 6장 발표용 요약
- `.csv`: 한글·영문 속성명 대응표

이 파일은 ERD 문서화용이며 실제 DB나 Neo4j에 아무런 변경을 가하지 않습니다.
