# Applying to a cross-platform monorepo

The case where one repo contains **both** a web app and a native app (`tf_detect_stack.py`
reports `cross_platform: true`). This changes the strategy materially — read `stack-web.md` and
`stack-native.md` too.

## Write the tokens once, into a shared package

Duplicating the theme into two apps guarantees drift. Prefer writing the neutral tokens plus
both resolutions **once** into a shared package (`packages/tokens` or similar) that exports:

- the platform-neutral token object (from `tokens.json`),
- the CSS resolution (for the web app),
- the native resolution (for the mobile app).

Then the web app imports the CSS resolution and the native app imports the native resolution.
Both point at the same neutral source, so regenerating means updating **one package**, not two
apps. Note this in `THEME.md`.

## Don't create the package unilaterally

Package layout is a strong opinion in someone else's repo.

- If a suitable shared package already exists, use it.
- If not, **propose** creating one and show the diff — file list and contents — and wait for a
  go-ahead. Do not create it silently.

## Respect the workspace

- Use the workspace protocol already in use (`workspace:*` for pnpm, `*` for npm/yarn).
- **Never edit the lockfile.** Adding a workspace dependency is a `package.json` edit plus an
  install the **user** runs — print the command.
- **Turborepo / Nx:** a new shared package may need a pipeline entry (`turbo.json`
  `dependsOn`, or an Nx project target). Mention it; don't edit the pipeline config without
  asking.

## Applying per app

- Web app package → follow `stack-web.md`, importing from the shared tokens package instead of
  inlining values.
- Native app package → follow `stack-native.md`, importing the native resolution from the
  shared package.
- Back up files in **both** app packages before writing (the backup mirrors relative paths from
  the repo root).
