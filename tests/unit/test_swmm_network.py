"""The SWMM network table, the INP writer, the INP reader and the report parser."""

from pathlib import Path

import pytest

from hydraulik.engines.swmm import inp as inp_module
from hydraulik.engines.swmm.network import (
    Conduit,
    Junction,
    Network,
    Outfall,
    SwmmSettings,
    read_network_table,
    write_inp,
)
from hydraulik.engines.swmm.report import routing_continuity_error_percent
from hydraulik.exceptions import (
    InputDataError,
    InvalidInputError,
    NotFoundError,
    UnsupportedError,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "swmm"
HEADER = "name,x_m,y_m,rim_m,depth_m,to,diameter_m\n"


def _table(tmp_path: Path, body: str, header: str = HEADER) -> Path:
    path = tmp_path / "network.csv"
    path.write_text(header + body, encoding="utf-8")
    return path


def test_chain_table_gives_junctions_conduits_and_one_outfall() -> None:
    network = read_network_table(FIXTURES / "network_chain.csv")

    assert [j.name for j in network.junctions] == ["J1", "J2", "J3"]
    assert [(c.name, c.from_node, c.to_node) for c in network.conduits] == [
        ("C_J1", "J1", "J2"),
        ("C_J2", "J2", "J3"),
        ("C_J3", "J3", "OUT"),
    ]
    assert network.outfall.name == "OUT"
    assert network.outfall.invert_m == pytest.approx(7.0)
    assert network.junctions[0].invert_m == pytest.approx(7.745)
    assert network.exchange_nodes["J2"] == (101.0, 21.0)


def test_conduit_length_defaults_to_the_distance_between_the_nodes() -> None:
    network = read_network_table(FIXTURES / "network_chain.csv")

    assert [c.length_m for c in network.conduits] == [50.0, 50.0, 49.0]


def test_length_and_losses_can_be_given_in_the_table(tmp_path: Path) -> None:
    path = _table(
        tmp_path,
        "J1,0,0,10,2,OUT,0.4,0.02,12.5,0.3,0.8\nOUT,3,4,9,2,,,,,,\n",
        HEADER.strip() + ",roughness,length_m,entry_loss,exit_loss\n",
    )

    conduit = read_network_table(path).conduits[0]

    assert (conduit.length_m, conduit.roughness) == (12.5, 0.02)
    assert (conduit.entry_loss, conduit.exit_loss) == (0.3, 0.8)


@pytest.mark.parametrize(
    ("body", "reason", "column"),
    [
        ("J1,0,0,10,2,J9,0.4\nOUT,3,4,9,2,,\n", "invalid_network_table", "to"),
        ("J1,0,0,ten,2,OUT,0.4\nOUT,3,4,9,2,,\n", "invalid_network_table", "rim_m"),
        ("J1,0,0,10,0,OUT,0.4\nOUT,3,4,9,2,,\n", "invalid_network_table", "depth_m"),
        ("J1,0,0,10,2,OUT,0\nOUT,3,4,9,2,,\n", "invalid_network_table", "diameter_m"),
        ("J1,0,0,10,2,OUT,0.4\nOUT,0,0,9,2,,\n", "invalid_network_table", "length_m"),
        ("J 1,0,0,10,2,OUT,0.4\nOUT,3,4,9,2,,\n", "invalid_network_table", "name"),
    ],
)
def test_invalid_rows_name_the_row_and_the_column(
    tmp_path: Path, body: str, reason: str, column: str
) -> None:
    with pytest.raises(InputDataError) as caught:
        read_network_table(_table(tmp_path, body))

    assert caught.value.details["reason"] == reason
    assert caught.value.details["column"] == column
    assert caught.value.details["row"] in (2, 3)


def test_the_table_needs_exactly_one_outfall(tmp_path: Path) -> None:
    with pytest.raises(InputDataError, match="exactly one outfall"):
        read_network_table(_table(tmp_path, "J1,0,0,10,2,J2,0.4\nJ2,3,4,9,2,J1,0.4\n"))


def test_missing_column_and_missing_file_are_reported(tmp_path: Path) -> None:
    with pytest.raises(InputDataError) as caught:
        read_network_table(_table(tmp_path, "J1,0,0\n", "name,x_m,y_m\n"))
    assert "rim_m" in caught.value.details["missing"]

    with pytest.raises(NotFoundError):
        read_network_table(tmp_path / "none.csv")


def test_network_refuses_duplicate_nodes_and_unknown_conduit_ends() -> None:
    junction = Junction("J1", 0, 0, 10, 2)
    outfall = Outfall("OUT", 1, 0, 8)

    with pytest.raises(InputDataError) as dup:
        Network((junction, junction), (), outfall)
    with pytest.raises(InputDataError) as unknown:
        Network((junction,), (Conduit("C", "J1", "NOPE", 1, 0.5),), outfall)

    assert dup.value.details["reason"] == "duplicate_node"
    assert unknown.value.details["node"] == "NOPE"


def test_inp_has_the_settings_found_stable_in_the_experiment() -> None:
    network = read_network_table(FIXTURES / "network_chain.csv")

    text = write_inp(network, SwmmSettings(duration_s=3600.0))
    parsed = inp_module.options(text)

    assert parsed["FLOW_ROUTING"] == "DYNWAVE"
    assert parsed["SURCHARGE_METHOD"] == "EXTRAN"
    assert parsed["ROUTING_STEP"] == "0.5"
    assert parsed["VARIABLE_STEP"] == "0"
    assert parsed["MIN_SURFAREA"] == "1.167"
    assert (parsed["END_DATE"], parsed["END_TIME"]) == ("01/01/2000", "01:00:00")
    assert inp_module.coordinates(text)["OUT"] == (200.0, 21.0)


def test_flooding_mode_lets_swmm_flood_and_coordinator_mode_never() -> None:
    network = read_network_table(FIXTURES / "network_chain.csv")

    flooding = write_inp(network, SwmmSettings(60.0, spill="swmm_flooding"))
    coordinator = write_inp(network, SwmmSettings(60.0, spill="coordinator"))

    assert {j.surcharge_depth_m for j in inp_module.junctions(flooding)} == {0.0}
    assert {j.surcharge_depth_m for j in inp_module.junctions(coordinator)} == {100.0}


def test_local_losses_are_written_with_non_zero_defaults() -> None:
    network = read_network_table(FIXTURES / "network_chain.csv")

    losses = inp_module.sections(write_inp(network, SwmmSettings(60.0)))["LOSSES"]

    assert [" ".join(line.split()) for line in losses] == [
        f"C_J{i} 0.5 1 0 NO 0" for i in (1, 2, 3)
    ]


def test_backwater_stage_series_and_flap_gate_are_written() -> None:
    outfall = Outfall("OUT", 5, 0, 8, ((0.0, 7.0), (1800.0, 7.0), (2700.0, 9.6)), True)
    network = Network(
        (Junction("J1", 0, 0, 10, 2),), (Conduit("C1", "J1", "OUT", 5, 0.5),), outfall
    )

    sections = inp_module.sections(write_inp(network, SwmmSettings(3600.0)))

    assert [" ".join(line.split()) for line in sections["OUTFALLS"]] == [
        "OUT 8.0000 TIMESERIES STAGE YES"
    ]
    assert sections["TIMESERIES"][-1] == "STAGE 01/01/2000 00:45:00 9.600"


def test_stage_series_must_increase_and_settings_must_be_positive() -> None:
    bad = Outfall("OUT", 5, 0, 8, ((0.0, 7.0), (0.0, 8.0)))
    network = Network(
        (Junction("J1", 0, 0, 10, 2),), (Conduit("C1", "J1", "OUT", 5, 0.5),), bad
    )

    with pytest.raises(InvalidInputError) as caught:
        write_inp(network, SwmmSettings(60.0))
    with pytest.raises(InvalidInputError):
        write_inp(read_network_table(FIXTURES / "network_chain.csv"), SwmmSettings(0))

    assert caught.value.details["reason"] == "invalid_stage_series"


def test_extra_options_replace_the_defaults_of_the_same_name() -> None:
    network = read_network_table(FIXTURES / "network_chain.csv")

    text = write_inp(network, SwmmSettings(60.0), {"HEAD_TOLERANCE": 0.00005})

    assert inp_module.options(text)["HEAD_TOLERANCE"] == "5e-05"


USER_INP = """[TITLE]
user model

[OPTIONS]
FLOW_UNITS           CMS
ROUTING_STEP         30 ; coarse
; a comment
END_TIME             06:00:00

[JUNCTIONS]
;;Name Invert MaxDepth InitDepth SurDepth Aponded
A  5.0 3.0 0 1.5 0
B  4.0 3.0

[COORDINATES]
A 10.0 20.0
B 30.0 40.0
"""


def test_reader_understands_a_user_inp() -> None:
    assert inp_module.options(USER_INP)["ROUTING_STEP"] == "30"
    assert [
        (j.name, j.rim_m, j.surcharge_depth_m) for j in inp_module.junctions(USER_INP)
    ] == [
        ("A", 8.0, 1.5),
        ("B", 7.0, 0.0),
    ]
    assert inp_module.coordinates(USER_INP) == {"A": (10.0, 20.0), "B": (30.0, 40.0)}


def test_patching_options_changes_only_those_lines() -> None:
    patched = inp_module.patch_options(
        USER_INP, {"routing_step": 0.5, "SURCHARGE_METHOD": "EXTRAN"}
    )

    assert inp_module.options(patched)["ROUTING_STEP"] == "0.5"
    assert inp_module.options(patched)["SURCHARGE_METHOD"] == "EXTRAN"
    assert "; a comment" in patched
    assert patched.count("END_TIME") == 1
    assert inp_module.junctions(patched) == inp_module.junctions(USER_INP)


def test_patching_the_surcharge_depth_of_named_junctions() -> None:
    patched = inp_module.patch_junction_surcharge(USER_INP, 0.0, names=["A"])

    assert [j.surcharge_depth_m for j in inp_module.junctions(patched)] == [0.0, 0.0]
    both = inp_module.patch_junction_surcharge(USER_INP, 100.0)
    assert [j.surcharge_depth_m for j in inp_module.junctions(both)] == [100.0, 100.0]


def test_patching_a_file_without_options_is_refused() -> None:
    with pytest.raises(InputDataError):
        inp_module.patch_options("[JUNCTIONS]\nA 1 2\n", {"ROUTING_STEP": 1})


def test_only_metric_flow_units_are_supported() -> None:
    inp_module.require_metric(USER_INP)

    with pytest.raises(UnsupportedError) as caught:
        inp_module.require_metric("[OPTIONS]\nFLOW_UNITS CFS\n")

    assert caught.value.details["reason"] == "flow_units"
    with pytest.raises(UnsupportedError):
        inp_module.require_metric("[OPTIONS]\nROUTING_STEP 1\n")  # SWMM defaults to CFS


def test_malformed_junction_and_coordinate_lines_are_data_errors() -> None:
    with pytest.raises(InputDataError):
        inp_module.junctions("[JUNCTIONS]\nA 1\n")
    with pytest.raises(InputDataError):
        inp_module.junctions("[JUNCTIONS]\nA x 2\n")
    with pytest.raises(InputDataError):
        inp_module.coordinates("[COORDINATES]\nA 1\n")


def test_continuity_error_of_a_real_swmm_report() -> None:
    report = FIXTURES / "report_sample.rpt"

    assert routing_continuity_error_percent(report) == pytest.approx(-4.234)
    assert routing_continuity_error_percent(report.read_text(encoding="utf-8")) == (
        routing_continuity_error_percent(report)
    )


def test_the_last_continuity_error_is_the_flow_routing_one() -> None:
    text = "Continuity Error (%) .....  0.100\nContinuity Error (%) .....  -2.790\n"

    assert routing_continuity_error_percent(text) == -2.79


def test_a_report_without_a_continuity_table_gives_none() -> None:
    assert routing_continuity_error_percent("run aborted") is None
