"""The public API is exactly ``__all__`` and type-checks for a consumer (AGI-7.1)."""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

import hydraulik


@pytest.mark.parametrize("name", hydraulik.__all__)
def test_every_name_in_all_can_be_imported(name: str) -> None:
    assert hasattr(importlib.import_module("hydraulik"), name)


def test_public_names_are_documented() -> None:
    for name in hydraulik.__all__:
        if name != "__version__":
            assert getattr(hydraulik, name).__doc__


def test_importing_the_package_loads_no_heavy_dependency() -> None:
    code = (
        "import sys, hydraulik;"
        "heavy = {'numpy','rasterio','geopandas','netCDF4','pyswmm','hydrolog',"
        "'imgwtools','pandas','shapely'};"
        "print(sorted(heavy & set(sys.modules)))"
    )

    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert done.stdout.strip() == "[]"


def test_a_consumer_snippet_type_checks_with_mypy(tmp_path: Path) -> None:
    from mypy import api

    snippet = tmp_path / "consumer.py"
    snippet.write_text(
        "import hydraulik\n"
        "from hydraulik import HydraulikError, run_command\n"
        "doc: hydraulik.Document = run_command('config show')\n"
        "text: str = doc.to_json()\n"
        "data: dict[str, object] = doc.to_dict()\n"
        "catalog: hydraulik.CommandsDocument = hydraulik.list_commands()\n"
        "try:\n"
        "    hydraulik.validate_command('commands guide', format='llms')\n"
        "except HydraulikError as exc:\n"
        "    code: str = exc.code\n",
        encoding="utf-8",
    )

    stdout, stderr, status = api.run(["--strict", "--no-incremental", str(snippet)])

    assert status == 0, stdout + stderr
