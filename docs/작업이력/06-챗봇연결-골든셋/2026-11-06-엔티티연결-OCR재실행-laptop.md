# 엔티티 연결(독립 구현)과 우리카드 OCR 재실행

- 날짜: 2026-11-06
- PC: laptop
- 담당: file_pipeline (결과 A)

## 한 일

1. **엔티티 연결을 팀 스키마 변경 없이 구현**(결정 D5 "삭제하지 않고 연결로 처리"). `fp_edges`의 edge_type 제약과 팀 코드(`src/graphrag_chatbot`)는 건드리지 않았다.
   - `graph/entity_links.sql`: 별도 테이블 `public.fp_entity_links`와 읽기 뷰 `fp_chat.entity_groups` **초안**. 실행하지 않았다(사용자가 직접 실행). 롤백 구문은 주석.
   - `graph/entity_links_loader.py`: 연결 CSV 검증과 병합 매핑 생성. DB에 쓰는 기능 없음.
   - `chat/entity_dedupe.py`: 같은 묶음 노드를 한 항목으로 합치되 근거는 모두 보존. 카드 사이 묶음은 합치지 않는다.
   - `chat/fp_chat_patch.py`, `chat/app_v2.py`: 연결부. 기본 꺼짐. `FP_ENTITY_DEDUPE`와 `FP_ENTITY_LINKS_CSV`가 모두 있어야 적용.
   - 테스트 `test_file_pipeline_graph_entity_links.py`, 점검 노트북 `entity_links_check.ipynb`(출력 비움).
2. **매핑 표 생성**(저장소 밖 `~/pilot_work/eval-assets/entity-links*/`): 같은 카드 안 강한 후보 149묶음·멤버 330·줄어드는 노드 181, 카드 사이 914묶음·멤버 2,779·줄어드는 노드 1,865(병합 대상 아님, link_type SIMILAR).
3. **사람 검수 시트**(`~/pilot_work/eval-assets/human-review/`): 놓친 라벨 22, 맞힌 표본 30, 엔티티 묶음 20.
4. **우리카드 OCR 재실행**: 로컬 tesseract, 결과를 `~/pilot_work/eval-assets/ocr-woori/`에 저장(/tmp 아님).

## 직접 확인한 결과

- 표준 테스트: 236 passed (이전 231 + 신규 5).
- 같은 카드 안 매핑: 149묶음, 330멤버, 감소 181, 한 노드가 두 묶음에 속하지 않음, 대표가 멤버에 포함. 두 번 생성 해시 동일.
- 카드 사이 매핑: 914묶음, 2,779멤버, 감소 1,865, 멤버 중복 없음(제가 CSV에서 다시 센 값).
- OCR: 45문서, 126쪽, 글자 315,330자, 빈 쪽 7, 평균 신뢰도 82.5, 60 미만 쪽 8. 이전 실행과 빈 쪽 수 동일. 실패 0.
- 수정한 기존 파일 4개의 변경은 27줄 추가, 1줄 삭제. 팀 코드는 변경 없음.

## 못 한 것과 남은 위험

- `entity_links.sql`은 DB에서 실행해 보지 않았다. 문법과 제약 이름은 눈으로만 점검했다(미확인).
- 질문별로 같은 묶음 노드가 함께 검색되는 빈도는 측정하지 못했다. 챗봇 답변에서 중복이 실제로 문제인지는 미측정.
- 카드 사이 노드가 업무상 같은 것인지는 판단하지 않았다.
- OCR 결과는 청킹·추출 전이다. 이후 단계는 OpenAI 비용이 든다(승인 필요). 숫자 오인식은 사람 대조가 필요하다.
- 검수 시트는 브라우저에서 열어 보지 않았다. 사람 판정 0건.

## 다음에 할 일

- 같은 카드 안 연결(181)을 적용할지 팀과 강사님께 확인. 적용하면 사용자가 `entity_links.sql`을 실행.
- OCR 결과 청킹과 추출 비용 추정 후 승인 받기.
- 검수 시트로 사람 확정 정확도 측정.
