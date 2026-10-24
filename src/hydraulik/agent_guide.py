"""AGENTS.md, llms.txt and the block for other repositories (AGI §8, DOC §4, DOC §5).

The guides are rendered from the command catalog and the templates in
``hydraulik/_data/agents/``; ``AGENTS.md`` and ``llms.txt`` in the repository root are
never edited by hand, and a contract test compares them with this output (DEV-10.4).
"""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from importlib.metadata import metadata
from typing import Final

from hydraulik.catalog.commands import COMMANDS
from hydraulik.catalog.spec import CommandSpec

__all__ = [
    "BEGIN_MARKER",
    "END_MARKER",
    "FLOWS",
    "Flow",
    "render_agents",
    "render_block",
    "render_llms",
]

BEGIN_MARKER: Final = "<!-- BEGIN hydraulik -->"
END_MARKER: Final = "<!-- END hydraulik -->"
RAW: Final = "https://raw.githubusercontent.com/Daldek/Hydraulik/main"


@dataclass(frozen=True)
class Flow:
    """A typical sequence of commands.

    Attributes
    ----------
    title : str
        What the flow achieves.
    steps : tuple of (str, str)
        Catalog name of each command and a note on what the step is for.
    """

    title: str
    steps: tuple[tuple[str, str], ...]


FLOWS: Final[tuple[Flow, ...]] = (
    Flow(
        "Learn the interface without any engine",
        (
            ("commands list", "See every command"),
            ("commands schema", "Read the options of one command"),
        ),
    ),
    Flow(
        "See how the settings were resolved",
        (("config show", "List each setting with its value and source"),),
    ),
)
"""Typical flows; every step names a command of the catalog (checked by a test)."""


def _summary() -> str:
    return metadata("hydraulik")["Summary"]


def _by_name(name: str) -> CommandSpec:
    return next(spec for spec in COMMANDS if spec.name == name)


def _command_index() -> str:
    return "\n".join(
        f"- `{spec.name}` (`hydraulik.{spec.python_name}`): {spec.summary} "
        f"Details: `hydraulik commands schema --command '{spec.name}'`."
        for spec in COMMANDS
    )


def _flows() -> str:
    parts: list[str] = []
    for flow in FLOWS:
        steps = "\n".join(
            f"{number}. {note}: `{_by_name(name).examples[0].call}`"
            for number, (name, note) in enumerate(flow.steps, start=1)
        )
        parts.append(f"**{flow.title}**\n\n{steps}")
    return "\n\n".join(parts)


def _template(name: str) -> str:
    return (
        importlib.resources.files("hydraulik")
        .joinpath("_data", "agents", name)
        .read_text(encoding="utf-8")
    )


def render_agents() -> str:
    """Render ``AGENTS.md`` (DOC-4.2).

    Returns
    -------
    str
        The guide for agents that use the tool, ending with the pointer to
        ``CLAUDE.md`` for agents that develop it.
    """
    return (
        _template("agents.md")
        .replace("{{summary}}", _summary())
        .replace("{{command_index}}", _command_index())
        .replace("{{flows}}", _flows())
    )


def render_llms() -> str:
    """Render ``llms.txt`` (DOC-5.1): H1, summary, link list with raw links.

    Returns
    -------
    str
        The file text.
    """
    entries = (
        ("README", "README.md", "what the tool is for, install, settings, licences"),
        (
            "AGENTS.md",
            "AGENTS.md",
            "how an agent calls the tool, result and error documents",
        ),
        ("CHANGELOG", "docs/CHANGELOG.md", "what changed between versions"),
        ("Decisions", "docs/DECISIONS.md", "why the tool is built the way it is"),
        (
            "Extraction note",
            "docs/plans/2026-10-24-sfincs-swmm-extraction.md",
            "what earlier SFINCS and SWMM work found",
        ),
    )
    links = "\n".join(
        f"- [{title}]({RAW}/{path}): {note}" for title, path, note in entries
    )
    return (
        _template("llms.md")
        .replace("{{summary}}", _summary())
        .replace("{{links}}", links)
    )


def render_block() -> str:
    """Render the compact block for the AGENTS.md of a consumer repository (AGI-8.2).

    Returns
    -------
    str
        The block between :data:`BEGIN_MARKER` and :data:`END_MARKER`.
    """
    lines = "\n".join(f"- `{spec.name}`: {spec.summary}" for spec in COMMANDS)
    return _template("block.md").replace("{{command_lines}}", lines)
