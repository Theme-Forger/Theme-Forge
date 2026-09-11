# Motion

<!--
  Attribution: The frequency gate, purpose categories, easing tokens, per-recipe values,
  severity rubric, and reduced-motion approach in this file are ported from:
  emilkowalski/skills — https://github.com/emilkowalski/skills
  Copyright © Emil Kowalski — MIT License — https://opensource.org/licenses/MIT
  Files: skills/review-animations/STANDARDS.md, skills/animate/SKILL.md
  Ported into Theme Forge under the MIT license. All values are verbatim or directly derived.
  NOTE: the repo's `find-animation-opportunities` and `improve-animations` skills are
  deliberately NOT installed, ported, or depended on by Theme Forge at runtime or in this
  file's content — this file is self-contained.
-->

## Changed since last refresh
Rewritten 2026-08-25 — added Emil Kowalski frequency tiers, per-surface motion budget,
exact easing recipes, purpose categories, severity rubric, and feedback-first purpose mix.
Previous version had blanket reduced-motion disable and no frequency gates.

---

## Motion intensity and the frequency gate

**Taste Skill** (Leonxlnx, MIT 2026) defaults to `MOTION_INTENSITY = 6` and biases toward
visible movement as the default expression of quality.

**Emil Kowalski's frequency gate** classifies UI surfaces by interaction frequency:
hundreds-per-day earns near-imperceptible motion; tens-per-day earns subtle; rare/first-time
earns delight.

**Resolution (Theme Forge policy):** Emil wins on the app and mobile surfaces, always.
`motion_budget.webapp` must be `near-imperceptible` regardless of the brief's motion adjectives.
`motion_budget.mobile` is per-screen: `delight` for onboarding/success/empty, `feedback-only`
for feed and detail.

The Taste Skill `motion_intensity` dial applies to the **website (marketing) surface only**,
where interaction frequency is low and theatrical motion earns its cost. A dial of 8 on a
website surface does not grant full motion on the webapp surface.

---

## The core problem: entrances fire once, feedback is felt every tap

A page with 164 entrance animations and 13 feedback instances still feels dead.
Entrances fire once on load. Nothing responds to touch. The frequency tier is what
determines whether motion adds life or adds lag.

Sources: Emil Kowalski's animation philosophy at emilkowal.ski / animations.dev (MIT, 13.3k stars).

---

## The Gate — four questions, in order

Every animation must survive all four. Record the answer — it goes in README.md rejected-animations.

### 1. Frequency

| Frequency | Verdict |
|---|---|
| 100+ times/day (keyboard shortcuts, command palette, core nav) | **Reject. No animation. Ever.** |
| Tens of times/day (hover states, list nav, frequent toggles) | Reject, or near-imperceptible only |
| Occasional (modals, drawers, toasts, settings) | Eligible — standard animation |
| Rare / first-time (onboarding, empty states, success, celebration) | **The delight budget lives here** |

Keyboard-initiated actions are a disqualifier, not a judgment call. Raycast has no open/close
animation — that is the optimal experience for 100+/day.

### 2. Purpose

Name it in one of these words. If you can't, reject.

- **Feedback** — interface confirms it heard the user (press scale, hold-to-confirm)
- **Spatial consistency** — shows where something came from or went (toast exits same edge it entered)
- **State indication** — makes a state change legible (morphing button, expanding accordion)
- **Preventing a jarring change** — bridges content that teleports
- **Explanation** — demonstrates how a feature works (marketing/onboarding only)
- **Delight** — allowed *only* at the rare/first-time tier

"It looks cool" on a frequently-seen element is not a purpose.

### 3. Speed

Must stay inside the duration budget. If it only "works" slowly, it fails the gate.

| Element | Duration |
|---|---|
| Button press feedback | 100–160ms |
| Tooltips, small popovers | 125–200ms |
| Dropdowns, selects | 150–250ms |
| Modals, drawers | 200–500ms |
| Marketing / explanatory | Can be longer |

**UI animations stay under 300ms.** A 180ms dropdown feels more responsive than 400ms.

### 4. Function

Data the user is reading or acting on should not move for style. A decorative
mouse-tracking effect belongs on a marketing page; not on a live analytics graph.

---

## Per-surface motion budget

One motion character across all three surfaces is wrong. Split it:

| Surface | Budget | Rule |
|---|---|---|
| **website** | Full delight budget | Generous — rare visit, first impression |
| **web app** | Near-imperceptible only | Daily tool, tens-of-times frequency. No decorative entrances on data being read |
| **mobile** | Per-screen | Onboarding / success / empty → delight. Feed and detail → feedback only |

Declare `motion_budget` in theme.json:
```json
"motion_budget": {
  "website": "full",
  "webapp": "near-imperceptible",
  "mobile": {
    "onboarding": "delight",
    "feed": "feedback-only",
    "detail": "feedback-only"
  }
}
```

---

## Purpose mix target: 40 feedback instances per theme

The failing pattern: 164 entrance/decorative, 13 feedback. Every interactive element
needs press feedback. Target minimum **40 feedback instances** per theme.

Every pressable element gets:
```css
.button, .card, .nav-item, .tab-item, .list-item, .table-row {
  transition: transform 160ms ease-out;
}
.button:active, .card:active, .nav-item:active,
.tab-item:active, .list-item:active, .table-row:active {
  transform: scale(0.97);
}
```

Subtle range: 0.95–0.98. Never 0.9 (too much) or 1.0 (nothing). Scale is correct for
touch too — `:active` fires on real press; hover gating is separate.

---

## Emil Kowalski Reference Curves

These three named curves are the canonical shapes themes derive from. Port verbatim. Source: emilkowalski/skills STANDARDS.md (MIT).

```css
--ease-out:     cubic-bezier(0.23, 1, 0.32, 1);      /* strong ease-out for UI — entering/exiting */
--ease-in-out:  cubic-bezier(0.77, 0, 0.175, 1);     /* on-screen movement */
--ease-drawer:  cubic-bezier(0.32, 0.72, 0, 1);      /* iOS-like drawer (Ionic) */
```

**Rule:** Built-in CSS easings (`ease`, `ease-out`, `ease-in-out`) are too weak for UI. Themes must use strong custom curves. Find additional curves at easing.dev or easings.co — don't hand-roll from scratch.

**Easing decision order:**
- Entering or exiting → `ease-out` (starts fast, responsive)
- Moving / morphing on screen → `ease-in-out`
- Hover / color change → `ease`
- Constant motion (marquee, progress) → `linear`
- Default → `ease-out`

**Never `ease-in` on UI.** It starts slow, delaying the exact moment the user is watching. `ease-out` at 200ms *feels* faster than `ease-in` at 200ms.

Themes may use their own curves but must match these in shape — strong, ease-out-dominant.

---

## Easing — exact values, not approximations

Decision order:

| Situation | Easing |
|---|---|
| Entering or exiting | `ease-out` |
| Moving / morphing on screen | `ease-in-out` |
| Hover / color change | `ease` |
| Constant motion (marquee, progress) | `linear` |
| Default | `ease-out` |

**Never `ease-in` on UI.** It starts slow, delaying the exact moment the user is watching.
`ease-out` at 200ms *feels* faster than `ease-in` at 200ms.

Built-in CSS easings are too weak. Use these tokens:

```css
--ease-out:    cubic-bezier(0.23, 1, 0.32, 1);     /* strong ease-out for UI */
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);    /* strong ease-in-out for on-screen movement */
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);     /* iOS-like drawer curve (Ionic) */
```

Theme-specific motion characters map to these curves:

| Character | Durations | Curve | Feels like |
|---|---|---|---|
| **Crisp** | 80–160ms | `--ease-out` | Precise, tool-like |
| **Springy** | Use springs | Springs (bounce 0.1–0.3) | Playful, physical |
| **Calm** | 250–400ms | `--ease-in-out` | Considered, premium |
| **Mechanical** | 120–200ms | `linear` or `steps(N)` | Deliberate, technical |

---

## Exact recipes

### Button / any pressable element
```css
.button {
  transition: transform 160ms var(--ease-out);
}
.button:active {
  transform: scale(0.97);
}
/* No hover gating needed: :active is a real press on touch */
```

### Entrance — never scale(0)
Nothing in the real world appears from nothing. Start from scale(0.95–0.97) + opacity 0:
```css
/* Bad */
.entering { transform: scale(0); }

/* Good */
.entering {
  transform: scale(0.95);
  opacity: 0;
}
/* Transition to settled state */
.entered {
  transform: scale(1);
  opacity: 1;
  transition: transform 200ms var(--ease-out), opacity 200ms var(--ease-out);
}
```

Use `@starting-style` for entry without JS (modern browsers):
```css
.toast {
  opacity: 1;
  transform: translateY(0);
  transition: opacity 400ms ease, transform 400ms ease;

  @starting-style {
    opacity: 0;
    transform: translateY(100%);
  }
}
```

### Popovers, dropdowns, menus — scale from trigger origin
```css
.popover {
  transform-origin: var(--transform-origin); /* Base UI supplies this */
  transition: opacity 200ms var(--ease-out), transform 200ms var(--ease-out);
}
.popover[data-starting-style],
.popover[data-ending-style] {
  opacity: 0;
  transform: scale(0.95);
}
```

**Modals are exempt** — they're not anchored to a trigger; `transform-origin: center` is correct.

### Toasts / sheets — exit same edge they entered
```css
/* translateY percentages — element's own height, not hardcoded pixels */
.toast-top    { transform: translateY(-100%); }    /* enters from top — hides above viewport */
.drawer       { transform: translateY(100%); }     /* enters from bottom — hides below viewport */
.drawer[data-open] { transform: translateY(0); transition: transform 500ms var(--ease-drawer); }
```

Direction must match where the element enters from. A toast that slides in from the top must
exit upward (`translateY(-100%)`); a bottom sheet must exit downward (`translateY(100%)`).

### Stagger — decorative, never blocks interaction
```css
.item { animation: fadeIn 300ms var(--ease-out) forwards; opacity: 0; transform: translateY(8px); }
.item:nth-child(2) { animation-delay: 50ms; }
.item:nth-child(3) { animation-delay: 100ms; }
/* 30–80ms between items */

@keyframes fadeIn { to { opacity: 1; transform: translateY(0); } }
```

### Hold-to-confirm
A destructive or high-stakes action needs a press-and-hold so accidental taps don't fire it.
Use a `clip-path` overlay that reveals a fill over 2 seconds; snap back on release:
```css
.hold-btn { position: relative; overflow: hidden; }
.hold-btn::after {
  content: '';
  position: absolute; inset: 0;
  background: var(--color-confirm);
  clip-path: inset(0 100% 0 0);        /* starts fully hidden */
  transition: clip-path 2s linear;
}
.hold-btn:active::after {
  clip-path: inset(0 0% 0 0);          /* fills left-to-right while held */
  transition: clip-path 2s linear;
}
/* Snap back quickly on release */
.hold-btn:not(:active)::after {
  transition: clip-path 200ms var(--ease-out);
}
```
Fire the action only when the 2 s transition completes (JS `transitionend` event).
This is the correct pattern for "hold to delete" and "hold to confirm payment."

### Accordion / collapse
```css
.accordion-body {
  overflow: hidden;
  transition: height 250ms var(--ease-out), opacity 200ms var(--ease-out);
}
.accordion-body[hidden] { height: 0; opacity: 0; }
```
Do not animate `max-height` — it produces an asymmetric snap. Measure and set explicit
`height` in JS before transitioning. Opacity provides a secondary softening so the
content doesn't appear to slam in.

### Gesture dismissal — velocity threshold and rubber-banding
```js
// Dismiss on velocity OR distance — whichever fires first
const velocity = Math.abs(distance) / elapsedMs;   // > ~0.11 = fast flick
const threshold = velocity > 0.11 || distance > panelHeight * 0.5;
if (threshold) dismiss(); else snapBack();
```

**Rubber-banding at gesture boundaries**: when a drag reaches its limit (top of a list,
edge of a sheet), continue moving at 30–40% of the finger's actual distance — never a
hard stop. Framer Motion: `drag="y" dragElastic={0.3}`. CSS: `overscroll-behavior: contain`
on the container.

### Springs
For drag, gesture-driven, or "alive" elements (not CSS):
```js
{ type: "spring", duration: 0.5, bounce: 0.2 }      // Apple-style
{ type: "spring", mass: 1, stiffness: 100, damping: 10 }  // traditional physics
```
Keep bounce at 0.1–0.3. Reserve visible bounce for drag-to-dismiss and playful moments.

### Transitions, not keyframes, for interruptible UI
CSS transitions retarget from the current value; keyframes restart from zero.
Use transitions for toasts, toggles, anything triggered rapidly.

---

## The four HIGH-severity violations (fix before shipping)

These are detectable by `tf_slop.py`'s stdlib fallback and always block assembly:

Severity rubric derived from `skills/review-animations/STANDARDS.md` (source of truth):

**HIGH** (blocks assembly) = wrong easing on UI (`ease-in`), animation on keyboard/high-frequency actions, dropped frames, `scale(0)`, `transition: all`

**MEDIUM** (advisory) = wrong `transform-origin` on popover, non-interruptible dynamic UI (keyframes on toggles/toasts), missing `prefers-reduced-motion`, ungated `:hover` motion, app durations > 300ms

**LOW** (polish) = missing stagger, blur-masked crossfades not applied where content teleports, token inconsistency

| Violation | Severity | Fix |
|---|---|---|
| `scale(0)` in CSS entrance | **HIGH** | Use `scale(0.95)` + `opacity: 0` |
| `ease-in` on UI transitions | **HIGH** | Use `ease-out` or `cubic-bezier(0.23, 1, 0.32, 1)` |
| `transition: all` | **HIGH** | Name the property explicitly; `all` animates layout properties off-GPU |
| `:hover` without `@media (hover: hover) and (pointer: fine)` | **MEDIUM** | Gate all hover motion |
| Missing `prefers-reduced-motion` | **MEDIUM** | Add gentler variant; keep opacity, drop movement |
| App-surface durations > 300ms | **MEDIUM** | Reduce to 150–250ms |

---

## Reduced motion — gentler, not zero

A blanket disable removes information. An opacity crossfade still communicates state
change to someone with vestibular sensitivity; killing it removes that information.

```css
/* Wrong — kills all feedback */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}

/* Right — keep opacity/color, drop position/transform */
@media (prefers-reduced-motion: reduce) {
  .element {
    animation: fade 0.2s ease; /* no transform-based motion */
  }
}
```

In JS:
```jsx
const reduce = useReducedMotion();
const closedX = reduce ? 0 : '-100%';
```

---

## Hover gating — always

Touch devices trigger `:hover` on tap, causing false positives. Gate every hover animation:
```css
@media (hover: hover) and (pointer: fine) {
  .element:hover { transform: scale(1.05); }
}
```

---

## Animate transform, opacity, and clip-path only

These skip layout and paint and run on the GPU:
- `transform` — translate, scale, rotate
- `opacity`
- `clip-path` — GPU-composited in all modern browsers; the correct property for
  reveal effects (hold-to-confirm fill, masked entrances, wipe transitions)

Never animate:
`width`, `height`, `margin`, `padding`, `top`, `left` — these trigger layout recalculation.
`transition: all` — **HIGH severity, always a finding.** Animates unintended properties
off-GPU and makes every future CSS addition an accidental animation.

## Tool selection hierarchy

Pick the first tool that fits. Only reach for the next when the earlier one can't do the job:

1. CSS `transition` — enter/exit, toggles, hover; interruptible by default
2. CSS `@starting-style` — entry without JS; retargets automatically
3. CSS `@keyframes` — predetermined sequences with no dynamic state
4. Web Animations API (`element.animate()`) — when JS must drive the timeline
5. Motion / Framer Motion — dynamic state, layout, presence, gesture-driven

## Asymmetric timing

Animate at different speeds depending on who initiated the action:

- **Deliberate user action** (press, hold, destructive confirm) → animate **slower** so the user feels their agency
- **System response** (toast dismiss, auto-close, background sync) → snap **instantly** so it doesn't block

---

## The required rejected-animations section

Every theme's README.md **must** include a section listing 2–5 places it deliberately
did NOT animate, with the gate question that killed each:

```markdown
## Rejected animations

- **Data table rows** — rejected: functional data being read; decoration hinders. (Function gate)
- **Search field** — rejected: keyboard-initiated, 100+/day. (Frequency gate)
- **Nav sidebar items** — rejected: tens/day, near-imperceptible only; no entrance stagger. (Frequency gate)
```

A theme that chose not to animate must be distinguishable from one that forgot.

---

## Web libraries

- **Motion** (formerly Framer Motion) — MIT, framework-agnostic. Import from `motion/react` in React. Declarative; the right choice for React state, layout, presence, and gesture animation.
- **GSAP** — v3, now entirely free including SplitText, MorphSVG, ScrollTrigger. Imperative; right for complex sequenced timelines and scroll storytelling. In React, use `useGSAP()` from `@gsap/react`.
- **CSS-first** — scroll-driven animations and View Transitions handle a surprising share of what used to need JS, run on the compositor, and cost nothing in bundle size.

### Framer Motion hardware-acceleration caveat

`x`/`y`/`scale` shorthands are NOT hardware-accelerated — they use `requestAnimationFrame`:
```jsx
<motion.div animate={{ x: 100 }} />                          // drops frames under load
<motion.div animate={{ transform: "translateX(100px)" }} />  // hardware accelerated
```

### CSS animations beat JS under load

CSS animations run off the main thread. Use CSS for predetermined motion, JS for dynamic
and interruptible motion.

---

## Native

- **React Native Reanimated v4** — animations run on the UI thread via worklets. v4 added CSS-style animations and transitions plus experimental shared element transitions. Pair with `react-native-gesture-handler` for gesture-driven motion.
- **Moti** — declarative wrapper over Reanimated; much less boilerplate for common cases.
- **@shopify/react-native-skia** — GPU-accelerated 2D graphics, custom shaders, high-performance charts.
- **Lottie / dotLottie** — designer-authored motion from After Effects. `react-native-skottie` renders via Skia.
- **Rive** — interactive state-machine animations; better than Lottie when animation responds to app state.

---

## SMIL — current browser status

SMIL was never actually deprecated in browsers. Chrome suspended its 2015 deprecation intent.
SMIL remains correct for SVG-native animation, particularly for assets in `<img>` tags where
CSS `@keyframes` can't reach.

**The `pathLength` attribute** is the key technique for stroke draw-on animation. Setting
`pathLength="100"` on a path declares a path length of 100 units regardless of actual geometry,
letting you write `stroke-dasharray="100" stroke-dashoffset="100"` on every path and animate
`stroke-dashoffset` from 100 to 0. No JS measurement needed.

**Path-morphing libraries** when two paths share command structure:
- **GSAP MorphSVG** — free since v3.13; GreenSock license
- **flubber** — MIT; interpolates between dissimilar shapes
- CSS `d` property interpolation — in Chrome and Safari; no library needed

---

## Cohesion

Motion must express the theme's thesis. Match motion to the component's personality: a dense mono technical theme should be crisp and fast; a warm organic theme can be slower and softer. Sonner feels right partly because easing, duration, design, and even the name are in harmony — slightly slower, `ease` rather than `ease-out`, to feel elegant. A theme named "Terminal Gold" with 320ms calm easing is incoherent even though both values pass individual gates.

Check cohesion at the composition level: does motion.character match the theme's design_language, typography register, and visual density?

`design_language` is an **open, brief-derived vocabulary with no default set.** A table of
expected motion registers used to sit here, keyed to six stock language names; both the table
and those names were removed on 2026-09-10. Real languages are the brief's own words
(`neobrutalism`, `hand-drawn`, `parallax-scrolling`, `minimalism`) or slugs derived from the
brief's subject matter, and none of them were ever in that table — so it could only ever match
names no theme produces, while tempting a reader to snap a live language onto the nearest row.

**Derive the motion register from the style itself, and argue for it in
`composition.ambition`.** Ask what the named style actually implies about how things should
move: what it is made of, how fast that material behaves, whether it snaps, settles, drags or
draws. `hand-drawn` implies a stroke with a speed; `neobrutalism` implies weight landing;
`parallax-scrolling` implies rate differences between planes. Those are answerable from the
style without a lookup, and they are answers a table of six registers could never have held.

`tf_motion_cohesion.py` (Gate 20) therefore performs **no register comparison at all** — it
keeps only its language-independent checks. Whether a theme's motion suits its direction is
design-critic's judgment, made against that theme's own stated ambition. A theme whose
ambition does not argue for its motion register has left the question ungradeable, which is
itself a finding.

---

## Interruptibility

CSS **transitions** can be interrupted and retargeted mid-animation. CSS **keyframes** restart from zero when interrupted. Rule:

- Enter/exit animations → CSS transitions (or springs for gesture-driven motion)
- Looping ambient sequences → keyframes acceptable
- One-shot decorative / load sequences → keyframes acceptable

Any `@keyframes`-driven animation on an element that also has an open/closed, expanded/collapsed, or toggled state is a MEDIUM finding. Use `@starting-style` for CSS-only entry without JS.

---

## Asymmetric Timing

Slow where the user is deciding; fast where the system responds.

```css
/* Hold-to-confirm / drag-release pattern */
.overlay { transition: clip-path 200ms ease-out; }            /* release: fast */
.button:active .overlay { transition: clip-path 2s linear; }  /* press: slow, deliberate */
```

Applies to: hold-to-confirm, drag-release, multi-step commits, progress disclosure.

---

## Blur-masked crossfade

When a crossfade shows two overlapping states despite tuning easing/duration, add `filter: blur(2px)` during the transition to blend them into one perceived transformation. Keep blur < 20px — heavy blur is expensive, especially Safari.

---

## Fix Ladder

When multiple motion findings exist for a theme, fix in this order (highest leverage first):

1. **Easing** — wrong curve (ease-in, built-in weak curves) → replace with strong custom curve
2. **Origin/physicality** — scale(0), wrong transform-origin → fix to scale(0.92–0.97), origin from trigger
3. **Interruptibility** — keyframes on toggled elements → convert to CSS transitions
4. **GPU** — animating layout properties (width/height/padding) → switch to transform/opacity
5. **Asymmetric timing** — uniform timing on deliberate/response actions → add asymmetric durations
6. **Polish** — blur crossfade, stagger, @starting-style, spring feel
7. **A11y + cohesion** — prefers-reduced-motion, motion character vs. thesis

Stop when the regeneration budget runs out; never skip a higher-leverage item to do polish first.

---

## Sources

Emil Kowalski: skills/review-animations/STANDARDS.md and skills/animate/SKILL.md (MIT,
github.com/emilkowalski/skills) — see this file's header comment for the exact scope; the
repo's `find-animation-opportunities` and `improve-animations` skills are explicitly not a
source. Motion and GSAP documentation; React Native Reanimated documentation; MDN
`prefers-reduced-motion`.
Ported 2026-08-25.
