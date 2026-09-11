---
name: export-theme
description: >-
  Saves a generated Theme Forge theme as a zip file you can keep, share, or hand to a designer.
  Use when someone wants to save, export, download, back up, or share a generated theme.
argument-hint: "<theme-slug-or-number> [output-dir]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), Bash(python3 ${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/*), Read
---

# Export theme

A thin wrapper over `tf_export.py`. Works whether or not the theme was applied.

1. Resolve the theme from the argument (number, slug, name). If you only have a description,
   read `current/run.json` to map it to a slug.
2. Default the output directory to the **project root** (`.`) unless the user names another.
3. Run:

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_export.py" --theme <slug-or-number> --out <dir> --json
```

4. Report the zip path and size from the JSON. The zip contains the full theme directory plus a
   generated `HOW-TO-USE.md` covering plain CSS, Tailwind v4, shadcn/ui, Expo + NativeWind,
   bare React Native, the shared-tokens monorepo case, and rasterization.

Notes:

- It refuses to overwrite an existing zip without `--force`; by default it suffixes
  (`<slug>-theme-1.zip`). Mention the final filename it chose.
- The export is recorded in `current/run.json`'s `exported` array, which is what suppresses the
  "unexported previous set" warning on the next generate run.
- Exported zips live in the user's project and are **never** touched by a wipe.
