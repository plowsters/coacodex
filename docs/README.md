# CoA Meta Analyzer Documentation

This directory documents the architecture and release roadmap for the Conquest of Azeroth meta analyzer. The current repository contains the Phase 1 package, the scraper/normalization pipeline, legacy prototype scripts, and planning docs for the next guide-site milestone.

## Document Map

- [ROADMAP.md](ROADMAP.md) defines phases, milestones, release gates, and exit criteria.
- [ARCHITECTURE.md](ARCHITECTURE.md) defines the target system boundaries and data flow.
- [MODULES.md](MODULES.md) defines each module's responsibility, inputs, outputs, and current code ownership.
- [NEXT_STEPS_DATA_COLLECTION.md](NEXT_STEPS_DATA_COLLECTION.md) lists the data the user needs to collect for each phase.
- [RETAIL_TOOLING_REFERENCES.md](RETAIL_TOOLING_REFERENCES.md) summarizes retail WoW tooling patterns this project should model.
- [DECISIONS.md](DECISIONS.md) records intentional architecture decisions so future agents can distinguish them from accidental prototype constraints.
- [ASSESSMENT.md](ASSESSMENT.md) assesses the prior conversation and identifies corrections or missing design work.
- [data/normalized-schema.md](data/normalized-schema.md) documents the `coa-normalized-v1` artifact contract.

## Current Repository Snapshot

The current codebase has these main areas:

- `coa_meta/`: Phase 1 package for normalized data loading, build legality/search, scoring profiles, APL generation, combat engine scaffolding, mechanics inference, stat/gear placeholders, report generation, and CLI entrypoints.
- `coa_scraper/`: Playwright/HAR capture, Next Flight payload extraction, normalization, AscensionDB enrichment, and captured reports/dist artifacts.
- `coa_optimizer_extensible.py` and `coa_graph_optimizer.py`: legacy prototype optimizer scripts retained for experimentation and compatibility.
- `CoADataLogger/`: minimal WotLK 3.3.5 addon scaffold that captures player-sourced combat events and basic snapshots to SavedVariables.

The target architecture keeps those concerns separate. Scrapers produce versioned structured data. Analyzers validate and enrich it. Optimizers consume only normalized data. Addons and logs provide empirical calibration data. Web frontends display reports and collect user inputs, but do not own simulation logic.

## Phase 1 Meta Report Command

After installing the package or running from the repository root, generate a theorycraft meta report with:

```bash
python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --out reports/meta \
  --format json --format md --format html
```

Useful bounded runs:

```bash
python -m coa_meta meta --class Venomancer --top 1 --format json --out reports/meta-smoke
python -m coa_meta meta --class "Sun Cleric" --spec Blessings --level 60 --out reports/sun-cleric-blessings
```

The report emits projected theorycraft indexes. It does not emit observed DPS, simulated DPS, or empirical rankings.

The command writes progress logs to stderr, including start, artifact/report stages, output formats, and completion.

For the M1.10 static guide-site renderer, include DB tooltip enrichment when available:

```bash
python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --db-tooltips coa_scraper/dist/coa_db_spell_tooltips.jsonl \
  --out reports/meta \
  --format html
```

This writes `index.html`, `meta-report.html`, `specs/*.html`, and static assets under `reports/meta/assets/`. Spec pages include static talent trees, level snapshots, diverse recommended builds, and player-facing core rotation loops when the corresponding report fields are available.

The legacy prototype can also be run from the repository root. Prefer the scraper artifact path:

```bash
python coa_optimizer_extensible.py optimize \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --class-name Venomancer \
  --profile stalker \
  --encounter single_target \
  --level 60 \
  --max-ae 26 \
  --max-te 25 \
  --top 10 \
  --show-rotation
```

For compatibility, the prototype now resolves a missing root-level `dist/coa_entries.jsonl` to `coa_scraper/dist/coa_entries.jsonl` when that artifact exists.

## Optional M1.8 DB Enrichment

The default Phase 1 report path remains network-free after artifacts exist. To refresh source and level enrichment from AscensionDB, run:

```bash
npm run pipeline:m1.8
```

From inside `coa_scraper/`, the equivalent command is `npm run pipeline:m1.8`; from any other working
directory, use `npm --prefix coa_scraper run pipeline:m1.8`.

This writes DB tooltip artifacts and an enriched entries file. AscensionDB enrichment is used for provenance and lower-level confidence; it does not replace builder legality fields.

## Current Planning Focus

M1.10 is the active Phase 1 guide-site milestone. It redesigns the static report as a player-facing guide site with a fel/void visual direction, individual class/spec guide pages, CoA-style talent trees, tooltip-rich spell/talent links, better role taxonomy, diverse playstyle build selection, and clearer stat/gear/rotation sections. See [ROADMAP.md](ROADMAP.md) and [M1.10 Guide Site and Report UX Design](superpowers/specs/2026-07-05-m1-10-guide-site-report-ux-design.md).

M1.10A/B, guide information architecture plus asset and tooltip integration, is implemented in the current repo. See [M1.10A/B Design](superpowers/specs/2026-07-05-m1-10-a-b-guide-ia-assets-design.md) and [M1.10A/B Implementation Plan](superpowers/plans/2026-07-05-m1-10-a-b-guide-ia-assets.md).

M1.10C/D, CoA-style static talent trees plus diverse build and core-loop selection, is also implemented. See [M1.10C/D Design](superpowers/specs/2026-07-05-m1-10-c-d-tree-diversity-design.md) and [M1.10C/D Implementation Plan](superpowers/plans/2026-07-05-m1-10-c-d-tree-diversity.md).

M1.10E/F, player-facing role taxonomy plus clearer stat and gear presentation, is designed and ready for implementation. See [M1.10E/F Design](superpowers/specs/2026-07-05-m1-10-e-f-role-gear-stats-design.md) and [M1.10E/F Implementation Plan](superpowers/plans/2026-07-05-m1-10-e-f-role-gear-stats.md).
