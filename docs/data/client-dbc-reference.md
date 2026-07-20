# Ascension Client Data-Source Reference

A lookup map of the client tables and files CoA Codex extraction depends on, so a session can find the
exact location of a data source without re-running an offline census. Built from direct StormLib reads
of the real client (`~/Games/ascension-wow/.../ascension-live/Data`, ~44 GB) and binary-string mining
of `Extensions.dll` / `Ascension.exe`, 2026-07-17/18.

**Confidence labels** on every column/fact:
- **VERIFIED** — empirically proven against the real client (ground-truth spells, structural checks).
- **REPORTED** — the table/field exists (header read or binary string reference), semantics from the
  stock 3.3.5a reference or a name string, not yet cell-proven.
- **RECON** — assumed by the current code or reference, **not** yet verified and known-or-suspected wrong;
  must be re-adjudicated (see [M1.14E design](../superpowers/specs/2026-07-18-m1-14-e-mechanics-extraction-completion-design.md)).

> **Load-bearing warning.** The `coa_client_extract/dbc_layouts.py` `Spell.dbc` column map shipped in
> M1.14A/C is **WRONG** for the mechanical columns (see below). Do not trust column offsets that are not
> labelled VERIFIED here.
>
> **Evidence boundary.** Ascension's server is a proprietary black box of unknown lineage. Column
> positions and semantics taken from open-source cores (TrinityCore, CMaNGOS, AzerothCore, MaNGOS) are
> **reference candidates to probe, never proven Ascension facts** — a `REPORTED`/`RECON` label backed
> only by a reference core is a hypothesis until an Ascension spell proves it. Where cores disagree
> (e.g. `SpellRuneCost` rune order) the raw cell order is preserved unmapped.

## How to read a table

Every DBC is a `WDBC` file at `DBFilesClient\<Name>.dbc` inside the MPQ patch chain. Header = 20 bytes:
`magic("WDBC")`, `record_count`, `field_count`, `record_size`, `string_block_size`. Records are
fixed-width (`record_size` bytes = `record_size/4` uint32 cells); the string block follows and is
indexed by byte offset. Read through the project backend:
`StormLibBackend.read_effective_file(root, attach, "DBFilesClient\\<Name>.dbc")` (or, for many reads,
`stormlib_ctypes.open_patched_archive` once + `open_file`/`read_all`). The effective bytes come from the
top of the patch chain; **the current CoA mechanical `Spell.dbc` is supplied by `patch-T.MPQ`**, not a
`patch-C*` archive (see [[client-spell-dbc-supplied-by-patch-t]] / M1.14A finding).

The MPQ `(listfile)` is **stripped** on the patched view (anti-datamining), so tables cannot be
enumerated that way. The complete filename roster below was recovered by extracting `*.dbc` strings from
`Extensions.dll` + `Ascension.exe` (354 DBC names total).

---

## Spell.dbc — the core spell table

`records=231372  field_count=234  record_size=936  (234 cells)`  ·  effective archive: `patch-T.MPQ`

WotLK 3.3.5a inline layout (Ascension has **not** widened it — 234/936 matches stock; effects,
cooldowns, GCD, aura options, proc/charges are all **inline columns**, not separate tables).

| Field | Cell | Type | Confidence | Notes |
|---|---|---|---|---|
| `id` | 0 | uint32 | VERIFIED | |
| `power_type` | **41** | int32 | **VERIFIED** | current code says 110 — **WRONG**. Stock: mana 0, rage 1, focus 2, energy 3, happiness 4, runes 5, runic_power 6, health −2. Custom resources are **not** here. |
| `school_mask` | **225** | uint32 | **VERIFIED** | current code says 139 — **WRONG**. Bitmask: physical 1, holy 2, fire 4, nature 8, frost 16, shadow 32, arcane 64. |
| `name` (enUS) | 136 | string | VERIFIED | current code correct; this is why the M1.14A acceptance test (name only) passes. |
| `description` (enUS) | **170** | string | **VERIFIED** | carries `$`-variable tooltip text and color-coded resource tokens (`\|cff..NAME\|r`); this is where custom-resource names surface. |
| `EffectApplyAuraName1` | 95 | int32 | REPORTED | candidate (periodic-damage aura = 3 on Corruption 172); confirm in recon. |
| `casting_time_index` | 28 (ref) | uint32 | RECON | TrinityCore + CMaNGOS both place it at 28 (strong candidate); current code agrees. **Not Ascension-verified** — re-adjudicate against Ascension spells. |
| `duration_index` | 40 (ref) | uint32 | RECON | current code says 24 (suspect); reference cores say 40. **Not Ascension-verified.** |
| `range_index` | 46 (ref) | uint32 | RECON | current code says 29 (suspect); reference cores say 46. **Not Ascension-verified.** |
| `category` | 1? | uint32 | RECON | current code says 1 (Fireball→0, 805775→55). |
| effect slots ×3 | ? | mixed | RECON | inline, offsets unproven. Note **three distinct multiplier arrays** — `EffectValueMultiplier`, `EffectDamageMultiplier`, `EffectBonusMultiplier` (extract all three, do not collapse). Plus `Effect1-3`, `EffectBasePoints`, `EffectDieSides`, `EffectRealPointsPerLevel`, `EffectAmplitude`, `EffectMiscValueA/B`, `EffectRadiusIndex`, `EffectChainTargets`, `EffectImplicitTargetA/B`, `EffectTriggerSpell`, `EffectMechanic`, `EffectItemType`, `EffectPointsPerComboPoint`, `EffectSpellClassMask[3]`. Store under neutral raw names + reference aliases. |
| cooldowns | ? | int32 | RECON | `RecoveryTime`, `CategoryRecoveryTime` inline — offsets unproven. |
| GCD operands | ? | int32 | RECON | `StartRecoveryTime` (base GCD), `StartRecoveryCategory`, `DmgClass`, `Attributes*` bits — inline, offsets unproven (M1.14D deferred these here). |
| costs / misc | ? | mixed | RECON | `ManaCost`, `ManaCostPerLevel`, `ManaCostPercentage`, `ManaPerSecond*`, `RuneCostID`, `PowerDisplayId`, `procCharges`, `procChance`, `procFlags`, `StackAmount`, `MaxAffectedTargets`, `SpellFamilyName`, `SpellFamilyFlags`, **`SpellDescriptionVariableID`** (needed to resolve `$` tooltip vars), `Stances`/`StancesNot` (form masks) — inline, offsets unproven. |

---

## Spell side / support tables (stock)

| Table | records | fields | rec_size | Key columns (confidence) | Supplies |
|---|---|---|---|---|---|
| `SpellCastTimes` | 71 | 4 | 16 | id@0, base_ms@1 (RECON) | cast time (indexed by Spell `casting_time_index`) |
| `SpellDuration` | 866 | 4 | 16 | id@0, base_ms@1 (RECON) | duration (`−1` = infinite sentinel) |
| `SpellRange` | 323 | **40** | **160** | id@0, min@1, max@3 (RECON) | range; **current code expects 39/156 → perpetual drift**, re-verify field map |
| `SpellRadius` | 318 | 4 | 16 | id@0 (RECON) | effect radius |
| `SpellIcon` | 16031 | 2 | 8 | id@0, path@1 | icon paths |
| `SpellMechanic` | 31 | 18 | 72 | id@0 | mechanic enum |
| `SpellCategory` | 5022 | 2 | 8 | id@0, flags@1 (REPORTED) | category flags (category id + cooldown are inline in Spell.dbc) |
| `SpellRuneCost` | 476 | 5 | 20 | id@0, three rune cells @1–3 (**raw order unproven** — TrinityCore says blood/unholy/frost, CMaNGOS is inconsistent), runic_power_gain@4 (RECON) | DK rune cost (Spell `RuneCostID`; id 0 = no cost). Preserve raw cell order until Ascension spells prove each rune. |
| `SpellDescriptionVariables` | — | — | — | REPORTED | resolves `$`-variables in `description` |
| `SpellDifficulty` / `SpellChainEffects` / `SpellMissile` / `SpellVisual*` | — | — | — | REPORTED | presentation/misc |

**ABSENT (Cataclysm-era; do not look for them):** `SpellEffect`, `SpellCooldowns`, `SpellAuraOptions`,
`SpellCategories`, `SpellPower`, `SpellScaling`. Their data is inline in `Spell.dbc`.

---

## Custom Ascension spell tables

Discovered by binary mining (not guessable; `(listfile)` stripped). All confirmed present + counted.

| Table | records | fields | rec_size | Columns (confidence) | Supplies |
|---|---|---|---|---|---|
| `SpellAlternativePowerType` | 4 | 19 | 76 | id@0, assoc@1, …, cap@18 (REPORTED); strings: `Shadow Orbs (3/5)`, `Holy Power (3/5)` | named **secondary resources** + caps (only Cata backports enumerated; **not** Insanity/Brood) |
| `SpellAlternativeCost` | **0** | 3 | 12 | — | empty (alternative costs not populated client-side) |
| `SpellCharges` | 393 | 2 | 8 | spell@0, charges@1 (REPORTED) | per-spell charge count |
| `SpellChargesCategory` | 97 | 3 | 12 | id@0, maxCharges@1, rechargeMs@2 (REPORTED) | charge-category recharge. **Join to a spell is recon-gated** — table existence does not prove its per-spell association (via `SpellCharges`? a category cell? unproven). |
| `SpellCustomAttr` | 56319 | 11 | 44 | id@0, spell@1, attr bits@2.. (REPORTED) | custom per-spell attribute bitmasks |
| `SpellTags` | 496487 | 3 | 12 | id@0, spell@1, tagType@2 (REPORTED) | spell→tag membership |
| `SpellTagTypes` | 755 | 61 | 244 | id@0, icon@26 (VERIFIED-icon); **name column TBD** (string block = `{name, "Ability Type: <name>", icon}` triples) | ability taxonomy: Core Damage, Combo Generator, Combo Spender, DoT, HoT, Smart Heal, Absorb, Mobility, Raid Buffs/Debuffs, … |
| `SpellRank` | 22816 | 4 | 16 | id@0, family@1, spell@2, rank@3 (REPORTED) | rank chains |
| `SpellShapeshiftForm` | 61 | 35 | 140 | id@0, name in string block (REPORTED) | forms (Cat, Metamorphosis, Dark Apotheosis, Mana-Forged Barrier, Blood/Frost/Unholy Presence, …) — relevant to form-dependent resources |
| `SpellAffect` | 36558 | 3 | 12 | id@0, spell?@1, mask@2 (REPORTED) | spell-modifier affect masks |
| `SpellAddon` | 5589 | 23 | 92 | id@0, spell@1 (REPORTED) | spell addon data |
| `OverrideSpellData` | — | — | — | REPORTED | spell override sets |

---

## Power / resource display

| Table | records | fields | rec_size | Notes |
|---|---|---|---|---|
| `PowerDisplay` | 7 | 6 | 15 | id@0, ActualType@1 (bytes 4–7), GlobalStringBaseTag@ stroffset (bytes 8–11), R/G/B @ bytes 12–14. VERIFIED: all 7 are **stock vehicle-power reskins** (Pyrite/Steam/Heat/Ooze/Blood Power/Wrath), ActualType mana/energy — **no CoA class resource**. |

**Custom resources are NOT in a dedicated static power table.** They surface as: `power_type` (stock
only, + one vehicle `7` = Flak Cannon 801829), `SpellAlternativePowerType` (Shadow Orbs / Holy Power
only), combo points, aura-stack meters, and `SpellCharges`. The full picture requires the runtime layer
(below). See [[m1-14e-real-client-recon-findings]].

## Client resource runtime surface (Extensions.dll)

Client Lua APIs / events (runtime, resolved by M1.14G, not static): `UnitAlternativePower`,
`UnitAlternativePowerMax`, `UnitAlternativePowerType`, `GetComboPoints`, `GetSpellCharges`,
`UNIT_COMBO_POINTS`, `ASCENSION_DISPLAYPOWER`, `UNIT_POWER_ALTERNATIVE_UPDATE`, `PrimaryResources`,
`SecondaryResources`, class strings `CLASS_CULTIST` / `CLASS_VENOMANCER` / …. Custom resource tooltip
template in the binary: `\|cffa54cffDrains {} Insanity\|r`.

---

## GameTables (M1.14D)

`gtCombatRatings`, `gtOCTClassCombatRatingScalar`, `gtChanceToMeleeCrit(Base)`,
`gtChanceToSpellCrit(Base)`, `gtRegenMPPerSpt`, `gtOCTRegenMP`, `gtRegenHPPerSpt`, `gtOCTRegenHP`,
`gtNPCManaCostScaler`, `gtBarberShopCostBase`, plus `GameTables.dbc` (index). Physical form and axis
policy are frozen in `coa_client_extract/data/gt_axis_policy_v1.json`; see the
[M1.14D design](../superpowers/specs/2026-07-17-m1-14-d-wow-constants-design.md). `gtOCTClassCombatRatingScalar`
is `explicit_id`; base HP/MP tables are absent (server-side).

## Class / advancement family (M1.14B)

| Table | records | Key columns | Notes |
|---|---|---|---|
| `ChrClasses` | 32 | id@0, power_type@2, name@5 (VERIFIED) | stock class axis for GameTables; 32 rows (extended, M1.14D) |
| `CharacterAdvancement` | 12037 | node_id@0, spell_id@5, class_type@32 (VERIFIED anchors) | unified all-class advancement registry; `coa_class` subgraph = CoA graph. Many columns still undecoded (legality) — see [[client-characteradvancement-dbc-is-coa-registry]]. |
| `CharacterAdvancementClassTypes` | — | id@0, name@1 (VERIFIED) | **21 CoA classes, ids 14–34** (see below); sentinel 35 = ConquestOfAzeroth |
| `CharacterAdvancementTabTypes` | — | id@0, name@1 | spec/tab names |
| `CharacterAdvancementEssence` | — | id@0 | per-level AE/TE progression (raw, undecoded — M1.15) |
| `CharacterAdvancementCategories` | — | — | REPORTED |

**The 21 CoA classes (class_type_id : internal name):** 14 Barbarian, 15 WitchDoctor, 16 DemonHunter,
17 WitchHunter, 18 Stormbringer, 19 KnightOfXoroth, 20 Guardian, 21 Monk, 22 SonOfArugal, 23 Ranger,
24 Chronomancer, 25 Necromancer, 26 Pyromancer, 27 Cultist, 28 Starcaller, 29 SunCleric, 30 Tinker,
31 Primalist, 32 Reaper, 33 Venomancer, 34 Runemaster. (Display renames: WitchDoctor→"Witch Doctor",
etc.; Bloodmage/Felsworn/Templar semantic aliases — see [client-class-types-schema.md](client-class-types-schema.md).)

**Candidate class resources — HYPOTHESES, not proven (carrier + behavior → M1.14G).** These come from
tooltip tokens / power-type mixes / tag/charge signals and are candidates only; a colored tooltip token
does not prove a canonical resource, a `power_type` mix does not prove a class uses every power (passives
carry a default enum), and "no candidate found" is not proven absence. Carrier column is the *hypothesis*.

| Class | Candidate resource | Static evidence | Carrier hypothesis |
|---|---|---|---|
| Cultist | Insanity | 32 spell descriptions; "Each stack of Insanity"; `Drains {} Insanity` binary template | aura-stack |
| Venomancer | Brood Marks / Nerubian Sting / Venom | brood×12, mark×9, venom×43 in descriptions; form-dependent power mix | combo points and/or aura-stack |
| Starcaller | Stars | "Stars"×10 in descriptions | counter (unresolved) |
| Reaper | Souls, Runic Power, Infusion | Souls×5, Runic Power×11 | runic power + counter |
| SonOfArugal | Blood Shard, health-cost | Blood Shard×2; health@33 as cost | aura-stack + health |
| Chronomancer | Echo Fragment | Echo Fragment×2 | counter (unresolved) |
| Monk | Holy Power | `SpellAlternativePowerType` "Holy Power (3/5)" | alternative power |
| Stormbringer | Maelstrom | Maelstrom×1 | aura-stack (unresolved) |
| WitchHunter | Sin / Marks | "of Sin"×4 | unresolved |
| SunCleric | Scorch Marks | Scorch Marks×2 | aura-stack (unresolved) |
| Pyromancer | Flamecasting | Flamecasting×2 (stacks) | aura-stack |
| Necromancer | Runic Power | runic_power@13; Runic Power×5 | runic power |
| Tinker | charges | 6 spells with `SpellCharges` (most of any class) | charges |

All 21 classes carry pervasive aura "stacks" (9–41 spells each) and are multi-power-type
(form/spec-dependent). Barbarian/WitchDoctor/DemonHunter/Guardian/Ranger/Primalist/Runemaster show
primary powers + stacks and need deeper tracing. **None of the above is confirmed** — M1.14E emits these
as `coa-resource-candidate-v1` with adjudication classes; M1.14G resolves carriers.

---

## Loose `Data/Content/*.json` (on disk, no MPQ)

`CharacterAdvancementData`, `SpellRankData`, `ItemVariationData`, `SpellToStatSuggestionData`,
`SpellToRoleSuggestionData`, `SpellToSpellSuggestionData`, `SpellToEnchantmentSuggestionData`,
`EnchantmentTo{Stat,Role,Enchantment}SuggestionData`, `Transmogrification{Item,ItemDisplay,ItemSet}Data`,
`SkillCardData`, `LFGData`, `HandOfFateQuestData`, `TradeSkillRecipeData`, `WorldMapAreaData`. These are
stale for mechanics (name/icon references only; `CharacterAdvancementData.json` is superseded by the
`.dbc`).

## Binaries & runtime (client root, not `Data/`)

`Ascension.exe` (game), `Extensions.dll` (12 MB custom client extension — resource/UI logic, DBC name
roster, Lua API surface), `MemoryBridge.log` + `MMgr64.exe` (runtime IPC server mirroring 6 large tables
into shared memory — an M1.14G avenue), `WowError.exe`. Ascension custom UI addons ship **inside the
MPQs** (`Interface\AddOns\AscensionUI`, `Ascension_CoATalents`, …), not loose on disk.

---

*Maintenance: update the confidence label when a RECON/REPORTED field is verified. This doc is a
navigation aid, not a schema contract — the authoritative field maps live in
`coa_client_extract/dbc_layouts.py` (once M1.14E corrects them) and the per-artifact schema docs.*

## M1.14E0R confidence note

The current real client's `Spell.dbc` is bound by sha256 + full header in the reviewed
`coa-spell-layout-v2` policy; offsets are the recon-proven ones (`power_type@41`, `school_mask@225`), not
stock 3.3.5a. `SpellEffect`/`SpellCooldowns` are confirmed **absent** on this client (effects/cooldowns are
inline); their operand extraction is M1.14E1.
