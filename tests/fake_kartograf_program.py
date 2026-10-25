"""A stand-in for the ``kartograf`` program, run as a script by the tests.

It answers like a Kartograf that implements the data-output convention (Nogat DEV
section 19): ``commands schema`` declares ``output_dir`` with ``path_role: output``,
``--check`` gives a plan whose entries have ``path`` and ``action``, a real call writes
the files and reports ``files[]`` as ``{path, size_bytes, sha256, status}``, a conflict
is an error document on the last line of stderr. The scenario is a JSON object in the
environment variable ``FAKE_KARTOGRAF``:

``plain`` (default true)
    False answers like today's Kartograf, whose ``output_dir`` is the root of a store
    (``path_role: root``) and whose plan option is ``check_updates``.
``log``
    File that gets one JSON line with the arguments of every call.
``errors``
    Command name to ``{code, message, hint, details, exit_code}``: that command ends
    with the error document when it fetches data (not with ``--check``).
``plan_errors``
    The same for the call with ``--check``.
``outcomes``
    Command name to ``partial`` or ``failed``: the call writes the first file only
    (partial) or none (failed) and reports a failed unit.
``hang``
    Command name that sleeps for a minute.
``garbage``
    Command name whose stdout is not JSON.
``crash``
    Command name to an exit code: the call dies without an error document.
``no_check``
    True leaves the ``check`` option out of the schema.
``plan``
    ``none`` makes a plan without per-file actions.
``skipped``
    Command name to a list of ``{id, reason, message}`` reported in ``skipped[]``.
``names``
    Command name to the list of file names the call writes (one per call by default).
``payloads``
    Command name to the path of a file whose bytes the call writes, under every name it
    writes, instead of the text that stands for data by default: a real GeoTIFF or
    GeoPackage that the next step of a test can read.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

VERSION = "kartograf 9.9.9-fake"
CRS = ["EPSG:2180", "EPSG:4326", "EPSG:2176", "EPSG:5514"]
EXIT_OF = {"conflict": 4, "source_unavailable": 5, "no_data": 14, "validation_error": 2}


def _option(name: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "type": kind,
        "required": extra.pop("required", False),
        "description": f"the {name} option of the fake",
        **extra,
    }


def _enum(*values: str) -> list[dict[str, str]]:
    return [{"value": value, "meaning": f"the value {value}"} for value in values]


def _area() -> list[dict[str, Any]]:
    return [
        _option("bbox", "array", items="number", one_of="area"),
        _option("bbox_crs", "string", enum=_enum(*CRS)),
        _option("geometry", "string", path_role="input", one_of="area"),
        _option("layer", "string"),
    ]


def _own(command: str) -> list[dict[str, Any]]:
    if command == "elevation download":
        return [
            _option("product", "string", required=True, enum=_enum("nmt", "nmpt")),
            _option("country", "string", enum=_enum("pl", "cz", "auto")),
            *_area(),
            _option("cutout", "boolean", default=False),
            _option("horizontal_crs", "string", enum=_enum("EPSG:2180", "EPSG:5514")),
            _option("vertical_crs", "string", enum=_enum("EVRF2007", "KRON86")),
        ]
    if command == "landcover download":
        return [
            _option("product", "string", required=True, enum=_enum("bdot10k", "bdoo")),
            *_area(),
        ]
    if command == "soil hsg":
        return [
            _option("depth", "string", required=True, enum=_enum("0-5cm", "5-15cm")),
            *_area(),
        ]
    return []


def _output(plain: bool, no_check: bool) -> list[dict[str, Any]]:
    if not plain:
        return [
            _option("output_dir", "string", required=True, path_role="root"),
            _option("check_updates", "boolean"),
        ]
    options = [
        _option("output_dir", "string", path_role="output", one_of="target"),
        _option("root", "string", path_role="root", one_of="target"),
        _option("force", "boolean"),
    ]
    return options if no_check else [*options, _option("check", "boolean")]


COMMANDS = ("elevation download", "landcover download", "soil hsg")


def _envelope(
    command: str, result: Any, status: str = "ok", *, check: bool = False, **extra: Any
) -> str:
    document = {
        "schema": "kartograf-result/1",
        "tool": "kartograf",
        "version": "9.9.9",
        "command": command,
        "check": check,
        "status": status,
        "result": result,
        **extra,
    }
    return json.dumps(document)


def _fail(error: dict[str, Any], command: str) -> int:
    code = error.get("code", "source_unavailable")
    document = {
        "schema": "kartograf-error/1",
        "code": code,
        "title": code,
        "message": error.get("message", f"the fake failed {command}"),
        "details": error.get("details", {}),
        "exit_code": error.get("exit_code", EXIT_OF.get(code, 1)),
    }
    if error.get("hint"):
        document["hint"] = error["hint"]
    print("Info: progress line of the fake", file=sys.stderr)
    print(json.dumps(document), file=sys.stderr)
    return int(document["exit_code"])


def _value(args: list[str], flag: str) -> str | None:
    prefix = flag + "="
    for arg in args:
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return None


def _names(command: str, args: list[str], scenario: dict[str, Any]) -> list[str]:
    """The names of the files a call would write, as Kartograf names them."""
    if command in scenario.get("names", {}):
        return list(scenario["names"][command])
    area = _value(args, "--bbox") or Path(_value(args, "--geometry") or "area").stem
    area = area.replace(",", "_").replace(".0", "")
    if command == "elevation download":
        return [f"{area}.tif"]
    if command == "landcover download":
        return ["1465.gpkg"]
    return [f"hsg_{area}.tif"]


def _content(name: str) -> bytes:
    return (name * 50).encode("utf-8")


def _payload(command: str, name: str, scenario: dict[str, Any]) -> bytes:
    """The bytes of a file: those of the scenario's payload, else a stand-in text."""
    source = scenario.get("payloads", {}).get(command)
    return Path(source).read_bytes() if source else _content(name)


def _call(command: str, args: list[str], scenario: dict[str, Any]) -> int:
    if command in scenario.get("hang", []):
        time.sleep(60)
    if command in scenario.get("crash", {}):
        print("Traceback: the fake crashed", file=sys.stderr)
        return int(scenario["crash"][command])
    if command in scenario.get("garbage", []):
        print("this is not json")
        return 0
    key = "plan_errors" if "--check" in args else "errors"
    if command in scenario.get(key, {}):
        return _fail(scenario[key][command], command)
    target = _value(args, "--output-dir")
    if target is None:
        print("error: --output-dir is required", file=sys.stderr)
        return 2
    directory = Path(target)
    force = "--force" in args
    check = "--check" in args
    names = _names(command, args, scenario)
    paths = [directory / name for name in names]
    actions = [
        {
            "path": str(path),
            "action": "conflict" if path.exists() and not force else "write",
        }
        for path in paths
    ]
    for entry, path in zip(actions, paths, strict=True):
        if path.exists() and force:
            entry["action"] = "replace"
        if entry["action"] == "conflict":
            entry["reason"] = "output_exists"
    if check:
        if scenario.get("plan") == "none":
            print(_envelope(command, {"schema": "kartograf-plan/1"}, check=True))
        else:
            plan = {"schema": "kartograf-plan/1", "items": actions}
            print(_envelope(command, plan, check=True))
        return 0
    conflicts = [entry["path"] for entry in actions if entry["action"] == "conflict"]
    if conflicts:
        error = {
            "code": "conflict",
            "message": f"{len(conflicts)} output file(s) already exist",
            "details": {"reason": "output_exists", "paths": conflicts},
            "hint": "Use --force to replace them, or choose another --output-dir.",
        }
        return _fail(error, command)
    outcome = scenario.get("outcomes", {}).get(command, "ok")
    skipped = scenario.get("skipped", {}).get(command, [])
    written = (
        paths[:1] if outcome == "partial" else [] if outcome == "failed" else paths
    )
    files: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    directory.mkdir(parents=True, exist_ok=True)
    for path in written:
        data = _payload(command, path.name, scenario)
        status = "replaced" if path.exists() else "written"
        path.write_bytes(data)
        files.append(
            {
                "path": str(path),
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "status": status,
            }
        )
        items.append({"id": path.stem, "status": "ok"})
    for path in paths[len(written) :] if outcome != "ok" else []:
        items.append(
            {
                "id": path.stem,
                "status": "failed",
                "code": "source_unavailable",
                "reason": "download_failed",
                "message": f"the fake could not fetch {path.name}",
            }
        )
    result = {"schema": "kartograf-download/1", "files": files, "skipped": skipped}
    notices = [
        {"level": "info", "code": "fake_notice", "message": f"fake notice of {command}"}
    ]
    status = outcome if outcome != "ok" else "ok"
    print(_envelope(command, result, status, items=items, notices=notices))
    return {"ok": 0, "partial": 10, "failed": 11}[status]


def main(argv: list[str]) -> int:
    """Answer one call the way the scenario says."""
    scenario: dict[str, Any] = json.loads(os.environ.get("FAKE_KARTOGRAF") or "{}")
    if scenario.get("log"):
        with Path(scenario["log"]).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(argv) + "\n")
    if argv == ["--version"]:
        print(scenario.get("version", VERSION))
        return 0
    if argv[:2] == ["commands", "schema"]:
        command = (_value(argv, "--command") or "").strip()
        if command in scenario.get("garbage", []):
            print("this is not json")
            return 0
        if command not in COMMANDS:
            print(f"error: unknown command {command!r}", file=sys.stderr)
            return 2
        plain = bool(scenario.get("plain", True))
        options = [
            *_own(command),
            *_output(plain, bool(scenario.get("no_check", False))),
        ]
        entry = {"name": command, "options": options}
        result = {"schema": "kartograf-commands/1", "tool": "kartograf"}
        print(_envelope("commands schema", {**result, "commands": [entry]}))
        return 0
    command = " ".join(argv[:2])
    if command not in COMMANDS:
        print(f"error: unknown command {command!r}", file=sys.stderr)
        return 2
    return _call(command, argv[2:], scenario)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
