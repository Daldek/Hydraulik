"""``commands guide``: render the agent guides from the catalog (AGI-3.8, AGI-8.2)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Literal

from hydraulik import agent_guide
from hydraulik.documents import GuideDocument
from hydraulik.exceptions import InvalidInputError, NotFoundError, OutputError

__all__ = ["render_guide"]

GuideFormat = Literal["agents", "llms", "agents-md-block"]


def _injected(current: str, block: str) -> str:
    """Return ``current`` with the hydraulik block replaced, or appended."""
    begin = current.find(agent_guide.BEGIN_MARKER)
    end = current.find(agent_guide.END_MARKER)
    if begin != -1 and end > begin:
        return (
            current[:begin]
            + block.rstrip("\n")
            + current[end + len(agent_guide.END_MARKER) :]
        )
    separator = (
        ""
        if not current or current.endswith("\n\n")
        else ("\n" if current.endswith("\n") else "\n\n")
    )
    return current + separator + block


def render_guide(
    *,
    format: GuideFormat = "agents",  # noqa: A002 - the catalog option is called format
    inject: str | os.PathLike[str] | None = None,
    check: bool = False,
) -> GuideDocument:
    """Render AGENTS.md, llms.txt or the block for another repository's AGENTS.md.

    Parameters
    ----------
    format : {"agents", "llms", "agents-md-block"}, optional
        Which guide to render.
    inject : path-like or None, optional
        ``AGENTS.md`` of a consumer repository; its hydraulik block is replaced, or
        appended when it has none (``agents-md-block`` only).
    check : bool, optional
        Plan the injection: report whether the file would change, change nothing.

    Returns
    -------
    GuideDocument
        The rendered text; ``injected_into`` and ``changed`` describe the file.

    Raises
    ------
    InvalidInputError
        If ``inject`` is combined with another format, or ``check`` is given without
        ``inject``.
    NotFoundError
        If ``inject`` names a file that does not exist.
    OutputError
        If the file cannot be rewritten.

    Examples
    --------
    >>> render_guide(format="agents-md-block").text.startswith("<!-- BEGIN hydraulik")
    True
    """
    if format == "agents":
        text = agent_guide.render_agents()
    elif format == "llms":
        text = agent_guide.render_llms()
    else:
        text = agent_guide.render_block()
    if inject is None:
        if check:
            raise InvalidInputError(
                "--check needs --inject: rendering changes no file",
                details={"option": "check"},
                reason="check_without_inject",
            )
        return GuideDocument(format=format, text=text)
    if format != "agents-md-block":
        raise InvalidInputError(
            "--inject works with --format agents-md-block only",
            details={
                "option": "inject",
                "value": str(inject),
                "allowed": ["agents-md-block"],
            },
            reason="inject_needs_block",
        )
    path = Path(inject)
    if not path.is_file():
        raise NotFoundError(
            f"AGENTS.md to inject into not found: {path}",
            details={"path": str(path)},
            hint="Name an existing AGENTS.md (the block is appended when it has none).",
        )
    current = path.read_text(encoding="utf-8")
    updated = _injected(current, text)
    changed = updated != current
    if changed and not check:
        try:
            handle, name = tempfile.mkstemp(dir=path.parent, prefix=".inject-")
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(updated)
            os.replace(name, path)
        except OSError as exc:
            raise OutputError(
                f"Cannot rewrite {path}: {exc}", details={"path": str(path)}
            ) from exc
    return GuideDocument(
        format=format, text=text, injected_into=str(path.resolve()), changed=changed
    )
