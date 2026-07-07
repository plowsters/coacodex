from pathlib import Path

from coa_meta.guide_writer import FONT_ASSET_DIR, write_guide_site
from coa_meta.reporting import MetaReportRunner, MetaRunConfig

FIXTURES = Path(__file__).parent / "fixtures"


def _report():
    return MetaReportRunner(MetaRunConfig(
        entries_path=FIXTURES / "meta_report_fixture.jsonl",
        classes_path=FIXTURES / "meta_classes.json",
        class_names=("Testclass",), top=1, beam_width=2, branch_width=2,
        require_budget_fraction=0.0,
    )).run()


def test_write_guide_site_copies_fonts(tmp_path):
    assert any(FONT_ASSET_DIR.glob("*.woff2")), "vendor fonts first (scripts/fetch_guide_fonts.py)"
    write_guide_site(_report(), tmp_path, entries_path=FIXTURES / "meta_report_fixture.jsonl")
    copied = list((tmp_path / "assets" / "fonts").glob("*.woff2"))
    assert copied, "no woff2 copied into assets/fonts/"
