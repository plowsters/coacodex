export function extractLevelText(text) {
  const match = String(text || "").match(/\bLevel\s+(\d+)\b/i);
  return match ? Number(match[1]) : null;
}

export function classifySourceCategory(node) {
  if (!node || !node.tab_name) {
    return "unknown";
  }
  if (node.tab_name === "Class") {
    return "class_pool";
  }
  if (node.tab_name === "None") {
    return "metadata_only";
  }
  return "spec_tree";
}

export function sourceConfidenceFor(category) {
  if (category === "spec_tree" || category === "class_pool") {
    return "high";
  }
  if (category === "metadata_only") {
    return "medium";
  }
  return "low";
}

export function deriveAvailability({
  builderRequiredLevel,
  builderTooltipText,
  dbTooltipLevel = null
}) {
  const builderLevel = Number(builderRequiredLevel || 0);
  const tooltipLevel = extractLevelText(builderTooltipText);
  const notes = [];

  if (builderLevel > 0) {
    if (dbTooltipLevel !== null && dbTooltipLevel !== builderLevel) {
      notes.push("db_tooltip_level_conflicts_with_builder_required_level");
    }
    return {
      builder_required_level: builderLevel,
      tooltip_required_level: tooltipLevel,
      db_tooltip_required_level: dbTooltipLevel,
      effective_required_level: builderLevel,
      level_source: "builder_required_level",
      level_confidence: "high",
      notes
    };
  }

  if (dbTooltipLevel !== null) {
    notes.push("builder_required_level_zero_but_tooltip_has_level");
    return {
      builder_required_level: builderLevel,
      tooltip_required_level: tooltipLevel,
      db_tooltip_required_level: dbTooltipLevel,
      effective_required_level: dbTooltipLevel,
      level_source: "db_tooltip",
      level_confidence: "medium",
      notes
    };
  }

  if (tooltipLevel !== null) {
    notes.push("builder_required_level_zero_but_tooltip_has_level");
    return {
      builder_required_level: builderLevel,
      tooltip_required_level: tooltipLevel,
      db_tooltip_required_level: null,
      effective_required_level: tooltipLevel,
      level_source: "builder_tooltip",
      level_confidence: "medium",
      notes
    };
  }

  return {
    builder_required_level: builderLevel,
    tooltip_required_level: null,
    db_tooltip_required_level: null,
    effective_required_level: builderLevel,
    level_source: builderLevel === 0 ? "builder_required_level_zero_or_unknown" : "builder_required_level",
    level_confidence: builderLevel === 0 ? "low" : "high",
    notes: builderLevel === 0 ? ["required_level_zero_means_available_or_unknown"] : []
  };
}

export function summarizeMetadataTabs(classes, entries) {
  const nodeTabs = new Set(
    entries.map(entry => `${entry.class_name}\t${entry.tab_id}\t${entry.tab_name}`)
  );
  const tabs = [];

  for (const cls of classes || []) {
    for (const tab of cls.tabs || []) {
      const key = `${cls.class_name}\t${tab.tab_id}\t${tab.tab_name}`;
      tabs.push({
        class_name: cls.class_name,
        tab_id: tab.tab_id,
        tab_name: tab.tab_name,
        sort_order: tab.sort_order,
        nominal_essence_kind: tab.nominal_essence_kind,
        has_nodes: nodeTabs.has(key)
      });
    }
  }

  return {
    schema_version: "coa-metadata-tab-report-v1",
    tab_count: tabs.length,
    tabs_without_nodes: tabs.filter(tab => !tab.has_nodes),
    tabs
  };
}
