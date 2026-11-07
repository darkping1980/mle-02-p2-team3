"""run_fp_chat.py 진입점 시험: DB·OpenAI 호출 없이 화면 로딩 경로만 확인한다.

install()이 sys.modules['llm']을 바꾸므로 각 경우를 별도 프로세스에서 실행한다.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ENTRY = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat" / "run_fp_chat.py"
SRC = Path(__file__).resolve().parents[3].parent  # .../src

SCRIPT = """
import sys
from streamlit.testing.v1 import AppTest
at = AppTest.from_file({entry!r}, default_timeout=60)
at.run()
print("EXC", len(at.exception))
print("ERR", [e.value for e in at.error])
print("INFO", [i.value for i in at.info])
import os
print("DBURL_SET", bool(os.environ.get("DB_URL")))
print("DBURL_TAIL", repr(os.environ.get("DB_URL", "")[-8:]))
"""


def _run(env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "DB_URL")}
    env["FP_CHAT_ENV_FILE"] = "/nonexistent/.env"  # 실제 .env를 읽지 않도록 막는다
    env.update(env_extra)
    env["PYTHONPATH"] = os.pathsep.join([str(SRC), str(SRC / "card_benefit")])
    return subprocess.run(
        [sys.executable, "-c", SCRIPT.format(entry=str(ENTRY))],
        capture_output=True, text=True, timeout=120, env=env,
    ).stdout


class RunEntryTest(unittest.TestCase):
    def test_missing_key_shows_message_instead_of_crashing(self):
        out = _run({})
        self.assertIn("EXC 0", out)
        self.assertIn("OPENAI_API_KEY", out)

    def test_with_key_loads_fp_chat_mode_without_network(self):
        out = _run({"OPENAI_API_KEY": "dummy-no-call"})
        self.assertIn("EXC 0", out)
        self.assertIn("우리 카드 데이터(fp_chat) 모드", out)

    def test_key_from_dotenv_file_without_export(self):
        with tempfile.TemporaryDirectory() as d:
            envf = Path(d) / ".env"
            envf.write_text("OPENAI_API_KEY=dummy-no-call\n", encoding="utf-8")
            out = _run({"FP_CHAT_ENV_FILE": str(envf)})
        self.assertIn("EXC 0", out)
        self.assertIn("우리 카드 데이터(fp_chat) 모드", out)

    def test_fp_database_url_fills_db_url_when_missing(self):
        out = _run({"OPENAI_API_KEY": "dummy-no-call", "FP_DATABASE_URL": "postgresql://dummy"})
        self.assertIn("DBURL_SET True", out)

    def test_db_uri_fills_db_url_when_only_it_exists(self):
        out = _run({"OPENAI_API_KEY": "dummy-no-call", "DB_URI": "postgresql://dummy"})
        self.assertIn("DBURL_SET True", out)

    def test_db_url_stays_unset_without_either(self):
        out = _run({"OPENAI_API_KEY": "dummy-no-call"})
        self.assertIn("DBURL_SET False", out)

    def test_trailing_carriage_return_in_exported_value_is_stripped(self):
        # 셸 source 로 CRLF .env 를 읽은 터미널은 값 끝에 '\r' 이 남아 DB 이름이 'postgres\r' 이 된다(실제 장애).
        out = _run({"OPENAI_API_KEY": "dummy-no-call", "DB_URI": "postgresql://dummy/postgres\r"})
        self.assertIn("DBURL_SET True", out)
        self.assertIn("DBURL_TAIL 'postgres'", out)
        self.assertNotIn("\\r", out)

    def test_exported_value_wins_over_dotenv(self):
        with tempfile.TemporaryDirectory() as d:
            envf = Path(d) / ".env"
            envf.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
            out = _run({"FP_CHAT_ENV_FILE": str(envf), "OPENAI_API_KEY": "exported"})
        self.assertIn("EXC 0", out)


if __name__ == "__main__":
    unittest.main()
