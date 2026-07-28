#!/usr/bin/env node
// OPT-IN, image-download-ONLY utility. This is the ONLY surviving db.ascension.gg touch in the repo: it
// downloads icon IMAGE files (jpg) for a caller-supplied list of icon slugs. It is NEVER invoked or
// imported by a canonical build (which is pointer-only + network-free) — a human runs it by hand to
// refresh local icon art, and E0R.1 gates that hand-run twice:
//   1. it refuses to run without an explicit `--authorize` (acknowledging the network access), and
//   2. it only ever writes under a `diagnostic/` directory — never into canonical dist/ assets.
//
//   node scripts/download-spell-icons.mjs --authorize --icons path/to/slugs.txt --out diagnostic/icons
//   node scripts/download-spell-icons.mjs --authorize --icon inv_misc_qirajicrystal
//
// slugs.txt is one icon slug per line (blank lines and '#' comments ignored).
import fs from "node:fs";
import path from "node:path";

const ICON_URL_TEMPLATES = [
  "https://db.ascension.gg/static/images/wow/icons/large/{icon}.jpg",
  "https://db.ascension.gg/static/images/wow/icons/medium/{icon}.jpg",
  "https://db.ascension.gg/static/images/wow/icons/small/{icon}.jpg",
];

const DEFAULT_OUT_DIR = path.join("diagnostic", "icons");

export function isDiagnosticDir(outDir) {
  return path.resolve(outDir).split(path.sep).includes("diagnostic");
}

function sanitize(slug) {
  return String(slug || "").trim().toLowerCase().replace(/[^a-z0-9_]+/g, "");
}

function readSlugs({ iconsFile, singleIcon }) {
  const out = [];
  if (singleIcon) out.push(singleIcon);
  if (iconsFile) {
    for (const line of fs.readFileSync(iconsFile, "utf8").split("\n")) {
      const s = line.trim();
      if (s && !s.startsWith("#")) out.push(s);
    }
  }
  return [...new Set(out.map(sanitize).filter(Boolean))];
}

async function fetchIcon(slug) {
  for (const template of ICON_URL_TEMPLATES) {
    const url = template.replace("{icon}", slug);
    try {
      const res = await fetch(url);
      if (res.ok) return Buffer.from(await res.arrayBuffer());
    } catch { /* try the next size */ }
  }
  return null;
}

export async function downloadSpellIcons({ slugs, outDir, authorized = false }) {
  if (!authorized) {
    throw new Error("refusing: downloading icon images requires explicit --authorize");
  }
  if (!isDiagnosticDir(outDir)) {
    throw new Error(`refusing: --out must be under a diagnostic/ directory, got ${outDir}`);
  }
  fs.mkdirSync(outDir, { recursive: true });
  const summary = { requested: slugs.length, downloaded: 0, skipped: 0, missing: [] };
  for (const slug of slugs) {
    const dest = path.join(outDir, `${slug}.jpg`);
    if (fs.existsSync(dest)) { summary.skipped += 1; continue; }
    const bytes = await fetchIcon(slug);
    if (!bytes) { summary.missing.push(slug); continue; }
    fs.writeFileSync(dest, bytes);
    summary.downloaded += 1;
  }
  return summary;
}

function isCliEntryPoint() {
  return process.argv[1] && import.meta.url === new URL(`file://${path.resolve(process.argv[1])}`).href;
}

if (isCliEntryPoint()) {
  const args = process.argv.slice(2);
  const flag = (name, def = null) => { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : def; };
  const authorized = args.includes("--authorize");
  const iconsFile = flag("--icons");
  const singleIcon = flag("--icon");
  const outDir = flag("--out", DEFAULT_OUT_DIR);
  const usage = "usage: download-spell-icons.mjs --authorize (--icons <file> | --icon <slug>) [--out diagnostic/<dir>]";
  if (!authorized) {
    console.error(`refusing: this utility fetches icon images from the AscensionDB host and requires explicit --authorize\n${usage}`);
    process.exit(2);
  }
  if (!iconsFile && !singleIcon) { console.error(usage); process.exit(2); }
  if (!isDiagnosticDir(outDir)) {
    console.error(`refusing: --out must be under a diagnostic/ directory (got ${outDir})\n${usage}`);
    process.exit(2);
  }
  const slugs = readSlugs({ iconsFile, singleIcon });
  downloadSpellIcons({ slugs, outDir, authorized })
    .then((s) => console.log(JSON.stringify(s, null, 2)))
    .catch((err) => { console.error(`error: ${err.message}`); process.exit(1); });
}
