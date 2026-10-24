"""Domain documents validate against the schemas shipped in the package (AGI-4.1)."""

import json
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from hydraulik import (
    build_model,
    build_rainfall,
    render_guide,
    run_network,
    show_config,
)
from hydraulik.catalog.commands import COMMANDS
from hydraulik.documents import PlanDocument
from hydraulik.output import plan_directory

SCHEMAS = resources.files("hydraulik").joinpath("schemas")


def _schema(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        SCHEMAS.joinpath(f"{name}.schema.json").read_text(encoding="utf-8")
    )
    return document


def _names() -> list[str]:
    return sorted(
        item.name.removesuffix(".schema.json")
        for item in SCHEMAS.iterdir()
        if item.name.endswith(".schema.json")
    )


@pytest.mark.parametrize("name", _names())
def test_schema_is_a_valid_json_schema_whose_title_matches_its_file(name: str) -> None:
    schema = _schema(name)

    Draft202012Validator.check_schema(schema)
    assert schema["title"].replace("/", "-") == name


def test_every_result_schema_of_the_catalog_has_a_file_or_is_vendored() -> None:
    vendored = {"hydraulik-commands/1"}  # commands-1 of Nogat, AGI-4.1

    for command in COMMANDS:
        schema = command.result_schema
        assert schema in vendored or schema.replace("/", "-") in _names(), schema


def test_config_document_validates() -> None:
    Draft202012Validator(_schema("hydraulik-config-1")).validate(
        show_config().to_dict()
    )


@pytest.mark.parametrize("fmt", ["agents", "llms", "agents-md-block"])
def test_guide_document_validates(fmt: str) -> None:
    document = render_guide(format=fmt).to_dict()  # type: ignore[arg-type]

    Draft202012Validator(_schema("hydraulik-guide-1")).validate(document)


def test_plan_document_validates_with_and_without_conflicts(tmp_path: Any) -> None:
    (tmp_path / "a.json").write_text("x", encoding="utf-8")
    for names in (["b.json"], ["a.json"]):
        plan = PlanDocument.from_write_plan(plan_directory(tmp_path, names))

        Draft202012Validator(_schema("hydraulik-plan-1")).validate(plan.to_dict())


def test_rain_document_validates_for_a_given_and_a_pmaxtp_depth(tmp_path: Any) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "rain"
    validator = Draft202012Validator(_schema("hydraulik-rain-1"))
    given = build_rainfall(
        hietogram_type="beta",
        total_mm=30.0,
        duration_min=60.0,
        output=tmp_path / "a.csv",
    )
    pmaxtp = build_rainfall(
        hietogram_type="block",
        pmaxtp=fixture / "pmaxtp_fetch.json",
        probability_percent=10,
        duration_min=60.0,
        output=tmp_path / "b.csv",
    )
    converted = build_rainfall(
        hietogram=fixture / "hietogram_euler_ii.json", output=tmp_path / "c.csv"
    )

    for document in (given, pmaxtp, converted):
        validator.validate(document.to_dict())


def test_swmm_document_validates(tmp_path: Any) -> None:
    pytest.importorskip("pyswmm")
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "swmm"
    (tmp_path / "q.csv").write_text(
        "time_min,discharge_m3s\n0,0.02\n3,0.02\n", encoding="utf-8"
    )

    document = run_network(
        network=fixture / "network_chain.csv",
        inflow=tmp_path / "q.csv",
        inflow_node="J1",
        output_dir=tmp_path / "swmm",
    )

    Draft202012Validator(_schema("hydraulik-swmm-1")).validate(document.to_dict())


def test_model_document_validates_with_every_optional_input(tmp_path: Any) -> None:
    pytest.importorskip("rasterio")
    pytest.importorskip("geopandas")
    import numpy as np
    from shapely.geometry import LineString

    from ..synthetic import write_raster, write_vector

    ground = write_raster(
        tmp_path / "dem.tif", np.full((20, 40), 5.0), west=362000.0, north=504020.0
    )
    cn = write_raster(
        tmp_path / "cn.tif", np.full((20, 20), 80.0), west=362000.0, north=504020.0
    )
    outlet = write_vector(
        tmp_path / "outlet.gpkg",
        LineString([(362000.0, 504000.5), (362040.0, 504000.5)]),
    )
    stations = tmp_path / "stations.csv"
    stations.write_text("name,x_m,y_m\nlow,362002.5,504002.5\n", encoding="utf-8")
    rain = tmp_path / "rain.csv"
    rain.write_text("time_min,depth_mm\n5,1.0\n10,2.0\n", encoding="utf-8")
    validator = Draft202012Validator(_schema("hydraulik-model-1"))

    minimal = build_model(
        dem=[ground], dx_m=5.0, rain=rain, output_dir=tmp_path / "minimal"
    )
    full = build_model(
        dem=[ground],
        dx_m=5.0,
        rain=rain,
        curve_number_raster=cn,
        outlet=outlet,
        observation_points=stations,
        bbox=[362000.0, 504000.0, 362040.0, 504020.0],
        crs="EPSG:2180",
        output_dir=tmp_path / "full",
    )

    for document in (minimal, full):
        validator.validate(document.to_dict())
