import fs from "node:fs";
import path from "node:path";

// Generic JSONL/name helpers, deliberately independent of the (retired) AscensionDB integration so a
// canonical mechanics build has no import path back to db.ascension.gg. Formerly lived in ascensiondb.mjs.

export function readJsonl(filePath) {
  if (!fs.existsSync(filePath)) return [];
  const text = fs.readFileSync(filePath, "utf8").trim();
  if (!text) return [];
  return text.split("\n").filter(Boolean).map((line) => JSON.parse(line));
}

export function writeJsonl(filePath, rows) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

export function normalizeName(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}
