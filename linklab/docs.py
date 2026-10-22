"""Static documentation generator.

Turns a validated project into a small website: a summary, the cable
schedule, the link budgets, and a rack elevation for every rack with its
cables drawn in.

Written with the standard library only, on purpose. A documentation tool that
needs a web framework to produce a folder of HTML is a tool nobody will run
on a site visit.
"""

import html
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .budget import (
    Optics,
    compute_copper_budget,
    compute_fiber_budget,
    compute_microwave_budget,
)
from .media import COPPER_TYPES, FIBRE_TYPES
from .models import Project
from .project import Finding, has_errors

#: Vertical size of one rack unit in the elevation drawing, in pixels.
U_HEIGHT_PX = 18
#: Height of the drawing area below the rack, for the cable fan-out.
FANOUT_PX = 120
#: Width of the rack itself in the drawing.
RACK_WIDTH_PX = 110

STYLE = """
:root {
  --ink: #16202b;
  --muted: #5b6b7c;
  --line: #dde5ec;
  --accent: #0b6ea8;
  --accent-soft: #e8f2f9;
  --ok: #1a7f4b;
  --ok-soft: #e6f4ec;
  --bad: #b3261e;
  --bad-soft: #fbeae9;
  --warn: #8a5a00;
  --warn-soft: #fdf3e0;
  --bg: #f6f8fa;
  --panel: #ffffff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: var(--ink);
  background: var(--bg);
}
.wrap { max-width: 1120px; margin: 0 auto; padding: 32px 24px 72px; }
header.top { border-bottom: 1px solid var(--line); background: var(--panel); }
header.top .wrap { padding-top: 28px; padding-bottom: 24px; }
h1 { font-size: 26px; margin: 0 0 6px; letter-spacing: -0.01em; }
h2 { font-size: 19px; margin: 34px 0 12px; letter-spacing: -0.01em; }
h3 { font-size: 15px; margin: 22px 0 8px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
p.sub { color: var(--muted); margin: 0; }
nav.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 18px; }
nav.tabs a {
  display: inline-block; padding: 7px 14px; border-radius: 7px;
  text-decoration: none; color: var(--muted); font-weight: 500; font-size: 14px;
  border: 1px solid transparent;
}
nav.tabs a:hover { background: var(--accent-soft); color: var(--accent); }
nav.tabs a.active { background: var(--accent); color: #fff; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; margin: 14px 0; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
tr:last-child td { border-bottom: none; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
code, .mono { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; font-size: 13px; }
.pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.pill.ok { background: var(--ok-soft); color: var(--ok); }
.pill.bad { background: var(--bad-soft); color: var(--bad); }
.pill.warn { background: var(--warn-soft); color: var(--warn); }
.stats { display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0 4px; }
.stat { flex: 1 1 150px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.stat .v { font-size: 24px; font-weight: 650; letter-spacing: -0.02em; }
.stat .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
.finding { border-left: 3px solid var(--bad); background: var(--bad-soft); padding: 10px 14px; border-radius: 0 8px 8px 0; margin: 8px 0; font-size: 14px; }
.finding.warn { border-left-color: var(--warn); background: var(--warn-soft); }
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line); margin: 18px 0 0; }
.tabs button { border: 0; background: none; padding: 9px 14px; font: inherit; font-size: 14px; color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent; }
.tabs button.on { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.tabs button:hover { color: var(--accent); }
pre { background: var(--ink); color: #e6edf3; padding: 14px 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; }
footer { color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); margin-top: 40px; padding-top: 18px; }
a { color: var(--accent); }
"""

SCRIPT = """
document.querySelectorAll('[data-tabs]').forEach(function (group) {
  var buttons = group.querySelectorAll('button');
  var panels = document.querySelectorAll('[data-panel="' + group.dataset.tabs + '"]');
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      buttons.forEach(function (x) { x.classList.remove('on'); });
      panels.forEach(function (p) { p.hidden = true; });
      b.classList.add('on');
      var target = document.querySelector('[data-panel="' + group.dataset.tabs + '-' + b.dataset.target + '"]');
      if (target) { target.hidden = false; }
    });
  });
});
"""


def esc(value) -> str:
    """HTML-escape a value."""
    return html.escape(str(value), quote=True)


def _page(project: Project, title: str, active: str, body: str) -> str:
    tabs = [
        ("index.html", "Overview"),
        ("schedule.html", "Cable schedule"),
        ("links.html", "Link budgets"),
    ]
    nav = "".join(
        f'<a href="{href}" class="{"active" if href == active else ""}">{esc(label)}</a>'
        for href, label in tabs
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} &middot; {esc(project.name)}</title>
<style>{STYLE}</style>
</head>
<body>
<header class="top"><div class="wrap">
<h1>{esc(project.name)}</h1>
<p class="sub">{esc(project.client)}{" &middot; " if project.client else ""}{esc(project.site)}{" &middot; " if project.site else ""}{esc(project.date)}</p>
<nav class="tabs">{nav}</nav>
</div></header>
<div class="wrap">
{body}
<footer>Generated by LinkLab. Every figure on this site is produced by the
engine in this repository, and every formula it uses is covered by a test.</footer>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""


def _pill(verdict: str) -> str:
    cls = "ok" if verdict == "PASS" else "bad"
    return f'<span class="pill {cls}">{esc(verdict)}</span>'


def _rack_filename(rack_id: str) -> str:
    """The file name - and the href - of a rack page.

    Only the bare name of the id is used. Rack ids are validated
    (``invalid-rack-id``), but ``--force`` documents a flagged project
    anyway, so a hostile id such as ``../../evil`` or an absolute path must
    not be able to move the page out of ``out/racks``.
    """
    return f"{Path(rack_id).name}.html"


def _cable_row(project: Project, cable) -> str:
    try:
        if cable.media in COPPER_TYPES:
            pairs = 4
            budget = compute_copper_budget(
                max(cable.length_m, 0.01), cable.media, pairs=pairs, application="1gbase-t"
            )
            verdict = budget.verdict
            detail = (
                f"{budget.insertion_loss_db:.2f} dB insertion, "
                f"{budget.derating_db:.1f} dB derating, "
                f"{budget.ps_next_penalty_db:.1f} dB PS-NEXT"
            )
            limit = f"{budget.channel_max_m:.0f} m channel"
        else:
            optics = Optics(tx_power_dbm=2.0, rx_sensitivity_dbm=-28.0)
            budget = compute_fiber_budget(
                max(cable.length_m / 1000.0, 0.001), cable.media, optics
            )
            verdict = budget.verdict
            detail = (
                f"{budget.fiber_loss_db:.2f} dB fibre, "
                f"{budget.splice_loss_db:.2f} dB splices, "
                f"{budget.connector_loss_db:.2f} dB connectors"
            )
            limit = f"{budget.max_reach_km:.1f} km reach"
    except ValueError as exc:
        # --force documents a flagged project, so a budget the engine
        # refuses to compute (unknown media, a nonsense length) is written
        # as a fail row instead of aborting the whole site.
        verdict = "FAIL"
        detail = f"budget could not be computed: {exc}"
        limit = ""
    working = f"{esc(detail)} &middot; {esc(limit)}" if limit else esc(detail)
    return (
        f"<tr><td class='mono'>{esc(cable.id)}</td>"
        f"<td>{esc(project.describe_endpoint(cable.a_end))}</td>"
        f"<td>{esc(project.describe_endpoint(cable.b_end))}</td>"
        f"<td class='mono'>{esc(cable.media)}</td>"
        f"<td class='num'>{cable.length_m:.1f} m</td>"
        f"<td>{_pill(verdict)}</td>"
        f"<td class='small muted'>{working}</td></tr>"
    )


def _span_rows(project: Project) -> str:
    rows = []
    for span in project.optical_spans:
        optics = Optics(
            tx_power_dbm=span.tx_power_dbm,
            rx_sensitivity_dbm=span.rx_sensitivity_dbm,
            wavelength_nm=1550,
            bitrate_gbps=span.bitrate_gbps,
            spectral_width_nm=span.spectral_width_nm,
            splice_count=span.splice_count,
            connector_pairs=span.connector_pairs,
            required_margin_db=span.required_margin_db,
        )
        try:
            b = compute_fiber_budget(span.length_km, span.fibre, optics)
            detail = (
                f"{b.fiber_loss_db:.2f} dB fibre, {b.splice_loss_db:.2f} dB splices, "
                f"{b.connector_loss_db:.2f} dB connectors"
            )
            extra = ""
            if b.dispersion_limit_km is not None:
                extra = (
                    f"; dispersion limit {b.dispersion_limit_km:.1f} km, "
                    f"penalty {b.dispersion_penalty_db:.2f} dB"
                )
            margin = f"{b.margin_db:.2f} dB"
            verdict = b.verdict
        except ValueError as exc:
            # Same story as _cable_row: under --force a budget the engine
            # refuses to compute renders as a failure, not as a crash.
            margin = "&mdash;"
            verdict = "FAIL"
            detail = f"budget could not be computed: {exc}"
            extra = ""
        rows.append(
            f"<tr><td class='mono'>{esc(span.id)}</td>"
            f"<td>{esc(span.a_end)}</td><td>{esc(span.b_end)}</td>"
            f"<td class='mono'>{esc(span.fibre)}</td>"
            f"<td class='num'>{span.length_km:.2f} km</td>"
            f"<td class='num'>{margin}</td>"
            f"<td>{_pill(verdict)}</td>"
            f"<td class='small muted'>{esc(detail)}{esc(extra)}</td></tr>"
        )
    return "".join(rows)


def _rack_elevation_svg(project: Project, rack) -> str:
    """Draw one rack: the panels in it, and every cable leaving it.

    The drawing is two columns. On the left the rack itself, to scale in rack
    units. On the right a "cable ladder" with one row per cable, so no two
    labels can ever land on top of each other - the failure mode of a naive
    drawing where every cable is labelled where it leaves the port.
    """
    u = rack.u_height
    height = u * U_HEIGHT_PX
    top = 44
    base_y = top + height
    rack_x = 30
    rack_w = 120
    ladder_x = 340
    label_x = 352

    def touches_rack(cable) -> bool:
        for end in (cable.a_end, cable.b_end):
            panel = project.port_owner(end)
            if panel is not None and panel.rack_id == rack.id:
                return True
        return False

    cables_here = [c for c in project.cables if touches_rack(c)]
    ladder_h = max(len(cables_here), 1) * 19 + 16
    legend_y = base_y + ladder_h + 34
    width = 940

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {legend_y + 34}" '
        f'width="100%" role="img" aria-label="Rack elevation for {esc(rack.name)}">',
        f'<rect x="{rack_x}" y="{top}" width="{rack_w}" height="{height}" rx="6" '
        f'fill="#ffffff" stroke="#b9c6d2" stroke-width="1.5"/>',
    ]

    for i in range(1, u + 1):
        y = base_y - i * U_HEIGHT_PX
        parts.append(
            f'<line x1="{rack_x}" y1="{y:.1f}" x2="{rack_x + rack_w}" y2="{y:.1f}" '
            f'stroke="#eef2f6" stroke-width="1"/>'
        )
        if u <= 14 or i % 2 == 1:
            parts.append(
                f'<text x="{rack_x - 6}" y="{y + 4:.1f}" font-size="8.5" fill="#93a3b1" '
                f'text-anchor="end">U{i}</text>'
            )

    def panel_y(panel) -> float:
        return base_y - (panel.u_position - 1 + panel.u_height) * U_HEIGHT_PX

    # panels, drawn in the rack
    for panel in rack.panels:
        y = panel_y(panel)
        h = panel.u_height * U_HEIGHT_PX
        fill = kind_fill_for(panel.kind)
        parts.append(
            f'<rect x="{rack_x + 4}" y="{y + 1:.1f}" width="{rack_w - 8}" height="{h - 2:.1f}" '
            f'rx="3" fill="{fill}" stroke="#b9c6d2" stroke-width="1">'
            f"<title>{esc(panel.name)} - {esc(panel.kind)} - U{panel.u_position} - "
            f"{len(panel.ports)} ports</title></rect>"
        )
        short = panel.name if len(panel.name) <= 16 else panel.name[:15] + "…"
        parts.append(
            f'<text x="{rack_x + 11}" y="{y + 13:.1f}" font-size="9.5" fill="#16202b" '
            f'font-weight="600">{esc(short)}</text>'
        )
        parts.append(
            f'<text x="{rack_x + 11}" y="{y + 23:.1f}" font-size="8" fill="#5b6b7c">'
            f"{esc(panel.kind)} · {len(panel.ports)} ports</text>"
        )
        parts.append(
            f'<text x="{rack_x + rack_w - 8}" y="{y + 13:.1f}" font-size="8" fill="#5b6b7c" '
            f'text-anchor="end">U{panel.u_position}</text>'
        )

    # the cable ladder
    palette = [
        "#0b6ea8", "#1a7f4b", "#b3261e", "#8a5a00",
        "#6a3d9a", "#0f766e", "#9a3412", "#4338ca",
    ]
    for index, cable in enumerate(cables_here):
        row_y = base_y + 26 + index * 19
        colour = palette[index % len(palette)]
        origins = []
        for end in (cable.a_end, cable.b_end):
            panel = project.port_owner(end)
            if panel is None or panel.rack_id != rack.id:
                continue
            py = panel_y(panel) + (panel.u_height * U_HEIGHT_PX) / 2
            origins.append((py, end))
        if not origins:
            continue
        for py, end in origins:
            parts.append(
                f'<path d="M {rack_x + rack_w} {py:.1f} C {rack_x + rack_w + 60} {py:.1f}, '
                f'{ladder_x - 60} {row_y:.1f}, {ladder_x} {row_y:.1f}" fill="none" '
                f'stroke="{colour}" stroke-width="1.4" opacity="0.9"/>'
            )
            parts.append(
                f'<circle cx="{rack_x + rack_w}" cy="{py:.1f}" r="2.8" fill="{colour}"/>'
            )
        far = cable.b_end if origins[-1][1] == cable.a_end else cable.a_end
        far_text = project.describe_endpoint(far)
        port_text = origins[-1][1].split(".")[2]
        if len(far_text) > 74:
            far_text = far_text[:73] + "…"
        parts.append(
            f'<circle cx="{ladder_x + 4}" cy="{row_y:.1f}" r="3.2" fill="{colour}"/>'
        )
        parts.append(
            f'<text x="{label_x}" y="{row_y + 3.5:.1f}" font-size="10" fill="#3b4b5a">'
            f'<tspan font-weight="600">{esc(cable.id)}</tspan> '
            f'<tspan fill="#6b7b8a">port {esc(port_text)} &rarr; {esc(far_text)}</tspan></text>'
        )

    # legend
    legend: List[str] = []
    for index, panel in enumerate(rack.panels):
        col = index % 4
        row = index // 4
        lx = 30 + col * 225
        ly = legend_y + row * 20
        legend.append(
            f'<rect x="{lx}" y="{ly - 8}" width="10" height="10" rx="2" '
            f'fill="{kind_fill_for(panel.kind)}" stroke="#b9c6d2"/>'
            f'<text x="{lx + 15}" y="{ly}" font-size="10" fill="#3b4b5a">'
            f"{esc(panel.name)}</text>"
        )
    parts.extend(legend)
    parts.append("</svg>")
    return "".join(parts)


def kind_fill_for(kind: str) -> str:
    return {
        "patch": "#e8f2f9",
        "odf": "#f3ecfb",
        "switch": "#e6f4ec",
        "router": "#fdf3e0",
        "active": "#fbeae9",
    }.get(kind, "#eef2f6")


def build_docs(
    project: Project,
    out_dir: str,
    findings: Optional[List[Finding]] = None,
) -> Dict:
    """Write the documentation site for ``project`` into ``out_dir``.

    Returns a summary dict with the files written and the headline numbers.
    """
    out = Path(out_dir)
    (out / "racks").mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    (out / "assets" / "style.css").write_text(STYLE, encoding="utf-8")
    (out / "assets" / "app.js").write_text(SCRIPT, encoding="utf-8")

    findings = findings if findings is not None else []
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    cables_pass = 0
    cables_total = 0
    for cable in project.cables:
        cables_total += 1
        try:
            if cable.media in COPPER_TYPES:
                b = compute_copper_budget(
                    max(cable.length_m, 0.01), cable.media, 4, "1gbase-t"
                )
            else:
                b = compute_fiber_budget(
                    max(cable.length_m / 1000.0, 0.001),
                    cable.media,
                    Optics(tx_power_dbm=2.0, rx_sensitivity_dbm=-28.0),
                )
        except ValueError:
            # Mirrors _cable_row: a budget the engine refuses to compute is
            # not a PASS and not a crash.
            continue
        if b.verdict == "PASS":
            cables_pass += 1

    spans_pass = 0
    for span in project.optical_spans:
        try:
            b = compute_fiber_budget(
                span.length_km,
                span.fibre,
                Optics(
                    tx_power_dbm=span.tx_power_dbm,
                    rx_sensitivity_dbm=span.rx_sensitivity_dbm,
                    bitrate_gbps=span.bitrate_gbps,
                    spectral_width_nm=span.spectral_width_nm,
                    splice_count=span.splice_count,
                    connector_pairs=span.connector_pairs,
                    required_margin_db=span.required_margin_db,
                ),
            )
        except ValueError:
            # Mirrors _span_rows: a budget the engine refuses to compute is
            # not a PASS and not a crash.
            continue
        if b.verdict == "PASS":
            spans_pass += 1

    ports = sum(len(p.ports) for r in project.racks for p in r.panels)

    # ---- overview ------------------------------------------------------
    finding_html = ""
    if findings:
        rows = "".join(
            f'<div class="finding{" warn" if f.severity == "warning" else ""}">'
            f"<strong>{esc(f.code)}</strong> &mdash; {esc(f.message)}"
            f"{' (' + esc(f.where) + ')' if f.where else ''}</div>"
            for f in findings
        )
        finding_html = f"<h2>Design findings</h2>{rows}"

    body = f"""
<div class="stats">
  <div class="stat"><div class="v">{len(project.racks)}</div><div class="k">Racks</div></div>
  <div class="stat"><div class="v">{ports}</div><div class="k">Ports</div></div>
  <div class="stat"><div class="v">{cables_total}</div><div class="k">Cables</div></div>
  <div class="stat"><div class="v">{cables_pass}</div><div class="k">Cables within budget</div></div>
  <div class="stat"><div class="v">{len(project.optical_spans)}</div><div class="k">Optical spans</div></div>
  <div class="stat"><div class="v">{spans_pass}</div><div class="k">Spans within budget</div></div>
</div>
{finding_html}
<h2>Racks</h2>
<div class="card"><table>
<thead><tr><th>Rack</th><th>Location</th><th class="num">Height</th><th class="num">Panels</th><th>Elevation</th></tr></thead>
<tbody>
{''.join(
    f"<tr><td><a href='racks/{esc(_rack_filename(r.id))}'>{esc(r.name)}</a></td>"
    f"<td class='muted'>{esc(r.location)}</td>"
    f"<td class='num'>{r.u_height}U</td>"
    f"<td class='num'>{len(r.panels)}</td>"
    f"<td><a href='racks/{esc(_rack_filename(r.id))}'>view drawing &rarr;</a></td></tr>"
    for r in project.racks
)}
</tbody></table></div>
<h2>What this site is</h2>
<div class="card"><p class="small muted">Every number here was produced by the
LinkLab engine from the project file, not typed by hand. The formulas and the
standards they come from are documented in the repository, and the test suite
checks each one against a hand-computed value. The optical budget deliberately
contains <strong>no free-space path loss term</strong>: FSPL describes radio
propagation through air and does not apply to light inside a glass core.</p></div>
"""
    (out / "index.html").write_text(
        _page(project, "Overview", "index.html", body), encoding="utf-8"
    )

    # ---- cable schedule ------------------------------------------------
    rows = "".join(
        f"<tr><td class='mono'>{esc(c.id)}</td>"
        f"<td>{esc(project.describe_endpoint(c.a_end))}</td>"
        f"<td>{esc(project.describe_endpoint(c.b_end))}</td>"
        f"<td class='mono'>{esc(c.media)}</td>"
        f"<td class='num'>{c.length_m:.1f} m</td>"
        f"<td class='muted small'>{esc(c.label)}</td></tr>"
        for c in project.cables
    )
    body = f"""
<h2>Cable schedule</h2>
<div class="card"><table>
<thead><tr><th>ID</th><th>A end</th><th>B end</th><th>Media</th><th class="num">Length</th><th>Label</th></tr></thead>
<tbody>{rows}</tbody></table></div>
"""
    (out / "schedule.html").write_text(
        _page(project, "Cable schedule", "schedule.html", body), encoding="utf-8"
    )

    # ---- link budgets --------------------------------------------------
    body = f"""
<h2>Cable budgets</h2>
<div class="card"><table>
<thead><tr><th>ID</th><th>A end</th><th>B end</th><th>Media</th><th class="num">Length</th><th>Verdict</th><th>Working</th></tr></thead>
<tbody>{''.join(_cable_row(project, c) for c in project.cables)}</tbody></table></div>
<h2>Optical span budgets</h2>
<div class="card"><table>
<thead><tr><th>ID</th><th>A end</th><th>B end</th><th>Fibre</th><th class="num">Length</th><th class="num">Margin</th><th>Verdict</th><th>Working</th></tr></thead>
<tbody>{_span_rows(project)}</tbody></table></div>
"""
    (out / "links.html").write_text(
        _page(project, "Link budgets", "links.html", body), encoding="utf-8"
    )

    # ---- rack elevations ------------------------------------------------
    for rack in project.racks:
        svg = _rack_elevation_svg(project, rack)
        cable_by_port: Dict[str, str] = {}
        for c in project.cables:
            for end in (c.a_end, c.b_end):
                panel = project.port_owner(end)
                if panel is not None and panel.rack_id == rack.id:
                    cable_by_port[end] = c.id
        panels = ""
        for p in rack.panels:
            port_rows = ""
            for port in p.ports:
                endpoint = f"{rack.id}.{p.id}.{port}"
                cable_id = cable_by_port.get(endpoint, "")
                far = ""
                if cable_id:
                    cable = next((c for c in project.cables if c.id == cable_id), None)
                    if cable is not None:
                        other = (
                            cable.b_end if endpoint == cable.a_end else cable.a_end
                        )
                        far = project.describe_endpoint(other)
                port_rows += (
                    f"<tr><td class='mono'>{esc(port)}</td>"
                    f"<td class='mono'>{esc(cable_id)}</td>"
                    f"<td class='muted small'>{esc(far)}</td></tr>"
                )
            panels += (
                f"<tr><td class='mono'>{esc(p.id)}</td><td>{esc(p.name)}</td>"
                f"<td class='muted'>{esc(p.kind)}</td>"
                f"<td class='num'>U{p.u_position}</td>"
                f"<td class='num'>{len(p.ports)}</td>"
                f"<td class='muted small'>{esc(p.model)}</td></tr>"
            )
        port_table = ""
        for p in rack.panels:
            endpoint = f"{rack.id}.{p.id}"
            rows = ""
            for port in p.ports:
                ep = f"{endpoint}.{port}"
                cid = cable_by_port.get(ep, "")
                far = ""
                if cid:
                    cable = next((c for c in project.cables if c.id == cid), None)
                    if cable is not None:
                        other = cable.b_end if ep == cable.a_end else cable.a_end
                        far = project.describe_endpoint(other)
                rows += (
                    f"<tr><td class='mono'>{esc(port)}</td>"
                    f"<td class='mono'>{esc(cid or '—')}</td>"
                    f"<td class='muted small'>{esc(far)}</td></tr>"
                )
            if rows:
                port_table += (
                    f"<h3>{esc(p.name)}</h3><table>"
                    f"<thead><tr><th>Port</th><th>Cable</th><th>Far end</th></tr></thead>"
                    f"<tbody>{rows}</tbody></table>"
                )
        body = f"""
<h2>{esc(rack.name)}</h2>
<p class="muted small">{esc(rack.location)} &middot; {rack.u_height}U</p>
<div class="card">{svg}</div>
<h2>Panels</h2>
<div class="card"><table>
<thead><tr><th>ID</th><th>Name</th><th>Kind</th><th class="num">Position</th><th class="num">Ports</th><th>Model</th></tr></thead>
<tbody>{panels}</tbody></table></div>
<h2>Port map</h2>
{port_table}
"""
        # The rack page is written where the id says. Ids are validated
        # (invalid-rack-id), but --force documents a flagged project anyway,
        # so this write also guards itself: only the bare name of the id is
        # used and the resolved path must land in out/racks, so a relative
        # or absolute id can at worst rename the page inside the site.
        rack_page = out / "racks" / _rack_filename(rack.id)
        if rack_page.resolve().parent != (out / "racks").resolve():
            raise ValueError(f"rack id {rack.id} is not a safe file name")
        rack_page.write_text(
            _page(project, f"Rack {rack.name}", "", body), encoding="utf-8"
        )

    written = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    return {
        "files": written,
        "racks": len(project.racks),
        "cables": cables_total,
        "cables_pass": cables_pass,
        "spans": len(project.optical_spans),
        "spans_pass": spans_pass,
        "errors": len(errors),
        "warnings": len(warnings),
    }
