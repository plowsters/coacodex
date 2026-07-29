# M1.14 E0R.2 — close the E0R.1 review blockers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) or
> superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking. **This file is the canonical task tracker** (the MCP tracker is offline).

**Goal:** Make every guarantee E0R.1 *documented* impossible to violate, so PR #1 can merge on evidence
rather than on description.

**Architecture:** Seven review blockers, closed in dependency order. A **cryptographically bound**
generation contract — staged as a generation child, hashed into `manifest.binding`, covered by candidate
trust, and independently re-derived by both languages — replaces the name-only child registry, and
expresses *relational* cardinalities against the client topology rather than conservative floors. The
acceptance record becomes one internally-executed command whose every claim is bound to a single
generation id **and** manifest hash. Recon re-probes the ambiguous joins against a hash-bound baseline.
The canonical Node build streams end to end. A v4 schema migration sheds ~225 MB of measured redundancy.

**Tech Stack:** Python 3.11 (`coa_client_extract/`, `coa_meta/`), Node 20 ESM
(`coa_scraper/scripts/`), pytest, `node --test`.

## Global Constraints

- **Branch:** `m1-14-e0r`. No history rewrite. **Do NOT merge PR #1. Do NOT start E1.**
- **Commits:** explicit file paths only — **NEVER `git add -A`**. One contract-focused commit per task.
- **Method:** probe-first TDD. Every adversarial case is a failing test *before* its fix.
- **EVERY COMMIT LEAVES THE FULL SYNTHETIC SUITE GREEN.** No task may end with a knowingly-red test.
  Schema changes land as expand → migrate → contract, with each step independently valid. A gate that
  can only pass after a real-client run (the headroom assertion) is committed **together with** the
  artifact that satisfies it, never earlier.
- **Push:** once, at the end (WS8), after the full local suite is green. Never claim a remote green
  before the push.
- **Anchor-evidence precedence (verbatim, unchanged from E0R):** 1. Hash-bound client-static evidence
  (client strings, known BLP paths). 2. Verified Builder payload fields
  (`coa_scraper/dist/coa_entries.jsonl`) that explicitly encode the value. 3. Stock 3.3.5 data ONLY as
  corroboration for demonstrably-unchanged stock spells. Do not use AscensionDB, remembered values,
  runtime behavior, or values inferred from the candidate DBC column being tested.
- **Client root:** always referenced as `$COA_CLIENT_ROOT`, never as a literal path — including in this
  document, which T7.1's hygiene test scans.
- **Suites:** `pytest -q` from the repo root (CI runs **bare** `pytest`); `npm --prefix coa_scraper test`.
- **Baseline at plan time:** branch head `d69b5d3`, 625 Python + 121 Node green, generation
  `a9663d1b410841dd8284cb7538c61185` at 523,026,495 bytes (97.42% of ceiling).

## Verified schema facts this plan depends on

Established by probe against the tree at `02e0b7c` — do not re-derive, do not assume otherwise:

| Fact | Value |
|---|---|
| Recon client build | `recon.source_pins.client_build` |
| Recon per-table capture hash | `recon.source_pins.dbc.<Table>.sha256` |
| Recon topology | `recon.topology.tables.<Table>` (`.header.record_count`, `.sha256`, `.member`, …) |
| Manifest policy hash | `manifest.binding.policy_sha256` |
| Manifest topology | `manifest.binding.topology.tables.<Table>` — **not** `manifest.binding.tables` |
| Spell header record_count | 208,447 — **equals** the full child's record count exactly |
| Full-child raw cell shapes | `scalar` (1 `policy_ref`) or `join-absent` (1 `policy_ref`); **zero** resolved joins today |
| Resolved join shape | `_compact_join` emits `components.{index,side_id,side_value}`, each with its **own** `policy_ref` |
| **Observation `state` vocabulary** | **`not_applicable`, `present`, `resolved`, `unresolved`** — and nothing else. Enumerated from every `Envelope`/`StringObservation`/`JoinObservation` construction site, not from string literals. |
| **Observation `decoded_reason` vocabulary** | **`decoded`, `index_zero`, `non_finite`, `not_present`, `proof_withheld`, `side_row_missing`, `value_out_of_domain`** — and nothing else. |
| `not_applicable` origin | `spell_proof.py:174,197` — emitted for **every index-zero join** via a positional `JoinObservation(...)` argument, so a `"state": "..."` regex never sees it |
| `candidate` / `absent` are NOT states | `candidate` is only `manifest.publication_state`; `absent` is only a dict **key** in `{"absent": env.to_dict()}` (`spell_record.py:225`) |
| `unknown_symbol` is NOT a decoded_reason | it is a **readiness** reason (`contracts.py:11-15`); the extractor's out-of-domain signal is `value_out_of_domain`, tallied in `unknown_symbol_inventory` |
| Reviewed source-of-truth counts | `spell_layout_v2.json` → `bound.tables.Spell.header.record_count` = 208,447 (hash-bound, reviewed) |
| `school_mask` **is** nullable | `_emit_school` returns `None` when `decoded_reason == "value_out_of_domain"` (`spell_record.py:174-178`), so a new school bit nulls the normalized value by design |
| Node module cycle | `generation.mjs:6` imports from `mechanics-projection.mjs`, and `readJsonlLines` lives in `generation.mjs` — importing it back would cycle |
| Policy rehash | `load_spell_policy` raises `policy sha256 mismatch` on an edited doc; only `compute_policy_sha256(json.load(...))` yields a new hash |

---

## Execution status

| Task | Status | Commit |
|---|---|---|
| T0.1 Observation vocabularies: shared wire schema, constructor-enforced | **done** | `c97d7d5` — 30 probes; `_STATES` dead code removed; 655 Py + 121 Node |
| — Mechanical re-bind (unplanned, user-approved) | **done** | `d935845` — Spell `c8cd440d`→`fc9d91ca` (+329 rows), SpellIcon string block −5 B; layout identical, semantic view byte-identical, 0 blocking |
| T0.2 Bind every source domain the contract cites (DBC + Content JSON) | **done** | `a7f7653` — 10 tables bound, `topology_matches_bound` EMPTY; content 52,744 = child exactly; policy `5fbd5b5d`→`056166c2` |
| T1.1 Contract registry introduced, staged, bound, adopted — **atomic** | **done** | `14632f0` — `e0r-v1` (12 children, no placeholders, wire schema pinned `5d9b743d`) digest `708a00e2`; validators derive from the generation's OWN staged contract via registry dispatch; 58 probes; 726 Py + 121 Node |
| T1.2 Reject a tampered, mismatched, or unsupported contract | **done** | `8107920` — binding leg (digest **and** revision) + registry membership proven behaviourally with a real two-revision registry; 745 Py + 121 Node |
| T1.3 Node dispatches on the supported-contract hash set | **done** | `78dbbae` — mirrored array deleted; independent Node validator (28-case matrix); hash, revision set and child list asserted against Python by subprocess; 745 Py + 168 Node |
| T2.1 **Policy-rooted** cardinalities + unregistered children rejected | **done** | `a9e244b` groundwork (bound content read, closing derivations, 10-table synthetic policy) → `f478b6d` Python enforcement (3-step trust chain, 7 rules, whitelist) → `242ff7e` Node mirror; 765 Py + 180 Node |
| T2.2 Per-child shape validation (both languages) | **done** | `cf19ad6` Python + `2e280c6` Node; 12 shapes each, golden documents from the real producer; 825 Py + 240 Node |
| T2.3 Full observation domain in the policy, validated at load | **done** | `a675153` — mandatory `artifact_contract`, re-derived from the layout at load; enforced at BOTH boundaries (Node `verifyFullRowAgainstPolicy` + new Python `publish._observation_domain`) and structural in both shapes; 840 Py + 247 Node |
| T2.4 Publication requires both validations and a clean budget | **done** | `f874c5a` — identity checks on both boundaries, byte ceilings recomputed from the staged children, `three_part_budget` escape hatch deleted from the publish path; 855 Py + 247 Node |
| T2.5 `converted` prohibited until a bundle validator exists | **done** | `204a26f` — status + `converted_ref` removed from both vocabularies, both shapes and both cross-child passes; behavioural producer test over resolve/missing/unjoined; 862 Py + 247 Node |
| T3.1 Live FK candidate scan on every recon | **done** | `3b23849` — `scan_index_candidates` (integer metrics, 2 passes not 234), `side_table_missing` distinguished from ambiguous, the "must not read its side table" test inverted; 870 Py + 247 Node |
| T3.2 Hash-bound ambiguity baseline; exact agreement required | **done** | `de9ff19` — `ambiguity_baseline` authored from a live client scan (30/34/14), integer thresholds, digest validated at load; **caught a wrong reviewed count (33 vs 34) on the real client**; policy sha `1c6376c6`; 896 Py + 247 Node |
| T3.3 Recon stops claiming artifact size; policy-bound rss/elapsed | **done** | `df8bca7` — `recon_budget` replaces `three_part_budget`; `DEFAULT_BUDGET` deleted; ceilings come from the reviewed policy or the run is refused; 908 Py + 247 Node |
| T4.1 `observation_coverage` + `field_readiness_coverage` producers | **done** | `f55e1d1` — Python accumulator folded into the existing per-row hook (counters + `__slots__`), Node readiness coverage over an explicit rows x fields denominator; 918 Py + 255 Node |
| T4.2 One internally-executed acceptance command | pending | |
| T4.3 Acceptance binds recon + mechanics to one generation (real schemas) | pending | |
| T5.1 Streaming projection consumption | pending | |
| T5.2 Generator mechanics rows + incremental statistics | pending | |
| T5.3 Bounded-retention RSS gate through the real canonical build | pending | |
| T6.1 Kind-aware field descriptors (expand) | pending | |
| T6.2 v4 spell rows: hoist + intern (`e0r-v2`, atomic) | pending | |
| T6.3 Icon v2: two-child normalized assets (`e0r-v3`, atomic) | pending | |
| T6.4 Cross-revision compatibility matrix | pending | |
| T7.1 CI runs `npm test` + `fetch-depth: 0`; path hygiene over tracked text | pending | |
| T7.2 Documentation + ROADMAP corrections | pending | |
| T8.1 Real-client re-run: recon, regenerate, build, acceptance | pending | |
| T8.2 Headroom gate committed with the record | pending | |
| T8.3 Push, PR update, CI green | pending | |

### Execution notes (deviations from the plan as written, with reasons)

- **T0.2 corrected two plan assumptions.** Recon did *not* already open the `CharacterAdvancement*`
  tables — `topology.py:40` iterates `required_tables`, which held only the five Spell-side tables. And
  the Content child has no WDBC source at all, so `derived_from_source_topology` was inexpressible for
  it; it needed its own `content_sources` policy binding (`read_bound_content`). `topology.py` itself
  needed no change: it generalizes once the policy declares the tables.
- **`verify_source_topology` reads `client_build` off the BACKEND**, which `StormLibBackend` does not
  set, so a raw report always carries `build_mismatch` unless the caller supplies it. This cost a false
  drift signal during the re-bind; T4.3's recon-binding digest must not treat that finding as real.
- **T1.1 absorbed registry dispatch from T1.2.** T1.1 must derive the required-child set from the
  generation's own staged contract (otherwise `required_children_for` is dead code for a commit). Doing
  that against an *unverified* staged file would be a one-commit trust REGRESSION versus the hardcoded
  list it replaces, so `_staged_contract` dispatches through the trusted registry by canonical digest in
  T1.1. **T1.2 is therefore reduced to** the third leg — comparing the staged child against
  `manifest.binding.generation_contract` — plus the systematic rejection matrix.
- **Contract digests are canonical, not byte digests.** `add_json` re-serializes the staged child
  (indented, key-sorted), so a byte digest of the registry file would never match the staged copy.
  `generation_contract_sha256` canonicalizes (`sort_keys`, `separators=(",", ":")`), which is also what
  lets Node re-derive it independently in T1.3.
- **T1.3 extended `tests/helpers/candidate.mjs` instead of adding `_e0r2-fixtures.mjs`.** Every Node test
  builds candidates through that helper; a parallel fixture would be a second thing to keep in step —
  exactly the drift this workstream removes. Two more Node fixtures also needed the twelfth child:
  `tests/helpers/streaming-probe.mjs` (the RSS probe) and `writeGenerationFixture` in
  `pipeline-scripts.test.mjs`.
- **T2.1 shipped as three commits**, each green: producer groundwork, Python enforcement, Node mirror.
  The groundwork was unavoidable — a cardinality rule cannot be enforced until the producer emits closing
  derivations and the fixtures stage a policy that actually binds a source domain.
- **`single_document` was unfalsifiable as specified.** `_scan_child` / `scanChild` register `records: 1`
  for every non-JSONL child unconditionally, so a record-count comparison could never fail. The rule now
  requires the child to PARSE as one JSON document — which is also the only check that a JSON child is
  well-formed before a consumer reads it.
- **`validate_candidate_generation` gained `lock_path`.** Python had no notion of a locally-supported
  policy; Node already checked the committed lock. Both boundaries now check the same artifact, and
  `regenerate` passes the lock it already had for Node.
- **Test fixtures now SIZE the staged policy to what they stage** (`bind_policy_doc` /
  `bindPolicyDoc`), and violations break that correspondence on purpose. Sizing the other way round —
  fixed counts in the corpus policy — would have made every existing cross-child test fail the
  cardinality gate before reaching the merge-join it was written to exercise.
- **T2.2's independent implementations earned their keep immediately.** Writing Node's validators
  surfaced a variance neither language had captured: a JOIN's `decoded` is the bare resolved scalar,
  while a scalar's and a component's is a `{kind, value}` envelope. Python's structure hid it (joins
  never reached the envelope check); Node's shared tail rejected the producer's own row. A transcribed
  implementation would have inherited the silence.
- **Golden documents come from the PRODUCER, not from hand-copied rows.** `tests/golden.py` runs the
  synthetic regenerate and reads the children back; `coa_scraper/tests/helpers/golden.mjs` reads the same
  documents through Python. A builder that changes shape moves the golden document and fails the shape
  test rather than shipping.
- **Four envelope facts the probes established** (all wrong in my first draft): an unresolved join
  carries no components; `decoded: null` is legitimate under `value_out_of_domain`; an unresolved rich
  join carries plain `proof` while a resolved one carries `composed_proof`; `archive_plan.excluded` is
  keyed by exclusion family, not a list.
- **T2.3's hole was bigger than the plan described.** The plan said `required_scalar_fields` "still
  permits omitting five fields." The probe found the production policy never carried the key AT ALL, so
  Node's `policyDoc.required_scalar_fields || []` asked nothing of any real row — the `|| []` converted
  an absent contract into an empty one. Permissive defaults are how a check becomes decorative.
- **The domain gate was consumer-only, so T2.3 added the producer half.** The plan's Step 4 named only
  Node. Python's `validate_candidate_generation` checked no observation domain whatsoever, which is not
  "two independent trust boundaries" — it is one boundary and a bystander. `publish._observation_domain`
  now runs in the same streaming cross-child pass, held to the same corpus policy.
- **Key presence is a POLICY question, not a structural one.** A shape validator has no policy, so it
  cannot know which mechanics keys must exist; the first draft of the T2.3 test asserted absence at the
  shape layer and was wrong. Structure says "a mechanics value may be null"; the policy-driven gate says
  "this key must be present." Both are needed and they live in different places.
- **`school_mask` stays nullable and that is not a weakening.** `_emit_school` nulls the value under
  `value_out_of_domain`, so a patch adding an unseen school bit produces a null BY DESIGN. A static
  nullability list cannot distinguish a legitimate null from a dropped one — the biconditional does.
- **Two assertions were retightened, not preserved.** A raw cell deleted to test expansion inequality is
  now caught one gate earlier as loss (the Node tamper became additive: same cells, different substrate),
  and the corpus's `required_field_omitted_from_both` case is rejected on the raw domain rather than the
  old mechanics∪raw union. A test that keeps passing for a new reason is worth re-reading.
- **T2.4's budget check needs ceilings, so the plan's sketch could not work as written.** "Recompute the
  byte ceilings from `self._children`" requires ceilings to recompute AGAINST, and the plan's passing
  case supplied `{"within_budget": True, "breach": []}` with none. The report must carry its `ceilings`
  block — which `policy_budget_report` already emits — and a report without one is refused for being
  uncheckable rather than waved through.
- **The three-part fallback was a second, quieter escape hatch.** `three_part_budget` applied whenever a
  policy declared no budget block — that is, it substituted hard-coded DEFAULT_BUDGET ceilings for
  reviewed ones exactly when review was missing. Deleting it forced every synthetic policy to declare
  its own ceilings, which is the honest state.
- **Publisher-side gates make some consumer-side tests unbuildable, and that is the point.** Two
  resolver-strict tests published deliberately-bad manifests; the publisher now refuses to produce them,
  so they write the manifest after publication. The consumer boundary still needs covering — a manifest
  edited post-publication, or written by a publisher without the gate, is the real threat it answers.
- **T2.5's `converted_ref` had to go with `converted`.** The plan removed the status but left the key
  admissible in both shapes and in `icon_coverage`'s asset-present branch. A bundle reference is
  unverifiable on ANY status, so it is not a structural key either — otherwise the schema still says a
  row may carry a reference nothing can check.
- **The guide renderer is deliberately untouched.** `tests/test_guide_*.py` still exercise a `converted`
  icon catalog. That catalog is a downstream consumer format, not a validated generation child; folding
  it in would have widened T2.5 past the trust boundary it is about. Worth revisiting when the guide's
  icon source is next touched.
- **T3.1's scan had to be cheaper than the code it sits beside.** `discover_join_pair` re-reads the
  whole table once per candidate cell — 234 passes over 208k records on the real client. Adding a
  same-shaped scan to three ambiguous joins would have tripled that. `scan_index_candidates` tallies
  every cell in ONE pass and only counts distinct ids for survivors, which also avoids holding 234
  distinct-id sets at once. Watch this in T3.3's real-client budget.
- **A test that asserted the bug had to be inverted, not deleted.**
  `test_reviewed_ambiguous_join_is_probed_without_reading_side_table` passed an `_ExplodingBackend`
  precisely to prove the side table was never read. It was a faithful test of a wrong design; the
  replacement asserts the scan happens and that the recorded verdict + evidence survive beside it.
- **T3.2 found a real error the moment it had teeth.** The reviewed evidence for `duration_index` said
  the FK-validity scan yields 33 candidate columns; the client yields 34. Before ruling the prose wrong I
  ran the OLD float predicate (`_discover_index_cell`) and the new integer one over the same live bytes:
  34 and 34, empty symmetric difference — so it was not an artifact of the threshold change. A count
  written into prose is not a baseline, and nothing was checking it. A test now requires every prose
  count to equal its baseline's candidate count.
- **Authoring the baseline needed the real client, and the committed recon report could not substitute.**
  That report records the same prose counts and no cells or metrics — exactly the deficiency T3.2 exists
  to fix. The scan ran against `$COA_CLIENT_ROOT` (208776 records x 234 cells, ~21s per join).
- **Adding a policy key breaks the T2.2 shape unless the shape is told.** `ambiguity_baseline` had to be
  added to both languages' `spell_policy_v2` optional key sets in the same commit, or the staged policy
  child would have failed its own exact-key-set check. Worth remembering for every future policy block.
- **Editing evidence prose moves `anchor_set.sha256`, not just the policy digest.** The join evidence
  lives inside `anchor_set`, which carries its own hash; both had to be recomputed, then the Node lock.
- **`DEFAULT_BUDGET` was the same hole as T2.4's, one layer down.** Deleting the publish-path fallback
  left a module-level constant that any recon caller inheriting the default silently got — including the
  600 s elapsed ceiling already known to be breached by the real ~700 s recon. Both are gone; a policy
  without a reviewed budget block is refused on both paths.
- **WS3 is done, and all three tasks removed a claim rather than adding one.** T3.1 stopped quoting a
  past review, T3.2 stopped accepting a count, T3.3 stopped forecasting a size. The pattern is worth
  naming: each was a gate whose NAME described a stronger guarantee than its body delivered, which is
  how they survived review for so long.
- **T4.1's whole content is the denominator.** Both accumulators were easy; what took the care was
  making the parts sum to a stated total at every level, and choosing denominators that a regression can
  move. `rows x READINESS_FIELDS` from an explicit constant, not from the rows: derived from the rows, a
  field that stopped being emitted would leave the set silently and the ratio would never budge.
- **Two same-named things counting different units is the actual bug class.** icon coverage counts
  SPELLS, observation coverage counts CELLS, source coverage counts fields WITH a winner, readiness
  coverage counts fields WITHOUT one. Each is fine; any two reported as "coverage" without their
  denominators is not.
- **Registry location is injectable in both languages** — Python monkeypatches `contracts.CONTRACTS_DIR`,
  Node takes a `contractsDir` option on `validateCandidateByPath`/`resolveGeneration`. Both are needed to
  test membership-vs-current before WS6 actually ships `e0r-v2`.

---

# Workstream 0 — prerequisite: closed, constructor-enforced vocabularies

### Task 0.1: The observation vocabularies become a shared wire schema, enforced at construction

**Files:**
- Create: `coa_client_extract/data/observation_wire_schema.json`
- Modify: `coa_client_extract/contracts.py`, `coa_client_extract/spell_proof.py` (`Envelope`,
  `StringObservation`, `JoinObservation` `__post_init__` validation)
- Test: `tests/test_e0r2_vocabularies.py`

**Why first:** T6.2 interns `state` and `decoded_reason` as integer codes. A value with no code
silently breaks round-tripping, and a code table read from the *staged* generation would let a tampered
descriptor relabel meanings while compact→rich expansion stayed self-consistent.

**Correction carried from review round 3 — my previous vocabularies were wrong in both directions.**
I derived them from a grep over string literals, which conflated three different enumerations. Verified
by enumerating every observation construction site:

- `not_applicable` **is** a state — emitted for *every index-zero join* at `spell_proof.py:174,197`
  as a **positional** `JoinObservation(...)` argument. A `"state": "..."` regex cannot see it, so my
  proposed test would have passed while the vocabulary was incomplete and interning silently lossy.
- `candidate` is **not** a state — it is `manifest.publication_state`.
- `absent` is **not** a state — it is a dict *key* in `{"absent": env.to_dict()}` (`spell_record.py:225`).
- `unknown_symbol` is **not** a decoded_reason — it is a *readiness* reason (`contracts.py:11-15`).
  The extractor's out-of-domain signal is `value_out_of_domain`.

**Where the codes live:** in `observation_wire_schema.json`, referenced by
`schema_version` + sha256 from the generation contract (WS1) and read by **both** languages. Python-only
constants would force Node to maintain a second mirror — the exact drift this milestone is removing.
The *staged* copy is never trusted: both languages load their own and dispatch on a supported hash.

- [ ] **Step 1: Write the failing test — behavioural, over every constructor**

```python
# tests/test_e0r2_vocabularies.py
"""E0R.2 T0.1: `state` and `decoded_reason` are closed vocabularies with no declared set anywhere.
T6.2 assigns integer codes, so both the vocabulary and its code assignment must be schema-owned and
COMPLETE. A regex over string literals is not sufficient evidence of completeness: `not_applicable` is
emitted positionally through JoinObservation for every index-zero join and a regex never sees it."""
import pytest

from coa_client_extract.contracts import (DECODED_REASONS, OBSERVATION_STATES, decoded_reason_code,
                                          observation_state_code, load_observation_wire_schema)
from coa_client_extract.spell_proof import (ObservationError, absent_envelope, make_domain_gated_envelope,
                                            make_envelope, make_join, make_string_join,
                                            make_string_observation)


def test_the_vocabularies_are_exactly_what_the_producer_emits():
    assert OBSERVATION_STATES == ("not_applicable", "present", "resolved", "unresolved")
    assert DECODED_REASONS == ("decoded", "index_zero", "non_finite", "not_present",
                               "proof_withheld", "side_row_missing", "value_out_of_domain")


def test_states_that_are_not_observation_states_are_absent():
    """`candidate` is a publication_state; `absent` is a dict key; `unknown_symbol` is a readiness
    reason. All three were wrongly proposed as observation vocabulary in an earlier draft."""
    for wrong in ("candidate", "absent"):
        assert wrong not in OBSERVATION_STATES
    assert "unknown_symbol" not in DECODED_REASONS


@pytest.mark.parametrize("resolution, expected_state, expected_reason", [
    ("index_zero", "not_applicable", "index_zero"),
    ("side_row_missing", "unresolved", "side_row_missing"),
    ("resolved", "resolved", "decoded"),
])
def test_every_join_constructor_outcome_is_in_the_vocabulary(resolution, expected_state, expected_reason):
    """Behavioural coverage of the constructors, which is where not_applicable actually comes from."""
    obs = make_join(_components(), resolution=resolution, decode=lambda c: 1500)
    assert obs.state == expected_state and obs.decoded_reason == expected_reason
    assert obs.state in OBSERVATION_STATES and obs.decoded_reason in DECODED_REASONS


@pytest.mark.parametrize("factory", [
    lambda: make_envelope(1, kind="int32", proof=_proof(), evidence_ref="/x"),
    lambda: make_envelope(1, kind="uint32", proof=_proof(), evidence_ref="/x"),
    lambda: make_envelope(1, kind="float", proof=_proof(), evidence_ref="/x"),
    lambda: absent_envelope(proof=_proof(), evidence_ref="/x", state="unresolved"),
    # `_KINDS` is ("int32", "uint32", "float") — there is no "bitmask" kind; the mask REFINEMENT is the
    # `refine` callback, not a kind. Passing one raises ValueError before the vocabulary is exercised.
    lambda: make_domain_gated_envelope(999, kind="uint32", proof=_proof(), evidence_ref="/x",
                                       refine=lambda v: (v, False)),
    lambda: make_string_observation(0, "n", proof=_proof(), evidence_ref="/x"),
    lambda: make_string_join(_string_components(), resolution="resolved"),
])
def test_every_observation_factory_emits_in_vocabulary_values(factory):
    obs = factory()
    assert obs.state in OBSERVATION_STATES
    assert obs.decoded_reason in DECODED_REASONS


def test_the_constructors_reject_an_out_of_vocabulary_value():
    """The guard that makes the vocabulary real: a future contributor adding a fifth state fails here
    rather than silently producing an uncodeable cell in T6.2."""
    with pytest.raises(ObservationError, match="state"):
        absent_envelope(proof=_proof(), evidence_ref="/x", state="probably_fine")


def test_every_golden_corpus_cell_is_in_vocabulary():
    from tests.golden import golden_full_rows
    for row in golden_full_rows():
        for field, cell in row["raw"].items():
            for observed in _iter_states_and_reasons(cell):
                assert observed[0] in OBSERVATION_STATES, (field, observed)
                assert observed[1] in DECODED_REASONS, (field, observed)


def test_codes_are_dense_and_come_from_the_shared_wire_schema():
    schema = load_observation_wire_schema()
    assert schema["schema_version"] == "coa-observation-wire-v1"
    assert [schema["states"][s] for s in OBSERVATION_STATES] == list(range(len(OBSERVATION_STATES)))
    assert [schema["decoded_reasons"][r] for r in DECODED_REASONS] == list(range(len(DECODED_REASONS)))
    assert observation_state_code("not_applicable") == schema["states"]["not_applicable"]
    assert decoded_reason_code("index_zero") == schema["decoded_reasons"]["index_zero"]


def test_an_unknown_code_fails_closed():
    with pytest.raises(KeyError):
        observation_state_code("probably_fine")
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Author `observation_wire_schema.json`**

**Correction carried from review round 4 — the wire schema is IMMUTABLE too.** An earlier draft's note
said codes "may be appended". Appending changes the file's bytes and therefore its hash, which
invalidates every already-published contract revision that pinned the old digest. Wire schemas live in
the same immutable-versioned registry discipline as contracts: a new vocabulary entry means
`coa-observation-wire-v2` as a **new file**, referenced by a **new** contract revision. Generations that
carry coded observations stage the wire schema they used, exactly as they stage their contract.

```json
{
  "schema_version": "coa-observation-wire-v1",
  "note": "IMMUTABLE. The closed observation vocabularies and their integer wire codes, read by BOTH languages. Never edit this file — a new vocabulary entry means a new coa-observation-wire-vN file referenced by a new contract revision, because editing changes the hash that published contracts pin. Enumerated from every Envelope/StringObservation/JoinObservation construction site; a grep over string literals conflates these with publication_state and with readiness reasons.",
  "states": {"not_applicable": 0, "present": 1, "resolved": 2, "unresolved": 3},
  "decoded_reasons": {"decoded": 0, "index_zero": 1, "non_finite": 2, "not_present": 3,
                      "proof_withheld": 4, "side_row_missing": 5, "value_out_of_domain": 6}
}
```

- [ ] **Step 4: Add the loader + accessors to `contracts.py` and validation to the three observation
  classes.** Each `__post_init__` raises `ObservationError` when `state` or `decoded_reason` falls
  outside the vocabulary — this is what makes the closed set enforceable rather than aspirational.

- [ ] **Step 5: Run the full suite; commit**

```bash
git add coa_client_extract/data/observation_wire_schema.json coa_client_extract/contracts.py \
        coa_client_extract/spell_proof.py tests/test_e0r2_vocabularies.py
git commit -m "feat(e0r2): T0.1 — closed observation vocabularies, shared wire codes, enforced at construction"
```

### Task 0.2: Bind every source domain the contract will cite

**Files:**
- Modify: `coa_client_extract/data/spell_layout_v2.json` (`required_tables`, `tables`, `bound.tables`,
  new `content_sources`), `coa_client_extract/topology.py`, `coa_client_extract/content_json.py`,
  `coa_scraper/config/spell_layout.lock.json`
- Test: `tests/test_e0r2_source_bindings.py`

**Correction carried from review round 4 — the cardinality rules cite sources that are not bound, and
one of them is not a DBC at all.** Verified:

- `topology.py:40` iterates **`policy.required_tables`** and requires `data[:4] == b"WDBC"`. The policy's
  `required_tables` is `["Spell", "SpellCastTimes", "SpellDuration", "SpellRange", "SpellIcon"]` and
  `bound.tables` covers exactly those five. **The `CharacterAdvancement*` tables are not bound at all**,
  so my earlier claim that "recon already opens them" was wrong — extending the binding is a task, not a
  step inside T2.1.
- `coa_client_content.jsonl` has **no DBC source whatsoever**. `content_json.read_content_records`
  reads five JSON files from `$COA_CLIENT_ROOT/Content` (`DEFAULT_FILES`) and **silently `continue`s
  past any that is missing**. There is no WDBC header and no `record_count`, so
  `derived_from_source_topology` is not merely unfilled for it — it is inexpressible.

This task exists so that T1.1 can author an immutable contract with **no placeholders**.

**Design — two source kinds, bound differently:**

*DBC sources* join the existing mechanism: add `CharacterAdvancement`, `CharacterAdvancementClassTypes`,
`CharacterAdvancementTabTypes`, `CharacterAdvancementEssence` and `SkillLineAbility` to
`required_tables` with their field policies, so `capture_topology` binds their sha256 + 5-field header
and `topology_matches_bound` covers them.

*The Content JSON source* gets its own rule, `declared_content_derivation`, backed by a new policy block:

```json
"content_sources": {
  "directory": "Content",
  "required_files": {
    "SpellRankData.json": {"kind": "spell_rank", "sha256": "<captured>", "source_entries": 0},
    "SpellToStatSuggestionData.json": {"kind": "spell_stat_suggestion", "sha256": "<captured>", "source_entries": 0},
    "SpellToRoleSuggestionData.json": {"kind": "spell_role_suggestion", "sha256": "<captured>", "source_entries": 0},
    "ItemVariationData.json": {"kind": "item_variation", "sha256": "<captured>", "source_entries": 0},
    "CharacterAdvancementData.json": {"kind": "character_advancement", "sha256": "<captured>", "source_entries": 0}
  }
}
```

and the validator requires, per file: present (a missing required file is **blocking**, not a silent
skip), sha256 matches, parsed entry count matches `source_entries`, and across all files
`sum(kept) + sum(rejected) == sum(source_entries)` with `sum(kept) == child records`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_source_bindings.py
"""E0R.2 T0.2: every source a cardinality rule cites must be BOUND before the contract can cite it.
Two gaps: the CharacterAdvancement* DBCs were never in required_tables (so topology never captured
them), and the Content child has no DBC source at all — it reads five JSON files and silently skips
missing ones, which is exactly the silent loss this milestone removes."""
import json
from pathlib import Path

import pytest

from coa_client_extract.content_json import ContentSourceError, read_content_records
from coa_client_extract.spell_layout import load_spell_policy
from coa_client_extract.topology import capture_topology, topology_matches_bound

POLICY = Path(__file__).resolve().parents[1] / "coa_client_extract/data/spell_layout_v2.json"


def test_the_ancillary_dbc_sources_are_required_and_bound():
    doc = json.loads(POLICY.read_text(encoding="utf-8"))
    expected = {"CharacterAdvancement", "CharacterAdvancementClassTypes",
                "CharacterAdvancementTabTypes", "CharacterAdvancementEssence", "SkillLineAbility"}
    assert expected <= set(doc["required_tables"])
    assert expected <= set(doc["bound"]["tables"])
    for name in expected:
        assert doc["bound"]["tables"][name]["header"]["record_count"] > 0


def test_topology_capture_covers_every_bound_table(synthetic_backend):
    policy = load_spell_policy(json.loads(POLICY.read_text(encoding="utf-8")))
    report = capture_topology(synthetic_backend, policy=policy)
    assert set(report["tables"]) == set(policy.bound["tables"])
    assert topology_matches_bound(report, policy.bound) == []


def test_a_missing_content_file_is_blocking_not_silently_skipped(tmp_path):
    """The current reader `continue`s past a missing file, so a client shipping four of five files
    produces a smaller generation with no signal anywhere."""
    (tmp_path / "SpellRankData.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ContentSourceError, match="SpellToStatSuggestionData.json"):
        read_content_records(tmp_path, policy=load_spell_policy(json.loads(POLICY.read_text("utf-8"))))


def test_a_content_file_whose_bytes_changed_is_rejected(tmp_path, content_dir):
    (content_dir / "ItemVariationData.json").write_text('[{"tampered": true}]', encoding="utf-8")
    with pytest.raises(ContentSourceError, match="sha256"):
        read_content_records(content_dir, policy=load_spell_policy(json.loads(POLICY.read_text("utf-8"))))


def test_the_content_derivation_accounting_closes(content_dir):
    policy = load_spell_policy(json.loads(POLICY.read_text(encoding="utf-8")))
    result = read_content_records(content_dir, policy=policy)
    declared = result.derivation
    assert declared["kept"] + declared["rejected"] == declared["source_entries"]
    assert declared["kept"] == len(result.records)
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Capture the real values.** Run `mechanics-recon` against the live client with the
  extended `required_tables` and read the captured headers out of the report; hash the five Content
  files and count their parsed entries. Write those numbers into `bound.tables` and `content_sources`.
  **Never invent them** — every count in this task comes from the client.

- [ ] **Step 4: Rehash the policy** with the T2.3 recipe (`compute_policy_sha256` on the loaded JSON —
  `load_spell_policy` raises on an edited doc) and update `coa_scraper/config/spell_layout.lock.json`.

- [ ] **Step 5: Run the full suite; commit**

```bash
git add coa_client_extract/data/spell_layout_v2.json coa_client_extract/topology.py \
        coa_client_extract/content_json.py coa_scraper/config/spell_layout.lock.json \
        tests/test_e0r2_source_bindings.py
git commit -m "feat(e0r2): T0.2 — bind the ancillary DBC and Content JSON source domains"
```

---

# Workstream 1 — a cryptographically bound generation contract (blocker 1, part 1)

**Blocker:** both validators accept a candidate carrying every required child *name* with zero
spell/projection/icon rows and arbitrary child `schema_version` strings. Reproduced at `02e0b7c`:

```
=== PYTHON validate_candidate_generation ===  ACCEPTED
=== NODE  validateCandidateByPath        ===  ACCEPTED
```

**Correction carried from review round 2:** a contract read from the working tree is not bound to the
generation. A generation produced under contract A could later be validated under contract B. The
contract must be staged as a child, hashed into `manifest.binding`, and covered by candidate trust —
and **both languages must compare the staged contract against their own trusted supported contract**,
so a tampered staged copy is rejected rather than obeyed.

**This workstream describes the CURRENT schema** (`coa-client-spell-v3`, `coa-client-spell-icons-v1`,
11 children). WS6 migrates to v4 and updates the contract atomically. Every commit here is green.

### Task 1.1: Introduce the contract registry, stage it, bind it, and switch — **one atomic commit**

**Files:**
- Create: `coa_client_extract/data/generation_contracts/e0r-v1.json`,
  `coa_client_extract/data/generation_contracts/index.json`
- Modify: `coa_client_extract/contracts.py`, `coa_client_extract/publish.py` (`REQUIRED_CHILDREN`),
  `coa_client_extract/cli.py` (`regenerate` stages the child and extends `binding`), every fixture that
  builds a synthetic generation
- Test: `tests/test_e0r2_generation_contract.py`

**Correction carried from review round 4 — introduction cannot be split from adoption.** The previous
draft authored a 12-child contract in T1.1, derived `REQUIRED_CHILDREN` from it in T1.1, and only staged
the twelfth child in T1.2 — so T1.1 would have left the suite **red**, violating the green-commit
constraint. It also wrote `"source_table": "<from T2.1 Step 3>"` into a file the plan calls immutable
and then had T2.1 edit it, which the immutability check must reject. Both are fixed the same way: **T0.2
resolves every source binding first**, so `e0r-v1.json` is authored complete and placeholder-free, and
introduction + staging + binding + the producer/validator/fixture switch land together.

**Correction carried from review round 3 — a single mutable contract file breaks versioning and
rollback.** If validation accepts only the contract currently in the working tree, then the moment T6.2
rewrites it for v4 every previously published v3 generation becomes unresolvable — including the
predecessor the publish transaction chains to, and any generation an operator would roll back to. E1
would hit the same wall on every child it adds.

**Design:** contracts are **immutable, versioned files** in a registry. A revision is written once and
never edited; a change means a new file. `index.json` lists the supported revisions and the current
producer default:

```json
{
  "schema_version": "coa-generation-contract-index-v1",
  "current": "e0r-v1",
  "supported": {
    "e0r-v1": {"path": "e0r-v1.json", "sha256": "<canonical digest>"}
  }
}
```

The manifest identifies its contract by `{schema_version, revision, sha256}`; validators dispatch on the
**hash**, accepting any revision in `supported`. The producer always writes `current`. WS6 adds
`e0r-v2` and moves `current` — it does **not** edit `e0r-v1`, so v3 generations stay independently
resolvable.

**Interfaces:**
- Produces: `GENERATION_CONTRACT_SCHEMA = "coa-generation-contract-v1"`,
  `load_contract_registry() -> dict`, `load_current_contract() -> tuple[str, dict]` (revision, doc),
  `load_supported_contract(revision, sha256) -> dict` (raises `ContractError` when unsupported or
  hash-mismatched), `validate_generation_contract(doc) -> dict`, `generation_contract_sha256(doc) -> str`
  (canonical JSON: sorted keys, `separators=(",", ":")`).

Per-child shape:

```json
{
  "kind": "jsonl" | "json",
  "child_schema_version": "<exact string>",
  "row_schema_version": "<exact string>" | null,
  "optional": false,
  "cardinality": {"rule": "<named relational rule>" | "min", "min": <int>},
  "shape": "<named semantic validator>"
}
```

`cardinality.rule` names a **relational** rule resolved at validation time (see T2.1); `"min"` with an
explicit floor is permitted **only** for ancillary datasets whose exact source-domain count cannot be
derived. `shape` names a validator implemented independently in both languages (see T2.2) — top-level
key presence is not a shape.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_generation_contract.py
"""E0R.2 T1.1: the generation contract is ONE versioned, SELF-VALIDATED document. A name list cannot
express cardinality, row schema, or shape — which is how a complete-but-empty generation passed both
validators at 02e0b7c. The loader validates the contract itself: a malformed contract is a broken gate,
and a broken gate that loads is worse than no gate."""
import copy

import pytest

from coa_client_extract.contracts import (ContractError, GENERATION_CONTRACT_SCHEMA,
                                          generation_contract_sha256, load_contract_registry,
                                          load_current_contract, load_supported_contract,
                                          validate_generation_contract)
from coa_client_extract.publish import REQUIRED_CHILDREN


def test_contract_covers_exactly_the_required_children():
    revision, contract = load_current_contract()
    assert contract["schema_version"] == GENERATION_CONTRACT_SCHEMA
    assert contract["revision"] == revision
    assert set(contract["children"]) == set(REQUIRED_CHILDREN)


def test_every_child_declares_kind_schema_cardinality_and_shape():
    for name, spec in load_current_contract()[1]["children"].items():
        assert spec["kind"] in ("jsonl", "json"), name
        assert spec["child_schema_version"], name
        assert spec["shape"], name
        assert spec["cardinality"]["rule"], name
        if spec["kind"] == "jsonl":
            assert spec["row_schema_version"], name
        else:
            assert spec["row_schema_version"] is None, name


def test_no_child_uses_a_bare_floor_where_a_source_count_exists():
    """A floor of 1 admits a one-spell generation — and equally a one-class-type generation, which is
    useless for a class guide. Every child whose source-domain count is derivable must derive it."""
    children = load_current_contract()[1]["children"]
    assert children["coa_client_spell.jsonl"]["cardinality"]["rule"] == "reviewed_bound_record_count"
    assert children["coa_client_spell_icons.jsonl"]["cardinality"]["rule"] == "equals_full_spell_records"
    assert children["coa_client_spell_coa.jsonl"]["cardinality"]["rule"] == "equals_is_coa_full_records"
    for name in ("coa_client_class_types.jsonl", "coa_client_tab_types.jsonl",
                 "coa_client_essence.jsonl"):
        assert children[name]["cardinality"]["rule"] == "derived_from_source_topology", name
    assert children["coa_client_advancement.jsonl"]["cardinality"]["rule"] == "declared_derivation"
    # Content has no WDBC source at all — five JSON files, bound by T0.2's content_sources block.
    assert children["coa_client_content.jsonl"]["cardinality"]["rule"] == "declared_content_derivation"


def test_no_contract_revision_contains_a_placeholder():
    """An immutable file with a TODO in it is a file that will be edited."""
    import re
    for revision, doc in _all_supported_contracts():
        blob = json.dumps(doc)
        assert not re.search(r"<[^>]*(from|TODO|captured|placeholder)[^>]*>", blob), revision


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d.update(schema_version="nope"), "schema_version"),
    (lambda d: d.update(smuggled_top_level=1), "smuggled_top_level"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(kind="parquet"), "kind"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(shape=""), "shape"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(unexpected_key=1), "unexpected_key"),
    (lambda d: d["children"]["spell_layout_v2.json"].update(optional="yes"), "optional"),
    (lambda d: d["children"]["coa_client_spell.jsonl"].update(row_schema_version=None), "row_schema_version"),
    (lambda d: d["children"].update(dupe=copy.deepcopy(d["children"]["spell_layout_v2.json"])), "shape"),
    (lambda d: d["children"].update(**{"../escape.json": d["children"]["spell_layout_v2.json"]}), "child name"),
    (lambda d: d["children"].update(**{"sub/dir.json": d["children"]["spell_layout_v2.json"]}), "child name"),
    (lambda d: d["children"]["coa_client_content.jsonl"]["cardinality"].update(min=True), "min"),
    (lambda d: d["children"]["coa_client_content.jsonl"]["cardinality"].update(min=-1), "min"),
    (lambda d: d["children"]["coa_client_content.jsonl"]["cardinality"].update(unexpected=1), "cardinality"),
])
def test_the_loader_rejects_a_malformed_contract(mutate, match):
    _, doc = load_current_contract()
    doc = copy.deepcopy(doc)
    mutate(doc)
    with pytest.raises(ContractError, match=match):
        validate_generation_contract(doc)


def test_the_contract_hash_is_canonical_and_stable():
    _, doc = load_current_contract()
    reordered = {"children": doc["children"], "schema_version": doc["schema_version"],
                 **{k: v for k, v in doc.items() if k not in ("children", "schema_version")}}
    assert generation_contract_sha256(doc) == generation_contract_sha256(reordered)
    assert len(generation_contract_sha256(doc)) == 64


def test_the_registry_pins_every_supported_revision_by_hash():
    registry = load_contract_registry()
    for revision, entry in registry["supported"].items():
        doc = load_supported_contract(revision, entry["sha256"])
        assert generation_contract_sha256(doc) == entry["sha256"]


def test_an_unsupported_or_tampered_revision_is_refused():
    with pytest.raises(ContractError, match="unsupported"):
        load_supported_contract("e0r-v99", "0" * 64)
    revision = load_contract_registry()["current"]
    with pytest.raises(ContractError, match="sha256"):
        load_supported_contract(revision, "0" * 64)


def test_every_revision_file_still_hashes_to_its_pinned_digest():
    """PRIMARY immutability check, and the one that always runs. `git log --name-only` was the previous
    draft's approach; CI uses actions/checkout@v4, which defaults to fetch-depth 1, so that command
    returns almost nothing and the test would have passed VACUOUSLY in exactly the environment it was
    meant to guard. Runtime hash pinning needs no history at all."""
    registry = load_contract_registry()
    for revision, entry in registry["supported"].items():
        path = CONTRACTS_DIR / entry["path"]
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert generation_contract_sha256(doc) == entry["sha256"], (
            f"{revision} was edited in place; add a new revision instead of changing a published one")
        assert doc["revision"] == revision, f"{revision} disagrees with its registry key"


def test_no_revision_file_is_modified_relative_to_the_merge_base():
    """SECONDARY check: catches an edit-plus-rehash, which the hash pin alone cannot see. Requires
    history, so T7.1 sets fetch-depth: 0 in CI. FAILS (never skips) when the merge base is unavailable —
    a guard that quietly opts out is the defect this replaces."""
    import subprocess
    base = subprocess.run(["git", "merge-base", "HEAD", "origin/main"],
                          capture_output=True, text=True)
    assert base.returncode == 0, (
        "merge base unavailable — run with full history (CI: fetch-depth: 0); refusing to pass vacuously")
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", base.stdout.strip(), "--",
         "coa_client_extract/data/generation_contracts/"], text=True).split()
    edited = [p for p in changed if not p.endswith("index.json")
              and p in _paths_supported_before(base.stdout.strip())]
    assert edited == [], f"published contract revision(s) modified: {edited}"


def test_the_registry_itself_is_validated():
    registry = load_contract_registry()
    assert registry["current"] in registry["supported"]
    for revision, entry in registry["supported"].items():
        assert set(entry) == {"path", "sha256"}
        assert re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.json", entry["path"]), entry["path"]
        assert len(entry["sha256"]) == 64
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Author the contract for the CURRENT schema**

**Twelve children** — the eleven `regenerate` emits today plus the staged contract itself. Every
cardinality is relational and every `source_table` names a domain T0.2 actually bound, so the file has
**no placeholders** and never needs a later edit.

```json
{
  "schema_version": "coa-generation-contract-v1",
  "revision": "e0r-v1",
  "note": "IMMUTABLE. The E0R child contract, staged as a generation child and identified in manifest.binding by revision + sha256, so a generation is always interpreted under the contract it was produced with and older revisions stay resolvable. Never edit this file — add a new revision.",
  "observation_wire_schema": {"schema_version": "coa-observation-wire-v1", "sha256": "<digest of observation_wire_schema.json>"},
  "children": {
    "coa_client_spell.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-v3",
      "row_schema_version": "coa-client-spell-v3", "optional": false,
      "cardinality": {"rule": "reviewed_bound_record_count", "source_table": "Spell"},
      "shape": "full_spell_row_v3"
    },
    "coa_client_spell_coa.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-projection-v3",
      "row_schema_version": "coa-client-spell-projection-v3", "optional": false,
      "cardinality": {"rule": "equals_is_coa_full_records"}, "shape": "projection_row_v3"
    },
    "coa_client_spell_icons.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-spell-icons-v1",
      "row_schema_version": "coa-client-spell-icons-v1", "optional": false,
      "cardinality": {"rule": "equals_full_spell_records"}, "shape": "icon_row_v1"
    },
    "coa_client_spell_projection.manifest.json": {
      "kind": "json", "child_schema_version": "coa-client-spell-projection-manifest-v3",
      "row_schema_version": null, "optional": false,
      "cardinality": {"rule": "single_document"}, "shape": "projection_manifest_v3"
    },
    "spell_layout_v2.json": {
      "kind": "json", "child_schema_version": "coa-spell-layout-v2",
      "row_schema_version": null, "optional": false,
      "cardinality": {"rule": "single_document"}, "shape": "spell_policy_v2"
    },
    "generation_contract.json": {
      "kind": "json", "child_schema_version": "coa-generation-contract-v1",
      "row_schema_version": null, "optional": false,
      "cardinality": {"rule": "single_document"}, "shape": "generation_contract_v1"
    },
    "coa_client_archive_plan.json": {
      "kind": "json", "child_schema_version": "coa-client-archive-plan-v1",
      "row_schema_version": null, "optional": false,
      "cardinality": {"rule": "single_document"}, "shape": "archive_plan_v1"
    },
    "coa_client_content.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-content-v1",
      "row_schema_version": "coa-client-content-v1", "optional": false,
      "cardinality": {"rule": "declared_content_derivation"},
      "shape": "content_row_v1"
    },
    "coa_client_advancement.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-advancement-v1",
      "row_schema_version": "coa-client-advancement-v1", "optional": false,
      "cardinality": {"rule": "declared_derivation", "source_table": "CharacterAdvancement"},
      "shape": "advancement_row_v1"
    },
    "coa_client_class_types.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-class-types-v1",
      "row_schema_version": "coa-client-class-types-v1", "optional": false,
      "cardinality": {"rule": "derived_from_source_topology",
                      "source_table": "CharacterAdvancementClassTypes"},
      "shape": "class_type_row_v1"
    },
    "coa_client_tab_types.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-tab-types-v1",
      "row_schema_version": "coa-client-tab-types-v1", "optional": false,
      "cardinality": {"rule": "derived_from_source_topology",
                      "source_table": "CharacterAdvancementTabTypes"},
      "shape": "tab_type_row_v1"
    },
    "coa_client_essence.jsonl": {
      "kind": "jsonl", "child_schema_version": "coa-client-essence-v1",
      "row_schema_version": "coa-client-essence-v1", "optional": false,
      "cardinality": {"rule": "derived_from_source_topology",
                      "source_table": "CharacterAdvancementEssence"},
      "shape": "essence_row_v1"
    }
  }
}
```

- [ ] **Step 4: Implement the loader with full self-validation**

```python
class ContractError(Exception):
    """The generation contract itself is malformed. A broken gate that loads is worse than no gate."""


_TOP_LEVEL_KEYS = {"schema_version", "revision", "note", "observation_wire_schema", "children"}
_CHILD_KEYS = {"kind", "child_schema_version", "row_schema_version", "optional", "cardinality", "shape"}
_CARDINALITY_KEYS = {"rule", "min", "source_table"}
_CARDINALITY_RULES = frozenset({
    "reviewed_bound_record_count", "equals_full_spell_records", "equals_is_coa_full_records",
    "derived_from_source_topology", "declared_derivation", "declared_content_derivation",
    "single_document", "min"})
_SAFE_CHILD_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_generation_contract(doc: dict) -> dict:
    if doc.get("schema_version") != GENERATION_CONTRACT_SCHEMA:
        raise ContractError(f"contract schema_version {doc.get('schema_version')!r}")
    extra_top = set(doc) - _TOP_LEVEL_KEYS
    if extra_top:
        raise ContractError(f"contract has unexpected top-level key(s) {sorted(extra_top)}")
    if not isinstance(doc.get("revision"), str) or not doc["revision"]:
        raise ContractError("contract revision must be a non-empty string")
    wire = doc.get("observation_wire_schema") or {}
    if len(str(wire.get("sha256", ""))) != 64:
        raise ContractError("contract must pin the observation wire schema by sha256")
    children = doc.get("children")
    if not isinstance(children, dict) or not children:
        raise ContractError("contract declares no children")
    seen_shapes = set()
    for name, spec in children.items():
        if not _SAFE_CHILD_NAME.match(name):
            raise ContractError(f"unsafe child name {name!r}: plain filenames only, no path separators")
        if not isinstance(spec, dict):
            raise ContractError(f"child {name!r} spec must be an object")
        extra = set(spec) - _CHILD_KEYS
        if extra:
            raise ContractError(f"child {name!r} has unexpected_key(s) {sorted(extra)}")
        missing = _CHILD_KEYS - set(spec)
        if missing:
            raise ContractError(f"child {name!r} missing {sorted(missing)}")
        if spec["kind"] not in ("jsonl", "json"):
            raise ContractError(f"child {name!r} kind {spec['kind']!r}")
        if not isinstance(spec["child_schema_version"], str) or not spec["child_schema_version"]:
            raise ContractError(f"child {name!r} child_schema_version")
        if spec["kind"] == "jsonl":
            if not isinstance(spec["row_schema_version"], str) or not spec["row_schema_version"]:
                raise ContractError(f"child {name!r} jsonl child needs a row_schema_version")
        elif spec["row_schema_version"] is not None:
            raise ContractError(f"child {name!r} json child must have row_schema_version null")
        if not isinstance(spec["optional"], bool):
            raise ContractError(f"child {name!r} optional must be a boolean")
        if not isinstance(spec["shape"], str) or not spec["shape"]:
            raise ContractError(f"child {name!r} shape must name a validator")
        if spec["shape"] in seen_shapes:
            raise ContractError(f"shape {spec['shape']!r} is reused; each child needs its own shape")
        seen_shapes.add(spec["shape"])
        card = spec["cardinality"]
        if not isinstance(card, dict):
            raise ContractError(f"child {name!r} cardinality must be an object")
        rule = card.get("rule")
        if rule not in _CARDINALITY_RULES:
            raise ContractError(f"child {name!r} cardinality rule {rule!r}")
        # EXACT per-rule key sets, not merely "no unknown keys": `single_document` carrying a `min` or a
        # `source_table` is a contradiction that a permissive check would wave through (E0R.2 T1.1).
        expected_keys = {
            "reviewed_bound_record_count": {"rule", "source_table"},
            "derived_from_source_topology": {"rule", "source_table"},
            "declared_derivation": {"rule", "source_table"},
            "declared_content_derivation": {"rule"},
            "equals_full_spell_records": {"rule"},
            "equals_is_coa_full_records": {"rule"},
            "single_document": {"rule"},
            "min": {"rule", "min"},
        }[rule]
        if set(card) != expected_keys:
            raise ContractError(
                f"child {name!r} cardinality for rule {rule!r} must have exactly {sorted(expected_keys)}, "
                f"got {sorted(card)}")
        if rule == "min":
            floor = card["min"]
            # `isinstance(True, int)` is True in Python — a boolean floor must not silently mean 1.
            if isinstance(floor, bool) or not isinstance(floor, int) or floor < 1:
                raise ContractError(f"child {name!r} min cardinality needs a positive integer floor")
        if "source_table" in expected_keys:
            if not isinstance(card["source_table"], str) or not card["source_table"]:
                raise ContractError(f"child {name!r} {rule} needs a source_table")
    return doc


def generation_contract_sha256(doc: dict) -> str:
    """Canonical digest: sorted keys, no whitespace variance — key order must not change the hash."""
    import hashlib
    import json
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
```

- [ ] **Step 5: Split the required-children concept in `publish.py` — this is what makes the registry
  operational rather than descriptive.**

```python
# The PRODUCER's target: what regenerate must emit today. Derived from the CURRENT revision.
CURRENT_REQUIRED_CHILDREN = tuple(sorted(load_current_contract()[1]["children"]))
# Back-compat alias for existing importers; new code should say which one it means.
REQUIRED_CHILDREN = CURRENT_REQUIRED_CHILDREN


def required_children_for(contract: dict) -> tuple[str, ...]:
    """A RESOLVER's requirement comes from the generation's own verified staged contract, never from
    `current`. Deriving it from `current` would make every generation published under an older revision
    unresolvable the moment a new revision ships — breaking rollback and the predecessor chain the
    publish transaction reads (E0R.2 T1.1)."""
    return tuple(sorted(n for n, s in contract["children"].items() if not s["optional"]))
```

`validate_candidate_generation` and `resolve_active_generation` both use `required_children_for(contract)`.

- [ ] **Step 6: Stage the contract child and extend `binding` in `regenerate`; migrate every synthetic
  fixture to the twelve-child shape.** Introduction and adoption are the same commit, so the suite is
  green at every point.

- [ ] **Step 7: Run the full suite (must be fully green); commit**

```bash
python -m pytest -q && npm --prefix coa_scraper test
git add coa_client_extract/data/generation_contracts/e0r-v1.json \
        coa_client_extract/data/generation_contracts/index.json \
        coa_client_extract/contracts.py coa_client_extract/publish.py coa_client_extract/cli.py \
        tests/_e0r2_fixtures.py tests/test_e0r2_generation_contract.py
git commit -m "feat(e0r2): T1.1 — immutable contract registry, staged, bound, and adopted atomically"
```

### Task 1.2: Reject a tampered, mismatched, or unsupported contract

**Files:**
- Modify: `coa_client_extract/publish.py` (`validate_candidate_generation`, `resolve_active_generation`)
- Test: `tests/test_e0r2_contract_binding.py`

> Staging and binding happened in T1.1 (atomically with adoption). This task adds the **rejection**
> paths: the three-way comparison and registry dispatch. Neither task edits a contract revision file —
> `e0r-v1.json` already lists `generation_contract.json` among its children.

**Design:** the contract revision is staged as `generation_contract.json` (a twelfth child,
self-describing) and `manifest.binding.generation_contract = {"schema_version": ..., "revision": ...,
"sha256": ...}`. `binding` is already inside `TRUST_CRITICAL_MANIFEST_KEYS`, so candidate trust covers
the hash with no change to the digest definition. Validation compares three things: the **staged child
bytes**, the **bound hash**, and a revision in the validator's **own supported registry**. All three
must agree — but the third is a *set* membership, not equality with the current default, which is what
keeps an older published generation resolvable after WS6 adds `e0r-v2`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_contract_binding.py
"""E0R.2 T1.2: a contract read from the working tree is not bound to the generation — a generation
produced under contract A could later be validated under contract B. Stage it, hash it into binding,
cover it with candidate trust, and make the validator compare the staged copy against its OWN trusted
contract so a tampered staged copy is rejected rather than obeyed."""
import json

import pytest

from coa_client_extract.contracts import generation_contract_sha256, load_current_contract
from coa_client_extract.publish import ResolveError, validate_candidate_generation
from tests._e0r2_fixtures import stage_candidate


def test_the_contract_is_staged_as_a_child_and_bound_in_the_manifest(tmp_path):
    gen = stage_candidate(tmp_path)
    manifest = json.loads((gen / "manifest.json").read_text(encoding="utf-8"))
    revision, doc = load_current_contract()
    bound = manifest["binding"]["generation_contract"]
    assert bound["revision"] == revision
    assert bound["sha256"] == generation_contract_sha256(doc)
    assert (gen / "generation_contract.json").is_file()


def test_a_staged_contract_that_differs_from_the_bound_hash_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, tamper_staged_contract={"schema_version": "coa-generation-contract-v1",
                                                            "children": {}})
    with pytest.raises(ResolveError, match="generation_contract"):
        validate_candidate_generation(gen)


def test_a_generation_bound_to_an_unsupported_contract_is_rejected(tmp_path):
    """Both the staged child AND the bound hash say contract B; B is not in the supported registry."""
    gen = stage_candidate(tmp_path, contract_override={"schema_version": "coa-generation-contract-v1",
                                                        "revision": "made-up-v9",
                                                        "children": {"only.jsonl": {}}})
    with pytest.raises(ResolveError, match="unsupported contract revision"):
        validate_candidate_generation(gen)


def test_a_generation_under_a_NON_CURRENT_but_supported_revision_still_validates(tmp_path):
    """Rollback and predecessor-chain resolution depend on this: WS6 adds e0r-v2 and moves `current`,
    and every generation published under e0r-v1 must remain independently resolvable."""
    gen = stage_candidate(tmp_path, contract_revision="e0r-v1", assume_current="e0r-v2")
    validate_candidate_generation(gen)


def test_candidate_trust_covers_the_bound_contract_hash(tmp_path):
    """Rewriting the bound hash without restaging breaks the trust digest."""
    gen = stage_candidate(tmp_path)
    manifest = json.loads((gen / "manifest.json").read_text(encoding="utf-8"))
    manifest["binding"]["generation_contract"]["sha256"] = "0" * 64
    (gen / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ResolveError, match="candidate_trust_sha256"):
        validate_candidate_generation(gen)
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement**

In `validate_candidate_generation` (and identically in `resolve_active_generation`, so a *published*
older-revision generation resolves by the same rules), before any per-child work:

```python
    staged_path = gen_dir / "generation_contract.json"
    if not staged_path.is_file():
        raise ResolveError("generation_contract child missing; the generation is unbound")
    staged = json.loads(staged_path.read_text(encoding="utf-8"))
    staged_sha = generation_contract_sha256(staged)
    bound = (manifest.get("binding") or {}).get("generation_contract") or {}
    if staged_sha != bound.get("sha256"):
        raise ResolveError(
            f"generation_contract: staged child hashes {staged_sha[:16]} but binding names "
            f"{str(bound.get('sha256'))[:16]}")
    try:
        # Set membership, NOT equality with `current`: a generation published under an older supported
        # revision must stay resolvable, or rollback and predecessor-chain reads break the moment a new
        # revision ships (E0R.2 T1.2).
        contract = load_supported_contract(bound.get("revision"), staged_sha)
    except ContractError as exc:
        raise ResolveError(f"generation_contract: unsupported contract revision — {exc}") from exc
    validate_generation_contract(contract)
```

Use `contract` — the registry copy, confirmed to hash-equal the staged child — for all downstream child
checks. Note it is the **registry** copy that is used, not the staged bytes: identical content, but
reading the trusted copy means a future parser difference cannot be exploited through the staged file.

- [ ] **Step 4: Run the full suite; commit**

```bash
git add coa_client_extract/publish.py tests/test_e0r2_contract_binding.py
git commit -m "fix(e0r2): T1.2 — reject a tampered, mismatched, or unsupported staged contract"
```

### Task 1.3: Node re-derives and compares the bound contract

**Files:**
- Modify: `coa_scraper/scripts/lib/generation.mjs:19-25` (delete the mirrored name list)
- Test: `coa_scraper/tests/generation-contract.test.mjs`

**Design:** Node loads its **own** trusted copy of the registry from
`coa_client_extract/data/generation_contracts/` (the same files Python ships, so there is no
hand-mirrored constant to drift), validates the selected revision with an independent implementation of
`validateGenerationContract`, then performs the same three-way comparison — staged bytes, bound hash,
supported-revision membership. Node's canonical-JSON hash must agree byte-for-byte with Python's, and
its supported-revision set must be identical; both equalities are tests.

- [ ] **Step 1: Write the failing test**

```javascript
// coa_scraper/tests/generation-contract.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { loadContractRegistry, loadCurrentContract, generationContractSha256,
         validateCandidateByPath, GenerationResolveError } from "../scripts/lib/generation.mjs";
import { stageCandidate } from "./_e0r2-fixtures.mjs";

test("Node and Python compute the same canonical contract hash", () => {
  const fromPython = execFileSync("python3", ["-c",
    "from coa_client_extract.contracts import generation_contract_sha256, load_current_contract;" +
    "print(generation_contract_sha256(load_current_contract()[1]))"],
    { cwd: "..", encoding: "utf8", env: { ...process.env, PYTHONPATH: ".." } }).trim();
  assert.equal(generationContractSha256(loadCurrentContract()[1]), fromPython);
});

test("Node and Python support exactly the same revision set", () => {
  const fromPython = execFileSync("python3", ["-c",
    "import json;from coa_client_extract.contracts import load_contract_registry;" +
    "r=load_contract_registry();print(json.dumps(sorted(r['supported'])))"],
    { cwd: "..", encoding: "utf8", env: { ...process.env, PYTHONPATH: ".." } }).trim();
  assert.deepEqual(Object.keys(loadContractRegistry().supported).sort(), JSON.parse(fromPython));
});

test("a generation under a non-current but supported revision still validates", (t) => {
  validateCandidateByPath(stageCandidate(t, { contractRevision: "e0r-v1", assumeCurrent: "e0r-v2" }));
});

test("a staged contract that differs from the bound hash is rejected", (t) => {
  const dir = stageCandidate(t, { tamperStagedContract: true });
  assert.throws(() => validateCandidateByPath(dir), /generation_contract/);
});

test("a generation bound to an unsupported contract is rejected", (t) => {
  const dir = stageCandidate(t, { contractOverride: { schema_version: "coa-generation-contract-v1", children: {} } });
  assert.throws(() => validateCandidateByPath(dir), /not the supported contract/);
});

test("the hand-mirrored name list is gone", () => {
  const src = fs.readFileSync(new URL("../scripts/lib/generation.mjs", import.meta.url), "utf8");
  assert.ok(!/REQUIRED_CHILDREN = \[/.test(src), "a mirrored constant is what drifts");
});
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement** `loadGenerationContract`, `validateGenerationContract`,
  `generationContractSha256` (canonical JSON: `JSON.stringify` over recursively key-sorted objects with
  no separators — verify against Python by the first test), and the three-way comparison in
  `validateCandidateByPath`. `REQUIRED_CHILDREN` becomes a derived export.

- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_scraper/scripts/lib/generation.mjs coa_scraper/tests/generation-contract.test.mjs \
        coa_scraper/tests/_e0r2-fixtures.mjs
git commit -m "feat(e0r2): T1.3 — Node re-derives and compares the bound contract"
```

---

# Workstream 2 — real domain enforcement (blocker 1, part 2; blocker 7)

### Task 2.1: Relational cardinalities; unregistered children rejected

**Files:**
- Modify: `coa_client_extract/publish.py`, `coa_scraper/scripts/lib/generation.mjs`
- Test: `tests/test_e0r2_cardinality.py`, `coa_scraper/tests/generation-contract.test.mjs`

**Correction carried from review round 2:** a floor of 1 admits a one-spell generation, and my earlier
claim that an unregistered child is "caught by `candidate_trust_sha256`" was **wrong** — the digest
authenticates an intentionally-added child, it does not reject one.

**Correction carried from review round 3 — the expected count must not come from the manifest.**
Deriving it from `manifest.binding.topology.tables.Spell.header.record_count` is circular: a malformed
candidate sets that count to 1, writes one spell row, recomputes `candidate_trust_sha256`, and satisfies
the equality. The count must be rooted in something the validator trusts **independently of the
candidate**. That is the reviewed policy, which is already pinned by
`coa_scraper/config/spell_layout.lock.json` in both languages.

**The trust chain, in order — each step is a separate assertion with its own message:**

1. The staged `spell_layout_v2.json` child hashes to the **locally supported** policy
   (`compute_policy_sha256(staged) == lock.sha256`), in **both** languages.
2. `manifest.binding.policy_sha256` equals that same hash.
3. `manifest.binding.topology` matches the staged policy's reviewed `bound` **exactly** (per-table
   sha256, header, source) — this is `topology_matches_bound()`, already implemented and used by recon.
4. Child cardinalities are then derived from `policy.bound`, **never** from `manifest.binding.topology`.

**The relational rules** (verified: `spell_layout_v2.json` → `bound.tables.Spell.header.record_count` is
208,447 and equals the full child's record count exactly):

| rule | assertion |
|---|---|
| `reviewed_bound_record_count` | child records **==** `policy.bound.tables.<source_table>.header.record_count` |
| `equals_full_spell_records` | icon-child records **==** full-child records |
| `equals_is_coa_full_records` | projection records **==** count of full rows with `coa_attribution.is_coa is True` |
| `derived_from_source_topology` | child records **==** `policy.bound.tables.<source_table>.header.record_count` (1:1 extraction) |
| `declared_derivation` | manifest declares `{source, kept, rejected}`; validator requires `kept + rejected == policy.bound…record_count` **and** `kept == child records` |
| `single_document` | exactly 1 record |
| `min` | records **>=** floor — **permitted only where no source count exists**, and no child uses it after this task |

`declared_derivation` exists because `coa_client_advancement.jsonl` is a *filtered* projection of
`CharacterAdvancement.dbc` (3,614 rows from a larger table), so equality is wrong but an **accounting
identity** is exactly right: every source row is either kept or explicitly rejected, and the rejection
count is published rather than implied. That closes the "one essence row passes" hole without inventing
a magic number like "21 playable classes" — the client states the number, and the reviewed policy binds
it.

> Every source these rules cite was bound in **T0.2** — the ancillary `CharacterAdvancement*` DBCs
> through `required_tables`/`bound.tables`, and the Content JSON files through `content_sources`. That
> ordering is deliberate: it lets T1.1 author a placeholder-free immutable contract, and it keeps this
> task purely about *enforcement*.

The projection equality is *already* enforced exactly by `_cross_child`'s streaming merge-join
(`projection_is_coa_subset` + `projection_within_domain` compose to an equality). The contract-level
count is a cheap manifest-level pre-check that fails fast with a clearer message — it is not new
coverage, and it must not be treated as replacing the merge-join.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_cardinality.py
"""E0R.2 T2.1: `min_records: 1` is not a domain gate — a one-spell generation passes it. The client
topology records the exact source-domain count, so the contract derives the expectation instead of
guessing a floor."""
import pytest

from coa_client_extract.publish import ResolveError, validate_candidate_generation
from tests._e0r2_fixtures import stage_candidate


def test_a_truncated_full_child_is_rejected(tmp_path):
    """Three spells in the reviewed bound; stage two and restage the manifest honestly."""
    gen = stage_candidate(tmp_path, truncate_full_to=2)
    with pytest.raises(ResolveError, match="reviewed_bound_record_count|2 != 3"):
        validate_candidate_generation(gen)


def test_a_candidate_that_rewrites_its_own_topology_to_match_a_truncation_is_rejected(tmp_path):
    """THE attack the manifest-rooted rule permitted: truncate to one spell, set the manifest topology
    to one, recompute candidate trust. The reviewed policy — not the candidate — states the count."""
    gen = stage_candidate(tmp_path, truncate_full_to=1, forge_manifest_topology_record_count=1)
    with pytest.raises(ResolveError, match="topology does not match the reviewed bound"):
        validate_candidate_generation(gen)


def test_a_staged_policy_that_is_not_the_locally_supported_policy_is_rejected(tmp_path):
    """Step 1 of the trust chain: a candidate cannot bring its own policy and be believed."""
    gen = stage_candidate(tmp_path, forge_staged_policy_bound_record_count=1)
    with pytest.raises(ResolveError, match="staged policy .* not the supported policy"):
        validate_candidate_generation(gen)


def test_a_manifest_policy_hash_that_disagrees_with_the_staged_policy_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, forge_manifest_policy_sha256="0" * 64)
    with pytest.raises(ResolveError, match="binding.policy_sha256"):
        validate_candidate_generation(gen)


def test_an_ancillary_child_truncated_to_one_row_is_rejected(tmp_path):
    """A floor of 1 admitted this: one class-type row is not a generation a class guide can use."""
    gen = stage_candidate(tmp_path, truncate_child=("coa_client_class_types.jsonl", 1))
    with pytest.raises(ResolveError, match="derived_from_source_topology"):
        validate_candidate_generation(gen)


def test_a_declared_derivation_whose_accounting_does_not_close_is_rejected(tmp_path):
    """kept + rejected must equal the reviewed source count; a silent drop breaks the identity."""
    gen = stage_candidate(tmp_path, advancement_derivation={"kept": 2, "rejected": 0})   # source is 3
    with pytest.raises(ResolveError, match="declared_derivation"):
        validate_candidate_generation(gen)


def test_an_icon_catalog_shorter_than_the_full_domain_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, truncate_icons_to=2)
    with pytest.raises(ResolveError, match="equals_full_spell_records"):
        validate_candidate_generation(gen)


def test_a_projection_missing_an_is_coa_row_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, drop_projection_rows=1)
    with pytest.raises(ResolveError, match="equals_is_coa_full_records|projection_is_coa_subset"):
        validate_candidate_generation(gen)


def test_a_json_child_with_more_than_one_document_is_rejected(tmp_path):
    gen = stage_candidate(tmp_path, duplicate_json_document="coa_client_archive_plan.json")
    with pytest.raises(ResolveError, match="single_document"):
        validate_candidate_generation(gen)


def test_an_unregistered_child_is_rejected(tmp_path):
    """candidate_trust_sha256 AUTHENTICATES an added child; it does not reject one."""
    gen = stage_candidate(tmp_path, extra_child=("smuggled.jsonl", b'{"x":1}\n'))
    with pytest.raises(ResolveError, match="unregistered child"):
        validate_candidate_generation(gen)


def test_a_wellformed_candidate_still_validates(tmp_path):
    validate_candidate_generation(stage_candidate(tmp_path))
```

- [ ] **Step 2: Run and confirm the first five fail.**

- [ ] **Step 3: Establish the trust chain, then implement
  `_resolve_cardinality(spec, name, meta, policy, counts)`**

Note the signature takes **`policy`, not `manifest`** — that is the whole correction. Run steps 1–3 of
the trust chain first (staged policy == locally supported policy; `binding.policy_sha256` agrees;
`topology_matches_bound(manifest.binding.topology, policy.bound)` is empty), and only then resolve
cardinalities against `policy.bound`.

All source bindings already exist (T0.2), so this task adds no policy content — only the resolver.

The `is_coa` count is accumulated during the streaming pass `_cross_child` already makes — do not add a
second full read. Reject unregistered children explicitly:

```python
    registered = set(contract["children"])
    for name in children:
        if name not in registered:
            raise ResolveError(
                f"unregistered child {name!r}: the contract is a whitelist, and candidate trust "
                "authenticates an added child rather than rejecting it")
```

- [ ] **Step 4: Mirror in `generation.mjs`; run both suites; commit**

```bash
git add coa_client_extract/publish.py coa_client_extract/spell_layout.py \
        coa_client_extract/cli.py coa_scraper/scripts/lib/generation.mjs \
        tests/_e0r2_fixtures.py tests/test_e0r2_cardinality.py \
        coa_scraper/tests/generation-contract.test.mjs
git commit -m "fix(e0r2): T2.1 — policy-rooted cardinalities and a child whitelist"
```

### Task 2.2: Per-child shape validation in both languages

**Files:**
- Create: `coa_client_extract/shapes.py`, `coa_scraper/scripts/lib/shapes.mjs`
- Modify: `coa_client_extract/publish.py`, `coa_scraper/scripts/lib/generation.mjs`
- Test: `tests/test_e0r2_shapes.py`, `coa_scraper/tests/shapes.test.mjs`

**Correction carried from review round 2:** checking `schema_version` plus top-level key presence
establishes neither field types, nullability, nested envelope shape, nor JSON-document semantics —
`{}` would pass as a one-record JSON artifact.

**Design:** each contract `shape` name maps to a validator function implemented **independently** in
both languages (independent implementations are the point — a shared serialization would reproduce a
shared bug). Each validator asserts: exact key set (no unknown keys), per-key type, explicit
nullability, and nested envelope shape. The two implementations are held together by the shared golden
corpus, which every shape validator runs against in both languages.

- [ ] **Step 1: Write the failing test** — for each shape, a positive case from the golden corpus and
  negative cases for: unknown key, wrong scalar type, null in a non-nullable slot, non-null in a
  must-be-null slot, malformed nested envelope, and (for JSON children) `{}`.

```python
# tests/test_e0r2_shapes.py
"""E0R.2 T2.2: a shape is a type contract, not a key list. `{}` passed as a one-record JSON artifact
because `requires: []` asked nothing of it."""
import pytest

from coa_client_extract.shapes import SHAPES, ShapeError
from tests.golden import golden_rows


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_accepts_its_golden_row(shape):
    SHAPES[shape](golden_rows(shape))


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_rejects_an_unknown_key(shape):
    row = dict(golden_rows(shape)); row["smuggled"] = 1
    with pytest.raises(ShapeError, match="smuggled"):
        SHAPES[shape](row)


def test_an_empty_json_document_is_not_a_valid_archive_plan():
    with pytest.raises(ShapeError):
        SHAPES["archive_plan_v1"]({})


def test_a_full_row_with_a_malformed_raw_envelope_is_rejected():
    row = dict(golden_rows("full_spell_row_v3"))
    row["raw"] = {"id": {"state": "present"}}          # no decoded_reason, no substrate
    with pytest.raises(ShapeError, match="raw.id"):
        SHAPES["full_spell_row_v3"](row)


def test_mechanics_values_may_be_null_but_the_keys_may_not_be_absent():
    row = dict(golden_rows("full_spell_row_v3"))
    row["mechanics"] = {k: None for k in row["mechanics"]}
    SHAPES["full_spell_row_v3"](row)                    # nullable values: fine
    row["mechanics"].pop("school_mask")
    with pytest.raises(ShapeError, match="school_mask"):
        SHAPES["full_spell_row_v3"](row)
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `SHAPES` in Python and `shapes.mjs` in Node**, wired into the streaming row
  loop from T2.1 (one pass, shape-checked per row).
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/shapes.py coa_scraper/scripts/lib/shapes.mjs \
        coa_client_extract/publish.py coa_scraper/scripts/lib/generation.mjs \
        tests/test_e0r2_shapes.py coa_scraper/tests/shapes.test.mjs
git commit -m "fix(e0r2): T2.2 — per-child shape validators in both languages"
```

### Task 2.3: The full observation domain lives in the policy and is validated at load

**Files:**
- Modify: `coa_client_extract/data/spell_layout_v2.json`, `coa_client_extract/spell_layout.py`
  (`load_spell_policy`), `coa_scraper/config/spell_layout.lock.json`
- Test: `tests/test_e0r2_observation_domain.py`

**Correction carried from review round 2:** `required_scalar_fields = ["id","name","power_type",
"school_mask"]` still permits omitting `description`, `cast_time_ms`, `duration_ms`, `range_min_yd`
and `range_max_yd` entirely. **Required means the observation envelope exists, not that a normalized
value exists** — and the real rows already satisfy that: every one of the 208,447 rows carries all nine
raw cells, the join-derived ones in `state: "unresolved"` form. My earlier exclusion of them conflated
"normalized value is null" with "cell absent" and was wrong.

**Correction carried from review round 3 — `school_mask` must stay nullable.** Its policy is verified,
but decoding is still *per-value domain-gated*: `_emit_school` (`spell_record.py:174-178`) returns
`None` when `make_domain_gated_envelope` reports `value_out_of_domain`, so a client patch adding an
unseen school bit nulls the normalized value **by design** and tallies the bit in
`unknown_symbol_inventory`. That is the fail-closed behaviour E0R exists to produce. Asserting
`"school_mask" not in nullable_mechanics_keys` would have made the structural schema contradict the
extractor and broken on the first new school bit.

**Design:** replace the single flat list with an explicit `artifact_contract`, validated in
`load_spell_policy()` rather than left as an unchecked JSON property that only Node consumes. **All six
mechanics keys are structurally nullable**; whether a value is *legitimately* null is a semantic
question the per-row verifier answers (populated iff the cell is present, decoded, and
promotion-eligible), not something a static nullability list can express:

```json
"artifact_contract": {
  "required_raw_observations": ["cast_time_ms", "description", "duration_ms", "id", "name",
                                "power_type", "range_max_yd", "range_min_yd", "school_mask"],
  "required_mechanics_keys": ["cast_time_ms", "duration_ms", "power_type", "range_max_yd",
                              "range_min_yd", "school_mask"],
  "nullable_mechanics_keys": ["cast_time_ms", "duration_ms", "power_type", "range_max_yd",
                              "range_min_yd", "school_mask"],
  "icon_observation_domain": ["spell_icon_id"]
}
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_observation_domain.py
"""E0R.2 T2.3: lossless extraction means every field has an OBSERVATION, even when it has no
normalized value. A raw_only join in `unresolved` state is still a required cell; omitting it is
silent loss, which is exactly what E0R exists to prevent."""
import copy
import json
from pathlib import Path

import pytest

from coa_client_extract.spell_layout import SpellPolicyError, compute_policy_sha256, load_spell_policy

POLICY = Path(__file__).resolve().parents[1] / "coa_client_extract/data/spell_layout_v2.json"


def _policy_doc():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_the_production_policy_requires_the_full_raw_domain():
    contract = _policy_doc()["artifact_contract"]
    assert set(contract["required_raw_observations"]) == {
        "cast_time_ms", "description", "duration_ms", "id", "name", "power_type",
        "range_max_yd", "range_min_yd", "school_mask"}


def test_every_mechanics_key_is_structurally_nullable():
    """Including school_mask: a proven policy still yields a null normalized value when an unseen
    school bit trips the per-value domain gate (value_out_of_domain). Nullability is structural;
    legitimacy is semantic."""
    contract = _policy_doc()["artifact_contract"]
    assert set(contract["nullable_mechanics_keys"]) == set(contract["required_mechanics_keys"])


def test_a_domain_gated_school_mask_row_is_accepted_by_the_structural_schema():
    from coa_client_extract.shapes import SHAPES
    from tests.golden import golden_rows
    row = dict(golden_rows("full_spell_row_v3"))
    row["mechanics"] = {**row["mechanics"], "school_mask": None}
    row["raw"] = {**row["raw"], "school_mask": {**row["raw"]["school_mask"],
                                                "decoded_reason": "value_out_of_domain"}}
    SHAPES["full_spell_row_v3"](row)              # structurally valid


def test_the_semantic_verifier_rejects_a_null_value_whose_cell_decoded_cleanly():
    """The rule static nullability cannot express: null is legitimate ONLY when the cell explains it."""
    from coa_client_extract.shapes import SemanticError, verify_row_semantics
    from tests.golden import golden_rows
    row = dict(golden_rows("full_spell_row_v3"))
    row["mechanics"] = {**row["mechanics"], "school_mask": None}   # but raw says decoded
    with pytest.raises(SemanticError, match="school_mask"):
        verify_row_semantics(row, _policy_doc())


def test_load_spell_policy_rejects_an_incoherent_artifact_contract():
    doc = _policy_doc()
    doc["artifact_contract"]["nullable_mechanics_keys"].append("not_a_field")
    doc["sha256"] = compute_policy_sha256(doc)      # rehash so we test the contract check, not the hash
    with pytest.raises(SpellPolicyError, match="not_a_field"):
        load_spell_policy(doc)


def test_load_spell_policy_rejects_a_missing_artifact_contract():
    doc = _policy_doc()
    del doc["artifact_contract"]
    doc["sha256"] = compute_policy_sha256(doc)
    with pytest.raises(SpellPolicyError, match="artifact_contract"):
        load_spell_policy(doc)
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Add the block, validate it in `load_spell_policy`, and rehash correctly**

`load_spell_policy` raises `policy sha256 mismatch` on an edited document, so
`load_default_policy().sha256` can **never** yield the new hash. Load the JSON directly:

```bash
python -c "
import json, pathlib
from coa_client_extract.spell_layout import compute_policy_sha256
p = pathlib.Path('coa_client_extract/data/spell_layout_v2.json')
doc = json.loads(p.read_text(encoding='utf-8'))
doc.pop('sha256', None)
doc['sha256'] = compute_policy_sha256(doc)
p.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(doc['sha256'])"
```

Write the printed value into `coa_scraper/config/spell_layout.lock.json` in the same commit.

- [ ] **Step 4: Point Node's `verifyFullRowAgainstPolicy` at `artifact_contract` (replacing the
  `policyDoc.required_scalar_fields || []` read at `mechanics-projection.mjs:326`), asserting the raw
  domain, the mechanics key set, and the nullability split.**

- [ ] **Step 5: Run both suites; commit**

```bash
git add coa_client_extract/data/spell_layout_v2.json coa_client_extract/spell_layout.py \
        coa_scraper/config/spell_layout.lock.json coa_scraper/scripts/lib/mechanics-projection.mjs \
        tests/test_e0r2_observation_domain.py
git commit -m "fix(e0r2): T2.3 — the full observation domain is policy-declared and load-validated"
```

### Task 2.4: Publication requires both validations and a clean budget

**Files:**
- Modify: `coa_client_extract/publish.py:171-204` (`finalize_and_publish`),
  `coa_client_extract/cli.py:329-346`
- Test: `tests/test_e0r2_publish_requires_validation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_publish_requires_validation.py
"""E0R.2 T2.4: a generation that failed a trust boundary or its budget must never become the pointer's
target. Consumer-side strictness is a second line of defence, not the gate."""
import pytest

from coa_client_extract.publish import POINTER_NAME, PublishError
from tests._e0r2_fixtures import staged_writer


@pytest.mark.parametrize("validation", [
    {"python": True, "node": False},
    {"python": True, "node": "yes"},       # truthy but not True
    {"python": True},                      # absent
])
def test_publishing_without_both_validations_is_refused(tmp_path, validation):
    gw, candidate = staged_writer(tmp_path)
    with pytest.raises(PublishError, match="validation"):
        gw.finalize_and_publish(candidate_manifest=candidate, validation=validation,
                                budget={"within_budget": True, "breach": []})
    assert not (tmp_path / POINTER_NAME).exists()


@pytest.mark.parametrize("budget", [
    {"within_budget": False, "breach": ["whole_generation bytes ..."]},
    {"within_budget": "ok", "breach": []},               # truthy but not True
    {"within_budget": True, "breach": ["a breach nobody acted on"]},
])
def test_publishing_with_an_unclean_budget_is_refused(tmp_path, budget):
    gw, candidate = staged_writer(tmp_path)
    with pytest.raises(PublishError, match="budget"):
        gw.finalize_and_publish(candidate_manifest=candidate,
                                validation={"python": True, "node": True}, budget=budget)
    assert not (tmp_path / POINTER_NAME).exists()


def test_the_budget_is_recomputed_from_staged_child_metadata(tmp_path):
    """A caller-supplied within_budget must not outrank the staged bytes."""
    gw, candidate = staged_writer(tmp_path, oversized=True)
    with pytest.raises(PublishError, match="budget"):
        gw.finalize_and_publish(candidate_manifest=candidate,
                                validation={"python": True, "node": True},
                                budget={"within_budget": True, "breach": []})


def test_a_fully_validated_within_budget_generation_publishes(tmp_path):
    gw, candidate = staged_writer(tmp_path)
    final = gw.finalize_and_publish(candidate_manifest=candidate,
                                    validation={"python": True, "node": True},
                                    budget={"within_budget": True, "breach": []})
    assert final["publication_state"] == "published"
    assert (tmp_path / POINTER_NAME).is_file()
```

- [ ] **Step 2: Run and confirm failure.**

- [ ] **Step 3: Implement** — `is True` identity checks (not truthiness), `breach == []`, and a
  recomputation of the byte ceilings from `self._children` inside `finalize_and_publish` so the
  caller's verdict cannot outrank the staged metadata. Keep it inside the existing `try:` so the
  `finally: self._release_publish_lock()` still covers the refusal path. Also delete the
  `three_part_budget` escape hatch at `cli.py:341-344`: a policy with no reviewed budget block raises
  `PublishError`, and synthetic test policies get explicit synthetic reviewed budgets.

- [ ] **Step 4: Run the full suite; commit**

```bash
git add coa_client_extract/publish.py coa_client_extract/cli.py \
        tests/test_e0r2_publish_requires_validation.py
git commit -m "fix(e0r2): T2.4 — publication requires both validations and a recomputed clean budget"
```

### Task 2.5: `converted` is prohibited until a bundle validator exists

**Files:**
- Modify: `coa_client_extract/contracts.py:16`, `coa_client_extract/publish.py` (`_verify_icon_row`,
  `_cross_child`), **`coa_client_extract/spell_icons.py:107`** (the producer's own
  `("source_only", "converted")` branch — omitted from the previous draft, which would have made the
  plan's own test fail), `coa_scraper/scripts/lib/generation.mjs:10,128-144,198-200`
- Test: `tests/test_e0r2_converted_prohibited.py`

**Context:** both validators only check that a bundle child *exists* if any row is `converted` — no tar
path containment, no internal manifest, no content hashes. No code path produces `converted`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_converted_prohibited.py
"""E0R.2 T2.5: `converted` promised tar containment, bundle-manifest and content-hash verification that
were never implemented, and nothing produces the status. An unverifiable status with no producer is not
a feature — reject it and reintroduce it WITH its validator."""
import pytest

from coa_client_extract.contracts import ICON_ASSET_STATUSES
from coa_client_extract.publish import ResolveError, _verify_icon_row


def test_converted_is_not_an_admissible_status():
    assert ICON_ASSET_STATUSES == frozenset({"source_only", "missing", "placeholder"})


def test_a_converted_row_is_rejected():
    with pytest.raises(ResolveError, match="converted"):
        _verify_icon_row({"spell_id": 1, "asset_status": "converted",
                          "client_path": "Interface\\Icons\\x", "converted_ref": "bundle:1"})


def test_the_catalog_producer_never_emits_converted(synthetic_icon_backend):
    """Behavioural, not a grep: run the real catalog producer over a client whose icons resolve, are
    missing, and are unjoined, and assert the emitted statuses. A double-quoted-literal scan is
    brittle in both directions — it fires on a comment and misses a computed value."""
    from coa_client_extract.spell_icons import iter_icon_catalog
    statuses = {row["asset_status"] for row in iter_icon_catalog(*synthetic_icon_backend)}
    assert statuses <= {"source_only", "missing", "placeholder"}
    assert statuses == {"source_only", "missing", "placeholder"}   # all three paths exercised
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement**, leaving the reintroduction requirements as a comment at the deleted check:

```python
# E0R.2 T2.5: `converted` (and its icon bundle) is PROHIBITED in this schema. Reintroducing it requires,
# in the same change: tar path containment, per-entry bundle-manifest verification, and per-asset content
# hashes checked against the catalog — the checks the E0R design specified and E0R.1 reduced to an
# existence test. Until then no producer may emit it and no validator may accept it.
```

- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/contracts.py coa_client_extract/publish.py \
        coa_client_extract/spell_icons.py coa_scraper/scripts/lib/generation.mjs \
        tests/test_e0r2_converted_prohibited.py
git commit -m "fix(e0r2): T2.5 — prohibit converted icon assets until the bundle validator exists"
```

---

# Workstream 3 — live join recon and an honest recon budget (blockers 3, 4)

**Blocker 3:** for `reviewed_ambiguous` joins `probe_joins` copies authored evidence *without reading
the side table or scanning the client* (`spell_mechanics.py:147-150`), and `_recon_status` accepts
`pair: null` unconditionally (`:194-196`).

**Blocker 4:** recon estimates `record_count * record_size` (raw DBC bytes) against the retired
`DEFAULT_BUDGET = {512, 4096, 600}`, reporting 186.07 MiB for a 523,026,495-byte generation.

### Task 3.1: A live FK candidate scan runs for every ambiguous join on every recon

**Files:**
- Modify: `coa_client_extract/spell_mechanics.py` (`probe_joins`, new `scan_index_candidates`)
- Test: `tests/test_e0r2_recon_live_joins.py`

**Interfaces:**
- Produces: `scan_index_candidates(view, side_view, *, side_id_cell=0) -> list[dict]` — one entry per
  surviving candidate cell: `{"cell": int, "nonzero_count": int, "valid_count": int, "distinct_ids": int}`.
  Metrics ride along because T3.2 compares them against a reviewed baseline.

**Correction carried from review round 3 — integers only.** The previous draft recorded a float
`valid_fraction` and T3.2 hashed it. Hashing floating-point values is needlessly fragile (repr and
rounding differences across platforms and Python/Node produce different digests for the same client).
Store `valid_count` and `nonzero_count` as integers, hash those, and **derive** the fraction for human
display only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_recon_live_joins.py
"""E0R.2 T3.1: an adjudicated-ambiguous join is still PROBED on every run. Copying the authored verdict
forward means recon cannot notice the day the client makes the join unique — the one thing the hold
exists to catch."""
from coa_client_extract.spell_mechanics import probe_joins, scan_index_candidates
from tests._e0r2_recon_fixtures import ambiguous_backend, unique_backend


def test_an_ambiguous_join_is_scanned_not_asserted():
    probes = probe_joins(*ambiguous_backend())
    cast = probes["casting_time_index"]
    assert cast["scanned"] is True
    assert cast["pair"] is None
    assert len(cast["candidates"]) >= 2
    assert [c["cell"] for c in cast["candidates"]] == sorted(c["cell"] for c in cast["candidates"])
    assert all({"cell", "nonzero_count", "valid_count", "distinct_ids"} == set(c)
               for c in cast["candidates"])
    assert all(isinstance(v, int) and not isinstance(v, bool)
               for c in cast["candidates"] for v in c.values()), "metrics must be integers, not floats"


def test_a_join_that_became_unique_is_recorded_as_unique():
    probes = probe_joins(*unique_backend())
    assert len(probes["casting_time_index"]["candidates"]) == 1


def test_a_missing_side_table_is_distinguishable_from_an_ambiguous_one():
    """Regression: the old path returned before read_effective_file, so the two were identical."""
    backend, root, attach, view, id_to_rec, policy, anchors = ambiguous_backend()
    backend.forget("DBFilesClient\\SpellCastTimes.dbc")
    probe = probe_joins(backend, root, attach, view, id_to_rec, policy, anchors)["casting_time_index"]
    assert probe["scanned"] is False
    assert probe["side_table_missing"] is True
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `scan_index_candidates` and rewire the `reviewed_ambiguous` branch** so it
  opens the side table first (recording `side_table_missing`/`scanned: False` when absent, rather than
  the old silent `continue`) and then scans.
- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/spell_mechanics.py tests/test_e0r2_recon_live_joins.py \
        tests/_e0r2_recon_fixtures.py
git commit -m "fix(e0r2): T3.1 — ambiguous joins are re-scanned live on every recon"
```

### Task 3.2: The reviewed ambiguity is a hash-bound baseline, not a count

**Files:**
- Modify: `coa_client_extract/data/spell_layout_v2.json` (per-join `ambiguity_baseline`),
  `coa_client_extract/spell_mechanics.py:176-202` (`_recon_status`),
  `coa_scraper/config/spell_layout.lock.json`
- Test: `tests/test_e0r2_recon_live_joins.py` (extend)

**Correction carried from review round 2:** accepting "any candidate set of size ≥2" means a change
from candidate cells `{10,11}` to `{90,91}` still verifies. The reviewed policy must hash-bind the scan
**algorithm version and thresholds**, the **expected candidate-cell set**, and the **per-candidate
metrics**; recon requires exact agreement, and any addition, removal, or metric drift is
`review_required`.

Thresholds are expressed as an integer ratio (`valid_num/valid_den`) so neither the stored baseline nor
its digest depends on float formatting:

```json
"ambiguity_baseline": {
  "scan_algorithm": "fk_validity_v1",
  "thresholds": {"min_support": 2, "min_distinct": 2, "valid_num": 99, "valid_den": 100},
  "joins": {
    "casting_time_index": {
      "candidates": [{"cell": 10, "nonzero_count": 190123, "valid_count": 190123, "distinct_ids": 41}, "..."],
      "digest": "<sha256 of the canonical integer candidate list>"
    }
  }
}
```

- [ ] **Step 1: Write the failing test**

```python
def test_a_join_whose_candidate_SET_changed_forces_review():
    """Same count, different cells — the ambiguity did not survive, it was replaced."""
    baseline = _baseline(cells=[10, 11])
    status = _recon_status(**_args(baseline=baseline, scanned={"casting_time_index": [90, 91]}))
    assert status == "review_required"


def test_a_join_whose_metrics_drifted_forces_review():
    status = _recon_status(**_args(baseline=_baseline(cells=[10, 11], distinct_ids=41),
                                   scanned_metrics={"distinct_ids": 12}))
    assert status == "review_required"


def test_a_join_that_collapsed_to_one_candidate_forces_review():
    status = _recon_status(**_args(baseline=_baseline(cells=[10, 11]),
                                   scanned={"casting_time_index": [10]}))
    assert status == "review_required"


def test_an_unscanned_ambiguous_join_forces_review():
    """The exact 02e0b7c behaviour: pair=None with no machine evidence read as verified."""
    status = _recon_status(**_args(join_pairs={"casting_time_index": {
        "pair": None, "adjudication": "reviewed_ambiguous"}}))
    assert status == "review_required"


def test_a_scan_run_under_different_thresholds_forces_review():
    status = _recon_status(**_args(baseline=_baseline(min_distinct=2), scan_thresholds={"min_distinct": 5}))
    assert status == "review_required"


def test_an_exactly_matching_baseline_verifies():
    status = _recon_status(**_args(baseline=_baseline(cells=[10, 11]),
                                   scanned={"casting_time_index": [10, 11]}))
    assert status == "verified"
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Author the baseline from a real recon run** (run T3.1's scan against the live client,
  record the observed candidates verbatim), add it to the policy, rehash with `compute_policy_sha256`
  per T2.3's recipe, update the Node lock, and implement the exact-agreement check in `_recon_status`.
- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/spell_mechanics.py coa_client_extract/data/spell_layout_v2.json \
        coa_scraper/config/spell_layout.lock.json tests/test_e0r2_recon_live_joins.py
git commit -m "fix(e0r2): T3.2 — verified requires exact agreement with a hash-bound ambiguity baseline"
```

### Task 3.3: Recon stops claiming artifact size

**Files:**
- Modify: `coa_client_extract/spell_mechanics.py` (`three_part_budget` → `recon_budget`, `:358-365`,
  `DEFAULT_BUDGET`), `coa_client_extract/cli.py`
- Test: `tests/test_e0r2_recon_budget.py`

**Design:** recon measures a *recon*. `record_count * record_size` is raw DBC bytes — off by 2.8×
against the real 523 MB. Recon gates its own peak RSS and elapsed against the reviewed policy ceilings
and makes no size claim. A serialized-sample forecast is an explicit **non-goal**: a wrong forecast is
worse than none, and publication measures the real thing exactly.

- [ ] **Step 1: Write the failing test** — `recon_budget` reports no `artifact_size_mb`/
  `serialized_bytes`; it breaches on `python_peak_rss_mb`; `DEFAULT_BUDGET` and `three_part_budget` no
  longer exist; recon reads ceilings from `spell_policy.doc["budget"]`.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `recon_budget(*, peak_rss_mb, elapsed_s, ceilings)`, delete `est_bytes`,
  `DEFAULT_BUDGET` and `three_part_budget`, and thread the policy budget through.**
- [ ] **Step 4: Run the full suite; commit**

```bash
git add coa_client_extract/spell_mechanics.py coa_client_extract/cli.py tests/test_e0r2_recon_budget.py
git commit -m "fix(e0r2): T3.3 — recon gates what it measures; the retired hard-coded budget is deleted"
```

---

# Workstream 4 — one internally-executed, generation-bound acceptance (blocker 2)

**Blocker:** `write_acceptance_summary` trusts a caller-supplied `build_mechanics` dict for `executed`,
`exit_code`, `network_attempts` and `pointer_only`; accepts a recon document containing only
`{"status": "verified"}`; binds no recon or mechanics identity to the generation; and silently
substitutes `{}` for absent coverage. *(Precision: the shipped subcommand does always execute the build
first — `cli.py:833-839` — so the committed record came from the executing path. The fabricable surface
is the function API.)*

**Additional finding:** `readiness_coverage` and `source_coverage` have **no producer anywhere** — only
the two reader lines at `cli.py:555-556`. The `{}` is not a dropped measurement; it was never
implemented, while the E0R.1 tracker's T6.2 checkbox claims it is recorded.

### Task 4.1: `observation_coverage` and `field_readiness_coverage` producers

**Files:**
- Modify: `coa_client_extract/spell_record.py`, `coa_client_extract/cli.py`,
  `coa_scraper/scripts/build-mechanics-artifacts.mjs`
- Test: `tests/test_e0r2_coverage_producers.py`, `coa_scraper/tests/coverage.test.mjs`

**Correction carried from review round 2:** raw extraction states are **observation** coverage, not
final mechanics readiness. Two different denominators, two different layers:

| coverage | layer | denominator |
|---|---|---|
| `observation_coverage` | generation manifest | every raw cell of every full row |
| `icon_coverage` | generation manifest | every spell in the domain (already exists) |
| `field_readiness_coverage` | mechanics manifest | Builder-domain mechanics fields, status/reason counts |
| `source_coverage` | mechanics manifest | `per_field_winner_counts_by_source` (already exists) |

- [ ] **Step 1: Write the failing test** — the accumulator counts states and reasons per field with an
  exact `cells` denominator; `regenerate` hoists `observation_coverage`; the mechanics build emits
  `field_readiness_coverage` with status/reason counts and an exact `fields_considered` denominator.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `observation_accumulator()` (single pass, folded into the existing streaming
  write loop) and the Node-side readiness accumulator.**

**Correction carried from review round 4 — a green task cannot defer its own implementation.** The
previous draft said the Node accumulator was "folded into T5.2's incremental statistics" while also
requiring T4.1 to commit green; T5.2 does not exist yet at that point. Implement it here against the
**current** `winnerCounts(rows)`-style builder, and let T5.2 fold it into the streaming loop when it
rewrites that code — a refactor of working, tested code, not a forward reference.
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/spell_record.py coa_client_extract/cli.py \
        coa_scraper/scripts/build-mechanics-artifacts.mjs \
        tests/test_e0r2_coverage_producers.py coa_scraper/tests/coverage.test.mjs
git commit -m "feat(e0r2): T4.1 — observation coverage (generation) and readiness coverage (mechanics)"
```

### Task 4.2: One acceptance command that executes what it attests to

**Files:**
- Modify: `coa_client_extract/cli.py:492-567`, `:833-846`
- Test: `tests/test_e0r2_acceptance_executes.py`

**Interfaces:**
- Produces: `run_acceptance(dist, *, recon_report_path, scraper_dir, builder_entries, mechanics_out,
  benchmark_env_id="local", out=None, node="node") -> dict`. `write_acceptance_summary` is **deleted**.
  Record `schema_version` becomes `coa-e0r-acceptance-summary-v3`.

- [ ] **Step 1: Write the failing test** — `cli` has no `write_acceptance_summary`; `run_acceptance`
  has no `build_mechanics` parameter; a monkeypatched executor returning `exit_code: 1` makes
  `run_acceptance` raise and proves the executor was called.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Fold the executor inside** — resolve → validate recon → **execute** → require executed →
  bind (T4.3) → write.
- [ ] **Step 4: Run; commit**

```bash
git add coa_client_extract/cli.py tests/test_e0r2_acceptance_executes.py
git commit -m "fix(e0r2): T4.2 — acceptance executes the build it attests to; the v2 writer is deleted"
```

### Task 4.3: The record binds recon and mechanics to one generation

**Files:**
- Modify: `coa_client_extract/cli.py` (`run_acceptance`),
  `coa_scraper/scripts/build-mechanics-artifacts.mjs` (record input identities)
- Test: `tests/test_e0r2_acceptance_binding.py`

**Correction carried from review round 2 — the field paths in the previous draft did not exist.** Use
the real schemas (verified by probe):

| what | recon | manifest |
|---|---|---|
| policy hash | `source_pins.policy_sha256` | `binding.policy_sha256` |
| client build | `source_pins.client_build` | `binding.topology.client_build` |
| per-table capture hash | `source_pins.dbc.<T>.sha256` | `binding.topology.tables.<T>.sha256` |
| topology | `topology.tables.<T>` | `binding.topology.tables.<T>` |

Compare via a **canonical recon-binding digest** computed identically from both sides, so the check is
one equality rather than a field-by-field walk that silently skips a key it does not know about.

**Correction carried from review round 3 — "canonical digest" must be spelled out**, or the omission it
is meant to prevent just moves into the digest definition. The digest covers **exactly** this object,
canonical JSON (`sort_keys=True, separators=(",", ":")`), and nothing else:

```python
def recon_binding_digest(*, report_schema_version, status, blocking_findings, policy_sha256,
                         client_build, expected_absent_ok, expected_absent_set, tables) -> str:
    """The complete identity a recon report and a generation manifest must agree on. Enumerated
    explicitly — every field is load-bearing, and an omitted one is a hole:

      report_schema_version  the recon schema this was produced under
      status                 must be "verified"; a digest over a review_required recon must not match
      blocking_findings      must be [] — a recon with findings is not an acceptance input
      policy_sha256          the reviewed policy both sides bound
      client_build           the capture the run describes
      expected_absent_ok +   the reviewed absent-table state (SpellEffect/SpellCooldowns); a client that
      expected_absent_set    started shipping them is a different substrate, not the same one
      tables                 per table: sha256, member, effective_archive, patch_chain, and the FULL
                             header (magic, record_count, field_count, record_size, string_block_size)
    """
```

Built from the recon side out of `source_pins` + `topology`, and from the generation side out of
`binding.policy_sha256` + `binding.topology`. A key present on one side and absent on the other changes
the digest, which is the point.

**Correction carried from review round 4 — the identity digest does not attest to the artifact.** By
construction it covers only the fields that must *match* the generation. Everything else in the recon
report — the ambiguity scan's candidate metrics, the budget measurements, `proposed_policy_delta`,
`index_fk` — is outside it, so that content could change with the acceptance record unmoved. Record
**both**, and commit the report bytes as E0R.1 already did:

- `recon_binding_sha256` — the canonical identity digest above, which is what is *compared*.
- `recon_report_sha256` — sha256 of the **exact normalized report bytes** that were validated and
  embedded, which is what is *attested*.

with a probe that mutates a **non-binding** field (a candidate's `distinct_ids`) and asserts
`recon_binding_sha256` is unchanged while `recon_report_sha256` moves. Two hashes with different jobs;
neither substitutes for the other.

**Mechanics binding, strengthened:**
1. The mechanics manifest records `input_generation_id`, `pointer_manifest_sha256`, `policy_sha256`,
   `projection_child_sha256`, and `builder_entries_sha256`.
2. Acceptance **hashes and counts the emitted mechanics JSONL itself** rather than trusting the
   manifest's claimed output hash.
3. **Completeness, not non-emptiness:** the mechanics record count must equal the number of **unique
   Builder spell ids** in `coa_entries.jsonl`. `record_count > 0` would accept a build that silently
   dropped 3,000 of 3,600 spells — which is precisely the class of silent loss this milestone exists to
   catch, and `builder_missing_from_projection` does not cover it because it checks the *projection*,
   not the *output*.
4. After the build, re-resolve the pointer and compare **both** `generation_id` **and**
   `manifest_sha256`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_acceptance_binding.py
"""E0R.2 T4.3: the record must prove the measurements and the generation are the same run. At 02e0b7c a
recon document containing only {"status": "verified"} was accepted, and a concurrent publish between
resolve and build would have combined two generations' measurements into one attestation."""
import pytest

from coa_client_extract.cli import AcceptanceError, run_acceptance
from tests._e0r2_fixtures import acceptance_env


def test_a_bare_status_only_recon_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="source_pins"):
        run_acceptance(**acceptance_env(tmp_path, recon={"status": "verified"}))


def test_a_recon_bound_to_a_different_policy_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_policy_sha256="0" * 64))


def test_a_recon_bound_to_a_different_client_capture_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_table_sha256={"Spell": "f" * 64}))


def test_a_pointer_that_moved_during_the_build_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="pointer moved"):
        run_acceptance(**acceptance_env(tmp_path, republish_during_build=True))


def test_a_pointer_whose_manifest_hash_changed_is_refused(tmp_path):
    """Same generation_id, rewritten manifest — id equality alone would have missed it."""
    with pytest.raises(AcceptanceError, match="manifest_sha256"):
        run_acceptance(**acceptance_env(tmp_path, rewrite_manifest_during_build=True))


def test_a_mechanics_manifest_claiming_a_hash_the_jsonl_does_not_have_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="mechanics jsonl sha256"):
        run_acceptance(**acceptance_env(tmp_path, forge_mechanics_output_hash=True))


def test_a_mechanics_build_bound_to_another_generation_is_refused(tmp_path):
    with pytest.raises(AcceptanceError, match="input_generation_id"):
        run_acceptance(**acceptance_env(tmp_path, mechanics_input_generation_id="deadbeef"))


@pytest.mark.parametrize("missing", ["observation_coverage", "icon_coverage"])
def test_absent_generation_coverage_fails_instead_of_becoming_an_empty_object(tmp_path, missing):
    with pytest.raises(AcceptanceError, match=missing):
        run_acceptance(**acceptance_env(tmp_path, drop_manifest_keys=[missing]))


@pytest.mark.parametrize("missing", ["field_readiness_coverage", "per_field_winner_counts_by_source"])
def test_absent_mechanics_coverage_fails(tmp_path, missing):
    with pytest.raises(AcceptanceError, match=missing):
        run_acceptance(**acceptance_env(tmp_path, drop_mechanics_keys=[missing]))


def test_an_incomplete_mechanics_build_is_refused(tmp_path):
    """record_count > 0 would accept a build that dropped 3,000 of 3,600 spells."""
    with pytest.raises(AcceptanceError, match="record_count .* builder spell"):
        run_acceptance(**acceptance_env(tmp_path, drop_mechanics_rows=1))


def test_a_recon_with_blocking_findings_cannot_match_the_digest(tmp_path):
    """status and blocking_findings are INSIDE the digest, so a doctored status alone cannot pass."""
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_blocking=[{"field": "x", "reason": "y"}]))


def test_a_client_that_started_shipping_an_expected_absent_table_is_refused(tmp_path):
    """expected_absent state is part of the substrate identity, not a detail."""
    with pytest.raises(AcceptanceError, match="recon binding digest"):
        run_acceptance(**acceptance_env(tmp_path, recon_expected_absent_ok=False))


def test_a_non_binding_recon_edit_moves_the_report_hash_but_not_the_identity_digest(tmp_path):
    """The two hashes have different jobs. Identity is what must MATCH the generation; the report hash
    is what the record ATTESTS to. Only recording the first would let candidate metrics, budget
    measurements or proposed_policy_delta change with the acceptance record unmoved."""
    base = run_acceptance(**acceptance_env(tmp_path))
    edited = run_acceptance(**acceptance_env(tmp_path, recon_candidate_distinct_ids=999))
    assert edited["recon_binding_sha256"] == base["recon_binding_sha256"]
    assert edited["recon_report_sha256"] != base["recon_report_sha256"]


def test_the_record_binds_every_identity(tmp_path):
    record = run_acceptance(**acceptance_env(tmp_path))
    assert record["schema_version"] == "coa-e0r-acceptance-summary-v3"
    assert len(record["recon_binding_sha256"]) == 64
    assert len(record["recon_report_sha256"]) == 64
    assert record["recon_report"]["status"] == "verified"       # the bytes themselves are committed
    assert record["generation_contract"]["revision"]
    assert len(record["generation_contract"]["sha256"]) == 64
    assert len(record["mechanics"]["jsonl_sha256"]) == 64
    assert record["mechanics"]["record_count"] == record["mechanics"]["builder_unique_spell_ids"]
    assert record["coverage"]["observation"]["cells"] > 0
    assert record["coverage"]["readiness"]["fields_considered"] > 0
    assert record["coverage"]["source"]
```

- [ ] **Step 2: Run and confirm every probe fails.**
- [ ] **Step 3: Implement** `recon_binding_digest(source_pins, topology)` (canonical, computed
  identically from the recon report and from `manifest.binding`), the mechanics input-identity block in
  the Node build, independent hashing of the emitted JSONL, the two-field pointer recheck, and
  fail-closed coverage. Record the generation contract schema and hash in the summary.
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/cli.py coa_scraper/scripts/build-mechanics-artifacts.mjs \
        tests/test_e0r2_acceptance_binding.py
git commit -m "fix(e0r2): T4.3 — acceptance binds recon, contract, coverage and mechanics to one generation"
```

---

# Workstream 5 — the canonical build streams end to end (blocker 5)

**Blocker:** the canonical mechanics path does `readFileSync` → `.toString("utf8")` → `.split("\n")` →
accumulate a `projection` array and a `clientById` Map over all of it, then retains the full output
array (`mechanics-projection.mjs:339-385`, `build-mechanics-artifacts.mjs:37-49,102-133,386-423`). The
E0R.1 design named "projection consumption → mechanics serialization" as in scope; the T4.2 RSS test
covers candidate validation instead. Node peaked at 866 MB on the real run.

**Key observation:** `buildCanonicalMechanics` emits one row per **Builder** spell (~3,600), not per
projection row (10,410). The projection is only a lookup, so the streaming pass needs to retain only
rows whose `spell_id` is in `builderSpellIds`.

### Task 5.1: Streaming projection consumption

**Files:**
- Create: `coa_scraper/scripts/lib/jsonl-stream.mjs`
- Modify: `coa_scraper/scripts/lib/mechanics-projection.mjs:339-385`,
  `coa_scraper/scripts/lib/generation.mjs` (import the shared primitive instead of defining it)
- Test: `coa_scraper/tests/mechanics-streaming.test.mjs`, `coa_scraper/tests/jsonl-stream.test.mjs`

**Correction carried from review round 3 — importing `readJsonlLines` back would create a cycle.**
`generation.mjs:6` already imports `assertPolicyLock`, `verifyRowAgainstPolicy`,
`verifyFullRowAgainstPolicy` and `expandCompact` **from** `mechanics-projection.mjs`, and
`readJsonlLines` is defined **in** `generation.mjs`. Extract the primitive into a leaf module
`jsonl-stream.mjs` that neither imports, exporting `readJsonlLines(path)` and
`readJsonlLinesHashed(path)` — the latter yielding rows while feeding the **exact bytes read** into a
running sha256, so the incremental digest provably equals a whole-file hash. Both modules import it.

**Interfaces:**
- Produces: `streamAndValidateProjectionV3({...}) -> { absent: false, clientById: Map, coverage,
  projection_sha256, manifest_sha256, client_build }`. The `projection` array is **gone**.

- [ ] **Step 1: Write the failing test** — the function source contains no `readFileSync(projectionPath`
  and no whole-file `.split`; only builder-domain rows are retained (`clientById.size === 3` over a
  5,000-row projection); **every** row is still validated (a corruption at line 73 throws even though
  only spell 1 is retained); the incremental hash equals the whole-file hash.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement** over the existing `readJsonlLines` generator, hashing incrementally, keeping
  every per-row check and the `seen` id set (counter-scale, ~10k ints).
- [ ] **Step 4: Run; commit**

```bash
git add coa_scraper/scripts/lib/jsonl-stream.mjs coa_scraper/scripts/lib/mechanics-projection.mjs \
        coa_scraper/scripts/lib/generation.mjs coa_scraper/scripts/build-mechanics-artifacts.mjs \
        coa_scraper/tests/jsonl-stream.test.mjs coa_scraper/tests/mechanics-streaming.test.mjs
git commit -m "perf(e0r2): T5.1 — the canonical build streams the projection instead of reading it whole"
```

### Task 5.2: Generator mechanics rows and incremental statistics

**Files:**
- Modify: `coa_scraper/scripts/build-mechanics-artifacts.mjs`
- Test: `coa_scraper/tests/mechanics-streaming.test.mjs` (extend)

- [ ] **Step 1: Record a golden output hash from the CURRENT implementation first**, so the refactor is
  provably output-preserving; then write the tests: `buildCanonicalMechanics` returns an iterator, not
  an array; no `rows.length` or `winnerCounts(rows)` remains; the artifact sha256 equals the golden.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement** — `function*` yielding ascending rows; `writeArtifact` folds
  `statsAccumulator()` (bySource, byTier, aggregates, and T4.1's `field_readiness_coverage`) into its
  existing write loop with a `recordCount` counter.
- [ ] **Step 4: Run; commit**

```bash
git add coa_scraper/scripts/build-mechanics-artifacts.mjs coa_scraper/tests/mechanics-streaming.test.mjs
git commit -m "perf(e0r2): T5.2 — mechanics rows are generated and counted incrementally"
```

### Task 5.3: A bounded-retention RSS gate through the real canonical build

**Files:**
- Create: `coa_scraper/tests/_canonical_build_probe.mjs`
- Modify: `coa_scraper/tests/generation-streaming.test.mjs`

**Correction carried from review round 2:** the growth is not literally sub-linear — the retained id set
grows with projection size. The property under test is **bounded row retention**: RSS must not grow in
proportion to the *projection row count*, measured as an absolute delta against a pinned threshold.

- [ ] **Step 1: Write the failing test** — run the **actual** `buildMechanicsArtifact` entry point in an
  isolated subprocess at 10k and 100k projection rows with a fixed ~3,600-spell builder domain; assert
  the `peak_rss_mb` delta is `< 150` **and** that the 100k peak is under
  `node_peak_rss_mb / 2 == 2048 MB`, derived from the reviewed policy budget rather than invented, and
  valid only under the `benchmark_env` the manifest pins (the same environment the T4.3 budget
  measurements are attributed to; a different machine invalidates the absolute number, not the delta).
  Mirror `tests/_streaming_probe.py`'s try/finally temp-dir cleanup — that leak produced a false "memory
  regression" during E0R.1 when it filled the tmpfs.
- [ ] **Step 2: Verify the probe is real** by stashing T5.1 locally and watching it fail.
- [ ] **Step 3: Commit**

```bash
git add coa_scraper/tests/_canonical_build_probe.mjs coa_scraper/tests/generation-streaming.test.mjs
git commit -m "test(e0r2): T5.3 — bounded-retention RSS gate through the real canonical build"
```

---

# Workstream 6 — real E1 headroom (blocker 6)

**Blocker:** the real generation is 523,026,495 of 536,870,912 bytes — **97.42%**, leaving 13.2 MiB
against a design exit condition of "substantial E1 headroom."

**Measured attribution** (20,000-row sample, extrapolated to 208,447; per-field constancy verified over
50,000 rows; cell-shape distribution verified over all 208,447):

| component | share | extrapolated | nature |
|---|---|---|---|
| `policy_ref` | 23.6% | 88.6 MB | **constant per field** (1 distinct value per field) |
| `decoded_reason` | 14.8% | 55.4 MB | closed vocabulary (T0.1) |
| `state` | 9.7% | 36.3 MB | closed vocabulary (T0.1) |
| `resolved` | 6.0% | 22.4 MB | descriptions; only 35% dedupable |
| `join_name` | 5.9% | 22.3 MB | **constant per field** |
| icons child | — | 66.1 MB | 14,022 unique paths across 179,774 resolved rows |

The review's first round proposed a description/string dictionary as the strongest opportunity. The
measurement says otherwise: descriptions are mostly unique and dedup to ~8 MB. The dominant redundancy
is per-cell **constant metadata** (111 MB) and **low-cardinality enums** (92 MB). Hoisting, interning,
and normalizing icons projects **~298 MB (55% of ceiling)** without touching descriptions.

**Sequencing so every commit stays green:** T6.1 *expands* (add descriptors, both encodings supported),
T6.2 and T6.3 *migrate and contract atomically* (producer + both validators + contract + golden corpus
in one commit each).

### Task 6.1: Kind-aware field descriptors (expand)

**Files:**
- Create: descriptor producer in `coa_client_extract/spell_record.py`
- Modify: `coa_client_extract/spell_record.py`, `coa_client_extract/publish.py`,
  `coa_scraper/scripts/lib/mechanics-projection.mjs`, `coa_scraper/scripts/lib/generation.mjs`
- Test: `tests/test_e0r2_field_descriptors.py`, `coa_scraper/tests/descriptors.test.mjs`

**Correction carried from review round 2:** a single `policy_ref` per field **cannot** reconstruct a
resolved join. `_compact_join` emits `components.{index,side_id,side_value}`, each with its own
`policy_ref` (via `policy_ref_component`). Descriptors must be kind-aware:

```json
{
  "schema_version": "coa-client-spell-fields-v1",
  "fields": {
    "school_mask": {"kind": "scalar", "policy_ref": "/tables/Spell/fields/school_mask"},
    "cast_time_ms": {
      "kind": "join",
      "join_name": "cast_time_ms",
      "index_policy_ref": "/tables/Spell/fields/casting_time_index",
      "components": {
        "index":      {"policy_ref": "/tables/Spell/fields/casting_time_index"},
        "side_id":    {"policy_ref": "/tables/SpellCastTimes/fields/id"},
        "side_value": {"policy_ref": "/tables/SpellCastTimes/fields/base_ms"}
      }
    }
  }
}
```

`index_policy_ref` serves the *absent-join* form (null index cell), `components` the *resolved* form.
**Both validators must independently derive the expected descriptor from the policy and reject a staged
descriptor that differs** — otherwise a tampered descriptor could redefine meanings while keeping
compact→rich expansion internally self-consistent.

> Today every cell in all 208,447 rows is `scalar` or `join-absent`, so the resolved-join path is
> unexercised by real data — but it is reachable the moment a join is adopted, which is exactly what E1
> does. The golden corpus must therefore include a resolved-join row.

- [ ] **Step 1: Write the failing test** — descriptors round-trip all three cell shapes (scalar,
  absent join, resolved join with three component refs); the derived descriptor equals the policy-derived
  expectation in **both** languages; a staged descriptor that differs from the policy-derived one is
  rejected; the golden corpus gains a resolved-join row.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `build_field_descriptors(policy)` + `derive_expected_descriptors(policy)` in
  both languages. `_expand_compact` and `expandCompact` gain a descriptors argument.** Both encodings
  (with and without inline `policy_ref`) are accepted at this step — that is what keeps the tree green.
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/spell_record.py coa_client_extract/publish.py \
        coa_scraper/scripts/lib/mechanics-projection.mjs coa_scraper/scripts/lib/generation.mjs \
        tests/golden/e0r1_corpus tests/test_e0r2_field_descriptors.py \
        coa_scraper/tests/descriptors.test.mjs
git commit -m "feat(e0r2): T6.1 — kind-aware field descriptors derived and cross-checked from the policy"
```

### Task 6.2: v4 spell rows — hoist and intern (migrate + contract, atomic)

**Files:** producer, both validators, a **new** `data/generation_contracts/e0r-v2.json` plus
`index.json` moving `current` (never an edit to `e0r-v1.json`), golden corpus — **one commit**.

**Design:** compact cells drop `policy_ref`/`join_name` (restored from descriptors) and carry `s`/`d`
integer codes from T0.1's shared **observation wire schema** — read by each language from its own
trusted copy, never from the staged descriptor. An out-of-range code fails closed. The projection stays
`coa-client-spell-projection-v3` because `expand_compact` absorbs the change, keeping
`expand_compact(full.raw) == projection.field_observations` literally true.

**This commit is atomic and must include all of:**
- `coa_client_spell.jsonl` → `coa-client-spell-v4` (producer + both validators)
- **`coa_client_spell_fields.json` staged as a child** — the descriptor document T6.1 introduced now
  ships *in* the generation, so expansion has a bound source
- **the staged `observation_wire_schema.json`**, since v4 rows carry coded observations and a generation
  must ship every schema needed to decode it
- a **new contract revision `e0r-v2`** in the registry adding those children (each with its own
  `shape` validator in both languages) and bumping the full child's schema, plus `index.json` moving
  `current` to `e0r-v2` — `e0r-v1` is **not edited**
- **the v3 decoder and v1 shape validators RETAINED**, and v4 fixtures **added alongside** the v3 golden
  corpus rather than replacing it

**Correction carried from review round 4 — "migrate the corpus" and "drop dual-encoding" contradict the
registry.** `e0r-v1` stays in `supported`, so an `e0r-v1` generation must still validate and still
expand. That is impossible if the v3 decoder is deleted or its fixtures overwritten. Concretely:
`expand_compact` dispatches on the row's schema version, keeping both paths; the golden corpus gains
`tests/golden/e0r2_corpus_v4/` **next to** `tests/golden/e0r1_corpus/`; and both shape validators stay
registered. The dual-encoding *tolerance* T6.1 added inside a single schema is what goes away — a v4 row
must be v4-encoded — not the ability to read v3 rows.

- [ ] **Step 1: Write the failing test** — round-trip equality per vocabulary member and per cell shape;
  an out-of-range code raises; codes come from `contracts.py` and **not** from the staged descriptor
  (mutate the staged copy's vocabulary and assert the expansion is unaffected or rejected); the
  cross-child equality still holds in both languages; measured bytes for the golden corpus drop.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement in `_compact`/`_compact_join`/`_expand_compact` and `expandCompact`; bump the
  contract's `coa_client_spell.jsonl` entry to v4; migrate the golden corpus; drop the dual-encoding
  support added in T6.1.**
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/spell_record.py coa_client_extract/cli.py coa_client_extract/publish.py \
        coa_client_extract/shapes.py coa_scraper/scripts/lib/mechanics-projection.mjs \
        coa_scraper/scripts/lib/generation.mjs coa_scraper/scripts/lib/shapes.mjs \
        coa_client_extract/data/generation_contracts/e0r-v2.json \
        coa_client_extract/data/generation_contracts/index.json \
        tests/golden/e0r2_corpus_v4 tests/test_e0r2_field_descriptors.py \
        coa_scraper/tests/descriptors.test.mjs
git commit -m "perf(e0r2): T6.2 — v4 spell rows: hoist per-field constants, intern vocabularies (-188 MB)"
```

### Task 6.3: Icon v2 — normalized assets (migrate + contract, atomic)

**Files:** `coa_client_extract/spell_icons.py`, `cli.py`, `publish.py`, `generation.mjs`, the `coa_meta`
icon consumer, a **new** `data/generation_contracts/e0r-v3.json` plus `index.json` moving `current`,
golden corpus — **one commit**.

**Correction carried from review round 2 — the previous model was internally ambiguous.** It said
`asset_ref` is null only for `placeholder` while requiring every asset row to carry
`source_asset_sha256` and `source_archive`; a `missing` asset (proven path, absent member) has neither.
Explicit model:

- **Asset row** = one normalized client path.
  `{asset_id, client_path, availability: "source_only" | "missing", source_asset_sha256, source_archive, schema_version}`
  Hash and archive are non-null **iff** `availability == "source_only"`, null **iff** `"missing"`.
- **Association row** = `{spell_id, spell_icon_id, asset_ref, state, decoded_reason, readiness,
  schema_version}`. `asset_ref` is null **iff no promoted decoded client path exists**; `readiness` is
  `"available"` iff `asset_ref` resolves to a `source_only` asset — and the cross-child check enforces
  that derivation rather than trusting the stored value.

**Correction carried from review round 4 — "null iff the join is unresolved" is too narrow, and the
current schema throws information away.** Verified in `spell_icons.py`: the path is
`jo.decoded if jo.decoded_reason == "decoded" else None`, so **four** distinct situations collapse into
one `_placeholder` — `index_zero` (no FK at all → `not_applicable`), `side_row_missing` (nonzero FK, no
side row → `unresolved`), `proof_withheld`, and `non_finite`. Worse, the producer *constructs* the
`JoinObservation` for the first two cases at lines 62 and 67 and then **discards it**. Carrying `state`
and `decoded_reason` onto the association row costs two small interned integers and turns an
unexplained null into an explained one — "this spell has no icon" and "this spell's icon row is missing
from the client" stop being the same value.

**The two children, with their exact contract entries** (added by the new `e0r-v3` revision):

```json
"coa_client_spell_icons.jsonl": {
  "kind": "jsonl", "child_schema_version": "coa-client-spell-icons-v2",
  "row_schema_version": "coa-client-spell-icons-v2", "optional": false,
  "cardinality": {"rule": "equals_full_spell_records"}, "shape": "icon_association_row_v2"
},
"coa_client_icon_assets.jsonl": {
  "kind": "jsonl", "child_schema_version": "coa-client-icon-assets-v1",
  "row_schema_version": "coa-client-icon-assets-v1", "optional": false,
  "cardinality": {"rule": "equals_referenced_asset_set"}, "shape": "icon_asset_row_v1"
}
```

`equals_referenced_asset_set` is a new relational rule: asset records **==** the number of distinct
non-null `asset_ref` values in the association child. Combined with the cross-child checks below it
makes the two children exactly mutually determined.

**Cross-child checks (streaming, in the existing merge-join pass):**
- association records == full-spell records, in lockstep by ascending `spell_id`
- asset rows sorted-unique by `asset_id`
- every non-null `asset_ref` resolves to an asset row (**no dangling**)
- every asset row is referenced at least once (**no orphans**)
- `readiness == "available"` **iff** the referenced asset is `source_only`
- `asset_ref is None` **iff** `decoded_reason != "decoded"`
- **`asset_id` is deterministic**: `sha256(canonical_path)[:32]` — **128 bits**, where `canonical_path`
  is the client path lowercased with backslashes normalized to forward slashes. Encounter-order
  numbering would make byte-identical inputs produce different generations. The previous draft's 64-bit
  truncation is unnecessarily tight; and regardless of width the producer **rejects any collision**
  where one `asset_id` maps to two distinct canonical paths, so identity never rests on a probability
  argument. Cost of the wider id: 14,022 rows × 16 chars ≈ 224 KB.

- [ ] **Step 1: Write the failing test** — a dangling `asset_ref` is rejected; an orphan asset row is
  rejected; a null `asset_ref` with `readiness: "available"` is rejected; a non-null `asset_ref` whose
  `decoded_reason != "decoded"` is rejected; a `missing` asset carrying a hash is rejected; a
  `source_only` asset without a hash is rejected; the four null causes (`index_zero`,
  `side_row_missing`, `proof_withheld`, `non_finite`) are **distinguishable** in the emitted rows rather
  than collapsed; `asset_id` is stable across two runs with shuffled input order; **an injected
  collision** — two distinct canonical paths forced to the same `asset_id` via a monkeypatched digest —
  raises rather than silently coalescing two icons into one; `icon_coverage` reports the same
  `resolved_paths`/`unique_paths` totals as the v1 catalog for identical input.
- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement**, accumulating `canonical_path -> asset_id` during the single existing
  catalog pass (14,022 entries — counter-scale) and **storing the canonical path itself** on the asset
  row, so a shuffled input cannot change any row's bytes. Update both validators, add the `e0r-v3`
  revision, add v2 fixtures alongside the v1 ones, retain the v1 icon shape validator while `e0r-v1`
  and `e0r-v2` remain supported, and update the `coa_meta` consumer to resolve through the asset table.
- [ ] **Step 4: Run both suites; commit**

```bash
git add coa_client_extract/spell_icons.py coa_client_extract/cli.py coa_client_extract/publish.py \
        coa_client_extract/shapes.py coa_scraper/scripts/lib/generation.mjs \
        coa_scraper/scripts/lib/shapes.mjs coa_meta/guide_assets.py \
        coa_client_extract/data/generation_contracts/e0r-v3.json \
        coa_client_extract/data/generation_contracts/index.json \
        tests/golden/e0r2_corpus_v4 tests/test_e0r2_icon_normalization.py \
        coa_scraper/tests/icon-assets.test.mjs
git commit -m "perf(e0r2): T6.3 — icon v2: two-child normalized assets with explained nulls (-37 MB)"
```

### Task 6.4: The compatibility matrix — prove the registry is operational

**Files:**
- Test: `tests/test_e0r2_cross_revision.py`, `coa_scraper/tests/cross-revision.test.mjs`

**Correction carried from review round 4 — without this the registry is descriptive, not operational.**
Three revisions now exist and all three are `supported`; nothing yet *proves* an older one still
resolves.

- [ ] **Step 1: Write the test (it should already pass if T1.1–T6.3 were done correctly; if it fails,
  the registry promise was never real)**

```python
# tests/test_e0r2_cross_revision.py
"""E0R.2 T6.4: the registry promises that a generation published under an older supported revision
stays independently resolvable — that is what rollback and the publish transaction's predecessor read
depend on. This is the test that makes the promise operational."""
import pytest

from coa_client_extract.contracts import load_contract_registry
from coa_client_extract.publish import ResolveError, resolve_active_generation, validate_candidate_generation
from tests._e0r2_fixtures import publish_generation_under


@pytest.mark.parametrize("revision", ["e0r-v1", "e0r-v2", "e0r-v3"])
def test_a_generation_of_every_supported_revision_validates_and_resolves(tmp_path, revision):
    assert revision in load_contract_registry()["supported"]
    dist = publish_generation_under(tmp_path, revision)
    resolved = resolve_active_generation(dist)
    assert resolved["manifest"]["binding"]["generation_contract"]["revision"] == revision


@pytest.mark.parametrize("revision, foreign_child", [
    ("e0r-v1", "coa_client_spell_fields.json"),        # v2 introduced it
    ("e0r-v1", "coa_client_icon_assets.jsonl"),        # v3 introduced it
    ("e0r-v2", "coa_client_icon_assets.jsonl"),
])
def test_a_generation_carrying_a_child_from_another_revision_is_rejected(tmp_path, revision, foreign_child):
    gen = publish_generation_under(tmp_path, revision, extra_child=foreign_child, publish=False)
    with pytest.raises(ResolveError, match="unregistered child"):
        validate_candidate_generation(gen)


@pytest.mark.parametrize("revision, encoding", [("e0r-v1", "v4_coded"), ("e0r-v3", "v3_inline")])
def test_a_generation_using_another_revisions_encoding_is_rejected(tmp_path, revision, encoding):
    """A v1 generation must not carry interned cells, and a v3 generation must not carry inline
    policy_refs — each revision pins exactly one encoding."""
    gen = publish_generation_under(tmp_path, revision, force_encoding=encoding, publish=False)
    with pytest.raises(ResolveError, match="schema_version|encoding"):
        validate_candidate_generation(gen)


def test_the_v3_decoder_survives(tmp_path):
    """The concrete regression this guards: deleting the v3 expansion path during the v4 migration."""
    from coa_client_extract.spell_record import _expand_compact
    from tests.golden import golden_v3_cell, golden_v3_expected
    assert _expand_compact(golden_v3_cell(), _policy(), fields=None) == golden_v3_expected()
```

The Node twin asserts the same matrix through `validateCandidateByPath`.

- [ ] **Step 2: Run both suites; commit**

```bash
git add tests/test_e0r2_cross_revision.py coa_scraper/tests/cross-revision.test.mjs
git commit -m "test(e0r2): T6.4 — cross-revision compatibility matrix over the contract registry"
```

---

# Workstream 7 — CI, hygiene, documentation

### Task 7.1: CI runs `npm test`; path hygiene over tracked text

**Files:**
- Modify: `.github/workflows/ci.yml:46-47`, the artifact producers
- Create: `tests/test_e0r2_path_hygiene.py`

**Context:** CI runs `npm --prefix coa_scraper run unit-test`, but `npm test` is
`unit-test && validate` — so `validate-normalized.mjs` has never been a merge gate. Eight tracked files
contain a machine-local home path, **including this plan's earlier draft**.

**Correction carried from review round 2:** do **not** hash the absolute client-root path — that makes
otherwise identical runs machine-dependent. Omit it, or record a symbolic label; archive names and
content hashes carry the actual identity.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e0r2_path_hygiene.py
"""E0R.2 T7.1: a tracked artifact is a published artifact. Machine-local absolute paths leak the
author's filesystem layout and make records non-reproducible across machines."""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME_PATH = re.compile(r"/home/[a-z][a-z0-9_-]*/")
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".py", ".mjs", ".js", ".yml", ".yaml", ".toml", ".txt"}


def _tracked_text():
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO, text=True)
    return [REPO / line for line in out.splitlines()
            if line and Path(line).suffix in TEXT_SUFFIXES]


def test_no_tracked_text_artifact_carries_a_machine_local_path():
    offenders = []
    for path in _tracked_text():
        if path.name == "test_e0r2_path_hygiene.py":
            continue                                   # this file names the pattern it forbids
        text = path.read_text(encoding="utf-8", errors="replace")
        if HOME_PATH.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], f"machine-local paths in tracked text: {offenders}"


def test_ci_runs_the_full_node_suite():
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "npm --prefix coa_scraper test" in ci
    assert "run unit-test" not in ci          # unit-test alone skips the validator


def test_ci_checks_out_full_history():
    """actions/checkout@v4 defaults to fetch-depth 1, which makes the contract-immutability
    merge-base check unable to run at all (T1.1)."""
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in ci
```

- [ ] **Step 2: Run and confirm both fail.**
- [ ] **Step 3: Fix CI; make producers emit repo-relative paths for in-repo files and a **symbolic
  label** (not a hash) for the out-of-tree client root; rewrite every doc to use `$COA_CLIENT_ROOT`.**
  Regenerate the tracked reports in WS8 rather than hand-editing them.
- [ ] **Step 4: Run; commit**

```bash
# Enumerate every file — `git add docs/` is the directory-wide staging the global constraints forbid.
# Extend this list with the exact docs the hygiene scan flags; do not widen it to a directory.
git add .github/workflows/ci.yml coa_client_extract/artifacts.py coa_client_extract/cli.py \
        docs/superpowers/plans/2026-07-28-m1-14-e0r2-close-review-blockers.md \
        docs/superpowers/specs/2026-07-19-m1-14-e0r-correctness-sunset-remediation-design.md \
        tests/test_e0r2_path_hygiene.py
git commit -m "fix(e0r2): T7.1 — CI runs npm test; tracked text carries no machine-local paths"
```

### Task 7.2: Documentation and ROADMAP corrections

**Files:** `docs/ROADMAP.md`, `docs/data/mechanics-schema.md`,
`docs/superpowers/plans/2026-07-20-m1-14-e0r1-enforce-contract.md`

- [ ] **Step 1: `docs/ROADMAP.md`** — M1.8/M1.10B/M1.11D entries are history and stay, each gaining a
  "superseded by M1.14E0R.1 (AscensionDB runtime deleted)" note. The forward-looking claims (line 170
  `db.ascension.gg` hotlinks, line 205 disclaimer, line 212 "extend AscensionDB scraping") are rewritten
  to the client-native reality.
- [ ] **Step 2: `docs/data/mechanics-schema.md`** — lines 7, 22, 38, 175 describe the retired
  DB-sourced schema; correct them to the three-tier model already documented at line 270.
- [ ] **Step 3: E0R.1 tracker line 188** — the T6.2 checkbox claims the record "records
  icon/readiness/source coverage counts"; readiness and source had no producer. Correct it and point at
  E0R.2 T4.1.
- [ ] **Step 4: Add the two deferred guide-product items as explicit ROADMAP entries** (the out-of-scope
  section says they belong there, so they must actually land there):
  - *M1.16 — label heuristic build rankings as candidates/hypotheses.* `MetaReportRunner` ranks with
    `TheoryScorer` and the guide shows "top theorycraft" language; until client mechanics,
    interpretation, logs, and expert review converge, these are not recommendations.
  - *M1.16 — report renderable icon coverage separately from source coverage.* Acceptance reports
    179,749 **source** BLPs; the guide renders only converted assets, so renderable coverage is
    currently zero. Report source / renderable / CoA-domain / Builder-domain separately, resolve the
    catalog through the published generation, and cache by `spell_id` or asset reference rather than
    label.
- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP.md docs/data/mechanics-schema.md \
        docs/superpowers/plans/2026-07-20-m1-14-e0r1-enforce-contract.md
git commit -m "docs(e0r2): T7.2 — correct stale AscensionDB claims; schedule the guide-honesty items"
```

---

# Workstream 8 — real-client re-run and PR

### Task 8.1: Re-run recon, regenerate, canonical build, acceptance

- [ ] **Step 1: Full local suite, both languages, then the exact CI command in a clean environment**

```bash
python -m pytest -q && npm --prefix coa_scraper test
python -m venv /tmp/e0r2-clean && /tmp/e0r2-clean/bin/pip install -q -e . pytest
/tmp/e0r2-clean/bin/pytest -q      # from the repo root; BARE pytest, exactly as CI runs it
```

- [ ] **Step 2: Recon**

```bash
export COA_CLIENT_ROOT="<the Ascension Data directory>"
python -m coa_client_extract mechanics-recon --client-root "$COA_CLIENT_ROOT" --out reports/client_extract
```

Expect exit 0. **Exit 4 (`review_required`) is now a legitimate outcome** — T3.2 compares against a
hash-bound baseline, so a changed candidate set or drifted metrics stops the run.

**Correction carried from review round 3 — the E0R.1 re-bind recipe no longer suffices.** That
precedent (`d549ac9`) advanced "only hashes and headers" while asserting the semantic policy view was
byte-identical. With T3.2 in place that is no longer possible in general: a data-only client patch that
adds or removes spell rows *will* shift `nonzero_count`/`valid_count`/`distinct_ids`, and those metrics
are now part of the reviewed baseline. So:

- If the candidate **cell sets** are unchanged and only the metrics moved: this is a **baseline
  refresh**, a reviewed change. Re-record the metrics from the new scan, restate them in the policy,
  rehash, update the lock, and say so explicitly in the commit — it is not a mechanical re-bind.
- If a candidate **cell set** changed (a cell appeared or vanished), or any join collapsed to one
  candidate: **stop and adjudicate.** Do not refresh the baseline to make the hold pass; that would
  discard the exact signal the hold exists to raise.
- Only the capture identity (per-table sha256/header) plus a metrics refresh may move in one commit,
  and the commit message must name both.

- [ ] **Step 3: Regenerate** (~11 min at the previous scale; background it and monitor by captured pid —
  `pgrep -f` matched its own shell command line during E0R.1 and reported a false "still running")

```bash
python -m coa_client_extract regenerate --client-root "$COA_CLIENT_ROOT" \
  --out reports/client_extract --builder-entries coa_scraper/dist/coa_entries.jsonl
```

- [ ] **Step 4: Acceptance** (executes the canonical build under the network trap internally)

```bash
python -m coa_client_extract acceptance-summary --dist reports/client_extract \
  --recon-report reports/client_extract/coa_spell_mechanics_recon.json \
  --out reports/client_extract/coa_e0r_acceptance_summary.json
```

- [ ] **Step 5: Read the measured whole-generation bytes out of the record** and confirm ≤75% of
  `max_whole_generation_bytes`. If over, reduce the remaining redundancy — **do not raise the ceiling.**

### Task 8.2: The headroom gate lands with the record

**Files:** `tests/test_e0r2_headroom.py`, `reports/client_extract/*` — **one commit**

Committing the assertion earlier would leave a knowingly-red test in history, which the global
constraints forbid. It lands together with the artifact that satisfies it.

```python
# tests/test_e0r2_headroom.py
"""E0R.2 T8.2: E0R's exit condition is 'substantial E1 headroom'. 97.42% of ceiling is not headroom,
and raising the ceiling is not reducing the artifact."""
import json
from pathlib import Path

RECORD = Path(__file__).resolve().parents[1] / "reports/client_extract/coa_e0r_acceptance_summary.json"
TARGET = 0.75


def test_the_published_generation_leaves_e1_headroom():
    budget = json.loads(RECORD.read_text(encoding="utf-8"))["budget"]
    used = budget["whole_generation_bytes"] / budget["ceilings"]["max_whole_generation_bytes"]
    assert used <= TARGET, f"generation uses {used:.1%} of ceiling; E1 needs room below {TARGET:.0%}"
```

- [ ] **Step 1: Run the full suite one final time (must be entirely green).**
- [ ] **Step 2: Commit**

```bash
git add tests/test_e0r2_headroom.py reports/client_extract/coa_e0r_acceptance_summary.json \
        reports/client_extract/coa_spell_mechanics_recon.json
git commit -m "feat(e0r2): T8.2 — real-client acceptance record and the E1 headroom gate"
```

### Task 8.3: Push, update the PR, require green CI

- [ ] **Step 1: Push** `m1-14-e0r`. The whole local history goes with it, so the E0R.1 tracker commit
  that was deliberately unpushed is carried along by this push and needs no separate handling.
- [ ] **Step 2: Update PR #1's body** with an E0R.2 section: the seven blockers, the reproductions that
  are now red, and the measured size reduction.
- [ ] **Step 3: Wait for CI green on both the push and the pull_request runs.**
- [ ] **Step 4: Report to the user. Do NOT merge; do NOT start E1.**

---

## Out of scope, recorded deliberately

- **Description string dictionary.** Measured at ~8 MB of savings (22.4 MB inline, only 35% dedupable).
  Not worth a string-table child while the other three measures reach 55% of ceiling. Revisit if E1's
  artifacts push past 70%.
- **Recon generation-size forecast.** Recon has no basis for one (T3.3); publication measures exactly.
- **Actually adjudicating the three numeric joins.** T3.1/T3.2 make the standing ambiguity honest and
  drift-detecting; they do not resolve it. Resolution needs admissible independent evidence that does
  not exist today under the anchor-evidence precedence — a controlled local client where a known
  spell's cast time can be read back, or a Builder field that explicitly encodes it. This is the E1
  blocker to schedule next.
- **The two guide-product findings.** Not blockers while the guide is unpublished/experimental, but
  T7.2 lands them as explicit ROADMAP items rather than leaving them in a plan appendix.
