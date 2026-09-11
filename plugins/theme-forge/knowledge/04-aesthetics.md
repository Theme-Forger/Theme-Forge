# The direction catalogue

## Changed since last refresh
Seed baseline — no refresh yet.

Twelve directions with concrete parameters. A theme-designer is assigned one and should commit to it fully. Hedging toward the safe middle is what produces six identical themes.

Each entry gives: the thesis, color strategy, typography, geometry, elevation, motion, and the failure mode to avoid.

---

## 1. Quiet Professional
**Thesis:** Trust through restraint. Nothing shouts.
**Color:** Low chroma (0.02–0.08). One brand hue, used sparingly. Neutrals carry a faint brand tint. Near-white ground.
**Type:** Neo-grotesque or a text serif. Modest scale ratio (1.2).
**Geometry:** Small radii (4–8px). Generous whitespace. Strict grid.
**Elevation:** Borders over shadows. Shadows, where used, are one soft layer.
**Motion:** Fast and unobtrusive. 120–180ms, standard easing. Nothing bounces.
**Fails when:** it becomes invisible. There still needs to be one moment of confidence — usually the primary button or a single accent.
**Native translation:** Translates cleanly. Border-based elevation works identically on both platforms. Safest choice when native is primary.

## 2. Confident Saturate
**Thesis:** This product has a personality and isn't apologizing for it.
**Color:** High chroma (0.15–0.25) primary. A genuinely contrasting accent, not an analogous one. Colored surfaces, not just colored buttons.
**Type:** A display face with character. Heavy weights used large.
**Geometry:** Medium-large radii (12–20px). Tighter whitespace — density reads as energy.
**Elevation:** Colored shadows, tinted toward the brand hue.
**Motion:** 200–280ms with a slight overshoot. Things arrive with intent.
**Fails when:** the saturation goes everywhere and nothing has hierarchy. Pick two or three places where the color lands hard.
**Native translation:** Colored shadows don't exist on Android — switch `native_strategy` to `border` there, or accept neutral elevation. Saturated fills translate fine.

## 3. Editorial Type-Led
**Thesis:** The words are the design.
**Color:** Nearly monochrome. Paper ground (a warm off-white), ink text, one accent used at maybe 2% of the surface area.
**Type:** The whole point. High-contrast serif display, dramatic scale ratio (1.4–1.5), real attention to measure, tracking, and rhythm.
**Geometry:** Radii near zero. Asymmetric layouts. Rules and hairlines as structure.
**Elevation:** Essentially flat. Hairline borders only.
**Motion:** Minimal. Fades and small position shifts, 200ms.
**Fails when:** it's just a serif font on a normal SaaS layout. The layout has to be editorial too — asymmetry, varied column widths, real hierarchy.
**Anti-default:** the direction is correct; its *stock reading* is one of the most recognizable AI-generated palettes — warm cream ground (~`#F4F1EA`) + high-contrast serif + a terracotta accent (~`#D97757`). Don't ship that reading. Push somewhere specific: cool the paper toward grey or push it warmer toward bone, make the ink a near-black that isn't `#000`, and pick an accent that is not terracotta. Pair the serif with a less-exposed body (Newsreader, Source Serif 4) rather than the reflexive Playfair-over-Inter.
**Native translation:** Translates well, but fluid type doesn't exist — pick fixed sizes per breakpoint, and support Dynamic Type by scaling from the token rather than hardcoding. Serif rendering differs subtly across platforms; check the Android fallback.

## 4. Technical Dark
**Thesis:** A tool for people who use it eight hours a day.
**Color:** Dark-first. Ground around `oklch(0.18–0.22)`. Low-chroma neutrals. One or two restrained accents, often a cool cyan, green, or amber. Semantic colors do real work.
**Type:** Compact sans plus a mono that's actually used, not decorative. Small sizes (13–14px base is acceptable here).
**Geometry:** Small radii (4–6px). High density. Tight spacing scale.
**Elevation:** Borders and surface-lightness steps. No drop shadows.
**Motion:** 80–150ms. Near-instant. Any perceptible delay reads as lag in a tool.
**Fails when:** density becomes illegibility. Line height and border contrast have to hold up.
**Native translation:** Translates cleanly and is well-suited to native. Dense layouts need explicit `hitSlop` to keep targets at 44/48.

## 5. Warm Human
**Thesis:** Made by people, for people.
**Color:** Warm neutrals — beige, sand, clay. Earthy or muted-bright accents. Hue drift toward warm across the neutral ramp.
**Type:** A humanist sans, or a soft serif like Fraunces with the `SOFT` axis engaged. Comfortable sizes and generous leading.
**Geometry:** Large radii (16–24px). Soft, rounded, occasionally organic shapes.
**Elevation:** Soft diffuse shadows, low opacity, generous blur.
**Motion:** 250–350ms with gentle easing. Nothing snaps.
**Fails when:** it turns into a wellness-app cliché. One structural element with hard edges keeps it honest.
**Native translation:** Translates cleanly. Large radii and soft shadows work on iOS; Android's blurred `elevation` actually suits this direction.

## 6. Neo-Brutalist
**Thesis:** Refuses to be polite.
**Color:** Flat, unmixed, high-saturation. Pure black borders and text. Often an off-white or a bright flat ground.
**Type:** Heavy grotesque or a mono. Big, tight, unapologetic.
**Geometry:** Zero radius, or a jarring mix of zero and full. Thick borders, 2–4px.
**Elevation:** Hard offset shadows with no blur — `4px 4px 0 #000`.
**Motion:** Instant or near-instant. Snap transforms, no easing curve worth naming.
**Fails when:** it's applied to something that needs to feel trustworthy. Great for tools, portfolios, and dev products; wrong for a bank.
**Native translation:** Hard offset shadow is impossible via `elevation`. Use a border-based strategy on Android, or an offset sibling `View`. Decide explicitly.

## 7. Swiss Minimal
**Thesis:** Structure is the whole argument.
**Color:** Black, white, one red or one blue. That's it.
**Type:** Helvetica-lineage neo-grotesque. Strict scale. Left-aligned, ragged right.
**Geometry:** Rigid grid, visible or implied. Zero radii. Whitespace as the dominant element.
**Elevation:** None. Everything on one plane.
**Motion:** 150ms linear or standard. Purely functional.
**Fails when:** the grid isn't actually rigorous. This direction has nowhere to hide — spacing has to be perfect.
**Anti-default:** black + white + zero-radius + broadsheet hairlines is also a known AI-design cluster; done by reflex it reads as "generic minimal" rather than Swiss. The direction is right, the default execution is not. Earn it specifically: let the single accent be an unexpected hue rather than the reflexive red or blue, shift the ground a few points off pure white (or invert to near-black), and make the *grid itself* do the expressive work — deliberate asymmetric column spans, a visible baseline rhythm — so structure reads as a choice, not an absence.
**Native translation:** Translates cleanly — no elevation to translate. Grid rigor must be rebuilt in Flexbox.

## 8. Liquid Glass
**Thesis:** The interface floats above the content.
**Color:** Translucent neutrals over a colorful or photographic ground. The content supplies the color; the chrome supplies the material.
**Type:** Clean sans, medium weights, good at small sizes over busy backgrounds.
**Geometry:** Large continuous corners (20–28px). Floating, inset panels.
**Elevation:** `backdrop-filter: blur(20px) saturate(180%)` plus a semi-transparent fill, a thin light top border, and a subtle inner highlight.
**Motion:** Fluid morphs, 300–400ms, spring-like.
**Fails when:** glass is applied to everything. Apple's own guidance restricts it to the navigation layer — tab bars, toolbars, sheets, popovers, floating buttons — never to content or full-screen backgrounds, and never stacked glass on glass. Always ensure text over glass still passes contrast against the *worst case* background.
**Native translation:** Requires `expo-blur` and a development build. Must ship a designed non-blur fallback. Restrict to the nav layer. At most one glass direction per set when native is primary.

## 9. Expressive Material
**Thesis:** Emotion through shape and motion.
**Color:** Broad tonal palettes derived from a source color. Bold color pairings, generous use of container colors.
**Type:** Variable sans across a wide weight range. Big type for emphasis, not just size steps.
**Geometry:** A shape *system* — multiple shapes beyond the rounded rectangle, morphing between states.
**Elevation:** Tonal elevation (lightness steps) plus shadow.
**Motion:** Spring physics rather than fixed durations. Bouncy, physical, responsive to gesture.
**Fails when:** the springiness is applied uniformly. Motion should be expressive at moments of consequence and calm everywhere else.
**Native translation:** Translates well — Reanimated springs are a better fit than CSS. Shape morphing needs Skia or is dropped.

## 10. Retro-Futurist
**Thesis:** The future as imagined in 1985.
**Color:** Gradient-heavy — magenta to cyan, sunset ramps. Deep grounds. Neon accents with glow.
**Type:** Wide geometric sans or a techno display face. Mono for support. Wide tracking on small caps.
**Geometry:** Sharp or slightly rounded. Grid lines, horizons, scanlines as motifs.
**Elevation:** Glow instead of shadow — colored box-shadow with high blur, zero offset.
**Motion:** Sweeping, 300–500ms. Glow pulses. Scanline sweeps.
**Fails when:** it's all surface and no structure. The underlying layout still needs to be a good layout.
**Native translation:** Gradients need `expo-linear-gradient`; radial/conic need Skia. Glow is a shadow on iOS and unavailable on Android — consider a border or a gradient stroke instead.

## 11. Bento Modular
**Thesis:** Everything is a card, and the arrangement is the design.
**Color:** Neutral ground, cards each carrying a distinct accent or gradient. Color lives inside the modules.
**Type:** Clean sans. Clear per-card hierarchy — a label, a headline, a value.
**Geometry:** Consistent large radii (16–20px), consistent gaps, varied cell spans on a grid.
**Elevation:** Cards sit slightly above the ground. One shadow level, or a border.
**Motion:** Cards lift on hover, 200ms. Stagger on entrance.
**Fails when:** every card is the same size. The variety of spans is the entire point.
**Native translation:** Translates cleanly. Varied grid spans must be rebuilt with nested Flexbox or a masonry library.

## 12. Organic Soft
**Thesis:** Nothing here has a hard edge.
**Color:** Pastel or desaturated. Mesh gradients. Blobs as background elements.
**Type:** Rounded sans or a soft humanist. Comfortable, never tight.
**Geometry:** Very large radii, up to full pills. Blob shapes via SVG paths.
**Elevation:** Claymorphic — a soft outer shadow plus a light inner shadow, giving a puffy, extruded look.
**Motion:** Slow and floating, 350–500ms, ease-in-out. Ambient background drift.
**Fails when:** the softness kills affordance. Buttons still need to look pressable and inputs still need to look editable.
**Native translation:** Blob SVGs need `react-native-svg`. Claymorphic inner shadows don't exist on either platform — approximate with a lighter inner `View` or a gradient.

---

## Choosing six

Pick directions that differ on **at least two** of: color strategy, type character, geometry. Two themes that are both low-chroma sans-serif small-radius are the same theme with different hues, and the user will say so.

Match to the brief. A children's education product and a compliance dashboard should not receive the same six. But keep the spread — even a conservative brief benefits from one genuinely unexpected option, because it clarifies what the user actually wants.

## Sources
Apple Human Interface Guidelines; Material Design 3; observed practice across current product design. Accessed for seed compilation, August 2026.
