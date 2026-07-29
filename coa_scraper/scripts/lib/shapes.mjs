// coa_scraper/scripts/lib/shapes.mjs
// E0R.2 T2.2 — the Node trust boundary's own shape validators.
//
// Written INDEPENDENTLY against the contract, not transcribed from coa_client_extract/shapes.py. Two
// boundaries that agree only because they share code are one boundary; what holds these two together is
// the shared golden corpus, which both run every validator against.
//
// A shape is a TYPE CONTRACT: exact key set (an unknown key is rejected, never ignored), the type of
// every key, explicit nullability, and the nested observation envelope. `{}` used to pass as a
// one-record JSON artifact because nothing asked anything of it.

export class ShapeError extends Error {}

const PROOF_FACETS = ["integrity", "interpretation", "layout"];
const PROMOTIONS = new Set(["normalized", "raw_only"]);
const JOIN_PARTS = new Set(["index", "side_id", "side_value"]);

// The closed observation vocabularies, read from the SAME immutable wire schema Python reads rather
// than restated here (T0.1).
import fs from "node:fs";
const WIRE = JSON.parse(fs.readFileSync(
  new URL("../../../coa_client_extract/data/observation_wire_schema.json", import.meta.url), "utf8"));
const STATES = new Set(Object.keys(WIRE.states));
const REASONS = new Set(Object.keys(WIRE.decoded_reasons));

const fail = (where, msg) => { throw new ShapeError(`${where}: ${msg}`); };

function obj(value, where) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail(where, `must be an object, got ${Array.isArray(value) ? "array" : typeof value}`);
  }
  return value;
}

function keys(value, { required, optional = [], where }) {
  const present = new Set(Object.keys(value));
  const missing = required.filter((k) => !present.has(k)).sort();
  if (missing.length) fail(where, `missing ${JSON.stringify(missing)}`);
  const allowed = new Set([...required, ...optional]);
  const unknown = [...present].filter((k) => !allowed.has(k)).sort();
  if (unknown.length) fail(where, `unknown key(s) ${JSON.stringify(unknown)}`);
}

function str(value, where, { nullable = false } = {}) {
  if (value === null && nullable) return;
  if (typeof value !== "string") fail(where, `must be a string${nullable ? " or null" : ""}`);
}

function int(value, where, { nullable = false } = {}) {
  if (value === null && nullable) return;
  // JSON has one number type; an integer check is what distinguishes an id from a float, and a boolean
  // is never a valid id (Python's isinstance(True, int) makes this a real hazard on the other side).
  if (typeof value !== "number" || !Number.isInteger(value)) {
    fail(where, `must be an integer${nullable ? " or null" : ""}`);
  }
}

function num(value, where, { nullable = false } = {}) {
  if (value === null && nullable) return;
  if (typeof value !== "number") fail(where, `must be a number${nullable ? " or null" : ""}`);
}

function proof(value, where) {
  obj(value, where);
  keys(value, { required: PROOF_FACETS, where });
  for (const facet of PROOF_FACETS) str(value[facet], `${where}.${facet}`);
}

// A component/scalar `decoded` is {kind, value}; a JOIN's is the bare resolved scalar. `null` is
// legitimate — the per-value domain gate emits it with `value_out_of_domain`.
function decoded(value, where) {
  if (value === null) return;
  obj(value, where);
  keys(value, { required: ["kind", "value"], where });
  str(value.kind, `${where}.kind`);
}

function vocabulary(cell, where) {
  if (!STATES.has(cell.state)) fail(where, `state ${cell.state} not in the closed vocabulary`);
  if (!REASONS.has(cell.decoded_reason)) fail(where, `decoded_reason ${cell.decoded_reason} not in the closed vocabulary`);
}

function component(value, where) {
  obj(value, where);
  vocabulary(value, where);
  keys(value, { required: ["state", "decoded_reason", "policy_ref"],
                optional: ["raw_u32", "raw_offset", "resolved", "proof", "promotion", "decoded"], where });
  str(value.policy_ref, `${where}.policy_ref`);
  if ("raw_u32" in value) int(value.raw_u32, `${where}.raw_u32`);
  if ("proof" in value) proof(value.proof, `${where}.proof`);
  if ("promotion" in value && !PROMOTIONS.has(value.promotion)) fail(`${where}.promotion`, `${value.promotion} is not a promotion`);
  if ("decoded" in value) decoded(value.decoded, `${where}.decoded`);
}

// One observation cell in either dialect: the full child is COMPACT (substrate only), the projection is
// RICH (substrate plus the proof and promotion a consumer re-derives against).
function observation(cell, where, rich) {
  obj(cell, where);
  vocabulary(cell, where);
  const richKeys = rich ? ["promotion", "decoded"] : [];
  if ("join_name" in cell || "components" in cell) {
    // An UNRESOLVED join carries no components: it records the index cell it could not follow and
    // nothing else. Complete, not partial — omitting the cell would be the loss.
    keys(cell, { required: ["state", "decoded_reason", "join_name"],
                 optional: ["components", "policy_ref",
                            ...(rich ? ["composed_proof", "proof", ...richKeys] : [])], where });
    str(cell.join_name, `${where}.join_name`);
    if ("policy_ref" in cell) str(cell.policy_ref, `${where}.policy_ref`);
    if ("components" in cell) {
      const parts = obj(cell.components, `${where}.components`);
      for (const part of Object.keys(parts)) {
        if (!JOIN_PARTS.has(part)) fail(`${where}.components`, `unknown join part ${part}`);
        component(parts[part], `${where}.components.${part}`);
      }
    }
    if (rich) {
      for (const facet of ["composed_proof", "proof"]) {
        if (facet in cell) proof(cell[facet], `${where}.${facet}`);
      }
    }
  } else if ("raw_offset" in cell || "resolved" in cell) {
    keys(cell, { required: ["state", "decoded_reason", "policy_ref", "raw_offset", "resolved"],
                 optional: rich ? ["proof", ...richKeys] : [], where });
    str(cell.policy_ref, `${where}.policy_ref`);
    int(cell.raw_offset, `${where}.raw_offset`, { nullable: true });
    str(cell.resolved, `${where}.resolved`, { nullable: true });
  } else {
    keys(cell, { required: ["state", "decoded_reason", "policy_ref", "raw_u32"],
                 optional: rich ? ["proof", ...richKeys] : [], where });
    str(cell.policy_ref, `${where}.policy_ref`);
    int(cell.raw_u32, `${where}.raw_u32`, { nullable: true });
  }
  if (rich) {
    const isJoin = "join_name" in cell || "components" in cell;
    if ("proof" in cell && !isJoin) proof(cell.proof, `${where}.proof`);
    if ("promotion" in cell && !PROMOTIONS.has(cell.promotion)) fail(`${where}.promotion`, `${cell.promotion} is not a promotion`);
    // A JOIN's `decoded` is the BARE resolved scalar — the join has no kind of its own beyond its
    // side-value component's, so {kind, value} applies to scalars and components only.
    if ("decoded" in cell && !isJoin) decoded(cell.decoded, `${where}.decoded`);
    if ("decoded" in cell && isJoin && cell.decoded !== null && typeof cell.decoded === "object") {
      fail(`${where}.decoded`, "a join's decoded value is a bare scalar, not an envelope");
    }
  }
}

function attribution(value, where) {
  obj(value, where);
  keys(value, { required: ["is_coa"],
                optional: ["status", "archive_family", "id_range", "policy_sha256", "confidence",
                           "exclusive_mode", "modes"], where });
  if (typeof value.is_coa !== "boolean") {
    fail(`${where}.is_coa`, "must be a boolean — an unknown attribution is false, never absent");
  }
}

function spellRow(row, { rich, schemaVersion, where }) {
  obj(row, where);
  const substrate = rich ? "field_observations" : "raw";
  keys(row, { required: ["schema_version", "spell_id", "name", "mechanics", "coa_attribution", substrate],
              optional: ["description"], where });
  if (row.schema_version !== schemaVersion) fail(`${where}.schema_version`, `${row.schema_version} != ${schemaVersion}`);
  int(row.spell_id, `${where}.spell_id`);
  str(row.name, `${where}.name`, { nullable: true });
  // Every mechanics value is structurally NULLABLE, school_mask included: a proven policy still yields
  // a null when an unseen school bit trips the per-value domain gate. The KEYS may not be absent.
  const mechanics = obj(row.mechanics, `${where}.mechanics`);
  for (const [key, value] of Object.entries(mechanics)) num(value, `${where}.mechanics.${key}`, { nullable: true });
  attribution(row.coa_attribution, `${where}.coa_attribution`);
  const cells = obj(row[substrate], `${where}.${substrate}`);
  if (!Object.keys(cells).length) fail(`${where}.${substrate}`, "carries no observations: a row with no substrate is not lossless");
  for (const [field, cell] of Object.entries(cells)) observation(cell, `${where}.${substrate}.${field}`, rich);
  return row;
}

function cols(value, where) {
  const map = obj(value, where);
  for (const [index, cell] of Object.entries(map)) {
    if (!/^\d+$/.test(index)) fail(where, `column key ${index} is not a decimal cell index`);
    int(cell, `${where}.${index}`);
  }
}

export const SHAPES = {
  full_spell_row_v3: (row) => spellRow(row, { rich: false, schemaVersion: "coa-client-spell-v3", where: "full_spell_row_v3" }),

  projection_row_v3: (row) => spellRow(row, { rich: true, schemaVersion: "coa-client-spell-projection-v3", where: "projection_row_v3" }),

  icon_row_v1(row) {
    const where = "icon_row_v1";
    obj(row, where);
    keys(row, { required: ["schema_version", "spell_id", "spell_icon_id", "asset_status", "client_path", "readiness"],
                optional: ["source_archive", "source_asset_sha256", "converted_ref"], where });
    if (row.schema_version !== "coa-client-spell-icons-v1") fail(`${where}.schema_version`, row.schema_version);
    int(row.spell_id, `${where}.spell_id`);
    int(row.spell_icon_id, `${where}.spell_icon_id`, { nullable: true });
    str(row.asset_status, `${where}.asset_status`);
    str(row.client_path, `${where}.client_path`, { nullable: true });
    str(row.readiness, `${where}.readiness`);
    for (const key of ["source_archive", "source_asset_sha256", "converted_ref"]) {
      if (key in row) str(row[key], `${where}.${key}`, { nullable: true });
    }
    return row;
  },

  content_row_v1(row) {
    const where = "content_row_v1";
    obj(row, where);
    keys(row, { required: ["schema_version", "content_kind", "values", "provenance", "coa_attribution"],
                optional: ["spell_id", "item_id"], where });
    if (row.schema_version !== "coa-client-content-v1") fail(`${where}.schema_version`, row.schema_version);
    str(row.content_kind, `${where}.content_kind`);
    obj(row.values, `${where}.values`);
    const prov = obj(row.provenance, `${where}.provenance`);
    keys(prov, { required: ["source_file", "file_sha256", "extraction_date"], where: `${where}.provenance` });
    for (const key of ["source_file", "file_sha256", "extraction_date"]) str(prov[key], `${where}.provenance.${key}`);
    const attr = obj(row.coa_attribution, `${where}.coa_attribution`);
    keys(attr, { required: ["status"], optional: ["note"], where: `${where}.coa_attribution` });
    for (const key of ["spell_id", "item_id"]) if (key in row) int(row[key], `${where}.${key}`);
    return row;
  },

  advancement_row_v1(row) {
    const where = "advancement_row_v1";
    obj(row, where);
    keys(row, { required: ["schema_version", "node_id", "spell_id", "name", "class", "tab", "entry_type",
                           "essence_kind", "legality", "field_confidence", "raw", "provenance",
                           "coa_attribution"], where });
    if (row.schema_version !== "coa-client-advancement-v1") fail(`${where}.schema_version`, row.schema_version);
    int(row.node_id, `${where}.node_id`);
    int(row.spell_id, `${where}.spell_id`, { nullable: true });
    str(row.name, `${where}.name`, { nullable: true });
    const klass = obj(row.class, `${where}.class`);
    keys(klass, { required: ["class_type_id", "internal", "display", "kind"], where: `${where}.class` });
    int(klass.class_type_id, `${where}.class.class_type_id`);
    for (const key of ["internal", "display", "kind"]) str(klass[key], `${where}.class.${key}`, { nullable: true });
    const tab = obj(row.tab, `${where}.tab`);
    keys(tab, { required: ["tab_type_id", "name"], where: `${where}.tab` });
    int(tab.tab_type_id, `${where}.tab.tab_type_id`, { nullable: true });
    str(tab.name, `${where}.tab.name`, { nullable: true });
    str(row.entry_type, `${where}.entry_type`, { nullable: true });
    str(row.essence_kind, `${where}.essence_kind`, { nullable: true });
    obj(row.legality, `${where}.legality`);
    obj(row.field_confidence, `${where}.field_confidence`);
    const raw = obj(row.raw, `${where}.raw`);
    keys(raw, { required: ["cols"], where: `${where}.raw` });
    cols(raw.cols, `${where}.raw.cols`);
    obj(row.provenance, `${where}.provenance`);
    attribution(row.coa_attribution, `${where}.coa_attribution`);
    return row;
  },

  class_type_row_v1(row) {
    const where = "class_type_row_v1";
    obj(row, where);
    keys(row, { required: ["schema_version", "class_type_id", "internal", "display", "kind",
                           "display_source", "display_evidence"], where });
    if (row.schema_version !== "coa-client-class-types-v1") fail(`${where}.schema_version`, row.schema_version);
    int(row.class_type_id, `${where}.class_type_id`);
    for (const key of ["internal", "display", "kind", "display_source"]) str(row[key], `${where}.${key}`, { nullable: true });
    if (!Array.isArray(row.display_evidence)) fail(`${where}.display_evidence`, "must be a list");
    return row;
  },

  tab_type_row_v1(row) {
    const where = "tab_type_row_v1";
    obj(row, where);
    keys(row, { required: ["schema_version", "tab_type_id", "name"], where });
    if (row.schema_version !== "coa-client-tab-types-v1") fail(`${where}.schema_version`, row.schema_version);
    int(row.tab_type_id, `${where}.tab_type_id`);
    str(row.name, `${where}.name`, { nullable: true });
    return row;
  },

  essence_row_v1(row) {
    const where = "essence_row_v1";
    obj(row, where);
    keys(row, { required: ["schema_version", "cols", "provenance"], where });
    if (row.schema_version !== "coa-client-essence-v1") fail(`${where}.schema_version`, row.schema_version);
    cols(row.cols, `${where}.cols`);
    obj(row.provenance, `${where}.provenance`);
    return row;
  },

  archive_plan_v1(doc) {
    const where = "archive_plan_v1";
    obj(doc, where);
    keys(doc, { required: ["schema_version", "client_root", "ordering_rule", "base_archives",
                           "patch_archives", "excluded"], where });
    if (doc.schema_version !== "coa-client-archive-plan-v1") fail(`${where}.schema_version`, doc.schema_version);
    str(doc.client_root, `${where}.client_root`);
    // The load order is what the whole extraction is bound to; a plan that omits it describes nothing.
    str(doc.ordering_rule, `${where}.ordering_rule`);
    for (const key of ["base_archives", "patch_archives"]) {
      if (!Array.isArray(doc[key])) fail(`${where}.${key}`, "must be a list");
    }
    const excluded = obj(doc.excluded, `${where}.excluded`);
    for (const [family, members] of Object.entries(excluded)) {
      if (!Array.isArray(members)) fail(`${where}.excluded.${family}`, "must be a list");
    }
    return doc;
  },

  projection_manifest_v3(doc) {
    const where = "projection_manifest_v3";
    obj(doc, where);
    keys(doc, { required: ["schema_version", "inclusion_rule", "client_build", "extractor_commit",
                           "extraction_date", "policy_sha256", "counts"], where });
    if (doc.schema_version !== "coa-client-spell-projection-manifest-v3") fail(`${where}.schema_version`, doc.schema_version);
    const rule = obj(doc.inclusion_rule, `${where}.inclusion_rule`);
    keys(rule, { required: ["predicate", "version"], where: `${where}.inclusion_rule` });
    str(rule.predicate, `${where}.inclusion_rule.predicate`);
    str(doc.policy_sha256, `${where}.policy_sha256`);
    if (doc.policy_sha256.length !== 64) fail(`${where}.policy_sha256`, "must be a 64-char digest");
    const counts = obj(doc.counts, `${where}.counts`);
    keys(counts, { required: ["source_records", "projected_records", "unique_spell_ids"], where: `${where}.counts` });
    for (const key of Object.keys(counts)) int(counts[key], `${where}.counts.${key}`);
    return doc;
  },

  spell_policy_v2(doc) {
    const where = "spell_policy_v2";
    obj(doc, where);
    keys(doc, { required: ["schema_version", "reviewed", "required_tables", "tables", "joins", "sha256",
                           "content_sources", "bound", "expected_absent", "enum_policy", "anchor_set"],
                optional: ["budget", "provenance_note", "required_scalar_fields", "artifact_contract"], where });
    if (doc.schema_version !== "coa-spell-layout-v2") fail(`${where}.schema_version`, doc.schema_version);
    if (doc.reviewed !== true) fail(`${where}.reviewed`, "an unreviewed policy may not be staged");
    obj(doc.tables, `${where}.tables`);
    return doc;
  },

  // Delegates to the contract's own self-validation — one authority for what a contract is.
  generation_contract_v1(doc) {
    return validateGenerationContractShape(doc);
  },
};

// Imported lazily to avoid a module cycle: generation.mjs imports this file for the shape table.
let _validateGenerationContract = null;
function validateGenerationContractShape(doc) {
  if (_validateGenerationContract === null) {
    fail("generation_contract_v1", "contract validator not installed");
  }
  try {
    return _validateGenerationContract(doc);
  } catch (e) {
    throw new ShapeError(`generation_contract_v1: ${e.message}`);
  }
}

export function installContractValidator(fn) {
  _validateGenerationContract = fn;
}
