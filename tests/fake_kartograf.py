"""Install the fake Kartograf for a test and read what it was asked.

The program is :mod:`tests.fake_kartograf_program`, started with the interpreter of the
test, so it works wherever the tests run. ``scenario`` is described in that module.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from hydraulik.engines.detect import EngineStatus, inspect_kartograf

PROGRAM = Path(__file__).with_name("fake_kartograf_program.py")


@dataclass(frozen=True)
class FakeKartograf:
    """A fake Kartograf: the command that starts it and the log of what it was asked.

    Attributes
    ----------
    words : tuple of str
        The command (the interpreter and the script).
    log : Path
        One JSON line with the arguments of every call.
    """

    words: tuple[str, ...]
    log: Path

    def calls(self) -> list[list[str]]:
        """Return the arguments of every call, in order."""
        if not self.log.exists():
            return []
        lines = self.log.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def probes(self) -> list[list[str]]:
        """Return the calls that only ask for the version or the schema."""
        return [
            c
            for c in self.calls()
            if c == ["--version"] or c[:2] == ["commands", "schema"]
        ]

    def plans(self) -> list[list[str]]:
        """Return the calls with ``--check``."""
        return [c for c in self.calls() if "--check" in c]

    def downloads(self) -> list[list[str]]:
        """Return the calls that fetch data: neither a probe nor a plan."""
        skip = [*self.probes(), *self.plans()]
        return [c for c in self.calls() if c not in skip]


def install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **scenario: Any
) -> FakeKartograf:
    """Make the fake the Kartograf of the next calls and return it.

    The scenario goes to the environment of the program; the log is in ``tmp_path``.
    """
    log = tmp_path / "kartograf-calls.log"
    monkeypatch.setenv("FAKE_KARTOGRAF", json.dumps({**scenario, "log": str(log)}))
    return FakeKartograf((sys.executable, str(PROGRAM)), log)


def use(
    monkeypatch: pytest.MonkeyPatch, fake: FakeKartograf, *, timeout_s: float = 60.0
) -> EngineStatus:
    """Make ``terrain download`` find the fake and return what it found of it."""
    status, words = inspect_kartograf(fake.words, "setting", timeout_s=timeout_s)
    monkeypatch.setattr(
        "hydraulik.operations.terrain.find_kartograf", lambda settings: (status, words)
    )
    return status
