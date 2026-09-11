# Theme Forge

This repository is a **Claude Code plugin marketplace** containing one plugin, `theme-forge`.

Theme Forge is a designer-in-a-box. From a project brief (an argument, a `CLAUDE.md`,
or the codebase itself) it researches current design practice, generates six distinct,
production-ready themes in parallel, previews them across website / web app / mobile
surfaces in a single offline `gallery.html`, and applies the chosen one to the project's
detected stack — web, React Native, or a cross-platform monorepo.

## Repository layout

```
./
├── .claude-plugin/marketplace.json    marketplace manifest
├── CLAUDE.md                          this file
├── README.md                          session transcript + usage
├── LICENSE                            MIT
└── plugins/theme-forge/               the plugin itself
    ├── .claude-plugin/plugin.json     plugin manifest (ONLY file in .claude-plugin/)
    ├── agents/                        design-researcher, theme-designer, brand-asset-designer,
    │                                  surface-composer, theme-applier, design-critic, theme-fixer
    ├── skills/                        generate-themes, apply-theme, export-theme, refresh-design-knowledge
    ├── knowledge/                     13 seeded design-knowledge domains + FRESHNESS.json + INDEX.md
    ├── scripts/                       27 stdlib-only Python tools (tf_*.py)
    ├── templates/                     schema (theme.schema.json), gallery chrome (gallery.shell.html,
    │                                  gallery.css), device-frame chrome (device-frames.html),
    │                                  a11y-reset.css — no shared page-structure templates; each
    │                                  theme's own surfaces/<website|webapp|mobile>.{html,css}
    │                                  (written by surface-composer) is the only source of that theme's
    │                                  markup and styling
    └── hooks/hooks.json               SessionStart seed hook
```

Layout rule: **only `plugin.json` lives inside `.claude-plugin/`.** Every component
directory sits at the plugin root.

## Working on the scripts

Conventions and selftest requirements live in `plugins/theme-forge/scripts/CLAUDE.md`
(loads automatically when editing script files).

**Safety prohibition (always applies, not just when editing scripts):**
Never delete a path that wasn't derived from `tf_paths.py`; assert it is under `TF_HOME` first.

## Runtime data

All generated output lives outside the plugin (which is replaced on update), under `TF_HOME`:

1. `$THEME_FORGE_HOME` if set
2. `$CLAUDE_PLUGIN_DATA` if set
3. `$HOME/.theme-forge`

`$TF_HOME/current/` holds the only theme set retained; it is wiped at the start of every
generate run. Exported zips live in the user's project and are never touched.

**Screenshots have exactly one home: `$TF_HOME/current/screenshots/`, split into two
subfolders by who wrote them.** `visual review/` is **design-critic's alone** — `tf_gallery.py`
counts its PNGs and prints the total as the gallery header's "visual critique: N shots", so
anything else written there overstates the review that actually happened (a real run reached 86
PNGs against a critic that took 10). Every other agent's verification shots — brand-asset
contact sheets, theme-fixer geometry proofs, font specimens — go to `build/`
(`tf_paths.build_shots_dir()`), which is deliberately uncounted.
`tf_paths.py` owns the path (`current_screenshots`), scaffolds it, and exposes
`resolve_screenshot_path()`, which forces any relative or out-of-tree output path back
into it. `tf_reset.py` recreates it after each wipe and `tf_verify_wipe.py` allowlists it,
so last run's review images are cleared with the themes they depict rather than
accumulating. Nothing may write a screenshot to the project workspace, a bare relative
filename, `/tmp`, or the MCP server's `.playwright-mcp/` scratch directory — all four sit
outside `current/`, so the wipe cannot reach them, and images of long-deleted theme slugs
pile up there. When an MCP tool refuses to write to `$TF_HOME`, stage through `%TEMP%`
(already a permitted directory) and move the files across — never through the repo.

## The cross-platform contract

A theme's tokens are platform-neutral and resolved **twice** — once to CSS, once to React
Native. Neither resolution is the source of truth. `tf_native.py` is the gate that stops a
CSS-shaped value (`oklch()`, `clamp()`, `"16px"`, a multiplier `lineHeight`) from shipping
into a `theme.ts` where React Native would silently ignore it.
