"""``terrain download`` on the real Kartograf and the real sources (network).

It skips itself until the installed Kartograf writes plain files: its schema must
declare ``output_dir`` with ``path_role: output`` (the data-output convention, DEV
section 19), which Kartograf 0.8.0 does not have yet. Set
``HYDRAULIK_KARTOGRAF_EXE`` (or have ``kartograf`` on ``PATH``) and run ``pytest -m
live``. The area is one square kilometre in Poznan (EPSG:2180); the BDOT10k county
package, 100 MB and more, is not fetched.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from hydraulik.cli import main
from hydraulik.engines.detect import find_kartograf
from hydraulik.settings import load_settings

KARTOGRAF = os.environ.get("HYDRAULIK_KARTOGRAF_EXE") or shutil.which("kartograf")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not KARTOGRAF,
        reason="set HYDRAULIK_KARTOGRAF_EXE or put kartograf on PATH to run this test",
    ),
]

AREA = ["--bbox", "362000,504000,363000,505000", "--crs", "EPSG:2180"]


def _call(
    capsys: pytest.CaptureFixture[str], *args: str, code: int = 0
) -> dict[str, object]:
    exit_code = main([*args, "--json"])
    captured = capsys.readouterr()
    assert exit_code == code, captured.err
    document = captured.out if code == 0 else captured.err.strip().splitlines()[-1]
    envelope: dict[str, object] = json.loads(document)
    return envelope


def test_the_terrain_and_the_soil_groups_of_a_square_kilometre_become_plain_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rasterio = pytest.importorskip("rasterio")
    monkeypatch.setenv("HYDRAULIK_KARTOGRAF_EXE", str(KARTOGRAF))
    status, words = find_kartograf(load_settings())
    if words is None:
        pytest.skip(status.detail)
    out = tmp_path / "data"
    arguments = ["terrain", "download", *AREA, "--products", "elevation,soil"]
    arguments += ["--output-dir", str(out)]

    planned = _call(capsys, *arguments, "--check")
    fetched = _call(capsys, *arguments)
    again = _call(capsys, *arguments, "--check")
    refused = _call(capsys, *arguments, code=4)

    assert planned["result"]["conflicts"] == []  # type: ignore[index]
    assert fetched["status"] == "ok"
    files = fetched["result"]["files"]  # type: ignore[index]
    assert sorted({Path(f["path"]).parent.name for f in files}) == ["elevation", "soil"]
    assert all(Path(f["path"]).is_file() for f in files)
    assert sorted(p.name for p in out.iterdir()) == ["elevation", "soil"]
    assert again["result"]["conflicts"] == ["output_exists"]  # type: ignore[index]
    assert refused["details"]["reason"] == "output_exists"  # type: ignore[index]
    elevation = next(f for f in files if "elevation" in f["path"])
    soil = next(f for f in files if "soil" in f["path"])
    with rasterio.open(elevation["path"]) as dem:
        assert dem.crs.to_epsg() == 2180 and dem.count == 1
    with rasterio.open(soil["path"]) as groups:
        assert groups.dtypes[0] == "uint8"
        assert set(groups.read(1).ravel().tolist()) <= {0, 1, 2, 3, 4}
