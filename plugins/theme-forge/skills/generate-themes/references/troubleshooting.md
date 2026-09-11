# Troubleshooting

## A script exits non-zero

Every script prints `{"ok": false, "error": "..."}` on an expected failure (exit 1) and a
traceback to stderr on an unexpected one (exit 2). Read stdout JSON first.

- **`tf_contrast.py` exits 1.** A theme has a failing pair. The JSON `failures[].suggestion`
  gives the nearest passing hex — hand that back to the theme-designer and re-run. Don't ship a
  theme whose `a11y.json` isn't `ok`.
- **`tf_native.py` exits 1.** A value React Native can't consume. `violations[].rule` names the
  class (`native-color-unresolved`, `dimension-string-with-unit`, `lineheight-multiplier`,
  `letterspacing-em`, `fontweight-without-family`, `shadow-css-string`, `android-shadow-color`).
  This is a "send it back to the designer once" event, not "abort".
- **`tf_reset.py` refuses.** It only deletes under `TF_HOME`. If it refused, the target wasn't
  under `TF_HOME` — that's the safety guard working, not a bug.

## No web access

`tf_freshness.py` still returns a recommendation, but the researchers will fail. Continue on the
seed and tell the user plainly (see step 2). The seed is current as of its `seed_version` and
still produces good themes.

## The browser didn't open

`tf_open.py` never fails the run. Print the absolute path from its JSON and tell the user to
open it manually. On WSL it tries `wslview` then `explorer.exe`; elsewhere `webbrowser`, then
the platform opener.

## Subagents returned huge responses

They shouldn't — each is instructed to return only a path and a three-sentence summary. If one
dumped CSS or SVG, don't paste it onward; just record its directory path in `run.json`.

## Themes came out too similar

That's a slot-assignment failure. The `design-critic` flags pairs within 20° hue with matching
type stacks and radii. Regenerate the flagged one with a more committed direction — the fix is
almost always "the designer hedged toward safe blue SaaS instead of committing to its slot."

## The gallery is over 2 MB

The SVGs are too detailed. Simplify brand marks and the empty-state illustration; keep
`feTurbulence numOctaves` ≤ 3. The chrome and surface markup are fixed-size; size growth is
always the theme assets.

## Native themes look identical on device but distinct on web

Their differentiation lived in CSS functions that got stripped in the native resolution. This
is exactly the `design-critic` cross-platform-integrity check. The fix is a designed native
expression (a border where the shadow was, a solid fallback where the glass was), not a
translation.
