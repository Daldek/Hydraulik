"""AGENTS.md and llms.txt equal their generator and stay within budget (DEV-10.4)."""

import re
from pathlib import Path

from hydraulik import agent_guide
from hydraulik.catalog.commands import COMMANDS

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_agents_md_equals_the_generator_output() -> None:
    assert _read("AGENTS.md") == agent_guide.render_agents()


def test_llms_txt_equals_the_generator_output() -> None:
    assert _read("llms.txt") == agent_guide.render_llms()


def test_agents_md_stays_within_200_lines_and_16_kib() -> None:
    text = _read("AGENTS.md")

    assert len(text.splitlines()) <= 200
    assert len(text.encode("utf-8")) <= 16 * 1024


def test_agents_md_ends_with_the_pointer_for_developers() -> None:
    assert _read("AGENTS.md").rstrip().splitlines()[-1] == (
        "Developing this repository? Read CLAUDE.md."
    )


def test_agents_md_indexes_every_command() -> None:
    text = _read("AGENTS.md")

    for command in COMMANDS:
        assert f"- `{command.name}`" in text


def test_llms_txt_follows_the_llms_txt_format() -> None:
    lines = _read("llms.txt").splitlines()
    first_list = next(i for i, line in enumerate(lines) if line.startswith("## "))
    before = "\n".join(lines[:first_list])

    assert lines[0] == "# Hydraulik"
    assert lines[2].startswith("> ")
    assert len(before) <= 8000
    for line in lines[first_list:]:
        if line.startswith("- "):
            assert re.fullmatch(r"- \[[^\]]+\]\(https://[^)]+\): .+", line)
        else:
            assert line.startswith("## ") or not line.strip()


def test_llms_txt_links_are_raw_not_rendered_pages() -> None:
    for url in re.findall(r"\]\((https://[^)]+)\)", _read("llms.txt")):
        assert url.startswith("https://raw.githubusercontent.com/Daldek/Hydraulik/")


def test_block_for_consumers_fits_60_lines_and_is_delimited() -> None:
    block = agent_guide.render_block()

    assert len(block.splitlines()) <= 60
    assert block.startswith(agent_guide.BEGIN_MARKER)
    assert block.rstrip().endswith(agent_guide.END_MARKER)


def test_every_step_of_a_flow_names_a_command_of_the_catalog() -> None:
    names = {command.name for command in COMMANDS}

    for flow in agent_guide.FLOWS:
        assert flow.steps
        for command, _ in flow.steps:
            assert command in names
