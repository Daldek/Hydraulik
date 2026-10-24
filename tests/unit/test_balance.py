"""The coupled balance books infiltration and flooding that has no cell to return to."""

import pytest

from hydraulik.coupling.balance import coupled_balance


def test_every_term_closes_the_books_and_a_missing_one_shows_on_its_side() -> None:
    terms = {
        "rain_m3": 100.0,
        "inflow_m3": 0.0,
        "infiltration_m3": 10.0,
        "surface_m3": 50.0,  # 100 - 10 - 50 = 40 m3 went to the network
        "network_m3": 10.0,
        "outfall_net_m3": 20.0,
        "exchanged_m3": 40.0,
        "pending_m3": 4.0,  # spilled, not yet back on the street
        "lost_flooding_m3": 6.0,  # flooded out of nodes that have no cell
    }

    closed = coupled_balance(**terms)
    forgotten = coupled_balance(**{**terms, "lost_flooding_m3": 0.0})

    assert closed.total_error_m3 == pytest.approx(0.0)
    assert closed.surface_side_error_m3 == pytest.approx(0.0)
    assert closed.network_side_error_m3 == pytest.approx(0.0)
    assert not closed.flagged
    # the error is on the network side, SWMM's, and the surface side still closes
    assert forgotten.surface_side_error_m3 == pytest.approx(0.0)
    assert forgotten.network_side_error_m3 == pytest.approx(6.0)
    assert forgotten.total_error_percent == pytest.approx(6.0) and forgotten.flagged
