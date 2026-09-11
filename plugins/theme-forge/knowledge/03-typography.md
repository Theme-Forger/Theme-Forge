# Typography

## Changed since last refresh
2026-09-03 (targeted refresh, 1 source — github.com/Leonxlnx/taste-skill, MIT): moved
Fraunces from the "reach for these first" table into the demoted list alongside Instrument
Serif (both are now the two most-flagged LLM-favorite display serifs, per the upstream
source — the two entries had been contradicting each other in this file). Added the
"serif is a choice, not a default" doctrine, the 20-font serif rotation pool, and the
same-family-emphasis / italic-descender-clearance rules.

## Variable fonts by default

One file, multiple axes (weight, width, optical size, and family-specific axes like Recursive's `MONO`/`CASL` or Newsreader's optical-size range). Better performance than four static weights and more expressive range. Use `font-variation-settings` or the standard properties where they map.

## Font sources

**Reach for these first (the defaults).** Distinctive variable families that read as current
and are not yet over-exposed. Unless the brief names a face, a theme's body and display should
come from this set:

| Family | Character | Good for |
|---|---|---|
| Geist / Geist Mono | Vercel's product sans and mono | Technical, developer-facing, clean product UI |
| Bricolage Grotesque | Distinctive display grotesque | Headlines with personality |
| Instrument Sans | Contemporary, slightly quirky | Modern editorial, body or display — **Sans** only; Instrument **Serif** is demoted below |
| Newsreader | Readable text serif with real character | Long-form reading, editorial body |
| Source Serif 4 | Sturdy, neutral-warm text serif | Long-form reading, documentation |
| Satoshi | Geometric-humanist sans (Fontshare) | Product, marketing, body |
| General Sans | Clean neutral-with-edge sans (Fontshare) | Product UI, body — the Inter alternative |
| Playfair Display | High-contrast didone serif | Luxury, editorial headlines |
| Funnel Display / Funnel Sans | New geometric family | Clean, friendly |
| Sora, Outfit, Manrope | Geometric sans | Product, SaaS |
| JetBrains Mono, IBM Plex Mono | Code | Mono needs |
| Literata | Readable book serif | Long-form reading |

**Fontshare** (Indian Type Foundry) — free for commercial use, not on Google Fonts, and
therefore less over-exposed. **Satoshi** and **General Sans** are the standouts; the pairing
shows up across modern product sites.

**Widely used — choose deliberately, never by default.** These are competent but so common
that reaching for one is the single clearest tell of an unconsidered, machine-generated theme.
Do not use any of them as a theme's **body** face unless the brief specifically asks for it:

| Family | Why demoted |
|---|---|
| Inter | The default UI grotesque of the last five years. Excellent, and everywhere. Prefer General Sans / Geist for the same neutral role. |
| Roboto | Android's system sans; reads as "no choice was made." |
| Space Grotesk | Was distinctive; now the reflexive pick for anything "technical." |
| **Fraunces** | The single most-flagged LLM-favorite display serif (Taste Skill names it explicitly, no soft carve-out). Appeared in 5 of 8 recent Theme Forge runs before this demotion — treat as **banned as a default**, not merely discouraged. Only acceptable with explicit brand justification from the brief. |
| **Instrument Serif** | The other of the two worst offenders, same treatment as Fraunces — Google Fonts' editorial-elegance default, banned as a default. |

They remain fine in a **fallback stack** — see below.

**Serif is a choice, not a default.** The deeper pattern behind the Fraunces/Instrument Serif
bans: "this brief feels creative / premium / editorial" is *not itself* a reason to reach for
serif at all — that exact inference (creative brief → serif) is the single most-tested AI tell
in production rounds, independent of which specific serif gets picked. If a slot's thesis
genuinely calls for serif, treat the choice with the same discipline as color: rotate through a
wide pool rather than reaching for the same 2–3 names every run, and check `used.md` so the
same serif doesn't repeat across consecutive runs (the ledger's display-font match rule already
enforces this mechanically). A wider rotation pool, roughly in order of how distinctive/
less-exposed each currently is: PP Editorial New, GT Sectra Display, Cardinal Grotesque,
Reckless Neue, Tiempos Headline, Recoleta, Cormorant Garamond, Playfair Display, EB Garamond,
IvyPresto, Migra, Editorial Old, Saol Display, Söhne Breit Kursiv, Domaine Display, Canela,
Schnyder, Tobias, NB Architekt, ITC Galliard. (Playfair Display and Source Serif 4 remain in
the "reach for these first" table above — they are lower-clustering-risk than Fraunces/
Instrument Serif but still count toward the rotation pool for repeat-avoidance purposes.)

**Emphasis and italics.**
- To emphasize a word inside a headline, use italic or bold **of the same font family** —
  injecting a different-family word (a serif word dropped into a sans headline, or vice versa)
  as the emphasis mechanism reads as amateur, not intentional.
- Italic display type clips descender letters (`y g j p q`) at `line-height: 1` /
  `leading-none`. Use `line-height: 1.1` minimum on any line containing italic display text,
  and reserve a small bottom-padding buffer — audit every italic word in a display headline
  before shipping.

**Preferred display + body pairings (non-default starting points).** When you need a
fresh pairing rather than a single-family stack, reach for one of these first — each pairs a
distinctive display voice with a working body face without landing on a demoted default:

- Geist + Geist Mono
- Satoshi + JetBrains Mono
- Cabinet Grotesk + Inter Tight
- Outfit (display) + any geometric sans body

Always specify a full fallback stack. If the network is down or the CDN is blocked, the page
should still look intentional. **"Avoid `system-ui`" is a rule about the font you _choose_, not
about fallbacks** — every stack must still end in a full system fallback, and Roboto is welcome
there as a common Android system face:

```css
--font-body: "General Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
--font-display: "Newsreader", Georgia, "Times New Roman", serif;
--font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
```

## Scale

Fluid type with `clamp()` — one declaration covers every viewport, no breakpoint juggling:

```css
--text-base: clamp(1rem, 0.96rem + 0.2vw, 1.125rem);
--text-4xl: clamp(2.25rem, 1.8rem + 2.25vw, 3.75rem);
```

Ratio guidance: 1.2 (minor third) for dense product UI, 1.25 (major third) for general use, 1.333 (perfect fourth) for marketing pages, 1.5+ for editorial with dramatic headline contrast. Larger ratios need more whitespace to work.

Baselines: body ≥16px, ≥18px for long-form reading. Line height 1.5–1.7 for body, 1.05–1.25 for display. Measure 45–75 characters. Tighten tracking as size increases — display type set at body tracking looks loose.

## Modern text properties

```css
h1, h2, h3 { text-wrap: balance; }   /* even line lengths in headings */
p          { text-wrap: pretty; }    /* avoids orphans in body copy */
```

`font-optical-sizing: auto` where the font has an `opsz` axis. `font-feature-settings` for tabular figures in data tables — misaligned numerals in a stats table is one of the most visible craft failures.

## Pairing

Reliable strategies, roughly in order of safety:

1. **One family, many weights.** General Sans 700 over General Sans 400. Never wrong, rarely memorable — the safe option, not the default one.
2. **Serif display + sans body.** The default editorial move, done with less-exposed faces: Newsreader + General Sans, Playfair Display + Source Serif 4, Cormorant Garamond + Satoshi.
3. **Sans display + serif body.** Inverted; feels contemporary and a little unexpected. Bricolage Grotesque over Newsreader.
4. **Grotesque + mono.** Geist + Geist Mono. Reads as technical and precise.
5. **Two contrasting sans.** Hard to do well — they need to be clearly different in structure, not just weight, or it looks like a mistake.

The failure mode is two families that are *similar but not the same*. Contrast should be obvious or absent.

## Sources
Google Fonts and Fontshare catalogues; MDN CSS text and font references. Accessed for seed compilation, August 2026.
