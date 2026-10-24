"""The result envelope ``hydraulik-result/1`` (AGI-4.2)."""

from __future__ import annotations

from typing import Any, Final

from hydraulik import __version__
from hydraulik._errors import OUTCOMES
from hydraulik.catalog.spec import TOOL
from hydraulik.documents import Document

__all__ = ["RESULT_SCHEMA", "build_envelope", "exit_code_of"]

RESULT_SCHEMA: Final = f"{TOOL}-result/1"


def exit_code_of(status: str) -> int:
    """Return the process exit code of an outcome (ERR §1).

    Parameters
    ----------
    status : str
        ``ok``, ``partial``, ``failed`` or ``cancelled``.

    Returns
    -------
    int
        0, 10, 11 or 130.

    Examples
    --------
    >>> exit_code_of("partial")
    10
    """
    return OUTCOMES[status]


def build_envelope(
    command: str,
    result: Document | list[Document] | None,
    *,
    check: bool = False,
    status: str | None = None,
) -> dict[str, Any]:
    """Wrap the result of a command in the envelope.

    Parameters
    ----------
    command : str
        Catalog name of the command.
    result : Document, list of Document or None
        The domain document; ``None`` when nothing was produced.
    check : bool, optional
        True when the run was a plan without effects.
    status : str or None, optional
        Overall outcome; by default the ``status`` of the document, else ``ok``.

    Returns
    -------
    dict
        ``schema``, ``tool``, ``version``, ``command``, ``check``, ``status`` and
        ``result``, plus ``items`` and ``notices`` when the document carries them.
    """
    first = result[0] if isinstance(result, list) and result else result
    carried = first if isinstance(first, Document) else None
    resolved = status or getattr(carried, "status", "ok")
    body: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "tool": TOOL,
        "version": __version__,
        "command": command,
        "check": check,
        "status": resolved,
    }
    if isinstance(result, list):
        body["result"] = [item.to_dict() for item in result]
    else:
        body["result"] = None if result is None else result.to_dict()
    items = getattr(carried, "items", None)
    if items:
        body["items"] = items
    notices = getattr(carried, "notices", None)
    if notices:
        body["notices"] = notices
    return body
