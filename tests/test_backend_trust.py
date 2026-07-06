from __future__ import annotations

from coa_meta.backend_trust import (
    BACKEND_TRUST_SCHEMA_VERSION,
    TrustComponent,
    TrustResult,
    load_live_sanity_watchlist,
    match_watchlist,
    trust_label_from_score,
)


def test_trust_result_serializes_component_scores_without_user_copy():
    result = TrustResult(
        schema_version=BACKEND_TRUST_SCHEMA_VERSION,
        subject_id="Testclass:Damage:build-1",
        trust_label="medium",
        score=0.66,
        components=(
            TrustComponent(
                component_id="mechanics_coverage",
                score=0.7,
                weight=0.25,
                notes=("Some inferred mechanics.",),
            ),
        ),
        watchlist_matches=tuple(),
        warnings=("mechanics_inferred",),
    )

    payload = result.to_dict()

    assert payload["schema_version"] == "coa-backend-trust-v1"
    assert payload["trust_label"] == "medium"
    assert payload["components"][0]["component_id"] == "mechanics_coverage"
    assert "user_facing_text" not in payload


def test_trust_label_thresholds_are_coarse():
    assert trust_label_from_score(0.86) == "high"
    assert trust_label_from_score(0.60) == "medium"
    assert trust_label_from_score(0.30) == "low"


def test_live_sanity_watchlist_entries_are_backend_only():
    entries = load_live_sanity_watchlist()

    assert entries
    assert all(entry.not_user_facing for entry in entries)
    assert all(entry.confidence in {"low", "medium", "high"} for entry in entries)
    assert any(entry.class_name == "Venomancer" for entry in entries)


def test_watchlist_matches_class_spec_and_role():
    entries = load_live_sanity_watchlist()

    matches = match_watchlist(
        entries,
        class_name="Venomancer",
        source_spec_name="Stalking",
        guide_role="melee_dps",
    )

    assert matches
    assert matches[0].not_user_facing is True
