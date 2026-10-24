"""``engines check``: what is reported, what ``--require`` refuses, nothing started."""

import json
from collections.abc import Callable

import pytest

from hydraulik import check_engines
from hydraulik.cli import main
from hydraulik.engines.detect import EngineStatus
from hydraulik.exceptions import InvalidInputError, MissingDependencyError


def _status(name: str, found: bool, hint: str | None = None) -> EngineStatus:
    return EngineStatus(
        name,
        found,
        "path" if found else None,
        f"/opt/{name}" if found else None,
        "1.0" if found else None,
        "found" if found else f"{name} is missing",
        None if found else hint,
    )


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Fake detection: SFINCS and SWMM found, the library and Kartograf not."""
    present = {
        "sfincs": True,
        "sfincs-library": False,
        "swmm": True,
        "kartograf": False,
    }
    hints = {"sfincs-library": "Build libsfincs.", "kartograf": "Install Kartograf."}

    def detector(name: str) -> Callable[..., EngineStatus]:
        def detect(*_args: object) -> EngineStatus:
            return _status(name, present[name], hints.get(name))

        return detect

    monkeypatch.setattr(
        "hydraulik.operations.engines.detect_sfincs",
        lambda settings: (_status("sfincs", present["sfincs"]), None),
    )
    for function, name in (
        ("detect_sfincs_library", "sfincs-library"),
        ("detect_swmm", "swmm"),
        ("detect_kartograf", "kartograf"),
    ):
        monkeypatch.setattr(f"hydraulik.operations.engines.{function}", detector(name))
    return present


def test_the_four_programs_the_packages_and_every_feature_are_listed(
    machine: dict[str, bool],
) -> None:
    body = check_engines().to_dict()

    assert body["schema"] == "hydraulik-engines/1"
    assert [(e["name"], e["found"]) for e in body["engines"]] == [
        ("sfincs", True),
        ("sfincs-library", False),
        ("swmm", True),
        ("kartograf", False),
    ]
    assert {x["name"] for x in body["extras"]} >= {"numpy", "netCDF4", "pyswmm"}
    features = {f["command"]: f for f in body["features"]}
    assert set(features) == {
        "terrain download",
        "rainfall build",
        "model build",
        "model run",
        "results read",
        "results export",
        "swmm run",
        "model couple",
    }
    assert features["terrain download"]["missing"] == ["kartograf"]
    assert "sfincs-library" in features["model couple"]["missing"]
    assert features["model couple"]["available"] is False
    assert features["model run"]["needs"] == ["sfincs", "numpy", "netCDF4"]


def test_require_passes_when_the_commands_can_run_here(
    machine: dict[str, bool],
) -> None:
    document = check_engines(require=["swmm run", "results read"])

    assert document.status == "ok"


def test_require_fails_with_everything_that_is_missing_and_how_to_fix_it(
    machine: dict[str, bool],
) -> None:
    with pytest.raises(MissingDependencyError) as caught:
        check_engines(require=["model couple", "terrain download", "swmm run"])

    error = caught.value
    assert (
        error.code == "missing_dependency"
        and error.details["reason"] == "engine_missing"
    )
    assert error.details["commands"] == ["model couple", "terrain download"]
    assert "sfincs-library" in str(error) and "kartograf" in str(error)
    assert error.hint is not None
    assert "Build libsfincs." in error.hint and "Install Kartograf." in error.hint


def test_a_command_that_needs_nothing_special_is_not_a_valid_require(
    machine: dict[str, bool],
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        check_engines(require=["config show"])

    assert caught.value.details["reason"] == "not_allowed"


def test_the_cli_validates_the_values_of_require_and_fails_with_exit_code_six(
    machine: dict[str, bool], capsys: pytest.CaptureFixture[str]
) -> None:
    bad = main(["engines", "check", "--require", "config show", "--json"])
    bad_error = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    missing = main(["engines", "check", "--require", "model couple", "--json"])
    missing_error = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    fine = main(["engines", "check", "--json"])
    envelope = json.loads(capsys.readouterr().out)

    assert (bad, bad_error["details"]["reason"]) == (2, "not_allowed")
    assert (missing, missing_error["code"]) == (6, "missing_dependency")
    assert fine == 0 and envelope["result"]["schema"] == "hydraulik-engines/1"
