"""Documentation generator and CLI tests.

The point of these is that the generated site is a real, complete artefact:
the files exist, they contain the engine's numbers, and the site refuses to
build a project that has design errors.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from linklab.cli import main
from linklab.docs import build_docs
from linklab.project import load_project, validate_project

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples/site-atlas-telecom/project.json"


def test_docs_build_writes_every_page(tmp_path):
    project = load_project(str(SAMPLE))
    summary = build_docs(project, str(tmp_path))
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "schedule.html").exists()
    assert (tmp_path / "links.html").exists()
    assert (tmp_path / "assets" / "style.css").exists()
    for rack in project.racks:
        assert (tmp_path / "racks" / f"{rack.id}.html").exists()
    assert summary["racks"] == 3
    assert summary["cables"] == 9


def test_generated_pages_contain_the_engines_numbers(tmp_path):
    project = load_project(str(SAMPLE))
    build_docs(project, str(tmp_path))
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Programme de cablage" in index
    links = (tmp_path / "links.html").read_text(encoding="utf-8")
    # the 42 km span: 10.5 dB of fibre loss, 19.10 dB of margin
    assert "10.50 dB" in links
    assert "19.10 dB" in links
    assert "PASS" in links


def test_the_cable_schedule_lists_every_cable(tmp_path):
    project = load_project(str(SAMPLE))
    build_docs(project, str(tmp_path))
    schedule = (tmp_path / "schedule.html").read_text(encoding="utf-8")
    for cable in project.cables:
        assert cable.id in schedule


def test_a_rack_page_carries_a_port_map(tmp_path):
    project = load_project(str(SAMPLE))
    build_docs(project, str(tmp_path))
    page = (tmp_path / "racks" / "SR01.html").read_text(encoding="utf-8")
    assert "Port map" in page
    assert "Gi1/0/1" in page
    assert "<svg" in page


def test_the_site_records_design_findings(tmp_path):
    project = load_project(str(SAMPLE))
    project.cables.append(
        __import__("linklab.models", fromlist=["Cable"]).Cable(
            id="C-BAD",
            a_end="SR01.PP1.01",
            b_end="SR01.SW1.Gi1/0/1",
            length_m=5.0,
        )
    )
    findings = validate_project(project)
    summary = build_docs(project, str(tmp_path), findings)
    assert summary["errors"] >= 1
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Design findings" in index
    assert "port-used-twice" in index


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_budget_fibre_exits_zero_on_pass(capsys):
    code = main(
        [
            "budget", "fiber",
            "--length", "42", "--fibre", "smf",
            "--tx", "5", "--rx", "-28",
            "--bitrate", "10", "--spectral-width", "0.05",
            "--splices", "8", "--connectors", "6", "--margin", "3",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "verdict      PASS" in out
    assert "19.100 dB" in out


def test_cli_budget_copper_exits_one_on_fail(capsys):
    code = main(
        [
            "budget", "copper",
            "--length", "105", "--category", "cat6",
            "--pairs", "4", "--application", "10gbase-t",
        ]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "verdict      FAIL" in out
    assert "90 m channel limit" in out


def test_cli_budget_microwave(capsys):
    code = main(
        [
            "budget", "microwave",
            "--length", "5", "--freq", "15",
            "--tx", "20", "--tx-gain", "30", "--rx-gain", "30",
            "--rx-threshold", "-80",
        ]
    )
    assert code == 0
    # FSPL over 5 km at 15 GHz = 129.941 dB
    assert "129.941 dB" in capsys.readouterr().out


def test_cli_budget_json_output(capsys):
    main(["budget", "fiber", "--length", "12", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "PASS"
    # 12 km at 0.25 dB/km = 3.00 dB of fibre, plus the default 2 connector
    # pairs at 0.50 dB = 1.00 dB. No splices by default.
    assert data["total_loss_db"] == pytest.approx(4.0, abs=0.01)


def test_cli_project_validate(capsys):
    code = main(["project", "validate", str(SAMPLE)])
    assert code == 0
    assert "internally consistent" in capsys.readouterr().out


def test_cli_docs_build(tmp_path, capsys):
    out = tmp_path / "site"
    code = main(["docs", "build", str(SAMPLE), "--out", str(out)])
    assert code == 0
    assert (out / "index.html").exists()
    assert "Wrote" in capsys.readouterr().out


def test_cli_docs_refuses_a_project_with_errors(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    data["cables"].append(
        {
            "id": "C-BAD",
            "a_end": "SR01.PP1.01",
            "b_end": "SR01.SW1.Gi1/0/1",
            "media": "cat6",
            "length_m": 5.0,
        }
    )
    broken.write_text(json.dumps(data), encoding="utf-8")
    code = main(["docs", "build", str(broken), "--out", str(tmp_path / "site2")])
    assert code == 1
    assert not (tmp_path / "site2" / "index.html").exists()
    assert "design errors" in capsys.readouterr().err
