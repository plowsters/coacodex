-- CoADataLogger.lua
-- Minimal WotLK 3.3.5-compatible data collector scaffold.
-- Saved data appears in WTF/Account/<ACCOUNT>/SavedVariables/CoADataLogger.lua after logout/reload.

CoADataLoggerDB = CoADataLoggerDB or {
  enabled = false,
  sessions = {},
  current = nil
}

local frame = CreateFrame("Frame")
local playerName = UnitName("player")

local function now()
  return GetTime()
end

local function shallowCopy(t)
  local out = {}
  if not t then return out end
  for k, v in pairs(t) do out[k] = v end
  return out
end

local function getStatsSnapshot()
  local stats = {}
  local names = {"strength", "agility", "stamina", "intellect", "spirit"}
  for i = 1, 5 do
    local base, effective, posBuff, negBuff = UnitStat("player", i)
    stats[names[i]] = {base = base, effective = effective, posBuff = posBuff, negBuff = negBuff}
  end

  -- WotLK combat rating IDs vary by rating type; keep raw IDs so your parser can decide later.
  stats.combatRatings = {}
  for id = 1, 25 do
    local ok, rating = pcall(GetCombatRating, id)
    if ok and rating and rating ~= 0 then
      stats.combatRatings[tostring(id)] = rating
    end
  end

  stats.attackPower = {UnitAttackPower("player")}
  stats.rangedAttackPower = {UnitRangedAttackPower("player")}
  stats.spellBonusDamage = {}
  for school = 1, 7 do
    local ok, value = pcall(GetSpellBonusDamage, school)
    if ok then stats.spellBonusDamage[tostring(school)] = value end
  end
  stats.spellCritChance = {}
  for school = 1, 7 do
    local ok, value = pcall(GetSpellCritChance, school)
    if ok then stats.spellCritChance[tostring(school)] = value end
  end
  return stats
end

local function getGearSnapshot()
  local gear = {}
  for slot = 1, 19 do
    local link = GetInventoryItemLink("player", slot)
    if link then
      gear[tostring(slot)] = link
    end
  end
  return gear
end

local function getTalentSnapshot()
  -- CoA custom talents may not map cleanly to stock 3.3.5 talent APIs.
  -- This still captures stock visible tabs if the server exposes them.
  local talents = {}
  local numTabs = GetNumTalentTabs and GetNumTalentTabs() or 0
  for tab = 1, numTabs do
    local tabName = GetTalentTabInfo(tab)
    talents[tabName or tostring(tab)] = {}
    local numTalents = GetNumTalents(tab) or 0
    for idx = 1, numTalents do
      local name, icon, tier, column, rank, maxRank = GetTalentInfo(tab, idx)
      talents[tabName or tostring(tab)][idx] = {
        name = name,
        tier = tier,
        column = column,
        rank = rank,
        maxRank = maxRank
      }
    end
  end
  return talents
end

local function startSession(label)
  local session = {
    label = label or date("%Y-%m-%d %H:%M:%S"),
    player = playerName,
    realm = GetRealmName(),
    startedAt = time(),
    startedAtGameTime = now(),
    snapshot = {
      level = UnitLevel("player"),
      class = select(2, UnitClass("player")),
      stats = getStatsSnapshot(),
      gear = getGearSnapshot(),
      talents = getTalentSnapshot()
    },
    events = {}
  }
  table.insert(CoADataLoggerDB.sessions, session)
  CoADataLoggerDB.current = table.getn(CoADataLoggerDB.sessions)
  CoADataLoggerDB.enabled = true
  print("CoADataLogger: started session " .. session.label)
end

local function stopSession()
  CoADataLoggerDB.enabled = false
  print("CoADataLogger: stopped. /reload or logout to flush SavedVariables.")
end

local function getCurrentSession()
  local idx = CoADataLoggerDB.current
  if idx and CoADataLoggerDB.sessions[idx] then
    return CoADataLoggerDB.sessions[idx]
  end
  return nil
end

local function appendEvent(ev)
  if not CoADataLoggerDB.enabled then return end
  local session = getCurrentSession()
  if not session then return end
  table.insert(session.events, ev)
end

-- WotLK 3.3.5 uses varargs for COMBAT_LOG_EVENT_UNFILTERED.
local function onCombatLogEvent(...)
  local timestamp, subevent, sourceGUID, sourceName, sourceFlags, destGUID, destName, destFlags = ...
  if sourceName ~= playerName then return end

  local ev = {
    t = now(),
    serverTimestamp = timestamp,
    event = subevent,
    source = sourceName,
    target = destName,
    sourceGUID = sourceGUID,
    destGUID = destGUID
  }

  if string.find(subevent or "", "SPELL_") == 1 then
    local _, _, _, _, _, _, _, _, spellId, spellName, spellSchool, amount, overkill, school, resisted, blocked, absorbed, critical = ...
    ev.spellId = spellId
    ev.spellName = spellName
    if subevent == "SPELL_DAMAGE" or subevent == "SPELL_PERIODIC_DAMAGE" then
      ev.amount = amount
      ev.critical = critical and true or false
      ev.overkill = overkill
      ev.resisted = resisted
      ev.blocked = blocked
      ev.absorbed = absorbed
    end
  elseif subevent == "SWING_DAMAGE" then
    local _, _, _, _, _, _, _, _, amount, overkill, school, resisted, blocked, absorbed, critical = ...
    ev.spellName = "Swing"
    ev.amount = amount
    ev.critical = critical and true or false
    ev.overkill = overkill
  end

  appendEvent(ev)
end

frame:RegisterEvent("COMBAT_LOG_EVENT_UNFILTERED")
frame:SetScript("OnEvent", function(self, event, ...)
  if event == "COMBAT_LOG_EVENT_UNFILTERED" then
    onCombatLogEvent(...)
  end
end)

SLASH_COADATALOGGER1 = "/coalog"
SlashCmdList["COADATALOGGER"] = function(msg)
  msg = msg or ""
  local cmd, rest = msg:match("^(%S*)%s*(.-)$")
  cmd = string.lower(cmd or "")
  if cmd == "start" then
    startSession(rest ~= "" and rest or nil)
  elseif cmd == "stop" then
    stopSession()
  elseif cmd == "snapshot" then
    local session = getCurrentSession()
    if not session then
      startSession("snapshot")
      session = getCurrentSession()
      CoADataLoggerDB.enabled = false
    end
    session.snapshot = {
      level = UnitLevel("player"),
      class = select(2, UnitClass("player")),
      stats = getStatsSnapshot(),
      gear = getGearSnapshot(),
      talents = getTalentSnapshot()
    }
    print("CoADataLogger: snapshot saved.")
  elseif cmd == "status" then
    local session = getCurrentSession()
    local count = session and table.getn(session.events) or 0
    print("CoADataLogger: enabled=" .. tostring(CoADataLoggerDB.enabled) .. ", events=" .. tostring(count))
  else
    print("CoADataLogger commands:")
    print("  /coalog start [label]  - start collecting player-sourced combat events")
    print("  /coalog stop           - stop collecting")
    print("  /coalog snapshot       - capture gear/stats/talents")
    print("  /coalog status         - show current status")
    print("SavedVariables flush on /reload or logout.")
  end
end
