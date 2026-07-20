# M1.14E0R.1 — Enforce the E0R Contract (make incomplete data unmistakable)

**Status:** design. **Branch:** `m1-14-e0r` (continues the milestone; no fresh branch, no squash/rewrite of pushed history). **Amends, does not replace,** the approved E0R design (`2026-07-19-m1-14-e0r-correctness-sunset-remediation-design.md`). E0R shipped several guarantees as *descriptive* (happy-path enforced, adversarial case still passes). E0R.1 makes the adversarial case **impossible**. It does **not** finish the mechanics model (that is E1) — its single job is that incomplete data can never be mistaken for finished data.

## Method (non-negotiable)

Every confirmed adversarial case below is first encoded as a **failing test**, then fixed until green. Commits stay small and contract-focused. No E1 work; no merge to `main`. Final push only after full synthetic **and** real-client acceptance pass with genuine GitHub CI.

## Confirmed defects (each becomes a probe-test)

Verified in the current tree (`aaf19ac`):

- **P1-recon** `mechanics_recon_command` passes no `join_value_anchors`/`power_type_anchors`; the joined-pair + negative-anchor probes never run; `verified` doesn't require them; the four joins stay null-cell/deferred. So `verified` doesn't attest to E0R's required adjudications.
- **P1-signedness** all eight policy anchors are non-negative; the negative-`power_type` reading rests on an *observed* `-2`, not a static client-corroborated anchor. Overclaimed → `power_type` must be `raw_only` until a static negative anchor is encoded.
- **P1-lossless/icons** `iter_spell_records` never emits the `description` raw (cell 170); the "rich projection" is a shallow copy, not the specified envelope expansion; `iter_icon_catalog` publishes a path without consulting join/component promotion, and with the real policy's **null** icon index every spell collapses to FK 0 (the 208,444-row icon child proves no coverage); production guide writers never accept/pass `icon_catalog`.
- **P1-trust-boundary** `generation.mjs --candidate` validates transport only (state/schema/child hashes); it does not check the required-child registry, `candidate_trust_sha256`, cross-child agreement, the policy lock, or row semantics — an **empty V3 candidate passes**. `assertPolicyLock` has **no caller**. `verifyRowAgainstPolicy` iterates only fields present in `row.raw`, so a populated mechanic whose raw observation is omitted is never examined.
- **P1-resolvers** `resolve_active_generation` (Python) and `resolveGeneration` (Node) accept manifest-v2 and don't require `publication_state=="published"`, a valid `candidate_trust_sha256`, both validations true, `budget.within_budget==true`, or the required-child registry. A garbage-state manifest resolves. Python cross-child is incomplete (identity checks only name/mechanics; icons checked for presence not id/path; trailing extra icon rows unrejected; bundle contents unchecked).
- **P1-transaction** the pointer advances before parity + the compatibility summary, both of which can still raise; `_predecessor()` runs before the lock with no revalidation under the lock → two publishers last-writer-win.
- **P1-streaming** full/projection/icon arrays, a giant JSONL string+bytes copy, whole-child Python/Node reads, and whole-projection arrays remain; real run hit 2.68 GiB RSS / 4 GiB ceiling with no E1 headroom; ceilings are code constants, per-child limits unenforced, benchmark env unpinned.
- **P1-sunset** `ascensiondb.mjs` + cache remain; `build-item-artifacts.mjs` emits `ascension_db` provenance; `guide_tooltips.py` prefers supplied DB rows and labels a name match "high"; `coa_meta/cli.py` exposes `--db-tooltips`; README describes the retired pipeline; **the player-facing site was never regenerated** (~7.3k `db.ascension.gg` refs across 96 tracked files; the tooltip catalog is DB-derived with live DB URLs).
- **P1-interlock** `reporting.py` sets `allow_heuristic = not ready` automatically, so requesting a rotation is implicit authorization to invent operands; `simulation.py` still fabricates gcd/cooldown/costs/magnitudes and reports `source:"simulated"`; the readiness loader accepts `available`+null, `verified_empty`+`not_extracted`, `unavailable`+`proven_empty`.
- **P1-CI** workflow runs on `push:main` only, uses `unit-test` not `npm test`, and `pytest -q` in a clean `pip install -e .` env fails collection (packaging omits `tests`, so `tests._spell_fixtures` is unimportable; `python -m pytest` masks it). Acceptance `recon_status`/`pointer_only` are caller inputs, bound to no recon report or network trap.
- **misc** `numberOrNull(null)===0`; `buildCanonicalMechanics` still accepts `spellRows` (DB reintroduction path); `test_e0r_client.py` asserts the real recon is *not* verified (contradicts the acceptance); `git diff --check` fails on a trailing blank line in the plan.

## Six workstreams (executed in order; each gated by its probes)

### 1. Recon + policy truth

**All four joins are probed NOW** (E0R pulled them forward) — `cast_time_ms`, `duration_ms`, `range_*`, `spell_icon_id`. The recon lifecycle and its `verified` predicate are made self-consistent (the current plan's contradiction — requiring `power_type_signed is True` while keeping `power_type` raw-only — is removed). The recon state machine:

- Every required join + the `power_type` anchors are probed on every recon run; the report records each attempted discovery **and its evidence** (matches/coverage/candidates), never silently skipped.
- A **unique** discovery must match the authored policy cell **and** promotion. A unique discovery the policy has **not** adopted ⇒ `review_required` (never `verified`).
- A genuinely **ambiguous** result may remain null/`raw_only`, but the report must record the attempted discovery + evidence (so "unadjudicated" is proven, not assumed).
- Signedness is required **only if** `power_type` claims a verified interpretation/normalization. Absent an admissible **static** anchor, recon may still be `verified` **only when** the policy declares `power_type` interpretation `unproven`/`raw_only` and the report records `no_static_anchor`.
- Add an explicit **policy-adjudication task** that authors the discovered join cells (unique+matched) into the reviewed policy; ambiguous joins stay null with recorded evidence. (Discovery → adjudication → re-bind, not discovery → nothing.)

`power_type` is demoted (Task 1.2): **promotion `raw_only` AND interpretation not `verified`**. The raw `u32` is retained, the decoded value is **withheld** with `decoded_reason: "proof_withheld"`, and no normalized client value is emitted — otherwise the policy still asserts a verified signed-int32 reading and could emit a decoded `-2`. Additionally, the Node builder currently backfills a withheld client `power_type` with Builder-derived `resources` at the `inferred` tier; canonical mechanics must instead expose **null + `unavailable`/`no_static_anchor`**, and any inferred power type stays **diagnostic/heuristic only** (never a canonical replacement).

### 2. Lossless artifacts + client-native icons

Emit `description` raw (offset+resolved) in v3; implement the real projection **envelope expansion** (not a shallow copy); route icon extraction through `make_string_join` + promotion. Run + **adjudicate the icon join now** (WS1) rather than pre-accepting an E1 deferral — zero coverage is acceptable **only** if the mandatory icon probe genuinely remains ambiguous and the committed recon report proves it. For an unresolved icon join, the catalog row is `asset_status: "placeholder"` with `readiness: "unavailable"` (**not** `"unavailable"` as a status — that is not a valid `ICON_ASSET_STATUSES` value; reserve `"missing"` for a proven path whose client asset cannot be found). Record honest **coverage** counts in the manifest/summary. Wire `icon_catalog` through the production guide writer. Regenerate or **untrack** every stale generated guide/site output (`reports/meta/**` + the DB tooltip catalog are generated outputs, not authority).

### 3. Trust boundary + real transaction

Node validates, **by candidate path**, everything the design promises — implemented in Node, not just Python:
- full/projection/icon **sorted uniqueness + exact domains**; identity/attribution/compact-raw-expansion agreement; trailing/missing/extra rows; icon **id/path agreement**; bundle **path containment + internal manifest + contents + hashes**;
- the required-child registry, `candidate_trust_sha256`, and the **policy lock** (`assertPolicyLock` gets its caller);
- row validation iterates **policy-required fields ∪ mechanics ∪ raw** (not merely mechanics ∪ raw — otherwise omitting both sides passes); test **both directions** of the eligibility biconditional, decoding disagreement, unresolved join states, and missing required raw.

One **shared golden fixture corpus** drives both the Python and Node validators. Both resolvers require strict `manifest-v3` + `published` + both-validations-true + `within_budget` + full registry. Python cross-child is completed to the same standard (icon id/path agreement, reject trailing/extra, bundle contents). The transaction is made real: stage parity **before** publication (the summary can never fail a publish); acquire the process lock **before** `_predecessor()` and revalidate the predecessor under the lock through the pointer replace.

### 4. True streaming + policy-bound budgets

Stream the **entire** pipeline with incremental hashing/parsing (no whole-table arrays or string+bytes double copies): producer → writer → **Python validation/cross-child** → **Node validation** → projection consumption → **mechanics serialization**. RSS tests run in **isolated subprocesses** and demonstrate **bounded growth** as synthetic record count increases. The policy carries separate, unambiguous ceilings: **max serialized bytes per child**, **max whole-generation bytes**, **Python peak RSS/elapsed**, **Node peak RSS/elapsed**, and optional per-child overrides — enforced per-child and whole-generation. The manifest pins a reproducible `benchmark_env`. Re-run the real client with substantial E1 headroom.

### 5. Finish the sunset + honest interlock

Give **every** runtime AscensionDB file an exact disposition (delete / strip / rewrite client-native), enumerated in the plan — not "delete or strip". The **opt-in image downloader** is the ONLY non-test file that may contain the hostname; it requires explicit authorization, writes only to a **diagnostic** directory, and never feeds canonical guide generation. `guide_tooltips` becomes client-native (no `db_rows` preference, no "high" name-match, no DB URL); `--db-tooltips` and the item builder's `ascension_db` provenance go.

Readiness gets a **complete status/value/reason truth table**: `available` requires a present non-null value; `verified_empty` is set-valued only and requires an actually-empty collection; `not_applicable`/`unavailable`/`ambiguous` require null; reason codes must be compatible with their status; a required load-bearing field cannot silently omit readiness. The consumer sweep covers the **actual quantitative paths** — `action_catalog.py`, `rotation_simulation.py`, `simulation.py`, `apl_interpreter.py`, combat conversion, `reporting.py` — with behavioral tests proving: missing input **blocks**; a verified `0` stays `0`; a verified `1500` stays `1500`; a verified empty cost stays free; heuristics require **explicit opt-in** and always report `source: "heuristic"`. Canonical reporting returns an explicit **blocked** section instead of auto-`allow_heuristic`. Fix `numberOrNull(null)→null`; drop `spellRows` from `buildCanonicalMechanics`.

### 6. Real CI + binding acceptance

Workflow triggers on **branch push and PR**, runs `python -m pytest` + `npm test` + the adversarial probes; packaging fixed so `pytest -q` collects in a clean env. **Ordering (a green remote check cannot precede the push):** complete local synthetic + real-client gates → **push the candidate once** → open a **draft PR** against `main` → require the green GitHub check **before merge**; a follow-up corrective push is allowed only for a remote-environment-only defect. The acceptance writer commits the **normalized recon report itself** (not merely its hash), asserts strict-V3/published/validation/budget from the resolved manifest, records **icon/readiness/source coverage** counts, and records `pointer_only` + the network-trap result **from executed commands**, never caller-supplied booleans.

## Exit criteria (E0R.1 done)

Every probe-test green; both suites green in a clean env; `git diff --check` clean; no runtime `db.ascension.gg` and no stale tracked generated DB output; all four joins probed + adjudicated (or ambiguity proven in the committed report); `power_type` raw-only with withheld decode and no unlabeled inferred replacement; a recorded real-client acceptance that **commits** a `verified` recon report, proves strict-V3 published-and-validated-within-budget publication, and records real coverage; a **genuine green GitHub CI check** on the pushed branch/draft-PR. Then — and only then — is E0R complete; E1 (operands/closure) and the merge to `main` follow separately.
