# Mobile design

## Changed since last refresh
Seed baseline — no refresh yet.

## iOS

Current guidance centers on the Liquid Glass material introduced with iOS 26. The rules that matter:

- Apply glass to the **navigation layer only** — tab bars, toolbars, sheets, popovers, floating action buttons. Not to content, not to full-screen backgrounds, and never stacked glass on glass.
- Tab bars float above content and minimize on scroll, with an accessory area above them.
- Corner radii are large and *concentric* — nested elements share a center of curvature with their container and with the hardware.
- Tabs are for navigation between peer sections, not for actions.

Independent of the material: respect safe areas (Dynamic Island, home indicator), support Dynamic Type so the layout survives large text sizes, and keep the visual weight of chrome low relative to content.

## Android

Material 3 Expressive is the current direction — an emotion-focused evolution of Material 3. Its substantive pieces:

- **Motion physics** — spring-based motion replacing fixed easing and duration tokens.
- **Dynamic color** — expanded tonal palettes derived from a source color or the user's wallpaper.
- **A shape system** — many shapes beyond the rounded rectangle, with morphing between states.
- **New component patterns** — button groups, FAB menus, split buttons, expressive loading indicators.
- Larger, easier-to-locate targets and stronger emphasis on the primary action.

## Layout

Design phone → tablet → foldable. Container queries and adaptive layouts (list-detail splitting on wide screens) matter more than raw breakpoints. Reachability: primary actions belong in the lower third on phones.

## Representing mobile in an HTML preview

The mobile surface in the gallery has to read as a phone, not a narrow div. What sells it:

- A device frame with a realistic bezel — roughly 12px, dark, with an outer radius around 44px and an inner radius around 38px.
- A logical width of 393px (a current-generation phone), scaled down as needed.
- A **status bar** row: time on the left, then signal / wifi / battery glyphs on the right, in the theme's foreground color.
- A **Dynamic Island** — a centered black pill roughly 125×36 with fully rounded ends, positioned about 12px from the top.
- **Visible safe areas** — content inset from the top past the island, and a home indicator bar at the bottom (a ~140×5 rounded rect, centered, ~8px from the bottom).
- A **floating tab bar** that sits above the content with a margin, rounded, rather than pinned edge-to-edge. This alone reads as current.

Three screens side by side communicate the app better than one: an onboarding or sign-in screen, a home feed with the tab bar, and a detail or profile screen.

## Sources
Apple Human Interface Guidelines; Material Design 3. Accessed for seed compilation, August 2026.
