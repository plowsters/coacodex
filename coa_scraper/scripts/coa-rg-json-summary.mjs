#!/usr/bin/env node
import fs from "node:fs";
import readline from "node:readline";

const counts = new Map();
const samples = new Map();
const MAX_SAMPLES_PER_FILE = 5;
const MAX_TEXT = 300;

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity
});

for await (const line of rl) {
  if (!line.trim()) continue;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    continue;
  }

  if (msg.type !== "match") continue;

  const file = msg.data.path.text;
  const text = msg.data.lines.text.trim().replace(/\s+/g, " ");

  counts.set(file, (counts.get(file) || 0) + 1);

  if (!samples.has(file)) samples.set(file, []);
  if (samples.get(file).length < MAX_SAMPLES_PER_FILE) {
    samples.get(file).push({
      line: msg.data.line_number,
      text: text.slice(0, MAX_TEXT)
    });
  }
}

const output = [...counts.entries()]
  .sort((a, b) => b[1] - a[1])
  .map(([file, count]) => ({
    file,
    count,
    samples: samples.get(file) || []
  }));

console.log(JSON.stringify(output, null, 2));
