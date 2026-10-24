"""Oscillation, held maxima and sustained spills of coupled runs."""

import numpy as np
import pytest

from hydraulik.coupling.balance import coupled_balance
from hydraulik.coupling.diagnostics import (
    held_maximum,
    is_numerical_spike,
    sign_flips,
    sustained_spill,
    window_statistics,
)


def test_sign_flips_ignore_values_near_zero() -> None:
    assert sign_flips([0.1, -0.1, 0.0, 0.2, 0.3, -0.2]) == 3
    assert sign_flips([1e-9, -1e-9, 1e-9]) == 0
    assert sign_flips([]) == 0
    assert sign_flips([1.0]) == 0


def test_window_statistics_of_a_steady_state_have_no_spread() -> None:
    t = np.arange(1, 601)
    stats = window_statistics(t, np.full(600, 0.034), end_s=600, length_s=300)

    assert stats.mean == pytest.approx(0.034)
    assert stats.std == 0.0
    assert stats.sign_flips == 0
    assert stats.drift == pytest.approx(0.0)


def test_window_statistics_see_a_limit_cycle() -> None:
    t = np.arange(1, 301)
    q = np.where(t % 2 == 0, 0.2, -0.2)

    stats = window_statistics(t, q, end_s=300, length_s=300)

    assert stats.sign_flips == 299
    assert stats.std == pytest.approx(0.2)


def test_window_statistics_refuse_an_empty_window() -> None:
    with pytest.raises(ValueError, match="no value"):
        window_statistics([1, 2], [1.0, 2.0], end_s=100, length_s=10)


def test_a_one_second_spike_does_not_raise_the_held_maximum() -> None:
    t = np.arange(60, dtype=float)
    head = np.full(60, 30.0)
    head[20] = 31.4

    assert held_maximum(t, head, hold_s=10.0) == 30.0
    assert is_numerical_spike(head.max(), held_maximum(t, head, 10.0))


def test_a_plateau_as_long_as_the_hold_time_is_kept() -> None:
    t = np.arange(60, dtype=float)
    head = np.full(60, 30.0)
    head[20:35] = 31.0

    assert held_maximum(t, head, hold_s=10.0) == 31.0
    assert not is_numerical_spike(head.max(), held_maximum(t, head, 10.0))


def test_held_maximum_does_not_depend_on_the_length_of_the_record() -> None:
    # A percentile would: README 7.1 (one measured peak, p99 = 0.054, 0.039, 0.005).
    peak = np.zeros(600)
    peak[100:130] = 0.053
    short = held_maximum(np.arange(600.0), peak, 10.0)
    long = held_maximum(
        np.arange(21600.0), np.concatenate([peak, np.zeros(21000)]), 10.0
    )

    assert short == long == pytest.approx(0.053)


def test_held_maximum_of_a_record_shorter_than_the_hold_time_is_its_minimum() -> None:
    assert held_maximum([0.0, 1.0, 2.0], [3.0, 1.0, 2.0], hold_s=10.0) == 1.0


def test_held_maximum_refuses_an_empty_or_ragged_series() -> None:
    with pytest.raises(ValueError):
        held_maximum([], [], 10.0)
    with pytest.raises(ValueError):
        held_maximum([0.0, 1.0], [1.0], 10.0)


def test_a_long_spill_is_sustained_and_a_short_one_is_not() -> None:
    t = list(range(1, 21))

    real = sustained_spill(t, [0.0] * 5 + [2.0] * 12 + [0.0] * 3)
    false = sustained_spill(t, [0.0] * 5 + [0.05] * 2 + [0.0] * 13)

    assert real.sustained and real.longest_s == 12.0
    assert real.sustained_m3 == pytest.approx(24.0)
    assert not false.sustained
    assert false.total_m3 == pytest.approx(0.1)
    assert false.sustained_m3 == 0.0


def test_a_long_trickle_below_the_volume_threshold_is_not_a_spill() -> None:
    t = list(range(1, 31))

    summary = sustained_spill(t, [0.001] * 30, min_duration_s=10, min_volume_m3=1.0)

    assert summary.longest_s == 30.0
    assert not summary.sustained


def test_no_spill_in_an_empty_series() -> None:
    assert not sustained_spill([], []).sustained


def test_balance_closes_when_every_volume_is_booked() -> None:
    balance = coupled_balance(
        rain_m3=100.0,
        inflow_m3=0.0,
        surface_m3=60.0,
        network_m3=10.0,
        outfall_net_m3=30.0,
        exchanged_m3=40.0,
    )

    assert balance.total_error_m3 == 0.0
    assert balance.surface_side_error_m3 == 0.0
    assert balance.network_side_error_m3 == 0.0
    assert not balance.flagged


def test_balance_separates_the_surface_error_from_the_network_error() -> None:
    balance = coupled_balance(
        rain_m3=100.0,
        inflow_m3=0.0,
        surface_m3=59.9,
        network_m3=10.0,
        outfall_net_m3=27.0,
        exchanged_m3=40.0,
        sink_m3=0.0,
    )

    assert balance.surface_side_error_m3 == pytest.approx(0.1)
    assert balance.network_side_error_m3 == pytest.approx(3.0)
    assert balance.total_error_m3 == pytest.approx(3.1)
    assert balance.flagged


def test_balance_counts_backwater_and_pending_spill() -> None:
    balance = coupled_balance(
        rain_m3=100.0,
        inflow_m3=0.0,
        surface_m3=250.0,
        network_m3=5.0,
        outfall_net_m3=-160.0,
        exchanged_m3=-195.0,
        outfall_gross_inflow_m3=200.0,
        pending_m3=5.0,
    )

    assert balance.total_error_m3 == pytest.approx(0.0)
    assert balance.total_error_percent == 0.0
