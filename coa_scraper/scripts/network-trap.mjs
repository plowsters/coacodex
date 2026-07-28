// A RUNNABLE network trap for the acceptance run (E0R.1 T6.2). Preload it with
//   node --import ./scripts/network-trap.mjs scripts/build-mechanics-artifacts.mjs …
// and every outbound network primitive throws instead of connecting, while the ATTEMPT is counted and
// written to $COA_NETWORK_TRAP_LOG on exit. The acceptance summary reads that count: "the canonical
// build made no network request" then rests on an executed measurement rather than on an assertion.
import fs from "node:fs";
import http from "node:http";
import https from "node:https";
import net from "node:net";
import dns from "node:dns";

const attempts = [];

function trap(api) {
  return (...args) => {
    const target = args.map((a) => (typeof a === "string" ? a : (a && a.host) || "")).filter(Boolean)[0] || "";
    attempts.push({ api, target: String(target) });
    throw new Error(`network access is forbidden in a canonical build (${api} ${target})`);
  };
}

http.request = trap("http.request");
http.get = trap("http.get");
https.request = trap("https.request");
https.get = trap("https.get");
net.connect = trap("net.connect");
net.createConnection = trap("net.createConnection");
dns.lookup = trap("dns.lookup");
globalThis.fetch = trap("fetch");

process.on("exit", () => {
  const logPath = process.env.COA_NETWORK_TRAP_LOG;
  if (!logPath) return;
  try {
    fs.writeFileSync(logPath, JSON.stringify({ attempts: attempts.length, detail: attempts }, null, 2) + "\n");
  } catch { /* the acceptance writer treats a missing log as an unproven trap and refuses */ }
});
