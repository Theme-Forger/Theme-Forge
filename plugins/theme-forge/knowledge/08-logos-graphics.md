# Logos, icons, and generated graphics

## Changed since last refresh
Seed baseline — no refresh yet.

Everything here is produced as **code**, not by an image model. SVG is written directly.

## Constructing a mark

Work on a grid. `viewBox="0 0 100 100"` for a mark, `0 0 320 80` for a horizontal lockup. Use `currentColor` for the primary fill so the mark inherits the theme, and keep stroke widths on a consistent unit.

Approaches that reliably produce something credible:

- **Geometric monogram** — the initial constructed from circles, rectangles, and arcs on a strict grid. Counters and stroke widths derived from one base unit.
- **Lettermark with a cut** — a letterform with one deliberate geometric intervention: a slice, a gap, an overlap, a rotated counter.
- **Abstract symbol** — two or three primitives in a relationship that echoes the product's concept. Nesting, orbit, convergence, stacking, flow.
- **Wordmark with a detail** — set the name in the theme's display face and modify one letter. Cheapest to produce and often the most professional-looking.
- **Container mark** — a symbol inside a rounded square or circle, which doubles as the app icon.

Constraints that separate a real mark from a generated one:

- It must work at **16×16**. Draw it, then look at it at 16px. Anything under ~3px stroke at that size disappears. Ship a simplified `favicon.svg` if the full mark can't survive.
- Single color first. If it only works with a gradient, it isn't a logo yet.
- No more than three shapes in the mark. Complexity reads as clip art.
- Optical alignment beats mathematical alignment. A circle next to a square needs to be slightly larger to look the same size.

## The asset set

| File | viewBox | Purpose |
|---|---|---|
| `logo.svg` | horizontal | Mark + wordmark lockup, for headers |
| `logomark.svg` | square | Mark alone |
| `wordmark.svg` | horizontal | Type alone |
| `icon.svg` | 1024×1024 | App icon; keep content inside a centered safe area |
| `favicon.svg` | 32×32 | Simplified; embed a `prefers-color-scheme` block |
| `pattern.svg` | tileable | Background texture |

Dark-mode favicon:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <style>
    :root { --fg: #1a1a2e; }
    @media (prefers-color-scheme: dark) { :root { --fg: #f0f0f5; } }
  </style>
  <path fill="var(--fg)" d="…"/>
</svg>
```

**This pattern does not survive rasterization outside a browser.** resvg — the
first and fastest rung of the rasterizer ladder — does not parse CSS custom
properties at all, and it does not honour the `var()` fallback either, so the
paint falls back to SVG's *initial* value. The failure is silent and differs by
property:

| Authored as | resvg renders | Result |
|---|---|---|
| `fill="var(--fg)"` | `fill` initial = **black** | wrong colour, looks plausible |
| `stroke="var(--fg)"` on `fill="none"` | `stroke` initial = **none** | **completely blank** |

`tf_raster.py` handles this without needing a browser at all. It detects
`var(--`, harvests the **default** declarations (ignoring anything inside an
`@media` block, so a dark-mode override can't be mistaken for the default),
substitutes them into the `var()` uses in a temp copy, and rasterizes that.
A PNG is a fixed-pixel artifact that can never respond to
`prefers-color-scheme` anyway, so the declared default is the only correct
value — and resolving it keeps the fast rung usable instead of forcing the
slowest one. `var(--x, #fallback)` with no declaration resolves to the
fallback. Anything genuinely engine-dependent (filter primitives) still routes
to the browser, and if no browser is reachable the result carries
`render_suspect` rather than passing as correct.

Still worth designing around:

- If you use `var()`, **put it on `fill`, never on `stroke` alone.** A
  wrong-coloured icon is recoverable; an invisible one is easy to miss in
  review, because a blank 16px favicon on a light page reads as "not loaded
  yet" rather than as a bug.
- Keep the `<style>` override the only conditional part. The resolver takes the
  default from an inline `style="--fg:…"` on the root or a non-`@media`
  declaration; if the *only* declaration sits inside a media query there is no
  default to bake in.

## Favicon and app icon pipeline

The current minimal web set is three files plus a manifest:

- `favicon.ico` — a 32×32 image at the site root. Add `sizes="32x32"` on the `<link>`.
- `icon.svg` — the modern primary, with the dark-mode media query above.
- `apple-touch-icon.png` — exactly 180×180, opaque background, roughly 20px of padding.

Manifest icons: 192×192, 512×512, and a 512×512 with `"purpose": "maskable"` whose artwork stays inside a centered circle of about 409px diameter.

**Android adaptive icons** — two layers (opaque background, foreground, optionally a monochrome layer for themed icons), each 108×108 dp, masked to 72×72 dp, with a 66 dp-diameter safe zone.

**iOS** — a single 1024×1024 opaque PNG is enough; Xcode generates the rest and the system applies its own material treatment. Icon Composer (bundled with recent Xcode) accepts layered SVG/PNG input for the layered look.

**Rasterizing.** There's no dependency you can count on. `tf_tools.py`/`tf_raster.py` try, in
order: `resvg`, `@resvg/resvg-js-cli` (needs node), `rsvg-convert -w 512 -h 512 in.svg -o
out.png`, `magick -background none in.svg -resize 512x512 out.png` (ImageMagick), `inkscape
in.svg --export-type=png --export-width=512`, `npx sharp-cli`, then Playwright/Chromium as the
last resort. (Python `cairosvg` is not part of this ladder — it needs the native Cairo library
installed separately, which is a much heavier ask than the CLI tools above, so it was left out
rather than wired in.) If none are available, ship the SVGs and write `RASTERIZE.md` with the
exact commands — that's a better outcome than a broken build step.

**The `.ico`.** No external tool is needed: `tf_raster.py --ico --in brand/favicon.svg --out
favicon.ico --sizes 16,32` rasterizes each size and packs the result. An ICO is a container
around image payloads rather than a codec of its own — a 6-byte header, a 16-byte directory
entry per image, then the payloads — and Windows Vista onward accepts embedded PNG verbatim,
so the packer is pure stdlib and reuses PNGs the ladder already produced. `magick icon-32.png
icon-16.png favicon.ico` remains a valid manual equivalent, and `png-to-ico` / `to-ico` are
the node options, but none of them are required. One hard limit: ICO stores each dimension in
a single byte, so **256px per side is the maximum** — anything larger cannot be represented
and is rejected rather than silently truncated.

**Optimizing.** `npx svgo --multipass icon.svg` (v4 line) strips editor metadata and redundant precision without changing rendering. Optional; never required.

## Procedural graphics

**Grain and noise** — the highest-value-per-line technique available. A grain overlay at 3–6% opacity makes flat gradients look like a considered surface instead of a CSS default.

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
  <filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch"/></filter>
  <rect width="100%" height="100%" filter="url(#n)" opacity="0.06"/>
</svg>
```

Keep `numOctaves` at 3 or below — it's expensive, and the visual difference above 3 is negligible.

**Mesh gradients** — several `radial-gradient()`s layered at different positions and sizes on a base color. Four to six blobs is plenty. Add grain on top.

```css
background:
  radial-gradient(at 20% 25%, oklch(0.7 0.16 264 / 0.5) 0px, transparent 55%),
  radial-gradient(at 80% 15%, oklch(0.72 0.14 190 / 0.45) 0px, transparent 50%),
  radial-gradient(at 60% 85%, oklch(0.68 0.15 330 / 0.4) 0px, transparent 55%),
  oklch(0.22 0.03 264);
```

**Dot and grid fields**

```css
background-image: radial-gradient(circle, oklch(0.5 0 0 / 0.18) 1px, transparent 1px);
background-size: 16px 16px;
```

**Blobs** — an SVG path from 5–7 points on a circle with randomized radii, joined with cubic curves. Two blobs animating between shapes gives ambient background motion for very little code.

**Conic spotlights** — `conic-gradient()` for radial sweeps, angular color wheels, and pie-shaped accents.

## Icons

Use a library rather than drawing a set. All of these are free for commercial use:

| Library | License | Count | Character |
|---|---|---|---|
| Lucide | ISC | ~1,700+ | 24px grid, 2px stroke, the shadcn default |
| Phosphor | MIT | ~7,700+ | Six weights including duotone |
| Heroicons | MIT | ~290 | Outline / solid / mini / micro, by the Tailwind team |
| Iconoir | MIT | 1,600+ | 1.5px stroke, no attribution required |
| Tabler | MIT | 5,000+ | Consistent 24px, large set |
| Material Symbols | Apache-2.0 | 2,500+ | Variable axes |

Default to **Lucide** — it's already in the shadcn ecosystem and its visual weight suits most directions. Choose **Phosphor** when the direction needs a weight the theme's stroke language calls for (duotone for warm/organic, bold for brutalist). Match the icon stroke width to the theme's border width; mismatched stroke weights are one of the most visible inconsistencies in a design system.

For the preview, inline the handful of paths you need. Don't reference an icon package.

## Iconify and themed icon sets

**Iconify** aggregates 220+ open-licensed icon sets behind one API and one toolchain. `@iconify/tools` provides a `customise` callback that rewrites SVG content at build time — adjusting stroke width, corner radius, colors, and stripping animations — across an entire set without touching individual files:

```js
customise: (content) => content.replaceAll('stroke-width="2"', 'stroke-width="1.5"')
```

This is the mechanism that makes a *themed* icon set — where every icon matches the theme's stroke language — achievable without manually editing each path. The public API at `api.iconify.design` is free. Attribution requirements depend on the underlying set's license; always check `12-asset-tooling.md` before selecting a set.

## Text outlining for portable wordmarks

A wordmark set as `<text>` fails anywhere the font isn't available — including `react-native-svg`, `<img>` tags, and PDF export. Convert it to outlined paths for portability.

**opentype.js** (MIT) — `font.getPath(text, x, y, size).toPathData(3)` returns raw SVG path data with kerning. Supports TrueType `glyf` and PostScript CFF tables. **Does not parse WOFF2** — fetch the TTF or OTF variant from `fonts.gstatic.com`, not the WOFF2 the Google Fonts CSS API serves by default.

**fontkit** — better CFF2 and variable-font support. **text-to-svg** wraps opentype.js for a simpler interface. Python: **fonttools** with `SVGPathPen`.

**Boolean path operations** for knockouts and counters (no design tool needed): **paper.js** (`unite`, `subtract`, `intersect`), **martinez-polygon-clipping**, **flatten-svg**, **svg-path-boolean**. Python: **shapely** for polygon ops, **svgpathtools** for bézier math.

## Rasterizer comparison

The speed/fidelity/dependency tradeoff matters for the native asset pipeline. Full comparison in `12-asset-tooling.md`; summary:

- **resvg** (Rust) — most accurate for plain SVG; no filters.
- **npx sharp-cli** — fastest in batch (~3.5× resvg-js); depends on librsvg for font rendering.
- **Playwright/Chromium** — the only option that renders SVG filters (`feTurbulence`, `feGaussianBlur`) and web fonts correctly. Use it when accuracy matters; it's also the slowest.

When no rasterizer is available: write a `RASTERIZE.md` with exact CLI commands for the user to run. Return `ok: true` — missing a rasterizer is not a generation failure.

## Sources
Web app manifest and favicon practice; Android adaptive icon and Apple app icon specifications; SVGO documentation; icon library licenses; opentype.js and fontkit repositories; Iconify documentation; rasterizer benchmarks. Accessed for seed compilation, August 2026.
