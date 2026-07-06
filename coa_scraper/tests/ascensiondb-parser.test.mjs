import assert from "node:assert/strict";
import test from "node:test";

import {
  htmlToText,
  parseAscensionDbPayload,
  parseCastTimeMs,
  parseCooldownMs,
  parseDurationMs,
  parseGcdMs,
  parseItemClass,
  parsePowerCosts,
  parsePowerPayload,
  parseRangeYards,
  parseStats
} from "../scripts/lib/ascensiondb.mjs";

const RICH_SPELL_PAYLOAD = `$WowheadPower.registerSpell(700001, 0, {
  "name_enus": "Venom Burst",
  "icon": "ability_venom_burst",
  "tooltip_enus": "<table><tr><td>Requires Level 20<br />30 yd range<br />2 sec cast<br />Costs 30 Energy<br />Deals 120 Nature damage over 12 sec, every 3 sec.<br />1.5 sec global cooldown<br />45 sec cooldown</td></tr></table>",
  "buff_enus": "<table><tr><td>Lasts 12 sec</td></tr></table>"
});`;

const ITEM_PAYLOAD = `$WowheadPower.registerItem(800001, 0, {
  "name_enus": "Fel Etched Longsword",
  "quality": 4,
  "icon": "inv_sword_fel_01",
  "tooltip_enus": "<table><tr><td><b class=\\"q4\\">Fel Etched Longsword</b><br />One-Hand Sword<br />+20 Agility<br />+15 Stamina<br />Requires Level 60<br /><span class=\\"q2\\">Use: <a href=\\"?spell=900001\\">Unleash fel venom.</a></span></td></tr></table>"
});`;

test("AscensionDB parser exposes v2 spell mechanic fields", () => {
  const parsed = parsePowerPayload(RICH_SPELL_PAYLOAD, {
    kind: "spell",
    id: 700001,
    url: "https://db.ascension.gg/?spell=700001&power",
    fetchedAt: "2026-07-06T00:00:00.000Z"
  });

  assert.equal(parsed.kind, "spell");
  assert.equal(parsed.status, "matched");
  assert.equal(parsed.name, "Venom Burst");
  assert.equal(parsed.icon, "ability_venom_burst");
  assert.equal(parsed.tooltip_text, "Requires Level 20 30 yd range 2 sec cast Costs 30 Energy Deals 120 Nature damage over 12 sec, every 3 sec. 1.5 sec global cooldown 45 sec cooldown");
  assert.equal(parsed.required_level, 20);
  assert.equal(parsed.cooldown_ms, 45000);
  assert.equal(parsed.gcd_ms, 1500);
  assert.equal(parsed.cast_time_ms, 2000);
  assert.equal(parsed.range_yards, 30);
  assert.equal(parsed.duration_ms, 12000);
  assert.equal(parsed.period_ms, 3000);
  assert.deepEqual(parsed.power_costs, [{ amount: 30, resource: "Energy" }]);
  assert(parsed.mechanic_tags.includes("damage"));
  assert(parsed.mechanic_tags.includes("dot"));
  assert.equal(parsed.buff_tooltip_html, "<table><tr><td>Lasts 12 sec</td></tr></table>");
  assert.deepEqual(parsed.warnings, []);
});

test("AscensionDB parser exposes item class, stats, and effects", () => {
  const parsed = parseAscensionDbPayload(ITEM_PAYLOAD, {
    kind: "item",
    id: 800001,
    url: "https://db.ascension.gg/?item=800001&power",
    fetchedAt: "2026-07-06T00:00:00.000Z"
  });

  assert.equal(parsed.kind, "item");
  assert.equal(parsed.status, "matched");
  assert.equal(parsed.name, "Fel Etched Longsword");
  assert.equal(parsed.quality, 4);
  assert.equal(parsed.required_level, 60);
  assert.equal(parsed.inventory_type, "one_hand");
  assert.equal(parsed.item_class, "weapon");
  assert.equal(parsed.item_subclass, "sword");
  assert.equal(parsed.weapon_type, "sword");
  assert.equal(parsed.armor_type, null);
  assert.deepEqual(parsed.stats, [
    { stat: "agility", value: 20 },
    { stat: "stamina", value: 15 }
  ]);
  assert.deepEqual(parsed.effects, [{ effect_type: "use", spell_id: 900001 }]);
  assert.deepEqual(parsed.linked_spell_ids, [900001]);
});

test("AscensionDB parser returns parse_failed for malformed registrations", () => {
  const parsed = parsePowerPayload("$WowheadPower.registerSpell(700001, 0, {", {
    kind: "spell",
    id: 700001,
    url: "https://db.ascension.gg/?spell=700001&power"
  });

  assert.equal(parsed.status, "parse_failed");
  assert.equal(parsed.name, null);
  assert.match(parsed.warnings[0], /parse_failed/);
});

test("tooltip parser helpers extract common mechanics", () => {
  const text = htmlToText("<table><tr><td>Requires Level 30<br />40 yd range<br />1.5 sec cast<br />Costs 40 Mana<br />Lasts 18 sec and ticks every 2 sec.<br />30 sec cooldown</td></tr></table>");

  assert.equal(parseCooldownMs(text), 30000);
  assert.equal(parseCastTimeMs(text), 1500);
  assert.equal(parseGcdMs("1 sec global cooldown"), 1000);
  assert.equal(parseRangeYards(text), 40);
  assert.equal(parseDurationMs(text), 18000);
  assert.deepEqual(parsePowerCosts(text), [{ amount: 40, resource: "Mana" }]);
});

test("item parser helpers extract class and stats", () => {
  assert.deepEqual(parseItemClass("Two-Hand Axe +10 Strength"), {
    inventory_type: "two_hand",
    item_class: "weapon",
    item_subclass: "axe",
    weapon_type: "axe",
    armor_type: null
  });
  assert.deepEqual(parseItemClass("Plate Chest +10 Stamina"), {
    inventory_type: "chest",
    item_class: "armor",
    item_subclass: "plate",
    weapon_type: null,
    armor_type: "plate"
  });
  assert.deepEqual(parseStats("+12 Strength +8 Critical Strike"), [
    { stat: "strength", value: 12 },
    { stat: "critical_strike", value: 8 }
  ]);
});
