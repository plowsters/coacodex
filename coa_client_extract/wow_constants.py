from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

AUTHORED_INPUTS = ("wow_rules", "rating_enum", "power_type_enum",
                   "gt_axis_policy", "wotlk_reference_anchors")
_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class AuthoredInput:
    name: str
    payload: dict
    version: str
    sha256: str


def load_authored_input(name: str, *, root: Path | None = None) -> AuthoredInput:
    path = (root or _DATA_DIR) / f"{name}_v1.json"
    raw = path.read_bytes()
    payload = json.loads(raw)
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{path.name}: missing string 'version'")
    return AuthoredInput(name=name, payload=payload, version=version,
                         sha256=hashlib.sha256(raw).hexdigest())


from .dbc_layouts import GameTableLayout
from .wdbc import GameTable


def load_axis_policy(payload: dict) -> tuple[dict[str, GameTableLayout], int, int]:
    level_stride = int(payload["level_stride"])
    rating_stride = int(payload["rating_stride"])
    defaults = payload.get("defaults", {})
    layouts: dict[str, GameTableLayout] = {}
    for group in ("tables", "recon_gated"):
        for key, spec in payload.get(group, {}).items():
            layouts[key] = GameTableLayout(
                key=key, source_dbc=spec["source_dbc"],
                physical_form=spec.get("physical_form", defaults["physical_form"]),
                key_source=spec.get("key_source", defaults["key_source"]),
                expected_field_count=int(spec.get("expected_field_count", defaults["expected_field_count"])),
                expected_record_size=int(spec.get("expected_record_size", defaults["expected_record_size"])),
                value_cell=int(spec.get("value_cell", defaults["value_cell"])),
                id_cell=spec.get("id_cell", defaults["id_cell"]),
                index_kind=spec["index_kind"], axes=tuple(spec["axes"]),
                class_indexed=bool(spec["class_indexed"]), supported=spec.get("supported", {}),
                index_offset=int(spec.get("index_offset", 0)),
                semantics=spec.get("semantics", "proven"))
    return layouts, level_stride, rating_stride


def _build_index(layout: GameTableLayout, table: GameTable) -> dict[int, float]:
    if layout.key_source == "explicit_id":
        index: dict[int, float] = {}
        for r in table.rows:
            if r["id"] in index:
                raise ValueError(f"{layout.key}: duplicate explicit id {r['id']}")
            index[r["id"]] = r["value"]
        return index
    return {r["ordinal"]: r["value"] for r in table.rows}


def map_table_entries(layout: GameTableLayout, table: GameTable, *, class_roster: list[int],
                      level_stride: int, rating_stride: int) -> tuple[list[dict], dict]:
    """Invert the reference index into explicit-coordinate entries. Uses the explicit id as the
    index when the physical form carries one (validating uniqueness), else the row ordinal.
    Never derives class width from a count."""
    by_index = _build_index(layout, table)
    entries: list[dict] = []

    def emit(index: int, coords: dict) -> None:
        if index in by_index:
            entries.append({**coords, "value": by_index[index]})

    if layout.index_kind == "rating_by_level":
        for rating_id in range(layout.supported["rating_id"]["min"], layout.supported["rating_id"]["max"] + 1):
            for level in range(layout.supported["level"]["min"], layout.supported["level"]["max"] + 1):
                emit(rating_id * level_stride + (level - 1), {"rating_id": rating_id, "level": level})
    elif layout.index_kind == "class_rating_scalar":
        for wow_class_id in class_roster:
            for rating_id in range(layout.supported["rating_id"]["min"], layout.supported["rating_id"]["max"] + 1):
                emit((wow_class_id - 1) * rating_stride + rating_id + layout.index_offset,
                     {"wow_class_id": wow_class_id, "rating_id": rating_id})
    elif layout.index_kind == "class_by_level":
        for wow_class_id in class_roster:
            for level in range(layout.supported["level"]["min"], layout.supported["level"]["max"] + 1):
                emit((wow_class_id - 1) * level_stride + (level - 1), {"wow_class_id": wow_class_id, "level": level})
    elif layout.index_kind == "class_only":
        for wow_class_id in class_roster:
            emit(wow_class_id - 1, {"wow_class_id": wow_class_id})
    else:
        raise ValueError(f"unknown index_kind {layout.index_kind!r}")

    counts = {"source_records": table.record_count, "emitted_entries": len(entries),
              "padding_records": table.record_count - len(entries)}
    return entries, counts


def build_class_axis(chr_rows: list[dict], *, reference_expected_ids: list[int],
                     reference_holes: list[int], power_type_enum: dict) -> dict:
    ids = [int(r["id"]) for r in chr_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ChrClasses ids")
    power_map = power_type_enum.get("map", {})
    default_power: dict[str, str] = {}
    for r in chr_rows:
        pt = str(int(r["power_type"]))
        if pt not in power_map:
            raise ValueError(f"class {r['id']}: unmapped power_type {pt}")
        default_power[str(int(r["id"]))] = power_map[pt]

    observed = sorted(ids)
    ref = sorted(reference_expected_ids)
    ref_set, obs_set = set(ref), set(observed)
    if obs_set == ref_set:
        comparison = "exact"
    elif obs_set > ref_set:
        comparison = "extended"
    elif obs_set < ref_set:
        comparison = "changed"
    else:
        comparison = "ambiguous"
    return {"namespace": "chr_classes", "reference_expected_ids": ref,
            "reference_holes": sorted(reference_holes), "observed_client_ids": observed,
            "comparison": comparison, "default_power_type_by_wow_class_id": default_power}


def class_roster(class_axis: dict) -> list[int]:
    return list(class_axis["observed_client_ids"])


import math
from collections import defaultdict

from .archive_backend import ArchiveBackend
from .dbc_layouts import CHR_CLASSES
from .errors import ArchiveError
from .wdbc import classify_physical_form, parse_dbc, parse_gametable


def _monotonic_violations(entries: list[dict], group_axis: str, order_axis: str) -> int:
    series = defaultdict(list)
    for e in entries:
        if group_axis in e and order_axis in e:
            series[e[group_axis]].append((e[order_axis], e["value"]))
    violations = 0
    for pts in series.values():
        pts.sort()
        violations += sum(1 for (_, a), (_, b) in zip(pts, pts[1:]) if b < a)  # nondecreasing
    return violations


def recon(backend: ArchiveBackend, root, attach, *, axis_policy, rating_enum, power_type_enum,
          reference_class_axis, chr_layout=CHR_CLASSES) -> dict:
    layouts, level_stride, rating_stride = axis_policy

    chr_member = backend.read_effective_file(root, attach, "DBFilesClient\\ChrClasses.dbc")
    chr_tbl = parse_dbc(chr_member.data, chr_layout)
    class_axis = build_class_axis(chr_tbl.rows,
                                  reference_expected_ids=reference_class_axis["reference_expected_ids"],
                                  reference_holes=reference_class_axis["reference_holes"],
                                  power_type_enum=power_type_enum)
    roster = class_roster(class_axis)

    rating_supported = set(rating_enum.get("supported", {}))
    observed_ratings: set[int] = set()
    tables: dict[str, dict] = {}
    for key, layout in layouts.items():
        try:
            member = backend.read_effective_file(root, attach, f"DBFilesClient\\{layout.source_dbc}.dbc")
        except ArchiveError:
            tables[key] = {"available": False, "source_dbc": layout.source_dbc}
            continue
        table = parse_gametable(member.data, physical_form=layout.physical_form,
                                expected_field_count=layout.expected_field_count,
                                expected_record_size=layout.expected_record_size,
                                value_cell=layout.value_cell, id_cell=layout.id_cell)
        physical = classify_physical_form(table.field_count, table.record_size)
        finite_ok = all(math.isfinite(r["value"]) for r in table.rows)
        try:
            entries, counts = map_table_entries(layout, table, class_roster=roster,
                                                level_stride=level_stride, rating_stride=rating_stride)
            dup = False
        except ValueError:
            entries, counts, dup = [], {"emitted_entries": 0}, True
        observed_ratings |= {e["rating_id"] for e in entries if "rating_id" in e}
        max_class = max(roster) if (layout.class_indexed and roster) else 0
        out_of_storage = (layout.class_indexed and layout.index_kind == "class_by_level"
                          and (max_class - 1) * level_stride >= table.record_count)
        group, order = (("rating_id", "level") if key == "combat_ratings" else ("wow_class_id", "level"))
        tables[key] = {"available": True, "source_dbc": layout.source_dbc, "physical_form": physical,
                       "declared_physical_form": layout.physical_form, "source_records": table.record_count,
                       "drift": table.drift, "finite_ok": finite_ok, "duplicate_ids": dup,
                       "coverage": counts, "padding_records": counts.get("padding_records", 0),
                       "monotonic_violations": _monotonic_violations(entries, group, order),
                       "extended_class_out_of_storage": bool(out_of_storage),
                       "class_indexed": layout.class_indexed, "semantics": layout.semantics}

    return {"tables": tables, "class_axis": class_axis,
            "enum_coverage": {"unmapped_rating_ids": sorted(r for r in observed_ratings
                                                            if str(r) not in rating_supported),
                              "unmapped_power_types": []},
            "class_context_resolution": "unproven"}


def run_recon(client_root, out_dir, *, backend, plan) -> dict:
    root, attach = plan.open_chain
    axis = load_authored_input("gt_axis_policy")
    layouts, ls, rs = load_axis_policy(axis.payload)
    report = recon(backend, root, attach, axis_policy=(layouts, ls, rs),
                   rating_enum=load_authored_input("rating_enum").payload,
                   power_type_enum=load_authored_input("power_type_enum").payload,
                   reference_class_axis=axis.payload["class_axis"])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coa_wow_constants_recon.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


WOW_CONSTANTS_SCHEMA = "coa-wow-constants-v1"


def reference_comparison(entries: list[dict], anchors: list[dict], *, axes: tuple[str, ...],
                         anchor_set_version: str, anchor_set_sha256: str) -> dict:
    index = {tuple(e[a] for a in axes): e["value"] for e in entries}
    checked = equal = different = 0
    for anchor in anchors:
        try:
            key = tuple(anchor[a] for a in axes)
        except KeyError:
            continue
        if key not in index:
            continue
        checked += 1
        if abs(index[key] - anchor["expected"]) <= anchor.get("tolerance", 0.0):
            equal += 1
        else:
            different += 1
    status = ("matches_on_checked_anchors" if checked and different == 0
              else "differs_on_checked_anchors" if checked else "no_anchors_checked")
    return {"scope": "anchors", "anchor_set_version": anchor_set_version,
            "anchor_set_sha256": anchor_set_sha256, "checked": checked, "equal": equal,
            "different": different, "status": status}


def build_snapshot(*, client_build: str, provenance: dict, class_axis: dict, game_tables: dict,
                   rules: dict, rating_enum: dict, power_type_enum: dict) -> dict:
    for key, table in game_tables.items():
        for entry in table.get("entries", []):
            if not math.isfinite(entry["value"]):
                raise ValueError(f"{key}: non-finite value in entries")
    return {"schema_version": WOW_CONSTANTS_SCHEMA, "client_build": client_build,
            "provenance": provenance, "class_axis": class_axis,
            "enum_maps": {"rating_enum": rating_enum, "power_type": power_type_enum},
            "game_tables": game_tables, "rules": rules}


class MissingRequiredTable(RuntimeError):
    pass


class ClassAxisAdjudicationRequired(RuntimeError):
    pass


def run_extract(client_root, out_dir, *, backend, plan, extractor_commit, client_build,
                adjudication_path: str | None = None) -> dict:
    root, attach = plan.open_chain
    axis_in = load_authored_input("gt_axis_policy")
    rating_in = load_authored_input("rating_enum")
    power_in = load_authored_input("power_type_enum")
    rules_in = load_authored_input("wow_rules")
    anchors_in = load_authored_input("wotlk_reference_anchors")
    layouts, ls, rs = load_axis_policy(axis_in.payload)

    report = recon(backend, root, attach, axis_policy=(layouts, ls, rs),
                   rating_enum=rating_in.payload, power_type_enum=power_in.payload,
                   reference_class_axis=axis_in.payload["class_axis"])
    class_axis = report["class_axis"]

    adjudication = None
    if class_axis["comparison"] != "exact":
        if not adjudication_path or not Path(adjudication_path).is_file():
            raise ClassAxisAdjudicationRequired(
                f"class axis comparison={class_axis['comparison']} requires a tracked adjudication file")
        raw = Path(adjudication_path).read_bytes()
        payload = json.loads(raw)
        from types import SimpleNamespace
        adjudication = SimpleNamespace(name="class_axis_adjudication",
                                       version=payload.get("version", "wow-class-axis-adjudication-v1"),
                                       sha256=hashlib.sha256(raw).hexdigest())

    roster = class_roster(class_axis)
    anchors = anchors_in.payload["anchors"]
    game_tables: dict = {}
    source_dbc_sha: dict = {}
    table_summary: dict = {}
    for key, layout in layouts.items():
        info = report["tables"][key]
        proven_required = layout.semantics == "proven" and key in axis_in.payload["tables"]
        if not info["available"]:
            if proven_required:
                raise MissingRequiredTable(f"proven-required table {layout.source_dbc} is absent")
            continue
        if layout.semantics == "unproven":
            continue
        member = backend.read_effective_file(root, attach, f"DBFilesClient\\{layout.source_dbc}.dbc")
        table = parse_gametable(member.data, physical_form=layout.physical_form,
                                expected_field_count=layout.expected_field_count,
                                expected_record_size=layout.expected_record_size,
                                value_cell=layout.value_cell, id_cell=layout.id_cell, strict=True)
        entries, counts = map_table_entries(layout, table, class_roster=roster,
                                            level_stride=ls, rating_stride=rs)
        rc = reference_comparison(entries, [a for a in anchors if a.get("table") == key],
                                  axes=layout.axes, anchor_set_version=anchors_in.version,
                                  anchor_set_sha256=anchors_in.sha256)
        game_tables[key] = {"source_dbc": layout.source_dbc, "physical_form": layout.physical_form,
                            "axes": list(layout.axes), "class_indexed": layout.class_indexed,
                            "domains": layout.supported, "drift": table.drift, "counts": counts,
                            "reference_comparison": rc, "entries": entries}
        source_dbc_sha[layout.source_dbc] = hashlib.sha256(member.data).hexdigest()
        table_summary[key] = {**counts, "drift": table.drift,
                              "reference_comparison_status": rc["status"]}

    chr_member = backend.read_effective_file(root, attach, "DBFilesClient\\ChrClasses.dbc")
    source_dbc_sha["ChrClasses"] = hashlib.sha256(chr_member.data).hexdigest()
    provenance = {"backend": getattr(backend, "name", "unknown"),
                  "backend_version": getattr(backend, "version", "unknown"),
                  "source_dbcs": {k: {"sha256": v} for k, v in source_dbc_sha.items()}}
    snapshot = build_snapshot(client_build=client_build, provenance=provenance, class_axis=class_axis,
                              game_tables=game_tables, rules=rules_in.payload["rules"],
                              rating_enum=rating_in.payload, power_type_enum=power_in.payload)

    from .artifacts import write_wow_constants
    return write_wow_constants(
        snapshot, Path(out_dir),
        authored_inputs=[rules_in, rating_in, power_in, axis_in, anchors_in],
        source_dbc_sha256=source_dbc_sha, class_context_resolution=report["class_context_resolution"],
        extractor_commit=extractor_commit, client_build=client_build, table_summary=table_summary,
        class_axis_adjudication=adjudication)
