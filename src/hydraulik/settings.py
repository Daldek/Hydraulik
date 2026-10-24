"""Settings of Hydraulik: ``nogat.toml``, environment variables and defaults (DEV §18).

A value comes from the first of: a command-line option (passed as ``overrides``),
the environment variable ``HYDRAULIK_<KEY>`` (and ``NOGAT_<KEY>`` for the shared
keys), the table ``[hydraulik]`` of ``nogat.toml`` (and ``[nogat]`` for the shared
keys), the built-in default (DEV-18.1). ``<KEY>`` is the dotted key in capitals with
underscores: ``sfincs.exe`` is ``HYDRAULIK_SFINCS_EXE``. The file is read with
``tomllib``; Hydraulik works without it and without the ``nogat`` package. An empty
variable counts as unset.

Hydraulik keeps no store and no cache, so ``data_dir`` and ``cache_dir`` are not read
and it needs no credentials (DEV-18.4, DEV-19.2).
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import platformdirs

from hydraulik.exceptions import InputDataError, InvalidInputError, NotFoundError

__all__ = [
    "SETTINGS",
    "Setting",
    "SettingSpec",
    "Settings",
    "config_file_path",
    "load_settings",
]

CONFIG_SCHEMA: Final = "hydraulik-config/1"
"""Value of the ``schema`` key of the ``config show`` document."""

DEFAULT_SFINCS_IMAGE: Final = "deltares/sfincs-cpu:sfincs-v2.4.1"
"""The engine release the author pinned (spec of 2026-08-20, decision 4)."""

Kind = Literal["string", "integer", "number", "path", "choice"]


@dataclass(frozen=True)
class SettingSpec:
    """Declaration of one setting.

    Attributes
    ----------
    key : str
        Dotted key, as in the ``[hydraulik]`` table of ``nogat.toml``.
    kind : {"string", "integer", "number", "path", "choice"}
        Type of the value; ``path`` is a string that names a file or program.
    default : object
        Value when nothing sets it; ``None`` means "not set".
    shared : bool
        True for a key that ``NOGAT_<KEY>`` and the ``[nogat]`` table also set.
    description : str
        One line for ``config show`` and the documentation.
    choices : tuple of str
        Allowed values of a ``choice`` setting.
    """

    key: str
    kind: Kind
    default: object
    description: str
    shared: bool = False
    choices: tuple[str, ...] = ()

    @property
    def env(self) -> tuple[str, ...]:
        """Tuple of str: environment variables read for this key, in order."""
        suffix = self.key.replace(".", "_").upper()
        names = (f"HYDRAULIK_{suffix}",)
        return (*names, f"NOGAT_{suffix}") if self.shared else names


SETTINGS: Final[tuple[SettingSpec, ...]] = (
    SettingSpec(
        "lang",
        "choice",
        "pl",
        "Language of human-readable output; machine output is always English.",
        shared=True,
        choices=("pl", "en"),
    ),
    SettingSpec(
        "log_level",
        "choice",
        "warning",
        "Log level of the command line on stderr.",
        choices=("debug", "info", "warning", "error"),
    ),
    SettingSpec(
        "sfincs.exe",
        "path",
        None,
        "SFINCS executable; found on PATH when not set.",
    ),
    SettingSpec(
        "sfincs.image",
        "string",
        DEFAULT_SFINCS_IMAGE,
        "Docker image that runs SFINCS when no executable is found.",
    ),
    SettingSpec(
        "sfincs.library",
        "path",
        None,
        "SFINCS shared library (libsfincs) that the coupling loads through the BMI.",
    ),
    SettingSpec(
        "sfincs.qext_unit",
        "choice",
        "m3s",
        "Unit of qext in the SFINCS library: m3s (main since PR 355) or ms (v2.4.1).",
        choices=("m3s", "ms"),
    ),
    SettingSpec(
        "sfincs.timeout_s",
        "number",
        7200.0,
        "Seconds one SFINCS run may take before it is stopped.",
    ),
    SettingSpec(
        "sfincs.threads",
        "integer",
        None,
        "OpenMP threads of one SFINCS run (OMP_NUM_THREADS); all cores when not set.",
    ),
    SettingSpec(
        "docker.exe",
        "path",
        "docker",
        "Docker command used to run the SFINCS image.",
    ),
    SettingSpec(
        "kartograf.exe",
        "path",
        None,
        "Kartograf command; found on PATH when not set.",
    ),
    SettingSpec(
        "kartograf.timeout_s",
        "number",
        3600.0,
        "Seconds one Kartograf download may take.",
    ),
)
"""Every setting of Hydraulik, in the order of ``config show``."""

_BY_KEY: Final = {spec.key: spec for spec in SETTINGS}


@dataclass(frozen=True)
class Setting:
    """A resolved setting: its value and where the value came from.

    Attributes
    ----------
    spec : SettingSpec
        Declaration of the key.
    value : object
        Resolved value; ``None`` when nothing sets it and there is no default.
    source : str
        ``option``, ``env:<NAME>``, ``file:[hydraulik]``, ``file:[nogat]`` or
        ``default``.
    """

    spec: SettingSpec
    value: object
    source: str


class Settings:
    """The resolved settings of one run.

    Parameters
    ----------
    items : Mapping[str, Setting]
        Resolved settings by key.
    config_file : Path
        The settings file that was looked for.
    config_file_source : str
        ``NOGAT_CONFIG``, ``default`` or ``argument``.
    config_file_exists : bool
        Whether ``config_file`` exists.
    """

    def __init__(
        self,
        items: Mapping[str, Setting],
        config_file: Path,
        config_file_source: str,
        config_file_exists: bool,
    ) -> None:
        self._items = dict(items)
        self.config_file = config_file
        self.config_file_source = config_file_source
        self.config_file_exists = config_file_exists

    def __iter__(self) -> Iterator[Setting]:
        """Iterate over the resolved settings in the order of :data:`SETTINGS`."""
        return iter(self._items.values())

    def as_document(self) -> dict[str, Any]:
        """Return the ``hydraulik-config/1`` document that ``config show`` prints.

        Returns
        -------
        dict
            Every key with its value and source, the settings file that was looked
            for, the credentials (none) and the store (none, DEV-18.6).
        """
        return {
            "schema": CONFIG_SCHEMA,
            "config_file": {
                "path": str(self.config_file),
                "source": self.config_file_source,
                "exists": self.config_file_exists,
            },
            "settings": [
                {
                    "key": item.spec.key,
                    "value": item.value,
                    "source": item.source,
                    "env": list(item.spec.env),
                    "description": item.spec.description,
                }
                for item in self
            ],
            "credentials": [],
            "store": None,
        }

    def value(self, key: str) -> Any:
        """Return the value of ``key``.

        Parameters
        ----------
        key : str
            Dotted key from :data:`SETTINGS`.

        Returns
        -------
        object
            The resolved value; ``None`` when the key is not set.

        Raises
        ------
        InvalidInputError
            If ``key`` is not a setting of Hydraulik.
        """
        return self._setting(key).value

    def source(self, key: str) -> str:
        """Return where the value of ``key`` came from (see :class:`Setting`)."""
        return self._setting(key).source

    def _setting(self, key: str) -> Setting:
        try:
            return self._items[key]
        except KeyError:
            raise InvalidInputError(
                f"Unknown setting {key!r}",
                details={"option": key, "allowed": sorted(_BY_KEY)},
                reason="unknown_setting",
            ) from None


def config_file_path(environ: Mapping[str, str] | None = None) -> tuple[Path, str]:
    """Return the path of ``nogat.toml`` and how it was chosen.

    Parameters
    ----------
    environ : Mapping[str, str] or None, optional
        Environment to read; the process environment when ``None``.

    Returns
    -------
    tuple of (Path, str)
        ``NOGAT_CONFIG`` and the source ``NOGAT_CONFIG`` when the variable is set,
        else ``nogat.toml`` in the user configuration folder and ``default``.

    Examples
    --------
    >>> path, source = config_file_path({"NOGAT_CONFIG": "x.toml"})
    >>> path.name, source
    ('x.toml', 'NOGAT_CONFIG')
    """
    env = os.environ if environ is None else environ
    explicit = env.get("NOGAT_CONFIG", "")
    if explicit:
        return Path(explicit), "NOGAT_CONFIG"
    return platformdirs.user_config_path("nogat") / "nogat.toml", "default"


def _flatten(table: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Return a nested TOML table as a flat mapping with dotted keys."""
    flat: dict[str, Any] = {}
    for name, value in table.items():
        key = f"{prefix}{name}"
        if isinstance(value, Mapping):
            flat.update(_flatten(value, f"{key}."))
        else:
            flat[key] = value
    return flat


def _read_file(path: Path, explicit: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the flattened ``[hydraulik]`` and ``[nogat]`` tables of the file."""
    if not path.is_file():
        if explicit:
            raise NotFoundError(
                f"Settings file not found: {path}",
                details={"path": str(path)},
                hint="Unset NOGAT_CONFIG or point it to an existing nogat.toml.",
                reason="settings_file_missing",
            )
        return {}, {}
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise InputDataError(
            f"Settings file is not valid TOML: {path}: {exc}",
            details={"path": str(path)},
            hint="Fix the syntax of the file or remove it.",
            reason="invalid_settings_file",
        ) from exc
    tool = document.get("hydraulik", {})
    shared = document.get("nogat", {})
    if not isinstance(tool, Mapping) or not isinstance(shared, Mapping):
        raise InputDataError(
            f"[hydraulik] and [nogat] must be tables: {path}",
            details={"path": str(path)},
            reason="invalid_settings_file",
        )
    return _flatten(tool), _flatten(shared)


def _convert(spec: SettingSpec, raw: object, origin: str) -> object:
    """Return ``raw`` as the type of ``spec`` or raise ``validation_error``."""

    def bad(why: str) -> InvalidInputError:
        return InvalidInputError(
            f"Setting {spec.key} from {origin}: {why}",
            details={
                "option": spec.key,
                "value": str(raw),
                **({"allowed": list(spec.choices)} if spec.choices else {}),
            },
            hint=f"Set {spec.key} to a valid value or remove it.",
            reason="invalid_setting",
        )

    if spec.kind in ("string", "path"):
        if not isinstance(raw, str):
            raise bad("expected text")
        return raw
    if spec.kind == "choice":
        text = str(raw).lower()
        if text not in spec.choices:
            raise bad(f"expected one of {', '.join(spec.choices)}")
        return text
    if isinstance(raw, bool):
        raise bad("expected a number")
    try:
        number = float(str(raw)) if spec.kind == "number" else int(str(raw), 10)
    except (TypeError, ValueError):
        raise bad("expected a number") from None
    if number <= 0:
        raise bad("expected a positive number")
    return number


def load_settings(
    overrides: Mapping[str, object] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    config_file: Path | None = None,
) -> Settings:
    """Resolve every setting of Hydraulik (DEV-18.1).

    Parameters
    ----------
    overrides : Mapping[str, object] or None, optional
        Values of command-line options by dotted key; ``None`` entries are ignored.
    environ : Mapping[str, str] or None, optional
        Environment to read; the process environment when ``None``.
    config_file : Path or None, optional
        Settings file, which may be absent; by default ``NOGAT_CONFIG`` (which must
        exist) or the file in the user configuration folder of ``nogat``.

    Returns
    -------
    Settings
        The resolved settings with their sources.

    Raises
    ------
    InvalidInputError
        If a value has the wrong type or is not allowed, or a key in the file is
        not a setting of Hydraulik.
    NotFoundError
        If ``NOGAT_CONFIG`` names a file that does not exist.
    InputDataError
        If the settings file is not valid TOML.

    Examples
    --------
    >>> env = {"HYDRAULIK_LANG": "en"}
    >>> settings = load_settings(environ=env, config_file=Path("absent.toml"))
    >>> settings.value("lang"), settings.source("lang")
    ('en', 'env:HYDRAULIK_LANG')
    """
    env = os.environ if environ is None else environ
    if config_file is None:
        path, file_source = config_file_path(env)
        explicit = file_source == "NOGAT_CONFIG"
    else:
        path, file_source, explicit = config_file, "argument", False
    tool_table, shared_table = _read_file(path, explicit)
    unknown = sorted(set(tool_table) - set(_BY_KEY))
    if unknown:
        raise InvalidInputError(
            f"Unknown setting in [hydraulik] of {path}: {', '.join(unknown)}",
            details={
                "option": unknown[0],
                "allowed": sorted(_BY_KEY),
                "path": str(path),
            },
            hint="Remove the key or fix its spelling.",
            reason="unknown_setting",
        )
    given = {k: v for k, v in (overrides or {}).items() if v is not None}
    for key in given:
        if key not in _BY_KEY:
            raise InvalidInputError(
                f"Unknown setting {key!r}",
                details={"option": key, "allowed": sorted(_BY_KEY)},
                reason="unknown_setting",
            )
    items: dict[str, Setting] = {}
    for spec in SETTINGS:
        value: object = spec.default
        source = "default"
        if spec.key in given:
            value, source = _convert(spec, given[spec.key], "option"), "option"
        else:
            for name in spec.env:
                if env.get(name):
                    value = _convert(spec, env[name], name)
                    source = f"env:{name}"
                    break
            else:
                if spec.key in tool_table:
                    value = _convert(spec, tool_table[spec.key], "[hydraulik]")
                    source = "file:[hydraulik]"
                elif spec.shared and spec.key in shared_table:
                    value = _convert(spec, shared_table[spec.key], "[nogat]")
                    source = "file:[nogat]"
        items[spec.key] = Setting(spec, value, source)
    return Settings(items, path, file_source, path.is_file())
