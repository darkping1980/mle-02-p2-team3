"""Run offline unit tests without inheriting live DB/API credentials.

This script runs all current common, sample, and recipe unittest suites.
It intentionally forces the child processes' live connection variables to
empty strings; python-dotenv's default override=False must respect them.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SUITES = (
    ("common", ROOT / "src/common/tests", ROOT / "src"),
    ("sample-step-01", ROOT / "src/graph_rag_sample/step_01_basic/tests", ROOT / "src"),
    ("sample-step-02", ROOT / "src/graph_rag_sample/step_02_layered/tests", ROOT / "src"),
    ("sample-step-03", ROOT / "src/graph_rag_sample/step_03_llm/tests", ROOT / "src"),
    ("recipe", ROOT / "src/recipe/recipe_recommender/tests", ROOT / "src/recipe"),
)

# Explicitly set empty values so load_dotenv(override=False) cannot restore
# real credentials from a local .env. Offline test runs must not access servers.
BLOCKED_ENV_VARS = (
    "DB_URL",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "CARD_STORAGE_SUPABASE_URL",
    "CARD_STORAGE_SUPABASE_SECRET_KEY",
    "CARD_STORAGE_BUCKET",
    "OPENAI_API_KEY",
    "RUN_NEO4J_INTEGRATION",
    "RUN_GRAPH_RAG_SAMPLE_INTEGRATION",
    "RECIPE_DB_DIAGNOSTIC",
)


def main() -> int:
    env = os.environ.copy()
    for name in BLOCKED_ENV_VARS:
        env[name] = ""
    env["RECIPE_QUERY_LOG"] = "0"

    source_paths = [str(ROOT / "src"), str(ROOT / "src/recipe")]
    if env.get("PYTHONPATH"):
        source_paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(source_paths)

    failed = []
    for name, test_dir, top_dir in SUITES:
        command = (
            sys.executable, "-m", "unittest", "discover", "-s", str(test_dir),
            "-t", str(top_dir), "-p", "test_*.py", "-v",
        )
        print(f"\n=== {name}: offline tests ===", flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if result.returncode != 0:
            failed.append(name)

    if failed:
        print("\nFailed test suites: " + ", ".join(failed))
        return 1
    print("\nAll selected offline suites completed successfully (see skipped tests above).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
