// coa_scraper/tests/jsonl-stream.test.mjs
// E0R.2 T5.1 — the shared JSONL streaming primitive.
//
// It has to be a LEAF module: generation.mjs already imports from mechanics-projection.mjs, so a
// primitive living in either of them cannot be reused by the other without an import cycle. That is why
// the canonical build read its projection whole in the first place.
import { test } from "node:test";
import assert from "node:assert";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { CHUNK, JsonlParseError, readJsonlLines, readJsonlLinesHashed }
  from "../scripts/lib/jsonl-stream.mjs";

function write(body) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "jsonl-"));
  const file = path.join(dir, "rows.jsonl");
  fs.writeFileSync(file, body);
  return file;
}

function rowsFile(n, { pad = 0 } = {}) {
  let body = "";
  for (let i = 1; i <= n; i++) body += JSON.stringify({ id: i, filler: "x".repeat(pad) }) + "\n";
  return write(body);
}

test("the module imports nothing of ours", () => {
  const src = fs.readFileSync(new URL("../scripts/lib/jsonl-stream.mjs", import.meta.url), "utf8");
  const ours = [...src.matchAll(/from\s+"([^"]+)"/g)].map((m) => m[1]).filter((s) => s.startsWith("."));
  assert.deepEqual(ours, [], `a leaf module must import no local module, got ${ours}`);
});

test("rows stream out one at a time", () => {
  const file = rowsFile(2000);
  let seen = 0, last = 0;
  for (const row of readJsonlLines(file)) { seen += 1; last = row.id; }
  assert.equal(seen, 2000);
  assert.equal(last, 2000);
});

test("a row spanning a chunk boundary is decoded once and correctly", () => {
  // Rows padded so that lines straddle the 1 MiB read boundary rather than aligning with it.
  const file = rowsFile(200, { pad: 20000 });
  const ids = [...readJsonlLines(file)].map((r) => r.id);
  assert.equal(ids.length, 200);
  assert.deepEqual(ids.slice(0, 3), [1, 2, 3]);
  assert.ok(fs.statSync(file).size > CHUNK, "the fixture must actually cross a chunk boundary");
});

test("a multi-byte character split across a chunk boundary survives", () => {
  // "…" is 3 bytes; place one so the read boundary lands mid-character.
  const filler = "a".repeat(CHUNK - 2);
  const file = write(JSON.stringify({ id: 1, s: `${filler}…tail` }) + "\n");
  const [row] = [...readJsonlLines(file)];
  assert.ok(row.s.includes("…tail"));
  assert.equal(row.s.length, filler.length + 5);
});

test("blank lines are skipped, and a file with no trailing newline still yields its last row", () => {
  const file = write('{"id":1}\n\n   \n{"id":2}');
  assert.deepEqual([...readJsonlLines(file)].map((r) => r.id), [1, 2]);
});

test("a malformed line names the file and the line number", () => {
  const file = write('{"id":1}\n{"id":\n{"id":3}\n');
  assert.throws(() => [...readJsonlLines(file)], (err) => {
    assert.ok(err instanceof JsonlParseError);
    assert.equal(err.lineNo, 2);
    assert.match(err.message, /line 2: invalid JSON/);
    return true;
  });
});

test("the incremental hash equals a whole-file hash", () => {
  const file = rowsFile(5000);
  const stream = readJsonlLinesHashed(file);
  let seen = 0;
  for (const { row } of stream.rows) { seen += 1; assert.ok(row.id); }
  const whole = fs.readFileSync(file);
  assert.equal(seen, 5000);
  assert.equal(stream.sha256(), crypto.createHash("sha256").update(whole).digest("hex"));
  assert.equal(stream.byteLength(), whole.length);
});

test("the hash covers the exact bytes on disk, including blank lines and the trailing newline", () => {
  // A digest computed from re-serialized rows would agree with a whole-file hash only by luck; this
  // fixture has bytes no row carries.
  const body = '{"id":1}\n\n{"id":2}\n\n\n';
  const file = write(body);
  const stream = readJsonlLinesHashed(file);
  assert.deepEqual([...stream.rows].map((r) => r.row.id), [1, 2]);
  assert.equal(stream.sha256(), crypto.createHash("sha256").update(Buffer.from(body)).digest("hex"));
});

test("sha256() is stable across calls", () => {
  const file = rowsFile(10);
  const stream = readJsonlLinesHashed(file);
  [...stream.rows];
  assert.equal(stream.sha256(), stream.sha256());
});

test("the file descriptor is closed even when the consumer stops early", () => {
  const file = rowsFile(1000);
  const before = fs.readdirSync("/proc/self/fd").length;
  for (const row of readJsonlLines(file)) if (row.id === 3) break;   // generator return() -> finally
  assert.ok(fs.readdirSync("/proc/self/fd").length <= before,
            "an abandoned stream must not leak a descriptor");
});
