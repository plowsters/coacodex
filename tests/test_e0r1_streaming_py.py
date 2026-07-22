# tests/test_e0r1_streaming_py.py
"""E0R.1 T4.1 — the Python producer -> writer -> validation path STREAMS: peak RSS in an isolated
subprocess grows sub-linearly as the synthetic record count scales 10k -> 100k (no whole-table row list,
no whole-child str+bytes double copy in the writer, validators read chunk/line-wise). Also pins the
writer's generator contract: add_jsonl consumes an iterable without materializing it."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _probe(n: int) -> dict:
    out = subprocess.run([sys.executable, "-m", "tests._streaming_probe", str(n)],
                         capture_output=True, text=True, cwd=str(REPO), timeout=1200)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_regenerate_peak_rss_is_bounded_as_records_scale():
    small, large = _probe(10_000), _probe(100_000)
    delta_mb = large["peak_rss_mb"] - small["peak_rss_mb"]
    # 10x the rows (~20x the serialized bytes vs the 10k run) must NOT cost ~10x the memory. A materialized
    # pipeline costs several hundred MB extra at 100k rows; a streaming one only the spooled index.
    assert delta_mb < 150, f"peak RSS grew {delta_mb:.0f}MB from 10k->100k rows ({small} -> {large})"


def test_add_jsonl_consumes_a_generator_without_materializing(tmp_path):
    from coa_client_extract.publish import GenerationWriter
    gw = GenerationWriter(tmp_path)
    gw.add_jsonl("coa_client_spell.jsonl", ({"schema_version": "coa-client-spell-v3", "spell_id": i}
                                            for i in range(1, 5001)),
                 schema_version="coa-client-spell-v3")
    meta = gw._children["coa_client_spell.jsonl"]
    assert meta["records"] == 5000
    lines = (gw.gen_dir / "coa_client_spell.jsonl").read_text().splitlines()
    assert len(lines) == 5000 and json.loads(lines[0])["spell_id"] == 1
