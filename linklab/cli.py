"""Command line interface.

    linklab budget fiber     --length 12 --fibre smf --tx 2 --rx -28
    linklab budget microwave --length 5 --freq 15 --tx 20 --rx-gain 30
    linklab budget copper    --length 80 --category cat6 --pairs 4
    linklab project validate project.json
    linklab docs build       project.json --out site/
    linklab serve            project.json --port 8080
"""

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from .budget import (
    Optics,
    compute_copper_budget,
    compute_fiber_budget,
    compute_microwave_budget,
)
from .media import COPPER_TYPES, FIBRE_TYPES, SPLICE_TYPES, CONNECTOR_TYPES
from .project import (
    ERROR,
    load_project,
    save_project,
    validate_project,
)


def _print_budget(result, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    verdict = result.verdict
    marker = "PASS" if verdict == "PASS" else "FAIL"
    print(f"  verdict      {verdict}")
    if getattr(result, "limiting_factor", "none") != "none":
        print(f"  limited by   {result.limiting_factor}")
    print()


def _cmd_fiber(args) -> int:
    optics = Optics(
        tx_power_dbm=args.tx,
        rx_sensitivity_dbm=args.rx,
        wavelength_nm=args.wavelength,
        bitrate_gbps=args.bitrate,
        spectral_width_nm=args.spectral_width,
        splice_count=args.splices,
        connector_pairs=args.connectors,
        splice_type=args.splice_type,
        connector_type=args.connector_type,
        required_margin_db=args.margin,
    )
    b = compute_fiber_budget(args.length, args.fibre, optics)
    if args.json:
        print(json.dumps(b.to_dict(), indent=2))
        return 0 if b.verdict == "PASS" else 1
    print(f"Fibre budget  {FIBRE_TYPES[args.fibre].label} @ {args.wavelength} nm")
    print(f"  length       {b.length_km:.3f} km")
    print(f"  attenuation  {b.attenuation_db_per_km:.3f} dB/km -> {b.fiber_loss_db:.3f} dB")
    print(f"  splices      {b.splice_loss_db:.3f} dB")
    print(f"  connectors   {b.connector_loss_db:.3f} dB")
    print(f"  total loss   {b.total_loss_db:.3f} dB")
    print(f"  budget       {b.available_budget_db:.3f} dB")
    print(f"  margin       {b.margin_db:.3f} dB")
    if b.dispersion_limit_km is not None:
        print(f"  dispersion   {b.dispersion_ps:.1f} ps, limit {b.dispersion_limit_km:.2f} km")
    print(f"  max reach    {b.max_reach_km:.3f} km")
    for note in b.notes:
        print(f"  ! {note}")
    print(f"  verdict      {b.verdict}")
    return 0 if b.verdict == "PASS" else 1


def _cmd_microwave(args) -> int:
    b = compute_microwave_budget(
        length_km=args.length,
        frequency_ghz=args.freq,
        tx_power_dbm=args.tx,
        tx_antenna_gain_dbi=args.tx_gain,
        rx_antenna_gain_dbi=args.rx_gain,
        rx_threshold_dbm=args.rx_threshold,
        feeder_loss_tx_db=args.feeder_tx,
        feeder_loss_rx_db=args.feeder_rx,
        rain_fade_allowance_db=args.rain_fade,
        required_margin_db=args.margin,
    )
    if args.json:
        print(json.dumps(b.to_dict(), indent=2))
        return 0 if b.verdict == "PASS" else 1
    print(f"Microwave budget  {b.frequency_ghz:g} GHz over {b.length_km:.2f} km")
    print(f"  FSPL         {b.fspl_db:.3f} dB")
    print(f"  EIRP         {b.eirp_dbm:.3f} dBm")
    print(f"  received     {b.received_level_dbm:.3f} dBm")
    print(f"  threshold    {b.rx_threshold_dbm:.3f} dBm")
    print(f"  margin       {b.margin_db:.3f} dB (required {b.required_margin_db:.2f} dB)")
    for note in b.notes:
        print(f"  ! {note}")
    print(f"  verdict      {b.verdict}")
    return 0 if b.verdict == "PASS" else 1


def _cmd_copper(args) -> int:
    b = compute_copper_budget(args.length, args.category, args.pairs, args.application)
    if args.json:
        print(json.dumps(b.to_dict(), indent=2))
        return 0 if b.verdict == "PASS" else 1
    print(f"Copper budget  {COPPER_TYPES[args.category].label} / {args.application}")
    print(f"  length       {b.length_m:.1f} m")
    print(f"  channel      max {b.channel_max_m:.0f} m")
    print(f"  permanent    max {b.permanent_link_max_m:.0f} m")
    print(f"  insertion    {b.insertion_loss_db:.3f} dB")
    print(f"  derating     {b.derating_db:.3f} dB")
    print(f"  PS-NEXT      {b.ps_next_penalty_db:.3f} dB")
    print(f"  total        {b.total_budget_db:.3f} dB of {b.max_insertion_loss_db:.1f} dB allowed")
    for note in b.notes:
        print(f"  ! {note}")
    print(f"  verdict      {b.verdict}")
    return 0 if b.verdict == "PASS" else 1


def _cmd_validate(args) -> int:
    project = load_project(args.project)
    findings = validate_project(project)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "severity": f.severity,
                        "code": f.code,
                        "message": f.message,
                        "where": f.where,
                    }
                    for f in findings
                ],
                indent=2,
            )
        )
    else:
        if not findings:
            print("No findings. The project is internally consistent.")
        else:
            for f in findings:
                print(f)
    errors = sum(1 for f in findings if f.severity == ERROR)
    return 1 if errors else 0


def _cmd_docs(args) -> int:
    from .docs import build_docs

    project = load_project(args.project)
    findings = validate_project(project)
    errors = [f for f in findings if f.severity == ERROR]
    if errors and not args.force:
        print("Refusing to document a project with design errors:\n", file=sys.stderr)
        for f in errors:
            print(f"  {f}", file=sys.stderr)
        print("\nFix them, or pass --force to document anyway.", file=sys.stderr)
        return 1
    summary = build_docs(project, args.out, findings)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print(f"Wrote {len(summary['files'])} files to {args.out}")
    print(
        f"  {summary['racks']} racks, {summary['cables']} cables "
        f"({summary['cables_pass']} within budget), "
        f"{summary['spans']} optical spans ({summary['spans_pass']} within budget)"
    )
    if summary["errors"]:
        print(f"  {summary['errors']} design error(s) recorded on the site")
    if summary["warnings"]:
        print(f"  {summary['warnings']} warning(s) recorded on the site")
    return 0


def _cmd_serve(args) -> int:
    try:
        from .server import serve
    except ImportError:
        print(
            "The web UI needs extra dependencies. Install them with:\n"
            "    pip install 'linklab[web]'",
            file=sys.stderr,
        )
        return 1
    serve(args.project, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linklab",
        description="Telecom link budget and network documentation toolkit.",
    )
    parser.add_argument("--version", action="version", version=f"linklab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- budget --------------------------------------------------------
    budget = sub.add_parser("budget", help="compute a link budget")
    bsub = budget.add_subparsers(dest="medium", required=True)

    fiber = bsub.add_parser("fiber", help="optical fibre link budget")
    fiber.add_argument("--length", type=float, required=True, help="length in km")
    fiber.add_argument("--fibre", default="smf", choices=sorted(FIBRE_TYPES))
    fiber.add_argument("--tx", type=float, default=0.0, help="transmit power in dBm")
    fiber.add_argument("--rx", type=float, default=-28.0, help="receiver sensitivity in dBm")
    fiber.add_argument("--wavelength", type=int, default=1550, help="wavelength in nm")
    fiber.add_argument("--bitrate", type=float, default=None, help="line rate in Gb/s")
    fiber.add_argument("--spectral-width", type=float, default=0.1, help="source width in nm")
    fiber.add_argument("--splices", type=int, default=0)
    fiber.add_argument("--connectors", type=int, default=2, help="mated connector pairs")
    fiber.add_argument("--splice-type", default="fusion", choices=sorted(SPLICE_TYPES))
    fiber.add_argument("--connector-type", default="lc", choices=sorted(CONNECTOR_TYPES))
    fiber.add_argument("--margin", type=float, default=0.0, help="required margin in dB")
    fiber.add_argument("--json", action="store_true")
    fiber.set_defaults(func=_cmd_fiber)

    micro = bsub.add_parser("microwave", help="point-to-point microwave link budget")
    micro.add_argument("--length", type=float, required=True, help="path length in km")
    micro.add_argument("--freq", type=float, required=True, help="carrier frequency in GHz")
    micro.add_argument("--tx", type=float, required=True, help="transmit power in dBm")
    micro.add_argument("--tx-gain", type=float, default=0.0, help="transmit antenna gain in dBi")
    micro.add_argument("--rx-gain", type=float, default=0.0, help="receive antenna gain in dBi")
    micro.add_argument(
        "--rx-threshold", type=float, default=-80.0, help="receiver threshold in dBm"
    )
    micro.add_argument("--feeder-tx", type=float, default=0.5, help="transmit feeder loss in dB")
    micro.add_argument("--feeder-rx", type=float, default=0.5, help="receive feeder loss in dB")
    micro.add_argument("--rain-fade", type=float, default=0.0, help="rain fade allowance in dB")
    micro.add_argument("--margin", type=float, default=10.0, help="required margin in dB")
    micro.add_argument("--json", action="store_true")
    micro.set_defaults(func=_cmd_microwave)

    copper = bsub.add_parser("copper", help="balanced twisted-pair link budget")
    copper.add_argument("--length", type=float, required=True, help="length in m")
    copper.add_argument("--category", default="cat6", choices=sorted(COPPER_TYPES))
    copper.add_argument("--pairs", type=int, default=4, choices=[1, 2, 4])
    copper.add_argument(
        "--application",
        default="1gbase-t",
        choices=["1gbase-t", "10gbase-t", "40gbase-t"],
    )
    copper.add_argument("--json", action="store_true")
    copper.set_defaults(func=_cmd_copper)

    # ---- project -------------------------------------------------------
    project = sub.add_parser("project", help="inspect a project file")
    psub = project.add_subparsers(dest="action", required=True)
    validate = psub.add_parser("validate", help="check a project for design errors")
    validate.add_argument("project")
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(func=_cmd_validate)
    export = psub.add_parser("export", help="write the project back out as JSON")
    export.add_argument("project")
    export.add_argument("--out", required=True)
    export.set_defaults(func=_cmd_export)

    # ---- docs ----------------------------------------------------------
    docs = sub.add_parser("docs", help="generate the documentation site")
    dsub = docs.add_subparsers(dest="action", required=True)
    build = dsub.add_parser("build", help="build the site")
    build.add_argument("project")
    build.add_argument("--out", required=True, help="output directory")
    build.add_argument(
        "--force", action="store_true", help="document even with design errors"
    )
    build.add_argument("--json", action="store_true")
    build.set_defaults(func=_cmd_docs)

    # ---- serve ---------------------------------------------------------
    serve = sub.add_parser("serve", help="run the web UI")
    serve.add_argument("project")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.set_defaults(func=_cmd_serve)

    return parser


def _cmd_export(args) -> int:
    project = load_project(args.project)
    save_project(project, args.out)
    print(f"Wrote {args.out}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
