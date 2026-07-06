import fs from "node:fs/promises";
import path from "node:path";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";

const DEFAULT_URL = "https://ascension.gg/en/v2/coa-builder/voljin-alpha";
const SCHEMA_VERSION = "coa-builder-tree-layout-v1";
const TREE_KINDS = ["ability_essence", "talent_essence", "level_passives"];

function valueAfter(argv, name, fallback = "") {
  const index = argv.indexOf(name);
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback;
}

function parseViewport(value) {
  const match = /^(\d+)x(\d+)$/i.exec(value || "");
  if (!match) return { width: 1920, height: 1080 };
  return { width: Number(match[1]), height: Number(match[2]) };
}

function parseOptions(argv = process.argv.slice(2)) {
  const args = new Set(argv);
  return {
    help: args.has("--help") || args.has("-h"),
    url: valueAfter(argv, "--url", DEFAULT_URL),
    className: valueAfter(argv, "--class", ""),
    specName: valueAfter(argv, "--spec", ""),
    outDir: valueAfter(argv, "--out", "reports/tree_layout"),
    screenshotsDir: valueAfter(argv, "--screenshots", ""),
    headless: args.has("--headless"),
    viewport: parseViewport(valueAfter(argv, "--viewport", "1920x1080")),
    pauseForManualSelection: args.has("--pause-for-manual-selection")
  };
}

function usage() {
  return `Usage: node scripts/capture-builder-tree-layout.mjs [options]

Options:
  --url <url>                         CoA Builder URL to open.
  --class <name>                      Class name to select or label in output.
  --spec <name>                       Spec/source tab name to select or label in output.
  --out <dir>                         Directory for layout JSON.
  --screenshots <dir>                 Optional screenshot output directory.
  --headless                          Run Chromium headless.
  --viewport <width>x<height>         Capture viewport, default 1920x1080.
  --pause-for-manual-selection        Pause after page load for manual class/spec selection.
`;
}

function slug(value) {
  return String(value || "unknown")
    .toLowerCase()
    .replace(/'/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "unknown";
}

async function clickTextIfPresent(page, text) {
  if (!text) return false;
  const locator = page.getByText(text, { exact: true }).first();
  try {
    await locator.click({ timeout: 2500 });
    return true;
  } catch (_error) {
    return false;
  }
}

async function pauseForManualSelection() {
  const rl = readline.createInterface({ input, output });
  try {
    await rl.question("[tree-layout] Select the desired class/spec in the browser, then press Enter here...");
  } finally {
    rl.close();
  }
}

async function captureDomLayout(page, options) {
  return page.evaluate(({ className, specName, schemaVersion, treeKinds, viewport }) => {
    function numericAttr(element, names) {
      for (const name of names) {
        const raw = element.getAttribute(name);
        if (raw && /^-?\d+$/.test(raw)) return Number(raw);
      }
      return null;
    }

    function spellId(element) {
      const direct = numericAttr(element, ["data-spell-id", "spell-id"]);
      if (direct !== null) return direct;
      const href = element.getAttribute("href") || element.querySelector("a[href*='spell=']")?.getAttribute("href") || "";
      const match = /[?&]spell=(\d+)/.exec(href);
      return match ? Number(match[1]) : null;
    }

    function elementName(element) {
      return (
        element.getAttribute("aria-label") ||
        element.getAttribute("title") ||
        element.querySelector("[aria-label]")?.getAttribute("aria-label") ||
        element.textContent ||
        ""
      ).trim();
    }

    function candidateTreeContainers() {
      const selectors = [
        "[data-tree-kind]",
        "[data-tree]",
        ".talent-tree",
        "[class*='TalentTree']",
        "[class*='talent-tree']",
        "[class*='tree']",
        "[class*='Tree']"
      ];
      const seen = new Set();
      const containers = [];
      for (const selector of selectors) {
        for (const element of document.querySelectorAll(selector)) {
          if (seen.has(element)) continue;
          seen.add(element);
          const rect = element.getBoundingClientRect();
          if (rect.width < 80 || rect.height < 60) continue;
          containers.push(element);
        }
      }
      return containers.slice(0, 3);
    }

    function nodeElements(container) {
      const selectors = [
        "[data-entry-id]",
        "[data-node-id]",
        "[data-spell-id]",
        "button[aria-label]",
        "[role='button'][aria-label]",
        "a[href*='spell=']"
      ];
      const seen = new Set();
      const nodes = [];
      for (const selector of selectors) {
        for (const element of container.querySelectorAll(selector)) {
          if (seen.has(element)) continue;
          seen.add(element);
          const entryId = numericAttr(element, ["data-entry-id", "data-node-id", "entry-id", "node-id"]);
          const spell = spellId(element);
          if (entryId === null && spell === null) continue;
          const rect = element.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) continue;
          nodes.push(element);
        }
      }
      return nodes;
    }

    const containers = candidateTreeContainers();
    const warnings = [];
    if (!containers.length) warnings.push("builder_tree_containers_not_detected");

    const trees = treeKinds.map((treeKind, index) => {
      const container = containers[index] || containers[0] || document.body;
      const containerRect = container.getBoundingClientRect();
      const nodes = nodeElements(container).map(element => {
        const rect = element.getBoundingClientRect();
        const entryId = numericAttr(element, ["data-entry-id", "data-node-id", "entry-id", "node-id"]);
        return {
          entry_id: entryId ?? spellId(element) ?? 0,
          spell_id: spellId(element),
          name: elementName(element),
          x: Math.round(rect.left - containerRect.left),
          y: Math.round(rect.top - containerRect.top),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        };
      }).filter(node => node.entry_id);
      if (!nodes.length) warnings.push(`builder_tree_nodes_not_detected:${treeKind}`);
      return {
        tree_kind: treeKind,
        layout_source: "builder_dom",
        bounds: {
          x: Math.round(containerRect.left),
          y: Math.round(containerRect.top),
          width: Math.round(containerRect.width),
          height: Math.round(containerRect.height)
        },
        nodes,
        edges: []
      };
    });

    return {
      schema_version: schemaVersion,
      class_name: className || "",
      source_spec_name: specName || "",
      display_spec_name: specName || "",
      captured_at: new Date().toISOString(),
      source_url: location.href,
      layout_source: "builder_dom",
      viewport,
      trees,
      warnings
    };
  }, {
    className: options.className,
    specName: options.specName,
    schemaVersion: SCHEMA_VERSION,
    treeKinds: TREE_KINDS,
    viewport: options.viewport
  });
}

async function writeOutputs(layout, options, page) {
  await fs.mkdir(options.outDir, { recursive: true });
  const fileName = `${slug(layout.class_name || options.className)}-${slug(layout.source_spec_name || options.specName)}.json`;
  const jsonPath = path.join(options.outDir, fileName);
  await fs.writeFile(jsonPath, JSON.stringify(layout, null, 2) + "\n", "utf8");
  console.log(`[tree-layout] Saved layout JSON: ${jsonPath}`);

  if (options.screenshotsDir) {
    await fs.mkdir(options.screenshotsDir, { recursive: true });
    const screenshotPath = path.join(options.screenshotsDir, fileName.replace(/\.json$/, ".png"));
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`[tree-layout] Saved screenshot: ${screenshotPath}`);
  }
}

async function main() {
  const options = parseOptions();
  if (options.help) {
    console.log(usage());
    return;
  }

  console.log(`[tree-layout] Stage 1: load page ${options.url}`);
  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ headless: options.headless });
  const page = await browser.newPage({ viewport: options.viewport });
  try {
    await page.goto(options.url, { waitUntil: "networkidle", timeout: 60000 });

    console.log("[tree-layout] Stage 2: select class/spec when possible");
    const clickedClass = await clickTextIfPresent(page, options.className);
    const clickedSpec = await clickTextIfPresent(page, options.specName);
    if (options.pauseForManualSelection || (!clickedClass && options.className) || (!clickedSpec && options.specName)) {
      await pauseForManualSelection();
    }

    console.log("[tree-layout] Stage 3: detect tree containers and DOM boxes");
    const layout = await captureDomLayout(page, options);
    console.log(`[tree-layout] Layout source: ${layout.layout_source}`);

    console.log("[tree-layout] Stage 4: save layout JSON and screenshots");
    await writeOutputs(layout, options, page);
  } finally {
    await browser.close();
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(error => {
    console.error(`[tree-layout] Failed: ${error.stack || error.message}`);
    process.exitCode = 1;
  });
}
