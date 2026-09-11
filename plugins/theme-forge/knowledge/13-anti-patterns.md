# Anti-Pattern Catalog — AI Slop Detection

<!-- Portions adapted from Taste Skill v2 (https://github.com/Leonxlnx/taste-skill),
     MIT License, Copyright 2026 Leonxlnx. See NOTICE for full attribution. -->

<!--
  Attribution: This catalog adapts and extends the impeccable rule set.
  impeccable — https://github.com/pbakaus/impeccable
  Copyright © impeccable contributors — Apache License 2.0
  https://www.apache.org/licenses/LICENSE-2.0
  Adapted into Theme Forge under the same license terms.
-->

*Source: impeccable (Apache-2.0, github.com/pbakaus/impeccable). This catalog
adapts and extends their 59-rule deterministic detection set for Theme Forge's generation
pipeline. Run `npx impeccable detect` against a preview.html for automated checking. This
file is the authoritative read for theme-designer and brand-asset-designer agents.*

---

## How to use this file

**Before generating any token, typeface, easing curve, illustration, or copy**, run
your choices against this catalog. The rules are deterministic — there is no
subjective grey zone. If a choice appears in the AVOID column, replace it, even
when the direction otherwise feels correct.

---

## Section 1 — Design System (rules 1–7)

| # | Rule | Avoid | Notes |
|---|------|-------|-------|
| 1 | **Incoherent token system** | Hex values scattered in components, not derived from a token | Semantic roles (`--tf-primary`, `--tf-surface`) must exist at the layer above raw palette |
| 2 | **Hard-coded spacing** | Magic number px in components (`padding: 13px`) | Every space value comes from the spatial scale's named steps |
| 3 | **Inconsistent elevation vocabulary** | Borders on some cards, shadows on others, neither tied to a rule | Elevation has one strategy per platform; components don't mix strategies |
| 4 | **Dark mode as naive invert** | `filter: invert(1)` or lightness-only inversion | Dark surfaces are lower chroma, elevation is lighter not darker; redesign, don't invert |
| 5 | **Missing semantic token layer** | Using `blue-500` in components directly | Semantic aliases (`primary`, `surface-raised`, `on-primary`) exist between palette ramps and components |
| 6 | **Responsive with no layout logic** | Breakpoints that only reflow columns | Type scale, spatial scale, and composition change at breakpoints; not just column count |
| 7 | **Placeholder content in production** | Lorem ipsum, `placeholder@example.com`, `user-avatar.png` | All copy in preview surfaces must be thematically appropriate to the product, not generic filler |

---

## Section 2 — Visual Details (rules 8–14)

| # | Rule | Avoid | Notes |
|---|------|-------|-------|
| 8 | **Drop shadow on every element** | Same shadow on cards, buttons, nav, modals, popovers simultaneously | Elevation = hierarchy; max 2–3 distinct shadow levels; when everything is elevated, nothing is |
| 9 | **Gradient addiction** | Gradients on backgrounds, buttons, text, icons, cards all at once | At most one gradient in the primary visual hierarchy; every other gradient must be earned |
| 10 | **Grain/noise as default atmosphere** | `filter: url(#grain)` on every surface to add "depth" | Grain is a specific texture choice, not a neutral backdrop; absent a deliberate reason, omit |
| 11 | **Generic glassmorphism** | `backdrop-filter: blur(20px)` on cards + nav without a designed background layer | Glass only works when the layer beneath is a deliberate, visible composition — a solid card behind glass is just a blurry rectangle |
| 12 | **Dividers instead of whitespace** | `<hr>` or 1px border-bottom between every section | Whitespace is structure; a divider should mark a genuine semantic boundary, not fill vertical rhythm |
| 13 | **Device mockups with placeholder UI** | iPhone outline showing lorem-ipsum screens | Device frames must contain real preview content; empty frames with no content add no value |
| 14 | **Stars as decorative social proof** | Five yellow stars with no actual rating product | Only ship rating stars when a rating system exists; decorative "5.0 ★" is misleading |

---

## Section 3 — Typography (rules 15–22)

| # | Rule | Avoid (demoted font list) | Notes |
|---|------|--------------------------|-------|
| 15 | **Inter as body face** | `font-family: 'Inter', sans-serif` | Most-deployed body face; signals no typographic intent; use Geist Mono for mono if you want Inter's aesthetic |
| 16 | **Roboto / Arial** | `font-family: 'Roboto', 'Arial', sans-serif` | Pre-2020 defaults; no longer distinguishing |
| 17 | **Space Grotesk** | `font-family: 'Space Grotesk', sans-serif` | Was distinct in 2021; now a cliché "modern tech" choice |
| 18 | **Geist** | `font-family: 'Geist', 'Geist Sans', sans-serif` | Rapidly becoming the new developer-neutral default; use only when the direction specifically calls for Vercel-adjacent aesthetics |
| 19 | **Instrument Serif / Fraunces as editorial display** | `font-family: 'Instrument Serif', serif` or `font-family: 'Fraunces', serif` | The two most-flagged LLM-favorite display serifs (Taste Skill, github.com/Leonxlnx/taste-skill, MIT, refreshed 2026-09-03) — over-exposed in AI-generated "editorial craft" themes since 2024; treat both as banned as a default |
| 20 | **system-ui as intentional display** | `font-family: system-ui, sans-serif` for display roles | The absence of a choice presented as a choice; acceptable for utility UI but not for a named design direction |
| 21 | **All-caps on every metadata element** | `text-transform: uppercase` on timestamps, tags, table headers, subtitles indiscriminately | All-caps draws attention; using it everywhere means nothing is emphasized |
| 22 | **Three or more typefaces** | Display + body + mono + accent face | A fourth face adds visual noise, not richness; two faces is almost always enough |

---

## Section 4 — Color/Contrast (rules 23–30)

| # | Rule | Avoid | Notes |
|---|------|-------|-------|
| 23 | **Warm cream ground as default** | Background near `#F4F1EA` (±2 OKLCH lightness, any warm hue) | Too common to carry identity; if warm neutrals are unavoidable, shift the hue strongly (toward sage, slate, or stone — not warm beige) |
| 24 | **Purple gradient as modern signal** | `#6B21A8 → #7C3AED` or similar purple-to-violet on hero sections | Every AI-generated "premium SaaS" hero uses this; reserve purple for products with a genuine purple brand |
| 25 | **Teal/coral combination** | `#0D9488` + `#F97316` or nearby hues together | Reads as "friendly SaaS circa 2021" regardless of context |
| 26 | **Single-weight primary** | Primary at full saturation with no mid-tones | A workable palette needs a primary ramp: hover, active, disabled, background-tint — all require steps below full saturation |
| 27 | **One grey for everything** | A single `--gray-500` used for borders, muted text, icons, and placeholders | Muted text, borders, and disabled elements have different optical weights; they need different greys |
| 28 | **Gradient text abuse** | `background-clip: text` on body copy, multiple headings, labels | Gradient text is a signature element; using it in multiple places in one view means none of them are signatures |
| 29 | **Minimum-passing contrast** | Contrast ratio 4.51:1 | Design to ≥5.0:1 for body text — 4.5:1 fails on anti-aliased screens and becomes inaccessible after a design tweak |
| 30 | **Red/green as sole semantic pair** | Error = `#EF4444`, success = `#22C55E` with no shape/icon differentiation | 8% of users have red-green colour blindness; semantic states must differ on more than hue |

**Cap rule (from impeccable detect):** One cream-ground theme per set maximum. If two or more slots have warm-beige backgrounds, the set reads as a palette, not six directions.

---

## Section 5 — Layout/Space (rules 31–38)

| # | Rule | Avoid | Notes |
|---|------|-------|-------|
| 31 | **Card grid as universal layout** | Equal 3-column card grid for features, team, posts, pricing, benefits | Card grids are a data-display pattern, not a marketing-section pattern; use when the items are genuinely comparable |
| 32 | **Hero + three features** | Hero headline → "Three things we do well" row | The template answer to any brief; only ship when the product genuinely has three discrete selling points |
| 33 | **Centred text in every hero** | `text-align: center` on hero headline + subtitle | Centre alignment reads as ceremonial; left-aligned content projects more confidence and is easier to read |
| 34 | **Whitespace as premium** | Aggressive margin applied uniformly to all sections | Generous space should emphasise hierarchy, not decorate; equal space everywhere is the same as no space |
| 35 | **Section heading + subtitle on every section** | Every `<section>` starts `<h2> + <p class="subtitle">` | Some sections should speak for themselves; overuse of the heading+deck pattern reads as template structure |
| 36 | **Asymmetry for decoration** | 8-column content + 4-column "accent stripe" with no content | Asymmetric layouts earn their complexity by placing something meaningful in the narrow column |
| 37 | **Sticky nav on short pages** | `position: sticky` header on a single-viewport page | Sticky nav adds overhead when there is nowhere to scroll to |
| 38 | **Full-bleed image + text overlay** | Hero photograph with a semi-transparent text overlay | The overlay always fights the image; either use the image as the hero (no text) or use the text as the hero (no image) |

---

## Section 6 — Motion (rules 39–44)

| # | Rule | Avoid | Notes |
|---|------|-------|-------|
| 39 | **Bounce/elastic CSS easing** | `cubic-bezier(x, y2 > 1, …)` on interface elements | CSS easing with y2 > 1 overshoots then springs back — physics without physics. Looks dated since 2023. Use ease-out-expo (`cubic-bezier(0.19, 1, 0.22, 1)`) or ease-out-quint (`cubic-bezier(0.22, 1, 0.36, 1)`) for snappy energy without overshoot. Reserve real spring physics for Reanimated on native where it is physically grounded (dampingRatio < 1 on native is fine; overshoot in CSS is not). |
| 40 | **Everything animates on scroll** | Scroll-triggered animation on every section, every card, every image | Scroll animation is expensive and busy; reserve it for moments that need extra emphasis (first hero section, a key metric, a milestone in a timeline) |
| 41 | **Stagger on every list** | `animation-delay: calc(var(--i) * 100ms)` on features, blog cards, menu items, team members | Stagger is a page-load device, not an ambient list behaviour; applying it to every list makes the page feel perpetually loading |
| 42 | **300ms as the default** | `transition: all 300ms ease` copied from tutorials | Most interface states (hover, focus, active) should transition in 120–200ms; 300ms feels sluggish on a cursor-driven device |
| 43 | **Skeleton on fast data** | Skeleton loading state for operations resolving in under 200ms | A flash of skeleton followed by real content is worse than no skeleton; add a 200ms delay before skeleton appears |
| 44 | **Hover scale on static elements** | `transform: scale(1.05)` on article cards, profile images, decorative icons | Hover effects signal interactivity; applying them to non-interactive elements trains users to click things that don't click |

---

## Section 7 — Copy (rules 45–50)

| # | Rule | Avoid | Notes |
|---|------|-------|-------|
| 45 | **Filler adjectives** | "Powerful", "seamless", "effortless", "intuitive", "revolutionary" | Describe what the product *does*, not how it *feels*; adjectives that could appear on any product's homepage have zero value |
| 46 | **Social proof theater** | "Trusted by 10,000+ teams" without a name or a quote | Round-number social proof with no attribution reads as fabricated; use a real quote or remove the claim |
| 47 | **Single CTA on every page** | "Get started for free" as the primary action regardless of funnel stage | The CTA should match where the user is; a user reading about pricing should see "Start trial", not "Get started" |
| 48 | **Generic empty state** | "No items yet. Create your first one!" on every empty screen | Empty states should guide toward a specific action relevant to the missing content type |
| 49 | **Opaque error copy** | "An error occurred" | Error copy must say what happened (or that it is unknown), whether the user should retry or contact support, and if there is something they can do now |
| 50 | **Template surface copy** | "Cash flow, simplified" hero copy that is fintech placeholder regardless of the theme brief | Preview surface copy must reflect the actual product brief; generic fintech/SaaS copy undermines the theme's personality |

---

## Section 8 — Imagery (rules 51–57)

| # | Rule | Avoid | Notes |
|---|------|-------|-------|
| 51 | **Shape-assembled illustration** | Circle + rectangle + line = abstract "scene" | Five primitives assembled into a vague shape are not an illustration; they are placeholder art. If the composition cannot be explained in one sentence, it should not ship. |
| 52 | **Amateurish hand-drawn SVG** | Stroke paths that look accidentally wobbly rather than deliberately gestural | Sketchy illustration is a style; it requires consistent line weight, intentional imperfection, and a coherent vocabulary. Random wobbly paths are not a style. |
| 53 | **Person-smiling-at-laptop** | Generic stock photo of a professional at a computer | This image appears in every SaaS product's hero regardless of whether the product is used at a laptop |
| 54 | **AI-blob render** | Iridescent purple/teal blob with no relation to the product's domain | The default output of every text-to-image service with the prompt "abstract digital technology background" |
| 55 | **Floating gradient blob** | `radial-gradient(ellipse at 20% 50%, rgba(124,58,237,0.3), transparent)` behind plain white | Gradient blobs add neither brand signal nor spatial information; they are filler |
| 56 | **Illustration without a system** | Different illustration styles across sections (geometric hero + isometric feature + hand-drawn empty state) | Illustrations should share stroke weight, palette, radius scale, and compositional vocabulary |
| 57 | **Wrong device model** | Old iPhone bezel, missing Dynamic Island, wrong aspect ratio | Device mockups must match current hardware; an off-by-one notch undermines credibility |

---

## Section 9 — General Quality (rules 58–64)

| # | Rule | Avoid | Notes |
|---|------|-------|-------|
| 58 | **Missing focus-visible** | `outline: none` or `outline: 0` with no `:focus-visible` replacement | Keyboard navigation is inaccessible without visible focus; `:focus-visible` exists to distinguish keyboard focus from mouse click |
| 59 | **No reduced-motion support** | Motion-heavy pages with no `@media (prefers-reduced-motion: reduce)` block | Required by WCAG 2.1 SC 2.3.3; entrance animations, scroll reveals, ambient loops must all be disabled or collapsed |
| 60 | **Sub-44px click targets** | Icon buttons, inline links, custom controls under 44×44px | WCAG 2.5.5 minimum; on mobile, anything under 44px requires precision tapping that causes errors |
| 61 | **Dark mode as filter invert** | `filter: invert(1)` or token set that merely swaps background/text lightness | True dark mode redesigns chroma (lower saturation), elevation (lighter higher = more light), and semantic colours (error/success shift toward better dark-context contrast) |
| 62 | **Form without inline validation** | All constraints communicated only on submit | Users should know when a field is valid while they're still in it — not after they click submit and scroll back up |
| 63 | **Missing empty state** | Page renders a blank area with no designed empty-state component when data is absent | Every list, table, or data surface needs a designed empty state; a blank rectangle is not a UX pattern |
| 64 | **De-emphasised attribution unstyled** | License notices, "powered by" text, or fine print inheriting body text weight and colour | Attribution copy should be visually de-emphasised (lighter, smaller, lower contrast) — not suppressed, but clearly secondary |

---

## Quick-reference card

**Never ship (hard stops):**
- Overshoot easing in CSS (`y2 > 1`)
- `:focus` removed without `:focus-visible` replacement
- Warm cream ground on more than one theme in a set
- Shape-assembled illustration (rule 51)

**Strong avoids (design critic flags these):**
- Geist, Inter, Space Grotesk, Instrument Serif, Fraunces as body face
- Card radii above 16px (pill/full excepted for tags and buttons only)
- Purple gradient hero without a purple brand
- Stagger on every list
- All-caps on every metadata element

*Seeded 2026-08. Refresh trigger: when impeccable.style/slop updates its rule count above 64, or when a new font joins the over-exposed list.*
