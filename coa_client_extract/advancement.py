from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .errors import DbcSemanticError

_MAX_LEVEL = 60
# Plausibility ceilings (cells are unsigned, so a mis-mapped column reads as a huge int — an
# upper bound catches that where a negative check cannot). Generous but far below a stray uint32.
_MAX_COST = 500
_MAX_RANK = 20
_MAX_ROWCOL = 200

# Which legality fields are node-id references (validated against the node-id domain).
_ADJ_FIELDS = ("connected_node_ids", "required_ids")
# Scalar legality fields with an inclusive upper bound.
_BOUNDS = {"ae_cost": _MAX_COST, "te_cost": _MAX_COST, "required_tab_ae": _MAX_COST,
           "required_tab_te": _MAX_COST, "max_rank": _MAX_RANK, "row": _MAX_ROWCOL, "col": _MAX_ROWCOL}


@dataclass(frozen=True)
class AdvancementNode:
    node_id: int
    spell_id: int
    class_type_id: int
    class_internal: str
    class_display: str
    class_kind: str
    tab_type_id: int
    tab_name: str
    entry_type: str
    essence_kind: str          # "ability" | "talent" | "" (derived from entry_type)
    legality: dict
    field_confidence: dict
    raw: dict                  # {cell_index: value} preserved for audit (explicit indices)


def _slots(row: dict, cols) -> list[int]:
    # gather node ids from fixed slot columns, dropping 0 padding, de-duped, sorted
    seen: list[int] = []
    for c in cols:
        v = row.get(c, 0)
        if v and v not in seen:
            seen.append(v)
    return sorted(seen)


def _essence_kind(entry_type: str) -> str:
    if entry_type in ("Ability", "TalentAbility"):
        return "ability"
    if entry_type == "Talent":
        return "talent"
    return ""


def read_advancement(ca, class_types, tab_types, layout) -> list[AdvancementNode]:
    """Build nodes from positional rows. A legality field is emitted ONLY when the layout proved
    it to `high` confidence (layout.confidence); a configured-but-unproven column is withheld, so
    a mis-decoded column never becomes canonical output."""
    L = layout
    conf_map = L.confidence or {}
    nodes: list[AdvancementNode] = []
    # Ownership FK columns are confidence-gated exactly like legality scalars: a node's tab and entry
    # type are emitted only when their columns proved `high`. A wrong column that coincidentally
    # resolves to a valid FK is withheld (tab_type_id=0 / entry_type="") and then blocks in
    # validate_semantics, rather than being shipped as canonical ownership.
    tab_ok = L.tab_type_col is not None and conf_map.get("tab_type") == "high"
    entry_ok = L.entry_type_col is not None and conf_map.get("entry_type") == "high"
    for row in ca.rows:
        cid = row.get(L.class_type_col, 0)
        ct = class_types.get(cid)
        tab_id = row.get(L.tab_type_col, 0) if tab_ok else 0
        # proven numeric->string map from the decode (JSON keys are strings); never hard-coded
        etype = L.entry_type_map.get(str(row.get(L.entry_type_col, "")), "") if entry_ok else ""
        legality, conf = {}, {}

        def emit(name, value):
            if conf_map.get(name) == "high":     # gate every legality field on proven confidence
                legality[name] = value
                conf[name] = "high"

        for name, col in (
            ("ae_cost", L.ae_cost_col), ("te_cost", L.te_cost_col),
            ("required_level", L.required_level_col),
            ("required_tab_ae", L.required_tab_ae_col), ("required_tab_te", L.required_tab_te_col),
            ("max_rank", L.max_rank_col), ("row", L.row_col), ("col", L.column_col),
        ):
            if col is not None:
                emit(name, row.get(col, 0))
        if L.connected_node_cols:
            emit("connected_node_ids", _slots(row, L.connected_node_cols))
        if L.required_id_cols:
            emit("required_ids", _slots(row, L.required_id_cols))

        nodes.append(AdvancementNode(
            node_id=row.get(L.node_id_col, 0), spell_id=row.get(L.spell_id_col, 0),
            class_type_id=cid,
            class_internal=(ct.internal if ct else ""),
            class_display=(ct.display if ct else ""),
            class_kind=(ct.kind if ct else "unknown"),
            tab_type_id=tab_id,
            tab_name=(tab_types.get(tab_id, "") if tab_ok else ""),
            entry_type=etype, essence_kind=_essence_kind(etype),
            legality=legality, field_confidence=conf,
            raw=dict(row),
        ))
    return nodes


def validate_semantics(nodes, class_types, tab_types) -> None:
    """Reject a mis-decoded or structurally invalid graph. A matching WDBC header is not enough:
    ownership FKs must resolve, adjacency must resolve in the node-id domain, and scalars must be
    plausible. Any failure raises DbcSemanticError (blocks canonical emission)."""
    node_ids = {n.node_id for n in nodes}
    dup = [nid for nid, c in Counter(n.node_id for n in nodes).items() if c > 1]
    if dup:
        raise DbcSemanticError(f"duplicate node ids: {sorted(dup)[:10]}")
    for n in nodes:
        if n.node_id == 0:
            raise DbcSemanticError("node id 0 is invalid")
        if n.class_kind == "unknown":
            raise DbcSemanticError(f"node {n.node_id}: unknown class type {n.class_type_id}")
        if n.tab_type_id and n.tab_type_id not in tab_types:
            raise DbcSemanticError(f"node {n.node_id}: unknown tab type {n.tab_type_id}")
        if n.entry_type == "":
            raise DbcSemanticError(f"node {n.node_id}: unknown entry_type")
        for adj_field in _ADJ_FIELDS:
            for ref in n.legality.get(adj_field, []):
                if ref == n.node_id:
                    raise DbcSemanticError(f"node {n.node_id}: self-reference in {adj_field}")
                if ref not in node_ids:
                    raise DbcSemanticError(f"node {n.node_id}: dangling {adj_field} reference {ref}")
        lvl = n.legality.get("required_level")
        if lvl is not None and not (lvl == 0 or 1 <= lvl <= _MAX_LEVEL):
            raise DbcSemanticError(
                f"node {n.node_id}: required_level {lvl} outside {{0}} u [1,{_MAX_LEVEL}]")
        for field_name, ceiling in _BOUNDS.items():
            v = n.legality.get(field_name)
            if v is not None and v > ceiling:
                raise DbcSemanticError(f"node {n.node_id}: {field_name} {v} exceeds ceiling {ceiling}")
    _validate_graph_invariants(nodes)


def _validate_graph_invariants(nodes) -> None:
    """Per (class, tab) subgraph, reject a mis-decoded adjacency layout with graph-level invariants
    that node-level ownership equality does NOT imply (identical (spell, class, tab, type) membership
    says nothing about whether the adjacency EDGES form a valid graph):

      - every tab with >1 node has a root (a node with no in-subgraph prerequisite);
      - every node is reachable from the roots over the union of connected/required edges (no orphans);
      - the prerequisite (required_ids) graph is acyclic.

    Runs only when adjacency was decoded to `high` (present in `legality`); when adjacency is
    undecoded it leaves `adjacency_ready` false via the parity readiness gate, not a semantic error here."""
    from collections import defaultdict, deque
    if not any("connected_node_ids" in n.legality or "required_ids" in n.legality for n in nodes):
        return
    subgraphs = defaultdict(list)
    for n in nodes:
        subgraphs[(n.class_type_id, n.tab_type_id)].append(n)
    for (cid, tid), sub in subgraphs.items():
        ids = {n.node_id for n in sub}
        by_id = {n.node_id: n for n in sub}
        roots = [n.node_id for n in sub
                 if not [r for r in n.legality.get("required_ids", []) if r in ids]]
        if len(sub) > 1 and not roots:
            raise DbcSemanticError(
                f"class {cid} tab {tid}: no root node (every node has a prerequisite)")
        # reachability over the undirected connected-node (visual tree) edges, from the roots
        adj = defaultdict(set)
        for n in sub:
            for e in n.legality.get("connected_node_ids", []):
                if e in ids:
                    adj[n.node_id].add(e)
                    adj[e].add(n.node_id)
        seen, q = set(roots), deque(roots)
        while q:
            for nb in adj[q.popleft()]:
                if nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        orphans = ids - seen
        if orphans:
            raise DbcSemanticError(
                f"class {cid} tab {tid}: {len(orphans)} unreachable/orphan node(s) "
                f"{sorted(orphans)[:5]}")
        # prerequisite graph must be acyclic (iterative DFS, three-color)
        color = dict.fromkeys(ids, 0)   # 0 white, 1 gray, 2 black
        for start in ids:
            if color[start] != 0:
                continue
            stack = [(start, iter([r for r in by_id[start].legality.get("required_ids", []) if r in ids]))]
            color[start] = 1
            while stack:
                u, it = stack[-1]
                nxt = next(it, None)
                if nxt is None:
                    color[u] = 2
                    stack.pop()
                elif color[nxt] == 1:
                    raise DbcSemanticError(f"class {cid} tab {tid}: prerequisite cycle at node {nxt}")
                elif color[nxt] == 0:
                    color[nxt] = 1
                    stack.append((nxt, iter([r for r in by_id[nxt].legality.get("required_ids", []) if r in ids])))
