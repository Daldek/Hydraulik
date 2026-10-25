"""``model build``: rasters on the grid, the domain, roughness, infiltration, outlet."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

pytest.importorskip("rasterio")
pytest.importorskip("geopandas")

from shapely.geometry import LineString, Point, box  # noqa: E402

from hydraulik import build_model, run_command  # noqa: E402
from hydraulik.cli import main  # noqa: E402
from hydraulik.data.tables import render_rain_table  # noqa: E402
from hydraulik.documents import ModelDocument, PlanDocument  # noqa: E402
from hydraulik.engines.sfincs.inp import precip_depth_mm, read_inp  # noqa: E402
from hydraulik.exceptions import (  # noqa: E402
    ConflictError,
    HydraulikError,
    InputDataError,
    InvalidInputError,
    MissingDependencyError,
    NotFoundError,
    UnsupportedError,
)

from ..synthetic import (  # noqa: E402
    read_model_array,
    write_raster,
    write_vector,
)

Float = NDArray[np.float64]
X0, Y0 = 362000.0, 504000.0  # south-west corner of the test terrain [m], EPSG:2180


def plane(
    rows: int = 20, columns: int = 40, *, west: float = X0, cell: float = 1.0
) -> Float:
    """Terrain z = 0.1 (x - X0) + 0.2 (y - Y0) at the source cell centres, north-up."""
    north = Y0 + rows * cell
    xs = west + (np.arange(columns) + 0.5) * cell
    ys = north - (np.arange(rows) + 0.5) * cell
    x, y = np.meshgrid(xs, ys)
    result: Float = 0.1 * (x - X0) + 0.2 * (y - Y0)
    return result


@pytest.fixture
def rain(tmp_path: Path) -> Path:
    """Twelve 5 min steps of 2.5 mm: 30 mm in an hour."""
    path = tmp_path / "rain.csv"
    path.write_text(render_rain_table(5.0, [2.5] * 12), encoding="utf-8")
    return path


@pytest.fixture
def dem(tmp_path: Path) -> Path:
    """A 40 m x 20 m terrain of 1 m cells that rises to the east and the north."""
    return write_raster(tmp_path / "dem.tif", plane(), west=X0, north=Y0 + 20.0)


def build(tmp_path: Path, dem: Path, rain: Path, **options: Any) -> ModelDocument:
    options.setdefault("dx_m", 5.0)
    options.setdefault("output_dir", tmp_path / "model")
    document = build_model(dem=[dem], rain=rain, **options)
    assert isinstance(document, ModelDocument)
    return document


def reason_of(call: Any) -> str:
    with pytest.raises(HydraulikError) as caught:
        call()
    return str(caught.value.details["reason"])


def test_a_fine_terrain_is_averaged_onto_a_grid_aligned_to_the_cell_size(
    tmp_path: Path, rain: Path
) -> None:
    # the terrain starts 1 m inside the first cell: the corner snaps to a multiple of 5
    shifted = write_raster(
        tmp_path / "shifted.tif",
        plane(20, 39, west=X0 + 1.0),
        west=X0 + 1.0,
        north=Y0 + 20.0,
    )

    document = build(tmp_path, shifted, rain)

    grid = document.grid
    assert (grid["x0_m"], grid["y0_m"], grid["columns"], grid["rows"]) == (
        X0,
        Y0,
        8,
        4,
    )
    z = read_model_array(tmp_path / "model", "sfincs.dep", "float32")
    rows, columns = np.indices((4, 8))
    expected = 0.1 * (2.5 + 5 * columns) + 0.2 * (2.5 + 5 * rows)
    # row 0 is the south edge, the lowest; the first column is only partly covered
    assert z[:, 1:] == pytest.approx(expected[:, 1:], abs=1e-4)
    assert z[0, 1] < z[3, 1] and z[0, 1] < z[0, 6]
    assert document.elevation["sources"][0]["resampling"] == "average"
    assert document.elevation["sources"][0]["cell_size_m"] == 1.0


def test_a_coarser_terrain_is_interpolated_not_averaged(
    tmp_path: Path, rain: Path
) -> None:
    coarse = write_raster(
        tmp_path / "coarse.tif",
        plane(2, 4, cell=10.0),
        west=X0,
        north=Y0 + 20.0,
        cell=10.0,
    )

    document = build(tmp_path, coarse, rain)

    source = document.elevation["sources"][0]
    assert (source["resampling"], source["cell_size_m"]) == ("bilinear", 10.0)
    assert document.grid["active_cells"] == 32


def test_the_domain_is_where_the_terrain_has_data(tmp_path: Path, rain: Path) -> None:
    values = plane()
    values[:, 10:20] = np.nan  # two grid columns (x from 10 to 20 m) have no data
    dem = write_raster(tmp_path / "dem.tif", values, north=Y0 + 20.0)

    document = build(tmp_path, dem, rain)

    assert document.grid["active_cells"] == 24
    mask = read_model_array(tmp_path / "model", "sfincs.msk", "int8")
    assert np.isnan(mask[:, 2:4]).all() and (mask[:, [0, 1, 4]] == 1).all()
    assert document.domain == {"source": "dem"}


def test_a_rectangle_or_polygon_over_a_hole_of_the_terrain_is_an_error(
    tmp_path: Path, rain: Path
) -> None:
    values = plane()
    values[:, 10:20] = np.nan
    dem = write_raster(tmp_path / "dem.tif", values, north=Y0 + 20.0)

    with pytest.raises(InputDataError) as caught:
        build(tmp_path, dem, rain, bbox=[X0, Y0, X0 + 40, Y0 + 20], crs="EPSG:2180")

    assert caught.value.details["reason"] == "dem_gaps"
    assert caught.value.details["cells"] == 8
    assert not (tmp_path / "model").exists()


def test_a_polygon_keeps_the_cells_whose_centre_is_inside_it(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    polygon = write_vector(
        tmp_path / "domain.gpkg",
        box(X0 + 7, Y0 + 3, X0 + 33, Y0 + 17),
        layer="catchment",
    )

    document = build(tmp_path, dem, rain, geometry=polygon, layer="catchment")

    grid = document.grid
    assert (grid["x0_m"], grid["y0_m"], grid["columns"], grid["rows"]) == (
        X0 + 5,
        Y0,
        6,
        4,
    )
    assert grid["active_cells"] == 12  # centres at x 7.5 .. 32.5, y 7.5 and 12.5
    mask = read_model_array(tmp_path / "model", "sfincs.msk", "int8")
    assert np.isnan(mask[[0, 3]]).all() and (mask[1:3] == 1).all()
    assert document.domain["source"] == "geometry"


def test_a_rectangle_in_another_crs_is_reprojected_to_the_crs_of_the_model(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    pyproj = pytest.importorskip("pyproj")
    lon_min, lat_min, lon_max, lat_max = pyproj.Transformer.from_crs(
        "EPSG:2180", "EPSG:4326", always_xy=True
    ).transform_bounds(X0 + 10, Y0 + 5, X0 + 30, Y0 + 15)

    document = build(
        tmp_path, dem, rain, bbox=[lon_min, lat_min, lon_max, lat_max], crs="EPSG:4326"
    )

    grid = document.grid
    assert grid["epsg"] == 2180
    assert grid["x0_m"] <= X0 + 10 and grid["x0_m"] + grid["columns"] * 5 >= X0 + 30
    assert grid["active_cells"] >= 8  # the 20 m x 10 m rectangle is 8 cells of 5 m
    assert document.domain["crs"] == "EPSG:4326"


def test_the_first_terrain_wins_and_the_next_ones_fill_what_it_leaves(
    tmp_path: Path, rain: Path
) -> None:
    first = write_raster(
        tmp_path / "a.tif", np.full((20, 20), 10.0), west=X0, north=Y0 + 20.0
    )
    second = write_raster(
        tmp_path / "b.tif", np.full((20, 40), 20.0), west=X0, north=Y0 + 20.0
    )

    document = build_model(
        dem=[first, second], dx_m=5.0, rain=rain, output_dir=tmp_path / "model"
    )

    assert isinstance(document, ModelDocument)
    z = read_model_array(tmp_path / "model", "sfincs.dep", "float32")
    assert (z[:, :4] == 10.0).all() and (z[:, 4:] == 20.0).all()
    assert [s["cells"] for s in document.elevation["sources"]] == [16, 16]


def test_a_terrain_without_a_crs_or_in_degrees_is_refused(
    tmp_path: Path, rain: Path
) -> None:
    bare = write_raster(tmp_path / "bare.tif", plane(), epsg=None, north=Y0 + 20.0)
    degrees = write_raster(
        tmp_path / "deg.tif", plane(), epsg=4326, west=17.0, north=52.0, cell=0.0001
    )

    def attempt(path: Path) -> str:
        return reason_of(lambda: build(tmp_path, path, rain))

    assert attempt(bare) == "crs_missing"
    assert attempt(degrees) == "crs_not_supported"
    with pytest.raises(UnsupportedError):
        build(tmp_path, degrees, rain)


def test_manning_is_uniform_by_default_a_number_or_a_raster(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    default = build(tmp_path, dem, rain)
    assert read_inp(tmp_path / "model")["manning"] == "0.04"
    assert not (tmp_path / "model" / "sfincs.man").exists()
    assert [n["code"] for n in default.notices if n["code"] == "manning_default"]

    number = build(tmp_path, dem, rain, manning=0.06, output_dir=tmp_path / "m2")
    assert read_inp(tmp_path / "m2")["manning"] == "0.06"
    assert number.roughness == {"source": "uniform", "value_s_m13": 0.06}
    assert "manning_default" not in [n["code"] for n in number.notices]

    values = np.where(np.arange(40) < 20, 0.03, 0.09) * np.ones((20, 1))
    raster = write_raster(tmp_path / "n.tif", values, north=Y0 + 20.0)
    mapped = build(
        tmp_path, dem, rain, manning_raster=raster, output_dir=tmp_path / "m3"
    )
    n = read_model_array(tmp_path / "m3", "sfincs.man", "float32")
    assert (n[:, :4] == pytest.approx(0.03)) and (n[:, 4:] == pytest.approx(0.09))
    assert "manningfile" in read_inp(tmp_path / "m3")
    assert mapped.roughness["source"] == "raster"
    assert mapped.roughness["max_s_m13"] == pytest.approx(0.09)


def test_a_manning_raster_that_misses_part_of_the_domain_is_an_error(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    half = write_raster(tmp_path / "n.tif", np.full((20, 20), 0.03), north=Y0 + 20.0)

    with pytest.raises(InputDataError) as caught:
        build(tmp_path, dem, rain, manning_raster=half)

    assert caught.value.details["reason"] == "manning_gaps"
    assert caught.value.details["cells"] == 16


def test_a_curve_number_or_a_retention_raster_gives_the_scs_storage(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    cn = write_raster(tmp_path / "cn.tif", np.full((20, 40), 80.0), north=Y0 + 20.0)
    retention = write_raster(
        tmp_path / "s.tif", np.full((20, 40), 50.8), north=Y0 + 20.0
    )

    by_cn = build(tmp_path, dem, rain, curve_number_raster=cn)
    s = read_model_array(tmp_path / "model", "sfincs.scs", "float32")
    assert s == pytest.approx(2.5)  # S = 1000 / 80 - 10 inches
    assert by_cn.infiltration is not None
    assert by_cn.infiltration["curve_number"]["mean"] == pytest.approx(80.0)

    by_s = build(
        tmp_path, dem, rain, retention_mm_raster=retention, output_dir=tmp_path / "m2"
    )
    s = read_model_array(tmp_path / "m2", "sfincs.scs", "float32")
    assert s == pytest.approx(2.0, abs=1e-5)  # 50.8 mm is 2 inches
    assert by_s.infiltration is not None
    assert by_s.infiltration["curve_number"]["mean"] == pytest.approx(
        25400.0 / 304.8, rel=1e-4
    )
    assert "scsfile" in read_inp(tmp_path / "m2")


def test_cells_without_a_curve_number_are_a_warning_and_get_no_infiltration(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    half = write_raster(tmp_path / "cn.tif", np.full((20, 20), 80.0), north=Y0 + 20.0)

    document = build(tmp_path, dem, rain, curve_number_raster=half)

    s = read_model_array(tmp_path / "model", "sfincs.scs", "float32")
    assert s[:, :4] == pytest.approx(2.5)
    assert np.all(s[:, 4:] == 0.0)
    assert document.infiltration is not None
    assert document.infiltration["gap_cells"] == 16
    warning = next(n for n in document.notices if n["code"] == "cn_gaps")
    assert warning["level"] == "warning" and "16 cells" in warning["message"]


def test_a_model_without_infiltration_says_so(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    document = build(tmp_path, dem, rain)

    assert document.infiltration is None
    assert not (tmp_path / "model" / "sfincs.scs").exists()
    assert "no_infiltration" in [n["code"] for n in document.notices]


def test_a_negative_retention_or_a_raster_beside_the_domain_is_an_error(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    negative = write_raster(
        tmp_path / "s.tif", np.full((20, 40), -1.0), north=Y0 + 20.0
    )
    elsewhere = write_raster(
        tmp_path / "cn.tif", np.full((5, 5), 80.0), west=X0 + 1000.0, north=Y0 + 1005.0
    )

    assert (
        reason_of(lambda: build(tmp_path, dem, rain, retention_mm_raster=negative))
        == "invalid_retention"
    )
    assert (
        reason_of(lambda: build(tmp_path, dem, rain, curve_number_raster=elsewhere))
        == "cn_gaps"
    )


def test_the_run_lasts_the_rain_plus_the_recession(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    document = build(tmp_path, dem, rain, recession_min=30.0)

    inp = read_inp(tmp_path / "model")
    assert inp["tstop"] == "20000101 013000" and inp["dtout"] == "5400.0"
    assert document.rain["tstop_s"] == 5400.0
    assert document.rain["total_mm"] == 30.0
    assert precip_depth_mm(tmp_path / "model" / "sfincs.precip") == pytest.approx(
        30.0, abs=0.01
    )
    default = build(tmp_path, dem, rain, output_dir=tmp_path / "m2")
    assert default.rain["recession_min"] == 60.0 and default.rain["tstop_s"] == 7200.0


def test_an_outlet_on_the_edge_makes_outflow_cells_and_none_closes_the_boundary(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    south = write_vector(
        tmp_path / "outlet.gpkg", LineString([(X0, Y0 + 0.5), (X0 + 40, Y0 + 0.5)])
    )

    closed = build(tmp_path, dem, rain)
    open_ = build(tmp_path, dem, rain, outlet=south, output_dir=tmp_path / "m2")

    assert closed.outlet is None and closed.grid["outflow_cells"] == 0
    assert "closed_boundary" in [n["code"] for n in closed.notices]
    assert open_.outlet is not None and open_.grid["outflow_cells"] == 8
    mask = read_model_array(tmp_path / "m2", "sfincs.msk", "int8")
    assert (mask[0] == 3).all() and (mask[1:] == 1).all()
    assert "closed_boundary" not in [n["code"] for n in open_.notices]


def test_an_outlet_inside_or_outside_the_domain_is_refused(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    inside = write_vector(tmp_path / "in.gpkg", Point(X0 + 22.5, Y0 + 10.5))
    outside = write_vector(tmp_path / "out.gpkg", Point(X0 + 5000.0, Y0 + 5000.0))

    assert (
        reason_of(lambda: build(tmp_path, dem, rain, outlet=inside))
        == "outlet_not_on_edge"
    )
    assert (
        reason_of(lambda: build(tmp_path, dem, rain, outlet=outside))
        == "outlet_outside_domain"
    )


def test_stations_are_written_with_their_names_and_must_lie_in_the_domain(
    tmp_path: Path, rain: Path
) -> None:
    values = plane()
    values[:, 10:20] = np.nan
    dem = write_raster(tmp_path / "dem.tif", values, north=Y0 + 20.0)
    good = tmp_path / "good.csv"
    good.write_text(
        f"name,x_m,y_m\nlow,{X0 + 2.5},{Y0 + 2.5}\nhigh,{X0 + 37.5},{Y0 + 17.5}\n"
    )
    bad = tmp_path / "bad.csv"
    bad.write_text(f"name,x_m,y_m\nhole,{X0 + 12.5},{Y0 + 2.5}\n")

    document = build(tmp_path, dem, rain, observation_points=good)

    text = (tmp_path / "model" / "sfincs.obs").read_text()
    assert text.splitlines()[0] == f'{X0 + 2.5:.3f} {Y0 + 2.5:.3f} "low"'
    assert [p["name"] for p in document.observation_points] == ["low", "high"]
    assert "obsfile" in read_inp(tmp_path / "model")
    assert (
        reason_of(
            lambda: build(
                tmp_path, dem, rain, observation_points=bad, output_dir=tmp_path / "m2"
            )
        )
        == "station_outside_domain"
    )


def test_the_files_of_the_result_are_exactly_the_files_that_were_planned(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    cn = write_raster(tmp_path / "cn.tif", np.full((20, 40), 80.0), north=Y0 + 20.0)
    n = write_raster(tmp_path / "n.tif", np.full((20, 40), 0.03), north=Y0 + 20.0)
    stations = tmp_path / "s.csv"
    stations.write_text(f"name,x_m,y_m\nlow,{X0 + 2.5},{Y0 + 2.5}\n")

    plan = build_model(
        dem=[dem],
        dx_m=5.0,
        rain=rain,
        manning_raster=n,
        curve_number_raster=cn,
        observation_points=stations,
        output_dir=tmp_path / "model",
        check=True,
    )
    document = build(
        tmp_path,
        dem,
        rain,
        manning_raster=n,
        curve_number_raster=cn,
        observation_points=stations,
    )

    assert isinstance(plan, PlanDocument)
    planned = [t["name"] for t in plan.targets]
    written = [Path(f["path"]).name for f in document.files]
    assert (
        sorted(planned)
        == sorted(written)
        == sorted(p.name for p in (tmp_path / "model").iterdir())
    )
    assert len(planned) == 8


def test_check_plans_the_grid_and_writes_nothing(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    plan = build_model(
        dem=[dem], dx_m=5.0, rain=rain, output_dir=tmp_path / "model", check=True
    )

    assert isinstance(plan, PlanDocument)
    assert "a grid of 8 x 4 cells of 5 m in EPSG:2180" in plan.steps[0]
    assert [t["action"] for t in plan.targets] == ["write"] * 5
    assert plan.blockers == [] and plan.conflicts == []
    assert not (tmp_path / "model").exists()


def test_check_names_the_missing_extra_and_a_real_run_refuses(
    tmp_path: Path, dem: Path, rain: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "hydraulik.operations._support.extra_found", lambda module: module != "rasterio"
    )

    plan = build_model(
        dem=[dem], dx_m=5.0, rain=rain, output_dir=tmp_path / "model", check=True
    )

    assert isinstance(plan, PlanDocument)
    assert [b["reason"] for b in plan.blockers] == ["extra_missing"]
    assert not any("in EPSG:" in step for step in plan.steps)  # no grid was read
    with pytest.raises(MissingDependencyError) as caught:
        build(tmp_path, dem, rain)
    assert caught.value.details["extras"] == ["model"]


def test_existing_files_are_a_conflict_until_force_replaces_them(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    build(tmp_path, dem, rain)

    with pytest.raises(ConflictError) as caught:
        build(tmp_path, dem, rain)
    replaced = build(tmp_path, dem, rain, force=True)

    assert caught.value.details["reason"] == "output_exists"
    assert len(caught.value.details["paths"]) == 5
    assert {f["status"] for f in replaced.files} == {"replaced"}


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        (
            {"bbox": [0, 0, 1, 1], "crs": "EPSG:2180", "geometry": "a.gpkg"},
            "exclusive_options",
        ),
        ({"bbox": [0, 0, 1, 1]}, "missing_option"),
        ({"crs": "EPSG:2180"}, "option_not_applicable"),
        ({"layer": "x"}, "option_not_applicable"),
        ({"outlet_layer": "x"}, "option_not_applicable"),
        ({"manning": 0.03, "manning_raster": "n.tif"}, "exclusive_options"),
        (
            {"curve_number_raster": "cn.tif", "retention_mm_raster": "s.tif"},
            "exclusive_options",
        ),
        ({"bbox": [0, 0, 1], "crs": "EPSG:2180"}, "invalid_bbox"),
        ({"recession_min": -1.0}, "out_of_range"),
        ({"hsg": "s.tif"}, "option_not_applicable"),
        ({"default_hsg": "C"}, "option_not_applicable"),
        ({"classes": "c.csv"}, "option_not_applicable"),
        ({"building_raise_m": 2.0}, "option_not_applicable"),
        ({"landcover": "b.gpkg", "manning": 0.03}, "exclusive_options"),
        ({"landcover": "b.gpkg", "manning_raster": "n.tif"}, "exclusive_options"),
        (
            {"landcover": "b.gpkg", "hsg": "s.tif", "curve_number_raster": "cn.tif"},
            "exclusive_options",
        ),
        (
            {
                "landcover": "b.gpkg",
                "default_hsg": "C",
                "retention_mm_raster": "s.tif",
            },
            "exclusive_options",
        ),
        ({"landcover": "b.gpkg", "default_hsg": "E"}, "not_allowed"),
        ({"landcover": "b.gpkg", "building_raise_m": -1.0}, "out_of_range"),
    ],
)
def test_options_that_do_not_go_together_are_refused_before_a_file_is_read(
    tmp_path: Path, options: dict[str, Any], reason: str
) -> None:
    def call() -> object:
        return build_model(
            dem=["missing.tif"],
            dx_m=5.0,
            rain="rain.csv",
            output_dir=tmp_path / "model",
            **options,
        )

    with pytest.raises(InvalidInputError) as caught:
        call()

    assert caught.value.details["reason"] == reason


def test_a_rectangle_with_inverted_corners_and_a_grid_too_large_are_refused(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    inverted = reason_of(
        lambda: build(
            tmp_path, dem, rain, bbox=[X0 + 10, Y0, X0, Y0 + 5], crs="EPSG:2180"
        )
    )
    huge = reason_of(
        lambda: build(
            tmp_path, dem, rain, dx_m=1.0, bbox=[0.0, 0.0, 1e6, 1e6], crs="EPSG:2180"
        )
    )
    bad_crs = reason_of(
        lambda: build(tmp_path, dem, rain, bbox=[0.0, 0.0, 1.0, 1.0], crs="not a crs")
    )

    assert (inverted, huge, bad_crs) == (
        "invalid_bbox",
        "grid_too_large",
        "invalid_crs",
    )


def test_a_bbox_and_a_polygon_exclude_each_other_in_the_catalog_too(
    tmp_path: Path, dem: Path, rain: Path
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        run_command(
            "model build",
            dem=[str(dem)],
            dx_m=5.0,
            rain=str(rain),
            output_dir=str(tmp_path / "m"),
            bbox=[X0, Y0, X0 + 5, Y0 + 5],
            crs="EPSG:2180",
            geometry="a.gpkg",
        )

    assert caught.value.details["reason"] == "exclusive_options"


def test_the_command_line_builds_a_model_and_names_a_missing_file(
    tmp_path: Path, dem: Path, rain: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "model"

    code = main(
        [
            "model",
            "build",
            "--dem",
            str(dem),
            "--dx-m",
            "5",
            "--rain",
            str(rain),
            "--output-dir",
            str(out),
            "--json",
        ]
    )

    envelope = json.loads(capsys.readouterr().out)
    assert code == 0 and envelope["status"] == "ok"
    assert envelope["result"]["schema"] == "hydraulik-model/1"
    assert envelope["result"]["grid"]["rows"] == 4
    assert {n["code"] for n in envelope["notices"]} == {
        "manning_default",
        "no_infiltration",
        "closed_boundary",
    }

    code = main(
        [
            "model",
            "build",
            "--dem",
            str(tmp_path / "gone.tif"),
            "--dx-m",
            "5",
            "--rain",
            str(rain),
            "--output-dir",
            str(tmp_path / "other"),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert code == 3 and captured.out == ""
    error = json.loads(captured.err.strip().splitlines()[-1])
    assert error["code"] == "not_found" and error["details"]["reason"] == "path_missing"
    with pytest.raises(NotFoundError):
        build(tmp_path, tmp_path / "gone.tif", rain)
