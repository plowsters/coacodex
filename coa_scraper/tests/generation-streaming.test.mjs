// coa_scraper/tests/generation-streaming.test.mjs
// E0R.2 T5.3 — a bounded-retention RSS gate through the REAL canonical mechanics build.
//
// E0R.1 named "projection consumption -> mechanics serialization" as in scope for the streaming work,
// but the RSS test that shipped measured candidate VALIDATION instead (e0r1-streaming-node.test.mjs).
// The path that actually peaked at 866 MB on the real client had no gate at all. This runs
// buildMechanicsArtifact itself, in an isolated subprocess, at two projection sizes.
//
// The property is BOUNDED ROW RETENTION, not sub-linear growth: the retained id set does grow with the
// projection (one integer per row), so the honest claim is that RSS must not grow in proportion to the
// projection's ROW COUNT. Measured as an absolute delta against a pinned threshold.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const PROBE = fileURLToPath(new URL("./_canonical_build_probe.mjs", import.meta.url));

// Derived from the REVIEWED policy budget (coa_client_extract/data/spell_layout_v2.json), not invented:
// node_peak_rss_mb is 4096, and the canonical build is one stage of the Node side, so half of it is the
// ceiling this stage may claim. Absolute numbers are valid only under the benchmark_env the generation
// manifest pins — a different machine invalidates the ABSOLUTE bound, never the delta.
const NODE_PEAK_RSS_MB = 4096;
const STAGE_CEILING_MB = NODE_PEAK_RSS_MB / 2;
const DELTA_CEILING_MB = 150;

function probe(rows) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), `t53-${rows}-`));
  try {
    const built = spawnSync(process.execPath, [PROBE, "build", String(rows), root],
                            { encoding: "utf8", timeout: 600_000 });
    assert.equal(built.status, 0, built.stderr);
    const run = spawnSync(process.execPath, [PROBE, "run", root], { encoding: "utf8", timeout: 600_000 });
    assert.equal(run.status, 0, run.stderr);
    const out = JSON.parse(run.stdout.trim().split("\n").pop());
    // The measurement is worthless unless the build really saw every row: a projection that failed to
    // load, or a domain that silently shrank, would report a beautifully small peak.
    assert.equal(out.projection_rows, rows, "the build must have streamed the whole projection");
    assert.equal(out.record_count, 3600, "the Builder domain is fixed at both sizes");
    return out;
  } finally {
    // The E0R.1 probe leaked its temp dirs and filled the tmpfs, which then presented as a "memory
    // regression". Cleanup is part of the measurement.
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("canonical build peak RSS is bounded as the projection scales 10k -> 100k rows", () => {
  const small = probe(10_000);
  const large = probe(100_000);
  const delta = large.peak_rss_mb - small.peak_rss_mb;
  assert.ok(delta < DELTA_CEILING_MB,
    `peak RSS grew ${delta.toFixed(0)}MB as the projection went 10k->100k rows ` +
    `(${JSON.stringify(small)} -> ${JSON.stringify(large)}); the projection is a LOOKUP, so a 10x ` +
    "row count must not cost 10x memory");
  assert.ok(large.peak_rss_mb < STAGE_CEILING_MB,
    `the canonical build peaked at ${large.peak_rss_mb}MB against a ${STAGE_CEILING_MB}MB stage ceiling ` +
    `(half of the reviewed policy's node_peak_rss_mb=${NODE_PEAK_RSS_MB})`);
});
