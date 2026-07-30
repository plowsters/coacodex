# Retail WoW Tooling References

This project should model mature retail WoW tools at the architecture level. Direct code reuse requires license review.

## SimulationCraft

Links:

- Repository: <https://github.com/simulationcraft/simc>
- README: <https://github.com/simulationcraft/simc/blob/thewarwithin/README.md>
- Action lists wiki: <https://github.com/simulationcraft/simc/wiki/ActionLists>
- ActionPriorityLists folder: <https://github.com/simulationcraft/simc/tree/thewarwithin/ActionPriorityLists>

Relevant patterns:

- Event-driven simulator rather than closed-form stat calculator.
- Separate engine, class modules, data extraction, profiles, APLs, reports, and CLI.
- APLs are priority lists scanned from top to bottom until an available action is found.
- Additional action lists can be used as named sub-priorities for cooldowns, openers, and behavior branches.
- Generated APL text is treated as output from source modules and is not manually edited in place.
- Reports and profiles are reproducible text artifacts.

How to apply to CoA:

- Use SimC's APL concept, not necessarily SimC code.
- Keep generated APLs editable and serializable.
- Execute CoA APL candidates through the local clean-room simulator before turning them into guide rotations.
- Keep simulator logic separate from build legality.
- Add report provenance and assumptions to every run.

License note:

- SimulationCraft is GPL-3.0 with additional bundled licenses. Copying source code requires a deliberate compatibility decision.
- M1.11E should remain clean-room: use priority-list and event-simulation concepts, not SimC source code, class modules, or generated APLs.

## SimulationCraft Addon

Links:

- Repository: <https://github.com/simulationcraft/simc-addon>
- README: <https://raw.githubusercontent.com/simulationcraft/simc-addon/master/README.md>

Relevant patterns:

- The addon collects character state and prints/export text suitable for an external simulator.
- The addon does not run the simulation in game.
- The `/simc` workflow is a clean separation between in-game state capture and external optimization.

How to apply to CoA:

- `CoADataLogger` should capture state and events, then export SavedVariables or text.
- Optimization should stay out of the addon.
- A future CoA profile export can mirror the `/simc` idea with CoA-specific class, build, gear, stats, and selected nodes.

## Raidbots

Links:

- Website: <https://www.raidbots.com/simbot>
- SimC APL docs mention custom APL usage in Raidbots: <https://github.com/simulationcraft/simc/tree/thewarwithin/ActionPriorityLists>

Relevant patterns:

- User-facing frontend for running many simulation jobs and comparing results.
- Workflows such as Top Gear and Droptimizer separate user intent from raw engine details.
- The frontend should make assumptions and inputs visible.

How to apply to CoA:

- Phase 4 should offer workflows like "Best Stalker single-target build", "AoE build comparison", "stat priority", and "rotation review".
- Reports should show the selected data source: theorycraft, simulated, empirical, or blended.

License note:

- Treat Raidbots primarily as a workflow reference unless a specific source repository and license are identified.

## WoWAnalyzer

Links:

- Repository: <https://github.com/WoWAnalyzer/WoWAnalyzer>
- README: <https://raw.githubusercontent.com/WoWAnalyzer/WoWAnalyzer/master/README.md>

Relevant patterns:

- Log-analysis application focused on performance feedback and gameplay suggestions.
- TypeScript web application with a source tree, docs, public assets, scripts, and tests.
- Warcraft Logs-oriented analysis model.

How to apply to CoA:

- Phase 2 and Phase 4 should borrow the concept of analyzers that turn logs into actionable suggestions.
- Keep log metrics separate from theory and simulation models.
- Use per-spec analyzers only after generic event metrics exist.
- For M1.11E, use the analyzer pattern of converting raw events into actionable guide feedback, but do not copy AGPL implementation code.

License note:

- WoWAnalyzer is AGPL-3.0. Copying source code can impose strong source-sharing obligations, including for networked use.

## HTTP Cache Validation

Links:

- RFC 9110 HTTP Semantics: <https://www.rfc-editor.org/rfc/rfc9110.html>
- MDN HTTP conditional requests: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests>

Relevant patterns:

- `ETag` and `Last-Modified` validators let clients avoid transferring unchanged resources.
- `If-None-Match` and `If-Modified-Since` enable conditional refreshes.
- `304 Not Modified` means the local cached representation can be reused.

How to apply to CoA:

- M1.11D cached AscensionDB power payloads, icon assets, and parsed rows. That pipeline was **removed** by M1.14E0R — mechanics and icons come from the local client — so this pattern now applies only to the opt-in icon-image downloader, not to any canonical build.
- Use HTTP validators when available and SHA-256 content/parsed hashes as a fallback.
- Keep conservative stale-age defaults and bounded concurrency to avoid unnecessary load on Project Ascension resources.

## Retail Class Guide Sites

Links:

- Icy Veins Outlaw Rogue rotation example: <https://www.icy-veins.com/wow/outlaw-rogue-pve-dps-rotation-cooldowns-abilities>
- Wowhead Demonology Warlock guide example: <https://www.wowhead.com/guide/classes/warlock/demonology/overview-pve-dps>
- Archon Brewmaster Monk build example: <https://www.archon.gg/wow/builds/brewmaster/monk/mythic-plus/overview/10/all-dungeons/this-week>
- Method Discipline Priest guide example: <https://www.method.gg/guides/discipline-priest>

Relevant patterns:

- Guides are organized around player tasks: overview, talents, rotation, gear, stats, utility, and update context.
- Rotation sections explain opener, core priority, cooldowns, maintenance, and conditional/proc rules. They do not list every ability in the kit.
- Data-backed sites expose context such as content type, recency, parse/sample counts, and ranking filters.
- Tooltip-rich spell links keep guides compact while preserving access to detailed spell/item data.

How to apply to CoA:

- Generate one concise rotation guide per selected build rather than category dumps.
- Keep analyzer-specific metrics behind tooltips or provenance sections.
- Use role-specific guide language: damage, healing, tank survival/threat, or support contribution.
- Show when output is theorycraft-only and reserve empirical claims for AscensionLogs/addon-calibrated data.

## Architecture Takeaways

- Separate data capture, normalization, simulation, analysis, and UI.
- Make every report reproducible from saved inputs.
- Treat APLs as priority lists with explicit conditions.
- Keep in-game addons lightweight.
- Label evidence source and confidence.
- Do not present uncalibrated theorycraft scores as observed DPS.
