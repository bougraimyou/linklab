"""Project model and validation tests.

The validation rules are the part of LinkLab that protects a design from
being documented into a wrong state, so they get their own file.
"""

import json

import pytest

from linklab.models import Cable, OpticalSpan, Panel, Project, Rack
from linklab.project import (
    ERROR,
    WARNING,
    has_errors,
    load_project,
    project_from_dict,
    project_to_dict,
    save_project,
    validate_project,
)

SAMPLE = Path = __import__("pathlib").Path(__file__).resolve().parents[1] / (
    "examples/site-atlas-telecom/project.json"
)


def make_project() -> Project:
    return Project(
        name="Test",
        racks=[
            Rack(
                id="R1",
                name="Rack 1",
                u_height=42,
                panels=[
                    Panel(
                        id="PP1",
                        name="Patch 1",
                        rack_id="R1",
                        kind="patch",
                        u_position=20,
                        ports=["01", "02"],
                    ),
                    Panel(
                        id="SW1",
                        name="Switch",
                        rack_id="R1",
                        kind="switch",
                        u_position=30,
                        ports=["Gi1/0/1"],
                    ),
                ],
            )
        ],
        cables=[
            Cable(id="C1", a_end="R1.PP1.01", b_end="R1.SW1.Gi1/0/1", length_m=5.0)
        ],
    )


def codes(project) -> set:
    return {f.code for f in validate_project(project)}


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_a_clean_project_has_no_findings():
    assert validate_project(make_project()) == []


def test_the_shipped_example_validates():
    project = load_project(str(SAMPLE))
    findings = validate_project(project)
    assert findings == [], [str(f) for f in findings]


# ---------------------------------------------------------------------------
# port assignment
# ---------------------------------------------------------------------------


def test_a_port_may_only_take_one_cable():
    p = make_project()
    p.cables.append(
        Cable(id="C2", a_end="R1.PP1.01", b_end="R1.SW1.Gi1/0/1", length_m=6.0)
    )
    findings = validate_project(p)
    assert "port-used-twice" in codes(p)
    assert has_errors(findings)


def test_two_panels_in_different_racks_may_reuse_a_port_name():
    p = make_project()
    p.racks.append(
        Rack(
            id="R2",
            name="Rack 2",
            u_height=42,
            panels=[
                Panel(
                    id="PP1",
                    name="Patch 1",
                    rack_id="R2",
                    kind="patch",
                    u_position=20,
                    ports=["01"],
                ),
                Panel(
                    id="SW1",
                    name="Switch",
                    rack_id="R2",
                    kind="switch",
                    u_position=30,
                    ports=["Gi1/0/1"],
                ),
            ],
        )
    )
    # a cable from R2's patch panel to R1's switch: the same port name, a
    # different physical port
    p.cables.append(
        Cable(id="C3", a_end="R2.PP1.01", b_end="R1.SW1.Gi1/0/2", length_m=9.0)
    )
    # R1.SW1 has no Gi1/0/2, so this must be an unknown-port error, not a
    # duplicate-port error
    found = codes(p)
    assert "unknown-b-end" in found
    assert "port-used-twice" not in found


def test_a_cable_to_an_unknown_port_is_an_error():
    p = make_project()
    p.cables.append(
        Cable(id="C9", a_end="R1.PP1.09", b_end="R1.SW1.Gi1/0/1", length_m=1.0)
    )
    assert "unknown-a-end" in codes(p)


def test_a_cable_with_both_ends_on_one_port_is_an_error():
    p = make_project()
    p.cables.append(
        Cable(id="C8", a_end="R1.PP1.01", b_end="R1.PP1.01", length_m=1.0)
    )
    assert "self-loop" in codes(p)


# ---------------------------------------------------------------------------
# rack geometry
# ---------------------------------------------------------------------------


def test_a_panel_that_does_not_fit_in_its_rack_is_an_error():
    p = make_project()
    p.racks[0].panels[0].u_position = 42
    p.racks[0].panels[0].u_height = 4
    assert "panel-overflows-rack" in codes(p)


def test_a_panel_at_u0_is_an_error():
    p = make_project()
    p.racks[0].panels[0].u_position = 0
    assert "bad-u-position" in codes(p)


def test_a_panel_claiming_another_rack_is_an_error():
    p = make_project()
    p.racks[0].panels[0].rack_id = "R9"
    assert "panel-wrong-rack" in codes(p)


def test_a_duplicate_panel_id_inside_one_rack_is_an_error():
    p = make_project()
    p.racks[0].panels.append(
        Panel(id="PP1", name="Copy", rack_id="R1", kind="patch", u_position=22, ports=["01"])
    )
    assert "duplicate-panel-id" in codes(p)


def test_a_duplicate_rack_id_is_an_error():
    p = make_project()
    p.racks.append(Rack(id="R1", name="Copy"))
    assert "duplicate-rack-id" in codes(p)


# ---------------------------------------------------------------------------
# media and lengths
# ---------------------------------------------------------------------------


def test_an_unknown_media_type_is_an_error():
    p = make_project()
    p.cables[0].media = "cat9"
    assert "unknown-media" in codes(p)


def test_a_negative_length_is_an_error():
    p = make_project()
    p.cables[0].length_m = -1.0
    assert "negative-length" in codes(p)


def test_a_panel_with_no_ports_is_a_warning_not_an_error():
    p = make_project()
    p.racks[0].panels.append(
        Panel(id="PP9", name="Empty", rack_id="R1", kind="patch", u_position=22)
    )
    findings = validate_project(p)
    assert "panel-no-ports" in {f.code for f in findings}
    assert not has_errors(findings)


# ---------------------------------------------------------------------------
# round trip
# ---------------------------------------------------------------------------


def test_a_project_survives_a_json_round_trip(tmp_path):
    project = make_project()
    path = tmp_path / "p.json"
    save_project(project, str(path))
    again = load_project(str(path))
    assert again.name == project.name
    assert len(again.racks) == 1
    assert again.racks[0].panels[0].ports == ["01", "02"]
    assert again.cables[0].a_end == "R1.PP1.01"


def test_project_to_dict_is_json_serialisable():
    json.dumps(project_to_dict(make_project()))
