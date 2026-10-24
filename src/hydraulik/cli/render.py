"""Human-readable rendering of results and errors (AGI-3.2, AGI-9.2).

Without ``--json`` the CLI prints a plain rendering of the envelope in the language
of ``lang``: headings and status words from the translation resources, the document
as an indented tree. Colours are never used (AGI-3.6).
"""

from __future__ import annotations

from typing import Any, Literal

from hydraulik.cli.messages import reason_text, text

__all__ = ["render_envelope", "render_error"]

Lang = Literal["pl", "en"]


def _lines(value: Any, indent: int) -> list[str]:
    pad = "  " * indent
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            if isinstance(item, dict | list) and item:
                out.append(f"{pad}{key}:")
                out.extend(_lines(item, indent + 1))
            else:
                out.append(f"{pad}{key}: {_scalar(item)}")
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                inner = _lines(item, indent + 1)
                first, rest = inner[0].lstrip(), inner[1:]
                out.append(f"{pad}- {first}")
                out.extend(rest)
            else:
                out.append(f"{pad}- {_scalar(item)}")
        return out
    return [f"{pad}{_scalar(value)}"]


def _scalar(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict | list):
        return "(none)"
    return str(value)


def render_envelope(envelope: dict[str, Any], lang: Lang) -> str:
    """Render a result envelope for a person.

    Parameters
    ----------
    envelope : dict
        The ``hydraulik-result/1`` document.
    lang : {"pl", "en"}
        Language of headings and status words.

    Returns
    -------
    str
        Text ending with a newline.
    """
    header = text("check.header" if envelope["check"] else "result.header", lang)
    status = text(f"status.{envelope['status']}", lang)
    out = [f"{envelope['command']}: {header}, {status}"]
    result = envelope["result"]
    if result is not None:
        body = result if isinstance(result, dict) else {"documents": result}
        out.extend(_lines({k: v for k, v in body.items() if k != "schema"}, 1))
    for key, name in (("items", "items.header"), ("notices", "notices.header")):
        if envelope.get(key):
            out.append(f"{text(name, lang)}:")
            out.extend(_lines(envelope[key], 1))
    return "\n".join(out) + "\n"


def render_error(document: dict[str, Any], lang: Lang) -> str:
    """Render an error document for a person (stderr, before the JSON line).

    Parameters
    ----------
    document : dict
        The ``hydraulik-error/1`` document (English).
    lang : {"pl", "en"}
        Language of the labels and, for the common reasons, of the explanation.

    Returns
    -------
    str
        One or two lines ending with a newline.
    """
    reason = document.get("details", {}).get("reason")
    explanation = reason_text(reason, lang) or document["message"]
    out = [f"{text('error.label', lang)}: {document['code']}: {explanation}"]
    if lang == "pl" and explanation != document["message"]:
        out.append(f"  ({document['message']})")
    if document.get("hint"):
        out.append(f"{text('hint.label', lang)}: {document['hint']}")
    return "\n".join(out) + "\n"
