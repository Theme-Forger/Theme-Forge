# Applying to a web stack

In every case, **prefer adding a new file plus a one-line import over rewriting an existing
stylesheet.** The theme dir's `web/` folder already contains the three shapes below.

## shadcn/ui (detect: `components.json`) — highest-leverage path

Map to shadcn's semantic variable names and existing components adopt the theme with **zero
edits**. Copy the `:root` and `.dark` blocks from `web/shadcn.css` into the global stylesheet
named in `components.json` (`tailwind.css`), or add them to a new `theme.css` imported after
the shadcn base:

```
--background --foreground --card --card-foreground --popover --popover-foreground
--primary --primary-foreground --secondary --secondary-foreground
--muted --muted-foreground --accent --accent-foreground
--destructive --destructive-foreground --border --input --ring --radius
```

Plus the `.dark` variants. Detect eagerly — this is by far the highest-leverage application
path on web.

## Tailwind v4 (detect: `@import "tailwindcss"` in a stylesheet, or `tailwindcss@^4`)

v4 is CSS-first — there is no `tailwind.config.js`. Write `src/styles/theme.css` from
`web/tailwind.theme.css` (a `@theme { … }` block) and add one line after the Tailwind import:

```css
@import "tailwindcss";
@import "./styles/theme.css";
```

The `@theme` block generates both the CSS variables and the utilities.

## Tailwind v3 (detect: `tailwind.config.*`)

Extend `theme.extend` in the config, referencing CSS variables so runtime theme switching still
works, and add the `:root` block from `web/theme.css` to the global stylesheet.

## Plain CSS / CSS Modules / Sass / styled-components / emotion

Drop `web/theme.css` (`:root` custom properties + `.dark`), import it once at the entry, and
document the variable names in `THEME.md`. Same shape, different entry file:

- **Next.js app router** → import in `app/layout.tsx`; stylesheet usually `app/globals.css`.
- **Next.js pages** → `pages/_app.tsx`.
- **Vite / CRA** → `src/main.{tsx,jsx}` or `src/index.css`.
- **Astro** → a layout `.astro` file or `src/styles/global.css`.
- **SvelteKit** → `src/routes/+layout.svelte` / `src/app.css`.
- **Remix** → `app/root.tsx` `links()`.
- **Nuxt** → `nuxt.config` `css` array or `app.vue`.

## Component libraries with their own theme system

MUI / Chakra / Mantine have their own theme objects. Write their config shape from the token
values rather than CSS variables, and expect **lower fidelity** — their design languages are
opinionated in ways a generated theme can't fully override. Detect, handle, and say so.
