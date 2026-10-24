"""The command-line interface: envelope, errors, languages and exit codes."""

import json
from pathlib import Path

import pytest

from hydraulik.cli import main


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_json_prints_exactly_one_envelope_and_nothing_else(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(capsys, "config", "show", "--json")

    envelope = json.loads(out)
    assert code == 0
    assert (envelope["schema"], envelope["command"], envelope["status"]) == (
        "hydraulik-result/1",
        "config show",
        "ok",
    )
    assert envelope["check"] is False
    assert err == ""


def test_global_options_work_before_and_after_the_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = _run(capsys, "--json", "config", "show")[1]
    after = _run(capsys, "config", "show", "--json")[1]

    assert json.loads(before) == json.loads(after)


def test_an_error_leaves_stdout_empty_and_ends_stderr_with_the_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(
        capsys, "commands", "schema", "--command", "no such", "--json"
    )

    document = json.loads(err.strip().splitlines()[-1])
    assert (code, out) == (2, "")
    assert document["code"] == "validation_error"
    assert document["details"]["reason"] == "unknown_command"
    assert document["exit_code"] == 2
    assert document["command"] == "commands schema"


def test_the_error_document_is_english_whatever_the_language(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, _, err_pl = _run(
        capsys, "commands", "schema", "--command", "x y", "--lang", "pl"
    )
    _, _, err_en = _run(
        capsys, "commands", "schema", "--command", "x y", "--lang", "en"
    )

    assert err_pl.strip().splitlines()[-1] == err_en.strip().splitlines()[-1]
    assert "Błąd" in err_pl
    assert "Error" in err_en


def test_human_output_follows_the_language_setting(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRAULIK_LANG", "pl")
    pl = _run(capsys, "config", "show")[1]
    monkeypatch.setenv("HYDRAULIK_LANG", "en")
    en = _run(capsys, "config", "show")[1]

    assert pl.startswith("config show: Wynik, OK")
    assert en.startswith("config show: Result, ok")


def test_lang_option_wins_over_the_environment(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRAULIK_LANG", "pl")

    out = _run(capsys, "config", "show", "--lang", "en")[1]

    assert out.startswith("config show: Result, ok")


def test_unknown_option_is_a_usage_error_with_the_exit_code_of_the_registry(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(capsys, "config", "show", "--nope")

    assert (code, out) == (2, "")
    assert json.loads(err.strip().splitlines()[-1])["details"]["reason"] == "usage"


def test_missing_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _run(capsys, "--json")

    assert code == 2
    assert json.loads(err.strip().splitlines()[-1])["details"]["reason"] == "usage"


def test_invalid_value_names_the_option(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _run(capsys, "commands", "guide", "--format", "pdf", "--json")

    document = json.loads(err.strip().splitlines()[-1])
    assert code == 2
    assert document["details"]["option"] == "format"
    assert document["details"]["allowed"] == ["agents", "llms", "agents-md-block"]


def test_version_and_help_exit_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(capsys, "--version")[0] == 0
    code, out, _ = _run(capsys, "commands", "guide", "--help")

    assert code == 0
    assert out.startswith("usage: hydraulik commands guide")
    assert "agents-md-block = compact block" in out
    assert "examples:" in out


def test_commands_guide_prints_the_raw_text_without_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = _run(capsys, "commands", "guide", "--format", "agents")

    assert code == 0
    assert out.startswith("# Hydraulik: agent guide")


def test_injection_changes_the_named_file_and_a_second_run_changes_nothing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# Consumer\n", encoding="utf-8")
    args = ("commands", "guide", "--format", "agents-md-block", "--inject", str(target))

    first = json.loads(_run(capsys, *args, "--json")[1])["result"]
    text = target.read_text(encoding="utf-8")
    second = json.loads(_run(capsys, *args, "--json")[1])["result"]

    assert (first["changed"], second["changed"]) == (True, False)
    assert text.startswith("# Consumer\n\n<!-- BEGIN hydraulik -->")
    assert target.read_text(encoding="utf-8") == text


def test_injection_check_plans_without_writing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# Consumer\n", encoding="utf-8")

    code, out, _ = _run(
        capsys,
        "commands",
        "guide",
        "--format",
        "agents-md-block",
        "--inject",
        str(target),
        "--check",
        "--json",
    )

    envelope = json.loads(out)
    assert code == 0
    assert envelope["check"] is True
    assert envelope["result"]["changed"] is True
    assert target.read_text(encoding="utf-8") == "# Consumer\n"


def test_injection_replaces_an_existing_block_in_place(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "# C\n<!-- BEGIN hydraulik -->\nold\n<!-- END hydraulik -->\n# After\n",
        encoding="utf-8",
    )

    _run(
        capsys,
        "commands",
        "guide",
        "--format",
        "agents-md-block",
        "--inject",
        str(target),
    )

    text = target.read_text(encoding="utf-8")
    assert "old" not in text
    assert text.startswith("# C\n<!-- BEGIN hydraulik -->")
    assert text.endswith("<!-- END hydraulik -->\n# After\n")


def test_inject_with_another_format_is_refused(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("x", encoding="utf-8")

    code, _, err = _run(
        capsys, "commands", "guide", "--format", "llms", "--inject", str(target)
    )

    assert code == 2
    assert json.loads(err.strip().splitlines()[-1])["details"]["reason"] == (
        "inject_needs_block"
    )


def test_inject_into_a_missing_file_is_not_found(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, _, err = _run(
        capsys,
        "commands",
        "guide",
        "--format",
        "agents-md-block",
        "--inject",
        str(tmp_path / "none.md"),
    )

    assert code == 3
    assert json.loads(err.strip().splitlines()[-1])["code"] == "not_found"


def test_a_broken_settings_file_is_reported_not_traced(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("[hydraulik\n", encoding="utf-8")
    monkeypatch.setenv("NOGAT_CONFIG", str(bad))

    code, out, err = _run(capsys, "config", "show", "--json")

    assert (code, out) == (7, "")
    assert json.loads(err.strip().splitlines()[-1])["code"] == "data_error"
