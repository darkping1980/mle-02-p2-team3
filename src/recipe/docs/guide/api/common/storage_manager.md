# storage_manager 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `common.storage_manager`
- **소스:** [common/storage_manager.py](../../../../common/storage_manager.py)
- **역할:** Supabase Storage 이미지 업로드 모듈.
- **주요 호출자:** 레시피 Repository와 DB 연결 팩토리; 일부 유틸은 다른 예제에서도 사용
- **정의:** 클래스 1개, 모듈 함수 0개

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [StorageManager](#storagemanager) | 클래스 | Supabase Storage 이미지 업로드 및 URL 조회 관리 |

## StorageManager

**클래스.** Supabase Storage 이미지 업로드 및 URL 조회 관리

- **정의:** [storage_manager.py](../../../../common/storage_manager.py) (18행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `bucket_name` | `str` | 이미지 파일을 저장할 Storage bucket 이름 |
| `supabase` | `object` | Supabase Client 객체 |

### Constructor Summary

`def __init__(self, bucket_name: str='images') -> None:` — 환경변수로 Supabase Client를 생성하고 Storage bucket을 설정한다.

생성·주입 경로: 레시피 Repository와 DB 연결 팩토리; 일부 유틸은 다른 예제에서도 사용. 세부 매개변수와 처리 내용은 [StorageManager.__init__](#storagemanager-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#storagemanager-__init__) | `None` | 환경변수로 Supabase Client를 생성하고 Storage bucket을 설정한다. |
| [build_car_image_path](#storagemanager-build_car_image_path) | `str` | 자동차 이미지의 Storage 경로를 생성한다. |
| [upload_car_image](#storagemanager-upload_car_image) | `str` | 자동차 이미지를 Storage에 업로드하고 Public URL을 반환한다. |
| [upload_car_image_bytes](#storagemanager-upload_car_image_bytes) | `str` | 자동차 이미지 bytes를 Storage에 업로드하고 Public URL을 반환한다. |
| [get_public_url](#storagemanager-get_public_url) | `str` | Storage에 저장된 파일의 Public URL을 반환한다. |

### StorageManager __init__

```python
def __init__(self, bucket_name: str='images') -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 환경변수로 Supabase Client를 생성하고 Storage bucket을 설정한다.
- **원본:** [storage_manager.py](../../../../common/storage_manager.py) (33행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `bucket_name` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**예외:** ValueError: ``SUPABASE_URL`` 또는 ``SUPABASE_SECRET_KEY`` 환경변수가 비어 있는 경우.

### StorageManager build_car_image_path

```python
def build_car_image_path(self, brand: str, model: str, image_name: str) -> str:
```

- **주요 호출자:** `StorageManager.upload_car_image_bytes`, `StorageManager.upload_car_image`
- **반환:** `str`. 자동차 이미지의 Storage 경로를 생성한다.
- **원본:** [storage_manager.py](../../../../common/storage_manager.py) (57행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `brand` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `model` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `image_name` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### StorageManager upload_car_image

```python
def upload_car_image(self, image_path: str | Path, brand: str, model: str, image_name: str) -> str:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `str`. 자동차 이미지를 Storage에 업로드하고 Public URL을 반환한다.
- **원본:** [storage_manager.py](../../../../common/storage_manager.py) (66행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `image_path` | `str \| Path` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `brand` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `model` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `image_name` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**예외:** FileNotFoundError: ``image_path`` 가 실제 파일이 아닌 경우.

### StorageManager upload_car_image_bytes

```python
def upload_car_image_bytes(self, image_bytes: bytes, brand: str, model: str, image_name: str) -> str:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `str`. 자동차 이미지 bytes를 Storage에 업로드하고 Public URL을 반환한다.
- **원본:** [storage_manager.py](../../../../common/storage_manager.py) (109행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `image_bytes` | `bytes` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `brand` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `model` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `image_name` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### StorageManager get_public_url

```python
def get_public_url(self, storage_path: str) -> str:
```

- **주요 호출자:** `StorageManager.upload_car_image_bytes`, `StorageManager.upload_car_image`
- **반환:** `str`. Storage에 저장된 파일의 Public URL을 반환한다.
- **원본:** [storage_manager.py](../../../../common/storage_manager.py) (141행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `storage_path` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
