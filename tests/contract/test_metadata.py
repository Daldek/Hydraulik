"""Discovery metadata, version and package data (AGI-10.1, DEV-7.4, REL-1.1)."""

import tomllib
from importlib import resources
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest
from packaging.version import Version

import hydraulik

ROOT = Path(__file__).resolve().parents[2]
PROJECT: dict[str, Any] = tomllib.loads(
    (ROOT / "pyproject.toml").read_text(encoding="utf-8")
)["project"]


def test_description_fits_the_200_character_budget() -> None:
    assert len(PROJECT["description"]) <= 200


def test_keywords_name_at_least_five_search_terms() -> None:
    assert len(PROJECT["keywords"]) >= 5


def test_classifiers_declare_the_package_typed() -> None:
    assert "Typing :: Typed" in PROJECT["classifiers"]


@pytest.mark.parametrize(
    "name", ["Homepage", "Source", "Documentation", "Changelog", "Issues"]
)
def test_project_urls_carry_every_required_entry(name: str) -> None:
    assert PROJECT["urls"][name].startswith("https://github.com/Daldek/Hydraulik")


def test_version_is_pep440_and_equals_the_installed_metadata() -> None:
    assert str(Version(hydraulik.__version__)) == hydraulik.__version__
    assert version("hydraulik") == hydraulik.__version__


def test_py_typed_marker_ships_inside_the_package() -> None:
    assert resources.files("hydraulik").joinpath("py.typed").is_file()
