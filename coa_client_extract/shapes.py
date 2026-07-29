# coa_client_extract/shapes.py
"""E0R.2 T2.2: a SHAPE is a type contract, not a key list.

Checking `schema_version` plus top-level key presence establishes neither field types, nullability,
nested envelope shape, nor JSON-document semantics — `{}` passed as a one-record JSON artifact because
nothing asked anything of it. Each contract `shape` name maps to a validator here that asserts the exact
key set (no unknown keys), the type of every key, explicit nullability, and the nested observation
envelope shape.

The Node implementation in `coa_scraper/scripts/lib/shapes.mjs` is written INDEPENDENTLY against the
same contract. That is the point: a shared serialization would reproduce a shared bug. What holds the
two together is the shared golden corpus, which every shape validator runs against in both languages.
"""
from __future__ import annotations

from .contracts import DECODED_REASONS, OBSERVATION_STATES, load_observation_wire_schema

_PROOF_FACETS = ("integrity", "layout", "interpretation")
_PROMOTIONS = ("normalized", "raw_only")
_JOIN_PARTS = ("index", "side_id", "side_value")


class ShapeError(ValueError):
    """A child row or document does not match its contracted shape."""


def _fail(where: str, msg: str):
    raise ShapeError(f"{where}: {msg}")


def _obj(value, where: str) -> dict:
    if not isinstance(value, dict):
        _fail(where, f"must be an object, got {type(value).__name__}")
    return value


def _keys(value: dict, *, required: tuple[str, ...], optional: tuple[str, ...] = (), where: str) -> None:
    """Exact key discipline: every required key present, no key outside required|optional. An unknown
    key is rejected rather than ignored — an ignored key is how a field enters a published artifact
    without ever being reviewed."""
    present = set(value)
    missing = sorted(set(required) - present)
    if missing:
        _fail(where, f"missing {missing}")
    unknown = sorted(present - set(required) - set(optional))
    if unknown:
        _fail(where, f"unknown key(s) {unknown}")


def _str(value, where: str, *, allow_null: bool = False) -> None:
    if value is None and allow_null:
        return
    if not isinstance(value, str):
        _fail(where, f"must be a string{' or null' if allow_null else ''}, got {type(value).__name__}")


def _int(value, where: str, *, allow_null: bool = False) -> None:
    if value is None and allow_null:
        return
    # `isinstance(True, int)` is True in Python; a boolean is never a valid id, offset or count.
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(where, f"must be an integer{' or null' if allow_null else ''}, got {type(value).__name__}")


def _number(value, where: str, *, allow_null: bool = False) -> None:
    if value is None and allow_null:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(where, f"must be a number{' or null' if allow_null else ''}, got {type(value).__name__}")


def _proof(value, where: str) -> None:
    _obj(value, where)
    _keys(value, required=_PROOF_FACETS, where=where)
    for facet in _PROOF_FACETS:
        _str(value[facet], f"{where}.{facet}")


def _decoded(value, where: str) -> None:
    """A component/scalar `decoded` is {kind, value}; a JOIN's `decoded` is the bare resolved scalar,
    because the join's value has no kind of its own beyond its side-value component's.

    `null` is legitimate: the per-value domain gate emits `decoded: null` alongside
    `decoded_reason: "value_out_of_domain"`, which is the fail-closed behaviour E0R exists to produce."""
    if value is None:
        return
    _obj(value, where)
    _keys(value, required=("kind", "value"), where=where)
    _str(value["kind"], f"{where}.kind")


def _vocabulary(cell: dict, where: str) -> None:
    if cell.get("state") not in OBSERVATION_STATES:
        _fail(where, f"state {cell.get('state')!r} not in the closed vocabulary {OBSERVATION_STATES}")
    if cell.get("decoded_reason") not in DECODED_REASONS:
        _fail(where, f"decoded_reason {cell.get('decoded_reason')!r} not in {DECODED_REASONS}")


def _component(value, where: str) -> None:
    """A join component is always the RICH form: it carries its own proof and promotion, which is what
    makes a composed join proof re-derivable rather than asserted."""
    _obj(value, where)
    _vocabulary(value, where)
    _keys(value, required=("state", "decoded_reason", "policy_ref"),
          optional=("raw_u32", "raw_offset", "resolved", "proof", "promotion", "decoded"), where=where)
    _str(value["policy_ref"], f"{where}.policy_ref")
    if "raw_u32" in value:
        _int(value["raw_u32"], f"{where}.raw_u32")
    if "proof" in value:
        _proof(value["proof"], f"{where}.proof")
    if "promotion" in value and value["promotion"] not in _PROMOTIONS:
        _fail(f"{where}.promotion", f"{value['promotion']!r} not in {_PROMOTIONS}")
    if "decoded" in value:
        _decoded(value["decoded"], f"{where}.decoded")


def _observation(cell, where: str, *, rich: bool) -> None:
    """One observation cell, in either dialect.

    The full child is COMPACT (substrate only); the projection is RICH (substrate plus the proof and
    promotion a consumer re-derives against). The three variants — scalar, string, join — are told apart
    by their substrate keys, and each variant's key set is exact, so a cell that is half one and half
    another is a malformed cell rather than a permissively-accepted one.
    """
    _obj(cell, where)
    _vocabulary(cell, where)
    if "join_name" in cell or "components" in cell:
        # An UNRESOLVED join carries no components at all — it records the index cell it could not
        # follow (`policy_ref`) and nothing else. That is a complete observation, not a partial one:
        # omitting the cell entirely would be the loss.
        required = ("state", "decoded_reason", "join_name")
        # An UNRESOLVED rich join carries a plain `proof` (there is nothing to compose); a RESOLVED one
        # carries `composed_proof`. Both are legitimate, so both are optional and each is type-checked.
        optional = ("components", "policy_ref") + (
            ("composed_proof", "proof", "promotion", "decoded") if rich else ())
        _keys(cell, required=required, optional=optional, where=where)
        _str(cell["join_name"], f"{where}.join_name")
        if "policy_ref" in cell:
            _str(cell["policy_ref"], f"{where}.policy_ref")
        if "components" in cell:
            components = _obj(cell["components"], f"{where}.components")
            unknown = sorted(set(components) - set(_JOIN_PARTS))
            if unknown:
                _fail(f"{where}.components", f"unknown join part(s) {unknown}")
            for part, component in components.items():
                _component(component, f"{where}.components.{part}")
        if rich:
            for facet in ("composed_proof", "proof"):
                if facet in cell:
                    _proof(cell[facet], f"{where}.{facet}")
            if "promotion" in cell and cell["promotion"] not in _PROMOTIONS:
                _fail(f"{where}.promotion", f"{cell['promotion']!r} not in {_PROMOTIONS}")
    elif "raw_offset" in cell or "resolved" in cell:
        required = ("state", "decoded_reason", "policy_ref", "raw_offset", "resolved")
        optional = ("proof", "promotion", "decoded") if rich else ()
        _keys(cell, required=required, optional=optional, where=where)
        _str(cell["policy_ref"], f"{where}.policy_ref")
        _int(cell["raw_offset"], f"{where}.raw_offset", allow_null=True)
        _str(cell["resolved"], f"{where}.resolved", allow_null=True)
        _rich_facets(cell, where, rich=rich)
    else:
        required = ("state", "decoded_reason", "policy_ref", "raw_u32")
        optional = ("proof", "promotion", "decoded") if rich else ()
        _keys(cell, required=required, optional=optional, where=where)
        _str(cell["policy_ref"], f"{where}.policy_ref")
        _int(cell["raw_u32"], f"{where}.raw_u32", allow_null=True)
        _rich_facets(cell, where, rich=rich)


def _rich_facets(cell: dict, where: str, *, rich: bool) -> None:
    if not rich:
        return
    if "proof" in cell:
        _proof(cell["proof"], f"{where}.proof")
    if "promotion" in cell and cell["promotion"] not in _PROMOTIONS:
        _fail(f"{where}.promotion", f"{cell['promotion']!r} not in {_PROMOTIONS}")
    if "decoded" in cell:
        _decoded(cell["decoded"], f"{where}.decoded")


def _attribution(value, where: str) -> None:
    _obj(value, where)
    _keys(value, required=("is_coa",),
          optional=("status", "archive_family", "id_range", "policy_sha256", "confidence",
                    "exclusive_mode", "modes"), where=where)
    if not isinstance(value["is_coa"], bool):
        _fail(f"{where}.is_coa", "must be a boolean — an unknown attribution is False, never absent")


def _mechanics(value, where: str) -> None:
    """Every mechanics value is structurally NULLABLE, including school_mask: a proven policy still
    yields a null normalized value when an unseen school bit trips the per-value domain gate
    (`value_out_of_domain`). Nullability is structural; whether a null is legitimate is a semantic
    question the per-row verifier answers. The KEYS, however, may not be absent — an absent key is
    silent loss, a null is a recorded observation."""
    _obj(value, where)
    for key, mech in value.items():
        _number(mech, f"{where}.{key}", allow_null=True)


def _spell_row(row, *, rich: bool, schema_version: str, where: str) -> dict:
    _obj(row, where)
    substrate = "field_observations" if rich else "raw"
    _keys(row, required=("schema_version", "spell_id", "name", "mechanics", "coa_attribution",
                         substrate),
          optional=("description",), where=where)
    if row["schema_version"] != schema_version:
        _fail(f"{where}.schema_version", f"{row['schema_version']!r} != {schema_version!r}")
    _int(row["spell_id"], f"{where}.spell_id")
    _str(row["name"], f"{where}.name", allow_null=True)
    _mechanics(row["mechanics"], f"{where}.mechanics")
    _attribution(row["coa_attribution"], f"{where}.coa_attribution")
    cells = _obj(row[substrate], f"{where}.{substrate}")
    if not cells:
        _fail(f"{where}.{substrate}", "carries no observations: a row with no substrate is not lossless")
    for field, cell in cells.items():
        _observation(cell, f"{where}.{substrate}.{field}", rich=rich)
    return row


# --- the twelve shapes ---

def full_spell_row_v3(row):
    return _spell_row(row, rich=False, schema_version="coa-client-spell-v3", where="full_spell_row_v3")


# --- E0R.2 T6.2: the v4 (hoisted + interned) compact dialect -------------------------------------
# RETAINED beside v3, not replacing it: `e0r-v1` stays a supported contract revision, so a generation
# published under it must still validate. What v4 removes is the DUAL-ENCODING tolerance within one
# schema — a v4 cell that repeats a hoisted key could contradict the descriptor, and there is no
# principled winner between them.
_V4_SUBSTRATE = ("raw_u32", "raw_offset", "resolved")


def _coded_vocabulary(cell: dict, where: str) -> None:
    states = load_observation_wire_schema()["states"]
    reasons = load_observation_wire_schema()["decoded_reasons"]
    for key, table, what in (("s", states, "state"), ("d", reasons, "decoded_reason")):
        code = cell.get(key)
        if isinstance(code, bool) or not isinstance(code, int) or code not in set(table.values()):
            _fail(f"{where}.{key}", f"{what} code {code!r} is outside the closed vocabulary "
                                    f"{sorted(set(table.values()))}")


def _observation_v4(cell, where: str, *, part: bool = False) -> None:
    """One v4 compact cell: two vocabulary codes plus a substrate. The join name and every policy
    pointer live in the staged descriptors, so a cell that carries one is malformed rather than
    generous."""
    _obj(cell, where)
    _coded_vocabulary(cell, where)
    for key in ("policy_ref", "join_name", "state", "decoded_reason"):
        if key in cell:
            _fail(f"{where}.{key}", "is hoisted into the field descriptors in v4 and must not be repeated")
    optional = _V4_SUBSTRATE if part else _V4_SUBSTRATE + ("components",)
    _keys(cell, required=("s", "d"), optional=optional, where=where)
    if "raw_u32" in cell:
        _int(cell["raw_u32"], f"{where}.raw_u32", allow_null=True)
    if "raw_offset" in cell:
        _int(cell["raw_offset"], f"{where}.raw_offset", allow_null=True)
        _str(cell["resolved"], f"{where}.resolved", allow_null=True)
    if "components" in cell:
        components = _obj(cell["components"], f"{where}.components")
        unknown = sorted(set(components) - set(_JOIN_PARTS))
        if unknown:
            _fail(f"{where}.components", f"unknown join part(s) {unknown}")
        for name, component in components.items():
            _observation_v4(component, f"{where}.components.{name}", part=True)


def full_spell_row_v4(row):
    where = "full_spell_row_v4"
    _obj(row, where)
    _keys(row, required=("schema_version", "spell_id", "name", "mechanics", "coa_attribution", "raw"),
          optional=("description",), where=where)
    if row["schema_version"] != "coa-client-spell-v4":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r} != 'coa-client-spell-v4'")
    _int(row["spell_id"], f"{where}.spell_id")
    _str(row["name"], f"{where}.name", allow_null=True)
    _mechanics(row["mechanics"], f"{where}.mechanics")
    _attribution(row["coa_attribution"], f"{where}.coa_attribution")
    cells = _obj(row["raw"], f"{where}.raw")
    if not cells:
        _fail(f"{where}.raw", "carries no observations: a row with no substrate is not lossless")
    for field, cell in cells.items():
        _observation_v4(cell, f"{where}.raw.{field}")
    return row


def spell_field_descriptors_v1(doc):
    """Structure only. WHETHER the descriptors describe this policy is a semantic question, answered by
    `spell_record.require_field_descriptors` re-deriving them — a shape has no policy to check against."""
    where = "spell_field_descriptors_v1"
    _obj(doc, where)
    _keys(doc, required=("schema_version", "policy_sha256", "fields"), where=where)
    if doc["schema_version"] != "coa-client-spell-fields-v1":
        _fail(f"{where}.schema_version", f"{doc['schema_version']!r}")
    _str(doc["policy_sha256"], f"{where}.policy_sha256")
    fields = _obj(doc["fields"], f"{where}.fields")
    if not fields:
        _fail(f"{where}.fields", "describes no field: a v4 row would be undecodable")
    for name, entry in fields.items():
        at = f"{where}.fields.{name}"
        _obj(entry, at)
        if entry.get("kind") == "scalar":
            _keys(entry, required=("kind", "policy_ref"), where=at)
            _str(entry["policy_ref"], f"{at}.policy_ref")
        elif entry.get("kind") == "join":
            _keys(entry, required=("kind", "join_name", "index_policy_ref", "components"), where=at)
            _str(entry["join_name"], f"{at}.join_name")
            _str(entry["index_policy_ref"], f"{at}.index_policy_ref")
            components = _obj(entry["components"], f"{at}.components")
            if set(components) != set(_JOIN_PARTS):
                _fail(f"{at}.components", f"must describe exactly {sorted(_JOIN_PARTS)}; a resolved join "
                                          "cannot be reconstructed from fewer")
            for part, component in components.items():
                _obj(component, f"{at}.components.{part}")
                _keys(component, required=("policy_ref",), where=f"{at}.components.{part}")
                _str(component["policy_ref"], f"{at}.components.{part}.policy_ref")
        else:
            _fail(f"{at}.kind", f"{entry.get('kind')!r} not in ('scalar', 'join')")
    return doc


def observation_wire_v1(doc):
    """Structure only; `contracts.require_observation_wire` decides whether it equals the trusted copy."""
    where = "observation_wire_v1"
    _obj(doc, where)
    _keys(doc, required=("schema_version", "states", "decoded_reasons"), optional=("note",), where=where)
    if doc["schema_version"] != "coa-observation-wire-v1":
        _fail(f"{where}.schema_version", f"{doc['schema_version']!r}")
    for group in ("states", "decoded_reasons"):
        table = _obj(doc[group], f"{where}.{group}")
        if not table:
            _fail(f"{where}.{group}", "is empty")
        for name, code in table.items():
            _int(code, f"{where}.{group}.{name}")
        if len(set(table.values())) != len(table):
            _fail(f"{where}.{group}", "codes are not unique; a cell would decode to two different names")
    return doc


def projection_row_v3(row):
    return _spell_row(row, rich=True, schema_version="coa-client-spell-projection-v3",
                      where="projection_row_v3")


def icon_row_v1(row):
    where = "icon_row_v1"
    _obj(row, where)
    _keys(row, required=("schema_version", "spell_id", "spell_icon_id", "asset_status", "client_path",
                         "readiness"),
          # E0R.2 T2.5: `converted_ref` left this list with `converted` itself. The status vocabulary is
          # checked semantically (publish._verify_icon_row / Node verifyIconRow), symmetrically in both
          # languages; here the key simply has no admissible use.
          optional=("source_archive", "source_asset_sha256"), where=where)
    if row["schema_version"] != "coa-client-spell-icons-v1":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r}")
    _int(row["spell_id"], f"{where}.spell_id")
    _int(row["spell_icon_id"], f"{where}.spell_icon_id", allow_null=True)
    _str(row["asset_status"], f"{where}.asset_status")
    _str(row["client_path"], f"{where}.client_path", allow_null=True)
    _str(row["readiness"], f"{where}.readiness")
    for key in ("source_archive", "source_asset_sha256"):
        if key in row:
            _str(row[key], f"{where}.{key}", allow_null=True)
    return row


# --- E0R.2 T6.3: the normalized icon dialect ------------------------------------------------------
# `icon_row_v1` above is RETAINED: `e0r-v1`/`e0r-v2` still name it, and a generation published under
# either must keep validating.
_ICON_AVAILABILITY = ("source_only", "missing")


def icon_association_row_v2(row):
    """One spell's icon reference. It carries no path, no hash and no archive — those live once on the
    referenced asset row — and its two interned codes say WHY a null reference is null."""
    where = "icon_association_row_v2"
    _obj(row, where)
    _keys(row, required=("schema_version", "spell_id", "spell_icon_id", "asset_ref", "s", "d",
                         "readiness"), where=where)
    if row["schema_version"] != "coa-client-spell-icons-v2":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r}")
    _int(row["spell_id"], f"{where}.spell_id")
    _int(row["spell_icon_id"], f"{where}.spell_icon_id", allow_null=True)
    _str(row["asset_ref"], f"{where}.asset_ref", allow_null=True)
    _coded_vocabulary(row, where)
    if row["readiness"] not in ("available", "unavailable"):
        _fail(f"{where}.readiness", f"{row['readiness']!r} not in ('available', 'unavailable')")
    return row


def icon_asset_row_v1(row):
    """One normalized client asset. Hash and archive are non-null IFF `source_only` — a `missing` asset
    is a PROVEN path whose member is absent from the chain, so it has neither, and the earlier model
    that required them of every asset row could never have been satisfied."""
    where = "icon_asset_row_v1"
    _obj(row, where)
    _keys(row, required=("schema_version", "asset_id", "client_path", "availability",
                         "source_asset_sha256", "source_archive"), where=where)
    if row["schema_version"] != "coa-client-icon-assets-v1":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r}")
    _str(row["asset_id"], f"{where}.asset_id")
    _str(row["client_path"], f"{where}.client_path")
    if row["availability"] not in _ICON_AVAILABILITY:
        _fail(f"{where}.availability", f"{row['availability']!r} not in {_ICON_AVAILABILITY}")
    _str(row["source_asset_sha256"], f"{where}.source_asset_sha256", allow_null=True)
    _str(row["source_archive"], f"{where}.source_archive", allow_null=True)
    present = row["availability"] == "source_only"
    for key in ("source_asset_sha256", "source_archive"):
        if present and row[key] is None:
            _fail(f"{where}.{key}", "a source_only asset must carry it")
        if not present and row[key] is not None:
            _fail(f"{where}.{key}", "a missing asset has no member to describe")
    return row


def content_row_v1(row):
    where = "content_row_v1"
    _obj(row, where)
    _keys(row, required=("schema_version", "content_kind", "values", "provenance", "coa_attribution"),
          optional=("spell_id", "item_id"), where=where)
    if row["schema_version"] != "coa-client-content-v1":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r}")
    _str(row["content_kind"], f"{where}.content_kind")
    _obj(row["values"], f"{where}.values")
    provenance = _obj(row["provenance"], f"{where}.provenance")
    _keys(provenance, required=("source_file", "file_sha256", "extraction_date"),
          where=f"{where}.provenance")
    for key in ("source_file", "file_sha256", "extraction_date"):
        _str(provenance[key], f"{where}.provenance.{key}")
    attribution = _obj(row["coa_attribution"], f"{where}.coa_attribution")
    _keys(attribution, required=("status",), optional=("note",), where=f"{where}.coa_attribution")
    for key in ("spell_id", "item_id"):
        if key in row:
            _int(row[key], f"{where}.{key}")
    return row


def advancement_row_v1(row):
    where = "advancement_row_v1"
    _obj(row, where)
    _keys(row, required=("schema_version", "node_id", "spell_id", "name", "class", "tab", "entry_type",
                         "essence_kind", "legality", "field_confidence", "raw", "provenance",
                         "coa_attribution"), where=where)
    if row["schema_version"] != "coa-client-advancement-v1":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r}")
    _int(row["node_id"], f"{where}.node_id")
    _int(row["spell_id"], f"{where}.spell_id", allow_null=True)
    _str(row["name"], f"{where}.name", allow_null=True)
    klass = _obj(row["class"], f"{where}.class")
    _keys(klass, required=("class_type_id", "internal", "display", "kind"), where=f"{where}.class")
    _int(klass["class_type_id"], f"{where}.class.class_type_id")
    for key in ("internal", "display", "kind"):
        _str(klass[key], f"{where}.class.{key}", allow_null=True)
    tab = _obj(row["tab"], f"{where}.tab")
    _keys(tab, required=("tab_type_id", "name"), where=f"{where}.tab")
    _int(tab["tab_type_id"], f"{where}.tab.tab_type_id", allow_null=True)
    _str(tab["name"], f"{where}.tab.name", allow_null=True)
    _str(row["entry_type"], f"{where}.entry_type", allow_null=True)
    _str(row["essence_kind"], f"{where}.essence_kind", allow_null=True)
    _obj(row["legality"], f"{where}.legality")
    _obj(row["field_confidence"], f"{where}.field_confidence")
    raw = _obj(row["raw"], f"{where}.raw")
    _keys(raw, required=("cols",), where=f"{where}.raw")
    _cols(raw["cols"], f"{where}.raw.cols")
    _obj(row["provenance"], f"{where}.provenance")
    _attribution(row["coa_attribution"], f"{where}.coa_attribution")
    return row


def _cols(value, where: str) -> None:
    """The index-keyed audit map: JSON object keys are strings, so the INDEX is a decimal string and the
    value an integer. Anything else is an undecoded cell smuggled in as text."""
    cols = _obj(value, where)
    for index, cell in cols.items():
        if not index.isdigit():
            _fail(where, f"column key {index!r} is not a decimal cell index")
        _int(cell, f"{where}.{index}")


def class_type_row_v1(row):
    where = "class_type_row_v1"
    _obj(row, where)
    _keys(row, required=("schema_version", "class_type_id", "internal", "display", "kind",
                         "display_source", "display_evidence"), where=where)
    if row["schema_version"] != "coa-client-class-types-v1":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r}")
    _int(row["class_type_id"], f"{where}.class_type_id")
    for key in ("internal", "display", "kind", "display_source"):
        _str(row[key], f"{where}.{key}", allow_null=True)
    if not isinstance(row["display_evidence"], list):
        _fail(f"{where}.display_evidence", "must be a list")
    return row


def tab_type_row_v1(row):
    where = "tab_type_row_v1"
    _obj(row, where)
    _keys(row, required=("schema_version", "tab_type_id", "name"), where=where)
    if row["schema_version"] != "coa-client-tab-types-v1":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r}")
    _int(row["tab_type_id"], f"{where}.tab_type_id")
    _str(row["name"], f"{where}.name", allow_null=True)
    return row


def essence_row_v1(row):
    where = "essence_row_v1"
    _obj(row, where)
    _keys(row, required=("schema_version", "cols", "provenance"), where=where)
    if row["schema_version"] != "coa-client-essence-v1":
        _fail(f"{where}.schema_version", f"{row['schema_version']!r}")
    _cols(row["cols"], f"{where}.cols")
    _obj(row["provenance"], f"{where}.provenance")
    return row


def archive_plan_v1(doc):
    where = "archive_plan_v1"
    _obj(doc, where)
    # `{}` used to pass as a one-record JSON artifact. An archive plan with no ordering rule and no
    # archives describes nothing, and the load order it fails to describe is what the whole extraction
    # is bound to.
    _keys(doc, required=("schema_version", "client_root", "ordering_rule", "base_archives",
                         "patch_archives", "excluded"), where=where)
    if doc["schema_version"] != "coa-client-archive-plan-v1":
        _fail(f"{where}.schema_version", f"{doc['schema_version']!r}")
    _str(doc["client_root"], f"{where}.client_root")
    _str(doc["ordering_rule"], f"{where}.ordering_rule")
    for key in ("base_archives", "patch_archives"):
        if not isinstance(doc[key], list):
            _fail(f"{where}.{key}", "must be a list")
    # `excluded` is keyed by exclusion FAMILY (area52, reborn): which families were considered is part
    # of the plan, so an empty list per family is a recorded decision and a missing family is not.
    excluded = _obj(doc["excluded"], f"{where}.excluded")
    for family, members in excluded.items():
        if not isinstance(members, list):
            _fail(f"{where}.excluded.{family}", "must be a list")
    return doc


def projection_manifest_v3(doc):
    where = "projection_manifest_v3"
    _obj(doc, where)
    _keys(doc, required=("schema_version", "inclusion_rule", "client_build", "extractor_commit",
                         "extraction_date", "policy_sha256", "counts"), where=where)
    if doc["schema_version"] != "coa-client-spell-projection-manifest-v3":
        _fail(f"{where}.schema_version", f"{doc['schema_version']!r}")
    rule = _obj(doc["inclusion_rule"], f"{where}.inclusion_rule")
    _keys(rule, required=("predicate", "version"), where=f"{where}.inclusion_rule")
    _str(rule["predicate"], f"{where}.inclusion_rule.predicate")
    _str(doc["policy_sha256"], f"{where}.policy_sha256")
    if len(doc["policy_sha256"]) != 64:
        _fail(f"{where}.policy_sha256", "must be a 64-char digest")
    counts = _obj(doc["counts"], f"{where}.counts")
    _keys(counts, required=("source_records", "projected_records", "unique_spell_ids"),
          where=f"{where}.counts")
    for key in counts:
        _int(counts[key], f"{where}.counts.{key}")
    return doc


def spell_policy_v2(doc):
    """The staged policy child. Full semantic validation is `load_spell_policy`, which the candidate
    validator's trust chain already runs against the LOCK; this is the structural gate that says the
    document is a policy at all before that runs."""
    where = "spell_policy_v2"
    _obj(doc, where)
    _keys(doc, required=("schema_version", "reviewed", "required_tables", "tables", "joins", "sha256",
                         "content_sources", "bound", "expected_absent", "enum_policy", "anchor_set",
                         "artifact_contract"),
          # E0R.2 T3.2: `ambiguity_baseline` is optional — a policy with no adjudicated-ambiguous
          # join needs none — but a staged policy that carries one must still parse as a policy.
          optional=("budget", "provenance_note", "ambiguity_baseline"),
          where=where)
    if doc["schema_version"] != "coa-spell-layout-v2":
        _fail(f"{where}.schema_version", f"{doc['schema_version']!r}")
    if doc["reviewed"] is not True:
        _fail(f"{where}.reviewed", "an unreviewed policy may not be staged")
    _obj(doc["tables"], f"{where}.tables")
    # E0R.2 T2.3: the observation domain is structural, not an optional annotation. Node has no
    # load_spell_policy to fall back on — the shape is the only thing standing between it and a policy
    # whose domain it would read as `undefined` and then check nothing against.
    contract = _obj(doc["artifact_contract"], f"{where}.artifact_contract")
    _keys(contract, required=("required_raw_observations", "required_mechanics_keys",
                              "nullable_mechanics_keys", "icon_observation_domain"),
          where=f"{where}.artifact_contract")
    for key, names in contract.items():
        if not isinstance(names, list):
            _fail(f"{where}.artifact_contract.{key}", "must be a list of field names")
        for name in names:
            _str(name, f"{where}.artifact_contract.{key}[]")
    return doc


def generation_contract_v1(doc):
    """Delegates to the contract's own self-validation — one authority for what a contract is."""
    from .contracts import ContractError, validate_generation_contract
    try:
        return validate_generation_contract(doc)
    except ContractError as exc:
        raise ShapeError(f"generation_contract_v1: {exc}") from exc


SHAPES = {
    "full_spell_row_v3": full_spell_row_v3,
    # E0R.2 T6.2: v4 is REGISTERED BESIDE v3, never in place of it — `e0r-v1` stays supported, so a
    # generation published under it must still validate against the shape it was produced with.
    "full_spell_row_v4": full_spell_row_v4,
    "spell_field_descriptors_v1": spell_field_descriptors_v1,
    "observation_wire_v1": observation_wire_v1,
    "projection_row_v3": projection_row_v3,
    "icon_row_v1": icon_row_v1,
    "icon_association_row_v2": icon_association_row_v2,
    "icon_asset_row_v1": icon_asset_row_v1,
    "content_row_v1": content_row_v1,
    "advancement_row_v1": advancement_row_v1,
    "class_type_row_v1": class_type_row_v1,
    "tab_type_row_v1": tab_type_row_v1,
    "essence_row_v1": essence_row_v1,
    "archive_plan_v1": archive_plan_v1,
    "projection_manifest_v3": projection_manifest_v3,
    "spell_policy_v2": spell_policy_v2,
    "generation_contract_v1": generation_contract_v1,
}
