# M1.14D WoW Conversion Primitives Design

> Fourth sub-milestone of [M1.14 Client DBC Data Foundation](2026-07-06-m1-14-client-dbc-data-foundation-design.md).
> Depends only on M1.14A (`ArchiveBackend`, patch-chain resolution, the WDBC reader, manifest and
> atomic-write machinery). Realizes the **modeling-inputs half** of [Decision 19](../../DECISIONS.md)
> (the analytical player-power model): D delivers the WoW *conversion primitives*, its sibling M1.14E
> delivers the *per-spell operands*, and M1.16 is the engine that consumes both. D builds none of the
> math.
>
> Revised 2026-07-17 after two independent design-review passes. The revisions that shaped this spec:
> the GameTable **class axis is the stock `ChrClasses` namespace, not the CoA class-type namespace**, so
> class-indexed use by CoA classes is an explicit, class-context-gated M1.16 viability gate; **record count does
> not prove axis meaning** (a pinned reference indexing contract validated against explicit keys,
> coverage, holes, and anchors does); **GCD is per-spell, not caster/physical** (D publishes only the
> floor + standard-base reference constants, the per-spell base value is an M1.14E operand); `gtOCTRegenMP` and the base
> HP/MP tables are **recon-gated candidates**, not required halves; real-client extraction **must not
> fail merely because Ascension differs from stock** (that is a recorded deviation, not corruption); and
> every authored input (rules, enum maps, axis policy) is **manifest-bound**.

## Purpose

M1.14D extracts the client-authoritative WoW **conversion primitives** — the GameTable lookup values
that turn ratings, stats, and level into game effects — and pairs them with a small set of documented,
verification-labelled WotLK **rules** that are not in any DBC. It emits them as one versioned artifact,
`coa-wow-constants-v1` (a single JSON snapshot plus a binding manifest), and ships a thin `coa_meta`
reader that loads, validates, and looks them up. It is the deterministic-model input layer for M1.16.

M1.14D is a **producer plus a non-computing reader**. It performs no analytical calculation: it does not
convert rating→%, compute GCD, crit, or regen, or model any spell. It hands M1.16 the raw looked-up
operands, their provenance, and the *identified* reference formulas — M1.16 owns every formula and every
number it produces.

## Non-Goals (deferred within M1.14, or later)

- **No analytical engine or formulas (M1.16).** The reader returns raw values and names the reference
  formula a value participates in; it never evaluates one. "No formulas" means **no executable
  analytical engine**, not "no documentation of the formula."
- **No per-spell mechanical operands (M1.14E).** Base GCD (`StartRecoveryTime`/`StartRecoveryCategory`),
  `damage_class`, the GCD-relevant attribute bits, cooldowns, costs, coefficients, and charges are
  per-spell fields that belong to M1.14E's `SpellEffect`/`SpellCooldowns`/`SpellRuneCost` extraction, not
  to the GameTable/constants layer. D publishes only the GCD **floor + standard-base reference constants**.
- **No CoA→stock class bridge resolution.** D extracts every class-indexed table in its native stock
  `ChrClasses` namespace and *flags* whether a client-native CoA→stock bridge exists; it does not build
  one. Resolving the bridge is an explicit M1.16 entry condition (see [Class-axis viability gate](#the-class-axis-viability-gate-load-bearing)).
- **No HP-regen extraction.** The mana-side regen table is in scope; the HP-regen pair
  (`gtRegenHPPerSpt` + `gtOCTRegenHP`) is deferred with a documented M1.16 entry condition. The reader
  and layouts stay generic so adding it later needs no redesign.
- **No server-side scaling/procs.** Scripted coefficients and custom scaling are not in client DBC; they
  are scoped to the M1.14G spike and Phase 2, unchanged.
- **No consumer rewire and no site changes.** D defines the seam and proves it round-trips; M1.16 wires
  the engine to it.

## The class-axis viability gate (load-bearing)

The single most consequential fact about the GameTables: their **class axis is the stock WoW
`ChrClasses` namespace**, which the stock 3.3.5a formulas index by `ChrClasses.ClassID` for
`gtOCTClassCombatRatingScalar`, the crit tables, and the base-pool tables. The **reference-expected**
stock roster is IDs `1–9` and `11`, with an **unused hole at `10`** — but that is the *expectation to
verify*, not an assumption a client-authoritative extractor may bake in: recon records the **observed
client** roster, and a valid Ascension extension is recorded and adjudicated, never treated as
corruption. Either way, the class axis is a **different domain** from every CoA identifier in this repo:

| Namespace | Domain | Source |
|---|---|---|
| Stock `ChrClasses.ClassID` (`wow_class_id`) | reference-expected `1–9`, `11` (hole `10`); observed set from recon | GameTable class axis |
| CoA `CharacterAdvancementClassTypes.class_type_id` | `14–34` (21 playable) + `35` sentinel | `class_types.py` (M1.14B) |
| Builder `class_id` | CoA class-type namespace (not stock) | `coa_classes.json` |

D takes a deliberately narrow, implementable stance: **it never translates a CoA identifier into a
`wow_class_id`, and it never guesses an integer's namespace.**

- **The reader exposes only native, explicitly-named methods** — e.g.
  `class_combat_rating_scalar(*, wow_class_id, rating_id)` — whose class argument is a `wow_class_id` in
  the GameTable's own namespace. It accepts no CoA class-type id and performs no mapping. A caller that
  holds only a CoA class-type must resolve a `wow_class_id` first (below).
- **Class context is M1.16's to resolve, and D publishes *evidence*, not a Boolean.** A Boolean cannot
  translate class-type `14–34` into a `wow_class_id`, and a global 1:1 CoA-class bridge may be the wrong
  abstraction. The manifest instead carries
  `class_context_resolution ∈ {unproven, actor_wow_class_id, versioned_bridge}`:
  - `unproven` — the M1.14D default; no client-native CoA→`wow_class_id` mapping was proven.
  - `actor_wow_class_id` — the likely-correct abstraction: the modeled character/profile carries its own
    `wow_class_id`, so class context comes from the **actor**, not from the CoA class definition. (Two
    CoA classes can share a power type yet scale like different stock classes, so `power_type` is
    **never** a bridge.)
  - `versioned_bridge` — a complete published mapping. If D or a later milestone ever publishes one, it
    must publish the **entire** payload — every CoA class-type → `wow_class_id` entry, provenance,
    per-entry confidence, a cardinality policy (1:1 / many:1 / partial), and a hash — not a Boolean.
  M1.16 performs the **composite readiness check** for a class-indexed calculation using either an
  explicit actor `wow_class_id` or a separately versioned resolver. Recon reports whether any
  client-native bridge candidate is even discoverable (and where), but resolves none.
- **Canonical extraction succeeds regardless.** The class-indexed tables are emitted in their true
  `wow_class_id` namespace with `class_context_resolution: unproven`; nothing downstream may apply them
  to a CoA class without an actor `wow_class_id` or a versioned bridge. This prevents both false-positive
  readiness and silently applying one class's coefficients to another.
- **Level-only lookups are context-free.** `gtCombatRatings` (the per-level rating divisor) is indexed
  by `(rating_id, level)` alone, so it is usable immediately. Rating→% for a *specific* class
  additionally needs `gtOCTClassCombatRatingScalar[wow_class_id, rating_id]` and so requires a resolved
  class context, exactly like crit/regen/base-pool.

Restated precisely: **extraction-independent of B; application of class-indexed tables to a CoA class
requires class-context resolution, which is M1.16's composite check.** Recording the class-context
*evidence* (not a Boolean) is the M1.16 entry condition, kept here so it cannot be lost in decomposition.

## Reconnaissance before canonical (proof, not assumption)

Following the M1.14B `decode-advancement` precedent, a **non-mutating reconnaissance mode** runs before
any canonical emission and again (as strict validation) during it. `wow-constants --recon-only` opens
the client through the M1.14A backend and, for each target DBC, records to
`reports/client_extract/coa_wow_constants_recon.json` (git-ignored):

- the raw WDBC header (magic, record/field counts, record size, string-block size);
- the **physical form** — explicit-ID two-column (`id`, `value`) vs single-float indexed-by-row — and,
  if explicit, whether the ID equals the reference-contract index;
- record count vs the reference dimensions, with **holes/padding** identified (unused class `10`, storage
  padding beyond supported rating IDs, storage level stride beyond the level cap);
- value-domain sanity: finiteness (no NaN/±Inf), sign, and monotonicity of the *raw* divisor;
- the observed enum coverage (which `rating_id`s and `power_type`s actually appear), against the pinned
  maps — an observed-but-undefined ID is a failure, an unobserved-but-defined ID is fine (the M1.14C
  enum-recon rule);
- whether a client-native CoA→`wow_class_id` bridge candidate is discoverable (reported, not resolved).

**Axis meaning is never taken from record count alone.** It is established from an immutable
**reference indexing contract** (below) and then validated against: physical form, explicit/implicit key
agreement, complete coordinate coverage, holes/padding policy, and independent sampled **anchors**.
Canonical emission parses **strict** and fails closed on structural mismatch or unmapped IDs; recon is
diagnostic and warns.

The implementation plan's **first task is a real-client `--recon-only` adjudication checkpoint**: freeze
the physical form, the observed class-ID roster, per-table availability, and the `class_context_resolution`
evidence *before* any canonical-extraction task is written, so the frozen layouts, enum maps, anchors,
and their hashes rest on observed client facts, not stock assumptions.

## Reference indexing contract

The pinned stock-3.3.5a indexing the recon validates against (from the reference server
implementations; treated as the *contract to verify*, not a runtime assumption):

- `GT_MAX_LEVEL = 100` **storage stride** — the table stores 100 levels regardless of the WotLK 80 cap
  or CoA's 60 target. The artifact records `level_stride: 100` distinctly from any playable cap.
- Combat-rating divisor: `gtCombatRatings` indexed `rating_id * GT_MAX_LEVEL + (level - 1)`.
- Class rating scalar: `gtOCTClassCombatRatingScalar` indexed
  `(wow_class_id - 1) * GT_MAX_RATING + rating_id + 1` — note the **`+1` offset** and the `wow_class_id-1`
  base. `GT_MAX_RATING = 32` is the **storage stride**; only rating IDs `0–24` (the `CombatRating` enum)
  are **supported**. The artifact records `rating_storage_stride: 32` and the supported-ID set
  separately, and preserves the **existence and coordinates** of unused storage slots (via the recorded
  strides and counts) rather than compacting the domain — it does not emit their values.
- The rating→% **reference formula is identified, not computed**: `multiplier =
  class_scalar->ratio / combat_rating->ratio`. The reader returns both operands; M1.16 divides.

Storage stride, supported domain, and record count are distinct facts, recorded as such: each table's
`counts` block distinguishes `source_records` (from the header), `emitted_entries` (the supported
coordinates actually emitted), and `padding_records` (unused storage slots not emitted). Class axis
width is **never** derived from `len(ChrClasses)` (sparse: `1–9`, `11`).

## GameTable layout and the reader

Two structural additions to the M1.14A extraction core, kept narrow:

1. **A float ordinal-preserving read path in `wdbc.py`.** The existing `parse_positional` decodes cells
   as `uint32` and is unsuitable for single-float, implicit-index GameTables; `parse_dbc` needs a named
   layout with an ID column. A new reader (e.g. `parse_gametable(data, layout)`) yields, per record, the
   **ordinal index** and the `float` value (and the explicit ID column when the physical form has one),
   preserving row order and the string block for completeness. It reuses the shared header parse and the
   same drift semantics (`strict` raises, non-strict flags).
2. **A dedicated `GameTableLayout` (in `dbc_layouts.py`, a `GAME_TABLES` group).** Distinct from
   `DbcLayout`/`CharacterAdvancementLayout`, it carries: `physical_form`
   (`explicit_id` | `implicit_row`), `key_source`, `index_base`, per-axis `strides` and `domains`
   (supported vs storage), and `padding_policy`. `ChrClasses` is **not** in this group — it is a normal
   named DBC (`id`, `power_type`, `name`) read with `parse_dbc`, used for the class-axis roster and the
   default-power-type map, never as a GameTable.

## Table scope (tiered by proof)

**Proven-required** (canonical exit depends on them; stock role is well-established):

- `gtCombatRatings` — per-level rating divisor. Bridge-free.
- `gtOCTClassCombatRatingScalar` — the class half of rating→% (`GetRatingMultiplier`). Class-indexed →
  class-context-gated for CoA classes.
- `gtChanceToMeleeCrit` + `gtChanceToMeleeCritBase` — agility→melee-crit per class/level and base.
- `gtChanceToSpellCrit` + `gtChanceToSpellCritBase` — intellect→spell-crit per class/level and base.
- `gtRegenMPPerSpt` — the stock mana-regen operand (combined with Spirit and √Intellect **by M1.16**).
- `ChrClasses` — class-axis roster (sparse `1–9`,`11`) and default power type.

**Recon-gated candidates** (extracted *if present*, semantics labelled unproven, **not** required by
exit criteria until recon proves the table exists under that name and establishes its role):

- `gtOCTRegenMP` — left **unloaded/unused** by the pinned reference servers (AzerothCore, CMaNGOS). It is
  extracted opportunistically and labelled `semantics: unproven`; it is **not** called "base mana regen"
  and does not gate exit. Its Ascension role is a recon/M1.16 finding.
- `gtOCTBaseHPByClass` / `gtOCTBaseMPByClass` — base pools. Real base HP/MP in 3.3.5a is largely
  server-side (`PlayerClassLevelStats`); recon must confirm the client tables exist under those names and
  carry usable values before exit criteria require them. Class-indexed → class-context-gated.

**Deferred** (documented M1.16 entry condition, reader stays generic): the HP-regen pair
`gtRegenHPPerSpt` + `gtOCTRegenHP`, gated on passive/base health regen or between-pull recovery becoming
an explicit modeled term — **not** on spell healing, leech, or talent regen (those are M1.14E
mechanics/effects, not constants).

**Excluded:** NPC-scoped tables such as `gtNPCManaCostScaler`.

## Enum maps (versioned, consumer-ready)

`rating_id` and `power_type` integers are not consumer-ready on their own. The snapshot ships:

- `rating_enum` — a **pinned, versioned** `CombatRating` ID→name map (`0` weapon-skill … `24`
  armor-penetration), with supported IDs distinguished from unused storage slots.
- `power_type` — the int→string map, sourced from the **shared, versioned power-type enum**
  (`coa_client_extract/data/power_type_enum_v1.json`, version `m1.14c-power-v1`) rather than re-invented,
  so every consumer agrees on one authority. It is **not** tied to any `coa-mechanics` artifact version:
  M1.14E0R introduces `coa-mechanics-v2` and may withhold `power_type` normalization entirely (absent a
  static negative anchor — see the [E0R design](2026-07-19-m1-14-e0r-correctness-sunset-remediation-design.md)),
  so D depends only on the shared enum's ID→name mapping, which is independent of that decision.

Both are validated in recon against observed values (observed-but-undefined → failure; the M1.14C rule)
and carry a version string that the manifest binds.

## Artifact: `coa-wow-constants-v1`

One JSON snapshot, `coa_wow_constants.json`, coherent to a single client capture:

```json
{
  "schema_version": "coa-wow-constants-v1",
  "client_build": "3.3.5a+patch-...",
  "provenance": {
    "backend": "...", "backend_version": "...", "stormlib_version": "...",
    "extraction_date": "2026-07-17",
    "source_dbcs": {
      "gtCombatRatings": {"effective_archive": "...", "sha256": "...",
                          "header": {"record_count": 3200, "field_count": 1, "record_size": 4},
                          "drift": false}
    }
  },
  "class_axis": {"namespace": "chr_classes",
                 "reference_expected_ids": [1,2,3,4,5,6,7,8,9,11], "reference_holes": [10],
                 "observed_client_ids": [1,2,3,4,5,6,7,8,9,11],
                 "comparison": "exact"},
  "enum_maps": {"rating_enum": {"version": "cr-3.3.5a-v1",
                                "supported": {"0": "weapon_skill", "6": "spell_crit", "24": "armor_penetration"},
                                "storage_stride": 32},
                "power_type": {"version": "m1.14c-power-v1", "map": {"0": "mana", "1": "rage", "...": "..."}}},
  "game_tables": {
    "combat_ratings": {
      "source_dbc": "gtCombatRatings", "physical_form": "implicit_row",
      "axes": ["rating_id", "level"], "index_base": 0,
      "domains": {"rating_id": {"supported": {"min": 0, "max": 24}, "storage_stride": 32},
                  "level": {"supported": {"min": 1, "max": 100}, "storage_stride": 100}},
      "counts": {"source_records": 3200, "emitted_entries": 2500, "padding_records": 700},
      "class_indexed": false, "drift": false,
      "reference_comparison": {"scope": "anchors", "anchor_set_version": "wotlk-335a-anchors-v1",
                               "anchor_set_sha256": "...", "checked": 12, "equal": 12, "different": 0,
                               "status": "matches_on_checked_anchors"},
      "entries": [{"rating_id": 6, "level": 60, "value": 14.0}]
    },
    "class_combat_rating_scalar": {
      "source_dbc": "gtOCTClassCombatRatingScalar", "axes": ["wow_class_id", "rating_id"],
      "class_indexed": true, "index_base": 1, "index_offset": 1, "drift": false,
      "reference_comparison": {"scope": "anchors", "anchor_set_version": "wotlk-335a-anchors-v1",
                               "anchor_set_sha256": "...", "checked": 8, "equal": 7, "different": 1,
                               "status": "differs_on_checked_anchors"},
      "entries": [{"wow_class_id": 1, "rating_id": 6, "value": 1.0}]
    }
  },
  "rules": { "...": "see below" }
}
```

Notes:

- `entries` use **explicit coordinates**, never opaque flattened arrays, so a consumer never re-derives
  an index. Unused storage slots are omitted from `entries` but their existence is recorded via the
  domain `storage_stride`.
- Each table carries `class_indexed` (whether lookups need a resolved `wow_class_id`) and a scoped
  `reference_comparison` (`scope: anchors`, the hashed anchor-set version, and `checked`/`equal`/
  `different` counts with a `status`) — a differing valid value is a recorded Ascension deviation, not an
  error; only a divergence that leaves axis identity unresolved is `ambiguous` and requires adjudication.
  Whole-table equality is a distinct, stronger claim reserved for a full comparison against a named,
  hashed reference dataset (`exact_match`), never asserted from sampled anchors.

### Manifest (validity marker, binds every input)

`coa_wow_constants.manifest.json`, written **last** using the M1.14C manifest-as-validity-marker
protocol (remove old manifest → atomic artifact → atomic manifest), binds:

```json
{
  "schema_version": "coa-wow-constants-manifest-v1",
  "artifact": {"path": "coa_wow_constants.json", "sha256": "...", "byte_length": 12345},
  "source_dbc_sha256": {"gtCombatRatings": "...", "gtOCTClassCombatRatingScalar": "...", "ChrClasses": "..."},
  "authored_inputs": {
    "rules": {"version": "wow-rules-v1", "sha256": "..."},
    "rating_enum": {"version": "cr-3.3.5a-v1", "sha256": "..."},
    "power_type_enum": {"version": "m1.14c-power-v1", "sha256": "..."},
    "axis_layout_policy": {"version": "gt-layout-v1", "sha256": "..."},
    "reference_anchors": {"version": "wotlk-335a-anchors-v1", "sha256": "..."}
  },
  "class_context_resolution": "unproven",
  "table_summary": {"combat_ratings": {"source_records": 3200, "emitted_entries": 2500,
                                        "padding_records": 700, "drift": false,
                                        "reference_comparison_status": "matches_on_checked_anchors"}},
  "extractor_commit": "…", "client_build": "3.3.5a+patch-...", "extraction_date": "2026-07-17"
}
```

`extractor_commit` alone binds neither the authored inputs nor a dirty tree, so the manifest carries a
**version and a SHA-256 for every authored input** — the rules payload, both enum maps, the axis/layout
policy, and the reference-anchor dataset — alongside the artifact hash and byte length and each source
DBC's hash. Edited authored data therefore cannot retain the same advertised provenance, and two builds
cannot claim identical provenance while differing in any input.

## Documented rules (`wow_rules_v1.json`, verification-labelled)

The non-DBC rules are **audited domain data**, so they live in a declarative, tracked
`coa_client_extract/data/wow_rules_v1.json` (Python owns only the loader and validator, mirroring
`coa_meta/data/scoring_profiles/*.json`). The extractor merges them into the snapshot at build time; the
manifest binds their hash. Each rule carries: `value`/`unit`, `authority`
(`wotlk_reference` | `ascension_observed`), `ascension_verification`
(`unverified` | `verified` | `contradicted`), `applies_to` (applicability scope), `source_ref`, `notes`.
Every rule ships `authority: wotlk_reference, ascension_verification: unverified` until M1.14G/logs
confirm — a stock assumption is **never** presented as verified Ascension truth, and M1.14G/logs can
override a rule without touching the DBC-derived `game_tables`.

Initial rules, with the wording refinements the reviews required:

- **Energy** — base `100`, "before aura/talent modifiers"; regen `10/sec` **flat, no haste in the stock
  path** (scope: energy users; the no-haste caveat is explicit).
- **Rage / Runic Power** — bounds with **display-vs-internal unit** distinction, and an **out-of-combat
  decay** path (not "no passive regen"): both are generated from events and *decay* out of combat.
- **Focus** — actor-scoped (pet), numeric behavior **deferred/unverified for CoA players** unless
  independently sourced; explicitly a **separate path** from energy.
- **GCD** — only two reference constants: `gcd_floor_ms: 1000` (the haste floor) and
  `standard_spell_gcd_base_ms: 1500` (the *standard default* base most spells carry, **not** a universal
  schema-level ceiling). There is **no** "1.5s caster / 1.0s physical" rule: base GCD is a per-spell
  operand (`StartRecoveryTime` / `StartRecoveryCategory`), extracted in M1.14E; haste applies
  conditionally per spell and M1.16 clamps to the floor. The rule records that haste affects cast time
  and *spell* GCD but **not** energy regen in the stock path (focus behavior is deferred/unverified, so
  the rule makes no haste claim about it).

`ChrClasses.power_type` is recorded as the class's **default** power type — not a CoA-class mapping and
not a complete description of every resource a build uses (forms, talents, and scripts can change it).

## `coa_meta` reader: `WowConstantsRepository`

A thin loader in `coa_meta/wow_constants.py`, responsibilities **only**:

- **Hard-reject** an unsupported `schema_version` (mirrors `mechanics.mechanic_from_raw`).
- **Structural + semantic validation**: axes present; `entries` coordinates within declared domains; no
  duplicate coordinates; finite values (reject NaN/±Inf); every `rating_id`/`power_type` mapped; rules
  carry the required label fields; `class_axis`/enum/rules versions present.
- **Lookups returning raw values + provenance**: `combat_rating_ratio(rating_id, level)` (context-free),
  `class_combat_rating_scalar(*, wow_class_id, rating_id)`, `melee_crit_per_agi(*, wow_class_id, level)`,
  `base_mana(*, wow_class_id, level)`, `rule(key)`, `rating_name(rating_id)`, …. It preserves raw DBC IDs.
- **Native namespace only**: class-indexed methods take a **keyword-only `wow_class_id`** in the
  GameTable's own namespace. The reader **never** accepts a CoA class-type id and **never** guesses an
  integer's namespace or maps between namespaces. Composite class-indexed readiness — is there a valid
  actor `wow_class_id` or a versioned bridge? — is **M1.16's** check, informed by the manifest's
  `class_context_resolution`; D's reader simply refuses to guess.
- **Clear errors** for a missing table or an out-of-domain coordinate.

It performs **no calculation** — no rating→%, GCD, crit, or regen math, no derived multiplier. It may
name the reference formula a value participates in; it never evaluates one.

## Module layout

```
coa_client_extract/
  wow_constants.py            # NEW: recon + strict extraction + axis validation + snapshot assembly
  dbc_layouts.py              # + GameTableLayout type + loader/validator for data/gt_axis_policy_v1.json;
                              #   ChrClasses named layout (Python, like the existing SPELL_FAMILY)
  wdbc.py                     # + parse_gametable() float ordinal-preserving path
  data/wow_rules_v1.json      # NEW: authored, verification-labelled rules (tracked, hash-bound)
  data/rating_enum_v1.json    # NEW: pinned CombatRating id->name map (tracked, hash-bound)
  data/gt_axis_policy_v1.json # NEW: GameTableLayout axis/index/stride/domain policy (tracked, hash-bound)
  data/wotlk_reference_anchors_v1.json  # NEW: named/hashed level-60/80 anchor set (tracked, hash-bound)
  cli.py                      # + `wow-constants` subcommand (+ --recon-only); fails closed w/o StormLib
  artifacts.py                # + write_wow_constants() reusing atomic-write + manifest-last
coa_meta/
  wow_constants.py            # NEW: WowConstantsRepository (load/validate/lookup) — NO calculation
docs/data/wow-constants-schema.md   # NEW schema doc
```

The CLI seam mirrors `regenerate`: `python -m coa_client_extract wow-constants --client-root … --out …`
fails closed with a clear message when StormLib is unavailable (extraction-time dependency only);
`--recon-only` writes the recon report and stops without emitting a canonical artifact.

## Testing (three tiers, mirroring the existing structure)

**Default tier (synthetic fixtures, no StormLib, no client)** — the tier that runs in CI:

- Self-authored WDBC `gt*.dbc` byte fixtures covering **both** physical forms (explicit-ID and
  single-float implicit-row) and the sparse class axis (present `1–9`,`11`; **hole at `10`**).
- `parse_gametable` unit tests (ordinal preservation, float decode, drift `strict` vs flag).
- Axis-mapping and reference-contract validation: the **`+1` scalar offset**, `wow_class_id-1` base,
  storage-stride-vs-supported-domain separation, complete-coverage and holes/padding checks.
- Snapshot assembly + **manifest-as-validity-marker** (an interrupt never leaves a new artifact beside a
  stale manifest) + **authored-input binding**: a per-file **hash-change test** for each tracked authored
  input (`wow_rules_v1.json`, `rating_enum_v1.json`, `gt_axis_policy_v1.json`,
  `wotlk_reference_anchors_v1.json`) — editing any one changes its `authored_inputs[...].sha256` and the
  artifact hash.
- `WowConstantsRepository`: schema-version rejection; duplicate-coordinate, out-of-domain, and
  **NaN/±Inf rejection**; **missing-vs-zero** (a real `0.0` is a value, an absent coordinate is an
  error); **native-namespace enforcement** — the class-indexed methods are keyword-only `wow_class_id`,
  perform no namespace inference, and **reject** a CoA class-type id or any out-of-domain id with a clear
  error (composite class-context readiness stays M1.16's, never the reader's).
- **Modeling-standard reference tests (synthetic only):** fixtures constructed so that
  `class_scalar / combat_rating` at levels **60 and 80** reproduces documented multipliers; the **raw
  divisor is nondecreasing within each supported `rating_id` as level increases** (plateaus allowed,
  never compared across flattened rating boundaries), with the derived per-point multiplier
  correspondingly **nonincreasing** — both asserted as **test-only oracles**, never as repository
  behavior; enum/rule labels present.

**`stormlib` tier** — the backend read path over a synthetic MPQ.

**`client` tier (`COA_CLIENT_ROOT`)** — recon + canonical build against the real client. It gates on
**structure and sanity, not stock equality**:

- structural/layout mismatch, impossible coordinates, duplicates, non-finite values, or unmapped IDs →
  **fail**;
- a valid client value that differs from stock WotLK → recorded in `reference_comparison` as
  `differs_on_checked_anchors` (an Ascension deviation), **not** a failure — otherwise
  "client-authoritative" would collapse into "stock-WotLK-authoritative";
- a divergence that leaves axis identity ambiguous → `ambiguous`, requiring adjudication;
- an observed client class roster that extends or changes the reference expectation → recorded in
  `class_axis.comparison` (`extended`/`changed`) and adjudicated, never auto-treated as corruption.

## Redistribution boundary

`coa_wow_constants.json` and its manifest are **client-derived factual outputs** → untracked, per
Decision 20, alongside the M1.14C artifacts. Committed test fixtures are **synthetic** (self-authored
WDBC bytes and a synthetic snapshot), never client bytes. The authored rules and enum maps are tracked
source (`wow_rules_v1.json`); only the merged snapshot is ignored. New file-specific ignore rules:

```
# client-derived factual outputs — regenerate from your own client
reports/client_extract/coa_wow_constants_recon.json
coa_scraper/dist/coa_wow_constants.json          # (or the chosen --out location)
coa_scraper/dist/coa_wow_constants.manifest.json
```

**Forward policy gate (mandatory, before M1.16 or any canonical public release).** `coa_wow_constants.json`
**joins the M1.14C forward policy gate** — it is not demoted to an M1.20-only concern. The single
explicit policy decision M1.14C requires before M1.16 consumes any client-derived output, or before any
canonical public release, must now cover `coa_wow_constants.json` consistently with
`coa_client_spell_coa.jsonl` and `coa_mechanics.jsonl`. D leaves the decision unresolved but registers
its artifact under the existing mandatory gate; this must not disappear during decomposition.

## Risks and boundaries

- **Class context unresolved.** The dominant risk: without a resolved `wow_class_id` for a CoA actor,
  class-indexed conversions cannot be applied to CoA classes. Mitigated by extracting in the true
  namespace, the `class_context_resolution` evidence in the manifest, a reader that exposes only native
  `wow_class_id` methods (never guessing), and surfacing the composite check as an explicit M1.16 entry
  condition rather than silently mapping one class's coefficients onto another.
- **Axis misread.** A plausible header does not prove column meaning (the M1.14B lesson). Mitigated by
  the reference indexing contract + recon validation (explicit keys, coverage, holes, anchors) and
  strict canonical parsing.
- **Recon-gated tables absent or repurposed.** `gtOCTRegenMP` and the base-pool tables may be unused or
  Ascension-repurposed; mitigated by labelling them `unproven` and keeping them off the exit gate until
  recon establishes their role.
- **Stock ≠ Ascension.** Treating a stock mismatch as corruption would make the tool stock-authoritative;
  mitigated by the scoped `reference_comparison` deviation model (anchor-scoped, not a whole-table
  equality claim) and the structure-only real-client gate.
- **StormLib install friction / fail-closed.** Same posture as M1.14A/C: extraction-time only, synthetic
  fixtures for the default suite, no canonical artifact without StormLib.

## Exit criteria

- `coa-wow-constants-v1` regenerates from a fresh MPQ read via the new `wow-constants` command, fails
  closed without StormLib, with the binding manifest written last and full per-DBC provenance + drift
  flags.
- The **proven-required** set is extracted with validated axis mappings: `gtCombatRatings`,
  `gtOCTClassCombatRatingScalar` (both halves of rating→%), the four crit tables, `gtRegenMPPerSpt`, and
  `ChrClasses`. Recon-gated candidates (`gtOCTRegenMP`, base HP/MP) are included **only** where recon
  proves the table and its role; the HP-regen pair is deferred with a documented M1.16 entry condition;
  NPC tables are excluded.
- The **class axis is recorded in the stock `ChrClasses` namespace** (reference-expected vs observed,
  with holes and a `comparison`); the manifest carries `class_context_resolution` (default `unproven`);
  the reader exposes only native keyword-only `wow_class_id` methods and never maps namespaces; composite
  class-indexed readiness is M1.16's check.
- The reconnaissance report resolves and records the real Ascension layout (headers, physical form,
  explicit/implicit keys, record counts, value domains, holes) and the enum coverage; axis meaning is
  validated against the reference indexing contract and anchors, never inferred from record count.
- Documented rules are verification-labelled (`authority` + `ascension_verification` + applicability)
  and live in tracked `wow_rules_v1.json`; every authored input (rules, both enum maps, axis policy,
  reference anchors) carries a manifest **version + SHA-256**; GCD ships only the floor + standard-base
  reference constants (per-spell base GCD deferred to M1.14E); no stock assumption is presented as
  verified Ascension truth.
- `WowConstantsRepository` loads the artifact, hard-rejects other schema versions, validates structure
  (including NaN/±Inf and missing-vs-zero), exposes raw lookups + provenance via native keyword-only
  `wow_class_id` methods (no namespace guessing), and computes **no** formulas.
- Default-tier synthetic tests pass (including the level-60/80 anchor oracle, sparse class `10`, the `+1`
  scalar offset, and the derived-multiplier monotonicity oracle); the client-tier acceptance test gates
  on structure/sanity and records deviations via `reference_comparison` rather than asserting stock
  equality.
- Implementation begins with a real-client `--recon-only` adjudication checkpoint that freezes physical
  form, observed class IDs, per-table availability, and `class_context_resolution` evidence before any
  canonical-extraction task.
- `coa_wow_constants.json` is registered under the M1.14C mandatory forward policy gate.

## Decision impacts

- **Decision 19** advances: its *modeling-inputs* half is now split concretely — D delivers the
  conversion primitives and documented rules, M1.14E delivers the per-spell operands, M1.16 remains the
  only engine. No new decision is required.
- **New M1.16 entry conditions recorded here:** (1) resolve class context — an actor `wow_class_id` or a
  versioned, hashed CoA→`wow_class_id` bridge — before applying any class-indexed conversion to a CoA
  class (D records `class_context_resolution` evidence and never guesses); (2) add the HP-regen pair only
  if base/passive health regen becomes an explicit modeled term.
- **M1.14E scope addition:** the GCD base operands (`StartRecoveryTime`/`StartRecoveryCategory`,
  `damage_class`, GCD-relevant attribute bits) are per-spell fields M1.14E must extract, since D
  deliberately publishes only the floor + standard-base reference constants.
- **Redistribution:** `coa_wow_constants.json` is added to the M1.14C mandatory forward policy gate; the
  boundary itself is unchanged (synthetic fixtures, untracked client-derived outputs).
