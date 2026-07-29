from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class ContentSourceError(Exception):
    """A bound content read failed: a required file is absent, its bytes differ from the reviewed
    policy, or its parsed entry count does not match. E0R.2 T0.2 — the Content child has no WDBC
    source, so it cannot be bound through `topology`; this is its equivalent hold. The unbound reader
    silently skipped a missing file, which made a client shipping four of five files produce a smaller
    generation with no signal anywhere."""


@dataclass(frozen=True)
class ContentReadResult:
    """Records plus the derivation accounting the generation contract's `declared_content_derivation`
    rule checks: kept + rejected == source_entries, and kept == the emitted child's record count."""
    records: list[dict]
    derivation: dict


DEFAULT_FILES: dict[str, str] = {
    "SpellRankData.json": "spell_rank",
    "SpellToStatSuggestionData.json": "spell_stat_suggestion",
    "SpellToRoleSuggestionData.json": "spell_role_suggestion",
    "ItemVariationData.json": "item_variation",
    "CharacterAdvancementData.json": "character_advancement",
}
_INVESTIGATE = {"character_advancement"}


def _id_fields(entry: dict) -> dict:
    out: dict = {}
    if "Spell" in entry:
        out["spell_id"] = entry["Spell"]
    if "Item" in entry:
        out["item_id"] = entry["Item"]
    return out


def _parse_entries(raw: bytes) -> list:
    payload = json.loads(raw.decode("utf-8"))
    return payload if isinstance(payload, list) else payload.get("data", [])


def _records_for_file(filename: str, kind: str, raw: bytes, today: str) -> list[dict]:
    """One record per source entry. Shared by the unbound and bound readers so their outputs can never
    diverge — the bound reader adds enforcement, never a different record shape."""
    digest = hashlib.sha256(raw).hexdigest()
    records: list[dict] = []
    for entry in _parse_entries(raw):
        ids = _id_fields(entry)
        values = {k: v for k, v in entry.items() if k not in ("Spell", "Item")}
        record = {
            "schema_version": "coa-client-content-v1",
            "content_kind": kind,
            **ids,
            "values": values,
            "provenance": {
                "source_file": filename,
                "file_sha256": digest,
                "extraction_date": today,
            },
            "coa_attribution": {"status": "unknown"},
        }
        if kind in _INVESTIGATE:
            record["coa_attribution"]["note"] = "investigate: may be classless/Area-52 system"
        records.append(record)
    return records


def read_content_records(content_dir: Path, *, files: dict[str, str] | None = None) -> list[dict]:
    """UNBOUND read: tolerates a missing file. Retained for the fixture-driven unit tests that predate
    the policy binding; the extractor uses read_bound_content (E0R.2 T0.2)."""
    files = files if files is not None else DEFAULT_FILES
    today = date.today().isoformat()
    records: list[dict] = []
    for filename, kind in files.items():
        path = content_dir / filename
        if not path.is_file():
            continue
        records.extend(_records_for_file(filename, kind, path.read_bytes(), today))
    return records


def read_bound_content(content_dir: Path, *, policy) -> ContentReadResult:
    """BOUND read against the reviewed `content_sources` policy block (E0R.2 T0.2).

    The Content child is the one generation child with no WDBC source, so `topology`/`bound.tables`
    cannot express its domain. This is the equivalent hold: every required file must be PRESENT, its
    bytes must hash to the reviewed digest, and its parsed entry count must match the reviewed
    `source_entries`. Files outside the required set are ignored — an extra file the client ships must
    not silently enter the generation.

    Returns the records plus a derivation that CLOSES (kept + rejected == source_entries), which is
    what the contract's `declared_content_derivation` cardinality rule verifies against the emitted
    child's record count.
    """
    sources = policy.content_sources
    required = sources["required_files"]
    today = date.today().isoformat()
    records: list[dict] = []
    source_entries = 0
    for filename in sorted(required):
        spec = required[filename]
        path = Path(content_dir) / filename
        if not path.is_file():
            raise ContentSourceError(
                f"required content file {filename!r} is absent from {content_dir}; a bound read never "
                "silently skips a source (that is how a four-of-five client shrank the generation)")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != spec["sha256"]:
            raise ContentSourceError(
                f"content file {filename!r} sha256 {digest[:16]} != reviewed {spec['sha256'][:16]}")
        entries = _parse_entries(raw)
        if len(entries) != spec["source_entries"]:
            raise ContentSourceError(
                f"content file {filename!r} source_entries {len(entries)} != reviewed "
                f"{spec['source_entries']}")
        source_entries += len(entries)
        records.extend(_records_for_file(filename, spec["kind"], raw, today))
    derivation = {"source": "content_json", "source_entries": source_entries,
                  "kept": len(records), "rejected": source_entries - len(records)}
    return ContentReadResult(records=records, derivation=derivation)
