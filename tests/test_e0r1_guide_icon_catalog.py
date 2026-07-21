# tests/test_e0r1_guide_icon_catalog.py
"""E0R.1 T2.4 — the PRODUCTION guide-writing entry point (write_report_outputs) accepts an icon_catalog and
threads it to the client-native resolver, so guide icons render `client_icon` from a CONVERTED client asset
(or a placeholder for source_only/absent), NEVER a db.ascension.gg hotlink."""
from pathlib import Path

from coa_meta.guide_builder import load_client_icon_catalog
from coa_meta.reporting import MetaReportRunner, MetaRunConfig, write_report_outputs

FIXTURES = Path(__file__).parent / "fixtures"
ENTRIES = FIXTURES / "meta_report_fixture.jsonl"
_NODE_IDS = (1000, 1001, 1002, 2001, 2002, 3001)


def _report():
    return MetaReportRunner(MetaRunConfig(
        entries_path=ENTRIES, classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",), top=1, beam_width=2, branch_width=2,
        require_budget_fraction=0.0)).run()


def _html(paths):
    return "\n".join(p.read_text(encoding="utf-8") for p in paths if str(p).endswith(".html"))


def test_production_writer_threads_converted_client_icons(tmp_path):
    catalog = {sid: {"client_path": f"Interface/Icons/Icon_{sid}.blp", "asset_status": "converted",
                     "converted_ref": f"icons.tar#icon_{sid}.png"} for sid in _NODE_IDS}
    out = write_report_outputs(_report(), tmp_path, formats=("html",), entries_path=ENTRIES,
                               icon_catalog=catalog)
    html = _html(out)
    assert "icons.tar#icon_1000.png" in html           # the client catalog reached the resolver
    assert "db.ascension.gg" not in html                # NEVER a DB hotlink


def test_production_writer_without_catalog_renders_placeholders_not_remote(tmp_path):
    out = write_report_outputs(_report(), tmp_path, formats=("html",), entries_path=ENTRIES)
    html = _html(out)
    assert "icons.tar#" not in html                     # no converted asset without a catalog
    assert "db.ascension.gg" not in html


def test_source_only_catalog_is_placeholder_not_hotlink(tmp_path):
    catalog = {sid: {"client_path": f"Interface/Icons/Icon_{sid}.blp", "asset_status": "source_only"}
               for sid in _NODE_IDS}
    out = write_report_outputs(_report(), tmp_path, formats=("html",), entries_path=ENTRIES,
                               icon_catalog=catalog)
    html = _html(out)
    assert "icons.tar#" not in html                     # source_only is not browser-renderable -> placeholder
    assert "db.ascension.gg" not in html


def test_load_client_icon_catalog_keys_by_spell_id(tmp_path):
    p = tmp_path / "coa_client_spell_icons.jsonl"
    p.write_text('{"spell_id": 133, "asset_status": "converted", "converted_ref": "icons.tar#f.png"}\n'
                 '{"spell_id": 116, "asset_status": "placeholder", "client_path": null}\n', encoding="utf-8")
    cat = load_client_icon_catalog(p)
    assert cat[133]["asset_status"] == "converted" and cat[116]["asset_status"] == "placeholder"
    assert load_client_icon_catalog(None) is None
