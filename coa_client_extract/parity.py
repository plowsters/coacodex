from __future__ import annotations

# adapter columns -> the CharacterAdvancementLayout attribute holding their column index.
_SCALAR_FIELD_COLS = {
    "ae_cost": "ae_cost_col", "te_cost": "te_cost_col", "required_level": "required_level_col",
    "required_tab_ae": "required_tab_ae_col", "required_tab_te": "required_tab_te_col",
    "max_rank": "max_rank_col", "row": "row_col", "col": "column_col",
    "tab_type": "tab_type_col", "entry_type": "entry_type_col",
}
_ADJACENCY_FIELD_COLS = {"connected_node_ids": "connected_node_cols", "required_ids": "required_id_cols"}

# legality scalars compared per node when the client decoded them to `high` (incl. cosmetic row/col).
_LEGALITY_FIELDS = ("ae_cost", "te_cost", "required_level", "required_tab_ae",
                    "required_tab_te", "max_rank", "row", "col")
# the REQUIRED legality responsibilities that gate per-field readiness + full_builder_retirement_ready.
# row/col are cosmetic layout fields (readiness.layout) and are deliberately excluded here.
_REQUIRED_LEGALITY = ("required_level", "ae_cost", "te_cost", "required_tab_ae",
                      "required_tab_te", "max_rank")

EXPECTED_BUILDER_RECORDS = 3612   # pinned Builder artifact size (the CLI passes this to guard truncation)


def flip_gate_inputs(layout):
    """Derive (low_confidence_fields, unresolved_layout_columns) from a resolved
    CharacterAdvancementLayout. A column never resolved (None / empty tuple) is 'unresolved'; a
    resolved column that did not prove to `high` confidence is 'low_confidence'. Both mark the field
    not-high, which build_parity_report turns into per-field readiness. Adjacency columns are handled
    the same way — their *value* agreement with the Builder is measured separately (adjacency_mismatches),
    but if adjacency never decoded high it is unresolved (so `adjacency_ready` cannot be true)."""
    conf = layout.confidence or {}
    low, unresolved = [], []
    for field, attr in {**_SCALAR_FIELD_COLS, **_ADJACENCY_FIELD_COLS}.items():
        col = getattr(layout, attr)
        resolved = col is not None and col != ()
        if not resolved:
            unresolved.append(field)
        elif conf.get(field) != "high":
            low.append(field)
    return low, unresolved


def _identity(spell_id, class_name):
    # The ownership-alignment identity uses ONLY the structurally-anchored fields: spell_id (col 5)
    # and class (col 32 FK). tab_name/entry_type are decode-gated (often unresolved) and must NOT
    # enter this tuple — otherwise a node whose tab/entry_type simply hasn't decoded would read as an
    # identity mismatch, coupling ownership to metadata decode (which Decision 21 keeps independent).
    return (int(spell_id), class_name)


def _norm(v):
    # normalize representation differences (Decision 22 class c): missing/None == 0
    return 0 if v is None else v


def build_parity_report(nodes, builder_entries, *, class_types=None,
                        low_confidence_fields=(), unresolved_layout_columns=(),
                        expected_builder_records=None, provenance=None) -> dict:
    """Node-level Builder-parity report + a SCOPED, per-responsibility/per-field `readiness` object
    (Decision 21), computing every comparison from a real node-id crosswalk.

    The Builder's `entry_id` and the client's `node_id` are the same advancement-row identity; the
    report crosswalks them directly and proves the id spaces align by checking each matched id's
    anchored tuple (spell_id, class) — `identity_mismatches`. Ownership is an exact
    SET over node ids: `builder_only` AND `client_only` must both be empty (a client graph that covers
    every Builder node but adds extras is not ownership-ready). Adjacency and legality are compared per
    matched node; legality differences are classified per Decision 22.

    There is NO single flip boolean. Instead `readiness` earns each dimension independently:
    `attribution_ready` (anchored class_type FK + 21-class cardinality, no legality dependency),
    `ownership_ready` (exact ownership + zero identity_mismatches + count/cardinality guards),
    `adjacency_ready` (both edge domains decoded high AND zero adjacency_mismatches), per-field
    `legality[field]` (`ready` only when decoded high and not a Decision-22 (a)/(d) defect; else
    `unresolved`, which keeps the Builder fallback and blocks flipping THAT field only — never
    attribution/ownership), cosmetic `layout.row`/`layout.col` (block nothing), a separate
    `leveling_progression_ready: False` (raw essence, M1.15), and the roll-up
    `full_builder_retirement_ready`. `blockers` is a flat diagnostic list of the specific unmet
    conditions, mirrored by the readiness object (not itself a gate). `low_confidence_fields` /
    `unresolved_layout_columns` come from `flip_gate_inputs(layout)`; a field is decoded-high iff it is
    in neither."""
    coa_nodes = [n for n in nodes if n.class_kind == "coa_class"]
    client_by_id = {n.node_id: n for n in coa_nodes}
    builder_by_id = {int(e["entry_id"]): e for e in builder_entries}
    client_ids, builder_ids = set(client_by_id), set(builder_by_id)
    matched = client_ids & builder_ids
    builder_only_ids = sorted(builder_ids - client_ids)
    client_only_ids = sorted(client_ids - builder_ids)

    # identity: matched ids whose anchored (spell_id, class) tuple disagrees — proves the id spaces
    # align (not accidental id collisions), using only structurally-verified anchors so an undecoded
    # tab/entry_type never fabricates a mismatch.
    identity_mismatch_ids = [
        nid for nid in matched
        if _identity(client_by_id[nid].spell_id, client_by_id[nid].class_display)
        != _identity(builder_by_id[nid]["spell_id"], builder_by_id[nid]["class_name"])]

    # adjacency parity (computed) over matched nodes that decoded adjacency to `high`
    adjacency_mismatch_ids = set()
    for nid in matched:
        n, e = client_by_id[nid], builder_by_id[nid]
        for field in ("connected_node_ids", "required_ids"):
            if field in n.legality and set(n.legality[field]) != set(e.get(field) or []):
                adjacency_mismatch_ids.add(nid)

    # legality parity (computed, Decision-22 classified) over matched nodes. Only fields the client
    # decoded to `high` (present in n.legality) are value-compared -> class (b) or (c); a field the
    # client could not decode is captured globally by low_confidence/unresolved (class a/d).
    legality_diffs = []
    for nid in matched:
        n, e = client_by_id[nid], builder_by_id[nid]
        for f in _LEGALITY_FIELDS:
            if f in e and f in n.legality:
                cv, bv = _norm(n.legality[f]), _norm(e[f])
                if cv != bv:                     # proven-high client value differs -> client wins
                    legality_diffs.append({"node_id": nid, "field": f,
                                           "client": cv, "builder": bv, "class": "b"})

    # per-class and per-tab node counts (+ the asymmetric-only tallies)
    def _counts(key):
        cc = {}
        blank = lambda: {"client_nodes": 0, "builder_records": 0, "client_only": 0, "builder_only": 0}
        for n in coa_nodes:
            cc.setdefault(key(n.class_display, n.tab_name), blank())["client_nodes"] += 1
        for e in builder_entries:
            cc.setdefault(key(e["class_name"], e.get("tab_name", "")), blank())["builder_records"] += 1
        for nid in client_only_ids:
            n = client_by_id[nid]
            cc[key(n.class_display, n.tab_name)]["client_only"] += 1
        for nid in builder_only_ids:
            e = builder_by_id[nid]
            cc[key(e["class_name"], e.get("tab_name", ""))]["builder_only"] += 1
        return cc

    per_class = _counts(lambda cls, tab: cls)
    per_tab = [{"class": cls, "tab": tab, **v}
               for (cls, tab), v in sorted(_counts(lambda cls, tab: (cls, tab)).items())]

    ownership_recall = round(len(matched) / len(builder_ids), 4) if builder_ids else 1.0
    ownership_precision = round(len(matched) / len(client_ids), 4) if client_ids else 1.0
    client_spells = {n.spell_id for n in coa_nodes}
    builder_spells = {int(e["spell_id"]) for e in builder_entries}

    # ---- scoped readiness (Decision 21). A field is decoded-high iff it is in neither
    # low_confidence_fields nor unresolved_layout_columns (both come from flip_gate_inputs(layout)).
    not_high = set(low_confidence_fields) | set(unresolved_layout_columns)
    field_ready = lambda f: f not in not_high

    taxonomy_ok = class_types is None or (
        sum(1 for c in class_types.values() if c.kind == "coa_class") == 21
        and not (class_types.get(35) is not None and class_types.get(35).kind == "coa_class"))
    count_ok = expected_builder_records is None or len(builder_entries) == expected_builder_records

    # attribution rests on the anchored class_type FK — NO legality dependency
    attribution_ready = bool(coa_nodes) and taxonomy_ok
    # ownership: exact node-id ownership + identity-tuple parity + count/cardinality/non-empty guards
    ownership_ready = (bool(coa_nodes) and bool(builder_entries) and taxonomy_ok and count_ok
                       and not builder_only_ids and not client_only_ids and not identity_mismatch_ids)
    # adjacency: BOTH edge domains decoded high AND zero per-node mismatches
    adjacency_ready = (field_ready("connected_node_ids") and field_ready("required_ids")
                       and not adjacency_mismatch_ids)
    # per-field legality readiness: `ready` only when decoded high (class b/c proven diffs stay ready;
    # a/d undecoded stay unresolved). row/col are cosmetic layout, never gating.
    legality_readiness = {f: ("ready" if field_ready(f) else "unresolved") for f in _REQUIRED_LEGALITY}
    layout_readiness = {"row": "ready" if field_ready("row") else "unresolved",
                        "col": "ready" if field_ready("col") else "unresolved"}
    full_builder_retirement_ready = (
        attribution_ready and ownership_ready and adjacency_ready
        and all(v == "ready" for v in legality_readiness.values()))

    readiness = {
        "attribution_ready": attribution_ready,
        "ownership_ready": ownership_ready,
        "adjacency_ready": adjacency_ready,
        "legality": legality_readiness,
        "layout": layout_readiness,
        # raw essence progression is undecoded in M1.14B: a SEPARATE M1.15 leveling gate that never
        # blocks any max-level dimension or full_builder_retirement_ready.
        "leveling_progression_ready": False,
        "full_builder_retirement_ready": full_builder_retirement_ready,
    }

    # flat diagnostic list of the specific unmet conditions (mirrors readiness; NOT itself a gate)
    blockers: list[str] = []
    if not coa_nodes:
        blockers.append("empty_client_input")
    if not builder_entries:
        blockers.append("empty_builder_input")
    if class_types is not None and sum(1 for c in class_types.values() if c.kind == "coa_class") != 21:
        blockers.append("playable_class_count")
    if class_types is not None and (class_types.get(35) is not None
                                    and class_types.get(35).kind == "coa_class"):
        blockers.append("sentinel_not_excluded")
    if not count_ok:
        blockers.append("builder_record_count")
    if builder_only_ids:
        blockers.append("builder_only_node_instances")
    if client_only_ids:
        blockers.append("client_only_node_instances")
    if identity_mismatch_ids:
        blockers.append("identity_mismatch")
    if adjacency_mismatch_ids:
        blockers.append("adjacency_mismatch")
    blockers += [f"low_confidence:{f}" for f in low_confidence_fields]
    blockers += [f"unresolved_layout_column:{c}" for c in unresolved_layout_columns]

    report = {
        "schema_version": "coa-builder-parity-v2",
        "builder_records": len(builder_entries),
        "client_nodes": len(coa_nodes),
        "unique_spell_recall": round(len(client_spells & builder_spells) / len(builder_spells), 4)
                               if builder_spells else 1.0,
        "ownership_recall": ownership_recall,
        "ownership_precision": ownership_precision,
        "builder_only_records": len(builder_only_ids),
        "client_only_records": len(client_only_ids),
        "builder_only_sample": builder_only_ids[:20],
        "client_only_sample": client_only_ids[:20],
        "identity_mismatches": len(identity_mismatch_ids),
        "identity_mismatch_sample": sorted(identity_mismatch_ids)[:20],
        "per_class": per_class,
        "per_tab": per_tab,
        "adjacency_mismatches": len(adjacency_mismatch_ids),
        "adjacency_mismatch_sample": sorted(adjacency_mismatch_ids)[:20],
        "legality_diffs": legality_diffs,
        "readiness": readiness,
        "blockers": blockers,
    }
    if provenance:
        report["provenance"] = dict(provenance)   # Decision 10 reproducibility pins
    return report
