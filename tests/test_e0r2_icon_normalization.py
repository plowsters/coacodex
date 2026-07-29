"""E0R.2 T6.3: the icon catalog becomes two normalized children, and its nulls become explained.

The icon child is 66.1 MB over 14,022 unique paths across 179,774 resolved rows: every spell that shares
an icon repeats the whole path string, its BLP hash and its source archive. Normalizing to an ASSET
table plus an ASSOCIATION row keyed by a deterministic `asset_id` removes the repetition.

The second half is a correction that costs almost nothing and recovers real information. Verified in
`spell_icons.py`: the path was `jo.decoded if jo.decoded_reason == "decoded" else None`, so FOUR
distinct situations collapsed into one `placeholder` —

    index_zero        no FK at all             -> "this spell has no icon"
    side_row_missing  nonzero FK, no side row  -> "this spell's icon row is missing from the client"
    proof_withheld    promotion withheld       -> "the join is not adjudicated for promotion"
    not_present       the index cell is unproven

— and the producer CONSTRUCTED the JoinObservation for the first two and then threw it away. Carrying
the interned `s`/`d` codes onto the association row turns an unexplained null into an explained one.

`asset_id` is `sha256(canonical_path)[:32]` — content-derived, so byte-identical inputs produce
byte-identical generations regardless of encounter order. Truncation is a probability argument, so the
producer does not rest on it: any collision mapping one id to two distinct canonical paths RAISES.
"""
from __future__ import annotations

import hashlib

import pytest

from coa_client_extract.contracts import decoded_reason_code, observation_state_code
from coa_client_extract.spell_icons import (ASSET_SCHEMA, ASSOCIATION_SCHEMA, IconCollisionError,
                                            canonical_icon_path, icon_asset_id, icon_asset_table,
                                            icon_coverage, iter_icon_catalog)
from tests._spell_fixtures import icon_side_views, spell_dbc, v2_icon_policy


def _resolver(path):
    # BLP bytes distinct from the path string, so a path-hash would NOT match a bytes-hash. Keyed on the
    # canonical form because that is the identity the asset row stores.
    return {"bytes": b"BLP:" + canonical_icon_path(path).encode(), "archive": "patch-T.MPQ",
            "member": path, "patch_chain": []}


def _catalog(resolver=_resolver, policy=None):
    assets = icon_asset_table()
    rows = list(iter_icon_catalog(spell_dbc(), icon_side_views(), policy=policy or v2_icon_policy(),
                                  asset_resolver=resolver, assets=assets))
    return rows, assets


# --- the two children ---

def test_an_association_row_carries_a_reference_not_a_path():
    rows, assets = _catalog()
    row = {r["spell_id"]: r for r in rows}[805775]
    assert row["schema_version"] == ASSOCIATION_SCHEMA
    assert set(row) == {"schema_version", "spell_id", "spell_icon_id", "asset_ref", "s", "d",
                        "readiness"}
    assert row["asset_ref"] in {a["asset_id"] for a in assets.rows()}
    assert row["readiness"] == "available"


def test_the_asset_row_carries_the_path_the_association_no_longer_repeats():
    rows, assets = _catalog()
    asset = {a["asset_id"]: a for a in assets.rows()}[
        {r["spell_id"]: r for r in rows}[805775]["asset_ref"]]
    assert asset["schema_version"] == ASSET_SCHEMA
    assert set(asset) == {"schema_version", "asset_id", "client_path", "availability",
                          "source_asset_sha256", "source_archive"}
    assert asset["availability"] == "source_only"
    assert asset["source_asset_sha256"] == hashlib.sha256(
        b"BLP:" + asset["client_path"].encode()).hexdigest()
    assert asset["source_archive"] == "patch-T.MPQ"


def test_two_spells_sharing_an_icon_share_one_asset_row():
    """The whole point of normalizing: 179,774 rows over 14,022 paths."""
    rows, assets = _catalog()
    by_id = {r["spell_id"]: r for r in rows}
    assert by_id[133]["asset_ref"] == by_id[805775]["asset_ref"]
    assert len({a["asset_id"] for a in assets.rows()}) == len(list(assets.rows()))


def test_a_missing_asset_carries_no_hash_and_no_archive():
    """Hash and archive are non-null IFF the asset is `source_only` — the earlier model required them of
    every asset row, which a proven path with an absent member can never satisfy."""
    _, assets = _catalog(resolver=lambda p: None)
    for asset in assets.rows():
        assert asset["availability"] == "missing"
        assert asset["source_asset_sha256"] is None and asset["source_archive"] is None


# --- the four null causes are distinguishable ---

def test_a_null_reference_says_WHY_it_is_null():
    """`index_zero` and `side_row_missing` are different facts about the client and must not arrive as
    the same value. The producer already built the observation that knows which; it discarded it.

    Driven through the real producer with the SpellIcon side table absent, which is the
    `side_row_missing` case for every nonzero FK."""
    assets = icon_asset_table()
    rows = list(iter_icon_catalog(spell_dbc(), {}, policy=v2_icon_policy(),
                                  asset_resolver=_resolver, assets=assets))
    assert rows and len(assets) == 0
    for row in rows:
        assert row["asset_ref"] is None and row["readiness"] == "unavailable"
        assert row["d"] == decoded_reason_code("side_row_missing"), "an EXPLAINED null"
        assert row["d"] != decoded_reason_code("index_zero")


def test_index_zero_and_side_row_missing_are_told_apart():
    from coa_client_extract.spell_icons import _association

    zero = _association(1, 0, None, state="not_applicable", reason="index_zero")
    absent = _association(2, 7, None, state="unresolved", reason="side_row_missing")
    assert zero["d"] == decoded_reason_code("index_zero")
    assert absent["d"] == decoded_reason_code("side_row_missing")
    assert zero["d"] != absent["d"], "one placeholder for four causes is the information loss"
    assert zero["s"] == observation_state_code("not_applicable")
    assert absent["s"] == observation_state_code("unresolved")


# --- asset_id is content-derived, and collisions are refused ---

def test_asset_id_is_the_canonical_path_digest():
    path = "Interface\\Icons\\Spell_Fire_FlameBolt"
    assert canonical_icon_path(path) == "interface/icons/spell_fire_flamebolt"
    assert icon_asset_id(path) == hashlib.sha256(
        canonical_icon_path(path).encode("utf-8")).hexdigest()[:32]
    assert len(icon_asset_id(path)) == 32, "128 bits"


def test_case_and_separator_variants_are_one_asset():
    assert icon_asset_id("Interface\\Icons\\X") == icon_asset_id("interface/icons/x")


def test_asset_ids_are_stable_across_shuffled_input():
    """Encounter-order numbering would make byte-identical inputs produce different generations."""
    table_a, table_b = icon_asset_table(), icon_asset_table()
    paths = ["Interface\\Icons\\A", "Interface\\Icons\\B", "Interface\\Icons\\C"]
    for path in paths:
        table_a.record(path, sha256="a" * 64, archive="patch-T.MPQ")
    for path in reversed(paths):
        table_b.record(path, sha256="a" * 64, archive="patch-T.MPQ")
    assert sorted(a["asset_id"] for a in table_a.rows()) == sorted(b["asset_id"] for b in table_b.rows())
    assert [a["asset_id"] for a in table_a.rows()] == [a["asset_id"] for a in table_a.rows()]
    assert list(table_a.rows()) == sorted(table_a.rows(), key=lambda a: a["asset_id"])


def test_an_injected_collision_raises_rather_than_coalescing_two_icons(monkeypatch):
    """Truncation is a probability argument. Identity never rests on one: if two distinct canonical
    paths ever produce one id, that is two icons silently becoming one, and it fails closed."""
    import coa_client_extract.spell_icons as icons

    monkeypatch.setattr(icons, "icon_asset_id", lambda path: "f" * 32)
    table = icon_asset_table()
    table.record("Interface\\Icons\\A", sha256="a" * 64, archive="patch-T.MPQ")
    with pytest.raises(IconCollisionError, match="asset_id"):
        table.record("Interface\\Icons\\B", sha256="b" * 64, archive="patch-T.MPQ")


def test_recording_the_same_path_twice_is_not_a_collision():
    table = icon_asset_table()
    table.record("Interface\\Icons\\A", sha256="a" * 64, archive="patch-T.MPQ")
    table.record("interface/icons/a", sha256="a" * 64, archive="patch-T.MPQ")
    assert len(list(table.rows())) == 1


# --- coverage is unchanged for identical input ---

def test_icon_coverage_reports_the_same_totals_as_the_v1_catalog():
    rows, assets = _catalog()
    coverage = icon_coverage(rows, assets)
    assert coverage["spells"] == len(rows)
    assert coverage["resolved_paths"] == sum(1 for r in rows if r["asset_ref"] is not None)
    assert coverage["unique_paths"] == len(list(assets.rows()))
    assert coverage["assets_present"] + coverage["assets_missing"] == coverage["resolved_paths"]
    assert coverage["placeholders"] == sum(1 for r in rows if r["asset_ref"] is None)


def test_coverage_counts_spells_and_paths_in_their_own_units():
    """Two denominators that a normalized model makes it easy to confuse: `resolved_paths` counts SPELL
    ROWS with a reference, `unique_paths` counts ASSETS."""
    rows, assets = _catalog()
    coverage = icon_coverage(rows, assets)
    assert coverage["resolved_paths"] >= coverage["unique_paths"] > 0
