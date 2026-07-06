from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .action_catalog import build_action_catalog
from .apl import generate_apl
from .apl_profiles import load_apl_profile_by_role
from .build_diversity import (
    BuildDiversityCandidate,
    build_playstyle_fingerprint,
    reliability_label,
    reliability_score,
    rotation_signature_from_apl,
    select_diverse_builds,
)
from .builds import BuildConfig, BuildRules
from .display_names import display_spec_name
from .domain import TalentNode
from .objectives import objective_for_role
from .profiles import load_profile_by_role
from .repository import TalentRepository
from .roles import (
    ENGINE_ROLES,
    GUIDE_ROLES,
    RoleResolution,
    resolve_configured_role,
    resolve_spec_role,
)
from .scoring import TheoryScorer
from .search import BuildSearchConfig, BuildSearcher
from .simulation import SimulationConfig, simulate_build
from .gear import recommend_gear_for_guide_role, recommend_weapon_and_armor
from .mechanics_inference import infer_mechanic_from_tooltip
from .mechanics_repository import MechanicsRepository
from .rotation_candidates import RotationCandidateConfig, generate_rotation_candidates
from .rotation_guides import build_rotation_guide
from .rotation_loops import build_rotation_loop
from .rotation_scoring import score_rotation_result, select_best_rotation_candidate
from .rotation_simulation import RotationSimulationConfig, simulate_apl
from .stats import stat_priority_for_role, stat_priority_report_for_role

META_REPORT_SCHEMA_VERSION = "coa-meta-report-v1"
DEFAULT_PUBLIC_ENCOUNTER = "baseline_single_target"
ENCOUNTER_ALIASES = {DEFAULT_PUBLIC_ENCOUNTER: "single_target"}
SHARED_TAB_NAMES = {"Class", "None"}
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
SUPPORTED_META_ROLES = {"auto", *GUIDE_ROLES, *ENGINE_ROLES}


@dataclass(frozen=True)
class ClassTabMetadata:
    class_name: str
    tab_id: int
    tab_name: str
    sort_order: int
    nominal_essence_kind: str


@dataclass(frozen=True)
class ReportableSpec:
    class_name: str
    spec_id: int
    spec_name: str
    sort_order: int = 0


@dataclass(frozen=True)
class BuildScope:
    class_name: str
    spec_id: int
    spec_name: str
    level: int
    encounter_profile_id: str
    search_profile_id: str
    scoring_profile_id: str
    apl_profile_id: str
    top: int

    @property
    def spec_key(self) -> str:
        return slugify_key(self.spec_name)

    @property
    def scoring_encounter(self) -> str:
        return ENCOUNTER_ALIASES.get(self.encounter_profile_id, self.encounter_profile_id)


def slugify_key(value: str) -> str:
    lowered = value.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")


def infer_spec_role(repository: TalentRepository, scope: BuildScope) -> str:
    return resolve_spec_role(repository, scope).engine_role


def resolve_scope_role(repository: TalentRepository, scope: BuildScope, configured_role: str) -> str:
    return resolve_scope_role_detail(repository, scope, configured_role).engine_role


def resolve_scope_role_detail(repository: TalentRepository, scope: BuildScope, configured_role: str) -> RoleResolution:
    if configured_role not in SUPPORTED_META_ROLES:
        raise ValueError(f"Unsupported role {configured_role!r}; expected one of {sorted(SUPPORTED_META_ROLES)}")
    inferred = resolve_spec_role(repository, scope)
    return resolve_configured_role(configured_role, inferred)


def effective_required_level(node: TalentNode) -> int:
    availability = node.availability or node.raw.get("availability") or {}
    confidence = availability.get("level_confidence")
    level = availability.get("effective_required_level")
    if confidence in {"high", "medium"} and type(level) is int:
        return level
    return node.required_level


def load_class_metadata(path: Path | str) -> tuple[ClassTabMetadata, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tabs: list[ClassTabMetadata] = []
    for class_record in data:
        class_name = str(class_record.get("class_name", ""))
        for tab in class_record.get("tabs", []):
            tabs.append(
                ClassTabMetadata(
                    class_name=class_name,
                    tab_id=int(tab.get("tab_id", 0)),
                    tab_name=str(tab.get("tab_name", "")),
                    sort_order=int(tab.get("sort_order", 0)),
                    nominal_essence_kind=str(tab.get("nominal_essence_kind", "")),
                )
            )
    return tuple(tabs)


class EligibilityPolicy:
    def reportable_specs(
        self,
        repository: TalentRepository,
        class_metadata: tuple[ClassTabMetadata, ...] = tuple(),
    ) -> tuple[ReportableSpec, ...]:
        node_tabs: dict[tuple[str, int, str], list[TalentNode]] = {}
        for class_name in repository.class_names():
            for node in repository.nodes_for_class(class_name):
                if node.tab_name in SHARED_TAB_NAMES:
                    continue
                node_tabs.setdefault((node.class_name, node.tab_id, node.tab_name), []).append(node)

        metadata_order = {(item.class_name, item.tab_id, item.tab_name): item.sort_order for item in class_metadata}
        specs = [
            ReportableSpec(
                class_name=class_name,
                spec_id=tab_id,
                spec_name=tab_name,
                sort_order=metadata_order.get((class_name, tab_id, tab_name), 0),
            )
            for (class_name, tab_id, tab_name), nodes in node_tabs.items()
            if nodes
        ]
        return tuple(sorted(specs, key=lambda item: (item.class_name, item.sort_order, item.spec_name)))

    def eligible_node_ids(self, repository: TalentRepository, scope: BuildScope) -> tuple[int, ...]:
        eligible: list[int] = []
        for node in repository.nodes_for_class(scope.class_name):
            if effective_required_level(node) > scope.level:
                continue
            if node.tab_id == scope.spec_id or node.tab_name == "Class":
                eligible.append(node.entry_id)
        return tuple(sorted(set(eligible)))

    def metadata_warnings(
        self,
        repository: TalentRepository,
        class_metadata: tuple[ClassTabMetadata, ...],
    ) -> tuple[str, ...]:
        node_tabs = {
            (node.class_name, node.tab_id, node.tab_name)
            for class_name in repository.class_names()
            for node in repository.nodes_for_class(class_name)
        }
        warnings: list[str] = []
        for item in class_metadata:
            if item.tab_name in SHARED_TAB_NAMES:
                continue
            if (item.class_name, item.tab_id, item.tab_name) not in node_tabs:
                warnings.append(f"metadata_tab_has_no_nodes:{item.class_name}:{item.tab_name}")
        return tuple(warnings)

    def scope_warnings(self, repository: TalentRepository, scope: BuildScope) -> tuple[str, ...]:
        warnings: list[str] = []
        class_pool_nodes = [
            node for node in repository.nodes_for_class(scope.class_name)
            if node.tab_name == "Class"
        ]
        if scope.level < 60 and any(not (node.availability or node.raw.get("availability")) for node in class_pool_nodes):
            warnings.append("class_pool_level_gating_incomplete")
            warnings.append("shared_class_level_gating_incomplete")
        return tuple(warnings)


@dataclass(frozen=True)
class MetaRunConfig:
    entries_path: Path
    classes_path: Path | None = None
    class_names: tuple[str, ...] = tuple()
    spec_names_or_ids: tuple[str, ...] = tuple()
    level: int = 60
    encounter_profile_ids: tuple[str, ...] = (DEFAULT_PUBLIC_ENCOUNTER,)
    search_profile_id: str = "default"
    scoring_profile_id: str = "auto"
    apl_profile_id: str = "auto"
    role: str = "auto"
    top: int = 3
    beam_width: int = 5
    branch_width: int = 10
    require_budget_fraction: float = 0.7
    max_ae: int = 26
    max_te: int = 25
    simulate: bool = False
    simulation_duration_ms: int = 60_000
    simulation_iterations: int = 1
    simulation_seed: int = 1
    simulate_rotations: bool = False
    rotation_duration_ms: int = 90_000
    rotation_candidates: int = 48
    gear_profile_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries_path": str(self.entries_path),
            "classes_path": str(self.classes_path) if self.classes_path else None,
            "class_names": list(self.class_names),
            "spec_names_or_ids": list(self.spec_names_or_ids),
            "level": self.level,
            "encounter_profile_ids": list(self.encounter_profile_ids),
            "search_profile_id": self.search_profile_id,
            "scoring_profile_id": self.scoring_profile_id,
            "apl_profile_id": self.apl_profile_id,
            "role": self.role,
            "top": self.top,
            "beam_width": self.beam_width,
            "branch_width": self.branch_width,
            "require_budget_fraction": self.require_budget_fraction,
            "max_ae": self.max_ae,
            "max_te": self.max_te,
            "simulate": self.simulate,
            "simulation_duration_ms": self.simulation_duration_ms,
            "simulation_iterations": self.simulation_iterations,
            "simulation_seed": self.simulation_seed,
            "simulate_rotations": self.simulate_rotations,
            "rotation_duration_ms": self.rotation_duration_ms,
            "rotation_candidates": self.rotation_candidates,
            "gear_profile_path": str(self.gear_profile_path) if self.gear_profile_path else None,
        }


@dataclass(frozen=True)
class BuildReport:
    rank: int
    projected_dps_index: float
    confidence_label: str
    selected_nodes: tuple[dict[str, Any], ...]
    score_breakdown: dict[str, Any]
    generated_apl: dict[str, Any]
    simulation_result: dict[str, Any] | None
    rotation_summary: dict[str, Any]
    stat_priority: tuple[dict[str, Any], ...]
    stat_priority_report: dict[str, Any]
    gear_recommendation: dict[str, Any]
    gear_recommendation_report: dict[str, Any]
    explanation: dict[str, Any]
    provenance: dict[str, Any]
    playstyle_fingerprint: dict[str, Any]
    selection_reason: dict[str, Any]
    rotation_loop: dict[str, Any]
    rotation_signature: dict[str, Any]
    warnings: tuple[str, ...]
    rotation_guide: dict[str, Any] | None = None
    primary_index: float | None = None
    primary_index_label: str = ""
    objective_id: str = ""
    objective_breakdown: dict[str, float] | None = None
    alternate_objective_scores: dict[str, dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        primary_index = self.primary_index if self.primary_index is not None else self.projected_dps_index
        return {
            "rank": self.rank,
            "projected_dps_index": self.projected_dps_index,
            "primary_index": primary_index,
            "primary_index_label": self.primary_index_label or "Projected Damage Index",
            "objective_id": self.objective_id or "damage",
            "objective_breakdown": dict(self.objective_breakdown or {}),
            "alternate_objective_scores": {
                role: dict(payload) for role, payload in (self.alternate_objective_scores or {}).items()
            },
            "confidence_label": self.confidence_label,
            "selected_nodes": list(self.selected_nodes),
            "score_breakdown": self.score_breakdown,
            "generated_apl": self.generated_apl,
            "simulation_result": self.simulation_result,
            "rotation_summary": self.rotation_summary,
            "stat_priority": list(self.stat_priority),
            "stat_priority_report": self.stat_priority_report,
            "gear_recommendation": self.gear_recommendation,
            "gear_recommendation_report": self.gear_recommendation_report,
            "explanation": self.explanation,
            "provenance": self.provenance,
            "playstyle_fingerprint": self.playstyle_fingerprint,
            "selection_reason": self.selection_reason,
            "rotation_loop": self.rotation_loop,
            "rotation_signature": self.rotation_signature,
            "rotation_guide": dict(self.rotation_guide or {}),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SpecResult:
    class_name: str
    spec_id: int
    spec_name: str
    role: str
    engine_role: str
    role_provenance: dict[str, Any]
    level: int
    encounter_profile_id: str
    search_profile_id: str
    scoring_profile_id: str
    apl_profile_id: str
    summary: dict[str, Any]
    top_builds: tuple[BuildReport, ...]
    warnings: tuple[str, ...]
    primary_role: str = ""
    secondary_roles: tuple[str, ...] = tuple()
    roles: tuple[str, ...] = tuple()

    def to_dict(self) -> dict[str, Any]:
        display_name = display_spec_name(self.class_name, self.spec_name)
        primary_role = self.primary_role or self.role
        secondary_roles = self.secondary_roles
        roles = self.roles or tuple(dict.fromkeys((primary_role, *secondary_roles)))
        return {
            "class_name": self.class_name,
            "spec_id": self.spec_id,
            "spec_name": display_name,
            "source_spec_name": self.spec_name,
            "role": self.role,
            "primary_role": primary_role,
            "secondary_roles": list(secondary_roles),
            "roles": list(roles),
            "engine_role": self.engine_role,
            "role_provenance": self.role_provenance,
            "level": self.level,
            "encounter_profile_id": self.encounter_profile_id,
            "search_profile_id": self.search_profile_id,
            "scoring_profile_id": self.scoring_profile_id,
            "apl_profile_id": self.apl_profile_id,
            "summary": self.summary,
            "top_builds": [build.to_dict() for build in self.top_builds],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class MetaReport:
    schema_version: str
    generated_at: str
    input_artifacts: dict[str, str]
    run_config: dict[str, Any]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    class_summaries: tuple[dict[str, Any], ...]
    spec_results: tuple[SpecResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "input_artifacts": self.input_artifacts,
            "run_config": self.run_config,
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "class_summaries": list(self.class_summaries),
            "spec_results": [result.to_dict() for result in self.spec_results],
        }


class MetaReportRunner:
    def __init__(self, config: MetaRunConfig, eligibility: EligibilityPolicy | None = None):
        self.config = config
        self.eligibility = eligibility or EligibilityPolicy()

    def run(self) -> MetaReport:
        repository = TalentRepository.from_entries(self.config.entries_path)
        metadata = load_class_metadata(self.config.classes_path) if self.config.classes_path else tuple()
        warnings = list(self.eligibility.metadata_warnings(repository, metadata))
        scopes = self._expand_scopes(repository, metadata)
        spec_results = tuple(self._run_scope(repository, scope) for scope in scopes)
        return MetaReport(
            schema_version=META_REPORT_SCHEMA_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(),
            input_artifacts={
                "entries": str(self.config.entries_path),
                "classes": str(self.config.classes_path) if self.config.classes_path else "",
            },
            run_config=self.config.to_dict(),
            assumptions=(
                "Projected DPS index is a theorycraft score, not observed DPS.",
                "Shared Class nodes are included for each reportable spec.",
                "Auto role inference resolves player-facing roles and maps them to broad scoring/APL profiles.",
            ),
            warnings=tuple(warnings),
            class_summaries=_class_summaries(spec_results),
            spec_results=spec_results,
        )

    def _expand_scopes(
        self,
        repository: TalentRepository,
        metadata: tuple[ClassTabMetadata, ...],
    ) -> tuple[BuildScope, ...]:
        specs = self.eligibility.reportable_specs(repository, metadata)
        class_filter = set(self.config.class_names)
        spec_filter = {item.casefold() for item in self.config.spec_names_or_ids}
        scopes: list[BuildScope] = []
        for spec in specs:
            if class_filter and spec.class_name not in class_filter:
                continue
            if spec_filter and str(spec.spec_id).casefold() not in spec_filter and spec.spec_name.casefold() not in spec_filter:
                continue
            for encounter_id in self.config.encounter_profile_ids:
                scopes.append(
                    BuildScope(
                        class_name=spec.class_name,
                        spec_id=spec.spec_id,
                        spec_name=spec.spec_name,
                        level=self.config.level,
                        encounter_profile_id=encounter_id,
                        search_profile_id=self.config.search_profile_id,
                        scoring_profile_id=self.config.scoring_profile_id,
                        apl_profile_id=self.config.apl_profile_id,
                        top=self.config.top,
                    )
                )
        return tuple(scopes)

    def _run_scope(self, repository: TalentRepository, scope: BuildScope) -> SpecResult:
        warnings = list(self.eligibility.scope_warnings(repository, scope))
        role_resolution = resolve_scope_role_detail(repository, scope, self.config.role)
        role = role_resolution.role
        engine_role = role_resolution.engine_role
        eligible_ids = self.eligibility.eligible_node_ids(repository, scope)
        rules = BuildRules(
            repository,
            BuildConfig(
                class_name=scope.class_name,
                level=scope.level,
                max_ae=self.config.max_ae,
                max_te=self.config.max_te,
                allowed_node_ids=eligible_ids,
            ),
        )
        candidate_limit = max(scope.top * 5, 12)
        search_results = BuildSearcher(repository, rules).search(
            BuildSearchConfig(
                top=candidate_limit,
                beam_width=self.config.beam_width,
                branch_width=self.config.branch_width,
                require_budget_fraction=self.config.require_budget_fraction,
            )
        )
        if not search_results and self.config.require_budget_fraction > 0:
            fallback_results = BuildSearcher(repository, rules).search(
                BuildSearchConfig(
                    top=candidate_limit,
                    beam_width=self.config.beam_width,
                    branch_width=self.config.branch_width,
                    require_budget_fraction=0.0,
                )
            )
            if fallback_results:
                search_results = fallback_results
                warnings.append("budget_floor_unreachable_with_current_gates")
        scoring_profile, scoring_warnings = load_profile_by_role(
            scope.class_name,
            scope.spec_key,
            engine_role,
            scope.scoring_encounter,
        )
        apl_profile, apl_warnings = load_apl_profile_by_role(scope.class_name, scope.spec_key, engine_role)
        scored_rows: list[tuple[Any, Any]] = []
        for result in search_results:
            if result.state is None:
                continue
            scored_rows.append((result, TheoryScorer(scoring_profile).score_build(result.state, repository)))
        scored_rows.sort(
            key=lambda item: (
                item[1].projected_dps_index,
                CONFIDENCE_RANK.get(item[1].confidence, 0),
                _build_key(item[0].state),
            ),
            reverse=True,
        )
        candidates: list[BuildDiversityCandidate] = []
        for result, scored in scored_rows:
            assert result.state is not None
            apl_doc = generate_apl(
                result.state,
                repository,
                apl_profile,
                encounter=scope.scoring_encounter,
                profile_warnings=apl_warnings,
            )
            selected_node_objects = tuple(
                node for node_id in sorted(result.state.selected_ids)
                if (node := repository.get_node(node_id)) is not None
            )
            candidate_warnings = tuple(scoring_warnings + list(scored.warnings) + list(apl_doc.warnings))
            fingerprint = build_playstyle_fingerprint(nodes=selected_node_objects, apl=apl_doc, role=role)
            reliability = reliability_score(
                nodes=selected_node_objects,
                apl=apl_doc,
                role=role,
                warnings=candidate_warnings,
            )
            loop = build_rotation_loop(
                apl=apl_doc,
                selected_nodes=selected_node_objects,
                role=role,
                encounter=scope.scoring_encounter,
            )
            rotation_signature = rotation_signature_from_apl(apl_doc, role=role)
            candidates.append(
                BuildDiversityCandidate(
                    build_id=str(_build_key(result.state)),
                    projected_dps_index=scored.projected_dps_index,
                    confidence_label=scored.confidence,
                    fingerprint=fingerprint,
                    reliability_score=reliability,
                    reliability_label=reliability_label(reliability),
                    rotation_signature=rotation_signature,
                    payload={
                        "result": result,
                        "scored": scored,
                        "apl_doc": apl_doc,
                        "rotation_loop": loop,
                        "rotation_signature": rotation_signature,
                        "selected_node_objects": selected_node_objects,
                        "warnings": candidate_warnings,
                    },
                    warnings=candidate_warnings,
                )
            )

        selected_candidates = select_diverse_builds(candidates, top=scope.top)
        top_builds: list[BuildReport] = []
        for index, candidate in enumerate(selected_candidates, start=1):
            payload = candidate.payload
            result = payload["result"]
            scored = payload["scored"]
            apl_doc = payload["apl_doc"]
            assert result.state is not None
            simulation_result = None
            if self.config.simulate:
                simulation_result = simulate_build(
                    result.state,
                    repository,
                    apl_doc,
                    SimulationConfig(
                        duration_ms=self.config.simulation_duration_ms,
                        iterations=self.config.simulation_iterations,
                        seed=self.config.simulation_seed,
                    ),
                ).to_dict()
            apl_payload = apl_doc.to_dict()
            rotation_summary = _rotation_summary(apl_payload, role)
            rotation_guide = None
            rotation_warnings: tuple[str, ...] = tuple()
            if self.config.simulate_rotations:
                rotation_guide, rotation_warnings = self._build_rotation_guide_for_candidate(
                    apl_doc=apl_doc,
                    selected_nodes=payload["selected_node_objects"],
                    role=role,
                    encounter=scope.scoring_encounter,
                    build_id=str(_build_key(result.state)),
                )
            stat_priority = tuple(priority.to_dict() for priority in stat_priority_for_role(engine_role))
            stat_priority_report = stat_priority_report_for_role(role, engine_role=engine_role).to_dict()
            gear_recommendation = recommend_weapon_and_armor(engine_role, tuple())
            gear_recommendation_report = recommend_gear_for_guide_role(
                role,
                engine_role=engine_role,
                items=tuple(),
            ).to_dict()
            objective = objective_for_role(
                role,
                scored.projected_dps_index,
                scored.components,
                secondary_roles=role_resolution.secondary_roles,
            )
            selected_nodes = tuple(_node_to_report(repository.node_by_id(node_id)) for node_id in sorted(result.state.selected_ids))
            selection_reason = candidate.selection_reason
            build_warnings = tuple(dict.fromkeys((*payload["warnings"], *rotation_warnings)))
            top_builds.append(
                BuildReport(
                    rank=index,
                    projected_dps_index=scored.projected_dps_index,
                    confidence_label=scored.confidence,
                    selected_nodes=selected_nodes,
                    score_breakdown=scored.to_dict(),
                    generated_apl=apl_payload,
                    simulation_result=simulation_result,
                    rotation_summary=rotation_summary,
                    stat_priority=stat_priority,
                    stat_priority_report=stat_priority_report,
                    gear_recommendation=gear_recommendation,
                    gear_recommendation_report=gear_recommendation_report,
                    explanation={"score_components": [component.__dict__ for component in scored.components]},
                    provenance={
                        "normalized_schema": "coa-normalized-v1",
                        "role": role,
                        "engine_role": engine_role,
                        "role_provenance": role_resolution.to_dict(),
                        "scoring_profile_id": scoring_profile.profile_id,
                        "apl_profile_id": apl_profile.profile_id,
                    },
                    playstyle_fingerprint=candidate.fingerprint.to_dict(),
                    selection_reason=selection_reason.to_dict() if selection_reason else {},
                    rotation_loop=payload["rotation_loop"].to_dict(),
                    rotation_signature=payload["rotation_signature"].to_dict(),
                    warnings=build_warnings,
                    rotation_guide=rotation_guide,
                    primary_index=objective.primary_index,
                    primary_index_label=objective.primary_index_label,
                    objective_id=objective.objective_id,
                    objective_breakdown=objective.objective_breakdown,
                    alternate_objective_scores=objective.alternate_objective_scores,
                )
            )
        if not top_builds:
            warnings.append("no_valid_builds_found")
        return SpecResult(
            class_name=scope.class_name,
            spec_id=scope.spec_id,
            spec_name=scope.spec_name,
            role=role,
            engine_role=engine_role,
            role_provenance=role_resolution.to_dict(),
            level=scope.level,
            encounter_profile_id=scope.encounter_profile_id,
            search_profile_id=scope.search_profile_id,
            scoring_profile_id=scoring_profile.profile_id,
            apl_profile_id=apl_profile.profile_id,
            summary=_spec_summary(scope, role, top_builds, warnings),
            top_builds=tuple(top_builds),
            warnings=tuple(warnings),
            primary_role=role_resolution.role,
            secondary_roles=role_resolution.secondary_roles,
            roles=role_resolution.roles,
        )

    def _build_rotation_guide_for_candidate(
        self,
        *,
        apl_doc: Any,
        selected_nodes: tuple[TalentNode, ...],
        role: str,
        encounter: str,
        build_id: str,
    ) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
        try:
            mechanics_repo = _mechanics_repository_from_nodes(selected_nodes)
            action_catalog = build_action_catalog(selected_nodes, mechanics_repo, role=role, encounter=encounter)
            rotation_candidates = generate_rotation_candidates(
                apl_doc,
                action_catalog,
                role=role,
                config=RotationCandidateConfig(max_candidates=self.config.rotation_candidates),
            )
            if not rotation_candidates:
                return None, ("rotation_guide_no_executable_candidates", *action_catalog.warnings)

            max_resources, initial_resources = _rotation_resource_defaults(action_catalog)
            scored = []
            for candidate in rotation_candidates:
                result = simulate_apl(
                    candidate.apl,
                    action_catalog,
                    RotationSimulationConfig(
                        source=candidate.candidate_id,
                        duration_ms=self.config.rotation_duration_ms,
                        target_count=_target_count_for_encounter(encounter),
                        initial_resources=initial_resources,
                        max_resources=max_resources,
                    ),
                )
                scored.append(score_rotation_result(result, role, action_catalog))

            selection = select_best_rotation_candidate(tuple(scored), role)
            candidate_by_id = {candidate.candidate_id: candidate for candidate in rotation_candidates}
            selected_candidate = candidate_by_id.get(selection.best.candidate_id, rotation_candidates[0])
            guide = build_rotation_guide(
                selection,
                selected_candidate.apl,
                action_catalog,
                role=role,
                encounter=encounter,
                build_id=build_id,
            )
            warnings = tuple(dict.fromkeys((*guide.warnings, *action_catalog.warnings)))
            return guide.to_dict(), warnings
        except Exception as exc:  # pragma: no cover - defensive report fallback
            return None, (f"rotation_guide_failed:{exc.__class__.__name__}",)


def _rotation_summary(apl_payload: dict[str, Any], role: str) -> dict[str, Any]:
    sections = {
        "opener": [],
        "maintenance": [],
        "cooldowns": [],
        "builder_spender": [],
        "defensive_support": [],
    }
    for action in apl_payload.get("actions", []):
        item = {
            "action_name": action.get("action_name"),
            "condition": action.get("condition", ""),
            "confidence": action.get("confidence", "low"),
        }
        category = action.get("category")
        if category == "maintenance":
            sections["maintenance"].append(item)
        elif category == "cooldown":
            sections["cooldowns"].append(item)
        elif category in {"builder", "spender", "filler", "execute", "aoe"}:
            sections["builder_spender"].append(item)
        elif category == "utility" or role in {"tank", "healer", "support"}:
            sections["defensive_support"].append(item)
        else:
            sections["opener"].append(item)
    return {
        "schema_version": "coa-rotation-summary-v1",
        "source": "generated_apl",
        "sections": {key: value for key, value in sections.items() if value},
        "warnings": list(apl_payload.get("warnings", [])),
    }


def _mechanics_repository_from_nodes(selected_nodes: tuple[TalentNode, ...]) -> MechanicsRepository:
    records = []
    seen_spell_ids: set[int] = set()
    for node in selected_nodes:
        if not node.spell_id or int(node.spell_id) in seen_spell_ids:
            continue
        seen_spell_ids.add(int(node.spell_id))
        records.append(
            infer_mechanic_from_tooltip(
                spell_id=int(node.spell_id),
                name=node.name,
                tooltip_text=node.description_text,
                source_node_ids=(node.entry_id,),
                tags=node.tags,
                damage_schools=node.damage_schools,
                resources=node.resources,
            )
        )
    return MechanicsRepository(records)


def _rotation_resource_defaults(action_catalog: Any) -> tuple[dict[str, float], dict[str, float]]:
    resource_names: set[str] = set()
    generated_names: set[str] = set()
    for action in action_catalog.actions:
        resource_names.update(action.costs)
        resource_names.update(action.generates)
        generated_names.update(action.generates)
    max_resources = {resource: 100.0 for resource in resource_names}
    initial_resources = {
        resource: 0.0 if resource in generated_names else maximum
        for resource, maximum in max_resources.items()
    }
    return max_resources, initial_resources


def _target_count_for_encounter(encounter: str) -> int:
    return 5 if "aoe" in encounter or "multi" in encounter else 1


def _spec_summary(scope: BuildScope, role: str, top_builds: list[BuildReport], warnings: list[str]) -> dict[str, Any]:
    best = top_builds[0] if top_builds else None
    return {
        "schema_version": "coa-spec-summary-v1",
        "class_name": scope.class_name,
        "spec_name": display_spec_name(scope.class_name, scope.spec_name),
        "source_spec_name": scope.spec_name,
        "role": role,
        "best_projected_dps_index": best.projected_dps_index if best else None,
        "data_confidence": best.confidence_label if best else "low",
        "strengths": _summary_strengths(best, role),
        "constraints": list(warnings),
    }


def _summary_strengths(best: BuildReport | None, role: str) -> list[str]:
    if best is None:
        return ["No legal build found with current gates."]
    if role == "tank":
        return ["Prioritizes defensive, mitigation, and control features from normalized tags."]
    if role == "healer":
        return ["Prioritizes healing throughput, recovery windows, and ally support from normalized tags."]
    if role == "support":
        return ["Prioritizes group utility, aura uptime, and flexible support tools from normalized tags."]
    if role == "caster_dps":
        return ["Prioritizes spell damage, effects, cooldown, and proc features from normalized tags."]
    if role == "ranged_dps":
        return ["Prioritizes ranged damage, uptime, cooldown, and proc features from normalized tags."]
    return ["Prioritizes melee damage, resource, cooldown, and proc features from normalized tags."]


def _build_key(state: Any) -> str:
    if state is None:
        return ""
    return ",".join(str(rank.node_id) for rank in state.selected_ranks)


def _node_to_report(node: TalentNode) -> dict[str, Any]:
    return {
        "node_id": node.entry_id,
        "spell_id": node.spell_id,
        "name": node.name,
        "tab_id": node.tab_id,
        "tab_name": node.tab_name,
        "essence_kind": node.essence_kind,
        "ae_cost": node.ae_cost,
        "te_cost": node.te_cost,
        "required_level": node.required_level,
        "icon": node.raw.get("icon") or node.raw.get("iconPath"),
        "tags": list(node.tags),
        "damage_schools": list(node.damage_schools),
        "resources": list(node.resources),
    }


def _class_summaries(spec_results: tuple[SpecResult, ...]) -> tuple[dict[str, Any], ...]:
    by_class: dict[str, list[SpecResult]] = {}
    for result in spec_results:
        by_class.setdefault(result.class_name, []).append(result)
    summaries: list[dict[str, Any]] = []
    for class_name, rows in sorted(by_class.items()):
        best = None
        for row in rows:
            if row.top_builds and (
                best is None or row.top_builds[0].projected_dps_index > best.top_builds[0].projected_dps_index
            ):
                best = row
        summaries.append(
            {
                "class_name": class_name,
                "spec_count": len(rows),
                "best_spec_name": display_spec_name(best.class_name, best.spec_name) if best else None,
                "source_best_spec_name": best.spec_name if best else None,
                "best_projected_dps_index": best.top_builds[0].projected_dps_index if best else None,
                "summary_note": "Derived from per-spec projected build rankings.",
            }
        )
    return tuple(summaries)


def render_markdown_report(report: MetaReport) -> str:
    data = report.to_dict()
    lines = [
        "# CoA Phase 1 Meta Report",
        "",
        "This report is a theorycraft projection. Projected DPS Index is not observed DPS.",
        "",
        "## Run",
        "",
        f"- Generated: `{data['generated_at']}`",
        f"- Schema: `{data['schema_version']}`",
        f"- Level: `{data['run_config']['level']}`",
        "",
    ]
    if data["warnings"]:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- `{warning}`" for warning in data["warnings"])
        lines.append("")
    lines.extend(["## Spec Results", ""])
    for result in data["spec_results"]:
        lines.append(f"### {result['class_name']} - {result['spec_name']}")
        lines.append(f"- Role: `{result['role']}`")
        if result["warnings"]:
            lines.extend(f"- Warning: `{warning}`" for warning in result["warnings"])
        lines.append("")
        lines.append("| Rank | Projected DPS Index | Sim DPS | Confidence | Selected Nodes |")
        lines.append("| --- | ---: | ---: | --- | --- |")
        for build in result["top_builds"]:
            nodes = ", ".join(node["name"] for node in build["selected_nodes"])
            sim_dps = build["simulation_result"]["dps"] if build.get("simulation_result") else ""
            lines.append(
                f"| {build['rank']} | {build['projected_dps_index']} | {sim_dps} | {build['confidence_label']} | {nodes} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html_report(
    report: MetaReport,
    asset_resolver: Any | None = None,
    entries_path: Path | str | None = None,
    db_tooltips_path: Path | str | None = None,
    builder_layout_root: Path | str | None = None,
) -> str:
    if entries_path is not None:
        from .guide_writer import render_guide_index_html

        return render_guide_index_html(
            report,
            entries_path=entries_path,
            db_tooltips_path=db_tooltips_path,
            asset_root=getattr(asset_resolver, "asset_root", None),
            builder_layout_root=builder_layout_root,
        )

    data = report.to_dict()
    warning_items = "".join(f"<li><code>{_html_escape(warning)}</code></li>" for warning in data["warnings"])
    sections: list[str] = []
    for result in data["spec_results"]:
        rows: list[str] = []
        spec_href = f"specs/{_html_escape(_spec_page_name(result))}"
        for build in result["top_builds"]:
            nodes = ", ".join(_html_escape(node["name"]) for node in build["selected_nodes"])
            sim_dps = build["simulation_result"]["dps"] if build.get("simulation_result") else ""
            rows.append(
                "<tr>"
                f"<td>{build['rank']}</td>"
                f"<td>{build['projected_dps_index']}</td>"
                f"<td>{sim_dps}</td>"
                f"<td>{_html_escape(build['confidence_label'])}</td>"
                f"<td>{nodes}</td>"
                "</tr>"
            )
        sections.append(
            "<section class=\"guide-card\">"
            f"<h2>{_html_escape(result['class_name'])} - {_html_escape(result['spec_name'])}</h2>"
            f"<p><strong>Role:</strong> <code>{_html_escape(result['role'])}</code></p>"
            f"<p><a href=\"{spec_href}\">Open spec guide</a></p>"
            "<table><thead><tr><th>Rank</th><th>Projected DPS Index</th><th>Sim DPS</th><th>Confidence</th><th>Selected Nodes</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "</section>"
        )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>CoA Phase 1 Meta Report</title>"
        "<style>body{font-family:Inter,system-ui,sans-serif;margin:0;background:#101820;color:#eef6f8;}a{color:#7bdff2;}header{padding:28px 32px;background:#162633;border-bottom:3px solid #34c6a4;}main{padding:24px 32px;}table{border-collapse:collapse;width:100%;margin-bottom:16px;}th,td{border:1px solid #34515f;padding:6px 8px;text-align:left;}th{background:#1f3848;}code{background:#243b4a;padding:1px 4px;border-radius:4px;}.guide-grid{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));}.guide-card{border:1px solid #34515f;border-radius:8px;padding:16px;background:#142430;}</style>"
        "</head><body>"
        "<header><h1>CoA Meta Guides</h1>"
        "<p>This report is a theorycraft projection. Projected DPS Index is not observed DPS.</p></header>"
        "<main class=\"guide-grid\">"
        f"<h2>Warnings</h2><ul>{warning_items}</ul>"
        f"{''.join(sections)}"
        "</main></body></html>"
    )


def render_spec_guide_html(report: MetaReport, result: SpecResult, asset_resolver: Any | None = None) -> str:
    data = result.to_dict()
    best = data["top_builds"][0] if data["top_builds"] else None
    rotation = _render_rotation_sections(best["rotation_summary"] if best else {})
    stat_priority = _render_stat_priority_report(best.get("stat_priority_report") or {}) if best else _render_stat_priority([])
    gear = _render_gear_recommendation_report(best.get("gear_recommendation_report") or {}) if best else _render_gear_recommendation({})
    warnings = "".join(f"<li><code>{_html_escape(warning)}</code></li>" for warning in data["warnings"])
    warning_section = f'<section class="panel"><h2>Warnings</h2><ul>{warnings}</ul></section>' if warnings else ""
    nodes = ""
    if best:
        nodes = "".join(
            f"<li>{_html_escape(node['name'])} <small>{_html_escape(node['tab_name'])}</small></li>"
            for node in best["selected_nodes"]
        )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{_html_escape(data['class_name'])} { _html_escape(data['spec_name']) } Guide</title>"
        "<style>body{font-family:Inter,system-ui,sans-serif;margin:0;background:#0f171d;color:#eef6f8;}a{color:#7bdff2}.spec-guide{max-width:1120px;margin:0 auto;padding:28px;}nav{margin-bottom:20px}.hero{border-left:5px solid #34c6a4;padding:18px 22px;background:#172632;border-radius:8px}.panel{margin:18px 0;padding:18px;border:1px solid #34515f;border-radius:8px;background:#13222d}.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));}code{background:#243b4a;padding:1px 4px;border-radius:4px}li{margin:6px 0}</style>"
        "</head><body><main class=\"spec-guide\">"
        "<nav><a href=\"../meta-report.html\">Back to index</a></nav>"
        "<section class=\"hero\">"
        f"<h1>{_html_escape(data['class_name'])} - {_html_escape(data['spec_name'])}</h1>"
        f"<p>Role: <code>{_html_escape(data['role'])}</code></p>"
        f"<p>{_html_escape(data['summary']['strengths'][0])}</p>"
        "</section>"
        "<section class=\"grid\">"
        f"<div class=\"panel\"><h2>Recommended Build</h2><ul>{nodes}</ul></div>"
        f"<div class=\"panel\"><h2>Stat Priority</h2>{stat_priority}</div>"
        f"<div class=\"panel\"><h2>Weapon and Armor</h2>{gear}</div>"
        "</section>"
        f"<section class=\"panel\"><h2>Rotation</h2>{rotation}</section>"
        f"{warning_section}"
        "</main></body></html>"
    )


def _render_rotation_sections(summary: dict[str, Any]) -> str:
    sections = summary.get("sections", {})
    if not sections:
        return "<p>No generated rotation actions were available.</p>"
    html: list[str] = []
    for name, actions in sections.items():
        items = "".join(
            f"<li>{_html_escape(action['action_name'])}"
            f"{' when ' + _html_escape(action['condition']) if action.get('condition') else ''}</li>"
            for action in actions
        )
        html.append(f"<h3>{_html_escape(name.replace('_', ' ').title())}</h3><ol>{items}</ol>")
    return "".join(html)


def _render_stat_priority(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>Stat priority is unavailable.</p>"
    items = "".join(
        f"<li><strong>{_html_escape(row['stat'].replace('_', ' ').title())}</strong> "
        f"<small>{_html_escape(row['reason'])}</small></li>"
        for row in rows[:8]
    )
    return f"<ol>{items}</ol>"


def _render_stat_priority_report(report: dict[str, Any]) -> str:
    if not report:
        return _render_stat_priority([])
    disclaimer = report.get("disclaimer")
    disclaimer_html = f"<p><strong>Warning:</strong> {_html_escape(disclaimer)}</p>" if disclaimer else ""
    groups: list[str] = []
    for group in report.get("groups", []):
        entries = "".join(
            f"<li><strong>{_html_escape(str(entry.get('stat', '')).replace('_', ' ').title())}</strong> "
            f"<small>{_html_escape(entry.get('reason', ''))}</small></li>"
            for entry in group.get("entries", [])
        )
        if entries:
            groups.append(f"<h3>{_html_escape(group.get('label') or group.get('group_id'))}</h3><ol>{entries}</ol>")
    if not groups:
        return _render_stat_priority([])
    return disclaimer_html + "".join(groups)


def _render_gear_recommendation(recommendation: dict[str, Any]) -> str:
    if not recommendation:
        return "<p>Gear recommendation is unavailable.</p>"
    weapons = ", ".join(recommendation.get("weapon_types", [])) or "unknown"
    armor = ", ".join(recommendation.get("armor_types", [])) or "unknown"
    warnings = "".join(f"<li><code>{_html_escape(warning)}</code></li>" for warning in recommendation.get("warnings", []))
    return (
        f"<p><strong>Weapons:</strong> {_html_escape(weapons)}</p>"
        f"<p><strong>Armor:</strong> {_html_escape(armor)}</p>"
        f"<ul>{warnings}</ul>"
    )


def _render_gear_recommendation_report(report: dict[str, Any]) -> str:
    if not report:
        return _render_gear_recommendation({})
    best_values = tuple(report.get("best_weapon_types", [])) + tuple(report.get("best_armor_types", []))
    available_values = tuple(report.get("available_weapon_types", [])) + tuple(report.get("available_armor_types", []))
    best = _render_inline_type_list(best_values)
    available = _render_inline_type_list(available_values)
    warnings = "".join(f"<li><code>{_html_escape(warning)}</code></li>" for warning in report.get("warnings", []))
    warnings_html = f"<ul>{warnings}</ul>" if warnings else ""
    return (
        f"<h3>Best targets for this spec</h3><p>{best}</p>"
        f"<h3>Available to this class</h3><p>{available}</p>"
        f"{warnings_html}"
    )


def _render_inline_type_list(values: tuple[str, ...]) -> str:
    unique_values = tuple(dict.fromkeys(value for value in values if value))
    if not unique_values:
        return "unknown"
    return _html_escape(", ".join(value.replace("_", " ").title() for value in unique_values))


def _spec_page_name(result: dict[str, Any]) -> str:
    return f"{slugify_key(result['class_name'])}-{slugify_key(result['spec_name'])}.html"


def write_report_outputs(
    report: MetaReport,
    out_dir: Path | str,
    formats: tuple[str, ...] = ("json", "md", "html"),
    asset_resolver: Any | None = None,
    entries_path: Path | str | None = None,
    db_tooltips_path: Path | str | None = None,
    builder_layout_root: Path | str | None = None,
) -> tuple[Path, ...]:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in formats:
        if fmt == "json":
            path = output_dir / "meta-report.json"
            path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        elif fmt == "md":
            path = output_dir / "meta-report.md"
            path.write_text(render_markdown_report(report), encoding="utf-8")
        elif fmt == "html":
            if entries_path is not None:
                from .guide_writer import write_guide_site

                written.extend(
                    write_guide_site(
                        report,
                        output_dir,
                        entries_path=entries_path,
                        db_tooltips_path=db_tooltips_path,
                        asset_root=getattr(asset_resolver, "asset_root", None),
                        builder_layout_root=builder_layout_root,
                    )
                )
                continue
            path = output_dir / "meta-report.html"
            path.write_text(render_html_report(report, asset_resolver=asset_resolver), encoding="utf-8")
            spec_dir = output_dir / "specs"
            spec_dir.mkdir(parents=True, exist_ok=True)
            for result in report.spec_results:
                spec_path = spec_dir / _spec_page_name(result.to_dict())
                spec_path.write_text(render_spec_guide_html(report, result, asset_resolver=asset_resolver), encoding="utf-8")
                written.append(spec_path)
        else:
            raise ValueError(f"Unsupported report format {fmt}")
        written.append(path)
    return tuple(written)


def _html_escape(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
