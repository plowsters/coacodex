from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from .contracts import (CANDIDATE_MUTABLE_KEYS, ContractError, GENERATION_CONTRACT_CHILD,
                        GENERATION_CONTRACT_SCHEMA, ICON_ASSET_STATUSES, generation_contract_sha256,
                        load_current_contract, load_supported_contract, validate_generation_contract)
from .manifest import build_manifest_v3
from .spell_layout import compute_policy_sha256, load_spell_policy
from .shapes import SHAPES, ShapeError
from .spell_record import _expand_compact as _expand_cell
from .topology import topology_matches_bound

POINTER_SCHEMA = "coa-client-extract-pointer-v1"
POINTER_NAME = "coa_client_extract.pointer.json"
MANIFEST_NAME = "manifest.json"
LOCK_NAME = ".publish.lock"
_RESERVED = {MANIFEST_NAME, POINTER_NAME, LOCK_NAME}

# The PRODUCER's target: what regenerate must emit today, derived from the CURRENT contract revision
# rather than restated as a constant (design A5; E0R.2 T1.1). The manifest is NOT a child; the contract
# IS one, so a consumer can re-check the generation under the contract it was produced with.
CURRENT_REQUIRED_CHILDREN = tuple(sorted(load_current_contract()[1]["children"]))
# Back-compat alias for existing importers; new code should say which one it means.
REQUIRED_CHILDREN = CURRENT_REQUIRED_CHILDREN


def required_children_for(contract: dict) -> tuple[str, ...]:
    """A RESOLVER's requirement comes from the generation's own verified staged contract, never from
    `current`. Deriving it from `current` would make every generation published under an older revision
    unresolvable the moment a new revision ships — breaking rollback and the predecessor chain the
    publish transaction reads (E0R.2 T1.1)."""
    return tuple(sorted(n for n, s in contract["children"].items() if not s["optional"]))


def candidate_trust_sha256(manifest: dict) -> str:
    """Digest the COMPLETE manifest minus ONLY the explicitly-mutable keys (publication_state,
    validation, budget) and the digest field itself — a strict complete view, so an unknown/new
    top-level field is never silently ignored, and only publication_state (candidate->published),
    /validation, and /budget may move candidate->final."""
    trust = {k: v for k, v in manifest.items()
             if k not in CANDIDATE_MUTABLE_KEYS and k != "candidate_trust_sha256"}
    return _sha256(json.dumps(trust, sort_keys=True, ensure_ascii=False).encode("utf-8"))


class PublishError(Exception):
    """A generation could not be staged/published (bad child name, collision, or staging failure)."""


class ResolveError(Exception):
    """The active generation pointer failed validation (schema, containment, hash, or a child mismatch).
    Fails closed — a consumer never reads an unvalidated generation child."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_child_name(name: str) -> None:
    if not name or name in _RESERVED:
        raise PublishError(f"reserved or empty child name {name!r}")
    if os.path.isabs(name) or ".." in Path(name).parts or "/" in name or "\\" in name:
        raise PublishError(f"unsafe child name {name!r} (no absolute/traversal/separators)")


class GenerationWriter:
    """Stages a new immutable generation under `root/gen-<uuid4>/` (exist_ok=False so two concurrent
    publishers never collide), streams each child to a temp file while hashing + counting it, then on
    publish writes the binding manifest and finally a validated pointer LAST."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.generation_id = uuid.uuid4().hex
        self.gen_dir = self.root / f"gen-{self.generation_id}"
        self.gen_dir.mkdir(exist_ok=False)          # collision-safe; a reused id raises FileExistsError
        self._children: dict[str, dict] = {}
        self._lock_fh = None                        # publish lock: predecessor read -> pointer replace

    def _stage(self, name: str, body: bytes, records: int, schema_version: str) -> None:
        _safe_child_name(name)
        if name in self._children:
            raise PublishError(f"duplicate child {name!r}")
        if not schema_version:
            raise PublishError(f"child {name!r} needs a non-empty schema_version")
        tmp = self.gen_dir / f".{name}.tmp-{os.getpid()}"
        tmp.write_bytes(body)
        os.replace(tmp, self.gen_dir / name)
        self._children[name] = {"sha256": _sha256(body), "byte_length": len(body),
                                "records": records, "schema_version": schema_version}

    def add_jsonl_lines(self, name: str, lines, *, schema_version: str) -> None:
        """Stage a JSONL child from an iterable of PRE-SERIALIZED lines (bytes, each one record ending in
        a newline), streamed straight to disk with incremental sha256/byte/record accounting — no
        whole-child body is ever materialized (design A4, E0R.1 T4.1)."""
        _safe_child_name(name)
        if name in self._children:
            raise PublishError(f"duplicate child {name!r}")
        if not schema_version:
            raise PublishError(f"child {name!r} needs a non-empty schema_version")
        tmp = self.gen_dir / f".{name}.tmp-{os.getpid()}"
        digest, total, records = hashlib.sha256(), 0, 0
        with open(tmp, "wb") as fh:
            for line in lines:
                digest.update(line)
                fh.write(line)
                total += len(line)
                records += 1
        os.replace(tmp, self.gen_dir / name)
        self._children[name] = {"sha256": digest.hexdigest(), "byte_length": total,
                                "records": records, "schema_version": schema_version}

    def add_jsonl(self, name: str, records, *, schema_version: str) -> None:
        """records is any iterable of dicts (a generator streams row-by-row to disk)."""
        self.add_jsonl_lines(
            name, ((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
                   for r in records),
            schema_version=schema_version)

    def add_json(self, name: str, doc: dict, *, schema_version: str) -> None:
        body = (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        self._stage(name, body, 1, schema_version)   # a non-JSONL child is defined as records == 1

    def _predecessor(self) -> str | None:
        pointer = self.root / POINTER_NAME
        if not pointer.is_file():
            return None
        try:
            return json.loads(pointer.read_text(encoding="utf-8")).get("generation_id")
        except (ValueError, OSError):
            return None

    # --- E0R transactional candidate -> pointer publication (design A5) ---

    def _acquire_publish_lock(self) -> None:
        if self._lock_fh is None:
            fh = open(self.root / LOCK_NAME, "w")
            fcntl.flock(fh, fcntl.LOCK_EX)
            self._lock_fh = fh

    def _release_publish_lock(self) -> None:
        if self._lock_fh is not None:
            fcntl.flock(self._lock_fh, fcntl.LOCK_UN)
            self._lock_fh.close()
            self._lock_fh = None

    def abort_publication(self) -> None:
        """Release the publish lock WITHOUT touching the pointer (idempotent; a no-op after a successful
        finalize). The staged candidate stays on disk, never pointer-resolvable, awaiting retention."""
        self._release_publish_lock()

    def publish_candidate(self, *, base_manifest: dict, binding: dict,
                          unknown_symbol_inventory: dict | None = None) -> dict:
        """Write the CANDIDATE manifest (publication_state='candidate', candidate_trust_sha256) into the
        generation dir WITHOUT touching the pointer. Acquires the publish lock BEFORE the predecessor read
        and holds it through finalize_and_publish (or abort_publication), so a concurrent publisher can
        never stage against a predecessor that is about to be replaced. A candidate is never
        pointer-resolvable, so an interrupted publish leaves no half-live generation to be collected."""
        self._acquire_publish_lock()
        try:
            manifest = build_manifest_v3(
                base=base_manifest, generation_id=self.generation_id, published_at=time.time_ns(),
                predecessor_generation_id=self._predecessor(), children=dict(self._children),
                unknown_symbol_inventory=unknown_symbol_inventory or {}, binding=binding,
                publication_state="candidate")
            manifest["candidate_trust_sha256"] = candidate_trust_sha256(manifest)
            body = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            (self.gen_dir / MANIFEST_NAME).write_bytes(body)
        except BaseException:
            self._release_publish_lock()
            raise
        return manifest

    def finalize_and_publish(self, *, candidate_manifest: dict, validation: dict, budget: dict) -> dict:
        """Produce the FINAL manifest (differs from the candidate ONLY in the CANDIDATE_MUTABLE_KEYS:
        publication_state->published, plus /validation and /budget) reproducing the identical
        candidate_trust_sha256, then publish the pointer LAST. Runs under the publish lock held since
        publish_candidate's predecessor read, and REVALIDATES the predecessor under that lock before the
        replace — a candidate staged against a superseded predecessor fails instead of last-writer-winning
        the generation chain. The lock is released on every exit path."""
        try:
            final = dict(candidate_manifest)
            final["publication_state"] = "published"
            final["validation"] = validation
            final["budget"] = budget
            if candidate_trust_sha256(final) != candidate_manifest.get("candidate_trust_sha256"):
                raise PublishError("finalize changed a trust-critical field (candidate_trust_sha256 differs)")
            body = (json.dumps(final, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

            self._acquire_publish_lock()               # no-op when held since publish_candidate
            current = self._predecessor()
            if current != candidate_manifest.get("predecessor_generation_id"):
                raise PublishError(
                    f"active generation changed since the candidate was staged "
                    f"(pointer now {current!r}, candidate predecessor "
                    f"{candidate_manifest.get('predecessor_generation_id')!r})")
            (self.gen_dir / MANIFEST_NAME).write_bytes(body)   # overwrite candidate with final
            pointer = {"schema_version": POINTER_SCHEMA, "generation_id": self.generation_id,
                       "manifest_path": f"gen-{self.generation_id}/{MANIFEST_NAME}",
                       "manifest_sha256": _sha256(body)}
            ptr_body = (json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            tmp = self.root / f".{POINTER_NAME}.tmp-{os.getpid()}"
            tmp.write_bytes(ptr_body)
            os.replace(tmp, self.root / POINTER_NAME)          # atomic pointer publish, LAST
        finally:
            self._release_publish_lock()
        return final


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _scan_child(path: Path, *, jsonl: bool) -> tuple[str, int, int]:
    """Chunked integrity scan — sha256 + byte length + record count (non-empty lines for JSONL, else 1)
    without ever holding the child in memory (mirrors Node countJsonlRecords) (design A4, E0R.1 T4.1)."""
    digest, total, records, carry = hashlib.sha256(), 0, 0, b""
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if jsonl:
                lines = (carry + chunk).split(b"\n")
                carry = lines.pop()
                records += sum(1 for l in lines if l.strip())
    if jsonl and carry.strip():
        records += 1
    return digest.hexdigest(), total, records if jsonl else 1


class _Cursor:
    """A forward, ascending-by-spell_id cursor that enforces sorted-unique order as it advances — no
    set/list materialization of the children."""
    def __init__(self, it, label):
        self._it, self._label, self._prev = iter(it), label, None
        self.row = None
        self.advance()

    def advance(self):
        self.row = next(self._it, None)
        if self.row is not None:
            sid = self.row["spell_id"]
            if self._prev is not None and sid <= self._prev:
                raise ResolveError(f"sorted_unique_ids: {self._label} duplicate/out-of-order spell_id {sid}")
            self._prev = sid
        return self.row


def _expand_full_raw(sid, raw, policy):
    """Expand a full child's compact `raw` block into canonical field observations (the SAME expansion the
    projection is built from), failing closed on a tampered/unresolvable cell."""
    try:
        return {f: _expand_cell(cell, policy) for f, cell in raw.items()}
    except (KeyError, TypeError, ValueError) as exc:
        raise ResolveError(f"compact_raw_expands_to_envelope: {sid} unresolvable compact cell ({exc})")


def _identity_agrees(frow, prow) -> None:
    """identity_agrees: the full-table row and its projection must agree on identity + normalized
    mechanics + attribution (the projection is a re-view of the same spell, never a divergent one)."""
    if frow.get("name") != prow.get("name"):
        raise ResolveError(f"identity_agrees: spell {frow['spell_id']} name differs full vs projection")
    if frow.get("mechanics") != prow.get("mechanics"):
        raise ResolveError(f"identity_agrees: spell {frow['spell_id']} mechanics differ full vs projection")
    if frow.get("coa_attribution") != prow.get("coa_attribution"):
        raise ResolveError(f"identity_agrees: spell {frow['spell_id']} attribution differs full vs projection")


def _verify_icon_row(r: dict) -> None:
    """Icon id/path agreement (mirrors Node verifyIconRow): a valid asset_status, a placeholder
    (unresolved join) has a null client_path while a resolved status carries one, and converted_ref
    exists iff the row is `converted`."""
    status = r.get("asset_status")
    if status not in ICON_ASSET_STATUSES:
        raise ResolveError(f"icon asset_status {status!r} not in {ICON_ASSET_STATUSES}")
    if status != "converted" and r.get("converted_ref"):
        raise ResolveError(f"icon {r.get('spell_id')}: non-converted row carries a converted_ref")
    if status == "converted" and not r.get("converted_ref"):
        raise ResolveError(f"icon {r.get('spell_id')}: converted row missing converted_ref")
    if status == "placeholder" and r.get("client_path") is not None:
        raise ResolveError(f"icon id/path: placeholder spell {r.get('spell_id')} carries a client_path")
    if status in ("source_only", "converted") and r.get("client_path") is None:
        raise ResolveError(f"icon id/path: {status} spell {r.get('spell_id')} missing client_path")


def _cross_child(gen_dir: Path, children: dict, policy=None, shapes: dict | None = None) -> dict:
    """Streaming merge-join over ascending spell_id across the three spell children (design A5) — cursors
    only, no set/list materialization. Enforces projection⊆is_coa, projection-within-domain, the disjoint
    v3 dialects (full=compact `raw`, projection=rich `field_observations`), identity/mechanics/attribution
    agreement, the compact_raw_expands_to_envelope EQUALITY (expand(full.raw) == projection.field_observations),
    the icon catalog as EXACTLY the full domain (lockstep 1:1 — a missing, orphan, or trailing icon row
    fails), per-row icon id/path agreement, converted->bundle-required, and sorted-unique ids."""
    if policy is None:
        policy = load_spell_policy(
            json.loads((gen_dir / "spell_layout_v2.json").read_text(encoding="utf-8")))
    # Shape-checked AS the rows stream through the cursors — one pass, no second read and no retained
    # row list (E0R.2 T2.2).
    shapes = shapes or {}

    def _shaped(name):
        rows = _read_jsonl(gen_dir / name)
        shape = shapes.get(name)
        if shape is None:
            return rows
        return (_check_shape(shape, row, name) or row for row in rows)

    full = _Cursor(_shaped("coa_client_spell.jsonl"), "full")
    proj = _Cursor(_shaped("coa_client_spell_coa.jsonl"), "projection")
    icons = _Cursor(_shaped("coa_client_spell_icons.jsonl"), "icons")
    any_converted = False
    full_count = is_coa_count = 0
    while full.row is not None:
        full_count += 1
        sid = full.row["spell_id"]
        # The icon catalog advances in LOCKSTEP with the full table: exactly one icon row per full row,
        # so an orphan icon (below/between full ids) is a mismatch, never silently skipped.
        if icons.row is None:
            raise ResolveError(f"icons_agree: spell {sid} lacks an icon-catalog row")
        if icons.row["spell_id"] != sid:
            raise ResolveError(f"icons_agree: icon row spell_id {icons.row['spell_id']} != full {sid}")
        _verify_icon_row(icons.row)
        any_converted = any_converted or icons.row.get("asset_status") == "converted"
        icons.advance()
        if proj.row is not None and proj.row["spell_id"] < sid:
            raise ResolveError(f"projection_within_domain: {proj.row['spell_id']} outside is_coa domain")
        # The full child is the COMPACT dialect: it carries `raw`, never `field_observations`.
        if "raw" not in full.row:
            raise ResolveError(f"full_is_compact: spell {sid} full row missing compact raw")
        if "field_observations" in full.row:
            raise ResolveError(f"full_is_compact: spell {sid} full row carries field_observations (rich dialect)")
        expanded = _expand_full_raw(sid, full.row["raw"], policy)
        is_coa = full.row.get("coa_attribution", {}).get("is_coa") is True
        is_coa_count += 1 if is_coa else 0
        if is_coa:
            if proj.row is None or proj.row["spell_id"] != sid:
                raise ResolveError(f"projection_is_coa_subset: {sid} missing from projection")
            # The projection is the RICH dialect: it carries `field_observations`, never compact `raw`.
            if "raw" in proj.row:
                raise ResolveError(f"projection_is_rich: spell {sid} projection carries compact raw")
            if "field_observations" not in proj.row:
                raise ResolveError(f"projection_is_rich: spell {sid} projection missing field_observations")
            _identity_agrees(full.row, proj.row)
            if expanded != proj.row["field_observations"]:
                raise ResolveError(
                    f"compact_raw_expands_to_envelope: spell {sid} full.raw expansion != projection.field_observations")
            proj.advance()
        full.advance()
    if proj.row is not None:
        raise ResolveError(f"projection_within_domain: {proj.row['spell_id']} outside is_coa domain")
    if icons.row is not None:
        raise ResolveError(f"icons_agree: trailing icon row {icons.row['spell_id']} beyond the full domain")
    if any_converted and "coa_client_spell_icons.bundle.tar" not in children:
        raise ResolveError("icon bundle required: a converted row exists but no bundle child is registered")
    # Tallies the cursors derived themselves, so the contract can cross-check them against the
    # manifest-registered record counts (E0R.2 T2.1).
    return {"full": full_count, "is_coa": is_coa_count}


def _validate_children_by_path(gen_dir: Path, manifest: dict) -> dict:
    """Per-child integrity (hash/bytes/records/schema/uniqueness) validated directly by path, without a
    pointer — reused by both the candidate validator and resolve_active_generation."""
    children = manifest.get("children", {})
    resolved: dict[str, Path] = {}
    seen: set[str] = set()
    for name, meta in children.items():
        _safe_name_resolve(name)
        if name in seen:
            raise ResolveError(f"duplicate child {name!r}")
        seen.add(name)
        child_path = (gen_dir / name).resolve()
        if child_path.parent != gen_dir.resolve():
            raise ResolveError(f"child {name!r} escapes the generation directory")
        if not child_path.is_file():
            raise ResolveError(f"child {name!r} missing")
        sha, byte_length, actual = _scan_child(child_path, jsonl=name.endswith(".jsonl"))
        if sha != meta.get("sha256"):
            raise ResolveError(f"child {name!r} sha256 mismatch")
        if byte_length != meta.get("byte_length"):
            raise ResolveError(f"child {name!r} byte_length mismatch")
        if actual != meta.get("records"):
            raise ResolveError(f"child {name!r} record count mismatch ({actual} != {meta.get('records')})")
        if not meta.get("schema_version"):
            raise ResolveError(f"child {name!r} missing schema_version")
        resolved[name] = child_path
    return resolved


DEFAULT_LOCK_PATH = Path(__file__).resolve().parents[1] / "coa_scraper" / "config" / "spell_layout.lock.json"


def _supported_policy_sha256(lock_path: Path | None) -> str:
    """The digest of the policy this validator LOCALLY supports, read from the committed lock — the same
    artifact the Node boundary checks. A candidate cannot supply it (E0R.2 T2.1)."""
    path = Path(lock_path) if lock_path is not None else DEFAULT_LOCK_PATH
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResolveError(f"policy lock unreadable: {exc}") from exc
    sha = lock.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise ResolveError(f"policy lock {str(path)!r} carries no usable sha256")
    return sha


def _trusted_policy(gen_dir: Path, manifest: dict, lock_path: Path | None):
    """The reviewed policy the cardinality rules are resolved against, established in three steps so a
    failure names which link broke (E0R.2 T2.1).

    Deriving a child's expected count from `manifest.binding.topology` is CIRCULAR: a malformed candidate
    sets that count to 1, writes one row, recomputes `candidate_trust_sha256`, and satisfies the
    equality. The count has to come from something the validator trusts independently of the candidate.
    """
    staged_path = gen_dir / "spell_layout_v2.json"
    if not staged_path.is_file():
        raise ResolveError("required child 'spell_layout_v2.json' missing; the generation is unbound")
    try:
        staged = json.loads(staged_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ResolveError(f"staged policy child is not valid JSON: {exc}") from exc

    # 1. the staged policy IS the locally supported policy (recomputed, never self-declared).
    actual = compute_policy_sha256(staged)
    supported = _supported_policy_sha256(lock_path)
    if actual != supported:
        raise ResolveError(
            f"staged policy {actual[:16]} is not the supported policy {supported[:16]}: a candidate "
            "cannot bring its own policy and be believed")
    # 2. the manifest binds that same policy.
    bound_sha = (manifest.get("binding") or {}).get("policy_sha256")
    if bound_sha != actual:
        raise ResolveError(
            f"binding.policy_sha256 {str(bound_sha)[:16]} != the staged policy child {actual[:16]}")
    try:
        policy = load_spell_policy(staged)
    except Exception as exc:                                   # SpellPolicyError and friends
        raise ResolveError(f"staged policy child rejected: {exc}") from exc
    if policy.bound is None:
        raise ResolveError(
            "staged policy is unbound (bound: null): it was never proven against a client capture, so "
            "the generation has no provable source domain")
    # 3. the recorded topology IS the reviewed bound, facet for facet.
    mismatch = topology_matches_bound((manifest.get("binding") or {}).get("topology") or {}, policy.bound)
    if mismatch:
        raise ResolveError(f"binding.topology does not match the reviewed bound: {mismatch}")
    return policy


def _source_record_count(policy, table: str, child: str) -> int:
    tables = policy.bound["tables"]
    if table not in tables:
        raise ResolveError(
            f"child {child!r} cites source table {table!r}, which the reviewed policy does not bind; "
            "its cardinality cannot be evaluated")
    return tables[table]["header"]["record_count"]


def _declared(manifest: dict, child: str, keys: set[str]) -> dict:
    declared = ((manifest.get("binding") or {}).get("derivations") or {}).get(child)
    if not isinstance(declared, dict) or set(declared) != keys:
        raise ResolveError(
            f"child {child!r} needs a binding.derivations entry with exactly {sorted(keys)}, got "
            f"{sorted(declared) if isinstance(declared, dict) else type(declared).__name__}")
    for key in keys - {"source"}:
        value = declared[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ResolveError(f"child {child!r} derivation {key} must be a non-negative integer")
    return declared


def _shape_for(name: str, spec: dict):
    shape = SHAPES.get(spec["shape"])
    if shape is None:
        raise ResolveError(
            f"child {name!r} names shape {spec['shape']!r}, which this validator does not implement; "
            "an unimplemented shape is a gate that silently does nothing")
    return shape


def _check_shape(shape, doc, name: str) -> None:
    try:
        shape(doc)
    except ShapeError as exc:
        raise ResolveError(f"shape: child {name!r} {exc}") from exc


def _assert_single_document(gen_dir: Path, name: str) -> None:
    """A JSON child must PARSE as exactly one document.

    `_scan_child` registers `records: 1` for every non-JSONL child unconditionally — it hashes bytes and
    counts nothing — so a record-count comparison alone can never fail here and the rule would be
    decorative. Two concatenated documents hash and byte-count perfectly consistently; only parsing
    catches them. This is also the only thing that checks a JSON child is well-formed at all before a
    consumer reads it."""
    try:
        json.loads((gen_dir / name).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ResolveError(
            f"single_document: child {name!r} is not a single JSON document ({exc})") from exc


def _resolve_cardinality(name: str, spec: dict, records: int, policy, manifest: dict,
                         counts: dict, gen_dir: Path | None = None) -> None:
    """Enforce ONE child's contract cardinality against the REVIEWED POLICY (E0R.2 T2.1).

    `counts` carries the numbers the streaming merge-join derived independently (full rows, is_coa rows,
    icon rows); rules that need them are resolved after `_cross_child` runs.
    """
    rule = spec["cardinality"]["rule"]
    if rule == "single_document":
        if records != 1:
            raise ResolveError(f"single_document: child {name!r} carries {records} records, not 1")
        if gen_dir is not None:
            _assert_single_document(gen_dir, name)
    elif rule == "min":
        if records < spec["cardinality"]["min"]:
            raise ResolveError(
                f"min: child {name!r} carries {records} records, below the floor "
                f"{spec['cardinality']['min']}")
    elif rule in ("reviewed_bound_record_count", "derived_from_source_topology"):
        expected = _source_record_count(policy, spec["cardinality"]["source_table"], name)
        if records != expected:
            raise ResolveError(
                f"{rule}: child {name!r} carries {records} records but the reviewed bound for "
                f"{spec['cardinality']['source_table']!r} states {expected}")
    elif rule == "declared_derivation":
        table = spec["cardinality"]["source_table"]
        declared = _declared(manifest, name, {"source", "kept", "rejected"})
        if declared["source"] != table:
            raise ResolveError(
                f"declared_derivation: child {name!r} derivation names source {declared['source']!r}, "
                f"but the contract states {table!r}")
        expected = _source_record_count(policy, table, name)
        if declared["kept"] + declared["rejected"] != expected:
            raise ResolveError(
                f"declared_derivation: child {name!r} accounting does not close — kept "
                f"{declared['kept']} + rejected {declared['rejected']} != reviewed source {expected}")
        if declared["kept"] != records:
            raise ResolveError(
                f"declared_derivation: child {name!r} declares {declared['kept']} kept but carries "
                f"{records} records")
    elif rule == "declared_content_derivation":
        declared = _declared(manifest, name, {"source", "source_entries", "kept", "rejected"})
        if declared["source"] != "content_json":
            raise ResolveError(
                f"declared_content_derivation: child {name!r} derivation names source "
                f"{declared['source']!r}, not 'content_json'")
        reviewed = sum(f["source_entries"] for f in policy.content_sources["required_files"].values())
        if declared["source_entries"] != reviewed:
            raise ResolveError(
                f"declared_content_derivation: child {name!r} declares {declared['source_entries']} "
                f"source entries but the reviewed content_sources state {reviewed}")
        if declared["kept"] + declared["rejected"] != reviewed:
            raise ResolveError(
                f"declared_content_derivation: child {name!r} accounting does not close — kept "
                f"{declared['kept']} + rejected {declared['rejected']} != reviewed source {reviewed}")
        if declared["kept"] != records:
            raise ResolveError(
                f"declared_content_derivation: child {name!r} declares {declared['kept']} kept but "
                f"carries {records} records")
    elif rule == "equals_full_spell_records":
        if records != counts["full"]:
            raise ResolveError(
                f"equals_full_spell_records: child {name!r} carries {records} records but the full "
                f"spell child carries {counts['full']}")
    elif rule == "equals_is_coa_full_records":
        if records != counts["is_coa"]:
            raise ResolveError(
                f"equals_is_coa_full_records: child {name!r} carries {records} records but the full "
                f"child holds {counts['is_coa']} is_coa spells")
    else:                                                      # pragma: no cover - validate() gates this
        raise ResolveError(f"child {name!r} cardinality rule {rule!r} has no resolver")


# Rules whose expectation is derived by the streaming merge-join, so they are resolved AFTER it. They
# cross-check two independently-derived numbers (the manifest-registered record count against the
# cursor's own tally); the merge-join itself remains the authoritative row-level enforcement.
_CROSS_CHILD_RULES = frozenset({"equals_full_spell_records", "equals_is_coa_full_records"})


def _staged_contract(gen_dir: Path, manifest: dict) -> dict:
    """The contract the generation was PRODUCED under, established by a THREE-WAY agreement (E0R.2
    T1.1/T1.2). A contract read from the working tree is not bound to anything: a generation produced
    under contract A could otherwise be validated under whichever contract happened to be checked out.

      1. the STAGED child — structurally valid on its own terms;
      2. the manifest BINDING — same revision, same canonical digest. `binding` is inside
         TRUST_CRITICAL_MANIFEST_KEYS, so candidate trust already covers it and the binding cannot be
         edited after the fact;
      3. the validator's OWN registry — set MEMBERSHIP, never equality with `current`, so a generation
         published under an older supported revision stays resolvable. Without that distinction,
         rollback and the predecessor chain the publish transaction reads break the moment a new
         revision ships.

    Dispatch is by canonical digest, so a re-serialized staged copy (indented, key-sorted) of a
    supported revision matches while any semantic edit does not. Returns the REGISTRY's copy — identical
    content by hash, but reading the trusted copy means a future parser difference cannot be exploited
    through the staged file."""
    path = gen_dir / GENERATION_CONTRACT_CHILD
    if not path.is_file():
        raise ResolveError(
            f"required child {GENERATION_CONTRACT_CHILD!r} missing: the generation does not declare "
            "the contract it was produced under")
    try:
        staged = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ResolveError(f"staged generation contract is not valid JSON: {exc}") from exc
    try:
        validate_generation_contract(staged)
    except ContractError as exc:
        raise ResolveError(f"staged generation contract rejected: {exc}") from exc

    staged_sha = generation_contract_sha256(staged)
    bound = (manifest.get("binding") or {}).get("generation_contract")
    if not isinstance(bound, dict):
        raise ResolveError(
            "manifest binding.generation_contract missing: the generation stages a contract but does "
            "not bind it, so the staged copy would be trusted on its own word")
    if bound.get("schema_version") != GENERATION_CONTRACT_SCHEMA:
        raise ResolveError(
            f"binding.generation_contract schema_version {bound.get('schema_version')!r} "
            f"(expected {GENERATION_CONTRACT_SCHEMA!r})")
    if bound.get("sha256") != staged_sha:
        raise ResolveError(
            f"binding.generation_contract: the staged child hashes {staged_sha[:16]} but the binding "
            f"names {str(bound.get('sha256'))[:16]}")
    if bound.get("revision") != staged["revision"]:
        raise ResolveError(
            f"binding.generation_contract: staged revision {staged['revision']!r} != bound revision "
            f"{bound.get('revision')!r}")
    try:
        return load_supported_contract(bound["revision"], staged_sha)
    except ContractError as exc:
        raise ResolveError(f"generation_contract: {exc}") from exc


def validate_candidate_generation(gen_dir: Path, *, lock_path: Path | None = None) -> dict:
    """Validate a staged CANDIDATE generation by path (not via the pointer): the manifest is a candidate,
    the staged contract agrees three ways, every child the contract requires is present and per-child
    valid, no child is present that the contract does not register, every child's CARDINALITY holds
    against the reviewed policy, the streaming cross-child merge-join holds, and the icon bundle is
    present iff any converted row exists. Raises ResolveError on any failure.

    `lock_path` names the policy lock that says which policy this validator locally supports; production
    uses the committed lock, which is also the artifact the Node boundary checks."""
    gen_dir = Path(gen_dir)
    manifest_path = gen_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ResolveError("candidate manifest missing")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("publication_state") != "candidate":
        raise ResolveError(f"not a candidate generation (publication_state={manifest.get('publication_state')!r})")
    if manifest.get("candidate_trust_sha256") != candidate_trust_sha256(manifest):
        raise ResolveError("candidate_trust_sha256 does not cover the manifest")
    # The contract is established BEFORE any per-child work: it is what says which children are required,
    # and an unbound/unsupported generation should fail as that rather than as an unrelated child error.
    contract = _staged_contract(gen_dir, manifest)
    resolved = _validate_children_by_path(gen_dir, manifest)
    registered = set(contract["children"])
    for name in required_children_for(contract):
        if name not in resolved:
            raise ResolveError(f"required child {name!r} missing from the candidate generation")
    # The contract is a WHITELIST. candidate_trust_sha256 AUTHENTICATES an added child — it covers
    # `children`, so a child added to both the manifest and the directory is perfectly self-consistent —
    # but authenticating is not rejecting. Unregistered files on disk are caught too: a consumer that
    # globs the directory would otherwise read something no contract describes.
    for name in sorted(set(resolved) | {p.name for p in gen_dir.iterdir() if p.is_file()}):
        if name not in registered and name not in _RESERVED:
            raise ResolveError(
                f"unregistered child {name!r}: the contract is a whitelist, and candidate trust "
                "authenticates an added child rather than rejecting it")

    policy = _trusted_policy(gen_dir, manifest, lock_path)
    children_meta = manifest.get("children", {})
    # Cardinalities that do not depend on the merge-join first, so a truncated generation fails fast.
    for name, spec in contract["children"].items():
        if spec["cardinality"]["rule"] not in _CROSS_CHILD_RULES and name in children_meta:
            _resolve_cardinality(name, spec, children_meta[name]["records"], policy, manifest, {},
                                 gen_dir)
    # SHAPES: every child is type-checked against the validator its contract names. The three spell
    # children are checked inside the merge-join below so they are read exactly once; every other child
    # is streamed here (E0R.2 T2.2).
    spell_children = {"coa_client_spell.jsonl", "coa_client_spell_coa.jsonl",
                      "coa_client_spell_icons.jsonl"}
    for name, spec in contract["children"].items():
        if name not in children_meta or name in spell_children:
            continue
        shape = _shape_for(name, spec)
        if spec["kind"] == "json":
            _check_shape(shape, json.loads((gen_dir / name).read_text(encoding="utf-8")), name)
        else:
            for row in _read_jsonl(gen_dir / name):
                _check_shape(shape, row, name)
    counts = _cross_child(gen_dir, children_meta, policy,
                          shapes={name: _shape_for(name, contract["children"][name])
                                  for name in spell_children if name in contract["children"]})
    for name, spec in contract["children"].items():
        if spec["cardinality"]["rule"] in _CROSS_CHILD_RULES and name in children_meta:
            _resolve_cardinality(name, spec, children_meta[name]["records"], policy, manifest, counts)
    return {"gen_dir": gen_dir, "manifest": manifest, "children": resolved}


def resolve_active_generation(root: Path) -> dict:
    """Validate and resolve the active generation the pointer names. Fails closed (ResolveError) on any
    mismatch: pointer schema, gen-dir containment, manifest hash, or a child's path/sha256/bytes/records/
    schema/uniqueness. Returns {generation_id, gen_dir, manifest, children:{name: Path}}."""
    root = Path(root)
    pointer_path = root / POINTER_NAME
    if not pointer_path.is_file():
        raise ResolveError("no active generation pointer")
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ResolveError(f"pointer is not valid JSON: {exc}") from exc
    if pointer.get("schema_version") != POINTER_SCHEMA:
        raise ResolveError(f"pointer bad schema_version {pointer.get('schema_version')!r}")

    gen_id = pointer.get("generation_id")
    if not isinstance(gen_id, str) or not gen_id:
        raise ResolveError("pointer missing generation_id")
    gen_dir = (root / f"gen-{gen_id}").resolve()
    if os.path.commonpath([gen_dir, root.resolve()]) != str(root.resolve()):
        raise ResolveError("generation directory escapes the root")
    manifest_path = gen_dir / MANIFEST_NAME
    if manifest_path.resolve().parent != gen_dir:
        raise ResolveError("manifest path escapes the generation directory")
    if not manifest_path.is_file():
        raise ResolveError("generation manifest missing")

    manifest_body = manifest_path.read_bytes()
    if _sha256(manifest_body) != pointer.get("manifest_sha256"):
        raise ResolveError("manifest sha256 does not match the pointer")
    manifest = json.loads(manifest_body)
    if manifest.get("generation_id") != gen_id:
        raise ResolveError("manifest generation_id disagrees with the pointer")
    _assert_published_manifest(manifest)
    # Identical rules to the candidate path, so a PUBLISHED generation under an older supported revision
    # resolves by exactly the same three-way agreement it was validated under.
    contract = _staged_contract(gen_dir, manifest)

    children = manifest.get("children", {})
    resolved: dict[str, Path] = {}
    seen: set[str] = set()
    for name, meta in children.items():
        _safe_name_resolve(name)
        if name in seen:
            raise ResolveError(f"duplicate child {name!r}")
        seen.add(name)
        child_path = (gen_dir / name).resolve()
        if child_path.parent != gen_dir:
            raise ResolveError(f"child {name!r} escapes the generation directory")
        if not child_path.is_file():
            raise ResolveError(f"child {name!r} missing")
        sha, byte_length, actual_records = _scan_child(child_path, jsonl=name.endswith(".jsonl"))
        if sha != meta.get("sha256"):
            raise ResolveError(f"child {name!r} sha256 mismatch")
        if byte_length != meta.get("byte_length"):
            raise ResolveError(f"child {name!r} byte_length mismatch")
        if actual_records != meta.get("records"):
            raise ResolveError(f"child {name!r} record count mismatch ({actual_records} != {meta.get('records')})")
        if not meta.get("schema_version"):
            raise ResolveError(f"child {name!r} missing schema_version")
        resolved[name] = child_path
    for name in required_children_for(contract):
        if name not in resolved:
            raise ResolveError(f"required child {name!r} missing from the published generation")
    return {"generation_id": gen_id, "gen_dir": gen_dir, "manifest": manifest, "children": resolved}


def _assert_published_manifest(manifest: dict) -> None:
    """A pointer may resolve ONLY a fully-published E0R generation. Fails closed on: a non-v3 (pre-E0R)
    manifest; a publication_state other than 'published' (a candidate is never half-live); a
    candidate_trust_sha256 that does not cover the manifest; a `validation` that is not BOTH python and node
    true (both trust boundaries must have run); or a budget that is not within its ceilings. The trust digest
    excludes the mutable validation/budget, so those are re-checked here independently."""
    if manifest.get("schema_version") != "coa-client-extract-manifest-v3":
        raise ResolveError(f"unsupported manifest schema_version {manifest.get('schema_version')!r} (E0R requires v3)")
    if manifest.get("publication_state") != "published":
        raise ResolveError(f"generation not published (publication_state={manifest.get('publication_state')!r})")
    if manifest.get("candidate_trust_sha256") != candidate_trust_sha256(manifest):
        raise ResolveError("candidate_trust_sha256 does not cover the published manifest")
    validation = manifest.get("validation") or {}
    if validation.get("python") is not True or validation.get("node") is not True:
        raise ResolveError(f"generation not validated by both trust boundaries (validation={validation})")
    budget = manifest.get("budget") or {}
    if budget.get("within_budget") is not True:
        raise ResolveError(f"generation exceeded its budget (within_budget={budget.get('within_budget')!r})")


def _safe_name_resolve(name: str) -> None:
    if not name or name in _RESERVED or os.path.isabs(name) or ".." in Path(name).parts \
            or "/" in name or "\\" in name:
        raise ResolveError(f"unsafe child name {name!r}")


def prune_generations(root: Path, *, grace_seconds: float, quiescent: bool = False,
                      now_ns: int | None = None) -> dict:
    """Best-effort retention (a SEPARATE maintenance op — publish never prunes). Keep the pointer's
    current target and its immediate predecessor (via `predecessor_generation_id`, so a random-UUID +
    date-only manifest can still identify the chain). Older `gen-*` are removed only when `quiescent`
    is set (an enforced quiescent window / advisory lock) AND they are older than `grace_seconds`.
    Without quiescence, deletes NOTHING and returns the plan (documented best-effort)."""
    root = Path(root)
    now_ns = now_ns if now_ns is not None else time.time_ns()
    active = resolve_active_generation(root)          # fails closed if the pointer is invalid
    keep = {active["generation_id"]}
    predecessor = active["manifest"].get("predecessor_generation_id")
    if predecessor:
        keep.add(predecessor)

    candidates, removed = [], []
    for d in sorted(root.glob("gen-*")):
        if not d.is_dir():
            continue
        gid = d.name[len("gen-"):]
        if gid in keep:
            continue
        published_at = _read_published_at(d)
        age_s = (now_ns - published_at) / 1e9 if published_at is not None else float("inf")
        if age_s <= grace_seconds:
            continue
        candidates.append(d.name)
        if quiescent:
            shutil.rmtree(d)
            removed.append(d.name)
    return {"kept": sorted(keep), "removed": removed, "prunable": candidates, "quiescent": quiescent}


def _read_published_at(gen_dir: Path) -> int | None:
    try:
        return json.loads((gen_dir / MANIFEST_NAME).read_text(encoding="utf-8")).get("published_at")
    except (ValueError, OSError):
        return None
