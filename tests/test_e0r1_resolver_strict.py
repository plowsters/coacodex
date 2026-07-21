# tests/test_e0r1_resolver_strict.py
"""E0R.1 T3.2 — resolve_active_generation resolves ONLY a fully-published E0R generation. A pre-v3 manifest,
a non-published state, a trust digest that does not cover the manifest, a `validation` that is not both
python+node true, a not-within-budget report, or a missing required child is REJECTED (fail closed). The
Node resolver enforces the identical gate (coa_scraper/tests/e0r1-resolver-strict.test.mjs)."""
import hashlib
import json

import pytest

from coa_client_extract.manifest import build_manifest
from coa_client_extract.publish import (
    GenerationWriter, POINTER_NAME, REQUIRED_CHILDREN, ResolveError,
    candidate_trust_sha256, resolve_active_generation,
)


def _binding():
    return {"source_dbc": {}, "policy_sha256": "p" * 64, "anchor_set_sha256": "a" * 32, "enum_policy_sha256": "e" * 32}


def _publish(root, *, validation=None, budget=None):
    w = GenerationWriter(root)
    w.add_jsonl("coa_client_spell.jsonl",
                [{"schema_version": "coa-client-spell-v3", "spell_id": 1, "raw": {}, "mechanics": {},
                  "coa_attribution": {"is_coa": False}}], schema_version="coa-client-spell-v3")
    w.add_jsonl("coa_client_spell_coa.jsonl", [], schema_version="coa-client-spell-projection-v3")
    w.add_json("coa_client_spell_projection.manifest.json",
               {"schema_version": "coa-client-spell-projection-manifest-v3"},
               schema_version="coa-client-spell-projection-manifest-v3")
    w.add_jsonl("coa_client_spell_icons.jsonl", [], schema_version="coa-client-spell-icons-v1")
    for name in ("coa_client_content.jsonl", "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
                 "coa_client_tab_types.jsonl", "coa_client_essence.jsonl"):
        w.add_jsonl(name, [], schema_version="coa-client-misc-v1")
    w.add_json("coa_client_archive_plan.json", {"schema_version": "coa-client-archive-plan-v1"},
               schema_version="coa-client-archive-plan-v1")
    w.add_json("spell_layout_v2.json", {"schema_version": "coa-spell-layout-v2"},
               schema_version="coa-spell-layout-v2")
    base = build_manifest(backend_name="fake", backend_version="v1", stormlib_version=None,
                          client_root="/x", client_build="3.3.5a+patch-CZZ", outputs={},
                          archive_plan={"schema_version": "coa-client-archive-plan-v1"})
    candidate = w.publish_candidate(base_manifest=base, binding=_binding())
    m = w.finalize_and_publish(candidate_manifest=candidate,
                               validation=validation if validation is not None else {"python": True, "node": True},
                               budget=budget if budget is not None else {"within_budget": True})
    return w, m


def _rewrite(root, gen_id, mutate):
    gen_dir = root / f"gen-{gen_id}"
    m = json.loads((gen_dir / "manifest.json").read_text())
    mutate(m)
    m["candidate_trust_sha256"] = candidate_trust_sha256(m)          # re-cover, so the target check surfaces
    body = (json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    (gen_dir / "manifest.json").write_bytes(body)
    ptr = json.loads((root / POINTER_NAME).read_text())
    ptr["manifest_sha256"] = hashlib.sha256(body).hexdigest()
    (root / POINTER_NAME).write_text(json.dumps(ptr, indent=2, sort_keys=True) + "\n")


def test_valid_published_generation_resolves(tmp_path):
    _w, m = _publish(tmp_path)
    assert resolve_active_generation(tmp_path)["generation_id"] == m["generation_id"]


def test_rejects_pre_v3_manifest(tmp_path):
    _w, m = _publish(tmp_path)
    _rewrite(tmp_path, m["generation_id"], lambda mm: mm.update({"schema_version": "coa-client-extract-manifest-v2"}))
    with pytest.raises(ResolveError, match="requires v3"):
        resolve_active_generation(tmp_path)


def test_rejects_non_published_state(tmp_path):
    _w, m = _publish(tmp_path)
    _rewrite(tmp_path, m["generation_id"], lambda mm: mm.update({"publication_state": "draft"}))
    with pytest.raises(ResolveError, match="not published"):
        resolve_active_generation(tmp_path)


def test_rejects_trust_digest_not_covering_manifest(tmp_path):
    _w, m = _publish(tmp_path)
    gen_dir = tmp_path / f"gen-{m['generation_id']}"
    doc = json.loads((gen_dir / "manifest.json").read_text())
    doc["generation_id"] = doc["generation_id"]           # unchanged struct, but corrupt the stored digest:
    doc["candidate_trust_sha256"] = "0" * 64
    body = (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    (gen_dir / "manifest.json").write_bytes(body)
    ptr = json.loads((tmp_path / POINTER_NAME).read_text())
    ptr["manifest_sha256"] = hashlib.sha256(body).hexdigest()
    (tmp_path / POINTER_NAME).write_text(json.dumps(ptr, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ResolveError, match="candidate_trust_sha256 does not cover"):
        resolve_active_generation(tmp_path)


def test_rejects_validation_not_both_true(tmp_path):
    _w, m = _publish(tmp_path, validation={"python": True, "node": False})
    with pytest.raises(ResolveError, match="not validated by both"):
        resolve_active_generation(tmp_path)


def test_rejects_over_budget(tmp_path):
    _w, m = _publish(tmp_path, budget={"within_budget": False})
    with pytest.raises(ResolveError, match="exceeded its budget"):
        resolve_active_generation(tmp_path)


def test_rejects_missing_required_child(tmp_path):
    _w, m = _publish(tmp_path)
    # drop a required child from BOTH the manifest registry and disk, re-covering the trust digest.
    (tmp_path / f"gen-{m['generation_id']}" / "coa_client_essence.jsonl").unlink()
    _rewrite(tmp_path, m["generation_id"], lambda mm: mm["children"].pop("coa_client_essence.jsonl"))
    with pytest.raises(ResolveError, match="required child 'coa_client_essence.jsonl' missing"):
        resolve_active_generation(tmp_path)
