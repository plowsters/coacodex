from __future__ import annotations

from pathlib import Path

from coa_meta.guide_builder import build_guide_site
from coa_meta.guide_models import GuideAsset, GuideBuildCard, GuideNode, GuideSite, GuideSpec
from coa_meta.guide_rendering import GUIDE_CSS, GUIDE_JS, render_index_html, render_spec_html
from coa_meta.guide_tooltips import sanitize_tooltip_html
from coa_meta.reporting import MetaReportRunner, MetaRunConfig


FIXTURES = Path(__file__).parent / "fixtures"


def _site():
    report = MetaReportRunner(
        MetaRunConfig(
            entries_path=FIXTURES / "meta_report_fixture.jsonl",
            classes_path=FIXTURES / "meta_classes.json",
            class_names=("Testclass",),
            top=1,
            beam_width=2,
            branch_width=2,
            require_budget_fraction=0.0,
        )
    ).run()
    return build_guide_site(report, entries_path=FIXTURES / "meta_report_fixture.jsonl")


def _hybrid_site():
    spec = GuideSpec(
        slug="guardian-inspiration",
        href="specs/guardian-inspiration.html",
        class_name="Guardian",
        spec_name="Inspiration",
        role="melee_dps",
        primary_role="melee_dps",
        secondary_roles=("support",),
        roles=("melee_dps", "support"),
        confidence_label="high",
        warning_count=0,
        summary="Melee support hybrid.",
        sections=("Overview", "Recommended Builds"),
        builds=(
            GuideBuildCard(
                rank=1,
                label="Hybrid Loop",
                confidence_label="high",
                projected_dps_index=121.0,
                primary_index=121.0,
                primary_index_label="Projected Damage Index",
                objective_id="damage",
                node_ids=tuple(),
                warnings=tuple(),
                playstyle_label="Hybrid Loop",
            ),
        ),
        nodes=tuple(),
        warnings=tuple(),
        role_provenance={"source": "authoritative_video"},
    )
    return GuideSite(
        schema_version="coa-guide-site-v1",
        generated_at="2026-07-05T00:00:00+00:00",
        index_path="index.html",
        legacy_index_path="meta-report.html",
        specs=(spec,),
        metric_definitions={},
        tooltips={},
        assets={},
        warnings=tuple(),
    )


def test_render_index_html_uses_player_facing_guide_shell():
    html = render_index_html(_site())

    assert "<!doctype html>" in html
    assert "CoA Codex" in html
    assert "Open guide" in html
    assert "data-role=" in html
    assert "Further accuracy tuning through combat logs/simming" in html
    assert "db.ascension.gg data" not in html
    assert "beam search" not in html.lower()


def test_pages_include_github_header_and_footer():
    site = _site()
    index_html = render_index_html(site)
    spec = next(item for item in site.specs if item.spec_name == "Damage")
    spec_html = render_spec_html(site, spec)

    for html in (index_html, spec_html):
        assert "https://github.com/plowsters/coacodex" in html
        assert "https://github.com/plowsters/coacodex/issues" in html
        assert "© 2026 CoA Codex" in html
        assert "Not affiliated with or endorsed by Project Ascension" in html
        assert 'aria-label="View source on GitHub"' in html


def test_index_groups_specs_by_role_and_supports_multi_role_filters():
    html = render_index_html(_site())

    assert "Tank" in html
    assert "Healer" in html
    assert "Support" in html
    assert "Caster DPS" in html
    assert "Ranged DPS" in html
    assert "Melee DPS" in html
    assert 'aria-pressed="true"' in html
    assert "selected.has(clicked)" in GUIDE_JS
    assert "data-role-section" in html


def test_role_filter_defaults_to_all_and_roles_start_unpressed():
    html = render_index_html(_site())

    all_button = html.split('data-role-filter="all"', 1)[1][:120]
    assert 'aria-pressed="true"' in all_button
    melee_button = html.split('data-role-filter="melee_dps"', 1)[1][:120]
    assert 'aria-pressed="false"' in melee_button
    assert "selected.size === 0" in GUIDE_JS


def test_index_places_hybrid_specs_in_secondary_role_sections():
    html = render_index_html(_hybrid_site())
    support_section = html.split('data-role-section="support"', 1)[1].split('data-role-section="caster_dps"', 1)[0]
    melee_section = html.split('data-role-section="melee_dps"', 1)[1]

    assert "Guardian - Inspiration" in support_section
    assert "Guardian - Inspiration" in melee_section
    assert 'data-role-chip="melee_dps"' in html
    assert 'data-role-chip="support"' in html


def test_index_spec_cards_render_spec_icon_image():
    html = render_index_html(_site())

    assert 'class="spec-icon"' in html
    segment = html.split('class="spec-icon"', 1)[1][:200]
    assert "<img" in segment


def test_render_spec_html_includes_sections_and_omits_empty_warnings():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "Overview" in html
    assert "Abilities and Talents" in html
    assert "Stat priorities are early theorycraft" in html
    assert 'id="warnings"' not in html
    assert "medium confidence" not in html


def test_render_spec_html_links_spell_and_tooltip_ids():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "https://db.ascension.gg/?spell=2001" in html
    assert 'data-tooltip-id="spell:2001"' in html


def test_render_spec_html_uses_local_icon_images_for_nodes():
    site = _hybrid_site()
    spec = site.specs[0]
    node = GuideNode(
        entry_id=1,
        spell_id=1001,
        name="Fel Strike",
        class_name="Guardian",
        tab_name="Class",
        essence_kind="ability",
        required_level=10,
        ae_cost=1,
        te_cost=0,
        tags=("melee",),
        active=True,
        db_url="https://db.ascension.gg/?spell=1001",
        tooltip_id="spell:1001",
        asset=GuideAsset(
            asset_id="icon:felstrike",
            kind="icon",
            label="Fel Strike",
            href="icons/fel_strike.png",
            source="ascension_db_asset",
            missing=False,
            source_path="dist/assets/icons/fel_strike.png",
        ),
    )
    spec = GuideSpec(
        **{
            **spec.__dict__,
            "nodes": (node,),
            "sections": (*spec.sections, "Abilities and Talents"),
        }
    )
    site = GuideSite(**{**site.__dict__, "specs": (spec,)})

    html = render_spec_html(site, spec)

    assert '<img src="../assets/icons/fel_strike.png"' in html
    assert "FS</span>" not in html


def test_tooltip_sanitizer_preserves_tables_and_strips_active_markup():
    sanitized = sanitize_tooltip_html(
        '<table onclick="bad()"><tr><td>Damage</td></tr></table>'
        '<script>alert(1)</script><img src=x onerror="bad()">'
    )

    assert "<table>" in sanitized
    assert "<tr>" in sanitized
    assert "<td>Damage</td>" in sanitized
    assert "onclick" not in sanitized
    assert "script" not in sanitized
    # Disallowed active markup is stripped entirely, not escaped into visible
    # literal text (which surfaced raw HTML in tooltips).
    assert "<img" not in sanitized
    assert "&lt;img" not in sanitized
    assert "onerror" not in sanitized


def test_render_spec_html_includes_static_talent_tree():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert 'class="talent-tree"' in html
    assert 'class="tree-links"' in html
    assert "data-tree-level-selector" in html
    assert 'data-tree-node-id="201"' in html
    assert "AE" in html
    assert "TE" in html


def test_spec_html_renders_exact_leveling_path_events():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "Leveling Path" in html
    assert "Ability" in html or "Talent" in html
    assert "No legal target choice" not in html


def test_leveling_path_omits_boilerplate_reason():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "as soon as it is legal" not in html
    assert 'class="muted">Take this' not in html


def test_render_spec_html_includes_separate_tree_groups_and_passive_lane():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert 'data-tree-kind="ability_essence"' in html
    assert 'data-tree-kind="talent_essence"' in html
    assert 'data-tree-kind="level_passives"' in html
    assert 'class="passive-lane"' in html
    assert 'data-tooltip-id="spell:2001"' in html


def test_spec_html_renders_build_playstyle_and_core_loop():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "Recommended Builds" in html
    assert "Core Loop" in html
    assert "Early theorycraft picks" not in html


def test_spec_html_prefers_simulated_rotation_guide_over_legacy_loop():
    site = _hybrid_site()
    build = GuideBuildCard(
        **{
            **site.specs[0].builds[0].__dict__,
            "rotation_loop": {"core_loop": ["Legacy loop should not render"], "objective": "Legacy objective"},
            "rotation_guide": {
                "schema_version": "coa-rotation-guide-v1",
                "source": "simulated",
                "reliability": "high",
                "simulation_summary": {"action_count": 42},
                "core_loop": [
                    {
                        "ability_name": "Fel Strike",
                        "text": "Use Fel Strike as part of the repeatable core loop.",
                        "db_url": "https://db.ascension.gg/?spell=1001",
                    }
                ],
                "priority_rules": [],
                "opener": [],
                "cooldown_rules": [],
                "proc_rules": [],
                "defensive_rules": [],
                "healing_rules": [],
                "support_rules": [],
                "aoe_adjustments": [],
                "warnings": [],
            },
        }
    )
    spec = GuideSpec(**{**site.specs[0].__dict__, "builds": (build,)})
    site = GuideSite(**{**site.__dict__, "specs": (spec,)})

    html = render_spec_html(site, spec)

    assert "Fel Strike" in html
    assert "Legacy loop should not render" not in html
    assert "high rotation reliability" in html


def test_spec_html_renders_role_specific_projected_index_label():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Support")

    html = render_spec_html(site, spec)

    assert "Projected Healing Index" in html
    assert 'data-tooltip-id="metric:primary_index"' in html


def test_spec_html_renders_grouped_stats_and_best_gear_targets():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "Best stats to target" in html
    assert "Stat priorities are early theorycraft" in html
    assert "Best targets for this spec" in html
    assert "Available to this class" in html


def test_static_assets_have_fel_void_theme_and_no_network_fetch():
    assert "#6cf06b" in GUIDE_CSS          # fel lead
    assert "#a879ff" in GUIDE_CSS          # void lead
    assert ':root[data-theme="void"]' in GUIDE_CSS
    assert "fetch(" not in GUIDE_JS


def test_header_has_theme_toggle_and_js_persists_choice():
    html = render_index_html(_site())
    assert "data-theme-toggle" in html
    assert 'data-theme-value="fel"' in html
    assert 'data-theme-value="void"' in html
    # persistence + application
    assert '"coa-theme"' in GUIDE_JS or "'coa-theme'" in GUIDE_JS
    assert "data-theme" in GUIDE_JS
    assert "localStorage" in GUIDE_JS


def test_static_tree_javascript_has_no_network_calls():
    assert "fetch(" not in GUIDE_JS
    assert "XMLHttpRequest" not in GUIDE_JS
    assert "getBoundingClientRect" in GUIDE_JS
    assert 'querySelectorAll("[data-tree-kind]")' in GUIDE_JS


def test_tree_css_keeps_desktop_geometry_and_horizontal_scroll():
    assert ".tree-scroll { overflow-x: auto" in GUIDE_CSS
    media_block = GUIDE_CSS.split("@media", 1)[1]
    assert "talent-tree" not in media_block
    assert "tree-group" not in media_block
    assert "passive-lane" not in media_block


def test_index_cards_do_not_surface_recommendation_confidence_badges():
    html = render_index_html(_site())

    assert "medium confidence" not in html


def test_spec_html_does_not_render_backend_trust_text():
    site = _site()
    spec = next(item for item in site.specs if item.spec_name == "Damage")

    html = render_spec_html(site, spec)

    assert "backend trust" not in html.lower()
    assert "live sanity" not in html.lower()


def test_index_tagline_drops_player_facing():
    html = render_index_html(_site())
    assert "Player-facing" not in html
    assert "Class and specialization guides for Conquest of Azeroth." in html
    assert "Meta Codex" in html


def test_guide_css_defines_self_hosted_font_faces():
    assert "@font-face" in GUIDE_CSS
    assert 'url("fonts/' in GUIDE_CSS
    assert "Cinzel" in GUIDE_CSS
    assert "Barlow" in GUIDE_CSS
    assert "JetBrains Mono" in GUIDE_CSS


def test_ember_canvas_respects_reduced_motion_and_has_no_network():
    assert "prefers-reduced-motion" in GUIDE_JS
    assert "requestAnimationFrame" in GUIDE_JS
    assert "getContext" in GUIDE_JS
    assert "fetch(" not in GUIDE_JS
    assert "XMLHttpRequest" not in GUIDE_JS


def test_index_shows_unique_spec_stat_line():
    site = _site()
    html = render_index_html(site)
    unique = len({spec.slug for spec in site.specs})
    assert "data-stat-line" in html
    assert f"{unique} spec" in html


def test_index_flagship_badge_only_on_tyrant():
    html = render_index_html(_hybrid_site())  # no tyrant -> no badge
    assert "data-flagship" not in html
