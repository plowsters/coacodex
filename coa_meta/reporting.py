from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .domain import TalentNode
from .repository import TalentRepository

META_REPORT_SCHEMA_VERSION = "coa-meta-report-v1"
DEFAULT_PUBLIC_ENCOUNTER = "baseline_single_target"
ENCOUNTER_ALIASES = {DEFAULT_PUBLIC_ENCOUNTER: "single_target"}
SHARED_TAB_NAMES = {"Class", "None"}


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
            if node.required_level > scope.level:
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
        if scope.level < 60 and any(node.tab_name == "Class" for node in repository.nodes_for_class(scope.class_name)):
            warnings.append("shared_class_level_gating_incomplete")
        return tuple(warnings)
