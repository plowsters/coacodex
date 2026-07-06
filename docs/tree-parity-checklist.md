# CoA Builder Tree Parity Checklist

First target: `Venomancer / Stalking`

Use this checklist when a browser capture is available. The unit tests should remain browser-independent.

## Capture

1. Capture the official builder layout:

   ```bash
   npm --prefix coa_scraper run capture:tree-layout -- \
     --class Venomancer \
     --spec Stalking \
     --out coa_scraper/reports/tree_layout \
     --screenshots coa_scraper/reports/tree_layout/screenshots \
     --viewport 1920x1080
   ```

2. If automatic class/spec selection misses the right state, rerun with:

   ```bash
   npm --prefix coa_scraper run capture:tree-layout -- \
     --class Venomancer \
     --spec Stalking \
     --out coa_scraper/reports/tree_layout \
     --screenshots coa_scraper/reports/tree_layout/screenshots \
     --viewport 1920x1080 \
     --pause-for-manual-selection
   ```

## Generate Guide

Generate the guide with the captured layout root:

```bash
PYTHONPATH=. python -m coa_meta meta \
  --entries coa_scraper/dist/coa_entries.jsonl \
  --classes coa_scraper/dist/coa_classes.json \
  --db-tooltips coa_scraper/dist/coa_db_spell_tooltips.jsonl \
  --builder-layout-root coa_scraper/reports/tree_layout \
  --out reports/meta \
  --format html
```

## Manual Comparison

For each target spec:

- [ ] Ability Essence tree is separate from the Talent Essence tree.
- [ ] Level passives render as a straight passive lane.
- [ ] Node order matches the CoA Builder screenshot.
- [ ] Node spacing matches the CoA Builder screenshot closely enough for desktop guide use.
- [ ] Required/prerequisite links match the CoA Builder screenshot.
- [ ] Selected nodes, available nodes, gated nodes, and free passives visually update when changing guide level.
- [ ] The tree scrolls horizontally in narrow containers instead of reflowing or resizing.
- [ ] Hover tooltips still open for every visible talent/ability node.

## Notes

Record any mismatches here before changing the renderer:

- `Venomancer / Stalking`: pending first browser capture.
