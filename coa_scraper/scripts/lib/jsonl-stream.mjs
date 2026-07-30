// coa_scraper/scripts/lib/jsonl-stream.mjs
// The shared JSONL streaming primitive, as a LEAF module: it imports nothing of ours.
//
// E0R.2 T5.1. `readJsonlLines` lived in generation.mjs, which already imports four things FROM
// mechanics-projection.mjs — so the canonical build could not reuse it without creating an import
// cycle, and read its 400 MB projection whole instead. Extracting the primitive is what lets both
// trust boundaries stream over the same code rather than one of them re-implementing it.
//
// Fixed-size reads with a byte-level carry, so a multi-byte character split across a chunk boundary is
// still decoded once and correctly. Nothing here retains a row, a line, or the file.
import crypto from "node:crypto";
import fs from "node:fs";

export const CHUNK = 1 << 20;

export class JsonlParseError extends Error {
  constructor(filePath, lineNo, cause) {
    super(`${filePath} line ${lineNo}: invalid JSON: ${cause.message}`);
    this.name = "JsonlParseError";
    this.filePath = filePath;
    this.lineNo = lineNo;
    this.cause = cause;
  }
}

function parseLine(line, filePath, lineNo) {
  try {
    return JSON.parse(line);
  } catch (err) {
    throw new JsonlParseError(filePath, lineNo, err);
  }
}

// The one loop. `hash` and `state` are optional sinks: when present every chunk is fed to them BEFORE
// any line splitting, so the running digest is over the exact bytes on disk — blank lines, trailing
// newline and all — and therefore equals a whole-file sha256 of the same file.
function* iterate(filePath, hash, state) {
  const fd = fs.openSync(filePath, "r");
  try {
    const buf = Buffer.allocUnsafe(CHUNK);
    let rem = Buffer.alloc(0);
    let lineNo = 0;
    while (true) {
      const n = fs.readSync(fd, buf, 0, CHUNK, null);
      if (n === 0) break;
      const chunk = buf.subarray(0, n);
      if (hash) hash.update(chunk);
      if (state) state.byteLength += n;
      const data = rem.length ? Buffer.concat([rem, chunk]) : chunk;
      let start = 0, idx;
      while ((idx = data.indexOf(0x0a, start)) !== -1) {
        lineNo += 1;
        const line = data.toString("utf8", start, idx);
        if (line.trim()) yield { row: parseLine(line, filePath, lineNo), lineNo };
        start = idx + 1;
      }
      rem = Buffer.from(data.subarray(start));   // copy: `buf` is reused by the next read
    }
    const tail = rem.toString("utf8");
    if (tail.trim()) yield { row: parseLine(tail, filePath, lineNo + 1), lineNo: lineNo + 1 };
  } finally {
    fs.closeSync(fd);
  }
}

// Sync generator over a JSONL file, yielding one parsed row at a time — never a whole-file string or a
// row array (E0R.1 T4.2).
export function* readJsonlLines(filePath) {
  for (const { row } of iterate(filePath, null, null)) yield row;
}

// The same stream, with the file's sha256 and byte length accumulated AS it is consumed, so a consumer
// that needs both the rows and the file's identity reads the bytes exactly once.
//
// `sha256()` and `byteLength()` describe what has been READ so far: call them after the generator is
// exhausted, or they describe a prefix. `sha256()` is memoized because a crypto hash can only be
// digested once.
export function readJsonlLinesHashed(filePath) {
  const hash = crypto.createHash("sha256");
  const state = { byteLength: 0 };
  let digest = null;
  return {
    rows: iterate(filePath, hash, state),
    sha256() {
      if (digest === null) digest = hash.digest("hex");
      return digest;
    },
    byteLength() { return state.byteLength; },
  };
}
