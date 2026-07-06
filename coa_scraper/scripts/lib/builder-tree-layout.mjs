import fs from "node:fs";
import path from "node:path";

export const BUILDER_TREE_LAYOUT_SCHEMA_VERSION = "coa-builder-tree-layout-v1";
export const BUILDER_TREE_KINDS = ["ability_essence", "talent_essence", "level_passives"];

const DEFAULT_LAYOUT = {
  nodeWidth: 64,
  nodeHeight: 64,
  padding: 24,
  colSpacing: 92,
  rowSpacing: 92,
  passiveX: 24
};

const DEFAULT_ENTRIES_PATHS = [
  "dist/coa_entries.jsonl",
  "coa_scraper/dist/coa_entries.jsonl"
];

function numberValue(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function textValue(value) {
  return String(value || "");
}

function idArray(value) {
  return Array.isArray(value)
    ? value.map(item => numberValue(item)).filter(item => item)
    : [];
}

function sameName(left, right) {
  return textValue(left).toLowerCase() === textValue(right).toLowerCase();
}

function isLevelPassiveEntry(entry) {
  const aeCost = numberValue(entry.ae_cost);
  const teCost = numberValue(entry.te_cost);
  return (
    textValue(entry.tab_name) !== "Class" &&
    aeCost === 0 &&
    teCost === 0 &&
    numberValue(entry.col) >= 10
  );
}

export function treeKindForNormalizedEntry(entry) {
  if (isLevelPassiveEntry(entry)) return "level_passives";
  if (
    textValue(entry.tab_name) === "Class" ||
    numberValue(entry.ae_cost) > 0
  ) {
    return "ability_essence";
  }
  return "talent_essence";
}

function nodeSortKey(entry, treeKind) {
  if (treeKind === "level_passives") {
    return [
      numberValue(entry.row),
      numberValue(entry.required_level),
      textValue(entry.name)
    ];
  }
  return [
    numberValue(entry.row),
    numberValue(entry.col),
    textValue(entry.name)
  ];
}

function compareEntries(left, right, treeKind) {
  const leftKey = nodeSortKey(left, treeKind);
  const rightKey = nodeSortKey(right, treeKind);
  for (let index = 0; index < leftKey.length; index++) {
    const leftValue = leftKey[index];
    const rightValue = rightKey[index];
    if (typeof leftValue === "number" && typeof rightValue === "number" && leftValue !== rightValue) {
      return leftValue - rightValue;
    }
    const textCompare = String(leftValue).localeCompare(String(rightValue));
    if (textCompare !== 0) return textCompare;
  }
  return numberValue(left.entry_id) - numberValue(right.entry_id);
}

function positionForEntry(entry, treeKind, layout) {
  const row = numberValue(entry.row);
  const col = numberValue(entry.col);
  if (treeKind === "level_passives") {
    return {
      x: layout.passiveX,
      y: layout.padding + row * layout.rowSpacing
    };
  }
  return {
    x: layout.padding + col * layout.colSpacing,
    y: layout.padding + row * layout.rowSpacing
  };
}

function layoutNode(entry, treeKind, layout) {
  const position = positionForEntry(entry, treeKind, layout);
  return {
    entry_id: numberValue(entry.entry_id),
    spell_id: entry.spell_id === null || entry.spell_id === undefined ? null : numberValue(entry.spell_id),
    name: textValue(entry.name),
    x: position.x,
    y: position.y,
    width: layout.nodeWidth,
    height: layout.nodeHeight
  };
}

function treeBounds(nodes, layout) {
  if (!nodes.length) {
    return {
      x: 0,
      y: 0,
      width: layout.nodeWidth + layout.padding * 2,
      height: layout.nodeHeight + layout.padding * 2
    };
  }
  const width = Math.max(...nodes.map(node => node.x + node.width)) + layout.padding;
  const height = Math.max(...nodes.map(node => node.y + node.height)) + layout.padding;
  return {
    x: 0,
    y: 0,
    width,
    height
  };
}

function edgeKey(sourceId, targetId, kind) {
  if (kind === "connection") {
    const [left, right] = [sourceId, targetId].sort((a, b) => a - b);
    return `${left}:${right}:${kind}`;
  }
  return `${sourceId}:${targetId}:${kind}`;
}

function buildEdges(entries) {
  const byId = new Map(entries.map(entry => [numberValue(entry.entry_id), entry]));
  const edges = new Map();
  for (const entry of entries) {
    const sourceId = numberValue(entry.entry_id);
    for (const connectedId of idArray(entry.connected_node_ids)) {
      if (!byId.has(connectedId)) continue;
      const [left, right] = [sourceId, connectedId].sort((a, b) => a - b);
      edges.set(edgeKey(left, right, "connection"), {
        source_entry_id: left,
        target_entry_id: right,
        kind: "connection"
      });
    }
    for (const requiredId of idArray(entry.required_ids)) {
      if (!byId.has(requiredId)) continue;
      edges.set(edgeKey(requiredId, sourceId, "requirement"), {
        source_entry_id: requiredId,
        target_entry_id: sourceId,
        kind: "requirement"
      });
    }
  }
  return [...edges.values()].sort((left, right) =>
    left.source_entry_id - right.source_entry_id ||
    left.target_entry_id - right.target_entry_id ||
    left.kind.localeCompare(right.kind)
  );
}

function normalizedRowsForSpec(rows, className, specName) {
  return rows.filter(row =>
    sameName(row.class_name, className) &&
    (textValue(row.tab_name) === "Class" || sameName(row.tab_name, specName))
  );
}

export function layoutFromNormalizedEntries(rows, options = {}) {
  const className = options.className || "";
  const specName = options.specName || "";
  const layout = { ...DEFAULT_LAYOUT, ...(options.layout || {}) };
  const selectedRows = normalizedRowsForSpec(rows, className, specName);
  const warnings = [];
  if (!selectedRows.length) {
    warnings.push("normalized_builder_rows_not_found");
  }

  const rowsByKind = new Map(BUILDER_TREE_KINDS.map(kind => [kind, []]));
  for (const row of selectedRows) {
    rowsByKind.get(treeKindForNormalizedEntry(row)).push(row);
  }

  const trees = BUILDER_TREE_KINDS.map(treeKind => {
    const entries = rowsByKind.get(treeKind).slice().sort((left, right) => compareEntries(left, right, treeKind));
    const nodes = entries.map(entry => layoutNode(entry, treeKind, layout));
    return {
      tree_kind: treeKind,
      layout_source: "builder_grid",
      bounds: treeBounds(nodes, layout),
      nodes,
      edges: buildEdges(entries)
    };
  });

  return {
    schema_version: BUILDER_TREE_LAYOUT_SCHEMA_VERSION,
    class_name: className,
    source_spec_name: specName,
    display_spec_name: specName,
    captured_at: options.capturedAt || new Date().toISOString(),
    source_url: options.sourceUrl || "",
    layout_source: "builder_grid",
    viewport: options.viewport || { width: 1920, height: 1080 },
    trees,
    warnings
  };
}

export function layoutHasNodes(layout) {
  return Boolean(layout?.trees?.some(tree => Array.isArray(tree.nodes) && tree.nodes.length > 0));
}

export function readNormalizedEntries(entriesPath) {
  const text = fs.readFileSync(entriesPath, "utf8");
  return text
    .split(/\r?\n/)
    .filter(line => line.trim())
    .map(line => JSON.parse(line));
}

export function resolveNormalizedEntriesPath(requestedPath = "", cwd = process.cwd()) {
  const candidates = requestedPath ? [requestedPath] : DEFAULT_ENTRIES_PATHS;
  for (const candidate of candidates) {
    const resolved = path.resolve(cwd, candidate);
    if (fs.existsSync(resolved)) return resolved;
  }
  return "";
}
