# Theme Forge

A designer-in-a-box Claude Code plugin. From a project brief it generates six
distinct, production-ready themes in parallel, previews them across website / web app /
mobile surfaces in a single offline `gallery.html`, and applies the chosen one to the
project's detected stack — web, React Native, or a cross-platform monorepo.

## Quick start

```
/generate-themes rap and hip hop page. Make it lively and interactive.
```

No installation beyond the plugin is required for basic operation. All scripts use
Python 3.9+ stdlib only.

---

## External dependencies

The table below describes every tool Theme Forge can use, whether it is required or
optional, and what a user loses by not having it. `tf_tools.py --json` detects most of these
at runtime and caches the result (`current/tools.json`) — read it if you want to see exactly
what this machine has.

| Tool | Required? | Fallback | What you lose without it |
|---|---|---|---|
| **Python 3.9+** (stdlib only) | **Required** | None | All scripts (`tf_*.py`) won't run. No fallback exists. |
| **Node.js + npx** | Optional | Stdlib fallback activates | Needed for `impeccable`, `svgo`, `opentype.js`, the node-based rasterizer/Playwright options, and `resvg-js`. Without it, everything below that lists a Python/no-node fallback still works; everything that doesn't, degrades to its documented fallback. |
| **impeccable** (`npx impeccable`) | Optional-with-fallback | `tf_slop.py` runs 37 static rules instead of 59 | 22 additional AI-slop rules are not checked. Hard-stops for the HIGH-severity motion rules (scale(0), ease-in, ungated-hover, missing reduced-motion, and others) still fire via the stdlib fallback. Note: the upstream `impeccable` project has grown past 59 rules since this pin — Theme Forge only requests the 59 it knows about. |
| **Playwright MCP** or **Chrome DevTools MCP** (browser, for `design-critic` + `theme-fixer`) | **Required for the visual-critique pass specifically** — not gracefully optional | None once both MCP options *and* a node/Python Playwright install are all unavailable | If literally no browser can be reached, `design-critic` does **not** silently fall back to structural-only analysis — it writes a hard `VISUAL REVIEW BLOCKED` line to `critique.md` and the pipeline's pre-flight check (`SKILL.md` Step 5d-pre) stops and asks you to run `npx @playwright/mcp@latest` before continuing. `theme-fixer` degrades more gently (falls back to static reasoning for the one or two fixes that need live measurement, per its own §0), but design-critic's screenshot pass is a hard requirement, not an optional enhancement. |
| **Playwright (node/Python package)** | Optional, but the **only correct renderer** for filter-bearing SVGs | Falls through to the rest of the rasterizer ladder with `render_suspect` set on the result, or triggers the hard-stop above if it was the last browser option | Used three ways: (1) as rasterizer-ladder option 7, (2) as the third browser option `design-critic`/`theme-fixer` try after both MCP servers fail, and (3) auto-selected by `tf_raster.py` for SVGs using filter primitives. **CSS custom properties do *not* need it:** resvg cannot parse `var()` at all (not even the fallback), so `fill="var(--fg)"` would render black and `stroke="var(--fg)"` nothing — but `tf_raster.py` resolves the declared defaults into a temp copy first, which is the only correct value for a fixed-pixel artifact anyway, so the fast rung stays usable. `tf_tools.py` detects Playwright without launching a browser — it checks the package is importable and that browser binaries exist under `%LOCALAPPDATA%\ms-playwright` / `~/.cache/ms-playwright`. |
| **svgo** (`npx svgo`) | Optional-with-fallback | `tf_optimize.py` copies the SVG through unoptimized | File size and editor-metadata cleanup are skipped; the SVG still renders and animates correctly. Two separate SVGO configs exist (static vs. animated) because the default preset strips attributes SMIL/CSS-animated assets depend on. |
| **Rasterizer** — `resvg`, `@resvg/resvg-js-cli` (node), `rsvg-convert`, ImageMagick (`magick`), Inkscape, `sharp-cli` (node), or Playwright/Chromium (last resort) | Optional-with-fallback | `tf_raster.py` ships the SVG as-is and writes `RASTERIZE.md` with the exact manual commands | Native app icons/splash screens/adaptive icons stay SVG-only; `app.json`'s PNG fields point at paths that don't exist yet until you run one of the `RASTERIZE.md` commands yourself. Never a build failure. Note that "never fails" is not the same as "always correct": each ladder entry has its own flag spelling, and a rejected flag looks identical to a missing tool — the run just falls through to the next entry and, eventually, to the browser. Run `tf_raster.py --selftest` to check every available rasterizer actually renders a known SVG at the requested geometry. `cairosvg` is deliberately **not** in this ladder — it needs the native Cairo library installed separately, a much heavier ask than the CLI tools above. |
| **opentype.js** (via `node`) | Optional | Pure-Python TrueType parser, then a plain `<text>` SVG element as the last resort | Wordmark-to-outline conversion (turning display type into a vector logomark) loses fidelity down each fallback tier; the final `<text>` tier is what actually fires on some Windows setups in practice and requires a manual step noted in `RASTERIZE.md` before shipping. |
| **`.ico` packing** — ImageMagick / `png-to-ico` / `to-ico` | **Not needed** | n/a — `tf_raster.py --ico` does it in-process | Nothing. An ICO is a container rather than a codec (header + one directory entry per image + payloads), and Vista onward accepts embedded PNG, so `favicon.ico` is assembled from PNGs the rasterizer ladder already produced, in pure stdlib. The external tools remain valid manual equivalents. Format limit: 256px per side, enforced rather than silently truncated. |
| **`PEXELS_API_KEY`** (env var) | Optional | Art-direction brief + deterministic `picsum.photos` placeholder URLs | No real stock photography in previews — `tf_imagery.py` never tries another provider (Pexels is the only one implemented; see `knowledge/12-asset-tooling.md`). Never a failure. The **same key** also serves video via `tf_assets.py --tiers video`. |
| **Fontsource** (`api.fontsource.org`) | Optional, no key | Theme ships a font *family name* only; `tf_outline.py` falls back through its own ladder | Keyless. Fetches the theme's declared display family as **TTF** (not WOFF2, which `opentype.js` cannot parse and React Native cannot use), gated on the machine-readable per-font `license` field. Never a failure. |
| **Poly Haven** (`api.polyhaven.com`) | Optional, no key | Generated geometric assets only | Keyless, CC0, 1k JPG colour maps only (HDRIs start at 1.73 MB and need a WebGL loader). Assets are **downloaded and vendored, never hotlinked** — the API ToS §2.5 requires a "Powered by Poly Haven" credit for live-API use, which vendoring avoids. |
| **SVG patterns** | **Not needed** | n/a — `tf_assets.py` generates them | Nothing. Every pattern service verified is browser-only with no HTTP API (see `knowledge/14-asset-sources.md`), so patterns are generated locally from the theme's own tokens: a few hundred bytes each, recolorable, offline-native, no license obligation. |
| **WebSearch / WebFetch** | Optional | Seeded knowledge base (August 2026) | Real-time design trend research is skipped. The seeded knowledge still produces good themes; they just won't reflect changes in the last few months. |
| **frontend-design** plugin skill | Optional enhancement | Essential guidance inlined in agents | More detailed direction-picking methodology. Core anti-default checks are inlined in `theme-designer.md` and `design-critic.md` and remain active regardless. |
| **frontend-aesthetics** plugin skill | Optional enhancement | Essential guidance inlined in agents | Additional anti-pattern checklist. The demoted font list, cream-cap rule, and motion rules from `13-anti-patterns.md` are already in agent prompts and fire independently. |

**Summary:** A machine with only Python 3.9+ gets full theme generation, 37 of 59 slop
rules, and seeded design knowledge — but **not** a shippable gallery, because the visual-critique
pass genuinely requires a working browser (Playwright MCP, Chrome DevTools MCP, or a node/Python
Playwright install) and will stop the pipeline rather than skip itself if none is reachable.
Everything else in the table — svgo, the rasterizer ladder, `opentype.js`, `PEXELS_API_KEY` —
adds fidelity without blocking the core workflow.

---

## Attribution

This plugin contains content adapted or ported from:

### impeccable
- Repository: https://github.com/pbakaus/impeccable
- License: **Apache License 2.0**
- Adapted into: `knowledge/13-anti-patterns.md` (64-rule catalog derived from
  impeccable's 59-rule detection set) and `scripts/tf_slop.py` (rule categories,
  severity model, stdlib checks 1–5)

### emilkowalski/skills
- Repository: https://github.com/emilkowalski/skills
- License: **MIT License** — Copyright © Emil Kowalski
- Files ported: `skills/review-animations/STANDARDS.md` and `skills/animate/SKILL.md`
  (the `find-animation-opportunities` and `improve-animations` skills from this repo
  are deliberately **not** installed or depended on by Theme Forge at runtime — see the
  attribution comment in `knowledge/06-motion.md`)
- Ported into: `knowledge/06-motion.md` (frequency gate, easing tokens, all
  per-recipe values, severity rubric, reduced-motion approach), `agents/theme-designer.md`
  (frequency gate table, severity rubric, press feedback and entrance recipes), and
  `scripts/tf_slop.py` (severity rubric and stdlib rules 6–14)

### Taste Skill (MIT)
Categorical quality rules (premium-consumer palette ban, eyebrow density, section-number
eyebrows, accent consistency, duplicate-cta-intent, dark-mode-pure-black-white), the
three-dial intensity system (plus its brief-vocabulary inference table and use-case
presets), and font-pairing guidance (including the Fraunces/Instrument Serif ban and
serif-rotation pool) are adapted from
[skills/taste-skill/SKILL.md](https://github.com/Leonxlnx/taste-skill) by Leonxlnx,
MIT License, Copyright 2026 — refreshed 2026-09-03 against the current upstream content.

See [`NOTICE`](NOTICE) for full license texts.

---

## Plugin layout

```
plugins/theme-forge/
├── .claude-plugin/plugin.json     plugin manifest
├── NOTICE                         third-party attribution
├── README.md                      this file
├── agents/                        design-researcher, theme-designer, brand-asset-designer,
│                                  surface-composer, design-critic, theme-applier
├── skills/                        generate-themes, apply-theme, export-theme,
│                                  refresh-design-knowledge
├── knowledge/                     13 seeded design-knowledge domains + FRESHNESS.json + INDEX.md
├── scripts/                       27 tf_*.py stdlib-only tools
├── templates/                     theme.schema.json, gallery chrome (gallery.shell.html,
│                                  gallery.css), device-frame chrome (device-frames.html),
│                                  a11y-reset.css — no shared page-structure templates; each
│                                  theme's own surfaces/<website|webapp|mobile>.{html,css}
│                                  (written by surface-composer) is the only source of that
│                                  theme's markup and styling
└── hooks/hooks.json               SessionStart seed hook
```
