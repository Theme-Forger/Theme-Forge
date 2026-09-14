#!/usr/bin/env python3
"""tf_gallery.py -- assemble the self-contained gallery.html and per-theme preview.html.

Everything is inlined: CSS, per-theme variable blocks, surface markup, and
brand SVGs (as base64 data URIs). No iframe, no CDN. The only network reference
is a single Google Fonts @import, which fails gracefully to full system fallback
stacks. Renders correctly from file:// with the network off.

    python3 tf_gallery.py --json [--home-run]

Reads $TF_HOME/current/run.json and each theme, writes current/gallery.html and
each theme's preview.html.
"""
from __future__ import annotations

import base64
import html
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin dir
import tf_paths
import tf_color
import tf_content
import tf_tokens

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def load_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def read(p: Path, default=""):
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return default


def inline_svg(p: Path) -> str:
    text = read(p)
    if not text:
        return ""
    text = re.sub(r'<\?xml[^?]*\?>', '', text).strip()
    text = re.sub(r'<!DOCTYPE\s[^>]*>', '', text).strip()
    return text


def gethex(v, fallback="#000000"):
    if isinstance(v, dict):
        return v.get("hex", fallback)
    if isinstance(v, str):
        return v
    return fallback


def getcss(v, fallback=""):
    if isinstance(v, dict):
        return v.get("css") or v.get("hex") or fallback
    if isinstance(v, str):
        return v
    return fallback


def svg_data_uri(svg: str) -> str:
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return "data:image/svg+xml;base64," + b64


def pick_mark_color(theme, mode):
    c = theme.get("color", {}).get(mode, {})
    bg = gethex(c.get("background"), "#ffffff")
    primary = gethex(c.get("primary"), "#000000")
    text = gethex(c.get("text"), "#000000")
    try:
        if tf_color.wcag_contrast(primary, bg) >= 3.0:
            return primary
    except Exception:
        pass
    return text


def logo_uri(theme_dir: Path, theme, mode):
    svg = read(theme_dir / "brand" / "logomark.svg")
    if not svg.strip():
        # generic fallback mark
        col = pick_mark_color(theme, mode)
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
               '<rect x="4" y="4" width="24" height="24" rx="7" fill="none" stroke="%s" stroke-width="3"/>'
               '<circle cx="16" cy="16" r="5" fill="%s"/></svg>' % (col, col))
    else:
        col = pick_mark_color(theme, mode)
        svg = svg.replace("currentColor", col)
    return svg_data_uri(svg)


def android_shadow(elev):
    """Neutral, non-offset, non-colored blurred shadow approximating Android elevation.

    `elevation: 0` means *no shadow*, and must return `none` rather than the
    smallest possible blur. Several themes deliberately declare 0 on every
    level because their Android strategy is a border, not a shadow (a
    neobrutalist theme states this outright: `{"elevation": 0,
    "borderWidth": 4}`). Clamping 0 up to a faint grey blur silently
    contradicted the theme's own stated platform decision -- and because the
    clamp floored every level at the same value, a four-step 0/4/8/14px depth
    ladder collapsed into four identical soft blurs.
    """
    try:
        e = int(elev)
    except Exception:
        e = 2
    if e <= 0:
        return "none"
    blur = max(2, int(round(e * 1.4)))
    y = max(1, int(round(e * 0.5)))
    a1 = min(0.30, 0.12 + e * 0.012)
    return "0 %dpx %dpx rgba(0,0,0,%.2f), 0 1px %dpx rgba(0,0,0,0.10)" % (y, blur, a1, max(1, e // 2))


# ---------------------------------------------------------------------------
# per-theme CSS variable block
# ---------------------------------------------------------------------------

SEM_KEYS = ["background", "surface", "surface-raised", "text", "text-muted", "border",
            "primary", "on-primary", "accent", "on-accent", "focus-ring", "overlay"]

VAR_MAP = {"background": "--tf-bg", "surface": "--tf-surface", "surface-raised": "--tf-surface-raised",
           "text": "--tf-text", "text-muted": "--tf-text-muted", "border": "--tf-border",
           "primary": "--tf-primary", "on-primary": "--tf-on-primary", "accent": "--tf-accent",
           "on-accent": "--tf-on-accent", "focus-ring": "--tf-focus", "overlay": "--tf-overlay"}


def _emit_role(out, seen, key, val):
    """Emit one color role under every spelling surface CSS actually reaches for.

    Three spellings, all pointing at the same value:
      1. the compact VAR_MAP name where one exists (--tf-bg, --tf-focus)
      2. the schema key verbatim            (--tf-background, --tf-focus-ring)
      3. a --tf-color-<key> prefixed form   (--tf-color-background, --tf-color-text)

    (1) alone was the whole emitted set, and it silently broke any surface that
    reached for the other two -- an undefined var() in a non-shorthand property
    computes to the inherited/unset value, so a dead reference renders as a
    plausible-looking page rather than an error. Confirmed live across a real
    six-theme run: 22 bare --tf-background references (three themes) and 148
    bare --tf-color-* references (one theme whose surfaces used that prefix
    throughout) all resolved to nothing, which is how a theme ships with its
    body text at the inherited color instead of its own.

    This is the same dual-spelling remedy already applied to the type scale
    (--tf-t-* / --tf-text-*), radius (--tf-r-* / --tf-radius-*) and motion
    (--tf-dur-* / --tf-duration-*) tokens below -- extended to color, which was
    the one family still emitted under a single name. Emitting an alias costs
    one CSS declaration; omitting one costs a silently unstyled surface.
    """
    for name in (VAR_MAP.get(key), "--tf-%s" % key, "--tf-color-%s" % key):
        if name and name not in seen:
            seen.add(name)
            out.append("  %s: %s;" % (name, val))


def sem_vars(colors):
    out = []
    seen = set()
    emitted = set()
    for k in SEM_KEYS:
        v = colors.get(k)
        if v is None:
            continue
        if k == "overlay":
            val = (v.get("rgba") if isinstance(v, dict) else None) or gethex(v)
        else:
            val = gethex(v)
        _emit_role(out, seen, k, val)
        emitted.add(k)
    # Any OTHER key a theme actually declared (surface-sunken, primary-hover,
    # primary-active, accent-hover, ...) that isn't in the fixed SEM_KEYS list
    # above -- confirmed live: these have real declared hex values in
    # theme.json and real consumers in surface CSS, but silently resolved to
    # nothing because SEM_KEYS was a curated subset, not the actual key set.
    # Emitted generically as --tf-<key> (hyphens preserved) rather than
    # requiring every theme-specific role name to be hand-added to VAR_MAP.
    for k, v in colors.items():
        if k in emitted or k == "overlay":
            continue
        val = gethex(v) if not isinstance(v, str) else v
        if val:
            _emit_role(out, seen, k, val)
    return "\n".join(out)


def ramp_vars(colors):
    """Numbered tint/shade ramps (--tf-primary-200, --tf-accent-700, ...) for
    the two roles surface-composer output most often invents a ramp against.
    No such ramp exists anywhere in theme.json -- these were pure surface-
    composer invention, resolving to nothing at all before this. Derived from
    each theme's own base hue/chroma via tf_color.ramp() rather than guessed
    at with fixed values, so the ramp stays true to that theme's specific
    color, not a generic tint ladder."""
    out = []
    for role in ("primary", "accent"):
        base = colors.get(role)
        base_hex = gethex(base)
        if not base_hex:
            continue
        try:
            oklch = tf_color.hex_to_oklch(base_hex)
        except (ValueError, IndexError, TypeError):
            continue
        for step, data in tf_color.ramp(oklch).items():
            out.append("  --tf-%s-%s: %s;" % (role, step, data["hex"]))
        # "deep"/"hover"/"active" as an alias onto the ramp's darker end --
        # confirmed used in real surface CSS with no numbered equivalent.
        out.append("  --tf-%s-deep: %s;" % (role, tf_color.ramp(oklch).get("800", {}).get("hex", base_hex)))
    return "\n".join(out)


def _natural_court(theme):
    """Which appearance shows this theme as its designer intended it.

    A "dark-court" theme writes its dark aesthetic into `color.light` (that key
    names the schema slot, not the look), so the court cannot be read off the
    key name -- only off which resolution is objectively darker. Returns the
    value the `data-tf-appear` attribute should carry to render the theme's
    primary identity rather than its alternative.
    """
    color = theme.get("color", {})
    return ("dark" if _bg_oklch_l(color.get("light", {}))
            < _bg_oklch_l(color.get("dark", {})) else "light")


def declared_ramp_vars(color):
    """The theme's OWN named ramps from theme.json `color.ramps`, verbatim.

    ramp_vars() above *synthesizes* a ramp for the two generic roles (primary,
    accent). This emits the ramps a theme-designer actually authored and named
    -- jade/coral/plum/mist, lime/cobalt/ink/paper, ochre, marigold, pine --
    which were declared with real hex values in theme.json and then never
    emitted under any name at all. Surface CSS referencing `var(--tf-lime-200)`
    therefore resolved to nothing, despite lime-200 being a real, deliberately
    chosen value sitting in that theme's own file.

    Ramps are mode-independent (lime-200 is the same swatch in either court),
    so this is emitted once in the base block rather than per appearance.
    """
    out = []
    for name, steps in (color.get("ramps") or {}).items():
        if not isinstance(steps, dict):
            continue
        for step, v in steps.items():
            val = gethex(v) if not isinstance(v, str) else v
            if val:
                out.append("  --tf-%s-%s: %s;" % (name, step, val))
    return "\n".join(out)


def _bg_oklch_l(role_map: dict) -> float:
    """OKLCH lightness of a color.<light|dark>.background hex, for ordering
    the two blocks by how dark they actually are -- not by which schema key
    they happen to sit under. A "dark-court" theme deliberately writes its
    dark aesthetic into color.light (see theme-designer.md's own documented
    convention: "dark-court themes ... must write their dark aesthetic into
    color.light.*"), so color.light is not reliably "the lighter one" and
    color.dark is not reliably "the darker one" -- for roughly a third of a
    real six-theme set, it's the opposite. Defaults to 1.0 (treat as light)
    on anything unparseable so a bad hex fails toward the safer assumption."""
    hexv = gethex((role_map or {}).get("background"), "")
    try:
        return tf_color.hex_to_oklch(hexv)[0]
    except (ValueError, IndexError, TypeError):
        return 1.0


def theme_style_block(idx, theme, theme_dir):
    color = theme.get("color", {})
    typ = theme.get("typography", {})
    radius = theme.get("radius", {})
    elev = theme.get("elevation", {})
    motion = theme.get("motion", {})

    light = color.get("light", {})
    dark = color.get("dark", {})
    semantic = color.get("semantic", {})

    # The gallery's Light/Dark toggle must mean the same thing for every
    # theme: pressing Dark shows the objectively darker of this theme's two
    # resolutions, pressing Light shows the objectively lighter one --
    # regardless of which schema key (color.light vs color.dark) that
    # happens to be. Without this, a dark-court theme (whose color.light IS
    # its dark aesthetic by design) turns LIGHTER when Dark is pressed,
    # confirmed live: Load Line and Surge Block both did exactly this before
    # this fix, going from a near-black background to a near-white one on
    # the "Dark" click.
    if _bg_oklch_l(light) >= _bg_oklch_l(dark):
        lighter, lighter_mode, darker, darker_mode = light, "light", dark, "dark"
    else:
        lighter, lighter_mode, darker, darker_mode = dark, "dark", light, "light"

    lines = ['[data-tf-theme="%d"] {' % idx]
    lines.append(sem_vars(lighter))
    lines.append(ramp_vars(lighter))
    # After ramp_vars() so a theme's own authored ramp wins over the
    # synthesized primary/accent one if the two ever share a name.
    lines.append(declared_ramp_vars(color))
    # semantic status colors (mode-independent) -- emitted under the same
    # --tf-<key> / --tf-color-<key> pair as every other color role. These sit
    # outside sem_vars() (they come from color.semantic, not the per-mode role
    # map), so they were the one color family the prefixed alias never reached.
    for k in ("success", "warning", "danger", "info"):
        if k in semantic:
            val = gethex(semantic[k])
            lines.append("  --tf-%s: %s;" % (k, val))
            lines.append("  --tf-color-%s: %s;" % (k, val))
    # radius -- emitted under both --tf-r-<key> and --tf-radius-<key>, same
    # split-convention issue as the type scale and motion tokens above.
    #
    # `css` wins over `px` when the two differ. A radius is not always one
    # number: `border-radius` takes up to eight values with a `/` separating
    # the horizontal and vertical axes, which is how a theme expresses an
    # elliptical or hand-drawn corner. Reading only `px` silently flattened
    # those to a plain rounded rectangle -- confirmed live on a hand-drawn
    # theme whose `radius.wobble` is `13px 5px 14px 6px / 6px 13px 5px 12px`
    # (its entire signature shape) and which reached every surface as `12px`.
    # `px` remains the fallback and is still what the native/RN side reads,
    # since React Native's borderRadius genuinely is a single number.
    for k, v in radius.items():
        if isinstance(v, dict):
            val = v.get("css") or ("%spx" % v.get("px"))
        else:
            val = "%spx" % v
        lines.append("  --tf-r-%s: %s;" % (k, val))
        lines.append("  --tf-radius-%s: %s;" % (k, val))
    # spacing scale: theme.json's space.scale is a list of unit multiples (not
    # raw px) -- --tf-space-N resolves to N * space.unit, matching the naming
    # convention surface-composer output already assumes bare (no fallback)
    # wherever a theme happened to also hand-write this block into its own
    # web/theme.css. That file is never embedded into the gallery/preview
    # (only this curated block is), so any surface CSS relying on
    # var(--tf-space-N) with no literal fallback silently collapsed to 0/
    # "normal" until this block existed at all -- confirmed by a design-critic
    # pass catching a theme's nav items rendering with zero gap.
    space = theme.get("space", {})
    unit = space.get("unit")
    scale = space.get("scale")
    if isinstance(unit, (int, float)) and isinstance(scale, list):
        for n in scale:
            if isinstance(n, (int, float)):
                lines.append("  --tf-space-%s: %spx;" % (int(n), n * unit))
    # Dense Tailwind-style index range (--tf-space-1 through --tf-space-32,
    # meaning N * space.unit) IN ADDITION to the theme's own sparse declared
    # scale above. theme.json's scale array is a curated, irregular set of
    # steps a theme-designer actually chose (e.g. hot-swap: 0,4,8,12,16,20,24,
    # 32,40,56,72,96,128) -- but six independently-authored surface-composer
    # agents, with no canonical scale list handed to them, reached for the
    # much more common convention of a dense sequential index (--tf-space-1,
    # -2, -3, -5, -6, -7, -9, -10, -11 all confirmed in real surface CSS,
    # none of which exist in most themes' own sparse array). Any index a
    # theme's own array happens to also declare naturally gets an identical
    # duplicate value here -- harmless, last declaration wins with the same
    # number either way.
    if isinstance(unit, (int, float)):
        for n in range(0, 33):
            lines.append("  --tf-space-%d: %spx;" % (n, n * unit))
    # fonts (always full fallback stacks)
    for role in ("display", "body", "mono"):
        r = typ.get(role, {})
        fam = r.get("family", "")
        fb = r.get("css_fallback", "sans-serif")
        lines.append('  --tf-font-%s: "%s", %s;' % (role, fam, fb))
    # type scale (px, predictable inside scaled compare cells) -- emitted under
    # BOTH --tf-t-<key> and --tf-text-<key>. Surface-composer agents split
    # roughly evenly between the two spellings with no canonical list handed
    # to them (the same split seen in the duration/easing tokens below).
    # Confirmed load-bearing live: one theme happened to use --tf-t-* (the
    # only form previously emitted) and was the only one in a six-theme set
    # whose headline hierarchy actually rendered -- the other five, all using
    # --tf-text-*, had every heading silently collapse to inherited body-text
    # size, because an undefined var() in a non-shorthand property computes
    # to the property's unset/inherited value, not a visible failure.
    for name, step in (typ.get("scale", {}).get("steps", {}) or {}).items():
        px = step.get("px") if isinstance(step, dict) else step
        if isinstance(px, (int, float)) and px < 12:
            px = 12
        lines.append("  --tf-t-%s: %spx;" % (name, px))
        lines.append("  --tf-text-%s: %spx;" % (name, px))
    # line-height ("leading") and letter-spacing ("tracking") -- previously
    # not emitted at all under any name, so every themed override of the
    # browser default (tighter tracking on display type, taller leading on
    # body copy) silently no-opped regardless of which name a surface used.
    for name, step in (typ.get("leading", {}) or {}).items():
        css = step.get("css") if isinstance(step, dict) else step
        if isinstance(css, (int, float, str)):
            lines.append("  --tf-leading-%s: %s;" % (name, css))
    for name, step in (typ.get("tracking", {}) or {}).items():
        css = step.get("css") if isinstance(step, dict) else step
        if isinstance(css, (int, float, str)):
            lines.append("  --tf-tracking-%s: %s;" % (name, css))
            lines.append("  --tf-track-%s: %s;" % (name, css))
    # elevation: web/iOS shadows + android neutral elevation
    levels = elev.get("levels", {})
    for n, lvl in levels.items():
        css = lvl.get("css") if isinstance(lvl, dict) else None
        if css:
            lines.append("  --tf-shadow-%s: %s;" % (n, css))
        android = (lvl.get("android") if isinstance(lvl, dict) else {}) or {}
        lines.append("  --tf-elev-%s: %s;" % (n, android_shadow(android.get("elevation", 2))))
    # motion -- emit EVERY key theme-designer actually put in motion.duration/
    # motion.easing, under both --tf-dur-<key> and --tf-duration-<key> (surface-
    # composer agents split roughly evenly between the two spellings with no
    # canonical list to draw from) and --tf-ease-<key>. A theme's own semantic
    # names (motion.duration.layer, motion.easing.ink, motion.easing.reticle,
    # ...) are real per-theme vocabulary invented to match that theme's motion
    # thesis, not typos -- hardcoding only "fast"/"normal"/"standard" here left
    # every other named token undefined, which silently invalidates the whole
    # animation/transition shorthand referencing it (permanently-invisible
    # content was one observed symptom; a transition that never fires is the
    # more common, quieter one). Iterating the actual keys is the only way to
    # cover six independently-authored vocabularies without guessing.
    dur = motion.get("duration", {})
    for key, val in dur.items():
        if isinstance(val, (int, float)):
            lines.append("  --tf-dur-%s: %sms;" % (key, val))
            lines.append("  --tf-duration-%s: %sms;" % (key, val))
    if "fast" not in dur:
        lines.append("  --tf-dur-fast: 150ms;")
        lines.append("  --tf-duration-fast: 150ms;")
    if "normal" not in dur:
        lines.append("  --tf-dur-normal: 240ms;")
        lines.append("  --tf-duration-normal: 240ms;")
    lines.append("  --tf-stagger: 60ms;")
    easing = motion.get("easing", {})
    for key, val in easing.items():
        css = val.get("css") if isinstance(val, dict) else val if isinstance(val, str) else None
        if css:
            lines.append("  --tf-ease-%s: %s;" % (key, css))
    std = easing.get("standard", {})
    std_css = (std.get("css") if isinstance(std, dict) else std) or "cubic-bezier(0.2,0,0,1)"
    lines.append("  --tf-ease: %s;" % std_css)
    # brand
    lines.append('  --tf-logo: url("%s");' % logo_uri(theme_dir, theme, lighter_mode))
    lines.append('  --tf-name: "%s";' % theme.get("name", "").replace('"', ""))

    # --tf-focus-ring is emitted by sem_vars() now (as the verbatim-key alias
    # of "focus-ring", alongside --tf-focus and --tf-color-focus-ring), so it
    # is no longer special-cased here. That move also fixed a real bug: this
    # block runs only for the base/`lighter` resolution, so the old alias kept
    # its light-mode value in the [data-tf-appear="dark"] override and a
    # dark-court focus ring silently rendered in the light court's color.
    # Universal, theme-independent defaults matching the documented
    # focus_visible convention ("2px solid focus-ring with a 2px offset") --
    # confirmed referenced in real surface CSS with no source anywhere.
    lines.append("  --tf-focus-width: 2px;")
    lines.append("  --tf-focus-offset: 2px;")
    # --tf-rule/--tf-rule-color: several themes' own signature motif is a
    # divider/hairline rule (counter-rule's steel rule, stated-plainly's ruled
    # sheet, two-hands' palm-line) and their surface CSS reaches for this name
    # with no local definition anywhere -- aliased to the theme's own border
    # color, the same color a rule/divider would sensibly use.
    lines.append("  --tf-rule: %s;" % gethex(lighter.get("border")))
    lines.append("  --tf-rule-color: %s;" % gethex(lighter.get("border")))
    lines.append("  --tf-rule-width: 1px;")
    lines.append("}")

    # Appearance-toggle overrides — canonical aliases must follow the toggle.
    # Two-selector form per block: the self-selector covers canvas/compare-cell;
    # the descendant selector covers surface sections that carry data-tf-theme
    # themselves (and therefore have the base rule applied directly on them,
    # which would otherwise win over variables inherited from the parent).
    #
    # Both "dark" and "light" get an explicit override block, always pointing
    # at the objectively darker / lighter resolution respectively (never at
    # "whichever schema key is named light/dark") -- see the lighter/darker
    # computation above. The base selector above already renders `lighter`,
    # so the [data-tf-appear="light"] block is redundant with it in the
    # normal case, but kept explicit rather than relying on "no dark
    # attribute" as the only path to a correct light view.
    dark_lines = [
        '[data-tf-theme="%d"][data-tf-appear="dark"],' % idx,
        '[data-tf-appear="dark"] [data-tf-theme="%d"] {' % idx,
    ]
    dark_lines.append(sem_vars(darker))
    dark_lines.append(ramp_vars(darker))
    dark_lines.append('  --tf-logo: url("%s");' % logo_uri(theme_dir, theme, darker_mode))
    focus_dark = darker.get("focus-ring")
    if focus_dark:
        dark_lines.append("  --tf-focus-ring: %s;" % gethex(focus_dark))
    dark_lines.append("  --tf-rule: %s;" % gethex(darker.get("border")))
    dark_lines.append("  --tf-rule-color: %s;" % gethex(darker.get("border")))
    dark_lines.append("}")

    light_lines = [
        '[data-tf-theme="%d"][data-tf-appear="light"],' % idx,
        '[data-tf-appear="light"] [data-tf-theme="%d"] {' % idx,
    ]
    light_lines.append(sem_vars(lighter))
    light_lines.append(ramp_vars(lighter))
    light_lines.append('  --tf-logo: url("%s");' % logo_uri(theme_dir, theme, lighter_mode))
    focus_light = lighter.get("focus-ring")
    if focus_light:
        light_lines.append("  --tf-focus-ring: %s;" % gethex(focus_light))
    light_lines.append("  --tf-rule: %s;" % gethex(lighter.get("border")))
    light_lines.append("  --tf-rule-color: %s;" % gethex(lighter.get("border")))
    light_lines.append("}")

    return "\n".join(lines) + "\n" + "\n".join(dark_lines) + "\n" + "\n".join(light_lines)


# ---------------------------------------------------------------------------
# rail + drawer + compare
# ---------------------------------------------------------------------------


def swatch_html(theme):
    light = theme.get("color", {}).get("light", {})
    cols = [gethex(light.get("primary")), gethex(light.get("accent")),
            gethex(light.get("surface")), gethex(light.get("text"))]
    return "".join('<span class="swatch" style="background:%s"></span>' % c for c in cols)


def rail_html(themes):
    out = []
    for i, (theme, _d, a11y, native) in enumerate(themes, 1):
        dev = theme.get("requires_dev_build") or (native or {}).get("requires_dev_build")
        badge = '<span class="badge-dev">needs dev build</span>' if dev else ""
        # Dark-court flag: same objective-lightness comparison theme_style_block
        # already makes (never "which schema key is named dark"). Threaded onto
        # the rail item so the JS toggle can default a dark-court theme's FIRST
        # view to its own intended dark reading instead of a blanket "light" --
        # confirmed live: switching the rail to a dark-court theme while the
        # global appear state was still "light" rendered its pale, non-primary
        # alternative as the first impression, with the theme's real dark
        # identity only reachable by manually pressing the Dark button.
        color = theme.get("color", {})
        is_dark_court = _bg_oklch_l(color.get("light", {})) < _bg_oklch_l(color.get("dark", {}))
        dark_court_attr = ' data-tf-dark-court="true"' if is_dark_court else ""
        out.append(
            '<button class="rail-item" data-theme="%d" data-slug="%s" aria-current="false"%s>'
            '<span class="ri-top"><span class="ri-num mono">%02d</span>'
            '<span class="ri-name">%s</span>'
            '<span class="ri-slot"><span class="slotchip">%s</span></span></span>'
            '<span class="ri-swatches">%s</span>'
            '<span class="ri-thesis">%s</span>%s</button>'
            % (i, html.escape(theme.get("slug", "")), dark_court_attr, i, html.escape(theme.get("name", "")),
               html.escape(theme.get("slot", "")), swatch_html(theme),
               html.escape(theme.get("thesis", "")), badge))
    return "\n".join(out)


def token_table(theme):
    light = theme.get("color", {}).get("light", {})
    rows = []
    for k in ["background", "surface", "text", "text-muted", "border", "primary", "accent", "focus-ring"]:
        v = light.get(k)
        if not v:
            continue
        hexv = gethex(v)
        cssv = getcss(v, hexv)
        rows.append(
            '<tr><td class="k">%s</td>'
            '<td class="v" data-copy="%s"><span class="sw" style="background:%s"></span>%s</td>'
            '<td class="n" data-copy="%s">%s</td></tr>'
            % (k, html.escape(cssv), hexv, html.escape(cssv), hexv, hexv))
    return "\n".join(rows)


def contrast_chips(a11y):
    if not a11y:
        return '<span class="chip warn">no a11y report</span>'
    chips = []
    for f in a11y.get("failures", []):
        chips.append('<span class="chip fail">%s · %.1f:1 ✗</span>'
                     % (html.escape(f.get("pair", "")), f.get("ratio", 0)))
    # show a handful of representative passes
    for p in a11y.get("passes", [])[:6]:
        chips.append('<span class="chip pass">%s · %.1f:1 ✓</span>'
                     % (html.escape(p.get("pair", "")), p.get("ratio", 0)))
    return "\n".join(chips) if chips else '<span class="chip pass">all pairs pass</span>'


def native_chips(theme, native):
    chips = []
    dev = theme.get("requires_dev_build") or (native or {}).get("requires_dev_build")
    if dev:
        chips.append('<span class="chip warn">requires a development build (Expo Go can\'t run it)</span>')
    for pkg in (native or {}).get("requires_packages", []) or theme.get("requires_packages", []) or []:
        chips.append('<span class="chip">%s</span>' % html.escape(pkg))
    for w in (native or {}).get("warnings", []) or []:
        chips.append('<span class="chip warn">%s: %s</span>'
                     % (html.escape(str(w.get("token", ""))), html.escape(str(w.get("note", "")))))
    if not chips:
        chips.append('<span class="chip pass">translates cleanly, no dev build</span>')
    return "\n".join(chips)


def ramp_rows_radius(theme):
    out = []
    for k, v in theme.get("radius", {}).items():
        px = v.get("px") if isinstance(v, dict) else v
        out.append('<div class="ramp-row"><span class="box" style="border-radius:%spx;background:var(--tf-surface, #ddd)"></span><span class="lbl">%s · %spx</span></div>' % (px, k, px))
    return "\n".join(out)


def elev_rows(theme, idx):
    out = []
    levels = theme.get("elevation", {}).get("levels", {})
    for n, lvl in levels.items():
        css = lvl.get("css") if isinstance(lvl, dict) else ""
        out.append('<div class="ramp-row"><span class="box" style="box-shadow:%s;background:#fff"></span><span class="lbl">level %s (iOS)</span>'
                   '<span class="box" style="box-shadow:%s;background:#fff"></span><span class="lbl">Android</span></div>'
                   % (css, n, android_shadow((lvl.get("android", {}) or {}).get("elevation", 2))))
    return "\n".join(out)


def logo_sizes(theme, theme_dir):
    uri = logo_uri(theme_dir, theme, "light")
    sizes = [16, 24, 32, 48, 96]
    out = ['<div class="logo-sizes">']
    for s in sizes:
        out.append('<span class="ls"><span class="brand-img" style="width:%dpx;height:%dpx;background:center/contain no-repeat url(&quot;%s&quot;)"></span><span>%dpx</span></span>' % (s, s, uri, s))
    out.append('</div>')
    return "".join(out)


def type_specimen(theme):
    steps = theme.get("typography", {}).get("scale", {}).get("steps", {})
    order = ["5xl", "4xl", "3xl", "2xl", "xl", "lg", "base"]
    out = ['<div class="specimen">']
    for k in order:
        if k in steps:
            px = steps[k].get("px") if isinstance(steps[k], dict) else steps[k]
            out.append('<div style="font-size:%spx">Ag %s</div>' % (px, k))
    out.append('</div>')
    return "".join(out)


def advisory_chips(theme_dir: Path, slug: str, run: dict) -> str:
    """Render advisory-tier findings for a theme's detail drawer.

    Sources (advisory tier — does not block, but user should see before picking):
      1. slop.json advisory array (impeccable warnings, not hard-stop)
      2. run.json["theme_advisories"][slug] (letter-not-spirit gate warnings)
    """
    chips = []

    # 1. slop.json advisory findings
    slop = load_json(theme_dir / "slop.json", {})
    for f in (slop.get("advisory") or []):
        rule = html.escape(str(f.get("rule", "")))
        msg = html.escape(str(f.get("message", "")))
        chips.append('<span class="chip warn">%s%s</span>'
                     % (("%s: " % rule) if rule else "", msg))

    # 2. run.json["theme_advisories"] gate warnings
    advisories = (run.get("theme_advisories") or {}).get(slug, [])
    for msg in advisories:
        chips.append('<span class="chip warn">%s</span>' % html.escape(str(msg)))

    if not chips:
        return ""
    return ('<h4>Quality notes</h4>'
            '<div class="chips advisory-chips">%s</div>' % "\n".join(chips))


def declared_chips(theme) -> str:
    """Render what this theme DECLARED it was doing (design_language,
    signature_type, per-surface motion_budget, dials) — not the rendered
    result. A user choosing a theme sees the finished preview everywhere else
    in this gallery; this section is the one place that shows the theme's
    own stated intent, so a mismatch (a springy theme declaring itself
    "calm", a webapp budget of "moderate" the schema doesn't even allow) is
    visible before picking, not just buried in a gate warning."""
    comp = theme.get("composition", {}) or {}
    motion = theme.get("motion", {}) or {}
    dials = theme.get("dials", {}) or {}
    mb = motion.get("motion_budget", {}) or {}

    chips = []
    if comp.get("design_language"):
        chips.append('<span class="chip">design_language: %s</span>' % html.escape(str(comp["design_language"])))
    if comp.get("intensity"):
        chips.append('<span class="chip">intensity: %s</span>' % html.escape(str(comp["intensity"])))
    if motion.get("signature_type"):
        chips.append('<span class="chip">signature_type: %s</span>' % html.escape(str(motion["signature_type"])))
    for surface in ("website", "webapp"):
        if mb.get(surface):
            chips.append('<span class="chip">motion_budget.%s: %s</span>' % (surface, html.escape(str(mb[surface]))))
    mobile_mb = mb.get("mobile")
    if isinstance(mobile_mb, dict):
        for screen, val in mobile_mb.items():
            chips.append('<span class="chip">motion_budget.mobile.%s: %s</span>' % (html.escape(str(screen)), html.escape(str(val))))
    for dial in ("design_variance", "motion_intensity", "visual_density"):
        if dials.get(dial) is not None:
            chips.append('<span class="chip">%s: %s/10</span>' % (dial, dials[dial]))

    if not chips:
        return ""
    return '<h4>Declared</h4><div class="chips declared-chips">%s</div>' % "\n".join(chips)


def drawers_html(subset, run: dict | None = None):
    run = run or {}
    out = []
    for i, (theme, theme_dir, a11y, native) in enumerate(subset, 1):
        slug = theme.get("slug", "")
        adv_html = advisory_chips(Path(theme_dir), slug, run)
        decl_html = declared_chips(theme)
        out.append(
            '<section class="drawer-theme" data-theme="%d" style="display:none">'
            '<h2 style="position:absolute;width:1px;height:1px;overflow:hidden;'
            'clip:rect(0,0,0,0);white-space:nowrap">Theme details</h2>'
            '<h3>%s <span class="mono" style="color:var(--c-text-faint);font-size:12px">· slot %s · %s</span></h3>'
            '<p class="d-sub">%s</p>'
            '%s'
            '%s'
            '<h4>Tokens · CSS ↔ native</h4>'
            '<table class="tokens"><thead><tr><th>Token</th><th>CSS resolution</th><th>Native</th></tr></thead><tbody>%s</tbody></table>'
            '<h4>Type scale</h4>%s'
            '<h4>Radius</h4>%s'
            '<h4>Elevation · iOS shadow vs Android elevation</h4>%s'
            '<h4>Motion · %s</h4><div class="motion-demo"><span class="ball" style="border-radius:var(--tf-r-md,6px);animation-timing-function:%s"></span></div>'
            '<h4>Logo, down to 16px</h4>%s'
            '<h4>Contrast · WCAG 2.2 AA</h4><div class="chips">%s</div>'
            '<h4>Native translation</h4><div class="chips">%s</div>'
            '</section>'
            % (i, html.escape(theme.get("name", "")), html.escape(theme.get("slot", "")),
               html.escape(theme.get("direction", "")), html.escape(theme.get("thesis", "")),
               adv_html, decl_html,
               token_table(theme), type_specimen(theme), ramp_rows_radius(theme),
               elev_rows(theme, i), html.escape(theme.get("motion", {}).get("character", "")),
               theme.get("motion", {}).get("easing", {}).get("standard", {}).get("css", "ease") if isinstance(theme.get("motion", {}).get("easing", {}).get("standard", {}), dict) else "ease",
               logo_sizes(theme, theme_dir), contrast_chips(a11y), native_chips(theme, native)))
    return "\n".join(out)


_SCRIPT_BLOCK_RE = re.compile(r'<script\b[^>]*>.*?</script\s*>', re.IGNORECASE | re.DOTALL)


def compare_html(themes, surface_markups):
    """Generate one compare-surface group per surface so the grid tracks the active tab.

    surface_markups values may be a list (one entry per theme) or a single string
    (shared markup used for all cells — used for app/mobile surfaces).
    """
    out = []
    for surface_name, markup in surface_markups.items():
        out.append('<div class="compare-surface" data-compare-surface="%s">' % surface_name)
        for i, (theme, _td, _a, _n) in enumerate(themes, 1):
            color = theme.get("color", {})
            light = color.get("light", {})
            # Same dark-court awareness as the main canvas (see rail_html):
            # a compare-grid cell hardcoded to "light" showed every dark-court
            # theme's non-primary, paler alternative in the one view meant to
            # let a reader judge all six side by side -- the exact opposite of
            # a fair comparison for roughly a third of a typical six-theme set.
            cell_appear = (
                "dark"
                if _bg_oklch_l(light) < _bg_oklch_l(color.get("dark", {}))
                else "light"
            )
            cell_markup = markup[i - 1] if isinstance(markup, list) else markup
            # Strip inline <script> blocks from the compare-grid copy. A
            # theme's surface markup is embedded twice -- once on the main
            # canvas, once per compare cell -- and any inline script inside
            # it (a live calculator, a form validator) runs unscoped
            # document.querySelector calls against the WHOLE assembled page,
            # not just its own copy. Confirmed live: counter-rule's trade-in
            # estimator script bound to whichever of the two embedded copies
            # happened to come first in DOM order, permanently leaving the
            # other showing a stale, never-wired-up figure. The compare grid
            # is a static side-by-side thumbnail view -- it never needed the
            # interactivity, so removing the script there (not from the
            # canvas copy, which keeps working exactly as before) resolves
            # the ambiguity at the root instead of requiring every theme's
            # own inline script to defensively scope itself.
            cell_markup = _SCRIPT_BLOCK_RE.sub('', cell_markup)
            out.append(
                '<div class="cell" data-theme="%d" data-tf-theme="%d" data-tf-appear="%s">'
                '<div class="cap"><span class="dot" style="background:%s"></span>'
                '<span class="nm">%s</span><span class="sl mono">%s</span></div>'
                '<div class="mini"><div class="scaler">%s</div></div></div>'
                % (i, i, cell_appear, gethex(light.get("primary")), html.escape(theme.get("name", "")),
                   html.escape(theme.get("slug", "")), cell_markup))
        out.append('</div>')
    return "\n".join(out)


# ---------------------------------------------------------------------------
# font import
# ---------------------------------------------------------------------------


def _is_google_source(src) -> bool:
    """Does this `typography.<role>.source` mean Google Fonts?

    `source` is an unconstrained string in theme.schema.json (`{"type":
    "string"}`), so there is no canonical spelling and every value a
    theme-designer writes is schema-valid. This used to be an exact `== "google"`
    comparison, which silently dropped every family whose theme happened to
    write `"google-fonts"` instead -- confirmed live on a six-theme run where
    four themes used that spelling and two used `"google"`, so the gallery
    imported only the two matching themes' faces and **four of six themes
    rendered entirely in Helvetica/Arial fallback**. Nothing errored, the
    `@import` was well-formed, and the type simply wasn't the type -- which also
    meant a design-critic pass praised "112px Big Shoulders Display caps" and
    "the only serif body in the set" while looking at a fallback sans.

    Matching on the normalized substring rather than a fixed list keeps any
    future spelling ("Google Fonts", "googlefonts", "google_fonts") working.
    """
    if not isinstance(src, str):
        return False
    return "google" in src.strip().lower().replace("_", "-")


def font_import(all_themes):
    families = {}
    skipped = []
    for theme, _td, _a, _n in all_themes:
        typ = theme.get("typography", {})
        for role in ("display", "body", "mono"):
            r = typ.get(role, {})
            fam = r.get("family")
            if not fam:
                continue
            if _is_google_source(r.get("source")):
                weights = set(families.get(fam, set())) | set(str(w) for w in r.get("weights", [400]))
                families[fam] = weights
            else:
                skipped.append((theme.get("slug", "?"), role, fam, r.get("source")))
    # A declared family that never reaches the @import renders as fallback with
    # no error anywhere, so say so out loud rather than leaving it to a reader
    # to notice the type looks wrong. Legitimately-local faces show up here too
    # (that is fine and expected) -- the point is that the list is visible.
    for slug, role, fam, src in skipped:
        sys.stderr.write(
            "tf_gallery: NOTE — %s/%s font %r not imported (source=%r); it will render "
            "from its css_fallback stack. If it is a Google font, fix the source value.\n"
            % (slug, role, fam, src)
        )
    families.setdefault("JetBrains Mono", set(["400", "700"]))
    parts = []
    for fam, weights in families.items():
        ws = ";".join(sorted(weights))
        parts.append("family=%s:wght@%s" % (fam.replace(" ", "+"), ws))
    if not parts:
        return ""
    url = "https://fonts.googleapis.com/css2?" + "&".join(parts) + "&display=swap"
    return "@import url('%s');" % url


# ---------------------------------------------------------------------------
# brand panel
# ---------------------------------------------------------------------------


def brand_panel_html(idx: int, theme: dict, theme_dir) -> str:
    td = Path(theme_dir)
    assets = theme.get("assets", {})
    platform_assets = theme.get("platform_assets", {})
    licensing = theme.get("licensing", {})
    brand_dir = td / "brand"

    if not brand_dir.exists():
        return (
            '<div class="brand-panel" data-brand-theme="%d">'
            '<div class="brand-empty">'
            '<p>Brand assets not yet generated.</p>'
            '<p>Run Step 5b (brand-asset-designer) to build this panel.</p>'
            '</div></div>' % idx
        )

    sections = []

    # Brand sheet: wordmark + logomark at multiple sizes
    mark_svg = inline_svg(brand_dir / "logomark.svg")
    word_svg = (inline_svg(brand_dir / "wordmark-outlined.svg")
                or inline_svg(brand_dir / "wordmark.svg"))
    sizes_html = "".join(
        '<div class="brand-size-item">'
        '<div class="brand-mark-wrap" style="width:%dpx;height:%dpx">%s</div>'
        '<span class="brand-size-label">%dpx</span></div>' % (sz, sz, mark_svg, sz)
        for sz in (64, 32, 24, 16) if mark_svg
    )
    if mark_svg or word_svg:
        sections.append(
            '<section class="brand-section">'
            '<h3 class="brand-section-title">Brand sheet</h3>'
            '<div class="brand-sheet">'
            + ('<div class="brand-wordmark">%s</div>' % word_svg if word_svg else '')
            + '<div class="brand-sizes">%s</div></div></section>' % sizes_html
        )

    # Animated marks
    motion_dir = brand_dir / "motion"
    motion_items = []
    for fname, label in [("logo-draw.svg", "Logo draw-on"), ("spinner.svg", "Spinner"),
                         ("success-check.svg", "Success"), ("error-x.svg", "Error")]:
        svg = inline_svg(motion_dir / fname)
        if svg:
            motion_items.append(
                '<div class="motion-item">'
                '<div class="motion-preview">%s</div>'
                '<span class="motion-label">%s</span></div>' % (svg, label)
            )
    if motion_items:
        badges = "".join(
            '<span class="asset-badge">%s</span>' % f
            for f in ("motion.css", "motion.ts") if (motion_dir / f).exists()
        )
        sections.append(
            '<section class="brand-section">'
            '<h3 class="brand-section-title">Motion %s</h3>'
            '<div class="motion-previews">%s</div></section>' % (badges, "".join(motion_items))
        )

    # Icons grid — discover SVG location (may be brand/icons/ or brand/icons/set/)
    icons_dir = brand_dir / "icons"
    icons_json = load_json(icons_dir / "icons.json", {})
    actual_icons_dir = icons_dir
    for candidate in (icons_dir / "set", icons_dir):
        if candidate.exists() and list(candidate.glob("*.svg")):
            actual_icons_dir = candidate
            break
    icon_names = icons_json.get("icons", [])
    if not isinstance(icon_names, list) or not icon_names:
        icon_names = [p.stem for p in sorted(actual_icons_dir.glob("*.svg"))]
    icon_items = []
    for name in icon_names[:24]:
        svg = inline_svg(actual_icons_dir / ("%s.svg" % name))
        if svg:
            icon_items.append(
                '<div class="icon-cell">'
                '<div class="icon-preview">%s</div>'
                '<span class="icon-name">%s</span></div>' % (svg, html.escape(str(name)))
            )
    if icon_items:
        stroke = assets.get("icons", {}).get("stroke", "")
        subtitle = " · %.1fpx stroke" % stroke if stroke else ""
        sections.append(
            '<section class="brand-section">'
            '<h3 class="brand-section-title">Icons · %d%s</h3>'
            '<div class="icons-grid">%s</div></section>' % (len(icon_items), subtitle, "".join(icon_items))
        )

    # Spot illustrations
    illus_dir = brand_dir / "illustrations"
    illus_items = []
    for name in ("empty-state", "onboarding-1", "onboarding-2", "onboarding-3", "error-404", "success"):
        svg = inline_svg(illus_dir / ("%s.svg" % name))
        if svg:
            illus_items.append(
                '<div class="illus-cell">'
                '<div class="illus-preview">%s</div>'
                '<span class="illus-name">%s</span></div>' % (svg, name)
            )
    if illus_items:
        sections.append(
            '<section class="brand-section">'
            '<h3 class="brand-section-title">Illustrations</h3>'
            '<div class="illustrations-grid">%s</div></section>' % "".join(illus_items)
        )

    # Avatars — discover SVG location (may be brand/avatars/ or brand/avatars/samples/)
    avatars_dir = brand_dir / "avatars"
    actual_avatars_dir = avatars_dir
    for candidate in (avatars_dir / "samples", avatars_dir):
        if candidate.exists() and list(candidate.glob("*.svg")):
            actual_avatars_dir = candidate
            break
    avatar_items = []
    if actual_avatars_dir.exists():
        for p in sorted(actual_avatars_dir.glob("*.svg"))[:8]:
            svg = inline_svg(p)
            if svg:
                avatar_items.append('<div class="avatar-item">%s</div>' % svg)
    if avatar_items:
        av = assets.get("avatars", {})
        sections.append(
            '<section class="brand-section">'
            '<h3 class="brand-section-title">Avatars · '
            '<span class="asset-badge">%s</span> · %s</h3>'
            '<div class="avatars-row">%s</div></section>' % (
                html.escape(av.get("license", "CC0")),
                html.escape(av.get("style", "")),
                "".join(avatar_items),
            )
        )

    # Imagery brief — check brand/imagery/ART-DIRECTION.md then theme root
    art_brief = (read(brand_dir / "imagery" / "ART-DIRECTION.md")
                 or read(td / "ART-DIRECTION.md"))
    if art_brief:
        img = assets.get("imagery", {})
        preview = html.escape(art_brief[:800] + ("…" if len(art_brief) > 800 else ""))
        sections.append(
            '<section class="brand-section">'
            '<h3 class="brand-section-title">Imagery brief · '
            '<span class="asset-badge">%s</span></h3>'
            '<div class="imagery-placeholder"><pre class="imagery-brief">%s</pre></div>'
            '</section>' % (html.escape(img.get("strategy", "brief")), preview)
        )

    # Asset inventory
    web_assets = platform_assets.get("web", [])
    _raw_nr = platform_assets.get("native_rasterized", [])
    # Normalise: entries may be {source, reason} dicts or bare strings
    native_rasterized = [
        r if isinstance(r, dict) else {"source": r, "reason": ""}
        for r in _raw_nr
    ]
    all_srcs = sorted(set(web_assets) | {r["source"] for r in native_rasterized})
    if all_srcs:
        rows = "".join(
            '<tr><td class="mono">%s</td><td>%s</td><td>%s</td><td class="native-note">%s</td></tr>'
            % (html.escape(src),
               "✓" if src in web_assets else "—",
               "✓" if any(r["source"] == src for r in native_rasterized) else "—",
               html.escape(next((r["reason"] for r in native_rasterized if r["source"] == src), "")))
            for src in all_srcs
        )
        ok = not licensing.get("attribution_required", False)
        sections.append(
            '<section class="brand-section">'
            '<h3 class="brand-section-title">Asset inventory · '
            '<span class="asset-badge %s">%s</span></h3>'
            '<div class="inventory-wrap"><table class="inventory-table">'
            '<thead><tr><th>Asset</th><th>Web</th><th>Native</th><th>Note</th></tr></thead>'
            '<tbody>%s</tbody></table></div></section>' % (
                "badge-ok" if ok else "badge-warn",
                "No attribution required" if ok else "Attribution required",
                rows,
            )
        )

    # Native differences
    if native_rasterized:
        items = "".join(
            '<li><code class="mono">%s</code> → PNG · <span class="native-note">%s</span></li>'
            % (html.escape(r["source"]), html.escape(r["reason"]))
            for r in native_rasterized
        )
        sections.append(
            '<section class="brand-section brand-section--native">'
            '<h3 class="brand-section-title">Native differences</h3>'
            '<ul class="native-diff">%s</ul></section>' % items
        )

    if not sections:
        sections = ['<div class="brand-empty"><p>Brand directory found but no assets generated yet.</p></div>']

    # The brand-section h3's above (Brand sheet, Motion, Icons, ...) are real
    # subsections of this panel, but nothing at h2 level ever preceded them --
    # in a theme's own standalone preview.html, this panel is appended right
    # after the mobile screens' own h1's, so the document outline jumped
    # straight from h1 to h3 with no h2 in between. A visually-hidden h2 here
    # (screen-reader-only, same clip-rect technique the surfaces already use
    # for their own off-screen headings) fixes the outline without changing
    # anything a sighted user sees -- this panel's tab/label chrome already
    # carries the visible "Brand" identification.
    _brand_h2 = (
        '<h2 style="position:absolute;width:1px;height:1px;overflow:hidden;'
        'clip:rect(0,0,0,0);white-space:nowrap">Brand &amp; assets</h2>'
    )
    return '<div class="brand-panel" data-brand-theme="%d">\n%s\n%s\n</div>' % (idx, _brand_h2, "\n".join(sections))


def brands_html(themes) -> str:
    panels = "\n".join(
        brand_panel_html(i, theme, td)
        for i, (theme, td, _a, _n) in enumerate(themes, 1)
    )
    return '<section class="surface surface-brand" data-surface="brand">\n%s\n</section>' % panels


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------


def extract_section(markup, cls):
    m = re.search(r'<section class="surface %s".*?</section>' % re.escape(cls), markup, re.S)
    return m.group(0) if m else ""


_DOCTYPE_RE = re.compile(r'<!DOCTYPE\s+html[^>]*>', re.IGNORECASE)
_HTML_OPEN_RE = re.compile(r'<html\b[^>]*>', re.IGNORECASE)
_HTML_CLOSE_RE = re.compile(r'</html\s*>', re.IGNORECASE)
_HEAD_BLOCK_RE = re.compile(r'<head\b[^>]*>.*?</head\s*>', re.IGNORECASE | re.DOTALL)
_BODY_OPEN_RE = re.compile(r'<body\b[^>]*>', re.IGNORECASE)
_BODY_CLOSE_RE = re.compile(r'</body\s*>', re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)


def _strip_document_wrapper(raw_html: str, source_label: str) -> str:
    """surface-composer's contract is a bare markup FRAGMENT (no <!DOCTYPE>,
    <html>, <head>, or <body> tags) -- gallery.html embeds six themes' worth of
    these fragments side by side inside its OWN single document. A surface
    file that instead wrote a full standalone document is not just inert
    boilerplate once embedded: browsers do not allow nested <html> elements,
    and the HTML5 parsing algorithm's handling of a stray <html>/<body> start
    tag mid-document does not discard it -- it merges that tag's attributes
    onto the REAL document root/body if not already present there. A theme
    whose fragment happened to include `<html data-tf-appear="light">` (a
    leftover from some standalone-preview convenience copy) was confirmed
    live to leak that attribute onto the actual page's <html> element,
    permanently pinning the gallery's light/dark toggle state at the CSS
    specificity tie-break level regardless of what the JS toggle state said --
    a bug that had nothing to do with that theme's own colors being wrong.
    Any <head> content (stray <link>/<style> tags pointing at paths that only
    exist standalone, like "web/theme.css") is discarded outright, which also
    explains 40+ browser console 404s observed against a theme set that
    otherwise rendered fully styled from tf_gallery's own inlined blocks.

    Detection runs against a comment-BLANKED copy (each `<!--...-->` replaced
    by same-length spaces, not deleted): a file correctly documenting its own
    compliance (a comment reading "no <html>/<head>/<body> here") must not be
    treated as if it contained a real wrapper tag -- confirmed live, this
    exact false positive aborted a run over a comment explaining why the file
    was already correct. Blanking rather than deleting preserves every
    character's original offset, so positions found in the blanked copy can
    still be used to slice the REAL raw_html -- deleting comments before
    searching would shift every subsequent offset and slice the wrong span,
    and would also strip legitimate content comments from the surface's own
    markup, not just the false-positive-prone compliance note.
    """
    check_against = _HTML_COMMENT_RE.sub(lambda m: ' ' * len(m.group(0)), raw_html)
    if not _HTML_OPEN_RE.search(check_against) and not _DOCTYPE_RE.search(check_against):
        return raw_html  # already a bare fragment, the expected case
    sys.stderr.write(
        "tf_gallery: WARNING — %s is a full document (<html>/<!DOCTYPE>), not a "
        "bare fragment. Stripping the wrapper; the surface-composer agent brief "
        "asks for body-only markup. Any <head> content in this file is discarded.\n"
        % source_label
    )
    body_open = _BODY_OPEN_RE.search(check_against)
    body_close = _BODY_CLOSE_RE.search(check_against)
    if body_open and body_close and body_close.start() > body_open.end():
        return raw_html[body_open.end():body_close.start()]
    # No <body> tags found (unusual) -- fall back to stripping the wrappers
    # we do recognize and hope the remainder is otherwise fragment-shaped.
    # (Safe to operate on check_against here: this fallback path is only ever
    # reached when a genuine wrapper tag was found outside a comment, at
    # which point a stray "<html>" mentioned inside some other comment is a
    # cosmetic, not functional, casualty -- unlike the slice above, there is
    # no offset-alignment requirement for a global .sub() pass.)
    out = _DOCTYPE_RE.sub('', check_against)
    out = _HEAD_BLOCK_RE.sub('', out)
    out = _HTML_OPEN_RE.sub('', out)
    out = _HTML_CLOSE_RE.sub('', out)
    return out


_EMITTED_CACHE: dict = {}


def _emitted_names_for(theme_dir: Path) -> set:
    """Every --tf-* name this theme's injected token block defines.

    Cached per theme_dir: read_theme_surface() runs once per surface, and
    re-deriving the whole token block three times per theme would triple the
    work for an identical answer.
    """
    key = str(theme_dir)
    if key not in _EMITTED_CACHE:
        try:
            theme = json.loads(read(theme_dir / "theme.json"))
            _EMITTED_CACHE[key] = tf_tokens.emitted_names(theme, theme_dir)
        except (OSError, ValueError):
            # An unreadable theme.json is already fatal elsewhere with a far
            # better message; degrade to "assume everything is defined" so this
            # gate never becomes the thing that reports it.
            _EMITTED_CACHE[key] = set()
    return _EMITTED_CACHE[key]


def read_theme_surface(theme_dir: Path, theme_idx: int, surface: str,
                        brand_prefix: str = "brand/") -> tuple[str, str]:
    """Read one theme's own bespoke surfaces/<surface>.html + .css, written by
    the surface-composer agent. Replaces the old _assemble_surface_web(), which
    picked from a shared hero/nav/section partial library -- there is no such
    library anymore; each theme's markup and CSS are its own.

    Returns (wrapped_html, scoped_css). Aborts the whole run if the surface
    file is missing: there is no shared-template fallback to degrade to, and
    silently skipping a theme would produce a gallery that looks complete but
    is missing one theme's surface.

    CSS scoping: six independently-authored stylesheets sit in the same DOM at
    once in compare mode, so class-name collisions between two themes' bespoke
    CSS (e.g. both happen to use ".hero") are a real risk without isolation.
    @scope (Baseline 2024, all evergreen browsers this offline tool targets)
    confines every selector in the theme's own CSS to only match inside that
    theme's own surface -- no selector-rewriting needed, the theme's CSS is
    used completely unmodified inside the @scope block.
    """
    surf_dir = theme_dir / "surfaces"
    html_path = surf_dir / f"{surface}.html"
    css_path = surf_dir / f"{surface}.css"
    if not html_path.is_file() or not css_path.is_file():
        sys.stderr.write(
            "tf_gallery: ABORT — %s is missing surfaces/%s.html or surfaces/%s.css. "
            "Run surface-composer for this theme/surface before assembling the gallery.\n"
            % (theme_dir.name, surface, surface)
        )
        print(json.dumps({
            "ok": False,
            "error": "missing bespoke surface",
            "theme": theme_dir.name,
            "surface": surface,
        }))
        sys.exit(1)

    raw_html = read(html_path)
    raw_css = read(css_path)
    raw_html = _strip_document_wrapper(raw_html, "%s/surfaces/%s.html" % (theme_dir.name, surface))

    # surface-composer writes asset references relative to its own file
    # (surfaces/<surface>.html), e.g. src="../brand/logo.svg" -- correct there,
    # but this same HTML is inlined verbatim into two different documents at
    # different directory depths (gallery.html and this theme's own
    # preview.html), so the relative path must be rewritten per destination.
    raw_html = raw_html.replace('"../brand/', '"%s' % brand_prefix)
    raw_html = raw_html.replace("'../brand/", "'%s" % brand_prefix)
    raw_css = raw_css.replace("../brand/", brand_prefix)

    _content_checker = tf_content._CHECKS.get(surface)
    content_findings = _content_checker(raw_html) if _content_checker else []
    if content_findings:
        for f in content_findings:
            sys.stderr.write("tf_gallery: ABORT — %s/%s: %s\n" % (theme_dir.name, surface, f["message"]))
        print(json.dumps({
            "ok": False,
            "error": "content-completeness check failed",
            "theme": theme_dir.name,
            "surface": surface,
            "findings": content_findings,
        }))
        sys.exit(1)

    # Dead-custom-property gate. A bare var(--tf-x) that nothing defines is
    # dropped at computed-value time -- no error, no warning, and the page
    # still renders plausibly, which is why every previous instance was found
    # by eye rather than by a check (one audited run carried 496 of them).
    # This aborts rather than warns for the same reason the content gate does:
    # the failure is deterministic, has no false-positive case (it is a parser
    # fact, not a judgment), and left as a warning it is exactly the kind of
    # finding that accumulates unread across runs.
    token_findings = tf_tokens.scan_css(raw_css, _emitted_names_for(theme_dir))["dead"]
    if token_findings:
        for name, n in sorted(token_findings.items(), key=lambda kv: -kv[1]):
            sys.stderr.write(
                "tf_gallery: ABORT — %s/%s.css uses %s %d time(s) with no fallback, "
                "and nothing defines it.\n" % (theme_dir.name, surface, name, n))
        print(json.dumps({
            "ok": False,
            "error": "dead custom property in surface CSS",
            "theme": theme_dir.name,
            "surface": surface,
            "findings": [{"property": k, "uses": v} for k, v in sorted(token_findings.items())],
        }))
        sys.exit(1)

    # Gallery CSS/JS keys surface-tab switching off a fixed class per surface
    # (surface-web, surface-app, surface-mobile) established before the
    # bespoke-composition rewrite — matched here, not chosen by this function.
    _SURFACE_CLASS = {"website": "surface-web", "webapp": "surface-app", "mobile": "surface-mobile"}
    surface_class = _SURFACE_CLASS.get(surface, "surface-%s" % surface)

    wrapped_html = (
        '<section class="surface %s" data-surface="%s" '
        'data-tf-theme="%d" role="region" aria-label="%s preview">\n'
        '%s\n</section>' % (surface_class, surface, theme_idx, surface.capitalize(), raw_html)
    )
    scoped_css = '@scope ([data-tf-theme="%d"] .%s) {\n%s\n}\n' % (theme_idx, surface_class, raw_css)
    return wrapped_html, scoped_css


def read_theme_mobile_screens(theme_dir: Path, theme_idx: int,
                               brand_prefix: str = "brand/") -> tuple[str, str]:
    """Read one theme's own bespoke surfaces/mobile.html (N `.screen-pane` divs)
    + .css, written by the surface-composer agent. Unlike website/webapp, the
    physical device frame (bezel/status-bar/home-indicator chrome) is shared
    infrastructure that stays in templates/device-frames.html -- this function
    only returns each theme's own screen *content*, which the caller either
    clones at runtime into the canvas's shared device frame (keyed by a
    per-theme <template>, see build()) or embeds directly per compare-grid
    cell (no runtime cloning needed there -- each cell is static).

    Returns (raw_screens_html, scoped_css). Aborts the whole run if the
    surface file is missing, same as read_theme_surface().
    """
    surf_dir = theme_dir / "surfaces"
    html_path = surf_dir / "mobile.html"
    css_path = surf_dir / "mobile.css"
    if not html_path.is_file() or not css_path.is_file():
        sys.stderr.write(
            "tf_gallery: ABORT — %s is missing surfaces/mobile.html or surfaces/mobile.css. "
            "Run surface-composer for this theme/surface before assembling the gallery.\n"
            % theme_dir.name
        )
        print(json.dumps({
            "ok": False,
            "error": "missing bespoke surface",
            "theme": theme_dir.name,
            "surface": "mobile",
        }))
        sys.exit(1)

    raw_html = read(html_path)
    raw_css = read(css_path)
    raw_html = _strip_document_wrapper(raw_html, "%s/surfaces/mobile.html" % theme_dir.name)

    raw_html = raw_html.replace('"../brand/', '"%s' % brand_prefix)
    raw_html = raw_html.replace("'../brand/", "'%s" % brand_prefix)
    raw_css = raw_css.replace("../brand/", brand_prefix)

    content_findings = tf_content.check_mobile(raw_html)
    if content_findings:
        for f in content_findings:
            sys.stderr.write("tf_gallery: ABORT — %s/mobile: %s\n" % (theme_dir.name, f["message"]))
        print(json.dumps({
            "ok": False,
            "error": "content-completeness check failed",
            "theme": theme_dir.name,
            "surface": "mobile",
            "findings": content_findings,
        }))
        sys.exit(1)

    # Screens are cloned/embedded as descendants of an element already carrying
    # data-tf-theme (the canvas div, or the compare-grid cell) -- no extra
    # wrapper needed here for the @scope anchor to work.
    scoped_css = '@scope ([data-tf-theme="%d"] .screen-pane) {\n%s\n}\n' % (theme_idx, raw_css)
    return raw_html, scoped_css


# What a missing capability actually cost this run. A bare capability name
# ("rasterizer") tells a reviewer nothing; the consequence is the reportable
# fact, because every one of these degrades silently and still returns ok:true.
_DEGRADED_IMPACT = {
    "rasterizer": "brand PNGs and favicons were not generated — see RASTERIZE.md",
    "opentype":   "wordmarks ship as <text> and depend on the font being installed",
    "svgo":       "SVGs were not optimized",
    "browser":    "no screenshots, and SVG filter effects were not rendered",
    "network":    "no stock imagery and no knowledge refresh",
}


def _degraded_html(subset) -> str:
    """Surface tf_tools.py's degraded-capability list in the header.

    tf_tools.py records which capabilities were unavailable for this run in
    current/tools.json, and until now nothing read it. That mattered because
    every tool ladder degrades gracefully and returns ok:true: a run with no
    rasterizer and no opentype.js shipped un-rasterized brand assets and
    font-dependent <text> wordmarks while reporting complete success. A missing
    tool is legitimately not an error -- but it must not be invisible either,
    and the gallery header is the one place a reviewer sees the whole run at
    once. Reports the consequence, not just the capability name.
    """
    if not subset:
        return ""
    # subset[0][1] is a theme dir (current/themes/NN-slug), so two levels up is
    # current/ -- same derivation the screenshot count below uses.
    tools = load_json(Path(subset[0][1]).parent.parent / "tools.json", {}) or {}
    if not tools:
        return ""  # never probed; claiming "all tools available" would be a lie
    raw = tools.get("degraded")
    if not isinstance(raw, list):
        # Key absent or the wrong shape (an older tools.json). "No degraded
        # entries recorded" and "every tool was available" are different facts;
        # rendering the green pill here would assert the second from the first.
        return ""
    degraded = [d for d in raw if isinstance(d, str)]
    if not degraded:
        return ('<div class="pair">'
                '<span>tools</span>'
                '<span class="verify-pill verify-ok">all available</span>'
                '</div>')
    impacts = "; ".join(
        "%s: %s" % (d, _DEGRADED_IMPACT.get(d, "unavailable")) for d in degraded)
    return (
        '<div class="pair">'
        '<span>tools</span>'
        '<span class="verify-pill verify-stdlib" title="%s">%s degraded — %s</span>'
        '</div>' % (html.escape(impacts, quote=True), len(degraded),
                    html.escape(", ".join(degraded)))
    )


def _verification_status_html(subset, run: dict) -> str:
    """Build the verification status rows for the gallery header."""
    # Slop check — read from first available slop.json
    slop_html = ""
    for _theme, td, _a, _n in subset:
        slop = load_json(Path(td) / "slop.json", {})
        if slop:
            source = slop.get("source", "impeccable")
            # No fallback to rules_total here: rules_checked (how many rules
            # actually ran) and rules_total (the ceiling, always 59) answer
            # different questions. Substituting one for the other used to
            # mean a slop.json missing rules_checked entirely would display
            # "59 of 59 rules" -- claiming full coverage that was never
            # confirmed -- instead of the honest "unknown of 59". Currently
            # dead in practice (tf_slop.py always writes rules_checked), but
            # the same shape of bug as the used.md ledger's signature column,
            # just not yet triggered by any real slop.json.
            rules_checked = slop.get("rules_checked", "?")
            rules_total = slop.get("rules_total", 59)
            if source == "stdlib":
                label = "%s of %s rules (CLI unavailable)" % (rules_checked, rules_total)
                cls = "verify-stdlib"
            else:
                label = "%s of %s rules (impeccable)" % (rules_checked, rules_total)
                cls = "verify-full"
            slop_html = (
                '<div class="pair">'
                '<span>slop</span>'
                '<span class="verify-pill %s">%s</span>'
                '</div>' % (cls, html.escape(label))
            )
            break

    # Visual review -- count review screenshots, and ONLY those.
    #
    # current/screenshots/visual review/ is the single canonical destination for
    # design-critic shots (tf_paths.py scaffolds it, tf_reset.py recreates it on
    # wipe), so counting it directly is both correct and unambiguous. This
    # deliberately does not walk the per-theme directories: those hold brand
    # assets, and once the rasterizer
    # populates brand/native/ every theme carries a dozen-plus PNGs that have
    # nothing to do with visual critique -- counting them reported "138 shots"
    # on a run where the critic never opened a browser, turning the badge from
    # a signal into noise.
    shot_count = 0
    if subset:
        shots_dir = Path(subset[0][1]).parent.parent / "screenshots" / "visual review"
        if shots_dir.is_dir():
            shot_count = len(list(shots_dir.glob("*.png")))
    if shot_count > 0:
        vis_html = (
            '<div class="pair">'
            '<span>visual critique</span>'
            '<span class="verify-pill verify-ok">%d shot%s</span>'
            '</div>' % (shot_count, "s" if shot_count != 1 else "")
        )
    else:
        vis_html = (
            '<div class="pair">'
            '<span>visual critique</span>'
            '<span class="verify-pill verify-skip">skipped, no browser</span>'
            '</div>'
        )

    parts = [p for p in (slop_html, vis_html, _degraded_html(subset)) if p]
    return "\n      ".join(parts)


def _check_surface_sanity(raw_htmls: list[str], subset, surface_label: str) -> None:
    """Degenerate-output sanity check — NOT a distinctiveness measurement (that's
    tf_structure.py / Gate 18, run separately by tf_distinct.py against each
    theme's actual rendered structure). Bespoke, independently-authored surfaces
    can legitimately land within a few percent of each other's total byte count
    despite being structurally unrelated (a rail-nav console layout and a
    centered editorial layout can both simply have "about that much copy") --
    a minimum-spread-percentage requirement was a false signal here and blocked
    genuine bespoke content. What a byte count *can* reliably catch: a surface
    that's near-empty, or two surfaces that are literal duplicates."""
    if len(raw_htmls) < 2:
        return
    byte_lens = [len(h.encode("utf-8")) for h in raw_htmls]
    sys.stderr.write(
        "tf_gallery: %s surface byte lengths: %s\n"
        % (surface_label, " ".join(str(l) for l in byte_lens))
    )
    _MIN_SURFACE_BYTES = 200
    _empties = [(i + 1) for i, bl in enumerate(byte_lens) if bl < _MIN_SURFACE_BYTES]
    if _empties:
        sys.stderr.write(
            "tf_gallery: ABORT — theme(s) %s produced a near-empty %s surface "
            "(< %d bytes). surface-composer did not write real content.\n"
            % (", ".join(str(i) for i in _empties), surface_label, _MIN_SURFACE_BYTES)
        )
        print(json.dumps({"ok": False, "error": "near-empty %s surface" % surface_label}))
        sys.exit(1)
    _seen: dict[str, int] = {}
    for i, raw in enumerate(raw_htmls, 1):
        if raw in _seen:
            _a, _b = _seen[raw], i
            _slug_a = subset[_a - 1][0].get("slug", str(_a))
            _slug_b = subset[_b - 1][0].get("slug", str(_b))
            sys.stderr.write(
                "tf_gallery: ABORT — theme %d (%s) and theme %d (%s) have byte-identical "
                "%s.html — one is a literal copy of the other.\n" % (_a, _slug_a, _b, _slug_b, surface_label)
            )
            print(json.dumps({"ok": False, "error": "duplicate %s surface content" % surface_label,
                               "slug_a": _slug_a, "slug_b": _slug_b}))
            sys.exit(1)
        _seen[raw] = i
    # 3× median outlier guard: one bloated surface = injection loop or inlined asset
    _sorted_lens = sorted(byte_lens)
    _median_len = _sorted_lens[len(_sorted_lens) // 2]
    if _median_len > 0:
        _outliers = [(i + 1, bl) for i, bl in enumerate(byte_lens) if bl > 3 * _median_len]
        if _outliers:
            for _ti, _bl in _outliers:
                _slug = subset[_ti - 1][0].get("slug", str(_ti)) if _ti <= len(subset) else str(_ti)
                sys.stderr.write(
                    "tf_gallery: OUTLIER ABORT — theme %d (%s) %s surface %d B is %.0fx "
                    "median (%d B). Likely injection loop in a section template.\n"
                    % (_ti, _slug, surface_label, _bl, _bl / _median_len, _median_len)
                )
            print(json.dumps({"ok": False, "error": "%s-surface size outlier: one theme exceeds 3x median" % surface_label}))
            sys.exit(1)


def build(shell, css, frames, themes, meta, primary_platform,
          only_theme=None, run: dict | None = None):
    subset = themes if only_theme is None else [themes[only_theme - 1]]
    # renumber subset to 1..n
    default_surface = "mobile" if primary_platform == "native" else "website"

    styles = []
    for i, (theme, td, _a, _n) in enumerate(subset, 1):
        styles.append(theme_style_block(i, theme, td))
    theme_styles = "\n".join(styles)

    rail = rail_html(subset)
    drawers = drawers_html(subset, run=run)

    # ── Surface HTML assembly ──────────────────────────────────────────────────
    # Website, webapp, and mobile are all bespoke per theme now (Phases 1-3 of
    # the bespoke-composition rewrite). Website/webapp: read_theme_surface()
    # reads each theme's own surfaces/<surface>.html + .css directly, wrapped
    # in a per-theme <section>. Mobile is different: the physical device frame
    # (bezel/status-bar chrome) stays shared infrastructure in
    # device-frames.html, so read_theme_mobile_screens() returns just each
    # theme's own screen content, cloned into that shared frame at runtime
    # (canvas) or embedded directly per cell (compare grid) below.

    # only_theme=None builds the combined gallery.html at current/gallery.html,
    # where a theme's brand assets sit at themes/<slug>/brand/. only_theme=i
    # builds that theme's own standalone preview.html at
    # current/themes/<slug>/preview.html, where brand assets sit at brand/
    # directly (this file's own read_theme_surface() call handles the rewrite
    # from surfaces/website.html's own "../brand/" references).
    per_theme_web: list[str] = []
    per_theme_web_css: list[str] = []
    per_theme_web_raw: list[str] = []
    per_theme_app: list[str] = []
    per_theme_app_css: list[str] = []
    per_theme_app_raw: list[str] = []
    per_theme_mobile: list[str] = []
    per_theme_mobile_css: list[str] = []
    per_theme_mobile_raw: list[str] = []
    for i, (theme, td, _a, _n) in enumerate(subset, 1):
        brand_prefix = "brand/" if only_theme is not None else "themes/%s/brand/" % Path(td).name
        wrapped_html, scoped_css = read_theme_surface(Path(td), i, "website", brand_prefix=brand_prefix)
        per_theme_web.append(wrapped_html)
        per_theme_web_css.append(scoped_css)
        per_theme_web_raw.append(read(Path(td) / "surfaces" / "website.html"))

        app_html, app_css = read_theme_surface(Path(td), i, "webapp", brand_prefix=brand_prefix)
        per_theme_app.append(app_html)
        per_theme_app_css.append(app_css)
        per_theme_app_raw.append(read(Path(td) / "surfaces" / "webapp.html"))

        mobile_html, mobile_css_scoped = read_theme_mobile_screens(Path(td), i, brand_prefix=brand_prefix)
        per_theme_mobile.append(mobile_html)
        per_theme_mobile_css.append(mobile_css_scoped)
        per_theme_mobile_raw.append(read(Path(td) / "surfaces" / "mobile.html"))
    web_surfaces_html = "\n".join(per_theme_web) + "\n"
    website_css = "\n".join(per_theme_web_css)
    app_surfaces_html = "\n".join(per_theme_app) + "\n"
    webapp_css = "\n".join(per_theme_app_css)
    mobile_css = "\n".join(per_theme_mobile_css)

    _check_surface_sanity(per_theme_web_raw, subset, "website")
    _check_surface_sanity(per_theme_app_raw, subset, "webapp")
    _check_surface_sanity(per_theme_mobile_raw, subset, "mobile")

    surfaces_out = web_surfaces_html + app_surfaces_html

    # For compare mode: one markup per theme per surface so the compare grid
    # shows each theme's distinct composition. Strip data-tf-theme from the
    # surface section so the parent cell's attribute controls CSS variable
    # scope.
    def _compare_variants(per_theme_markup: list[str], surface_class: str) -> list[str]:
        out = []
        for _ci, _html in enumerate(per_theme_markup, 1):
            _m = _html.replace(' data-tf-theme="%d"' % _ci, "")
            _m = _m.replace('class="surface %s"' % surface_class, 'class="surface %s is-active"' % surface_class)
            out.append(_m)
        return out

    web_markup = _compare_variants(per_theme_web, "surface-web")
    webapp_markup = _compare_variants(per_theme_app, "surface-app")

    # Mobile compare-grid cells are static (no runtime interactivity needed at
    # that scale) — embed each theme's own screens directly into a fresh copy
    # of the shared device-frame markup, rather than cloning via JS. The two
    # target divs are always empty in device-frames.html's own markup.
    mobile_frame_section = extract_section(frames, "surface-mobile")

    def _mobile_compare_variant(screens_html: str) -> str:
        variant = mobile_frame_section.replace(
            'class="surface surface-mobile"', 'class="surface surface-mobile is-active"'
        )
        variant = variant.replace(
            '<div class="screens" data-frame="ios" tabindex="0" aria-label="iOS screens, swipe to browse"></div>',
            '<div class="screens" data-frame="ios" tabindex="0" aria-label="iOS screens, swipe to browse">%s</div>' % screens_html,
        )
        variant = variant.replace(
            '<div class="screens" data-frame="android" tabindex="0" aria-label="Android screens, swipe to browse"></div>',
            '<div class="screens" data-frame="android" tabindex="0" aria-label="Android screens, swipe to browse">%s</div>' % screens_html,
        )
        return variant

    mobile_markup = [_mobile_compare_variant(s) for s in per_theme_mobile]

    compare = compare_html(subset, {"website": web_markup, "webapp": webapp_markup, "mobile": mobile_markup})
    brand = brands_html(subset)

    # Canvas mode: one <template id="tf-screens-N"> per theme, all inert until
    # gallery.shell.html's JS clones the active theme's own template into the
    # shared device frame's (empty) .screens containers on load and on every
    # theme switch — see fillMobileScreens() there.
    mobile_templates_html = "\n".join(
        '<template id="tf-screens-%d">%s</template>' % (i, s)
        for i, s in enumerate(per_theme_mobile, 1)
    )
    frames_out = frames + "\n" + mobile_templates_html

    # Inline the first available theme's motion.css as a global <style> block.
    # Keyframe names and utility classes (.tf-fade-up, .tf-stagger, etc.) are
    # identical across all themes; per-theme timing differences come from the
    # --tf-dur-* custom properties already in THEME_STYLES, which win via
    # selector specificity over motion.css's :root declarations.
    motion_css_inline = ""
    for td in (Path(tf_paths.resolve(create=False).current) / "themes").iterdir() if (Path(tf_paths.resolve(create=False).current) / "themes").exists() else []:
        mc = td / "brand" / "motion" / "motion.css"
        if mc.exists():
            motion_css_inline = read(mc)
            break

    out = shell
    repl = {
        "{{FONT_IMPORT}}": font_import(themes),
        "{{GALLERY_CSS}}": css,
        "{{THEME_STYLES}}": theme_styles,
        "{{WEBSITE_CSS}}": website_css,
        "{{WEBAPP_CSS}}": webapp_css,
        "{{MOBILE_CSS}}": mobile_css,
        "{{MOTION_CSS}}": motion_css_inline,
        "{{THEME_RAIL}}": rail,
        "{{SURFACES}}": surfaces_out,
        "{{DEVICE_FRAMES}}": frames_out,
        "{{COMPARE}}": compare,
        "{{BRAND_PANELS}}": brand,
        "{{DRAWERS}}": drawers,
        "{{PROJECT_NAME}}": html.escape(meta["project"]),
        "{{GEN_DATE}}": html.escape(meta["gen"]),
        "{{REFRESH_DATE}}": html.escape(meta["refresh"]),
        "{{THEME_COUNT}}": str(len(subset)),
        "{{DEFAULT_THEME}}": "1",
        # Theme 1's own court, used only as the opening state before any theme
        # switch has happened. THEME_COURTS below is what actually keeps each
        # theme honest once the user starts browsing.
        "{{DEFAULT_APPEAR}}": _natural_court(subset[0][0]) if subset else "light",
        # Every theme's natural court, in rail order. The main canvas used to
        # apply one global appearance derived from THEME 1 ALONE, so in a set
        # whose first theme is light-court, a dark-court theme selected from
        # the rail rendered its light alternative -- the "dark theme
        # disappeared" report, reproduced three runs running. It was never a
        # surface bug: theme_style_block() emits both resolutions correctly,
        # and compare_html() already bakes each cell to its own court. Only
        # the single-theme canvas ignored that. The shell now reads this array
        # whenever the user has not explicitly touched the Light/Dark toggle,
        # which is exactly the rule the compare grid has always followed.
        "{{THEME_COURTS}}": json.dumps([_natural_court(entry[0]) for entry in subset]),
        "{{DEFAULT_SURFACE}}": default_surface,
        "{{VERIFICATION_STATUS}}": _verification_status_html(subset, run or {}),
    }
    for k, v in repl.items():
        out = out.replace(k, v)
    return out


def _knowledge_label(paths, run: dict) -> str:
    """Header text for the Knowledge meta pair.

    Three states that must not be collapsed into one word:

      "2026-09-09"      knowledge was refreshed from the live web, on that date
      "seed (never refreshed)"
                        the knowledge base is the hand-authored baseline shipped
                        with the plugin -- a real, reportable condition
      "not recorded"    we cannot tell, because neither FRESHNESS.json nor
                        run.json was readable

    This previously read `run.get("knowledge_refreshed") or "seed"`, which
    reported a *missing run.json* as *unrefreshed knowledge*. Those are
    different facts and the wrong one is actively misleading: on a run whose
    knowledge had been refreshed two days earlier, the header said "seed".

    FRESHNESS.json is the authority here, not run.json -- tf_freshness.py owns
    it and updates it at refresh time, whereas run.json only carries a copy and
    is written at the end of a run. Preferring the authority also means the
    label is correct even when the gallery is rebuilt standalone.
    """
    fresh = load_json(getattr(paths, "freshness_json", None), {}) or {}
    domains = fresh.get("domains") or {}
    if domains:
        if all((d or {}).get("status") == "seed" for d in domains.values()):
            return "seed (never refreshed)"
        stamps = [
            (d or {}).get("refreshed", "")
            for d in domains.values()
            if (d or {}).get("refreshed")
        ]
        newest = fresh.get("last_full_refresh") or (max(stamps) if stamps else "")
        if newest:
            return newest[:10]

    stamped = (run.get("knowledge_refreshed") or "")[:10]
    return stamped or "not recorded"


def main(argv):
    want_json = "--json" in argv
    paths = tf_paths.resolve(create=True)
    run = load_json(paths.run_json, {}) or {}
    # ── Gate A: refuse to assemble if distinctiveness gate is dirty ──────────
    _distinct_script = Path(__file__).parent / "tf_distinct.py"
    if _distinct_script.is_file():
        import subprocess as _sp
        _themes_dir = str(paths.current / "themes")
        _dr = _sp.run(
            [sys.executable, str(_distinct_script), "--themes-dir", _themes_dir, "--json"],
            capture_output=True, text=True,
        )
        # Forward gate table (stderr) so the orchestrator always sees it before assembly
        if _dr.stderr:
            sys.stderr.write(_dr.stderr)
        if _dr.returncode == 1:
            try:
                _dj = json.loads(_dr.stdout or "{}")
            except Exception:
                _dj = {}
            _fails = _dj.get("failures", [])
            sys.stderr.write(
                "tf_gallery: ABORT — Gate A (tf_distinct.py) %d failure(s):\n" % len(_fails)
            )
            for _f in _fails:
                sys.stderr.write("  · %s\n" % _f.get("message", str(_f)))
            sys.stderr.write(
                "  Set run.json[\"gate_distinct_override\"]=true to bypass (user-confirmed proceed).\n"
            )
            if not run.get("gate_distinct_override"):
                print(json.dumps({"ok": False, "error": "Gate A failures block assembly", "failures": _fails}))
                return 1
    # ── Gate B: refuse to assemble over a CURRENT slop hard-stop ─────────────
    # A HIGH-severity anti-slop finding (scale(0) entrance, opacity:0 rest
    # state, overshoot easing, transition:all) used to be advisory in practice:
    # tf_slop.py exited 0 regardless, its top-level summary reported no
    # hard-stop total, and nothing downstream refused to build. The same HIGH
    # finding could therefore survive run after run while every command
    # reported success. Blocking here is what makes "HIGH" mean anything.
    #
    # Ordering: Gate B needs the preview.html this script writes, so the FIRST
    # build of a run legitimately precedes any slop.json and proceeds. From
    # then on, a hard-stop blocks rebuilds until it is fixed.
    #
    # Staleness guard, so the fix->rebuild cycle cannot deadlock. The dependency
    # chain is surfaces -> preview.html -> slop.json, and the question that
    # matters is whether the PREVIEW tf_slop judged still reflects the surfaces.
    # So compare preview.html against the surface files, NOT slop.json against
    # them: after a fix, tf_slop rewrites slop.json (making it the newest file
    # of the three) while still reading the stale preview it was handed, so a
    # slop.json-vs-surfaces comparison reports "current" for a finding that no
    # longer exists in the source. Verified by injecting a real scale(0), fixing
    # it, and watching that version of the guard deadlock: the finding lived
    # only in a preview.html this script then refused to regenerate.
    _slop_blockers: list[dict] = []
    _slop_stale: list[str] = []
    for _td in sorted((paths.current / "themes").glob("*")):
        _sj = _td / "slop.json"
        if not _sj.is_file():
            continue
        try:
            _sd = json.loads(read(_sj))
        except (OSError, ValueError):
            continue
        _hs = _sd.get("hard_stop") or []
        if not _hs:
            continue
        _surf = list((_td / "surfaces").glob("*")) if (_td / "surfaces").is_dir() else []
        _newest_surface = max((p.stat().st_mtime for p in _surf), default=0)
        _prev = _td / "preview.html"
        _prev_mtime = _prev.stat().st_mtime if _prev.is_file() else 0
        if _newest_surface > _prev_mtime:
            _slop_stale.append(_td.name)
            continue
        for _f in _hs:
            _slop_blockers.append({
                "theme": _td.name,
                "rule": _f.get("rule") or _f.get("antipattern") or "?",
                "message": (_f.get("message") or "")[:200],
            })
    for _name in _slop_stale:
        sys.stderr.write(
            "tf_gallery: NOTE — %s records a hard-stop, but the preview.html it was judged from "
            "predates that theme's surface files; treating the finding as stale and rebuilding. "
            "Re-run tf_slop.py afterwards to confirm it is resolved.\n" % _name
        )
    if _slop_blockers:
        sys.stderr.write(
            "tf_gallery: ABORT — Gate B (tf_slop.py) %d HIGH hard-stop finding(s):\n"
            % len(_slop_blockers)
        )
        for _b in _slop_blockers:
            sys.stderr.write("  · %s [%s] %s\n" % (_b["theme"], _b["rule"], _b["message"]))
        sys.stderr.write(
            "  Fix the surface, then re-run tf_slop.py. Set "
            "run.json[\"gate_slop_override\"]=true to bypass (user-confirmed proceed).\n"
        )
        if not run.get("gate_slop_override"):
            print(json.dumps({
                "ok": False,
                "error": "Gate B hard-stop findings block assembly",
                "hard_stops": _slop_blockers,
            }))
            return 1

    tdir = paths.templates
    if not tdir:
        print(json.dumps({"ok": False, "error": "cannot locate plugin templates"}))
        return 1

    shell = read(tdir / "gallery.shell.html")
    css = read(tdir / "gallery.css")
    # a11y-reset.css: the one CSS file every bespoke theme shares (confirmed
    # carve-out — pure accessibility/behavior, zero visual identity). Appended
    # after gallery.css so its rules aren't accidentally overridden by
    # shared-component specificity.
    a11y_reset = read(tdir / "a11y-reset.css")
    if a11y_reset:
        css = css + "\n" + a11y_reset
    else:
        sys.stderr.write("tf_gallery: WARNING — templates/a11y-reset.css not found\n")
    frames = read(tdir / "device-frames.html")

    # NOTE: preview.partials.html, preview.surfaces.html, templates/sections/
    # hero-*.html, and the surfaces.content.json {{SC_*}} substitution
    # mechanism they fed are gone as of Phase 4 cleanup (the bespoke-
    # composition rewrite's website/webapp/mobile surfaces all migrated off
    # them in Phases 1-3; nothing read them anymore by the time they were
    # deleted). content-brief.json is the one content model now, for all
    # three surfaces — see read_theme_surface() / read_theme_mobile_screens().

    theme_entries = run.get("themes", [])
    if not theme_entries:
        # scan themes dir
        theme_entries = []
        if paths.current_themes.is_dir():
            for child in sorted(paths.current_themes.iterdir()):
                if child.is_dir() and (child / "theme.json").is_file():
                    theme_entries.append({"dir": "themes/" + child.name})

    themes = []
    for e in theme_entries:
        d = paths.current / e["dir"] if not Path(e["dir"]).is_absolute() else Path(e["dir"])
        theme = load_json(d / "theme.json")
        if not theme:
            continue
        a11y = load_json(d / "a11y.json", {})
        native = load_json(d / "native.json", {})
        themes.append((theme, d, a11y, native))

    if not themes:
        print(json.dumps({"ok": False, "error": "no themes found under current/themes"}))
        return 1

    brief = load_json(paths.brief_product_json, {}) or {}
    _brief_design = load_json(paths.brief_design_json, {}) or {}
    brief.update(_brief_design)
    primary_platform = run.get("primary_platform") or brief.get("primary_platform") or "web"
    meta = {
        # No fallback to run.get("brief_summary"): that field is a full
        # prose sentence ("Voltside — electronics and appliance store. Six
        # slots pre-assigned..."), not a short name -- if brief.name were
        # ever missing, the header's compact "Project: ..." meta pair would
        # silently render that whole sentence instead. A missing name is
        # a data gap to show plainly ("Your project"), not one to paper
        # over with a differently-shaped field.
        "project": brief.get("name") or "Your project",
        # "not recorded" != "—". run.json is written at the END of a run, so a
        # gallery assembled before it exists (or after a crash) has no date to
        # show. Saying so plainly beats an em dash that reads like a rendering
        # bug, and beats inventing datetime.now(), which would assert a
        # generation time this function did not observe.
        "gen": (run.get("generated_at") or "")[:10] or "not recorded",
        "refresh": _knowledge_label(paths, run),
    }

    # gallery
    gallery = build(shell, css, frames, themes, meta, primary_platform, run=run)
    paths.gallery_html.write_text(gallery, encoding="utf-8")

    # per-theme standalone previews
    previews = []
    for i, (theme, d, _a, _n) in enumerate(themes, 1):
        one = build(shell, css, frames, themes, meta, primary_platform,
                    only_theme=i, run=run)
        (d / "preview.html").write_text(one, encoding="utf-8")
        previews.append(str(d / "preview.html"))

    size = paths.gallery_html.stat().st_size
    result = {"ok": True, "gallery": str(paths.gallery_html), "size_bytes": size,
              "size_mb": round(size / 1048576, 3), "themes": len(themes), "previews": previews}
    sys.stderr.write("tf_gallery: wrote %s (%.2f MB, %d themes)\n"
                     % (paths.gallery_html, result["size_mb"], len(themes)))

    # Record this run into $TF_HOME/used.md so future runs don't recycle this
    # set's hues/fonts/composition. Reaching this line already proves Gate A
    # (tf_distinct.py) passed, since main() aborts before this point otherwise.
    # Run as a subprocess (not an in-process import call): tf_ledger's error
    # paths call sys.exit(), which would propagate up and kill tf_gallery.py
    # itself if called in-process. Best-effort: a ledger failure must never
    # block gallery delivery. The ledger call is idempotent, so tf_gallery.py
    # re-runs later in the same session (after design-critic, after manual
    # fixes) never duplicate rows.
    _ledger_script = Path(__file__).parent / "tf_ledger.py"
    if _ledger_script.is_file():
        import subprocess as _sp2
        try:
            _lr = _sp2.run(
                [sys.executable, str(_ledger_script), "--json"],
                capture_output=True, text=True,
            )
            if _lr.stderr:
                sys.stderr.write(_lr.stderr)
            _lj = json.loads(_lr.stdout or "{}")
            result["ledger"] = _lj
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("tf_gallery: WARNING — used.md ledger recording failed: %s\n" % exc)
            result["ledger"] = {"ok": False, "error": str(exc)}

    if want_json:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        import traceback
        sys.stderr.write("tf_gallery: unexpected error: %s\n%s\n" % (exc, traceback.format_exc()))
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
