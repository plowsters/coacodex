# CoA Meta Analyzer Documentation

This directory documents the architecture and release roadmap for the Conquest of Azeroth meta analyzer. The current repository contains the Phase 1 package, the scraper/normalization pipeline, the client-native extraction producer, legacy prototype scripts, the M1.10 guide site, the M1.11 report-correctness/data-parity/simulation-hardening pass (A–G), and the in-progress M1.14 client DBC data foundation.

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
- `coa_scraper/`: Playwright/HAR capture, Next Flight payload extraction, normalization, mechanics artifact building from a published client-extraction pointer, and captured reports/dist artifacts.
- `coa_client_extract/`: the client-native extraction producer — MPQ/DBC reading behind a StormLib binding, the reviewed client-bound layout policy, and transactional publication of a hash-pinned generation.
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

For the static guide-site renderer, ask for the HTML format:

```bash
python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --out reports/meta \
  --format html
```

Spell icons and hover tooltips resolve from the published client generation, so the renderer takes no
tooltip-enrichment input and makes no network request.

This writes `index.html`, `meta-report.html`, `specs/*.html`, and static assets under `reports/meta/assets/`. Spec pages include static talent trees, level snapshots, diverse recommended builds, and player-facing core rotation loops when the corresponding report fields are available.

### Backend Trust Sidecar (maintainer-only)

To emit an internal QA sidecar alongside the report, add `--write-backend-trust` (optionally `--backend-trust-out PATH`):

```bash
python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --out reports/meta \
  --format json \
  --write-backend-trust
```

This writes `backend-trust-report.json` (`coa-backend-trust-v1`) with coarse per-build trust components and live-sanity watchlist matches. It is a maintainer/QA artifact only: trust scores are never rendered in the guide and must not be presented as empirical confidence until Phase 2 logs exist. See [backend-trust-schema.md](data/backend-trust-schema.md).

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

## Client-Native Mechanics Extraction

Spell mechanics come from the local Ascension client, not from a remote database. The M1.8/M1.9 DB
enrichment pipeline was **retired** by M1.14E0R: its runtime is deleted, `ascension_db` is no longer a
reconciliation tier, and a canonical build makes no network request at all.

Extraction runs against a real client install and publishes a hash-pinned generation:

```bash
python -m coa_client_extract mechanics-recon --client-root "$COA_CLIENT_ROOT" --out reports/client_extract
python -m coa_client_extract regenerate --client-root "$COA_CLIENT_ROOT" --out reports/client_extract
```

`mechanics-recon` is the hard hold: it proves the client topology against the reviewed layout policy and
must report `verified` before a `regenerate` may promote any value. `regenerate` stages a candidate
generation, validates it in both Python and Node, and only then writes the pointer the consumers read.
`$COA_CLIENT_ROOT` is the client's `Data` directory; both commands need the proprietary client and are
therefore local-only, never CI steps.

The Node consumer builds its mechanics artifacts from that pointer:

```bash
npm --prefix coa_scraper run build-mechanics
```

It fails closed when the pointer is absent or unready rather than substituting a default, so a missing
cost or cooldown stays `null` (unknown) instead of becoming a fabricated number.

## Current Status

Phase 1 is mid-**M1.14** (client DBC data foundation). Mechanics, legality, and icons resolve from the
local client under a reviewed, hash-bound policy; per-field readiness marks what is genuinely extracted
and what remains unavailable, and consumers fail closed on the difference. Cast time, effect duration,
and spell range are **not** yet available — their `Spell.dbc` columns are not uniquely resolvable from
admissible evidence (see [ROADMAP.md](ROADMAP.md), M1.14G). Rankings therefore remain projected
theorycraft indexes, not empirical or recommendation-grade output.

### Milestone History (as shipped)

The entries below record each milestone as it shipped, and are **history**: several describe
AscensionDB enrichment, DB tooltips, and remote icon hotlinks, all of which M1.14E0R removed in favour
of the client-native pipeline described above.

M1.11, the Phase 1 report-correctness, data-parity, and simulation-hardening milestone, is implemented as a first pass across all sub-milestones (A–G) and merged to `main`. It corrected guide output where the M1.10 static site was useful but not yet faithful enough to the CoA Builder, intended roles, source assets, or rotation expectations. See [ROADMAP.md](ROADMAP.md), [M1.11 Design](superpowers/specs/2026-07-05-m1-11-report-correctness-data-parity-design.md), and [M1.11 Implementation Plan](superpowers/plans/2026-07-05-m1-11-report-correctness-data-parity.md).

M1.11A quick fixes, M1.11B role/objective work, and M1.11C builder-tree layout plumbing are implemented:

- Main guide index role sections for Tank, Healer, Support, Caster DPS, Ranged DPS, and Melee DPS.
- Multi-select role filters.
- Front-page theorycrafting disclaimer.
- Legacy user-facing spec renames while preserving source names for internal joins.
- Safe DB tooltip table rendering.
- `ranged_dps` role support in report filters, stats, gear, and rotation wording.
- Harvest and Soul Reaper curated as DPS specs.
- Official launch-video class/spec role map with primary and secondary roles.
- Role-specific objective index labels for damage, healing, survival/threat, and support while preserving `projected_dps_index` for compatibility.
- Hybrid specs can appear in secondary-role guide sections.
- Builder tree layout artifact parser and capture command.
- Static guide rendering for separate Ability Essence, Talent Essence, and level-passive tree groups.
- `--builder-layout-root` support for guide HTML generation.

M1.11D and M1.11E are implemented as first passes:

- Cache-aware AscensionDB icon/image/item/effect scraping.
- APL-backed rotation simulation and guide-ready priority output.

M1.11F and M1.11G are implemented as first passes:

- M1.11F exact level-by-level talent paths and stronger build diversity clustering. Design: [M1.11F Exact Leveling Path and Build Diversity Correctness](superpowers/specs/2026-07-06-m1-11-f-leveling-path-build-diversity-design.md). Plan: [M1.11F Implementation Plan](superpowers/plans/2026-07-06-m1-11-f-leveling-path-build-diversity.md).
- M1.11G backend-only verification/trust heuristic. Design: [M1.11G Backend Verification and Trust Heuristic](superpowers/specs/2026-07-06-m1-11-g-backend-trust-heuristic-design.md). Plan: [M1.11G Implementation Plan](superpowers/plans/2026-07-06-m1-11-g-backend-trust-heuristic.md). The sidecar remains internal in P1; user-facing calibration waits for P2 logs.

M1.10 redesigned the static report as a player-facing guide site with a fel/void visual direction, individual class/spec guide pages, CoA-style talent trees, tooltip-rich spell/talent links, better role taxonomy, diverse playstyle build selection, and clearer stat/gear/rotation sections. See [M1.10 Guide Site and Report UX Design](superpowers/specs/2026-07-05-m1-10-guide-site-report-ux-design.md).

M1.10A/B, guide information architecture plus asset and tooltip integration, is implemented in the current repo. See [M1.10A/B Design](superpowers/specs/2026-07-05-m1-10-a-b-guide-ia-assets-design.md) and [M1.10A/B Implementation Plan](superpowers/plans/2026-07-05-m1-10-a-b-guide-ia-assets.md).

M1.10C/D, CoA-style static talent trees plus diverse build and core-loop selection, is also implemented. See [M1.10C/D Design](superpowers/specs/2026-07-05-m1-10-c-d-tree-diversity-design.md) and [M1.10C/D Implementation Plan](superpowers/plans/2026-07-05-m1-10-c-d-tree-diversity.md).

M1.10E/F, player-facing role taxonomy plus clearer stat and gear presentation, is implemented. See [M1.10E/F Design](superpowers/specs/2026-07-05-m1-10-e-f-role-gear-stats-design.md) and [M1.10E/F Implementation Plan](superpowers/plans/2026-07-05-m1-10-e-f-role-gear-stats.md).

The CoA Builder tree renderer produces faithful trees across specs; pixel-level builder DOM/screenshot parity was evaluated and judged unnecessary (see [DECISIONS.md](DECISIONS.md) Decision 17). The remaining first-pass areas — backend trust scoring (M1.11G) and rotation reliability (M1.11E) — are intentionally Phase 2-gated on empirical logs.

After M1.11, the Phase 1 continuation (M1.12–M1.20) takes the tool to a public GitHub Pages release
whose numbers model WoW's actual power systems. **M1.12 (public-release UI quick fixes) is
implemented**: icons on nodes and spec cards (AscensionDB hotlink), a select-to-include role filter,
updated disclaimer copy, a header GitHub link, a footer, and removal of leveling-path boilerplate.
M1.13 (fel/void redesign), M1.14 (client DBC data foundation), M1.15 (talent-tree correctness),
M1.16 (analytical player-power model), and M1.17–M1.20 are planned. See
[M1.12–M1.20 Public-Release and Systems-Correctness Roadmap](superpowers/specs/2026-07-06-m1-12-to-m1-20-public-release-roadmap-design.md).
Phase 2 data collection, AscensionLogs/addon calibration, and the Vercel personal
upload/simulation workflow remain the next major cross-phase focus.
