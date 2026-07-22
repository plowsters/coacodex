// coa_scraper/tests/e0r1-streaming-node.test.mjs
// E0R.1 T4.2 — the Node candidate validation path STREAMS: peak RSS in an isolated subprocess grows
// sub-linearly as the record count scales 10k -> 100k (chunked child scans, generator row readers, cursor
// cross-child — no whole-child readFileSync+split retained arrays). Pre-fix this path cost 201MB -> 912MB
// (+710MB); streamed it costs ~110MB -> ~157MB (+47MB) against a 150MB delta gate.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const PROBE = fileURLToPath(new URL("./helpers/streaming-probe.mjs", import.meta.url));

function probe(n) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), `t42-${n}-`));
  try {
    const built = spawnSync(process.execPath, [PROBE, "build", String(n), root], { encoding: "utf8", timeout: 600_000 });
    assert.equal(built.status, 0, built.stderr);
    const run = spawnSync(process.execPath, [PROBE, "validate", root], { encoding: "utf8", timeout: 600_000 });
    assert.equal(run.status, 0, run.stderr);
    const out = JSON.parse(run.stdout.trim().split("\n").pop());
    assert.equal(out.n, n);                                  // the validator really saw all N records
    return out;
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("Node candidate validation peak RSS is bounded as records scale 10k -> 100k", () => {
  const small = probe(10_000);
  const large = probe(100_000);
  const delta = large.peak_rss_mb - small.peak_rss_mb;
  assert.ok(delta < 150,
    `peak RSS grew ${delta.toFixed(0)}MB from 10k->100k rows (${JSON.stringify(small)} -> ${JSON.stringify(large)})`);
});
