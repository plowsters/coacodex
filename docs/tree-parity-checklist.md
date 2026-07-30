# CoA Builder Tree Parity Checklist

> Status: optional spot-check. CoA Builder DOM/screenshot parity was evaluated and judged unnecessary — the current normalized tree-generation method renders faithfully across specs (see [DECISIONS.md](DECISIONS.md) Decision 17). This checklist is retained only for investigating a spec that ever renders poorly; it is not a required M1.11 exit step.

First target: `Venomancer / Stalking`

Use this checklist if a browser capture is ever needed to diagnose a rendering issue. The unit tests should remain browser-independent.

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

- `Venomancer / Stalking`: no parity issues observed; current generation renders faithfully across specs. Optional browser capture not run.
