# M1.14E0R Correctness & Sunset Remediation Design

> Remediation sub-milestone of [M1.14 Client DBC Data Foundation](2026-07-06-m1-14-client-dbc-data-foundation-design.md).
> Precedes **M1.14E1**. Fixes forward from `main@f76da24` (the merged M1.14E0 tip); it introduces no new
> **mechanics-operand** extraction surface — it makes the M1.14E0 evidence model **enforced and
> non-bypassable at every boundary**, and **hard-cuts db.ascension.gg (AscensionDB) from the canonical
> spell-mechanics pipeline**. It does add one genuinely new client-native artifact lane — a spell-icon
> catalog + asset contract (B4) — as the price of removing AscensionDB's icon role. Written after two
> independent architecture reviews of the merged E0 found that the
> load-bearing E0 guarantees — independent recon, raw-vs-normalized promotion, client-byte binding,
> independent Node validation, real resource budgets, transactional publication — are *stated* in the
> [E0 plan](../plans/2026-07-18-m1-14-e0-correctness-publication-foundation.md) but not *enforced* in
> the shipped implementation. Every finding below was reproduced against the working tree.
>
> **E0 is treated as "merged but not accepted."** E1 does not begin until E0R's exit gates pass. The
> M1.14E [evidence boundary](2026-07-18-m1-14-e-mechanics-extraction-completion-design.md) still holds
> in full: the Ascension server is a black box; static client bytes prove stored layout and raw values,
> never runtime behavior; no open-source core is authority.

## Purpose

M1.14E0R makes CoA Codex behave like the **evidence-tracked compiler** the E0 design chose to be —
client bytes and external sources become mechanics *only when every trust gate is satisfied* — rather
than the best-effort extractor the shipped E0 behaves like in several load-bearing places. It does two
things and nothing else:

1. **Enforce the E0 evidence model end-to-end** (Workstream A): the raw-only promotion gate, the recon
   hard hold's full-topology binding, the independent Node trust boundary, real streaming + size
   budgets, transactional family publication, an honestly-anchored `power_type`, and a clean tree.
2. **Hard-cut AscensionDB from canonical mechanics** (Workstream B): remove the live `db.ascension.gg`
   fetch and the `ascension_db` reconciliation tier from the canonical path, make missing data explicit
   instead of fabricated, make spell icons client-native, and install a bounded consumer fail-closed
   interlock so unknown mechanics can never re-enter quantitative output as `0`/`1500`/free.

E0R deliberately makes canonical output **less complete but trustworthy**: `cooldown_ms`, `gcd_ms`, and
`costs` become honestly unavailable until the client operands (E1) and effective-value derivation
(M1.16) land. Temporary unavailability is preferable to confidently-wrong or fabricated mechanics.

## The five epistemic states (the distinction E0R enforces)

Every finding below is a place where two of these states were conflated. They are **not
interchangeable confidence levels**; they are different kinds of knowledge, and the pipeline must keep
them distinct:

1. **Raw observation** — the exact bytes at a cell (always retained).
2. **Decoded representation** — a typed reading (int32/uint32/float) of those bytes; requires a proven
   *layout* and a proven *interpretation* (signedness/encoding is itself an interpretation).
3. **Semantically-promoted value** — a decoded value the policy **authorizes** as a normalized mechanic
   (`promotion: normalized`). Evidence sufficient to decode does **not** by itself authorize promotion.
4. **Reconciled canonical value** — the winner across sources, chosen by the Node reconciler under
   Decision 18 precedence.
5. **Runtime-verified behavior** — how the value actually behaves in a live session (M1.14G).

E0R touches states 1–4. It never asserts state 5. The M1.14E "two decode gates"
(`raw_decode_eligible = integrity ∧ layout`; `semantic_promotion_eligible = + interpretation`) govern
states 1–2; **promotion (state 3) is a separate authorization**, and the Node trust boundary (state 4)
must re-derive states 2–3 independently rather than trust the producer's summary.

## Non-Goals (stay out of E0R)

- **No M1.16 math.** No effective cooldown/GCD/cost derivation from operands; no coefficients/regen/
  resource state machines. E0R prevents fabrication; it does not compute mechanics.
- **No canonical-mechanics consumer rewire.** `reporting.py`/scoring/simulation stay on their current
  inputs; E0R only installs *guardrails* (the fail-closed interlock). The producer emits
  `coa-mechanics-v2`, but rewiring the consumers to *read* it is M1.16.
- **No E1 extraction.** No cooldown/GCD/cost/charge/effect operands, no sidecar, no closure. E0R only
  finishes and hardens what E0 already emits (identity, corrected scalars, the four side-table joins),
  plus the client spell-icon catalog those joins enable (B4) — the one new client-native artifact,
  added only to remove AscensionDB's icon role.
- **No client-native item extraction.** E0R removes the AscensionDB item pipeline (B6) but does not
  replace it; items are honestly un-enriched until client-native item extraction is built later. Only
  *spell* icons become client-native here.

## Design-lock invariants (frozen before implementation)

Four contracts are **locked** here and re-stated as the plan's first (design-lock) task; implementation
must not drift from them, and no code lands until they appear in both this design and the plan:

1. **Streaming cross-child validation with an explicit catalog domain.** Candidate validation
   merge-joins the sorted full table, CoA projection, and icon catalog and proves they agree (domain,
   compact-raw ↔ rich-envelope expansion, icon agreement, dup/out-of-order failure). The icon catalog's
   domain is the **full table** (every spell whose icon join resolves), deduplicated. (See A5, B4.)
2. **Candidate→final manifest trust digest.** The candidate manifest carries a `candidate_trust_sha256`
   over all trust-critical fields; only `/validation` and `/budget` may change in the final manifest,
   which must reproduce that digest; a `publication_state: candidate` manifest never resolves through a
   pointer. (See A5.)
3. **Concrete `policy_ref` + split numeric/string validation.** Rows carry a compact JSON-Pointer
   `policy_ref` (not free-form evidence text); Node resolves `kind`/proof/`promotion`/evidence through
   it. Numeric values are re-decoded from `raw_u32`; string values (icon path/name) are verified via
   `state`/normalization/`resolved` equality, with offset→string treated as producer attestation. (See
   A3, A4.)
4. **Machine-enforced icon-bundle conditions.** The catalog is always required; the asset bundle is
   required iff any row is `asset_status: converted`; every `converted_ref` resolves safely in-bundle and
   hash-matches; no-conversion → intentional bundle absence; the validator checks the bundle's internal
   manifest; compressed and uncompressed bytes both count toward budget. (See B4, A5.)

## Workstream A — Enforce the evidence model

### A1. Evidence vs authorization — the raw-only gate

`_proof()` stays **evidence-only**: it reports the field's proof facets, unchanged. Promotion is a
**separate authorization** decision. `build_spell_v2_records` populates a normalized `mechanics[field]`
only when `FieldPolicy.promotion == "normalized"`; a field whose facets are coincidentally
`verified` but whose policy says `raw_only` keeps its normalized value **null** while its observation
(raw bits, and the decoded reading when facets permit) remains available. This is the shipped defect:
`_proof()`/`_emit_join()` ignore `promotion` and promote any join whose composed proof happens to be
promotion-eligible, and the tests encode it (`test_spell_v2` expects `cast_time_ms == 1500` under
`raw_only` cells). Both flip: raw/decoded observation retained, normalized `null`.

**Join output promotion is one explicit predicate.** `JoinPolicy` gains a `promotion` field for the
emitted value. Component promotion is a *separate* fact from composed proof (which is over facets only),
so the predicate names both explicitly. A join emits a normalized value **iff all four** hold:

```
join_normalized_eligible =
      join.promotion == "normalized"
  AND every contributing FieldPolicy.promotion == "normalized"   # index cell, side id cell, side value cell
  AND semantic_promotion_eligible(composed_proof)                # composed over the same three fields' facets
  AND observation.state == "resolved"
```

Any `raw_only` contributor, any unproven facet, `index_zero`, or `side_row_missing` yields normalized
`null` with the raw retained. A truth-table test covers the corner case of a `normalized` join output
with one `raw_only` component (→ withheld), so producer and Node cannot diverge on the rule.

### A2. One shared topology verifier + full source binding

Recon and canonical regeneration must never diverge, so both call **one shared
`verify_source_topology(policy, backend, …)`** function. For **every required table** it opens the
member and verifies: exact `sha256`; the **full WDBC header** (`magic`, `record_count`, `field_count`,
`record_size`, `string_block_size`); the exact effective archive/member and patch chain; dense/
record-bounds; and **id uniqueness under a policy-declared key**. The policy declares each table's **key
cell and uniqueness rule** (uniqueness is not assumed to be cell 0 for every table). The
`expected_absent` set is verified absent. This replaces the shipped existence-only `has_file` checks,
which verify none of the above and run only for adjudicated joins.

The **hard hold binds the whole topology.** A flat `{table: sha256}` map cannot express headers,
archives, patch chains, or expected-absent topology, so `coa-spell-layout-v2`'s `bound` is an explicit
structure (archive identities are **logical/relative** names, never installation-specific absolute
paths):

```jsonc
"bound": {
  "client_build": "3.3.5a+patch-CZZ",
  "tables": {
    "Spell": {
      "sha256": "…",
      "header": {"magic": "WDBC", "record_count": 0, "field_count": 0, "record_size": 0, "string_block_size": 0},
      "source": {"member": "DBFilesClient\\Spell.dbc", "effective_archive": "patch-CZZ.MPQ", "patch_chain": []}
    }
    // … every required table
  },
  "expected_absent": ["SpellEffect", "SpellCooldowns"]
}
```

`regenerate()` re-runs `verify_source_topology` and refuses to publish unless the reviewed, `bound`
policy matches the opened client across **all** required tables' bytes, full header, archive/member,
patch chain, and the `expected_absent` topology. A required table that disappears, changes bytes/header,
or moves archives, or an expected-absent split table that appears, fails closed at recon **and**
regenerate.

### A3. The independent Node trust boundary

Node cannot verify promotion from the shipped artifact — observations carry no `promotion`, `JoinPolicy`
has none, and the join's resolved state is the `state` field (there is no `resolution` field; the E0R
draft's `resolution == "resolved"` was wrong). E0R makes Node a genuine independent verifier **within the
boundary of what Node can actually re-derive** — it does not overstate. Node has the artifact and the
policy, but **not** the client DBC bytes, so it re-derives layout/interpretation/promotion but **not**
integrity:

- The **reviewed layout policy is published as a generation child** (`coa-spell-layout-v2`), its
  `sha256` bound in the manifest. Node holds a **separately pinned** expected canonical policy hash and
  refuses a generation whose policy child does not match it — a tampered or swapped policy is caught.
  The pinned hash lives in a **committed lock file** `coa_scraper/config/spell_layout.lock.json`
  (`{schema_version, client_build, sha256}`), rotated in the same reviewed commit that rebinds the
  policy — never an unexplained code constant.
- Node independently validates **transport integrity** (pointer → manifest → child: schema,
  containment, hashes, byte/record counts) and checks the manifest's **verified source-topology
  attestation + binding** (A2) — it trusts that attestation for *integrity* rather than re-proving it,
  because integrity is a runtime fact established while opening the DBC and Node lacks those bytes.
- For every populated normalized value, Node derives `layout`, `interpretation`, `kind`, and
  `promotion` from the pinned **policy** (via each observation's `policy_ref`, A4) and re-checks
  `promotion == normalized`, `state ∈ {present, resolved}`, `decoded_reason == "decoded"`, and the A1
  join predicate — but the raw→value step splits by kind:
  - **Numeric** (`int32`/`uint32`/`float`): Node **re-decodes `raw_u32`** per the policy `kind` and
    accepts the producer's value only if the re-decode agrees.
  - **String** (`SpellIcon.path`, names): a string cannot be recovered from `raw_offset` without the
    DBC string block, which Node lacks. Node instead verifies policy eligibility, observation `state`,
    path normalization, and equality between the normalized output and `StringObservation.resolved`; the
    `offset → string` relationship is part of the producer's **source-integrity attestation**.
  Node never trusts producer-supplied `decoded`/`proof`/`promotion` summaries, and ignores producer
  evidence text (it resolves evidence from the policy via `policy_ref`).

A Python producer regression (e.g. a promotion-gate bug, or a normalized value that disagrees with its
own raw) can therefore no longer certify itself past the consumer. What Node does **not** claim: that
Python actually read those raw bytes from the client — that remains the producer's attested,
topology-bound integrity fact (unless Node is separately handed the DBCs).

### A4. Streaming and a real size budget

Streaming the writer alone is insufficient: `build_spell_v2_records`, attribution, projection
filtering, and `GenerationWriter.add_jsonl` all materialize full collections, and streaming lowers RSS
without shrinking the review-estimated ~1.04 GiB full-table artifact under the 512 MiB ceiling. E0R
makes three coupled changes:

- **Iterator/two-pass producer.** Extraction, attribution, projection filtering, writing, and Node
  validation all stream record-by-record. No whole-artifact `str`-then-`bytes` double copy. This
  includes `generation.mjs` (the Node resolver), which today reads every child fully and splits JSONL
  in memory: it validates line-by-line, hashing the byte stream without materializing a row array.
- **Hoist repeated data out of rows (the real size lever).** Today the producer copies each field's
  free-form `FieldPolicy.evidence` **text** into every observation's `evidence_ref` (and repeats the
  ~55-entry patch provenance per row) — the actual cause of the ~1.04 GiB estimate. E0R replaces the
  per-row evidence text with a compact **`policy_ref`** JSON pointer, e.g. `"/tables/Spell/fields/
  power_type"`. A join's `index`/`side_id`/`side_value` components each carry a `policy_ref` to their
  **underlying table-field node** (e.g. `/tables/SpellCastTimes/fields/base_ms`), resolved through the
  join mapping — there is **no** synthetic `/joins/...` policy node to resolve against. The policy path
  supplies `kind`, proof, `promotion`, and evidence. Generation provenance is written **once** to the
  manifest. Node resolves everything through `policy_ref` and ignores any producer evidence text.
- **Domain-scoped emission that never sheds raw.** The **full-table child** (`coa-client-spell-v3`)
  streams **compact** rows, but a compact row still retains **enough raw to reconstruct eligibility**: a
  normalized value in the full artifact must never exist without its raw substrate. Each compact row
  carries identity + normalized `mechanics` + attribution **plus a compact raw block** — the scalar raw
  `u32`/string raw offset for each field, every join's raw index/side-id/side-value cells, and the
  `state` for `unresolved`/`not_applicable` observations — with proof, promotion, and evidence text
  **inferred from the generation policy** rather than repeated per row. The **CoA projection**
  (`coa-client-spell-projection-v3`) expands that compact form into the rich `field_observations`
  envelopes. This bounds the *repetition*, not the *retention*: closure work over non-CoA spells (E1+)
  still has an auditable raw substrate for every record.

Two states that A4 must not conflate: a field **located** at a proven cell but authored `raw_only`
retains its raw bytes/offset (there is a cell to read); a field with **`cell: null`** is `unresolved`
and retains **no** raw (no cell is known). Only the former is "raw-only"; the latter is honestly
absent.

**Budget scope is defined, not implied.** Ceilings are predeclared in the policy and apply **per child
and to the whole generation**, measured on **uncompressed serialized bytes**. The required full child is
an uncompressed `.jsonl` with byte/record validation; a `.jsonl.gz` alternative is permitted **only** if
the child registry declares it explicitly and its **uncompressed** byte/record counts are validated
after decompression (so compression never hides a budget breach). `within_budget` is computed from
**all three** of
serialized bytes, subprocess **peak RSS** (measured in a subprocess so `ru_maxrss` is that run's;
Linux KiB→MiB), and elapsed — not raw DBC bytes. A **full real-client `regenerate`** (not just recon)
is measured and recorded within budget, for both the Python generation and the canonical Node build,
against a pinned benchmark environment recorded in the manifest.

### A5. Transactional family with a required-child registry

**One authoritative manifest model.** `gen-<uuid>/manifest.json` **is** `coa-client-extract-manifest-v3`
— it holds the child registry and is hashed by the pointer, so it **cannot list or hash itself as a
child**. The required children it registers are: `coa_client_spell.jsonl` (full, v3), the projection +
its projection-manifest (v3), the **spell-icon catalog** (`coa-client-spell-icons-v1`) and its optional
asset bundle (B4), `coa_client_content.jsonl`, `coa_client_archive_plan.json`,
`coa_client_advancement.jsonl`, `coa_client_class_types.jsonl`, `coa_client_tab_types.jsonl`,
`coa_client_essence.jsonl`, and the **reviewed policy child** (`coa-spell-layout-v2`). **Parity is
conditional**: if requested it must complete and stage before publication; otherwise the manifest
records it **intentionally absent**. Any fixed-name `coa_client_extract_manifest.json` is a
**noncanonical compatibility summary** produced *after* publication and never a generation child.
`coa-mechanics-v2` is a **separate output family** built by the Node consumer — it is not part of the
client-extract generation transaction.

**Prepublication validation sequence** (Node cannot consume the active pointer before it flips, yet a
failed Node build must not occur after the flip). Publication therefore validates a **candidate
generation** by path, not via the pointer:

1. Stage all required children into `gen-<uuid>/`.
2. Write a **candidate** manifest (`publication_state: "candidate"`, which can **never** be resolved
   through a canonical pointer and is safely collectible after an interrupted run) that records a
   **`candidate_trust_sha256`** — a digest over every trust-critical field (child registry, topology
   binding, policy binding, schema versions), i.e. everything except `/validation` and `/budget`.
3. Run the Python **and** Node validators directly against that candidate generation (by path),
   including **cross-child consistency** (below), not merely per-child validity.
4. Produce the **final** manifest, which may differ from the candidate **only** under `/validation` and
   `/budget`; it must **reproduce the identical `candidate_trust_sha256`** (so acceptance/budget results
   can never silently mutate a trust-critical field after validation).
5. Verify the digest matches, then publish the pointer **last** (the pointer hashes the entire final
   manifest).

**Cross-child consistency (a streaming merge-join over sorted `spell_id`).** Individually-valid children
can still disagree about a spell, so validation merge-joins the full table, projection, and icon
catalog and asserts: every `is_coa == true` full-table row appears **exactly once** in the projection;
no projection row exists outside that domain; identity/normalized-mechanics/attribution/compact-raw
agree across children; the projection's rich observation is a **valid expansion** of the corresponding
compact raw block; icon ids/paths in the catalog agree with the spell artifacts; and duplicate or
out-of-order `spell_id`s fail.

A late parity/manifest/validation failure leaves the previous pointer untouched (the shipped order
publishes the pointer *before* parity and the final manifest). Fixed-path compatibility outputs are
**noncanonical** and must never cause `regenerate()` to fail after publication. Concurrency uses **one**
mechanism: a **process file lock** held from the predecessor-pointer read through pointer replacement,
with predecessor revalidation immediately before the replace (the `gen-<uuid>/ exist_ok=False` collision
guard stays).

### A6. `power_type` is honestly anchored or fully raw-only

The shipped policy marks `power_type` `interpretation: verified` (a signed `int32` reading), but every
anchor is non-negative and cannot distinguish signed from unsigned. E0R **requires a verified
negative-value anchor** — a spell whose raw `power_type` cell reads `0xFFFFFFFE` **and** whose
health-cost nature is corroborated by **static client evidence** (its `description`/tooltip text),
proving the signed `int32` reading. The admissible evidence is **immutable and static only**: if
`-2` (health) can be established only via runtime behavior or AscensionDB, it is not admissible and
`power_type` becomes **`raw_only` for the entire field** (raw retained, normalized withheld). E0R does
**not** introduce an incidental value-level signed/unsigned promotion model (that would be a new proof
model outside remediation scope).

### A7. Repo hygiene — fix the generator, then untrack deliberately

The machine-local `/home/archbug/...` paths in `coa_artifact_manifest.json` are a **generator** bug:
`write-artifact-manifest.mjs` emits absolute paths. E0R fixes the generator to emit repo-relative
paths, then classifies every artifact in the E0 churn as **source**, **committed acceptance fixture**,
or **disposable output**; disposable outputs are untracked with `git rm --cached` (`.gitignore` alone
does not untrack) and ignored; committed fixtures are kept intentionally and documented. The ~184k-line
generated-data churn merged into E0 is separated in a dedicated, intentional commit — not mixed with
correctness fixes.

## Workstream B — AscensionDB removal + fail-closed interlock

### B1. Remove AscensionDB integration entirely (not quarantine)

E0R **deletes** the AscensionDB scraping/integration code — `enrich-ascensiondb.mjs`,
`enrich-ascensiondb-assets.mjs`, `enrich-db`, `apply-db-enrichment`, `--db-spells`, `pipeline:m1.9` (root
+ `coa_scraper`), the item enrichment that depends on AscensionDB (`enrich-items`/`build-items` lose
their AscensionDB source), and the `guide_tooltips.py` `db.ascension.gg` host usage. Canonical
`build-mechanics` runs `--client-extract-pointer`, network-free. **The one permitted `db.ascension.gg`
touch is a single new opt-in utility** — `download-spell-icons.mjs` — that downloads *only image files*
to local disk to fill any client-icon gap (see B4); it emits no runtime URLs and no data enrichment. No
"quarantine namespace" remains: the integration is removed, not hidden. Items losing AscensionDB
enrichment is an accepted consequence; client-native item extraction is later work.

### B2. Remove `ascension_db` as a reconciliation tier + a network-trap negative gate

`TIERS` drops `ascension_db`; the canonical build function's signature cannot accept DB rows. Frozen
AscensionDB payloads survive **only** as committed test fixtures / diagnostic comparison inputs — never
winners. The **negative dependency gate** is behavioral, not textual: a canonical build runs under an
**injected network trap** (any outbound request fails the test) against a fixture that includes a
would-be DB payload, and the test asserts the produced mechanics/manifest carry **no** `ascension_db`
provenance winner, tier, hash, or `db.ascension.gg` URL, and that the build made **no** network request.
Both `package.json` files are inspected for a lingering canonical AscensionDB command.

### B3. `coa-mechanics-v2` — represent "unknown"

`coa-mechanics-v1` cannot express "cost unknown": `costs` defaults to `{}` and its loader coerces
missing/null to `{}` (indistinguishable from free). E0R defines **`coa-mechanics-v2`**:

- `costs: null | object`, with the `numberOrNull` missing-vs-zero repair applied throughout (missing ≠
  zero, unknown ≠ free).
- **Machine-readable field readiness** — a small state machine with **status/value/reason invariants**
  (enforced, not merely documented):
  - `available` → the field's value is **non-null** (a verified `0`/`1500`/empty-cost is `available`,
    not withheld); **non-blocking**.
  - `verified_empty` → **set-valued fields only** (e.g. costs proven empty): value is an empty
    collection; **non-blocking**. It is never a timer-field status.
  - `not_applicable` → value is `null`; **non-blocking** (the field does not apply to this spell).
  - `unavailable` / `ambiguous` → value is `null`; **blocking** (not yet extractable / not uniquely
    resolvable).
  The *why* is a **closed `reason_code` enum** (`pending_e1_operand`, `join_ambiguous`, `unknown_symbol`,
  `side_row_missing`, `index_zero`, `no_static_anchor`, `not_extracted`), never a free string. A
  contradictory pair (e.g. `verified_empty` + `not_extracted`) is rejected at load.
- A v1 **rejection / explicit migration boundary**: a v1 consumer artifact is rejected with a
  regenerate message; pre-E0R client generations are rejected for lacking the trusted policy child.

### B4. Client-native spell icons

The guide today prefers DB icon rows + cached paths and, absent a local image, constructs a **live
`db.ascension.gg` icon URL** (`guide_assets.py:8,47`; `icon-assets.mjs:6-8`; `guide_builder.py` and its
callers pass DB icon names/cached paths). E0R makes spell icons fully client-native and removes those
URLs entirely.

- **New proof type — string-valued join.** `SpellIcon.path` is a **string-block offset**; the shipped
  `Envelope`/`make_join` are numeric-only. E0R adds `make_string_join` (side component is a
  `StringObservation`) so the icon path is extracted under the two-gate/promotion model.
- **Asset resolver (real bytes).** An asset resolver reads the **effective client member** for each
  `SpellIcon.path` (`Interface\\Icons\\<name>.blp` in the MPQ chain) and returns its **bytes, member,
  archive, patch chain**. `source_asset_sha256` is the hash of the **actual BLP bytes**, never the path
  string; `source_archive` is the exact logical archive. `missing` means the resolver found no client
  member.
- **Catalog child — `coa-client-spell-icons-v1`.** Always-required, **full-table domain** (every spell
  whose icon join resolves), keyed by `spell_id`: `spell_icon_id`, `client_path` (normalized
  `SpellIcon.path`), `source_asset_sha256` (BLP bytes) + `source_archive`, `asset_status ∈ {converted,
  source_only, missing, placeholder}`, optional `converted_ref` + `converted_sha256`, `readiness`. Asset
  entries are **deduplicated** by `client_path` (many spells share one icon).
- **Coverage decision (drives whether any URL survives).** The client `SpellIcon` table maps essentially
  every spell to a BLP, so client coverage is expected to be complete. If a **BLP→web conversion**
  pipeline runs, converted rows carry `converted_ref` into a **single hash-bound bundle child**; the
  catalog + bundle then fully replace AscensionDB icons and **all live URLs are removed**. If conversion
  leaves a **gap**, a single new opt-in utility `download-spell-icons.mjs` downloads **only the missing
  image files** from `db.ascension.gg` to **local disk** (feeding the bundle) — it is not a runtime URL
  and not data enrichment; **no live `db.ascension.gg` URL remains in the guide either way**.
- **Bundle contract (machine-enforceable).** Converted assets are one hash-bound archive child with its
  own internal manifest. The candidate validator enforces: catalog always required; **if any row is
  `converted` the bundle is required**; every `converted_ref` resolves safely in-bundle (deterministic
  ordering + path normalization, no traversal), matches its recorded hash, and is referenced by exactly
  one catalog entry (dedup honored); no-conversion → bundle absence recorded intentionally;
  `source_only`/`missing`/`placeholder` rows carry **no** `converted_ref`. It validates the bundle's
  **internal manifest**, and **both** compressed and uncompressed bytes count toward budget.
- **Guide wiring.** `guide_assets.py`, `guide_builder.py`, and their callers read the client icon
  catalog; `ASCENSIONDB_ICON_URL_TEMPLATE` + the `icon-assets.mjs` URL templates are **deleted**.
  `source_only` (a verified BLP that is not itself browser-renderable) renders a **placeholder** unless a
  converted bundle entry exists; the guide **must not** fall through to the generic `asset_root` search
  in a way that resurrects a cached AscensionDB image. It never emits a `db.ascension.gg` URL.

### B5. Bounded consumer fail-closed interlock

"Preserve null" is not implementable without type and control-flow changes, and silently dropping
individual unready actions distorts a rotation into a false-valid result. E0R installs guardrails
only — no derivation, no rewire — behind an explicit validation boundary:

- **Nullable types.** `CatalogAction.cooldown_ms`/`gcd_ms` become `int | None` **and** `costs` becomes
  `dict | None` (else `coa-mechanics-v2`'s unknown cost collapses straight back to empty/free at the
  consumer). The `or 0` / `else 1500` / `{}` coercions in `action_catalog.py` are removed and null is
  preserved.
- **Explicit readiness + a validation gate.** `ActionCatalog` exposes `quantitative_readiness` listing
  the blocking fields and reason codes. `simulate_apl` and combat conversion **require a ready catalog
  before entering their loops**: when any required action in a quantitative scope lacks load-bearing
  timing/cost data, the **entire quantitative scope fails closed** (an explicit blocked/unverified
  result) rather than dropping the action and reporting a plausible-looking rotation. `CombatAction`
  stays fully concrete **after** that validation passes.
- **Heuristic construction is a separate mode.** `simulation.py`'s invented GCD/cooldown/cost/effect
  values are built by an **explicitly separate factory / opt-in mode, default off**, tagged `source:
  heuristic` with degraded readiness; `reporting.py`'s tooltip-inference path is labeled heuristic.
- **Behavioral sweep, not a literal grep.** Verified `0`/`1500`/`{}` are **legitimate values** and must
  not be rejected for resembling defaults. So the sweep is a set of **missing-vs-verified behavioral
  tests** (a missing input propagates to null/blocked; a verified `0`/`1500`/empty-cost is preserved)
  plus a **narrow allowlist** of intentional constants — not a repository-wide search for the literals.

### B6. Item/asset AscensionDB code is removed too

The AscensionDB **item/asset** pipeline (`enrich-items`, `build-items`, `enrich-ascensiondb-assets`) is
**removed** with the rest of the integration (B1) — not quarantined. Item enrichment loses its
AscensionDB source; **client-native item extraction is later work** and items are honestly un-enriched
until then. The only surviving `db.ascension.gg` touch anywhere is the opt-in
`download-spell-icons.mjs` image-only utility (B4).

## Check-ins — one agent gate, one human gate

**Recon adjudication is agent-executable, not a human gate.** An agent (main or sub) runs
`mechanics-recon` against the real client and authors the reviewed, client-bound `coa-spell-layout-v2`
policy + `spell_layout.lock.json` from the frozen `proposed_policy_delta` — the four join cells +
evidence (including `SpellIcon.path`'s layout/interpretation and the resulting icon-catalog coverage),
`power_type`'s static negative anchor, and the full topology. Recon still **proposes** and never
self-approves: authoring the policy is a distinct, reviewable commit driven by the delta, and canonical
regeneration runs only against the resulting `verified`, bound policy. A field is marked
`promotion: normalized` only when the delta uniquely proves it (ambiguous → `cell: null`, `unresolved`).

**The single human check-in is the end-of-E0R acceptance review, performed on the WIP branch.** E0R is
pushed to `m1-14-e0r` and reviewed against the [exit criteria](#exit-criteria-m114e0r) before ff-merge.
This is the **only** push in the milestone — intermediate work is committed locally and pushed once, at
the end, for that review.

## Fork resolutions (adopted)

- **Spell icons:** id **+ resolved path**, plus client asset verification (converted asset or honest
  placeholder); never AscensionDB.
- **Cast/duration/range/icon joins:** run value-anchor joined-pair discovery for **all four now** in
  E0R. Promote only unique, human-reviewed results; an ambiguous result stays **unresolved** (`cell:
  null`, no raw observation) — *not* "raw-only," which is reserved for a located-but-non-promoted cell.
  (This materially reduces E1a, which no longer carries join adjudication.)
- **CI:** synthetic Python and Node suites run on every push/PR (GitHub Actions); the proprietary
  real-client tier stays local/self-hosted with a committed **hash-bound acceptance summary**.
- **`power_type`:** require the negative anchor (A6); otherwise fully raw-only.

## Schema versioning (explicit)

Row schemas and manifest schemas are named distinctly (a row schema is never a manifest schema):

- **`coa-spell-layout-v2`** — the reviewed policy: per-table key-cell + uniqueness rule,
  `JoinPolicy.promotion`, the explicit full-topology `bound` structure (A2), published as a generation
  child.
- **`coa-client-spell-v3`** (full-table **rows**) — compact rows that still retain a compact raw block
  (A4); no per-row proof/provenance (hoisted to the manifest + policy).
- **`coa-client-spell-projection-v3`** (projection **rows**) — the rich `field_observations` rows for
  the CoA subset; **`coa-client-spell-projection-manifest-v3`** is its (distinct) projection manifest.
- **`coa-client-spell-icons-v1`** (catalog **rows**) — the client spell-icon catalog (B4); its optional
  converted-asset bundle is a separate hash-bound child.
- **`coa-client-extract-manifest-v3`** — the **generation manifest itself** (`gen-<uuid>/manifest.json`,
  hashed by the pointer, **not** a child): the required-child registry, hoisted provenance, full-topology
  binding, pinned benchmark env + three-part budget + candidate-validation results. Pre-E0R generations
  are rejected for lacking the trusted policy child + full binding.
- **`coa-mechanics-v2`** (a **separate output family**, not part of the extract generation) — `costs:
  null | object`, machine-readable field readiness, v1 rejection.

## Module layout (files touched)

```
coa_client_extract/
  spell_proof.py         # _proof stays evidence-only; promotion authorized by the emitter, not here;
                         #   NEW string-valued join (side component is a StringObservation)
  spell_layout.py        # v2: JoinPolicy.promotion; per-table key cell + uniqueness; full-topology bound
  data/spell_layout_v2.json  # reviewed, client-bound; all four joins + power_type negative anchor
  spell_mechanics.py     # shared verify_source_topology; joined-pair discovery for all four joins;
                         #   three-part budget (bytes+RSS+elapsed); recon proposes, never writes policy
  spell_icons.py         # NEW: coa-client-spell-icons-v1 catalog (SpellIcon id+path, source hash/status)
  spell_record.py        # (renamed from spell_v2.py; emits v3) promotion-gated normalized emission;
                         #   streaming/iterator; compact-raw full row + policy_ref (no per-row evidence text)
  publish.py / manifest.py  # required-child registry; policy child; hoisted provenance; candidate-then-
                         #   pointer publish (pointer LAST); process lock; manifest-v3 (not a child)
  cli.py                 # regenerate: shared topology hard hold; stage+candidate-validate+publish
coa_scraper/
  config/spell_layout.lock.json         # NEW: pinned canonical policy {schema_version, client_build, sha256}
  scripts/lib/mechanics-projection.mjs  # independent verify: pinned policy lock + recompute decode/eligibility
  scripts/lib/mechanics-reconcile.mjs   # drop ascension_db from canonical TIERS
  scripts/lib/jsonl.mjs                 # NEW: generic readJsonl moved off ascensiondb.mjs (no retired-source import)
  scripts/build-mechanics-artifacts.mjs # pointer-only canonical; coa-mechanics-v2; no --db-spells;
                                        #   canonical build fn signature cannot accept DB rows (legacy wrapper does)
  scripts/lib/generation.mjs            # STREAM line-by-line; validate policy child; reject pre-E0R gens
  scripts/lib/icon-assets.mjs           # remove db.ascension.gg spell-icon URLs; read client catalog
  scripts/write-artifact-manifest.mjs   # relative paths (no machine-local absolute paths)
  package.json + root package.json      # canonical build-mechanics pointer-only; pipeline:m1.9 -> legacy
coa_meta/
  action_catalog.py      # nullable cooldown_ms/gcd_ms; drop 0/1500/{} coercions
  simulation.py          # invented values behind an explicit default-off heuristic mode
  reporting.py / guide_assets.py / guide_tooltips.py  # client icon catalog; label heuristic path
  mechanics.py / mechanics_repository.py  # coa-mechanics-v2 (costs nullable, field readiness), v1 reject
.github/workflows/       # CI: synthetic Python + Node suites on push/PR
docs/  DECISIONS.md; client-spell-schema (v3); mechanics-schema (v2); generation schema (v3);
       recon schema (topology + negative anchor); NEW field-readiness doc
```

## Testing (mirrors existing tiers)

- **Promotion gate (truth table):** a `raw_only` field with verified facets → normalized `null`, raw
  (and decoded when facets permit) retained; the four-part join predicate is table-tested, including a
  `normalized` join output with **one `raw_only` component** → withheld; the shipped `cast_time_ms ==
  1500`-under-`raw_only` expectation is inverted.
- **Topology hard hold:** one shared verifier; recon and regenerate agree; a changed/missing required
  table, wrong full header, moved archive, non-unique key (under the policy key), or appeared
  expected-absent table fails closed in **both** paths; `bound` covers every required table.
- **Independent Node verification:** for a **numeric** field Node re-decodes `raw_u32` per the pinned
  policy and rejects a value whose re-decode disagrees; for a **string** field (icon path/name) Node
  cannot re-decode from `raw_offset` and instead checks eligibility, `state`, path normalization, and
  `normalized == StringObservation.resolved`. It recomputes the join eligibility predicate, resolves the
  policy via `policy_ref` (ignoring producer evidence text), rejects a generation whose policy child hash
  ≠ the `spell_layout.lock.json` pin or that lacks the policy child (pre-E0R), and validates transport
  integrity but does **not** re-prove source integrity.
- **Compact-raw full table:** a full-table row retains enough raw (scalar `u32`/string offset, join
  component cells, `state`) to reconstruct eligibility — no normalized value exists without its raw
  substrate; the projection expands the same compact form into rich envelopes.
- **String-valued join + icon catalog:** the icon path resolves via the string-valued join (side =
  `StringObservation`) under the promotion gate; `coa-client-spell-icons-v1` is keyed by `spell_id` with
  `asset_status`/`readiness`; the guide falls back to a placeholder (never AscensionDB) when absent.
- **Streaming + budget:** provenance/evidence hoisted (rows shrink); full child compact, rich envelopes
  only in the projection; `generation.mjs` validates line-by-line; `within_budget` uses bytes +
  subprocess peak RSS + elapsed; a recorded **full real-client regenerate** stays within budget for the
  Python generation and the Node build.
- **Transactional family:** all required children (incl. the policy + icon-catalog children) staged and
  **candidate-validated** (Python + Node, by path) before the pointer flips; the manifest is not a child;
  the final manifest reproduces the candidate's `candidate_trust_sha256` (only `/validation` + `/budget`
  may change); a candidate manifest can never resolve through the pointer; a late parity/manifest failure
  leaves the prior pointer intact; concurrent publish is serialized by the process lock.
- **Cross-child consistency:** a merge-join over sorted `spell_id` — each `is_coa` full-table row appears
  once in the projection, no projection row outside that domain, identity/mechanics/attribution/compact-
  raw agree, the projection observation is a valid expansion of the compact raw, icons agree, and
  duplicate/out-of-order ids fail.
- **`power_type`:** the static negative anchor promotes the signed reading; without an admissible static
  anchor, `power_type` is raw-only across the field.
- **AscensionDB negative dependency gate:** the canonical mechanics build takes no AscensionDB input,
  selects no `ascension_db` winner, embeds no `db.ascension.gg` URL/hash, and makes no network request.
- **`coa-mechanics-v2`:** field readiness distinguishes `available`/`unavailable`/`not_applicable`/
  `ambiguous`/`verified_empty`; `costs` is `null` when unknown (never `{}`); unknown cooldown/GCD
  serialize as `null`, never `0`/`1500`; v1 rejected.
- **Consumer interlock (behavioral):** nullable catalog timing **and costs**; a scope with any unready
  load-bearing action fails closed (no silent action drop); heuristic simulation is off by default and
  labeled; **missing-vs-verified** tests confirm a missing input propagates to null/blocked while a
  verified `0`/`1500`/empty-cost is preserved (an allowlist, not a literal search).
- **`client` tier:** recon `verified` with all four joins adjudicated (or honestly **unresolved**,
  `cell: null`), corrected offsets + `power_type` static negative anchor on real spells, full topology
  bound, within budget.

## Exit criteria (M1.14E0R)

- Canonical `build-mechanics` runs **pointer-based and AscensionDB-free**; the fixed-path fallback is a
  distinct, clearly-named legacy command; `pipeline:m1.9` is retired as canonical in root and scraper.
- Recon and regenerate use **one shared topology verifier** and **bind the full source topology**
  (every required table's sha256 + header + archive + patch chain, plus `expected_absent`); drift fails
  closed in both.
- `promotion: raw_only` + verified facets **retains a decoded observation but never populates normalized
  mechanics**; Node **independently** re-decodes the raw and recomputes eligibility (layout/
  interpretation/promotion) from a **pinned, hash-bound policy child** and rejects anything ineligible or
  any pre-E0R generation (it validates transport integrity but does not re-prove source integrity).
- All canonical children are **staged before the pointer flips**; a late failure leaves the prior
  pointer untouched; concurrent publish is serialized.
- JSONL is **streamed**, repeated provenance/evidence is **hoisted** to the manifest, and a recorded
  **full real-client regenerate** (not just recon) is within a **three-part budget** (serialized bytes +
  subprocess peak RSS + elapsed) on a pinned benchmark environment.
- `power_type` carries a **negative anchor** or is fully raw-only.
- AscensionDB is **not a selectable canonical source**; unknown cooldown/GCD/costs are **null with
  readiness reasons**, never `0`/`1500`/free; spell icons are **client-native** (id + path + client
  asset or honest placeholder); the consumer interlock **fails the quantitative scope closed** rather
  than fabricating.
- Generated-data churn + the machine-local manifest paths are cleaned in a **separate, intentional
  commit** (generator fixed, disposable outputs untracked).
- **CI** runs the synthetic Python + Node suites on push/PR; the real-client tier is local/self-hosted
  with a committed hash-bound **acceptance summary** — a small, **schema-stable, intentionally curated
  run record** (not byte-deterministic, since `generation_id`/RSS/elapsed vary): `client_build`,
  `generation_id`, `manifest_sha256`, policy `sha256`, `extractor_commit`, `benchmark_env_id`, per-child
  `{sha256, byte_length, records}`, the three-part budget measurements, and recon `status` — never the
  large generated artifacts A7 untracks.
- Schema versions are explicit: `coa-spell-layout-v2`, `coa-client-spell-v3`/`-projection-v3`
  (+ `-projection-manifest-v3`), `coa-client-spell-icons-v1`, `coa-client-extract-manifest-v3` (the
  generation manifest, not a child), `coa-mechanics-v2`.

## Decisions

- **Evidence ≠ authorization (new).** Proof facets are evidence; `promotion` is a separate
  authorization. A field may be fully decodable yet intentionally raw-only. The emitter, not
  `_proof()`, gates normalized emission on `promotion == normalized`.
- **Independent Node trust boundary (amends E0).** The reviewed policy is a hash-bound generation child
  pinned in a committed lock file; Node **re-decodes** raw and **recomputes eligibility** (layout/
  interpretation/promotion) from `(policy, raw_u32)`, never trusting producer summaries — but it
  validates only **transport** integrity, not source integrity (it lacks the client bytes).
- **The generation manifest is authoritative, not a child (new).** `gen-<uuid>/manifest.json` **is**
  `coa-client-extract-manifest-v3` and cannot register itself; publication stages children, writes a
  `publication_state: candidate` manifest carrying a `candidate_trust_sha256` over all trust-critical
  fields, validates the candidate generation with both Python and Node **by path** — including
  **cross-child consistency** (a merge-join proving the full table, projection, and icon catalog agree)
  — and the final manifest may change only `/validation` + `/budget` (reproducing the same digest) before
  the pointer flips last. Any fixed-name manifest is a post-publication compatibility summary.
- **Full-topology hard hold (amends E0).** One shared verifier; `bound` is a structured record covering
  every required table's bytes + full header + archive + patch chain + expected-absent topology (not a
  flat sha map).
- **AscensionDB is not a canonical source (completes the M1.14C sunset).** M1.14C demoted it to
  fallback-only and deferred the rewire to M1.16; E0R removes it from the canonical spell-mechanics
  path entirely. Frozen payloads survive only as fixtures/diagnostic. Item/asset retirement is tracked
  separately.
- **Missing ≠ default (new).** Unknown load-bearing mechanics are `null` with machine-readable
  readiness (`coa-mechanics-v2`), never `0`/`1500`/free; a quantitative scope with unready load-bearing
  data fails closed. Effective-value derivation and the consumer rewire remain M1.16.
- **Client-native spell icons (new).** Spell icons resolve from the client (`SpellIcon` id + path) with
  a client asset or honest placeholder; the `db.ascension.gg` remote/cached spell-icon fallbacks are
  removed.
- **Explicit schema versioning (new).** Breaking shape/semantics changes bump the schema version and
  reject prior generations; they are never silently reinterpreted.

## Impact on M1.14E1

E0R pulls **all four join adjudications** and the streaming/budget/publication hardening forward, so
E1a shrinks: E1 no longer carries join discovery and inherits a streaming, transactionally-published,
independently-verified substrate. E1 proceeds entirely **without AscensionDB** — its raw client
operands (cooldown/GCD/cost/charge/effect) fill the fields E0R made honestly unavailable, and M1.16
derives their effective values and rewires the consumers.
