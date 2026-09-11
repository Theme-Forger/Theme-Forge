# React Native platform constraints

## Changed since last refresh
Seed baseline — no refresh yet.

This is the reference a theme-designer reads before resolving anything to native,
and the domain a `design-researcher` refreshes most often — Expo ships SDK
releases several times a year and each one changes the config surface. Treat it
as high-priority in a delta check when the project has a native platform.

## What React Native does not have

No CSS custom properties. No cascade — styles don't inherit except for a narrow
set of text properties, and only from `<Text>` to nested `<Text>`. No `calc()`,
`clamp()`, `min()`, `max()`, `var()`, `color-mix()`, `light-dark()`, `oklch()`.
No pseudo-selectors, no `::before`/`::after`, no media queries. No
`backdrop-filter`, no `filter`, no `transition`, no `cursor`. No CSS grid —
Flexbox only, and `flexDirection` defaults to `column`, not `row`.

Theming is therefore a **runtime JavaScript concern**: a context provider
holding a theme object, swapped on `useColorScheme()`. There is no way to change
a value in one place and have the tree re-render from CSS. This is why `theme.ts`
and `useTheme.ts` exist and why they must contain only flat values.

## Units

Everything is a **unitless number** in density-independent pixels. `padding: 16`,
not `"16px"`. Percentage strings work for width/height and a few layout
properties only.

`lineHeight` is **absolute**, not a multiplier. `lineHeight: 1.5` means one and a
half pixels of line height and will render as overlapping text. Pre-multiply: a
16px font at 1.55 leading is `lineHeight: 25`.

`letterSpacing` is absolute too. `-0.02em` at 16px is `letterSpacing: -0.32`.

This is why the schema stores `px_at_base` alongside the CSS value for leading
and tracking.

## Fonts

React Native does not synthesize font weights reliably. On Android especially,
setting `fontWeight: '700'` on a custom family that has no registered bold
variant produces either the regular weight or a mangled synthetic bold.

The correct pattern is one registered family name per weight:

```ts
fontFamily: theme.typography.body.families['600']  // "Inter_600SemiBold"
```

Variable fonts are supported unevenly across platforms and SDK versions. Treat
discrete weights as the safe default and variable axes as an enhancement.

Fonts load asynchronously. Expo's `useFonts` returns a loaded flag and the splash
screen should be held until it flips, or the app flashes system fonts. Note this
in `fonts.md` for every theme.

The system fallbacks that always exist: iOS `System` / `Georgia` / `Menlo`;
Android `sans-serif` / `serif` / `monospace`.

## Shadows and elevation

The single biggest translation gap.

**iOS** takes `shadowColor`, `shadowOffset: {width, height}`, `shadowOpacity`,
`shadowRadius` — a real shadow model, close enough to CSS to translate directly.

**Android** takes a single `elevation` integer. It is always a neutral blurred
shadow, positioned by the system. You cannot offset it, color it, or make it
hard-edged.

Consequences a designer has to decide about, not discover:

- A **colored shadow** — common in the Confident Saturate and Retro-Futurist
  directions — has no Android equivalent. Either accept a neutral shadow there,
  or switch Android to a border-based elevation strategy for that theme.
- A **hard offset shadow with no blur** — the defining feature of Neo-Brutalism —
  is impossible via `elevation`. The honest Android expression is a solid border
  plus an offset sibling `View`, or a border-only elevation strategy. Pick one
  and write it down.
- **Multi-layer shadows** don't exist on either platform. Collapse to one.
- On Android, `elevation` requires a `backgroundColor` on the same view or
  nothing renders. That backgroundColor comes from the surface color token
  applied to the view — the elevation token itself carries only the integer.

The schema's `native_strategy` field exists so a theme can say "shadow on iOS,
border on Android" explicitly rather than degrading silently.

## Blur and glass

`backdrop-filter` does not exist. Blur comes from `expo-blur`'s `<BlurView>` (or
`@react-native-community/blur` in bare projects), which is a **native module** —
it does not run in Expo Go and requires a development build.

Every glass-dependent theme must therefore ship:

- an `intensity` and `tint` for `BlurView`,
- a **designed fallback** — a solid or high-opacity color that still expresses
  the theme when blur is unavailable,
- `requires_dev_build: true` so the user is told before they pick it.

Blur is also expensive. On a scrolling list it will cost frames. Restrict it to
the navigation layer, which is what Apple's own guidance says anyway.

## Gradients

No CSS gradients. `expo-linear-gradient` provides linear gradients — another
native module, though a cheap and universally available one. Radial and conic
gradients require Skia (`@shopify/react-native-skia`), which is a substantially
heavier dependency.

A theme whose identity rests on a mesh gradient background needs either Skia, or
a pre-rendered image asset, or a redesigned native expression. Decide at design
time.

## Layout

Flexbox only. `flexDirection` defaults to `column`. No `gap` on older versions —
check the RN version before using it; `gap`, `rowGap`, and `columnGap` are
supported on modern versions but a fallback of margin-based spacing is safer for
a generated theme.

Safe areas come from `react-native-safe-area-context`'s `useSafeAreaInsets()`,
not from `env(safe-area-inset-*)`. Any theme that specifies edge padding needs to
say whether that padding is inside or outside the safe area.

`position: fixed` doesn't exist. `position: absolute` is relative to the nearest
positioned ancestor. There's no `z-index` stacking context in the CSS sense —
later siblings render on top, and `zIndex` works only within the same parent.

Touch targets: the 24×24 CSS pixel minimum from WCAG applies, but platform
guidance is stricter — Apple has long recommended 44×44 pt and Material
recommends 48×48 dp. Generate native components at the platform minimum, not the
WCAG one. Use `hitSlop` to extend a target beyond its visual bounds where the
design needs a small control.

## Styling libraries

**NativeWind v4** — Tailwind class names compiled for React Native. Consumes a
`tailwind.config.js`, which is why a theme that emits a Tailwind config ports
with modest changes. Note that it is Tailwind **v3**-shaped config, not v4's
CSS-first `@theme` block — the web and native Tailwind configs are not the same
file, and the applier must not assume they are. Supports dark mode via `dark:`
and `useColorScheme`. Not every Tailwind utility has a native equivalent;
unsupported ones are silently dropped.

**Tamagui** — universal, compiler-optimized, its own token and theme system.
Strong performance. Write tokens into its config shape.

**gluestack-ui** — built on NativeWind.

**Restyle** (Shopify) — a typed theme object with constrained style props.
Closest to a pure design-token approach.

**Plain StyleSheet** — `theme/theme.ts` plus a `useTheme()` hook backed by
`useColorScheme()`. Least magic, works everywhere, and the correct default when
nothing else is detected.

## Expo specifics

`app.json` / `app.config.{js,ts}` fields a theme touches:

```jsonc
{
  "expo": {
    "icon": "./assets/icon.png",                         // 1024×1024, opaque
    "userInterfaceStyle": "automatic",                   // light | dark | automatic
    "splash": { "image": "./assets/splash.png",
                "resizeMode": "contain",
                "backgroundColor": "#ffffff" },
    "ios": { "icon": "./assets/icon.png" },
    "android": {
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png", // 1024×1024 canvas, 66% safe circle
        "backgroundColor": "#ffffff",
        "monochromeImage": "./assets/monochrome-icon.png"
      }
    },
    "web": { "favicon": "./assets/favicon.png" }
  }
}
```

All of these are **PNG**, not SVG. Since there's no guaranteed rasterizer (see
`08-logos-graphics.md`), a native apply that can't rasterize must write the SVGs,
write `RASTERIZE.md` with the exact commands, and set the `app.json` fields to the
paths the PNGs *will* occupy — flagging clearly that the user must run those two
commands before the icons appear. Silently leaving the default Expo icon in place
is a bad outcome; so is writing a broken path with no explanation.

**Expo Router** puts the root layout at `app/_layout.tsx`. That's where a
`ThemeProvider` and `useFonts` go. **React Navigation** projects put it wherever
`NavigationContainer` lives, and React Navigation has its own theme object
(`DefaultTheme` / `DarkTheme` with `colors.primary`, `colors.background`,
`colors.card`, `colors.text`, `colors.border`, `colors.notification`) that should
also be populated from the theme, or navigation chrome will stay default-blue
while everything else changes.

Anything requiring a native module — blur, Skia, some Reanimated features, custom
fonts in a bare project — needs a **development build**. Expo Go can't run it. Say
so up front.

## Native translation notes for the twelve directions

These mirror the `**Native translation:**` lines in `04-aesthetics.md`.

| Direction | Native translation |
|---|---|
| Quiet Professional | Translates cleanly. Border-based elevation works identically on both platforms. Safest choice when native is primary. |
| Confident Saturate | Colored shadows don't exist on Android — switch `native_strategy` to `border` there, or accept neutral elevation. Saturated fills translate fine. |
| Editorial Type-Led | Translates well, but fluid type doesn't exist — pick fixed sizes per breakpoint, and support Dynamic Type by scaling from the token rather than hardcoding. Serif rendering differs subtly across platforms; check the Android fallback. |
| Technical Dark | Translates cleanly and is well-suited to native. Dense layouts need explicit `hitSlop` to keep targets at 44/48. |
| Warm Human | Translates cleanly. Large radii and soft shadows work on iOS; Android's blurred `elevation` actually suits this direction. |
| Neo-Brutalist | Hard offset shadow is impossible via `elevation`. Use a border-based strategy on Android, or an offset sibling `View`. Decide explicitly. |
| Swiss Minimal | Translates cleanly — no elevation to translate. Grid rigor must be rebuilt in Flexbox. |
| Liquid Glass | Requires `expo-blur` and a development build. Must ship a designed non-blur fallback. Restrict to the nav layer. At most one glass direction per set when native is primary. |
| Expressive Material | Translates well — Reanimated springs are a better fit than CSS. Shape morphing needs Skia or is dropped. |
| Retro-Futurist | Gradients need `expo-linear-gradient`; radial/conic need Skia. Glow is a shadow on iOS and unavailable on Android — consider a border or a gradient stroke instead. |
| Bento Modular | Translates cleanly. Varied grid spans must be rebuilt with nested Flexbox or a masonry library. |
| Organic Soft | Blob SVGs need `react-native-svg`. Claymorphic inner shadows don't exist on either platform — approximate with a lighter inner `View` or a gradient. |

## Sources

Expo and React Native documentation and release notes; Apple Human Interface
Guidelines; Material Design 3. Accessed for seed compilation, August 2026.
