"""Web-UI tests.

The web UI is the optional ``web`` extra; where fastapi is not installed
the whole file skips rather than pretending to test. The transport-level
assertions run through ``fastapi.testclient`` when that is usable, and
fall back to driving the ASGI application directly, because the packaged
TestClient needs httpx2 on top of fastapi and a checkout may carry the
``web`` extra without it.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from linklab import server  # noqa: E402  (import guarded by the skip above)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples/site-atlas-telecom/project.json"


class _ASGIResponse:
    """The two things the tests need from a TestClient response."""

    def __init__(self, status_code: int, raw: bytes):
        self.status_code = status_code
        self._raw = raw

    def json(self):
        return json.loads(self._raw) if self._raw else None


class _ASGIDriver:
    """Call the ASGI application directly, without a test HTTP stack.

    The app is driven with a plain scope, receive and send over asyncio; an
    exception escaping the middleware stack is reported as a 500, exactly
    as a server would present it.
    """

    def __init__(self, app):
        self.app = app

    def _call(self, method: str, path: str, payload=None):
        import asyncio

        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        headers = [(b"content-length", str(len(body)).encode("ascii"))]
        if body:
            headers.insert(0, (b"content-type", b"application/json"))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "server": ("testserver", 80),
            "client": ("test", 0),
        }
        sent = []
        state = {"received": False}

        async def receive():
            if not state["received"]:
                state["received"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        try:
            asyncio.run(self.app(scope, receive, send))
        except Exception:
            return 500, b"Internal Server Error"
        status = next(m for m in sent if m["type"] == "http.response.start")["status"]
        raw = b"".join(
            m.get("body", b"") for m in sent if m["type"] == "http.response.body"
        )
        return status, raw

    def get(self, path: str) -> _ASGIResponse:
        status, raw = self._call("GET", path)
        return _ASGIResponse(status, raw)

    def post(self, path: str, json=None) -> _ASGIResponse:
        status, raw = self._call("POST", path, json)
        return _ASGIResponse(status, raw)


def _client():
    """Prefer the packaged TestClient; speak raw ASGI to the app otherwise."""
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError):
        # starlette's test client demands httpx2, which this checkout does
        # not carry even though fastapi itself is installed.
        return _ASGIDriver(server.build_app(str(SAMPLE)))
    return TestClient(server.build_app(str(SAMPLE)))


# ---------------------------------------------------------------------------
# /api/budget
# ---------------------------------------------------------------------------


def test_the_budget_endpoint_computes_the_fibre_budget():
    http = _client()
    r = http.post("/api/budget", json={"medium": "fiber", "length_km": 12})
    assert r.status_code == 200
    data = r.json()
    # The CLI's own defaults: 12 km of SMF at 0.25 dB/km plus the default
    # two connector pairs at 0.50 dB, against a 28 dB optical budget.
    assert data["total_loss_db"] == pytest.approx(4.0, abs=0.01)
    assert data["margin_db"] == pytest.approx(24.0, abs=0.01)
    assert data["verdict"] == "PASS"


def test_the_budget_endpoint_computes_the_microwave_budget():
    http = _client()
    r = http.post(
        "/api/budget",
        json={
            "medium": "microwave",
            "length_km": 5,
            "frequency_ghz": 15,
            "tx_power_dbm": 20,
            "tx_antenna_gain_dbi": 30,
            "rx_antenna_gain_dbi": 30,
            "rx_threshold_dbm": -80,
        },
    )
    assert r.status_code == 200
    data = r.json()
    # FSPL over 5 km at 15 GHz is 129.94 dB, the published textbook figure.
    assert data["fspl_db"] == pytest.approx(129.94, abs=0.01)
    assert data["margin_db"] == pytest.approx(29.06, abs=0.02)
    assert data["verdict"] == "PASS"


def test_the_budget_endpoint_computes_the_copper_budget():
    http = _client()
    r = http.post("/api/budget", json={"medium": "copper", "length_m": 80})
    assert r.status_code == 200
    data = r.json()
    # Cat6, four pairs, gigabit at 80 m: 17.12 dB insertion + 3.60 dB PS-NEXT.
    assert data["total_budget_db"] == pytest.approx(20.72, abs=0.01)
    assert data["verdict"] == "PASS"


def test_an_unknown_medium_is_a_400():
    http = _client()
    r = http.post("/api/budget", json={"medium": "wireless"})
    assert r.status_code == 400
    assert "medium" in r.json()["error"]


def test_a_cleared_field_is_treated_as_omitted_not_as_a_500():
    # The shipped form sends null for every blank field; the payload must
    # fall back to the same defaults the CLI uses.
    http = _client()
    r = http.post(
        "/api/budget",
        json={
            "medium": "fiber",
            "length_km": None,
            "tx_power_dbm": None,
            "rx_sensitivity_dbm": None,
            "wavelength_nm": None,
            "spectral_width_nm": None,
            "splice_count": None,
            "connector_pairs": None,
            "required_margin_db": None,
        },
    )
    assert r.status_code == 200
    data = r.json()
    # 1 km of SMF at 0.25 dB/km plus 1.00 dB of connectors.
    assert data["total_loss_db"] == pytest.approx(1.25, abs=0.01)
    assert data["verdict"] == "PASS"


def test_cleared_copper_fields_fall_back_to_the_defaults():
    http = _client()
    r = http.post(
        "/api/budget", json={"medium": "copper", "length_m": None, "pairs": None}
    )
    assert r.status_code == 200
    assert r.json()["verdict"] == "PASS"


def test_a_nan_value_is_a_400_never_a_pass():
    http = _client()
    r = http.post("/api/budget", json={"medium": "fiber", "length_km": float("nan")})
    assert r.status_code == 400
    assert "error" in r.json()


def test_nonsense_values_are_a_400_not_a_500():
    http = _client()
    assert http.post("/api/budget", json={"medium": "fiber", "length_km": 0}).status_code == 400
    # a list where a number belongs raises TypeError inside the engine
    assert (
        http.post("/api/budget", json={"medium": "fiber", "length_km": [1]}).status_code
        == 400
    )
    assert (
        http.post("/api/budget", json={"medium": "fiber", "fibre": "not-a-fibre"}).status_code
        == 400
    )


def test_a_body_that_is_not_an_object_is_a_400():
    http = _client()
    r = http.post("/api/budget", json=["not", "an", "object"])
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /api/project and /api/reference
# ---------------------------------------------------------------------------


def test_the_project_endpoint_reports_the_shipped_example():
    http = _client()
    r = http.get("/api/project")
    assert r.status_code == 200
    data = r.json()
    assert data["name"].startswith("Programme de cablage")
    assert [rack["id"] for rack in data["racks"]] == ["SR01", "SR02", "BAI01"]
    assert len(data["cables"]) == 9
    assert len(data["spans"]) == 2
    assert data["findings"] == []


def test_the_reference_endpoint_carries_the_fspl_example():
    http = _client()
    r = http.get("/api/reference")
    assert r.status_code == 200
    data = r.json()
    # 1 km at 1 GHz: the 92.44 dB of every propagation table.
    assert data["fspl_example"]["1km_1GHz"] == pytest.approx(92.44, abs=0.01)
    assert "smf" in data["fibres"]
    assert "cat6" in data["copper"]
