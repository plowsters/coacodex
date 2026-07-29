# tests/test_e0r2_source_bindings.py
"""E0R.2 T0.2: every source a cardinality rule cites must be BOUND before the contract can cite it.

Two gaps at c97d7d5:

  * `topology.verify_source_topology` iterates `policy.required_tables` and requires WDBC magic, and
    required_tables was only the five Spell-side tables — so the CharacterAdvancement* / SkillLineAbility
    DBCs were never captured and never bound. A cardinality rule citing them had nothing to read.
  * `coa_client_content.jsonl` has no DBC source AT ALL. `read_content_records` reads five JSON files
    from <client>/Content and silently `continue`s past any that is missing, so a client shipping four
    of five files yields a smaller generation with no signal anywhere. It needs its own binding kind.

Captured from the live client (3.3.5a+patch-T), and every one reconciles against the published
generation a9663d1b:

    CharacterAdvancementClassTypes   46 rows  ==  coa_client_class_types.jsonl   46
    CharacterAdvancementTabTypes     94 rows  ==  coa_client_tab_types.jsonl     94
    CharacterAdvancementEssence    5600 rows  ==  coa_client_essence.jsonl     5600
    Content JSON (5 files)        52744 ent.  ==  coa_client_content.jsonl    52744
    CharacterAdvancement          10182 rows  ->  3614 kept + 6568 rejected  (filtered)
"""
import json
from pathlib import Path

import pytest

from coa_client_extract.content_json import ContentSourceError, read_bound_content
from coa_client_extract.spell_layout import SpellPolicyError, compute_policy_sha256, load_spell_policy

REPO = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO / "coa_client_extract/data/spell_layout_v2.json"
ANCILLARY = {"CharacterAdvancement", "CharacterAdvancementClassTypes",
             "CharacterAdvancementTabTypes", "CharacterAdvancementEssence", "SkillLineAbility"}
CONTENT_FILES = {"SpellRankData.json", "SpellToStatSuggestionData.json",
                 "SpellToRoleSuggestionData.json", "ItemVariationData.json",
                 "CharacterAdvancementData.json"}


def _policy_doc():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _rehash(doc):
    doc.pop("sha256", None)
    doc["sha256"] = compute_policy_sha256(doc)
    return doc


# --------------------------------------------------------------------------- DBC source bindings

def test_the_ancillary_dbc_sources_are_required_and_bound():
    doc = _policy_doc()
    assert ANCILLARY <= set(doc["required_tables"])
    assert ANCILLARY <= set(doc["bound"]["tables"])
    assert ANCILLARY <= set(doc["tables"])


def test_every_bound_ancillary_table_carries_a_real_header():
    """Captured from the client, never invented: these are the numbers the cardinality rules read."""
    bound = _policy_doc()["bound"]["tables"]
    expected = {"CharacterAdvancement": 10182, "CharacterAdvancementClassTypes": 46,
                "CharacterAdvancementTabTypes": 94, "CharacterAdvancementEssence": 5600,
                "SkillLineAbility": 40904}
    for name, records in expected.items():
        entry = bound[name]
        assert entry["header"]["magic"] == "WDBC"
        assert entry["header"]["record_count"] == records, name
        assert len(entry["sha256"]) == 64
        assert entry["source"]["member"] == f"DBFilesClient\\{name}.dbc"


def test_the_ancillary_counts_reconcile_with_the_published_generation():
    """The whole point of binding them: the 1:1 children must equal their source record counts."""
    bound = _policy_doc()["bound"]["tables"]
    manifest = json.loads(
        (REPO / "reports/client_extract/gen-a9663d1b410841dd8284cb7538c61185/manifest.json")
        .read_text(encoding="utf-8"))
    children = manifest["children"]
    for child, table in (("coa_client_class_types.jsonl", "CharacterAdvancementClassTypes"),
                         ("coa_client_tab_types.jsonl", "CharacterAdvancementTabTypes"),
                         ("coa_client_essence.jsonl", "CharacterAdvancementEssence")):
        assert children[child]["records"] == bound[table]["header"]["record_count"], child


def test_a_policy_whose_bound_omits_a_required_table_is_rejected():
    doc = _policy_doc()
    doc["bound"]["tables"].pop("SkillLineAbility")
    with pytest.raises(SpellPolicyError, match="bound.tables must equal required_tables"):
        load_spell_policy(_rehash(doc))


# --------------------------------------------------------------------------- content source binding

def test_the_policy_declares_every_content_source():
    sources = _policy_doc()["content_sources"]
    assert sources["directory"] == "Content"
    assert set(sources["required_files"]) == CONTENT_FILES
    for filename, spec in sources["required_files"].items():
        assert len(spec["sha256"]) == 64, filename
        assert isinstance(spec["source_entries"], int) and spec["source_entries"] > 0, filename
        assert spec["kind"], filename


def test_the_content_source_entries_sum_to_the_published_child():
    sources = _policy_doc()["content_sources"]["required_files"]
    manifest = json.loads(
        (REPO / "reports/client_extract/gen-a9663d1b410841dd8284cb7538c61185/manifest.json")
        .read_text(encoding="utf-8"))
    assert sum(s["source_entries"] for s in sources.values()) == \
        manifest["children"]["coa_client_content.jsonl"]["records"]


def test_load_spell_policy_rejects_an_incoherent_content_sources_block():
    doc = _policy_doc()
    doc["content_sources"]["required_files"]["SpellRankData.json"]["source_entries"] = -1
    with pytest.raises(SpellPolicyError, match="source_entries"):
        load_spell_policy(_rehash(doc))


def test_load_spell_policy_rejects_a_missing_content_sources_block():
    doc = _policy_doc()
    del doc["content_sources"]
    with pytest.raises(SpellPolicyError, match="content_sources"):
        load_spell_policy(_rehash(doc))


# --------------------------------------------------------------------------- the bound content reader

@pytest.fixture()
def content_env(tmp_path):
    """A content directory plus a policy bound to exactly its bytes."""
    import hashlib

    payloads = {
        "SpellRankData.json": [{"Spell": 1, "Rank": 1}, {"Spell": 2, "Rank": 2}],
        "SpellToStatSuggestionData.json": [{"Spell": 1, "Stat": "int"}],
        "SpellToRoleSuggestionData.json": [{"Spell": 1, "Role": "dps"}],
        "ItemVariationData.json": [{"Item": 5, "V": 1}],
        "CharacterAdvancementData.json": [{"Spell": 9, "Node": 3}],
    }
    kinds = {"SpellRankData.json": "spell_rank",
             "SpellToStatSuggestionData.json": "spell_stat_suggestion",
             "SpellToRoleSuggestionData.json": "spell_role_suggestion",
             "ItemVariationData.json": "item_variation",
             "CharacterAdvancementData.json": "character_advancement"}
    content_dir = tmp_path / "Content"
    content_dir.mkdir()
    required = {}
    for filename, payload in payloads.items():
        raw = (json.dumps(payload) + "\n").encode("utf-8")
        (content_dir / filename).write_bytes(raw)
        required[filename] = {"kind": kinds[filename],
                              "sha256": hashlib.sha256(raw).hexdigest(),
                              "source_entries": len(payload)}
    doc = _policy_doc()
    doc["content_sources"] = {"directory": "Content", "required_files": required}
    return content_dir, load_spell_policy(_rehash(doc))


def test_a_bound_content_read_returns_records_and_a_closing_derivation(content_env):
    content_dir, policy = content_env
    result = read_bound_content(content_dir, policy=policy)
    assert result.derivation["source_entries"] == 6
    assert result.derivation["kept"] + result.derivation["rejected"] == result.derivation["source_entries"]
    assert result.derivation["kept"] == len(result.records)
    assert {r["content_kind"] for r in result.records} == {
        "spell_rank", "spell_stat_suggestion", "spell_role_suggestion", "item_variation",
        "character_advancement"}


def test_a_missing_content_file_is_blocking_not_silently_skipped(content_env):
    """The defect: the old reader `continue`s past a missing file, so a client shipping four of five
    produces a smaller generation with no signal anywhere."""
    content_dir, policy = content_env
    (content_dir / "ItemVariationData.json").unlink()
    with pytest.raises(ContentSourceError, match="ItemVariationData.json"):
        read_bound_content(content_dir, policy=policy)


def test_a_content_file_whose_bytes_changed_is_rejected(content_env):
    content_dir, policy = content_env
    (content_dir / "ItemVariationData.json").write_text('[{"Item": 5, "V": 999}]', encoding="utf-8")
    with pytest.raises(ContentSourceError, match="sha256"):
        read_bound_content(content_dir, policy=policy)


def test_a_content_file_with_an_unexpected_entry_count_is_rejected(content_env, tmp_path):
    """A file whose bytes match but whose declared entry count does not is a bound-policy error, and
    the accounting identity must never be satisfiable by adjusting the expectation at read time."""
    content_dir, policy = content_env
    doc = _policy_doc()
    doc["content_sources"] = {
        "directory": "Content",
        "required_files": {**{k: dict(v) for k, v in policy.content_sources["required_files"].items()}},
    }
    doc["content_sources"]["required_files"]["SpellRankData.json"]["source_entries"] = 99
    with pytest.raises(ContentSourceError, match="source_entries"):
        read_bound_content(content_dir, policy=load_spell_policy(_rehash(doc)))


def test_an_extra_unbound_file_in_the_content_directory_is_ignored(content_env):
    """Only the REQUIRED set is read; an unrelated file the client ships must not silently enter the
    generation."""
    content_dir, policy = content_env
    (content_dir / "SomethingElse.json").write_text('[{"Spell": 77}]', encoding="utf-8")
    result = read_bound_content(content_dir, policy=policy)
    assert result.derivation["source_entries"] == 6
    assert all(r["provenance"]["source_file"] != "SomethingElse.json" for r in result.records)
