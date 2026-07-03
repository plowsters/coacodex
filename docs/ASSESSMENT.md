# Assessment of Prior Conversation

This assessment reviews the earlier discussion about optimizing Stalker Venomancer, extending the optimizer, and estimating a projected CoA meta.

## Accurate and Useful Points

The earlier conversation was directionally sound on these points:

- Separating scraping, payload extraction, normalization, optimization, rotation generation, and log ingestion is the right architecture.
- The current scraper pipeline is a good foundation because it already captures HAR/raw assets, extracts the Next Flight builder payload, normalizes records, and emits reports.
- `coa_entries.jsonl` is the correct optimizer input. The optimizer should not scrape the web UI directly.
- Retail WoW tooling is a useful model: SimC-style profile input, event-driven simulation, APL priority lists, cloud/UI batch workflows, and log-analysis feedback are separate concerns.
- A theorycrafting tool can estimate a projected meta from structured abilities and talents, but it cannot truthfully produce definitive DPS rankings without empirical data or a calibrated simulator.
- A projected DPS index is more honest than raw DPS during the theorycraft phase.
- ML is not needed early. Deterministic parsing, legality, scoring, APL generation, and calibration should come first.
- Data-driven calibration should come from combat logs and addon snapshots, not damage meter UI summaries.

## Incomplete or Overstated Points

The earlier conversation needs these corrections:

- The optimizer scaffold is not production-ready. It is a useful prototype monolith that needs package boundaries, tests, schema validation, and reproducible reports.
- The phrase "can be definitive for legal build graph construction" is too strong until legality is validated against official builder UI examples, especially for multi-rank nodes, starting nodes, tab gates, and any hidden rules.
- The custom addon scaffold is minimal. It does not yet capture enough metadata for robust data-driven rankings, especially pet attribution, fight segmentation, selected CoA build IDs, and resource events.
- The prior answer mentioned using Recount, Skada, and Details as useful references. They can help cross-check results, but this project should treat raw combat logs and SavedVariables as primary sources.
- The Stalker profile in the prototype is hand-tuned. Production scoring needs data-driven profile definitions and explanation fields.
- Rotation scaffolds are not optimal rotations. They are baseline APLs that need simulation or empirical validation.
- "Compare simulated DPS numbers" should be deferred until Phase 3. Phase 1 can compare projected indexes, not simulated DPS.
- Code-lifting from retail tools needs license review. SimulationCraft and WoWAnalyzer are open source, but their licenses are not neutral drop-in choices for this project.

## Architectural Revisions Needed

### Split Prototype Scripts Into Modules

Current state:

- `coa_optimizer_extensible.py` mixes domain models, loading, legality, scoring, optimization, APL generation, log parsing, graph exports, and CLI.

Required revision:

- Split the script into importable package modules with tests.
- Keep the CLI thin.
- Keep raw scraping and normalized data loading separate.

### Add Versioned Data Contracts

Current state:

- Normalized records are useful, but their schema is implicit.

Required revision:

- Add explicit schema versions and validation.
- Separate source fields from inferred fields.
- Add capture provenance and checksums.

### Add Legal Build Ground Truth

Current state:

- Build legality is inferred from normalized fields.

Required revision:

- Collect official builder UI examples and validate the legality engine against them.
- Explain legality failures with exact rule names.

### Add Confidence and Provenance Everywhere

Current state:

- The prototype can score and explain some builds, but confidence is not formalized.

Required revision:

- Every score, build, rotation, and ranking needs source, confidence, assumptions, and uncertainty.

### Make Addon and Log Data Phase 2, Not Phase 1

Current state:

- The optimizer can ingest logs, but the log path is a scaffold.

Required revision:

- Build a real event schema, fight segmenter, empirical store, and calibration engine before claiming data-driven recommendations.

### Keep Simulation Separate

Current state:

- The conversation correctly identified simulation as the next major capability, but it should not be bundled into Phase 1.

Required revision:

- Build simulation as Phase 3 after stable domain data, APLs, and empirical validation exist.

## Thoroughness Assessment

The prior conversation was useful as a strategic direction, but it mixed architecture, prototype implementation, user advice, and future simulation ideas in one flow. The new roadmap separates those into phases and modules so future agents can work incrementally.

Strong parts:

- Correct high-level separation of concerns.
- Honest caveat that theorycraft-only rankings are projections.
- Good instinct to model SimC-style APLs.
- Good instinct to use combat logs and SavedVariables for calibration.

Weak parts:

- Too much implied confidence in legality before UI validation.
- Not enough emphasis on schema versioning and provenance.
- Not enough license caution around copying retail tool source.
- No explicit production release gates.
- No clear split between theorycraft, empirical calibration, and simulation releases.

## Recommended Next Action

Start Phase 1 Milestone 1.1 and Milestone 1.2 together:

1. Add capture manifests and schema validation to the current scraper/normalizer pipeline.
2. Freeze the normalized data contract.
3. Add tests around the current Vol'Jin Alpha artifacts.
4. Only then split the optimizer into package modules.

