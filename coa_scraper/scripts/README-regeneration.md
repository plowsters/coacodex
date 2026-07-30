# Regenerating client-derived artifacts

This repo does **not** commit the real client-derived outputs — the CoA client extract generation,
the canonical mechanics artifact, and their manifests. Per the redistribution boundary (see
[docs/DECISIONS.md](../../docs/DECISIONS.md) and the M1.14C design spec's
"Redistribution boundary and ignore rules" section), only **synthetic** fixtures, schemas, tests, and
this regeneration doc are tracked. The real artifacts are excluded by file-specific `.gitignore`
rules (see the repo root `.gitignore`) — never a blanket directory ignore, so curated files like
`reports/client_extract/coa_ca_decode_report.json` and
`reports/client_extract/client_only_adjudication.json` stay tracked.

The pipeline is **pointer-only and client-native**: the mechanics build consumes ONLY the published
client-extract generation named by `coa_client_extract.pointer.json` plus the verified Builder
entries (`dist/coa_entries.jsonl`). There is no remote-DB input, no scraped-tooltip input, and a
canonical build makes **zero network requests** (enforced by
`coa_scraper/tests/no-ascensiondb.test.mjs`).

**What a fresh clone can and cannot reproduce:**

- A fresh clone **can** reproduce the Node test suite (`npm test` in `coa_scraper/`) and the Python
  test suite (`python -m pytest`, default tier) — both run against synthetic/in-memory fixtures, no
  client and no StormLib required.
- A fresh clone **can** produce a **fallback** (degraded) `coa_mechanics.fallback.jsonl` from the
  committed Builder entries alone (`npm run build-mechanics:fallback`) — degraded output on separate
  filenames, never the canonical name.
- A fresh clone **cannot** reproduce the **canonical** `coa_mechanics.jsonl` without **your own**
  licensed CoA client install (MPQ archives) and a StormLib binding to read them. The canonical
  build fails closed (`MechanicsBuildError`) if the published generation is missing, and fails
  closed even *with* `--allow-fallback-mechanics` if a generation is present but invalid.

## Step 1 — Regenerate the client extract generation

Requires a local CoA client install and [StormLib](http://www.zezula.net/en/mpq/stormlib.html) (MIT).
Run from the repo root:

```bash
python -m coa_client_extract regenerate \
  --client-root "$HOME/Games/ascension-wow/drive_c/Program Files/Ascension Launcher/resources/ascension-live/Data" \
  --out reports/client_extract \
  --builder-entries coa_scraper/dist/coa_entries.jsonl
```

- `--client-root` points at the client's `Data` directory (containing the base + patch MPQ archives).
- `--out` is where the generation is staged and published: a `generation-<uuid>/` directory of v3
  children (full spell extract, CoA projection, icon catalog, advancement graph, …), its
  `generation.manifest.json`, and the atomic pointer `coa_client_extract.pointer.json`. Publication
  is transactional — the pointer only flips after both-language validation (Python + Node), parity,
  and the policy-bound budget all pass.
- `--builder-entries` supplies the verified Builder scrape used for parity + attribution.
- Without StormLib available, the command fails closed and writes nothing — never a partial or
  degraded client extract.

See [coa_client_extract/README.md](../../coa_client_extract/README.md) for the full command reference
and test tiers (`-m stormlib`, `-m client`).

## Step 2 — Build the mechanics artifact

Run from `coa_scraper/`:

```bash
# Canonical build — REQUIRES Step 1's published generation pointer.
npm run build-mechanics

# Fallback (degraded) build — no client/generation required; NOT canonical, separate filenames.
npm run build-mechanics:fallback
```

- `npm run build-mechanics` invokes `node scripts/build-mechanics-artifacts.mjs
  --builder-entries dist/coa_entries.jsonl
  --client-extract-pointer ../reports/client_extract/coa_client_extract.pointer.json --out dist`.
  The pointer resolves ONLY a strictly published, both-language-validated, within-budget v3
  generation (manifest hash + per-child sha256/byte/record verification before a single row is
  reconciled — see [docs/data/mechanics-schema.md](../../docs/data/mechanics-schema.md)). On success
  it writes `dist/coa_mechanics.jsonl` and `dist/coa_mechanics.manifest.json` with
  `"canonical": true`.
- `npm run build-mechanics:fallback` passes `--allow-fallback-mechanics`. If the generation is
  **entirely absent**, it writes a **degraded** build to the separate filenames
  `dist/coa_mechanics.fallback.jsonl` / `dist/coa_mechanics.fallback.manifest.json`
  (`"canonical": false`, `"client_source": "absent"`) — it never writes to the canonical
  `coa_mechanics.jsonl` name, so a fallback run can't silently shadow (or be mistaken for) a
  canonical one. If a generation **is** present but invalid, the build still fails — even with the
  flag. Only a fully-**absent** generation is eligible to degrade.
- Refresh the committed artifact inventory afterwards with
  `node scripts/write-artifact-manifest.mjs` (writes `reports/coa_artifact_manifest.json`).

## Opt-in icon image downloader (diagnostic only)

`scripts/download-spell-icons.mjs` is the ONLY file in the repo that may contact the retired remote
DB host, and only to fetch icon **image** files by hand. It is never imported by any runtime script,
refuses to run without an explicit `--authorize`, and only writes under a `diagnostic/` directory —
canonical guide icons resolve exclusively from the client icon catalog.

## Redistribution policy gate (forward note — mandatory before M1.16 / public release)

M1.14C does **not** decide, and does not broaden, the redistribution boundary. It records a hard
entry condition for later work: **before M1.16 consumes these artifacts, and before any canonical
public release**, one explicit policy decision must cover **all** client-derived outputs
*consistently* — at minimum the published CoA projection, `coa_mechanics.jsonl`, and any public-site
output that embeds facts derived from those two. This mirrors the M1.15 adjacency-domain entry
condition and must not be dropped or forgotten during later decomposition of M1.16 work. Until that
decision is made, the default remains: real client-derived artifacts are regenerated locally by each
user from their own client, are never committed, and are never republished.
