# Component systems

## Changed since last refresh
Seed baseline — no refresh yet.

## Web

**shadcn/ui** — components are copied into the project as source, not installed as a dependency. This is the single most important target for theme application: because every component reads from a fixed set of CSS custom properties, writing those variables re-themes an entire app without touching a component file.

The variables to write:

```
--background --foreground --card --card-foreground --popover --popover-foreground
--primary --primary-foreground --secondary --secondary-foreground
--muted --muted-foreground --accent --accent-foreground
--destructive --destructive-foreground --border --input --ring --radius
```

Plus the `.dark` variants. Detect shadcn by the presence of `components.json`.

Recent shifts worth knowing: the CLI can scaffold full templates across Next.js, Vite, TanStack, React Router, Astro, and Laravel; **Base UI is now the default primitive layer**, with Radix still fully supported and React Aria available; the new-york style imports from the unified `radix-ui` package; there's an MCP server and a registry with namespacing, plus shareable presets encoding colors, fonts, and radius.

**Radix** — headless primitives, now shipped as a single `radix-ui` package. Unstyled, so themes apply cleanly.

**Base UI** — from the Radix team; shadcn's current default.

**Headless UI** — Tailwind Labs' primitives for React and Vue.

**MUI / Chakra / Mantine** — these have their own theme objects. Applying a Theme Forge theme means writing their config shape, not CSS variables. Detect and handle, but expect lower fidelity — their design languages are opinionated in ways a generated theme can't fully override.

## Native

**NativeWind** — Tailwind for React Native, and the most portable path between web and native because it consumes a Tailwind config. A theme that emits a Tailwind theme block ports to native with modest changes.

**Tamagui** — universal (web + native), compiler-optimized, strong performance. Has its own token and theme system; write tokens into its config shape.

**gluestack-ui** — component library built on NativeWind.

**React Native Reusables** — shadcn-shaped components for React Native, and therefore themeable the same way via NativeWind variables.

**Plain StyleSheet** — write `theme/theme.ts` exporting a typed object plus a `useTheme()` hook backed by `useColorScheme()`. Least magic, works everywhere.

## Application strategy

Order of preference when applying a theme:

1. If shadcn/ui is present → write its CSS variables. Zero component edits, immediate full effect.
2. If Tailwind v4 → write a `@theme` block in a new file, add one `@import`.
3. If Tailwind v3 → extend the config with variable references, add the `:root` block.
4. If a component library with its own theme system → write its config shape.
5. Otherwise → drop `theme.css` with custom properties, import it at the entry, and document the variable names.

In every case, prefer adding a new file plus a one-line import over rewriting an existing stylesheet.

## Sources
shadcn/ui, Radix, Base UI, NativeWind, and Tamagui documentation. Accessed for seed compilation, August 2026.
