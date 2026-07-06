from __future__ import annotations

from pathlib import Path

from coa_meta import cli


class DummyReport:
    def to_dict(self):
        return {"schema_version": "coa-meta-report-v1"}


class DummyRunner:
    last_config = None

    def __init__(self, config):
        DummyRunner.last_config = config

    def run(self):
        return DummyReport()


def test_meta_cli_dispatches_to_runner_and_writers(monkeypatch, tmp_path):
    written = {}

    def fake_write_outputs(
        report,
        out_dir,
        formats,
        asset_resolver=None,
        entries_path=None,
        db_tooltips_path=None,
        builder_layout_root=None,
    ):
        written["report"] = report
        written["out_dir"] = Path(out_dir)
        written["formats"] = formats
        written["asset_resolver"] = asset_resolver
        return (Path(out_dir) / "meta-report.json",)

    monkeypatch.setattr(cli, "MetaReportRunner", DummyRunner)
    monkeypatch.setattr(cli, "write_report_outputs", fake_write_outputs)

    exit_code = cli.main(
        [
            "meta",
            "--entries",
            "coa_scraper/dist/coa_entries.jsonl",
            "--classes",
            "coa_scraper/dist/coa_classes.json",
            "--class",
            "Venomancer",
            "--spec",
            "Stalker",
            "--level",
            "60",
            "--top",
            "2",
            "--beam-width",
            "4",
            "--branch-width",
            "8",
            "--require-budget-fraction",
            "0.5",
            "--role",
            "tank",
            "--simulate",
            "--simulation-duration",
            "60",
            "--simulation-iterations",
            "2",
            "--simulation-seed",
            "99",
            "--gear-profile",
            "gear.json",
            "--format",
            "json",
            "--format",
            "html",
            "--out",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert DummyRunner.last_config is not None
    assert DummyRunner.last_config.entries_path == Path("coa_scraper/dist/coa_entries.jsonl")
    assert DummyRunner.last_config.classes_path == Path("coa_scraper/dist/coa_classes.json")
    assert DummyRunner.last_config.class_names == ("Venomancer",)
    assert DummyRunner.last_config.spec_names_or_ids == ("Stalker",)
    assert DummyRunner.last_config.top == 2
    assert DummyRunner.last_config.beam_width == 4
    assert DummyRunner.last_config.branch_width == 8
    assert DummyRunner.last_config.require_budget_fraction == 0.5
    assert DummyRunner.last_config.role == "tank"
    assert DummyRunner.last_config.simulate is True
    assert DummyRunner.last_config.simulation_duration_ms == 60_000
    assert DummyRunner.last_config.simulation_iterations == 2
    assert DummyRunner.last_config.simulation_seed == 99
    assert DummyRunner.last_config.gear_profile_path == Path("gear.json")
    assert written["formats"] == ("json", "html")
    assert written["out_dir"] == tmp_path


def test_meta_cli_logs_progress_stages(monkeypatch, tmp_path, capsys):
    def fake_write_outputs(
        report,
        out_dir,
        formats,
        asset_resolver=None,
        entries_path=None,
        db_tooltips_path=None,
        builder_layout_root=None,
    ):
        return (Path(out_dir) / "meta-report.json",)

    monkeypatch.setattr(cli, "MetaReportRunner", DummyRunner)
    monkeypatch.setattr(cli, "write_report_outputs", fake_write_outputs)

    exit_code = cli.main(
        [
            "meta",
            "--entries",
            "coa_scraper/dist/coa_entries.jsonl",
            "--classes",
            "coa_scraper/dist/coa_classes.json",
            "--format",
            "json",
            "--out",
            str(tmp_path),
        ]
    )

    stderr = capsys.readouterr().err
    assert exit_code == 0
    assert "[coa-meta] Starting meta report" in stderr
    assert "[coa-meta] Running build search and scoring" in stderr
    assert "[coa-meta] Writing outputs" in stderr
    assert "[coa-meta] Complete" in stderr


def test_meta_cli_passes_guide_context_to_writer(monkeypatch, tmp_path):
    written = {}

    def fake_write_outputs(
        report,
        out_dir,
        formats,
        asset_resolver=None,
        entries_path=None,
        db_tooltips_path=None,
        builder_layout_root=None,
    ):
        written["entries_path"] = entries_path
        written["db_tooltips_path"] = db_tooltips_path
        written["builder_layout_root"] = builder_layout_root
        written["asset_resolver"] = asset_resolver
        return (Path(out_dir) / "index.html",)

    monkeypatch.setattr(cli, "MetaReportRunner", DummyRunner)
    monkeypatch.setattr(cli, "write_report_outputs", fake_write_outputs)

    exit_code = cli.main(
        [
            "meta",
            "--entries",
            "coa_scraper/dist/coa_entries.jsonl",
            "--classes",
            "coa_scraper/dist/coa_classes.json",
            "--db-tooltips",
            "coa_scraper/dist/coa_db_spell_tooltips.jsonl",
            "--asset-root",
            "coa_scraper/data/raw",
            "--builder-layout-root",
            "coa_scraper/reports/tree_layout",
            "--format",
            "html",
            "--out",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert written["entries_path"] == Path("coa_scraper/dist/coa_entries.jsonl")
    assert written["db_tooltips_path"] == Path("coa_scraper/dist/coa_db_spell_tooltips.jsonl")
    assert written["builder_layout_root"] == Path("coa_scraper/reports/tree_layout")
    assert written["asset_resolver"] is not None


def test_meta_cli_accepts_new_guide_role_values(monkeypatch, tmp_path):
    calls = {}

    class DummyGuideRoleRunner:
        def __init__(self, config):
            calls["config"] = config

        def run(self):
            return DummyReport()

    monkeypatch.setattr(cli, "MetaReportRunner", DummyGuideRoleRunner)
    monkeypatch.setattr(cli, "write_report_outputs", lambda *args, **kwargs: tuple())

    exit_code = cli.main(
        [
            "meta",
            "--entries",
            str(tmp_path / "entries.jsonl"),
            "--role",
            "caster_dps",
            "--format",
            "json",
            "--out",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    assert calls["config"].role == "caster_dps"


def test_cli_returns_nonzero_for_unknown_command(capsys):
    exit_code = cli.main(["unknown"])

    assert exit_code == 2
    assert "usage:" in capsys.readouterr().err
