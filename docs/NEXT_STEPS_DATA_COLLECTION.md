# Data Collection Next Steps

This document lists data the user should collect or verify for each phase. The current captured Vol'Jin Alpha data is enough to begin Phase 1, but several validation datasets will make the roadmap safer.

## Phase 1 Data Needs

### Fresh Builder Capture

Collect a fresh official Ascension CoA builder capture when you want Phase 1 work to begin against current live data.

Collect:

- `coa.har`
- `data/raw/`
- `data/snapshots/initial-page-content.html`
- `data/snapshots/final-page-content.html`
- `data/snapshots/runtime-dump.json`
- `data/snapshots/final-runtime-dump.json`

Capture procedure:

1. Run the Playwright capture script.
2. Let the page load completely.
3. Manually click each class and each visible tab/spec if the script is not automated yet.
4. Press Enter in the capture terminal so final snapshots are saved.
5. Run extraction and normalization scripts.
6. Keep the full generated `reports/` and `dist/` directories together.

Why it matters:

- Phase 1 relies on builder data. Fresh captures reduce the risk of ranking builds from stale talent text or costs.

### Builder UI Validation Examples

Collect 5 to 10 known-valid and known-invalid build examples from the official builder UI.

For each example, save:

- class
- selected tab/spec intent
- selected node names or IDs
- level
- AE budget
- TE budget
- whether the official UI accepts or rejects the build
- screenshot or exported link if available

Why it matters:

- The build legality engine needs ground truth for tab gates, prerequisites, multi-rank nodes, and zero-cost starting/passive nodes.

### Budget and Progression Rules

Confirm:

- max Ability Essence at level 60
- max Talent Essence at level 60
- whether AE/TE budgets change by level
- whether all classes share the same caps
- whether some nodes are granted automatically by level, class, form, or quest state

Why it matters:

- Current reports show `maxAbilityEssence: 26` and `maxTalentEssence: 25` for all classes in the captured payload, but production tools should not assume that this always remains true.

### Tooltip Edge Cases

Collect examples of abilities with:

- weapon damage scaling
- spell power scaling
- attack power scaling
- periodic damage
- target caps
- pet or summon scaling
- proc chance
- charges
- cooldown reduction
- resource generation and spending
- ambiguous "nearby enemies" wording

Why it matters:

- Phase 1 can score from tooltip features, but Phase 3 simulation needs reliable parser coverage.

## Phase 2 Data Needs

### Controlled Target Dummy Sessions

For each class/spec you want calibrated, collect multiple short sessions under controlled conditions.

Recommended minimum per spec:

- 5 single-target target dummy sessions, 3 minutes each
- 5 5-target AoE sessions, 3 minutes each if a suitable dummy setup exists
- 3 burst-window sessions, 60 seconds each

For each session, record:

- class/spec/tab focus
- selected build
- level
- gear set
- weapon types
- armor type
- stats from character sheet
- target count
- buffs/debuffs used
- whether consumables were used
- encounter label
- addon SavedVariables export
- built-in `WoWCombatLog.txt`

Why it matters:

- Controlled sessions distinguish actual spell behavior from dungeon/raid mechanics and player movement.

### Real Encounter Logs

Collect dungeon, raid, and solo logs separately.

For each log batch, record:

- encounter name or content type
- group size
- target count pattern
- build used
- gear/stat snapshot
- combat log
- addon export if available
- notes about deaths, disconnects, or unusual mechanics

Why it matters:

- Real logs reveal uptime, movement, target switching, overkill, downtime, and player execution issues that dummy sessions hide.

### Addon Compatibility Notes

While using `CoADataLogger`, record:

- Ascension client build/version if shown
- whether `/coalog start`, `/coalog stop`, `/coalog snapshot`, and `/coalog status` work
- whether SavedVariables flush on `/reload`
- whether stock talent APIs expose CoA talents
- whether pet/guardian damage appears as player-sourced or pet-sourced events
- any Lua errors

Why it matters:

- The addon scaffold is minimal. Phase 2 needs evidence about what the 3.3.5 Ascension client exposes.

### AscensionLogsCompanion Probe

AscensionLogsCompanion is promising as a capture-pattern reference because it embeds compressed combatant-info payloads into `WoWCombatLog.txt`, but it should not become a dependency until a CoA sample proves it exposes CoA class/spec/essence state.

This remains a Phase 2 probe, not a Phase 1 dependency. Do not build an adapter until a CoA combat-log sample includes `ALC_CI_v1` and the decoded payload contains CoA node state.

Collect one short CoA combat log with AscensionLogsCompanion installed and combat logging enabled.

For the sample, record:

- AscensionLogsCompanion version or commit if known
- Ascension client build/version if shown
- class/spec/build used
- whether `WoWCombatLog.txt` contains `ALC_CI_v1`
- one decoded payload if the sentinel is present
- whether the decoded payload includes CoA class/spec, selected Ability Essence nodes, selected Talent Essence nodes, ranks, and spell IDs
- whether it only includes legacy CharacterAdvancement, gear, mystic enchants, or vanilla talent data

Decision rule:

- If CoA node state is present, add an `AscensionLogsCompanionAdapter` in Phase 2.
- If only legacy Ascension state is present, use the addon as a design reference and continue extending `CoADataLogger`.
- If no sentinel is present in CoA logs, mark the avenue not viable until the addon adds CoA support.

## Phase 3 Data Needs

### Coefficient Tests

For spells with unclear formulas, collect controlled tests where only one stat changes at a time.

Recommended method:

1. Remove variable buffs and procs.
2. Record naked or baseline stats.
3. Cast the same spell enough times to get non-crit and crit samples.
4. Change one stat source, such as spell power, attack power, weapon damage, or agility.
5. Repeat the same casts.
6. Save logs and snapshots for both states.

Why it matters:

- The simulator needs coefficients, not just tooltip text.

### Proc and Tick Tests

For proc-heavy builds, collect:

- number of triggering casts
- number of proc events
- whether DoT ticks can trigger the proc
- whether AoE hits can trigger once per cast or once per target
- tick intervals
- whether haste changes tick rate
- whether DoTs snapshot buffs or update dynamically

Why it matters:

- Proc normalization and DoT behavior are common sources of false rankings.

### Target Cap Tests

For AoE abilities, collect logs at different target counts:

- 1 target
- 2 targets
- 3 targets
- 5 targets
- as many targets as the client/content allows

Why it matters:

- Tooltip text often says "nearby enemies" without target cap, falloff, or per-target proc behavior.

## File Handling

Keep each data batch in its own folder with a short README:

```text
data_collected/
  2026-07-03_stalker_single_target_dummy/
    README.md
    WoWCombatLog.txt
    CoADataLogger.lua
    build.txt
    screenshots/
```

The README should include class, build, level, gear notes, stat notes, target count, session length, and anything unusual that happened.
