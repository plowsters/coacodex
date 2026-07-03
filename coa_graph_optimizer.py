#!/usr/bin/env python3
"""
coa_graph_optimizer.py

A lightweight "graph DB simulation" / build optimizer for Project Ascension CoA talent data.

What it CAN do:
- Load coa_entries.jsonl.
- Build an in-memory graph of talent/ability nodes.
- Model hard gates from:
  * required_level
  * required_ids
  * required_tab_ae / required_tab_te
  * ae_cost / te_cost
  * max_rank treated as a score signal, not multi-point rank spending yet
- Use beam search to find high-scoring legal builds under AE/TE budgets.
- Export graph JSON and optional Cypher-ish node/edge statements for Neo4j import experiments.

What it CANNOT do by itself:
- Prove the true best DPS build without a combat simulator or combat-log-derived weights.
- Know the exact per-level AE/TE earn schedule unless you pass budgets explicitly.
- Interpret every tooltip placeholder or hidden server formula perfectly.

Usage examples:
  python coa_graph_optimizer.py --entries ./coa_entries.jsonl --class-name Venomancer --preset stalker_dps --level 60 --max-ae 26 --max-te 25 --top 10
  python coa_graph_optimizer.py --entries ./coa_entries.jsonl --class-name Venomancer --preset stalker_dps --level 40 --max-ae 16 --max-te 15
  python coa_graph_optimizer.py --entries ./coa_entries.jsonl --class-name Venomancer --preset stalker_dps --export-graph venomancer_graph.json --export-cypher venomancer_graph.cypher
"""

from __future__ import annotations

import argparse
import dataclasses
import heapq
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


@dataclasses.dataclass(frozen=True)
class Node:
    entry_id: int
    spell_id: int | None
    name: str
    class_name: str
    tab_id: int
    tab_name: str
    entry_type: str
    essence_kind: str
    ae_cost: int
    te_cost: int
    required_tab_ae: int
    required_tab_te: int
    required_level: int
    max_rank: int
    row: int
    col: int
    node_type: str
    is_passive: bool
    is_starting_node: bool
    required_ids: tuple[int, ...]
    connected_node_ids: tuple[int, ...]
    tags: tuple[str, ...]
    damage_schools: tuple[str, ...]
    resources: tuple[str, ...]
    description_text: str

    @property
    def cost(self) -> tuple[int, int]:
        return (self.ae_cost, self.te_cost)

    @property
    def paid(self) -> bool:
        return self.ae_cost > 0 or self.te_cost > 0


@dataclasses.dataclass(frozen=True)
class State:
    selected: frozenset[int]
    ae_spent: int
    te_spent: int
    # Per-tab paid spend. This is what reqTabAE/reqTabTE gates usually refer to.
    tab_ae: tuple[tuple[int, int], ...]
    tab_te: tuple[tuple[int, int], ...]

    def tab_ae_map(self) -> dict[int, int]:
        return dict(self.tab_ae)

    def tab_te_map(self) -> dict[int, int]:
        return dict(self.tab_te)


PRESETS: dict[str, dict[str, Any]] = {
    # Heuristic for the Stalker Venomancer concept discussed in chat.
    # Adjust these weights after looking at combat logs.
    "stalker_dps": {
        "tab_weights": {
            "Stalking": 8.0,
            "Venom": 3.0,
            "Class": 1.0,
            "Vizier": 0.5,
            "Fortitude": -1.5,
        },
        "tag_weights": {
            "dot": 5.0,
            "proc": 4.0,
            "builder": 3.0,
            "spender": 3.5,
            "resource_management": 3.0,
            "cooldown": 2.5,
            "mobility": 0.75,
            "crowd_control": 0.5,
            "tank": -2.0,
            "heal": -0.75,
            "hot": -1.0,
            "summon": 1.0,
            "melee": 0.5,
            "ranged": 0.25,
            "aura": 1.0,
        },
        "school_weights": {
            "nature": 5.0,
            "shadow": 2.0,
            "arcane": 0.75,
            "physical": -0.25,
            "holy": -0.25,
            "fire": -0.25,
            "frost": -0.25,
            "fel": -0.25,
        },
        "resource_weights": {
            "Energy": 4.0,
            "Mana": -0.5,
            "Rage": -1.0,
        },
        "name_boosts": {
            "Brood Marks": 20.0,
            "Venom Fang": 15.0,
            "Widow's Kiss": 14.0,
            "Nerubian Sting": 14.0,
            "Facemelter": 14.0,
            "Noxious Empowerment": 13.0,
            "Cunning of the Nerub'ar": 11.0,
            "Brood Lord": 8.0,
            "Venomous Bite": 8.0,
            "Blistering Fangs": 7.0,
            "Contagion": 7.0,
            "Deadly Kiss": 7.0,
            "Nature Against Nature": 7.0,
            "Deadly Neurotoxins": 6.0,
            "Glory to Shadra": 6.0,
            "Virulent Resonance": 6.0,
            "Adrenal Venom": 5.0,
            "Blight Venom": 5.0,
            "Withering Venom": 5.0,
            "Rot": -2.0,
            "Fortitude": -4.0,
        },
        "desc_regex_boosts": {
            r"\bBrood Mark": 5.0,
            r"\bVenom Fang\b": 5.0,
            r"\bWidow": 4.0,
            r"\bNerubian Sting\b": 4.0,
            r"\bFacemelter\b": 4.0,
            r"\bEnergy\b": 3.0,
            r"\bhaste\b": 3.0,
            r"\bcritical strike|critically|critical damage\b": 2.0,
            r"\bNature damage\b": 2.0,
            r"\bShadow damage\b": 1.0,
            r"\bSpider Form\b": 3.0,
            r"\btank|threat|armor|block|parry|dodge\b": -3.0,
        },
        # Pairwise/small-set synergy bonuses. These are intentionally transparent and editable.
        "synergies": [
            (["Brood Marks", "Venom Fang"], 12.0, "core mark builder"),
            (["Brood Marks", "Facemelter"], 12.0, "core mark spender"),
            (["Venom Fang", "Widow's Kiss"], 8.0, "every third fang conversion"),
            (["Nerubian Sting", "Nature Against Nature"], 8.0, "sting amplifies Venom Fang/Widowmaker"),
            (["Facemelter", "Blistering Fangs"], 7.0, "5+ mark spender refund"),
            (["Noxious Empowerment", "Contagion"], 5.0, "burst/proc window"),
            (["Widow's Kiss", "Deadly Kiss"], 5.0, "crit damage package"),
            (["Cunning of the Nerub'ar", "Nerubian Sting"], 6.0, "extra sting stack package"),
        ],
    }
}


def load_nodes(entries_path: Path, class_name: str) -> dict[int, Node]:
    nodes: dict[int, Node] = {}
    with entries_path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = json.loads(line)
            if raw.get("class_name") != class_name:
                continue
            req_ids = tuple(int(x) for x in raw.get("required_ids", []) if int(x) != 0)
            con_ids = tuple(int(x) for x in raw.get("connected_node_ids", []) if int(x) != 0)
            node = Node(
                entry_id=int(raw["entry_id"]),
                spell_id=raw.get("spell_id"),
                name=raw.get("name", ""),
                class_name=raw.get("class_name", ""),
                tab_id=int(raw.get("tab_id", 0)),
                tab_name=raw.get("tab_name", ""),
                entry_type=raw.get("entry_type", ""),
                essence_kind=raw.get("essence_kind", ""),
                ae_cost=int(raw.get("ae_cost", 0) or 0),
                te_cost=int(raw.get("te_cost", 0) or 0),
                required_tab_ae=int(raw.get("required_tab_ae", 0) or 0),
                required_tab_te=int(raw.get("required_tab_te", 0) or 0),
                required_level=int(raw.get("required_level", 0) or 0),
                max_rank=int(raw.get("max_rank", 1) or 1),
                row=int(raw.get("row", 0) or 0),
                col=int(raw.get("col", 0) or 0),
                node_type=raw.get("node_type", ""),
                is_passive=bool(raw.get("is_passive", False)),
                is_starting_node=bool(raw.get("is_starting_node", False)),
                required_ids=req_ids,
                connected_node_ids=con_ids,
                tags=tuple(raw.get("tags", []) or []),
                damage_schools=tuple(raw.get("damage_schools", []) or []),
                resources=tuple(raw.get("resources", []) or []),
                description_text=raw.get("description_text", "") or "",
            )
            nodes[node.entry_id] = node

    # Drop edges to nodes outside this class, but warn via stdout later if desired.
    return nodes


def initial_state(nodes: dict[int, Node], level: int) -> State:
    """Auto-include free starting/passive prerequisites at or below level.

    In this CoA export, some required nodes cost 0 and function like automatically
    granted passives/forms/mechanics. This closure adds all zero-cost nodes whose
    required_ids are already satisfied. It does NOT add paid talents.
    """
    selected: set[int] = set()
    changed = True
    while changed:
        changed = False
        for node_id, n in nodes.items():
            if node_id in selected:
                continue
            if n.paid:
                continue
            if n.required_level > level:
                continue
            if all(req in selected or req not in nodes for req in n.required_ids):
                selected.add(node_id)
                changed = True

    return State(
        selected=frozenset(selected),
        ae_spent=0,
        te_spent=0,
        tab_ae=tuple(),
        tab_te=tuple(),
    )


def add_node_to_state(state: State, node: Node) -> State:
    tab_ae = state.tab_ae_map()
    tab_te = state.tab_te_map()
    tab_ae[node.tab_id] = tab_ae.get(node.tab_id, 0) + node.ae_cost
    tab_te[node.tab_id] = tab_te.get(node.tab_id, 0) + node.te_cost
    return State(
        selected=frozenset(set(state.selected) | {node.entry_id}),
        ae_spent=state.ae_spent + node.ae_cost,
        te_spent=state.te_spent + node.te_cost,
        tab_ae=tuple(sorted(tab_ae.items())),
        tab_te=tuple(sorted(tab_te.items())),
    )


def is_legal_add(
    state: State,
    node: Node,
    nodes: dict[int, Node],
    *,
    level: int,
    max_ae: int,
    max_te: int,
) -> bool:
    if node.entry_id in state.selected:
        return False
    if node.required_level > level:
        return False
    if state.ae_spent + node.ae_cost > max_ae:
        return False
    if state.te_spent + node.te_cost > max_te:
        return False

    tab_ae = state.tab_ae_map().get(node.tab_id, 0)
    tab_te = state.tab_te_map().get(node.tab_id, 0)
    if tab_ae < node.required_tab_ae:
        return False
    if tab_te < node.required_tab_te:
        return False

    # Hard prerequisites from the builder payload.
    # Missing req IDs are treated as external/auto to avoid false negatives,
    # but the current data should not have missing Venomancer reqs.
    if any((req in nodes and req not in state.selected) for req in node.required_ids):
        return False

    return True


def base_node_score(node: Node, preset: dict[str, Any]) -> float:
    s = 0.0
    s += preset.get("tab_weights", {}).get(node.tab_name, 0.0)
    s += sum(preset.get("tag_weights", {}).get(t, 0.0) for t in node.tags)
    s += sum(preset.get("school_weights", {}).get(d, 0.0) for d in node.damage_schools)
    s += sum(preset.get("resource_weights", {}).get(r, 0.0) for r in node.resources)

    # Active spend-square nodes usually matter more than minor passives.
    if node.node_type == "SpendSquare":
        s += 4.0
    if node.is_passive and node.paid:
        s += 1.0

    text = f"{node.name}\n{node.description_text}"
    for name, boost in preset.get("name_boosts", {}).items():
        if name.lower() in text.lower():
            s += float(boost)
    for pat, boost in preset.get("desc_regex_boosts", {}).items():
        if re.search(pat, text, flags=re.IGNORECASE):
            s += float(boost)

    # Prefer max-rank nodes slightly, but do not implement rank allocation yet.
    s += min(node.max_rank, 3) * 0.25
    return s


def state_score(state: State, nodes: dict[int, Node], preset: dict[str, Any]) -> tuple[float, list[str]]:
    selected_nodes = [nodes[i] for i in state.selected if i in nodes]
    score = sum(base_node_score(n, preset) for n in selected_nodes)
    notes: list[str] = []

    selected_text = "\n".join(n.name for n in selected_nodes)
    for names, bonus, reason in preset.get("synergies", []):
        if all(name in selected_text for name in names):
            score += float(bonus)
            notes.append(f"+{bonus:g} synergy: {reason} ({', '.join(names)})")

    # Small penalty for unspent points; it pushes complete builds above partial builds.
    score -= (1.0 * (state.ae_spent == 0))
    return score, notes


def beam_search(
    nodes: dict[int, Node],
    *,
    preset_name: str,
    level: int,
    max_ae: int,
    max_te: int,
    beam_width: int,
    branch_width: int,
    top: int,
) -> list[tuple[float, State, list[str]]]:
    preset = PRESETS[preset_name]
    start = initial_state(nodes, level)
    paid_nodes = [n for n in nodes.values() if n.paid and n.required_level <= level]
    node_scores = {n.entry_id: base_node_score(n, preset) for n in nodes.values()}

    def fast_state_score(st: State) -> float:
        # Fast additive score for beam pruning. Pairwise synergies are added in final scoring.
        return sum(node_scores.get(i, 0.0) for i in st.selected) + st.ae_spent * 0.01 + st.te_spent * 0.01

    beam: list[State] = [start]
    seen: set[State] = {start}
    best: dict[frozenset[int], State] = {start.selected: start}

    # Each paid node costs at least one AE or TE in this data, so this is enough steps.
    max_steps = max_ae + max_te
    for _ in range(max_steps):
        scored_candidates: list[tuple[float, State]] = []
        for st in beam:
            legal_nodes = [
                n for n in paid_nodes
                if is_legal_add(st, n, nodes, level=level, max_ae=max_ae, max_te=max_te)
            ]
            # Consider only the strongest local additions. This keeps the search interactive.
            legal_nodes.sort(key=lambda n: node_scores.get(n.entry_id, 0.0), reverse=True)
            for n in legal_nodes[:branch_width]:
                ns = add_node_to_state(st, n)
                if ns not in seen:
                    seen.add(ns)
                    best[ns.selected] = ns
                    scored_candidates.append((fast_state_score(ns), ns))

        if not scored_candidates:
            break

        # Keep the strongest frontier. nlargest avoids sorting huge candidate sets fully.
        beam = [st for _, st in heapq.nlargest(beam_width, scored_candidates, key=lambda x: x[0])]

    all_scored: list[tuple[float, State, list[str]]] = []
    for st in best.values():
        # Prefer builds that spend nearly all relevant budget, but don't discard AE-light TE builds.
        if st.ae_spent + st.te_spent < (max_ae + max_te) * 0.7:
            continue
        sc, notes = state_score(st, nodes, preset)
        sc -= 2.0 * ((max_ae - st.ae_spent) + (max_te - st.te_spent))
        all_scored.append((sc, st, notes))

    all_scored.sort(key=lambda x: x[0], reverse=True)
    return all_scored[:top]


def explain_state(state: State, nodes: dict[int, Node], preset: dict[str, Any]) -> dict[str, Any]:
    paid_nodes = [nodes[i] for i in state.selected if i in nodes and nodes[i].paid]
    free_nodes = [nodes[i] for i in state.selected if i in nodes and not nodes[i].paid]
    paid_nodes.sort(key=lambda n: (n.tab_name, n.required_tab_ae, n.required_tab_te, n.row, n.col, n.name))

    by_tab: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in paid_nodes:
        by_tab[n.tab_name].append({
            "id": n.entry_id,
            "name": n.name,
            "cost": {"AE": n.ae_cost, "TE": n.te_cost},
            "requires": list(n.required_ids),
            "req_tab": {"AE": n.required_tab_ae, "TE": n.required_tab_te},
            "level": n.required_level,
            "tags": list(n.tags),
            "schools": list(n.damage_schools),
            "score": round(base_node_score(n, preset), 2),
        })

    return {
        "spent": {"AE": state.ae_spent, "TE": state.te_spent},
        "paid_count": len(paid_nodes),
        "auto_free_nodes": sorted([n.name for n in free_nodes]),
        "paid_by_tab": by_tab,
    }


def export_graph(nodes: dict[int, Node], path: Path) -> None:
    payload = {
        "nodes": [
            dataclasses.asdict(n)
            for n in sorted(nodes.values(), key=lambda x: x.entry_id)
        ],
        "edges": [],
    }
    edges = payload["edges"]
    for n in nodes.values():
        for req in n.required_ids:
            if req in nodes:
                edges.append({"source": req, "target": n.entry_id, "type": "REQUIRES"})
        for con in n.connected_node_ids:
            if con in nodes:
                edges.append({"source": n.entry_id, "target": con, "type": "CONNECTED_TO"})
        if n.required_tab_ae:
            edges.append({"source": f"tab:{n.tab_id}:AE:{n.required_tab_ae}", "target": n.entry_id, "type": "UNLOCKED_BY_TAB_AE"})
        if n.required_tab_te:
            edges.append({"source": f"tab:{n.tab_id}:TE:{n.required_tab_te}", "target": n.entry_id, "type": "UNLOCKED_BY_TAB_TE"})
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def cypher_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def export_cypher(nodes: dict[int, Node], path: Path) -> None:
    lines: list[str] = []
    for n in sorted(nodes.values(), key=lambda x: x.entry_id):
        lines.append(
            "MERGE (n:Talent {entry_id: %d}) "
            "SET n.name='%s', n.tab='%s', n.kind='%s', n.ae_cost=%d, n.te_cost=%d, "
            "n.required_level=%d, n.required_tab_ae=%d, n.required_tab_te=%d;"
            % (
                n.entry_id,
                cypher_escape(n.name),
                cypher_escape(n.tab_name),
                cypher_escape(n.essence_kind),
                n.ae_cost,
                n.te_cost,
                n.required_level,
                n.required_tab_ae,
                n.required_tab_te,
            )
        )
    for n in sorted(nodes.values(), key=lambda x: x.entry_id):
        for req in n.required_ids:
            if req in nodes:
                lines.append(
                    "MATCH (a:Talent {entry_id: %d}), (b:Talent {entry_id: %d}) "
                    "MERGE (a)-[:REQUIRES]->(b);"
                    % (n.entry_id, req)
                )
        for con in n.connected_node_ids:
            if con in nodes:
                lines.append(
                    "MATCH (a:Talent {entry_id: %d}), (b:Talent {entry_id: %d}) "
                    "MERGE (a)-[:CONNECTED_TO]->(b);"
                    % (n.entry_id, con)
                )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_dataset_summary(nodes: dict[int, Node]) -> None:
    print(f"Loaded {len(nodes)} nodes.")
    print("By essence kind:", dict(Counter(n.essence_kind for n in nodes.values())))
    print("By tab:", dict(Counter(n.tab_name for n in nodes.values())))
    print("Required levels:", dict(sorted(Counter(n.required_level for n in nodes.values()).items())))
    print("Required tab TE:", dict(sorted(Counter(n.required_tab_te for n in nodes.values()).items())))
    print("Required tab AE:", dict(sorted(Counter(n.required_tab_ae for n in nodes.values()).items())))
    print("Hard required-id edges:", sum(len(n.required_ids) for n in nodes.values()))
    print("Connected-node edges:", sum(len(n.connected_node_ids) for n in nodes.values()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", required=True, type=Path, help="Path to coa_entries.jsonl")
    ap.add_argument("--class-name", default="Venomancer")
    ap.add_argument("--preset", default="stalker_dps", choices=sorted(PRESETS.keys()))
    ap.add_argument("--level", type=int, default=60)
    ap.add_argument("--max-ae", type=int, default=26)
    ap.add_argument("--max-te", type=int, default=25)
    ap.add_argument("--beam-width", type=int, default=6)
    ap.add_argument("--branch-width", type=int, default=25, help="Per-state cap on next nodes considered during beam search.")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--json", action="store_true", help="Print full result JSON instead of compact text.")
    ap.add_argument("--export-graph", type=Path)
    ap.add_argument("--export-cypher", type=Path)
    args = ap.parse_args()

    nodes = load_nodes(args.entries, args.class_name)
    if not nodes:
        raise SystemExit(f"No nodes loaded for class {args.class_name!r}")

    if args.summary:
        print_dataset_summary(nodes)

    if args.export_graph:
        export_graph(nodes, args.export_graph)
        print(f"Wrote graph JSON: {args.export_graph}")

    if args.export_cypher:
        export_cypher(nodes, args.export_cypher)
        print(f"Wrote Cypher: {args.export_cypher}")

    results = beam_search(
        nodes,
        preset_name=args.preset,
        level=args.level,
        max_ae=args.max_ae,
        max_te=args.max_te,
        beam_width=args.beam_width,
        branch_width=args.branch_width,
        top=args.top,
    )

    if args.json:
        out = []
        preset = PRESETS[args.preset]
        for score, st, notes in results:
            item = explain_state(st, nodes, preset)
            item["score"] = round(score, 2)
            item["synergy_notes"] = notes
            out.append(item)
        print(json.dumps(out, indent=2))
        return

    print(f"\nTop {len(results)} {args.class_name} builds for preset={args.preset}, level={args.level}, AE={args.max_ae}, TE={args.max_te}")
    preset = PRESETS[args.preset]
    for rank, (score, st, notes) in enumerate(results, start=1):
        print("=" * 88)
        print(f"#{rank} score={score:.2f} spent AE={st.ae_spent}/{args.max_ae}, TE={st.te_spent}/{args.max_te}")
        exp = explain_state(st, nodes, preset)
        for tab, ns in exp["paid_by_tab"].items():
            print(f"\n[{tab}]")
            for n in ns:
                print(f"  - {n['name']} (id={n['id']}, cost AE={n['cost']['AE']} TE={n['cost']['TE']}, score={n['score']})")
        if notes:
            print("\nSynergy notes:")
            for note in notes:
                print(f"  {note}")


if __name__ == "__main__":
    main()
