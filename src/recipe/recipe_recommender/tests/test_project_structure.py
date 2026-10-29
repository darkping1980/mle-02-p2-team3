"""Small checks for imports and execution from outside the task directory."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.config import PACKAGE_DIR


class ProjectStructureTests(unittest.TestCase):
    def test_expected_package_files_exist(self):
        for relative in (
            "__init__.py",
            "config.py",
            "main.py",
            "setup/__init__.py",
            "setup/register_recipe_csv.py",
            "setup/load_recipe_graph.py",
            "tools/check_neo4j_connection.py",
            "tools/check_supabase_connection.py",
        ):
            with self.subTest(path=relative):
                self.assertTrue((PACKAGE_DIR / relative).is_file())

    def test_main_runs_from_an_unrelated_working_directory(self):
        main_file = PACKAGE_DIR / "main.py"
        with tempfile.TemporaryDirectory() as unrelated_cwd:
            result = subprocess.run(
                [sys.executable, str(main_file)],
                cwd=unrelated_cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("scaffold is ready", result.stdout)

    def test_graph_mapper_loads_from_an_unrelated_working_directory(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(TASK_DIR) + os.pathsep + environment.get("PYTHONPATH", "")
        code = (
            "from unittest.mock import Mock; "
            "from recipe_recommender.recipe_graph_repository import RecipeGraphRepository; "
            "repository = RecipeGraphRepository(driver=Mock(), database='neo4j'); "
            "print(len(repository.mapper.mappers))"
        )
        with tempfile.TemporaryDirectory() as unrelated_cwd:
            result = subprocess.run(
                [sys.executable, "-c", code], cwd=unrelated_cwd, env=environment,
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "55")


if __name__ == "__main__":
    unittest.main()

