"""One representative document per contract shape, taken from what the PRODUCER actually emits.

E0R.2 T2.2: a shape validator is only worth anything if its positive case is the real thing. Rather
than hand-copying rows (which drift the moment a builder changes), this runs the synthetic regenerate
once per session and reads the rows back out of the published generation. If a producer starts emitting
a different shape, the golden row changes with it and the shape test fails — which is the signal wanted.

The three spell children come from the shared golden corpus instead, because that is the corpus Node
validates against too, and holding both languages to the same rows is what keeps the two independent
shape implementations honest.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

CORPUS = Path(__file__).resolve().parent / "golden" / "e0r1_corpus"
CORPUS_V4 = Path(__file__).resolve().parent / "golden" / "e0r2_corpus_v4"

_GENERATION: Path | None = None


def _corpus_row(name: str, case: str, corpus: Path = CORPUS) -> dict:
    for line in (corpus / name).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["case"] == case:
            return {k: v for k, v in row.items() if k not in ("case", "golden_accept")}
    raise LookupError(f"no {case!r} row in {name}")


def _generation() -> Path:
    """The synthetic regenerate's published generation directory, built once per session."""
    global _GENERATION
    if _GENERATION is None:
        from tests.test_client_extract_cli import (_bound_spell_policy, _client, _fake_backend,
                                                   _synthetic_layouts)
        from coa_client_extract.cli import regenerate
        from coa_client_extract.publish import resolve_active_generation

        root = Path(tempfile.mkdtemp(prefix="e0r2-golden-"))
        client_root = _client(root)
        out = root / "out"
        policy = _bound_spell_policy(_fake_backend(), client_root)
        lock = root / "spell_layout.lock.json"
        lock.write_text(json.dumps({"schema_version": "coa-spell-layout-lock-v1",
                                    "sha256": policy.sha256}))
        regenerate(client_root, out, backend=_fake_backend(), layouts=_synthetic_layouts(),
                   spell_policy=policy, node_lock_path=lock)
        _GENERATION = resolve_active_generation(out)["gen_dir"]
    return _GENERATION


def _first_row(child: str) -> dict:
    return json.loads((_generation() / child).read_text().splitlines()[0])


def _document(child: str) -> dict:
    return json.loads((_generation() / child).read_text())


_CORPUS_SHAPES = {
    "full_spell_row_v3": ("full_rows.jsonl", "valid_full"),
    "projection_row_v3": ("projection_rows.jsonl", "valid"),
    "icon_row_v1": ("icons.jsonl", "valid_icon"),
}
# E0R.2 T6.2: the v4 baseline lives in its own corpus directory BESIDE the v3 one, because `e0r-v1`
# stays a supported revision and its rows must keep validating against the shape they were produced
# with. Everything else in the corpus is shared — the projection dialect does not change in v4.
_CORPUS_V4_SHAPES = {
    "full_spell_row_v4": ("full_rows.jsonl", "valid_full"),
}
_PRODUCER_DOC_SHAPES_V4 = {
    "spell_field_descriptors_v1": "coa_client_spell_fields.json",
    "observation_wire_v1": "observation_wire_schema.json",
}
_PRODUCER_ROW_SHAPES = {
    "content_row_v1": "coa_client_content.jsonl",
    "advancement_row_v1": "coa_client_advancement.jsonl",
    "class_type_row_v1": "coa_client_class_types.jsonl",
    "tab_type_row_v1": "coa_client_tab_types.jsonl",
    "essence_row_v1": "coa_client_essence.jsonl",
}
_PRODUCER_DOC_SHAPES = {
    "archive_plan_v1": "coa_client_archive_plan.json",
    "projection_manifest_v3": "coa_client_spell_projection.manifest.json",
    "spell_policy_v2": "spell_layout_v2.json",
    "generation_contract_v1": "generation_contract.json",
}


def golden_rows(shape: str) -> dict:
    if shape in _CORPUS_SHAPES:
        return _corpus_row(*_CORPUS_SHAPES[shape])
    if shape in _CORPUS_V4_SHAPES:
        return _corpus_row(*_CORPUS_V4_SHAPES[shape], corpus=CORPUS_V4)
    if shape in _PRODUCER_DOC_SHAPES_V4:
        return _document(_PRODUCER_DOC_SHAPES_V4[shape])
    if shape in _PRODUCER_ROW_SHAPES:
        return _first_row(_PRODUCER_ROW_SHAPES[shape])
    if shape in _PRODUCER_DOC_SHAPES:
        return _document(_PRODUCER_DOC_SHAPES[shape])
    raise LookupError(f"no golden document for shape {shape!r}")


def producer_spell_rows() -> tuple[dict, dict, dict]:
    """The full / projection / icon rows the REAL producer emits, as distinct from the corpus rows.
    Both must satisfy the same shape — the corpus is a hand-authored subset and could otherwise drift
    away from what is actually published."""
    return (_first_row("coa_client_spell.jsonl"), _first_row("coa_client_spell_coa.jsonl"),
            _first_row("coa_client_spell_icons.jsonl"))
