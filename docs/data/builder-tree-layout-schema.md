# Builder Tree Layout Schema

Schema version: `coa-builder-tree-layout-v1`

This artifact captures the CoA Builder's visual tree geometry so the static guide renderer can reproduce the in-game/builder structure instead of recalculating a rough grid from normalized rows and columns.

The artifact is desktop-first. Tree geometry should preserve captured coordinates for 1080p, 2k, and 4k desktop layouts. Narrow containers should scroll horizontally; the tree component should not reflow or resize nodes for mobile.

## Top-Level Object

- `schema_version`: always `coa-builder-tree-layout-v1`
- `class_name`: player-facing class name, such as `Venomancer`
- `source_spec_name`: builder/API spec tab name, such as `Stalking`
- `display_spec_name`: user-facing spec name after legacy rename handling
- `captured_at`: UTC timestamp for the capture
- `source_url`: builder URL or DB URL used for capture
- `layout_source`: `builder_runtime`, `builder_dom`, or `normalized_fallback`
- `viewport`: capture viewport metadata
- `trees`: three tree groups
- `warnings`: capture or parser warnings

## Tree Groups

Every layout should include these `tree_kind` values:

- `ability_essence`: class-wide Ability Essence tree
- `talent_essence`: specialization Talent Essence tree
- `level_passives`: automatic level-gated passive lane

Each tree contains:

- `tree_kind`
- `layout_source`
- `bounds`: `{ "x", "y", "width", "height" }` for the tree container
- `nodes`: captured node boxes
- `edges`: captured or inferred prerequisite lines

## Nodes

Each node contains:

- `entry_id`: normalized entry ID used for joins
- `spell_id`: Ascension spell ID when known
- `name`: display name
- `x`, `y`: node position inside the tree group
- `width`, `height`: captured node dimensions

The parser assigns `tree_kind` to each node from its parent tree. Later guide tree snapshots still own selected/free/available/gated state by `entry_id`.

## Edges

Each edge contains:

- `source_entry_id`
- `target_entry_id`
- `kind`: usually `requires`

Edges represent visual/prerequisite links from the builder. If the capture script cannot prove an edge source, it should omit the edge and emit a warning rather than inventing a connection.

## Fallbacks

If no builder layout is available, guide generation may fall back to normalized row/column layout and emit `builder_layout_missing`.

If a selected or renderable normalized node is missing from a loaded layout, guide generation should emit `layout_node_missing:<entry_id>` and place the node in a deterministic fallback position inside the appropriate tree group.
