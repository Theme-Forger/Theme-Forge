# Color

## Changed since last refresh
2026-09-03 (targeted refresh, 1 source — github.com/Leonxlnx/taste-skill, MIT): added the
"Premium-consumer palette ban" section (hardened hex anchors + 7 alternative palette
families + rotation rule) and the pure-white counterpart to the existing pure-black rule.

## Work in OKLCH

OKLCH is the default working space for UI color in 2026. It is perceptually uniform: equal lightness values look equally light regardless of hue, which is what makes programmatic palette generation predictable. In HSL, a yellow and a blue at the same `L` differ enormously in perceived brightness, and every generated ramp comes out lopsided.

Syntax: `oklch(L C H / alpha)` where L is 0–1 (or a percentage), C is 0 to roughly 0.37 in practice, H is 0–360 degrees. Browser support is universal across current engines.

```css
--brand: oklch(0.55 0.14 264);
--brand-hover: oklch(from var(--brand) calc(l - 0.06) c h);   /* relative color syntax */
--brand-tint:  color-mix(in oklch, var(--brand), white 85%);
```

Relative color syntax (`oklch(from …)`) and `color-mix()` let a theme derive its interaction states from one base color rather than hardcoding a dozen hex values. Prefer this — it's fewer tokens, and states stay consistent when the base changes.

## Gamut is the trap

Not every OKLCH triple is representable in sRGB. High chroma at very high or very low lightness falls outside the gamut, and browsers clip inconsistently. Always clamp chroma into gamut before emitting a hex fallback: binary-search C downward until the linear-sRGB conversion lands in `[0,1]` on all three channels.

Wide-gamut P3 is available via `color(display-p3 …)` behind `@supports (color: color(display-p3 1 1 1))`, with an sRGB fallback. Worth it for a saturated accent; not worth it for neutrals.

## Building a ramp

A good ramp is a lightness ladder with chroma tapered at both ends:

- **Steps**: 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950.
- **Lightness**: roughly 0.97 → 0.20, spaced perceptually rather than linearly — tighter in the middle where the eye is more sensitive.
- **Chroma**: peaks around 400–600 and tapers toward both ends. A 50-step at full chroma looks like a stain; a 950-step at full chroma looks purple-black.
- **Hue**: hold it constant, or drift it 3–8° across the ramp for a subtle richness. Warm shadows and cool highlights read as more considered. Don't overdo it.

Neutrals are not gray. A neutral ramp carrying 0.005–0.02 chroma at the brand hue makes a UI feel designed rather than defaulted. Pure `oklch(L 0 0)` grays look sterile next to a colored brand.

## Contrast

**WCAG 2.2 is the operative standard.** Its ratio-based formula:

- 4.5:1 — normal body text, AA
- 3:1 — large text (≥24px, or ≥18.66px bold) and non-text UI components/graphical objects, AA
- 7:1 — normal text, AAA

**APCA** is the perceptually-better algorithm being developed for WCAG 3.0. It's directional (light-on-dark and dark-on-light are different problems) and reports Lc on a roughly 0–106 scale. It is **not yet a normative requirement**. Report it alongside WCAG for future-readiness; gate on WCAG 2.2 AA.

WCAG 3.0 itself is still a Working Draft and is not expected to reach Recommendation before roughly 2028. Do not build compliance against it.

## Light and dark

Declare `color-scheme: light dark` on `:root` so form controls, scrollbars, and the canvas follow, then use `light-dark()` for paired values:

```css
:root {
  color-scheme: light dark;
  --surface: light-dark(oklch(0.99 0.002 264), oklch(0.21 0.012 264));
  --text:    light-dark(oklch(0.24 0.02 264),  oklch(0.95 0.008 264));
}
```

Dark mode is not an inversion. Practical rules:

- Reduce chroma in dark mode. A saturated color on a dark ground vibrates.
- Don't use pure black **or pure white** as a surface color — `#000000`/`#ffffff` (`oklch(0.16–0.22)` for the dark side) reads as a designed surface, not an absence. This applies to whichever mode is the "inverted" one for a given theme, not just a literal `.dark` class — a dark-default theme's lighter alternative surface should not land on pure `#ffffff` either.
- Elevation reverses: in light mode raised surfaces get shadows, in dark mode they get *lighter*. Shadows are nearly invisible on dark grounds — use surface lightness steps or borders instead.
- Large areas of the brand color rarely survive the switch. Dark themes usually want the brand as an accent, not a field.

A useful trick for automatic foregrounds, approximating the not-yet-universal `contrast-color()`:

```css
--on-brand: oklch(from var(--brand) round(1.21 - l) 0 0);
```

## Premium-consumer palette ban

For premium-consumer briefs (cookware, wellness, artisan, luxury, heritage craft, DTC home
goods) the reflexive default is warm beige/cream + brass/clay/oxblood/ochre + espresso/ink
dark text. This is now the second-most-recurring AI tell after the em-dash, and `tf_slop.py`'s
`premium-consumer-palette` rule blocks it mechanically. Concretely banned as a default
background + accent combination (hardened against `skills/taste-skill/SKILL.md`,
github.com/Leonxlnx/taste-skill, MIT, refreshed 2026-09-03):

- Backgrounds: `#f5f1ea`, `#f7f5f1`, `#fbf8f1`, `#efeae0`, `#ece6db`, `#faf7f1`, `#e8dfcb`
- Accents: `#b08947`, `#b6553a`, `#9a2436`, `#9c6e2a`, `#bc7c3a`, `#7d5621`
- Text: `#1a1714`, `#1a1814`, `#1b1814`

**Alternative palette families** for premium-consumer briefs — rotate through these rather than
reaching for warm-cream-and-brass every time, and don't repeat the same family across
consecutive premium-consumer runs (cross-check `used.md`'s primary/accent hue columns):

1. **Cold luxury** — cool near-white or pale grey ground, chrome/steel/graphite accent
2. **Forest** — deep green ground or accent, no warm neutral in sight
3. **Black and tan** — near-black ground, warm tan/leather accent (skips the cream entirely)
4. **Cobalt + cream** — a genuine saturated blue as the accent, breaking the brass-metal cliché
5. **Terracotta + slate** — terracotta as accent only, paired with cool slate rather than cream
6. **Olive + brick + paper** — three-note earth palette, avoids the beige-and-brass duo
7. **Pure monochrome + single pop** — near-grayscale ground/type, one saturated accent color

## Sources
CSS Color Module specifications; MDN color value reference; WCAG 2.2 Recommendation; APCA documentation. Accessed for seed compilation, August 2026. Premium-palette ban and alternative families cross-referenced against github.com/Leonxlnx/taste-skill (MIT), 2026-09-03.
