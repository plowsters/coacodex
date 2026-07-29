// coa_scraper/tests/helpers/golden.mjs
// E0R.2 T2.2: the golden document per shape, taken from what the PRODUCER emits.
//
// The producer is Python, so Node reads the documents through it rather than hand-copying rows that
// would drift the moment a builder changes. That is deliberate: the two shape implementations are
// independent, but the documents they are held to are the SAME ones, which is what makes their
// agreement mean something.
import { execFileSync } from "node:child_process";

const REPO = new URL("../../../", import.meta.url).pathname;

let _cache = null;

export function goldenDocuments() {
  if (_cache === null) {
    const out = execFileSync("python3", ["-c", `
import json
from coa_client_extract.shapes import SHAPES
from tests.golden import golden_rows, producer_spell_rows
docs = {shape: golden_rows(shape) for shape in SHAPES}
full, projection, icon = producer_spell_rows()
print(json.dumps({"shapes": docs, "producer": {"full": full, "projection": projection, "icon": icon}}))
`], { cwd: REPO, encoding: "utf8", maxBuffer: 64 << 20,
      env: { ...process.env, PYTHONPATH: REPO } });
    _cache = JSON.parse(out);
  }
  return _cache;
}

export function goldenRows(shape) {
  const docs = goldenDocuments().shapes;
  if (!(shape in docs)) throw new Error(`no golden document for shape ${shape}`);
  return structuredClone(docs[shape]);
}

export function producerSpellRows() {
  return structuredClone(goldenDocuments().producer);
}
