# Target Architecture

The architecture follows the separation used by mature retail WoW tools:

- SimulationCraft separates game data, profiles, action priority lists, class modules, simulation engine, CLI, and reports.
- The SimulationCraft addon collects character state in game and exports a text profile rather than simulating in game.
- Raidbots acts as a user-facing batch/run frontend over SimulationCraft-style profiles and simulations.
- WoWAnalyzer is a log-analysis and feedback application, not a build legality engine or simulator.

CoA Meta Analyzer should mirror those boundaries while adapting them to Ascension CoA data.

## System Boundary

```text
Ascension CoA builder web app
  -> scraper/capture module
  -> payload extraction module
  -> normalized data module
  -> analyzer/schema reports
  -> build legality and graph module
  -> theory scoring module
  -> APL/rotation module
  -> meta report module

WoW 3.3.5 client
  -> CoADataLogger addon and/or WoWCombatLog.txt
  -> log ingestion module
  -> empirical metrics store
  -> calibration module
  -> data-driven reports

Future simulator
  -> ability model
  -> combat state engine
  -> APL interpreter
  -> DPS/stat weight/rotation search reports
```

## Data Flow

### Builder Data Flow

1. `scrape-coa-network.mjs` captures HAR, raw assets, snapshots, and runtime dumps.
2. `extract-coa-builder-payload.mjs` extracts the Next Flight payload containing builder data.
3. `export-coa-normalized.mjs` converts builder payload records into normalized JSONL and JSON artifacts.
4. Analyzer scripts produce schema and coverage reports.
5. Optimizer modules load only normalized data, not HTML, HAR, Playwright state, or web runtime dumps.

This is intentional. Web scraping is brittle and should be isolated from build legality and scoring.

### Theorycraft Flow

1. Load normalized classes, entries, and essence caps.
2. Validate schema and capture provenance.
3. Build a graph of talents/abilities and prerequisites.
4. Generate legal builds under AE/TE, level, and prerequisite constraints.
5. Score builds using encounter and spec profiles.
6. Generate editable APL scaffolds for top builds.
7. Emit projected meta reports with confidence labels.

### Data-Driven Flow

1. Collect in-game sessions with the addon and/or built-in combat logs.
2. Convert logs into a common event schema.
3. Segment fights and attach character/build snapshots.
4. Derive empirical metrics.
5. Calibrate theory weights and mechanics assumptions.
6. Emit empirical or blended reports with sample size and uncertainty.

## Confidence Labels

Every ranking must state its evidence source:

- `theorycraft`: based on builder data, tooltip parsing, graph structure, and explicit assumptions.
- `simulated`: based on an event-driven simulator under stated assumptions.
- `empirical`: based on logs/addon data.
- `blended`: simulation or theory corrected by empirical data.

Raw DPS should not be shown in Phase 1. Phase 1 uses a projected DPS index. Raw DPS is acceptable only for empirical logs or Phase 3 simulation output, and it must be labeled by source.

## Current Prototype Boundaries

`coa_optimizer_extensible.py` currently contains several modules in one file:

- domain DTOs
- repository
- build legality
- scoring
- optimizer search
- APL generation
- combat log adapters
- graph exporters
- CLI

That is useful for prototyping, but not the target architecture. Phase 1 should split those concerns into a package with narrow modules and tests.

## License and Source Reuse Policy

Retail tool source code can inform architecture, interfaces, and test strategy. Direct code lifting must be explicit and license-reviewed.

- SimulationCraft is GPL-3.0 with additional bundled third-party licenses. Copying engine code may require this project to become GPL-compatible.
- WoWAnalyzer is AGPL-3.0. Copying code can impose network-use source distribution obligations.
- SimC addon code is useful as an exporter pattern, but compatibility with 3.3.5 and license obligations must be checked before reuse.

Default policy: model architecture and concepts first. Copy source code only after adding a project license decision and attribution plan.

## Production Definition

A module is production-ready when:

- Its inputs and outputs are versioned and documented.
- It has tests covering normal cases and known failure modes.
- It reports provenance and confidence.
- It can be run by command or API without editing source.
- It preserves raw source data for audit.
- It avoids hidden coupling to unrelated modules.

