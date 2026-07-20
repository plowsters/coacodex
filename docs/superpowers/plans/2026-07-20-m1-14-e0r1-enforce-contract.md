# M1.14E0R.1 Implementation Plan — Enforce the E0R Contract

> **For agentic workers:** execute task-by-task on branch `m1-14-e0r` (no fresh branch, no squash of pushed history). Each task: write the failing probe test FIRST, run it red, fix until green, commit small. Steps use `- [ ]`.

**Goal:** Make every confirmed E0R adversarial case impossible; convert descriptive guarantees into enforced ones.

**Design:** [E0R.1 spec](../specs/2026-07-20-m1-14-e0r1-enforce-contract-design.md). Amends E0R; does not finish the mechanics model (E1) or merge to `main`.

## Global Constraints

- Probe-first TDD; small contract-focused commits; commit locally throughout; single push after full synthetic + real-client acceptance + green GitHub CI.
- `power_type` stays `raw_only` until a **static** negative anchor is encoded (observation ≠ authorization). `power_type=7` stays withheld.
- No new AscensionDB runtime; only the opt-in image downloader + explicit test fixtures survive.
- Every ceiling policy-bound; strict V3/published/validated/within-budget at every boundary.

---

## Workstream 1 — Recon + policy truth

### Task 1.1: Mandatory recon probes + honest `verified`
**Files:** Modify `coa_client_extract/cli.py` (`mechanics_recon_command`), `coa_client_extract/spell_mechanics.py` (`recon_spell_mechanics` status logic); Test: `tests/test_e0r1_recon_mandatory.py`, update `tests/test_e0r_client.py`.
- [ ] Probe: a recon run whose `join_value_anchors`/`power_type_anchors` are absent, or whose join-pair/negative probes did not run+match, MUST NOT be `verified` (assert `verified` ⟹ `join_pairs` populated for every required join AND `power_type_signed is True`).
- [ ] Fix: `mechanics_recon_command` loads the reviewed anchor set (from the policy/adjudication) and passes `join_value_anchors` + `power_type_anchors`; `recon_spell_mechanics` adds a `verified` precondition that every required probe ran and matched (`join_pairs` unique or reviewed-ambiguous; `power_type_signed is True`), else `review_required`.
- [ ] Green: `pytest tests/test_e0r1_recon_mandatory.py tests/test_e0r_client.py -q`. Commit.

### Task 1.2: Demote `power_type` to `raw_only` pending a static negative anchor
**Files:** Modify `coa_client_extract/data/spell_layout_v2.json` (power_type promotion → `raw_only`; recompute sha), `coa_scraper/config/spell_layout.lock.json`; add a `power_type_static_anchor` field to the anchor set when a client-static negative source is encoded; Test: `tests/test_e0r1_power_type_rawonly.py`.
- [ ] Probe: assert the reviewed policy's `power_type.promotion == "raw_only"` (until a static negative anchor exists) and that `iter_spell_records` never emits a normalized `mechanics.power_type` for it.
- [ ] Fix: flip promotion; recompute policy sha256 + lock (mechanical re-bind pattern; semantic diff limited to that field + digests). Node lock cross-check.
- [ ] Green + commit.

---

## Workstream 2 — Lossless artifacts + client-native icons

### Task 2.1: Emit `description` raw in v3
**Files:** Modify `coa_client_extract/spell_record.py` (`iter_spell_records`); Test: `tests/test_e0r1_description_raw.py`.
- [ ] Probe: a spell row's `raw` MUST contain a `description` entry with `raw_offset` + `resolved` (the client tooltip text), even though it is `raw_only`.
- [ ] Fix: emit the `description` string observation (cell 170) into `raw` (never into `mechanics`). Green + commit.

### Task 2.2: Real projection envelope expansion
**Files:** Modify `coa_client_extract/cli.py` (projection build) or `coa_client_extract/spell_record.py`; Test: `tests/test_e0r1_projection_expansion.py`.
- [ ] Probe: the projection row expands each compact `raw` cell into the specified rich `field_observations` envelope (not a shallow copy of the compact row); cross-child `_expand_compact` + Node consumer accept it.
- [ ] Fix: implement the expansion; keep the full child compact. Green + commit.

### Task 2.3: Icons through promotion + honest coverage
**Files:** Modify `coa_client_extract/spell_icons.py` (`iter_icon_catalog`), `coa_client_extract/cli.py` (icon coverage in manifest/summary); Test: `tests/test_e0r1_icon_promotion.py`.
- [ ] Probe: with a **null** icon index the catalog MUST NOT emit a resolved path for FK 0; it records `asset_status:"unavailable"` + `readiness:"unavailable"` and the manifest reports **zero** resolved-icon coverage. A resolved path requires the join + components to be promotion-eligible via `make_string_join`.
- [ ] Fix: route icon resolution through `make_string_join` + promotion; compute real coverage counts. Green + commit.

### Task 2.4: Wire the client icon catalog through the production guide writer
**Files:** Modify `coa_meta/guide_builder.py` callers + the production guide writer (`coa_meta/guide_writer.py` or equivalent) to accept/pass `icon_catalog`; Test: `tests/test_e0r1_guide_icon_catalog.py`.
- [ ] Probe: the production guide-writing entry point accepts an `icon_catalog` and renders `client_icon`/placeholder (never a DB hotlink). Green + commit.

### Task 2.5: Regenerate or delete stale generated guide/site output
**Files:** whichever committed generated pages/catalogs carry `db.ascension.gg`; `.gitignore`.
- [ ] Audit tracked generated output with `db.ascension.gg`; regenerate client-native or `git rm` (untrack) disposable generated pages + the DB tooltip catalog. Test: `tests/test_e0r1_no_stale_db_output.py` asserts no tracked *generated* artifact contains `db.ascension.gg`. Green + commit.

---

## Workstream 3 — Trust boundary + real transaction

### Task 3.1: Node candidate validator does semantics, not transport
**Files:** Modify `coa_scraper/scripts/lib/generation.mjs` (`validateCandidateByPath`), reuse `mechanics-projection.mjs` (`verifyRowAgainstPolicy`, `assertPolicyLock`); Test: `coa_scraper/tests/e0r1-candidate-trust.test.mjs`.
- [ ] Probe: an **empty** V3 candidate FAILS; a candidate missing a required child FAILS; a bad `candidate_trust_sha256` FAILS; a row whose populated mechanic lacks a raw observation FAILS; a policy child not matching the lock FAILS.
- [ ] Fix: `validateCandidateByPath` checks the required-child registry, recomputes `candidate_trust_sha256`, runs `assertPolicyLock` against the staged policy child, and runs row biconditionals over **mechanics ∪ raw** (not just `row.raw`). Green + commit.

### Task 3.2: Both resolvers require strict published state
**Files:** Modify `coa_client_extract/publish.py` (`resolve_active_generation`), `coa_scraper/scripts/lib/generation.mjs` (`resolveGeneration`); Test: `tests/test_e0r1_resolver_strict.py`, `coa_scraper/tests/e0r1-resolver-strict.test.mjs`.
- [ ] Probe: a manifest-v2, or v3 with `publication_state!="published"`, missing/invalid `candidate_trust_sha256`, `validation` not both-true, or `budget.within_budget!=true`, or missing a required child, is REJECTED by BOTH resolvers.
- [ ] Fix: enforce strict `manifest-v3` + published + trust digest + validation + budget + required registry. Green + commit.

### Task 3.3: Complete Python cross-child
**Files:** Modify `coa_client_extract/publish.py` (`_cross_child`, `_icon_bundle`); Test: `tests/test_e0r1_cross_child.py`.
- [ ] Probe: mismatched icon id/path FAILS; a trailing extra icon row FAILS; a bundle whose contents/paths/hash/internal-manifest disagree FAILS.
- [ ] Fix: extend cross-child to icon id/path agreement + reject trailing/extra; validate bundle contents. Green + commit.

### Task 3.4: True transaction under late failure + concurrency
**Files:** Modify `coa_client_extract/cli.py` (stage parity BEFORE publish; summary cannot fail publication), `coa_client_extract/publish.py` (hold lock predecessor-read→replace with revalidation); Test: `tests/test_e0r1_transaction.py`.
- [ ] Probe: a parity/summary failure leaves the previous pointer untouched; two concurrent publishers cannot last-writer-win (predecessor revalidated under the lock).
- [ ] Fix: move parity into the candidate stage; acquire the lock before `_predecessor()` and revalidate before replace. Green + commit.

---

## Workstream 4 — True streaming + policy-bound budgets

### Task 4.1: Stream the producer→writer path
**Files:** Modify `coa_client_extract/cli.py` (`regenerate`), `coa_client_extract/publish.py` (`add_jsonl` streaming write + incremental sha/count); Test: `tests/test_e0r1_streaming.py` (assert no whole-table list is materialized — e.g. a generator is consumed once; peak-RSS check on a synthetic large table).
- [ ] Probe + fix: stream rows to disk with incremental hashing/record-count; avoid the projection/icon full arrays (two-pass or a spooled index). Green + commit.

### Task 4.2: Stream the Node validator + mechanics consumer
**Files:** Modify `coa_scraper/scripts/lib/generation.mjs`, `mechanics-projection.mjs`, `build-mechanics-artifacts.mjs`; Test: `coa_scraper/tests/e0r1-streaming.test.mjs`.
- [ ] Probe + fix: line-by-line child validation + projection consumption with incremental hashing (no whole-child `readFileSync`+split into a retained array). Green + commit.

### Task 4.3: Policy-bound per-child + whole-generation budgets + pinned env
**Files:** Modify `coa_client_extract/data/spell_layout_v2.json` (budget block), `coa_client_extract/spell_mechanics.py`/`publish.py` (read ceilings from policy; enforce per-child), `coa_client_extract/manifest.py` (record `benchmark_env`); Test: `tests/test_e0r1_budget_policy_bound.py`.
- [ ] Probe: a child over the per-child ceiling FAILS even if the whole is under; ceilings come from the policy; the manifest records a reproducible `benchmark_env`. Green + commit.

---

## Workstream 5 — Finish the sunset + honest interlock

### Task 5.1: Delete runtime AscensionDB
**Files:** `git rm` `coa_scraper/scripts/lib/ascensiondb.mjs` (+ cache), `build-item-artifacts.mjs` (or strip `ascension_db`), remove `--db-tooltips` from `coa_meta/cli.py`, make `coa_meta/guide_tooltips.py` client-native (drop `db_rows` preference + "high" name-match), README; keep the opt-in downloader + test fixtures; Test: `tests/test_e0r1_sunset_complete.py`, `coa_scraper/tests/no-ascensiondb.test.mjs` (extend).
- [ ] Probe: no runtime module imports `ascensiondb`; `guide_tooltips` never emits an `ascension_db` source or a DB URL; no CLI exposes a DB input. Green + commit.

### Task 5.2: Strict readiness invariants
**Files:** Modify `coa_meta/mechanics.py` (`_validate_field_readiness`); Test: `tests/test_e0r1_readiness_strict.py`.
- [ ] Probe: reject `available`+null, `verified_empty`+`not_extracted`, `unavailable`+`proven_empty` (and the reason⇔status coupling). Green + commit.

### Task 5.3: numberOrNull + drop spellRows
**Files:** Modify `coa_scraper/scripts/build-mechanics-artifacts.mjs`; Test: extend `coa_scraper/tests/mechanics-v2.test.mjs`.
- [ ] Probe: `numberOrNull(null)===null`; `buildCanonicalMechanics` signature has no `spellRows`. Green + commit.

### Task 5.4: Separate heuristic mode; canonical reporting returns blocked
**Files:** Modify `coa_meta/reporting.py` (no auto `allow_heuristic`; canonical returns an explicit `blocked` rotation section), add a default-off heuristic command/mode; `coa_meta/simulation.py` (tag `source:"heuristic"`); Test: `tests/test_e0r1_reporting_blocked.py`.
- [ ] Probe: canonical rotation over unready actions returns a `blocked` section (not a silently-heuristic rotation); heuristic is a distinct opt-in tagged `heuristic`. Green + commit.

---

## Workstream 6 — Real CI + binding acceptance

### Task 6.1: Real CI + clean-env packaging
**Files:** Modify `.github/workflows/ci.yml` (trigger on branch push + PR; `python -m pytest` + `npm test`; run the probe tests), `pyproject.toml` (clean-env collection: make `pytest -q` importable — add a `conftest.py`/`rootdir` sys.path shim or package the fixtures); Test: `tests/test_e0r1_clean_env_collect.py` (asserts a clean `pytest -q` collects).
- [ ] Probe + fix. Green + commit.

### Task 6.2: Binding acceptance writer
**Files:** Modify `coa_client_extract/cli.py` (`write_acceptance_summary` + `acceptance-summary` subcommand); Test: `tests/test_e0r1_acceptance_binding.py`.
- [ ] Probe: the summary hashes the actual recon report (and asserts its `status=="verified"`), reads strict-V3/published/validation/budget from the resolved manifest (not caller strings), and records icon/readiness/source **coverage** counts + the network-trap result.
- [ ] Fix + green + commit.

### Task 6.3: Real-client acceptance + push
- [ ] Stop the launcher; re-run recon (must be `verified` post-rebind); run the full acceptance (regenerate + measured pointer-only build-mechanics) binding the recon report; confirm strict-V3 published + within budget + real coverage.
- [ ] Commit the acceptance summary; push `m1-14-e0r`; confirm the GitHub CI check is green on the branch (open the PR against `main` to trigger it — do NOT merge).

---

## Self-Review

Spec coverage: every P1 + the misc items map to a task. Probe-first: each task names its failing probe. Type consistency: reuses E0R interfaces (`verifyRowAgainstPolicy`, `assertPolicyLock`, `make_string_join`, `three_part_budget`, readiness contracts). No E1 work; no `main` merge.
