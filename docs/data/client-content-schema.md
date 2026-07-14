# Client Content Schema

Records use schema version `coa-client-content-v1`, produced by `coa_client_extract` (M1.14A) from the
loose `Data/Content/*.json` tier.

## Required Fields
- `schema_version`: always `coa-client-content-v1`
- `content_kind`: `spell_rank` | `spell_stat_suggestion` | `spell_role_suggestion` |
  `item_variation` | `character_advancement`
- `spell_id` and/or `item_id`: whichever the source entry keys on
- `values`: the remaining source fields verbatim
- `provenance`: `source_file`, `file_sha256`, `extraction_date`
- `coa_attribution`: `status` (`unknown` in M1.14A); `character_advancement` carries an `investigate`
  note pending attribution.

## `character_advancement` is superseded (M1.14B)

The loose `Data/Content/CharacterAdvancementData.json` export is **superseded by
`DBFilesClient/CharacterAdvancement.dbc`** (see
[client-advancement-schema.md](client-advancement-schema.md)), which M1.14B proved is both current and
complete where the loose JSON is neither: the JSON is a stale 2026-02-08 export (its row for spell
`805775` still reads *Fang Venom: Lifeblood*, where the DBC reads the current *Adrenal Venom*), and a
real decode run found it stripped besides — `MaxRank`/`Row` are absent from it entirely, `Tab`/`Type`
are display-name strings rather than ids, and adjacency/cost/investment fields appear in only a small
minority of entries. It proves only a few columns (e.g. `required_level`, `col`) to `high` confidence
on its own.

Accordingly, `coa-client-advancement-v1` records carry `provenance.supersedes: {"source_file":
"CharacterAdvancementData.json"}`, and this `content_kind: "character_advancement"` record is
**retained only as a QA drift signal** — a way to spot-check that the DBC and the loose export still
agree where the loose export does have a value — not as an input to any canonical artifact. Nothing
downstream reads its values for attribution, legality, or graph structure.
