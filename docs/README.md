# CoA Meta Analyzer Documentation

This directory documents the intended architecture and release roadmap for the Conquest of Azeroth meta analyzer. The current repository contains prototype scripts and captured data; these docs define how those pieces should become production-ready modules.

## Document Map

- [ROADMAP.md](ROADMAP.md) defines phases, milestones, release gates, and exit criteria.
- [ARCHITECTURE.md](ARCHITECTURE.md) defines the target system boundaries and data flow.
- [MODULES.md](MODULES.md) defines each module's responsibility, inputs, outputs, and current code ownership.
- [NEXT_STEPS_DATA_COLLECTION.md](NEXT_STEPS_DATA_COLLECTION.md) lists the data the user needs to collect for each phase.
- [RETAIL_TOOLING_REFERENCES.md](RETAIL_TOOLING_REFERENCES.md) summarizes retail WoW tooling patterns this project should model.
- [DECISIONS.md](DECISIONS.md) records intentional architecture decisions so future agents can distinguish them from accidental prototype constraints.
- [ASSESSMENT.md](ASSESSMENT.md) assesses the prior conversation and identifies corrections or missing design work.

## Current Repository Snapshot

The current codebase has three prototype areas:

- `coa_scraper/`: Playwright/HAR capture, Next Flight payload extraction, normalization scripts, and captured reports/dist artifacts.
- `coa_optimizer_extensible.py` and `coa_graph_optimizer.py`: prototype optimizer scripts with repository, legality, scoring, rotation, graph export, and log parsing concepts mostly contained in one file.
- `CoADataLogger/`: minimal WotLK 3.3.5 addon scaffold that captures player-sourced combat events and basic snapshots to SavedVariables.

The target architecture keeps those concerns separate. Scrapers produce versioned structured data. Analyzers validate and enrich it. Optimizers consume only normalized data. Addons and logs provide empirical calibration data. Web frontends display reports and collect user inputs, but do not own simulation logic.

