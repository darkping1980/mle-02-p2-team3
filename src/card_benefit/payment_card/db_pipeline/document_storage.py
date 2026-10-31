"""카드 PDF 원본의 Storage 보관을 맡는 모듈. 문서 등록·AI 추출 흐름과 분리되어 있다.

객체는 ``pdf/{doc_sha256}.pdf`` 에 두고 DB에는 경로를 저장하지 않는다. 해시로 위치가 정해지므로
다른 Supabase 프로젝트로 옮길 때는 ``CARD_STORAGE_*`` 설정 변경과 파일 복사만 하면 된다.

로컬 파일을 우선한다. 로컬 PDF가 정상이면 Storage에 접속하지 않고, 파일이 없을 때 요청받은 경우에만 내려받는다.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path
import re

from dotenv import load_dotenv

URL_ENV = "CARD_STORAGE_SUPABASE_URL"
SECRET_KEY_ENV = "CARD_STORAGE_SUPABASE_SECRET_KEY"
BUCKET_ENV = "CARD_STORAGE_BUCKET"

OBJECT_PREFIX = "pdf"
CONTENT_TYPE = "application/pdf"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DUPLICATE_STATUS = ("409", "Duplicate")          # Storage가 같은 경로의 객체가 있을 때 돌려주는 값

storage_logger = logging.getLogger("card_benefit.document_storage")


class StorageError(Exception):
    """Storage 처리 실패. 메시지에는 응답 본문이나 접속 정보를 넣지 않는다."""


class StorageIntegrityError(StorageError):
    """파일의 SHA-256이 기대값과 다른 경우."""


@dataclass(frozen=True)
class UploadResult:
    """업로드 결과. ``status`` 는 UPLOADED 또는 ALREADY_EXISTS다."""

    status: str
    object_path: str
    size: int


@dataclass(frozen=True)
class ResolvedPdf:
    """로컬 파일 확인 결과. ``source`` 는 LOCAL, STORAGE, MISSING, HASH_MISMATCH, STORAGE_FAILED 중 하나다."""

    source: str
    path: Path

    @property
    def usable(self) -> bool:
        return self.source in ("LOCAL", "STORAGE")


def sha256_file(path: str | Path) -> str:
    """파일의 소문자 16진수 SHA-256을 계산한다."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_path(doc_sha256: str) -> str:
    """문서 해시로 객체 경로를 만든다."""
    if not SHA256_PATTERN.match(doc_sha256):
        raise ValueError("doc_sha256은 소문자 16진수 64자여야 합니다")
    return f"{OBJECT_PREFIX}/{doc_sha256}.pdf"


def is_storage_configured() -> bool:
    """Storage 환경변수가 모두 있는지 확인한다. 접속은 하지 않는다."""
    load_dotenv()
    return all(os.getenv(name) for name in (URL_ENV, SECRET_KEY_ENV, BUCKET_ENV))


class DocumentStorage:
    """``CARD_STORAGE_*`` 설정의 비공개 버킷에 PDF를 올리고 내려받는다.

    Supabase client는 첫 Storage 호출 때 만든다. 객체를 만들기만 해서는 접속하지 않는다.
    기존 객체를 덮어쓰거나 지우는 기능은 두지 않는다.
    """

    def __init__(self, client=None, bucket: str | None = None):
        self._client = client
        self._bucket = bucket

    def _bucket_api(self):
        """버킷 API를 돌려준다. 설정이 없으면 ``StorageError`` 를 낸다."""
        if self._client is None or self._bucket is None:
            load_dotenv()
            url = os.getenv(URL_ENV)
            secret_key = os.getenv(SECRET_KEY_ENV)
            bucket = os.getenv(BUCKET_ENV)
            if not url or not secret_key or not bucket:
                raise StorageError(f"Storage 설정이 없습니다: {URL_ENV}, {SECRET_KEY_ENV}, {BUCKET_ENV}")
            from supabase import create_client

            self._client = create_client(url, secret_key)
            self._bucket = bucket
        return self._client.storage.from_(self._bucket)

    def exists(self, doc_sha256: str) -> bool:
        """객체가 있는지 확인한다. 권한·네트워크 오류는 없음으로 판단하지 않고 ``StorageError`` 를 낸다.

        SDK의 ``exists()`` 는 본문 없는 HEAD 응답의 400을 모두 없음으로 처리해 권한 오류와 구분되지 않는다.
        목록 조회는 오류가 응답으로 오므로 이쪽을 쓴다.
        """
        name = object_path(doc_sha256).removeprefix(f"{OBJECT_PREFIX}/")
        try:
            items = self._bucket_api().list(OBJECT_PREFIX, {"search": name, "limit": 2})
        except StorageError:
            raise
        except Exception as exc:
            raise self._failure("존재 확인", exc) from None
        return any(item.get("name") == name for item in items)

    def upload(self, path: str | Path, doc_sha256: str) -> UploadResult:
        """PDF를 업로드한다. 같은 객체가 있으면 올리지 않고 ALREADY_EXISTS를 반환한다.

        Raises:
            StorageIntegrityError: 파일 해시가 ``doc_sha256`` 과 다른 경우.
            StorageError: Storage 접근에 실패한 경우.
        """
        target = object_path(doc_sha256)
        content = Path(path).read_bytes()
        if hashlib.sha256(content).hexdigest() != doc_sha256:
            raise StorageIntegrityError(f"파일 해시가 기대값과 다릅니다: {target}")
        if self.exists(doc_sha256):
            storage_logger.info("STORAGE SKIP object=%s", target)
            return UploadResult("ALREADY_EXISTS", target, len(content))
        try:
            self._bucket_api().upload(
                target, content, file_options={"content-type": CONTENT_TYPE, "upsert": "false"},
            )
        except StorageError:
            raise
        except Exception as exc:
            if self._is_duplicate(exc):                  # 확인과 업로드 사이에 다른 실행이 올린 경우
                storage_logger.info("STORAGE SKIP object=%s", target)
                return UploadResult("ALREADY_EXISTS", target, len(content))
            raise self._failure("업로드", exc) from None
        storage_logger.info("STORAGE UPLOADED object=%s size=%d", target, len(content))
        return UploadResult("UPLOADED", target, len(content))

    def download(self, doc_sha256: str) -> bytes:
        """객체를 내려받아 해시를 확인한 뒤 내용을 반환한다."""
        target = object_path(doc_sha256)
        try:
            content = self._bucket_api().download(target)
        except StorageError:
            raise
        except Exception as exc:
            raise self._failure("다운로드", exc) from None
        if hashlib.sha256(content).hexdigest() != doc_sha256:
            raise StorageIntegrityError(f"내려받은 파일 해시가 기대값과 다릅니다: {target}")
        storage_logger.info("STORAGE DOWNLOADED object=%s size=%d", target, len(content))
        return content

    def restore(self, doc_sha256: str, target_path: str | Path) -> Path:
        """없는 로컬 파일을 복원한다. 이미 파일이 있으면 덮어쓰지 않고 ``FileExistsError`` 를 낸다."""
        target_path = Path(target_path)
        if target_path.exists():
            raise FileExistsError(f"로컬 파일이 이미 있습니다: {target_path.name}")
        content = self.download(doc_sha256)              # 해시가 맞을 때만 파일을 만든다
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("xb") as file:
            file.write(content)
        return target_path

    @staticmethod
    def _failure(action: str, exc: Exception) -> StorageError:
        """오류 유형과 HTTP 상태만 담은 예외를 만든다. 응답 본문은 넣지 않는다."""
        status = getattr(exc, "status", None)
        return StorageError(f"Storage {action} 실패: {type(exc).__name__}" + (f" status={status}" if status else ""))

    @staticmethod
    def _is_duplicate(exc: Exception) -> bool:
        """같은 경로의 객체가 있다는 오류인지 판단한다."""
        values = (getattr(exc, "status", None), getattr(exc, "code", None))
        return any(str(value) in DUPLICATE_STATUS for value in values)


def resolve_local_pdf(
    path: str | Path,
    doc_sha256: str,
    storage: DocumentStorage | None = None,
    allow_download: bool = False,
) -> ResolvedPdf:
    """처리에 쓸 로컬 PDF를 확인한다. Storage 실패는 예외 대신 상태로 돌려준다.

    로컬 파일이 있으면 해시만 확인하고 Storage에 접속하지 않는다. 해시가 달라도 파일을 바꾸지 않는다.
    파일이 없고 ``allow_download=True`` 이며 ``storage`` 가 있을 때만 내려받는다.
    """
    path = Path(path)
    object_path(doc_sha256)
    if path.is_file():
        return ResolvedPdf("LOCAL" if sha256_file(path) == doc_sha256 else "HASH_MISMATCH", path)
    if not allow_download or storage is None:
        return ResolvedPdf("MISSING", path)
    try:
        return ResolvedPdf("STORAGE", storage.restore(doc_sha256, path))
    except StorageError as error:
        storage_logger.warning("STORAGE RESTORE FAILED: %s", error)
        return ResolvedPdf("STORAGE_FAILED", path)
