#!/usr/bin/env node
// OPT-IN, image-download-ONLY utility. This is the ONLY surviving db.ascension.gg touch in the repo: it
// downloads icon IMAGE files (jpg) for a caller-supplied list of icon slugs to a local directory. It is
// NEVER invoked by a canonical build (which is pointer-only + network-free) — a human runs it by hand to
// refresh local icon art. It writes files and prints a summary; it emits no runtime URLs into artifacts.
//
//   node scripts/download-spell-icons.mjs --icons path/to/slugs.txt --out dist/assets/icons
//   node scripts/download-spell-icons.mjs --icon inv_misc_qirajicrystal --out dist/assets/icons
//
// slugs.txt is one icon slug per line (blank lines and '#' comments ignored).
import fs from "node:fs";
import path from "node:path";

const ICON_URL_TEMPLATES = [
  "https://db.ascension.gg/static/images/wow/icons/large/{icon}.jpg",
  "https://db.ascension.gg/static/images/wow/icons/medium/{icon}.jpg",
  "https://db.ascension.gg/static/images/wow/icons/small/{icon}.jpg",
];

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

export async function downloadSpellIcons({ slugs, outDir }) {
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
  const iconsFile = flag("--icons");
  const singleIcon = flag("--icon");
  const outDir = flag("--out", "dist/assets/icons");
  if (!iconsFile && !singleIcon) { console.error("usage: download-spell-icons.mjs (--icons <file> | --icon <slug>) [--out <dir>]"); process.exit(2); }
  const slugs = readSlugs({ iconsFile, singleIcon });
  downloadSpellIcons({ slugs, outDir })
    .then((s) => console.log(JSON.stringify(s, null, 2)))
    .catch((err) => { console.error(`error: ${err.message}`); process.exit(1); });
}
