# Scripts

- **Python 3.9+, standard library only.** No pip, no npm. If you want a dependency, write the math.
- Every script takes `--json` and prints one JSON object to stdout on success.
- Human-readable progress goes to **stderr**, never stdout.
- Exit 0 on success, 1 on expected failure (`{"ok": false, "error": "..."}`), 2 on unexpected.
- Never delete a path that wasn't derived from `tf_paths.py`; assert it is under `TF_HOME` first.
- **Screenshots go under `$TF_HOME/current/screenshots/` and nowhere else** — but into one of
  **two** subfolders, and which one matters:
  - `visual review/` (`tf_paths.screenshots_dir()`) — **design-critic only.**
  - `build/` (`tf_paths.build_shots_dir()`) — every other agent's own verification shots:
    brand-asset contact sheets, theme-fixer before/after geometry, font specimens, rasterizer
    read-backs.

  Use `tf_paths.resolve_screenshot_path(out)` when the path came from a caller — it pulls a
  relative name (which would otherwise follow the CWD) and any absolute path outside TF_HOME
  back into the canonical directory. Both trees live under `current/` so `tf_reset.py` clears
  them; if you add a new scaffold dir there, add it to `tf_verify_wipe.py`'s `allowed_dirs` too
  or the post-wipe check will flag it.
- **The `visual review/` folder IS the header's claim, so only the critic may write to it.**
  `tf_gallery.py` counts its PNGs and renders the total as "visual critique: N shots". Any
  other image dropped there silently inflates how much review the run appears to have had.
  Confirmed twice: an early version counted `brand/native/` rasters and claimed **138 shots on
  a run with no browser at all**; the fix narrowed the path but left the docstring inviting
  "design-critic *and other visual-capture agents*", so a later six-theme run accumulated **86**
  PNGs there while `critique.md` recorded the critic's own count as **10**. Narrowing the path
  is only half the fix — restrict the *writers*.
- **Cross-check the two numbers.** `critique.md`'s own `visual critique: N shots` line is
  written by the critic from what it actually captured; the header pill is derived from the
  folder. If they disagree, the folder has contamination, not the critic.
- **`knowledge/` has two authorship channels that silently diverge.** The plugin's
  `knowledge/` is a hand-authored seed; `$TF_HOME/knowledge/` is the live base and the **only**
  copy agents read. `tf_seed_knowledge.py` is copy-if-absent (deliberately — a refresh may have
  improved a file), so **any seed edit after a domain's first seeding is invisible forever**.
  Editing the plugin seed does not change agent behaviour. Run
  `python3 scripts/tf_knowledge_drift.py` to find stranded seed content; it classifies each gap
  as `internal` (Theme Forge machinery a web refresh cannot regenerate — the seed is
  authoritative and a gap is a defect) or `external` (a claim about the world the refresh may
  have deliberately superseded).
- **Never deliver a knowledge edit with a whole-file operation. Apply the edit to each copy.**
  Edit the live file, then make the same edit to the seed so a fresh install inherits it — two
  small edits, never one copy. If the two have genuinely diverged, reconcile paragraph by
  paragraph (see the 2026-09-09 reconciliation of four domains), never by overwriting.
- **When reconciling, the two channels carry different kinds of truth — that is the merge rule.**
  The **seed wins** for Theme Forge internals a web search cannot regenerate: `tf_*.py`
  behaviour, required `theme.json` fields, plugin policy, licence attribution. The **live/refresh
  copy wins** for external facts: library versions, browser support, provider licence terms.
  This is the same split `tf_knowledge_drift.py` reports as `internal` vs `external`, so use its
  classification rather than judging paragraph by paragraph from scratch. The worst case found
  in the 2026-09-09 pass shows why the seed half matters: live `06-motion.md` had **zero**
  mentions of `motion_budget`, a field `theme.schema.json` *requires*, so theme-designer was
  being asked for a field whose policy it could not read — and the same file had lost the
  `emilkowalski/skills` MIT attribution that the plugin's `NOTICE` explicitly claims lives there.
- **Do not touch `FRESHNESS.json` after a reconciliation.** Its timestamps mean "last researched
  from the web", and a reconciliation adds no sources — writing a date there makes stale content
  look freshly researched. `tf_freshness.py --mark-refreshed <domain> --sources <n>` is for a
  real refresh pass only. (The asymmetry is also the cheapest way to see this whole problem: the
  plugin's own `FRESHNESS.json` shows every domain at `status: "seed"`, `refreshed: null`,
  `sources: 0`, while a populated live copy shows `"refreshed"` with real source counts.)
- **The `--force` hazard is about the *operation*, not the flag.** `tf_seed_knowledge.py --force`
  is merely the labelled version. Every one of these destroys the same researched content just
  as completely, and none of them warns you:

  | | |
  |---|---|
  | `tf_seed_knowledge.py --force` | the obvious one |
  | `Copy-Item seed\<domain>.md live\<domain>.md` | **the one that actually caused the incident** |
  | `cp seed/<domain>.md live/<domain>.md` | POSIX equivalent |
  | `robocopy` / `xcopy` over the live tree | bulk equivalent |
  | a `Write` of the seed's full contents to the live path | agent equivalent |
  | restoring the live file from the plugin as a "known good" copy | reasoning equivalent |

  The rule generalizes: **whenever two copies of a file exist and only one is live, any
  whole-file replacement of the live one is a data-loss event regardless of the verb.** It is
  the easier mistake to make precisely because it reads as "syncing one file" rather than as a
  delete. Ask "what does the destination contain that the source does not?" before any copy
  whose destination already exists.

  This happened on 2026-09-09: a one-paragraph addition to `06-motion.md` was "synced" seed→live
  with `Copy-Item`, silently destroying a 17-source research pass (library versions, release
  dates, browser-support status, the `## Refreshed` header and the whole changelog). The seed
  content survived, so a casual check looked fine — only the *researched* half was gone. There
  was no backup and no git, so it cost a full re-research to repair.

## `${CLAUDE_PLUGIN_ROOT}` is a hook-manifest variable, not an env var

Every `python3` call in an `agents/*.md` or `skills/**/SKILL.md` body must use the fallback
chain, exactly:

```
python3 "${CLAUDE_PLUGIN_ROOT:-${THEME_FORGE_ROOT:-plugins/theme-forge}}/scripts/tf_x.py" --json
```

- **Why, concretely.** `CLAUDE_PLUGIN_ROOT` is substituted by the harness in
  `hooks/hooks.json` (and MCP/LSP configs). It is **not exported into the Bash environment**
  for agent or skill bodies — verified against the live env, which carries only
  `CLAUDE_CODE_*`, `CLAUDE_EFFORT`, `CLAUDE_PID`. So a bare
  `"${CLAUDE_PLUGIN_ROOT}/scripts/x.py"` expands to `"/scripts/x.py"`; under Git Bash that
  resolves to `…\Git\scripts\x.py` and dies with `No such file or directory`. All 39 shell
  invocations shipped this way and never worked from an agent body in either install mode,
  which is why manual orchestration needed hand-substituted absolute paths.
- **Resolution order** is deliberate: harness variable (real plugin install) → `THEME_FORGE_ROOT`
  (custom or project-scoped layout) → `plugins/theme-forge` (running straight out of a clone,
  cwd at repo root). Verified in all three modes plus the old-form control.
- **`hooks/hooks.json` keeps the bare form.** That is the one context where substitution
  actually happens; adding shell `:-` syntax there would be substituted-then-not-expanded.
  Don't "make it consistent".
- **`allowed-tools:` needs both literals.** The permission matcher compares text, so a widened
  command with the old pattern alone produces needless prompts. Each skill declares
  `Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)` **and** the fallback-chain form.
- **Scripts already self-locate and must keep doing so.** `tf_paths.find_plugin_root()` walks up
  from `__file__` for `.claude-plugin/plugin.json`, so no script body depends on the variable.
  This matches Anthropic's own guidance in `superpowers`' porting doc: *"Use what your harness
  exports; the script re-derives the root itself."* Never make a script read
  `CLAUDE_PLUGIN_ROOT` directly.
- **Do not rewrite these to plain project-relative paths.** Installed plugins live under
  `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, so a bare
  `plugins/theme-forge/...` cannot resolve there — that change would trade installability for
  local convenience. The fallback chain is additive and keeps both working.

## Deciding a host is unreachable

- **`Invoke-WebRequest` failing does not mean the host is blocked. Retry through Python before
  believing it.** On this machine IWR fails against `fonts.googleapis.com` with *"The SSL
  connection could not be established"* — a .NET TLS quirk, not a firewall or proxy. Verified
  2026-09-09: `urllib.request.urlopen` fetched both the `css2` stylesheet and a 68 KB TTF from
  `fonts.gstatic.com` moments after IWR failed on the same URL from the same shell.
- **Why this matters more than it looks:** a false "host blocked" conclusion is sticky. It gets
  written into a run's notes, trips the `tf_assets.py` circuit breaker's reasoning, and sends
  the next session hunting for a proxy that was never the problem — while the actual fetch path
  the plugin uses works fine. No plugin code uses IWR; **all Theme Forge network access goes
  through `urllib`**, so an IWR result is never evidence about what the plugin can reach.
- Distinguish the two failure shapes before concluding anything: a **TLS/handshake** error is
  client-stack-specific and worth retrying through another client; a **timeout that burns the
  full duration** is the blackhole signature of a corporate filter and is real (see
  `_UNREACHABLE_STREAK` in `tf_assets.py`). Metadata and download hosts also differ
  (`api.polyhaven.com` vs `dl.polyhaven.org`), so one working and the other not is expected
  rather than contradictory.
## Sourced assets (`tf_assets.py`)

Verified sources and their terms live in `knowledge/14-asset-sources.md`. Re-verify by probing
endpoints, never by reading aggregator sites — that pass found a dead documented API, a live
undocumented one, and a license aggregators reported as MIT when it is proprietary.

- **An asset's license and its API's terms are different documents.** Poly Haven's assets are
  CC0 (*"You do not need to give credit"*) while its API ToS §2.5 requires a *"Powered by Poly
  Haven"* credit for content surfaced **via the live API**. Coverr requires a clickable logo;
  Pixabay requires showing users the source. So we **download and vendor** rather than hotlink —
  that leaves only the asset license in play. Never read "no attribution" off a license page
  alone.
- **Redistribution, not attribution, is the binding constraint.** Theme Forge exports zips.
  unDraw, DrawKit, Blush, LottieFiles, Coverr and Mixkit all forbid redistributing assets as a
  compilation, whatever their attribution stance. unDraw additionally forbids use *"for
  training, fine-tuning, or developing artificial intelligence, machine learning models"* —
  aimed squarely at a tool like this one. The safe set is **CC0 / MIT / OFL only**.
- **Three license tiers, not two.** `attribution_free` (CC0, Pexels) owes nothing;
  `notice_only` (MIT, OFL, Apache) must ship the license text but owes no visible credit and is
  allowed by default; `attribution_req` (CC-BY) is opt-in and is the only tier that populates
  `licensing.notices`. Conflating the last two would put credits in the gallery that nothing
  requires — and would make a genuinely obligation-free run look encumbered.
- **An unknown license is forbidden, not permitted.** `classify_license("")` and any
  unrecognised id return `forbidden`. An unrecognised license is precisely the case where nobody
  has checked what it obliges.
- **Share-alike is never allowed, not even opt-in.** CC-BY-SA and the Lottie Simple License
  oblige derivatives to carry the same terms, which Theme Forge cannot promise on the user's
  behalf — it would infect the exported theme.
- **Cap candidates and break on an unreachable host.** Poly Haven lists 858 textures; without
  `_MAX_CANDIDATES` a blocked download host is retried 858 times. A corporate filter
  *blackholes* rather than refuses, so each attempt burns the full timeout — one such loop ran
  for hours. Metadata and download hosts differ (`api.polyhaven.com` vs `dl.polyhaven.org`,
  `api.pexels.com` vs `videos.pexels.com`), so the API can answer perfectly while every download
  fails; treat an unreachable streak as one dead host and name it.
- **Enforce size ceilings during the read, not from `Content-Length`.** A missing or lying header
  would otherwise let a 400 MB HDRI into a gallery that must stay openable as one file.
- **Patterns are generated, not fetched, on purpose.** Every SVG-pattern service verified is
  browser-only (fffuel, Haikei, BGJar, SVGBackgrounds); Pattern Monster's `/api/patterns` is 404
  and its patterns live inside a Svelte app's internals. Hero Patterns is CC BY 4.0. Generating
  them is the better answer for this tier: zero bytes, recolored from the theme's own tokens,
  offline-native, no obligation.

## DiceBear specifics (`tf_avatars.py`)

- **Never read a style's license from `package.json`.** It reports `MIT` for every style because
  it describes Körner's *code*; each style wraps a third-party artist's work under that artist's
  terms. A naive read marks all 13 CC-BY styles as MIT. The authority is `meta.license`.
- **The license is in-band.** Every DiceBear SVG embeds Dublin Core RDF (`dcterms:license`,
  `dc:creator`, `dc:rights` — the last is a ready-made credit line), so
  `tf_assets.license_from_svg()` can read terms from the asset itself. **`removeMetadata` is
  therefore disabled in both `tf_optimize.py` configs** — svgo's `preset-default` strips
  `<metadata>` and would silently destroy the only in-band provenance. Also absent under
  `?format=png`. Absence of metadata is not CC0.
- **Pinned to `9.x`.** 10.x serves ~61 styles, ~30 new and unaudited. Four are blocked outright
  (`avataaars`, `avataaars-neutral`, `bottts`, `bottts-neutral`): upstream terms are the single
  line *"Free for personal and commercial use. 😇"*, never addressing redistribution, and both
  source domains serve expired TLS certificates so even that cannot be retrieved reliably.
- All six default `SLOT_STYLES` are CC0, so a default run owes nothing. `style_allowed()` gates
  before anything is written, so an edited slot table cannot smuggle a CC-BY or blocked style in.

## Custom properties are the quietest failure in the pipeline

A surface stylesheet reaching for a `--tf-*` name that nothing defines does not error, does not
warn, and does not visibly break. `var(--tf-nope)` in a non-shorthand property is discarded at
computed-value time and the property keeps its inherited or initial value — so a headline whose
`font-size` died renders at body size, which reads as a design decision rather than a bug. Every
instance was found late, by eye, usually from a design-critic screenshot.

- **`tf_gallery.py` is the only definition source, and surface CSS is written blind to it.** Six
  independently-authored surface-composer agents invent token names by convention, not from a
  canonical list. That is why the emitter carries dual spellings — `--tf-t-*`/`--tf-text-*`,
  `--tf-r-*`/`--tf-radius-*`, `--tf-dur-*`/`--tf-duration-*`, `--tf-<role>`/`--tf-color-<role>`,
  a dense `--tf-space-N` index, and a generic "any other declared key" pass. Each one was added
  after a real run shipped something silently unstyled. **Emitting an alias costs one
  declaration; omitting one costs a surface.** When in doubt, emit both spellings.
- **A theme's own declared `color.ramps` are emitted verbatim** (`declared_ramp_vars`), separate
  from the synthesized primary/accent ramps (`ramp_vars`). These were authored with real hex
  values in `theme.json` and for a long time emitted under no name at all, so `var(--tf-lime-200)`
  resolved to nothing while lime-200 sat in the theme file.
- **Run `python3 scripts/tf_tokens.py --all` after touching either the emitter or any surface
  CSS.** It derives the emitted set by *running* `theme_style_block()` rather than from a
  hand-kept list — a parallel list would drift from the generator, which is the exact bug it
  exists to catch. It is also wired into `tf_gallery.py`'s assembly and hard-aborts there: the
  check is a parser fact with no false-positive case, and as a warning it is precisely the kind
  of finding that accumulates unread. A confirmed audit of one six-theme run found **496** bare
  dead references across 10 of 12 surfaces, including one theme that used a `--tf-color-*` prefix
  throughout and therefore had essentially all of its color resolve to inherited values.
- **A surface declaring its own locals is correct, not a smell.** Anything with no source in
  `theme.json` (`--tf-press-travel`, `--tf-keyline`, a grid measure) *should* be declared on the
  surface's own root selector. The contract is that a name resolves somewhere, not that it comes
  from the theme. `var(--tf-x, 2px)` with a real fallback is likewise fine and never flagged.
- **`tf_tokens.py` imports `tf_gallery` lazily, inside `emitted_names()`.** `tf_gallery` imports
  `tf_tokens` at module scope to run the gate inline, so a module-level import in both directions
  is a cycle. Don't hoist it.
- **`--tf-shadow-<level>` is the web value; `--tf-elev-<level>` is the Android one.** Both are
  emitted per elevation level and they are not interchangeable: `--tf-shadow-*` is the theme's own
  `elevation.levels.<level>.css` verbatim, while `--tf-elev-*` is synthesized from that level's
  `android.elevation` to answer "what does this look like on Android". A surface reaching for
  `--tf-elev-*` on a web surface gets a neutral Material blur where the theme specified something
  else — confirmed live on a neobrutalist theme whose website and webapp used `--tf-elev-*`
  exclusively (70 references, zero to `--tf-shadow-*`), so its signature zero-blur hard offset
  never rendered on either surface. The name is the trap: `elev` reads like the generic word for
  elevation. Both names are load-bearing, so neither can be removed.
- **`android_shadow(0)` must return `none`.** `elevation: 0` is a deliberate statement that a
  theme's Android strategy is a border rather than a shadow (`{"elevation": 0, "borderWidth": 4}`
  is a real declaration). Clamping it up to the smallest blur both contradicted that and, because
  the clamp floored every level at the same value, collapsed a four-step 0/4/8/14px ladder into
  four identical soft blurs.
- **A token's value is not always one number — emit `css` and fall back to `px`.** `border-radius`
  takes up to eight values with `/` separating the two axes, which is how a theme expresses an
  elliptical or hand-drawn corner. Reading only `radius.<key>.px` flattened those to a plain
  rounded rectangle: a hand-drawn theme whose `radius.wobble` is
  `13px 5px 14px 6px / 6px 13px 5px 12px` — its entire signature shape — reached every surface as
  `12px`. `px` stays the fallback and is still what the React Native side reads, since RN's
  `borderRadius` genuinely is a single number. Check the same trap before adding any new token
  family where the CSS grammar is richer than one scalar.

## Never compare an unconstrained schema string with `==`

`typography.<role>.source` is `{"type": "string"}` in `theme.schema.json` — no enum, so every
value a theme-designer writes is schema-valid. `font_import()` compared it with
`== "google"`, so every theme that wrote `"google-fonts"` had its faces silently dropped from
the gallery's single Google Fonts `@import`.

- **Confirmed live, and it invalidated a whole critique pass.** In one six-theme run, four
  themes wrote `"google-fonts"` and two wrote `"google"`: the gallery imported 7 families
  instead of 14, and **four of six themes rendered entirely in Helvetica/Arial fallback**.
  Nothing errored — the `@import` was well-formed and every `css_fallback` stack did its job.
  A `design-critic` pass then praised *"112px Big Shoulders Display caps"* and *"the only serif
  body in the set"* while looking at a fallback sans, so the typographic half of that critique
  had to be redone.
- `_is_google_source()` now normalizes and matches on substring, so `"google"`,
  `"google-fonts"`, `"Google Fonts"` and `"google_fonts"` all work.
- **Report the skips.** `font_import()` writes a `NOTE` to stderr naming every declared family
  it did not import and the `source` value that caused it. A legitimately-local face appears
  there too, which is fine — the point is that "declared but not loaded" is never silent again.
- The general rule: when the schema leaves a field open, the consumer must not narrow it back
  down to one spelling. Same defect as the `--tf-color-*` prefix and the Rule 15 `"input"`
  substring — a convention assumed by a reader of data that never promised to follow it.
- **Verify a font by measuring it, not by `document.fonts.check()`.** That API takes a full
  font shorthand and defaults to weight 400, so it returns `false` for a family imported only
  at 500-900 (Gabarito here) even though the face is loaded and rendering. Canvas
  `measureText` is also unreliable for this. Measure an `inline-block` span against
  `monospace`/`sans-serif` generics instead.

## A HIGH finding must block something, or it is advisory with extra steps

`tf_slop.py` used to exit 0 no matter what it found, and its top-level summary reported only
`total_findings` — one number mixing 600 advisories with a blocker. A HIGH severity hard-stop
was therefore discoverable only by opening each theme's own `slop.json`, and nothing downstream
refused to proceed. The same HIGH finding could survive run after run while every command
reported success.

- **`tf_slop.py` now exits 1 when any hard-stop exists** and reports `total_hard_stops`,
  `hard_stop_rules` and `themes_with_hard_stops` at the top level. `--no-fail` inspects without
  failing the exit code.
- **`tf_gallery.py` refuses to assemble over a current hard-stop** (Gate B abort, mirroring the
  existing Gate A abort), overridable with `run.json["gate_slop_override"]=true`.
- **The staleness guard compares `preview.html` against the surface files — not `slop.json`
  against them.** The dependency chain is surfaces → preview.html → slop.json, and the question
  is whether the preview tf_slop *judged* still reflects the surfaces. Getting this wrong
  deadlocks the fix→rebuild cycle: after a fix, tf_slop rewrites `slop.json` (making it the
  newest of the three) while still reading the stale preview it was handed, so a
  slop.json-vs-surfaces comparison reports "current" for a finding that no longer exists in the
  source, and the gallery then refuses to regenerate the very preview that would clear it. Found
  by injecting a real `scale(0)`, fixing it, and watching the first version of this guard
  deadlock.

## A gate must not fire on a comment, or on a naming convention

Two `tf_slop.py` hard-stops in one run were both the gate's fault, not the theme's. Neither was
a judgment call — each flagged code that was demonstrably correct, and "fixing" the surface would
have meant deleting an accurate comment or breaking an accessible control.

- **Strip comments before any rule scans the document.** `_stdlib_check` now calls
  `_strip_comments()` (HTML comments first, then CSS, so a `<!-- /* */ -->` nest cannot leave a
  dangling fragment) before dispatching to any rule. Three themes hard-stopped on
  `scale-zero-entrance` whose only occurrence of `scale(0)` was a comment reading *"Never from
  scale(0): nothing in the real world appears from nothing"* — the rule fired on the sentence
  asserting the rule was obeyed. `tf_content.py`'s document-wrapper check already carried this
  fix for the same reason; keep them consistent. This is also right for the copy-scanning rules
  (em-dash, all-caps, buzzwords): comment prose is not user-visible copy and must not be judged
  as copy.
- **Never gate an exemption on what a class is NAMED.** Rule 15's visually-hidden-input escape
  required the selector to contain the literal substring `input`. Two themes abbreviated to
  `-in` (`.dp-chip-in`, `.agecell-in`) and hard-stopped, despite being genuine `<input>` elements
  stretched over their own styled label — the correct accessible pattern, where the input must
  stay hit-testable (so `pointer-events:none` is wrong) and its opacity never returns to 1 by
  design (so no companion-`opacity:1` escape applies either). The fix asks the markup whether
  the class actually sits on an `<input>`/`<select>`/`<textarea>` rather than guessing from its
  name. Prefer ground truth in the document over a convention when one is available.
- **A gate defect does not consume `regen_budget`.** These five hard-stops had one correct fix
  each, in the gate. Spending a regeneration pool on them would have burned budget to make
  correct code look different. Confirm a hard-stop is real — read the cited line — before
  treating it as a theme failure.

## `@scope` silently kills ancestor selectors on the mobile surface

`tf_gallery.py` wraps mobile CSS in `@scope ([data-tf-theme="N"] .screen-pane)`, and inside an
`@scope` block every selector that does not already name `:scope` is implicitly prefixed with
`:scope `. The device frame is an **ancestor** of that scope root
(`.device.ios > … > .screens > .screen-pane`), so the `.device.ios .card` form that
`agents/surface-composer.md` asks every composer to write for native honesty compiles to
`:scope .device.ios .card` and matches nothing.

- **The failure is invisible in exactly the usual way**: the CSS parses, is well-formed, and is
  inert, so iOS and Android render identically while every gate reports clean. In one six-theme
  run, three themes shipped platform rules that matched nothing; it was caught only because three
  agents independently rendered the surface in a real browser.
- **Two forms work**, both verified: `.card:where(.device.android *)` (subject in scope, ancestor
  condition inside `:where()`) and `.device.android :scope .card` (names `:scope`, so it is not
  re-prefixed). Prefer the first. Converting drops specificity — `:where()` contributes zero — so
  a rule that previously outranked a base rule may need source order to keep winning.
- **`tf_tokens.py` reports these** (`tokens.unmatchable_scoped_selector`), but unlike the dead-
  property check it does **not** hard-abort assembly: an inert rule that has a working twin is
  harmless dead code rather than broken output, and the check cannot tell the two apart.
- **Do not "fix" this by widening the scope root** to include `.device`. Mobile CSS is scoped to
  `.screen-pane` precisely so one theme's stylesheet cannot restyle the shared device chrome.

- Run `python3 scripts/tf_tokens.py --selftest` after touching its matcher. The regexes are
  load-bearing in a non-obvious way: comments are stripped *before* scanning, so a commented-out
  definition must not rescue a real use, and a token named only inside an explanatory `/* ... */`
  counts as neither a definition nor a use.
- Run `python3 scripts/tf_color.py --selftest` after touching the color engine.
- Run `python3 scripts/tf_assets.py --selftest` after touching the license policy, the
  provenance shape, or the pattern builders. It needs no network.
- Run `python3 scripts/tf_knowledge_drift.py --selftest` after touching its matcher. Its two
  calibration constants are load-bearing: matching is by *distinctive token* (code spans and
  identifiers), never by prose, because a refresh rewrites wording freely — and `_ABSENT_RATIO`
  is applied with **no absolute floor**, since a paragraph whose single identifier is missing has
  lost all of its distinctive content.
- Run `python3 scripts/tf_raster.py --selftest` after touching a rasterizer command builder
  or the ICO packer. It renders known square/wide SVGs through *every* detected rasterizer and
  asserts exact output dimensions, then packs and re-parses an ICO from raw bytes.
  **Expect several minutes** — the browser legs launch Chromium twice via npx and dominate the
  runtime. It is not hung. Run it with `python3 -u ... > log 2>&1` and tail the log if you want
  progress: a shell that buffers redirected output shows nothing until the process exits.
- **`.ico` needs no external tool.** `tf_raster.py --ico` builds the container in stdlib
  (`build_ico`), embedding PNGs the ladder produced. Don't reintroduce an ImageMagick
  dependency for favicons. ICO stores each dimension in one byte (0 = 256), so 256px per side
  is a hard format limit — reject oversize input, never truncate it into a bogus 0.
- **tf_slop.py** wraps `impeccable` (59 rules) with a 14-rule stdlib fallback. It calls the
  binary directly (`impeccable detect`) rather than via `npx impeccable` to avoid npm registry
  network latency. Do not change `_impeccable_argv()` to use npx unconditionally.

## Shelling out to node-backed tools

Every one of these fails *silently* — the callers all have graceful fallbacks, so a
misconfigured tool is indistinguishable from a missing one until you check the output.

- **Resolve the executable with `shutil.which`, never a bare name.** On Windows the file is
  `npx.CMD`, and `subprocess.run(["npx", ...])` raises `FileNotFoundError`. (`node` is safe —
  `node.EXE` resolves natively.) Resolve it with `which`, don't *probe* for it: `_npx()` used
  to run `npx --version` at import time under the default 5 s timeout, but npx cold start costs
  4-11 s here, so npx was intermittently reported absent — which cascades into svgo, resvg-js,
  sharp-cli and playwright all being reported missing.
- **Capture subprocess output to a temp FILE, not a pipe, whenever the child may spawn.**
  `subprocess.run(timeout=)` kills only the direct child on expiry, then blocks in
  `communicate()` draining pipes a surviving grandchild still holds open — no EOF, no timeout,
  forever. A capability probe hung 32 minutes at 0.3 s CPU this way. Use
  `tempfile.TemporaryFile()` + `Popen.wait(timeout=)`, pass `stdin=DEVNULL`, and reap the tree
  with `taskkill /F /T /PID` on Windows (`proc.kill()` leaves grandchildren running — one
  timeout stranded eight node/chrome processes).
- **node does not search npm's global root.** `require('pkg')` finds a global install only when
  `NODE_PATH` points there, so a `node -e "require(...)"` probe reports a globally installed
  library as absent. Inject it: `_global_node_modules()` / `_node_env()` in `tf_tools.py` and
  `tf_outline.py`. Do not derive the root from `shutil.which("npm")` on Windows — npm.cmd lives
  in the Node install dir while the global prefix is `%APPDATA%\npm`, so that guess returns
  node's own bundled modules. The helper is deliberately duplicated rather than shared: it is a
  self-contained pure function, and a worker script should not import the capability-cache
  module to get at a path lookup.
- **Budget for cold start.** npx takes 7-9 s before the tool begins work. Capability probes
  need `timeout=30`; actual work needs 120 s+. A 5 s timeout reports every node tool as absent.
- **Verify flags against the installed CLI, not from memory.** `@resvg/resvg-js-cli` uses
  `--fit-width`/`--fit-height` (not `--width`), and `sharp-cli` takes dimensions as positionals
  on a `resize` subcommand (not `--width`). Both reject the wrong flag with exit 1, which just
  looks like "this rasterizer isn't working" and falls through the ladder.
- **svgo configs must be `.mjs`.** svgo v4 loads config as an ES module; a `.json` config dies
  on Node 22+ with `ERR_IMPORT_ATTRIBUTE_MISSING`. Emit `export default {...};`.
- **Always pass `prefixIds` an explicit `prefix`.** Its default is the file name alone, so every
  theme's `pattern.svg` mints the same `pattern_svg__a` — a cross-theme collision no
  single-file optimizer can detect. `tf_optimize.py` uses `<stem>-<theme-slug>` (stem first,
  because a theme slug's leading digit is illegal in a CSS identifier). Don't drop the param
  back to a bare `"prefixIds"` string.
- **A fallback must preserve the caller's intent, not just produce a file.** The Playwright
  rasterizer defaulted a missing height to 800 px, so every asset came out `<width>x800` —
  correct-looking, valid PNGs, silently wrong geometry. Derive the height from the viewBox.
- **opentype.js v2: use `parse()`, never `loadSync()`.** v2 made `loadSync` return `undefined`
  rather than throw, so the only symptom is a `TypeError` one line later — which `tf_outline.py`
  turned into a silent `<text>` fallback indistinguishable from "library not installed".
  `opentype.parse(fs.readFileSync(p))` is public API in both v1 and v2.
- **Validate glyph path data for `NaN` before writing it.** opentype.js v2 emits `NaN`
  coordinates for some glyphs (Fredoka, DM Serif Display, Syne). An SVG parser abandons the
  path at the bad token, dropping that glyph *and every later one*, leaving a valid file —
  Fredoka rendered "Pa" out of "Palmline". `_usable_path()` rejects nan/inf so the ladder falls
  through to the Python parser.
- **Composite glyphs are not optional.** A `numberOfContours < 0` glyph is built from
  components; `i`, `j` and every accented letter use this. Skipping them drops the letter
  silently (Bricolage Grotesque rendered "Palml ne"). `_composite_paths()` expands the
  translation form, and its glyph resolver must return `None` when `loca[gid] == loca[gid+1]`
  or the offset lands on the *next* glyph and draws the wrong shape.
- **Fonts live in `$TF_HOME/fonts/`, searched before system dirs.** Themes pick Google Fonts,
  which are never installed system-wide, so a system-only search always failed. The directory
  sits beside `current/` so the generate wipe does not discard it. Fetch **TTF, not woff2**
  (opentype.js cannot parse woff2) — the `css2` endpoint returns TTF to urllib's default
  User-Agent and woff2 to a browser UA.
- **These three bugs all passed every structural check** — file present, non-empty, has
  `<path>`, no `<text>`, right `aria-label`, plausible `viewBox`. Only rasterizing and looking
  at the image caught them. Render brand assets and *view* them before calling the job done.
