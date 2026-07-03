#!/usr/bin/env bash
set -euo pipefail

# run-coa-postcapture.sh
# Run from the coa_scraper project root, after scrape-coa-network.mjs has produced:
#   data/coa.har
#   data/snapshots/final-page-content.html
#   data/snapshots/runtime-dump.json and/or final-runtime-dump.json
#
# Example:
#   chmod +x run-coa-postcapture.sh
#   ./run-coa-postcapture.sh
#
# Or if saved under scripts/:
#   chmod +x scripts/run-coa-postcapture.sh
#   ./scripts/run-coa-postcapture.sh
#
# Optional paths:
#   ./run-coa-postcapture.sh data reports dist

ROOT_DIR="$(pwd)"
DATA_DIR="${1:-data}"
REPORTS_DIR="${2:-reports}"
DIST_DIR="${3:-dist}"
SCRIPTS_DIR="${SCRIPTS_DIR:-scripts}"

HAR_PATH="$DATA_DIR/coa.har"
SNAPSHOT_DIR="$DATA_DIR/snapshots"
FINAL_HTML="$SNAPSHOT_DIR/final-page-content.html"
INITIAL_HTML="$SNAPSHOT_DIR/initial-page-content.html"
RUNTIME_DUMP="$SNAPSHOT_DIR/runtime-dump.json"
FINAL_RUNTIME_DUMP="$SNAPSHOT_DIR/final-runtime-dump.json"

mkdir -p "$REPORTS_DIR" "$DIST_DIR"

need_file() {
  local file="$1"
  local hint="$2"

  if [[ ! -s "$file" ]]; then
    echo "ERROR: Missing or empty file: $file" >&2
    echo "Hint: $hint" >&2
    exit 1
  fi
}

need_cmd() {
  local cmd="$1"

  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: Required command not found: $cmd" >&2
    exit 1
  fi
}

run_step() {
  local name="$1"
  shift

  echo
  echo "===== $name ====="
  echo "+ $*"
  "$@"
}

run_optional_step() {
  local name="$1"
  shift

  echo
  echo "===== $name ====="
  echo "+ $*"

  if ! "$@"; then
    echo "WARNING: '$name' failed, continuing because this step is diagnostic/non-canonical." >&2
  fi
}

need_cmd node
need_cmd bash
need_cmd rg

need_file "$HAR_PATH" \
  "Run scripts/scrape-coa-network.mjs first and complete the manual browser-click capture."

# The payload extractor needs the final rendered HTML if available. If the final file is
# missing, fall back to the initial snapshot, but final is preferred because it may contain
# more rendered node labels after manual class/tab clicks.
if [[ -s "$FINAL_HTML" ]]; then
  HTML_FOR_PAYLOAD="$FINAL_HTML"
else
  need_file "$INITIAL_HTML" \
    "Expected final-page-content.html or initial-page-content.html under $SNAPSHOT_DIR."

  HTML_FOR_PAYLOAD="$INITIAL_HTML"
  echo "WARNING: $FINAL_HTML missing; falling back to $INITIAL_HTML" >&2
fi

# Prefer the final runtime dump if it exists, because it reflects any manual tab/class clicks.
if [[ -s "$FINAL_RUNTIME_DUMP" ]]; then
  RUNTIME_FOR_ROSTER="$FINAL_RUNTIME_DUMP"
else
  need_file "$RUNTIME_DUMP" \
    "Expected runtime-dump.json or final-runtime-dump.json under $SNAPSHOT_DIR."

  RUNTIME_FOR_ROSTER="$RUNTIME_DUMP"
fi

# Check that all scripts exist before doing any real work.
for script in \
  coa-diagnose.sh \
  extract-coa-builder-payload.mjs \
  summarize-coa-payload.mjs \
  inspect-coa-payload-shape.mjs \
  extract-class-roster.mjs \
  export-coa-normalized.mjs \
  build-class-profile-input.mjs \
  extract-rendered-node-labels.mjs \
  coa-rg-json-summary.mjs
do
  need_file "$SCRIPTS_DIR/$script" \
    "Make sure you are running this from the coa_scraper project root, or set SCRIPTS_DIR=/path/to/scripts."
done

# 1. Diagnose the capture. This is intentionally non-fatal because rg/head/SIGPIPE
# behavior inside diagnostic scripts can fail even when the capture is good enough.
run_optional_step "Capture diagnostics" \
  bash "$SCRIPTS_DIR/coa-diagnose.sh" \
    "$DATA_DIR" \
    "$REPORTS_DIR/coa_diagnostic_report.txt"

# 2. Extract canonical CoA builder payload from Next Flight stream.
run_step "Extract builder payload" \
  node "$SCRIPTS_DIR/extract-coa-builder-payload.mjs" \
    "$HTML_FOR_PAYLOAD" \
    "$REPORTS_DIR"

need_file "$REPORTS_DIR/coa_builder_payload.json" \
  "Payload extraction failed; inspect $REPORTS_DIR/next_flight_stream.txt and $REPORTS_DIR/coa_diagnostic_report.txt."

# 3. Summarize payload in human-readable form.
run_step "Summarize payload" \
  node "$SCRIPTS_DIR/summarize-coa-payload.mjs" \
    "$REPORTS_DIR/coa_builder_payload.json" \
    "$REPORTS_DIR/coa_payload_report.txt"

# 4. Inspect schema/shape for drift.
run_step "Inspect payload shape" \
  node "$SCRIPTS_DIR/inspect-coa-payload-shape.mjs" \
    "$REPORTS_DIR/coa_builder_payload.json" \
    "$REPORTS_DIR/coa_payload_shape_report.txt" \
    "$REPORTS_DIR/coa_payload_shape.json"

# 5. Extract class roster from runtime dump as an independent cross-check.
run_step "Extract class roster candidates" \
  node "$SCRIPTS_DIR/extract-class-roster.mjs" \
    "$RUNTIME_FOR_ROSTER" \
    "$REPORTS_DIR/class_roster_candidates.json"

# 6. Normalize payload into optimizer-friendly dist files.
run_step "Export normalized CoA data" \
  node "$SCRIPTS_DIR/export-coa-normalized.mjs" \
    "$REPORTS_DIR/coa_builder_payload.json" \
    "$DIST_DIR"

need_file "$DIST_DIR/coa_entries.jsonl" \
  "Normalization failed; inspect $REPORTS_DIR/coa_payload_shape_report.txt."

need_file "$DIST_DIR/coa_classes.json" \
  "Normalization failed; inspect $REPORTS_DIR/coa_payload_shape_report.txt."

# 7. Build full per-class profile input used by analysis/optimizer tooling.
run_step "Build class profile input" \
  node "$SCRIPTS_DIR/build-class-profile-input.mjs" \
    "$DIST_DIR/coa_entries.jsonl" \
    "$DIST_DIR/coa_classes.json" \
    "$DIST_DIR/coa_class_profile_input.json"

# 8. Extract rendered node labels from the HTML snapshot. This catches UI-only prerequisite text.
run_step "Extract rendered node labels" \
  node "$SCRIPTS_DIR/extract-rendered-node-labels.mjs" \
    "$HTML_FOR_PAYLOAD" \
    "$REPORTS_DIR/rendered_node_labels.json"

# 9. Generate a ripgrep JSON summary for quick manual sanity checks.
# This is non-canonical, so it is allowed to fail without aborting the pipeline.
RG_PATTERN='runtimeBuildProcess|api/v3 builder CoA parser|classId|className|tabId|tabName|entriesByTab|essenceByClass|requiredIds|connectedNodeIds|reqTabAE|reqTabTE|aeCost|teCost|Venomancer|Stalking|Venom|Fortitude|Vizier|Talent Essence|Ability Essence'

run_optional_step "Build rg JSON summary" \
  bash -lc "rg -a --json '$RG_PATTERN' '$DATA_DIR' '$REPORTS_DIR' '$DIST_DIR' 2>/dev/null | node '$SCRIPTS_DIR/coa-rg-json-summary.mjs' > '$REPORTS_DIR/coa_rg_summary.json'"

# 10. Final summary.
echo
echo "===== Done ====="
echo "Input HAR:              $HAR_PATH"
echo "Input HTML snapshot:    $HTML_FOR_PAYLOAD"
echo "Input runtime dump:     $RUNTIME_FOR_ROSTER"
echo
echo "Primary outputs:"
echo "  $REPORTS_DIR/coa_builder_payload.json"
echo "  $REPORTS_DIR/coa_builder_summary.json"
echo "  $REPORTS_DIR/coa_payload_report.txt"
echo "  $REPORTS_DIR/coa_payload_shape_report.txt"
echo "  $DIST_DIR/coa_classes.json"
echo "  $DIST_DIR/coa_essence_caps.json"
echo "  $DIST_DIR/coa_entries.jsonl"
echo "  $DIST_DIR/coa_entries.pretty.json"
echo "  $DIST_DIR/coa_class_profile_input.json"
echo
echo "Diagnostics/debug outputs:"
echo "  $REPORTS_DIR/coa_diagnostic_report.txt"
echo "  $REPORTS_DIR/class_roster_candidates.json"
echo "  $REPORTS_DIR/rendered_node_labels.json"
echo "  $REPORTS_DIR/coa_rg_summary.json"
echo
echo "Suggested quick checks:"
echo "  grep -E 'Missing class records|Missing tab records|Unknown essence-kind records|Deduped records' reports/coa_normalization_report.txt"
echo "  jq '.classes[] | select(.className==\"Venomancer\")' reports/coa_builder_summary.json"
echo "  head -3 dist/coa_entries.jsonl | jq ."
