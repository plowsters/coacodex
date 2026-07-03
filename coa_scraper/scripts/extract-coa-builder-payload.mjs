#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const input =
  process.argv[2] ||
  "data/snapshots/final-page-content.html";

const outDir =
  process.argv[3] ||
  "reports";

fs.mkdirSync(outDir, { recursive: true });

const html = fs.readFileSync(input, "utf8");

function extractScriptBodies(html) {
  const bodies = [];
  const rx = /<script[^>]*>([\s\S]*?)<\/script>/gi;

  for (const m of html.matchAll(rx)) {
    if (m[1].includes("self.__next_f.push")) {
      bodies.push(m[1]);
    }
  }

  return bodies;
}

function readBracketExpression(src, start) {
  const open = src[start];
  const close = open === "[" ? "]" : open === "{" ? "}" : null;
  if (!close) throw new Error(`Expected [ or { at ${start}`);

  let depth = 0;
  let inString = false;
  let quote = null;
  let escaped = false;

  for (let i = start; i < src.length; i++) {
    const ch = src[i];

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === quote) {
        inString = false;
        quote = null;
      }
      continue;
    }

    if (ch === '"' || ch === "'") {
      inString = true;
      quote = ch;
      continue;
    }

    if (ch === open) depth++;
    if (ch === close) depth--;

    if (depth === 0) {
      return {
        text: src.slice(start, i + 1),
        end: i + 1
      };
    }
  }

  throw new Error("Could not find matching bracket");
}

function extractNextFlightChunks(html) {
  const chunks = [];
  const bodies = extractScriptBodies(html);
  const prefix = "self.__next_f.push(";

  for (const body of bodies) {
    let pos = 0;

    while (true) {
      const idx = body.indexOf(prefix, pos);
      if (idx === -1) break;

      const exprStart = idx + prefix.length;
      const firstBracket = body.indexOf("[", exprStart);

      if (firstBracket === -1) {
        pos = exprStart;
        continue;
      }

      try {
        const { text, end } = readBracketExpression(body, firstBracket);
        const arr = JSON.parse(text);

        if (Array.isArray(arr) && typeof arr[1] === "string") {
          chunks.push(arr[1]);
        }

        pos = end;
      } catch (err) {
        console.warn("Failed to parse one __next_f push:", err.message);
        pos = exprStart + 1;
      }
    }
  }

  return chunks;
}

function balancedSlice(src, start) {
  const open = src[start];
  const close = open === "{" ? "}" : open === "[" ? "]" : null;
  if (!close) throw new Error(`Expected object/array at ${start}`);

  let depth = 0;
  let inString = false;
  let quote = null;
  let escaped = false;

  for (let i = start; i < src.length; i++) {
    const ch = src[i];

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === "\\") {
        escaped = true;
      } else if (ch === quote) {
        inString = false;
        quote = null;
      }
      continue;
    }

    if (ch === '"' || ch === "'") {
      inString = true;
      quote = ch;
      continue;
    }

    if (ch === open) depth++;
    if (ch === close) depth--;

    if (depth === 0) {
      return src.slice(start, i + 1);
    }
  }

  throw new Error("Unbalanced JSON-ish slice");
}

function findBuilderPayload(flight) {
  const marker = "api/v3 builder CoA parser";
  const markerIdx = flight.indexOf(marker);

  if (markerIdx === -1) {
    throw new Error(`Could not find marker: ${marker}`);
  }

  const valueIdx = flight.lastIndexOf('{"value":[', markerIdx);
  if (valueIdx === -1) {
    throw new Error('Could not find preceding {"value":[ marker');
  }

  const objText = balancedSlice(flight, valueIdx);
  const wrapper = JSON.parse(objText);

  if (!wrapper.value || !Array.isArray(wrapper.value)) {
    throw new Error("Parsed wrapper did not contain value array");
  }

  const payload = wrapper.value.find(x =>
    x &&
    typeof x === "object" &&
    x.talents &&
    x.talents.meta &&
    x.talents.meta.runtimeBuildProcess === "api/v3 builder CoA parser"
  );

  if (!payload) {
    throw new Error("Could not find builder payload inside wrapper.value");
  }

  return payload;
}

function summarizePayload(payload) {
  const talents = payload.talents || {};
  const classes = Array.isArray(talents.classes) ? talents.classes : [];

  const allKeys = {};
  for (const [k, v] of Object.entries(talents)) {
    allKeys[k] = Array.isArray(v) ? `array(${v.length})` : typeof v;
  }

  return {
    id: payload.id,
    slug: payload.slug,
    name: payload.name,
    max_level: payload.max_level,
    talentsMeta: talents.meta || null,
    talentKeys: allKeys,
    classCount: classes.length,
    classes: classes.map(c => ({
      classId: c.classId,
      className: c.className,
      tabCount: Array.isArray(c.tabs) ? c.tabs.length : 0,
      tabs: Array.isArray(c.tabs)
        ? c.tabs
            .slice()
            .sort((a, b) => (a.sortOrder ?? 0) - (b.sortOrder ?? 0))
        : []
    }))
  };
}

const chunks = extractNextFlightChunks(html);
const flight = chunks.join("");

fs.writeFileSync(
  path.join(outDir, "next_flight_stream.txt"),
  flight,
  "utf8"
);

const payload = findBuilderPayload(flight);
const summary = summarizePayload(payload);

fs.writeFileSync(
  path.join(outDir, "coa_builder_payload.json"),
  JSON.stringify(payload, null, 2),
  "utf8"
);

fs.writeFileSync(
  path.join(outDir, "coa_builder_summary.json"),
  JSON.stringify(summary, null, 2),
  "utf8"
);

fs.writeFileSync(
  path.join(outDir, "coa_classes.json"),
  JSON.stringify(summary.classes, null, 2),
  "utf8"
);

console.log(`Input: ${input}`);
console.log(`Extracted ${chunks.length} Next Flight chunks`);
console.log(`Flight stream length: ${flight.length.toLocaleString()} chars`);
console.log(`Builder: ${summary.name} (${summary.slug}), max level ${summary.max_level}`);
console.log(`Classes: ${summary.classCount}`);

for (const c of summary.classes) {
  console.log(
    `${String(c.classId).padStart(3)}  ${c.className.padEnd(18)}  ${c.tabs.map(t => t.tabName).join(", ")}`
  );
}

console.log(`Wrote ${path.join(outDir, "coa_builder_payload.json")}`);
console.log(`Wrote ${path.join(outDir, "coa_builder_summary.json")}`);
console.log(`Wrote ${path.join(outDir, "coa_classes.json")}`);
