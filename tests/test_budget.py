"""Physics tests: every expected value here is hand-computed or taken from a
published figure, not captured from the implementation.

The point of this file is that a reviewer can check the numbers with a
calculator and a standard, without running the code.
"""

import math

import pytest

from linklab.budget import (
    Optics,
    compute_copper_budget,
    compute_fiber_budget,
    compute_microwave_budget,
)
from linklab.media import COPPER_TYPES, FIBRE_TYPES
from linklab.units import dispersion_penalty_db, fspl_db

# ---------------------------------------------------------------------------
# Free space path loss (radio only)
# ---------------------------------------------------------------------------


def test_fspl_one_km_at_one_ghz_is_the_textbook_92_44():
    # 4*pi*d/lambda at 1 GHz over 1 km gives 92.44 dB. This is the number
    # printed in every propagation table.
    assert fspl_db(1.0, 1.0e9) == pytest.approx(92.44, abs=0.01)


def test_fspl_100m_at_1550nm():
    # 92.44 + 20*log10(0.1) + 20*log10(193100 GHz) = 178.15 dB
    expected = 92.44 + 20 * math.log10(0.1) + 20 * math.log10(193100.0)
    assert fspl_db(0.1, 193.1e12) == pytest.approx(178.15, abs=0.01)
    assert fspl_db(0.1, 193.1e12) == pytest.approx(expected, abs=1e-9)


def test_fspl_scales_with_the_square_of_distance():
    # Doubling the distance adds 6.02 dB.
    one = fspl_db(10.0, 7.0e9)
    two = fspl_db(20.0, 7.0e9)
    assert two - one == pytest.approx(6.0206, abs=0.001)


def test_fspl_rejects_non_positive_inputs():
    with pytest.raises(ValueError):
        fspl_db(0.0, 1e9)
    with pytest.raises(ValueError):
        fspl_db(1.0, 0.0)


# ---------------------------------------------------------------------------
# Chromatic dispersion
# ---------------------------------------------------------------------------


def test_dispersion_penalty_matches_the_standard_two_db_figure():
    # D=17 ps/nm/km, L=100 km, spectral width 0.05 nm -> sigma = 85 ps.
    # At 10 Gb/s the bit period is 100 ps.
    # 10*log10(1 + (85/100)^2) = 2.36 dB, the figure quoted for a
    # 100 km single-mode span at 10 Gb/s.
    sigma = 17.0 * 100.0 * 0.05
    assert sigma == pytest.approx(85.0)
    assert dispersion_penalty_db(sigma, 100.0) == pytest.approx(2.36, abs=0.005)


def test_dispersion_penalty_is_zero_without_broadening():
    assert dispersion_penalty_db(0.0, 100.0) == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Fibre budget
# ---------------------------------------------------------------------------


def test_fibre_budget_has_no_free_space_path_loss_term():
    """Regression guard.

    Free space path loss is a radio-propagation term. Fibre does not suffer
    it, and including it would understate every optical link by more than
    100 dB. The total loss must be exactly attenuation + splices + connectors.
    """
    optics = Optics(
        tx_power_dbm=2.0,
        rx_sensitivity_dbm=-28.0,
        splice_count=3,
        connector_pairs=4,
    )
    b = compute_fiber_budget(12.0, "smf", optics)
    expected = 12.0 * 0.25 + 3 * 0.05 + 4 * 0.50
    assert b.total_loss_db == pytest.approx(expected, abs=1e-9)
    assert b.fiber_loss_db == pytest.approx(3.0, abs=1e-9)
    assert b.splice_loss_db == pytest.approx(0.15, abs=1e-9)
    assert b.connector_loss_db == pytest.approx(2.0, abs=1e-9)


def test_fibre_budget_margin_and_verdict():
    optics = Optics(
        tx_power_dbm=2.0,
        rx_sensitivity_dbm=-28.0,
        splice_count=3,
        connector_pairs=4,
        bitrate_gbps=1.0,
    )
    b = compute_fiber_budget(12.0, "smf", optics)
    assert b.available_budget_db == pytest.approx(30.0)
    assert b.total_loss_db == pytest.approx(5.15, abs=1e-9)
    assert b.margin_db == pytest.approx(24.85, abs=1e-9)
    assert b.verdict == "PASS"
    assert b.limiting_factor == "none"


def test_fibre_budget_fails_when_the_budget_is_exceeded():
    # 150 km of G.652 at 0.25 dB/km is 37.5 dB of fibre loss alone, which
    # is more than a 30 dB optical budget.
    optics = Optics(tx_power_dbm=2.0, rx_sensitivity_dbm=-28.0)
    b = compute_fiber_budget(150.0, "smf", optics)
    assert b.verdict == "FAIL"
    assert b.limiting_factor == "power budget"
    assert b.margin_db < 0


def test_fibre_max_reach_is_exact_because_loss_is_linear():
    # Remaining budget 30 - 0.15 - 2.00 = 27.85 dB over 0.25 dB/km = 111.4 km
    optics = Optics(
        tx_power_dbm=2.0,
        rx_sensitivity_dbm=-28.0,
        splice_count=3,
        connector_pairs=4,
    )
    b = compute_fiber_budget(1.0, "smf", optics)
    assert b.max_reach_km == pytest.approx(111.4, abs=0.001)


def test_fibre_dispersion_limit_is_enforced():
    # 1000/(100 Gb/s * 17 ps/nm/km * 0.1 nm) = 5.88 km
    optics = Optics(
        tx_power_dbm=2.0,
        rx_sensitivity_dbm=-28.0,
        bitrate_gbps=100.0,
        spectral_width_nm=0.1,
    )
    b = compute_fiber_budget(12.0, "smf", optics)
    assert b.dispersion_limit_km == pytest.approx(5.882, abs=0.01)
    assert b.verdict == "FAIL"
    assert b.limiting_factor == "chromatic dispersion"


def test_fibre_dispersion_limit_at_10g_is_117_km():
    # 1000/(10 * 17 * 0.05) = 117.6 km
    optics = Optics(
        tx_power_dbm=2.0,
        rx_sensitivity_dbm=-28.0,
        bitrate_gbps=10.0,
        spectral_width_nm=0.05,
    )
    b = compute_fiber_budget(12.0, "smf", optics)
    assert b.dispersion_limit_km == pytest.approx(117.647, abs=0.01)
    assert b.verdict == "PASS"


def test_multimodal_reach_is_limited_by_modal_bandwidth():
    # OM4 is 4700 MHz*km: at 10 Gb/s that is 0.47 km.
    optics = Optics(
        tx_power_dbm=0.0,
        rx_sensitivity_dbm=-20.0,
        bitrate_gbps=10.0,
        wavelength_nm=850,
    )
    b = compute_fiber_budget(1.0, "om4", optics)
    assert b.modal_limit_km == pytest.approx(0.47, abs=0.001)
    assert b.verdict == "FAIL"
    assert b.limiting_factor == "modal bandwidth"


def test_g657_and_g655_use_their_own_attenuation():
    optics = Optics(tx_power_dbm=2.0, rx_sensitivity_dbm=-28.0)
    assert compute_fiber_budget(10.0, "smf", optics).fiber_loss_db == pytest.approx(2.5)
    assert compute_fiber_budget(10.0, "smf-nzdf", optics).fiber_loss_db == pytest.approx(2.2)


def test_fibre_budget_rejects_unknown_fibre_and_bad_length():
    with pytest.raises(ValueError):
        compute_fiber_budget(1.0, "not-a-fibre")
    with pytest.raises(ValueError):
        compute_fiber_budget(0.0, "smf")


def test_a_nan_length_is_rejected_on_every_medium():
    # NaN compares false against every bound, so an unguarded NaN length
    # would walk straight to a PASS verdict.
    with pytest.raises(ValueError):
        compute_fiber_budget(float("nan"), "smf")
    with pytest.raises(ValueError):
        compute_microwave_budget(float("nan"), 15.0, 20.0, 30.0)
    with pytest.raises(ValueError):
        compute_copper_budget(float("nan"), "cat6")


def test_nan_optics_are_rejected():
    with pytest.raises(ValueError):
        compute_fiber_budget(
            1.0, "smf", Optics(tx_power_dbm=float("nan"), rx_sensitivity_dbm=-28.0)
        )
    with pytest.raises(ValueError):
        compute_fiber_budget(
            1.0, "smf", Optics(tx_power_dbm=0.0, rx_sensitivity_dbm=-28.0, bitrate_gbps=float("nan"))
        )
    with pytest.raises(ValueError):
        compute_fiber_budget(
            1.0,
            "smf",
            Optics(
                tx_power_dbm=0.0,
                rx_sensitivity_dbm=-28.0,
                spectral_width_nm=float("nan"),
            ),
        )


def test_nan_microwave_powers_are_rejected():
    with pytest.raises(ValueError):
        compute_microwave_budget(1.0, 15.0, float("nan"), 30.0)
    with pytest.raises(ValueError):
        compute_microwave_budget(1.0, 15.0, 20.0, float("nan"))


def test_a_zero_spectral_width_is_rejected_instead_of_dividing_by_zero():
    # 1000/(bitrate * dispersion * 0) used to raise ZeroDivisionError.
    optics = Optics(
        tx_power_dbm=0.0,
        rx_sensitivity_dbm=-28.0,
        bitrate_gbps=10.0,
        spectral_width_nm=0.0,
    )
    with pytest.raises(ValueError) as excinfo:
        compute_fiber_budget(1.0, "smf", optics)
    assert "spectral width" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Microwave budget
# ---------------------------------------------------------------------------


def test_microwave_budget_end_to_end():
    # 5 km at 15 GHz: FSPL = 92.44 + 20log10(5) + 20log10(15) = 129.94 dB
    b = compute_microwave_budget(
        length_km=5.0,
        frequency_ghz=15.0,
        tx_power_dbm=20.0,
        tx_antenna_gain_dbi=30.0,
        rx_antenna_gain_dbi=30.0,
        rx_threshold_dbm=-80.0,
        feeder_loss_tx_db=0.5,
        feeder_loss_rx_db=0.5,
    )
    assert b.fspl_db == pytest.approx(129.94, abs=0.01)
    assert b.eirp_dbm == pytest.approx(50.0)
    assert b.received_level_dbm == pytest.approx(-50.94, abs=0.02)
    assert b.margin_db == pytest.approx(29.06, abs=0.02)
    assert b.verdict == "PASS"


def test_microwave_fails_when_the_fade_margin_is_gone():
    b = compute_microwave_budget(
        length_km=40.0,
        frequency_ghz=15.0,
        tx_power_dbm=10.0,
        tx_antenna_gain_dbi=30.0,
        rx_antenna_gain_dbi=30.0,
        rx_threshold_dbm=-80.0,
        required_margin_db=10.0,
    )
    assert b.verdict == "FAIL"
    assert b.limiting_factor == "fade margin"


def test_microwave_rain_fade_is_reported():
    # Clear air is fine (19 dB of margin, 10 dB required) but a 25 dB rain
    # fade breaks the link, so the rain is the limiting factor.
    b = compute_microwave_budget(
        length_km=5.0,
        frequency_ghz=15.0,
        tx_power_dbm=20.0,
        tx_antenna_gain_dbi=30.0,
        rx_antenna_gain_dbi=30.0,
        rx_threshold_dbm=-70.0,
        rain_fade_allowance_db=25.0,
        required_margin_db=10.0,
    )
    assert b.margin_db == pytest.approx(19.06, abs=0.02)
    assert b.verdict == "FAIL"
    assert b.limiting_factor == "rain fade"
    assert any("rain fade" in n for n in b.notes)


# ---------------------------------------------------------------------------
# Copper budget
# ---------------------------------------------------------------------------


def test_copper_cat6_at_80m_four_pairs_gigabit_passes():
    b = compute_copper_budget(80.0, "cat6", pairs=4, application="1gbase-t")
    # insertion 21.4 * 0.8 = 17.12, no 1G derating, PS-NEXT 3.6 dB
    assert b.insertion_loss_db == pytest.approx(17.12, abs=1e-9)
    assert b.derating_db == pytest.approx(0.0)
    assert b.ps_next_penalty_db == pytest.approx(3.6, abs=1e-9)
    assert b.total_budget_db == pytest.approx(20.72, abs=1e-9)
    assert b.verdict == "PASS"


def test_copper_cat6_at_90m_four_pairs_10g_fails_on_insertion_loss():
    b = compute_copper_budget(90.0, "cat6", pairs=4, application="10gbase-t")
    # insertion 21.4 * 0.9 = 19.26, 10G 4-pair derating 6.0, PS-NEXT 3.6
    assert b.insertion_loss_db == pytest.approx(19.26, abs=1e-9)
    assert b.derating_db == pytest.approx(6.0)
    assert b.total_budget_db == pytest.approx(28.86, abs=1e-9)
    assert b.verdict == "FAIL"
    assert b.limiting_factor == "insertion loss"


def test_copper_length_limits():
    # 95 m exceeds the 90 m channel limit for Cat6 ...
    b = compute_copper_budget(95.0, "cat6", pairs=2, application="1gbase-t")
    assert b.verdict == "FAIL"
    assert b.limiting_factor == "channel length"
    # ... but Cat6A allows a 100 m permanent link.
    b6a = compute_copper_budget(95.0, "cat6a", pairs=2, application="1gbase-t")
    assert b6a.verdict == "PASS"
    assert b6a.channel_max_m == 100.0


def test_copper_ps_next_penalty_only_applies_above_two_pairs():
    assert compute_copper_budget(50.0, "cat6", 2, "1gbase-t").ps_next_penalty_db == 0.0
    assert compute_copper_budget(50.0, "cat6", 4, "1gbase-t").ps_next_penalty_db == pytest.approx(3.6, abs=1e-9)


def test_copper_limits_match_the_standard():
    assert COPPER_TYPES["cat6"].channel_max_m == 90.0
    assert COPPER_TYPES["cat6"].permanent_link_max_m == 90.0
    assert COPPER_TYPES["cat6a"].permanent_link_max_m == 100.0
    assert COPPER_TYPES["cat5e"].max_insertion_loss_db == pytest.approx(20.8)
    assert COPPER_TYPES["cat6"].max_insertion_loss_db == pytest.approx(21.4)
    assert COPPER_TYPES["cat6a"].max_insertion_loss_db == pytest.approx(23.2)


def test_copper_rejects_unknown_combinations():
    with pytest.raises(ValueError):
        compute_copper_budget(10.0, "cat7")
    with pytest.raises(ValueError):
        compute_copper_budget(10.0, "cat6", pairs=3, application="1gbase-t")
    with pytest.raises(ValueError):
        compute_copper_budget(10.0, "cat6", pairs=1, application="40gbase-t")


# ---------------------------------------------------------------------------
# Media tables
# ---------------------------------------------------------------------------


def test_fibre_table_matches_the_itu_values():
    assert FIBRE_TYPES["smf"].attenuation_db_per_km[1310] == pytest.approx(0.35)
    assert FIBRE_TYPES["smf"].attenuation_db_per_km[1550] == pytest.approx(0.25)
    assert FIBRE_TYPES["smf"].dispersion_ps_nm_km == pytest.approx(17.0)
    assert FIBRE_TYPES["om4"].modal_bandwidth_mhz_km == pytest.approx(4700.0)
