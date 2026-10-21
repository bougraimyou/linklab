"""Decibel arithmetic and physical constants.

Every conversion in LinkLab goes through this module, so a reviewer can audit
the maths in one place instead of hunting for ``math.log10`` calls.
"""

import math

#: Speed of light in vacuum, m/s.
C_M_PER_S = 299_792_458.0

#: Reference frequency for the free-space path loss formula, Hz.
FSPL_REFERENCE_HZ = 1.0e9


def db_to_ratio(db: float) -> float:
    """Convert a decibel value to a power ratio (1.0 = 0 dB)."""
    return 10.0 ** (db / 10.0)


def ratio_to_db(ratio: float) -> float:
    """Convert a power ratio to decibels. ``ratio`` must be strictly positive."""
    if ratio <= 0:
        raise ValueError("ratio must be > 0")
    return 10.0 * math.log10(ratio)


def dbm_to_mw(dbm: float) -> float:
    """Convert dBm to milliwatts."""
    return db_to_ratio(dbm)


def mw_to_dbm(mw: float) -> float:
    """Convert milliwatts to dBm."""
    return ratio_to_db(mw)


def dbm_to_w(dbm: float) -> float:
    """Convert dBm to watts."""
    return db_to_ratio(dbm) / 1.0e3


def linear_to_db(amplitude: float) -> float:
    """Convert a field (amplitude) ratio to decibels, i.e. 20*log10."""
    if amplitude <= 0:
        raise ValueError("amplitude must be > 0")
    return 20.0 * math.log10(amplitude)


def fspl_db(distance_km: float, frequency_hz: float) -> float:
    """Free space path loss in dB.

    ``FSPL(dB) = 92.44 + 20*log10(d_km) + 20*log10(f_GHz)``

    Sanity check: 1 km at 1 GHz gives 92.44 dB, the textbook value.
    """
    if distance_km <= 0:
        raise ValueError("distance must be > 0")
    if frequency_hz <= 0:
        raise ValueError("frequency must be > 0")
    d_km = distance_km
    f_ghz = frequency_hz / 1.0e9
    return 92.44 + 20.0 * math.log10(d_km) + 20.0 * math.log10(f_ghz)


def dispersion_penalty_db(dispersion_ps: float, bit_period_ps: float) -> float:
    """Chromatic dispersion power penalty in dB.

    The rms pulse broadening is ``sigma`` ps; the eye-closure penalty for a
    Gaussian pulse is ``10*log10(1 + (sigma/T)^2)`` where ``T`` is the bit
    period. With ``sigma = 85 ps`` and ``T = 100 ps`` (10 Gb/s) this gives
    2.36 dB, the figure quoted in standard single-mode fibre planning guides.
    """
    if bit_period_ps <= 0:
        raise ValueError("bit period must be > 0")
    ratio = dispersion_ps / bit_period_ps
    return 10.0 * math.log10(1.0 + ratio * ratio)
