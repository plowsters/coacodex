# M1.14 E0R.3 — close the final E0R.2 review blockers

> **This file is the canonical execution record for E0R.3** (the MCP tracker is offline). Unlike the
> E0R.1/E0R.2 trackers it is not a bite-sized task plan: the round is three findings, executed
> probe-first in one session, and a plan written after the fact would be fiction. What it records is
> what was found, what was done, what was decided, and where the work deviated from the report.

**Goal:** Close the three findings the external review raised against E0R.2 — one merge-blocking
packaging defect and two handoff/documentation defects — so PR #1 can merge on evidence.

**Baseline:** branch `m1-14-e0r` at `6eb5a5e`, 1088 Python + 343 Node green, PR #1 draft/MERGEABLE with
CI green on both the push and `pull_request` runs. Published generation
`069a9b18af264941a5386c84a0b9d89a` under contract revision `e0r-v3`, 58.27% of ceiling.

## Global Constraints

- **Branch:** `m1-14-e0r`. No history rewrite. **Do NOT merge PR #1. Do NOT start E1.**
- **Commits:** explicit file paths only — **NEVER `git add -A`**. One finding per commit.
- **Method:** probe-first TDD. Every case is a failing test *before* its fix.
- **EVERY COMMIT LEAVES BOTH FULL SUITES GREEN.**
- **User directive:** *"add these revisions to v3 rather than creating a new versioned system."* Honoured
  trivially and verified rather than assumed: **none of the three findings touches the generation
  contract.** No revision file was edited, no revision was minted, `index.json` is untouched, and all
  three digests re-verify (`e0r-v1` `708a00e2…`, `e0r-v2` `7f256a35…`, `e0r-v3` `d2180203…`, current =
  `e0r-v3`). The published generation stays valid, so — as the reviewer said — **no real-client
  regeneration is required**. `git diff --name-only 6eb5a5e..HEAD -- 'coa_client_extract/data/**'
  'reports/**'` is empty.
- **Anchor-evidence precedence:** unchanged, verbatim from E0R. It is load-bearing in this round: it is
  what makes the three unresolved joins unresolvable rather than merely unresolved.
- **Suites:** `pytest -q` from the repo root (CI runs **bare** `pytest`); `npm --prefix coa_scraper test`.

## Execution status

| Finding | Status | Evidence |
|---|---|---|
| **P1 — the built wheel omits the generation-contract registry** | **done** | `da51727` — reproduced from a clean `git archive` build installed into a fresh venv outside the repo (`FileNotFoundError` on `data/generation_contracts/index.json`); fixed with recursive `data/**/*.json`; gated by a tracked-tree invariant test **and** a new CI `wheel` job |
| **P2 — the E1 handoff contradicts the realized recon result** | **done** | `dcb1751` — the three `reviewed_ambiguous` joins are inherited as `unavailable` and assigned to **M1.14G**; gate reads the committed acceptance record so it fails in both directions |
| **P2 — active operator documentation resurrects AscensionDB** | **done** | `1fdd62f` — 32 active docs gated by a marker rule; 10 files corrected; negative control proves the gate can fail |

Suites after each commit: **1091 → 1098 → 1105 Python**, 343 Node, `git diff --check` clean.

## What each finding actually was

### P1 — one defect, two instances, invisible to every existing gate

`coa_client_extract = ["data/*.json"]` matches one directory level. `data/generation_contracts/` — the
hash-pinned registry `coa_client_extract.contracts` loads by absolute package path at import — was in no
wheel ever built. `coa_meta/data/live_sanity_watchlist.json`, read by `coa_meta.backend_trust`, was
omitted by the same mechanism.

Why nothing caught it: `pip install -e .` puts the whole source tree on `sys.path`, so an omitted data
file still loads in development **and** in CI's `test` job. This is the same shape as E0R.2's T8.3 lesson
one level further out — a clean venv is not a clean checkout, and a clean checkout is not a built
distribution.

Two gates, because neither suffices alone: a pattern-level test holding the declared globs to the
**tracked** `data/` tree in both packages (so a file that must not ship has to be excluded in the open),
and a CI `wheel` job that builds, installs into a clean venv with no source tree, and runs
`scripts/wheel_smoke.py` from `runner.temp`. The smoke script refuses to run against the checkout rather
than passing vacuously — verified by tripping that guard deliberately.

### P2 — the E1 handoff

E0R's design said it pulled all four join adjudications forward, so E1 would not carry join discovery.
The realized run promoted **one** (`spell_icon_id` → cell 133). `casting_time_index`, `duration_index`,
and `range_index` came back `reviewed_ambiguous` (30 / 34 / 14 FK-validity candidate columns).

Of the reviewer's two options, **the second was chosen and the first is not choosable**: acquiring
genuinely independent evidence requires a value anchor — one known spell's ms or yards from an admissible
source — and under the precedence in force none exists. Owner is **M1.14G**, the first milestone that
establishes an instrument which could produce one.

### P2 — active documentation

The runtime sunset was enforced and proven; nothing read the docs. So the docs still told readers to run
`--db-tooltips` and `npm run pipeline:m1.8`, listed artifacts with no producer, documented a
`db_enrichment` field with no writer, and left Decision 15 at `Status: accepted` for a model that had
been deleted. `docs/README.md` is also the distribution's readme, so it shipped in package metadata.

## Execution notes (deviations, self-corrections, and decisions)

- **My first docs probe was wrong twice, and passed for the wrong reason.** (1) `git ls-files "docs/*.md"`
  returns `docs/superpowers/**` too — git pathspecs are not shell globs, `*` crosses `/` — so the gate was
  scanning 60+ historical design docs. (2) Line-level marker matching cannot see a marker that landed on
  the next line of a wrapped markdown sentence. Fixed by filtering paths explicitly and scoping markers to
  **prose blocks** (a paragraph, or a single list item with its continuations), with list items cut apart
  so a marked bullet cannot exempt the unmarked bullet beside it. Then verified the gate can fail at all:
  an unmarked mention injected into `ARCHITECTURE.md` fails it, a marked one passes.
- **Commands and names are gated differently, on purpose.** A removed CLI flag or npm script gets no
  marker exemption anywhere in an active doc — a command reads as runnable whatever the prose says, and a
  reader who copies it gets an error, not a history lesson. Removed *artifact and field names* ride the
  marker rule, because a schema doc naming `db_enrichment` in order to say it is gone is doing its job. A
  companion test checks each forbidden command really is absent from the runtime, so the blacklist tracks
  the code instead of outliving it.
- **`docs/superpowers/**` is excluded by construction**, not by exception: every file there is a dated
  design, plan, or tracker, historical the moment it is written. Scrubbing AscensionDB from them would
  destroy the record of why it was removed. This matches the reviewer's own rule.
- **I over-corrected `docs/data/normalized-schema.md` and caught it by probing the artifact.** My first
  edit deleted "DB tooltip" from the `availability` description. But
  `availability.db_tooltip_required_level` genuinely **does** survive in emitted records (written by
  `lib/source-level.mjs`, now always `null`); only `db_enrichment` is gone. Deleting the mention would
  have made the doc wrong in the other direction. The doc now states exactly that: the key survives for
  shape compatibility, is always null, and can never contribute to `effective_required_level`.
- **`docs/data/item-schema.md` has no producer at all**, which the review did not name. M1.9 sourced item
  records from AscensionDB power payloads; that pipeline is deleted and no client-native item extraction
  replaced it (E0R explicitly deferred item extraction). The doc now says it describes a target shape for
  a later milestone, not an artifact the repo builds.
- **Recursive globs over two more literal paths.** `data/**/*.json` needs setuptools ≥ 62.3 and the build
  requires ≥ 68; verified empirically rather than trusted — the rebuilt wheel carries all **23** tracked
  data files, and the CI job re-proves it every run. Naming the two offending directories would have fixed
  today's defect and left the next nested directory free to reintroduce it.
- **`test_pyproject_declares_package_data_and_console_script` was narrowed, not weakened.** It asserted
  three glob strings were present — exactly the check that a nested directory slips past. The tracked-tree
  invariant test strictly supersedes those assertions.
- **The E1 handoff gate reads the record, not a frozen list.** It derives the ambiguous set from
  `recon_report.join_pairs[*].adjudication` in the committed acceptance record, so if a later recon
  promotes one of the three, the test fails and forces the docs to be corrected in **that** direction too.
- **Quoting a falsified claim trips its own gate.** The withdrawal in the E0R design paraphrases rather
  than quotes, so a grep for the false sentence returns nothing anywhere in the three docs.

## Flagged for the user (an owner decision, not an implementer's)

Assigning the three joins to M1.14G does **not** by itself make them resolvable. G's instrument is a
controlled client, and the anchor-evidence precedence explicitly excludes **runtime behavior**. So a
measured cast time from a controlled client becomes admissible only if you extend the precedence to admit
it, under stated conditions (a controlled local client, a spell whose identity is hash-bound, a
reproducible read). Both the design and the roadmap say this rather than quietly assuming G will manage —
which is the exact failure this round is fixing one level up. Until then the three fields remain honestly
unavailable, and the guide cannot present cast time, duration, or range at all.

## Out of scope, recorded deliberately

- **Marking PR #1 ready / merging.** The reviewer's checklist ends with "mark PR #1 ready and merge it";
  the standing instruction is that the user reviews and merges. Left to them, unchanged.
- **Rewriting the rest of `docs/README.md`'s milestone log.** The stale-as-current claims were corrected
  and the log is now explicitly historical under its own heading. A full rewrite is not this round's job.
- **Client-native item extraction.** Still deferred; `item-schema.md` now says so instead of implying a
  producer exists.
- **The `db_tooltip_required_level` key itself.** It survives in `coa-normalized-v1` for shape
  compatibility and is always null. Removing it is a schema change with consumer reach — not a
  documentation fix, and not worth a migration while it is harmless and documented.
