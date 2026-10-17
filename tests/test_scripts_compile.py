import pathlib
import py_compile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("path", sorted((ROOT / "scripts").rglob("*.py")))
def test_script_compiles(path):
    py_compile.compile(str(path), doraise=True)
