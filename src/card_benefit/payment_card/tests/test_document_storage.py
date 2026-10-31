"""PDF Storage 단위 테스트. Mock만 쓰며 네트워크에 접속하지 않는다.

실행(src/card_benefit 폴더에서):
    uv run python -m unittest discover -s payment_card/tests -v
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import inspect
import io
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from payment_card.db_pipeline import document_service, storage_main
from payment_card.db_pipeline import document_storage as module
from payment_card.db_pipeline.document_storage import (
    DocumentStorage,
    StorageError,
    StorageIntegrityError,
    is_storage_configured,
    object_path,
    resolve_local_pdf,
)

CONTENT = b"%PDF-1.4 card benefit source text"
SHA = hashlib.sha256(CONTENT).hexdigest()
SECRET = "test-secret-value"
ENV = {
    module.URL_ENV: "https://storage.example.test",
    module.SECRET_KEY_ENV: SECRET,
    module.BUCKET_ENV: "card-pdf",
}


class ApiError(Exception):
    """Supabase 오류처럼 status·code를 가진 예외. 메시지에 민감 정보가 있다고 가정한다."""

    def __init__(self, status, code):
        super().__init__(f"url with {SECRET}")
        self.status = status
        self.code = code


class FakeBucket:
    """Supabase Storage 버킷 API와 같은 메서드 형식의 대역."""

    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.upload_calls = []
        self.error = None
        self.upload_error = None

    def list(self, path=None, options=None):
        if self.error:
            raise self.error
        names = [key.removeprefix(f"{path}/") for key in self.objects if key.startswith(f"{path}/")]
        return [{"name": name} for name in names if options["search"] in name]

    def upload(self, path, file, file_options=None):
        self.upload_calls.append((path, file_options))
        if self.upload_error:
            raise self.upload_error
        self.objects[path] = file

    def download(self, path, options=None, query_params=None):
        if self.error:
            raise self.error
        return self.objects[path]


def storage_with(bucket: FakeBucket) -> DocumentStorage:
    client = MagicMock()
    client.storage.from_.return_value = bucket
    return DocumentStorage(client=client, bucket="card-pdf")


class FileCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.path = self.folder / "a.pdf"
        self.path.write_bytes(CONTENT)


class ObjectPathTests(unittest.TestCase):
    def test_path_is_derived_from_hash(self):
        self.assertEqual(object_path(SHA), f"pdf/{SHA}.pdf")

    def test_invalid_hash_is_rejected(self):
        for value in ("", "ABC", SHA.upper(), SHA + "0", "../" + SHA[3:]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                object_path(value)


class ConfigurationTests(unittest.TestCase):
    def test_creating_object_does_not_connect(self):
        with patch("supabase.create_client") as create_client:
            DocumentStorage()
        create_client.assert_not_called()

    def test_car_supabase_variables_are_not_used(self):
        car_env = {"SUPABASE_URL": "https://car.example.test", "SUPABASE_SECRET_KEY": SECRET}
        blank = {name: "" for name in ENV}
        with patch.dict(os.environ, {**car_env, **blank}), patch.object(module, "load_dotenv"):
            self.assertFalse(is_storage_configured())
            with patch("supabase.create_client") as create_client, self.assertRaisesRegex(StorageError, "설정이 없습니다"):
                DocumentStorage().exists(SHA)
            create_client.assert_not_called()

    def test_card_storage_variables_are_used(self):
        with patch.dict(os.environ, ENV), patch.object(module, "load_dotenv"), patch("supabase.create_client") as create_client:
            create_client.return_value.storage.from_.return_value = FakeBucket()
            DocumentStorage().exists(SHA)
        create_client.assert_called_once_with(ENV[module.URL_ENV], SECRET)
        create_client.return_value.storage.from_.assert_called_with("card-pdf")


class ExistsTests(unittest.TestCase):
    def test_object_is_found_by_exact_name(self):
        self.assertTrue(storage_with(FakeBucket({f"pdf/{SHA}.pdf": CONTENT})).exists(SHA))

    def test_missing_object_is_false(self):
        self.assertFalse(storage_with(FakeBucket()).exists(SHA))

    def test_longer_name_is_not_a_match(self):
        self.assertFalse(storage_with(FakeBucket({f"pdf/{SHA}.pdf.bak": CONTENT})).exists(SHA))

    def test_permission_and_network_errors_are_not_treated_as_missing(self):
        for error, expected in ((ApiError(403, "Unauthorized"), "status=403"), (ApiError(400, "InvalidJWT"), "status=400"),
                                (ConnectionError(), "ConnectionError")):
            bucket = FakeBucket()
            bucket.error = error
            with self.subTest(error=error), self.assertRaisesRegex(StorageError, expected):
                storage_with(bucket).exists(SHA)

    def test_upload_stops_when_existence_is_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.pdf"
            path.write_bytes(CONTENT)
            bucket = FakeBucket()
            bucket.error = ApiError(403, "Unauthorized")
            with self.assertRaises(StorageError):
                storage_with(bucket).upload(path, SHA)
        self.assertEqual(bucket.upload_calls, [])


class UploadTests(FileCase):
    def test_upload_uses_hash_path_and_never_overwrites(self):
        bucket = FakeBucket()
        result = storage_with(bucket).upload(self.path, SHA)
        self.assertEqual((result.status, result.object_path, result.size), ("UPLOADED", f"pdf/{SHA}.pdf", len(CONTENT)))
        self.assertEqual(bucket.upload_calls[0][1], {"content-type": "application/pdf", "upsert": "false"})

    def test_existing_object_is_not_uploaded_again(self):
        bucket = FakeBucket({f"pdf/{SHA}.pdf": CONTENT})
        self.assertEqual(storage_with(bucket).upload(self.path, SHA).status, "ALREADY_EXISTS")
        self.assertEqual(bucket.upload_calls, [])

    def test_object_created_by_other_run_counts_as_existing(self):
        for error in (ApiError(400, "Duplicate"), ApiError(409, "Conflict")):
            bucket = FakeBucket()
            bucket.upload_error = error
            self.assertEqual(storage_with(bucket).upload(self.path, SHA).status, "ALREADY_EXISTS")

    def test_file_different_from_expected_hash_is_not_uploaded(self):
        bucket = FakeBucket()
        with self.assertRaises(StorageIntegrityError):
            storage_with(bucket).upload(self.path, "0" * 64)
        self.assertEqual(bucket.upload_calls, [])

    def test_network_error_message_hides_response(self):
        bucket = FakeBucket()
        bucket.upload_error = ConnectionError(f"failed {SECRET}")
        with self.assertRaises(StorageError) as caught:
            storage_with(bucket).upload(self.path, SHA)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)


class DownloadTests(FileCase):
    def test_download_checks_hash(self):
        self.assertEqual(storage_with(FakeBucket({f"pdf/{SHA}.pdf": CONTENT})).download(SHA), CONTENT)

    def test_corrupted_object_is_rejected(self):
        with self.assertRaises(StorageIntegrityError):
            storage_with(FakeBucket({f"pdf/{SHA}.pdf": b"broken"})).download(SHA)

    def test_network_error_becomes_storage_error(self):
        bucket = FakeBucket({f"pdf/{SHA}.pdf": CONTENT})
        bucket.error = TimeoutError()
        with self.assertRaises(StorageError):
            storage_with(bucket).download(SHA)

    def test_restore_writes_missing_file(self):
        target = self.folder / "new" / "b.pdf"
        storage_with(FakeBucket({f"pdf/{SHA}.pdf": CONTENT})).restore(SHA, target)
        self.assertEqual(target.read_bytes(), CONTENT)

    def test_restore_never_overwrites_local_file(self):
        self.path.write_bytes(b"local")
        with self.assertRaises(FileExistsError):
            storage_with(FakeBucket({f"pdf/{SHA}.pdf": CONTENT})).restore(SHA, self.path)
        self.assertEqual(self.path.read_bytes(), b"local")

    def test_corrupted_object_leaves_no_file(self):
        target = self.folder / "c.pdf"
        with self.assertRaises(StorageIntegrityError):
            storage_with(FakeBucket({f"pdf/{SHA}.pdf": b"broken"})).restore(SHA, target)
        self.assertFalse(target.exists())


class ResolveLocalPdfTests(FileCase):
    def test_valid_local_file_does_not_touch_storage(self):
        storage = MagicMock()
        result = resolve_local_pdf(self.path, SHA, storage, allow_download=True)
        self.assertEqual((result.source, result.usable), ("LOCAL", True))
        self.assertEqual(storage.mock_calls, [])

    def test_changed_local_file_is_reported_and_kept(self):
        self.path.write_bytes(b"changed")
        storage = MagicMock()
        result = resolve_local_pdf(self.path, SHA, storage, allow_download=True)
        self.assertEqual((result.source, result.usable), ("HASH_MISMATCH", False))
        self.assertEqual(self.path.read_bytes(), b"changed")
        self.assertEqual(storage.mock_calls, [])

    def test_missing_file_needs_explicit_download(self):
        storage = MagicMock()
        self.assertEqual(resolve_local_pdf(self.folder / "x.pdf", SHA, storage).source, "MISSING")
        self.assertEqual(storage.mock_calls, [])

    def test_missing_file_is_restored_when_requested(self):
        target = self.folder / "x.pdf"
        storage = storage_with(FakeBucket({f"pdf/{SHA}.pdf": CONTENT}))
        result = resolve_local_pdf(target, SHA, storage, allow_download=True)
        self.assertEqual((result.source, result.usable), ("STORAGE", True))
        self.assertEqual(target.read_bytes(), CONTENT)

    def test_storage_failure_is_returned_as_status(self):
        bucket = FakeBucket()
        bucket.error = ConnectionError()
        with self.assertLogs("card_benefit.document_storage", logging.WARNING):
            result = resolve_local_pdf(self.folder / "x.pdf", SHA, storage_with(bucket), allow_download=True)
        self.assertEqual((result.source, result.usable), ("STORAGE_FAILED", False))


class IndependenceTests(unittest.TestCase):
    def test_registration_flow_does_not_depend_on_storage(self):
        from payment_card.db_pipeline import main, register_service

        for target in (document_service, register_service, main):
            self.assertNotIn("document_storage", inspect.getsource(target))


class LogSafetyTests(FileCase):
    def test_logs_contain_no_secret_or_pdf_content(self):
        logger = logging.getLogger("card_benefit.document_storage")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        self.addCleanup(logger.removeHandler, handler)
        storage = storage_with(FakeBucket())
        storage.upload(self.path, SHA)
        storage.download(SHA)
        bucket = FakeBucket()
        bucket.error = ConnectionError(SECRET)
        resolve_local_pdf(self.folder / "x.pdf", SHA, storage_with(bucket), allow_download=True)
        output = stream.getvalue()
        self.assertIn("STORAGE UPLOADED", output)
        self.assertNotIn(SECRET, output)
        self.assertNotIn("card benefit source text", output)


class CliTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "a.pdf").write_bytes(CONTENT)
        self.addCleanup(patch.stopall)
        patch.object(storage_main, "resolve_pdf_path", lambda pdf: (self.root / pdf)).start()
        self.storage_class = patch.object(storage_main, "DocumentStorage").start()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = storage_main.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_commands_without_apply_do_not_create_storage(self):
        for argv in (("status", "--pdf", "a.pdf"), ("upload", "--pdf", "a.pdf"), ("verify", "--pdf", "a.pdf"),
                     ("restore", "--pdf", "a.pdf", "--doc-sha256", SHA)):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv)[0], 0)
        self.storage_class.assert_not_called()

    def test_upload_requires_apply(self):
        self.storage_class.return_value.upload.return_value = module.UploadResult("UPLOADED", f"pdf/{SHA}.pdf", 1)
        code, output, _ = self.run_cli("upload", "--pdf", "a.pdf", "--apply")
        self.assertEqual(code, 0)
        self.assertIn("UPLOADED", output)
        self.storage_class.return_value.upload.assert_called_once_with(self.root / "a.pdf", SHA)

    def test_storage_error_uses_exit_code_three(self):
        self.storage_class.return_value.upload.side_effect = StorageError("Storage 업로드 실패: ConnectionError")
        self.assertEqual(self.run_cli("upload", "--pdf", "a.pdf", "--apply")[0], 3)

    def test_hash_mismatch_uses_exit_code_one(self):
        self.storage_class.return_value.download.side_effect = StorageIntegrityError("다릅니다")
        self.assertEqual(self.run_cli("verify", "--pdf", "a.pdf", "--apply")[0], 1)

    def test_missing_file_is_input_error(self):
        code, _, error = self.run_cli("upload", "--pdf", "missing.pdf", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("없습니다", error)
        self.storage_class.assert_not_called()

    def test_restore_failure_uses_exit_code_three(self):
        self.storage_class.return_value.restore.side_effect = StorageError("실패")
        self.assertEqual(self.run_cli("restore", "--pdf", "new.pdf", "--doc-sha256", SHA, "--apply")[0], 3)

    def test_no_delete_command_exists(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            storage_main.parse_args(["delete", "--pdf", "a.pdf"])


class ResolvePathTests(unittest.TestCase):
    def test_only_pdf_under_data_root_is_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(storage_main.resolve_pdf_path("debit/a.pdf", root), (root / "debit/a.pdf").resolve())
            for value in ("../a.pdf", "a.txt"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    storage_main.resolve_pdf_path(value, root)


if __name__ == "__main__":
    unittest.main()
