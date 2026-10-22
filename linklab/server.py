"""Web UI.

Optional: needs FastAPI and uvicorn (``pip install 'linklab[web]'``). The
engine itself never imports this module, so the core stays dependency-free.

Three things the web UI adds over the command line:

* a form that computes a budget as you type, with the working shown line by
  line rather than a single pass/fail;
* the project on screen, with every cable's verdict and the design findings;
* a link-budget calculator that fills the form with the project's own optics
  when you click a span.
"""

import json
from typing import Any, Dict, List, Optional

from .budget import (
    Optics,
    compute_copper_budget,
    compute_fiber_budget,
    compute_microwave_budget,
)
from .media import COPPER_TYPES, FIBRE_TYPES
from .project import load_project, validate_project
from .units import fspl_db


def _number(body: Dict[str, Any], key: str, default: float) -> float:
    """A number from the request body, or the default when it is absent.

    The shipped form sends ``null`` for every field the user left blank
    (blank means "unknown"), and ``float(None)`` would raise TypeError and
    land on the client as an HTTP 500. An explicitly null field therefore
    counts as omitted.
    """
    value = body.get(key, default)
    if value is None:
        return default
    return float(value)


def _fibre_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    optics = Optics(
        tx_power_dbm=_number(body, "tx_power_dbm", 0.0),
        rx_sensitivity_dbm=_number(body, "rx_sensitivity_dbm", -28.0),
        wavelength_nm=int(_number(body, "wavelength_nm", 1550)),
        bitrate_gbps=(_number(body, "bitrate_gbps", 0.0) or None),
        spectral_width_nm=_number(body, "spectral_width_nm", 0.1),
        splice_count=int(_number(body, "splice_count", 0)),
        connector_pairs=int(_number(body, "connector_pairs", 2)),
        required_margin_db=_number(body, "required_margin_db", 0.0),
    )
    result = compute_fiber_budget(
        _number(body, "length_km", 1.0),
        str(body.get("fibre", "smf")),
        optics,
    )
    return result.to_dict()


def _microwave_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    result = compute_microwave_budget(
        length_km=_number(body, "length_km", 1.0),
        frequency_ghz=_number(body, "frequency_ghz", 15.0),
        tx_power_dbm=_number(body, "tx_power_dbm", 20.0),
        tx_antenna_gain_dbi=_number(body, "tx_antenna_gain_dbi", 0.0),
        rx_antenna_gain_dbi=_number(body, "rx_antenna_gain_dbi", 30.0),
        rx_threshold_dbm=_number(body, "rx_threshold_dbm", -80.0),
        feeder_loss_tx_db=_number(body, "feeder_loss_tx_db", 0.5),
        feeder_loss_rx_db=_number(body, "feeder_loss_rx_db", 0.5),
        rain_fade_allowance_db=_number(body, "rain_fade_allowance_db", 0.0),
        required_margin_db=_number(body, "required_margin_db", 10.0),
    )
    return result.to_dict()


def _copper_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    result = compute_copper_budget(
        length_m=_number(body, "length_m", 10.0),
        category=str(body.get("category", "cat6")),
        pairs=int(_number(body, "pairs", 4)),
        application=str(body.get("application", "1gbase-t")),
    )
    return result.to_dict()


def build_app(project_path: str):
    """Build the FastAPI application for a given project file."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import FileResponse, JSONResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "The web UI needs FastAPI and uvicorn: pip install 'linklab[web]'"
        ) from exc

    import pathlib

    here = pathlib.Path(__file__).parent
    app = FastAPI(title="LinkLab", version="1.0.0")

    @app.get("/api/project")
    def api_project() -> JSONResponse:
        project = load_project(project_path)
        findings = validate_project(project)
        return JSONResponse(
            {
                "name": project.name,
                "client": project.client,
                "site": project.site,
                "racks": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "location": r.location,
                        "u_height": r.u_height,
                        "panels": [
                            {
                                "id": p.id,
                                "name": p.name,
                                "kind": p.kind,
                                "u_position": p.u_position,
                                "ports": p.ports,
                                "model": p.model,
                            }
                            for p in r.panels
                        ],
                    }
                    for r in project.racks
                ],
                "cables": [
                    {
                        "id": c.id,
                        "a_end": project.describe_endpoint(c.a_end),
                        "b_end": project.describe_endpoint(c.b_end),
                        "a_raw": c.a_end,
                        "b_raw": c.b_end,
                        "media": c.media,
                        "length_m": c.length_m,
                        "label": c.label,
                    }
                    for c in project.cables
                ],
                "spans": [
                    {
                        "id": s.id,
                        "a_end": s.a_end,
                        "b_end": s.b_end,
                        "length_km": s.length_km,
                        "fibre": s.fibre,
                        "tx_power_dbm": s.tx_power_dbm,
                        "rx_sensitivity_dbm": s.rx_sensitivity_dbm,
                        "bitrate_gbps": s.bitrate_gbps,
                        "spectral_width_nm": s.spectral_width_nm,
                        "splice_count": s.splice_count,
                        "connector_pairs": s.connector_pairs,
                        "required_margin_db": s.required_margin_db,
                    }
                    for s in project.optical_spans
                ],
                "findings": [
                    {
                        "severity": f.severity,
                        "code": f.code,
                        "message": f.message,
                        "where": f.where,
                    }
                    for f in findings
                ],
            }
        )

    @app.post("/api/budget")
    async def api_budget(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            # A JSON body that is not an object has no medium to name: that
            # is a client error, not a traceback.
            return JSONResponse(
                {"error": "the request body must be a JSON object"},
                status_code=400,
            )
        medium = str(body.get("medium", "fiber"))
        try:
            if medium == "microwave":
                data = _microwave_payload(body)
            elif medium == "copper":
                data = _copper_payload(body)
            elif medium == "fiber":
                data = _fibre_payload(body)
            else:
                return JSONResponse(
                    {"error": f"unknown medium: {medium}"}, status_code=400
                )
        except (ValueError, TypeError, KeyError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(data)

    @app.get("/api/reference")
    def api_reference() -> JSONResponse:
        return JSONResponse(
            {
                "fibres": {
                    k: {
                        "label": v.label,
                        "attenuation": v.attenuation_db_per_km,
                        "dispersion": v.dispersion_ps_nm_km,
                        "modal_bandwidth": v.modal_bandwidth_mhz_km,
                    }
                    for k, v in FIBRE_TYPES.items()
                },
                "copper": {
                    k: {
                        "label": v.label,
                        "channel_max_m": v.channel_max_m,
                        "permanent_link_max_m": v.permanent_link_max_m,
                        "max_insertion_loss_db": v.max_insertion_loss_db,
                        "spec_frequency_mhz": v.spec_frequency_mhz,
                    }
                    for k, v in COPPER_TYPES.items()
                },
                "fspl_example": {
                    "1km_1GHz": round(fspl_db(1.0, 1.0e9), 2),
                    "100m_1550nm": round(fspl_db(0.1, 193.1e12), 2),
                },
            }
        )

    @app.get("/favicon.svg")
    def favicon() -> FileResponse:
        return FileResponse(here / "static" / "favicon.svg", media_type="image/svg+xml")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(here / "static" / "index.html")

    app.mount(
        "/static", StaticFiles(directory=str(here / "static")), name="static"
    )
    return app


def serve(
    project_path: str, host: str = "127.0.0.1", port: int = 8080
) -> None:  # pragma: no cover - process entry point
    import uvicorn

    uvicorn.run(build_app(project_path), host=host, port=port, log_level="info")
