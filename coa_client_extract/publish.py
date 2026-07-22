from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from .contracts import CANDIDATE_MUTABLE_KEYS, ICON_ASSET_STATUSES
from .manifest import build_manifest_v3
from .spell_layout import load_spell_policy
from .spell_record import _expand_compact as _expand_cell

POINTER_SCHEMA = "coa-client-extract-pointer-v1"
POINTER_NAME = "coa_client_extract.pointer.json"
MANIFEST_NAME = "manifest.json"
LOCK_NAME = ".publish.lock"
_RESERVED = {MANIFEST_NAME, POINTER_NAME, LOCK_NAME}

# Every child a complete E0R generation MUST carry (design A5). The manifest is NOT a child.
REQUIRED_CHILDREN = (
    "coa_client_spell.jsonl", "coa_client_spell_coa.jsonl",
    "coa_client_spell_projection.manifest.json", "coa_client_spell_icons.jsonl",
    "coa_client_content.jsonl", "coa_client_archive_plan.json",
    "coa_client_advancement.jsonl", "coa_client_class_types.jsonl",
    "coa_client_tab_types.jsonl", "coa_client_essence.jsonl", "spell_layout_v2.json",
)


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


def _cross_child(gen_dir: Path, children: dict) -> None:
    """Streaming merge-join over ascending spell_id across the three spell children (design A5) — cursors
    only, no set/list materialization. Enforces projection⊆is_coa, projection-within-domain, the disjoint
    v3 dialects (full=compact `raw`, projection=rich `field_observations`), identity/mechanics/attribution
    agreement, the compact_raw_expands_to_envelope EQUALITY (expand(full.raw) == projection.field_observations),
    the icon catalog as EXACTLY the full domain (lockstep 1:1 — a missing, orphan, or trailing icon row
    fails), per-row icon id/path agreement, converted->bundle-required, and sorted-unique ids."""
    policy = load_spell_policy(json.loads((gen_dir / "spell_layout_v2.json").read_text(encoding="utf-8")))
    full = _Cursor(_read_jsonl(gen_dir / "coa_client_spell.jsonl"), "full")
    proj = _Cursor(_read_jsonl(gen_dir / "coa_client_spell_coa.jsonl"), "projection")
    icons = _Cursor(_read_jsonl(gen_dir / "coa_client_spell_icons.jsonl"), "icons")
    any_converted = False
    while full.row is not None:
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


def validate_candidate_generation(gen_dir: Path) -> dict:
    """Validate a staged CANDIDATE generation by path (not via the pointer): the manifest is a candidate,
    every REQUIRED_CHILDREN is present and per-child valid, the streaming cross-child merge-join holds,
    and the icon bundle is present iff any converted row exists. Raises ResolveError on any failure."""
    gen_dir = Path(gen_dir)
    manifest_path = gen_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ResolveError("candidate manifest missing")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("publication_state") != "candidate":
        raise ResolveError(f"not a candidate generation (publication_state={manifest.get('publication_state')!r})")
    if manifest.get("candidate_trust_sha256") != candidate_trust_sha256(manifest):
        raise ResolveError("candidate_trust_sha256 does not cover the manifest")
    resolved = _validate_children_by_path(gen_dir, manifest)
    for name in REQUIRED_CHILDREN:
        if name not in resolved:
            raise ResolveError(f"required child {name!r} missing from the candidate generation")
    _cross_child(gen_dir, manifest.get("children", {}))
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
    for name in REQUIRED_CHILDREN:
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
