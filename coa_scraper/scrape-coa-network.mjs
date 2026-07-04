// scrape-coa-network.mjs
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

import { parseCaptureOptions } from "./scripts/lib/capture-options.mjs";

const options = parseCaptureOptions();
const URL = options.url;
const OUT = options.outDir;
const SNAP = options.snapshotDir;
const HAR = options.harPath;
const WAIT_MS = options.waitMs;
const HEADLESS = options.headless;
const INTERACTIVE = options.interactive;

await fs.mkdir(OUT, { recursive: true });
await fs.mkdir(SNAP, { recursive: true });

const safeName = url =>
  url
    .replace(/^https?:\/\//, "")
    .replace(/[^a-zA-Z0-9._-]+/g, "_")
    .slice(0, 220);

const looksInteresting = (url, contentType = "") => {
  const hay = `${url} ${contentType}`;
  return (
    /json/i.test(contentType) ||
    /javascript/i.test(contentType) ||
    /text\/html/i.test(contentType) ||
    /\/api\//i.test(url) ||
    /_next/i.test(url) ||
    /coa|builder|talent|ability|spell|essence|class|tree/i.test(hay)
  );
};

const browser = await chromium.launch({
  headless: HEADLESS,
  executablePath: "/usr/bin/chromium"
});

const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  recordHar: {
    path: HAR,
    content: "embed",
    mode: "full"
  }
});

const page = await context.newPage();

// Chromium-specific: increase network body retention.
const cdp = await context.newCDPSession(page);
await cdp.send("Network.enable", {
  maxTotalBufferSize: 1000 * 1024 * 1024,
  maxResourceBufferSize: 200 * 1024 * 1024
});

const cdpRequests = new Map();

cdp.on("Network.responseReceived", evt => {
  cdpRequests.set(evt.requestId, {
    url: evt.response.url,
    mimeType: evt.response.mimeType,
    status: evt.response.status
  });
});

cdp.on("Network.loadingFinished", async evt => {
  const meta = cdpRequests.get(evt.requestId);
  if (!meta) return;
  if (!looksInteresting(meta.url, meta.mimeType)) return;

  try {
    const body = await cdp.send("Network.getResponseBody", {
      requestId: evt.requestId
    });

    const ext =
      /html/i.test(meta.mimeType) ? ".html" :
      /json/i.test(meta.mimeType) ? ".json" :
      /javascript/i.test(meta.mimeType) ? ".js" :
      ".body";

    const name = `${meta.status}_${safeName(meta.url)}${ext}`;
    const file = path.join(OUT, name);

    if (body.base64Encoded) {
      await fs.writeFile(file, Buffer.from(body.body, "base64"));
    } else {
      await fs.writeFile(file, body.body, "utf8");
    }

    console.log("cdp saved", meta.status, meta.mimeType, meta.url);
  } catch (err) {
    console.warn("cdp failed", meta.url, err.message);
  }
});

// Normal Playwright response capture too.
const seen = new Set();

page.on("response", async response => {
  const url = response.url();
  const contentType = response.headers()["content-type"] || "";

  if (seen.has(url)) return;
  seen.add(url);

  if (!looksInteresting(url, contentType)) return;

  try {
    const body = await response.body();

    const ext =
      /html/i.test(contentType) ? ".html" :
      /json/i.test(contentType) ? ".json" :
      /javascript/i.test(contentType) ? ".js" :
      /css/i.test(contentType) ? ".css" :
      "";

    await fs.writeFile(
      path.join(OUT, `${response.status()}_${safeName(url)}${ext}`),
      body
    );

    console.log("pw saved", response.status(), contentType, url);
  } catch (err) {
    console.warn("pw failed", url, err.message);
  }
});

page.on("console", msg => {
  const text = msg.text();
  if (/error|warning|api|coa|talent|ability|spell|essence/i.test(text)) {
    console.log("browser console:", msg.type(), text.slice(0, 500));
  }
});

await page.goto(URL, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(WAIT_MS);

await fs.writeFile(
  path.join(SNAP, "initial-page-content.html"),
  await page.content(),
  "utf8"
);

await fs.writeFile(
  path.join(SNAP, "initial-url.txt"),
  page.url(),
  "utf8"
);

// Capture obvious Next/React/runtime storage.
const runtimeDump = await page.evaluate(() => {
  const dumpStorage = store => {
    const out = {};
    for (let i = 0; i < store.length; i++) {
      const key = store.key(i);
      out[key] = store.getItem(key);
    }
    return out;
  };

  const scriptTexts = [...document.scripts]
    .map((s, i) => ({
      i,
      id: s.id || null,
      type: s.type || null,
      src: s.src || null,
      textStart: s.textContent?.slice(0, 5000) || ""
    }))
    .filter(s =>
      /next|flight|coa|talent|ability|spell|essence|class|builder/i.test(
        `${s.id} ${s.type} ${s.src} ${s.textStart}`
      )
    );

  return {
    href: location.href,
    title: document.title,
    nextData: globalThis.__NEXT_DATA__ ?? null,
    nextFlight: globalThis.__next_f ?? null,
    localStorage: dumpStorage(localStorage),
    sessionStorage: dumpStorage(sessionStorage),
    scriptTexts
  };
});

await fs.writeFile(
  path.join(SNAP, "runtime-dump.json"),
  JSON.stringify(runtimeDump, null, 2),
  "utf8"
);

async function finalizeCapture() {
  await page.waitForTimeout(2000);

  await fs.writeFile(
    path.join(SNAP, "final-page-content.html"),
    await page.content(),
    "utf8"
  );

  const finalRuntimeDump = await page.evaluate(() => {
    const dumpStorage = store => {
      const out = {};
      for (let i = 0; i < store.length; i++) {
        const key = store.key(i);
        out[key] = store.getItem(key);
      }
      return out;
    };

    return {
      href: location.href,
      title: document.title,
      nextData: globalThis.__NEXT_DATA__ ?? null,
      nextFlight: globalThis.__next_f ?? null,
      localStorage: dumpStorage(localStorage),
      sessionStorage: dumpStorage(sessionStorage)
    };
  });

  await fs.writeFile(
    path.join(SNAP, "final-runtime-dump.json"),
    JSON.stringify(finalRuntimeDump, null, 2),
    "utf8"
  );

  await context.close();
  await browser.close();

  console.log("Saved HAR:", HAR);
  console.log("Saved snapshots:", SNAP);
}

if (!INTERACTIVE) {
  await finalizeCapture();
  process.exit(0);
}

console.log("Initial capture complete.");
console.log("Now manually click class tabs and essence/talent panels in the browser.");
console.log("When finished, press Enter here.");

process.stdin.resume();
process.stdin.once("data", async () => {
  await finalizeCapture();
  process.exit(0);
});
