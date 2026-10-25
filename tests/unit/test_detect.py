"""Finding the engines: settings, PATH, Docker and the Python package of SWMM."""

import importlib.metadata
import importlib.util
import sys
from pathlib import Path

import pytest

from hydraulik.engines import detect
from hydraulik.settings import Settings, load_settings

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="the fake programs are scripts with a shebang"
)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return load_settings(overrides, environ={}, config_file=tmp_path / "none.toml")


def _script(path: Path, body: str) -> str:
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


@posix_only
def test_sfincs_executable_from_the_setting_reports_the_banner_version(
    tmp_path: Path,
) -> None:
    exe = _script(tmp_path / "sfincs", 'print("Build-Revision: $Rev: v9.9.9 Fake")')

    status, install = detect.detect_sfincs(_settings(tmp_path, **{"sfincs.exe": exe}))

    assert (status.found, status.via, status.version) == (
        True,
        "setting",
        "v9.9.9 Fake",
    )
    assert install is not None and install.kind == "exe" and install.command == (exe,)


@posix_only
def test_sfincs_on_path_is_found_when_no_setting_names_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _script(tmp_path / "sfincs", 'print("Build-Revision: $Rev: v1.2.3")')
    monkeypatch.setenv("PATH", str(tmp_path))

    status, install = detect.detect_sfincs(_settings(tmp_path))

    assert (status.found, status.via, status.version) == (True, "path", "v1.2.3")
    assert install is not None


def test_a_setting_that_names_a_missing_file_is_not_replaced_by_another(
    tmp_path: Path,
) -> None:
    status, install = detect.detect_sfincs(
        _settings(tmp_path, **{"sfincs.exe": str(tmp_path / "gone")})
    )

    assert not status.found and install is None
    assert "does not exist" in status.detail
    assert status.hint is not None and "HYDRAULIK_SFINCS_EXE" in status.hint


def test_nothing_found_says_that_hydraulik_installs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    status, install = detect.detect_sfincs(
        _settings(tmp_path, **{"docker.exe": "no-such-docker-command"})
    )

    assert not status.found and install is None
    assert status.hint is not None and "never installs" in status.hint


@posix_only
def test_a_docker_image_that_is_present_is_found_without_being_pulled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker = _script(
        tmp_path / "docker",
        "import sys\nsys.exit(0 if sys.argv[1:3] == ['image', 'inspect'] else 9)",
    )
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    status, install = detect.detect_sfincs(
        _settings(tmp_path, **{"docker.exe": docker})
    )

    assert (status.found, status.via, status.version) == (True, "docker", "v2.4.1")
    assert install is not None and install.image == "deltares/sfincs-cpu:sfincs-v2.4.1"


@posix_only
def test_a_docker_image_that_is_absent_is_reported_with_the_pull_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker = _script(
        tmp_path / "docker",
        'import sys\nsys.stderr.write("no such image")\nsys.exit(1)',
    )
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    status, install = detect.detect_sfincs(
        _settings(tmp_path, **{"docker.exe": docker})
    )

    assert not status.found and install is None
    assert "no such image" in status.detail
    assert status.hint is not None and "docker pull" in status.hint


def test_library_is_found_only_when_the_setting_names_an_existing_file(
    tmp_path: Path,
) -> None:
    library = tmp_path / "libsfincs.so"
    library.write_bytes(b"")

    unset = detect.detect_sfincs_library(_settings(tmp_path))
    missing = detect.detect_sfincs_library(
        _settings(tmp_path, **{"sfincs.library": str(tmp_path / "gone.so")})
    )
    found = detect.detect_sfincs_library(
        _settings(tmp_path, **{"sfincs.library": str(library)})
    )

    assert not unset.found and unset.hint is not None
    assert "enable-shared" in unset.hint
    assert not missing.found and "does not exist" in missing.detail
    assert found.found and found.location == str(library.resolve())


def test_swmm_is_found_when_pyswmm_is_installed() -> None:
    pytest.importorskip("pyswmm")

    status = detect.detect_swmm()

    assert status.found and status.via == "python"
    assert status.version == importlib.metadata.version("pyswmm")


def test_swmm_missing_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    status = detect.detect_swmm()

    assert not status.found
    assert status.hint is not None and "hydraulik[swmm]" in status.hint


def _fake_kartograf(folder: Path) -> str:
    """A ``kartograf`` script that runs the fake program of the tests."""
    from ..fake_kartograf import PROGRAM

    body = f"import runpy; runpy.run_path({str(PROGRAM)!r}, run_name='__main__')"
    return _script(folder / "kartograf", body)


@posix_only
def test_a_kartograf_that_writes_plain_files_is_found_with_its_command(
    tmp_path: Path,
) -> None:
    exe = _fake_kartograf(tmp_path)

    status, command = detect.find_kartograf(
        _settings(tmp_path, **{"kartograf.exe": exe})
    )

    assert (status.found, status.via, status.version) == (
        True,
        "setting",
        "kartograf 9.9.9-fake",
    )
    assert command == (exe,)
    assert "plain files" in status.detail
    assert detect.detect_kartograf(_settings(tmp_path, **{"kartograf.exe": exe})).found


@posix_only
def test_a_kartograf_whose_output_dir_is_a_store_root_is_found_but_not_usable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = _fake_kartograf(tmp_path)
    monkeypatch.setenv("FAKE_KARTOGRAF", '{"plain": false}')

    status, command = detect.find_kartograf(
        _settings(tmp_path, **{"kartograf.exe": exe})
    )

    assert command is None and not status.found
    assert (status.via, status.location) == ("setting", exe)
    assert status.version == "kartograf 9.9.9-fake"
    assert "versioned store" in status.detail
    assert status.hint is not None and "data-output convention" in status.hint


@posix_only
def test_a_kartograf_that_does_not_describe_its_commands_is_not_usable(
    tmp_path: Path,
) -> None:
    exe = _script(tmp_path / "kartograf", 'print("kartograf 0.1.0")')

    status, command = detect.find_kartograf(
        _settings(tmp_path, **{"kartograf.exe": exe})
    )

    assert command is None and not status.found and status.version == "kartograf 0.1.0"
    assert "kartograf-result/1" in status.detail or "commands schema" in status.detail


def test_kartograf_missing_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))

    status = detect.detect_kartograf(_settings(tmp_path))

    assert not status.found and status.hint is not None
