"""The network project data model.

A project is the design being documented: the racks, the panels in them, the
cables between them, and the optical spans. Everything the documentation
generator prints comes from this model, and every port assignment is checked
by :mod:`linklab.project` before it is allowed to reach a document.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

#: Media types a cable can carry.
CABLE_MEDIA = ("cat5e", "cat6", "cat6a", "smf", "smf-le", "smf-nzdf", "om3", "om4")


@dataclass
class Panel:
    """A panel or a device mounted in a rack."""

    id: str
    name: str
    rack_id: str
    #: "patch" (patch panel), "odf" (optical distribution frame),
    #: "switch", "router", "active" (active equipment)
    kind: str = "patch"
    #: 1-based rack unit where the panel starts
    u_position: int = 1
    #: how many rack units the panel occupies
    u_height: int = 1
    #: port numbers, in order
    ports: List[str] = field(default_factory=list)
    model: str = ""
    notes: str = ""


@dataclass
class Rack:
    """A rack, and the panels mounted in it."""

    id: str
    name: str
    location: str = ""
    #: usable height in rack units
    u_height: int = 42
    panels: List[Panel] = field(default_factory=list)


@dataclass
class Cable:
    """A cable between two ports."""

    id: str
    #: "rack.panel.port" at the A end
    a_end: str
    #: "rack.panel.port" at the B end
    b_end: str
    #: one of :data:`CABLE_MEDIA`
    media: str = "cat6"
    length_m: float = 0.0
    label: str = ""
    color: str = ""
    notes: str = ""


@dataclass
class OpticalSpan:
    """An optical span between two sites, with its own transceiver pair."""

    id: str
    a_end: str
    b_end: str
    length_km: float = 0.0
    #: a key of :data:`linklab.media.FIBRE_TYPES`
    fibre: str = "smf"
    tx_power_dbm: float = 2.0
    rx_sensitivity_dbm: float = -28.0
    bitrate_gbps: Optional[float] = None
    spectral_width_nm: float = 0.1
    splice_count: int = 0
    connector_pairs: int = 2
    required_margin_db: float = 0.0
    notes: str = ""


@dataclass
class Project:
    """A whole design: the site, the racks, the cabling and the optical spans."""

    name: str
    client: str = ""
    site: str = ""
    author: str = ""
    date: str = ""
    racks: List[Rack] = field(default_factory=list)
    cables: List[Cable] = field(default_factory=list)
    optical_spans: List[OpticalSpan] = field(default_factory=list)

    # -- lookups ---------------------------------------------------------
    def rack(self, rack_id: str) -> Optional[Rack]:
        for r in self.racks:
            if r.id == rack_id:
                return r
        return None

    def panel(self, panel_id: str, rack_id: Optional[str] = None) -> Optional[Panel]:
        """Find a panel.

        Panel ids are rack-local (two racks may each have an "ODF"), so a
        rack id disambiguates. Without one, a panel id that appears in more
        than one rack is ambiguous and returns ``None``.
        """
        if rack_id is not None:
            rack = self.rack(rack_id)
            if rack is None:
                return None
            for p in rack.panels:
                if p.id == panel_id:
                    return p
            return None
        found: List[Panel] = []
        for r in self.racks:
            for p in r.panels:
                if p.id == panel_id:
                    found.append(p)
        return found[0] if len(found) == 1 else None

    def port_owner(self, endpoint: str) -> Optional[Panel]:
        """Return the panel holding ``rack.panel.port``."""
        parts = endpoint.split(".")
        if len(parts) != 3:
            return None
        rack_id, panel_id, _port = parts
        return self.panel(panel_id, rack_id)

    def port_exists(self, endpoint: str) -> bool:
        """True when ``rack.panel.port`` names a port that exists."""
        panel = self.port_owner(endpoint)
        if panel is None:
            return False
        port = endpoint.split(".")[2]
        return port in panel.ports

    def describe_endpoint(self, endpoint: str) -> str:
        """A human-readable description of a port, for the cable schedule."""
        panel = self.port_owner(endpoint)
        if panel is None:
            return endpoint
        port = endpoint.split(".")[2]
        rack = self.rack(panel.rack_id)
        rack_name = rack.name if rack else panel.rack_id
        return f"{rack_name} / {panel.name} / port {port}"

    def to_dict(self) -> Dict:
        return asdict(self)
