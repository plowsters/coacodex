# CoA Optimizer Scaffold

This is a scaffold for making Conquest of Azeroth build decisions data-driven.

## Inputs

Use your existing extraction pipeline to produce:

- `dist/coa_entries.jsonl`
- `dist/coa_classes.json`
- `dist/coa_essence_caps.json`

Recommended pipeline:

```bash
node scripts/extract-coa-builder-payload.mjs data/snapshots/final-page-content.html reports
node scripts/export-coa-normalized.mjs reports/coa_builder_payload.json dist
node scripts/build-class-profile-input.mjs dist/coa_entries.jsonl dist/coa_classes.json dist/coa_class_profile_input.json
```

## Optimize Stalker single-target

```bash
python coa_optimizer_extensible.py optimize \
  --entries dist/coa_entries.jsonl \
  --class-name Venomancer \
  --profile stalker \
  --encounter single_target \
  --level 60 \
  --max-ae 26 \
  --max-te 25 \
  --top 10 \
  --show-rotation
```

## Optimize Stalker AoE

```bash
python coa_optimizer_extensible.py optimize \
  --entries dist/coa_entries.jsonl \
  --class-name Venomancer \
  --profile stalker \
  --encounter aoe \
  --level 60 \
  --max-ae 26 \
  --max-te 25 \
  --top 10 \
  --show-rotation
```

## Generate a rotation scaffold from selected talents

```bash
python coa_optimizer_extensible.py rotation \
  --entries dist/coa_entries.jsonl \
  --class-name Venomancer \
  --profile stalker \
  --encounter single_target \
  --selected-names "Venom Fang" "Nerubian Sting" "Facemelter" "Noxious Empowerment"
```

## Parse combat log data

```bash
python coa_optimizer_extensible.py parse-log \
  --combat-log "Logs/WoWCombatLog.txt" \
  --player "Yourname"
```

## Use empirical data to influence builds

```bash
python coa_optimizer_extensible.py optimize \
  --entries dist/coa_entries.jsonl \
  --class-name Venomancer \
  --profile stalker \
  --encounter single_target \
  --combat-log "Logs/WoWCombatLog.txt" \
  --player "Yourname" \
  --empirical-blend 0.30
```

## Export graph data

```bash
python coa_optimizer_extensible.py graph \
  --entries dist/coa_entries.jsonl \
  --class-name Venomancer \
  --summary \
  --export-graph venomancer_graph.json \
  --export-cypher venomancer_graph.cypher
```

## Custom addon scaffold

The included `CoADataLogger.zip` is a minimal 3.3.5 addon scaffold. Install by extracting the `CoADataLogger` folder into `Interface/AddOns`.

Commands:

```text
/coalog start [label]
/coalog stop
/coalog snapshot
/coalog status
```

After `/reload` or logout, inspect:

```text
WTF/Account/<ACCOUNT>/SavedVariables/CoADataLogger.lua
```

Convert the SavedVariables table to JSON before passing it to:

```bash
python coa_optimizer_extensible.py parse-log --addon-json coa_data_logger_export.json --player "Yourname"
```

## Architecture

The script intentionally separates:

- Repository: normalized JSONL loading
- BuildRules: legality and prerequisite checks
- ScoringStrategy: heuristic or log-derived scoring
- BuildOptimizer: beam search
- RotationStrategy: SimC-like APL scaffolds
- CombatLogAdapter: Blizzard log/custom addon ingestion
- Exporters: graph JSON and Cypher

This is deliberately not a full simulator yet. The next step is adding a combat engine that models GCDs, cooldowns, resources, target counts, DoT ticks, proc rates, and encounter length.
