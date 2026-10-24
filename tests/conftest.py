"""Shared fixtures: an environment that does not depend on the machine."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_environment(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remove every Hydraulik and Nogat variable and use an empty settings file.

    Tests then see the defaults whatever the developer has exported, and the
    settings file of the user is never read (DEV-18.1).
    """
    for name in list(os.environ):
        if name.startswith(("HYDRAULIK_", "NOGAT_")):
            monkeypatch.delenv(name)
    empty = Path(tmp_path_factory.mktemp("settings")) / "nogat.toml"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(empty))
