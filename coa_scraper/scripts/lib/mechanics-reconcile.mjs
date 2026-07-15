import { isPresent } from "./mechanics-normalize.mjs";

export const TIERS = Object.freeze(["client_dbc", "verified_builder", "ascension_db", "inferred"]);

export const REASON = Object.freeze({
  HIGHEST_PRECEDENCE_ELIGIBLE: "highest_precedence_eligible",
  ONLY_CANDIDATE: "only_candidate",
  DB_FALLBACK: "db_fallback",
  INFERRED_LAST_RESORT: "inferred_last_resort",
  INFERRED_FROM_TEXT: "inferred_from_text",
  KIND_NODE_DISAGREEMENT_RESOLVED: "kind_node_disagreement_resolved",
  OMITTED_UNRESOLVED_CONFLICT: "omitted_unresolved_conflict",
  OMITTED_NO_ELIGIBLE_CANDIDATE: "omitted_no_eligible_candidate",
  SAME_TIER_CONFLICT: "same_tier_conflict",
  CLIENT_TABLE_DRIFT: "client_table_drift",
  DB_IDENTITY_MISMATCH: "db_identity_mismatch",
  DB_IDENTITY_UNVERIFIABLE: "db_identity_unverifiable",
  UNKNOWN_ENUM: "unknown_enum",
  UNKNOWN_MASK_BIT: "unknown_mask_bit",
  ABSENT: "absent",
});

// Note: the conditions that FATALLY fail a canonical build — per-table drift on a populated field,
// unknown school-mask bit, unknown power enum — are thrown directly by the projection validator
// (`assertRecordSemantics`, Task 9) BEFORE reconciliation. Candidate assembly (Task 7) additionally
// marks the corresponding client candidates ineligible as belt-and-suspenders, but the hard failure
// is the validator's; there is no separate "fatal reasons" lookup to keep in sync.

function sameValue(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// Mutates candidates: within each tier, if >1 present candidate disagrees, mark them all ineligible.
function applyTierConflicts(candidates) {
  for (const tier of TIERS) {
    const present = candidates.filter(
      (c) => c.precedence_tier === tier && c.eligible !== false && isPresent(c.normalized_value),
    );
    if (present.length < 2) continue;
    const first = present[0].normalized_value;
    if (present.some((c) => !sameValue(c.normalized_value, first))) {
      for (const c of present) {
        c.eligible = false;
        if (!c.eligibility_reasons.includes(REASON.SAME_TIER_CONFLICT)) {
          c.eligibility_reasons.push(REASON.SAME_TIER_CONFLICT);
        }
      }
    }
  }
}

export function reconcileField({ field, candidates }) {
  applyTierConflicts(candidates);
  let selected;
  let provenance = {
    selected_source: null, selected_tier: null, selected_value: null,
    selection_reason: null, warnings: [], candidates,
  };
  for (const tier of TIERS) {
    const winner = candidates.find(
      (c) => c.precedence_tier === tier && c.eligible && isPresent(c.normalized_value),
    );
    if (!winner) continue;
    selected = winner.normalized_value;
    const hadConflict = candidates.some((c) => c.eligibility_reasons.includes(REASON.SAME_TIER_CONFLICT));
    provenance.selected_source = winner.source;
    provenance.selected_tier = winner.precedence_tier;
    provenance.selected_value = selected;
    provenance.selection_reason =
      winner.precedence_tier === "ascension_db" ? REASON.DB_FALLBACK
      : winner.precedence_tier === "inferred" ? REASON.INFERRED_LAST_RESORT
      : candidates.length === 1 ? REASON.ONLY_CANDIDATE
      : REASON.HIGHEST_PRECEDENCE_ELIGIBLE;
    return { field, selected, provenance, hadConflict };
  }
  const anyConflict = candidates.some((c) => c.eligibility_reasons.includes(REASON.SAME_TIER_CONFLICT));
  provenance.selection_reason = anyConflict
    ? REASON.OMITTED_UNRESOLVED_CONFLICT
    : REASON.OMITTED_NO_ELIGIBLE_CANDIDATE;
  return { field, selected: undefined, provenance, hadConflict: anyConflict };
}
