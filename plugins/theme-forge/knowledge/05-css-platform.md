# CSS platform capabilities

## Changed since last refresh
Seed baseline — no refresh yet.

## Tailwind CSS v4

v4.0 shipped January 2025; the line is at 4.1/4.2 by mid-2026. The change that matters for theming: **configuration moved into CSS**. There is no `tailwind.config.js` in a v4 project.

```css
@import "tailwindcss";

@theme {
  --color-brand-500: oklch(0.55 0.14 264);
  --font-display: "Fraunces", Georgia, serif;
  --text-4xl: clamp(2.25rem, 1.8rem + 2.25vw, 3.75rem);
  --radius-lg: 0.875rem;
  --shadow-card: 0 1px 3px oklch(0.2 0.02 264 / 0.08);
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
}
```

The `@theme` block generates both the CSS custom properties and the corresponding utilities (`bg-brand-500`, `font-display`, `rounded-lg`). The namespace prefix determines which utility family a variable feeds. `@utility` defines custom utilities; `@custom-variant` defines custom variants.

This makes applying a theme to a v4 project close to trivial: write a `@theme` block, import it. Detect v4 by an `@import "tailwindcss"` in a stylesheet or `tailwindcss@^4` in dependencies — the absence of `tailwind.config.js` is a strong signal but not proof.

For v3, the theme goes in `tailwind.config.*` under `theme.extend`, ideally referencing CSS variables so runtime theme switching still works.

## Layout and selection

- **Container queries** — `@container` with a named container. Components that adapt to their own space rather than the viewport. This is the correct tool for a card that appears in both a sidebar and a main column.
- **`:has()`** — parent selection. `.card:has(img)`, `label:has(input:checked)`. Removes a large class of JS state-mirroring.
- **Nesting** — native, no preprocessor needed.
- **Cascade layers** — `@layer reset, base, components, utilities` gives deterministic precedence, which matters when injecting a theme into someone else's stylesheet.
- **`subgrid`** — child grids that align to the parent's tracks. Solves card-content alignment across a row.

## Transitions and animation

- **View Transitions API** — same-document via `document.startViewTransition()`; cross-document via `@view-transition { navigation: auto; }`. `view-transition-name` on an element makes it morph between states. Support is strong in Chromium and WebKit; Firefox has been catching up. Degrades to a crossfade or to nothing, so it's safe to use unguarded.
- **Scroll-driven animations** — `animation-timeline: scroll()` or `view()` with `animation-range`. Runs on the compositor with no JavaScript. Progress bars, reveal-on-scroll, parallax.
- **`@starting-style`** — defines the state an element animates *from* when it first renders, which is what finally makes entry animations work for `popover` and `dialog` without JS.

## Components and overlays

- **`popover` attribute** — top-layer overlays with light-dismiss, declaratively.
- **`<dialog>`** — modals with proper focus trapping and inert background.
- **Anchor positioning** — `anchor-name` / `position-anchor` / `position-area`. Tooltips and menus positioned relative to a trigger without JS measurement. Support is uneven; provide a fallback position.
- **`field-sizing: content`** — inputs and textareas that size to their content.

## Rules for the preview file

The gallery must render from `file://` with the network off. That means:

- No CDN scripts. No external CSS.
- Fonts via `@import` from Google, always with a complete local fallback stack after them.
- No `<iframe>` — `file://` iframe behavior varies by browser. Inline all six themes under scoped attribute selectors.
- No `localStorage` or `sessionStorage`. Plain JS variables.
- Charts as hand-written inline SVG from hardcoded data. No chart library.

## Sources
Tailwind CSS release notes and documentation; MDN CSS reference; Chrome and WebKit platform status. Accessed for seed compilation, August 2026.
