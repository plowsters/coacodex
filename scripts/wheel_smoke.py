#!/usr/bin/env python3
"""Prove an INSTALLED coa-meta-analyzer can reach every data file it loads at runtime.

Run against a wheel installed into a clean environment, from a working directory outside the checkout:

    python -m build --wheel --outdir dist
    python -m venv /tmp/wheelenv && /tmp/wheelenv/bin/pip install dist/*.whl
    cd /tmp && /tmp/wheelenv/bin/python <repo>/scripts/wheel_smoke.py

Why this exists (E0R.3 P1): `pip install -e .` puts the entire source tree on `sys.path`, so a data
file the wheel omits still loads perfectly in development and in CI's `test` job. That is how the
generation-contract registry — four files the publication layer reads by absolute package path —
shipped missing from every wheel while every suite stayed green. This script is the only place that
failure can surface, so it must import the INSTALLED package and touch each data file for real.

`sys.path[0]` is this script's directory (`<repo>/scripts`), which contains no packages, so running it
by path does not smuggle the checkout onto the path. The repo-root guard below fails loudly if the
imports resolved to the source tree anyway.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _require_installed(module) -> Path:
    """The whole point is the installed copy; resolving to the checkout would prove nothing."""
    root = Path(module.__file__).resolve().parent
    if root == REPO or REPO in root.parents:
        raise SystemExit(
            f"{module.__name__} imported from the checkout ({root}), not from an installed "
            "distribution — this smoke test cannot detect a packaging omission that way. Run it from "
            "a working directory outside the repository, with only the wheel installed."
        )
    return root


def main() -> int:
    import coa_client_extract
    import coa_meta

    client_root = _require_installed(coa_client_extract)
    _require_installed(coa_meta)

    # The defect itself: the registry index plus every revision it supports, loaded and digest-verified
    # through the real loader, not merely stat()ed.
    from coa_client_extract.contracts import (
        load_contract_registry,
        load_current_contract,
        load_observation_wire_schema,
        load_supported_contract,
    )

    registry = load_contract_registry()
    supported = registry["supported"]
    for revision, entry in sorted(supported.items()):
        contract = load_supported_contract(revision, entry["sha256"])
        print(f"contract {revision}: {len(contract['children'])} children")
    current, _ = load_current_contract()
    if current not in supported:
        raise SystemExit(f"registry `current` {current!r} is not in `supported`")
    load_observation_wire_schema()

    # Importing the publication layer is the exact import that raised FileNotFoundError from a wheel.
    import coa_client_extract.publish  # noqa: F401

    # Every other data file either package loads at runtime, by the loader that loads it.
    from coa_meta.apl_profiles import load_builtin_apl_profile
    from coa_meta.backend_trust import load_live_sanity_watchlist
    from coa_meta.profiles import load_builtin_profile

    load_builtin_profile("generic_dps", encounter="single_target")
    load_builtin_apl_profile("generic_dps")
    load_live_sanity_watchlist()

    from coa_client_extract.spell_layout import load_default_policy

    load_default_policy()

    # Anything committed under a package's `data/` that the wheel dropped is a silent latent failure
    # until some later code path reaches it, so account for the whole tree, not just today's readers.
    missing = [str(p) for p in (REPO / "coa_client_extract" / "data").rglob("*.json")
               if not (client_root / "data" / p.relative_to(REPO / "coa_client_extract" / "data")).exists()]
    if missing:
        raise SystemExit("installed package is missing data file(s): " + ", ".join(sorted(missing)))

    print(f"wheel smoke OK: {len(supported)} contract revision(s), current={current}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
