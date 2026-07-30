from __future__ import annotations

from datetime import date


def build_manifest(
    *,
    backend_name: str,
    backend_version: str,
    stormlib_version: str | None,
    client_root: str,
    client_build: str,
    outputs: dict[str, str],
    archive_plan: dict,
) -> dict:
    return {
        "schema_version": "coa-client-extract-manifest-v1",
        "wrapper_version": "coa-stormlib-v1",
        "backend": backend_name,
        "backend_version": backend_version,
        "stormlib_version": stormlib_version,
        "client_root": client_root,
        "client_build": client_build,
        "extraction_date": date.today().isoformat(),
        "archive_plan": archive_plan,
        "outputs": outputs,
    }


def build_manifest_v3(
    *,
    base: dict,
    generation_id: str,
    published_at: int,
    predecessor_generation_id: str | None,
    children: dict,
    unknown_symbol_inventory: dict,
    binding: dict,
    publication_state: str = "candidate",
) -> dict:
    """The E0R generation manifest (coa-client-extract-manifest-v3): a SUPERSET of all ten v1 fields
    (from `base`) plus generation identity, monotonic `published_at` (ns), the pointer's prior target
    `predecessor_generation_id`, the exact `children` inventory (with `outputs` re-derived as a
    deterministic {name: sha256} index view over it), the per-value `unknown_symbol_inventory`,
    source/policy/anchor/enum `binding` hashes, and an explicit `publication_state`
    ("candidate" | "published"): a candidate manifest is NEVER pointer-resolvable, so an interrupted
    publish leaves no half-live generation. The candidate_trust_sha256 is added by the publisher over
    everything except the three CANDIDATE_MUTABLE_KEYS."""
    manifest = dict(base)
    manifest["schema_version"] = "coa-client-extract-manifest-v3"
    manifest["outputs"] = {name: meta["sha256"] for name, meta in sorted(children.items())}
    manifest["generation_id"] = generation_id
    manifest["published_at"] = published_at
    manifest["predecessor_generation_id"] = predecessor_generation_id
    manifest["children"] = children
    manifest["unknown_symbol_inventory"] = unknown_symbol_inventory
    manifest["binding"] = binding
    manifest["publication_state"] = publication_state
    return manifest
