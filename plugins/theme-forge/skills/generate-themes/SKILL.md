---
name: generate-themes
description: >-
  Generates six distinct, research-backed design themes for a project and opens a browser
  preview showing each one as a website, a web app, and a mobile app — then applies the one
  you pick. Use this whenever someone wants design directions, a visual identity, a design
  system, a color palette, a theme, branding, a logo, a restyle, or a UI refresh for their
  project, and also when they ask what their app should look like or say the design feels
  generic. Works for web projects, React Native and Expo apps, and monorepos containing both,
  from a project description, a CLAUDE.md, or an existing codebase.
argument-hint: "[project description, or leave blank to read CLAUDE.md]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), Bash(python3 ${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/*), Read, Write, Glob, Grep, Task, WebSearch, WebFetch
---

# Generate themes

The full loop: read the brief → research → generate six themes in parallel → preview → ask
which → apply → offer a zip. Keep the user informed in two or three bullets per step, not walls
of text. Run every `python3` call **quoted** (paths have spaces) and with the plugin-root
fallback chain exactly as written below:
`"${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/…"`.

`CLAUDE_PLUGIN_ROOT` is substituted by the harness in `hooks/hooks.json`, but it is **not**
exported into the Bash environment for agent or skill bodies — verified by inspecting the live
env, where only `CLAUDE_CODE_*`, `CLAUDE_EFFORT` and `CLAUDE_PID` are present. A bare
`"${CLAUDE_PLUGIN_ROOT}/scripts/x.py"` therefore expands to `"/scripts/x.py"` and fails
silently-ish, in every mode. The chain resolves in priority order: the harness variable when a
real plugin install sets it, then `THEME_FORGE_ROOT` for a custom layout, then the repo-relative
path for running straight out of a clone. Do not "simplify" it back to the bare form.

All scripts print one JSON object to stdout; progress goes to stderr. Read the JSON.

## Step 0 — Resolve paths, check for a previous run

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_paths.py" --json
```

Read `current/run.json` if it exists. If it exists **and** its `exported` array is empty, tell
the user once and wait for an answer:

> There's a previous theme set from {generated_at} that was never exported. Generating will
> delete it. Want me to export any of them first?

Then proceed on their answer. Do not wipe anything yet.

## Step 1 — Build the brief

Resolution order — stop when you have enough:

1. The skill argument.
2. `./CLAUDE.md` — read it fully. This is the primary documented input.
3. `./README.md`, `./package.json`, `./app.json` or `app.config.{js,ts}`.
4. If none yield enough, ask **at most three** short questions: what the product is, who it's
   for, and three adjectives for how it should feel.

Also detect the stack **now** — the platform set belongs in the brief:

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_detect_stack.py" --root . --json
```

An Expo-only project should be designed **mobile-first**, the website surface serving as a
marketing site. A cross-platform monorepo needs both surfaces equally strong.

Compose `brief.product.json` with the structure below. **Do not write it to disk yet** —
`current/` is wiped in Step 4 and anything written here would be destroyed before an agent
could read it. Compose it now, confirm it with the user at the end of this step, and write it
in Step 4 immediately after the wipe verifies clean. (Preserving it through the wipe instead is
the wrong fix: `tf_verify_wipe.py` requires `current/` to be *exactly* empty, and a brief that
outlives a wipe is the same class of cross-run contamination the check exists to catch.)

```json
{
  "version": 2,
  "name": "…",
  "description": "one-sentence product description",
  "audience": "specific audience description",
  "adjectives": ["…", "…", "…"],
  "voice": "brand voice — e.g. 'confident and terse' / 'warm and encouraging'",
  "brand_lane": "brand | product | both",
  "anti_references": ["designs the brief explicitly rejects"],
  "motion_budget": {
    "website": "full | moderate | conservative",
    "webapp": "moderate | conservative | minimal",
    "mobile": "moderate | minimal"
  },
  "content_theme": "what the surface copy should actually be about — not 'fintech placeholder'",
  "platforms": ["web"],
  "primary_platform": "web",
  "motion_note": "…"
}
```

Also compose `brief.design.json` (written in Step 4 alongside the product brief):

```json
{
  "locked_tokens": {},
  "locked_fonts": []
}
```

`brief.design.json` holds any client-mandated tokens (specific hex values, required typefaces).
Leave the defaults if the brief has no lock requirements — do not omit the file.

**`brand_lane`** drives per-surface motion budgets:
- `brand` — marketing site is the product; animate freely. App UI is secondary; keep it conservative.
- `product` — app UI is the product; animate purposefully. Marketing site is a summary; keep it restrained.
- `both` — full motion budget on both surfaces, scaled to the brief's adjectives.

**`content_theme`** prevents fintech/SaaS placeholder copy. State the actual product domain
so the preview surfaces use contextually appropriate copy.

Show the user a **three-line** summary of what you understood — product, audience/feel, and the
platforms you detected — and let them correct it before you spend six subagents on it. See
`references/brief-extraction.md`.

### Step 1b — Generate surface copy (immediately after the brief is confirmed)

Compose the following in the same turn as Step 1 — authored directly, not by a subagent. Like
the two brief files above, it is **written in Step 4 after the wipe**, not here.

**`current/content-brief.json`** — the raw-material content model for all three
surfaces (website, webapp, mobile — Phases 1-3 of the bespoke-composition rewrite
all read this same file). Each `surface-composer` invocation (Step 5b2 website,
5b3 webapp, 5b4 mobile) reads this directly and writes literal text into its own
bespoke HTML — there is no shared template with named slots to fill for any
surface anymore (the old `{{SC_*}}`-token / `surfaces.content.json` mechanism and
the shared partials it fed were fully retired in Phase 4). Write real content
specific to this brief: product name, domain, audience, voice, a one-paragraph
description, a feature list, sample data rows / stats / KPIs relevant to the
product (the webapp surface's `data-tf-role="data-display"` element, empty/
loading/error states, and the mobile surface's own screens all pull from this
same material — do not write a second, surface-specific content file), 2–4 FAQ
pairs, one testimonial, pricing tiers if the product has them, and a couple of
empty-state copy blocks (e.g. "no results yet", "something broke"). There is no
fixed schema — write whatever raw material this brief's product actually needs;
surface-composer adapts.

**Do not include a pre-built navigation array** (e.g. a `nav_areas: [...]` field
listing literal nav labels in a fixed order). A design-critic pass across a real
six-theme run found four of six themes using the exact same nav array, verbatim,
in the same order, because it existed as a single copyable field here — only the
two themes whose slot happened to call for something structurally different
(an icon rail, a mega-menu) diverged. Nav *content* (the product's category/
feature vocabulary) belongs in this file; nav *structure* — how many top-level
items, what they're grouped as, rail vs. bar vs. menu — is a `surface-composer`
design decision per theme, not something to standardize here. Put the raw
vocabulary in `categories`/`features` (already documented above) and let each
surface-composer invocation derive its own nav from that.

Use the brief's `name`, `description`, `audience`, and `content_theme` fields as the source.
Write realistic product copy: the hero h1 should be a real marketing headline for this brief,
not a description of what a headline should say. Pricing tier features should be the
product's actual differentiating features.

## Step 2 — Research (before generation, every run)

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_seed_knowledge.py" --json
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_freshness.py" --json
```

Act on `recommendation`:

- **`full_refresh`** → spawn **thirteen `design-researcher` subagents in parallel** (one per
  knowledge domain including `13-anti-patterns`, one `Task` block, one turn). When they
  return, mark each refreshed: `tf_freshness.py --mark-refreshed <domain> --sources <n>`,
  and regenerate `INDEX.md`.
- **`delta_check`** → spawn **two or three** on the domains most likely to have moved:
  `05-css-platform`, `07-component-systems`, `12-asset-tooling` (license terms and rate
  limits change without notice — always include when brand assets will be generated), and —
  if the project has a native platform — `11-native-platform`, which changes fastest.
- **`skip`** → no subagents; report when the knowledge was last refreshed.

Then **update the skill base** (the second half of requirement 3): fold what the researchers
found back into `04-aesthetics.md`'s direction catalogue, including each direction's native
translation note, and append any newly-discovered technique to the relevant `references/` file
with a dated note. The knowledge the tool uses tomorrow should be better than today's.

If `WebSearch` is unavailable or every researcher fails, continue with the seed and say so:

> No web access this run — using the seeded knowledge base from {seed_version}. The themes will
> still be good, but they won't reflect anything from the last few months.

Report two or three bullets of what changed, not a wall.

## Step 3 — Assign the six slots

Read `references/theme-slots.md`. The default six:

| Slot | Role |
|---|---|
| A | The safe one. Restrained, professional, obviously shippable. |
| B | The confident one. Saturated, expressive, strong personality. |
| C | The typographic one. Editorial, type-led, minimal ornament. |
| D | The technical one. Dark-first, dense, tool-like. |
| E | The human one. Warm, organic, softer geometry. |
| F | The swing. Whatever the brief secretly wants. Take a real risk. |

Adapt to the brief — a children's education app doesn't need a dark technical theme — but keep
six mutually distinct directions (differ on at least two of: color strategy, type character,
geometry).

**When `primary_platform` is native, bias toward directions that survive translation.** At most
**one** glass-dependent direction per set when native is primary — otherwise the set collapses
into sameness on device. This is a real constraint, not a preference (see `11-native-platform.md`).

Show the user the six one-line directions before spending the tokens, and let them swap one.

**Cream-ground cap:** Warm cream / parchment backgrounds (OKLCH hue 40–80°, lightness > 0.88)
are permitted on **at most one** slot in the set of six. If two or more assigned directions
would naturally use warm-neutral grounds, redirect the second one to a cooler or darker
neutral before spawning any subagents.

**Easing rule:** Remind each theme-designer: CSS `cubic-bezier` with `y2 > 1` is banned.
Springy energy in CSS = ease-out-expo/quint (see 13-anti-patterns.md rule 39).

**Illustration default:** Unless a direction has a strong abstract shape grammar, set
`assets.illustrations.strategy: "none"` in the brief direction notes you pass to each agent.

## Step 4 — Wipe and generate

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_reset.py --json"
```

`tf_reset.py` now self-verifies every wipe (`tf_verify_wipe.py`, called automatically): it
proves `current/` is left with zero files of any kind — no leftover CSS, copy/content JSON,
images, gallery/preview HTML — and that `$TF_HOME`'s top level has no stray entry outside
`current/`, `knowledge/`, `logs/`, `used.md`. Check the JSON's `verified_clean` field; if
`false`, read `verification.violations` and surface it to the user before continuing — don't
silently proceed on an unproven wipe.

### Step 4a — Write the brief files (immediately after the verified wipe)

Now write the three files composed in Steps 1 and 1b, in this order, before spawning anything:

```
current/brief.product.json     (Step 1)
current/brief.design.json      (Step 1)
current/content-brief.json     (Step 1b)
```

**This is the only correct place for these writes.** They belong to Step 1 logically and every
agent in Step 4 and Steps 5b2-5b4 reads them, but `tf_reset.py` `rmtree`s `current/` wholesale,
so writing them in Step 1 would delete them before a single agent spawned — the run would then
proceed with six designers reading a missing brief. Compose in Step 1, confirm with the user,
write here.

Verify all three exist before continuing; a missing `content-brief.json` in particular fails
late and confusingly, in `tf_content.py` during Step 5c, long after the composers have already
invented their own copy.

**Before spawning, pre-assign unique composition values across the six slots** to prevent
Gate A collisions that would otherwise require post-hoc patching or regeneration cycles:

| Value | Available options | Rule |
|---|---|---|
| `motion.signature_type` | logo-stroke-draw, curtain-drop-stagger, ink-drop-reveal, targeting-reticle-draw, prismatic-shimmer-assemble, scroll-triggered-parallax, parallax-layers, magnetic-buttons, draw-on-scroll, counter-sequences | One per slot |
| `design_language` | **Open vocabulary** — any kebab-case slug. **No default list; derive them (see below).** | One per theme, no repeats. Assign before spawning. |

**When the brief names its own styles, use the brief's words as the `design_language` values.**
A brief asking for "Minimalism, Retro, Progressive, Neobrutalism, Hand-drawn, Parallax scrolling"
should produce exactly those six slugs — `minimalism`, `retro`, `progressive`, `neobrutalism`,
`hand-drawn`, `parallax-scrolling`.

**When the brief names none, derive six of your own from the brief itself. There is no default
list, by design.** Read the product, its subject matter, its audience and its domain, and name
six directions that a designer pitching *this* brief would actually propose. Draw them from the
vernacular of the thing being designed — its materials, its era, its craft, how the people who
use it talk — not from a catalogue of generic registers. A toy shop, a dialysis clinic and a
freight brokerage must yield three completely different vocabularies; if your six slugs would
work unchanged on any other brief, they are wrong. Sanity-check them the way you would the
themes: six directions that differ on at least two of colour strategy, type character and
geometry, with at least one genuinely unexpected. Record them in `run.json` alongside the slot
assignment so the set is reproducible, and hand each theme-designer its slug verbatim.

The field stopped being an enum on 2026-09-09, and the six stock values were removed outright
on 2026-09-10. Both changes had the same cause: a closed set of six names for six slots makes
distinctness arithmetically forced rather than earned, and it cannot accept a brief's own
vocabulary without destroying information — a scroll technique and a tonal register are
orthogonal, so mapping one onto the other told each theme-designer something the brief never
said, and the motion gate then graded the theme against the wrong register. Distinctness is
enforced by Gate 11's uniqueness check, not by the vocabulary being closed. Gate 20 now runs
no register lookup at all: every theme's motion is judged by design-critic against its own
`composition.ambition`, which is why that field has to argue for the interpretation.

There is no pre-assigned `hero_archetype` / `grid_strategy` / `nav_pattern` anymore —
those enum fields were retired with the bespoke-composition rewrite (there is no
shared template library left to select from). Instead, each theme-designer authors
its own free-form `composition.structural_brief` (2–5 sentences of genuine creative
direction — see the agent's own "Your composition" section); `tf_structure.py`
(Gate 18, advisory) measures the resulting *rendered* structure for real similarity
rather than comparing self-reported labels.

Include each slot's pre-assigned `motion.signature_type` and `composition.design_language` in
that agent's prompt under **"Composition assignment (mandatory)"**. The agent must use
exactly these values in `theme.json` — Gate A (and Gate 11 for `design_language`)
will fail otherwise.

Spawn **six `theme-designer` subagents in parallel, in a single turn** (one message, six `Task`
calls). Each gets: the brief (including `platforms` and `primary_platform`), its slot and
direction, the target platforms, its output directory
(`current/themes/0N-<slug>/`), the knowledge file paths, the schema path
(`templates/theme.schema.json`), and its **composition assignment** (above). Each
self-validates with `tf_contrast.py` and `tf_native.py` before returning and returns only a
path + three-sentence summary.

**theme-designer no longer authors website markup or copy.** It stops at tokens,
palette, type, motion, dials, and brand-asset concepts — the actual bespoke
`surfaces/website.html`/`.css` is written by `surface-composer` in the new Step 5b2,
below, from `current/content-brief.json`.

**`used.md` is recorded automatically — do not write it yourself.** `tf_gallery.py` calls
`tf_ledger.py` at the end of every successful assembly (which only happens after Gate A has
passed), so the ledger updates itself once you run Step 5's gallery assembly. This used to be
a manual "the orchestrator writes it after Gate A" step; it silently got skipped often enough
(nothing else in the pipeline enforced it, and a wiped `current/` means a skipped run leaves
zero trace) that it was moved into the pipeline itself. Explicitly tell each agent: "Do not
write to `$TF_HOME/used.md` — it is recorded automatically, not by any agent."

Write `current/run.json` as they return (schema below). Set `requires_dev_build` and
`requires_packages` per theme from each `native.json`.

```json
{ "schema": 1, "generated_at": "…Z", "brief_summary": "…",
  "platforms": ["web","native"], "primary_platform": "native",
  "knowledge_refreshed": "…Z",
  "themes": [ { "index": 1, "slug": "…", "name": "…", "slot": "C", "direction": "…",
    "thesis": "…", "primary": "#…", "dir": "themes/01-…", "a11y": "pass", "native": "pass",
    "requires_dev_build": false, "requires_packages": [] } ],
  "exported": [], "applied": null }
```

## Step 5a — Deterministic gate sweep (A, C, D only — theme-file gates)

> **Gate ordering constraint:** Gate B (tf_slop.py) requires per-theme `preview.html` files
> that `tf_gallery.py` creates in Step 5c. Gates A, C, and D only need `theme.json` and can
> run now. Gate B **must** run in Step 5c, immediately after the gallery is built.
> Running tf_slop.py before tf_gallery.py causes it to find no preview.html and skip every
> theme silently — the slop gate produces no output and the gallery header shows nothing.

### Three-tier finding system

| Tier | Source | Effect |
|---|---|---|
| **hard-stop** | slop.json `hard_stop` array; tf_distinct.py gate failures; tf_contrast.py failures; tf_native.py failures | Blocks assembly. Triggers constrained regeneration (budget permitting). |
| **advisory** | slop.json `advisory` array; tf_distinct.py letter-not-spirit `warnings`; design-critic advisory findings | Does not block *assembly*, but is not left for the user to notice either — every advisory finding design-critic writes gets a real fix attempt in Step 5d2 before the gallery is presented. Still renders in the drawer for anything a fix pass couldn't resolve or judged a false positive. |
| **informational** | critique.md qualitative notes | critique.md only, refreshed post-fix (Step 5d3) so it reflects what actually shipped. |

### Constrained regeneration protocol

When a theme must be regenerated, do **not** discard what was already right.
A full rediscovery from zero wastes budget and risks trading one violation for another.

Before spawning the new theme-designer:
1. Read the failing theme's `theme.json` → extract `thesis`, `typography.display.family`, `motion.character`, `slot`.
2. Read the first paragraph of the theme's `README.md` → extract the logo concept (one sentence describing the mark).
3. Construct the regeneration task with this structure:

```
Keep exactly:
  thesis: "<thesis from theme.json>"
  display_font: "<family from theme.json>"
  logo_concept: "<one sentence from README.md>"
  motion_character: "<character from theme.json>"

Change only to satisfy:
  <verbatim constraint from the gate — e.g. "accent hue must be ≥ 20° from hue 43 and hue 28">
```

The theme-designer receiving this is in constrained regeneration mode: keep all four
preserved elements exactly, derive a fresh palette and spatial system that satisfies
the named constraint. Do not reconsider the thesis or display font.

**Regeneration budget — one pool of 3 per gate group.** Before the first gate runs,
add this to `current/run.json`:

```json
"regen_budget": { "gate_a": 3, "gate_cd": 3, "gate_b": 3, "critic": 3 }
```

Each gate group draws **only** from its own pool:

| Pool | Spent by |
|---|---|
| `gate_a` | Gate A (`tf_distinct.py`) failures — Step 5a |
| `gate_cd` | Gate C (`tf_contrast.py`) and Gate D (`tf_native.py`) failures — Step 5a |
| `gate_b` | Gate B (`tf_slop.py`) `hard_stop` findings — Step 5c |
| `critic` | design-critic's `REGENERATE` recommendation — Step 5e |

A regeneration decrements its own pool and no other. When a pool reaches 0, record the
residual for **that** gate and proceed — never loop, and never borrow from another pool.

**Why per-gate and not one shared counter.** This was a single `"regen_budget": 3` shared
across every trigger, and on a real run that meant the first gate to fail consumed the whole
allowance: a six-theme set hit four Gate A failures (clustered accents, a lightness-band
overflow, an over-used intensity), spent all 3 fixing them, and arrived at Gates C/D, Gate B
and design-critic with **zero** remedy available — every later hard-stop would have had to be
recorded as a residual and shipped, not because it was unfixable but because an earlier,
unrelated gate had already drained the pool. Gate A failures are set-level (hue spacing,
distribution) while Gate C is per-theme accessibility and Gate B is per-theme anti-slop; they
fail for unrelated reasons and should not compete for the same allowance.

**The ceiling is now 12 regenerations, so the anti-loop rules matter more, not less.** Keep
both: a theme regenerated by any gate is re-checked by **all** gates (a Gate C fix can easily
break Gate A's hue spacing), and no pool ever refills within a run.

Run Gates A, C, and D in sequence in this step. Gate B (tf_slop.py) runs in
Step 5c, immediately after tf_gallery.py builds the preview.html files it needs.
Each gate is blocking: a theme that fails is regenerated (budget permitting) and
re-checked by **all gates** (including Gate B, re-run in its correct position
after gallery rebuild) before the next gate runs on the rest of the set.

### Gate A — tf_distinct.py (set-level, hue/bg/font)

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_distinct.py" --json
```

**Always print the gate table in chat after every tf_distinct.py run** — not
just a summary. Reproduce the DISTINCTIVENESS GATE table verbatim (from
tf_distinct.py's stderr output), then the per-pair hue gaps, then the GATE
RESULT line. This must appear in chat before Step 5c.

On failure: for each `regeneration_hints` entry, apply the **constrained
regeneration protocol** (above), using the hint's `constraint` field as the
`Change only to satisfy:` value. Decrement **`regen_budget.gate_a`** per theme
regenerated. Re-run tf_distinct.py and print the gate table again.

**Allocate the pool across failures before spawning, not one hint at a time.**
`tf_distinct.py` emits one hint per implicated theme, but the failures are
set-level and a single theme can often satisfy several at once — so following
hints literally can burn the pool and still leave failures standing. On the run
that motivated this note there were 4 failures and only 3 hints: fixing the
hinted themes would have left an accent pair at 4° and a lightness-band overflow
unresolved with the pool empty, while assigning three fixes (accent, intensity,
background lightness) to the one theme that could carry them cleared all four
within budget. Work out the minimum set of themes that resolves every failure,
then spend.

**If failures remain after regeneration AND `regen_budget.gate_a` is exhausted —
STOP. Do not call tf_gallery.py.** Tell the user:

> Gate A FAILED — {N} failure(s) remain after {used}/3 Gate A regenerations. I
> can't auto-fix these any further. Options:
> - Tell me which theme to fix manually (I'll apply the constraint by hand)
> - Tell me to proceed to gallery with these failures noted in the drawer

Wait for their instruction. Only after an explicit "proceed" may you assemble
the gallery. Record residuals in `run.json["distinctiveness_warnings"]`.

`tf_distinct.py` also runs three advisory-only checks that never block this step:
Gate 18 (structural similarity across this run's own six themes), Gate 19
(does this run clash with a prior run's recorded hue/font/motion in
`$TF_HOME/used.md`?), and Gate 20 (does each theme's `motion.character`/duration/
easing actually cohere with its `composition.design_language`, via
`tf_motion_cohesion.py`). All three land in the same `warnings` array for
`design-critic` to weigh — see its §5 and §7b-cohesion for how it reads them.

### Gate C — tf_contrast.py (per-theme, accessibility)

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_contrast.py" --theme <dir> --json
```

Run for each theme directory. On failure: apply the constrained regeneration protocol,
decrementing **`regen_budget.gate_cd`**. The constraint to pass: the specific failing pair
and the target ratio (e.g., "text on background must achieve 4.5:1; current ratio is 3.2:1").

### Gate D — tf_native.py (per-theme, cross-platform)

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_native.py" --theme <dir> --json
```

Run for each theme directory. On failure: apply the constrained regeneration protocol,
decrementing **`regen_budget.gate_cd`** — Gates C and D share one pool, because they are both
per-theme correctness checks and a single regeneration commonly fixes findings from both (a
token rewritten to a flat hex for React Native usually shifts its contrast ratio too). The
constraint to pass: the specific token name and the React Native incompatibility (e.g.,
"surface-raised uses oklch() — must resolve to a flat hex or rgba value").

**Report** to the user after all gates: one line per gate (PASS / FAIL + finding
count), which themes were regenerated, and the remaining budget **per pool**
(`gate_a N/3 · gate_cd N/3 · gate_b N/3 · critic N/3`). Report every pool, not
just the ones spent — a reader needs to know what remedy is still available to
the gates that have not run yet.

**Letter-not-spirit warnings (advisory tier).** After reporting the gate results,
read `result.warnings` from tf_distinct.py's JSON and `result.table` (per-theme
metrics). For each warning, print a `⚠` line. Warnings do not decrement the
budget and do not block assembly.

Write them to `run.json["gate_warnings"]` (set-level, for design-critic).
**Also** compute which specific themes each warning implicates and write to
`run.json["theme_advisories"]` — a map from slug to list of applicable warning
messages. tf_gallery.py reads this to render advisory notes in each theme's drawer.

Attribution rules (use `result.table` per-theme metrics):

| Warning code | Implicated themes |
|---|---|
| `bg_cluster` | themes where `bg_l ≥ 0.90` |
| `primary_range_narrow` | all themes (set-level narrowness affects every slot) |
| `accent_range_narrow` | all themes |
| `accent_chroma_floor` | themes where `accent_chroma < 0.06` |
| `font_exhaustion` | all themes |
| `structural_similarity` | the specific `slug_a`/`slug_b` pair named in the warning |
| `ledger_hue_conflict`, `ledger_font_conflict`, `ledger_motion_conflict` | the theme named in the warning's `slug` field |
| `motion_cohesion_character`, `motion_cohesion_duration`, `motion_cohesion_easing` | the theme named in the warning's `slug` field |

**`structural_similarity` warnings** (Gate 18, `tf_structure.py`) only appear once
Step 5b2/5b3 have written each theme's `surfaces/website.html`/`webapp.html` — they
measure actual rendered structure (heading sequence, section count, class-name
shingles, layout mode, grid tracks) per surface, not self-reported labels, and are
advisory-only in this phase.
design-critic resolves each flagged pair against the screenshots (see its own
"Structural distinctiveness" section) — do not try to resolve them here.

Example `run.json["theme_advisories"]`:
```json
{
  "blazing-court": [
    "bg_cluster: background is near-white (L=0.97) — passed gate but may be a default rather than a deliberate choice"
  ]
}
```

## Step 5b — Brand assets (second wave)

After all gates complete (or budget is exhausted with residuals recorded), spawn
**six `brand-asset-designer` subagents in parallel, in a single turn** — one per
theme, using each theme's directory. This is Wave 2; the designer wave and all
gates in 5a must be complete before Wave 2 starts.

Each `brand-asset-designer` receives: the theme directory path, the knowledge file
paths (`knowledge/08-logos-graphics.md`, `06-motion.md`, `11-native-platform.md`),
and the plugin root. It returns an asset count and any outstanding manual steps.

Collect the return messages. Report to the user:
- Total assets generated (icons × 6, illustrations × 6, etc.)
- Any themes with outstanding `RASTERIZE.md` steps the user needs to run
- Any attribution required (should be "none on a default run")

Update `current/run.json` to record `brand_assets: "complete"` and any
`rasterize_needed` flags.

## Step 5b2 — Compose website surfaces (surface-composer, Wave 3)

After brand assets complete, spawn **six `surface-composer` subagents in parallel,
in a single turn** — one per theme, each parameterized `surface: website`. This is
Wave 3; it must come after Wave 2 (brand assets), since each surface-composer
references that theme's own generated icons/illustrations by path — never a shared
icon sprite.

Each `surface-composer` receives: the theme's directory (and its gated `theme.json` —
tokens, dials, motion budget, `composition.structural_brief`, `composition.ambition`),
that theme's own `brand/` assets, `current/content-brief.json` (the raw content
material from Step 1b), and the semantic-hooks reference
(`references/semantic-hooks.md` — the `data-tf-role`/`data-tf-interaction`/
`data-screen` contract the mechanical gates below depend on). It writes exactly two
files: `themes/0N-<slug>/surfaces/website.html` and `surfaces/website.css`, styled
only against that theme's own `--tf-*` custom properties — no shared component
classes, no shared icon sprite, and no recycled decorative shape from another
theme or from memory of "what hero decoration usually looks like." It then writes
`composition.layout_signature.website` back into that theme's `theme.json` (a few
self-declared structural facts — section count, nav style, primary grid, one-sentence
notes) for design-critic's narrative context and as raw input to Gate 18 below.

`tf_gallery.py` (Step 5c) reads these two files directly and **aborts the whole run**
if either is missing for any theme — there is no shared-template fallback to degrade
to. Do not skip this step or proceed to Step 5b3 before all six have returned.

## Step 5b3 — Compose webapp surfaces (surface-composer, Wave 4)

After Wave 3 (website surfaces) completes, spawn **six more `surface-composer`
subagents in parallel, in a single turn** — one per theme, each parameterized
`surface: webapp`. This is Wave 4; it does not have to wait on anything from Wave 3
beyond that wave's own completion (each webapp invocation is independent of that
theme's own website surface, and independent of every other theme).

Inputs are the same as Wave 3 (theme directory, gated `theme.json`, that theme's
`brand/` assets, `content-brief.json`, `semantic-hooks.md`) with `surface: webapp`.
It writes `themes/0N-<slug>/surfaces/webapp.html` and `surfaces/webapp.css` — a
real product surface with a `data-tf-role="data-display"` element, at least one
`<form>` with a real input, and `empty-state`/`loading-state`/`error-state`
elements (the webapp per-surface floor `tf_content.py` checks mechanically). It
then writes `composition.layout_signature.webapp` back into that theme's
`theme.json`, same shape as the website entry.

`tf_gallery.py` (Step 5c) reads these two files directly too and **aborts the whole
run** if either is missing for any theme, exactly as it does for website. Do not
skip this step or proceed to Step 5b4 before all six have returned.

## Step 5b4 — Compose mobile surfaces (surface-composer, Wave 5)

After Wave 4 (webapp surfaces) completes, spawn **six more `surface-composer`
subagents in parallel, in a single turn** — one per theme, each parameterized
`surface: mobile`. This is Wave 5; independent of every other theme and surface,
same as Wave 4.

Inputs are the same as Waves 3-4 with `surface: mobile`. It writes
`themes/0N-<slug>/surfaces/mobile.html` — at least 4 distinct
`<div class="screen-pane" data-screen="<name>">...</div>` blocks, each with
genuinely different content, not the device-frame chrome itself (bezel/status-bar
are shared infrastructure in `templates/device-frames.html`, never authored here)
— and `surfaces/mobile.css` styling that content. `composition.layout_signature.mobile`
gets written back with a `screen_count` in place of website/webapp's `section_count`.

Unlike website/webapp, mobile screens don't get wrapped in a per-theme `<section>`
directly — `tf_gallery.py` clones each theme's own screens into the shared device
frame at runtime (canvas) or embeds them directly per compare-grid cell, keyed by
that theme's numeric index. `tf_gallery.py` (Step 5c) still **aborts the whole
run** if either file is missing for any theme. Do not skip this step or proceed to
Step 5c before all six have returned.

## Step 5c — Draft gallery

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_gallery.py" --json
```

Assembles the complete `gallery.html` with all six themes, brand assets, and
motion CSS. Do **not** open it — the user will not see a draft. Record the
gallery path from the JSON result.

> **If assembly aborts with `dead custom property in surface CSS`:** a surface
> stylesheet uses `var(--tf-x)` with no fallback that nothing defines — neither
> `tf_gallery.py`'s injected token block nor the stylesheet itself. This is a
> hard stop by design and does **not** consume any `regen_budget` pool: it is a
> mechanical defect with one correct fix, not a design judgment. Run
> `python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_tokens.py" --all` to list every
> offender, then send the owning `surface-composer` back to declare each token
> on its surface's own root selector (or give it a real fallback). Do not
> "fix" it by deleting the declaration that used the token — the token exists
> because the value repeats, and deleting it removes the styling rather than
> restoring it. Re-run `tf_gallery.py` once clean.
>
> Why this is a hard stop: an undefined custom property is discarded at
> computed-value time, so the page renders plausibly with inherited values and
> nothing warns. One audited run shipped 496 of these across 10 of 12 surfaces.

> **Draft-only warning:** The gallery built here does NOT yet show slop counts
> or visual-review status in its header — those fields populate in Step 5f after
> tf_slop.py and design-critic have both run. Do not present or open this build.

### Gate B — tf_slop.py (per-theme, anti-slop) — runs HERE, after gallery build

> **This gate runs immediately after tf_gallery.py, not in Step 5a.** Gate B
> requires the per-theme `preview.html` files that tf_gallery.py just created.
> Running it before this point will silently skip every theme and produce no output.

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_slop.py" --json
```

Writes `slop.json` per theme — design-critic reads these later; do not delete them.
Each `slop.json` has separate `hard_stop` and `advisory` arrays.

> **If Gate B produces `"source": "stdlib"` and `"rules_checked": 14`** instead of 59,
> impeccable is not installed on this machine. Install it once with
> `npm install -g impeccable` and re-run. The script prefers the direct binary
> (`impeccable`) over `npx impeccable` to avoid npm registry network latency — so
> after a global install it will work on every subsequent run without any npx round-trip.
- `hard_stop` findings (severity high or above: scale(0) entrance, ease-in on UI,
  easing overshoot, extra cream ground, shape-assembled illustration): apply the
  **constrained regeneration protocol** from Step 5a. The `Change only to satisfy:`
  value is the finding's `rule` and `message` combined,
  e.g. `scale-zero-entrance: replace scale(0) with scale(0.95) + opacity:0`.
  Decrement **`regen_budget.gate_b`**, rebuild gallery (`tf_gallery.py`), re-run Gate B for
  that theme. When `gate_b` reaches 0, record the remaining `hard_stop` findings as residuals
  in `run.json["slop_residuals"]` and proceed — design-critic reads them and must note
  explicitly that they survived budget exhaustion rather than being judged acceptable.
- `advisory` findings: no regeneration. They will render in the gallery drawer (Step 5f).

## Step 5d — Critique

### Step 5d-pre — Start HTTP server and verify browser for design-critic

Start a local HTTP server so design-critic can navigate the gallery with a browser.
Do this BEFORE spawning design-critic.

```bash
python -m http.server 7890 --directory "<TF_HOME>" &
```

Gallery URL: `http://localhost:7890/current/gallery.html`

Verify it responds:
```bash
python -c "import urllib.request; urllib.request.urlopen('http://localhost:7890/current/gallery.html'); print('ok')"
```

If port 7890 is busy, try 7891, 7892 (increment until one succeeds).
Pass the confirmed URL to design-critic as `gallery_url`.

`current/screenshots/` already exists — `tf_paths.py` scaffolds it and
`tf_reset.py` recreates it after every wipe, so there is nothing to create
here. Get its absolute path from `tf_paths.py --json` (`current_screenshots`)
rather than assembling the string by hand, and pass that as `screenshots_dir`.

**It is the only permitted screenshot destination.** Every image any agent
captures during the run belongs there and nowhere else — not the project
workspace, not a bare relative filename, not `/tmp`, not the MCP server's
`.playwright-mcp/` scratch dir. It sits inside `current/` so the next run's
wipe clears it; anywhere else and review images outlive the themes they
depict. If an agent reports shots written elsewhere, treat that as a defect
in the agent, not a path to work around.

**Browser pre-flight check (mandatory — do not skip):**

Check whether a browser is available for design-critic BEFORE spawning it.
Visual review is mandatory; the agent must not silently fall back to structural-only.

```bash
claude mcp list 2>&1
```

Parse the output for `playwright`:
- If it shows `✓` or `Connected` → Playwright is live, proceed to Step 5d.
- If it shows `Failed to connect`, `timed out`, or `×` → **do not believe it yet.** Confirm with
  a real call before treating the browser as down (see below).
- If `chrome-devtools-mcp` shows `✓` or `Connected` → proceed to Step 5d (design-critic will
  use Chrome DevTools MCP automatically).

> **`claude mcp list` false-negatives, so a timeout here is not evidence.** Confirmed
> 2026-09-10: it reported **both** `playwright` and `chrome-devtools-mcp` as "Failed to connect
> — timed out after 30000ms" while Playwright was fully working — sibling agents had been
> screenshotting successfully throughout that same session. The check spawns a fresh `npx`
> instance and npx cold start costs 4-11s+ on this class of machine, so it times out against a
> server that connects fine in ordinary use.
>
> **Probe directly before stopping the run.** Call `mcp__playwright__browser_navigate` on the
> `gallery_url` you just verified. If it returns a page title, the browser is live — proceed to
> Step 5d, and **say so explicitly in the critic's task message** ("the health check reports
> both browsers down; that is an npx cold-start false negative, I verified `browser_navigate`
> works"). Without that, the critic runs the same check, reads the same lie, and falls back to
> structural-only on its own.
>
> Stopping the run on a false negative costs a full generation cycle and teaches the wrong
> lesson — the browser was never the problem.

Only if a **real browser call also fails** → **STOP and surface to the user:**

> ⚠ **Browser unavailable** — Playwright MCP timed out and Chrome DevTools MCP is also unreachable. The design-critic requires a browser to take screenshots; proceeding without one is not allowed (visual review is mandatory).
>
> To fix: in a separate terminal run `npx @playwright/mcp@latest`, then type "continue" here.

Wait for the user to confirm before spawning the critic.

**One path restriction that is not a browser failure:** MCP Playwright's screenshot tool refuses
any `filename` outside the plugin repo, so it cannot write into
`$TF_HOME/current/screenshots/visual review/`. That is not a dead browser — `browser_navigate`
and `browser_evaluate` still work. The critic falls through to **Node Playwright**, which writes
there fine. Do not restart or stop the run over it; mention it in the critic's task message so
it doesn't rediscover the problem.

### Step 5d — Spawn design-critic

**Always spawn the `design-critic` agent — no exceptions.** Without it, the run has
no craft analysis and the gallery header will show no visual-review status.

The design-critic agent has MCP Playwright **and** Chrome DevTools MCP tools in its
`tools:` frontmatter. It selects whichever browser is live at runtime:
Playwright first, then Chrome DevTools MCP, then node Playwright. If none is available
it writes a hard error to `critique.md` and stops — it does NOT silently skip the
visual pass. The pre-flight check above ensures this hard-stop case is surfaced to
the user before the critic is even spawned.

**Do not pre-take screenshots on its behalf;** pass only the paths and URL so it
can work autonomously.

Spawn the `design-critic` agent, passing it:
- `gallery_html_path` — absolute path to `current/gallery.html`
- `current_dir` — absolute path to the `current/` directory
- `gallery_url` — the `http://localhost:7890/...` URL confirmed above
- `screenshots_dir` — absolute path to `current/screenshots/`
- `plugin_root` — resolve it and pass the **absolute** path, don't hand the agent the
  variable: `python3 -c "import sys;sys.path.insert(0,'scripts');import tf_paths;print(tf_paths.find_plugin_root())"`
  from the plugin root, or the already-resolved value from `tf_paths.py --json` (`plugin_root`).
  A subagent's own shell does not inherit `CLAUDE_PLUGIN_ROOT` either, so passing the literal
  string just moves the empty-expansion problem into the agent.

The critic navigates to `gallery_url`, takes screenshots, runs structural
analysis, and writes `critique.md`. It does not fix anything itself and may
recommend at most **one** regeneration, drawn from `regen_budget.critic` — but its
findings are not just displayed to the user either: Step 5d2, immediately
next, spawns a `theme-fixer` per theme to act on every finding it wrote.

## Step 5d2 — Post-critique fix pass (MANDATORY — do not skip)

> **Why this step exists.** `design-critic` used to be pure advisory output — findings sat in
> `critique.md` for a human to notice or not. A real six-theme run found that in practice
> nobody went back and fixed them: touch-target violations, undersized type, orphan CSS,
> duplicate CTAs, nav-copy collisions across themes, and a shared card-grid pattern four themes
> fell into all shipped to the user untouched, because nothing in the pipeline *acted* on
> `critique.md` — it only displayed it. This step closes that gap: every finding `design-critic`
> writes gets a real fix attempt before the gallery is presented, not just a mention in a drawer.

Read `critique.md` in full. For each of the six per-theme sections (motion findings table,
touch-target rows, orphan-css-class/duplicate-cta-intent/skipped-heading findings, craft-check
verdicts, structural anomalies), extract that theme's own punch list. **Every finding gets
included** — advisory-tier findings are exactly what this step exists to close out, not just
`BLOCK`-tier ones (those are simply non-negotiable within the punch list, not the only items on it).

**Resolve cross-theme conflicts yourself, before spawning anything.** Two shapes of conflict
recur and cannot be resolved independently by six parallel agents without them contradicting
each other:
- **Nav-copy collisions** — critique.md's "Nav identity" section names themes using identical
  or near-identical wording for the same nav item. Pick one theme to keep the original phrase
  (whichever theme's own voice fits it best) and assign each other colliding theme a distinct
  rewording that still names the same destination, matching that theme's own established voice.
  State the exact assigned wording per theme in that theme's `theme-fixer` prompt.
- **Shared structural pattern** (critique.md's "Structural distinctiveness" section — e.g.
  several themes converging on one card-grid shape) — if a theme's *own* `composition.structural_brief`
  contradicts what's rendered (it claims variation it doesn't deliver), that theme's fix is
  mandatory truth-in-labeling, highest priority. For the others sharing the pattern, assign each
  a *different* bounded, CSS-only variation mechanism (one gets uneven column spans, another gets
  row-span/height variation, another gets a scale/rotation "peeking" treatment) — assigning the
  same mechanism to more than one theme just trades one convergence for another.
- If `critique.md`'s own `## Regenerate` line names a defect no targeted fix can address, that
  theme is exempt from this step for that specific finding — handle it in Step 5e instead.

The HTTP server started in Step 5d-pre is still running — reuse the same `gallery_url`,
don't start a second server on a different port.

Spawn **six `theme-fixer` subagents in parallel, in a single turn** — one per theme. Each
receives: the theme's own directory, the plugin root, its full per-theme punch list extracted
above (quote the actual critique.md text, don't paraphrase from memory), any cross-theme
wording/structural assignment made above, and the same `gallery_url` passed to `design-critic`
in Step 5d — `theme-fixer` has its own browser fallback chain (§0 of its own agent file) for
geometry-dependent fixes (touch targets, `scroll-margin-top`, assigned layout tweaks) and needs
this URL to use it. Tell each agent explicitly that up to five siblings are hitting the same
gallery concurrently, per its own §0 guidance on using its own tab.

> **Reliability note.** A background-run `theme-fixer` (and `design-critic`) has been observed
> to stall indefinitely (a stream watchdog timeout with no further progress) on a large,
> multi-hundred-tool-call task, while the identical task in the foreground completes normally.
> If a spawned agent in this wave stalls, retry it once in the foreground before escalating to
> the user — do not just report the stall as a final result.

After all six return, rebuild the gallery once (`tf_gallery.py`) and re-run Gate B
(`tf_slop.py --json`) across the full set to confirm findings actually dropped and no theme
regressed to a hard-stop. If any theme still shows a hard-stop after this pass, apply the
constrained regeneration protocol for that specific finding (same as Step 5a) before continuing.

## Step 5d3 — Re-critique (MANDATORY — do not skip)

Spawn `design-critic` again, exactly as in Step 5d, with one addition to its task message: tell
it this is a post-fix refresh, summarize what the Step 5d2 fix pass changed per theme (from
each `theme-fixer`'s own report), and tell it to treat the review as fresh — re-derive
everything, don't assume the fix reports are accurate without checking. This **overwrites**
`critique.md` with a current snapshot; per its own §8, the file's `pass:` line will read
`post-fix refresh` so anyone reading it later can tell it's current, not a pre-fix snapshot.

This is the mechanism that satisfies "critique.md reflects the fixes" — not a human remembering
to re-run it, not a note added to the old file. If `theme-fixer` fixed something that
`design-critic` still finds wrong (or, worse, introduced something new — a fix pass is a code
change like any other and can regress something that was fine before), that surfaces here,
before the user ever sees the gallery.

**This fix-and-refresh cycle runs at most once per generation run** — same discipline as the
regeneration budget elsewhere in this pipeline. If the refreshed `critique.md` still carries
findings, do not loop back into another `theme-fixer` wave automatically; record the residuals
and let Step 5e's regeneration path (or the user, after Step 6) decide whether they're worth a
further pass.

## Step 5e — Post-refresh regeneration (conditional)

### Step 5e-triage — is a regeneration actually the right instrument?

**Do this before spending any budget.** A critic recommending regeneration is stating a
verdict, not prescribing a mechanism — and it is reasoning from a screenshot, so it cannot
always tell how entangled a defect is in the theme's data. Read the critic's *stated reason*
and classify it:

**Targeted remediation** — the reason names one **replaceable token group** and does not
implicate the theme's thesis, composition, or structure. The clearest case is typography: a
theme whose faces duplicate a sibling's (Gate 21 `font_identity`) needs different families,
which touches only `typography.*`, the derived brand assets that are *set* in the display face
(wordmark, logo lockup, their outlined siblings and native rasters) and `requires_packages`'
font entries. It does **not** touch hue spacing, the ledger, layout, or any surface's markup,
because every surface already styles against `--tf-font-display`/`-body`/`-mono`.

Apply it like this, and **do not decrement `regen_budget.critic`** — that pool bounds
*re-design* cycles, and nothing is being re-designed here; the same reasoning that exempts a
gate defect (Step 5c) applies. Allowed **once per theme per run**:
1. Change the named tokens in that theme's `theme.json` (and `tokens.json`/`README.md` if they
   restate the value — they usually do; a token and its prose must not disagree).
2. Re-render only the artifacts derived from them. For a font swap that means every brand
   asset carrying live text, **including the outlined variants and the `brand/native/*.png`
   rasters** — a raster taken from the old face is a perfectly valid PNG of the wrong
   typeface, which has shipped before. Update the `@expo-google-fonts/*` package entries.
3. Re-run **Gates A, C, D**, then `tf_gallery.py`, then **Gate B** for that theme only.
4. Verify by *looking at* the re-rendered marks, not by exit code.

**Full constrained regeneration** — the reason implicates the thesis, the composition, more
than one token group at once, or anything whose change would cascade into Gate A's hue
spacing or the cross-run ledger. Proceed to the protocol below.

**When the critic's stated reason bundles both** (e.g. "borrowed typefaces *and* the palette
abandons its ambition), split it: remediate the targeted half, and record the rest under
`run.json["critic_residuals"]` for the user to judge from the finished gallery in Step 6.
Do not spend a regeneration on a bundled reason where only part of it is actionable —
especially where two critic passes disagreed on the contested half, which is itself evidence
the judgment is not settled enough to discard working work over.

### Step 5e — Post-refresh regeneration (conditional)

If Step 5e-triage classified the finding as **full constrained regeneration**, the
**refreshed** `critique.md` recommends it, and `regen_budget.critic > 0`:

1. Decrement `regen_budget.critic`.
2. Apply the **constrained regeneration protocol**: read thesis, display font, logo
   concept, motion character from the named theme, and construct the task with only
   the critic's stated reason as the change constraint.
3. Re-run **Gates A, C, D** (from Step 5a), then rebuild gallery (`tf_gallery.py`),
   then re-run **Gate B** (from Step 5c) for that theme only.
4. Rebuild the gallery: re-run `tf_gallery.py`.

If `regen_budget.critic == 0`: write the critic's request to `run.json` under
`"critic_residuals"` and proceed. Do not substitute an unspent pool from another gate — a
critic finding is not a Gate A finding, and the pools exist precisely so one gate's spend
cannot silently consume another's remedy.

Surface the critique to the user in 3–5 bullets before continuing to Step 5f — include what
the Step 5d2 fix pass resolved, not just what's still outstanding.

## Step 5f — Final gallery (MANDATORY — do not skip)

> **This step is not optional.** Skipping it leaves the gallery header showing
> slop count = 0 and visual review = "skipped" even when both ran correctly.
> tf_gallery.py is cheap (< 1 s); there is no reason to skip it.
> If you arrive at Step 6 and realise you skipped this step, run it now before
> opening the gallery.

The design-critic may have produced advisory findings in `critique.md` and
`current/slop-browser.json`. These are **advisory tier** — they do not block
but the user should see them before picking a theme.

Write any critic advisory findings (from `slop-browser.json`) to
`run.json["theme_advisories"]`, merging with the gate_warnings already there.
Then rebuild the gallery one final time:

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_gallery.py" --json
```

This final gallery includes the advisory notes in each theme's detail drawer
(tf_gallery.py reads `run.json["theme_advisories"]` and per-theme `slop.json`
advisory arrays). Step 5e's rebuild (if it ran) does **not** substitute for 5f,
because 5f picks up the slop-browser advisory findings that 5e doesn't know about.

## Step 6 — Open gallery

**Pre-open check — run this before tf_open.py:**

Verify all of these are true:
1. `current/themes/*/slop.json` exists for all six themes (written by Gate B in Step 5c).
2. `current/critique.md` exists **and its `pass:` line (second/third line of the file) reads
   `post-fix refresh`, not `initial`** — this confirms Steps 5d2/5d3 actually ran and the file
   reflects fixed content, not the pre-fix snapshot from Step 5d.
3. Step 5f's `tf_gallery.py` ran **after** all of the above were written.

If any condition is false, run the missing step now (5d2/5d3 if critique.md is still marked
`initial`, then 5f) — never open a gallery whose `critique.md` is a stale pre-fix snapshot.
The gallery shown to the user must always reflect the complete gate + critique + fix picture,
not a partial build.

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_open.py" --path <gallery.html> --json
```

Always print the absolute path as a fallback — never fail the run because the
browser didn't open.

**Print the final budget spend** before presenting themes, per pool, so an exhausted pool is
visible as the reason a residual shipped:
> Regenerations this run: gate_a N/3 · gate_cd N/3 · gate_b N/3 · critic N/3
> — [slug: gate, reason, …]

## Step 7 — Select

Present the six numbered in chat: number, name, one-line thesis, primary hex. **Flag any theme
that `requires_dev_build`** so the user knows before they pick. Accept a number, name, slug, or
description ("the dark one", "the second"). Resolve loosely and confirm.

If they want changes rather than a pick ("I like 3 but the green is too loud"), hand that to a
`theme-designer` as a revision task on that theme's directory, then regenerate the gallery
(`tf_gallery.py`). Don't make them start over.

## Step 8 — Apply

Invoke the **apply-theme** skill flow with the chosen slug. Don't duplicate that logic here.

## Step 9 — Export

After a successful apply, offer it without being asked: *"Want me to save this theme as a zip?"*
On yes, run the export-theme flow.

If anything misbehaves, see `references/troubleshooting.md`.
