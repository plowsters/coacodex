# tests/test_e0r_acceptance_summary.py
from coa_client_extract.cli import write_acceptance_summary, _parse_gnu_time


def _fake_manifest():
    return {
        "schema_version": "coa-client-extract-manifest-v3",
        "client_build": "3.3.5a+patch-CZZ",
        "generation_id": "abc123",
        "extractor_commit": "deadbeef",
        "binding": {"policy_sha256": "f817b59b"},
        "budget": {"within_budget": True, "serialized_mb": 3.2, "peak_rss_mb": 210.0, "elapsed_s": 94.1},
        "children": {"coa_client_spell.jsonl": {"sha256": "aa", "byte_length": 10, "records": 2}},
    }


def test_acceptance_summary_has_stable_fields(tmp_path):
    summary = write_acceptance_summary(
        tmp_path, _fake_manifest(), recon_status="verified", benchmark_env_id="local-x86-64",
        build_mechanics={"elapsed_s": 4.2, "peak_rss_mb": 210, "pointer_only": True})
    assert set(summary) >= {"client_build", "generation_id", "manifest_sha256", "policy_sha256",
                            "extractor_commit", "benchmark_env_id", "children", "budget", "recon_status",
                            "build_mechanics"}
    assert summary["recon_status"] == "verified"
    assert summary["build_mechanics"]["pointer_only"] is True
    assert summary["client_build"] == "3.3.5a+patch-CZZ"
    assert summary["policy_sha256"] == "f817b59b"
    assert summary["children"]["coa_client_spell.jsonl"]["records"] == 2


def test_acceptance_summary_writes_file(tmp_path):
    out = tmp_path / "summary.json"
    write_acceptance_summary(tmp_path, _fake_manifest(), recon_status="verified", benchmark_env_id="ci",
                             build_mechanics={"pointer_only": True}, out=out)
    assert out.is_file()


def test_parse_gnu_time_extracts_elapsed_and_peak_rss():
    sample = (
        "\tCommand being timed: \"npm run build-mechanics\"\n"
        "\tElapsed (wall clock) time (h:mm:ss or m:ss): 0:12.34\n"
        "\tMaximum resident set size (kbytes): 215040\n"
    )
    parsed = _parse_gnu_time(sample)
    assert parsed["elapsed_s"] == 12.34
    assert parsed["peak_rss_mb"] == 210.0
