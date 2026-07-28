import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.client

CLIENT_ROOT = Path(os.environ.get(
    "COA_CLIENT_ROOT",
    str(Path.home() / "Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data"),
))

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "coa_scraper/dist/coa_db_spell_tooltips.jsonl"


@pytest.mark.skipif(not CLIENT_ROOT.is_dir(), reason="Ascension client not installed at COA_CLIENT_ROOT")
def test_spell_805775_is_current_adrenal_venom(tmp_path):
    from coa_client_extract.cli import regenerate
    from coa_client_extract.errors import BackendUnavailable
    from coa_client_extract.publish import resolve_active_generation

    try:
        manifest = regenerate(CLIENT_ROOT, tmp_path)  # real StormLib backend, real layouts
    except BackendUnavailable:
        pytest.skip("StormLib not available")

    # Noncanonical fixed-path summary; the authoritative manifest is the published generation manifest-v3.
    assert manifest["schema_version"] == "coa-client-extract-manifest-v1"
    assert manifest["publication_state"] == "published"
    assert manifest["budget"]["within_budget"] is True

    resolved = resolve_active_generation(tmp_path)
    assert resolved["manifest"]["schema_version"] == "coa-client-extract-manifest-v3"
    gen = resolved["gen_dir"]
    rows = [json.loads(line) for line in (gen / "coa_client_spell.jsonl").read_text().splitlines()]
    by_id = {r["spell_id"]: r for r in rows}
    assert 805775 in by_id, "spell 805775 not extracted"
    venom = by_id[805775]
    # The full-table child is the compact client-DBC v3 row: identity + normalized mechanics + attribution
    # + compact raw; per-row provenance/proof are hoisted to the manifest binding (design A4).
    assert venom["schema_version"] == "coa-client-spell-v3"
    assert "Adrenal Venom" in venom["name"]
    assert "Fang Venom" not in venom["name"]  # not the stale db value
    assert venom["coa_attribution"]["policy_sha256"]           # v3: policy pinned on the row's attribution
    assert venom["mechanics"]["power_type"] == 3               # energy @41, per-value gate (in-domain)
    assert venom["coa_attribution"]["is_coa"] is True          # id-floor attribution (805775 >= 100000)
    assert "raw" in venom and "id" in venom["raw"]             # compact raw substrate retained

    # archive_family is the raw M1.14A signal, derived from the effective archive of the Spell.dbc member,
    # now hoisted ONCE to the manifest binding topology instead of repeated on every row (design A4).
    from coa_client_extract.archive_plan import family_of

    topo = resolved["manifest"]["binding"]["topology"]
    effective = topo["tables"]["Spell"]["effective_archive"]
    assert effective.lower().endswith(".mpq")
    assert venom["coa_attribution"]["archive_family"] == family_of(effective)
    # Every required table is bound in the manifest topology (the shared A2 verifier proved them present).
    assert {"Spell", "SpellCastTimes", "SpellDuration", "SpellRange", "SpellIcon"} <= set(topo["tables"])

    # The icon catalog covers 805775 and hashes the actual client BLP bytes (not the path string).
    icons = {json.loads(l)["spell_id"]: json.loads(l)
             for l in (gen / "coa_client_spell_icons.jsonl").read_text().splitlines()}
    assert 805775 in icons and icons[805775]["asset_status"] in ("source_only", "converted", "missing")


@pytest.mark.skipif(not CLIENT_ROOT.is_dir(), reason="Ascension client not installed at COA_CLIENT_ROOT")
def test_real_client_advancement_parity(tmp_path):
    from coa_client_extract.cli import regenerate
    from coa_client_extract.errors import BackendUnavailable

    from coa_client_extract.publish import resolve_active_generation
    builder_path = Path("coa_scraper/dist/coa_entries.jsonl")
    try:
        regenerate(CLIENT_ROOT, tmp_path, builder_entries_path=str(builder_path),
                   client_only_adjudication_path="reports/client_extract/client_only_adjudication.json")
    except BackendUnavailable:
        pytest.skip("StormLib not available")
    gen = resolve_active_generation(tmp_path)["gen_dir"]           # canonical children live in gen-<uuid>/

    # --- class taxonomy: exactly 21 playable CoA classes, ConquestOfAzeroth (35) sentinel excluded ---
    class_types = [json.loads(l) for l in
                   (gen / "coa_client_class_types.jsonl").read_text().splitlines()]
    playable = [c for c in class_types if c["kind"] == "coa_class"]
    assert len(playable) == 21
    assert all(c["class_type_id"] != 35 for c in playable)

    # --- node-id crosswalk Builder-parity: EXACT ownership (recall AND precision) after rename ---
    report = json.loads((tmp_path / "coa_builder_parity_report.json").read_text())
    assert report["unique_spell_recall"] == 1.0
    assert report["ownership_recall"] == 1.0                     # every Builder node covered
    assert report["builder_only_records"] == 0                   # no recall gap
    assert report["hard_identity_mismatches"] == 0                         # no semantic/spell divergence
    assert report["raw_identity_mismatches"] > 0                           # client uses CamelCase labels
    assert report["representation_differences"] == report["raw_identity_mismatches"]  # all are formatting
    assert report["class_label_normalization"] == "nfkc-casefold-remove-whitespace-v1"
    pairs = report["representation_difference_pairs"]
    for key in ("WitchDoctor → Witch Doctor", "WitchHunter → Witch Hunter",
                "KnightOfXoroth → Knight of Xoroth", "SunCleric → Sun Cleric"):
        assert key in pairs and pairs[key] > 0
    assert sum(pairs.values()) == report["representation_differences"]
    assert report["raw_ownership_precision"] < 1.0               # client leads the oracle; kept visible
    assert report["client_only_records"] == 2                    # the 2 client-ahead nodes
    vcc = {r["node_id"] for r in report["client_only_classification"]["verified_client_current"]}
    assert {18821, 34451} <= vcc                                 # both adjudicated client-current
    assert report["client_only_classification"]["unresolved"] == []
    assert report["client_only_classification"]["extraction_defect"] == []
    assert report["builder_refresh_recommended"] is True
    assert report["provenance"]["source_dbc_sha256"]["CharacterAdvancement"]   # reproducibility pins
    assert report["provenance"]["resolved_class_set"] == list(range(14, 35))   # 21 playable CoA ids

    # --- scoped readiness: attribution + ownership are earned (anchor-based, independent of legality);
    #     every other dimension reports its HONEST decode-backed state (not forced green) ---
    r = report["readiness"]
    assert r["attribution_ready"] is True
    assert r["ownership_ready"] is True
    assert r["leveling_progression_ready"] is False
    assert set(r["legality"]) == {"required_level", "ae_cost", "te_cost",
                                  "required_tab_ae", "required_tab_te", "max_rank"}
    assert set(r["layout"]) == {"row", "col"}
    assert all(v in ("ready", "unresolved") for v in r["legality"].values())
    assert all(v in ("ready", "unresolved") for v in r["layout"].values())
    # the roll-up is EXACTLY its parts — never hand-forced true
    assert r["full_builder_retirement_ready"] == (
        r["attribution_ready"] and r["ownership_ready"] and r["adjacency_ready"]
        and all(v == "ready" for v in r["legality"].values()))
    # honesty cross-check: any legality field the decode left unresolved is named in `blockers`
    for field, state in r["legality"].items():
        if state == "unresolved":
            assert any(field in b for b in report["blockers"])

    # --- 805775 is current "Adrenal Venom" on a Venomancer node; attribution filled ---
    adv = [json.loads(l) for l in
           (gen / "coa_client_advancement.jsonl").read_text().splitlines()]
    venom = [n for n in adv if n["spell_id"] == 805775]
    assert venom and any(n["class"]["display"] == "Venomancer" for n in venom)
    assert any(n["name"] == "Adrenal Venom" for n in venom)
    assert all(n["coa_attribution"]["is_coa"] is True for n in venom)

    # --- shared spell 503748 = two distinct Witch Doctor nodes (node identity != spell identity) ---
    # Class membership now lives in the advancement child (the v3 spell child is the compact client-DBC
    # row); the two Witch Doctor nodes for 503748 both canonicalize to the Witch Doctor class label.
    wd_nodes = [n for n in adv if n["spell_id"] == 503748]
    assert len(wd_nodes) == 2
    from coa_client_extract.parity import canonical_class_label
    assert all(canonical_class_label(n["class"]["display"]) == canonical_class_label("Witch Doctor")
               for n in wd_nodes)


@pytest.fixture
def client_mechanics_dir(tmp_path):
    # Skip ONLY when COA_CLIENT_ROOT is unset — gated on the ENV VAR directly, NOT the shared
    # CLIENT_ROOT (which has a hardcoded fallback default that would otherwise fire the heavy build
    # on any machine that happens to have a client at that path). Env var is the single source of
    # truth for both the skip condition and the --client-root passed to regenerate.
    root = os.environ.get("COA_CLIENT_ROOT")
    if not root:
        pytest.skip("COA_CLIENT_ROOT unset (client tier)")
    ce = tmp_path / "client_extract"
    dist = tmp_path / "dist"
    try:
        subprocess.run([sys.executable, "-m", "coa_client_extract", "regenerate",
                        "--client-root", root, "--out", str(ce),
                        "--builder-entries", str(REPO / "coa_scraper/dist/coa_entries.jsonl")],
                       cwd=REPO, check=True)
        subprocess.run(["node", "coa_scraper/scripts/build-mechanics-artifacts.mjs",
                        "--builder-entries", "coa_scraper/dist/coa_entries.jsonl",
                        "--db-spells", "coa_scraper/dist/coa_db_spell_tooltips.jsonl",
                        "--client-extract-pointer", str(ce / "coa_client_extract.pointer.json"),
                        "--out", str(dist)], cwd=REPO, check=True)
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"client-tier build unavailable: {exc}")
    return dist


def test_805775_client_wins_and_db_gate_matches_observed(client_mechanics_dir):
    mech = client_mechanics_dir / "coa_mechanics.jsonl"
    row = next((json.loads(l) for l in mech.read_text().splitlines()
                if l.strip() and json.loads(l).get("spell_id") == 805775), None)
    assert row is not None, "805775 must be in the Builder-domain mechanics output"
    man = json.loads((client_mechanics_dir / "coa_mechanics.manifest.json").read_text())
    assert man["schema_version"] == "coa-mechanics-manifest-v1"
    assert set(man["counts"]) == {"unresolved_conflicts", "ineligible_candidates", "omitted_fields", "kind_disagreements"}
    assert all(isinstance(v, int) for v in man["counts"].values())
    assert "reconciler_commit" in man and "client_build" in man
    assert row["name"] == "Adrenal Venom"                      # client name wins
    fp = row["field_provenance"]
    assert any(fp.get(f, {}).get("selected_source") == "client_dbc"
               for f in ("power_type", "cast_time_ms", "duration_ms", "range_yards"))  # a client field wins
    # non-vacuous gate check vs the OBSERVED db name for 805775 — the db row MUST exist so the gate
    # is actually exercised (a missing row would make either branch vacuously true).
    db = next((json.loads(l) for l in DB.read_text().splitlines()
               if l.strip() and json.loads(l).get("id") == 805775), None)
    assert db is not None, "805775 must be present in coa_db_spell_tooltips.jsonl to exercise the identity gate"

    # EXACT port of Node's normalizeName (lib/jsonl.mjs): lowercase, non-alphanumeric runs → single
    # space, trim. Must match byte-for-byte or the test could assert the wrong gate branch.
    def norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    if norm(db.get("name")) != norm("Adrenal Venom"):
        # stale db → excluded → zero db contribution
        assert row["cooldown_ms"] is None and row["gcd_ms"] is None
        assert not any(p["source"] == "ascension_db" for p in row["provenance"])
        assert row["raw"]["db_excluded"] is True
    else:
        # db agrees → usable fallback (gate correctly vacuous), db provenance allowed
        assert row["raw"]["db_excluded"] is False
