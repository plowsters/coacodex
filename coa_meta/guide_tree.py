from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from .builder_tree_layout import BuilderLayoutTree, BuilderTreeLayout
from .builds import BuildConfig, BuildRules
from .domain import SelectedRank, TalentNode, ValidationIssue
from .guide_models import GuideAsset, GuideNode, GuideNodeGate, GuideTree, GuideTreeEdge, GuideTreePanel, GuideTreeSnapshot
from .guide_tooltips import ascension_spell_url
from .repository import TalentRepository


def default_tree_levels(report_level: int) -> tuple[int, ...]:
    return tuple(sorted(level for level in {10, 20, 30, 40, 50, 60, int(report_level)} if level >= 1))


def build_guide_tree(
    *,
    repository: TalentRepository,
    class_name: str,
    spec_name: str,
    build_rank: int,
    build_label: str,
    selected_node_ids: tuple[int, ...],
    config: BuildConfig,
    spec_nodes: tuple[TalentNode, ...],
    levels: tuple[int, ...] | None = None,
    guide_nodes_by_id: Mapping[int, GuideNode] | None = None,
) -> GuideTree:
    guide_nodes_by_id = guide_nodes_by_id or {}
    node_ids = {node.entry_id for node in spec_nodes}
    selected_ids = {node_id for node_id in selected_node_ids if node_id in node_ids}
    max_row = max((node.row for node in spec_nodes), default=0)
    max_col = max((node.col for node in spec_nodes), default=0)
    snapshot_levels = levels or default_tree_levels(config.level)
    warnings: list[str] = []

    report_rules = _rules_for_level(repository, config, spec_nodes, config.level)
    report_selected = _paid_selected_ranks(repository, selected_ids, config.level)
    report_result = report_rules.validate(report_selected)
    report_state = report_result.state or report_rules.initial_state()
    issues_by_node = _issues_by_node(report_result.issues)
    available_ids = _available_node_ids(report_rules, report_state, spec_nodes, selected_ids)

    free_ids = set(report_state.free_node_ids)
    tree_nodes: list[GuideNode] = []
    for node in sorted(spec_nodes, key=lambda item: (item.tab_name != "Class", item.row, item.col, item.name)):
        state, reasons, _codes = classify_node_state(
            node=node,
            selected_ids=selected_ids,
            free_ids=free_ids,
            available_ids=available_ids,
            issues_by_node=issues_by_node,
        )
        base = guide_nodes_by_id.get(node.entry_id) or _guide_node_from_talent(node)
        tree_nodes.append(
            replace(
                base,
                row=node.row,
                col=node.col,
                node_type=node.node_type or "SpendCircle",
                max_rank=node.max_rank,
                rank=report_state.rank_for(node.entry_id),
                selected=node.entry_id in selected_ids and node.entry_id not in free_ids,
                free=node.entry_id in free_ids,
                required_ids=node.required_ids,
                connected_node_ids=node.connected_node_ids,
                required_tab_ae=node.required_tab_ae,
                required_tab_te=node.required_tab_te,
                availability_confidence=_availability_confidence(node),
                source_level=_availability_level(node, "source_required_level"),
                tooltip_required_level=_availability_level(node, "tooltip_required_level"),
                tree_state=state,
                gate_reasons=reasons,
            )
        )

    edges = _build_edges(spec_nodes, selected_ids, available_ids, warnings)
    snapshots = tuple(
        _build_snapshot(
            repository=repository,
            config=config,
            spec_nodes=spec_nodes,
            selected_ids=selected_ids,
            level=level,
        )
        for level in snapshot_levels
    )
    warnings.extend(issue.code for issue in report_result.issues)

    return GuideTree(
        tree_id=f"{_slug(class_name)}-{_slug(spec_name)}-{build_rank}",
        class_name=class_name,
        spec_name=spec_name,
        build_rank=build_rank,
        build_label=build_label,
        level=config.level,
        max_ae=config.max_ae,
        max_te=config.max_te,
        ae_spent=report_state.ae_spent,
        te_spent=report_state.te_spent,
        rows=max_row + 1,
        cols=max_col + 1,
        nodes=tuple(tree_nodes),
        edges=tuple(edges),
        snapshots=snapshots,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def build_guide_tree_panel(
    *,
    repository: TalentRepository,
    class_name: str,
    source_spec_name: str,
    display_spec_name: str,
    build_rank: int,
    build_label: str,
    selected_node_ids: tuple[int, ...],
    config: BuildConfig,
    spec_nodes: tuple[TalentNode, ...],
    levels: tuple[int, ...] | None = None,
    guide_nodes_by_id: Mapping[int, GuideNode] | None = None,
    builder_layout: BuilderTreeLayout | None = None,
    layout_required: bool = False,
    combined_tree: GuideTree | None = None,
) -> GuideTreePanel:
    combined = combined_tree or build_guide_tree(
        repository=repository,
        class_name=class_name,
        spec_name=source_spec_name,
        build_rank=build_rank,
        build_label=build_label,
        selected_node_ids=selected_node_ids,
        config=config,
        spec_nodes=spec_nodes,
        levels=levels,
        guide_nodes_by_id=guide_nodes_by_id,
    )
    warnings = list(combined.warnings)
    if layout_required and builder_layout is None:
        warnings.append("builder_layout_missing")
    trees = tuple(
        _split_tree_group(
            combined,
            tree_kind,
            layout_tree=builder_layout.tree_by_kind(tree_kind) if builder_layout else None,
            warnings=warnings,
        )
        for tree_kind in _TREE_GROUP_ORDER
    )
    return GuideTreePanel(
        tree_panel_id=combined.tree_id,
        class_name=class_name,
        source_spec_name=source_spec_name,
        display_spec_name=display_spec_name,
        build_rank=build_rank,
        build_label=build_label,
        level=config.level,
        max_ae=config.max_ae,
        max_te=config.max_te,
        trees=trees,
        snapshots=combined.snapshots,
        warnings=tuple(dict.fromkeys(warnings)),
    )


_TREE_GROUP_ORDER = ("ability_essence", "talent_essence", "level_passives")


def _split_tree_group(
    tree: GuideTree,
    tree_kind: str,
    *,
    layout_tree: BuilderLayoutTree | None = None,
    warnings: list[str],
) -> GuideTree:
    fallback_nodes = tuple(node for node in tree.nodes if _tree_kind_for_node(node) == tree_kind)
    nodes = _apply_layout_nodes(fallback_nodes, tree_kind=tree_kind, layout_tree=layout_tree, warnings=warnings)
    node_ids = {node.entry_id for node in nodes}
    edges = _apply_layout_edges(tree, node_ids=node_ids, layout_tree=layout_tree)
    rows = max((node.row or 0 for node in nodes), default=0) + 1
    cols = max((node.col or 0 for node in nodes), default=0) + 1
    layout_source = layout_tree.layout_source if layout_tree else "normalized_fallback"
    bounds = layout_tree.bounds.to_dict() if layout_tree else None
    return replace(
        tree,
        tree_id=f"{tree.tree_id}-{tree_kind}",
        tree_kind=tree_kind,
        layout_source=layout_source,
        bounds=bounds,
        rows=rows,
        cols=cols,
        nodes=nodes,
        edges=edges,
    )


def _apply_layout_nodes(
    fallback_nodes: tuple[GuideNode, ...],
    *,
    tree_kind: str,
    layout_tree: BuilderLayoutTree | None,
    warnings: list[str],
) -> tuple[GuideNode, ...]:
    if layout_tree is None:
        return fallback_nodes
    fallback_by_id = {node.entry_id: node for node in fallback_nodes}
    seen: set[int] = set()
    ordered: list[GuideNode] = []
    for layout_node in layout_tree.nodes:
        base = fallback_by_id.get(layout_node.entry_id)
        if base is None:
            continue
        expected_kind = _tree_kind_for_node(base)
        if expected_kind != tree_kind:
            warnings.append(f"layout_tree_kind_conflict:{base.entry_id}:{expected_kind}:{tree_kind}")
        ordered.append(
            replace(
                base,
                x=layout_node.x,
                y=layout_node.y,
                width=layout_node.width,
                height=layout_node.height,
            )
        )
        seen.add(layout_node.entry_id)
    for node in fallback_nodes:
        if node.entry_id in seen:
            continue
        warnings.append(f"layout_node_missing:{node.entry_id}")
        ordered.append(node)
    return tuple(ordered)


def _apply_layout_edges(
    tree: GuideTree,
    *,
    node_ids: set[int],
    layout_tree: BuilderLayoutTree | None,
) -> tuple[GuideTreeEdge, ...]:
    if layout_tree is None:
        return tuple(edge for edge in tree.edges if edge.source_id in node_ids and edge.target_id in node_ids)
    fallback_edges = {
        (edge.source_id, edge.target_id, edge.kind): edge
        for edge in tree.edges
    }
    edges: list[GuideTreeEdge] = []
    for layout_edge in layout_tree.edges:
        if layout_edge.source_entry_id not in node_ids or layout_edge.target_entry_id not in node_ids:
            continue
        fallback = fallback_edges.get((layout_edge.source_entry_id, layout_edge.target_entry_id, layout_edge.kind))
        edges.append(
            GuideTreeEdge(
                source_id=layout_edge.source_entry_id,
                target_id=layout_edge.target_entry_id,
                kind=layout_edge.kind,
                state=fallback.state if fallback else "inactive",
            )
        )
    return tuple(edges)


def _tree_kind_for_node(node: GuideNode) -> str:
    if node.tab_name == "Class" or node.ae_cost > 0:
        return "ability_essence"
    if node.ae_cost == 0 and node.te_cost == 0 and (node.col or 0) >= 10:
        return "level_passives"
    return "talent_essence"


def classify_node_state(
    *,
    node: TalentNode,
    selected_ids: set[int],
    free_ids: set[int],
    available_ids: set[int],
    issues_by_node: dict[int, tuple[ValidationIssue, ...]],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if node.entry_id in free_ids:
        return "free", tuple(), tuple()
    node_issues = issues_by_node.get(node.entry_id, tuple())
    if node.entry_id in selected_ids and not node_issues:
        return "selected", tuple(), tuple()
    if node.entry_id in selected_ids and node_issues:
        reasons = tuple(issue.message for issue in node_issues)
        codes = tuple(issue.code for issue in node_issues)
        return _state_from_issue_codes(codes, selected=True), reasons, codes
    if node.entry_id in available_ids:
        return "available", tuple(), tuple()
    if node_issues:
        reasons = tuple(issue.message for issue in node_issues)
        codes = tuple(issue.code for issue in node_issues)
        return _state_from_issue_codes(codes, selected=False), reasons, codes
    return "inactive", tuple(), tuple()


def _build_snapshot(
    *,
    repository: TalentRepository,
    config: BuildConfig,
    spec_nodes: tuple[TalentNode, ...],
    selected_ids: set[int],
    level: int,
) -> GuideTreeSnapshot:
    rules = _rules_for_level(repository, config, spec_nodes, level)
    selected_at_level = {
        node.entry_id
        for node in spec_nodes
        if node.entry_id in selected_ids and node.required_level <= level
    }
    selected_ranks = _paid_selected_ranks(repository, selected_at_level, level)
    result = rules.validate(selected_ranks)
    state = result.state or rules.initial_state()
    available_ids = _available_node_ids(rules, state, spec_nodes, selected_at_level)
    issues_by_node = _issues_by_node(result.issues)
    gated_nodes: list[GuideNodeGate] = []
    for node in spec_nodes:
        if node.entry_id in state.selected_ids or node.entry_id in available_ids:
            continue
        test_result = rules.can_add(state, node, 1) if node.paid else rules.validate(selected_ranks)
        issues = issues_by_node.get(node.entry_id, tuple()) or test_result.issues
        if not issues:
            continue
        state_name, reasons, codes = classify_node_state(
            node=node,
            selected_ids=selected_at_level,
            free_ids=set(state.free_node_ids),
            available_ids=available_ids,
            issues_by_node={node.entry_id: tuple(issues)},
        )
        gated_nodes.append(
            GuideNodeGate(
                node_id=node.entry_id,
                state=state_name,
                reasons=reasons,
                issue_codes=codes,
            )
        )
    return GuideTreeSnapshot(
        level=level,
        max_ae=config.max_ae,
        max_te=config.max_te,
        ae_spent=state.ae_spent,
        te_spent=state.te_spent,
        selected_node_ids=tuple(sorted(state.selected_ids & selected_ids)),
        free_node_ids=tuple(sorted(state.free_node_ids)),
        available_node_ids=tuple(sorted(available_ids)),
        gated_nodes=tuple(gated_nodes),
    )


def _rules_for_level(
    repository: TalentRepository,
    config: BuildConfig,
    spec_nodes: tuple[TalentNode, ...],
    level: int,
) -> BuildRules:
    return BuildRules(
        repository,
        BuildConfig(
            class_name=config.class_name,
            level=level,
            max_ae=config.max_ae,
            max_te=config.max_te,
            allowed_node_ids=tuple(sorted(node.entry_id for node in spec_nodes)),
        ),
    )


def _paid_selected_ranks(repository: TalentRepository, selected_ids: set[int], level: int) -> list[SelectedRank]:
    ranks: list[SelectedRank] = []
    for node_id in sorted(selected_ids):
        node = repository.get_node(node_id)
        if node is None or not node.paid or node.required_level > level:
            continue
        ranks.append(SelectedRank(node_id, 1))
    return ranks


def _available_node_ids(
    rules: BuildRules,
    state,
    spec_nodes: tuple[TalentNode, ...],
    selected_ids: set[int],
) -> set[int]:
    available: set[int] = set()
    for node in spec_nodes:
        if node.entry_id in state.selected_ids or node.entry_id in selected_ids:
            continue
        if not node.paid:
            continue
        result = rules.can_add(state, node, 1)
        if result.valid:
            available.add(node.entry_id)
    return available


def _build_edges(
    spec_nodes: tuple[TalentNode, ...],
    selected_ids: set[int],
    available_ids: set[int],
    warnings: list[str],
) -> list[GuideTreeEdge]:
    node_ids = {node.entry_id for node in spec_nodes}
    edges: dict[tuple[int, int, str], GuideTreeEdge] = {}
    for node in spec_nodes:
        for target_id in node.connected_node_ids:
            if target_id not in node_ids:
                warnings.append(f"tree_edge_missing_target:{node.entry_id}:{target_id}")
                continue
            source_id, dest_id = sorted((node.entry_id, target_id))
            edges[(source_id, dest_id, "connection")] = GuideTreeEdge(
                source_id=source_id,
                target_id=dest_id,
                kind="connection",
                state=_edge_state(source_id, dest_id, selected_ids, available_ids),
            )
        for required_id in node.required_ids:
            if required_id not in node_ids:
                warnings.append(f"tree_requirement_missing_source:{required_id}:{node.entry_id}")
                continue
            edges[(required_id, node.entry_id, "requirement")] = GuideTreeEdge(
                source_id=required_id,
                target_id=node.entry_id,
                kind="requirement",
                state=_edge_state(required_id, node.entry_id, selected_ids, available_ids),
            )
    return [edges[key] for key in sorted(edges)]


def _edge_state(source_id: int, target_id: int, selected_ids: set[int], available_ids: set[int]) -> str:
    if source_id in selected_ids and target_id in selected_ids:
        return "selected"
    if source_id in selected_ids and target_id in available_ids:
        return "available"
    if target_id in selected_ids and source_id not in selected_ids:
        return "gated"
    return "inactive"


def _issues_by_node(issues: tuple[ValidationIssue, ...]) -> dict[int, tuple[ValidationIssue, ...]]:
    out: dict[int, list[ValidationIssue]] = {}
    for issue in issues:
        if issue.node_id is None:
            continue
        out.setdefault(issue.node_id, []).append(issue)
    return {node_id: tuple(values) for node_id, values in out.items()}


def _state_from_issue_codes(codes: tuple[str, ...], *, selected: bool) -> str:
    if "level_required" in codes:
        return "gated_level"
    if "tab_ae_gate_unmet" in codes:
        return "gated_tab_ae"
    if "tab_te_gate_unmet" in codes:
        return "gated_tab_te"
    if "required_node_missing" in codes:
        return "gated_required_node"
    if "ae_budget_exceeded" in codes or "te_budget_exceeded" in codes:
        return "over_budget"
    return "over_budget" if selected else "inactive"


def _guide_node_from_talent(node: TalentNode) -> GuideNode:
    asset = GuideAsset(
        asset_id=f"icon:{_slug(node.name) or node.entry_id}",
        kind="icon",
        label=node.name,
        href=None,
        source="placeholder",
        missing=True,
    )
    return GuideNode(
        entry_id=node.entry_id,
        spell_id=node.spell_id,
        name=node.name,
        class_name=node.class_name,
        tab_name=node.tab_name,
        essence_kind=node.essence_kind,
        required_level=node.required_level,
        ae_cost=node.ae_cost,
        te_cost=node.te_cost,
        tags=tuple(node.tags),
        active=not node.is_passive,
        db_url=ascension_spell_url(node.spell_id),
        tooltip_id=f"spell:{node.spell_id}" if node.spell_id is not None else f"entry:{node.entry_id}",
        asset=asset,
    )


def _availability_confidence(node: TalentNode) -> str:
    return str(node.availability.get("level_confidence") or node.availability.get("confidence") or "unknown")


def _availability_level(node: TalentNode, key: str) -> int | None:
    value = node.availability.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(char.lower() if char.isalnum() else "-" for char in value).split("-") if part)
