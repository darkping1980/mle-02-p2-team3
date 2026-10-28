"""Supabase Storage 이미지 업로드 모듈.

PDF 매뉴얼에서 추출한 이미지를 Supabase Storage bucket에 올리고,
DB에 저장할 public URL을 돌려준다.
"""

import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


#=========================================================
# Supabase Storage 이미지 업로드 관리
#=========================================================
class StorageManager:
    """
    Supabase Storage 이미지 업로드 및 URL 조회 관리

    생성자에서 ``SUPABASE_URL`` / ``SUPABASE_SECRET_KEY`` 로 Supabase client를 만들고,
    모든 업로드는 ``bucket_name`` bucket의 ``cars/{brand}/{model}/{image_name}`` 경로에 저장한다.
    업로드는 ``upsert`` 옵션을 사용하므로 같은 경로의 파일은 덮어쓴다.
    """

    bucket_name: str                 # 이미지 파일을 저장할 Storage bucket 이름
    supabase: object                 # Supabase Client 객체

    #=========================================================
    # 생성자 및 Supabase Client 설정
    #=========================================================
    def __init__(self, bucket_name: str = "images") -> None:
        """
        환경변수로 Supabase Client를 생성하고 Storage bucket을 설정한다.

        Raises:
            ValueError: ``SUPABASE_URL`` 또는 ``SUPABASE_SECRET_KEY`` 환경변수가 비어 있는 경우.
        """
        # .env 파일의 값을 환경변수로 읽어 온 뒤 필수 값부터 확인한다.
        load_dotenv()

        supabase_url = os.getenv("SUPABASE_URL")
        if not supabase_url:
            raise ValueError("SUPABASE_URL 환경변수가 설정되지 않았습니다.")

        supabase_secret_key = os.getenv("SUPABASE_SECRET_KEY")
        if not supabase_secret_key:
            raise ValueError("SUPABASE_SECRET_KEY 환경변수가 설정되지 않았습니다.")

        self.bucket_name = bucket_name
        self.supabase = create_client(supabase_url, supabase_secret_key)

    #=========================================================
    # 자동차 이미지 Storage 경로 생성
    #=========================================================
    def build_car_image_path(self, brand: str, model: str, image_name: str) -> str:
        """
        자동차 이미지의 Storage 경로를 생성한다.
        """
        return f"cars/{brand}/{model}/{image_name}"

    #=========================================================
    # 자동차 이미지 파일 업로드
    #=========================================================
    def upload_car_image(
        self,
        image_path: str | Path,
        brand: str,
        model: str,
        image_name: str,
    ) -> str:
        """
        자동차 이미지를 Storage에 업로드하고 Public URL을 반환한다.

        Raises:
            FileNotFoundError: ``image_path`` 가 실제 파일이 아닌 경우.
        """
        image_path = Path(image_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        # 파일 확장자로 MIME type을 추정하고, 알 수 없으면 일반 바이너리 type을 사용한다.
        # region [Python 설명] tuple unpacking과 `_` 변수
        # `mimetypes.guess_type()`은 `(type, encoding)` 두 값을 tuple로 반환한다.
        # `content_type, _ = ...`처럼 받으면 첫 값만 사용하고, 쓰지 않는 값은 관례적으로 `_`에 받는다.
        # endregion
        storage_path = self.build_car_image_path(brand, model, image_name)
        content_type, _ = mimetypes.guess_type(image_path.name)
        if content_type is None:
            content_type = "application/octet-stream"

        # 파일을 바이너리 모드("rb")로 열어 업로드하고, with 블록이 끝나면 파일을 닫는다.
        with image_path.open("rb") as image_file:
            self.supabase.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=image_file,
                file_options={
                    "content-type": content_type,
                    "upsert": "true"
                }
            )

        return self.get_public_url(storage_path)

    #=========================================================
    # 자동차 이미지 bytes 업로드
    #=========================================================
    def upload_car_image_bytes(
        self,
        image_bytes: bytes,
        brand: str,
        model: str,
        image_name: str,
    ) -> str:
        """
        자동차 이미지 bytes를 Storage에 업로드하고 Public URL을 반환한다.

        로컬 파일을 만들지 않고 메모리의 이미지 데이터를 바로 올릴 때 사용한다.
        MIME type은 ``image_name`` 의 확장자로 추정한다.
        """
        storage_path = self.build_car_image_path(brand, model, image_name)
        content_type, _ = mimetypes.guess_type(image_name)
        if content_type is None:
            content_type = "application/octet-stream"

        self.supabase.storage.from_(self.bucket_name).upload(
            path=storage_path,
            file=image_bytes,
            file_options={
                "content-type": content_type,
                "upsert": "true"
            }
        )

        return self.get_public_url(storage_path)

    #=========================================================
    # Public URL 조회
    #=========================================================
    def get_public_url(self, storage_path: str) -> str:
        """
        Storage에 저장된 파일의 Public URL을 반환한다.

        URL 문자열을 만드는 호출이며, 파일 존재 여부나 bucket 공개 설정을 확인하지 않는다.
        """
        return self.supabase.storage.from_(self.bucket_name).get_public_url(storage_path)