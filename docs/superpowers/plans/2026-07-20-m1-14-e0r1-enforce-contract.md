# M1.14E0R.1 Implementation Plan — Enforce the E0R Contract

> **For agentic workers:** execute task-by-task on branch `m1-14-e0r` (no fresh branch, no squash of pushed history). Each task: write the failing probe test FIRST, run it red, fix until green, commit small. Steps use `- [ ]`.

**Goal:** Make every confirmed E0R adversarial case impossible; convert descriptive guarantees into enforced ones.

**Design:** [E0R.1 spec](../specs/2026-07-20-m1-14-e0r1-enforce-contract-design.md). Amends E0R; does not finish the mechanics model (E1) or merge to `main`.

## Execution status (updated 2026-07-21; this file is the task tracker — the MCP tracker is offline)

| Task | Status | Commit |
|------|--------|--------|
| T1.1–T1.4 | done | `47d7c14`, `0320ae3`, `2df6b58`, `488e4f6` |
| T2.1–T2.5 | done | `5021d68`, `e62f480`, `ac4f95c`, `b7923bd`, `e53a64b` |
| T3.0, T3.1, T3.1b | done | `c65acaf`, `55ac22a`, `ab50866` |
| T3.2, T3.3, T3.4 | done | `adb942a`, `372efa3`, `cef2a32` |
| T4.1 | done | `d83a91f` |
| T4.2 | done | `9ce7d9e` |
| **T4.3** | **next** | policy-bound ceilings + benchmark_env |
| T5.1–T5.4, T6.1–T6.3 | open | — |

- Deferred inside T3.1b/T3.3 (documented): deep icon-bundle **tar contents/internal-manifest/hash** verification — no converter emits a `converted` bundle yet, so only the converted→bundle-required guard + id/path agreement are enforced; revisit at the conversion milestone.
- Known pre-existing client-tier failures (triaged 2026-07-21, none from E0R.1 WS3/WS4 work): real regenerate breaches `elapsed_s=600` (~700s; T4.3's driving evidence); `tests/test_e0_client_recon.py` ×2 are stale E0-era tests superseded by `test_e0r_client.py` (migrate/retire in T6.2/T6.3).

## Global Constraints

- Probe-first TDD; small contract-focused commits; commit locally throughout; single push after full synthetic + real-client acceptance + green GitHub CI.
- `power_type` stays `raw_only` until a **static** negative anchor is encoded (observation ≠ authorization). `power_type=7` stays withheld.
- No new AscensionDB runtime; only the opt-in image downloader + explicit test fixtures survive.
- Every ceiling policy-bound; strict V3/published/validated/within-budget at every boundary.

---

## Workstream 1 — Recon + policy truth

### Task 1.1: Mandatory probes + a self-consistent `verified` state machine
**Files:** Modify `coa_client_extract/cli.py` (`mechanics_recon_command`), `coa_client_extract/spell_mechanics.py` (`recon_spell_mechanics` status logic + always-run probes); Test: `tests/test_e0r1_recon_mandatory.py`.
- [x] Probe A: every required join (`cast_time_ms`, `duration_ms`, `range_min_yd`, `range_max_yd`, `spell_icon_id`) AND the `power_type` anchors are probed on every recon run — the report records each attempt + its evidence (matches/coverage/candidates), never skipped.
- [x] Probe B: a **unique** join/anchor discovery that the policy has NOT adopted (cell/promotion) ⇒ `review_required`, NOT `verified`.
- [x] Probe C: `power_type` signedness is required for `verified` **only if** the policy claims a verified `power_type` interpretation; when the policy declares `power_type` interpretation `unproven`/`raw_only`, recon may be `verified` while recording `no_static_anchor` (no `power_type_signed is True` requirement).
- [x] Probe D: a genuinely ambiguous join may stay null/`raw_only`, but the report must carry its attempted-discovery evidence.
- [x] Fix: `mechanics_recon_command` loads the reviewed anchors/value-anchors and passes `join_value_anchors` + `power_type_anchors` for ALL four joins; `recon_spell_mechanics` runs every probe unconditionally and computes `status` from the state machine above.
- [x] Green: `pytest tests/test_e0r1_recon_mandatory.py -q`. Commit.

### Task 1.2: Adjudicate the four discovered join cells into the reviewed policy
**Files:** Modify `coa_client_extract/data/spell_layout_v2.json` (author unique+matched join index cells; recompute sha), `coa_scraper/config/spell_layout.lock.json`; Test: `tests/test_e0r1_join_adjudication.py`, update `tests/test_e0r_client.py`.
- [x] Probe: after adjudication, recon `verified` requires every join to be either (a) adjudicated with the discovered unique cell + matching promotion, or (b) recorded ambiguous (null) with evidence; a unique-but-unadopted join ⇒ `review_required`.
- [x] Fix: run recon against the real client, author the uniquely-discovered join index cells into the policy (ambiguous stay null with recorded evidence), recompute policy sha256 + lock (mechanical re-bind pattern; Node lock cross-check). Update `test_e0r_client` to the corrected expectation.
- [x] Green + commit.

### Task 1.3: Demote `power_type` — promotion AND interpretation — with withheld decode
**Files:** Modify `coa_client_extract/data/spell_layout_v2.json` (`power_type`: promotion `raw_only`, interpretation not `verified`; recompute sha), `coa_scraper/config/spell_layout.lock.json`, `coa_client_extract/spell_record.py` (emit `decoded_reason: "proof_withheld"`, no normalized value); Test: `tests/test_e0r1_power_type_rawonly.py`.
- [x] Probe: the policy's `power_type` promotion is `raw_only` AND interpretation is NOT `verified`; `iter_spell_records` retains the raw `u32`, withholds the decoded value with `decoded_reason: "proof_withheld"`, and emits no normalized `mechanics.power_type`.
- [x] Fix: flip both facets; withhold decode; recompute sha + lock.
- [x] Green + commit.

### Task 1.4: Canonical mechanics never backfill a withheld power type from Builder inferred
**Files:** Modify `coa_scraper/scripts/build-mechanics-artifacts.mjs` / `coa_scraper/scripts/lib/mechanics-candidates.mjs` (an `inferred`-tier `power_type` cannot become the canonical value; expose `null` + `unavailable`/`no_static_anchor`; any inferred power type is diagnostic/heuristic-tagged only); Test: `coa_scraper/tests/e0r1-power-type-not-backfilled.test.mjs`.
- [x] Probe: with a withheld client `power_type`, the canonical mechanics row's `power_type` is `null` (with readiness `no_static_anchor`/`unavailable`), NOT the Builder `resources`-derived value; any inferred value appears only in a diagnostic field tagged `heuristic`.
- [x] Fix + green + commit.

---

## Workstream 2 — Lossless artifacts + client-native icons

### Task 2.1: Emit `description` raw in v3
**Files:** Modify `coa_client_extract/spell_record.py` (`iter_spell_records`); Test: `tests/test_e0r1_description_raw.py`.
- [x] Probe: a spell row's `raw` MUST contain a `description` entry with `raw_offset` + `resolved` (the client tooltip text), even though it is `raw_only`.
- [x] Fix: emit the `description` string observation (cell 170) into `raw` (never into `mechanics`). Green + commit.

### Task 2.2: Real projection envelope expansion
**Files:** Modify `coa_client_extract/cli.py` (projection build) or `coa_client_extract/spell_record.py`; Test: `tests/test_e0r1_projection_expansion.py`.
- [x] Probe: the projection row expands each compact `raw` cell into the specified rich `field_observations` envelope (not a shallow copy of the compact row); cross-child `_expand_compact` + Node consumer accept it.
- [x] Fix: implement the expansion; keep the full child compact. Green + commit.

### Task 2.3: Icons through promotion + honest coverage (icon join adjudicated in WS1)
**Files:** Modify `coa_client_extract/spell_icons.py` (`iter_icon_catalog`), `coa_client_extract/cli.py` (icon coverage in manifest/summary); Test: `tests/test_e0r1_icon_promotion.py`.
- [x] Probe: an unresolved icon join row is `asset_status: "placeholder"` (a valid `ICON_ASSET_STATUSES` value) with `readiness: "unavailable"` — NOT `asset_status:"unavailable"` (invalid) and NOT a resolved FK-0 path; `"missing"` is reserved for a proven path whose client asset is absent. A resolved path requires the join + components promotion-eligible via `make_string_join`. The manifest records real resolved-icon **coverage** counts; zero coverage is emitted only when the WS1 icon probe genuinely stayed ambiguous (proven in the committed recon report).
- [x] Fix: route icon resolution through `make_string_join` + promotion; if WS1 adjudicated the icon index cell, resolve real paths; else emit placeholders + zero coverage. Green + commit.

### Task 2.4: Wire the client icon catalog through the production guide writer
**Files:** Modify `coa_meta/guide_builder.py` callers + the production guide writer (`coa_meta/guide_writer.py` or equivalent) to accept/pass `icon_catalog`; Test: `tests/test_e0r1_guide_icon_catalog.py`.
- [x] Probe: the production guide-writing entry point accepts an `icon_catalog` and renders `client_icon`/placeholder (never a DB hotlink). Green + commit.

### Task 2.5: Untrack stale generated site + DB tooltip catalog
**Files:** `git rm --cached` the tracked generated outputs (`reports/meta/**`, the DB tooltip catalog, any generated guide pages carrying `db.ascension.gg`) + `.gitignore` them; the generator/templates + source fonts stay under `coa_meta` (authority). Test: `tests/test_e0r1_no_stale_db_output.py`.
- [x] Probe: no tracked *generated* artifact contains `db.ascension.gg`; the generator + templates remain committed. (Optionally regenerate an **untracked** client-native preview AFTER Workstream 5, once blocked sections + heuristic labeling are correct — never committed.) Green + commit.

---

## Workstream 3 — Trust boundary + real transaction

### Task 3.0: One shared golden fixture corpus (Python + Node)
**Files:** Create `tests/golden/e0r1_corpus/` (accept + reject rows/candidates) consumed by BOTH suites; Test scaffolding referenced by 3.1/3.1b/3.3.
- [x] Build a corpus covering: valid rows; both directions of the eligibility biconditional (eligible-not-populated AND populated-not-eligible); decoding disagreement; unresolved join states; a **required field omitted from both mechanics AND raw**; icon id/path (dis)agreement; trailing/extra/missing rows; a tampered bundle. Commit.

### Task 3.1: Node candidate validator does row semantics over the full required domain
**Files:** Modify `coa_scraper/scripts/lib/generation.mjs` (`validateCandidateByPath`), `mechanics-projection.mjs` (`verifyRowAgainstPolicy`, wire `assertPolicyLock`); Test: `coa_scraper/tests/e0r1-candidate-trust.test.mjs` (uses the 3.0 corpus).
- [x] Probe: an **empty** V3 candidate FAILS; missing required child FAILS; bad `candidate_trust_sha256` FAILS; policy child not matching the lock FAILS; a required field omitted from **both** mechanics and raw FAILS (row validation iterates **policy-required fields ∪ mechanics ∪ raw**, not just `row.raw`); both biconditional directions + decoding disagreement + unresolved-join FAIL as specified.
- [x] Fix: `validateCandidateByPath` checks the required-child registry, recomputes `candidate_trust_sha256`, calls `assertPolicyLock` against the staged policy child, and iterates the full required-field domain. Green + commit.

### Task 3.1b: Node cross-child + bundle verification (candidate path)
**Files:** Modify `coa_scraper/scripts/lib/generation.mjs` (streaming cross-child in Node); Test: `coa_scraper/tests/e0r1-node-cross-child.test.mjs` (3.0 corpus).
- [x] Probe: Node candidate validation verifies full/projection/icon **sorted uniqueness + exact domains**; identity/attribution/compact-raw-expansion agreement; trailing/missing/extra rows; icon **id/path agreement**; bundle **path containment + internal manifest + contents + hashes**. Each corpus reject-case FAILS in Node.
- [x] Fix: implement the Node streaming cross-child + bundle checks (mirroring Python `_cross_child`). Green + commit.

### Task 3.2: Both resolvers require strict published state
**Files:** Modify `coa_client_extract/publish.py` (`resolve_active_generation`), `coa_scraper/scripts/lib/generation.mjs` (`resolveGeneration`); Test: `tests/test_e0r1_resolver_strict.py`, `coa_scraper/tests/e0r1-resolver-strict.test.mjs`.
- [x] Probe: a manifest-v2, or v3 with `publication_state!="published"`, missing/invalid `candidate_trust_sha256`, `validation` not both-true, or `budget.within_budget!=true`, or missing a required child, is REJECTED by BOTH resolvers.
- [x] Fix: enforce strict `manifest-v3` + published + trust digest + validation + budget + required registry. Green + commit.

### Task 3.3: Complete Python cross-child (same standard, shared corpus)
**Files:** Modify `coa_client_extract/publish.py` (`_cross_child`, `_icon_bundle`); Test: `tests/test_e0r1_cross_child.py` (3.0 corpus).
- [x] Probe: mismatched icon id/path FAILS; a trailing/extra icon row FAILS; a bundle whose contents/paths/hash/internal-manifest disagree FAILS — every 3.0 reject-case FAILS identically in Python and Node.
- [x] Fix: extend Python cross-child to icon id/path agreement + reject trailing/extra + validate bundle contents; assert parity with 3.1b over the shared corpus. Green + commit.

### Task 3.4: True transaction under late failure + concurrency
**Files:** Modify `coa_client_extract/cli.py` (stage parity BEFORE publish; summary cannot fail publication), `coa_client_extract/publish.py` (hold lock predecessor-read→replace with revalidation); Test: `tests/test_e0r1_transaction.py`.
- [x] Probe: a parity/summary failure leaves the previous pointer untouched; two concurrent publishers cannot last-writer-win (predecessor revalidated under the lock).
- [x] Fix: move parity into the candidate stage; acquire the lock before `_predecessor()` and revalidate before replace. Green + commit.

---

## Workstream 4 — True streaming + policy-bound budgets

### Task 4.1: Stream producer → writer → Python validation/cross-child
**Files:** Modify `coa_client_extract/cli.py` (`regenerate`), `coa_client_extract/publish.py` (`add_jsonl` streaming write + incremental sha/count; `_cross_child`/`_validate_children_by_path` stream by line, no whole-child read); Test: `tests/test_e0r1_streaming_py.py`.
- [x] Probe: RSS measured in an **isolated subprocess** shows **bounded growth** as synthetic record count scales (e.g. 10k→100k rows ⇒ sub-linear peak RSS); no whole-table list/`str`+`bytes` double copy; validators read line-by-line.
- [x] Fix: stream rows to disk with incremental hashing/record-count; two-pass or spooled index for projection/icons; stream Python validation + cross-child. Green + commit.

### Task 4.2: Stream Node validation → projection consumption → mechanics serialization
**Files:** Modify `coa_scraper/scripts/lib/generation.mjs`, `mechanics-projection.mjs`, `build-mechanics-artifacts.mjs` (stream the mechanics OUTPUT serialization too); Test: `coa_scraper/tests/e0r1-streaming-node.test.mjs`.
- [x] Probe: line-by-line child validation + projection consumption + **mechanics output serialization** with incremental hashing; subprocess RSS bounded as record count scales; no whole-child `readFileSync`+split retained array, no whole-output array.
- [x] Fix + green + commit.

### Task 4.3: Separate, unambiguous policy-bound ceilings + pinned env
**Files:** Modify `coa_client_extract/data/spell_layout_v2.json` (a `budget` block), `coa_client_extract/spell_mechanics.py`/`publish.py` (read ceilings from policy; enforce per-child AND whole-generation), `coa_client_extract/manifest.py` (record `benchmark_env`); Test: `tests/test_e0r1_budget_policy_bound.py`.
- [ ] Probe: the policy declares **max_serialized_bytes_per_child**, **max_whole_generation_bytes**, **python_peak_rss_mb**/**python_elapsed_s**, **node_peak_rss_mb**/**node_elapsed_s**, and optional per-child overrides; a single child over its per-child ceiling FAILS even if the whole is under; whole-gen over FAILS; the manifest records a reproducible `benchmark_env`.
- [ ] Fix + green + commit.

---

## Workstream 5 — Finish the sunset + honest interlock

### Task 5.1: AscensionDB runtime — exact disposition per file
**Files (each gets a named disposition, not "delete or strip"):**
- `coa_scraper/scripts/lib/ascensiondb.mjs` + `ascensiondb-cache.mjs`: **`git rm`** (delete). Move any still-needed pure helpers (none expected) to a neutral module first.
- `coa_scraper/scripts/build-item-artifacts.mjs`: **`git rm`** (the item builder is DB-derived) OR, if item output must survive, **rewrite** to client-native with no `ascension_db` provenance — default is delete.
- `coa_meta/guide_tooltips.py`: **rewrite** client-native — remove `load_db_tooltip_rows` preference, the `ascension_db` source, and the "high" name-match; a tooltip is `normalized` from the client description.
- `coa_meta/cli.py`: **remove** the `--db-tooltips` input.
- `coa_scraper/scripts/download-spell-icons.mjs`: **keep** — the ONLY non-test file that may contain the hostname; require an explicit `--authorize` flag, write only under a `diagnostic/` dir, and it must never be importable by canonical guide generation.
- `coa_scraper/scripts/README-regeneration.md` (+ any op docs): **rewrite** to the pointer-only client-native pipeline.
- Test: `tests/test_e0r1_sunset_complete.py`, extend `coa_scraper/tests/no-ascensiondb.test.mjs`.
- [ ] Probe: no runtime (non-test, non-downloader) file imports `ascensiondb` or contains `db.ascension.gg`; `guide_tooltips` emits neither an `ascension_db` source nor a DB URL; no CLI exposes a DB input; the downloader refuses to run without `--authorize` and only writes under the diagnostic dir. Green + commit.

### Task 5.2: Complete readiness status/value/reason truth table
**Files:** Modify `coa_meta/mechanics.py` (`_validate_field_readiness`) and `coa_client_extract/contracts.py` (reason⇔status compatibility map if needed); Test: `tests/test_e0r1_readiness_strict.py`.
- [ ] Probe (full truth table): `available` requires a present non-null value; `verified_empty` is set-valued only AND requires an actually-empty collection (reject a non-empty map); `not_applicable`/`unavailable`/`ambiguous` require null; each reason_code must be compatible with its status (e.g. `proven_empty`⇒`verified_empty`, `not_extracted`⇏`verified_empty`, `proven_empty`⇏`unavailable`); a required load-bearing field cannot silently omit readiness. Green + commit.

### Task 5.3: numberOrNull + drop spellRows
**Files:** Modify `coa_scraper/scripts/build-mechanics-artifacts.mjs`; Test: extend `coa_scraper/tests/mechanics-v2.test.mjs`.
- [ ] Probe: `numberOrNull(null)===null`; `buildCanonicalMechanics` has no `spellRows` parameter. Green + commit.

### Task 5.4: Honest interlock across every quantitative path
**Files:** Modify `coa_meta/reporting.py` (no auto `allow_heuristic`; canonical returns an explicit `blocked` rotation section), `coa_meta/action_catalog.py`, `coa_meta/rotation_simulation.py`, `coa_meta/simulation.py` (`source:"heuristic"`), `coa_meta/apl_interpreter.py`, combat conversion; add a default-off heuristic command/mode; Test: `tests/test_e0r1_interlock_behavioral.py`.
- [ ] Probe (behavioral, over action_catalog + rotation_simulation + simulation + apl_interpreter + combat + reporting): a missing load-bearing input **blocks** (canonical returns `blocked`, never a silent heuristic); a verified `0` stays `0`; a verified `1500` stays `1500`; a verified empty cost stays free (`{}`); heuristics require **explicit opt-in** and every heuristic output reports `source: "heuristic"`. Green + commit.

---

## Workstream 6 — Real CI + binding acceptance

### Task 6.1: Real CI + clean-env packaging
**Files:** Modify `.github/workflows/ci.yml` (trigger on branch push + PR; `python -m pytest` + `npm test`; run the probe tests), `pyproject.toml` (clean-env collection: make `pytest -q` importable — add a `conftest.py`/`rootdir` sys.path shim or package the fixtures); Test: `tests/test_e0r1_clean_env_collect.py` (asserts a clean `pytest -q` collects).
- [ ] Probe + fix. Green + commit.

### Task 6.2: Binding acceptance writer (commits the recon report; executed booleans)
**Files:** Modify `coa_client_extract/cli.py` (`write_acceptance_summary` + `acceptance-summary` subcommand: take a recon-report PATH, hash it, assert `status=="verified"`; run the network-trap + a real `--client-extract-pointer` build to derive `pointer_only`); Test: `tests/test_e0r1_acceptance_binding.py`.
- [ ] Probe: the summary **commits the normalized recon report itself** (not only its hash) and binds its hash; asserts the recon `status=="verified"`; reads strict-V3/published/validation/budget from the RESOLVED manifest (rejects a caller-supplied status/pointer_only); records icon/readiness/source **coverage** counts; `pointer_only` + the network-trap result come from **executed commands**, not caller booleans.
- [ ] Fix + green + commit.

### Task 6.3: Real-client acceptance, then push → draft PR → CI-before-merge
- [ ] Local gates first: full synthetic suites green in a clean env; stop the launcher; re-run recon (must be `verified` under the E0R.1 state machine + all-four-join adjudication); run the full acceptance (regenerate + measured pointer-only build-mechanics) that COMMITS the recon report + binds it; confirm strict-V3 published + within budget + real coverage.
- [ ] Commit the recon report + acceptance summary; **push `m1-14-e0r` once**; open a **draft PR** against `main` (this triggers the branch/PR CI). Require the GitHub check **green before any merge**; a follow-up corrective push is allowed ONLY for a remote-environment-only defect. **Do NOT merge** (E1 + merge are separate).

---

## Self-Review

Spec coverage: every P1 + the misc items map to a task (WS1 recon state machine + all-four-join adjudication + power_type interpretation demotion + no inferred backfill; WS2 description-raw + projection expansion + icon promotion/placeholder + guide-writer wiring + stale-output untrack; WS3 shared golden corpus + Node semantics/cross-child/bundle + full required-field domain + strict resolvers + real transaction; WS4 full-pipeline streaming + separate policy ceilings; WS5 exact sunset disposition + readiness truth table + numberOrNull + all-quantitative-path interlock; WS6 real CI + recon-report-committing acceptance + push→draft-PR→CI-before-merge). Probe-first: each task names its failing probe; WS3 shares one golden corpus across Python + Node. Type consistency: reuses E0R interfaces (`verifyRowAgainstPolicy`, `assertPolicyLock`, `make_string_join`, `three_part_budget`, readiness contracts). Ordering realism: no remote CI green is claimed before the push. No E1 work; no `main` merge.
