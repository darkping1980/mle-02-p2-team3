# pantry_graphrag 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.pantry_graphrag`
- **소스:** [recipe_recommender/pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py)
- **역할:** 냉장고 재료 추천 GraphRAG — LangGraph 흐름: 입력 해석 → Neo4j 조회 → 근거 기반 답변.
- **주요 호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **정의:** 클래스 5개, 모듈 함수 13개

- **직접 의존:** `.pantry_recommend_service`, `.name_normalization`

- **관련 API:** [pantry_recommend_service](pantry_recommend_service.md), [recipe_graph_repository](recipe_graph_repository.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [IngredientTerms](#ingredientterms) | Pydantic BaseModel | 입력 해석 LLM의 구조화 출력; Pydantic이 재료 목록의 형태를 검증한다. |
| [RecipeReason](#recipereason) | Pydantic BaseModel | 레시피 ID와 해당 레시피의 LLM 추천 이유 한 건을 검증한다. |
| [PantryAnswer](#pantryanswer) | Pydantic BaseModel | 설명 LLM의 구조화 출력; ``validate_answer``가 DB 근거와 다시 대조한다. |
| [PantryState](#pantrystate) | TypedDict / LangGraph State | LangGraph 노드가 공유하는 상태의 키와 값 형식. |
| [PantryGraphRAG](#pantrygraphrag) | 클래스 | 입력 해석, Neo4j 추천 조회, 근거 설명을 LangGraph로 연결한다. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [create_llm](#function-create_llm) | `타입 힌트 없음` | API 키가 있을 때만 Streamlit 파이프라인용 ChatOpenAI를 생성한다. |
| [terms_in_question](#function-terms_in_question) | `list[str]` | LLM이 뽑은 입력어 중 사용자 문장에 실제로 있는 것만 남긴다(정규화·공백 무시 비교, 중복 제거). |
| [mask_phrases](#function-mask_phrases) | `str` | ``phrases`` (레시피명 등)를 지운다. 띄어쓰기만 다른 표기('닭고기 김치찌개')도 함께 지운다. |
| [scan_vocabulary_terms](#function-scan_vocabulary_terms) | `list[str]` | 문장에 들어 있는 DB 표준명·별칭을 긴 이름부터 찾아 문장 순서로 돌려준다(LLM 없는 문장 해석 대체 규칙). |
| [foreign_ingredients](#function-foreign_ingredients) | `list[str]` | ``text`` 에 나온 DB 식재료 이름 중 ``allowed`` 가 아닌 것. |
| [has_final_consonant](#function-has_final_consonant) | `bool \| None` | 마지막 글자가 한글이면 받침 여부, 숫자면 읽는 소리 기준, 그 밖(영문 등)은 None. |
| [josa](#function-josa) | `str` | ``word`` 뒤에 붙을 조사. ``josa('두부', '을', '를')`` → ``'두부를'``. 판단할 수 없으면 '을(를)' 형태. |
| [josa_ro](#function-josa_ro) | `str` | '으로/로': 받침이 없거나 ㄹ 받침이면 '로'. |
| [list_text](#function-list_text) | `str` | ``['a','b','c']`` → ``'a, b, c'``. ``limit`` 을 넘으면 ``'a, b 외 N개'``. |
| [grounded_reason](#function-grounded_reason) | `str` | 근거만으로 만든 추천 이유(LLM 실패·검증 실패 시 대체 문장). |
| [grounded_summary](#function-grounded_summary) | `str` | 추천 결과의 첫 레시피와 보유 재료로 LLM 없이 요약 문장을 만든다. |
| [build_context](#function-build_context) | `list[dict]` | Neo4j 추천 DTO에서 LLM에 전달할 근거 필드만 추린다. |
| [validate_answer](#function-validate_answer) | `tuple[dict, list[str]]` | LLM 답변의 레시피 ID와 재료명을 조회 근거와 대조한다. |

## IngredientTerms

**Pydantic BaseModel.** 입력 해석 LLM의 구조화 출력; Pydantic이 재료 목록의 형태를 검증한다.

- **정의:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (46행)
- **생성 위치:** `PantryGraphRAG.interpret`가 `llm.with_structured_output(IngredientTerms)`로 응답 모델을 지정한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `terms` | `list[str]` | 원문에서 추출한 이름 목록; interpret가 실제 질문에 있는 단어만 남긴다. |

### Constructor Summary

명시적 생성자는 없다. Pydantic이 선언된 필드를 바탕으로 입력값을 검증하고 모델 객체를 만든다.

## RecipeReason

**Pydantic BaseModel.** 레시피 ID와 해당 레시피의 LLM 추천 이유 한 건을 검증한다.

- **정의:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (52행)
- **생성 위치:** `PantryAnswer.recipes`의 항목 모델로 Pydantic이 검증한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_id` | `str` | 조회 결과의 ID여야 하며 validate_answer에서 실제 추천 목록과 대조한다. |
| `reason` | `str` | 근거 밖 재료가 언급되면 해당 이유는 규칙 기반 설명으로 대체한다. |

### Constructor Summary

명시적 생성자는 없다. Pydantic이 선언된 필드를 바탕으로 입력값을 검증하고 모델 객체를 만든다.

## PantryAnswer

**Pydantic BaseModel.** 설명 LLM의 구조화 출력; ``validate_answer``가 DB 근거와 다시 대조한다.

- **정의:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (60행)
- **생성 위치:** `PantryGraphRAG.answer`가 `llm.with_structured_output(PantryAnswer)`로 응답 모델을 지정한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `summary` | `str` | 전체 추천 요약; 검증에 실패하면 grounded_summary로 대체한다. |
| `recipes` | `list[RecipeReason]` | 추천 ID별 이유; 실제 조회 목록과의 일치는 후속 검증에서 확인한다. |

### Constructor Summary

명시적 생성자는 없다. Pydantic이 선언된 필드를 바탕으로 입력값을 검증하고 모델 객체를 만든다.

## PantryState

**TypedDict / LangGraph State.** LangGraph 노드가 공유하는 상태의 키와 값 형식.

- **정의:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (92행)
- **생성 위치:** `PantryGraphRAG._build`가 State 스키마로 등록한다. 런타임 값은 `run`에서 dict로 시작한다.

`total=False`는 정적 타입 검사에서 키 생략을 허용한다. 런타임에는 `run`의 초기 값과 앞선 Node가 만든 키를 다음 Node가 요구한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `question` | `str` | run 입력; interpret가 읽고 answer의 LLM 프롬프트에도 사용한다. |
| `limit` | `int` | run 입력; retrieve가 사용하며 누락 시 기본값 5. |
| `sort` | `str` | run 입력; retrieve가 coverage/missing 정렬에 사용하며 누락 시 coverage. |
| `terms` | `list[str]` | interpret가 추출; retrieve가 식재료 조회에 사용한다. |
| `term_source` | `str` | interpret가 기록한 'llm'\|'rule'\|'vocabulary'; 화면의 해석 출처. |
| `result` | `PantryResult` | retrieve가 만든 결과; answer가 설명의 근거로 사용한다. |
| `answer` | `dict` | answer가 생성; summary, reasons, sources, llm_status 등을 화면이 읽는다. |
| `warnings` | `list[str]` | run에서 빈 목록으로 시작; interpret와 answer가 새 목록으로 누적한다. |

### Constructor Summary

명시적 생성자는 없다. 런타임 값은 일반 `dict`이며 타입 선언은 키의 정적 형식을 설명한다.

## PantryGraphRAG

**클래스.** 입력 해석, Neo4j 추천 조회, 근거 설명을 LangGraph로 연결한다.

- **정의:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (313행)
- **생성 위치:** `streamlit_app.get_pipeline`에서 추천 Service와 선택적 LLM을 주입해 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `service` | `타입 힌트 없음` | 생성자 323행에서 설정; 입력 해석, Neo4j 추천 조회, 근거 설명을 LangGraph로 연결한다. |
| `llm` | `타입 힌트 없음` | 생성자 324행에서 설정; 입력 해석, Neo4j 추천 조회, 근거 설명을 LangGraph로 연결한다. |
| `graph` | `타입 힌트 없음` | 생성자 325행에서 설정; 입력 해석, Neo4j 추천 조회, 근거 설명을 LangGraph로 연결한다. |

### Constructor Summary

`def __init__(self, service: PantryRecommendService, llm=None):` — 추천 Service와 LLM을 보관하고 실행 가능한 그래프를 컴파일한다.

생성·주입 경로: `streamlit_app.get_pipeline`에서 추천 Service와 선택적 LLM을 주입해 만든다.. 세부 매개변수와 처리 내용은 [PantryGraphRAG.__init__](#pantrygraphrag-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#pantrygraphrag-__init__) | `타입 힌트 없음` | 추천 Service와 LLM을 보관하고 실행 가능한 그래프를 컴파일한다. |
| [_build](#pantrygraphrag-_build) | `타입 힌트 없음` | 세 Node를 순서대로 잇고 ``invoke`` 가능한 그래프로 컴파일한다. |
| [run](#pantrygraphrag-run) | `PantryState` | 질문과 정렬 조건으로 State를 초기화하고 그래프를 한 번 실행한다. |
| [interpret](#pantrygraphrag-interpret) | `PantryState` | 구분 입력은 규칙으로, 문장은 LLM 또는 DB 어휘로 해석한다. |
| [_interpret_without_llm](#pantrygraphrag-_interpret_without_llm) | `PantryState` | 문장형 입력을 LLM 없이 해석한다: 문장에서 DB 식재료명·별칭을 찾고, 없으면 구분자 규칙 결과를 쓴다. |
| [retrieve](#pantrygraphrag-retrieve) | `PantryState` | 해석된 재료를 Service에 전달해 Neo4j 추천 결과를 추가한다. |
| [answer](#pantrygraphrag-answer) | `PantryState` | 조회 근거로 설명을 만들고 LLM 실패 시 근거 문장으로 대체한다. |

### PantryGraphRAG __init__

```python
def __init__(self, service: PantryRecommendService, llm=None):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 추천 Service와 LLM을 보관하고 실행 가능한 그래프를 컴파일한다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (321행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `service` | `PantryRecommendService` | 업무 처리를 위임할 Service |
| `llm` | `타입 힌트 없음` | 선택적으로 사용되는 LLM 객체 |

### PantryGraphRAG _build

```python
def _build(self):
```

- **주요 호출자:** `PantryGraphRAG.__init__`; 클래스 내부: `PantryGraphRAG.__init__`
- **반환:** `타입 힌트 없음`. 세 Node를 순서대로 잇고 ``invoke`` 가능한 그래프로 컴파일한다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (327행)

### PantryGraphRAG run

```python
def run(self, question: str, limit: int=5, sort: str='coverage') -> PantryState:
```

- **주요 호출자:** `streamlit_app.run_pipeline`
- **반환:** `PantryState`. 질문과 정렬 조건으로 State를 초기화하고 그래프를 한 번 실행한다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (341행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `question` | `str` | 사용자 재료 목록 또는 문장. |
| `limit` | `int` | 표시할 추천 건수. |
| `sort` | `str` | ``coverage`` 또는 ``missing``. |

**처리 흐름:** 초기 State에 질문·건수·정렬·빈 경고 목록을 넣고 컴파일된 그래프의 `invoke`를 호출한다.

**관련 API:** [pantry_recommend_service](pantry_recommend_service.md), [recipe_graph_repository](recipe_graph_repository.md)

### PantryGraphRAG interpret

```python
def interpret(self, state: PantryState) -> PantryState:
```

- **주요 호출자:** LangGraph의 `interpret` Node; `_build`에서 등록
- **반환:** `PantryState`. 구분 입력은 규칙으로, 문장은 LLM 또는 DB 어휘로 해석한다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (354행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `state` | `PantryState` | 질문과 기존 경고를 담은 상태. |

**처리 흐름:** 구분된 짧은 입력은 규칙으로 처리한다. 문장 입력은 구조화 LLM 출력에서 원문에 없는 재료를 제거하고, 실패하면 DB 어휘 또는 규칙으로 돌아간다.

**관련 API:** [pantry_recommend_service](pantry_recommend_service.md), [recipe_graph_repository](recipe_graph_repository.md)

### PantryGraphRAG _interpret_without_llm

```python
def _interpret_without_llm(self, question: str, rule_terms: list[str], warnings: list[str]) -> PantryState:
```

- **주요 호출자:** `PantryGraphRAG.interpret`
- **반환:** `PantryState`. 문장형 입력을 LLM 없이 해석한다: 문장에서 DB 식재료명·별칭을 찾고, 없으면 구분자 규칙 결과를 쓴다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (385행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `question` | `str` | 사용자가 입력한 재료 목록 또는 문장 |
| `rule_terms` | `list[str]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `warnings` | `list[str]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### PantryGraphRAG retrieve

```python
def retrieve(self, state: PantryState) -> PantryState:
```

- **주요 호출자:** LangGraph의 `retrieve` Node; `_build`에서 등록
- **반환:** `PantryState`. 해석된 재료를 Service에 전달해 Neo4j 추천 결과를 추가한다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (393행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `state` | `PantryState` | interpret가 만든 terms와 초기 limit, sort. |

**처리 흐름:** `terms`를 추천 Service에 전달하고 반환된 `PantryResult`를 State의 `result`에 넣는다.

**관련 API:** [pantry_recommend_service](pantry_recommend_service.md), [recipe_graph_repository](recipe_graph_repository.md)

### PantryGraphRAG answer

```python
def answer(self, state: PantryState) -> PantryState:
```

- **주요 호출자:** LangGraph의 `answer` Node; `_build`에서 등록
- **반환:** `PantryState`. 조회 근거로 설명을 만들고 LLM 실패 시 근거 문장으로 대체한다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (405행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `state` | `PantryState` | retrieve 결과와 원문 질문, 이전 경고. |

**처리 흐름:** 조회 근거로 기본 설명을 먼저 만든다. 추천과 LLM이 있으면 구조화 출력을 요청하고 `validate_answer`로 근거 밖 문장을 교체한다.

**관련 API:** [pantry_recommend_service](pantry_recommend_service.md), [recipe_graph_repository](recipe_graph_repository.md)

## Function create_llm

```python
def create_llm():
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `타입 힌트 없음`. API 키가 있을 때만 Streamlit 파이프라인용 ChatOpenAI를 생성한다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (110행)

## Function terms_in_question

```python
def terms_in_question(terms: list[str], question: str) -> list[str]:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `list[str]`. LLM이 뽑은 입력어 중 사용자 문장에 실제로 있는 것만 남긴다(정규화·공백 무시 비교, 중복 제거).
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (127행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `terms` | `list[str]` | 입력에서 추출한 재료명 목록 |
| `question` | `str` | 사용자가 입력한 재료 목록 또는 문장 |

## Function mask_phrases

```python
def mask_phrases(text: str, phrases) -> str:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `str`. ``phrases`` (레시피명 등)를 지운다. 띄어쓰기만 다른 표기('닭고기 김치찌개')도 함께 지운다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (139행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 처리할 입력 문자열 |
| `phrases` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function scan_vocabulary_terms

```python
def scan_vocabulary_terms(question: str, vocabulary: list[dict]) -> list[str]:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `list[str]`. 문장에 들어 있는 DB 표준명·별칭을 긴 이름부터 찾아 문장 순서로 돌려준다(LLM 없는 문장 해석 대체 규칙).
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (148행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `question` | `str` | 사용자가 입력한 재료 목록 또는 문장 |
| `vocabulary` | `list[dict]` | DB 표준 재료명과 별칭 목록 |

## Function foreign_ingredients

```python
def foreign_ingredients(text: str, allowed: set[str], vocabulary: set[str], ignore=()) -> list[str]:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `list[str]`. ``text`` 에 나온 DB 식재료 이름 중 ``allowed`` 가 아닌 것.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (164행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 처리할 입력 문자열 |
| `allowed` | `set[str]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `vocabulary` | `set[str]` | DB 표준 재료명과 별칭 목록 |
| `ignore` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function has_final_consonant

```python
def has_final_consonant(word: str) -> bool | None:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `bool | None`. 마지막 글자가 한글이면 받침 여부, 숫자면 읽는 소리 기준, 그 밖(영문 등)은 None.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (181행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `word` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function josa

```python
def josa(word: str, with_final: str, without_final: str) -> str:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `str`. ``word`` 뒤에 붙을 조사. ``josa('두부', '을', '를')`` → ``'두부를'``. 판단할 수 없으면 '을(를)' 형태.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (194행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `word` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `with_final` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `without_final` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function josa_ro

```python
def josa_ro(word: str) -> str:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `str`. '으로/로': 받침이 없거나 ㄹ 받침이면 '로'.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (202행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `word` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function list_text

```python
def list_text(items: list[str], limit: int | None=None) -> str:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `str`. ``['a','b','c']`` → ``'a, b, c'``. ``limit`` 을 넘으면 ``'a, b 외 N개'``.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (213행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `items` | `list[str]` | 처리할 항목 목록 |
| `limit` | `int \| None` | 반환하거나 표시할 최대 건수 |

## Function grounded_reason

```python
def grounded_reason(rec) -> str:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `str`. 근거만으로 만든 추천 이유(LLM 실패·검증 실패 시 대체 문장).
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (220행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rec` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function grounded_summary

```python
def grounded_summary(result: PantryResult) -> str:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `str`. 추천 결과의 첫 레시피와 보유 재료로 LLM 없이 요약 문장을 만든다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (233행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `result` | `PantryResult` | 조회 또는 추천 결과 |

## Function build_context

```python
def build_context(result: PantryResult) -> list[dict]:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `list[dict]`. Neo4j 추천 DTO에서 LLM에 전달할 근거 필드만 추린다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (244행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `result` | `PantryResult` | ``retrieve``가 만든 추천 결과. |

## Function validate_answer

```python
def validate_answer(raw: PantryAnswer, result: PantryResult, vocabulary: list[dict]) -> tuple[dict, list[str]]:
```

- **호출자:** `streamlit_app.run_pipeline` → `PantryGraphRAG.run`
- **반환:** `tuple[dict, list[str]]`. LLM 답변의 레시피 ID와 재료명을 조회 근거와 대조한다.
- **원본:** [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) (260행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `raw` | `PantryAnswer` | Pydantic으로 형태를 검증한 LLM 출력. |
| `result` | `PantryResult` | Neo4j 조회를 담은 변경 불가 근거. |
| `vocabulary` | `list[dict]` | 근거 밖 식재료 탐지에 쓰는 DB 표준명·별칭. |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
