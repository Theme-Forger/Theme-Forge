# Accessibility

## Changed since last refresh
Seed baseline — no refresh yet.

## The standard

**WCAG 2.2** is a W3C Recommendation and the operative standard. It's what the ADA, Section 508, and the European Accessibility Act reference. Target **AA**.

WCAG 3.0 remains a Working Draft with a different conformance model and is not a compliance target — not before roughly 2028. Design to 2.2 AA and track APCA informally.

## Contrast

- 4.5:1 — body text, AA
- 3:1 — large text (≥24px, or ≥18.66px bold) and non-text UI components and graphical objects, AA
- 7:1 — body text, AAA

Non-text is the one that gets missed: input borders, toggle tracks, icon-only buttons, chart series, and focus indicators all need 3:1 against their surroundings.

## Criteria worth designing for directly

**2.5.8 Target Size (Minimum), AA.** Pointer targets are at least **24×24 CSS pixels**. There's a spacing exception — an undersized target passes if a 24px-diameter circle centered on it doesn't intersect another target's circle — plus exceptions for inline targets, equivalent alternatives, user-agent defaults, and cases where the size is essential. The 44×44 figure people remember is the AAA criterion, 2.5.5 Enhanced.

**2.4.11 Focus Not Obscured (Minimum), AA.** A focused element must not be entirely hidden behind sticky headers, footers, or cookie banners. Sticky headers and `scroll-margin-top` need to be considered together.

**2.5.7 Dragging Movements, AA.** Anything draggable needs a non-drag alternative — buttons, a menu, keyboard controls.

**3.3.8 Accessible Authentication (Minimum), AA.** Don't block paste into password fields, and don't require the user to solve a cognitive puzzle from memory.

**3.2.6 Consistent Help, A** and **3.3.7 Redundant Entry, A** — help in a consistent place; don't make people re-enter what they already gave you.

Also worth knowing: 4.1.1 Parsing was removed as obsolete in 2.2.

## Focus

Every interactive element needs a visible focus indicator. Use `:focus-visible` so mouse users don't see rings but keyboard users do.

```css
:where(a, button, input, select, textarea, [tabindex]):focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
  border-radius: inherit;
}
```

The ring needs 3:1 against the adjacent background, and it must be visible in both light and dark. A focus ring in the brand color often fails this on a brand-colored button — use a contrasting ring, or double it with a white inner outline.

## Preferences

- `prefers-reduced-motion: reduce` — see `06-motion.md`. Always honored.
- `prefers-contrast: more` — increase border contrast, remove translucency, strengthen text.
- `prefers-color-scheme` — paired with `color-scheme: light dark` on `:root`.
- `forced-colors: active` — Windows High Contrast. Don't fight it; use `forced-color-adjust` sparingly and make sure borders exist so shapes survive.

## Structure

Semantic landmarks (`<header>`, `<nav>`, `<main>`, `<footer>`, `<aside>`), one `<h1>` per page, headings in order without skipping levels, labels bound to inputs, `alt` on meaningful images and `alt=""` on decorative ones. A skip link as the first focusable element.

Don't rely on color alone. A status badge needs an icon or a text label as well as a hue — 8% of men have some form of color vision deficiency.

## Checking

Automated tools (axe-core, Lighthouse, Pa11y) catch roughly a third of real issues — contrast, missing labels, structural problems. The remaining two thirds need keyboard-only navigation and a screen reader. For generated themes, the automatable subset is what `tf_contrast.py` covers, and it's the right place to draw the line.

## Sources
WCAG 2.2 Recommendation and W3C WAI "What's New in WCAG 2.2"; MDN media feature references. Accessed for seed compilation, August 2026.
