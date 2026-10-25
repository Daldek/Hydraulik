"""Finding the external programs (ADR-0003).

Hydraulik never bundles, installs or downloads an engine. It looks where the user
says (the settings of ``config show``), then on ``PATH``, and reports what it found
and what to do when it found nothing. Looking never changes anything: the SFINCS
version is read from the banner that the program prints when it is started in an empty
directory, and a Docker image is only inspected, never pulled.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from hydraulik.data.kartograf import KartografCli, plain_output_problem
from hydraulik.exceptions import HydraulikError
from hydraulik.settings import Settings

__all__ = [
    "EngineStatus",
    "SfincsInstall",
    "detect_kartograf",
    "detect_sfincs",
    "detect_sfincs_library",
    "detect_swmm",
    "find_kartograf",
    "inspect_kartograf",
]

_PROBE_TIMEOUT_S: Final = 15.0
_KARTOGRAF_PROBE: Final = "elevation download"
"""The Kartograf command whose schema tells whether it writes plain files."""
_BANNER = re.compile(r"Build-Revision:\s*\$Rev:\s*(?P<version>[^\n]+)")
_TAG = re.compile(r"sfincs-(?P<version>v[0-9][^\s]*)")


@dataclass(frozen=True)
class EngineStatus:
    """What was found of one external program.

    Attributes
    ----------
    name : str
        ``sfincs``, ``sfincs-library``, ``swmm`` or ``kartograf``.
    found : bool
        True when the program can be used.
    via : str or None
        How it was found: ``setting``, ``path``, ``docker`` or ``python``.
    location : str or None
        The executable, the library, the image or the package version.
    version : str or None
        The version the program reports.
    detail : str
        One line on what was looked at.
    hint : str or None
        What to do when it was not found.
    """

    name: str
    found: bool
    via: str | None
    location: str | None
    version: str | None
    detail: str
    hint: str | None = None


@dataclass(frozen=True)
class SfincsInstall:
    """A SFINCS that can run a model directory.

    Attributes
    ----------
    kind : {"exe", "docker"}
        A program on this machine or a container image.
    command : tuple of str
        The program (``exe``) or the Docker command (``docker``).
    image : str or None
        The image of a Docker install.
    version : str or None
        The version it reported.
    """

    kind: Literal["exe", "docker"]
    command: tuple[str, ...]
    image: str | None = None
    version: str | None = None


def _run(
    command: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_S,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def _sfincs_banner_version(executable: str) -> str | None:
    """Return the version printed in the banner of a SFINCS executable, or ``None``."""
    with tempfile.TemporaryDirectory(prefix="hydraulik-probe-") as empty:
        try:
            done = _run([executable], Path(empty))
        except (OSError, subprocess.TimeoutExpired):
            return None
    match = _BANNER.search(done.stdout + done.stderr)
    return match["version"].strip() if match else None


def detect_sfincs(settings: Settings) -> tuple[EngineStatus, SfincsInstall | None]:
    """Find a SFINCS that can run a model: a setting, ``PATH`` or a Docker image.

    The first that works wins: ``sfincs.exe``, ``sfincs`` on ``PATH``, then the Docker
    image of ``sfincs.image`` through ``docker.exe``. A ``sfincs.exe`` that names a
    missing file is reported as such and is not replaced by another.

    Parameters
    ----------
    settings : Settings
        The resolved settings.

    Returns
    -------
    tuple of (EngineStatus, SfincsInstall or None)
        What was found and how to run it; ``None`` when nothing was found.
    """
    configured = settings.value("sfincs.exe")
    if configured:
        path = shutil.which(str(configured)) or (
            str(configured) if Path(str(configured)).is_file() else None
        )
        if path is None:
            return (
                EngineStatus(
                    "sfincs",
                    False,
                    None,
                    str(configured),
                    None,
                    f"sfincs.exe names a file that does not exist: {configured}",
                    "Fix sfincs.exe (HYDRAULIK_SFINCS_EXE) or unset it.",
                ),
                None,
            )
        version = _sfincs_banner_version(path)
        status = EngineStatus(
            "sfincs", True, "setting", path, version, "executable from sfincs.exe"
        )
        return status, SfincsInstall("exe", (path,), None, version)
    on_path = shutil.which("sfincs")
    if on_path:
        version = _sfincs_banner_version(on_path)
        status = EngineStatus(
            "sfincs", True, "path", on_path, version, "executable on PATH"
        )
        return status, SfincsInstall("exe", (on_path,), None, version)
    return _detect_docker_sfincs(settings)


def _detect_docker_sfincs(
    settings: Settings,
) -> tuple[EngineStatus, SfincsInstall | None]:
    image = str(settings.value("sfincs.image"))
    docker = shutil.which(str(settings.value("docker.exe")))
    install_hint = (
        "Install SFINCS from https://download.deltares.nl/sfincs and set "
        "HYDRAULIK_SFINCS_EXE, or install Docker and pull the image "
        f"(docker pull {image}). Hydraulik never installs or pulls an engine."
    )
    if docker is None:
        return (
            EngineStatus(
                "sfincs",
                False,
                None,
                None,
                None,
                "no sfincs executable and no Docker command were found",
                install_hint,
            ),
            None,
        )
    try:
        done = _run([docker, "image", "inspect", image])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return (
            EngineStatus(
                "sfincs",
                False,
                None,
                image,
                None,
                f"docker did not answer: {exc}",
                install_hint,
            ),
            None,
        )
    if done.returncode != 0:
        why = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no answer"]
        return (
            EngineStatus(
                "sfincs",
                False,
                None,
                image,
                None,
                f"docker has no image {image}: {why[0]}",
                install_hint,
            ),
            None,
        )
    tag = _TAG.search(image)
    version = tag["version"] if tag else None
    status = EngineStatus(
        "sfincs", True, "docker", image, version, "image present in the local Docker"
    )
    return status, SfincsInstall("docker", (docker,), image, version)


def detect_sfincs_library(settings: Settings) -> EngineStatus:
    """Find the SFINCS shared library that the coupling loads through the BMI.

    The file is not loaded: loading a library into the process cannot be undone.

    Parameters
    ----------
    settings : Settings
        The resolved settings.

    Returns
    -------
    EngineStatus
        ``found`` when ``sfincs.library`` names an existing file.
    """
    configured = settings.value("sfincs.library")
    hint = (
        "Build SFINCS from its sources with `--enable-shared` and set "
        "HYDRAULIK_SFINCS_LIBRARY to libsfincs (the Docker image has no library). "
        "Set HYDRAULIK_SFINCS_QEXT_UNIT=ms for SFINCS v2.4.1 or older."
    )
    if not configured:
        return EngineStatus(
            "sfincs-library", False, None, None, None, "sfincs.library is not set", hint
        )
    path = Path(str(configured))
    if not path.is_file():
        return EngineStatus(
            "sfincs-library",
            False,
            None,
            str(path),
            None,
            f"sfincs.library names a file that does not exist: {path}",
            hint,
        )
    return EngineStatus(
        "sfincs-library",
        True,
        "setting",
        str(path.resolve()),
        None,
        f"library from sfincs.library, qext unit {settings.value('sfincs.qext_unit')}",
    )


def detect_swmm() -> EngineStatus:
    """Find SWMM: the ``pyswmm`` package, which carries the engine in ``swmm-toolkit``.

    Returns
    -------
    EngineStatus
        ``found`` when ``pyswmm`` can be imported; the version is the one of the
        package.
    """
    if importlib.util.find_spec("pyswmm") is None:
        return EngineStatus(
            "swmm",
            False,
            None,
            None,
            None,
            "the Python package pyswmm is not installed",
            "Install it: uv add 'hydraulik[swmm]'",
        )
    version = importlib.metadata.version("pyswmm")
    try:
        toolkit = importlib.metadata.version("swmm-toolkit")
        detail = f"pyswmm {version} with swmm-toolkit {toolkit}"
    except importlib.metadata.PackageNotFoundError:
        detail = f"pyswmm {version}"
    return EngineStatus("swmm", True, "python", "pyswmm", version, detail)


def find_kartograf(settings: Settings) -> tuple[EngineStatus, tuple[str, ...] | None]:
    """Find the Kartograf command that downloads terrain and land cover.

    A Kartograf counts as found only when it writes plain files: its schema of
    ``elevation download`` must declare ``output_dir`` with ``path_role: output``
    (DEV-19.1). A Kartograf without the data-output convention has ``output_dir`` as
    the root of a versioned store, and ``--output-dir`` would write a store into the
    directory of the user, so it is reported as unusable and says why.

    Parameters
    ----------
    settings : Settings
        The resolved settings.

    Returns
    -------
    tuple of (EngineStatus, tuple of str or None)
        What was found and the command that runs it; ``None`` when nothing usable was
        found. A status that is not ``found`` and has a ``via`` is a Kartograf that
        runs but cannot write plain files.
    """
    configured = settings.value("kartograf.exe")
    path = shutil.which(str(configured or "kartograf")) or (
        str(configured) if configured and Path(str(configured)).is_file() else None
    )
    hint = "Install Kartograf (github.com/Daldek/Kartograf) or set kartograf.exe."
    if path is None:
        return (
            EngineStatus(
                "kartograf",
                False,
                None,
                str(configured) if configured else None,
                None,
                "the kartograf command was not found",
                hint,
            ),
            None,
        )
    via = "setting" if configured else "path"
    return inspect_kartograf(
        (path,),
        via,
        timeout_s=float(settings.value("kartograf.timeout_s")),
    )


def inspect_kartograf(
    words: tuple[str, ...], via: str, *, timeout_s: float
) -> tuple[EngineStatus, tuple[str, ...] | None]:
    """Look at a Kartograf command: its version and whether it writes plain files.

    Parameters
    ----------
    words : tuple of str
        The command that runs Kartograf; its first word is the program.
    via : str
        How the command was found (``setting`` or ``path``).
    timeout_s : float
        Seconds a call of Kartograf that fetches data may take (for the command that
        is returned).

    Returns
    -------
    tuple of (EngineStatus, tuple of str or None)
        ``found`` and ``words`` when ``commands schema --command "elevation
        download"`` declares ``output_dir`` with ``path_role: output``; otherwise a
        status that says why not and ``None``.
    """
    cli = KartografCli(words, timeout_s=timeout_s, probe_timeout_s=_PROBE_TIMEOUT_S)
    version = cli.version()
    try:
        problem = plain_output_problem(cli.schema(_KARTOGRAF_PROBE))
    except HydraulikError as exc:
        problem = str(exc)
    if problem is not None:
        return (
            EngineStatus(
                "kartograf",
                False,
                via,
                words[0],
                version,
                f"{version or 'kartograf'} runs, but {problem}",
                "Use a Kartograf that implements the data-output convention (Nogat "
                "DEV section 19, `--output-dir` writes plain files); `terrain "
                "download` cannot run without it.",
            ),
            None,
        )
    return (
        EngineStatus(
            "kartograf",
            True,
            via,
            words[0],
            version,
            "command found; --output-dir writes plain files",
        ),
        words,
    )


def detect_kartograf(settings: Settings) -> EngineStatus:
    """Report the Kartograf that ``terrain download`` would use.

    Parameters
    ----------
    settings : Settings
        The resolved settings.

    Returns
    -------
    EngineStatus
        ``found`` when ``kartograf.exe`` or ``kartograf`` on ``PATH`` runs and writes
        plain files (:func:`find_kartograf`); the version is the one ``kartograf
        --version`` prints.
    """
    return find_kartograf(settings)[0]
