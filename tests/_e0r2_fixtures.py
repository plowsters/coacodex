"""Shared E0R.2 generation-fixture helpers.

Every synthetic generation carries a TWELFTH child — `generation_contract.json`, the immutable registry
revision it was produced under — plus the `binding.generation_contract` that identifies it by revision
and canonical digest (T1.1/T1.2).

T2.1 adds the second half: a generation now has to satisfy POLICY-ROOTED cardinalities, so a fixture
must stage a policy that actually binds a source domain. `bind_policy_doc` gives a synthetic policy a
structured `bound` SIZED TO WHAT THE FIXTURE STAGES, and `topology_report_for` builds the matching
`binding.topology`. Violations are then introduced by breaking that correspondence on purpose — which is
the only way a negative test can be about the rule rather than about the fixture.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from coa_client_extract.contracts import (GENERATION_CONTRACT_CHILD, GENERATION_CONTRACT_SCHEMA,
                                          generation_contract_sha256, load_current_contract)
from coa_client_extract.contracts import load_observation_wire_schema
from coa_client_extract.publish import GenerationWriter
from coa_client_extract.spell_icons import (ASSET_CHILD as ICON_ASSET_CHILD,
                                            ASSET_SCHEMA as ICON_ASSET_SCHEMA,
                                            ASSOCIATION_SCHEMA as ICON_ASSOCIATION_SCHEMA)
from coa_client_extract.spell_layout import compute_policy_sha256, derive_artifact_contract
from coa_client_extract.spell_record import (FIELD_DESCRIPTORS_CHILD, FIELD_DESCRIPTORS_SCHEMA,
                                             SPELL_SCHEMA_V4, WIRE_SCHEMA_CHILD,
                                             build_field_descriptors)

CORPUS = Path(__file__).resolve().parent / "golden" / "e0r1_corpus"
CORPUS_V4 = Path(__file__).resolve().parent / "golden" / "e0r2_corpus_v4"

# The ancillary CoA tables the contract's cardinality rules name. Bound TOPOLOGY-ONLY (no `fields`),
# exactly as T0.2 bound them in the real policy.
ANCILLARY_TABLES = ("CharacterAdvancement", "CharacterAdvancementClassTypes",
                    "CharacterAdvancementTabTypes", "CharacterAdvancementEssence")
ANCILLARY_CHILD_FOR = {
    "CharacterAdvancementClassTypes": "coa_client_class_types.jsonl",
    "CharacterAdvancementTabTypes": "coa_client_tab_types.jsonl",
    "CharacterAdvancementEssence": "coa_client_essence.jsonl",
}
ANCILLARY_SHAPE_FOR = {
    "coa_client_class_types.jsonl": "class_type_row_v1",
    "coa_client_tab_types.jsonl": "tab_type_row_v1",
    "coa_client_essence.jsonl": "essence_row_v1",
}
CLIENT_BUILD = "3.3.5a+fixture"


def _fake_table_binding(name: str, record_count: int) -> dict:
    """A deterministic per-table bound entry. The digest is derived from the table name so two fixtures
    never collide, and `topology_report_for` reproduces it exactly — the point of the pair is that the
    reviewed bound and the reported topology agree, not that either is a real capture."""
    return {
        "sha256": hashlib.sha256(f"fixture:{name}".encode()).hexdigest(),
        "header": {"magic": "WDBC", "record_count": record_count, "field_count": 2,
                   "record_size": 8, "string_block_size": 1},
        "source": {"member": f"DBFilesClient\\{name}.dbc", "effective_archive": "common.MPQ",
                   "patch_chain": []},
    }


def bind_policy_doc(doc: dict, *, spell_records: int, ancillary_records: dict | None = None,
                    content_entries: int = 2) -> dict:
    """Return a copy of `doc` with the ancillary tables added and a structured `bound` sized to what the
    caller stages. Rehashed, so it loads.

    A policy with `bound: None` cannot state a source domain, and a generation produced from one has no
    provable cardinality — which is why the validator refuses it outright rather than skipping the rules.
    """
    ancillary_records = {**{t: 2 for t in ANCILLARY_TABLES}, **(ancillary_records or {})}
    doc = copy.deepcopy(doc)
    for name in ANCILLARY_TABLES:
        doc["tables"].setdefault(name, {"expected_field_count": 2, "key_cell": 0, "unique": True})
    doc["required_tables"] = sorted(doc["tables"])
    doc["expected_absent"] = []
    counts = {name: ancillary_records.get(name, 1) for name in doc["tables"]}
    counts["Spell"] = spell_records
    doc["bound"] = {"client_build": CLIENT_BUILD, "expected_absent": [],
                    "tables": {name: _fake_table_binding(name, counts[name]) for name in doc["tables"]}}
    doc["content_sources"] = {
        "directory": "Content",
        # No file is read here — only `source_entries` is load-bearing, because it is what
        # `declared_content_derivation` roots the Content child's expected count in.
        "required_files": {"SpellRankData.json": {
            "kind": "spell_rank", "sha256": "0" * 64, "source_entries": content_entries}},
    }
    doc["artifact_contract"] = derive_artifact_contract(doc)
    doc.pop("sha256", None)
    doc["sha256"] = compute_policy_sha256(doc)
    return doc


def stage_v4_documents(gw, policy_doc: dict | None = None) -> None:
    """Stage the two children a v4 row needs to be decodable (E0R.2 T6.2). A generation without them is
    incomplete under `e0r-v2`, so every fixture that stages a generation by hand stages these too."""
    gw.add_json(FIELD_DESCRIPTORS_CHILD,
                build_field_descriptors(policy_doc) if policy_doc is not None
                else {"schema_version": FIELD_DESCRIPTORS_SCHEMA, "policy_sha256": "0" * 64,
                      "fields": {}},
                schema_version=FIELD_DESCRIPTORS_SCHEMA)
    gw.add_json(WIRE_SCHEMA_CHILD, load_observation_wire_schema(),
                schema_version="coa-observation-wire-v1")


def topology_report_for(doc: dict) -> dict:
    """The `binding.topology` a producer would have recorded for this bound policy — matching it
    facet-for-facet, so `topology_matches_bound` is empty."""
    bound = doc["bound"]
    return {
        "client_build": bound["client_build"],
        "tables": {name: {"sha256": t["sha256"], "header": t["header"],
                          "member": t["source"]["member"],
                          "effective_archive": t["source"]["effective_archive"],
                          "patch_chain": t["source"]["patch_chain"],
                          "key_unique": True, "dense": True}
                   for name, t in bound["tables"].items()},
        "expected_absent_ok": True, "expected_absent_set": list(bound.get("expected_absent", [])),
        "blocking": [],
    }


def policy_binding(doc: dict) -> dict:
    """The `binding` fragment a producer records for a reviewed policy (T2.1's trust-chain legs 2 and 3)."""
    return {"policy_sha256": doc["sha256"], "topology": topology_report_for(doc)}


# --- the generation contract (T1.1/T1.2) ---

def generation_contract_binding(contract=None) -> dict:
    """The `binding` fragment identifying the staged contract. A producer records it so a consumer can
    tell WHICH revision governed the generation without trusting the staged bytes.

    `contract` is a (revision, doc) pair; it defaults to the current revision. It describes whatever was
    actually STAGED — binding a document other than the staged one is a desynchronization a test opts
    into explicitly (`bind_override`), never a fixture default. Keeping the two in step by default is
    what lets the binding leg and the registry leg be exercised one at a time."""
    revision, doc = contract if contract is not None else load_current_contract()
    return {"generation_contract": {"schema_version": GENERATION_CONTRACT_SCHEMA,
                                    "revision": revision,
                                    "sha256": generation_contract_sha256(doc)}}


def staged_contract_doc(*, contract=None, mutate=None) -> tuple[str, dict]:
    """The (revision, doc) a fixture will stage. `mutate` (tests only) alters the copy so the validator
    can be exercised against a tampered, structurally broken, or unsupported document."""
    revision, doc = contract if contract is not None else load_current_contract()
    doc = copy.deepcopy(doc)
    if mutate is not None:
        mutate(doc)
    return (doc.get("revision", revision) if isinstance(doc, dict) else revision), doc


def stage_generation_contract(gw: GenerationWriter, *, mutate=None, contract=None) -> tuple[str, dict]:
    """Stage the contract child; returns the (revision, doc) actually written."""
    revision, doc = staged_contract_doc(contract=contract, mutate=mutate)
    gw.add_json(GENERATION_CONTRACT_CHILD, doc, schema_version=GENERATION_CONTRACT_SCHEMA)
    return revision, doc


# --- the golden corpus baseline ---

def corpus_rows(name: str, *cases: str, corpus: Path = None) -> list[dict]:
    """Corpus rows for the given cases, stripped of the corpus labels. `corpus` selects the v3 baseline
    (default) or the v4 one — both are committed, because `e0r-v1` stays supported (T6.2)."""
    rows = [json.loads(line) for line in ((corpus or CORPUS) / name).read_text().splitlines()
            if line.strip()]
    return [{k: v for k, v in r.items() if k not in ("case", "golden_accept")}
            for r in rows if r["case"] in cases]


def corpus_policy_doc() -> dict:
    return json.loads((CORPUS / "policy.json").read_text())


def _ancillary_rows(shape: str, count: int) -> list[dict]:
    """`count` copies of the row the REAL producer emits for this child (tests/golden.py). T2.2 shape-
    checks every row, so a placeholder would only prove the fixture can dodge its own gate."""
    from tests.golden import golden_rows

    return [copy.deepcopy(golden_rows(shape)) for _ in range(count)]


def stage_candidate(root, *, full=None, proj=None, icons=None, policy_doc=None,
                    ancillary_counts=None, advancement_kept=2, advancement_source=3,
                    content_entries=2, base_manifest=None,
                    # --- contract knobs (T1.2), each isolating one leg of the three-way check ---
                    drop_contract=False, contract_mutate=None, contract=None, bind_override=None,
                    drop_binding=False,
                    # --- cardinality knobs (T2.1), each breaking ONE correspondence on purpose ---
                    truncate_full_to=None, truncate_icons_to=None, drop_projection_rows=0,
                    truncate_child=None, extra_child=None, duplicate_json_document=None,
                    advancement_derivation=None, content_derivation=None, drop_derivations=False,
                    forge_manifest_topology_record_count=None, forge_staged_policy_bound_record_count=None,
                    forge_manifest_policy_sha256=None, unbind_staged_policy=False,
                    # --- v4 decoder knobs (T6.2): the two children a hoisted row needs ---
                    forge_descriptors=None, forge_wire=None,
                    # --- normalized-icon knobs (T6.3) ---
                    icon_assets=None,
                    return_writer=False):
    """A COMPLETE staged candidate whose policy is sized to what it stages, so the honest case validates
    and each knob breaks exactly one rule. Returns the generation directory.

    The three spell children come from the shared golden corpus (the same rows Node validates), so the
    cross-child merge-join has real work to do rather than being trivially satisfied by empty files.
    """
    full = corpus_rows("full_rows.jsonl", "valid_full", corpus=CORPUS_V4) if full is None else full
    proj = corpus_rows("projection_rows.jsonl", "valid") if proj is None else proj
    icons = corpus_rows("icons.jsonl", "valid_icon", corpus=CORPUS_V4) if icons is None else icons
    icon_assets = (corpus_rows("icon_assets.jsonl", "valid_asset", corpus=CORPUS_V4)
                   if icon_assets is None else icon_assets)
    ancillary_counts = {**{t: 2 for t in ANCILLARY_TABLES}, **(ancillary_counts or {})}
    ancillary_counts["CharacterAdvancement"] = advancement_source

    base = corpus_policy_doc() if policy_doc is None else policy_doc
    policy = bind_policy_doc(base, spell_records=len(full), ancillary_records=ancillary_counts,
                             content_entries=content_entries)

    # Violations are applied AFTER the policy is sized, so each one breaks the correspondence rather
    # than the fixture never having established it.
    staged_policy = copy.deepcopy(policy)
    if forge_staged_policy_bound_record_count is not None:
        staged_policy["bound"]["tables"]["Spell"]["header"]["record_count"] = \
            forge_staged_policy_bound_record_count
        staged_policy["sha256"] = compute_policy_sha256(
            {k: v for k, v in staged_policy.items() if k != "sha256"})
    if unbind_staged_policy:
        staged_policy["bound"] = None
        staged_policy["sha256"] = compute_policy_sha256(
            {k: v for k, v in staged_policy.items() if k != "sha256"})

    if truncate_full_to is not None:
        full = full[:truncate_full_to]
    if truncate_icons_to is not None:
        icons = icons[:truncate_icons_to]
    if drop_projection_rows:
        proj = proj[:-drop_projection_rows]

    ancillary_rows = {
        "coa_client_content.jsonl": _ancillary_rows("content_row_v1", content_entries),
        "coa_client_advancement.jsonl": _ancillary_rows("advancement_row_v1", advancement_kept),
    }
    for table, child in ANCILLARY_CHILD_FOR.items():
        ancillary_rows[child] = _ancillary_rows(ANCILLARY_SHAPE_FOR[child], ancillary_counts[table])
    if truncate_child is not None:
        name, keep = truncate_child
        ancillary_rows[name] = ancillary_rows[name][:keep]

    gw = GenerationWriter(root)
    write_lock(gw.root, policy)      # the HONEST policy: a forged staged copy is caught against this
    gw.add_jsonl("coa_client_spell.jsonl", full, schema_version=SPELL_SCHEMA_V4)
    gw.add_jsonl("coa_client_spell_coa.jsonl", proj, schema_version="coa-client-spell-projection-v3")
    gw.add_jsonl("coa_client_spell_icons.jsonl", icons, schema_version=ICON_ASSOCIATION_SCHEMA)
    gw.add_jsonl(ICON_ASSET_CHILD, icon_assets, schema_version=ICON_ASSET_SCHEMA)
    from tests.golden import golden_rows
    gw.add_json("coa_client_spell_projection.manifest.json", golden_rows("projection_manifest_v3"),
                schema_version="coa-client-spell-projection-manifest-v3")
    for name, rows in ancillary_rows.items():
        gw.add_jsonl(name, rows, schema_version=f"fixture-{name}")
    gw.add_json("coa_client_archive_plan.json", golden_rows("archive_plan_v1"),
                schema_version="coa-client-archive-plan-v1")
    gw.add_json("spell_layout_v2.json", staged_policy, schema_version="coa-spell-layout-v2")
    # E0R.2 T6.2: a v4 row is only decodable WITH these two, so every complete generation ships them.
    # Derived from the HONEST policy — a fixture that derived them from a forged staged copy would be
    # self-consistent and prove nothing.
    descriptors = build_field_descriptors(policy)
    if forge_descriptors is not None:
        forge_descriptors(descriptors)
    wire = copy.deepcopy(load_observation_wire_schema())
    if forge_wire is not None:
        forge_wire(wire)
    gw.add_json(FIELD_DESCRIPTORS_CHILD, descriptors, schema_version=FIELD_DESCRIPTORS_SCHEMA)
    gw.add_json(WIRE_SCHEMA_CHILD, wire, schema_version="coa-observation-wire-v1")

    binding: dict = dict(policy_binding(policy))
    if forge_staged_policy_bound_record_count is not None or unbind_staged_policy:
        binding["policy_sha256"] = staged_policy["sha256"]      # the binding follows the staged copy
    if forge_manifest_topology_record_count is not None:
        binding["topology"] = copy.deepcopy(binding["topology"])
        binding["topology"]["tables"]["Spell"]["header"]["record_count"] = \
            forge_manifest_topology_record_count
    if forge_manifest_policy_sha256 is not None:
        binding["policy_sha256"] = forge_manifest_policy_sha256
    binding["derivations"] = {
        "coa_client_advancement.jsonl": advancement_derivation if advancement_derivation is not None else
        {"source": "CharacterAdvancement", "kept": advancement_kept,
         "rejected": advancement_source - advancement_kept},
        "coa_client_content.jsonl": content_derivation if content_derivation is not None else
        {"source": "content_json", "source_entries": content_entries, "kept": content_entries,
         "rejected": 0},
    }
    if drop_derivations:
        binding.pop("derivations")

    if not drop_contract:
        staged = stage_generation_contract(gw, mutate=contract_mutate, contract=contract)
        binding.update(generation_contract_binding(staged))
    elif contract is not None:
        binding.update(generation_contract_binding(contract))
    if bind_override is not None:
        binding["generation_contract"] = bind_override
    if drop_binding:
        binding.pop("generation_contract", None)

    if duplicate_json_document is not None:
        # Two concatenated documents, registered HONESTLY: `_scan_child` counts every non-JSONL child as
        # exactly one record regardless of content, so the manifest stays perfectly self-consistent and
        # only parsing catches the second document.
        path = gw.gen_dir / duplicate_json_document
        body = path.read_bytes()
        path.write_bytes(body + body)
        gw._children[duplicate_json_document]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        gw._children[duplicate_json_document]["byte_length"] = path.stat().st_size

    candidate = gw.publish_candidate(base_manifest=dict(base_manifest or {}), binding=binding)

    if extra_child is not None:
        name, body = extra_child
        (gw.gen_dir / name).write_bytes(body)          # on disk but NOT registered: the whitelist case
    if return_writer:
        return gw, candidate
    return gw.gen_dir


# E0R.2 T2.4: policy-shaped ceilings a fixture generation comfortably fits under.
GENEROUS_CEILINGS = {
    "max_serialized_bytes_per_child": 16 * 1024 * 1024,
    "max_whole_generation_bytes": 64 * 1024 * 1024,
    "python_peak_rss_mb": 16384, "python_elapsed_s": 3600,
    "node_peak_rss_mb": 16384, "node_elapsed_s": 3600,
}


def staged_writer(root, *, oversized=False, **kwargs):
    """A COMPLETE staged candidate plus the writer that staged it and the ceilings it fits under, so a
    test can drive `finalize_and_publish` directly (E0R.2 T2.4).

    `oversized=True` returns ceilings the staged children BREACH while the test still hands finalize a
    report claiming `within_budget: True` — the case that proves the byte check is recomputed from the
    staged children rather than read off the caller's verdict."""
    gw, candidate = stage_candidate(root, return_writer=True, **kwargs)
    ceilings = dict(GENEROUS_CEILINGS)
    if oversized:
        ceilings["max_serialized_bytes_per_child"] = 1     # one byte: every staged child breaches
    return gw, candidate, ceilings


def clean_budget(ceilings: dict) -> dict:
    """A report shaped exactly like `policy_budget_report`'s output, claiming a clean verdict."""
    return {"whole_generation_bytes": None, "measured": {}, "ceilings": dict(ceilings),
            "within_budget": True, "breach": []}


def write_lock(root, policy_doc: dict) -> Path:
    """Write the policy lock beside a generation root. The lock is what 'locally supported' means for
    both languages — the honest policy's digest, which a candidate cannot supply."""
    path = Path(root) / "spell_layout.lock.json"
    path.write_text(json.dumps({"schema_version": "coa-spell-layout-lock-v1",
                                "sha256": policy_doc["sha256"]}), encoding="utf-8")
    return path


def validate_staged(gen_dir, **kwargs):
    """Validate a fixture-staged candidate against the lock the fixture wrote. The fixture's synthetic
    policy is what is 'locally supported' for a test, exactly as the committed lock is in production."""
    from coa_client_extract.publish import validate_candidate_generation

    return validate_candidate_generation(gen_dir, lock_path=gen_dir.parent / "spell_layout.lock.json",
                                         **kwargs)


# Back-compat alias: T1.1/T1.2 built "a complete candidate" through this name.
stage_minimal_generation = stage_candidate
