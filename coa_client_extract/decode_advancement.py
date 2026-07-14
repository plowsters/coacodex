# coa_client_extract/decode_advancement.py
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .dbc_layouts import CharacterAdvancementLayout

# JSON field (loose CharacterAdvancementData.json) -> layout attribute it resolves. Every entry
# here is proven by correlation, never assumed. Names follow the loose JSON's own field names.
_SCALAR_FIELDS = {
    "AECost": "ae_cost_col", "TECost": "te_cost_col", "RequiredLevel": "required_level_col",
    "RequiredAEInvestment": "required_tab_ae_col", "RequiredTEInvestment": "required_tab_te_col",
    "MaxRank": "max_rank_col", "Row": "row_col", "Column": "column_col",
}


@dataclass(frozen=True)
class ScalarProof:
    column: int
    score: float
    runner_up: float
    margin: float
    nonzero: int


def _s32(u: int) -> int:
    return u - 0x100000000 if u >= 0x80000000 else u


def correlate_scalar(pairs, json_field, *, min_nonzero: int = 50) -> ScalarProof | None:
    """Rank every column by exact-match fraction against json_field over (json, row) pairs, and
    return the winner WITH its uniqueness margin over the runner-up and its non-zero evidence
    count. Returns None when the best column lacks >= min_nonzero non-zero matched values (guards
    against zero-dominated columns matching a mostly-zero field by accident)."""
    cols = set().union(*[set(r) for _, r in pairs]) if pairs else set()
    scored = []
    for c in cols:
        matched = total = nonzero = 0
        for je, row in pairs:
            if json_field in je and c in row:
                total += 1
                jv = je[json_field]
                if row[c] == jv or _s32(row[c]) == jv:
                    matched += 1
                    if row[c] != 0:
                        nonzero += 1
        if total >= min_nonzero:
            scored.append((matched / total, nonzero, c))
    if not scored:
        return None
    scored.sort(reverse=True)
    top = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    if top[1] < min_nonzero:
        return None
    return ScalarProof(top[2], round(top[0], 4), round(runner, 4), round(top[0] - runner, 4), top[1])


def prove_adjacency_domain(ca_rows, node_ids, candidate_cols, *, min_nonzero: int = 50) -> tuple[str, tuple[int, ...]]:
    """Prove the candidate columns are node-id references: every non-zero value resolves to an
    existing node id (col-0 domain), and there is at least min_nonzero non-zero evidence across
    the block (an all-zero block is 'unresolved', never a silent pass). Zero is padding."""
    nonzero = 0
    for row in ca_rows:
        for c in candidate_cols:
            v = row.get(c, 0)
            if v:
                nonzero += 1
                if v not in node_ids:
                    return "unresolved", ()
    if nonzero < min_nonzero:
        return "unresolved", ()
    return "node_id", tuple(candidate_cols)


def _unique_spell_pairs(ca_rows, json_entries):
    json_by_spell = defaultdict(list)
    for e in json_entries:
        sps = e.get("Spells") or []
        if len(sps) == 1:
            json_by_spell[int(sps[0])].append(e)
    ca_by_spell = defaultdict(list)
    for r in ca_rows:
        if r.get(5):
            ca_by_spell[r[5]].append(r)
    pairs = []
    for sp in set(json_by_spell) & set(ca_by_spell):
        if len(json_by_spell[sp]) == 1 and len(ca_by_spell[sp]) == 1:
            pairs.append((json_by_spell[sp][0], ca_by_spell[sp][0]))
    return pairs


# decode attr -> the legality/ownership field name read_advancement emits (so confidence keys line up
# with what read_advancement's emit()/gates check — keyed by FIELD name, not the "_col" attribute).
_LEGALITY_NAME = {
    "ae_cost_col": "ae_cost", "te_cost_col": "te_cost", "required_level_col": "required_level",
    "required_tab_ae_col": "required_tab_ae", "required_tab_te_col": "required_tab_te",
    "max_rank_col": "max_rank", "row_col": "row", "column_col": "col",
    "tab_type_col": "tab_type", "entry_type_col": "entry_type",
    "connected_node_cols": "connected_node_ids", "required_id_cols": "required_ids",
}


def _json_by_id(json_entries):
    return {int(e["ID"]): e for e in json_entries if e.get("ID") is not None}


def _node_id_hit_rate(ca_rows, node_ids) -> dict:
    """Per-column fraction of non-zero values that resolve to a node id (recorded evidence)."""
    cols = set().union(*[set(r) for r in ca_rows]) if ca_rows else set()
    out = {}
    for c in sorted(cols):
        nz = [r[c] for r in ca_rows if r.get(c)]
        if nz:
            out[str(c)] = round(sum(1 for v in nz if v in node_ids) / len(nz), 3)
    return out


_ANCHOR_COLS = {0, 5, 32}   # node_id, spell_id, class_type FK — never adjacency, excluded from discovery


def _discover_adjacency_blocks(ca_rows, node_ids, *, min_hit=0.9, min_nonzero=50):
    """Deterministically find contiguous column runs whose non-zero values overwhelmingly resolve to
    node ids — candidate adjacency blocks. No operator interpretation: the runs are computed here.
    The three anchor columns (node_id/spell/class) are excluded so col 0 is not mistaken for a block."""
    cols = [c for c in sorted(set().union(*[set(r) for r in ca_rows])) if c not in _ANCHOR_COLS] \
        if ca_rows else []
    good = set()
    for c in cols:
        nz = [r[c] for r in ca_rows if r.get(c)]
        if len(nz) >= min_nonzero and sum(1 for v in nz if v in node_ids) / len(nz) >= min_hit:
            good.add(c)
    blocks, run = [], []
    for c in cols:
        if c in good:
            run.append(c)
        elif run:
            blocks.append(tuple(run)); run = []
    if run:
        blocks.append(tuple(run))
    return blocks


def _classify_adjacency(ca_rows, json_by_id, block):
    """Match a proven node-ref block to the JSON ConnectedNodes or RequiredIDs field by per-node set
    agreement. Returns (json_field | None, agreement_fraction)."""
    best = (None, 0.0)
    for jf in ("ConnectedNodes", "RequiredIDs"):
        agree = total = 0
        for r in ca_rows:
            je = json_by_id.get(r.get(0))
            if not je or jf not in je:
                continue
            total += 1
            if {r.get(c) for c in block if r.get(c)} == set(je.get(jf) or []):
                agree += 1
        if total and agree / total > best[1]:
            best = (jf, round(agree / total, 4))
    return best


def _decode_entry_type(pairs, *, min_nonzero=50, score_threshold=0.85):
    """Prove the entry-type column by a ROBUST majority numeric->string mapping. A strict 1:1 that any
    single stale/noisy pair would reject fails against the real (stale) loose JSON; instead, for each
    candidate column map each numeric value to its MOST-COMMON JSON 'Type' string, and accept the column
    only when that mapping explains >= score_threshold of pairs, is injective, and has >= 2 classes.
    Returns (column, {str(int): str} mapping, evidence_count) or (None, {}, 0)."""
    from collections import Counter, defaultdict
    cols = set().union(*[set(r) for _, r in pairs]) if pairs else set()
    best = (None, {}, 0.0, 0)
    for c in sorted(cols):
        by_val, total = defaultdict(Counter), 0
        for je, row in pairs:
            if "Type" in je and c in row:
                by_val[row[c]][je["Type"]] += 1
                total += 1
        if total < min_nonzero or len(by_val) < 2:
            continue
        mapping = {v: cnt.most_common(1)[0][0] for v, cnt in by_val.items()}
        if len(set(mapping.values())) != len(mapping):        # mapping must be injective
            continue
        agree = sum(cnt[mapping[v]] for v, cnt in by_val.items())
        score = agree / total
        if score >= score_threshold and score > best[2]:
            best = (c, {str(k): v for k, v in mapping.items()}, score, total)
    return best[0], best[1], best[3]


def decode_layout(ca, class_types, tab_types, json_entries, *,
                  score_threshold: float = 0.85, margin_threshold: float = 0.15,
                  min_nonzero: int = 50) -> tuple[CharacterAdvancementLayout, dict]:
    """Resolve EVERY non-anchor adapter column from the loose-JSON schema key with recorded evidence,
    and emit the finished layout (no operator interpretation): scalars by exact-match correlation;
    the tab FK by correlation AND tag-domain membership; entry_type by a proven numeric->string
    mapping; and BOTH adjacency blocks by deterministic block discovery + `prove_adjacency_domain` +
    per-node set-match against the JSON's ConnectedNodes/RequiredIDs. A field is `high` only when its
    evidence clears the thresholds; otherwise it is left None/unproven (blocks canonical emission).
    Returns (layout, report); report['resolved_layout'] is the finished layout, loaded back by
    `load_resolved_layout` so `regenerate` consumes it with zero hand-editing."""
    ca_rows = ca.rows
    node_ids = {r.get(0) for r in ca_rows if r.get(0)}
    pairs = _unique_spell_pairs(ca_rows, json_entries)
    json_by_id = _json_by_id(json_entries)
    report = {"schema_version": "coa-ca-decode-report-v3", "unique_pairs": len(pairs),
              "thresholds": {"score": score_threshold, "margin": margin_threshold,
                             "min_nonzero": min_nonzero},
              "fields": {}}
    kwargs: dict = {}
    confidence: dict = {}

    def _record_scalar(attr, proof: ScalarProof | None, *, in_domain=True):
        if proof is None:
            report["fields"][attr] = {"confidence": "unproven", "column": None}
            return
        high = (proof.score >= score_threshold and proof.margin >= margin_threshold
                and proof.nonzero >= min_nonzero and in_domain)
        report["fields"][attr] = {
            "column": proof.column, "score": proof.score, "runner_up": proof.runner_up,
            "margin": proof.margin, "nonzero": proof.nonzero, "in_fk_domain": bool(in_domain),
            "confidence": "high" if high else "low"}
        if high:
            kwargs[attr] = proof.column
            confidence[_LEGALITY_NAME[attr]] = "high"

    # 1. scalar legality/position fields
    for json_field, attr in _SCALAR_FIELDS.items():
        _record_scalar(attr, correlate_scalar(pairs, json_field, min_nonzero=min_nonzero))

    # 2. tab-type FK: the loose JSON "Tab" is a display NAME string (e.g. "Frost"), NOT the numeric FK
    #    id, so a direct scalar correlation cannot match. Translate each name to its tab-type id via the
    #    resolved tab-types table, correlate the TRANSLATED id against columns, then require the winning
    #    column's non-zero domain to be tab-type ids. (Names already present as ids pass through.)
    name_to_tab_id = {name: tid for tid, name in tab_types.items()} if tab_types else {}
    def _tab_id(v):
        return v if v in tab_types else name_to_tab_id.get(v)
    tab_pairs = [({**je, "_TabId": _tab_id(je.get("Tab"))}, row)
                 for je, row in pairs if _tab_id(je.get("Tab")) is not None]
    tab_proof = correlate_scalar(tab_pairs, "_TabId", min_nonzero=min_nonzero)
    tab_domain_ok = bool(tab_types) and tab_proof is not None and all(
        r[tab_proof.column] in tab_types for r in ca_rows if r.get(tab_proof.column))
    _record_scalar("tab_type_col", tab_proof, in_domain=tab_domain_ok)

    # 3. entry-type: proven numeric -> JSON 'Type' string mapping
    et_col, et_map, et_ev = _decode_entry_type(pairs, min_nonzero=min_nonzero)
    report["fields"]["entry_type_col"] = {
        "column": et_col, "mapping": et_map, "evidence": et_ev,
        "confidence": "high" if et_col is not None else "unproven"}
    report["entry_type_map"] = et_map
    if et_col is not None:
        kwargs["entry_type_col"] = et_col
        kwargs["entry_type_map"] = et_map        # proven map rides into resolved_layout -> the reader
        confidence["entry_type"] = "high"

    # 4. adjacency: discover node-ref blocks, prove each, classify vs ConnectedNodes / RequiredIDs
    report["node_id_hit_rate"] = _node_id_hit_rate(ca_rows, node_ids)
    report["adjacency"] = []
    for block in _discover_adjacency_blocks(ca_rows, node_ids, min_nonzero=min_nonzero):
        domain, cols = prove_adjacency_domain(ca_rows, node_ids, block, min_nonzero=min_nonzero)
        jf, agree = (_classify_adjacency(ca_rows, json_by_id, block)
                     if domain == "node_id" else (None, 0.0))
        report["adjacency"].append({"block": list(block), "domain": domain,
                                    "json_field": jf, "agreement": agree})
        if domain == "node_id" and agree >= score_threshold:
            if jf == "ConnectedNodes":
                kwargs["connected_node_cols"] = cols
                confidence["connected_node_ids"] = "high"
            elif jf == "RequiredIDs":
                kwargs["required_id_cols"] = cols
                confidence["required_ids"] = "high"

    layout = CharacterAdvancementLayout(**kwargs, confidence=confidence)
    report["resolved_layout"] = {
        **{k: (list(v) if isinstance(v, tuple) else v) for k, v in kwargs.items()},
        "confidence": confidence}
    return layout, report


def load_resolved_layout(path) -> CharacterAdvancementLayout | None:
    """Reconstruct the resolved CharacterAdvancementLayout from a committed decode report's
    `resolved_layout` block, so `regenerate` consumes the proven layout with NO hand-editing."""
    p = Path(path)
    if not p.is_file():
        return None
    rl = json.loads(p.read_text()).get("resolved_layout")
    if not rl:
        return None
    conf = rl.pop("confidence", {})
    kwargs = {k: (tuple(v) if isinstance(v, list) else v) for k, v in rl.items()}
    return CharacterAdvancementLayout(**kwargs, confidence=conf)


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
