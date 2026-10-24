"""The continuous exchange law between a surface cell and a sewer node."""

import math

import pytest

from hydraulik.coupling.laws import (
    Inlet,
    exchange_discharge_m3s,
    limit_to_available_water,
    orifice_discharge_m3s,
    relax,
)

INLET = Inlet()
GROUND = 10.0


def test_perimeter_is_that_of_a_circle_of_the_node_area() -> None:
    assert INLET.perimeter_m == pytest.approx(2 * math.sqrt(math.pi * 1.167))
    assert Inlet(area_m2=4.0).perimeter_m == pytest.approx(2 * math.sqrt(4 * math.pi))


def test_free_weir_at_ten_centimetres_matches_the_hand_calculation() -> None:
    # 2/3 * 0.54 * P * 0.1**1.5 * sqrt(2 * 9.81) with P = 3.8296 m, by hand 0.1931
    q = exchange_discharge_m3s(INLET, zs_m=GROUND + 0.1, ground_m=GROUND, head_m=0.0)

    assert q == pytest.approx(0.1931, abs=2e-4)


def test_free_weir_discharge_grows_with_depth_to_the_power_one_and_a_half() -> None:
    q1 = exchange_discharge_m3s(INLET, GROUND + 0.05, GROUND, head_m=0.0)
    q2 = exchange_discharge_m3s(INLET, GROUND + 0.10, GROUND, head_m=0.0)

    assert q2 / q1 == pytest.approx(2**1.5)


def test_orifice_caps_the_weir_at_larger_depth() -> None:
    q = exchange_discharge_m3s(INLET, GROUND + 1.0, GROUND, head_m=0.0)

    assert q == pytest.approx(orifice_discharge_m3s(INLET, 1.0))


def test_dry_cell_and_equal_levels_exchange_nothing() -> None:
    assert exchange_discharge_m3s(INLET, GROUND, GROUND, head_m=5.0) == 0.0
    assert exchange_discharge_m3s(INLET, GROUND - 0.1, GROUND, head_m=0.0) == 0.0
    assert exchange_discharge_m3s(INLET, 10.5, GROUND, head_m=10.5) == 0.0


def test_a_node_above_the_surface_spills_by_the_orifice_law() -> None:
    q = exchange_discharge_m3s(INLET, zs_m=10.1, ground_m=GROUND, head_m=10.4)

    assert q < 0
    assert q == pytest.approx(-orifice_discharge_m3s(INLET, 0.3))


def test_discharge_has_no_jump_where_the_head_crosses_the_rim() -> None:
    zs = GROUND + 0.05
    below = exchange_discharge_m3s(INLET, zs, GROUND, head_m=GROUND - 1e-6)
    above = exchange_discharge_m3s(INLET, zs, GROUND, head_m=GROUND + 1e-6)

    assert above == pytest.approx(below, rel=1e-3)


def test_discharge_has_no_jump_where_the_head_reaches_the_surface() -> None:
    zs = GROUND + 0.05
    inflow = exchange_discharge_m3s(INLET, zs, GROUND, head_m=zs - 1e-9)
    spill = exchange_discharge_m3s(INLET, zs, GROUND, head_m=zs + 1e-9)

    assert abs(inflow) < 1e-3
    assert abs(spill) < 1e-3


def test_discharge_falls_as_the_node_head_rises() -> None:
    zs = GROUND + 0.2
    heads = [GROUND - 1, GROUND, GROUND + 0.05, GROUND + 0.15, zs, zs + 0.1]
    values = [exchange_discharge_m3s(INLET, zs, GROUND, h) for h in heads]

    assert values == sorted(values, reverse=True)


def test_orifice_is_linear_below_one_centimetre_and_symmetric() -> None:
    small = orifice_discharge_m3s(INLET, 0.005)
    half = orifice_discharge_m3s(INLET, 0.0025)

    assert small == pytest.approx(2 * half)
    assert orifice_discharge_m3s(INLET, -0.3) == orifice_discharge_m3s(INLET, 0.3)
    assert orifice_discharge_m3s(INLET, 0.01) == pytest.approx(
        orifice_discharge_m3s(INLET, 0.0100001), rel=1e-3
    )


def test_scaled_inlet_changes_the_coefficients_and_not_the_area() -> None:
    scaled = INLET.scaled(0.5)

    assert scaled.area_m2 == INLET.area_m2
    assert exchange_discharge_m3s(scaled, GROUND + 0.1, GROUND, 0.0) == pytest.approx(
        0.5 * exchange_discharge_m3s(INLET, GROUND + 0.1, GROUND, 0.0)
    )


def test_inflow_is_limited_to_the_water_in_the_cell_and_outflow_is_not() -> None:
    assert limit_to_available_water(1.0, 0.01, 4.0, 2.0) == (0.02, True)
    assert limit_to_available_water(0.01, 0.01, 4.0, 2.0) == (0.01, False)
    assert limit_to_available_water(-5.0, 0.0, 4.0, 2.0) == (-5.0, False)
    assert limit_to_available_water(1.0, 0.0, 4.0, 2.0) == (0.0, True)


def test_relaxation_blends_the_previous_and_the_new_discharge() -> None:
    assert relax(1.0, 0.0, 0.1) == pytest.approx(0.1)
    assert relax(1.0, 0.5, 1.0) == 1.0
    assert relax(0.4, 0.4, 0.3) == pytest.approx(0.4)
