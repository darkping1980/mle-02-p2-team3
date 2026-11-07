# chat/retrieval/

챗봇 검색 결과를 다듬는 보조 도구다. `fp_chat_patch.py` 가 이 모듈들을 불러 쓴다. 단독 실행 명령은 없다.

| 파일 | 역할 |
|---|---|
| `entity_dedupe.py` | 검증된 동일 카드 내 `SAME_AS_STRONG` 연결을 사용해 검색 서브그래프를 병합한다. |
| `seed_union.py` | 검색 시작점(시드) 후보를 결정적으로 합쳐 보완한다. |
| `source_label.py` | 문서 파일명에서 사람이 읽는 출처 라벨을 만들어 서브그래프에 붙인다. |

임포트는 `payment_card.file_pipeline.chat.retrieval.<모듈>` 이다. 스크립트식 임포트(`from retrieval.<모듈> import ...`)가 필요하면 `PYTHONPATH` 에 `chat/` 폴더를 포함한다.
