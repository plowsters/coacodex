"""A stand-in for `node --import ./scripts/network-trap.mjs scripts/build-mechanics-artifacts.mjs`.

E0R.2 T4.3 gates the mechanics ARTIFACTS the canonical build leaves on disk: their input-identity
binding, the emitted JSONL's own recomputed hash, and its record count against the Builder domain. A
test that monkeypatches `run_measured_build_mechanics` writes no artifacts at all, so it can only ever
reach the measurement gate — everything past it would be untested.

So the acceptance fixtures hand `run_acceptance` this script AS the node binary. The real executor still
spawns it with the real argv, the real cwd, the real network-trap log and the real `pointer_only`
derivation (read back out of the emitted manifest), and the scenario decides only what the build emits.
Each knob corresponds to one way a build can be bound to something other than the generation under test.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

MECHANICS_JSONL = "coa_mechanics.jsonl"
MECHANICS_MANIFEST = "coa_mechanics.manifest.json"


def _flag(argv: list[str], name: str) -> str:
    i = argv.index(name)
    return argv[i + 1]


def _unique_spell_ids(entries_path: Path) -> list[int]:
    """One row per unique Builder spell id, exactly as `buildCanonicalMechanics` groups them."""
    seen, ids = set(), []
    for line in entries_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            sid = int(json.loads(line)["spell_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return sorted(ids)


def _readiness_coverage(rows: int) -> dict:
    fields = ["cooldown_ms", "costs", "gcd_ms", "power_type"]
    return {"schema_version": "coa-mechanics-readiness-coverage-v1", "rows": rows,
            "fields_considered": rows * len(fields),
            "statuses": {"unavailable": rows * len(fields)},
            "reason_codes": {"no_static_anchor": rows * len(fields)},
            "fields": {f: {"cells": rows, "statuses": {"unavailable": rows},
                           "reason_codes": {"no_static_anchor": rows}} for f in fields}}


def main(scenario: dict, argv: list[str]) -> int:
    trap_log = os.environ.get("COA_NETWORK_TRAP_LOG")
    if trap_log:
        Path(trap_log).write_text(json.dumps({"attempts": scenario.get("network_attempts", 0)}),
                                  encoding="utf-8")
    if scenario.get("exit_code"):
        return int(scenario["exit_code"])

    entries_path = Path(_flag(argv, "--builder-entries"))
    pointer_path = Path(_flag(argv, "--client-extract-pointer"))
    out_dir = Path(_flag(argv, "--out"))
    out_dir.mkdir(parents=True, exist_ok=True)

    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    gen_dir = pointer_path.parent / f"gen-{pointer['generation_id']}"
    manifest_path = gen_dir / "manifest.json"
    generation = json.loads(manifest_path.read_text(encoding="utf-8"))
    children = generation.get("children") or {}
    projection_child = children.get("coa_client_spell_coa.jsonl") or {}

    ids = _unique_spell_ids(entries_path)
    drop = int(scenario.get("drop_rows", 0))
    emitted = ids[: len(ids) - drop] if drop else ids

    digest = hashlib.sha256()
    with (out_dir / MECHANICS_JSONL).open("wb") as handle:
        for sid in emitted:
            line = (json.dumps({"spell_id": sid, "name": f"Spell {sid}",
                                "sources": {"name": "client_dbc"}}) + "\n").encode("utf-8")
            handle.write(line)
            digest.update(line)

    binding = {
        "input_generation_id": pointer["generation_id"],
        "pointer_manifest_sha256": pointer.get("manifest_sha256"),
        "policy_sha256": (generation.get("binding") or {}).get("policy_sha256"),
        "projection_child_sha256": projection_child.get("sha256"),
        "builder_entries_sha256": hashlib.sha256(entries_path.read_bytes()).hexdigest(),
    }
    binding.update(scenario.get("forge_binding") or {})

    mechanics_manifest = {
        "schema_version": "coa-mechanics-manifest-v1",
        "generated_at": "2026-07-29T00:00:00.000Z",
        "canonical": True, "client_source": "present", "fallback_authorized": False,
        "reconciliation_policy_version": "m1.14c-1", "reconciler_commit": None,
        "client_build": generation.get("client_build"),
        "binding": binding,
        "inputs": {
            "builder_entries": {"path": str(entries_path),
                                "sha256": binding["builder_entries_sha256"]},
            "db_spell_tooltips": None,
            "projection": {"path": str(gen_dir / "coa_client_spell_coa.jsonl"),
                           "sha256": projection_child.get("sha256")},
            "projection_manifest": {
                "path": str(gen_dir / "coa_client_spell_projection.manifest.json"),
                "sha256": (children.get("coa_client_spell_projection.manifest.json") or {}).get("sha256")},
        },
        "outputs": {"mechanics_jsonl": MECHANICS_JSONL, "sha256": digest.hexdigest(),
                    "record_count": len(emitted)},
        "coverage": {"builder_joined_to_projection": len(emitted),
                     "builder_missing_from_projection": 0, "projection_only": 0},
        "per_field_winner_counts_by_source": {"name": {"client_dbc": len(emitted)}},
        "per_field_winner_counts_by_tier": {"name": {"client_dbc": len(emitted)}},
        "field_readiness_coverage": _readiness_coverage(len(emitted)),
        "counts": {"unresolved_conflicts": 0, "ineligible_candidates": 0, "omitted_fields": 0},
    }
    if scenario.get("forge_output_sha256"):
        mechanics_manifest["outputs"]["sha256"] = "0" * 64
    if scenario.get("forge_record_count") is not None:
        mechanics_manifest["outputs"]["record_count"] = scenario["forge_record_count"]
    for key in scenario.get("drop_manifest_keys") or ():
        mechanics_manifest.pop(key, None)
    (out_dir / MECHANICS_MANIFEST).write_text(
        json.dumps(mechanics_manifest, indent=2) + "\n", encoding="utf-8")

    # --- concurrent publication, simulated where it really happens: DURING the build ---
    if scenario.get("republish_during_build"):
        pointer_path.write_text(json.dumps({**pointer, "generation_id": "cafed00d"}), encoding="utf-8")
    elif scenario.get("rewrite_manifest_during_build"):
        rewritten = json.dumps({**generation, "rewritten_after_the_build": True},
                               ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        manifest_path.write_text(rewritten, encoding="utf-8")
        pointer_path.write_text(
            json.dumps({**pointer,
                        "manifest_sha256": hashlib.sha256(rewritten.encode("utf-8")).hexdigest()}),
            encoding="utf-8")
    return 0
