"""Reading and patching a SWMM input file that the user wrote (ADR-0002).

Only what the coupling needs is understood: the sections as text, the junctions, the
names of every node, their coordinates and the options. Patching changes ``[OPTIONS]``
and the surcharge depth of junctions and leaves every other line as it is.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from hydraulik.exceptions import InputDataError, UnsupportedError

__all__ = [
    "InpJunction",
    "coordinates",
    "junctions",
    "node_names",
    "options",
    "patch_junction_surcharge",
    "patch_options",
    "require_metric",
    "sections",
]

_SECTION = re.compile(r"^\s*\[(?P<name>[A-Za-z_]+)\]\s*$")


def sections(text: str) -> dict[str, list[str]]:
    r"""Split an INP text into its sections.

    Parameters
    ----------
    text : str
        The content of an INP file.

    Returns
    -------
    dict
        Section name in capitals to its data lines; comments (``;``) and empty lines
        are dropped. Lines before the first section are ignored.

    Examples
    --------
    >>> sections("[OPTIONS]\\nFLOW_UNITS CMS ; metric\\n;; note\\n")
    {'OPTIONS': ['FLOW_UNITS CMS']}
    """
    result: dict[str, list[str]] = {}
    current: list[str] | None = None
    for raw in text.splitlines():
        header = _SECTION.match(raw)
        if header:
            current = result.setdefault(header["name"].upper(), [])
            continue
        line = raw.split(";", 1)[0].strip()
        if current is not None and line:
            current.append(line)
    return result


def options(text: str) -> dict[str, str]:
    r"""Return the ``[OPTIONS]`` of an INP text, keys in capitals.

    Parameters
    ----------
    text : str
        The content of an INP file.

    Returns
    -------
    dict
        Option name to its value text.

    Examples
    --------
    >>> options("[OPTIONS]\\nFLOW_UNITS CMS\\nROUTING_STEP 0.5\\n")["ROUTING_STEP"]
    '0.5'
    """
    found: dict[str, str] = {}
    for line in sections(text).get("OPTIONS", []):
        key, _, value = line.partition(" ")
        found[key.upper()] = value.strip()
    return found


def require_metric(text: str) -> None:
    """Refuse an INP whose flow unit is not CMS.

    The coupler passes flows in the unit of the file and reads heads in its length
    unit; only ``FLOW_UNITS CMS`` (metres, cubic metres per second) is supported.

    Parameters
    ----------
    text : str
        The content of an INP file.

    Raises
    ------
    UnsupportedError
        If ``FLOW_UNITS`` is not ``CMS`` (reason ``flow_units``).
    """
    units = options(text).get("FLOW_UNITS", "CFS").upper()
    if units != "CMS":
        raise UnsupportedError(
            f"the SWMM file uses FLOW_UNITS {units}; only CMS is supported",
            details={"option": "FLOW_UNITS", "value": units, "allowed": ["CMS"]},
            hint="Convert the model to SI units (FLOW_UNITS CMS) in SWMM.",
            reason="flow_units",
        )


@dataclass(frozen=True)
class InpJunction:
    """A junction as the INP file declares it.

    Attributes
    ----------
    name : str
        Node name.
    invert_m : float
        Invert elevation [m].
    max_depth_m : float
        Maximum depth [m]; the rim is ``invert_m + max_depth_m``.
    surcharge_depth_m : float
        Extra depth above the rim before the node floods [m].
    """

    name: str
    invert_m: float
    max_depth_m: float
    surcharge_depth_m: float

    @property
    def rim_m(self) -> float:
        """float: rim elevation [m]."""
        return self.invert_m + self.max_depth_m


def junctions(text: str) -> list[InpJunction]:
    r"""Return the junctions of an INP text.

    Parameters
    ----------
    text : str
        The content of an INP file.

    Returns
    -------
    list of InpJunction
        In file order.

    Raises
    ------
    InputDataError
        If a junction line has fewer than three fields or a field is not a number.

    Examples
    --------
    >>> junctions("[JUNCTIONS]\\nJ1 8.0 2.0 0 0 0\\n")[0].rim_m
    10.0
    """
    found: list[InpJunction] = []
    for line in sections(text).get("JUNCTIONS", []):
        fields = line.split()
        try:
            if len(fields) < 3:
                raise ValueError("too few fields")
            found.append(
                InpJunction(
                    fields[0],
                    float(fields[1]),
                    float(fields[2]),
                    float(fields[4]) if len(fields) > 4 else 0.0,
                )
            )
        except ValueError as exc:
            raise InputDataError(
                f"cannot read the junction line {line!r}: {exc}",
                details={"line": line},
                reason="invalid_inp",
            ) from exc
    return found


def node_names(text: str) -> list[str]:
    r"""Return the names of every node that an INP text declares.

    Parameters
    ----------
    text : str
        The content of an INP file.

    Returns
    -------
    list of str
        The junctions, outfalls, dividers and storage units, in that order and in file
        order within each.

    Examples
    --------
    >>> node_names("[JUNCTIONS]\\nJ1 8.0 2.0\\n[OUTFALLS]\\nOUT 7.0 FREE NO\\n")
    ['J1', 'OUT']
    """
    found = sections(text)
    return [
        line.split()[0]
        for section in ("JUNCTIONS", "OUTFALLS", "DIVIDERS", "STORAGE")
        for line in found.get(section, [])
    ]


def coordinates(text: str) -> dict[str, tuple[float, float]]:
    r"""Return the ``[COORDINATES]`` of an INP text.

    Parameters
    ----------
    text : str
        The content of an INP file.

    Returns
    -------
    dict
        Node name to ``(x, y)``.

    Raises
    ------
    InputDataError
        If a line is not ``name x y``.

    Examples
    --------
    >>> coordinates("[COORDINATES]\\nJ1 10.5 20.0\\n")
    {'J1': (10.5, 20.0)}
    """
    found: dict[str, tuple[float, float]] = {}
    for line in sections(text).get("COORDINATES", []):
        fields = line.split()
        try:
            found[fields[0]] = (float(fields[1]), float(fields[2]))
        except (IndexError, ValueError) as exc:
            raise InputDataError(
                f"cannot read the coordinate line {line!r}",
                details={"line": line},
                reason="invalid_inp",
            ) from exc
    return found


def patch_options(text: str, updates: Mapping[str, str | float]) -> str:
    r"""Set options in the ``[OPTIONS]`` section, adding those that are absent.

    Parameters
    ----------
    text : str
        The content of an INP file.
    updates : Mapping[str, str or float]
        Option name to its new value.

    Returns
    -------
    str
        The text with the options set; every other line is unchanged.

    Raises
    ------
    InputDataError
        If the file has no ``[OPTIONS]`` section.

    Examples
    --------
    >>> patch_options("[OPTIONS]\\nROUTING_STEP 30\\n", {"ROUTING_STEP": 0.5})
    '[OPTIONS]\\nROUTING_STEP          0.5\\n'
    """
    lines = text.splitlines(keepends=True)
    start = next(
        (
            i
            for i, raw in enumerate(lines)
            if (m := _SECTION.match(raw)) and m["name"].upper() == "OPTIONS"
        ),
        None,
    )
    if start is None:
        raise InputDataError(
            "the SWMM file has no [OPTIONS] section",
            reason="invalid_inp",
            hint="A SWMM input file starts with [TITLE] and [OPTIONS].",
        )
    end = next(
        (i for i in range(start + 1, len(lines)) if _SECTION.match(lines[i])),
        len(lines),
    )
    remaining = {key.upper(): value for key, value in updates.items()}
    for i in range(start + 1, end):
        data = lines[i].split(";", 1)[0].strip()
        if not data:
            continue
        key = data.split(None, 1)[0].upper()
        if key in remaining:
            lines[i] = f"{key:<20} {remaining.pop(key)}\n"
    added = [f"{key:<20} {value}\n" for key, value in remaining.items()]
    if added and end > start + 1 and not lines[end - 1].endswith("\n"):
        lines[end - 1] += "\n"
    lines[end:end] = added
    return "".join(lines)


def patch_junction_surcharge(
    text: str, depth_m: float, names: Iterable[str] | None = None
) -> str:
    """Set ``SurDepth`` of junctions (all of them, or the named ones).

    Parameters
    ----------
    text : str
        The content of an INP file.
    depth_m : float
        New surcharge depth [m]: 0 lets SWMM flood a full node, a large value stops it.
    names : iterable of str or None, optional
        Junctions to change; every junction when ``None``.

    Returns
    -------
    str
        The text with the junction lines rewritten; other lines are unchanged.
    """
    wanted = None if names is None else set(names)
    lines = text.splitlines(keepends=True)
    inside = False
    for i, raw in enumerate(lines):
        header = _SECTION.match(raw)
        if header:
            inside = header["name"].upper() == "JUNCTIONS"
            continue
        data = raw.split(";", 1)[0].split()
        if (
            not inside
            or len(data) < 3
            or (wanted is not None and data[0] not in wanted)
        ):
            continue
        data = (data + ["0", "0", "0"])[:6]
        data[4] = f"{depth_m:g}"
        lines[i] = f"{data[0]:<8} " + " ".join(data[1:]) + "\n"
    return "".join(lines)
