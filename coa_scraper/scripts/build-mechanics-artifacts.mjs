#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import crypto from "node:crypto";
import { execSync } from "node:child_process";

import { readJsonl } from "./lib/ascensiondb.mjs";
import { reconcileField, dbIdentityReference, applyDbIdentityGate, REASON } from "./lib/mechanics-reconcile.mjs";
import { fieldCandidates } from "./lib/mechanics-candidates.mjs";
import { isPresent } from "./lib/mechanics-normalize.mjs";
import { loadAndValidateProjection, MechanicsBuildError } from "./lib/mechanics-projection.mjs";

const MECHANICS_SCHEMA_VERSION = "coa-mechanics-v1";

const CLIENT_FIELDS = ["cast_time_ms", "duration_ms", "range_yards", "schools", "power_type"];
const DB_ONLY_FIELDS = ["cooldown_ms", "gcd_ms", "costs"];
const KIND_BEHAVIOR_ORDER = { pet_action: 0, cooldown: 1, ability: 2, debuff: 3, passive: 4 };

export function buildMechanicsRows({ entries, spellRows, projection = [] }) {
  const clientById = new Map(projection.map((r) => [Number(r.spell_id), r]));
  const dbById = new Map(spellRows.map((r) => [Number(r.id ?? r.spell_id), r]));

  const bySpell = new Map();
  for (const entry of entries) {
    const sid = Number(entry.spell_id);
    if (!Number.isFinite(sid)) continue;
    if (!bySpell.has(sid)) bySpell.set(sid, []);
    bySpell.get(sid).push(entry);
  }

  const rows = [];
  for (const [sid, rawNodes] of [...bySpell.entries()].sort((a, b) => a[0] - b[0])) {
    // Determinism: canonicalize nodes by entry_id so reversing input order is byte-identical.
    const nodes = [...rawNodes].sort((a, b) => Number(a.entry_id) - Number(b.entry_id));
    const clientRec = clientById.get(sid) || null;
    const dbRow = dbById.get(sid) || null;

    const clientName = clientRec?.name || "";
    const builderNames = nodes.map((n) => n.name).filter(Boolean);
    const referenceName = dbIdentityReference({ clientName, builderNames, dbName: dbRow?.name || "" });
    const gate = dbRow ? applyDbIdentityGate({ dbRow, referenceName }) : { excluded: false, reason: null };
    const dbUsable = Boolean(dbRow && !gate.excluded);

    const fieldProvenance = {};
    const selected = {};

    // name: client_dbc → verified_builder (consensus) → ascension_db (only if identity-usable)
    const nameOut = reconcileField({ field: "name", candidates: nameCandidates({ clientRec, nodes, dbRow, dbUsable }) });
    fieldProvenance.name = nameOut.provenance;
    const name = nameOut.selected ?? (clientName || builderNames[0] || dbRow?.name || "");

    // reconciled mechanical fields (client/builder/db)
    for (const field of CLIENT_FIELDS) {
      const candidates = fieldCandidates({ field, clientRec, builderNodes: nodes, dbRow, dbExcluded: gate.excluded, dbExclusionReason: gate.reason });
      if (candidates.length === 0) continue;
      const { selected: value, provenance } = reconcileField({ field, candidates });
      fieldProvenance[field] = provenance;
      if (value !== undefined) selected[field] = value;
    }

    // db-only fields: single-source field_provenance (barred when the db row failed identity)
    for (const field of DB_ONLY_FIELDS) {
      const fp = dbOnlyProvenance({ field, dbRow, dbUsable, gate });
      if (fp) fieldProvenance[field] = fp;
    }

    // Tooltip used to classify kind and infer effects. When the identity-matched db row supplies
    // the tooltip, that participation is recorded in provenance (not silently attributed to the
    // builder); otherwise fall back to the first builder description in entry_id order.
    const dbTooltip = dbUsable && dbRow.tooltip_text ? String(dbRow.tooltip_text) : "";
    const builderTooltip = nodes.map((n) => n.description_text).filter(Boolean)[0] || "";
    const tooltipText = dbTooltip || builderTooltip;
    const tooltipMeta = dbTooltip
      ? { text: dbTooltip, source: "ascension_db", tier: "ascension_db", source_id: `ascension_db:${dbRow.id}` }
      : { text: builderTooltip, source: "builder", tier: "verified_builder", source_id: `builder_node:${nodes[0]?.entry_id}` };

    // kind: derived from ALL nodes (order-independent) + the tooltip's real source
    const { kind, provenance: kindProv } = resolveKind(nodes, tooltipText, tooltipMeta);
    fieldProvenance.kind = kindProv;

    const schools = selected.schools || [];
    // Effects derive from a deterministic MERGED node view (tags unioned across all nodes, sorted)
    // plus the tooltip — never one arbitrary node — so output is input-order-independent.
    const mergedTags = [...new Set(nodes.flatMap((n) => n.tags || []))].sort();
    const mergedEntry = { tags: mergedTags, description_text: builderTooltip };
    const effects = inferEffects({ entry: mergedEntry, tooltipText, spellRow: dbUsable ? dbRow : null, schools, durationMs: selected.duration_ms ?? null });
    fieldProvenance.effects = effectsProvenance({ effects, tooltip: tooltipMeta });

    rows.push({
      schema_version: MECHANICS_SCHEMA_VERSION,
      spell_id: sid,
      name,
      kind,
      source_node_ids: [...new Set(nodes.map((n) => Number(n.entry_id)).filter(Number.isFinite))].sort((a, b) => a - b),
      source_urls: dbUsable ? sourceUrls(dbRow) : [],
      school: schools.length === 1 ? schools[0] : "",
      schools,
      power_type: selected.power_type || "",
      cast_time_ms: selected.cast_time_ms ?? null,
      duration_ms: selected.duration_ms ?? null,
      range_yards: selected.range_yards ?? null,
      cooldown_ms: dbUsable ? numberOrNull(dbRow.cooldown_ms) : null,
      gcd_ms: dbUsable ? numberOrNull(dbRow.gcd_ms) : null,
      costs: dbUsable ? costsObject(dbRow.power_costs) : {},
      generates: {},
      spends: {},
      effects,
      field_provenance: fieldProvenance,
      provenance: buildProvenance(fieldProvenance),
      confidence: recordConfidence(fieldProvenance),
      raw: {
        tags: mergedTags, // set-like builder tags; not a top-level coa-mechanics-v1 field, so carried in raw
        category: clientRec?.mechanics?.category ?? null,
        spell_icon_id: clientRec?.mechanics?.spell_icon_id ?? null,
        school_mask: clientRec?.mechanics?.school_mask ?? null,
        db_status: dbRow?.status || null,
        db_excluded: gate.excluded,
        db_exclusion_reason: gate.reason,
        linked_item_ids: dbUsable ? (dbRow.linked_item_ids || []) : [],
      },
    });
  }
  return rows;
}

function nameCandidates({ clientRec, nodes, dbRow, dbUsable }) {
  const out = [];
  if (clientRec?.name) out.push({ source: "client_dbc", precedence_tier: "client_dbc", source_id: `client_spell:${clientRec.spell_id}`, source_field: "name", raw_value: clientRec.name, normalized_value: clientRec.name, confidence: clientRec?.coa_attribution?.confidence || "low", eligible: true, eligibility_reasons: [] });
  for (const n of nodes) if (n.name) out.push({ source: "builder", precedence_tier: "verified_builder", source_id: `builder_node:${n.entry_id}`, source_field: "name", raw_value: n.name, normalized_value: n.name, confidence: "high", eligible: true, eligibility_reasons: [] });
  if (dbUsable && dbRow?.name) out.push({ source: "ascension_db", precedence_tier: "ascension_db", source_id: `ascension_db:${dbRow.id}`, source_field: "name", raw_value: dbRow.name, normalized_value: dbRow.name, confidence: "medium", eligible: true, eligibility_reasons: [] });
  return out;
}

function dbOnlyProvenance({ field, dbRow, dbUsable, gate }) {
  if (!dbRow) return null;
  const rawByField = { cooldown_ms: dbRow.cooldown_ms, gcd_ms: dbRow.gcd_ms, costs: dbRow.power_costs };
  const raw = rawByField[field];
  if (!isPresent(raw)) return null;
  const value = field === "costs" ? costsObject(raw) : numberOrNull(raw);
  const eligible = dbUsable;
  return {
    selected_source: eligible ? "ascension_db" : null,
    selected_tier: eligible ? "ascension_db" : null,
    selected_value: eligible ? value : null,
    selection_reason: eligible ? REASON.DB_FALLBACK : REASON.OMITTED_NO_ELIGIBLE_CANDIDATE,
    warnings: [],
    candidates: [{
      source: "ascension_db", precedence_tier: "ascension_db", source_id: `ascension_db:${dbRow.id}`,
      source_field: field, raw_value: raw, normalized_value: value, confidence: "medium",
      eligible, eligibility_reasons: eligible ? [] : [gate.reason || REASON.DB_IDENTITY_MISMATCH],
    }],
  };
}

// kind is classified from every node's entry_type AND the tooltip text (the tooltip can flip the
// classification). The tooltip candidate carries its REAL source, and is marked `contributed` when
// it is db-derived so the db's participation surfaces in record-level provenance.
function resolveKind(nodes, tooltipText, tooltip) {
  const perNode = nodes.map((n) => ({ node: n, kind: classifyMechanicKind(n, tooltipText) }));
  const distinct = [...new Set(perNode.map((x) => x.kind))];
  const chosen = distinct.slice().sort((a, b) => (KIND_BEHAVIOR_ORDER[a] ?? 9) - (KIND_BEHAVIOR_ORDER[b] ?? 9))[0];
  const candidates = perNode.map((x) => ({
    source: "builder", precedence_tier: "verified_builder", source_id: `builder_node:${x.node.entry_id}`,
    source_field: "entry_type", raw_value: x.node.entry_type, normalized_value: x.kind,
    confidence: "medium", eligible: true, eligibility_reasons: [], contributed: true,
  }));
  if (tooltip && tooltip.text) {
    candidates.push({
      source: tooltip.source, precedence_tier: tooltip.tier, source_id: tooltip.source_id,
      source_field: "tooltip_text", raw_value: null, normalized_value: chosen,
      confidence: "low", eligible: true, eligibility_reasons: [], contributed: tooltip.source === "ascension_db",
    });
  }
  return {
    kind: chosen,
    provenance: {
      selected_source: "builder", selected_tier: "verified_builder", selected_value: chosen,
      selection_reason: distinct.length > 1 ? REASON.KIND_NODE_DISAGREEMENT_RESOLVED : REASON.ONLY_CANDIDATE,
      warnings: distinct.length > 1 ? ["kind_node_disagreement"] : [],
      candidates,
    },
  };
}

// effects are heuristically inferred from the tooltip + merged builder tags. Provenance records the
// tooltip's real source (db participation marked `contributed`); when no effects were inferred the
// field contributes nothing.
function effectsProvenance({ effects, tooltip }) {
  const has = effects.length > 0;
  const candidates = [];
  if (has && tooltip && tooltip.text) {
    candidates.push({
      source: tooltip.source, precedence_tier: tooltip.tier, source_id: tooltip.source_id,
      source_field: "tooltip_text", raw_value: null, normalized_value: effects.length,
      confidence: "low", eligible: true, eligibility_reasons: [], contributed: tooltip.source === "ascension_db",
    });
  }
  return {
    selected_source: has ? "inferred" : null,
    selected_tier: has ? "inferred" : null,
    selected_value: effects.length,
    selection_reason: has ? REASON.INFERRED_FROM_TEXT : REASON.OMITTED_NO_ELIGIBLE_CANDIDATE,
    warnings: [], candidates,
  };
}

// Record-level provenance is the union of every field's selected source PLUS every candidate that
// actually shaped an emitted value (`contributed`) — so a db tooltip that informed kind/effects, or
// a db-fallback cooldown, always leaves a db provenance entry even when no db value was "selected".
function buildProvenance(fieldProvenance) {
  const used = new Set();
  for (const fp of Object.values(fieldProvenance)) {
    if (!fp) continue;
    if (fp.selected_source) used.add(fp.selected_source);
    for (const c of fp.candidates || []) if (c.contributed) used.add(c.source);
  }
  const conf = { client_dbc: "high", builder: "medium", ascension_db: "medium", inferred: "low" };
  const notes = { client_dbc: "client_dbc_mechanical", builder: "verified_builder_or_inferred", ascension_db: "db_fallback", inferred: "inferred" };
  const out = [];
  for (const src of ["client_dbc", "builder", "ascension_db", "inferred"]) {
    if (used.has(src)) out.push({ source: src, parser: "build-mechanics-artifacts", confidence: conf[src], notes: [notes[src]] });
  }
  if (out.length === 0) out.push({ source: "inferred", parser: "build-mechanics-artifacts", confidence: "low", notes: ["no_source"] });
  return out;
}

function recordConfidence(fp) {
  const src = (f) => fp[f]?.selected_source;
  const core = ["schools", "power_type"].every((f) => src(f) === "client_dbc");
  const timing = src("cast_time_ms") === "client_dbc" || src("duration_ms") === "client_dbc";
  if (core && timing) return "high";
  const anyClient = Object.values(fp).some((p) => p && p.selected_source === "client_dbc");
  return anyClient ? "medium" : "low";
}

export function summarizeMechanicsArtifacts({ mechanicsRows, itemRows }) {
  const kinds = countBy(mechanicsRows, row => row.kind);
  const confidence = countBy(mechanicsRows, row => row.confidence);
  return {
    schema_version: "coa-mechanics-artifact-summary-v1",
    generated_at: new Date().toISOString(),
    mechanics_count: mechanicsRows.length,
    item_count: itemRows.length,
    mechanic_kind_counts: kinds,
    mechanic_confidence_counts: confidence
  };
}

function inferEffects({ entry, tooltipText, spellRow, schools = [], durationMs = null }) {
  const tags = entry?.tags || [];
  const school = schools.length === 1 ? schools[0] : (schools.length ? "" : inferSchool(tooltipText));
  const resolvedDuration = durationMs ?? numberOrNull(spellRow?.duration_ms) ?? inferDurationMs(tooltipText);
  const periodMs = numberOrNull(spellRow?.period_ms);
  const amount = inferAmount(tooltipText);
  if (tags.includes("heal") || /\bheal/i.test(tooltipText)) {
    return [
      {
        effect_type: "heal",
        school,
        target: "ally",
        amount,
        duration_ms: resolvedDuration,
        tick_interval_ms: periodMs,
        tags: tags.filter(Boolean)
      }
    ];
  }
  if (tags.includes("summon") || /\bsummon|companion|pet\b/i.test(tooltipText)) {
    return [
      {
        effect_type: "summon",
        target: "self",
        duration_ms: resolvedDuration,
        tick_interval_ms: periodMs,
        tags: tags.filter(Boolean)
      }
    ];
  }
  if (tags.includes("aura") || tags.includes("cooldown") || /\bbuff|aura|increases?\b/i.test(tooltipText)) {
    return [
      {
        effect_type: "aura_apply",
        target: "self",
        duration_ms: resolvedDuration,
        tick_interval_ms: periodMs,
        tags: tags.filter(Boolean)
      }
    ];
  }
  if (tags.includes("dot") || schools.length || /\bdamage\b/i.test(tooltipText)) {
    return [
      {
        effect_type: "damage",
        school,
        target: "enemy",
        amount,
        duration_ms: resolvedDuration,
        tick_interval_ms: periodMs,
        tags: tags.filter(Boolean)
      }
    ];
  }
  return [];
}

function classifyMechanicKind(entry, tooltipText) {
  const tags = entry.tags || [];
  if (entry.is_passive || entry.entry_type === "Talent" && !/\bcast|deals?|heals?\b/i.test(tooltipText)) {
    return "passive";
  }
  if (tags.includes("summon")) {
    return "pet_action";
  }
  if (tags.includes("dot")) {
    return "debuff";
  }
  if (tags.includes("cooldown")) {
    return "cooldown";
  }
  return "ability";
}

function inferDurationMs(text) {
  const match = String(text || "").match(/\b(?:over|for|lasts?)\s+(\d+(?:\.\d+)?)\s*(sec|second|seconds|s)\b/i);
  return match ? Math.round(Number(match[1]) * 1000) : null;
}

function inferAmount(text) {
  const match = String(text || "").match(/\b(\d+(?:\.\d+)?)\s+(?:[A-Za-z]+\s+)?(?:damage|healing|health|heal)\b/i);
  return match ? Number(match[1]) : null;
}

function inferSchool(text) {
  const match = String(text || "").match(/\b(arcane|fire|frost|holy|nature|physical|shadow|fel)\b/i);
  return match ? match[1].toLowerCase() : "";
}

function costsObject(costs) {
  const output = {};
  for (const item of costs || []) {
    const resource = item?.resource ? String(item.resource) : "";
    const amount = Number(item?.amount);
    if (resource && Number.isFinite(amount)) {
      output[resource] = amount;
    }
  }
  return output;
}

export function sourceUrls(row) {
  const urls = [
    row?.source_url,
    row?.provenance?.url,
    ...(Array.isArray(row?.source_urls) ? row.source_urls : [])
  ].filter(Boolean);
  return [...new Set(urls)];
}

export function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function countBy(rows, keyFn) {
  return rows.reduce((acc, row) => {
    const key = keyFn(row) || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function sha256File(p) { return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex"); }

function atomicWrite(targetPath, data) {
  const tmp = `${targetPath}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, targetPath);
}

function jsonlBytes(rows) {
  return rows.map((r) => JSON.stringify(r)).join("\n") + (rows.length ? "\n" : "");
}

function winnerCounts(rows) {
  const bySource = {}; const byTier = {};
  for (const r of rows) {
    for (const [f, fp] of Object.entries(r.field_provenance || {})) {
      if (!fp.selected_source) continue;
      bySource[f] = bySource[f] || {}; byTier[f] = byTier[f] || {};
      bySource[f][fp.selected_source] = (bySource[f][fp.selected_source] || 0) + 1;
      byTier[f][fp.selected_tier] = (byTier[f][fp.selected_tier] || 0) + 1;
    }
  }
  return { bySource, byTier };
}

function aggregateCounts(rows) {
  let unresolved_conflicts = 0, ineligible_candidates = 0, omitted_fields = 0, kind_disagreements = 0;
  for (const r of rows) {
    const fp = r.field_provenance || {};
    for (const p of Object.values(fp)) {
      if (Array.isArray(p.candidates)) {
        for (const c of p.candidates) if (c.eligible === false) ineligible_candidates++;
        if (!p.selected_source && p.candidates.length > 0) omitted_fields++;
      }
      if (p.selection_reason === REASON.OMITTED_UNRESOLVED_CONFLICT) unresolved_conflicts++;
    }
    if (fp.kind && fp.kind.selection_reason === REASON.KIND_NODE_DISAGREEMENT_RESOLVED) kind_disagreements++;
  }
  return { unresolved_conflicts, ineligible_candidates, omitted_fields, kind_disagreements };
}

function gitHeadCommit() {
  try {
    return execSync("git rev-parse HEAD", { stdio: ["ignore", "pipe", "ignore"] }).toString().trim() || null;
  } catch {
    return null;
  }
}

export function buildMechanicsArtifact({ entries, spellRows, projectionPath, manifestPath, outDir, allowFallback = false, inputs = {} }) {
  const builderSpellIds = new Set(entries.map((e) => Number(e.spell_id)).filter(Number.isFinite));
  const loaded = loadAndValidateProjection({ projectionPath, manifestPath, builderSpellIds });

  if (loaded.absent) {
    if (!allowFallback) throw new MechanicsBuildError("projection absent; refusing canonical build (pass --allow-fallback-mechanics for a degraded build)");
    const rows = buildMechanicsRows({ entries, spellRows, projection: [] });
    // A degraded build writes ONLY the coa_mechanics.fallback.* files. It NEVER writes the canonical
    // filename — MechanicsRepository reads the JSONL directly and would ingest degraded bytes as
    // canonical regardless of a canonical:false marker. There is no override.
    return writeArtifact({ rows, outDir, canonical: false, clientSource: "absent", fallbackAuthorized: true, loaded, inputs, base: "coa_mechanics.fallback" });
  }

  const rows = buildMechanicsRows({ entries, spellRows, projection: loaded.projection });
  return writeArtifact({ rows, outDir, canonical: true, clientSource: "present", fallbackAuthorized: false, loaded, inputs, base: "coa_mechanics" });
}

function writeArtifact({ rows, outDir, canonical, clientSource, fallbackAuthorized, loaded, inputs, base }) {
  fs.mkdirSync(outDir, { recursive: true }); // outDir may not exist yet (e.g. a fresh temp dir)
  const jsonlName = `${base}.jsonl`;
  const manifestName = `${base}.manifest.json`;
  const jsonlPath = path.join(outDir, jsonlName);
  const manifestPath = path.join(outDir, manifestName);

  const body = jsonlBytes(rows);
  const sha = crypto.createHash("sha256").update(body).digest("hex");
  const { bySource, byTier } = winnerCounts(rows);
  const manifest = {
    schema_version: "coa-mechanics-manifest-v1",
    generated_at: new Date().toISOString(),
    canonical, client_source: clientSource, fallback_authorized: fallbackAuthorized,
    reconciliation_policy_version: "m1.14c-1",
    reconciler_commit: canonical ? (inputs.reconciler_commit ?? null) : null,
    client_build: loaded.absent ? null : (loaded.client_build ?? null),
    inputs: {
      builder_entries: inputs.builder_entries || null,
      db_spell_tooltips: inputs.db_spell_tooltips || null,
      projection: loaded.absent ? { path: null, sha256: null } : { path: inputs.projection_path || null, sha256: loaded.projection_sha256 },
      projection_manifest: loaded.absent ? { path: null, sha256: null } : { path: inputs.projection_manifest_path || null, sha256: loaded.manifest_sha256 },
    },
    outputs: { mechanics_jsonl: jsonlName, sha256: sha, record_count: rows.length },
    coverage: loaded.absent ? null : loaded.coverage,
    per_field_winner_counts_by_source: bySource,
    per_field_winner_counts_by_tier: byTier,
    counts: aggregateCounts(rows),
  };

  // manifest-as-validity-marker: remove previous manifest first, then JSONL, then manifest — each atomic.
  if (fs.existsSync(manifestPath)) fs.rmSync(manifestPath);
  atomicWrite(jsonlPath, body);
  atomicWrite(manifestPath, JSON.stringify(manifest, null, 2) + "\n");
  return { canonical, manifest };
}

function isCliEntryPoint() {
  return process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
}

if (isCliEntryPoint()) {
  const args = process.argv.slice(2);
  const flag = (name, def) => {
    const i = args.indexOf(name);
    return i >= 0 && args[i + 1] ? args[i + 1] : def;
  };
  const has = (name) => args.includes(name);
  const entriesPath = flag("--builder-entries", "dist/coa_entries.jsonl");
  const dbPath = flag("--db-spells", "dist/coa_db_spell_tooltips.jsonl");
  // npm runs scripts from coa_scraper/, but the extractor writes the projection to the REPO-ROOT
  // reports/client_extract/ — so the default (and the npm scripts) reach it via ../reports/...
  const projectionPath = flag("--projection", "../reports/client_extract/coa_client_spell_coa.jsonl");
  const projManifestPath = flag("--projection-manifest", "../reports/client_extract/coa_client_spell_projection.manifest.json");
  const outDir = flag("--out", "dist");
  if (!fs.existsSync(entriesPath)) { console.error(`required builder entries missing: ${entriesPath}`); process.exit(2); }
  const entries = readJsonl(entriesPath);
  const spellRows = fs.existsSync(dbPath) ? readJsonl(dbPath) : [];
  try {
    const { canonical, manifest } = buildMechanicsArtifact({
      entries, spellRows, projectionPath, manifestPath: projManifestPath, outDir,
      allowFallback: has("--allow-fallback-mechanics"),
      inputs: {
        builder_entries: { path: entriesPath, sha256: sha256File(entriesPath) },
        db_spell_tooltips: fs.existsSync(dbPath) ? { path: dbPath, sha256: sha256File(dbPath) } : null,
        projection_path: projectionPath, projection_manifest_path: projManifestPath,
        reconciler_commit: gitHeadCommit(),
      },
    });
    console.log(JSON.stringify({ canonical, record_count: manifest.outputs.record_count, coverage: manifest.coverage }, null, 2));
  } catch (err) {
    console.error(`error: ${err.message}`);
    process.exit(2);
  }
}
