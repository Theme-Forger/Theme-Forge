# Asset tooling, licensing, and external services

## Changed since last refresh
Seed baseline — no refresh yet.

## Refresh priority
**High.** This file records license terms, rate limits, and version-specific breakage rather than technique. A stale fact here can produce a theme the user cannot legally ship, or one that renders blank on a device. When refreshing, verify terms against the provider's own current documentation — not a blog post, not an aggregator, not this file's previous contents.

---

## Rasterization

No dependency can be assumed. Detect what exists and degrade to documented manual steps.

| Order | Tool | Character |
|---|---|---|
| 1 | `resvg` | Rust, zero deps, correct output, custom font loading. Slower at high volume; has crashed on very large batches. |
| 2 | `npx @resvg/resvg-js-cli` | Same engine, needs node. |
| 3 | `rsvg-convert` | Fast, common on Linux. |
| 4 | `magick` (ImageMagick 7) | Also produces `.ico`. Uses Ghostscript for SVG, so minor rendering differences. |
| 5 | `inkscape` | Needs installed fonts. Heavy. |
| 6 | `npx sharp-cli` | libvips backend, fastest in batch — roughly 3.5× resvg-js on a published 400-icon benchmark. Fonts render only if available to librsvg. |
| 7 | Playwright / Chromium screenshot | **The only option guaranteed to render SVG filters and web fonts correctly.** Slowest. |

Option 7's position understates it. Anything with `feTurbulence`, `feGaussianBlur`, or a web font needs a real browser renderer. Use the fast tools for plain geometry and the browser for filter-bearing assets.

Python: `cairosvg` (LGPL) handles filters, gradients, and masks accurately but needs Cairo and libffi. `pyvips` for speed. (Background only — neither is in `tf_tools.py`'s actual detection ladder above; both need a native library Theme Forge doesn't try to detect.)

`.ico`: Theme Forge needs no dependency here — `tf_raster.py --ico` packs one itself. An ICO is
a container (6-byte header, 16-byte directory entry per image, then payloads), and Vista+ accepts
embedded PNG, so packing is stdlib byte assembly over PNGs the rasterizer ladder already made.
**Maximum 256px per side** — the format stores each dimension in one byte, with 0 meaning 256.
`png-to-ico`, `to-ico`, and ImageMagick remain valid manual equivalents. The old `svg2png`
package is dead — don't reach for it.

---

## SVG optimization — the animation trap

SVGO is on the **v4** line (MIT). It does not understand the relationship between CSS selectors, SMIL targets, and the DOM, so it removes things that merely *look* unused.

**Plugins that break animated SVGs**, and what each destroys:

| Plugin | Damage |
|---|---|
| `cleanupIds` | The worst. Renames or removes the IDs that SMIL, CSS, and JS target. |
| `inlineStyles` | Dissolves `<style>` blocks, taking `@keyframes` with them. |
| `minifyStyles` | Drops keyframe rules it believes are unused. |
| `removeHiddenElems` | Deletes elements an animation later reveals. |
| `mergePaths` | Merges away paths that were individually animated. |
| `collapseGroups` | Collapses groups carrying animated transforms. |
| `removeUnknownsAndDefaults` | Strips attributes it doesn't recognize, including some animation attributes. |

Run two configs. Static assets get `preset-default` plus `prefixIds`. Animated assets get `preset-default` with all seven above disabled, plus `prefixIds` — which does the ID-collision job `cleanupIds` was there for, without breaking references.

**`prefixIds` only prevents collisions within one theme unless you set the prefix.** Its default
prefix is derived from the *file name* alone, so every theme's `pattern.svg` produces the
identical `pattern_svg__a`. Because each file is optimized in isolation, nothing in svgo can
notice that six themes just minted the same id. Pass an explicit
`params: { prefix: "<stem>-<theme-slug>" }` — `tf_optimize.py` derives exactly that from the
nearest ancestor holding `theme.json`, overridable with `--id-prefix`. Put the stem first: theme
slugs start with a digit (`01-…`) and a leading digit is illegal in a CSS identifier.

Re-running is safe — `prefixIds` replaces an existing prefix rather than stacking, so
`pattern_svg__a` becomes `pattern-01-glasswire__a`, not a doubled id, and references are
rewritten with it.

Tweak via `overrides` on `preset-default` rather than composing a plugin list from scratch; a hand-built list silently loses future default improvements.

If SVGO isn't available, skip optimization. Unoptimized SVG works. Broken SVG doesn't.

---

## Icon libraries

All of the following are free for commercial use with **no attribution requirement**:

| Library | License | Count | Character |
|---|---|---|---|
| Lucide | ISC | ~1,700+ | 24px grid, 2px stroke. The shadcn default. |
| Phosphor | MIT | ~7,700+ | Six weights including duotone. |
| Heroicons | MIT | ~290 | Outline / solid / mini / micro. Tailwind team. |
| Iconoir | MIT | 1,600+ | 1.5px stroke, no attribution. |
| Tabler | MIT | 5,000+ | Consistent 24px, very large set. |
| Material Symbols | Apache-2.0 | ~2,500 | Variable axes. |
| Remix Icon | Apache-2.0 | ~2,800 | Neutral, well-balanced. |

**Iconify** aggregates 220+ sets behind one API and one toolchain. `@iconify/tools` provides a `customise` callback that rewrites SVG content at build time — stroke width, corner radius, colors, opacity, stripping animations — across an entire set:

```js
customise: (content) => content.replaceAll('stroke-width="2"', 'stroke-width="1.5"')
```

This is what makes a *themed* icon set possible rather than just a chosen one. The public API at `api.iconify.design` is free.

Match icon stroke width to the theme's border width. Mismatched stroke weights are among the most visible inconsistencies in a design system, and they're invisible in a token file — you only see it in a contact sheet.

---

## Text to outlines

A wordmark set as `<text>` breaks anywhere the font isn't loaded, including `react-native-svg`. Outline it.

**opentype.js** (MIT) — `font.getPath(text, x, y, size).toPathData(3)` returns raw path data. Supports TrueType `glyf` and PostScript CFF, kerning via GPOS and `kern`, ligatures. **Does not parse WOFF2** — fetch the TTF or OTF from `fonts.gstatic.com`, not the WOFF2 the Google Fonts CSS API serves.

**fontkit** — better CFF2 and variable-font support. **text-to-svg** wraps opentype.js. Python: **fonttools** with `SVGPathPen`.

Boolean path operations, for knockouts and counters, without a design tool: **paper.js** (`unite`, `subtract`, `intersect`), **martinez-polygon-clipping**, **flatten-svg**, **svg-path-boolean**. Python: **shapely** for polygon ops, **svgpathtools** for bézier math.

---

## Avatars — DiceBear per-style licensing

**DiceBear 10.** Core is MIT. 55 styles. Free hosted API at `api.dicebear.com/10.x/<style>/svg?seed=<seed>`, self-hostable in one Docker container, CLI via `npx dicebear`. Native libraries for JavaScript, PHP, Python, Rust, Go, and Dart, all passing a shared test suite that requires **byte-identical SVG output** from the same seed. Determinism comes from FNV-1a hashing plus Mulberry32.

**Each style carries its own license.** This is the fact most likely to catch someone out:

| License | Styles | Attribution |
|---|---|---|
| **CC0** | Identicon, Initials, Lorelei, Notionists, Open Peeps, Pixel Art, Rings, Shapes, Thumbs | **None** |
| CC-BY-4.0 | Adventurer, Big Ears, Big Smile, Croodles, Micah, Miniavs, Personas | **Visible credit required** |
| Other free-commercial | Avataaars, Bottts | Check current terms |

Default to CC0 only. Adventurer and Micah are the two most-reached-for styles and both require credit — an easy mistake that lands a legal obligation on the user.

Theming: `backgroundColor` plus per-style color options accept the theme's palette.

**Alternatives.** `boring-avatars` (MIT, React, takes an explicit `colors` array) is the lighter choice for pure geometry. Also `minidenticons`, `jdenticon` (MIT), `multiavatar`, `identicon.js`.

**Offline fallback.** A deterministic geometric identicon is trivial in pure Python — hash the seed, map bits to a symmetric 5×5 grid, fill with theme colors. No network, no dependency, and it looks deliberate because it uses the palette.

---

## Stock photography — terms and limits

**Verify these against each provider's current documentation on every refresh.** They are license terms, not technique, and they change.

| Provider | Attribution | Rate limit | Hosting | Notes |
|---|---|---|---|---|
| **Pexels** | **Not required** (appreciated) | 200/hr, 20,000/month | Either | SDKs for Ruby, JS, .NET. The only provider Theme Forge implements. |

Pexels is the only stock-photo provider Theme Forge fetches from (`tf_imagery.py`, gated on
`PEXELS_API_KEY`) — no attribution burden, no hosting constraint, either license terms a theme
handed to someone else can live with. Without a key, imagery falls back to an art-direction
brief plus deterministic `picsum.photos` placeholders (below); it does not try another provider.

**Placeholders**, safe for previews but never for shipped brand imagery: `picsum.photos` (deterministic via `/seed/<string>/1200/800`), `placehold.co` (accepts colors, so it can render in the theme palette).

---

## Image-generation MCP servers

All require the user's own API key. Several are alpha personal projects — describe them as such rather than as infrastructure.

| Server | Providers | Notes |
|---|---|---|
| `shinpr/mcp-image` | Gemini, GPT Image, BytePlus Seedream | MIT. Ships a prompt-optimization skill. |
| `guinacio/claude-image-gen` | Gemini, OpenAI | Reference images, inpainting. Available as skill or MCP server. |
| Black Forest Labs FLUX MCP | FLUX.2 | Official. Remote OAuth HTTP endpoint. Bills to the user's BFL org. |
| `GongRzhe/Image-Generation-MCP-Server` | Replicate FLUX | |
| `TamerinTECH/claude-code-generate-images-mcp` | Gemini, Azure OpenAI, Flux | |
| `pvliesdonk/image-generation-mcp` | Multi-provider | Includes a zero-cost placeholder provider. |

Never call one unprompted. Offer it, and only when the user has one connected.

---

## Art direction briefs

The correct output when no image source exists. A brief that's actually usable — as a prompt, or as a handoff to a photographer — contains:

- **Subject** — what is depicted
- **Context** — setting, situation, time of day
- **Composition** — crop, framing, focal point, aspect ratio, pixel dimensions
- **Lighting** — direction, quality, temperature
- **Palette** — hex values pulled from the theme's own tokens
- **Mood** — three adjectives, drawn from the theme's thesis
- **Negative constraints** — what to avoid

The Subject-Context-Style framing is the established shape and is what the prompt-optimization skills in the MCP servers above expect. A good brief is a real deliverable, not a consolation prize.

---

## 3D

**Code-authorable:** three.js scenes, procedural and parametric geometry, instanced meshes, materials, lighting. `react-three-fiber` and `drei` for React. CSS 3D transforms (`transform-style: preserve-3d`, `perspective`, `rotateX/Y`) give pseudo-3D UI with no library at all.

**Not code-authorable:** modeled organic or branded assets. Source them CC0 instead:

| Source | License | Character |
|---|---|---|
| Poly Haven | CC0 | HDRIs, textures, models |
| Quaternius | CC0 | Stylized low-poly packs |
| Kenney | CC0 | Game-oriented asset packs |
| Sketchfab | Filter to CC0 / CC-BY | Large, mixed quality |

glTF/GLB is the format to target. `<model-viewer>` displays a GLB with one custom element.

**Editor-only:** Spline, Rive 3D. Export and embed, don't generate.

**Headless preview:** screenshot a local WebGL page with Playwright or Puppeteer. Do **not** use `headless-gl` — WebGL1 only, and three.js deprecated WebGL1 at r163. Headless WebGPU is still incomplete; blank-canvas reports are common.

**Native:** `react-three-fiber` via `expo-gl` and `expo-three` works for moderate scenes with a real performance ceiling and setup friction. Not a default.

---

## The visual feedback loop

An agent generating SVG works blind — it emits coordinates and never sees the render. Closing that loop is the largest single quality gain available.

**Screenshot MCP servers:**

| Server | Maintainer | Character |
|---|---|---|
| `chrome-devtools-mcp` | Google Chrome DevTools team | Official. `take_screenshot`, `take_snapshot` (accessibility tree), performance traces, network and console. Chromium only. Use headless with an isolated `user-data-dir` for long agent runs. |
| `playwright-mcp` | Microsoft | Official. Cross-engine. Defaults to accessibility-tree snapshots; `browser_take_screenshot` for pixels. |
| `puppeteer-mcp` | community | Chromium only, screenshot-first. |
| `browser-use`, Browserbase, `mcp-chrome` | various | Agentic, managed, and real-profile options. |

Guidance: accessibility snapshots are cheap in tokens and often sufficient. Reach for pixels when you need to *look* — legibility, composition, visual regression.

**Automated checks that don't need eyes:** SVG bounding-box and viewBox validation, contrast ratios computed from tokens, overflow detection via DOM measurement, `axe-core` (MPL-2.0) via `@axe-core/playwright` or `@axe-core/cli` reading `results.violations`.

**Visual regression:** `pixelmatch` (Mapbox, ISC — per-pixel with anti-alias detection, smallest and fastest), `odiff` (MIT, native SIMD, roughly 6× faster), Playwright's built-in `toHaveScreenshot()` (uses pixelmatch underneath, waits for stability). `BackstopJS` is config-heavy and lightly maintained; `resemblejs` is largely stale.

**Prior art.** Anthropic's `frontend-design` skill instructs taking screenshots and self-critiquing — *a picture is worth 1000 tokens*. Anthropic's engineering write-up on long-running application development documents a generator/evaluator loop where an evaluator agent screenshots the live page, scores it against calibrated criteria, and feeds critique back over 5–15 iterations. That's the pattern worth copying, with a cap on iterations.

---

## Version-specific breakage worth tracking

Re-verify each of these on refresh. They're the ones that fail silently.

- **`react-native-svg`** — no `<filter>` support, no SMIL, no `<foreignObject>`. Filter rendering has regressed between minor versions (one release broke filters on iOS entirely). `<mask>` is supported but historically buggy. Pin a known-good version and test on both platforms.
- **SVGO** — the seven plugins above break animated output.
- **`headless-gl`** — WebGL1 only; three.js deprecated WebGL1 at r163.
- **`opentype.js`** — no WOFF2.
- **Scroll-driven CSS animations** — around 82% global support; Firefox still behind a flag in stable as of mid-2026. Gate with `@supports` and make the fallback *visible*, never hidden.
- **GSAP** — free including MorphSVG, DrawSVG, and MotionPath since v3.13 (April 2025), but under GreenSock's own license, **not MIT**. Worth stating when recommending it.

## Gaps
None recorded at seed time.

## Sources
Provider documentation for Pexels, Pixabay, Unsplash, DiceBear, and Iconify; SVGO, opentype.js, react-native-svg, and three.js repositories and changelogs; Anthropic Claude Code documentation and the `frontend-design` skill. Accessed for seed compilation, August 2026.
