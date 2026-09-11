# Brief extraction

The brief is what keeps six subagents from producing six generic blue themes. Spend a little
effort here; it pays for itself.

## Sources, in order

1. **The skill argument.** If the user typed a description, that's the brief. Still detect the
   stack.
2. **`./CLAUDE.md`.** Read it fully — it's the primary documented input. Pull the product's
   purpose, audience, tone, and any stated brand constraints (existing colors, "must feel
   trustworthy", "our users are developers").
3. **`./README.md`, `./package.json`, `./app.json` / `app.config.{js,ts}`.** The package name,
   description, keywords, and dependencies say a lot. `app.json` confirms an Expo app and its
   current icon/splash.
4. **The codebase itself.** An existing global stylesheet, a `THEME.md`, a `tailwind.config`,
   or a `components.json` tells you what's already there and what "restyle" means to them.

## Only ask if you must — at most three questions

If nothing above yields enough, ask exactly:

1. What is the product, in one sentence?
2. Who is it for?
3. Three adjectives for how it should feel.

Never ask a fourth. Never ask about colors or fonts — that's your job.

## What the brief must contain

Write `current/brief.product.json`:

```json
{
  "version": 2,
  "name": "Northwind",
  "description": "A budgeting app for freelancers with irregular income.",
  "audience": "Solo freelancers, anxious about cash flow.",
  "adjectives": ["calm", "trustworthy", "quietly confident"],
  "voice": "warm and encouraging",
  "brand_lane": "product",
  "anti_references": ["designs the brief explicitly rejects"],
  "motion_budget": {
    "website": "moderate",
    "webapp": "moderate",
    "mobile": "moderate"
  },
  "content_theme": "personal budgeting for irregular freelance income — not generic fintech placeholder copy",
  "platforms": ["web", "native"],
  "primary_platform": "native",
  "motion_note": "…"
}
```

**`brand_lane`** drives per-surface motion budgets — pick one:
- `brand` — the marketing site is the product; animate freely. App UI is secondary; keep it
  conservative.
- `product` — the app UI is the product; animate purposefully. The marketing site is a summary;
  keep it restrained.
- `both` — full motion budget on both surfaces, scaled to the brief's adjectives.

**`content_theme`** prevents fintech/SaaS placeholder copy on every surface's preview content.
State the actual product domain so `content-brief.json` (Step 1b) and every `surface-composer`
invocation write contextually appropriate copy instead of a generic default.

Also write `current/brief.design.json` if it does not already exist:

```json
{
  "locked_tokens": {},
  "locked_fonts": []
}
```

`brief.design.json` holds any client-mandated design constraints — specific hex values,
required typefaces — extracted from the brief (e.g. "existing brand green #1f7a5a" becomes a
`locked_tokens` entry). Leave the defaults if the brief states no lock requirements — do not
omit the file.

`platforms` and `primary_platform` come from `tf_detect_stack.py`, not from guessing:

- Expo / React Native only → `primary_platform: "native"`, design mobile-first; the website is
  a marketing site.
- Web only → `primary_platform: "web"`.
- Cross-platform monorepo → both platforms, both must be equally strong; pick the primary from
  where the product actually lives (usually the app, not the marketing site).

## Confirm before spending tokens

Show three lines and let the user correct them:

```
Product   A budgeting app for freelancers with irregular income.
Feel      Calm, trustworthy, quietly confident.
Platforms web + native (Expo Router, NativeWind v4)  — primary: native
```

A wrong platform guess is the expensive mistake — it changes the whole slot assignment and the
mobile-vs-web emphasis. Getting a correction here costs one message and saves six subagents.
