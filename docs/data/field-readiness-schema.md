# Field readiness (`field_readiness`) — the missing-vs-default state machine

**Milestone:** M1.14E0R. **Authority:** `coa_client_extract/contracts.py`.

E0R makes "we don't know this value yet" a first-class, load-bearing state distinct from a real value.
A quantitative field (a spell/mechanic cost, cooldown, or gcd) carries a `field_readiness` entry
`{status, reason_code}` so a consumer can fail **closed** on unknown data rather than silently
substituting an invented default. The core rule: **missing ≠ default**. A `null` cost is *unknown*; an
empty `{}` cost is *proven empty*; a `0` cooldown is *proven instant*.

## Statuses (`READINESS_STATUSES`)

| status | value must be | blocks a quantitative scope? | meaning |
|---|---|---|---|
| `available` | present (non-null) | no | the value is extracted and trustworthy |
| `verified_empty` | a (possibly empty) set/map | no | proven to have no entries (e.g. a truly free ability) |
| `not_applicable` | `null` | no | the field does not apply to this record |
| `unavailable` | `null` | **yes** | not yet extracted; a consumer must not proceed quantitatively |
| `ambiguous` | `null` | **yes** | extraction found conflicting candidates and withheld |

The value/blocking constraints are the `READINESS_INVARIANTS` state machine — a loader rejects a record
whose value contradicts its status (e.g. `verified_empty` with a `null` value, or `unavailable` with a
populated value) with a `readiness invariant` error.

## Reason codes (`READINESS_REASON_CODES`)

`pending_e1_operand` (the operand/side-table extraction lands in M1.14E1), `join_ambiguous`,
`unknown_symbol`, `side_row_missing`, `index_zero`, `no_static_anchor`, `not_extracted`, `proven_empty`.

## Consumers

- **`coa-mechanics-v2`** (`coa_meta/mechanics.py`): `costs` is `dict | None`, always serialized
  explicitly; `field_readiness` is validated against the enums + invariants above. The Node builder emits
  `cooldown_ms`/`gcd_ms`/`costs` as `null` with `{unavailable, pending_e1_operand}` until E1 supplies the
  operands.
- **The consumer interlock** (`coa_meta/action_catalog.py`): `ActionCatalog.quantitative_readiness`
  aggregates the load-bearing fields; `assert_quantitative_ready()` raises `QuantitativeScopeUnready`, and
  `simulate_apl` fails closed unless heuristic mode is explicitly authorized.
