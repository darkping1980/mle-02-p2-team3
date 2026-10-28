# recipe_ingredient_parser 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.setup.recipe_ingredient_parser`
- **소스:** [recipe_recommender/setup/recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py)
- **역할:** ``RCP_PARTS_DTLS`` 재료 원문을 staging 행 후보로 나누는 보수적 파서.
- **주요 호출자:** `RecipeRegisterService`
- **정의:** 클래스 2개, 모듈 함수 9개

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [ParsedIngredient](#parsedingredient) | dataclass DTO | 원문 재료 한 항목의 파싱 후보; 등록 Service가 staging 행에 사용한다. |
| [RecipeIngredientParser](#recipeingredientparser) | 클래스 | 재료 원문 파서. DB와 무관한 순수 업무 규칙이며 ``RecipeRegisterService`` 가 주입받아 사용한다. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [parse_quantity](#function-parse_quantity) | `Decimal \| None` | '75', '0.5', '1/2', '½', '1½' 를 Decimal(소수 3자리)로 바꾼다. 해석할 수 없으면 None. |
| [split_items](#function-split_items) | `list[str]` | 괄호 밖의 쉼표로만 나눈다. '참치(캔, 30g)' 안의 쉼표는 유지한다. |
| [_split_header](#function-_split_header) | `tuple[str \| None, str \| None, str]` | 줄 앞의 구획 머리글을 분리한다. Returns ``(section, serving_note, rest)``. |
| [_choose_amount](#function-_choose_amount) | `tuple[Decimal \| None, str \| None, list[str], int]` | 분량 후보 문자열 목록에서 대표 분량을 고른다. 미터법 단위를 우선한다. |
| [_status_for_name](#function-_status_for_name) | `str` | 후보 재료명의 불확실성을 확인해 검토 상태와 사유를 조정한다. |
| [parse_item](#function-parse_item) | `tuple[str \| None, Decimal \| None, str \| None, str, list[str]]` | 재료 항목 하나를 ``(name, qty, unit, status, notes)`` 로 분리한다. |
| [_split_inline_sections](#function-_split_inline_sections) | `list[tuple[str \| None, str \| None]]` | 줄 나머지를 ``(바뀐 구획 또는 None, 재료 항목 또는 None)`` 목록으로 나눈다. |
| [_split_item_headers](#function-_split_item_headers) | `list[tuple[str \| None, str \| None]]` | 한 재료 조각 안의 구획 머리글을 분리한다. |
| [parse_ingredient_text](#function-parse_ingredient_text) | `list[ParsedIngredient]` | 재료 원문 전체를 등장 순서대로 ``ParsedIngredient`` 목록으로 만든다. |

## ParsedIngredient

**dataclass DTO.** 원문 재료 한 항목의 파싱 후보; 등록 Service가 staging 행에 사용한다.

- **정의:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (65행)
- **생성 위치:** `RecipeIngredientParser`가 원문 항목별 후보로 만든다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `line_no` | `int` | 원문에서 발견한 순번; 1부터 시작한다. |
| `raw_txt` | `str` | 손실 없이 보존할 원문 재료 조각. |
| `parsed_nm` | `str \| None` | 분리한 후보 재료명; 실패 시 None. |
| `qty` | `Decimal \| None` | 수량 후보; 해석 불가 또는 미기재 시 None. |
| `unit_nm` | `str \| None` | 수량 단위 또는 분량 표현; 없으면 None. |
| `section_txt` | `str \| None` | 주재료·양념 등 원문 구획; 없으면 None. |
| `parse_status` | `str` | OK, PARTIAL, AMBIGUOUS, FAILED 중 검토 상태. |
| `note` | `str` | 사람이 검토할 때 참고할 불확실성 설명; 없으면 빈 문자열. |
| `review_note` | `str` | `@property`로 계산되는 읽기 속성; [review_note 상세](#parsedingredient-review_note-getter) 참조 |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [review_note (getter)](#parsedingredient-review_note-getter) | `str` | staging ``rcp_ingr_review_note`` 에 저장할 문자열. 항상 ``parse=상태`` 로 시작한다. |

### ParsedIngredient review_note getter

```python
@property
def review_note(self) -> str:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `str`. staging ``rcp_ingr_review_note`` 에 저장할 문자열. 항상 ``parse=상태`` 로 시작한다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (82행)

## RecipeIngredientParser

**클래스.** 재료 원문 파서. DB와 무관한 순수 업무 규칙이며 ``RecipeRegisterService`` 가 주입받아 사용한다.

- **정의:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (305행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `version` | `str` | staging rcp_ingr_parser_version에 기록할 파서 버전 |

### Constructor Summary

명시적 `__init__`가 없다. 상위 클래스 또는 Python 기본 생성자를 사용한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [parse](#recipeingredientparser-parse) | `list[ParsedIngredient]` | ``parse_ingredient_text()`` 와 같다. 원문 등장 순서대로 후보 목록을 돌려준다. |

### RecipeIngredientParser parse

```python
def parse(self, parts_text: str | None, recipe_name: str='') -> list[ParsedIngredient]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `list[ParsedIngredient]`. ``parse_ingredient_text()`` 와 같다. 원문 등장 순서대로 후보 목록을 돌려준다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (317행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `parts_text` | `str \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `recipe_name` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function parse_quantity

```python
def parse_quantity(text: str) -> Decimal | None:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `Decimal | None`. '75', '0.5', '1/2', '½', '1½' 를 Decimal(소수 3자리)로 바꾼다. 해석할 수 없으면 None.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (87행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 처리할 입력 문자열 |

## Function split_items

```python
def split_items(line: str) -> list[str]:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `list[str]`. 괄호 밖의 쉼표로만 나눈다. '참치(캔, 30g)' 안의 쉼표는 유지한다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (108행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `line` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _split_header

```python
def _split_header(line: str, recipe_name: str) -> tuple[str | None, str | None, str]:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `tuple[str | None, str | None, str]`. 줄 앞의 구획 머리글을 분리한다. Returns ``(section, serving_note, rest)``.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (125행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `line` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `recipe_name` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _choose_amount

```python
def _choose_amount(parts: list[str]) -> tuple[Decimal | None, str | None, list[str], int]:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `tuple[Decimal | None, str | None, list[str], int]`. 분량 후보 문자열 목록에서 대표 분량을 고른다. 미터법 단위를 우선한다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (150행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `parts` | `list[str]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _status_for_name

```python
def _status_for_name(name: str, base_status: str, notes: list[str]) -> str:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `str`. 후보 재료명의 불확실성을 확인해 검토 상태와 사유를 조정한다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (170행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `name` | `str` | 조회할 이름 또는 식별자 |
| `base_status` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `notes` | `list[str]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function parse_item

```python
def parse_item(item: str) -> tuple[str | None, Decimal | None, str | None, str, list[str]]:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `tuple[str | None, Decimal | None, str | None, str, list[str]]`. 재료 항목 하나를 ``(name, qty, unit, status, notes)`` 로 분리한다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (182행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `item` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _split_inline_sections

```python
def _split_inline_sections(text: str) -> list[tuple[str | None, str | None]]:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `list[tuple[str | None, str | None]]`. 줄 나머지를 ``(바뀐 구획 또는 None, 재료 항목 또는 None)`` 목록으로 나눈다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (236행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 처리할 입력 문자열 |

## Function _split_item_headers

```python
def _split_item_headers(text: str) -> list[tuple[str | None, str | None]]:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `list[tuple[str | None, str | None]]`. 한 재료 조각 안의 구획 머리글을 분리한다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (252행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 처리할 입력 문자열 |

## Function parse_ingredient_text

```python
def parse_ingredient_text(parts_text: str | None, recipe_name: str='') -> list[ParsedIngredient]:
```

- **호출자:** `RecipeRegisterService`
- **반환:** `list[ParsedIngredient]`. 재료 원문 전체를 등장 순서대로 ``ParsedIngredient`` 목록으로 만든다.
- **원본:** [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) (265행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `parts_text` | `str \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `recipe_name` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
