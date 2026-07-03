#!/usr/bin/env python3
"""
coa_optimizer_extensible.py

Extensible build/rotation optimization scaffold for Project Ascension Conquest of Azeroth.

Design goals:
- Keep scraping/extraction/normalization outside this file. This script consumes the normalized
  coa_entries.jsonl produced by export-coa-normalized.mjs.
- Support any CoA class/spec by keeping scoring strategies data-driven and pluggable.
- Separate build legality, scoring, search, rotation generation, graph export, and log ingestion.
- Allow empirical data from 3.3.5 combat logs or a custom addon JSON export to become the
  strongest source for weights over time.

Typical usage:
  python coa_optimizer_extensible.py optimize \
    --entries ./dist/coa_entries.jsonl \
    --class-name Venomancer \
    --profile stalker \
    --encounter single_target \
    --level 60 --max-ae 26 --max-te 25 --top 10

  python coa_optimizer_extensible.py optimize \
    --entries ./dist/coa_entries.jsonl \
    --class-name Venomancer \
    --profile stalker \
    --encounter aoe \
    --json

  python coa_optimizer_extensible.py rotation \
    --entries ./dist/coa_entries.jsonl \
    --class-name Venomancer \
    --profile stalker \
    --encounter single_target \
    --selected-names "Venom Fang" "Nerubian Sting" "Facemelter" "Noxious Empowerment"

  python coa_optimizer_extensible.py parse-log --combat-log ./Logs/WoWCombatLog.txt --player "Yourname"

  python coa_optimizer_extensible.py graph \
    --entries ./dist/coa_entries.jsonl --class-name Venomancer \
    --export-graph venomancer_graph.json --export-cypher venomancer_graph.cypher

Notes:
- This is not a full combat simulator yet. It is a build graph + heuristic/log-informed optimizer.
- Combat logs can calibrate spell weights, uptime, proc rates, and target-count assumptions.
- The long-term architecture should split this file into a package once the interfaces stabilize.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import heapq
import json
import math
import re
import statistics
import sys
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol

EncounterType = Literal["single_target", "aoe", "cleave", "solo"]


# -----------------------------
# Domain model / DTOs
# -----------------------------

@dataclasses.dataclass(frozen=True)
class TalentNode:
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
    raw: dict[str, Any] = dataclasses.field(default_factory=dict, compare=False, hash=False)

    @property
    def paid(self) -> bool:
        return self.ae_cost > 0 or self.te_cost > 0

    @property
    def text_blob(self) -> str:
        return f"{self.name}\n{self.description_text}"


@dataclasses.dataclass(frozen=True)
class BuildState:
    selected: frozenset[int]
    ae_spent: int
    te_spent: int
    tab_ae: tuple[tuple[int, int], ...]
    tab_te: tuple[tuple[int, int], ...]

    def tab_ae_map(self) -> dict[int, int]:
        return dict(self.tab_ae)

    def tab_te_map(self) -> dict[int, int]:
        return dict(self.tab_te)


@dataclasses.dataclass(frozen=True)
class SearchConfig:
    level: int = 60
    max_ae: int = 26
    max_te: int = 25
    beam_width: int = 10
    branch_width: int = 40
    top: int = 10
    require_budget_fraction: float = 0.70


@dataclasses.dataclass
class ScoreBreakdown:
    score: float
    reasons: list[str]


@dataclasses.dataclass
class CombatMetrics:
    player: str | None
    total_damage: int = 0
    active_time: float = 0.0
    event_count: int = 0
    casts_by_spell: Counter[str] = dataclasses.field(default_factory=Counter)
    damage_by_spell: Counter[str] = dataclasses.field(default_factory=Counter)
    crits_by_spell: Counter[str] = dataclasses.field(default_factory=Counter)
    hits_by_spell: Counter[str] = dataclasses.field(default_factory=Counter)
    aura_uptime_events: Counter[str] = dataclasses.field(default_factory=Counter)
    target_hits_by_spell: defaultdict[str, Counter[str]] = dataclasses.field(default_factory=lambda: defaultdict(Counter))

    def dps(self) -> float:
        return self.total_damage / self.active_time if self.active_time > 0 else 0.0

    def spell_damage_share(self) -> dict[str, float]:
        if self.total_damage <= 0:
            return {}
        return {spell: dmg / self.total_damage for spell, dmg in self.damage_by_spell.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "total_damage": self.total_damage,
            "active_time": round(self.active_time, 3),
            "dps": round(self.dps(), 2),
            "event_count": self.event_count,
            "casts_by_spell": dict(self.casts_by_spell.most_common()),
            "damage_by_spell": dict(self.damage_by_spell.most_common()),
            "damage_share_by_spell": {k: round(v, 4) for k, v in self.spell_damage_share().items()},
            "crits_by_spell": dict(self.crits_by_spell.most_common()),
            "hits_by_spell": dict(self.hits_by_spell.most_common()),
            "aura_events_by_spell": dict(self.aura_uptime_events.most_common()),
            "unique_targets_by_spell": {k: len(v) for k, v in self.target_hits_by_spell.items()},
        }


# -----------------------------
# Repository / normalization adapter
# -----------------------------

class TalentRepository:
    """Facade over normalized CoA entry data.

    The scraper/extractor scripts should own the web-specific pieces. This repository only knows
    how to load the normalized JSONL schema.
    """

    def __init__(self, entries_path: Path):
        self.entries_path = entries_path
        self._all_nodes: list[TalentNode] | None = None

    def load_all(self) -> list[TalentNode]:
        if self._all_nodes is not None:
            return self._all_nodes
        nodes: list[TalentNode] = []
        with self.entries_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {self.entries_path}:{line_no}: {exc}") from exc
                nodes.append(node_from_raw(raw))
        self._all_nodes = nodes
        return nodes

    def by_class(self, class_name: str) -> dict[int, TalentNode]:
        out = {n.entry_id: n for n in self.load_all() if n.class_name == class_name}
        if not out:
            known = sorted({n.class_name for n in self.load_all() if n.class_name})
            raise SystemExit(f"No nodes loaded for class {class_name!r}. Known classes: {', '.join(known)}")
        return out

    def class_names(self) -> list[str]:
        return sorted({n.class_name for n in self.load_all() if n.class_name})


def as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        if isinstance(value, str) and not value.strip():
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def int_tuple(values: Iterable[Any] | None) -> tuple[int, ...]:
    out: list[int] = []
    for v in values or []:
        n = as_int(v, 0)
        if n:
            out.append(n)
    return tuple(out)


def node_from_raw(raw: dict[str, Any]) -> TalentNode:
    return TalentNode(
        entry_id=as_int(raw.get("entry_id")),
        spell_id=as_int(raw.get("spell_id"), 0) or None,
        name=raw.get("name") or "",
        class_name=raw.get("class_name") or "",
        tab_id=as_int(raw.get("tab_id")),
        tab_name=raw.get("tab_name") or "",
        entry_type=raw.get("entry_type") or "",
        essence_kind=raw.get("essence_kind") or "",
        ae_cost=as_int(raw.get("ae_cost")),
        te_cost=as_int(raw.get("te_cost")),
        required_tab_ae=as_int(raw.get("required_tab_ae")),
        required_tab_te=as_int(raw.get("required_tab_te")),
        required_level=as_int(raw.get("required_level")),
        max_rank=max(1, as_int(raw.get("max_rank"), 1)),
        row=as_int(raw.get("row")),
        col=as_int(raw.get("col")),
        node_type=raw.get("node_type") or "",
        is_passive=bool(raw.get("is_passive")),
        is_starting_node=bool(raw.get("is_starting_node")),
        required_ids=int_tuple(raw.get("required_ids")),
        connected_node_ids=int_tuple(raw.get("connected_node_ids")),
        tags=tuple(raw.get("tags") or []),
        damage_schools=tuple(raw.get("damage_schools") or []),
        resources=tuple(raw.get("resources") or []),
        description_text=raw.get("description_text") or "",
        raw=raw,
    )


# -----------------------------
# Build legality service
# -----------------------------

class BuildRules:
    """Service/facade responsible for CoA tree legality.

    This should remain deterministic and independent from scoring. If CoA builder rules change,
    the change should happen here, not inside a scoring strategy.
    """

    def __init__(self, nodes: dict[int, TalentNode], config: SearchConfig):
        self.nodes = nodes
        self.config = config

    def initial_state(self) -> BuildState:
        selected: set[int] = set()
        changed = True
        while changed:
            changed = False
            for node_id, n in self.nodes.items():
                if node_id in selected or n.paid or n.required_level > self.config.level:
                    continue
                if all(req in selected or req not in self.nodes for req in n.required_ids):
                    selected.add(node_id)
                    changed = True
        return BuildState(frozenset(selected), 0, 0, tuple(), tuple())

    def is_legal_add(self, state: BuildState, node: TalentNode) -> bool:
        if node.entry_id in state.selected:
            return False
        if node.required_level > self.config.level:
            return False
        if state.ae_spent + node.ae_cost > self.config.max_ae:
            return False
        if state.te_spent + node.te_cost > self.config.max_te:
            return False

        tab_ae = state.tab_ae_map().get(node.tab_id, 0)
        tab_te = state.tab_te_map().get(node.tab_id, 0)
        if tab_ae < node.required_tab_ae or tab_te < node.required_tab_te:
            return False

        if any(req in self.nodes and req not in state.selected for req in node.required_ids):
            return False
        return True

    def add_node(self, state: BuildState, node: TalentNode) -> BuildState:
        tab_ae = state.tab_ae_map()
        tab_te = state.tab_te_map()
        tab_ae[node.tab_id] = tab_ae.get(node.tab_id, 0) + node.ae_cost
        tab_te[node.tab_id] = tab_te.get(node.tab_id, 0) + node.te_cost
        return BuildState(
            selected=frozenset(set(state.selected) | {node.entry_id}),
            ae_spent=state.ae_spent + node.ae_cost,
            te_spent=state.te_spent + node.te_cost,
            tab_ae=tuple(sorted(tab_ae.items())),
            tab_te=tuple(sorted(tab_te.items())),
        )


# -----------------------------
# Scoring Strategy pattern
# -----------------------------

class ScoringStrategy(ABC):
    name: str

    @abstractmethod
    def node_score(self, node: TalentNode) -> ScoreBreakdown:
        raise NotImplementedError

    @abstractmethod
    def state_score(self, state: BuildState, nodes: dict[int, TalentNode]) -> ScoreBreakdown:
        raise NotImplementedError


@dataclasses.dataclass
class WeightProfile:
    name: str
    encounter: EncounterType
    tab_weights: dict[str, float]
    tag_weights: dict[str, float]
    school_weights: dict[str, float]
    resource_weights: dict[str, float]
    name_boosts: dict[str, float]
    desc_regex_boosts: dict[str, float]
    synergies: list[tuple[list[str], float, str]]
    anti_synergies: list[tuple[list[str], float, str]] = dataclasses.field(default_factory=list)
    aoe_target_hint: int = 1


class HeuristicScoringStrategy(ScoringStrategy):
    def __init__(self, profile: WeightProfile, metrics: CombatMetrics | None = None, empirical_blend: float = 0.0):
        self.profile = profile
        self.metrics = metrics
        self.empirical_blend = max(0.0, min(1.0, empirical_blend))
        self.name = profile.name
        self._empirical_shares = metrics.spell_damage_share() if metrics else {}

    def node_score(self, node: TalentNode) -> ScoreBreakdown:
        score = 0.0
        reasons: list[str] = []

        def add(amount: float, reason: str) -> None:
            nonlocal score
            if amount:
                score += amount
                reasons.append(f"{amount:+.2f} {reason}")

        add(self.profile.tab_weights.get(node.tab_name, 0.0), f"tab:{node.tab_name}")
        for t in node.tags:
            add(self.profile.tag_weights.get(t, 0.0), f"tag:{t}")
        for school in node.damage_schools:
            add(self.profile.school_weights.get(school, 0.0), f"school:{school}")
        for resource in node.resources:
            add(self.profile.resource_weights.get(resource, 0.0), f"resource:{resource}")

        if node.node_type == "SpendSquare":
            add(4.0, "active/square node")
        if node.is_passive and node.paid:
            add(0.75, "paid passive")

        text = node.text_blob.lower()
        for needle, boost in self.profile.name_boosts.items():
            if needle.lower() in text:
                add(float(boost), f"name/text boost:{needle}")
        for pat, boost in self.profile.desc_regex_boosts.items():
            if re.search(pat, node.text_blob, flags=re.IGNORECASE):
                add(float(boost), f"regex:{pat}")

        # Empirical weights: if a node name appears in observed damage/casts, blend its actual share in.
        if self._empirical_shares and node.name in self._empirical_shares:
            # 25 points for a spell doing 25% of observed damage before blend scaling.
            empirical = self._empirical_shares[node.name] * 100.0
            add(empirical * self.empirical_blend, f"empirical damage share:{node.name}")

        # Rank is a hint, not full allocation. Keep small to avoid overfitting parser artifacts.
        add(min(node.max_rank, 3) * 0.20, "rank hint")
        return ScoreBreakdown(score, reasons)

    def state_score(self, state: BuildState, nodes: dict[int, TalentNode]) -> ScoreBreakdown:
        selected_nodes = [nodes[i] for i in state.selected if i in nodes]
        score = 0.0
        reasons: list[str] = []
        for n in selected_nodes:
            ns = self.node_score(n)
            score += ns.score

        selected_text = "\n".join(n.name for n in selected_nodes)
        for names, bonus, reason in self.profile.synergies:
            if all(name in selected_text for name in names):
                score += bonus
                reasons.append(f"{bonus:+.2f} synergy: {reason} ({', '.join(names)})")
        for names, penalty, reason in self.profile.anti_synergies:
            if all(name in selected_text for name in names):
                score += penalty
                reasons.append(f"{penalty:+.2f} anti-synergy: {reason} ({', '.join(names)})")

        # Encounter-specific budget nudges.
        if self.profile.encounter == "aoe":
            aoe_words = re.compile(r"\bnearby|up to \d+|all enemies|cleave|area|enemies\b", re.I)
            aoe_count = sum(1 for n in selected_nodes if aoe_words.search(n.description_text))
            score += min(aoe_count, 8) * 2.0
            if aoe_count:
                reasons.append(f"+{min(aoe_count, 8) * 2.0:.2f} AoE text coverage ({aoe_count} nodes)")
        else:
            # Single-target prefers fewer tank/heal-only dilutions.
            tank_heal = sum(1 for n in selected_nodes if "tank" in n.tags or "hot" in n.tags)
            if tank_heal:
                score -= tank_heal * 1.25
                reasons.append(f"-{tank_heal * 1.25:.2f} single-target dilution ({tank_heal} tank/hot nodes)")

        return ScoreBreakdown(score, reasons)


# -----------------------------
# Weight profile factory
# -----------------------------

def generic_profile(class_name: str, encounter: EncounterType) -> WeightProfile:
    # Safe default for any class/spec; it favors active DPS nodes and avoids tanks/heals for DPS searches.
    tag_weights = {
        "dot": 3.0, "proc": 3.0, "builder": 2.5, "spender": 2.5,
        "resource_management": 2.0, "cooldown": 2.0, "execute": 2.0,
        "melee": 0.75, "ranged": 0.75, "aura": 1.0, "summon": 1.5,
        "mobility": 0.4, "crowd_control": 0.25, "heal": -0.5, "hot": -0.5, "tank": -1.25,
    }
    if encounter == "aoe":
        tag_weights.update({"dot": 3.5, "summon": 2.0, "aura": 1.5, "crowd_control": 0.75})
    return WeightProfile(
        name=f"generic_{class_name}_{encounter}",
        encounter=encounter,
        tab_weights={"Class": 1.0},
        tag_weights=tag_weights,
        school_weights={k: 0.75 for k in ["physical", "fire", "frost", "shadow", "holy", "nature", "arcane", "fel"]},
        resource_weights={"Energy": 1.0, "Mana": 0.5, "Rage": 0.5, "Insanity": 0.5, "Felfury": 0.5, "Static": 0.5, "Heat": 0.5, "Advantage": 0.5},
        name_boosts={},
        desc_regex_boosts={
            r"\bcritical strike|critically|critical damage\b": 1.25,
            r"\bhaste\b": 1.25,
            r"\bcooldown\b": 1.0,
            r"\bperiodic damage|damage over\b": 1.5,
            r"\bnearby|up to \d+|all enemies|cleave\b": 2.0 if encounter == "aoe" else 0.25,
        },
        synergies=[],
        aoe_target_hint=5 if encounter == "aoe" else 1,
    )


def stalker_profile(encounter: EncounterType) -> WeightProfile:
    is_aoe = encounter == "aoe"
    tag_weights = {
        "dot": 5.0, "proc": 4.0, "builder": 3.25, "spender": 3.75,
        "resource_management": 3.25, "cooldown": 2.75, "execute": 2.0,
        "summon": 1.25, "aura": 1.0, "melee": 0.5, "ranged": 0.25,
        "mobility": 0.75, "crowd_control": 0.5, "tank": -2.25, "heal": -0.75, "hot": -1.0,
    }
    name_boosts = {
        "Brood Marks": 20.0,
        "Venom Fang": 15.0,
        "Widow's Kiss": 14.0,
        "Nerubian Sting": 14.0,
        "Facemelter": 14.0,
        "Noxious Empowerment": 13.0,
        "Cunning of the Nerub'ar": 11.0,
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
    }
    synergies = [
        (["Brood Marks", "Venom Fang"], 12.0, "core mark builder"),
        (["Brood Marks", "Facemelter"], 12.0, "core mark spender"),
        (["Venom Fang", "Widow's Kiss"], 8.0, "every third fang conversion"),
        (["Nerubian Sting", "Nature Against Nature"], 8.0, "sting amplifies poison loop"),
        (["Facemelter", "Blistering Fangs"], 7.0, "high-mark spender refund"),
        (["Noxious Empowerment", "Contagion"], 5.0, "burst/proc window"),
        (["Widow's Kiss", "Deadly Kiss"], 5.0, "crit damage package"),
        (["Cunning of the Nerub'ar", "Nerubian Sting"], 6.0, "extra sting stack package"),
    ]
    if is_aoe:
        tag_weights.update({"summon": 2.5, "crowd_control": 1.0, "dot": 5.75})
        name_boosts.update({"Brood Lord": 13.0, "Contagion": 11.0, "Facemelter": 12.0})
        synergies.extend([
            (["Brood Lord", "Facemelter"], 9.0, "web/mark spender AoE package"),
            (["Contagion", "Withering Venom"], 6.0, "periodic-damage spread window"),
        ])
    else:
        name_boosts.update({"Brood Lord": 5.0})

    return WeightProfile(
        name=f"stalker_{encounter}",
        encounter=encounter,
        tab_weights={"Stalking": 8.0, "Venom": 3.0, "Class": 1.0, "Vizier": 0.5, "Fortitude": -1.75},
        tag_weights=tag_weights,
        school_weights={"nature": 5.0, "shadow": 2.0, "arcane": 0.75, "physical": -0.25, "holy": -0.25, "fire": -0.25, "frost": -0.25, "fel": -0.25},
        resource_weights={"Energy": 4.0, "Mana": -0.5, "Rage": -1.0},
        name_boosts=name_boosts,
        desc_regex_boosts={
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
            r"\bnearby|up to \d+|all enemies|enemies within\b": 4.0 if is_aoe else 0.5,
            r"\btank|threat|armor|block|parry|dodge\b": -3.0,
        },
        synergies=synergies,
        anti_synergies=[(["Cunning of the Nerub'ar", "Brood Lord"], -5.0, "likely competing Spider Form packages; test both separately")],
        aoe_target_hint=5 if is_aoe else 1,
    )


def make_profile(class_name: str, profile_name: str, encounter: EncounterType) -> WeightProfile:
    if profile_name == "stalker" and class_name == "Venomancer":
        return stalker_profile(encounter)
    return generic_profile(class_name, encounter)


# -----------------------------
# Optimizer service
# -----------------------------

class BuildOptimizer:
    def __init__(self, nodes: dict[int, TalentNode], rules: BuildRules, scorer: ScoringStrategy):
        self.nodes = nodes
        self.rules = rules
        self.scorer = scorer
        self._node_scores = {node_id: scorer.node_score(n).score for node_id, n in nodes.items()}

    def optimize(self, config: SearchConfig) -> list[tuple[float, BuildState, list[str]]]:
        start = self.rules.initial_state()
        paid_nodes = [n for n in self.nodes.values() if n.paid and n.required_level <= config.level]

        def fast_state_score(st: BuildState) -> float:
            return sum(self._node_scores.get(i, 0.0) for i in st.selected) + st.ae_spent * 0.01 + st.te_spent * 0.01

        beam = [start]
        seen: set[BuildState] = {start}
        best: dict[frozenset[int], BuildState] = {start.selected: start}
        max_steps = config.max_ae + config.max_te

        for _ in range(max_steps):
            candidates: list[tuple[float, BuildState]] = []
            for st in beam:
                legal_nodes = [n for n in paid_nodes if self.rules.is_legal_add(st, n)]
                legal_nodes.sort(key=lambda n: self._node_scores.get(n.entry_id, 0.0), reverse=True)
                for node in legal_nodes[: config.branch_width]:
                    ns = self.rules.add_node(st, node)
                    if ns not in seen:
                        seen.add(ns)
                        best[ns.selected] = ns
                        candidates.append((fast_state_score(ns), ns))
            if not candidates:
                break
            beam = [st for _, st in heapq.nlargest(config.beam_width, candidates, key=lambda x: x[0])]

        scored: list[tuple[float, BuildState, list[str]]] = []
        for st in best.values():
            if st.ae_spent + st.te_spent < (config.max_ae + config.max_te) * config.require_budget_fraction:
                continue
            breakdown = self.scorer.state_score(st, self.nodes)
            # Reward spending budgets, but allow asymmetric AE/TE builds.
            unspent = (config.max_ae - st.ae_spent) + (config.max_te - st.te_spent)
            total = breakdown.score - unspent * 2.0
            scored.append((total, st, breakdown.reasons))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[: config.top]


# -----------------------------
# Rotation Strategy pattern
# -----------------------------

@dataclasses.dataclass
class APLRule:
    action: str
    condition: str = ""
    note: str = ""

    def simc_like(self) -> str:
        suffix = f",if={self.condition}" if self.condition else ""
        comment = f"  # {self.note}" if self.note else ""
        return f"actions+=/{slugify_action(self.action)}{suffix}{comment}"


class RotationStrategy(ABC):
    @abstractmethod
    def generate(self, selected: list[TalentNode]) -> list[APLRule]:
        raise NotImplementedError


class GenericRotationStrategy(RotationStrategy):
    def __init__(self, encounter: EncounterType):
        self.encounter = encounter

    def generate(self, selected: list[TalentNode]) -> list[APLRule]:
        by_name = {n.name: n for n in selected}
        cooldowns = [n for n in selected if "cooldown" in n.tags and not n.is_passive]
        dots = [n for n in selected if "dot" in n.tags and not n.is_passive]
        builders = [n for n in selected if "builder" in n.tags and not n.is_passive]
        spenders = [n for n in selected if "spender" in n.tags and not n.is_passive]

        rules = [APLRule("auto_attack", note="keep baseline combat active if relevant")]
        for n in sorted(dots, key=lambda x: (x.tab_name != "Class", x.name)):
            rules.append(APLRule(n.name, condition=f"dot.{slugify_condition(n.name)}.remains<gcd", note="maintain DoT/debuff uptime"))
        for n in sorted(cooldowns, key=lambda x: x.name):
            rules.append(APLRule(n.name, condition="cooldown.ready", note="generic cooldown placeholder; refine with logs"))
        if self.encounter == "aoe":
            aoe_nodes = [n for n in selected if re.search(r"\bnearby|up to \d+|all enemies|cleave|enemies\b", n.description_text, re.I)]
            for n in sorted(aoe_nodes, key=lambda x: x.name):
                rules.append(APLRule(n.name, condition="active_enemies>=3", note="AoE/cleave text detected"))
        for n in sorted(spenders, key=lambda x: x.name):
            rules.append(APLRule(n.name, condition="resource>=spender_threshold", note="spender threshold placeholder"))
        for n in sorted(builders, key=lambda x: x.name):
            rules.append(APLRule(n.name, condition="resource.deficit>0", note="builder/filler"))
        return dedupe_apl(rules)


class StalkerRotationStrategy(RotationStrategy):
    def __init__(self, encounter: EncounterType):
        self.encounter = encounter

    def generate(self, selected: list[TalentNode]) -> list[APLRule]:
        names = {n.name for n in selected}
        rules: list[APLRule] = [
            APLRule("snapshot_stats", note="capture starting stats if your sim runner supports it"),
            APLRule("auto_attack", note="only meaningful if poisons/weapon procs matter in CoA"),
        ]
        def has(name: str) -> bool:
            return name in names or any(name.lower() in n.lower() for n in names)
        def add(name: str, condition: str = "", note: str = "") -> None:
            if has(name):
                rules.append(APLRule(name, condition, note))

        add("Adrenal Venom", "!buff.adrenal_venom.up", "pre-buff / venom package")
        add("Blight Venom", "!buff.blight_venom.up", "pre-buff / venom package")
        add("Spider Form", "!buff.spider_form.up", "form maintenance")
        add("Withering Venom", "dot.withering_venom.remains<gcd", "maintain ramping poison DoT")
        add("Nerubian Sting", "debuff.nerubian_sting.stack<max_stack|debuff.nerubian_sting.remains<gcd", "stack/maintain sting")
        add("Venom Fang", "brood_marks<5&energy>=cost.venom_fang", "primary Brood Mark builder")
        add("Widow's Kiss", "buff.widows_kiss.ready|brood_marks<5", "generated/converted fang event placeholder")
        add("Noxious Empowerment", "brood_marks>=4&dot.withering_venom.up&energy.deficit>=30", "burst/resource window")
        if self.encounter == "aoe":
            add("Contagion", "active_enemies>=3&dot.withering_venom.up", "AoE periodic-damage window")
            add("Brood Lord", "active_enemies>=3", "AoE/utility package if selected")
            add("Facemelter", "active_enemies>=3&brood_marks>=5", "AoE spender after setup")
        else:
            add("Facemelter", "brood_marks>=5", "single-target mark spender")
        add("Widowmaker", "target.health.pct<35", "execute if selected/talented")
        add("Venom Fang", "energy>=cost.venom_fang", "default filler/builder")
        return dedupe_apl(rules)


def make_rotation_strategy(class_name: str, profile_name: str, encounter: EncounterType) -> RotationStrategy:
    if class_name == "Venomancer" and profile_name == "stalker":
        return StalkerRotationStrategy(encounter)
    return GenericRotationStrategy(encounter)


def slugify_action(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower().replace("'", "")).strip("_")


def slugify_condition(name: str) -> str:
    return slugify_action(name)


def dedupe_apl(rules: list[APLRule]) -> list[APLRule]:
    seen: set[tuple[str, str]] = set()
    out: list[APLRule] = []
    for r in rules:
        key = (r.action, r.condition)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# -----------------------------
# Combat log / addon adapters
# -----------------------------

class CombatLogAdapter(ABC):
    @abstractmethod
    def parse(self) -> CombatMetrics:
        raise NotImplementedError


class Wow335CombatLogAdapter(CombatLogAdapter):
    """Best-effort parser for WoWCombatLog.txt-era comma-separated events.

    It handles the common damage/cast/aura events needed for early optimizer calibration.
    Vanilla/WotLK private-server logs can vary; keep this tolerant and inspect unknown rows.
    """

    DAMAGE_EVENTS = {"SPELL_DAMAGE", "SPELL_PERIODIC_DAMAGE", "RANGE_DAMAGE", "SWING_DAMAGE", "DAMAGE_SHIELD", "DAMAGE_SPLIT"}
    CAST_EVENTS = {"SPELL_CAST_SUCCESS", "SPELL_CAST_START"}
    AURA_EVENTS = {"SPELL_AURA_APPLIED", "SPELL_AURA_REMOVED", "SPELL_AURA_REFRESH", "SPELL_AURA_APPLIED_DOSE", "SPELL_AURA_REMOVED_DOSE"}

    def __init__(self, path: Path, player: str | None = None):
        self.path = path
        self.player = player

    def parse(self) -> CombatMetrics:
        metrics = CombatMetrics(player=self.player)
        first_ts: float | None = None
        last_ts: float | None = None

        with self.path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                row = parse_wow_log_line(line)
                if not row:
                    continue
                ts, event, fields = row
                source_name = fields.get("sourceName")
                if self.player and source_name and strip_quotes(source_name) != self.player:
                    continue
                if self.player and not source_name:
                    # SWING_DAMAGE sometimes still has source; skip if ambiguous.
                    continue

                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)
                metrics.event_count += 1

                spell_name = fields.get("spellName") or ("Swing" if event == "SWING_DAMAGE" else "Unknown")
                spell_name = strip_quotes(spell_name)
                dest_name = strip_quotes(fields.get("destName") or "Unknown")

                if event in self.CAST_EVENTS:
                    metrics.casts_by_spell[spell_name] += 1
                elif event in self.AURA_EVENTS:
                    metrics.aura_uptime_events[spell_name] += 1
                elif event in self.DAMAGE_EVENTS:
                    amount = as_int(fields.get("amount"), 0)
                    overkill = max(0, as_int(fields.get("overkill"), 0))
                    amount = max(0, amount - overkill)
                    metrics.total_damage += amount
                    metrics.damage_by_spell[spell_name] += amount
                    metrics.hits_by_spell[spell_name] += 1
                    metrics.target_hits_by_spell[spell_name][dest_name] += 1
                    if truthy(fields.get("critical")):
                        metrics.crits_by_spell[spell_name] += 1

        if first_ts is not None and last_ts is not None:
            metrics.active_time = max(0.0, last_ts - first_ts)
        return metrics


class CustomAddonJSONAdapter(CombatLogAdapter):
    """Adapter for a future CoADataLogger SavedVariables-to-JSON export.

    Expected shape:
      {
        "player": "Name",
        "events": [
          {"t": 123.45, "event":"SPELL_DAMAGE", "source":"Name", "target":"Dummy", "spellName":"Venom Fang", "amount":1234, "critical":true},
          ...
        ],
        "snapshot": {"level":60, "stats": {...}, "gear": [...]}
      }
    """

    def __init__(self, path: Path, player: str | None = None):
        self.path = path
        self.player = player

    def parse(self) -> CombatMetrics:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        player = self.player or payload.get("player")
        metrics = CombatMetrics(player=player)
        events = payload.get("events") or []
        times: list[float] = []
        for ev in events:
            if player and ev.get("source") and ev.get("source") != player:
                continue
            event = ev.get("event") or ""
            spell = ev.get("spellName") or ev.get("spell") or "Unknown"
            t = float(ev.get("t") or ev.get("timestamp") or 0.0)
            if t:
                times.append(t)
            metrics.event_count += 1
            if event in Wow335CombatLogAdapter.CAST_EVENTS:
                metrics.casts_by_spell[spell] += 1
            elif event in Wow335CombatLogAdapter.AURA_EVENTS:
                metrics.aura_uptime_events[spell] += 1
            elif event in Wow335CombatLogAdapter.DAMAGE_EVENTS:
                amount = max(0, as_int(ev.get("amount"), 0))
                metrics.total_damage += amount
                metrics.damage_by_spell[spell] += amount
                metrics.hits_by_spell[spell] += 1
                metrics.target_hits_by_spell[spell][ev.get("target") or "Unknown"] += 1
                if ev.get("critical"):
                    metrics.crits_by_spell[spell] += 1
        if times:
            metrics.active_time = max(times) - min(times)
        return metrics


# WotLK log lines are awkward because the timestamp contains spaces. This parser extracts the
# leading timestamp-ish prefix and sends the rest through CSV.
def parse_wow_log_line(line: str) -> tuple[float, str, dict[str, Any]] | None:
    line = line.strip()
    if not line:
        return None
    m = re.match(r"^(?P<date>\d+/\d+\s+\d+:\d+:\d+\.\d+)\s+(?P<body>.+)$", line)
    if not m:
        return None
    timestamp = timestamp_to_seconds(m.group("date"))
    try:
        parts = next(csv.reader([m.group("body")], skipinitialspace=True))
    except Exception:
        return None
    if not parts:
        return None
    event = parts[0]
    base = ["sourceGUID", "sourceName", "sourceFlags", "destGUID", "destName", "destFlags"]
    fields: dict[str, Any] = {}
    idx = 1
    for key in base:
        if idx < len(parts):
            fields[key] = parts[idx]
        idx += 1

    # Spell events include spellId/spellName/spellSchool after base fields.
    if event.startswith("SPELL_") or event in {"DAMAGE_SHIELD", "DAMAGE_SPLIT"}:
        if idx < len(parts): fields["spellId"] = parts[idx]
        if idx + 1 < len(parts): fields["spellName"] = parts[idx + 1]
        if idx + 2 < len(parts): fields["spellSchool"] = parts[idx + 2]
        idx += 3

    # Damage suffix: amount, overkill, school, resisted, blocked, absorbed, critical, glancing, crushing
    if event in Wow335CombatLogAdapter.DAMAGE_EVENTS:
        damage_keys = ["amount", "overkill", "school", "resisted", "blocked", "absorbed", "critical", "glancing", "crushing"]
        for key in damage_keys:
            if idx < len(parts):
                fields[key] = parts[idx]
            idx += 1
    return (timestamp, event, fields)


def timestamp_to_seconds(ts: str) -> float:
    # Month/day is irrelevant inside one log; use day/hour/min/sec as monotonic-ish value.
    m = re.match(r"(?P<month>\d+)/(?P<day>\d+)\s+(?P<h>\d+):(?P<m>\d+):(?P<s>\d+\.\d+)", ts)
    if not m:
        return 0.0
    return int(m.group("day")) * 86400 + int(m.group("h")) * 3600 + int(m.group("m")) * 60 + float(m.group("s"))


def strip_quotes(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().strip('"')


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "nil=false"}


# -----------------------------
# Exporters
# -----------------------------

def export_graph(nodes: dict[int, TalentNode], path: Path) -> None:
    payload = {"nodes": [], "edges": []}
    for n in sorted(nodes.values(), key=lambda x: x.entry_id):
        d = dataclasses.asdict(n)
        d.pop("raw", None)
        payload["nodes"].append(d)
    for n in sorted(nodes.values(), key=lambda x: x.entry_id):
        for req in n.required_ids:
            if req in nodes:
                payload["edges"].append({"source": req, "target": n.entry_id, "type": "REQUIRES"})
        for con in n.connected_node_ids:
            if con in nodes:
                payload["edges"].append({"source": n.entry_id, "target": con, "type": "CONNECTED_TO"})
        if n.required_tab_ae:
            payload["edges"].append({"source": f"tab:{n.tab_id}:AE:{n.required_tab_ae}", "target": n.entry_id, "type": "UNLOCKED_BY_TAB_AE"})
        if n.required_tab_te:
            payload["edges"].append({"source": f"tab:{n.tab_id}:TE:{n.required_tab_te}", "target": n.entry_id, "type": "UNLOCKED_BY_TAB_TE"})
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def cypher_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def export_cypher(nodes: dict[int, TalentNode], path: Path) -> None:
    lines: list[str] = []
    for n in sorted(nodes.values(), key=lambda x: x.entry_id):
        lines.append(
            "MERGE (n:CoATalent {entry_id: %d}) "
            "SET n.name='%s', n.class='%s', n.tab='%s', n.kind='%s', n.ae_cost=%d, n.te_cost=%d, "
            "n.required_level=%d, n.required_tab_ae=%d, n.required_tab_te=%d;" % (
                n.entry_id, cypher_escape(n.name), cypher_escape(n.class_name), cypher_escape(n.tab_name), cypher_escape(n.essence_kind),
                n.ae_cost, n.te_cost, n.required_level, n.required_tab_ae, n.required_tab_te,
            )
        )
    for n in sorted(nodes.values(), key=lambda x: x.entry_id):
        for req in n.required_ids:
            if req in nodes:
                lines.append("MATCH (a:CoATalent {entry_id:%d}), (b:CoATalent {entry_id:%d}) MERGE (a)-[:REQUIRES]->(b);" % (n.entry_id, req))
        for con in n.connected_node_ids:
            if con in nodes:
                lines.append("MATCH (a:CoATalent {entry_id:%d}), (b:CoATalent {entry_id:%d}) MERGE (a)-[:CONNECTED_TO]->(b);" % (n.entry_id, con))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# -----------------------------
# Reporting helpers
# -----------------------------

def explain_state(state: BuildState, nodes: dict[int, TalentNode], scorer: ScoringStrategy) -> dict[str, Any]:
    selected = [nodes[i] for i in state.selected if i in nodes]
    paid = [n for n in selected if n.paid]
    free = [n for n in selected if not n.paid]
    paid.sort(key=lambda n: (n.tab_name, n.required_tab_ae, n.required_tab_te, n.row, n.col, n.name))
    by_tab: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in paid:
        ns = scorer.node_score(n)
        by_tab[n.tab_name].append({
            "id": n.entry_id,
            "name": n.name,
            "cost": {"AE": n.ae_cost, "TE": n.te_cost},
            "requires": list(n.required_ids),
            "req_tab": {"AE": n.required_tab_ae, "TE": n.required_tab_te},
            "level": n.required_level,
            "tags": list(n.tags),
            "schools": list(n.damage_schools),
            "score": round(ns.score, 2),
        })
    return {
        "spent": {"AE": state.ae_spent, "TE": state.te_spent},
        "paid_count": len(paid),
        "auto_free_nodes": sorted(n.name for n in free),
        "paid_by_tab": by_tab,
    }


def selected_by_names(nodes: dict[int, TalentNode], names: list[str]) -> list[TalentNode]:
    if not names:
        return []
    out: list[TalentNode] = []
    lowered = [name.lower() for name in names]
    for n in nodes.values():
        if n.name.lower() in lowered:
            out.append(n)
    missing = [name for name in names if not any(n.name.lower() == name.lower() for n in out)]
    if missing:
        print(f"Warning: selected names not found: {', '.join(missing)}", file=sys.stderr)
    return out


def print_dataset_summary(nodes: dict[int, TalentNode]) -> None:
    print(f"Loaded {len(nodes)} nodes.")
    print("By essence kind:", dict(Counter(n.essence_kind for n in nodes.values())))
    print("By tab:", dict(Counter(n.tab_name for n in nodes.values())))
    print("Required levels:", dict(sorted(Counter(n.required_level for n in nodes.values()).items())))
    print("Required tab TE:", dict(sorted(Counter(n.required_tab_te for n in nodes.values()).items())))
    print("Required tab AE:", dict(sorted(Counter(n.required_tab_ae for n in nodes.values()).items())))
    print("Hard required-id edges:", sum(len(n.required_ids) for n in nodes.values()))
    print("Connected-node edges:", sum(len(n.connected_node_ids) for n in nodes.values()))


# -----------------------------
# CLI factory / commands
# -----------------------------

def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--entries", type=Path, default=Path("dist/coa_entries.jsonl"), help="Path to normalized coa_entries.jsonl")
    p.add_argument("--class-name", default="Venomancer")
    p.add_argument("--profile", default="generic", help="Scoring profile: generic or stalker for Venomancer")
    p.add_argument("--encounter", default="single_target", choices=["single_target", "aoe", "cleave", "solo"])
    p.add_argument("--level", type=int, default=60)
    p.add_argument("--max-ae", type=int, default=26)
    p.add_argument("--max-te", type=int, default=25)
    p.add_argument("--combat-log", type=Path, help="Optional WoWCombatLog.txt to derive empirical spell weights")
    p.add_argument("--addon-json", type=Path, help="Optional JSON exported from a custom addon/SavedVariables conversion")
    p.add_argument("--player", help="Player name to filter log/addon events")
    p.add_argument("--empirical-blend", type=float, default=0.0, help="0..1 blend of empirical spell damage share into scoring")


def make_scorer(args: argparse.Namespace, class_name: str) -> ScoringStrategy:
    metrics: CombatMetrics | None = None
    if getattr(args, "combat_log", None):
        metrics = Wow335CombatLogAdapter(args.combat_log, args.player).parse()
    if getattr(args, "addon_json", None):
        metrics = CustomAddonJSONAdapter(args.addon_json, args.player).parse()
    profile = make_profile(class_name, args.profile, args.encounter)
    return HeuristicScoringStrategy(profile, metrics=metrics, empirical_blend=getattr(args, "empirical_blend", 0.0))


def command_optimize(args: argparse.Namespace) -> None:
    repo = TalentRepository(args.entries)
    nodes = repo.by_class(args.class_name)
    config = SearchConfig(args.level, args.max_ae, args.max_te, args.beam_width, args.branch_width, args.top, args.require_budget_fraction)
    rules = BuildRules(nodes, config)
    scorer = make_scorer(args, args.class_name)
    if args.summary:
        print_dataset_summary(nodes)
    optimizer = BuildOptimizer(nodes, rules, scorer)
    results = optimizer.optimize(config)

    if args.json:
        out = []
        for score, st, notes in results:
            item = explain_state(st, nodes, scorer)
            item["score"] = round(score, 2)
            item["state_notes"] = notes
            selected = [nodes[i] for i in st.selected if i in nodes]
            rot = make_rotation_strategy(args.class_name, args.profile, args.encounter).generate(selected)
            item["rotation_apl"] = [r.simc_like() for r in rot]
            out.append(item)
        print(json.dumps(out, indent=2))
        return

    print(f"Top {len(results)} builds: class={args.class_name}, profile={args.profile}, encounter={args.encounter}, level={args.level}, AE={args.max_ae}, TE={args.max_te}")
    for rank, (score, st, notes) in enumerate(results, start=1):
        print("=" * 96)
        print(f"#{rank} score={score:.2f} spent AE={st.ae_spent}/{args.max_ae}, TE={st.te_spent}/{args.max_te}")
        exp = explain_state(st, nodes, scorer)
        for tab, ns in exp["paid_by_tab"].items():
            print(f"\n[{tab}]")
            for n in ns:
                print(f"  - {n['name']} (id={n['id']}, AE={n['cost']['AE']}, TE={n['cost']['TE']}, score={n['score']})")
        if notes:
            print("\nState notes:")
            for note in notes[:16]:
                print(f"  {note}")
        if args.show_rotation:
            selected = [nodes[i] for i in st.selected if i in nodes]
            rot = make_rotation_strategy(args.class_name, args.profile, args.encounter).generate(selected)
            print("\nRotation scaffold:")
            for r in rot:
                print("  " + r.simc_like())


def command_rotation(args: argparse.Namespace) -> None:
    repo = TalentRepository(args.entries)
    nodes = repo.by_class(args.class_name)
    selected = selected_by_names(nodes, args.selected_names)
    if not selected and args.from_build_json:
        payload = json.loads(args.from_build_json.read_text(encoding="utf-8"))
        ids = set()
        if isinstance(payload, list) and payload:
            payload = payload[0]
        for tab_nodes in (payload.get("paid_by_tab") or {}).values():
            for item in tab_nodes:
                ids.add(as_int(item.get("id")))
        selected = [nodes[i] for i in ids if i in nodes]
    if not selected:
        # Use all nodes as a rough class rotation catalog.
        selected = list(nodes.values())
    strategy = make_rotation_strategy(args.class_name, args.profile, args.encounter)
    for rule in strategy.generate(selected):
        print(rule.simc_like())


def command_parse_log(args: argparse.Namespace) -> None:
    if args.combat_log:
        metrics = Wow335CombatLogAdapter(args.combat_log, args.player).parse()
    elif args.addon_json:
        metrics = CustomAddonJSONAdapter(args.addon_json, args.player).parse()
    else:
        raise SystemExit("parse-log requires --combat-log or --addon-json")
    print(json.dumps(metrics.to_dict(), indent=2))


def command_graph(args: argparse.Namespace) -> None:
    repo = TalentRepository(args.entries)
    nodes = repo.by_class(args.class_name)
    if args.summary:
        print_dataset_summary(nodes)
    if args.export_graph:
        export_graph(nodes, args.export_graph)
        print(f"Wrote graph JSON: {args.export_graph}")
    if args.export_cypher:
        export_cypher(nodes, args.export_cypher)
        print(f"Wrote Cypher: {args.export_cypher}")
    if not args.export_graph and not args.export_cypher:
        print_dataset_summary(nodes)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Extensible CoA build/rotation optimizer scaffold")
    sub = ap.add_subparsers(dest="command", required=True)

    opt = sub.add_parser("optimize", help="Search legal builds and score them")
    add_common_args(opt)
    opt.add_argument("--beam-width", type=int, default=10)
    opt.add_argument("--branch-width", type=int, default=40)
    opt.add_argument("--top", type=int, default=10)
    opt.add_argument("--require-budget-fraction", type=float, default=0.70)
    opt.add_argument("--summary", action="store_true")
    opt.add_argument("--json", action="store_true")
    opt.add_argument("--show-rotation", action="store_true")
    opt.set_defaults(func=command_optimize)

    rot = sub.add_parser("rotation", help="Generate SimC-like APL scaffold for a selected build")
    add_common_args(rot)
    rot.add_argument("--selected-names", nargs="*", default=[])
    rot.add_argument("--from-build-json", type=Path)
    rot.set_defaults(func=command_rotation)

    log = sub.add_parser("parse-log", help="Parse WoWCombatLog.txt or custom addon JSON into metrics")
    log.add_argument("--combat-log", type=Path)
    log.add_argument("--addon-json", type=Path)
    log.add_argument("--player")
    log.set_defaults(func=command_parse_log)

    graph = sub.add_parser("graph", help="Export graph JSON/Cypher or print graph summary")
    graph.add_argument("--entries", type=Path, default=Path("dist/coa_entries.jsonl"))
    graph.add_argument("--class-name", default="Venomancer")
    graph.add_argument("--summary", action="store_true")
    graph.add_argument("--export-graph", type=Path)
    graph.add_argument("--export-cypher", type=Path)
    graph.set_defaults(func=command_graph)
    return ap


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
