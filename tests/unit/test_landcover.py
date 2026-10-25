"""The land-cover tables, the painter of BDOT10k classes and the raster helpers."""

import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("geopandas")
pytest.importorskip("rasterio")

import geopandas  # noqa: E402
import rasterio  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import LineString, box  # noqa: E402

from hydraulik.engines.sfincs.model import RegularGrid  # noqa: E402
from hydraulik.exceptions import InputDataError, NotFoundError  # noqa: E402
from hydraulik.model.classes import (  # noqa: E402
    UNCLASSIFIED,
    load_classes,
    load_mapping,
)
from hydraulik.model.landcover import build_landcover, subdivision  # noqa: E402
from hydraulik.terrain.grid import (  # noqa: E402
    NODATA,
    resample_codes,
    write_grid_raster,
)

ROOT = Path(__file__).resolve().parents[2]
GRID = RegularGrid(1000.0, 2000.0, 10.0, 2, 2, 2180)
"""Two by two cells of 10 m: row 0 is the south, column 0 the west."""

# class -> the TR-55 row of Hydrolog's cn_lookup that has the same values
TR55 = {
    "water": ("water", None),
    "forest": ("forest", "good"),
    "shrub": ("brush", "fair"),
    "grass": ("pasture", "fair"),
    "arable": ("row_crops", "poor"),
    "barren": ("fallow", None),
    "built_up_dense": ("residential_high", None),
    "commercial": ("commercial", None),
    "industrial": ("industrial", None),
    "road_paved": ("paved", None),
    "road_gravel": ("gravel", None),
    "road_dirt": ("dirt", None),
    "building": ("paved", None),
}


def test_every_class_of_the_shipped_table_is_valid_and_documented() -> None:
    table = load_classes()

    assert table.source == "shipped" and table.overridden == ()
    assert len(set(table.names)) == len(table.names) and UNCLASSIFIED in table.names
    for item in table.classes:
        assert 0.001 <= item.manning_n <= 1.0
        assert list(item.curve_numbers) == sorted(item.curve_numbers)
        assert item.description and item.manning_basis and item.cn_basis


def test_the_mapping_names_known_classes_and_covers_every_land_cover_layer() -> None:
    table = load_classes()

    mapping = load_mapping(table)

    mapped = {row.class_name for row in mapping}
    assert mapped | {UNCLASSIFIED} == set(table.names)
    # the classes of "pokrycie terenu" in the BDOT10k classification of GUGiK
    for code in [
        "PTWP",
        "PTZB",
        "PTLZ",
        "PTRK",
        "PTUT",
        "PTTR",
        "PTKM",
        "PTGN",
        "PTPL",
        "PTSO",
        "PTWZ",
        "PTNZ",
    ]:
        assert f"OT_{code}_A" in {row.layer for row in mapping}, code
    assert {"OT_SKJZ_L", "OT_BUBD_A"} <= {row.layer for row in mapping}
    for layer in {row.layer for row in mapping}:
        rows = [row for row in mapping if row.layer == layer and row.field]
        for field in {row.field for row in rows}:
            stars = [r for r in rows if r.field == field and r.value == "*"]
            assert len(stars) <= 1


def test_curve_numbers_are_those_of_hydrologs_tr55_table_where_it_has_the_row() -> None:
    cn_lookup = pytest.importorskip("hydrolog.runoff.cn_lookup")
    table = load_classes()

    for name, (cover, condition) in TR55.items():
        item = table.classes[table.index(name)]
        expected = tuple(
            float(cn_lookup.get_cn(group, cover, condition)) for group in "ABCD"
        )
        assert item.curve_numbers == expected, name


def test_the_document_lists_the_values_of_the_shipped_table() -> None:
    text = (ROOT / "docs" / "LAND_COVER.md").read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| `(\w+)` \| ([\d.]+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|", text, re.M
    )
    documented = {r[0]: (float(r[1]), tuple(float(v) for v in r[2:])) for r in rows}

    table = load_classes()

    assert set(documented) == set(table.names)
    for item in table.classes:
        assert documented[item.name] == (item.manning_n, item.curve_numbers), item.name


def test_an_override_replaces_the_values_it_gives_and_keeps_the_others(
    tmp_path: Path,
) -> None:
    path = tmp_path / "classes.csv"
    path.write_text(
        "class,manning_n,cn_b,cn_c\nforest,0.12,50,\ngrass,,,80\n", encoding="utf-8"
    )

    table = load_classes(path)

    forest = table.classes[table.index("forest")]
    grass = table.classes[table.index("grass")]
    shipped = load_classes()
    assert forest.manning_n == 0.12
    assert forest.curve_numbers == (30.0, 50.0, 70.0, 77.0)
    assert grass.manning_n == shipped.classes[shipped.index("grass")].manning_n
    assert grass.curve_numbers == (49.0, 69.0, 80.0, 84.0)
    assert table.source == str(path) and table.overridden == ("forest", "grass")


def test_a_file_saved_by_a_polish_spreadsheet_is_read(tmp_path: Path) -> None:
    path = tmp_path / "klasy.csv"
    path.write_text("\ufeffclass;manning_n;cn_a\nwater;0,045;99\n", encoding="utf-8")

    water = load_classes(path).classes[0]

    assert (water.name, water.manning_n, water.curve_numbers[0]) == (
        "water",
        0.045,
        99.0,
    )


@pytest.mark.parametrize(
    "content",
    [
        "class,manning_n\nlake,0.03\n",
        "class,manning_n\nwater,1.5\n",
        "class,manning_n\nwater,fast\n",
        "class,cn_a\nwater,20\n",
        "class,cn_a,cn_d\nforest,90,80\n",
        "class,colour\nwater,blue\n",
        "class,manning_n\n",
    ],
)
def test_an_override_that_cannot_be_right_is_refused_with_the_reason(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "classes.csv"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(InputDataError) as caught:
        load_classes(path)

    assert caught.value.details["reason"] == "invalid_classes_table"
    assert str(path) in str(caught.value)


def test_an_override_file_that_does_not_exist_is_not_found(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        load_classes(tmp_path / "gone.csv")


def _layer(path: Path, name: str, geometries: list[Any], **columns: Any) -> None:
    frame = geopandas.GeoDataFrame(columns, geometry=geometries, crs="EPSG:2180")
    frame.to_file(path, layer=name, driver="GPKG", mode="a")


@pytest.fixture
def bdot(tmp_path: Path) -> Path:
    """Grass south-west, forest north-west, water east, a road along the south."""
    path = tmp_path / "bdot10k.gpkg"
    _layer(path, "OT_PTWP_A", [box(1010, 2000, 1020, 2020)], RODZAJ=["woda stojąca"])
    _layer(
        path,
        "OT_PTTR_A",
        [box(1000, 2000, 1010, 2010)],
        RODZAJ=["roślinność trawiasta"],
    )
    _layer(path, "OT_PTLZ_A", [box(1000, 2010, 1010, 2020)], RODZAJ=["las"])
    _layer(
        path,
        "OT_SKJZ_L",
        [
            LineString([(1000, 2005), (1020, 2005)]),
            LineString([(1000, 2015), (1010, 2015)]),  # a bridge
            LineString([(1000, 2018), (1010, 2018)]),  # a conventional line
        ],
        MATERIALNAWIERZCHNI=["masa bitumiczna"] * 3,
        SZEROKOSCNAWIERZCHNI=[2.0, 4.0, None],
        POLOZENIE=[
            "na powierzchni gruntu",
            "ponad powierzchnią gruntu poziom 1",
            "na powierzchni gruntu",
        ],
        CECHAGEOMETRII=[None, None, "linia umowna"],
    )
    _layer(path, "OT_BUBD_A", [box(1000, 2010, 1005, 2020)], KODKST=["110"])
    return path


def _paint(path: Path, *, roofs: bool = False, soil: Any = 1) -> Any:
    active = np.ones(GRID.shape, dtype=bool)
    groups = None if soil is None else np.full(GRID.shape, soil, dtype=np.int8)
    return build_landcover(
        path, GRID, active, load_classes(), soil_groups=groups, building_roughness=roofs
    )


def test_each_cell_gets_the_n_and_the_curve_number_of_the_classes_under_it(
    bdot: Path,
) -> None:
    result = _paint(bdot)

    # row 0 is the south: [south-west, south-east], [north-west, north-east]
    np.testing.assert_allclose(
        result.manning,
        [[0.8 * 0.15 + 0.2 * 0.011, 0.8 * 0.035 + 0.2 * 0.011], [0.40, 0.035]],
    )
    np.testing.assert_allclose(
        result.curve_number,
        [[0.8 * 69 + 0.2 * 98, 0.8 * 100 + 0.2 * 98], [0.5 * 55 + 0.5 * 98, 100.0]],
    )
    assert result.building_fraction.tolist() == [[0.0, 0.0], [0.5, 0.0]]
    areas = {item["class"]: item["area_m2"] for item in result.report["classes"]}
    assert areas == pytest.approx(
        {
            "water": 180.0,
            "grass": 80.0,
            "forest": 50.0,
            "building": 50.0,
            "road_paved": 40.0,
        }
    )
    assert sum(areas.values()) == pytest.approx(400.0)
    assert result.report["roads"] == {
        "features": 3,
        "skipped_not_on_ground": 1,
        "skipped_conventional": 1,
        "default_width": 0,
    }
    assert result.report["unclassified_percent"] == 0.0
    assert result.report["painting_cell_m"] == 1.0


def test_the_roughness_of_roofs_counts_only_where_buildings_are_raised(
    bdot: Path,
) -> None:
    kept = _paint(bdot, roofs=False)
    raised = _paint(bdot, roofs=True)

    assert kept.manning[1, 0] == pytest.approx(0.40)  # the ground under the roof
    assert raised.manning[1, 0] == pytest.approx(0.5 * 0.40 + 0.5 * 0.011)
    assert raised.curve_number[1, 0] == kept.curve_number[1, 0]  # a roof sheds water
    assert raised.manning[0, 0] == kept.manning[0, 0]


def test_an_unknown_soil_group_leaves_the_curve_number_of_that_cell_open(
    bdot: Path,
) -> None:
    active = np.ones(GRID.shape, dtype=bool)
    groups = np.array([[1, -1], [3, 0]], dtype=np.int8)  # B, unknown / D, A

    result = build_landcover(
        bdot, GRID, active, load_classes(), soil_groups=groups, building_roughness=False
    )

    cn = result.curve_number
    assert cn is not None
    assert np.isnan(cn[0, 1]) and np.isfinite(result.manning[0, 1])
    assert cn[1, 0] == pytest.approx(0.5 * 77 + 0.5 * 98)  # forest D and roof
    assert cn[1, 1] == 100.0 and cn[0, 0] == pytest.approx(0.8 * 69 + 0.2 * 98)
    assert _paint(bdot, soil=None).curve_number is None


def test_a_road_without_a_width_gets_five_metres(tmp_path: Path) -> None:
    path = tmp_path / "b.gpkg"
    _layer(
        path,
        "OT_PTTR_A",
        [box(1000, 2000, 1020, 2020)],
        RODZAJ=["roślinność trawiasta"],
    )
    _layer(
        path,
        "OT_SKJZ_L",
        [LineString([(1000, 2005.5), (1010, 2005.5)])],
        MATERIALNAWIERZCHNI=["żwir"],
        SZEROKOSCNAWIERZCHNI=[None],
    )

    result = _paint(path)

    assert result.manning[0, 0] == pytest.approx(0.5 * 0.15 + 0.5 * 0.011)
    assert result.curve_number[0, 0] == pytest.approx(0.5 * 69 + 0.5 * 85)  # gravel B
    assert result.report["roads"]["default_width"] == 1


def test_land_that_no_polygon_covers_and_values_the_mapping_lacks_are_reported(
    tmp_path: Path,
) -> None:
    path = tmp_path / "b.gpkg"
    _layer(path, "OT_PTTR_A", [box(1000, 2000, 1020, 2020)], RODZAJ=["inne"])

    result = _paint(path)

    assert result.report["unclassified_percent"] == pytest.approx(100.0)
    np.testing.assert_allclose(result.manning, [[0.15, 0.15], [0.15, 0.15]])
    assert result.report["unmapped"] == [
        {"layer": "OT_PTTR_A", "field": "RODZAJ", "value": "inne", "features": 1}
    ]
    codes = {item["code"]: item["level"] for item in result.notices}
    assert codes["landcover_unclassified"] == "warning"
    assert codes["landcover_unmapped"] == "warning"
    assert codes["landcover_layers_missing"] == "info"


def test_a_file_without_land_cover_layers_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "b.gpkg"
    _layer(path, "OT_BUBD_A", [box(1000, 2000, 1010, 2010)], KODKST=["110"])

    with pytest.raises(InputDataError) as caught:
        _paint(path)
    with pytest.raises(NotFoundError):
        _paint(tmp_path / "gone.gpkg")

    assert caught.value.details["reason"] == "landcover_layers_missing"


def test_the_painting_cell_is_about_a_metre_and_never_finer_than_a_tenth() -> None:
    assert [subdivision(v) for v in (0.5, 1.0, 2.4, 5.0, 25.0)] == [1, 1, 2, 5, 10]


def test_class_codes_are_taken_from_the_nearest_cell_south_up(tmp_path: Path) -> None:
    path = tmp_path / "hsg.tif"
    codes = np.array([[1, 2], [3, 0]], dtype=np.uint8)  # north-up: A B / C no data
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:2180",
        transform=from_origin(1000.0, 2020.0, 10.0, 10.0),
        nodata=0,
    ) as target:
        target.write(codes, 1)

    on_grid = resample_codes(path, GRID)
    finer = resample_codes(path, RegularGrid(1000.0, 2000.0, 5.0, 4, 4, 2180))

    assert on_grid.tolist() == [[3, 0], [1, 2]]  # row 0 is the south
    assert finer.tolist() == [[3, 3, 0, 0], [3, 3, 0, 0], [1, 1, 2, 2], [1, 1, 2, 2]]
    outside = resample_codes(path, RegularGrid(5000.0, 2000.0, 10.0, 2, 2, 2180))
    assert outside.tolist() == [[0, 0], [0, 0]] and outside.dtype == np.uint8


def test_an_array_on_the_grid_is_written_north_up_with_no_data_where_not_finite(
    tmp_path: Path,
) -> None:
    path = tmp_path / "n.tif"
    values = np.array([[0.1, np.nan], [0.3, 0.4]])  # row 0 is the south

    write_grid_raster(path, GRID, values, tags={"variable": "manning_n"})

    with rasterio.open(path) as source:
        written = source.read(1)
        assert source.crs.to_epsg() == 2180 and source.nodata == NODATA
        assert source.bounds.left == 1000.0 and source.bounds.top == 2020.0
        assert source.tags()["variable"] == "manning_n"
    np.testing.assert_allclose(written, [[0.3, 0.4], [0.1, NODATA]], rtol=1e-6)
