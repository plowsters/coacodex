from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .apl import generate_apl
from .apl_profiles import load_apl_profile_by_role
from .builds import BuildConfig, BuildRules
from .domain import TalentNode
from .profiles import load_profile_by_role
from .repository import TalentRepository
from .scoring import TheoryScorer
from .search import BuildSearchConfig, BuildSearcher

META_REPORT_SCHEMA_VERSION = "coa-meta-report-v1"
DEFAULT_PUBLIC_ENCOUNTER = "baseline_single_target"
ENCOUNTER_ALIASES = {DEFAULT_PUBLIC_ENCOUNTER: "single_target"}
SHARED_TAB_NAMES = {"Class", "None"}
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


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
    role: str = "dps"
    top: int = 3
    beam_width: int = 5
    branch_width: int = 10
    require_budget_fraction: float = 0.7
    max_ae: int = 26
    max_te: int = 25

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
        }


@dataclass(frozen=True)
class BuildReport:
    rank: int
    projected_dps_index: float
    confidence_label: str
    selected_nodes: tuple[dict[str, Any], ...]
    score_breakdown: dict[str, Any]
    generated_apl: dict[str, Any]
    explanation: dict[str, Any]
    provenance: dict[str, Any]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "projected_dps_index": self.projected_dps_index,
            "confidence_label": self.confidence_label,
            "selected_nodes": list(self.selected_nodes),
            "score_breakdown": self.score_breakdown,
            "generated_apl": self.generated_apl,
            "explanation": self.explanation,
            "provenance": self.provenance,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SpecResult:
    class_name: str
    spec_id: int
    spec_name: str
    level: int
    encounter_profile_id: str
    search_profile_id: str
    scoring_profile_id: str
    apl_profile_id: str
    top_builds: tuple[BuildReport, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "level": self.level,
            "encounter_profile_id": self.encounter_profile_id,
            "search_profile_id": self.search_profile_id,
            "scoring_profile_id": self.scoring_profile_id,
            "apl_profile_id": self.apl_profile_id,
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
        search_results = BuildSearcher(repository, rules).search(
            BuildSearchConfig(
                top=max(scope.top * 3, scope.top),
                beam_width=self.config.beam_width,
                branch_width=self.config.branch_width,
                require_budget_fraction=self.config.require_budget_fraction,
            )
        )
        scoring_profile, scoring_warnings = load_profile_by_role(
            scope.class_name,
            scope.spec_key,
            self.config.role,
            scope.scoring_encounter,
        )
        apl_profile, apl_warnings = load_apl_profile_by_role(scope.class_name, scope.spec_key, self.config.role)
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
        top_builds: list[BuildReport] = []
        for index, (result, scored) in enumerate(scored_rows[: scope.top], start=1):
            assert result.state is not None
            apl_doc = generate_apl(
                result.state,
                repository,
                apl_profile,
                encounter=scope.scoring_encounter,
                profile_warnings=apl_warnings,
            )
            selected_nodes = tuple(_node_to_report(repository.node_by_id(node_id)) for node_id in sorted(result.state.selected_ids))
            top_builds.append(
                BuildReport(
                    rank=index,
                    projected_dps_index=scored.projected_dps_index,
                    confidence_label=scored.confidence,
                    selected_nodes=selected_nodes,
                    score_breakdown=scored.to_dict(),
                    generated_apl=apl_doc.to_dict(),
                    explanation={"score_components": [component.__dict__ for component in scored.components]},
                    provenance={
                        "normalized_schema": "coa-normalized-v1",
                        "scoring_profile_id": scoring_profile.profile_id,
                        "apl_profile_id": apl_profile.profile_id,
                    },
                    warnings=tuple(scoring_warnings + list(scored.warnings) + list(apl_doc.warnings)),
                )
            )
        if not top_builds:
            warnings.append("no_valid_builds_found")
        return SpecResult(
            class_name=scope.class_name,
            spec_id=scope.spec_id,
            spec_name=scope.spec_name,
            level=scope.level,
            encounter_profile_id=scope.encounter_profile_id,
            search_profile_id=scope.search_profile_id,
            scoring_profile_id=scoring_profile.profile_id,
            apl_profile_id=apl_profile.profile_id,
            top_builds=tuple(top_builds),
            warnings=tuple(warnings),
        )


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
                "best_spec_name": best.spec_name if best else None,
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
        if result["warnings"]:
            lines.extend(f"- Warning: `{warning}`" for warning in result["warnings"])
        lines.append("")
        lines.append("| Rank | Projected DPS Index | Confidence | Selected Nodes |")
        lines.append("| --- | ---: | --- | --- |")
        for build in result["top_builds"]:
            nodes = ", ".join(node["name"] for node in build["selected_nodes"])
            lines.append(
                f"| {build['rank']} | {build['projected_dps_index']} | {build['confidence_label']} | {nodes} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html_report(report: MetaReport, asset_resolver: Any | None = None) -> str:
    data = report.to_dict()
    warning_items = "".join(f"<li><code>{_html_escape(warning)}</code></li>" for warning in data["warnings"])
    sections: list[str] = []
    for result in data["spec_results"]:
        rows: list[str] = []
        for build in result["top_builds"]:
            nodes = ", ".join(_html_escape(node["name"]) for node in build["selected_nodes"])
            rows.append(
                "<tr>"
                f"<td>{build['rank']}</td>"
                f"<td>{build['projected_dps_index']}</td>"
                f"<td>{_html_escape(build['confidence_label'])}</td>"
                f"<td>{nodes}</td>"
                "</tr>"
            )
        sections.append(
            "<section>"
            f"<h2>{_html_escape(result['class_name'])} - {_html_escape(result['spec_name'])}</h2>"
            "<table><thead><tr><th>Rank</th><th>Projected DPS Index</th><th>Confidence</th><th>Selected Nodes</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "</section>"
        )
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>CoA Phase 1 Meta Report</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:24px;}table{border-collapse:collapse;width:100%;margin-bottom:24px;}th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;}th{background:#f4f4f4;}code{background:#eee;padding:1px 4px;}</style>"
        "</head><body>"
        "<h1>CoA Phase 1 Meta Report</h1>"
        "<p>This report is a theorycraft projection. Projected DPS Index is not observed DPS.</p>"
        f"<h2>Warnings</h2><ul>{warning_items}</ul>"
        f"{''.join(sections)}"
        "</body></html>"
    )


def write_report_outputs(
    report: MetaReport,
    out_dir: Path | str,
    formats: tuple[str, ...] = ("json", "md", "html"),
    asset_resolver: Any | None = None,
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
            path = output_dir / "meta-report.html"
            path.write_text(render_html_report(report, asset_resolver=asset_resolver), encoding="utf-8")
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
