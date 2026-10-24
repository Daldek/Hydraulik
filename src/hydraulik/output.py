"""Plain-mode output writer of Hydraulik (DEV §19).

Hydraulik has no versioned store, so every command that writes data writes plain
files: a directory (``--output-dir``) or exactly one file (``--output``). The rules
are those of DEV-19.3 to DEV-19.11:

* The names of all targets are known before the first byte (:func:`plan_directory`,
  :func:`plan_file`). A duplicate name is ``conflict`` (reason
  ``duplicate_output_name``), an existing target without ``--force`` is ``conflict``
  (reason ``output_exists``), a directory that is or lies inside a store of any Nogat
  tool is ``conflict`` (reason ``output_in_store``); the error lists every offending
  path in ``details.paths`` and nothing is written.
* A plan is also the result of ``--check``: it lists ``write``, ``replace`` (only with
  ``--force``) or ``conflict`` for each target and never fails.
* :class:`Writer` writes through a staging directory
  ``<dir>/.hydraulik-incoming/<host>_<pid>_<token>/`` on the same file system,
  verifies each file there and moves it into place with :func:`os.replace`. Staging is
  removed on success, on error, on SIGINT and on SIGTERM; leftovers older than 24 hours
  are removed on the next run. Nothing but the data files is created: no sidecar, no
  hard link, no ``versions/`` directory.
* The result lists ``files[]``: ``path``, ``size_bytes``, ``sha256`` and ``status``
  (``written`` or ``replaced``).

Stores are recognised by the marker file name alone and nothing is imported from
another tool (DEV-19.12).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import secrets
import shutil
import signal
import socket
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import FrameType, TracebackType
from typing import Any, Final, Literal

from hydraulik.exceptions import (
    ConflictError,
    InvalidInputError,
    OutputError,
    TerminatedError,
)

__all__ = [
    "STAGING_DIR",
    "STORE_MARKERS",
    "FileRecord",
    "PlannedTarget",
    "WritePlan",
    "Writer",
    "plan_directory",
    "plan_file",
    "sha256_file",
]

STAGING_DIR: Final = ".hydraulik-incoming"
"""Name of the staging directory inside the output directory (DEV-19.7)."""

STORE_MARKERS: Final = ("kartograf-store.json", "imgw-store.json")
"""Marker file names of the stores of the other Nogat tools (DEV-19.12)."""

_STALE_AFTER_S: Final = 24 * 3600
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

Action = Literal["write", "replace", "conflict"]


@dataclass(frozen=True)
class PlannedTarget:
    """One file a write would produce.

    Attributes
    ----------
    name : str
        Path relative to the output directory, with ``/`` separators.
    path : Path
        Absolute path of the target.
    action : {"write", "replace", "conflict"}
        What the write does with it; ``conflict`` fails the real run.
    reason : str or None
        ``output_exists`` for a conflict; ``None`` otherwise.
    """

    name: str
    path: Path
    action: Action
    reason: str | None = None


@dataclass(frozen=True)
class FileRecord:
    """A file that was written (DEV-19.19).

    Attributes
    ----------
    path : Path
        Absolute path of the file.
    size_bytes : int
        Size of the file.
    sha256 : str
        SHA-256 of the file, 64 lower-case hexadecimal digits.
    status : {"written", "replaced"}
        ``replaced`` when ``--force`` replaced an existing file.
    """

    path: Path
    size_bytes: int
    sha256: str
    status: Literal["written", "replaced"]

    def to_dict(self) -> dict[str, Any]:
        """Return the ``files[]`` entry as a JSON-compatible dictionary."""
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "status": self.status,
        }


@dataclass(frozen=True)
class WritePlan:
    """The preflight of a plain write: every target with its action.

    Attributes
    ----------
    directory : Path
        Absolute directory the files go into (``--output-dir``, or the directory
        that holds ``--output``).
    targets : tuple of PlannedTarget
        Every file, in the order given.
    store_paths : tuple of Path
        Store markers that make the directory a conflict (reason ``output_in_store``).
    duplicates : tuple of str
        Names that occur more than once.
    force : bool
        Whether existing targets are replaced.
    """

    directory: Path
    targets: tuple[PlannedTarget, ...]
    store_paths: tuple[Path, ...] = ()
    duplicates: tuple[str, ...] = ()
    force: bool = False

    @property
    def conflicts(self) -> tuple[str, ...]:
        """Tuple of str: the reasons that make the real run fail, in check order."""
        found: list[str] = []
        if self.store_paths:
            found.append("output_in_store")
        if self.duplicates:
            found.append("duplicate_output_name")
        if any(t.action == "conflict" for t in self.targets):
            found.append("output_exists")
        return tuple(found)

    def raise_on_conflict(self) -> None:
        """Raise :class:`ConflictError` listing every offending path, if any.

        Raises
        ------
        ConflictError
            With ``details.reason`` ``output_in_store``, ``duplicate_output_name`` or
            ``output_exists`` (the first that applies) and ``details.paths``.
        """
        if self.store_paths:
            raise ConflictError(
                f"{self.directory} is or lies inside a Nogat store",
                reason="output_in_store",
                details={"paths": [str(p) for p in self.store_paths]},
                hint=(
                    "A store is written by the tool that owns it (its --root); "
                    "choose another --output-dir."
                ),
            )
        if self.duplicates:
            raise ConflictError(
                "Two outputs would have the same name",
                reason="duplicate_output_name",
                details={"paths": [str(self.directory / n) for n in self.duplicates]},
                hint="Give every output a different name.",
            )
        existing = [t.path for t in self.targets if t.action == "conflict"]
        if existing:
            raise ConflictError(
                f"{len(existing)} output file(s) already exist",
                reason="output_exists",
                details={"paths": [str(p) for p in existing]},
                hint="Use --force to replace them, or choose another --output-dir.",
            )

    def to_dict(self) -> dict[str, Any]:
        """Return the ``hydraulik-plan/1`` document of this plan."""
        document: dict[str, Any] = {
            "schema": "hydraulik-plan/1",
            "output_dir": str(self.directory),
            "force": self.force,
            "targets": [
                {
                    "name": t.name,
                    "path": str(t.path),
                    "action": t.action,
                    **({"reason": t.reason} if t.reason else {}),
                }
                for t in self.targets
            ],
            "conflicts": list(self.conflicts),
        }
        if self.store_paths:
            document["store_paths"] = [str(p) for p in self.store_paths]
        return document


def _clean_name(name: str) -> str:
    """Return ``name`` as a safe relative POSIX path or raise ``validation_error``."""

    def bad(why: str) -> InvalidInputError:
        return InvalidInputError(
            f"Unsafe output name {name!r}: {why}",
            details={"option": "output", "value": name},
            hint="Use a relative path without '..' inside the output directory.",
            reason="unsafe_output_name",
        )

    if not name or _CONTROL.search(name):
        raise bad("empty or contains control characters")
    posix = PurePosixPath(name.replace("\\", "/"))
    if posix.is_absolute() or any(part in ("..", "") for part in posix.parts):
        raise bad("absolute or leaves the output directory")
    if len(posix.parts) > 0 and posix.parts[0] == STAGING_DIR:
        raise bad("reserved for staging")
    return posix.as_posix()


def _markers_above(directory: Path) -> list[Path]:
    """Return the store markers in ``directory`` and in each of its ancestors."""
    found: list[Path] = []
    for folder in (directory, *directory.parents):
        found.extend(
            folder / marker for marker in STORE_MARKERS if (folder / marker).is_file()
        )
    return found


def plan_directory(
    output_dir: str | os.PathLike[str],
    names: Iterable[str],
    *,
    force: bool = False,
) -> WritePlan:
    """Plan a plain write of ``names`` into a directory (DEV-19.6, DEV-19.10).

    Nothing is created or changed.

    Parameters
    ----------
    output_dir : path-like
        Directory for the files; it is created by :class:`Writer` when missing.
    names : iterable of str
        Relative path of every file the command will write, known before it starts
        (DEV-19.5).
    force : bool, optional
        Replace existing targets instead of reporting a conflict.

    Returns
    -------
    WritePlan
        The targets with their actions; check :attr:`WritePlan.conflicts`.

    Raises
    ------
    InvalidInputError
        If a name is empty, absolute, contains ``..`` or control characters, or if
        ``output_dir`` exists and is not a directory.

    Examples
    --------
    >>> plan = plan_directory("results", ["summary.json", "hmax.tif"])
    >>> [t.action for t in plan.targets]
    ['write', 'write']
    """
    directory = Path(output_dir).resolve()
    if directory.exists() and not directory.is_dir():
        raise InvalidInputError(
            f"--output-dir is not a directory: {directory}",
            details={"option": "output_dir", "value": str(directory)},
            hint="Choose a directory, or use --output for a single file.",
            reason="not_a_directory",
        )
    cleaned = [_clean_name(name) for name in names]
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in cleaned:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    targets: list[PlannedTarget] = []
    store_paths = list(_markers_above(directory))
    for name in cleaned:
        path = directory / name
        for parent in path.parents:
            if parent == directory:
                break
            store_paths.extend(
                parent / marker
                for marker in STORE_MARKERS
                if (parent / marker).is_file()
            )
        if not path.exists():
            targets.append(PlannedTarget(name, path, "write"))
        elif force and path.is_file():
            targets.append(PlannedTarget(name, path, "replace"))
        else:
            targets.append(PlannedTarget(name, path, "conflict", "output_exists"))
    unique_store = tuple(dict.fromkeys(store_paths))
    return WritePlan(directory, tuple(targets), unique_store, tuple(duplicates), force)


def plan_file(output: str | os.PathLike[str], *, force: bool = False) -> WritePlan:
    """Plan a plain write of exactly one file (``--output``, DEV-19.1).

    The file has the name the caller gave it; its directory is where staging lives
    (DEV-19.7).

    Parameters
    ----------
    output : path-like
        The file to write.
    force : bool, optional
        Replace the file when it exists.

    Returns
    -------
    WritePlan
        A plan with one target.

    Raises
    ------
    InvalidInputError
        If ``output`` names an existing directory or has no file name.
    """
    path = Path(output).resolve()
    if path.is_dir() or not path.name:
        raise InvalidInputError(
            f"--output must name a file, not a directory: {path}",
            details={"option": "output", "value": str(path)},
            hint="Use --output-dir for a directory.",
            reason="not_a_file",
        )
    return plan_directory(path.parent, [path.name], force=force)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file as 64 lower-case hexadecimal digits.

    Parameters
    ----------
    path : Path
        File to read; it is streamed in blocks.

    Returns
    -------
    str
        The digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _host() -> str:
    return re.sub(r"[^A-Za-z0-9.-]", "-", socket.gethostname()) or "host"


def remove_stale_staging(directory: Path, now: float | None = None) -> list[Path]:
    """Remove staging directories older than 24 hours (DEV-19.7).

    Parameters
    ----------
    directory : Path
        The output directory whose ``.hydraulik-incoming`` folder is cleaned.
    now : float or None, optional
        Current time as a POSIX timestamp; the clock when ``None``.

    Returns
    -------
    list of Path
        The directories that were removed.
    """
    root = directory / STAGING_DIR
    if not root.is_dir():
        return []
    limit = (time.time() if now is None else now) - _STALE_AFTER_S
    removed: list[Path] = []
    for entry in root.iterdir():
        try:
            if entry.is_dir() and entry.stat().st_mtime < limit:
                shutil.rmtree(entry, ignore_errors=True)
                removed.append(entry)
        except OSError:
            continue
    return removed


class Writer:
    """Write the planned files through a staging directory (DEV-19.7).

    Use as a context manager. The caller creates every planned file under
    :attr:`staging` (or asks :meth:`staged_path` for its location), then calls
    :meth:`commit`. The staging directory is removed when the block ends, however it
    ends.

    Parameters
    ----------
    plan : WritePlan
        The preflight; it must have no conflict.

    Raises
    ------
    ConflictError
        On entry, if the plan has a conflict (nothing has been created yet).
    OutputError
        If the directories cannot be created.

    Examples
    --------
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     with Writer(plan_directory(tmp, ["a.txt"])) as writer:
    ...         _ = writer.staged_path("a.txt").write_text("x")
    ...         files = writer.commit()
    ...     files[0].status
    'written'
    """

    def __init__(self, plan: WritePlan) -> None:
        self.plan = plan
        self._staging: Path | None = None
        self._previous_handler: Any = None
        self._handler_installed = False

    @property
    def staging(self) -> Path:
        """Path: the staging directory; only valid inside the ``with`` block."""
        if self._staging is None:
            raise RuntimeError("Writer is used outside its with block")
        return self._staging

    def staged_path(self, name: str) -> Path:
        """Return where the planned file ``name`` is created in staging.

        Parameters
        ----------
        name : str
            A name of the plan.

        Returns
        -------
        Path
            The path in the staging directory; its parent directories exist.

        Raises
        ------
        InvalidInputError
            If ``name`` is not in the plan.
        """
        if name not in {t.name for t in self.plan.targets}:
            raise InvalidInputError(
                f"{name!r} is not a planned output",
                details={"option": "output", "value": name},
                reason="unplanned_output",
            )
        path = self.staging / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def __enter__(self) -> Writer:
        """Check the plan, create the staging directory and trap SIGTERM."""
        self.plan.raise_on_conflict()
        directory = self.plan.directory
        try:
            directory.mkdir(parents=True, exist_ok=True)
            remove_stale_staging(directory)
            staging = (
                directory
                / STAGING_DIR
                / f"{_host()}_{os.getpid()}_{secrets.token_hex(4)}"
            )
            staging.mkdir(parents=True)
        except OSError as exc:
            raise OutputError(
                f"Cannot create the output directory {directory}: {exc}",
                details={"path": str(directory)},
                hint="Check the permissions and the free space of the target disk.",
                reason="output_unwritable",
            ) from exc
        self._staging = staging
        try:
            self._previous_handler = signal.signal(signal.SIGTERM, self._on_terminate)
            self._handler_installed = True
        except ValueError:  # not the main thread: only SIGINT unwinds the block
            self._handler_installed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Remove the staging directory and restore the SIGTERM handler."""
        if self._handler_installed:
            signal.signal(signal.SIGTERM, self._previous_handler)
            self._handler_installed = False
        if self._staging is not None:
            shutil.rmtree(self._staging, ignore_errors=True)
            root = self._staging.parent
            self._staging = None
            with contextlib.suppress(OSError):
                root.rmdir()  # only when no other run is staging there

    @staticmethod
    def _on_terminate(signum: int, frame: FrameType | None) -> None:
        raise TerminatedError("Terminated by SIGTERM", details={"signal": signum})

    def commit(self, sizes: dict[str, int] | None = None) -> tuple[FileRecord, ...]:
        """Verify every planned file in staging and move it into place.

        Parameters
        ----------
        sizes : dict of str to int or None, optional
            Expected size in bytes of files whose size is known beforehand.

        Returns
        -------
        tuple of FileRecord
            One record per planned file, in plan order.

        Raises
        ------
        OutputError
            If a planned file is missing or has the wrong size in staging, or a move
            fails. Files moved before the failure stay in place.
        ConflictError
            If a target appeared since the plan was made and ``force`` is off.
        """
        records: list[FileRecord] = []
        expected = sizes or {}
        for target in self.plan.targets:
            staged = self.staging / target.name
            if not staged.is_file():
                raise OutputError(
                    f"The run did not produce {target.name}",
                    details={"path": str(target.path)},
                    hint="See the log of the run; nothing was written for this file.",
                    reason="output_missing",
                )
            size = staged.stat().st_size
            if target.name in expected and expected[target.name] != size:
                raise OutputError(
                    f"{target.name} has {size} bytes, expected {expected[target.name]}",
                    details={"path": str(target.path)},
                    reason="output_size_mismatch",
                )
            existed = target.path.exists()
            if existed and not self.plan.force:
                raise ConflictError(
                    f"{target.path} appeared during the run",
                    reason="output_exists",
                    details={"paths": [str(target.path)]},
                    hint="Use --force to replace it.",
                )
            digest = sha256_file(staged)
            target.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(staged, target.path)
            except OSError as exc:
                raise OutputError(
                    f"Cannot move {target.name} into place: {exc}",
                    details={"path": str(target.path)},
                    reason="output_unwritable",
                ) from exc
            records.append(
                FileRecord(
                    target.path, size, digest, "replaced" if existed else "written"
                )
            )
        return tuple(records)
