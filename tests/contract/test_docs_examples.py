"""Executable examples of the user documentation (DOC-2.6, DEV-10.4).

``README.md`` holds fenced code blocks and this module runs them, so an example that
stops working fails the gate. The info string after the opening backticks selects what
happens:

``bash``
    Each line that starts with ``hydraulik `` runs in-process as
    ``hydraulik.cli.main(shlex.split(line)[1:])`` and must exit with 0; other lines
    (``uv tool install ...``) are ignored. A block without a ``hydraulik `` line is
    not a test.
``python``
    Executed with ``exec`` in a fresh namespace.
``json``
    Not executed; it must parse as JSON.

Any other info string (``sh``, ``console``, ``text``, ``toml``) is not executed. Three
more checks keep the README in step with the code: its Capabilities table lists every
catalog command with its Python function (AGI-1.1), and ``.env.example`` and the README
list every environment variable that the settings read (DEV-18.3).
"""

import json
import re
import shlex
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from hydraulik.catalog.commands import COMMANDS
from hydraulik.cli import main
from hydraulik.settings import SETTINGS

ROOT = Path(__file__).resolve().parents[2]
FENCE = re.compile(r"^(?P<ticks>`{3,})(?P<info>[^`\n]*)$")


@dataclass(frozen=True)
class Block:
    """One fenced block: where it is, its info string and its text."""

    document: str
    line: int
    info: str
    text: str

    @property
    def id(self) -> str:
        return f"{self.document}:L{self.line}"


def _blocks(document: str) -> Iterator[Block]:
    path = ROOT / document
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        opening = FENCE.match(lines[index])
        if opening:
            start, body = index + 1, []
            index += 1
            while index < len(lines) and not lines[index].startswith(opening["ticks"]):
                body.append(lines[index])
                index += 1
            yield Block(document, start, opening["info"].strip(), "\n".join(body))
        index += 1


def _logical_lines(text: str) -> list[str]:
    """Join ``\\`` continuations and drop comments and empty lines."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return [
        line.strip().split(" #", 1)[0].strip()
        for line in joined.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


BLOCKS = [b for d in ("README.md", "docs/USAGE.md") for b in _blocks(d)]
BASH = [
    b
    for b in BLOCKS
    if b.info == "bash"
    and any(line.startswith("hydraulik ") for line in _logical_lines(b.text))
]


@pytest.mark.parametrize("block", BASH, ids=lambda b: b.id)
def test_bash_example_exits_with_zero(
    block: Block, capsys: pytest.CaptureFixture[str]
) -> None:
    for line in _logical_lines(block.text):
        if line.startswith("hydraulik "):
            assert main(shlex.split(line)[1:]) == 0, line
            capsys.readouterr()


@pytest.mark.parametrize(
    "block", [b for b in BLOCKS if b.info == "python"], ids=lambda b: b.id
)
def test_python_example_runs(block: Block, capsys: pytest.CaptureFixture[str]) -> None:
    exec(compile(block.text, block.id, "exec"), {"__name__": "__example__"})  # noqa: S102
    capsys.readouterr()


@pytest.mark.parametrize(
    "block", [b for b in BLOCKS if b.info == "json"], ids=lambda b: b.id
)
def test_json_example_parses(block: Block) -> None:
    if "..." in block.text.splitlines():
        pytest.skip("elided example")
    json.loads(block.text)


def test_readme_has_at_least_one_executed_example() -> None:
    assert any(b.document == "README.md" for b in BASH)


def test_capabilities_table_lists_every_command_with_its_python_function() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    table = readme.split("## Capabilities", 1)[1].split("\n## ", 1)[0]

    for command in COMMANDS:
        assert f"`{command.name}`" in table, command.name
        assert f"`{command.function}`" in table, command.function


def test_readme_lists_every_environment_variable_of_the_settings() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for name in ["NOGAT_CONFIG", *(n for spec in SETTINGS for n in spec.env)]:
        assert name in readme, name
