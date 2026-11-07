import json
import re
from pathlib import Path

import pytest


FILE_PIPELINE = Path(__file__).parents[1] / "file_pipeline"
NOTEBOOKS = FILE_PIPELINE / "notebooks"
MODULE_LIST = NOTEBOOKS / "모듈-점검-목록.md"


def _assert_empty_outputs(paths):
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert all(not cell.get("outputs", []) for cell in document["cells"] if cell.get("cell_type") == "code"), path


def _modules():
    modules = {
        path.stem
        for directory in (FILE_PIPELINE / "extraction", FILE_PIPELINE / "graph")
        for path in directory.rglob("*.py")
        if path.name != "__init__.py"
    }
    # chat/ 모듈은 이름 충돌을 피하려고 'chat/<모듈>' 로 목록에 적는다.
    modules |= {
        f"chat/{path.relative_to(FILE_PIPELINE / 'chat').with_suffix('').as_posix()}"
        for path in (FILE_PIPELINE / "chat").rglob("*.py")
        if path.name != "__init__.py"
    }
    return modules


def _entries():
    entries = {}
    for line in MODULE_LIST.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"\|\s*([^|]+?)\s*\|\s*(있음|예정)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if match:
            module, status, notebook, title = (part.strip() for part in match.groups())
            entries[module] = (status, notebook, title)
    return entries


def test_every_extraction_and_graph_module_is_listed():
    assert _modules() == set(_entries())


def test_listed_notebooks_exist_and_have_empty_code_outputs():
    for module, (status, notebook, _title) in _entries().items():
        if status == "예정":
            continue
        path = NOTEBOOKS / notebook
        document = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(document.get("cells"), list), module
        assert all(not cell.get("outputs", []) for cell in document["cells"] if cell.get("cell_type") == "code"), module


def test_all_notebooks_have_empty_outputs():
    notebooks = [path for path in NOTEBOOKS.rglob("*.ipynb") if ".ipynb_checkpoints" not in path.parts]
    assert notebooks, "no notebooks found"
    _assert_empty_outputs(notebooks)


def test_nested_notebook_with_output_is_rejected(tmp_path):
    nested_notebooks = tmp_path / "notebooks"
    nested_notebooks.mkdir()
    nested = nested_notebooks / "학습용"
    nested.mkdir()
    notebook = nested / "practice.ipynb"
    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "code", "outputs": [{"output_type": "stream", "text": "sample"}]}
                ]
            }
        ),
        encoding="utf-8",
    )

    discovered = list(nested_notebooks.rglob("*.ipynb"))

    assert discovered == [notebook]
    with pytest.raises(AssertionError):
        _assert_empty_outputs(discovered)
