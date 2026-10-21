"""Loading, saving and validating a project.

The validation is the part that matters. A cable schedule that lists the same
switch port twice, or a panel that does not physically fit in its rack, is
not a documentation problem - it is a design error that a document should
refuse to hide. :func:`validate_project` therefore returns every problem it
finds rather than stopping at the first, so a designer can fix them in one
pass.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .models import CABLE_MEDIA, Cable, OpticalSpan, Panel, Project, Rack

#: Severity of a validation finding.
ERROR = "error"
WARNING = "warning"


@dataclass
class Finding:
    """One problem found in a project."""

    severity: str
    code: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        where = f" [{self.where}]" if self.where else ""
        return f"{self.severity.upper()}: {self.message}{where}"


def _panel_from_dict(data: Dict) -> Panel:
    return Panel(
        id=data.get("id", ""),
        name=data.get("name", ""),
        rack_id=data.get("rack_id", ""),
        kind=data.get("kind", "patch"),
        u_position=int(data.get("u_position", 1)),
        u_height=int(data.get("u_height", 1)),
        ports=list(data.get("ports", [])),
        model=data.get("model", ""),
        notes=data.get("notes", ""),
    )


def _rack_from_dict(data: Dict) -> Rack:
    return Rack(
        id=data.get("id", ""),
        name=data.get("name", ""),
        location=data.get("location", ""),
        u_height=int(data.get("u_height", 42)),
        panels=[_panel_from_dict(p) for p in data.get("panels", [])],
    )


def project_from_dict(data: Dict) -> Project:
    """Build a :class:`~linklab.models.Project` from plain dictionaries."""
    return Project(
        name=data.get("name", "Untitled project"),
        client=data.get("client", ""),
        site=data.get("site", ""),
        author=data.get("author", ""),
        date=data.get("date", ""),
        racks=[_rack_from_dict(r) for r in data.get("racks", [])],
        cables=[
            Cable(
                id=c.get("id", ""),
                a_end=c.get("a_end", ""),
                b_end=c.get("b_end", ""),
                media=c.get("media", "cat6"),
                length_m=float(c.get("length_m", 0.0)),
                label=c.get("label", ""),
                color=c.get("color", ""),
                notes=c.get("notes", ""),
            )
            for c in data.get("cables", [])
        ],
        optical_spans=[
            OpticalSpan(
                id=s.get("id", ""),
                a_end=s.get("a_end", ""),
                b_end=s.get("b_end", ""),
                length_km=float(s.get("length_km", 0.0)),
                fibre=s.get("fibre", "smf"),
                tx_power_dbm=float(s.get("tx_power_dbm", 2.0)),
                rx_sensitivity_dbm=float(s.get("rx_sensitivity_dbm", -28.0)),
                bitrate_gbps=(
                    float(s["bitrate_gbps"]) if s.get("bitrate_gbps") else None
                ),
                spectral_width_nm=float(s.get("spectral_width_nm", 0.1)),
                splice_count=int(s.get("splice_count", 0)),
                connector_pairs=int(s.get("connector_pairs", 2)),
                required_margin_db=float(s.get("required_margin_db", 0.0)),
                notes=s.get("notes", ""),
            )
            for s in data.get("optical_spans", [])
        ],
    )


def project_to_dict(project: Project) -> Dict:
    """Serialise a project back to plain dictionaries."""
    return project.to_dict()


def load_project(path: str) -> Project:
    """Load a project from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return project_from_dict(data)


def save_project(project: Project, path: str) -> None:
    """Write a project to a JSON file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(project_to_dict(project), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def validate_project(project: Project) -> List[Finding]:
    """Check a project for design errors.

    Returns every finding, most severe first. An empty list means the project
    is internally consistent and safe to document.
    """
    findings: List[Finding] = []

    rack_ids = [r.id for r in project.racks]
    if len(set(rack_ids)) != len(rack_ids):
        findings.append(
            Finding(ERROR, "duplicate-rack-id", "Two or more racks share an id.")
        )

    for rack in project.racks:
        panel_ids = [p.id for p in rack.panels]
        if len(set(panel_ids)) != len(panel_ids):
            findings.append(
                Finding(
                    ERROR,
                    "duplicate-panel-id",
                    f"Rack {rack.id} has two panels with the same id.",
                    rack.id,
                )
            )
        if rack.u_height <= 0:
            findings.append(
                Finding(
                    ERROR,
                    "bad-rack-height",
                    f"Rack {rack.id} has a non-positive usable height.",
                    rack.id,
                )
            )

    for rack in project.racks:
        for panel in rack.panels:
            if panel.rack_id != rack.id:
                findings.append(
                    Finding(
                        ERROR,
                        "panel-wrong-rack",
                        f"Panel {panel.id} claims rack {panel.rack_id} but is mounted "
                        f"in {rack.id}.",
                        panel.id,
                    )
                )
            if panel.u_position < 1:
                findings.append(
                    Finding(
                        ERROR,
                        "bad-u-position",
                        f"Panel {panel.id} starts at U{panel.u_position}; rack units "
                        "are numbered from 1.",
                        panel.id,
                    )
                )
            top = panel.u_position + panel.u_height - 1
            if top > rack.u_height:
                findings.append(
                    Finding(
                        ERROR,
                        "panel-overflows-rack",
                        f"Panel {panel.id} occupies U{panel.u_position}-U{top} but "
                        f"rack {rack.id} is only {rack.u_height}U high.",
                        panel.id,
                    )
                )
            if not panel.ports:
                findings.append(
                    Finding(
                        WARNING,
                        "panel-no-ports",
                        f"Panel {panel.id} has no ports listed.",
                        panel.id,
                    )
                )

    # Port assignment: a port may terminate at most one cable.
    used: Dict[str, List[str]] = {}
    for cable in project.cables:
        for end in (cable.a_end, cable.b_end):
            used.setdefault(end, []).append(cable.id)
        if not project.port_exists(cable.a_end):
            findings.append(
                Finding(
                    ERROR,
                    "unknown-a-end",
                    f"Cable {cable.id} starts at {cable.a_end}, which is not a "
                    "known port.",
                    cable.id,
                )
            )
        if not project.port_exists(cable.b_end):
            findings.append(
                Finding(
                    ERROR,
                    "unknown-b-end",
                    f"Cable {cable.id} ends at {cable.b_end}, which is not a "
                    "known port.",
                    cable.id,
                )
            )
        if cable.a_end == cable.b_end:
            findings.append(
                Finding(
                    ERROR,
                    "self-loop",
                    f"Cable {cable.id} has both ends on the same port.",
                    cable.id,
                )
            )
        if cable.media not in CABLE_MEDIA:
            findings.append(
                Finding(
                    ERROR,
                    "unknown-media",
                    f"Cable {cable.id} uses unknown media '{cable.media}'.",
                    cable.id,
                )
            )
        if cable.length_m < 0:
            findings.append(
                Finding(
                    ERROR,
                    "negative-length",
                    f"Cable {cable.id} has a negative length.",
                    cable.id,
                )
            )

    for port, cable_ids in sorted(used.items()):
        if len(cable_ids) > 1:
            findings.append(
                Finding(
                    ERROR,
                    "port-used-twice",
                    f"Port {port} is terminated by {len(cable_ids)} cables "
                    f"({', '.join(sorted(cable_ids))}); a port takes one cable.",
                    port,
                )
            )

    for span in project.optical_spans:
        if span.length_km <= 0:
            findings.append(
                Finding(
                    ERROR,
                    "bad-span-length",
                    f"Optical span {span.id} has a non-positive length.",
                    span.id,
                )
            )

    errors = sum(1 for f in findings if f.severity == ERROR)
    if errors:
        findings.sort(key=lambda f: 0 if f.severity == ERROR else 1)
    return findings


def has_errors(findings: List[Finding]) -> bool:
    return any(f.severity == ERROR for f in findings)
