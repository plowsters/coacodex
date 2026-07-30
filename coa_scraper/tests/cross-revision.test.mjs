// coa_scraper/tests/cross-revision.test.mjs
// E0R.2 T6.4 — the compatibility matrix, derived independently of Python.
//
// Three revisions are `supported` and they genuinely differ: `e0r-v1` carries v3 spell rows with inline
// pointers and the flat v1 icon catalog; `e0r-v2` carries v4 hoisted+interned rows plus the two decoder
// children; `e0r-v3` adds the normalized icon pair. Until something STAGES each one and puts it through
// this validator, "older revisions stay resolvable" is a promise the code makes to itself.
//
// The consumer half matters on its own: the resolver is what a build runs against, and it derives the
// required-child set from the generation's OWN staged contract. If it ever read `current` instead, every
// generation published before today's revision would stop resolving — silently, at the boundary that is
// supposed to be independent.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

import { GenerationResolveError, ICON_ASSET_CHILD, loadContractRegistry, loadCurrentContract,
         resolveGeneration, validateCandidateByPath } from "../scripts/lib/generation.mjs";
import { FIELD_DESCRIPTORS_CHILD, WIRE_SCHEMA_CHILD } from "../scripts/lib/mechanics-projection.mjs";
import { buildCandidate, loadCorpus, supportedContract } from "./helpers/candidate.mjs";

const SUPPORTED = Object.keys(loadContractRegistry().supported).sort();
const CURRENT = loadCurrentContract()[0];

test("the matrix covers every supported revision", () => {
  assert.deepEqual(SUPPORTED, Object.keys(loadContractRegistry().supported).sort());
  assert.ok(SUPPORTED.length > 1 && SUPPORTED.some((r) => r !== CURRENT),
            "a matrix over `current` alone proves nothing about older revisions");
});

for (const revision of SUPPORTED) {
  test(`a candidate under ${revision} validates`, () => {
    const { genDir, lockPath } = buildCandidate({ contract: supportedContract(revision) });
    const r = validateCandidateByPath(genDir, { lockPath });
    assert.equal(r.manifest.binding.generation_contract.revision, revision);
  });

  test(`a published generation under ${revision} resolves through the pointer`, () => {
    // Not the same check twice: the candidate path validates by directory, the resolver arrives through
    // the POINTER and re-derives the required-child set from the generation's own staged contract.
    const { root } = buildCandidate({ contract: supportedContract(revision), publish: true });
    const r = resolveGeneration(root);
    assert.equal(r.manifest.binding.generation_contract.revision, revision);
    assert.deepEqual(Object.keys(r.children).sort(),
                     Object.keys(supportedContract(revision)[1].children).sort());
  });
}

// --- a child belongs to a revision, not to the working tree ---

for (const [revision, foreign] of [
  ["e0r-v1", FIELD_DESCRIPTORS_CHILD],          // e0r-v2 introduced it
  ["e0r-v1", WIRE_SCHEMA_CHILD],                // e0r-v2 introduced it
  ["e0r-v1", ICON_ASSET_CHILD],                 // e0r-v3 introduced it
  ["e0r-v2", ICON_ASSET_CHILD],
]) {
  test(`a ${revision} generation carrying ${foreign} from a later revision is rejected`, () => {
    const { genDir, lockPath } = buildCandidate({ contract: supportedContract(revision),
                                                  extraChild: [foreign, "{}\n"] });
    assert.throws(() => validateCandidateByPath(genDir, { lockPath }), /unregistered child/);
  });
}

test("the same child is required by one revision and refused by another", () => {
  // `coa_client_icon_assets.jsonl` is required under e0r-v3 and unregistered under e0r-v1. The
  // requirement is read from the generation's own revision — deriving it from `current` is what would
  // make every older generation unresolvable the moment a revision ships.
  const dropped = buildCandidate({ contract: supportedContract("e0r-v3"), drop: [ICON_ASSET_CHILD] });
  assert.throws(() => validateCandidateByPath(dropped.genDir, { lockPath: dropped.lockPath }),
                new RegExp(`required child ${ICON_ASSET_CHILD} missing`));
  const older = buildCandidate({ contract: supportedContract("e0r-v1") });
  assert.doesNotThrow(() => validateCandidateByPath(older.genDir, { lockPath: older.lockPath }));
});

// --- each revision pins exactly one encoding ---

for (const [revision, child, rows] of [
  ["e0r-v1", "coa_client_spell.jsonl", (c) => ({ full: c.validFull() })],        // interned cells in a v3 generation
  ["e0r-v3", "coa_client_spell.jsonl", (c) => ({ full: c.validFullV3() })],      // inline pointers in a v4 generation
  ["e0r-v2", "coa_client_spell_icons.jsonl", (c) => ({ icons: c.validIconsV2() })],  // associations with no asset child
  ["e0r-v3", "coa_client_spell_icons.jsonl", (c) => ({ icons: c.validIcons() })],    // the flat catalog after normalizing
]) {
  test(`a ${revision} generation using another revision's ${child} encoding is rejected`, () => {
    // A revision names one SHAPE per child, and every shape pins the row schema_version it accepts, so
    // mixing encodings is refused at the row rather than discouraged in a note.
    const { genDir, lockPath } = buildCandidate({ contract: supportedContract(revision),
                                                  ...rows(loadCorpus()) });
    assert.throws(() => validateCandidateByPath(genDir, { lockPath }),
                  new RegExp(`shape: child ${child.replace(/\./g, "\\.")}`));
  });
}

// --- the declared child_schema_version is load-bearing ---

for (const revision of SUPPORTED) {
  test(`a ${revision} manifest registers the schema_version its revision declares`, () => {
    const { genDir } = buildCandidate({ contract: supportedContract(revision) });
    const manifest = JSON.parse(fs.readFileSync(path.join(genDir, "manifest.json"), "utf8"));
    for (const [name, spec] of Object.entries(supportedContract(revision)[1].children)) {
      assert.equal(manifest.children[name].schema_version, spec.child_schema_version, name);
    }
  });
}

test("a child registered under another revision's schema_version is rejected", () => {
  // Every revision DECLARES a child_schema_version per child. If nothing checks it the field is
  // decorative, and a consumer that dispatches on the manifest-registered version can be handed v4 rows
  // labelled v3 — with every hash, byte count and record count perfectly valid.
  const { genDir, lockPath } = buildCandidate({
    forgeChildSchema: ["coa_client_spell.jsonl", "coa-client-spell-v3"] });
  assert.throws(() => validateCandidateByPath(genDir, { lockPath }),
                (e) => e instanceof GenerationResolveError && /schema_version/.test(e.message));
});

test("the resolver refuses a published generation whose child label disagrees with its revision", () => {
  // The consumer boundary re-checks it independently: a candidate validator cannot un-publish a pointer
  // that already flipped.
  const { root } = buildCandidate({ publish: true,
                                    forgeChildSchema: ["coa_client_spell_icons.jsonl", "coa-client-spell-icons-v1"] });
  assert.throws(() => resolveGeneration(root), /schema_version/);
});
