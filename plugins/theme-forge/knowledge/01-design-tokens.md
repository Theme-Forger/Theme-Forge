# Design tokens

## Changed since last refresh
Seed baseline — no refresh yet.

## The standard

The Design Tokens Community Group (DTCG) published its first stable specification, **2025.10**, on 28 October 2025. It is a W3C *Community Group* specification, not a W3C Recommendation on the Standards Track — but it is the de facto industry format, with support shipping or in progress across Figma, Sketch, Framer, Penpot, Supernova, Knapsack, zeroheight, Tokens Studio, Style Dictionary, and Terrazzo.

## Format

Spec-reserved properties are `$`-prefixed. `$value` and `$type` are the required pair; `$description`, `$extensions`, and `$deprecated` are optional. File extension `.tokens` or `.tokens.json`; media type `application/design-tokens+json`.

```json
{
  "color": {
    "primary": {
      "500": {
        "$type": "color",
        "$value": { "colorSpace": "oklch", "components": [0.55, 0.14, 264], "alpha": 1, "hex": "#4a63c8" },
        "$description": "Primary brand color"
      }
    }
  },
  "space": {
    "md": { "$type": "dimension", "$value": { "value": 16, "unit": "px" } }
  },
  "button": {
    "background": { "$type": "color", "$value": "{color.primary.500}" }
  }
}
```

Two things changed meaningfully in 2025.10 and are easy to get wrong:

- **`dimension` and `duration` are objects**, not strings. `{"value": 16, "unit": "px"}`, not `"16px"`.
- **`color` carries `colorSpace` and a `components` array**, with `alpha` and a `hex` fallback. This is what makes OKLCH tokens portable.

Composite types — object or array values with typed sub-values — cover `shadow`, `gradient`, `border`, `typography`, and `strokeStyle`. Aliasing uses `"{group.token}"` and resolves to a single value even inside arrays.

## Tooling

**Style Dictionary v5** is the current major line; v4 introduced first-class DTCG support and v5 tracks 2025.10. **Tokens Studio** targets the spec directly. Neither is required here — Theme Forge emits the formats itself with stdlib Python — but a token file that validates against DTCG is one a designer can import into Figma, which is a large part of the value.

## Mapping to platforms

- **CSS custom properties** — flatten the tree to `--group-name: value`. Path segments joined with `-`.
- **Tailwind v4** — emit directly inside `@theme { --color-primary-500: …; --font-display: …; --radius-lg: …; }`. Tailwind generates both the utilities and the CSS variables from that block. Namespace prefixes matter: `--color-*`, `--font-*`, `--text-*`, `--spacing-*`, `--radius-*`, `--shadow-*`, `--ease-*`, `--animate-*`.
- **shadcn/ui** — map to its semantic names (`--background`, `--foreground`, `--card`, `--popover`, `--primary`, `--primary-foreground`, `--secondary`, `--muted`, `--muted-foreground`, `--accent`, `--destructive`, `--border`, `--input`, `--ring`, `--radius`). Hitting these exactly means existing components adopt the theme with zero edits — by far the highest-leverage application path.
- **React Native** — a typed TS object plus a `useTheme` hook. NativeWind consumes the Tailwind config, so a v4-shaped theme block ports with minor changes.

## Sources
DTCG specification announcement and format documentation; Style Dictionary release notes. Accessed for seed compilation, August 2026.
