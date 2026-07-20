import { isPresent, normalizeSchoolMask, normalizePowerType, normalizeDurationMs } from "./mechanics-normalize.mjs";
import { REASON } from "./mechanics-reconcile.mjs";

// The real client Spell-family column each mechanics field is sourced from (for candidate source_field).
const CLIENT_SOURCE_FIELD = {
  cast_time_ms: "cast_time_ms", duration_ms: "duration_ms", range_yards: "range_max_yd",
  schools: "school_mask", power_type: "power_type",
};

function clientNormalized(clientRec, field) {
  const m = clientRec?.mechanics || {};
  switch (field) {
    case "cast_time_ms": return { raw: m.cast_time_ms, value: isPresent(m.cast_time_ms) ? m.cast_time_ms : null };
    case "duration_ms": return { raw: m.duration_ms, value: normalizeDurationMs(m.duration_ms) };
    case "range_yards": return { raw: { min: m.range_min_yd, max: m.range_max_yd }, value: isPresent(m.range_max_yd) ? m.range_max_yd : null };
    case "schools": {
      const { schools, unknownBits } = normalizeSchoolMask(m.school_mask);
      return { raw: m.school_mask, value: schools.length ? schools : null, unknownBits };
    }
    case "power_type": {
      const { value, unknown } = normalizePowerType(m.power_type);
      return { raw: m.power_type, value, unknown };
    }
    default: return { raw: null, value: null };
  }
}

// Builder inferred fields (source/inferred split): damage_schools → schools, resources → power_type.
function builderNormalized(node, field) {
  if (field === "schools") {
    const v = Array.isArray(node.damage_schools) ? node.damage_schools.map(String) : [];
    return { raw: node.damage_schools, value: v.length ? v : null, inferred: true };
  }
  if (field === "power_type") {
    const v = Array.isArray(node.resources) && node.resources.length ? String(node.resources[0]).toLowerCase() : null;
    return { raw: node.resources, value: v, inferred: true };
  }
  return { raw: null, value: null, inferred: true };
}

export function fieldCandidates({ field, clientRec, builderNodes }) {
  const out = [];
  if (clientRec) {
    const { raw, value, unknownBits, unknown } = clientNormalized(clientRec, field);
    const reasons = [];
    // v2: the client value is already per-field/per-value proof-gated at extraction (an unproven or
    // out-of-domain value was withheld to null), so a present value is eligible. The unknown-bit/enum
    // guards remain as defensive belt-and-suspenders.
    let eligible = value !== null && value !== undefined;
    if (unknownBits && unknownBits.length) { eligible = false; reasons.push(REASON.UNKNOWN_MASK_BIT); }
    if (unknown) { eligible = false; reasons.push(REASON.UNKNOWN_ENUM); }
    out.push({
      source: "client_dbc", precedence_tier: "client_dbc", source_id: `client_spell:${clientRec.spell_id}`,
      source_field: CLIENT_SOURCE_FIELD[field] || field, raw_value: raw,
      normalized_value: eligible ? value : (value ?? null),
      confidence: clientRec?.coa_attribution?.confidence || "low", eligible, eligibility_reasons: reasons,
    });
  }
  for (const node of builderNodes || []) {
    const { raw, value } = builderNormalized(node, field);
    if (value === null) continue;
    out.push({
      source: "builder", precedence_tier: "inferred", source_id: `builder_node:${node.entry_id}`,
      source_field: field === "schools" ? "damage_schools" : "resources",
      raw_value: raw, normalized_value: value, confidence: "medium", eligible: true, eligibility_reasons: [],
    });
  }
  return out;
}
