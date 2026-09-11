---
name: audit-motion
description: >-
  Surveys an existing project's own animation and motion code and writes a prioritized,
  self-contained fix plan — read-only, never edits source. Use after apply-theme finishes, or
  whenever someone asks to audit, review, or improve a project's existing animations.
argument-hint: "[project directory, defaults to the current one]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), Bash(python3 ${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/*), Read, Write, Glob, Grep, Task
---

# Audit motion

Surveys a real project's own motion code (not a Theme Forge-generated preview) and produces one
markdown plan naming exact fixes at exact locations. Never modifies the project. Two-stage: a
script finds every mechanical pattern match for free, an agent decides which ones are worth
fixing and in what order.

## Step 1 — Resolve the target

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_paths.py" --json
```

Default to the current project root unless the argument names a different directory. Confirm
it exists and looks like a real project (has a package manifest or a recognizable source
layout) before scanning — don't run this against an empty or unrelated directory.

## Step 2 — Mechanical scan

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_motion_audit.py" --root <target-dir> --json
```

This is a free, exact text-pattern scan — no LLM judgment yet. It reports every plain-text match
for a fixed set of motion anti-patterns (overshoot easing, `scale(0)` entrances, `ease-in` on
transitions, `transition: all`, ungated `:hover`, missing `prefers-reduced-motion`, motion with
no custom easing anywhere) across the project's `.css`/`.scss`/`.js`/`.jsx`/`.ts`/`.tsx` files,
each with a file path and line number. It is a text scan, not a framework-aware parser — say so
plainly if `files_scanned` is 0 or surprisingly low (e.g. the project's motion lives entirely in
a CSS-in-JS object syntax this scan can't see into).

If `finding_count` is 0, report that plainly and stop — don't spawn the agent to triage nothing.

## Step 3 — Triage and plan (motion-auditor, Task)

Spawn one `motion-auditor` subagent with: the project root, the full JSON findings list from
Step 2, and the output path for its plan (default `MOTION-AUDIT.md` at the project root, or a
path the user named). It decides which findings are actually worth fixing, orders them by
leverage, and writes one self-contained plan file — it does not edit the project itself.

## Step 4 — Report

Relay what the agent returned: the plan file path, how many mechanical findings were kept vs.
triaged out, and the single highest-leverage fix in one sentence. Point the user at the plan
file for the rest — don't reproduce it in chat.

## Notes

- This skill is offered automatically at the end of **apply-theme** (its own Step 8), but also
  works standalone against any project, whether or not Theme Forge ever touched it.
- Nothing here writes to the project except the one plan file the agent produces. If the user
  wants the plan actually applied, that's a separate, explicit follow-up — hand the plan to
  whatever agent or session they want to execute it with, don't apply it yourself in this flow.
