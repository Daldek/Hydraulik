"""``model build`` with the BDOT10k land cover: Manning n, the curve number, the roofs.

The land is a 40 m x 20 m terrain of 5 m cells (8 columns, 4 rows; row 0 is the south):
grass in the west half, forest in the three southern rows of the east half and a pond
in the northern row of the east half. Three buildings lie along the south edge: the
first covers the whole cell (row 0, column 0), the second 60 % of the next cell and the
third 40 % of the one after. The soil is group B in the west and D in the east. Every
expected value is computed by hand from the class table of ``docs/LAND_COVER.md``.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

pytest.importorskip("rasterio")
pytest.importorskip("geopandas")

import rasterio  # noqa: E402
from shapely.geometry import box  # noqa: E402

from hydraulik import build_model  # noqa: E402
from hydraulik.cli import main  # noqa: E402
from hydraulik.data.tables import render_rain_table  # noqa: E402
from hydraulik.documents import ModelDocument, PlanDocument  # noqa: E402
from hydraulik.exceptions import (  # noqa: E402
    HydraulikError,
    InputDataError,
    NotFoundError,
)

from ..synthetic import (  # noqa: E402
    add_layer,
    read_model_array,
    write_codes,
    write_raster,
)

Float = NDArray[np.float64]
X0, Y0 = 362000.0, 504000.0
GRASS_N, FOREST_N, POND_N, ROOF_N = 0.15, 0.40, 0.035, 0.011
ALL_FILES = [
    "sfincs.inp",
    "sfincs.ind",
    "sfincs.msk",
    "sfincs.dep",
    "sfincs.precip",
    "sfincs.man",
    "sfincs.scs",
    "manning.tif",
    "curve_number.tif",
]


def ground() -> Float:
    """The terrain z = 0.1 (x - X0) + 0.2 (y - Y0) averaged onto the 5 m cells."""
    rows, columns = np.indices((4, 8))
    result: Float = 0.1 * (5.0 * columns + 2.5) + 0.2 * (5.0 * rows + 2.5)
    return result


def storage(curve_number: Any) -> Any:
    """The SCS storage S [inches] that sfincs.scs holds for a curve number."""
    return 1000.0 / np.asarray(curve_number) - 10.0


def expected_n(*, raised: bool) -> Float:
    """Manning n of every cell; a roof counts only where the buildings are raised."""
    n = np.full((4, 8), GRASS_N)
    n[:3, 4:] = FOREST_N
    n[3, 4:] = POND_N
    if raised:
        n[0, 0] = ROOF_N
        n[0, 1] = 0.4 * GRASS_N + 0.6 * ROOF_N
        n[0, 2] = 0.6 * GRASS_N + 0.4 * ROOF_N
    return n


def expected_cn() -> Float:
    """The composite curve number of every cell: grass B, forest D, a pond, roofs 98."""
    cn = np.full((4, 8), 69.0)
    cn[:, 4:] = 77.0
    cn[3, 4:] = 100.0
    cn[0, 0] = 98.0
    cn[0, 1] = 0.4 * 69.0 + 0.6 * 98.0
    cn[0, 2] = 0.6 * 69.0 + 0.4 * 98.0
    return cn


@pytest.fixture
def rain(tmp_path: Path) -> Path:
    path = tmp_path / "rain.csv"
    path.write_text(render_rain_table(5.0, [2.5] * 12), encoding="utf-8")
    return path


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    xs = X0 + np.arange(40) + 0.5
    ys = Y0 + 20.0 - (np.arange(20) + 0.5)
    x, y = np.meshgrid(xs, ys)
    values = 0.1 * (x - X0) + 0.2 * (y - Y0)
    return write_raster(tmp_path / "dem.tif", values, west=X0, north=Y0 + 20.0)


@pytest.fixture
def bdot(tmp_path: Path) -> Path:
    path = tmp_path / "bdot10k.gpkg"
    add_layer(
        path,
        "OT_PTTR_A",
        [box(X0, Y0, X0 + 20, Y0 + 20)],
        RODZAJ=["roślinność trawiasta"],
    )
    add_layer(path, "OT_PTLZ_A", [box(X0 + 20, Y0, X0 + 40, Y0 + 15)])
    add_layer(path, "OT_PTWP_A", [box(X0 + 20, Y0 + 15, X0 + 40, Y0 + 20)])
    add_layer(
        path,
        "OT_BUBD_A",
        [
            box(X0, Y0, X0 + 5, Y0 + 5),
            box(X0 + 5, Y0, X0 + 8, Y0 + 5),
            box(X0 + 10, Y0, X0 + 12, Y0 + 5),
        ],
        KODKST=["110", "110", "110"],
    )
    return path


@pytest.fixture
def hsg(tmp_path: Path) -> Path:
    """Group B (2) in the west half and D (4) in the east half, 20 m cells."""
    codes = np.array([[2, 4]], dtype=np.uint8)
    return write_codes(tmp_path / "hsg.tif", codes, west=X0, north=Y0 + 20.0, cell=20.0)


def build(tmp_path: Path, dem: Path, rain: Path, **options: Any) -> ModelDocument:
    options.setdefault("output_dir", tmp_path / "model")
    document = build_model(dem=[dem], dx_m=5.0, rain=rain, **options)
    assert isinstance(document, ModelDocument)
    return document


def reason_of(call: Any) -> str:
    with pytest.raises(HydraulikError) as caught:
        call()
    return str(caught.value.details["reason"])


def codes_of(document: ModelDocument) -> dict[str, str]:
    return {item["code"]: item["level"] for item in document.notices}


def test_the_classes_under_each_cell_give_its_manning_n_and_curve_number(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path, hsg: Path
) -> None:
    document = build(tmp_path, dem, rain, landcover=bdot, hsg=hsg)

    model = tmp_path / "model"
    n = read_model_array(model, "sfincs.man", "float32")
    s = read_model_array(model, "sfincs.scs", "float32")
    assert n == pytest.approx(expected_n(raised=False), abs=1e-6)
    assert s == pytest.approx(storage(expected_cn()), abs=1e-4)
    # the pond is the north row of the east half: row 3, columns 4 to 7
    assert n[3, 4:] == pytest.approx(POND_N) and n[2, 4:] == pytest.approx(FOREST_N)
    infiltration = document.infiltration
    assert infiltration is not None
    assert (document.roughness["source"], infiltration["source"]) == (
        "landcover",
        "landcover",
    )
    assert document.roughness["min_s_m13"] == pytest.approx(POND_N)
    assert document.roughness["max_s_m13"] == pytest.approx(FOREST_N)
    assert infiltration["resampling"] == "nearest" and infiltration["gap_cells"] == 0
    assert "path" not in infiltration
    assert infiltration["hsg"] == {
        "path": str(hsg),
        "default": None,
        "default_cells": 0,
        "cells": {"A": 0, "B": 16, "C": 0, "D": 16},
    }
    assert read_model_array(model, "sfincs.dep", "float32") == pytest.approx(
        ground(), abs=1e-4
    )  # not raised: the roofs are ground


def test_the_result_reports_the_areas_the_roads_and_the_buildings(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path, hsg: Path
) -> None:
    document = build(tmp_path, dem, rain, landcover=bdot, hsg=hsg)

    report = document.landcover
    assert report is not None
    areas = {item["class"]: item["area_m2"] for item in report["classes"]}
    assert areas == pytest.approx(
        {"grass": 350.0, "forest": 300.0, "water": 100.0, "building": 50.0}
    )
    assert report["path"] == str(bdot)
    assert report["table"] == {"source": "shipped", "overridden": []}
    assert report["unclassified_percent"] == 0.0
    assert report["buildings"] == {"cells": 2, "share": 0.5, "raise_m": 0.0}
    codes = codes_of(document)
    assert codes["landcover_buildings"] == "info"
    assert "landcover_unclassified" not in codes and "cn_gaps" not in codes
    assert "no_infiltration" not in codes and "manning_default" not in codes


def test_raised_buildings_are_higher_and_rough_like_a_roof(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path, hsg: Path
) -> None:
    document = build(tmp_path, dem, rain, landcover=bdot, hsg=hsg, building_raise_m=3.0)

    model = tmp_path / "model"
    z = read_model_array(model, "sfincs.dep", "float32")
    n = read_model_array(model, "sfincs.man", "float32")
    lifted = ground()
    lifted[0, :2] += 3.0  # shares of 1.0 and 0.6; the third building holds 0.4 only
    assert z == pytest.approx(lifted, abs=1e-4)
    assert n == pytest.approx(expected_n(raised=True), abs=1e-6)
    assert read_model_array(model, "sfincs.scs", "float32") == pytest.approx(
        storage(expected_cn()), abs=1e-4
    )  # a roof sheds water the same either way
    assert document.landcover is not None
    assert document.landcover["buildings"] == {"cells": 2, "share": 0.5, "raise_m": 3.0}
    assert document.elevation["max_m"] == pytest.approx(lifted.max(), abs=1e-4)
    message = next(
        item["message"]
        for item in document.notices
        if item["code"] == "landcover_buildings"
    )
    assert "2 cells" in message and "raised by 3 m" in message


def test_the_manning_and_curve_number_rasters_are_written_beside_the_model(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path, hsg: Path
) -> None:
    document = build(tmp_path, dem, rain, landcover=bdot, hsg=hsg)

    assert sorted(Path(f["path"]).name for f in document.files) == sorted(ALL_FILES)
    assert sorted(p.name for p in (tmp_path / "model").iterdir()) == sorted(ALL_FILES)
    with rasterio.open(tmp_path / "model" / "manning.tif") as manning:
        assert manning.crs.to_epsg() == 2180
        assert (manning.bounds.left, manning.bounds.top) == (X0, Y0 + 20.0)
        assert manning.tags()["variable"] == "manning_n"
        assert manning.tags()["source"] == "bdot10k.gpkg"
        # north-up: the first row of the file is the northern row of the model
        np.testing.assert_allclose(
            np.flipud(manning.read(1)), expected_n(raised=False), rtol=1e-5
        )
    with rasterio.open(tmp_path / "model" / "curve_number.tif") as curve:
        np.testing.assert_allclose(np.flipud(curve.read(1)), expected_cn(), rtol=1e-5)


def test_a_class_table_replaces_the_values_it_names(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path, hsg: Path
) -> None:
    table = tmp_path / "classes.csv"
    table.write_text("class,manning_n,cn_b\ngrass,0.2,60\n", encoding="utf-8")

    document = build(tmp_path, dem, rain, landcover=bdot, hsg=hsg, classes=table)

    model = tmp_path / "model"
    n = read_model_array(model, "sfincs.man", "float32")
    s = read_model_array(model, "sfincs.scs", "float32")
    assert n[3, 0] == pytest.approx(0.2) and n[3, 4] == pytest.approx(POND_N)
    assert s[3, 0] == pytest.approx(storage(60.0), abs=1e-4)
    assert document.landcover is not None
    assert document.landcover["table"] == {
        "source": str(table),
        "overridden": ["grass"],
    }


def test_a_default_group_fills_the_cells_the_soil_raster_does_not_cover(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path
) -> None:
    west = write_codes(
        tmp_path / "west.tif",
        np.array([[2]], dtype=np.uint8),
        west=X0,
        north=Y0 + 20.0,
        cell=20.0,
    )

    gaps = build(tmp_path, dem, rain, landcover=bdot, hsg=west)
    filled = build(
        tmp_path,
        dem,
        rain,
        landcover=bdot,
        hsg=west,
        default_hsg="C",
        output_dir=tmp_path / "filled",
    )

    s = read_model_array(tmp_path / "model", "sfincs.scs", "float32")
    assert np.all(s[:, 4:] == 0.0) and np.all(s[:, :4] > 0.0)  # no infiltration east
    assert gaps.infiltration is not None and gaps.infiltration["gap_cells"] == 16
    warning = next(n for n in gaps.notices if n["code"] == "cn_gaps")
    assert warning["level"] == "warning" and "16 cells" in warning["message"]
    assert "--default-hsg" in warning["message"]
    s = read_model_array(tmp_path / "filled", "sfincs.scs", "float32")
    assert s[:3, 4:] == pytest.approx(storage(70.0), abs=1e-4)  # forest, group C
    assert filled.infiltration is not None and filled.infiltration["gap_cells"] == 0
    assert filled.infiltration["hsg"] == {
        "path": str(west),
        "default": "C",
        "default_cells": 16,
        "cells": {"A": 0, "B": 16, "C": 16, "D": 0},
    }
    notice = next(n for n in filled.notices if n["code"] == "hsg_default")
    assert notice["level"] == "warning" and "16 cells" in notice["message"]
    assert "cn_gaps" not in codes_of(filled)


def test_a_default_group_alone_gives_every_cell_that_group(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path
) -> None:
    document = build(tmp_path, dem, rain, landcover=bdot, default_hsg="D")

    s = read_model_array(tmp_path / "model", "sfincs.scs", "float32")
    assert s[3, 0] == pytest.approx(storage(84.0), abs=1e-4)  # grass, group D
    infiltration = document.infiltration
    assert infiltration is not None and "resampling" not in infiltration
    assert infiltration["hsg"]["path"] is None
    assert infiltration["hsg"]["cells"]["D"] == 32
    notice = next(n for n in document.notices if n["code"] == "hsg_default")
    assert notice["level"] == "info" and "every cell gets group D" in notice["message"]


def test_the_land_cover_without_a_soil_group_leaves_infiltration_off_and_says_how(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path
) -> None:
    document = build(tmp_path, dem, rain, landcover=bdot)

    model = tmp_path / "model"
    assert document.infiltration is None
    assert not (model / "sfincs.scs").exists()
    assert not (model / "curve_number.tif").exists()
    assert (model / "manning.tif").is_file()
    message = next(n for n in document.notices if n["code"] == "no_infiltration")
    assert "--default-hsg" in message["message"]


def test_the_curve_number_may_come_from_a_raster_beside_the_land_cover(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path
) -> None:
    cn = write_raster(
        tmp_path / "cn.tif", np.full((20, 40), 80.0), west=X0, north=Y0 + 20.0
    )

    document = build(tmp_path, dem, rain, landcover=bdot, curve_number_raster=cn)

    model = tmp_path / "model"
    infiltration = document.infiltration
    assert document.roughness["source"] == "landcover"
    assert infiltration is not None and "hsg" not in infiltration
    assert infiltration["source"] == "curve_number_raster"
    assert read_model_array(model, "sfincs.scs", "float32") == pytest.approx(2.5)
    assert not (model / "curve_number.tif").exists()


def test_a_soil_raster_that_is_not_one_of_groups_or_misses_the_domain_is_an_error(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path
) -> None:
    wrong = write_codes(
        tmp_path / "wrong.tif",
        np.array([[2, 7]], dtype=np.uint8),
        west=X0,
        north=Y0 + 20.0,
        cell=20.0,
    )
    elsewhere = write_codes(
        tmp_path / "elsewhere.tif",
        np.array([[2]], dtype=np.uint8),
        west=X0 + 5000.0,
        north=Y0 + 5020.0,
        cell=20.0,
    )

    with pytest.raises(InputDataError) as invalid:
        build(tmp_path, dem, rain, landcover=bdot, hsg=wrong)
    with pytest.raises(InputDataError) as missing:
        build(tmp_path, dem, rain, landcover=bdot, hsg=elsewhere)

    assert invalid.value.details["reason"] == "invalid_hsg"
    assert (invalid.value.details["cells"], invalid.value.details["value"]) == (16, 7)
    assert missing.value.details["reason"] == "cn_gaps"
    assert "soil raster" in str(missing.value)
    assert not (tmp_path / "model").exists()  # nothing reached the output directory


def test_a_land_cover_file_and_a_class_table_that_cannot_be_used_are_refused(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    other = tmp_path / "other.gpkg"
    add_layer(other, "OT_BUBD_A", [box(X0, Y0, X0 + 5, Y0 + 5)], KODKST=["110"])
    table = tmp_path / "classes.csv"
    table.write_text("class,manning_n\nlake,0.03\n", encoding="utf-8")
    fine = tmp_path / "fine.gpkg"
    add_layer(fine, "OT_PTLZ_A", [box(X0, Y0, X0 + 40, Y0 + 20)])

    assert (
        reason_of(lambda: build(tmp_path, dem, rain, landcover=other))
        == "landcover_layers_missing"
    )
    assert (
        reason_of(lambda: build(tmp_path, dem, rain, landcover=fine, classes=table))
        == "invalid_classes_table"
    )
    with pytest.raises(NotFoundError):
        build(tmp_path, dem, rain, landcover=tmp_path / "gone.gpkg")
    assert not (tmp_path / "model").exists()


def test_check_plans_the_land_cover_and_reads_what_a_run_would_read(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path, hsg: Path
) -> None:
    plan = build_model(
        dem=[dem],
        dx_m=5.0,
        rain=rain,
        landcover=bdot,
        hsg=hsg,
        default_hsg="C",
        building_raise_m=3.0,
        output_dir=tmp_path / "model",
        check=True,
    )

    assert isinstance(plan, PlanDocument)
    assert sorted(t["name"] for t in plan.targets) == sorted(ALL_FILES)
    step = next(s for s in plan.steps if s.startswith("paint the land cover"))
    assert str(bdot) in step and "the shipped class values" in step
    assert str(hsg) in step and "group C where it has none" in step
    assert "raise the cells under roofs by 3 m" in step
    assert not (tmp_path / "model").exists()


def test_the_plan_names_what_makes_the_curve_number_and_which_values_are_replaced(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path, hsg: Path
) -> None:
    table = tmp_path / "classes.csv"
    table.write_text("class,manning_n\nforest,0.2\nwater,0.03\n", encoding="utf-8")

    def step(**options: Any) -> str:
        plan = build_model(
            dem=[dem],
            dx_m=5.0,
            rain=rain,
            landcover=bdot,
            output_dir=tmp_path / "model",
            check=True,
            **options,
        )
        assert isinstance(plan, PlanDocument)
        return next(s for s in plan.steps if s.startswith("paint the land cover"))

    assert step().endswith("into Manning n")  # no soil group: no curve number
    assert step(hsg=hsg).endswith(
        f"with the soil groups of {hsg}, into the curve number"
    )
    assert step(default_hsg="B").endswith(
        "with soil group B everywhere, into the curve number"
    )
    assert f"the class values of {table} (2 replaced)" in step(classes=table)


def test_check_fails_on_a_missing_file_and_on_a_class_table_a_run_would_refuse(
    tmp_path: Path, dem: Path, rain: Path, bdot: Path
) -> None:
    table = tmp_path / "classes.csv"
    table.write_text("class,manning_n\nwater,2.5\n", encoding="utf-8")

    def check(**options: Any) -> object:
        return build_model(
            dem=[dem],
            dx_m=5.0,
            rain=rain,
            output_dir=tmp_path / "model",
            check=True,
            **options,
        )

    with pytest.raises(NotFoundError):
        check(landcover=tmp_path / "gone.gpkg")
    with pytest.raises(NotFoundError):
        check(landcover=bdot, hsg=tmp_path / "gone.tif")
    assert reason_of(lambda: check(landcover=bdot, classes=table)) == (
        "invalid_classes_table"
    )


def test_the_command_line_takes_the_five_options_and_the_catalog_refuses_a_bad_group(
    tmp_path: Path,
    dem: Path,
    rain: Path,
    bdot: Path,
    hsg: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = ["model", "build", "--dem", str(dem), "--dx-m", "5", "--rain", str(rain)]
    base += ["--landcover", str(bdot), "--output-dir", str(tmp_path / "model")]

    code = main([*base, "--hsg", str(hsg), "--building-raise-m", "3", "--json"])

    envelope = json.loads(capsys.readouterr().out)
    assert code == 0 and envelope["status"] == "ok"
    result = envelope["result"]
    assert result["roughness"]["source"] == "landcover"
    assert result["landcover"]["buildings"]["raise_m"] == 3.0
    assert result["infiltration"]["hsg"]["cells"]["B"] == 16

    code = main([*base, "--default-hsg", "E", "--json"])

    captured = capsys.readouterr()
    error = json.loads(captured.err.strip().splitlines()[-1])
    assert code == 2 and captured.out == ""
    assert error["details"]["reason"] == "not_allowed"
