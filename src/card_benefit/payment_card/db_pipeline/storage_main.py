"""카드 PDF Storage CLI. ``--apply`` 가 없으면 Storage에 접속하지 않는다.

실행 예(src/card_benefit 폴더에서, PDF 경로는 data/raw/hana_all 기준):
    uv run python -m payment_card.db_pipeline.storage_main status --pdf "debit/파일명.pdf"
    uv run python -m payment_card.db_pipeline.storage_main upload --pdf "debit/파일명.pdf" --apply
    uv run python -m payment_card.db_pipeline.storage_main verify --pdf "debit/파일명.pdf" --apply
    uv run python -m payment_card.db_pipeline.storage_main restore --pdf "debit/파일명.pdf" --doc-sha256 <해시> --apply

한 번에 파일 1건만 처리한다. 객체를 덮어쓰거나 지우는 명령은 없다.
종료 코드: 0 성공, 1 입력 오류·해시 불일치, 2 인자 오류(argparse), 3 Storage 오류.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from .document_service import DATA_ROOT
from .document_storage import (
    DocumentStorage,
    StorageError,
    StorageIntegrityError,
    is_storage_configured,
    object_path,
    resolve_local_pdf,
    sha256_file,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """``status`` / ``upload`` / ``verify`` / ``restore`` 하위 명령을 해석한다."""
    parser = argparse.ArgumentParser(prog="storage_main", description="카드 PDF Storage 관리")
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="로컬 파일과 객체 경로 확인 (Storage 접속 없음)")
    status.add_argument("--pdf", required=True, help="data/raw/hana_all 기준 PDF 경로")

    upload = commands.add_parser("upload", help="PDF 1건 업로드")
    upload.add_argument("--pdf", required=True, help="data/raw/hana_all 기준 PDF 경로")
    upload.add_argument("--apply", action="store_true", help="실제로 업로드한다. 없으면 dry-run")

    verify = commands.add_parser("verify", help="객체를 내려받아 로컬 파일과 해시 대조 (파일은 쓰지 않음)")
    verify.add_argument("--pdf", required=True, help="data/raw/hana_all 기준 PDF 경로")
    verify.add_argument("--apply", action="store_true", help="실제로 내려받는다. 없으면 dry-run")

    restore = commands.add_parser("restore", help="없는 로컬 PDF 복원")
    restore.add_argument("--pdf", required=True, help="복원할 data/raw/hana_all 기준 경로")
    restore.add_argument("--doc-sha256", required=True, help="card_doc.doc_sha256 값")
    restore.add_argument("--apply", action="store_true", help="실제로 내려받는다. 없으면 dry-run")
    return parser.parse_args(argv)


def resolve_pdf_path(pdf: str | Path, data_root: Path = DATA_ROOT) -> Path:
    """수집 폴더 안의 PDF 경로만 허용한다."""
    root = data_root.resolve()
    path = (root / pdf).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != ".pdf":
        raise ValueError(f"{root} 아래의 PDF만 처리할 수 있습니다: {pdf}")
    return path


def existing_pdf(pdf: str | Path) -> Path:
    """있는 파일이어야 하는 명령의 경로를 확인한다."""
    path = resolve_pdf_path(pdf)
    if not path.is_file():
        raise ValueError(f"PDF 파일이 없습니다: {pdf}")
    return path


def run_status(args: argparse.Namespace) -> int:
    """로컬 파일 정보와 업로드될 객체 경로를 출력한다."""
    path = existing_pdf(args.pdf)
    doc_sha256 = sha256_file(path)
    print(f"파일: {path.name} ({path.stat().st_size:,} byte)")
    print(f"doc_sha256: {doc_sha256}")
    print(f"객체 경로: {object_path(doc_sha256)}")
    print(f"Storage 설정: {'있음' if is_storage_configured() else '없음'}")
    return 0


def run_upload(args: argparse.Namespace) -> int:
    """PDF 1건을 업로드한다."""
    path = existing_pdf(args.pdf)
    doc_sha256 = sha256_file(path)
    if not args.apply:
        print(f"dry-run: {path.name} → {object_path(doc_sha256)} (--apply 없이는 업로드하지 않음)")
        return 0
    result = DocumentStorage().upload(path, doc_sha256)
    print(f"{result.status}: {result.object_path} ({result.size:,} byte)")
    return 0


def run_verify(args: argparse.Namespace) -> int:
    """객체를 내려받아 로컬 파일과 같은지 확인한다. 로컬 파일은 바꾸지 않는다."""
    path = existing_pdf(args.pdf)
    doc_sha256 = sha256_file(path)
    if not args.apply:
        print(f"dry-run: {object_path(doc_sha256)} 대조 예정 (--apply 없이는 내려받지 않음)")
        return 0
    content = DocumentStorage().download(doc_sha256)
    print(f"일치: {object_path(doc_sha256)} ({len(content):,} byte)")
    return 0


def run_restore(args: argparse.Namespace) -> int:
    """로컬 파일이 없을 때만 Storage에서 복원한다."""
    path = resolve_pdf_path(args.pdf)
    if not args.apply:
        result = resolve_local_pdf(path, args.doc_sha256)
        print(f"dry-run: 로컬 상태 {result.source} (--apply 없이는 내려받지 않음)")
        return 0 if result.source in ("LOCAL", "MISSING") else 1
    result = resolve_local_pdf(path, args.doc_sha256, DocumentStorage(), allow_download=True)
    print(f"결과: {result.source} {path.name}")
    if result.usable:
        return 0
    return 3 if result.source == "STORAGE_FAILED" else 1


COMMANDS = {"status": run_status, "upload": run_upload, "verify": run_verify, "restore": run_restore}


def main(argv: list[str] | None = None) -> int:
    """명령을 실행하고 오류를 종료 코드로 바꾼다."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)      # 요청 주소를 INFO로 남기지 않는다
    try:
        return COMMANDS[args.command](args)
    except (ValueError, FileExistsError, StorageIntegrityError) as error:
        print(f"입력 오류: {error}", file=sys.stderr)
        return 1
    except StorageError as error:
        print(f"Storage 오류: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
