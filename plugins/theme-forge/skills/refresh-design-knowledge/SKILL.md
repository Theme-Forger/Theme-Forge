---
name: refresh-design-knowledge
description: >-
  Refreshes Theme Forge's design knowledge base from the live web — current CSS features, design
  token standards, color and typography practice, motion libraries, component systems, React
  Native and Expo platform constraints, mobile design guidelines, and accessibility requirements.
  Use when someone wants the design knowledge updated, asks how current the design knowledge is,
  or wants themes generated against the latest practices.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), Bash(python3 ${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/*), Read, Write, Task, WebSearch, WebFetch
---

# Refresh design knowledge

Forces a **full fourteen-way refresh** regardless of freshness, and reports a per-domain
changelog.

## Steps

1. Ensure the live base exists:

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_seed_knowledge.py" --json
```

2. Spawn **thirteen `design-researcher` subagents in parallel, in a single turn** — one per
   domain, each given the domain name and the absolute path to its file under
   `$TF_HOME/knowledge/`:

   `01-design-tokens 02-color 03-typography 04-aesthetics 05-css-platform 06-motion
   07-component-systems 08-logos-graphics 09-mobile 10-accessibility 11-native-platform
   12-asset-tooling 13-anti-patterns 14-asset-sources`

   Each runs 15–25 targeted searches across three layers (primary sources → secondary
   analysis → community signal), rewrites its file in place preserving headings, and returns a
   source count and a bullet list of what changed. Prioritize `11-native-platform`,
   `05-css-platform`, `07-component-systems`, `12-asset-tooling`, and `14-asset-sources` — the
   first three move fastest, and the last two record **license terms and API availability**,
   which change without notice and silently. `14-asset-sources` is the highest-consequence of
   all: it is the difference between a legal obligation being known and being discovered after
   shipping. Re-verify its endpoints by probing them, not by reading aggregator sites — that
   pass found a dead documented API, a live undocumented one, and a license that aggregators
   reported as MIT when it is proprietary.

3. As each returns, mark it refreshed and record the source count:

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_freshness.py" --mark-refreshed <domain> --sources <n> --json
```

   After all thirteen, stamp the full refresh (the script does this automatically once every
   domain is refreshed; `--full` forces it).

4. **Verify no Theme Forge-internal content was lost in the rewrite:**

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_knowledge_drift.py" --internal-only --json
```

   A refresh rewrites prose freely, and content describing *this plugin* — a `tf_*.py` script, a
   `theme.json` field, plugin policy, a licence header — cannot be reconfirmed from the web, so
   it is the content most likely to be dropped as unverifiable. `design-researcher.md` forbids
   this, but the instruction is not self-enforcing and the agent cannot check itself (its tools
   are Read/Write/WebSearch/WebFetch — no Bash).

   Any `internal` finding is a regression **introduced by this refresh**: restore that paragraph
   into `$TF_HOME/knowledge/<domain>.md` from the plugin seed at
   `${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/knowledge/<domain>.md`,
   then re-run until clean. Never "fix" it with
   `tf_seed_knowledge.py --force` — that overwrites all the live files and discards the research
   you just paid for. `external` findings are expected and need no action: those are seed claims
   the refresh legitimately superseded.

   The 2026-08-26 refresh lost `motion_budget` (a **required** `theme.json` field), the
   `tf_slop.py` gate reference, hover gating, the `.ico` in-process packer note, the
   `tf_imagery.py` wiring, and the MIT and Apache-2.0 attribution headers from two files. This
   step is what would have caught it.

5. Regenerate `INDEX.md` if any domain's summary line changed.

6. Report a **per-domain changelog** — one line each: domain, source count, headline change.
   If a researcher hit `## Gaps` (no web access, tool unavailable), surface that honestly
   rather than claiming a refresh that didn't happen.

## No web access

If `WebSearch`/`WebFetch` is unavailable, say so plainly and stop — a forced refresh with no
web access can't do anything useful, and the seeded base remains in place. Don't mark domains
refreshed when they weren't.
