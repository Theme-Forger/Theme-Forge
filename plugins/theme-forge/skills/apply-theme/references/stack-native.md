# Applying to a React Native stack

The theme dir's `native/` folder already contains `theme.ts`, `useTheme.ts`,
`tailwind.config.js` (a Tailwind **v3**-shaped fragment — **not** the web v4 `@theme` block),
`fonts.md`, and `app-icons.md`. Never run a package manager; print the commands.

## Expo + NativeWind

1. Merge `native/tailwind.config.js`'s `theme.extend` into the project's `tailwind.config.js`.
2. Copy `native/theme.ts` and `native/useTheme.ts` into the project (e.g. `theme/`).
3. Add `global.css` with the NativeWind directives if not present, imported from the root.
4. Wire the provider + `useFonts` into `app/_layout.tsx` (Expo Router) or the
   `NavigationContainer` parent (React Navigation). Hold the splash screen until fonts load.
5. **Populate React Navigation's own theme object** (`DefaultTheme`/`DarkTheme` with
   `colors.primary/background/card/text/border/notification`) from the theme, or navigation
   chrome stays default-blue while everything else changes.
6. Update `app.json` — `icon`, `splash`, `android.adaptiveIcon`, `userInterfaceStyle`.

## Expo + StyleSheet

Copy `theme/theme.ts` and `theme/useTheme.ts`, add the provider in the root layout, and read
values with `useTheme()`. No Tailwind config needed.

## Bare React Native

Same as StyleSheet, plus font linking via `react-native.config.js` and a note that
`cd ios && pod install` is needed. Custom fonts in a bare project need a rebuild.

## Tamagui / gluestack / Restyle

Write the tokens into their config shape. gluestack sits on NativeWind, so the Tailwind config
mostly applies; Tamagui and Restyle have their own token objects.

## Fonts — always

React Native doesn't synthesize weights. Install the exact packages from `native/fonts.md`
(one family per weight) and hold the splash until `useFonts` reports loaded. Print, don't run:

```
npx expo install expo-font @expo-google-fonts/<family> …
```

## Icons — PNG-only fields

`app.json` icon/splash/adaptiveIcon fields are **PNG**, not SVG. If a rasterizer is available
(`sharp-cli`, `rsvg-convert`, `magick`, `inkscape` — see `brand/RASTERIZE.md`), generate the
PNGs into `assets/` and point the fields at them. If none is available:

1. Write the SVGs into the project (or leave them in the theme dir).
2. Copy `brand/RASTERIZE.md` next to them.
3. Set the `app.json` fields to the paths the PNGs **will** occupy.
4. Tell the user clearly: two commands remain before the icons appear.

Silently leaving the default Expo icon, or writing a broken path with no note, are both bad
outcomes.

## Dev build

If the theme `requires_dev_build` (blur, Skia, newer Reanimated), say so up front — Expo Go
can't run it. Print `npx expo prebuild` / `eas build --profile development` guidance rather
than running it.
