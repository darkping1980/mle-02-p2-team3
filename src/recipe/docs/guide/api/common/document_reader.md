# document_reader 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `common.document_reader`
- **소스:** [common/document_reader.py](../../../../common/document_reader.py)
- **역할:** PDF/CSV 문서를 읽어 페이지별 텍스트 목록으로 만드는 도우미 모듈.
- **주요 호출자:** 레시피 Repository와 DB 연결 팩토리; 일부 유틸은 다른 예제에서도 사용
- **정의:** 클래스 1개, 모듈 함수 0개

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [DocumentReader](#documentreader) | 클래스 | 문서 파일 읽기 및 전처리 관리 |

## DocumentReader

**클래스.** 문서 파일 읽기 및 전처리 관리

- **정의:** [document_reader.py](../../../../common/document_reader.py) (15행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `file_path` | `str` | 파일경로 |
| `doc_list` | `list[Any]` | 문서 리스트 |
| `reader` | `Any` | 문서 리더 객체 |

### Constructor Summary

`def __init__(self, file_path):` — 읽을 파일 경로를 ``Path`` 로 저장하고 reader와 doc_list를 빈 상태로 초기화한다.

생성·주입 경로: 레시피 Repository와 DB 연결 팩토리; 일부 유틸은 다른 예제에서도 사용. 세부 매개변수와 처리 내용은 [DocumentReader.__init__](#documentreader-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#documentreader-__init__) | `타입 힌트 없음` | 읽을 파일 경로를 ``Path`` 로 저장하고 reader와 doc_list를 빈 상태로 초기화한다. |
| [set_pdf_reader](#documentreader-set_pdf_reader) | `타입 힌트 없음` | pdf 읽어서 설정 |
| [set_csv_reader](#documentreader-set_csv_reader) | `타입 힌트 없음` | csv 읽어서 설정 |
| [set_pdf_doc_list](#documentreader-set_pdf_doc_list) | `타입 힌트 없음` | 읽은 pdf 내용 doc_list 로 설정 |
| [set_pdf_chunk_doc_list](#documentreader-set_pdf_chunk_doc_list) | `타입 힌트 없음` | doc_list 청크 설정후 재저장 |

### DocumentReader __init__

```python
def __init__(self, file_path):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 읽을 파일 경로를 ``Path`` 로 저장하고 reader와 doc_list를 빈 상태로 초기화한다.
- **원본:** [document_reader.py](../../../../common/document_reader.py) (39행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `file_path` | `타입 힌트 없음` | 입력 파일 경로 |

### DocumentReader set_pdf_reader

```python
def set_pdf_reader(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. pdf 읽어서 설정
- **원본:** [document_reader.py](../../../../common/document_reader.py) (53행)

### DocumentReader set_csv_reader

```python
def set_csv_reader(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. csv 읽어서 설정
- **원본:** [document_reader.py](../../../../common/document_reader.py) (70행)

### DocumentReader set_pdf_doc_list

```python
def set_pdf_doc_list(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 읽은 pdf 내용 doc_list 로 설정
- **원본:** [document_reader.py](../../../../common/document_reader.py) (84행)

### DocumentReader set_pdf_chunk_doc_list

```python
def set_pdf_chunk_doc_list(selft):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. doc_list 청크 설정후 재저장
- **원본:** [document_reader.py](../../../../common/document_reader.py) (108행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `selft` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
