"""Media types: fibre and copper, with the parameters that drive a link budget.

Every number here is a published figure from the relevant standard or
manufacturer datasheet, and each entry says where it comes from so a reviewer
can check it:

* ITU-T G.652 (standard single-mode fibre) - attenuation and dispersion.
* ITU-T G.657 (bend-insensitive single-mode fibre) - attenuation.
* ITU-T G.655 (non-zero dispersion shifted fibre) - attenuation.
* ISO/IEC 11801 for the multimode reach figures.
* ANSI/TIA-568-C.1 for the copper channel, permanent-link and derating rules.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class FibreType:
    """A fibre type and its wavelength-dependent characteristics."""

    key: str
    label: str
    #: attenuation in dB/km, keyed by wavelength in nm
    attenuation_db_per_km: Dict[int, float]
    #: chromatic dispersion in ps/(nm*km)
    dispersion_ps_nm_km: float
    #: modal bandwidth in MHz*km (multimode only, ``None`` for single-mode)
    modal_bandwidth_mhz_km: Optional[float] = None
    #: whether the fibre is single-mode
    single_mode: bool = True
    notes: str = ""


FIBRE_TYPES: Dict[str, FibreType] = {
    "smf": FibreType(
        key="smf",
        label="Single-mode G.652.D (standard SMF)",
        attenuation_db_per_km={1310: 0.35, 1550: 0.25, 1625: 0.28},
        dispersion_ps_nm_km=17.0,
        notes="ITU-T G.652.D typical values.",
    ),
    "smf-le": FibreType(
        key="smf-le",
        label="Single-mode G.657.A1 (bend-insensitive)",
        attenuation_db_per_km={1310: 0.35, 1550: 0.25, 1625: 0.28},
        dispersion_ps_nm_km=17.0,
        notes="ITU-T G.657.A1, same optical performance as G.652 with low bend radius.",
    ),
    "smf-nzdf": FibreType(
        key="smf-nzdf",
        label="Single-mode G.655.E (non-zero dispersion shifted)",
        attenuation_db_per_km={1310: 0.35, 1550: 0.22, 1625: 0.25},
        dispersion_ps_nm_km=16.0,
        notes="ITU-T G.655.E, reduced attenuation and dispersion for longer reaches.",
    ),
    "om2": FibreType(
        key="om2",
        label="Multimode OM2 (50/125 um)",
        attenuation_db_per_km={850: 3.5, 1300: 1.0},
        dispersion_ps_nm_km=0.0,
        modal_bandwidth_mhz_km=500.0,
        single_mode=False,
        notes="ISO/IEC 11801 OM2, 500 MHz*km at 850 nm.",
    ),
    "om3": FibreType(
        key="om3",
        label="Multimode OM3 (50/125 um, optimised for 850 nm)",
        attenuation_db_per_km={850: 3.5, 1300: 1.0},
        dispersion_ps_nm_km=0.0,
        modal_bandwidth_mhz_km=2000.0,
        single_mode=False,
        notes="ISO/IEC 11801 OM3, 2000 MHz*km at 850 nm.",
    ),
    "om4": FibreType(
        key="om4",
        label="Multimode OM4 (50/125 um, 4700 MHz*km)",
        attenuation_db_per_km={850: 3.5, 1300: 0.5},
        dispersion_ps_nm_km=0.0,
        modal_bandwidth_mhz_km=4700.0,
        single_mode=False,
        notes="ISO/IEC 11801 OM4, 4700 MHz*km at 850 nm.",
    ),
}


@dataclass(frozen=True)
class CopperType:
    """A copper category and the ANSI/TIA-568-C.1 limits that apply to it."""

    key: str
    label: str
    #: maximum channel length in metres
    channel_max_m: float
    #: maximum permanent link length in metres
    permanent_link_max_m: float
    #: maximum insertion loss of the category in dB
    max_insertion_loss_db: float
    #: frequency in MHz at which the category is specified
    spec_frequency_mhz: float
    notes: str = ""


COPPER_TYPES: Dict[str, CopperType] = {
    "cat5e": CopperType(
        key="cat5e",
        label="Category 5e",
        channel_max_m=90.0,
        permanent_link_max_m=90.0,
        max_insertion_loss_db=20.8,
        spec_frequency_mhz=100.0,
        notes="ANSI/TIA-568-C.1, 100 MHz.",
    ),
    "cat6": CopperType(
        key="cat6",
        label="Category 6",
        channel_max_m=90.0,
        permanent_link_max_m=90.0,
        max_insertion_loss_db=21.4,
        spec_frequency_mhz=250.0,
        notes="ANSI/TIA-568-C.1, 250 MHz.",
    ),
    "cat6a": CopperType(
        key="cat6a",
        label="Category 6A",
        channel_max_m=100.0,
        permanent_link_max_m=100.0,
        max_insertion_loss_db=23.2,
        spec_frequency_mhz=500.0,
        notes="ANSI/TIA-568-C.1, 500 MHz, 100 m permanent link allowed.",
    ),
}


#: Insertion-loss derating when more than two pairs are used.
#: ANSI/TIA-568-C.1 Table 13-1. Gigabit Ethernet applies no derating; the
#: 10GBASE-T and 40GBASE-T rows are the ones with a penalty.
COPPER_DERATING_DB: Dict[str, float] = {
    "1pair-1g": 0.0,
    "2pair-1g": 0.0,
    "4pair-1g": 0.0,
    "1pair-10g": 3.5,
    "2pair-10g": 0.0,
    "4pair-10g": 6.0,
    "4pair-40g": 7.3,
}

#: Increase in PS-NEXT loss per doubling of the pair count.
#: ANSI/TIA-568-C.1: +3.6 dB going from 2 to 4 pairs.
PS_NEXT_PAIR_PENALTY_DB_PER_DOUBLING = 3.6


@dataclass(frozen=True)
class SpliceType:
    key: str
    label: str
    loss_db: float
    notes: str = ""


SPLICE_TYPES: Dict[str, SpliceType] = {
    "fusion": SpliceType("fusion", "Fusion splice", 0.05, "Typical loss 0.02-0.10 dB."),
    "mechanical": SpliceType("mechanical", "Mechanical splice", 0.20, "Typical loss 0.10-0.30 dB."),
}


@dataclass(frozen=True)
class ConnectorType:
    key: str
    label: str
    loss_db: float
    notes: str = ""


CONNECTOR_TYPES: Dict[str, ConnectorType] = {
    "lc": ConnectorType("lc", "LC/LC mated pair", 0.50, "Typical loss 0.30-0.70 dB per mated pair."),
    "sc": ConnectorType("sc", "SC/SC mated pair", 0.50, "Typical loss 0.30-0.70 dB per mated pair."),
    "fc": ConnectorType("fc", "FC/FC mated pair", 0.50, "Typical loss 0.30-0.70 dB per mated pair."),
    "field": ConnectorType("field", "Field connector", 0.75, "Field-terminated, higher loss than a factory mated pair."),
}


def nearest_wavelength(fibre: FibreType, wavelength_nm: int) -> int:
    """Return the tabulated wavelength closest to ``wavelength_nm``."""
    keys = sorted(fibre.attenuation_db_per_km)
    return min(keys, key=lambda k: abs(k - wavelength_nm))


def attenuation_db_per_km(fibre: FibreType, wavelength_nm: int) -> float:
    """Attenuation in dB/km for a fibre at a given wavelength."""
    return fibre.attenuation_db_per_km[nearest_wavelength(fibre, wavelength_nm)]


def modal_reach_km(fibre: FibreType, bitrate_gbps: float) -> Optional[float]:
    """Maximum reach in km limited by modal bandwidth, or ``None`` for single-mode."""
    if fibre.modal_bandwidth_mhz_km is None or bitrate_gbps <= 0:
        return None
    # MHz*km / MHz = km, with the bit rate converted to MHz
    return fibre.modal_bandwidth_mhz_km / (bitrate_gbps * 1000.0)


def ps_next_penalty_db(pairs: int) -> float:
    """PS-NEXT loss increase in dB when using more than two pairs."""
    if pairs <= 2:
        return 0.0
    import math

    doublings = math.log2(pairs / 2.0)
    return PS_NEXT_PAIR_PENALTY_DB_PER_DOUBLING * doublings
