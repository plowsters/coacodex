const DEFAULT_URL = "https://ascension.gg/en/v2/coa-builder/voljin-alpha";

function valueAfter(argv, name, fallback) {
  const index = argv.indexOf(name);
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback;
}

export function parseCaptureOptions(argv = process.argv.slice(2)) {
  const args = new Set(argv);

  return {
    url: valueAfter(argv, "--url", DEFAULT_URL),
    outDir: valueAfter(argv, "--out-dir", "data/raw"),
    snapshotDir: valueAfter(argv, "--snapshot-dir", "data/snapshots"),
    harPath: valueAfter(argv, "--har", "data/coa.har"),
    waitMs: Number(valueAfter(argv, "--wait-ms", "8000")),
    headless: args.has("--headless"),
    interactive: args.has("--interactive") || !args.has("--finalize-on-load")
  };
}
