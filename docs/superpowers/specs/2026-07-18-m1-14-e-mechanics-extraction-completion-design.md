# M1.14E Mechanics Extraction Completion Design

> Fifth sub-milestone of [M1.14 Client DBC Data Foundation](2026-07-06-m1-14-client-dbc-data-foundation-design.md).
> Depends on **M1.14A** (extraction core, WDBC reader, backend, manifest/atomic-write) and **M1.14C**
> (the per-field precedence reconciliation engine it extends). Independent of M1.14D. Completes the
> **modeling-inputs half** of [Decision 19](../../DECISIONS.md): D delivered the WoW conversion
> primitives; E delivers the per-spell operands and the *static* resource substrate; M1.16 is the only
> engine and the only resource state machine. E builds none of the math.
>
> Revised twice (2026-07-18) after architecture reviews. The load-bearing revisions: a **black-box
> evidence boundary** (no emulator core is authority); **two decode gates, not one three-layer gate**;
> **raw operands ride their own provenance, never the multi-source reconciler**; **effect interpretation
> is per-slot**; a **size/streaming design** with an operands sidecar and a **statically discoverable
> mechanical closure** emitted into the mechanics output; resources split into **candidate / observation
> / canonical** contracts with *candidate* IDs only; and **E's exit gate requires complete raw extraction
> and honest candidates, never runtime-verified semantics** (so E and G do not form a cycle).
>
> **Sequencing.** The implementation plan is written against the **post-D working tree** (branch
> `m1-14-d`, which already alters `wdbc.py`, the CLI, manifests, and authored-input loading), not public
> `main` (0febc5c, which lacks D's implementation). G is **not** designed here — E defines only the
> [handoff interface](#eg-handoff-interface-not-a-g-design) G will later consume.

## Server architecture and evidence boundary (load-bearing)

CoA Codex **has not established Ascension's server lineage from a verifiable source**; the server is
treated as a proprietary **black box**. No open-source emulator (TrinityCore, MaNGOS/CMaNGOS,
AzerothCore) is ever *authority* for an Ascension claim — such projects only supply **reference
hypotheses** and **candidate probes** to be independently proven. Reference column positions where cores
agree (e.g. `CastingTimeIndex` at cell 28) are strong *candidates*; where cores disagree (e.g.
`SpellRuneCost` rune order) the raw cell order is preserved **unmapped** until Ascension spells prove it.
Coefficient-like cells are stored under **neutral raw names + reference aliases + verification status**.

**Sources** (what each can prove) — distinct from **methods**:

- **Ascension client bytes + artifact hashes** prove *stored layout and raw values*; they prove **no
  runtime behavior**.
- **Ascension binaries / Lua / MPQ-hosted addons / logs** prove *what the client ships/references*.
- **Controlled Ascension runtime observations** (M1.14G) prove *behavior under the captured conditions*
  only, and carry that condition identity with them.
- **Cross-validation across independent observations** is a *method* applied to the above, not a source.
- **Open-source cores** are hypothesis generators, never a source of Ascension truth.

So: static client observations prove stored bytes; runtime observations prove behavior under recorded
conditions; canonical mechanics require explicit Ascension-specific evidence and provenance. Each claim
records which source/method established it.

## Purpose

M1.14E extends `coa_client_extract` to the per-spell mechanical operands M1.14A/C/D left on the stale
db/inferred tiers, extracts the Ascension spell tables that carry them, and makes them available to M1.16
with honest provenance. It carries a **mandatory corrective repair** of the M1.14A `Spell.dbc` column map
(proven wrong by recon), and produces the **static resource substrate**: a class-wide *candidate*
resource inventory + a statically discoverable mechanical closure. E performs no analytical calculation,
builds no resource state machine, and rewires no consumer (`reporting.py` stays deferred to M1.16 with
the M1.14C deferral).

## Non-Goals (deferred, or unresolved pending runtime evidence)

- **No analytical engine / resource state machine (M1.16).** No coefficient/GCD/regen/resource math.
- **No live/runtime resolution (M1.14G).** Runtime carrier binding, generate/spend amounts, caps,
  regen/decay, reset/form/target behavior require a live session.
- **No consumer rewire.** `reporting.py`/scoring stay on current inputs until M1.16.
- **Server-authoritative mechanics are *unresolved*, not "server-side."** Scripted coefficients, custom
  scaling, proc numbers, and base HP/MP pools were **not established in the inspected static client
  sources**; their authoritative location and behavior are **unresolved and require runtime evidence**.

## Two decode gates (the M1.14A defect's real lesson)

The M1.14A defect — `power_type`/`school_mask` read from wrong columns yet marked
`schema_match_confidence.Spell: high` — happened because **header match proves structure, not
semantics**. But requiring full semantic proof before *any* decode would forbid the raw-with-unproven-
interpretation extraction the unknown-symbol policy correctly allows. So E uses **two gates**, evaluated
per field, from three independent proof facets (`integrity`, `layout`, `interpretation`):

```
raw_decode_eligible        = integrity(table)  && layout(field)
semantic_promotion_eligible = raw_decode_eligible && interpretation(field)
```

- **integrity** — magic/header, record & string bounds, record-size divisibility, duplicate-id check,
  source hash. (What M1.14A's `high` actually covered.)
- **layout** — the field's cell/type/array width/stride, plus the *independent* evidence fixing it
  (ground-truth anchors, side-table FK validity, value-domain sanity) — never "the header matched."
- **interpretation** — enum/bit/unit/semantic mapping, each with its own verification state.

A field that is `raw_decode_eligible` is **extracted raw** even when `interpretation` is unproven; only
`semantic_promotion_eligible` fields yield a normalized/interpreted value. `schema_match_confidence.Spell
== high` **no longer certifies any field's layout or interpretation.** Behavioral and canonical
(resource) claims carry their own scope/coverage requirements on top of these gates. Recon emits a
reproducible, reviewable `coa-spell-mechanics-recon-v1` report; **canonical extraction consumes a
separately reviewed, hash-bound layout policy** (`data/spell_layout_v1.json`) — recon never silently
rewrites or self-approves it. Scope is the **complete M1.14E extraction map** (the operand-inventory
fields), not all 234 columns.

## Reconnaissance hard hold (first task) — layout, not semantics

`mechanics-recon` runs against the real client and freezes `coa-spell-mechanics-recon-v1` (git-ignored,
reproducible): the per-field `integrity`/`layout` proof for the M1.14E extraction map; the confirmed
topology (effects/cooldowns/GCD/aura-options/charges **inline** in `Spell.dbc`; `SpellEffect`/
`SpellCooldowns`/`SpellAuraOptions`/`SpellCategories` **absent** in the inspected client; `SpellRuneCost`
the one side table; the custom tables with each **join path adjudicated** — *a table existing does not
prove its per-spell association*, e.g. `SpellChargesCategory`'s join is recon-gated); observed
opcode/enum domains; the representative spell set; and the measured **budgets** (below).

**The hard hold gates layout, not interpretation.** If the extraction map (offsets + topology) cannot be
established from Ascension evidence, E pauses. It does **not** require verified effect *interpretations*
to proceed — zero verified interpretations is an honest, valid E outcome (they are promoted when
available and reported when not; see [E/G handoff](#eg-handoff-interface-not-a-g-design)).

## The carried-in offset repair

Recon proved (VERIFIED vs ground-truth spells) the M1.14A map wrong: `power_type` cell **41** (not 110),
`school_mask` **225** (not 139), `name`@136 correct, `description`@**170**; `SpellRange` is **40 fields/
160 B** (layout expects 39/156 → drift). Because M1.14C reconciled `schools`/`power_type` from the wrong
cells and marked them client-authoritative, **it shipped wrong values.** E (1) freezes the reviewed,
hash-bound corrected layout policy and (2) **regenerates the M1.14C artifacts**. The frozen policy records
the real positions *and how each was proven*; `805775` remains only the currentness/name anchor.

## The raw-value observation envelope (lossless)

Every extracted cell/field is a **raw observation envelope** that preserves the raw bits independently
from any typed interpretation, so a wrong type guess or an unknown sentinel never destroys the datum:

```jsonc
{
  "state": "present" | "not_applicable" | "unresolved",
  "raw_u32": 4294967294,                 // the raw 32-bit cell(s), always retained
  "decoded": { "kind": "int32", "value": -2 } | null,   // typed reading; null if type unproven
  "proof": { "integrity": "verified", "layout": "verified", "interpretation": "unproven" },
  "evidence_ref": "recon:spell_layout_v1#power_type"
}
```

- `state`: `present` (a value exists — its `raw_u32` is always kept), `not_applicable` (zero FK / unused
  slot — see below), `unresolved` (decode failed). "Present-zero" vs "present-nonzero" is read from
  `raw_u32`; it is not a separate `state`.
- **Signedness/type is an interpretation**, carried in `decoded.kind`, never assumed in `state`. A
  **non-finite float** keeps its `raw_u32` with `decoded: null` and `interpretation: unproven` — it does
  not fail a structurally valid extraction (it may be an unknown sentinel/bit pattern).
- For **inline cells** a *layout* failure (cannot read the cell) fails canonical generation; an
  *interpretation* failure does not. For **joins**: zero FK → `not_applicable`; nonzero FK + matched row
  → `present`; nonzero FK + **missing** row → **integrity failure**.
- **Effect slots retain every raw cell even when `effect_opcode == 0`**, plus a separate
  `slot_activity: unused | active | unknown` (opcode-0 is not conflated with `not_applicable`).

Provenance is **co-located** with each value (the envelope's `evidence_ref` + `operand_provenance`
entries keyed by **exact JSON Pointer** into the record) — never a loose parallel object that can drift
out of alignment.

## Two lanes

### Scalar lane — operands are NOT reconciliation candidates for derived fields

Cooldown, GCD, cost, and rune operands are **direct client facts**, semantically distinct from the
existing db-derived `cooldown_ms`/`gcd_ms`/`costs`; forcing them through M1.14C's `reconcileField` (which
merges sources meaning the *same normalized thing*) would be a category error. They ride
**`operand_provenance`** (co-located, JSON-Pointer-keyed); `field_provenance` stays only for
same-normalized-meaning fields. M1.16 derives effective cooldown/GCD/cost from the operands and *then*
compares against the legacy fallbacks; E never redefines `cooldown_ms`/`gcd_ms`/`costs`.

Operands (all raw envelopes): `cooldown_operands` (`recovery_time_ms`, `category_id`,
`category_recovery_time_ms`); GCD operands (`gcd_base_ms`, `gcd_category`, `damage_class`,
`attributes_raw[]`; a derived `gcd_flags` only via a **verified** attribute→flag map); `cost_operands`
(`mana_flat`, `mana_per_level`, `mana_percentage`, `mana_per_second`, `mana_per_second_per_level`,
`power_type`, `power_display_id`, `rune_cost_id` + the `SpellRuneCost` row in **raw cell order**);
`charge_operands` (`charges`, `max_charges`, `recharge_ms`, `category` — **recon-gated join**).
`power_type` is captured raw incl. non-stock (see [unknown-symbol policy](#unknown-symbol-policy-amends-m114c)).

### Effect-operand lane — lossless, index-stable raw slots

Every effect slot is a raw envelope in **`effect_operands[3]`** (`effect_index` 0–2, all cells retained,
`slot_activity` per slot). The inventory is a versioned, manifest-bound `m1.14e-operand-inventory`; each
entry declares **reference_alias, array width, and the *candidate* encoding** (int32/uint32/float — a
`layout`-proven claim, not assumed). Neutral raw names. Minimum inventory (add-or-explicitly-adjudicate):

| Field (raw) | width | cand. encoding | reference_alias | notes |
|---|---|---|---|---|
| `effect_opcode` | ×3 | int32 | Effect | 0 → `slot_activity: unused` (cells still retained) |
| `aura_opcode` | ×3 | int32 | EffectApplyAuraName | |
| `base_points_raw` | ×3 | int32 | EffectBasePoints | no +1/die/scaling interpretation here |
| `die_sides` / `points_per_level` | ×3 | int32/float | EffectDieSides / EffectRealPointsPerLevel | |
| `amplitude_ms` | ×3 | int32 | EffectAmplitude | tick/period |
| `misc_value_a` / `misc_value_b` | ×3 | int32 | EffectMiscValue(B) | |
| `radius_index` | ×3 | uint32 | EffectRadiusIndex | → SpellRadius |
| `chain_targets` / `implicit_target_a` / `_b` | ×3 | int32/uint32 | EffectChainTargets / ImplicitTargetA/B | |
| `trigger_spell_id` | ×3 | uint32 | EffectTriggerSpell | closure edge |
| `value_multiplier` / `damage_multiplier` / `bonus_multiplier` | ×3 | float | Effect{Value,Damage,Bonus}Multiplier | **three distinct arrays** |
| `effect_mechanic` / `item_type` | ×3 | uint32 | EffectMechanic / EffectItemType | |
| `points_per_combo_point` | ×3 | float | EffectPointsPerComboPoint | |
| `spell_class_mask` | ×3 | uint32[3] | EffectSpellClassMask | |
| `proc_flags` / `proc_chance` / `proc_charges` / `stack_amount` | ×1 | int32 | | spell-level; `proc_charges` ≠ ability charges |
| `max_affected_targets` | ×1 | int32 | MaxAffectedTargets | |
| `spell_family_name` / `spell_family_flags` | ×1 | uint32 | | family classification |
| `spell_description_variable_id` | ×1 | uint32 | | → `SpellDescriptionVariables` (resolves `$` tooltip vars) |
| `stances` / `stances_not` | ×1 | uint32 | | form masks (resource/form evidence) |
| `projectile_speed` | ×1 | float | Speed | **in inventory** (travel time is plausibly M1.16-relevant; cheap raw field) |

## Effect interpretation — per-slot, never whole-array

Whole-array precedence loses information (one understood slot letting a partial client array replace the
whole field, dropping the other slots' tooltip interpretations). Structure:

- **`effect_operands[3]`** — mandatory raw slots.
- **`effect_interpretations[]`** — verified, per-slot interpretations **keyed by `effect_index`**, each
  with its own provenance + the authored-rule ID/version/hash. Only slots with an Ascension-**`verified`**
  rule produce an entry; others stay raw-only. **Zero interpretations is valid and honest.**
- existing **`effects[]`** — **unchanged** this milestone (until every relevant nonzero slot is mapped,
  or M1.16 introduces an explicit per-slot/aggregate model).

Rules live in `data/effect_semantics_v1.json` as a **declarative, non-executable DSL**: each rule has a
stable `rule_id`, a **predicate** over an operand slot from a *permitted predicate vocabulary*
(opcode/aura equality, target membership, misc-value/attr-bit tests — no arbitrary code), a
`normalized_kind` + operand→field bindings, and its own `ascension_verification` (`unverified` ⇒
withheld; only independently-`verified` ⇒ emitted). Two rules matching one slot → the slot is
`ambiguous`, stays raw-only, and is reported. A stock-referenced interpretation is **never** called
"client-proven."

## Size design and the operands sidecar

Three ~20-field effect envelopes + provenance + resource refs across **231,372** rows would be enormous
(the current reader materializes every decoded row twice). Architecture:

- **`coa-client-spell-v2`** stays **compact** (identity + corrected scalar `mechanics` block +
  attribution).
- **`coa-client-spell-operands-v1`** is a **sidecar** carrying the heavy envelopes. **Contract:** keyed
  by `spell_id` (unique, sorted); each row carries the **generation id** as a foreign key to the manifest;
  it covers exactly the closure domain (below); mechanics fields **reference** the sidecar by
  `(generation_id, spell_id)` — they are **not** embedded (keeps `coa-mechanics-v1` compact and lets a
  consumer load operands on demand).
- Detailed operands are emitted for the **closure domain**, not the whole table; full-table figures come
  from a **streaming diagnostic pass** (counts only). The decoder gains **selective/streaming** decoding.
- **Budgets** are **predeclared** in the layout/enums policy (artifact-size ceiling) and measured against
  a **pinned benchmark environment** recorded in the manifest — recon *reports* measurements against the
  predeclared budget; it does **not** measure a run and then implicitly approve its own budget. Exceeding
  a predeclared ceiling fails closed.

## Statically discoverable mechanical closure

`CharacterAdvancement` gives selectable **roots**, not every spell needed to model them. E emits
**`coa-client-spell-closure-v1`** = the *statically discoverable* mechanical closure (script-created
dependencies cannot be proven absent and are labelled as such). A **versioned edge-policy registry**
governs traversal; every edge carries `rule_id`, `source` (table + cell), `direction`, `proof_state`
(`candidate` | `verified`), `activation_conditions`, and `root_class_reachability`. Edge families with
their caveats: `trigger` (`EffectTriggerSpell`, directed root→target); `aura` (only when an effect
*applies* a specific spell as an aura — not every aura is a cross-spell edge); `rank`/`override`/`learn`
(via `SpellRank`/`OverrideSpellData` — must not pull unrelated siblings; scoped to the chain of the
root); `skill_line` (`SkillLineAbility` — sibling-pull guarded); `pet`/`summon` (needs
creature/pet sources, labelled `candidate` until those are decoded). Traversal is BFS from roots to a
fixed point; **cycles are retained and reported as strongly-connected components, never "broken"**;
missing targets are flagged, never silently dropped.

**Output domain (no ambiguous deferral).** E emits `coa-mechanics-v1` records for the **union of the
Builder-domain and closure-domain spell IDs**, with **separate readiness scopes** so consumers see which
came from which — counting closure-only spells is not enough to make them consumable, so their mechanics
are actually emitted. **Four readiness scopes:** (1) full `Spell.dbc` — diagnostic; (2) CoA attributed
roots; (3) **CoA mechanical closure — load-bearing for M1.16**; (4) Builder-domain — the historical
M1.14C domain.

## Unknown-symbol policy (amends M1.14C)

M1.14C fails the **entire** build on an unknown `power_type`/school bit — too brittle for a black-box
client. The consistent rule, applied to **power types, school bits, effect/aura/target opcodes, and
custom-attr bits**:

- **malformed structure / impossible typed value** (bad header, out-of-bounds offset) → **fail the
  artifact**;
- **previously-unseen enum/bit/opcode** → **preserve raw, block semantic promotion for that field,
  report it** (do not fail the build);
- **required normalized semantics unresolved within the CoA closure** → **readiness/blocking failure for
  the affected consumer scope** (M1.16 fails closed for that class/spell).

Recorded as a Decision amendment: update `DECISIONS.md`, the schemas, and the M1.14C tests that currently
require an unknown power enum to throw.

## Resources — candidate (E) only; observation & canonical are later

Three **immutable** contracts across milestones, with **candidate IDs in E and canonical IDs only after
adjudication** (a static hypothesis may later merge, split, alias, or be rejected, so a canonical
`resource_id` must not be baked into mechanics records prematurely):

- **`coa-resource-candidate-v1` (M1.14E, static)** — each candidate has a **stable `candidate_id`**,
  per-item evidence (spell IDs, tags, tooltip tokens, forms, alt-power/charge links), a **carrier
  hypothesis** (ordinary/alternative power, combo points, aura stacks, charges, custom, or unresolved),
  and an **adjudication class**: `confirmed_resource`, `related_mechanic`, `presentation_only`,
  `shared_or_system`, `false_positive`, `unresolved`. Mechanics records reference candidates via
  `resource_candidate_refs` (→ `candidate_id`), never a canonical `resource_id` and never a free-form
  token.
- **`coa-resource-observation-v1` (M1.14G, runtime)** — captured live evidence, carrying **build +
  condition identity**: client/source hashes, realm, level, build/spec/form, target context, capture
  time, observation procedure, and staleness rules.
- **`coa-resource-contract-v1` (post-adjudication, canonical)** — reconciled definitions produced by an
  assembler over a **candidate→resource mapping** that supports merge / split / alias / rejection, with a
  **field- and scope-specific authority policy** (a narrow live observation does **not** automatically
  supersede a proven static cap or a broader observation; contradictions stay **unresolved until
  adjudicated**). Fields: names; class/forms/builds/activation; carrier; scope; min/max/initial + scaling;
  generators/spenders + amounts; regen/decay/drain/conversion/refund; reset/death/zone/target-switch/
  form-transition; runtime APIs/events + static identifiers; per-claim provenance + condition identity;
  per-resource readiness.

**What E can and cannot prove.** The 21-class registry is only the **root set**; the discovery closure
also considers shared/`coa_system` spells, `SkillLineAbility`/baseline/granted abilities, rank/override/
learn/trigger relations, form masks + aura requirements, pet/summon abilities, MPQ-hosted UI addon code,
and binary/API evidence. Downgraded to **hypotheses**: a `power_type` distribution (passives carry a
default enum), a colored tooltip token (not a canonical identity), "no candidate found" (not proven
absence), and binary filename strings (a discovery roster, not proof no unlisted/dynamically-loaded file
exists). **E proves only that its declared static census ran completely** — resource *absence* and exact
*live behavior* belong to G.

## E/G handoff interface (NOT a G design)

E does not design G. E guarantees a **stable handoff** G will later consume, built from E's *actual*
emitted artifacts:

- `coa-resource-candidate-v1` (candidates + adjudication classes + carrier hypotheses + `candidate_id`s);
- `coa-client-spell-closure-v1` (the mechanical closure + edge provenance);
- the raw scalar/effect operands (`coa-client-spell-operands-v1`);
- honest **unresolved/readiness states** (nothing fabricated to look resolved);
- enough per-item metadata (stable ids, source refs) for later runtime observations to reference.

G's acquisition strategy, live-probing implementation, privacy/redaction, patch-staleness, and the
canonical assembler are **out of scope for this spec** and are designed later against these artifacts.
The M1.14 closure gate still holds (M1.14 cannot close with unresolved load-bearing class resources), and
the M1.16 gates below prevent unresolved resources from reaching authoritative reports — so E does not
need G finished to be correct.

## Artifact contracts (exact)

- **`coa-client-spell-v2`** (compact) + **`coa-client-spell-projection-v2`**; the projection reader
  asserts v2 and requires the corrected scalar block (a v1 artifact fails with a clear "regenerate with
  M1.14E" error).
- **`coa-client-spell-operands-v1`** sidecar (keyed `spell_id`, unique+sorted, generation-id FK, closure
  coverage) and **`coa-client-spell-closure-v1`** and **`coa-resource-candidate-v1`**.
- **`coa-client-extract-manifest-v2`** — an **exact dependency graph** + a **generation id**: per child
  {path, schema, sha256, bytes, records}; per source DBC {hash, header, archive}; the layout/enums/
  semantic-policy hashes; the projection/closure/candidate/recon-report hashes; the pinned benchmark
  environment + measured size/memory/runtime. **Transactional publication:** the whole family is
  generated into a **staging/versioned directory**; the manifest (carrying the generation id) is
  published **last**; **every consumer resolves the active generation via the manifest pointer**, so a
  failed run never pairs new children with an old manifest (the current `write_jsonl`/`write_json` write
  fixed paths non-atomically — E fixes this for the family).
- **`coa-mechanics-v1`** — additive only, **existing field meanings unchanged**. `cooldown_ms`, `gcd_ms`,
  `effects[]` are not redefined; the existing scalar `charges: int|null` is **kept** and **E populates it
  only after the `SpellCharges` join is proven** (today the producer never sets it), with the structured
  data in the additive **`charge_operands`**. New additive fields: `effect_operands`/
  `effect_interpretations` (sidecar-referenced), `operand_provenance`, `cost_operands`, GCD/cooldown
  operands, `resource_candidate_refs`. `MechanicsRepository` (`coa_meta/mechanics_repository.py`;
  dataclasses in `coa_meta/mechanics.py`) loads/validates/round-trips every new field.
  `reconciliation_policy_version` advances from `m1.14c-1`; the mechanics manifest binds
  `effect_semantics_v1` + all policy inputs; the `numberOrNull(null) → 0` coercion is repaired with
  missing-vs-zero tests on every new and legacy timer field.
- **Readiness** = evidence objects with an explicit `status` enum
  (`ready | partial | unavailable | ambiguous`) and, per scope, an **exact denominator** (e.g.
  `cooldown`: `decoded_records / eligible_records`; `effects`: `interpreted_slots / active_slots`), so a
  percentage is never ambiguous.
- **Policy-evidence retention.** The detailed recon report is git-ignored (client-derived), but the
  tracked layout/semantic policy files (`spell_layout_v1.json`, `effect_semantics_v1.json`,
  `spell_mechanics_enums_v1.json`) **embed the reviewable evidence summary per field/rule** (anchor spell
  ids, side-table validity counts, proof state) so review does not depend on the ignored report.

All new client-derived artifacts are git-ignored and join the M1.14C mandatory forward policy gate.

## Module layout

```
coa_client_extract/
  wdbc.py                         # + array/stride reads, per-field validation, streaming/selective decode
  dbc_layouts.py                  # corrected Spell map (from data/spell_layout_v1.json) + SPELL_MECHANICS_TABLES
  spell_mechanics.py              # NEW: recon (two-gate) + operand envelopes + closure BFS/edge policy
  spell_effects.py                # NEW: declarative per-slot interpretation DSL (+ ambiguity)
  resources.py                    # NEW: static census -> coa-resource-candidate-v1 (candidate ids)
  data/spell_layout_v1.json       # NEW: reviewed, hash-bound proven map w/ embedded per-field evidence
  data/effect_semantics_v1.json   # NEW: declarative rule DSL; per-rule ascension_verification
  data/spell_mechanics_enums_v1.json  # NEW: enums + predeclared size budget + benchmark env
  artifacts.py                    # + v2 writers, sidecar, closure, candidates; transactional staging
  cli.py                          # + `mechanics-recon` (hard hold) and canonical `mechanics`
coa_scraper/scripts/build-mechanics-artifacts.mjs + lib/*  # operand_provenance (not reconcileField);
                                  #   union output domain; readiness; policy-version bump; numberOrNull repair
coa_meta/mechanics.py + mechanics_repository.py   # round-trip new fields; charges only after join proven
docs/data/  client-spell-schema.md -> v2; mechanics-schema.md additive; NEW resource-candidate-schema.md
docs/DECISIONS.md  # unknown-symbol amendment; evidence boundary; operand-vs-derived; resource split
```

## Testing (mirrors existing tiers)

- **Offset regression**: `power_type@41`, `school_mask@225`, `description@170`; old 110/139 rejected.
- **Two gates**: a field passing integrity+layout but not interpretation is `raw_decode_eligible` and
  extracted raw, but not promoted; header-only match certifies nothing.
- **Envelope**: raw_u32 always retained; non-finite float → raw kept + `interpretation: unproven` (not a
  failure); `slot_activity` for opcode-0 slots; join FK states (`not_applicable`/`present`/integrity
  failure); provenance JSON-Pointer alignment.
- **Interpretation**: `unverified`/`ambiguous` → raw-only; `verified` → one `effect_interpretations[]`
  entry keyed by index; multi-slot spells keep all slots; **zero interpretations is a passing outcome**;
  `effects[]` unchanged.
- **Reconciliation**: operands on `operand_provenance` (not `reconcileField`); unknown-symbol amendment
  (raw + block + report, not build-fail); `MechanicsRepository` round-trips; `charges` scalar populated
  only after join proven; `charge_operands` additive.
- **Closure**: BFS + edge-policy provenance; SCC cycle retention; missing-ref diagnostics; **union output
  domain** emits mechanics for closure-only spells; four readiness scopes with exact denominators.
- **Publication**: interrupted extract never pairs new children with an old manifest; consumers resolve
  the active generation via the manifest pointer; predeclared size budget enforced against the pinned
  benchmark env.
- **Resources**: 21-class census runs completely; `coa-resource-candidate-v1` with `candidate_id`s +
  adjudication taxonomy (incl. `unresolved` and a `false_positive`); schema/algorithm tests use
  **generic synthetic** resources; class-specific generator/spender/cap/reset/form/target tests use
  **hash-bound real G observation fixtures** and are added only once that evidence exists.
- **`client` tier**: recon + canonical extraction; corrected offsets on `805775` + representative spells;
  census over all 21 classes; every observed resource token mapped or adjudicated; within budget.

## M1.16 handoff — remove or gate the current dangerous fallbacks

M1.16 entry conditions it must not silently inherit: `reporting.py` rebuilds mechanics from tooltip
inference instead of consuming canonical mechanics; it assigns every discovered resource a maximum of
100; `action_catalog.py` defaults missing GCD to 1500 and cooldown to 0; `simulation.py` invents costs,
amounts, GCDs, and generic resource pools. **For a class with an unresolved load-bearing resource,
authoritative rotation/build output must fail closed or render an explicit blocked/unverified report —
never fall through to these defaults.** Mandatory normalized effects that M1.16 needs are an **M1.16
entry/readiness gate**, never an E exit requirement (E never fabricates semantics to pass).

## Milestone decomposition

- **E0 — Correctness & publication foundation.** Reproducible recon report; reviewed, hash-bound field
  map (with embedded evidence); the two-gate proof model; streaming/selective decoder; transactional
  family publication + generation-id resolution.
- **E1 — Raw operands & closure.** Scalar/charge/effect operand envelopes + sidecar; 3-slot raw
  completeness + envelope states + `slot_activity`; joins + integrity rules; the statically discoverable
  mechanical closure + edge policy; **union output domain** in `coa-mechanics-v1`.
  **E1 inherits three joins as `unavailable`, by measurement, not by deferral.** E0R ran the
  value-anchor discovery for all four required joins and promoted one (`spell_icon_id` → cell 133);
  `casting_time_index`, `duration_index`, and `range_index` came back `reviewed_ambiguous` (30 / 34 / 14
  FK-validity candidate columns, no admissible anchor) and are owned by **M1.14G**. E1 must not plan
  around cast time, effect duration, or spell range, must not promote a candidate cell for them, and
  must not treat a re-run of the same FK-validity scan as new evidence. E1's own operands
  (cooldown/GCD/cost/charge/effect) are all inline in `Spell.dbc` and do not depend on those three side
  tables, so E1's scope is unaffected — only its assumptions are. See
  [E0R → Impact on M1.14E1](2026-07-19-m1-14-e0r-correctness-sunset-remediation-design.md#impact-on-m114e1).
- **E2 — Conservative interpretations.** Per-slot `verified` interpretations via the DSL (zero is valid);
  `coa-mechanics-v1` additive fields + repository round-trip; operand-vs-derived provenance.
- **E3 — Static resource candidates.** Exhaustive declared-source census; `coa-resource-candidate-v1`
  (candidate ids + adjudication) + the E→G handoff interface; no canonical/live claims.

**E's exit gate requires complete raw extraction + honest candidates, never runtime-verified semantics**,
so E and G do not form a cycle: G starts from published E1/E3 artifacts; verified interpretations are
promoted when available and reported when not; M1.14/M1.16 gates keep unresolved resources out of
authoritative output.

## Exit criteria (M1.14E)

- Recon emits reproducible `coa-spell-mechanics-recon-v1`; a **reviewed, hash-bound** corrected map is
  frozen (evidence embedded in the tracked policy); the M1.14A offset defect is repaired and the M1.14C
  artifacts regenerated; recon never self-approves.
- Every mechanical field is gated by **`raw_decode_eligible` / `semantic_promotion_eligible`**;
  `schema_match_confidence.Spell:high` certifies no field.
- Scalar operands ride `operand_provenance`; legacy derived fields unchanged. Every value is a raw
  envelope (raw bits retained; type as interpretation; `slot_activity` for effect slots).
- Every effect slot is losslessly in `effect_operands[3]`; interpretations are per-slot in
  `effect_interpretations[]` via the declarative DSL (**zero is a valid, honest outcome**); `effects[]`
  unchanged.
- The **operands sidecar** + **statically discoverable closure** exist; `coa-mechanics-v1` is emitted for
  the **Builder∪closure** domain with four readiness scopes (exact denominators); the family is
  **transactionally published** with a generation id; the **v2 manifest** binds the full graph + pinned
  benchmark budgets.
- `coa-mechanics-v1` additively extended (scalar `charges` populated only after join proven;
  `charge_operands` added); `numberOrNull` repair + missing-vs-zero tests; `MechanicsRepository`
  round-trips.
- The **unknown-symbol amendment** is applied consistently and recorded in `DECISIONS.md`.
- The class-wide static census runs completely and emits `coa-resource-candidate-v1` (candidate ids,
  adjudication) for all 21 classes + the E→G handoff interface; E claims only census completeness, never
  absence or live behavior.
- All new client-derived artifacts join the M1.14C forward policy gate; default-tier synthetic tests pass.

## Decision impacts

- **Evidence boundary (new):** black-box server; no emulator core is authority; sources vs methods;
  per-claim source/method recorded.
- **Two decode gates (new):** `raw_decode_eligible` (integrity+layout) vs `semantic_promotion_eligible`
  (+interpretation); raw extraction never waits on interpretation.
- **Operand-vs-derived provenance (new):** direct operands ride `operand_provenance`; only
  same-normalized-meaning sources use `field_provenance`.
- **Unknown-symbol amendment (amends M1.14C):** raw + block-promotion + report for unseen symbols;
  build-fail only for malformed/impossible; closure-scope readiness gates consumers.
- **Resource contracts split (new):** candidate (E, `candidate_id`) / observation (G) / canonical
  (post-adjudication, `resource_id`); candidate→resource mapping (merge/split/alias/reject); field- and
  scope-specific authority; condition identity on observations/contracts.
- **Mechanics output domain (new):** `coa-mechanics-v1` covers Builder∪closure; the closure is the
  load-bearing M1.16 scope; not deferred to M1.15.
- **M1.14G interface (not design):** E emits a stable handoff; G is designed later against E's artifacts;
  M1.14 cannot close with unresolved load-bearing class resources; M1.16 fails closed for them.
- **Decision 19 completes:** D = conversion primitives, E = per-spell operands + static resource
  substrate, M1.16 = engine + resource state machines.
- **Schema:** `coa-client-spell-v2` / `-projection-v2` / `-operands-v1` / `-closure-v1` /
  `-extract-manifest-v2` / `coa-resource-candidate-v1`; `coa-mechanics-v1` additive.
