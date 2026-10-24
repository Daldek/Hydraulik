"""The coupling loop on fakes: mass, the cap on a cell's water, both modes, refusals."""

import pytest

from hydraulik.coupling.balance import CoupledBalance, coupled_balance
from hydraulik.coupling.coupler import (
    CouplerResult,
    CouplerSettings,
    ExchangeNode,
    couple,
)
from hydraulik.exceptions import EngineError, InvalidInputError

from ..coupling_fakes import FakeNetwork, FakeSurface

J1 = ExchangeNode("J1", 5.0, 5.0)


def balance_of(
    result: CouplerResult, surface: FakeSurface, initial_m3: float = 0.5
) -> CoupledBalance:
    """Book the run; the tanks held ``initial_m3`` before it, which is not rain."""
    return coupled_balance(
        rain_m3=surface.rain_m3,
        inflow_m3=0.0,
        surface_m3=result.surface_final_m3,
        network_m3=result.network_final_m3 - initial_m3,
        outfall_net_m3=result.outfall_net_m3,
        exchanged_m3=result.exchanged_m3,
        pending_m3=result.pending_m3,
    )


def test_the_interface_adds_no_mass_error_even_when_the_surface_overshoots() -> None:
    surface = FakeSurface([10.0, 10.0], rain_mm_h=600.0, end_s=300.0, step_s=3.0)
    network = FakeNetwork({"J1": 10.0}, initial_m3=0.5, end_s=300.0)

    result = couple(surface, network, [J1], CouplerSettings(interval_s=5))

    balance = balance_of(result, surface)
    node = result.nodes[0]
    assert result.intervals == 60
    assert 0.0 < max(result.overshoot_s) < 3.0  # SFINCS goes beyond its target
    assert abs(balance.total_error_m3) < 1e-6
    assert abs(balance.surface_side_error_m3) < 1e-6
    assert abs(balance.network_side_error_m3) < 1e-6
    assert surface.created_m3 == 0.0
    assert result.exchanged_m3 > 0.0 and node.capped_steps == 0


def test_water_that_swmm_floods_comes_back_to_the_cell_and_is_booked() -> None:
    surface = FakeSurface([10.0], rain_mm_h=600.0, end_s=300.0, step_s=3.0)
    network = FakeNetwork({"J1": 10.0}, initial_m3=0.5, end_s=300.0)

    result = couple(surface, network, [J1], CouplerSettings(interval_s=5))

    node = result.nodes[0]
    assert node.flooded_m3 > 0.0 and node.returned_m3 > 0.0
    assert node.returned_m3 + node.pending_m3 == pytest.approx(node.flooded_m3)
    assert abs(node.pending_m3) < 0.5  # about one interval of flooding
    assert max(node.spill_m3s) > 0.0
    assert abs(balance_of(result, surface).total_error_m3) < 1e-6


def test_a_node_never_takes_more_than_the_water_that_stands_in_its_cell() -> None:
    surface = FakeSurface([10.0], cell_m=1.0, depth_m=0.2, end_s=20.0, step_s=1.0)
    network = FakeNetwork({"J1": 10.0}, initial_m3=0.5, end_s=20.0)
    node_in_cell = ExchangeNode("J1", 0.5, 0.5)  # the cells are 1 m wide

    result = couple(surface, network, [node_in_cell], CouplerSettings(interval_s=5))

    node = result.nodes[0]
    assert node.capped_steps >= 1
    assert node.exchange_m3s[0] <= 0.2 / 6.0 + 1e-12  # depth * area / (dt_c + dtmax)
    assert surface.created_m3 == 0.0  # SFINCS would have created water
    assert result.exchanged_m3 <= 0.2 + 1e-9


def test_nodes_that_share_a_cell_share_what_the_cell_holds() -> None:
    surface = FakeSurface([10.0], cell_m=1.0, depth_m=0.2, end_s=20.0, step_s=1.0)
    network = FakeNetwork({"J1": 10.0, "J2": 10.0}, initial_m3=0.5, end_s=20.0)
    nodes = [ExchangeNode("J1", 0.4, 0.4), ExchangeNode("J2", 0.6, 0.6)]

    result = couple(surface, network, nodes, CouplerSettings(interval_s=5))

    first, second = result.nodes
    assert first.cell == second.cell
    assert surface.created_m3 == 0.0
    assert first.capped_steps >= 1 and second.capped_steps >= 1
    assert first.exchanged_m3 == pytest.approx(second.exchanged_m3)
    assert result.exchanged_m3 <= 0.2 + 1e-9


def test_the_coordinator_spills_a_full_node_through_the_exchange_law() -> None:
    surface = FakeSurface([10.0], end_s=60.0, step_s=1.0)
    network = FakeNetwork(
        {"J1": 10.0},
        tank_m2=20.0,
        initial_m3=60.0,
        capacity_m3s=0.0,
        flooding=False,
        end_s=60.0,
    )  # the head is 11 m, one metre above the street

    result = couple(
        surface,
        network,
        [J1],
        CouplerSettings(interval_s=5, mode="coordinator", relaxation=0.1),
    )

    node = result.nodes[0]
    assert result.exchanged_m3 < 0.0  # the network gave water to the surface
    assert min(node.exchange_m3s) < 0.0 and node.returned_m3 == 0.0
    assert result.surface_final_m3 > 0.0
    assert result.surface_final_m3 + result.network_final_m3 == pytest.approx(60.0)
    assert surface.created_m3 == 0.0


def test_a_rim_that_is_not_the_bed_of_the_cell_is_refused_before_any_step() -> None:
    surface = FakeSurface([10.0, 10.0], end_s=60.0)
    network = FakeNetwork({"J1": 10.5, "J2": 10.0}, initial_m3=0.5, end_s=60.0)
    nodes = [J1, ExchangeNode("J2", 15.0, 5.0)]

    with pytest.raises(InvalidInputError) as caught:
        couple(surface, network, nodes, CouplerSettings(interval_s=5))

    assert caught.value.details["reason"] == "rim_mismatch"
    assert caught.value.details["nodes"] == [
        {"node": "J1", "rim_m": 10.5, "bed_m": 10.0}
    ]
    assert surface.calls == [] and surface.time == 0.0
    couple(surface, network, nodes, CouplerSettings(interval_s=5, rim_tolerance_m=0.6))
    assert surface.calls  # the same pair runs once the tolerance allows it


def test_nodes_off_the_domain_exchange_nothing_and_without_any_the_run_is_refused() -> (
    None
):
    network = FakeNetwork({"J1": 10.0}, initial_m3=0.5, end_s=30.0)
    surface = FakeSurface([10.0], end_s=30.0)
    nodes = [J1, ExchangeNode("J9", 500.0, 5.0)]

    result = couple(surface, network, nodes, CouplerSettings(interval_s=5))

    assert result.outside == ["J9"] and [n.name for n in result.nodes] == ["J1"]
    with pytest.raises(InvalidInputError) as caught:
        couple(
            FakeSurface([10.0], end_s=30.0),
            network,
            [ExchangeNode("J9", 500.0, 5.0)],
            CouplerSettings(interval_s=5),
        )
    assert caught.value.details["reason"] == "no_exchange_nodes"


def test_the_last_interval_is_shorter_when_the_run_is_not_a_multiple() -> None:
    surface = FakeSurface([10.0], rain_mm_h=600.0, end_s=12.0, step_s=1.0)
    network = FakeNetwork({"J1": 10.0}, initial_m3=0.5, end_s=12.0)

    result = couple(surface, network, [J1], CouplerSettings(interval_s=5))

    assert result.times_s == [5.0, 10.0, 12.0]
    assert network.time_s == 12.0
    assert abs(balance_of(result, surface).total_error_m3) < 1e-9


@pytest.mark.parametrize(
    ("settings", "stride"),
    [
        (CouplerSettings(interval_s=3), 2),
        (CouplerSettings(interval_s=0), 1),
        (CouplerSettings(interval_s=5, relaxation=0.0), 1),
        (CouplerSettings(interval_s=5, relaxation=1.5), 1),
    ],
)
def test_settings_the_loop_cannot_honour_are_refused(
    settings: CouplerSettings, stride: int
) -> None:
    network = FakeNetwork({"J1": 10.0}, initial_m3=0.5, stride_s=stride)

    with pytest.raises(InvalidInputError) as caught:
        couple(FakeSurface([10.0]), network, [J1], settings)

    assert caught.value.details["reason"] == "out_of_range"


def test_a_network_that_ends_before_the_surface_is_an_error() -> None:
    surface = FakeSurface([10.0], end_s=12.0, step_s=1.0)
    network = FakeNetwork({"J1": 10.0}, initial_m3=0.5, end_s=8.0)

    with pytest.raises(EngineError) as caught:
        couple(surface, network, [J1], CouplerSettings(interval_s=5))

    assert caught.value.details["reason"] == "swmm_time"
