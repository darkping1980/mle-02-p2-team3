# chat/

그래프 기반 카드 혜택 챗봇의 실행 화면, 사용자 소유 연결 어댑터, 오프라인 평가·검수 도구를 둔다. `src/graphrag_chatbot/`은 팀 코드이며 이 폴더의 어댑터로만 연결한다.

## 실행용 파일과 연결부

| 파일 | 역할 |
|---|---|
| `__init__.py` | 챗봇 관련 모듈을 패키지로 표시한다. |
| `run_fp_chat.py` | Streamlit 진입점으로 팀 화면을 띄우고 `fp_chat` 연결부와 OpenAI 어댑터를 적용한다. |
| `run_fp_chat_v2.py` | 사용자 소유 v2 화면 진입점으로 페이지 설정 후 `panel.py`의 백엔드 준비와 화면 렌더를 호출한다. |
| `panel.py` | 호스트용 공개 접점으로 `prepare_backend()`와 `render()`를 제공한다. |
| `fp_chat_patch.py` | 팀 GraphRAG 모듈에 `fp_chat` 조회, Q/A 기록, 선택적 하위 그래프 처리를 연결하는 옵트인 어댑터다. |
| `openai_llm_patch.py` | 팀 챗봇 LLM 호출을 OpenAI로 바꾸는 지연 적용 어댑터이며 모듈 임포트만으로 API를 호출하지 않는다. |
| `qa_log.py` | Q/A, 지연시간, 답변 형식·숫자 확인 결과를 로컬 진단 기록으로 구성하고 쓴다. |
| `db_pool.py` | `fp_chat` 어댑터의 PostgreSQL 조회를 위한 지연 초기화 풀 래퍼다. |

두 화면 실행 명령은 저장소 루트에서 사용한다.

```bash
PYTHONPATH=src:src/card_benefit uv run --locked streamlit run src/card_benefit/payment_card/file_pipeline/chat/run_fp_chat.py
PYTHONPATH=src:src/card_benefit uv run --locked streamlit run src/card_benefit/payment_card/file_pipeline/chat/run_fp_chat_v2.py
```

첫 명령은 팀 화면과 사용자 연결부를 사용하고, 둘째 명령은 사용자 v2 화면을 사용한다. `ui/app_v2.py`를 직접 실행하지 않는다.

## 하위 폴더

| 폴더 | 내용 |
|---|---|
| [`eval/`](eval/README.md) | 질문 생성, 골든셋, 평가 실행, 판정, 검색 진단 등 오프라인 평가 도구 12개와 골든셋 템플릿이다. |
| [`ui/`](ui/README.md) | v2 Streamlit 화면과 화면 독립 도우미 2개다. |
| [`answer/`](answer/README.md) | 답변 형식 지침, 답변 판정, 숫자 근거 확인 등 답변 기능 3개다. |
| [`retrieval/`](retrieval/README.md) | 검색 결과 병합, 시드 보완, 출처 라벨 등 검색 보조 도구 3개다. |
| [`review/`](review/README.md) | 답변과 그래프 근거를 사람이 대조하는 검수 자료 생성 도구 2개다. |

이동한 도구도 같은 패키지 아래라서 `payment_card.file_pipeline.chat.eval.<모듈>`, `payment_card.file_pipeline.chat.review.<모듈>` 로 실행하고, 화면 모듈은 `payment_card.file_pipeline.chat.ui.<모듈>`, 답변·검색 보조 모듈은 `payment_card.file_pipeline.chat.answer.<모듈>`, `payment_card.file_pipeline.chat.retrieval.<모듈>` 로 임포트한다(예: `python -m payment_card.file_pipeline.chat.eval.run_eval`). 스크립트식 임포트(`from answer_eval import ...`)가 필요한 도구는 `PYTHONPATH` 에 `chat/` 폴더를 포함한다.

## 데이터·초안 문서

| 파일 | 역할 |
|---|---|
| `카드혜택-Supabase-구조-보완-초안.md` | Supabase 카드 혜택 구조 보완을 정리한 초안 문서다. |

평가·검수 도구도 기본 데이터 경로에서 데이터베이스나 OpenAI를 자동 호출하지 않으며, 호출 기능이 있는 경우 코드에서 명시적으로 실행 경로를 선택해야 한다.

`FP_ANALYSIS_CACHE=1`은 정규화 질문별 분석 결과 캐시를 선택적으로 켠다(기본값 꺼짐). `FP_ANALYSIS_CACHE_FILE=/경로/cache.json`을 지정하면 JSON 캐시를 읽고 새 항목을 원자적으로 저장한다.
