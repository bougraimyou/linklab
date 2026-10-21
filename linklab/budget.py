"""The link budget engine.

Three engines live here, one per transmission medium:

* :func:`compute_fiber_budget` - optical fibre. Loss is fibre attenuation
  plus splices and connectors. **There is no free-space path loss term in
  fibre**: FSPL describes radio propagation through air and does not apply to
  light inside a glass core. Including it would understate every optical link
  by more than 100 dB.
* :func:`compute_microwave_budget` - point-to-point microwave / RF, where free
  space path loss *is* the dominant term, together with antenna gains and a
  rain-fade allowance.
* :func:`compute_copper_budget` - balanced twisted pair, governed by the
  ANSI/TIA-568-C.1 channel and permanent-link length limits and by
  insertion-loss derating when more than two pairs are used.

Every engine returns the individual line items, not just a pass/fail, because
the output of a link budget is the working: a reader has to see *which* term
closed the link.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .media import (
    CONNECTOR_TYPES,
    COPPER_DERATING_DB,
    COPPER_TYPES,
    FIBRE_TYPES,
    SPLICE_TYPES,
    CopperType,
    FibreType,
    attenuation_db_per_km,
    modal_reach_km,
    ps_next_penalty_db,
)
from .units import dispersion_penalty_db, fspl_db


@dataclass
class Optics:
    """Transceiver characteristics at the two ends of an optical link."""

    tx_power_dbm: float
    rx_sensitivity_dbm: float
    wavelength_nm: int = 1550
    #: line rate in Gb/s; needed for the dispersion and modal limits
    bitrate_gbps: Optional[float] = None
    #: source spectral width in nm; drives the chromatic dispersion penalty
    spectral_width_nm: float = 0.1
    #: number of mated connector pairs on the link (patch panels, ODFs)
    connector_pairs: int = 2
    #: number of splices on the link
    splice_count: int = 0
    #: type of splice, a key of :data:`linklab.media.SPLICE_TYPES`
    splice_type: str = "fusion"
    #: type of connector, a key of :data:`linklab.media.CONNECTOR_TYPES`
    connector_type: str = "lc"
    #: margin that must remain after all losses, in dB
    required_margin_db: float = 0.0

    @property
    def available_budget_db(self) -> float:
        """Optical power the optics can tolerate end to end, in dB."""
        return self.tx_power_dbm - self.rx_sensitivity_dbm

    @property
    def splice_loss_db(self) -> float:
        return self.splice_count * SPLICE_TYPES[self.splice_type].loss_db

    @property
    def connector_loss_db(self) -> float:
        return self.connector_pairs * CONNECTOR_TYPES[self.connector_type].loss_db


@dataclass
class FiberBudget:
    """Line-by-line result of an optical fibre link budget."""

    length_km: float
    wavelength_nm: int
    bitrate_gbps: Optional[float]
    fibre: str

    attenuation_db_per_km: float
    fiber_loss_db: float
    splice_loss_db: float
    connector_loss_db: float
    total_loss_db: float

    available_budget_db: float
    margin_db: float
    required_margin_db: float

    dispersion_ps: float
    dispersion_penalty_db: float
    dispersion_limit_km: Optional[float]
    modal_limit_km: Optional[float]
    max_reach_km: float

    limiting_factor: str
    verdict: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MicrowaveBudget:
    """Line-by-line result of a point-to-point microwave link budget."""

    length_km: float
    frequency_ghz: float

    fspl_db: float
    tx_power_dbm: float
    tx_antenna_gain_dbi: float
    rx_antenna_gain_dbi: float
    feeder_loss_tx_db: float
    feeder_loss_rx_db: float
    rain_fade_allowance_db: float

    eirp_dbm: float
    received_level_dbm: float
    rx_threshold_dbm: float
    margin_db: float
    required_margin_db: float

    limiting_factor: str
    verdict: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CopperBudget:
    """Line-by-line result of a balanced twisted-pair link budget."""

    length_m: float
    category: str
    pairs: int
    application: str

    channel_max_m: float
    permanent_link_max_m: float
    insertion_loss_db: float
    derating_db: float
    ps_next_penalty_db: float
    total_budget_db: float
    max_insertion_loss_db: float

    limiting_factor: str
    verdict: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


def compute_fiber_budget(
    length_km: float,
    fibre_key: str = "smf",
    optics: Optional[Optics] = None,
) -> FiberBudget:
    """Compute an optical fibre link budget.

    :param length_km: link length in kilometres.
    :param fibre_key: a key of :data:`linklab.media.FIBRE_TYPES`.
    :param optics: transceiver characteristics; a conservative default is used
        when omitted.
    """
    if length_km <= 0:
        raise ValueError("length must be > 0")
    if fibre_key not in FIBRE_TYPES:
        raise ValueError(f"unknown fibre type: { fibre_key }")
    fibre: FibreType = FIBRE_TYPES[fibre_key]
    if optics is None:
        optics = Optics(tx_power_dbm=0.0, rx_sensitivity_dbm=-28.0)

    attenuation = attenuation_db_per_km(fibre, optics.wavelength_nm)
    fiber_loss = attenuation * length_km
    splice_loss = optics.splice_loss_db
    connector_loss = optics.connector_loss_db
    total_loss = fiber_loss + splice_loss + connector_loss

    available = optics.available_budget_db
    margin = available - total_loss

    dispersion_total = fibre.dispersion_ps_nm_km * length_km * optics.spectral_width_nm
    bit_period_ps = 1000.0 / optics.bitrate_gbps if optics.bitrate_gbps else None
    penalty = (
        dispersion_penalty_db(dispersion_total, bit_period_ps) if bit_period_ps else 0.0
    )
    dispersion_limit = None
    if optics.bitrate_gbps and fibre.dispersion_ps_nm_km > 0:
        dispersion_limit = (
            1000.0
            / (optics.bitrate_gbps * fibre.dispersion_ps_nm_km * optics.spectral_width_nm)
        )
    modal_limit = modal_reach_km(fibre, optics.bitrate_gbps) if optics.bitrate_gbps else None

    # Fibre loss is linear in length, so the maximum reach is exact rather than
    # a numerical search: remaining budget divided by the attenuation.
    fixed_loss = splice_loss + connector_loss
    if attenuation > 0:
        max_reach = max(0.0, (available - fixed_loss) / attenuation)
    else:
        max_reach = float("inf")

    notes: List[str] = []
    limiting = "none"
    verdict = "PASS"

    if margin < optics.required_margin_db:
        verdict = "FAIL"
        limiting = "power budget"
        notes.append(
            f"Power margin is {margin:.2f} dB, {optics.required_margin_db:.2f} dB required."
        )
    if dispersion_limit is not None and length_km > dispersion_limit:
        verdict = "FAIL"
        limiting = "chromatic dispersion" if limiting == "none" else limiting
        notes.append(
            f"Length {length_km:.2f} km exceeds the dispersion limit of "
            f"{dispersion_limit:.2f} km for {optics.bitrate_gbps:g} Gb/s."
        )
    if modal_limit is not None and length_km > modal_limit:
        verdict = "FAIL"
        limiting = "modal bandwidth" if limiting == "none" else limiting
        notes.append(
            f"Length {length_km:.2f} km exceeds the modal-bandwidth limit of "
            f"{modal_limit:.2f} km."
        )

    return FiberBudget(
        length_km=length_km,
        wavelength_nm=optics.wavelength_nm,
        bitrate_gbps=optics.bitrate_gbps,
        fibre=fibre.key,
        attenuation_db_per_km=attenuation,
        fiber_loss_db=fiber_loss,
        splice_loss_db=splice_loss,
        connector_loss_db=connector_loss,
        total_loss_db=total_loss,
        available_budget_db=available,
        margin_db=margin,
        required_margin_db=optics.required_margin_db,
        dispersion_ps=dispersion_total,
        dispersion_penalty_db=penalty,
        dispersion_limit_km=dispersion_limit,
        modal_limit_km=modal_limit,
        max_reach_km=max_reach,
        limiting_factor=limiting,
        verdict=verdict,
        notes=notes,
    )


def compute_microwave_budget(
    length_km: float,
    frequency_ghz: float,
    tx_power_dbm: float,
    rx_antenna_gain_dbi: float,
    tx_antenna_gain_dbi: float = 0.0,
    rx_threshold_dbm: float = -80.0,
    feeder_loss_tx_db: float = 0.5,
    feeder_loss_rx_db: float = 0.5,
    rain_fade_allowance_db: float = 0.0,
    required_margin_db: float = 10.0,
) -> MicrowaveBudget:
    """Compute a point-to-point microwave / RF link budget.

    :param length_km: path length in kilometres.
    :param frequency_ghz: carrier frequency in GHz.
    :param tx_power_dbm: transmitter output power at the feed.
    :param rx_antenna_gain_dbi: receive antenna gain.
    :param tx_antenna_gain_dbi: transmit antenna gain.
    :param rx_threshold_dbm: receiver sensitivity (the level it must beat).
    :param feeder_loss_tx_db: waveguide / feeder loss at the transmit end.
    :param feeder_loss_rx_db: waveguide / feeder loss at the receive end.
    :param rain_fade_allowance_db: fade margin to set aside for rain.
    :param required_margin_db: margin that must remain after all losses.
    """
    if length_km <= 0:
        raise ValueError("length must be > 0")
    if frequency_ghz <= 0:
        raise ValueError("frequency must be > 0")

    path = fspl_db(length_km, frequency_ghz * 1.0e9)
    eirp = tx_power_dbm + tx_antenna_gain_dbi
    received = eirp - path + rx_antenna_gain_dbi - feeder_loss_tx_db - feeder_loss_rx_db
    margin = received - rx_threshold_dbm

    notes: List[str] = []
    limiting = "none"
    verdict = "PASS"

    if margin < required_margin_db:
        verdict = "FAIL"
        limiting = "fade margin"
        notes.append(
            f"Available margin is {margin:.2f} dB, {required_margin_db:.2f} dB required."
        )
    if rain_fade_allowance_db and margin - rain_fade_allowance_db < required_margin_db:
        verdict = "FAIL"
        limiting = "rain fade" if limiting == "none" else limiting
        notes.append(
            f"After a {rain_fade_allowance_db:.2f} dB rain fade the margin falls to "
            f"{margin - rain_fade_allowance_db:.2f} dB, below the "
            f"{required_margin_db:.2f} dB requirement."
        )

    return MicrowaveBudget(
        length_km=length_km,
        frequency_ghz=frequency_ghz,
        fspl_db=path,
        tx_power_dbm=tx_power_dbm,
        tx_antenna_gain_dbi=tx_antenna_gain_dbi,
        rx_antenna_gain_dbi=rx_antenna_gain_dbi,
        feeder_loss_tx_db=feeder_loss_tx_db,
        feeder_loss_rx_db=feeder_loss_rx_db,
        rain_fade_allowance_db=rain_fade_allowance_db,
        eirp_dbm=eirp,
        received_level_dbm=received,
        rx_threshold_dbm=rx_threshold_dbm,
        margin_db=margin,
        required_margin_db=required_margin_db,
        limiting_factor=limiting,
        verdict=verdict,
        notes=notes,
    )


def compute_copper_budget(
    length_m: float,
    category: str = "cat6",
    pairs: int = 4,
    application: str = "1gbase-t",
) -> CopperBudget:
    """Compute a balanced twisted-pair link budget.

    :param length_m: link length in metres.
    :param category: a key of :data:`linklab.media.COPPER_TYPES`.
    :param pairs: number of pairs actually used (1, 2 or 4).
    :param application: one of ``1gbase-t``, ``10gbase-t``, ``40gbase-t``.
    """
    if length_m <= 0:
        raise ValueError("length must be > 0")
    if category not in COPPER_TYPES:
        raise ValueError(f"unknown copper category: { category }")
    copper: CopperType = COPPER_TYPES[category]

    derating_key = {
        (1, "1gbase-t"): "1pair-1g",
        (2, "1gbase-t"): "2pair-1g",
        (4, "1gbase-t"): "4pair-1g",
        (1, "10gbase-t"): "1pair-10g",
        (2, "10gbase-t"): "2pair-10g",
        (4, "10gbase-t"): "4pair-10g",
        (4, "40gbase-t"): "4pair-40g",
    }.get((pairs, application))
    if derating_key is None:
        raise ValueError(f"no derating rule for {pairs} pairs on {application}")
    derating = COPPER_DERATING_DB[derating_key]
    psnext = ps_next_penalty_db(pairs)

    insertion = copper.max_insertion_loss_db * (length_m / 100.0)
    total = insertion + derating + psnext

    notes: List[str] = []
    limiting = "none"
    verdict = "PASS"

    if length_m > copper.channel_max_m:
        verdict = "FAIL"
        limiting = "channel length"
        notes.append(
            f"{length_m:.1f} m exceeds the {copper.channel_max_m:.0f} m channel limit."
        )
    if length_m > copper.permanent_link_max_m:
        verdict = "FAIL"
        limiting = "permanent link length" if limiting == "none" else limiting
        notes.append(
            f"{length_m:.1f} m exceeds the {copper.permanent_link_max_m:.0f} m "
            "permanent-link limit."
        )
    if total > copper.max_insertion_loss_db:
        verdict = "FAIL"
        limiting = "insertion loss" if limiting == "none" else limiting
        notes.append(
            f"Total budget {total:.2f} dB exceeds the {copper.max_insertion_loss_db:.1f} dB "
            f"limit for {copper.label}."
        )

    return CopperBudget(
        length_m=length_m,
        category=category,
        pairs=pairs,
        application=application,
        channel_max_m=copper.channel_max_m,
        permanent_link_max_m=copper.permanent_link_max_m,
        insertion_loss_db=insertion,
        derating_db=derating,
        ps_next_penalty_db=psnext,
        total_budget_db=total,
        max_insertion_loss_db=copper.max_insertion_loss_db,
        limiting_factor=limiting,
        verdict=verdict,
        notes=notes,
    )
