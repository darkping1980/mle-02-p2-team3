# name_normalization 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.name_normalization`
- **소스:** [recipe_recommender/name_normalization.py](../../../../recipe_recommender/name_normalization.py)
- **역할:** 적재와 추천 Service가 공유하는 식재료명 비교 규칙.
- **주요 호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **정의:** 클래스 0개, 모듈 함수 1개

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [normalize_name](#function-normalize_name) | `str` | 식재료명 매칭과 중복 제거에 쓸 비교 문자열로 정규화한다. |

## Function normalize_name

```python
def normalize_name(value: str) -> str:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `str`. 식재료명 매칭과 중복 제거에 쓸 비교 문자열로 정규화한다.
- **원본:** [name_normalization.py](../../../../recipe_recommender/name_normalization.py) (4행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str` | 사용자 입력 또는 DB의 식재료·별칭. |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
