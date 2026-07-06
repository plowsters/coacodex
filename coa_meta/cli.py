from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .report_assets import AssetResolver
from .reporting import SUPPORTED_META_ROLES, MetaReportRunner, MetaRunConfig, write_report_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coa_meta")
    subparsers = parser.add_subparsers(dest="command")

    meta = subparsers.add_parser("meta", help="Generate Phase 1 theorycraft meta reports")
    meta.add_argument("--entries", type=Path, default=Path("coa_scraper/dist/coa_entries.jsonl"))
    meta.add_argument("--classes", dest="classes_path", type=Path, default=Path("coa_scraper/dist/coa_classes.json"))
    meta.add_argument("--level", type=int, default=60)
    meta.add_argument("--class", dest="class_names", action="append", default=[])
    meta.add_argument("--spec", dest="specs", action="append", default=[])
    meta.add_argument("--encounter-profile", dest="encounters", action="append", default=[])
    meta.add_argument("--top", type=int, default=3)
    meta.add_argument("--beam-width", type=int, default=5)
    meta.add_argument("--branch-width", type=int, default=10)
    meta.add_argument("--require-budget-fraction", type=float, default=0.7)
    meta.add_argument("--role", choices=tuple(sorted(SUPPORTED_META_ROLES)), default="auto")
    meta.add_argument("--simulate", action="store_true")
    meta.add_argument("--simulation-duration", type=float, default=60.0, help="Simulation duration in seconds")
    meta.add_argument("--simulation-iterations", type=int, default=1)
    meta.add_argument("--simulation-seed", type=int, default=1)
    meta.add_argument("--simulate-rotations", dest="simulate_rotations", action="store_true")
    meta.add_argument("--no-simulate-rotations", dest="simulate_rotations", action="store_false")
    meta.add_argument("--rotation-duration-ms", type=int, default=90_000)
    meta.add_argument("--rotation-candidates", type=int, default=48)
    meta.add_argument("--gear-profile", type=Path, default=None)
    meta.add_argument("--workers", type=int, default=1)
    meta.add_argument("--format", dest="formats", action="append", choices=("json", "md", "html"), default=[])
    meta.add_argument("--out", type=Path, default=Path("reports/meta"))
    meta.add_argument("--asset-root", type=Path, default=None)
    meta.add_argument("--db-tooltips", type=Path, default=None, help="Optional AscensionDB tooltip JSONL for static guide tooltips")
    meta.add_argument("--builder-layout-root", type=Path, default=None, help="Optional CoA Builder tree layout artifact directory")
    meta.add_argument("--write-backend-trust", action="store_true")
    meta.add_argument("--backend-trust-out", type=Path, default=None)
    meta.set_defaults(handler=run_meta)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args))


def run_meta(args: argparse.Namespace) -> int:
    _log_progress(
        "Starting meta report: "
        f"entries={args.entries}, classes={args.classes_path}, out={args.out}"
    )
    config = MetaRunConfig(
        entries_path=args.entries,
        classes_path=args.classes_path,
        class_names=tuple(args.class_names),
        spec_names_or_ids=tuple(args.specs),
        level=args.level,
        encounter_profile_ids=tuple(args.encounters) if args.encounters else ("baseline_single_target",),
        top=args.top,
        beam_width=args.beam_width,
        branch_width=args.branch_width,
        require_budget_fraction=args.require_budget_fraction,
        role=args.role,
        simulate=args.simulate,
        simulation_duration_ms=int(args.simulation_duration * 1000),
        simulation_iterations=args.simulation_iterations,
        simulation_seed=args.simulation_seed,
        simulate_rotations=args.simulate_rotations,
        rotation_duration_ms=args.rotation_duration_ms,
        rotation_candidates=args.rotation_candidates,
        gear_profile_path=args.gear_profile,
    )
    _log_progress("Loading artifacts and expanding report scopes")
    _log_progress("Running build search and scoring")
    if args.simulate_rotations:
        _log_progress(
            "Running rotation simulation: "
            f"duration_ms={args.rotation_duration_ms}, candidates={args.rotation_candidates}"
        )
    report = MetaReportRunner(config).run()
    formats = tuple(args.formats) if args.formats else ("json", "md", "html")
    asset_resolver = AssetResolver(args.asset_root) if args.asset_root else None
    _log_progress(f"Writing outputs: formats={', '.join(formats)}")
    writer_kwargs = {}
    if args.write_backend_trust or args.backend_trust_out is not None:
        writer_kwargs["write_backend_trust"] = True
        writer_kwargs["backend_trust_out"] = args.backend_trust_out
    outputs = write_report_outputs(
        report,
        args.out,
        formats=formats,
        asset_resolver=asset_resolver,
        entries_path=args.entries,
        db_tooltips_path=args.db_tooltips,
        builder_layout_root=args.builder_layout_root,
        **writer_kwargs,
    )
    _log_progress(f"Complete: wrote {len(outputs)} file(s) to {args.out}")
    return 0


def _log_progress(message: str) -> None:
    print(f"[coa-meta] {message}", file=sys.stderr)
