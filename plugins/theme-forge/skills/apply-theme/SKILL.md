---
name: apply-theme
description: >-
  Applies a previously generated Theme Forge theme to the current project — design tokens, CSS
  variables, Tailwind theme block, NativeWind config, React Native theme object, and brand
  assets, matched to the project's detected stack, with a full backup first. Use when someone
  picks a theme to apply, says apply theme X, or wants to switch their web or Expo project to
  a different generated theme.
argument-hint: "<theme-slug-or-number>"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), Bash(python3 ${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/*), Read, Write, Edit, Glob, Grep, Task
---

# Apply theme

Applies one generated theme to the current project, safely, after showing a plan and getting a
go-ahead. Never write to the project before both of those happen.

## 1 — Resolve the theme

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_paths.py" --json
```

Read `current/run.json`. Resolve the argument (a number, slug, name, or loose description) to a
theme entry and its directory. If `current/` is empty or has no themes, say so and offer to run
**generate-themes** instead — don't guess.

## 1b — Quality check before applying

Read the resolved theme directory for `slop.json`. If present:

- Check `slop.json.ok`. If `false` (hard-stop findings survived), list each finding's
  `rule` and `message` and warn the user **before showing the plan**:

  > ⚠ This theme has **N unresolved quality finding(s)** that survived the generation
  > gate (regeneration budget was exhausted). The applied files will include these issues.
  > Findings: [list rules]. You can still apply — the backup lets you roll back — but
  > consider re-running **generate-themes** for a fresh attempt.

- If `slop.json` is absent, note it silently (no warning needed).
- Advisory-only findings (those without a hard-stop flag) do not need to be shown here.

Also read `current/run.json` field `residual_findings` for the same theme slug. If it
lists findings, surface them in the warning above rather than re-reading slop.json.

## 2 — Detect the stack

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_detect_stack.py" --root . --json
```

Note `platforms`, `confidence`, and `targets`. If `confidence` is `low`, ask targeted
questions before doing anything (which framework, which global stylesheet, is this the app or
the marketing site).

## 3 — Git check

If git is present and the tree is dirty, say so and ask whether to continue. **Don't refuse** —
plenty of people work dirty — but make sure they know the backup is your safety net, not their
uncommitted changes.

## 4 — Show the plan, then ask

Before writing anything, show:

- **Files to create** (prefer these) — e.g. `src/styles/theme.css`, `theme/theme.ts`.
- **Files to modify**, each with a one-line description of the change (e.g. "add one `@import`
  to `app/globals.css`", "add `ThemeProvider` + `useFonts` to `app/_layout.tsx`").
- **Files skipped and why** (node_modules, `.git/`, lockfiles, .env, gitignored).
- **Packages to install afterward**, with exact commands, and whether a **development build**
  is required.

Then ask for a go-ahead. If the user declines, stop cleanly with **nothing written**. Read the
matching reference before planning: `references/stack-web.md`, `references/stack-native.md`, or
— on a cross-platform monorepo — all of `stack-web.md`, `stack-native.md`, `stack-monorepo.md`.
See `references/rollback.md` for the backup layout.

## 5 — Apply

Spawn one `theme-applier` subagent with: the theme directory, the stack profile, and the
approved plan. It backs up every file it will touch into
`$TF_HOME/current/backups/<timestamp>/` **before** the first write, writes
`THEME-ROLLBACK.md` there, applies the theme, writes `THEME.md` at the project root, and never
runs a package manager.

## 6 — Report

Relay what the applier returned: files created, files modified, the backup path, the one-line
rollback command, the exact install commands the user must run, and anything skipped. If the
theme `requires_dev_build`, state it here in plain terms (Expo Go can't run it).

## 7 — Record

Update `current/run.json`'s `applied` field:

```json
"applied": { "slug": "…", "at": "…Z", "backup": "…/backups/<timestamp>/" }
```

## 8 — Offer the zip

*"Want me to save this theme as a zip?"* On yes, run the **export-theme** flow.

## 9 — Offer a motion audit

*"Want me to check the project's existing animations for common issues? (This only reads the
project — nothing gets changed without you reviewing a plan first.)"* On yes, run the
**audit-motion** flow against the project root. This surveys the project's own motion code,
not the theme you just applied — genuinely useful whether the applied theme touched any
animation-heavy files or not.
