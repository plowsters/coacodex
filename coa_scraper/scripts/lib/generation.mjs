import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

export class GenerationResolveError extends Error {}

const POINTER_SCHEMA = "coa-client-extract-pointer-v1";
const POINTER_NAME = "coa_client_extract.pointer.json";
const MANIFEST_NAME = "manifest.json";
const RESERVED = new Set([MANIFEST_NAME, POINTER_NAME]);

function sha256(buf) { return crypto.createHash("sha256").update(buf).digest("hex"); }

function assertSafeChildName(name) {
  const parts = name.split(/[\\/]/);
  if (!name || RESERVED.has(name) || path.isAbsolute(name) || parts.includes("..") ||
      name.includes("/") || name.includes("\\")) {
    throw new GenerationResolveError(`unsafe child name ${name}`);
  }
}

// Equivalent validation to the Python resolve_active_generation: fails closed on pointer schema,
// gen-dir containment, manifest hash, and each child's path/sha256/byte_length/record-count/schema/
// uniqueness. `rootOrPointer` may be the directory holding the pointer OR the pointer file itself.
export function resolveGeneration(rootOrPointer) {
  let pointerPath = rootOrPointer;
  if (fs.existsSync(rootOrPointer) && fs.statSync(rootOrPointer).isDirectory()) {
    pointerPath = path.join(rootOrPointer, POINTER_NAME);
  }
  const root = path.resolve(path.dirname(pointerPath));
  if (!fs.existsSync(pointerPath)) throw new GenerationResolveError("no active generation pointer");

  let pointer;
  try { pointer = JSON.parse(fs.readFileSync(pointerPath, "utf8")); }
  catch (e) { throw new GenerationResolveError(`pointer invalid JSON: ${e.message}`); }
  if (pointer.schema_version !== POINTER_SCHEMA) throw new GenerationResolveError(`pointer bad schema_version ${pointer.schema_version}`);
  const genId = pointer.generation_id;
  if (typeof genId !== "string" || !genId) throw new GenerationResolveError("pointer missing generation_id");

  const genDir = path.resolve(root, `gen-${genId}`);
  if (path.relative(root, genDir).startsWith("..")) throw new GenerationResolveError("generation dir escapes root");
  const manifestPath = path.join(genDir, MANIFEST_NAME);
  if (!fs.existsSync(manifestPath)) throw new GenerationResolveError("generation manifest missing");

  const manifestBytes = fs.readFileSync(manifestPath);
  if (sha256(manifestBytes) !== pointer.manifest_sha256) throw new GenerationResolveError("manifest sha256 does not match the pointer");
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  if (manifest.generation_id !== genId) throw new GenerationResolveError("manifest generation_id disagrees with the pointer");
  // A candidate manifest is never consumable (an interrupted publish leaves no half-live generation).
  if (manifest.publication_state === "candidate") throw new GenerationResolveError("pointer resolves a candidate manifest (never publishable)");
  // Pre-E0R generations are rejected: E0R consumers require the manifest-v3 transaction.
  if (manifest.schema_version && manifest.schema_version !== "coa-client-extract-manifest-v3" &&
      manifest.schema_version !== "coa-client-extract-manifest-v2") {
    throw new GenerationResolveError(`unsupported manifest schema_version ${manifest.schema_version}`);
  }

  const children = manifest.children || {};
  const resolved = {};
  const seen = new Set();
  for (const [name, meta] of Object.entries(children)) {
    assertSafeChildName(name);
    if (seen.has(name)) throw new GenerationResolveError(`duplicate child ${name}`);
    seen.add(name);
    const childPath = path.resolve(genDir, name);
    if (path.dirname(childPath) !== genDir) throw new GenerationResolveError(`child ${name} escapes the generation directory`);
    if (!fs.existsSync(childPath)) throw new GenerationResolveError(`child ${name} missing`);
    const body = fs.readFileSync(childPath);
    if (sha256(body) !== meta.sha256) throw new GenerationResolveError(`child ${name} sha256 mismatch`);
    if (body.length !== meta.byte_length) throw new GenerationResolveError(`child ${name} byte_length mismatch`);
    const records = name.endsWith(".jsonl")
      ? body.toString("utf8").split("\n").filter((l) => l.trim()).length : 1;
    if (records !== meta.records) throw new GenerationResolveError(`child ${name} record count mismatch (${records} != ${meta.records})`);
    if (!meta.schema_version) throw new GenerationResolveError(`child ${name} missing schema_version`);
    resolved[name] = childPath;
  }
  return { generationId: genId, genDir, manifest, children: resolved };
}

// CLI: `node lib/generation.mjs <pointer-or-root>` prints the resolved child paths (exit 0) or the
// validation error (exit 3), so the transactional contract is scriptable from the shell / e2e test.
function isCliEntryPoint() {
  return process.argv[1] && import.meta.url === new URL(`file://${path.resolve(process.argv[1])}`).href;
}
if (isCliEntryPoint()) {
  const target = process.argv[2];
  if (!target) { console.error("usage: generation.mjs <pointer-or-root>"); process.exit(2); }
  try {
    const r = resolveGeneration(target);
    console.log(JSON.stringify({ generation_id: r.generationId, children: r.children }, null, 2));
  } catch (e) {
    console.error(`error: ${e.message}`);
    process.exit(3);
  }
}
