#!/usr/bin/env python3
"""tf_distinct.py -- hard distinctiveness gate for a generated theme set.

Reads all theme.json files in <themes-dir>, computes pairwise primary/accent
hue gaps, background lightness (light mode), and display font usage.
Exits 0 on pass, 1 on failure (with JSON report), 2 on unexpected error.

Also runs two advisory-only cross-cutting checks that append to `warnings`
(never `failures`, never affect the exit code): Gate 18, structural
similarity via tf_structure.py (compares this run's six themes' rendered
surfaces against each other), and Gate 19, cross-run ledger conflicts via
$TF_HOME/used.md (compares this run's six themes against prior runs' recorded
hue/font/motion -- see `_check_used_ledger`). Gate 19 exists because, before
it, used.md's "avoid a hue/font/motion clash with a prior run" rule was
enforced purely by theme-designer reading the file and trying to comply --
nothing verified that it actually did. This is that verification.

Also runs Gate 20, motion/design_language cohesion via tf_motion_cohesion.py --
a mechanical re-derivation of design-critic.md's motion-cohesion lookup table
(design_language -> expected motion.character/duration baseline), also
advisory-only.

Usage:
    python3 tf_distinct.py [--themes-dir <dir>] [--slot-d <slug>] [--used-md <path>] [--json]

Acceptance:
    I26 -- default run exits 0 when all gates pass.
    I27 -- exits 1 when any two accent hues are within 20°.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Thresholds
# ─────────────────────────────────────────────────────────────────────────────

PRIM_GAP_MIN  = 20.0  # minimum circular gap between any two primary hues (°)
ACCENT_GAP_MIN= 20.0  # minimum circular gap between any two accent hues (°)
BG_DARK_MAX   = 0.30  # OKLCH L: at least one light-mode bg must be ≤ this
FONT_MAX_USES = 2     # display font may appear on at most this many themes

# Gate 19 (cross-run used.md ledger) -- mirrors used.md's own "Avoidance
# constraints" section verbatim (15° hue band, 20-run decay window).
LEDGER_HUE_GAP_MIN = 15.0
LEDGER_MAX_LIVE_RUNS = 20


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_oklch(css: str) -> tuple[float, float, float] | None:
    """Parse the first oklch(L C H) triple found in *css*, return floats or None."""
    m = re.search(r'oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)', css or '')
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    return None


def _hex_to_lum(hex_str: str) -> float:
    """Approximate OKLCH-L from sRGB hex (fallback when oklch absent)."""
    h = hex_str.lstrip('#')
    if len(h) == 6:
        r = int(h[0:2], 16) / 255
        g = int(h[2:4], 16) / 255
        b = int(h[4:6], 16) / 255
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    return 0.5


def _hue_gap(h1: float, h2: float) -> float:
    """Circular angular distance between two hues (result: 0–180)."""
    d = abs(h1 - h2) % 360.0
    return min(d, 360.0 - d)


def _nested(obj: dict, *keys: str) -> dict:
    node = obj
    for k in keys:
        if not isinstance(node, dict):
            return {}
        node = node.get(k, {})
    return node if isinstance(node, dict) else {}


# ─────────────────────────────────────────────────────────────────────────────
# Theme loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_theme(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        sys.stderr.write(f'tf_distinct: cannot read {path}: {exc}\n')
        return None

    color = data.get('color', {})
    light = color.get('light', {})

    # Primary hue from light.primary.css
    prim_css = _nested(light, 'primary').get('css', '')
    prim_hex = _nested(light, 'primary').get('hex', '')
    prim_lch    = _parse_oklch(prim_css)
    prim_hue    = prim_lch[2] if prim_lch else None
    prim_chroma = prim_lch[1] if prim_lch else None
    # Achromatic primaries (chroma < 0.03) have meaningless hue — treat as neutral
    prim_neutral = prim_chroma is not None and prim_chroma < 0.03
    if prim_neutral:
        prim_hue = None  # skip hue gating for achromatic primaries

    # Accent hue + chroma from light.accent.css
    acc_css    = _nested(light, 'accent').get('css', '')
    acc_hex    = _nested(light, 'accent').get('hex', '')
    acc_lch    = _parse_oklch(acc_css)
    acc_hue    = acc_lch[2] if acc_lch else None
    acc_chroma = acc_lch[1] if acc_lch else None

    # Background lightness from light.background.css (light mode = gallery default view)
    bg_css = _nested(light, 'background').get('css', '')
    bg_hex = _nested(light, 'background').get('hex', '')
    bg_lch = _parse_oklch(bg_css)
    if bg_lch:
        bg_l = bg_lch[0]
    elif bg_hex:
        bg_l = _hex_to_lum(bg_hex)
    else:
        bg_l = 1.0

    comp = data.get('composition', {})
    motion = data.get('motion', {})
    dials = data.get('dials', {})
    _mb = motion.get('motion_budget')
    motion_budget = _mb if isinstance(_mb, dict) else {}
    motion_rejected = motion.get('rejected') if isinstance(motion.get('rejected'), list) else []
    motion_delight  = motion.get('delight')  if isinstance(motion.get('delight'),  list) else []

    intensity_raw = comp.get('intensity')
    if intensity_raw is None:
        sys.stderr.write(
            f"tf_distinct: {data.get('slug', path.parent.name)}: "
            f"composition.intensity missing — defaulting to \"balanced\"\n"
        )
        intensity_raw = 'balanced'

    return {
        'slug':         data.get('slug', path.parent.name),
        'slot':         data.get('slot', '?'),
        'direction':    data.get('direction', ''),
        'primary_hex':    prim_hex or '#??????',
        'primary_hue':    round(prim_hue, 1)    if prim_hue    is not None else None,
        'primary_chroma': round(prim_chroma, 3) if prim_chroma is not None else None,
        'primary_neutral': prim_neutral,
        'accent_hex':     acc_hex or '#??????',
        'accent_hue':     round(acc_hue, 1)     if acc_hue     is not None else None,
        'accent_chroma':  round(acc_chroma, 3)  if acc_chroma  is not None else None,
        'bg_l':           round(bg_l, 3),
        'display_font':   data.get('typography', {}).get('display', {}).get('family', 'unknown'),
        # body/mono are extracted for Gate 21 (typographic identity). Gate 5
        # only ever looked at `display`, so a theme could borrow every one of
        # its three faces from siblings and still pass every font check.
        'body_font':      data.get('typography', {}).get('body', {}).get('family', 'unknown'),
        'mono_font':      data.get('typography', {}).get('mono', {}).get('family', 'unknown'),
        'structural_brief': comp.get('structural_brief', ''),
        'design_language':  comp.get('design_language', ''),
        'intensity':        intensity_raw,
        # Canonical field only: motion.signature_type (short kebab-slug for
        # exact-match gating). No fallback to motion.signature (a multi-sentence
        # prose description -- the wrong shape for gating, since two themes'
        # prose descriptions will never collide even when their actual
        # signature type does) or the legacy visual.signature_motion path
        # (belongs to a schema generation that no longer exists). A three-way
        # hedge here previously masked a real bug in tf_ledger.py where the
        # ledger's own "signature type" column silently recorded a different
        # field (motion.character) for every historical row -- see
        # tf_ledger.py's _build_row for the full history. If signature_type
        # is genuinely missing, that is the finding Gate 8 below reports; it
        # is not something to paper over with a differently-shaped fallback.
        'signature_type': motion.get('signature_type', ''),
        'design_variance':  dials.get('design_variance'),
        'motion_intensity': dials.get('motion_intensity'),
        'visual_density':   dials.get('visual_density'),
        'ambition':         comp.get('ambition', ''),
        'motion_budget':    motion_budget,
        'motion_rejected':  motion_rejected,
        'motion_delight':   motion_delight,
        'path':             str(path),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pairwise gap computation
# ─────────────────────────────────────────────────────────────────────────────

def _pairwise(themes: list[dict], hue_key: str) -> list[dict]:
    records = []
    for i in range(len(themes)):
        for j in range(i + 1, len(themes)):
            a, b = themes[i], themes[j]
            ha, hb = a.get(hue_key), b.get(hue_key)
            gap = round(_hue_gap(ha, hb), 1) if (ha is not None and hb is not None) else None
            records.append({
                'slot_a': a['slot'], 'slug_a': a['slug'], 'hue_a': ha,
                'slot_b': b['slot'], 'slug_b': b['slug'], 'hue_b': hb,
                'gap': gap,
            })
    return records


# ─────────────────────────────────────────────────────────────────────────────
# Hue span helper
# ─────────────────────────────────────────────────────────────────────────────

def _hue_span(hues: list[float]) -> float:
    """Degrees occupied by a set of hues (360° minus the widest empty arc)."""
    if len(hues) < 2:
        return 0.0
    s = sorted(h % 360.0 for h in hues)
    gaps = [s[i + 1] - s[i] for i in range(len(s) - 1)]
    gaps.append(s[0] + 360.0 - s[-1])  # wrap-around gap
    return round(360.0 - max(gaps), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Gate evaluation
# ─────────────────────────────────────────────────────────────────────────────

def _run_gates(themes: list[dict], slot_d_slug: str | None) -> tuple[list[dict], list[dict]]:
    """Return (failures, regeneration_hints)."""
    failures: list[dict] = []
    hints:    list[dict] = []

    # ── Gate 1: primary hue gap ───────────────────────────────────────────────
    pg = _pairwise(themes, 'primary_hue')
    valid_pg = [r for r in pg if r['gap'] is not None]
    if valid_pg:
        worst = min(valid_pg, key=lambda r: r['gap'])
        if worst['gap'] < PRIM_GAP_MIN:
            failures.append({
                'gate':    'primary_hue_gap',
                'message': (
                    f"Slots {worst['slot_a']} ({worst['slug_a']}, "
                    f"hue {worst['hue_a']:.0f}°) and "
                    f"{worst['slot_b']} ({worst['slug_b']}, "
                    f"hue {worst['hue_b']:.0f}°) gap={worst['gap']:.1f}° "
                    f"< {PRIM_GAP_MIN:.0f}° required"
                ),
                'gap': worst['gap'],
                'slug_a': worst['slug_a'],
                'slug_b': worst['slug_b'],
                'hue_a': worst['hue_a'],
                'hue_b': worst['hue_b'],
            })
            taken = [t['primary_hue'] for t in themes
                     if t['primary_hue'] is not None and t['slug'] != worst['slug_b']]
            hints.append({
                'slug': worst['slug_b'],
                'constraint': (
                    f"primary hue must differ from {[round(h) for h in taken]} "
                    f"by ≥{PRIM_GAP_MIN:.0f}°"
                ),
                'exclude_primary_hues': [round(h) for h in taken],
            })

    # ── Gate 1b: co-neutral primaries ────────────────────────────────────────
    # Two or more themes with near-achromatic primaries both read as black/white —
    # compare lightness of their primaries and flag the pair as indistinct.
    neutral_themes = [t for t in themes if t.get('primary_neutral')]
    if len(neutral_themes) >= 2:
        neutral_slugs = [t['slug'] for t in neutral_themes]
        failures.append({
            'gate':    'co_neutral_primary',
            'message': (
                f"Multiple themes have near-achromatic primaries (chroma < 0.03): "
                f"{neutral_slugs} — both read as black/white at a glance; "
                f"at least one must use a chromatic primary."
            ),
            'neutral_slugs': neutral_slugs,
        })
        for t in neutral_themes[1:]:
            hints.append({
                'slug': t['slug'],
                'constraint': (
                    'primary must have OKLCH chroma ≥ 0.03 — cannot be near-black or near-white'
                ),
            })

    # ── Gate 2: accent hue gap ────────────────────────────────────────────────
    ag = _pairwise(themes, 'accent_hue')
    valid_ag = [r for r in ag if r['gap'] is not None]
    if valid_ag:
        worst = min(valid_ag, key=lambda r: r['gap'])
        if worst['gap'] < ACCENT_GAP_MIN:
            failures.append({
                'gate':    'accent_hue_gap',
                'message': (
                    f"Slots {worst['slot_a']} ({worst['slug_a']}, "
                    f"hue {worst['hue_a']:.0f}°) and "
                    f"{worst['slot_b']} ({worst['slug_b']}, "
                    f"hue {worst['hue_b']:.0f}°) gap={worst['gap']:.1f}° "
                    f"< {ACCENT_GAP_MIN:.0f}° required"
                ),
                'gap': worst['gap'],
                'slug_a': worst['slug_a'],
                'slug_b': worst['slug_b'],
                'hue_a': worst['hue_a'],
                'hue_b': worst['hue_b'],
            })
            taken = [t['accent_hue'] for t in themes
                     if t['accent_hue'] is not None and t['slug'] != worst['slug_b']]
            hints.append({
                'slug': worst['slug_b'],
                'constraint': (
                    f"accent hue must differ from {[round(h) for h in taken]} "
                    f"by ≥{ACCENT_GAP_MIN:.0f}°"
                ),
                'exclude_accent_hues': [round(h) for h in taken],
            })

    # ── Gate 2b: cross-type hue proximity (accent vs other themes' primaries) ──
    # Two themes with the same coral color in different roles still look identical.
    _cross_seen: set[tuple] = set()
    for _a in themes:
        for _b in themes:
            if _a['slug'] == _b['slug']:
                continue
            _key = (min(_a['slug'], _b['slug']), max(_a['slug'], _b['slug']),
                    'acc_prim' if _a['slug'] < _b['slug'] else 'prim_acc')
            if _key in _cross_seen:
                continue
            _ah = _a.get('accent_hue')
            _bh = _b.get('primary_hue')
            if _ah is None or _bh is None:
                continue
            # Skip near-neutral colors — chroma < 0.04 means hue is perceptually meaningless
            if (_a.get('accent_chroma') or 0.0) < 0.04 or (_b.get('primary_chroma') or 0.0) < 0.04:
                continue
            _gap = round(_hue_gap(_ah, _bh), 1)
            if _gap < ACCENT_GAP_MIN:
                _cross_seen.add(_key)
                failures.append({
                    'gate':    'cross_type_hue_proximity',
                    'message': (
                        f"accent of '{_a['slug']}' ({_a['accent_hex']}, hue {_ah:.0f}°) is "
                        f"{_gap:.1f}° from primary of '{_b['slug']}' ({_b['primary_hex']}, "
                        f"hue {_bh:.0f}°) — visually identical color in different roles"
                    ),
                    'gap': _gap,
                    'slug_accent': _a['slug'],
                    'slug_primary': _b['slug'],
                })
                hints.append({
                    'slug': _a['slug'],
                    'constraint': (
                        f"accent ({_a['accent_hex']}, hue {_ah:.0f}°) too close to "
                        f"'{_b['slug']}' primary (hue {_bh:.0f}°) — accent must differ "
                        f"from all other themes' primaries by ≥{ACCENT_GAP_MIN:.0f}°"
                    ),
                })

    # ── Gate 3: at least one dark light-mode background ──────────────────────
    bg_ls = [t['bg_l'] for t in themes]
    dark_count = sum(1 for l in bg_ls if l <= BG_DARK_MAX)
    if dark_count == 0:
        failures.append({
            'gate':     'bg_lightness',
            'message':  (
                f"No theme has a light-mode background L ≤ {BG_DARK_MAX}; "
                f"at least one dark-court theme required "
                f"(lowest found: {min(bg_ls):.3f})"
            ),
            'min_bg_l':    round(min(bg_ls), 3),
            'dark_count':  0,
        })
        # Prefer Slot D as the natural dark candidate; fall back to first theme
        target = next((t for t in themes if t['slot'] == 'D'), themes[0])
        hints.append({
            'slug': target['slug'],
            'constraint': (
                'require_background_lightness_max: 0.30 '
                '— light-mode ground must be dark (e.g., charcoal ≤ oklch(0.25 0.01 N))'
            ),
        })

    # ── Gate 4: Slot D hard background constraint ─────────────────────────────
    slot_d = None
    if slot_d_slug:
        slot_d = next((t for t in themes if t['slug'] == slot_d_slug), None)
    if slot_d is None:
        slot_d = next((t for t in themes if t['slot'] == 'D'), None)

    if slot_d is not None and slot_d['bg_l'] > BG_DARK_MAX:
        failures.append({
            'gate':    'slot_d_bg',
            'message': (
                f"Slot D ({slot_d['slug']}) light-mode bg L="
                f"{slot_d['bg_l']:.3f} > {BG_DARK_MAX} — "
                "Slot D is always dark-first"
            ),
            'slug':  slot_d['slug'],
            'bg_l':  slot_d['bg_l'],
        })
        hints.append({
            'slug': slot_d['slug'],
            'constraint': (
                'Slot D must use a dark-court ground in both modes: '
                'color.light.background OKLCH L ≤ 0.30'
            ),
        })

    # ── Gate 4b: background lightness distribution ───────────────────────────
    # No more than 3 themes per 10-point OKLCH L band (prevents visual clustering)
    for _band_start in range(0, 100, 10):
        _band_end = _band_start + 10
        _in_band = [t for t in themes if _band_start <= round(t['bg_l'] * 100) < _band_end]
        if len(_in_band) > 3:
            _band_slugs = [t['slug'] for t in _in_band]
            failures.append({
                'gate':    'bg_lightness_distribution',
                'message': (
                    f"Band L={_band_start}–{_band_end} contains {len(_in_band)} themes "
                    f"({', '.join(_band_slugs)}) — max 3 per 10-point lightness band."
                ),
                'band':  f'{_band_start}–{_band_end}',
                'slugs': _band_slugs,
            })
            hints.append({
                'slug': _band_slugs[-1],
                'constraint': (
                    f'background lightness must move outside the '
                    f'{_band_start}–{_band_end} band (overcrowded)'
                ),
            })

    # ── Gate 5: display font diversity ───────────────────────────────────────
    font_counts = Counter(t['display_font'] for t in themes)
    for font, count in font_counts.items():
        if count > FONT_MAX_USES:
            slugs = [t['slug'] for t in themes if t['display_font'] == font]
            failures.append({
                'gate':    'font_diversity',
                'message': (
                    f"Display font '{font}' used on {count} themes "
                    f"({', '.join(slugs)}); max {FONT_MAX_USES}"
                ),
                'font':  font,
                'count': count,
                'slugs': slugs,
            })
            hints.append({
                'slug': slugs[-1],
                'constraint': (
                    f"display font must differ from: "
                    f"{slugs[:-1]!r} — choose a distinct display typeface"
                ),
                'exclude_display_fonts': slugs[:-1],
            })

    # Gates 6/7/9 (hero_archetype uniqueness, grid_strategy+nav_pattern pair
    # uniqueness, section_inventory uniqueness) were retired with the
    # bespoke-composition rewrite — those theme.json fields no longer exist
    # (see templates/theme.schema.json's composition block), so these checks
    # would hard-fail every theme unconditionally. tf_structure.py (Gate 18,
    # wired below as an advisory warning) measures the rendered structure
    # these gates used to approximate via self-reported enum labels.

    # ── Gate 8: signature_type uniqueness ───────────────────────────────────
    motion_seen: dict[str, str] = {}
    for t in themes:
        motion = t.get('signature_type', '')
        if not motion:
            failures.append({
                'gate':    'composition_signature_type',
                'message': f"'{t['slug']}' missing motion.signature_type — required in theme.json motion block",
                'slug':    t['slug'],
            })
            hints.append({'slug': t['slug'], 'constraint':
                'set motion.signature_type to a unique kebab-slug: scroll-driven-diagram, '
                'cursor-reactive, magnetic-buttons, text-scramble, parallax-layers, '
                'draw-on-scroll, particle-field, counter-sequences'})
            continue
        if motion in motion_seen:
            failures.append({
                'gate':    'composition_signature_type',
                'message': (
                    f"signature_type '{motion}' used by both "
                    f"'{motion_seen[motion]}' and '{t['slug']}' "
                    f"— each theme must have a distinctive, exclusive interaction"
                ),
                'motion': motion,
                'slug_a': motion_seen[motion],
                'slug_b': t['slug'],
            })
            hints.append({
                'slug': t['slug'],
                'constraint': (
                    f"signature_type must differ from "
                    f"{list(motion_seen.keys())} — "
                    f"choose a unique interaction: scroll-driven-diagram, "
                    f"cursor-reactive, magnetic-buttons, text-scramble, "
                    f"parallax-layers, draw-on-scroll, particle-field, "
                    f"counter-sequences"
                ),
            })
        else:
            motion_seen[motion] = t['slug']

    # ── Gate 10: design_variance span ────────────────────────────────────────────
    # The six themes must span at least 4 points on design_variance (1-10) so the
    # set offers a real range, not six themes at the same layout intensity.
    dv_vals = [t.get('design_variance') for t in themes if t.get('design_variance') is not None]
    if len(dv_vals) >= 3:
        dv_span = max(dv_vals) - min(dv_vals)
        if dv_span < 4:
            failures.append({
                'gate':    'dials_design_variance_span',
                'message': (
                    f"design_variance span = {dv_span} (values: {sorted(dv_vals)}) "
                    f"< 4 required — six themes must offer real layout range, "
                    f"not cluster at one intensity"
                ),
                'span':  dv_span,
                'values': sorted(dv_vals),
            })
            # hint: nudge extremes outward
            min_t = min(themes, key=lambda t: t.get('design_variance') or 5)
            max_t = max(themes, key=lambda t: t.get('design_variance') or 5)
            if min_t['slug'] == max_t['slug']:
                hints.append({'slug': themes[-1]['slug'],
                              'constraint': 'set dials.design_variance to expand the set range to ≥4'})
            else:
                hints.append({'slug': min_t['slug'],
                              'constraint': f'reduce dials.design_variance to expand range to ≥4'})

    # ── Gate 11: design_language uniqueness ──────────────────────────────────────
    lang_seen: dict[str, str] = {}
    for t in themes:
        lang = t.get('design_language', '')
        if not lang:
            failures.append({
                'gate':    'composition_design_language',
                'message': f"'{t['slug']}' missing design_language — required in composition block",
                'slug':    t['slug'],
            })
            hints.append({'slug': t['slug'],
                'constraint': (
                    'composition.design_language required: a kebab-case slug naming '
                    'this theme\'s direction. Open vocabulary, and there is no '
                    'default list to fall back on. When the brief names a style, '
                    'use the brief\'s own word (neobrutalism, hand-drawn, '
                    'parallax-scrolling). When it names none, DERIVE a slug from '
                    'this theme\'s own thesis and the brief\'s subject matter, '
                    'audience and domain — the vernacular of the thing being '
                    'designed, not a generic register borrowed from a fixed set.'
                )})
            continue
        if lang in lang_seen:
            failures.append({
                'gate':    'composition_design_language',
                'message': (
                    f"design_language '{lang}' used by both '{lang_seen[lang]}' "
                    f"and '{t['slug']}' — each theme must occupy a distinct design language"
                ),
                'lang':   lang,
                'slug_a': lang_seen[lang],
                'slug_b': t['slug'],
            })
            hints.append({'slug': t['slug'],
                'constraint': (
                    f"design_language must differ from {list(lang_seen.keys())} — "
                    f"any distinct kebab-case slug is valid (open vocabulary); "
                    f"prefer one the brief actually names"
                )})
        else:
            lang_seen[lang] = t['slug']

    # ── Gate 12: intensity distribution ──────────────────────────────────────
    # Across the 6-theme set, composition.intensity must span ≥3 distinct values
    # and no single value may be used by more than 2 themes.
    INTENSITY_MIN_DISTINCT  = 3
    INTENSITY_MAX_PER_VALUE = 2
    intensity_counts: Counter = Counter(t.get('intensity', 'balanced') for t in themes)
    distinct_count = len(intensity_counts)
    if distinct_count < INTENSITY_MIN_DISTINCT:
        all_slugs = [t['slug'] for t in themes]
        failures.append({
            'gate':    'intensity_span',
            'message': (
                f"intensity-span-too-narrow: only {distinct_count} distinct intensity "
                f"values across {all_slugs} — need ≥3 to span the energy range"
            ),
            'distinct': distinct_count,
            'slugs':    all_slugs,
        })
        hints.append({
            'slug': themes[-1]['slug'],
            'constraint': (
                'assign more varied intensity values — need ≥3 distinct values from: '
                'distilled, quiet, balanced, bold, overdrive'
            ),
        })
    for iv, count in intensity_counts.items():
        if count > INTENSITY_MAX_PER_VALUE:
            iv_slugs = [t['slug'] for t in themes if t.get('intensity', 'balanced') == iv]
            failures.append({
                'gate':    'intensity_distribution',
                'message': (
                    f"intensity-overused: '{iv}' appears in {count} themes "
                    f"({iv_slugs}) — max 2 themes per intensity value"
                ),
                'value':  iv,
                'count':  count,
                'slugs':  iv_slugs,
            })
            hints.append({
                'slug': iv_slugs[-1],
                'constraint': (
                    f"change composition.intensity away from '{iv}' — "
                    f"that value already used by {iv_slugs[:-1]}; "
                    f"choose from: distilled, quiet, balanced, bold, overdrive"
                ),
            })

    # ── Gate 13: motion_budget presence and valid surface values ─────────────
    _BUDGET_VALID = {'full', 'moderate', 'near-imperceptible', 'feedback-only', 'delight', 'sparse'}
    for t in themes:
        mb = t.get('motion_budget', {})
        if not mb:
            failures.append({
                'gate':    'motion_budget',
                'message': (
                    f"'{t['slug']}' missing motion.motion_budget — "
                    f"required object with website/webapp/mobile keys"
                ),
                'slug': t['slug'],
            })
            hints.append({'slug': t['slug'], 'constraint':
                'add motion.motion_budget: {"website": "full|moderate|sparse", '
                '"webapp": "moderate|near-imperceptible", '
                '"mobile": {"onboarding": "delight", "feed": "feedback-only", "detail": "feedback-only"}}'})
        else:
            for _surf in ('website', 'webapp'):
                _val = mb.get(_surf, '')
                if not _val:
                    failures.append({
                        'gate':    'motion_budget',
                        'message': f"'{t['slug']}' motion.motion_budget.{_surf} missing",
                        'slug':    t['slug'],
                    })
                elif _val not in _BUDGET_VALID:
                    failures.append({
                        'gate':    'motion_budget',
                        'message': (
                            f"'{t['slug']}' motion.motion_budget.{_surf}='{_val}' invalid; "
                            f"must be one of: {sorted(_BUDGET_VALID)}"
                        ),
                        'slug':    t['slug'],
                    })

    # ── Gate 14: composition.ambition non-empty ────────────────────────────────
    for t in themes:
        if not t.get('ambition', '').strip():
            failures.append({
                'gate':    'composition_ambition',
                'message': (
                    f"'{t['slug']}' missing composition.ambition — "
                    f"required string explaining what makes this theme exceed the obvious"
                ),
                'slug': t['slug'],
            })
            hints.append({'slug': t['slug'], 'constraint':
                'add composition.ambition: one paragraph describing what exceeds the obvious interpretation — '
                'Emil: "the rejected list is what separates a motion system from an animation wishlist"'})

    # ── Gate 15: motion.rejected — at least 2 named discarded animations ──────
    for t in themes:
        rejected = t.get('motion_rejected', [])
        if len(rejected) < 2:
            failures.append({
                'gate':    'motion_rejected',
                'message': (
                    f"'{t['slug']}' has {len(rejected)} rejected animation(s) (need ≥ 2) — "
                    f"a motion system without a rejected list is an animation wishlist"
                ),
                'slug':  t['slug'],
                'count': len(rejected),
            })
            hints.append({'slug': t['slug'], 'constraint':
                'add motion.rejected: [{"name": "cursor-trail", "reason": "..."}, ...] — '
                'minimum 2 named concepts deliberately excluded with explicit reasons'})

    # ── Gate 16: motion.delight — at least 1 delight moment ──────────────────
    for t in themes:
        delight = t.get('motion_delight', [])
        if not delight:
            failures.append({
                'gate':    'motion_delight',
                'message': (
                    f"'{t['slug']}' missing motion.delight — "
                    f"at least 1 named delight interaction required"
                ),
                'slug': t['slug'],
            })
            hints.append({'slug': t['slug'], 'constraint':
                'add motion.delight: ["..."] — one or more named moments that reward deliberate user action'})

    # ── Gate 17: README.md must have ## Rejected Animations section ───────────
    for t in themes:
        _readme = Path(t['path']).parent / 'README.md'
        if _readme.exists():
            try:
                _rc = _readme.read_text(encoding='utf-8', errors='replace')
                if 'rejected animations' not in _rc.lower():
                    failures.append({
                        'gate':    'readme_rejected_animations',
                        'message': (
                            f"'{t['slug']}' README.md missing '## Rejected Animations' section — "
                            f"Emil: this is what separates a motion system from an animation wishlist"
                        ),
                        'slug': t['slug'],
                    })
                    hints.append({'slug': t['slug'], 'constraint':
                        'add ## Rejected Animations section to README.md listing named motion '
                        'concepts considered and deliberately discarded, with reasons'})
            except Exception:
                pass
        else:
            failures.append({
                'gate':    'readme_rejected_animations',
                'message': f"'{t['slug']}' missing README.md — required for motion system documentation",
                'slug':    t['slug'],
            })

    # Deduplicate hints — keep last entry per slug
    seen: set[str] = set()
    dedup: list[dict] = []
    for h in reversed(hints):
        if h['slug'] not in seen:
            seen.add(h['slug'])
            dedup.insert(0, h)

    return failures, dedup


# ─────────────────────────────────────────────────────────────────────────────
# Letter-not-spirit detection
# ─────────────────────────────────────────────────────────────────────────────

def _letter_not_spirit(themes: list[dict]) -> list[dict]:
    """Detect passes that cleared the threshold without satisfying the intent.

    These do not decrement the budget and do not block assembly.  They are
    reported as warnings so the orchestrator and critic can decide whether to
    act on them.
    """
    warnings: list[dict] = []
    n = len(themes)

    # ── Background homogeneity ────────────────────────────────────────────────
    # Even if the dark-bg gate passes, six near-white backgrounds mean nobody
    # actually chose a background — they all defaulted.
    near_white = [t for t in themes if t['bg_l'] >= 0.90]
    if len(near_white) >= max(4, n - 1):
        warnings.append({
            'code':    'bg_cluster',
            'gate':    'bg_lightness',
            'message': (
                f"{len(near_white)}/{n} themes have light-mode background L ≥ 0.90 "
                "— nobody chose a background; all defaulted to near-white"
            ),
            'slugs':   [t['slug'] for t in near_white],
        })

    # ── Hue range (pairwise gaps pass 20° but all themes sit in one arc) ─────
    for hue_key, label, gate in [
        ('primary_hue', 'primary', 'primary_hue_gap'),
        ('accent_hue',  'accent',  'accent_hue_gap'),
    ]:
        hues = [t[hue_key] for t in themes if t[hue_key] is not None]
        if len(hues) >= 3:
            span = _hue_span(hues)
            if span < 120.0:
                warnings.append({
                    'code':    f'{label}_range_narrow',
                    'gate':    gate,
                    'message': (
                        f"{label.capitalize()} hues span only {span:.0f}° of the wheel "
                        f"— pairwise 20° gaps pass but all {label}s sit in the same arc"
                    ),
                    'span':    span,
                    'hues':    hues,
                })

    # ── Accent chroma floor (accent is functionally neutral, hue gap is moot) ─
    # An accent with chroma < 0.06 is effectively a neutral; its hue value has
    # no perceptible colour to differentiate it from another near-neutral accent.
    low_c = [t for t in themes
             if t.get('accent_chroma') is not None and t['accent_chroma'] < 0.06]
    if len(low_c) >= 2:
        warnings.append({
            'code':    'accent_chroma_floor',
            'gate':    'accent_hue_gap',
            'message': (
                f"{len(low_c)} accents have chroma < 0.06 "
                f"({', '.join(t['slug'] for t in low_c)}) — "
                "these are functionally neutral; the hue-gap gate passes on a value "
                "with no visible hue"
            ),
            'slugs':   [t['slug'] for t in low_c],
        })

    # ── Font exhaustion (every font doubled up, no theme has an exclusive voice) ─
    fc = Counter(t['display_font'] for t in themes)
    if n >= 4 and all(count >= 2 for count in fc.values()):
        warnings.append({
            'code':        'font_exhaustion',
            'gate':        'font_diversity',
            'message':     (
                f"Every display font appears on ≥2 themes "
                f"({len(fc)} fonts for {n} themes) — "
                "no theme was given an exclusive typographic identity; "
                "font diversity gate passes at bare minimum"
            ),
            'font_counts': dict(fc),
        })

    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# Gate 19: cross-run used.md ledger check
# ─────────────────────────────────────────────────────────────────────────────

def _parse_used_md(text: str) -> list[dict[str, str]]:
    """Parse used.md's Entries table into row dicts keyed by its own header.

    Never assume a fixed column list -- theme-designer.md warns this file's
    column order has been wrong before. The header row is the only source of
    truth for which cell is which column.
    """
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if header is None:
            if cells and cells[0].lower() == 'slug':
                header = cells
            continue
        if all(c == '' or set(c) <= {'-'} for c in cells):
            continue  # separator row
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def _live_ledger_rows(rows: list[dict[str, str]], max_runs: int = LEDGER_MAX_LIVE_RUNS) -> list[dict[str, str]]:
    """Keep only rows whose run-date is among the most-recent max_runs distinct dates.

    Rows are appended in run order (tf_ledger.py only ever appends), so later
    rows in the file are newer runs -- count backward from the bottom, per
    used.md's own decay rule.
    """
    seen_dates: list[str] = []
    for r in reversed(rows):
        d = r.get('run-date', '')
        if d and d not in seen_dates:
            seen_dates.append(d)
        if len(seen_dates) >= max_runs:
            break
    live_dates = set(seen_dates)
    return [r for r in rows if r.get('run-date', '') in live_dates]


def _check_used_ledger(themes: list[dict], used_md_path: Path) -> list[dict]:
    """Advisory-only: do this run's six themes clash with a live used.md entry?

    Mirrors used.md's own "Avoidance constraints" (OR, not AND: 15° primary-hue
    band, exact display-font match, exact signature_type match), which
    theme-designer is instructed to honor by reading the file -- nothing
    previously verified it actually did. This closes that verification gap.

    Advisory, not a hard-stop, for now: kept advisory pending calibration
    against real runs using the corrected field (same phasing as Gate 18),
    now that tf_ledger.py's bug is fixed. Previously this compared
    motion.character (a closed 4-value enum) instead of the real
    motion.signature_type slug, because the ledger column both agents read
    and wrote was silently populated from the wrong field -- a near-guaranteed
    collision against a 4-value enum was the actual old behavior, which is
    why it was advisory-only. signature_type's real domain is much larger, so
    a genuine collision is now a meaningful signal worth promoting to a
    hard-stop once real-run data confirms it doesn't false-positive.
    """
    warnings: list[dict] = []
    if not used_md_path.is_file():
        return warnings
    try:
        text = used_md_path.read_text(encoding='utf-8')
    except OSError:
        return warnings

    rows = _live_ledger_rows(_parse_used_md(text))
    if not rows:
        return warnings

    for t in themes:
        slug = t['slug']
        hue = t.get('primary_hue')
        font = (t.get('display_font') or '').strip().lower()
        motion = (t.get('signature_type') or '').strip().lower()

        hue_hits: list[dict] = []
        font_hits: list[str] = []
        motion_hits: list[str] = []

        for r in rows:
            r_slug = r.get('slug', '?')
            if r_slug == slug:
                continue  # this theme's own row from an earlier gallery rebuild, not a clash

            if hue is not None:
                try:
                    r_hue = float(r.get('primary_hue') or '')
                except ValueError:
                    r_hue = None
                if r_hue is not None:
                    gap = _hue_gap(hue, r_hue)
                    if gap < LEDGER_HUE_GAP_MIN:
                        hue_hits.append({
                            'slug': r_slug, 'run_date': r.get('run-date', '?'),
                            'hue': r_hue, 'gap': round(gap, 1),
                        })

            r_font = (r.get('display_font') or '').strip().lower()
            if font and r_font and font == r_font:
                font_hits.append(f"{r_slug} ({r.get('run-date', '?')})")

            r_motion = (r.get('signature_type') or '').strip().lower()
            if motion and r_motion and motion == r_motion:
                motion_hits.append(f"{r_slug} ({r.get('run-date', '?')})")

        if hue_hits:
            worst = min(hue_hits, key=lambda h: h['gap'])
            warnings.append({
                'code': 'ledger_hue_conflict',
                'gate': 'used_md_ledger',
                'message': (
                    f"'{slug}' primary hue {hue:.0f}° is {worst['gap']:.1f}° from "
                    f"'{worst['slug']}' ({worst['run_date']}, hue {worst['hue']:.0f}°) in the "
                    f"live used.md window — inside the {LEDGER_HUE_GAP_MIN:.0f}° avoidance band"
                ),
                'slug': slug,
                'conflicts': hue_hits,
            })

        if font_hits:
            warnings.append({
                'code': 'ledger_font_conflict',
                'gate': 'used_md_ledger',
                'message': (
                    f"'{slug}' display font '{t.get('display_font')}' repeats a live "
                    f"used.md entry: {', '.join(font_hits)}"
                ),
                'slug': slug,
                'conflicts': font_hits,
            })

        if motion_hits:
            warnings.append({
                'code': 'ledger_motion_conflict',
                'gate': 'used_md_ledger',
                'message': (
                    f"'{slug}' signature_type '{t.get('signature_type')}' repeats a live "
                    f"used.md entry: {', '.join(motion_hits)}"
                ),
                'slug': slug,
                'conflicts': motion_hits,
            })

    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# Console output
# ─────────────────────────────────────────────────────────────────────────────

_W = 110

def _pr(msg: str = '') -> None:
    sys.stderr.write(msg + '\n')


def _print_table(themes: list[dict]) -> None:
    _pr()
    _pr('DISTINCTIVENESS GATE')
    _pr('─' * _W)
    _pr(f"  {'Slot':4s} │ {'Slug':22s} │ {'Primary':10s} │ {'P°':>5s} │ "
        f"{'Accent':10s} │ {'A°':>5s} │ {'Bg L':>5s} │ {'DV':>3s} │ "
        f"{'Intensity':13s} │ Display font")
    _pr('─' * _W)
    for t in themes:
        ph = t['primary_hue']
        ah = t['accent_hue']
        _pr(
            f"  {t['slot']:4s} │ {t['slug']:22s} │ {t['primary_hex']:10s} │ "
            f"{(f'{ph:.0f}' if ph is not None else '?'):>5s} │ "
            f"{t['accent_hex']:10s} │ "
            f"{(f'{ah:.0f}' if ah is not None else '?'):>5s} │ "
            f"{t['bg_l']:>5.2f} │ "
            f"{(str(t.get('design_variance','?'))):>3s} │ "
            f"{t.get('intensity', '?'):13s} │ {t['display_font']}"
        )
    _pr('─' * _W)


def _print_pairwise(themes: list[dict], hue_key: str, label: str, thresh: float) -> None:
    gaps = _pairwise(themes, hue_key)
    _pr(f'\nPairwise {label} hue gaps (min ≥ {thresh:.0f}°):')
    for r in gaps:
        g = r['gap']
        mark = 'PASS ✓' if (g is not None and g >= thresh) else 'FAIL ✗'
        g_str = f"{g:.1f}°" if g is not None else 'N/A '
        _pr(f"  {r['slot_a']}↔{r['slot_b']}: {g_str:>7s}  {mark}")
    valid = [r['gap'] for r in gaps if r['gap'] is not None]
    if valid:
        mn = min(valid)
        mark = 'PASS ✓' if mn >= thresh else 'FAIL ✗'
        _pr(f"  Minimum: {mn:.1f}°  {mark}")


def _print_bg(themes: list[dict], slot_d: dict | None) -> None:
    vals = '  '.join(f'{t["bg_l"]:.2f}' for t in themes)
    dark = sum(1 for t in themes if t['bg_l'] <= BG_DARK_MAX)
    mark = 'PASS ✓' if dark > 0 else 'FAIL ✗'
    _pr(f'\nLight-mode background L: {vals}')
    _pr(f'  Themes with L ≤ {BG_DARK_MAX}: {dark}  {mark}')
    if slot_d:
        m = 'PASS ✓' if slot_d['bg_l'] <= BG_DARK_MAX else 'FAIL ✗'
        _pr(f'  Slot D ({slot_d["slug"]}) bg L={slot_d["bg_l"]:.3f}  {m}')
    else:
        _pr('  Slot D: not assigned — skipping hard-bg check')


def _print_warnings(warnings: list[dict]) -> None:
    if not warnings:
        return
    _pr()
    _pr('LETTER-NOT-SPIRIT WARNINGS (gate passed; intent may not be met)')
    _pr('─' * _W)
    for w in warnings:
        _pr(f"  ⚠  [{w['gate']}] {w['message']}")
    _pr('─' * _W)


def _print_fonts(themes: list[dict]) -> None:
    fc = Counter(t['display_font'] for t in themes)
    items = '  '.join(f'{f} ×{n}' for f, n in fc.most_common())
    max_n = max(fc.values()) if fc else 0
    mark = 'PASS ✓' if max_n <= FONT_MAX_USES else 'FAIL ✗'
    _pr(f'\nDisplay font usage: {items}')
    _pr(f'  Max uses: {max_n}  (allowed ≤{FONT_MAX_USES})  {mark}')


def _print_composition_table(themes: list[dict]) -> None:
    _W2 = 130
    _BUDGET_VALID = {'full', 'moderate', 'near-imperceptible', 'feedback-only', 'delight', 'sparse'}
    _pr()
    _pr('COMPOSITION GATE')
    _pr('─' * _W2)
    _pr(f"  {'Slug':22s} │ {'Structural brief':30s} │ "
        f"{'Lang':20s} │ {'Budget W':18s} │ {'Budget A':18s} │ "
        f"{'Rej':>3s} │ {'Del':>3s} │ Amb")
    _pr('─' * _W2)
    for t in themes:
        mb = t.get('motion_budget') or {}
        wb = mb.get('website', '?')
        ab = mb.get('webapp', '?')
        wb_mark = '' if wb in _BUDGET_VALID else ' ✗'
        ab_mark = '' if ab in _BUDGET_VALID else ' ✗'
        rej = len(t.get('motion_rejected') or [])
        dlt = len(t.get('motion_delight') or [])
        amb = '✓' if (t.get('ambition') or '').strip() else '✗'
        rej_mark = f'{rej:3d}' if rej >= 2 else f'{rej:3d} ✗'
        dlt_mark = f'{dlt:3d}' if dlt >= 1 else f'{dlt:3d} ✗'
        brief = (t.get('structural_brief') or '').strip()
        brief_cell = (brief[:27] + '...') if len(brief) > 30 else (brief or '✗ missing')
        _pr(
            f"  {t['slug']:22s} │ {brief_cell:30s} │ "
            f"{t.get('design_language') or '?':20s} │ {(wb + wb_mark):18s} │ "
            f"{(ab + ab_mark):18s} │ {rej_mark} │ {dlt_mark} │ {amb}"
        )
    _pr('─' * _W2)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    want_json  = '--json' in argv
    slot_d_slug: str | None = None
    themes_dir: Path | None = None
    used_md_arg: Path | None = None

    i = 0
    while i < len(argv):
        if argv[i] == '--themes-dir' and i + 1 < len(argv):
            themes_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == '--slot-d' and i + 1 < len(argv):
            slot_d_slug = argv[i + 1]; i += 2
        elif argv[i] == '--used-md' and i + 1 < len(argv):
            used_md_arg = Path(argv[i + 1]); i += 2
        else:
            i += 1

    if themes_dir is None:
        scripts_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(scripts_dir))
        try:
            import tf_paths
            paths = tf_paths.resolve(create=False)
            themes_dir = paths.current_themes
        except Exception:
            msg = '--themes-dir required (tf_paths unavailable)'
            sys.stderr.write(f'tf_distinct: {msg}\n')
            print(json.dumps({'ok': False, 'error': msg}))
            return 1

    if not themes_dir.is_dir():
        msg = f'themes-dir not found: {themes_dir}'
        sys.stderr.write(f'tf_distinct: {msg}\n')
        print(json.dumps({'ok': False, 'error': msg}))
        return 1

    theme_files = sorted(themes_dir.glob('*/theme.json'))
    if not theme_files:
        msg = f'no theme.json files in {themes_dir}'
        sys.stderr.write(f'tf_distinct: {msg}\n')
        print(json.dumps({'ok': False, 'error': msg}))
        return 1

    themes = [t for f in theme_files if (t := _load_theme(f)) is not None]

    # Resolve Slot D for reporting
    slot_d = None
    if slot_d_slug:
        slot_d = next((t for t in themes if t['slug'] == slot_d_slug), None)
    if slot_d is None:
        slot_d = next((t for t in themes if t['slot'] == 'D'), None)

    # Print full gate table to stderr every run
    _print_table(themes)
    _print_pairwise(themes, 'primary_hue', 'primary', PRIM_GAP_MIN)
    _print_pairwise(themes, 'accent_hue',  'accent',  ACCENT_GAP_MIN)
    _print_bg(themes, slot_d)
    _print_fonts(themes)
    _print_composition_table(themes)

    failures, hints = _run_gates(themes, slot_d_slug)
    warnings        = _letter_not_spirit(themes)

    # ── Gate 18: structural distinctiveness (tf_structure.py) ────────────────
    # Advisory-only in this phase: the old hero_archetype/grid_strategy/nav_pattern
    # enum-uniqueness checks retired with the bespoke-composition rewrite (there is
    # no more enum to compare), and tf_distinct.py never inspected rendered output
    # before this either. tf_structure.py measures actual rendered structure
    # instead of self-reported labels. Findings are appended to `warnings`, never
    # `failures`, until thresholds are calibrated against several real runs -- see
    # the phasing note in the project's implementation plan before promoting this
    # to a hard gate.
    try:
        scripts_dir = Path(__file__).resolve().parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import tf_structure
        structure_result = tf_structure.check(themes_dir, surfaces=("website", "webapp", "mobile"))
        for f in structure_result.get("findings", []):
            warnings.append({
                "code": "structural_similarity",
                "gate": "tf_structure",
                "message": f["message"],
                "surface": f["surface"],
                "slug_a": f["slug_a"],
                "slug_b": f["slug_b"],
                "similarity": f["similarity"],
                "driving_signals": f["driving_signals"],
            })
        if structure_result.get("skipped"):
            _pr(f"  (tf_structure: {len(structure_result['skipped'])} surface(s) not yet authored, skipped)")
    except Exception as exc:  # noqa: BLE001 -- advisory gate must never abort the run
        _pr(f"  ⚠ tf_structure.py failed to run ({exc}) -- structural-similarity check skipped")

    # ── Gate 19: cross-run used.md ledger check ───────────────────────────────
    # Advisory-only for now -- see _check_used_ledger's docstring: this used to
    # compare motion.character (genuinely unpromotable, a 4-value enum) due to
    # a tf_ledger.py bug; now that it compares the real motion.signature_type,
    # promotion to a hard-stop is back on the table once calibrated.
    try:
        used_md_path = used_md_arg
        if used_md_path is None:
            scripts_dir = Path(__file__).resolve().parent
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))
            import tf_paths
            used_md_path = tf_paths.resolve(create=False).home / 'used.md'
        ledger_warnings = _check_used_ledger(themes, used_md_path)
        warnings.extend(ledger_warnings)
        if not used_md_path.is_file():
            _pr(f"  (used.md not found at {used_md_path} — ledger check skipped)")
    except Exception as exc:  # noqa: BLE001 -- advisory gate must never abort the run
        _pr(f"  ⚠ used.md ledger check failed to run ({exc}) -- skipped")

    # ── Gate 20: motion/design_language cohesion (tf_motion_cohesion.py) ──────
    # Advisory-only -- a mechanical re-derivation of design-critic.md's
    # §7b-cohesion table (design_language -> expected motion.character/duration
    # baseline, plus a bare-easing-keyword check). Moving it here means the
    # LLM critic no longer computes this lookup-table-plus-arithmetic check by
    # hand every run; it only judges the parts a table can't (screenshot feel,
    # motion-vs-stated-ambition match).
    try:
        scripts_dir = Path(__file__).resolve().parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import tf_motion_cohesion
        cohesion_result = tf_motion_cohesion.check(themes_dir)
        for f in cohesion_result.get("findings", []):
            warnings.append({
                "code": f["code"],
                "gate": "tf_motion_cohesion",
                "message": f["message"],
                "slug": f["slug"],
            })
    except Exception as exc:  # noqa: BLE001 -- advisory gate must never abort the run
        _pr(f"  ⚠ tf_motion_cohesion.py failed to run ({exc}) -- cohesion check skipped")

    # ── Gate 21: typographic identity ─────────────────────────────────────────
    # Every theme must own at least ONE typeface no other theme in the set uses.
    #
    # Gate 5 caps how many themes may share a *display* face (FONT_MAX_USES) and
    # never looks at body or mono at all, so each individual sharing here can be
    # perfectly legal while the theme ends up with no typographic identity
    # whatsoever. Confirmed live: one theme's display (Gabarito) was shared with
    # a sibling, its body (Hanken Grotesk) with a different sibling, and its
    # mono (JetBrains Mono) with both -- three legal pairwise shares summing to
    # zero distinctiveness, which no per-role count could see. A design-critic
    # caught it by eye and called it "no typeface of its own".
    #
    # It stayed invisible for another reason too, worth recording: the gallery's
    # font @import was dropping four themes' families entirely (see
    # tf_gallery.py's _is_google_source), so for several runs *every* theme
    # rendered in the same Arial fallback and no amount of looking would have
    # revealed which faces were actually shared.
    #
    # Advisory, not a hard failure: which face to change is a design decision,
    # and the remedy is a targeted typography swap (SKILL.md Step 5e), not a
    # regeneration. Emitting it as a warning puts it in front of the critic and
    # the user without hard-stopping a set that is otherwise sound.
    _font_role_counts = {
        'display': Counter(t['display_font'] for t in themes),
        'body':    Counter(t['body_font'] for t in themes),
        'mono':    Counter(t['mono_font'] for t in themes),
    }
    for t in themes:
        unique_roles = [
            role for role, key in (('display', 'display_font'),
                                   ('body', 'body_font'),
                                   ('mono', 'mono_font'))
            if _font_role_counts[role][t[key]] == 1
        ]
        if unique_roles:
            continue
        shared_with = {}
        for role, key in (('display', 'display_font'), ('body', 'body_font'),
                          ('mono', 'mono_font')):
            others = [o['slug'] for o in themes
                      if o['slug'] != t['slug'] and o[key] == t[key]]
            shared_with[role] = (t[key], others)
        warnings.append({
            'code': 'font_identity',
            'gate': 'typographic_identity',
            'slug': t['slug'],
            'message': (
                f"'{t['slug']}' has no typeface of its own — every one of its three "
                f"faces is used by another theme in this set: "
                + '; '.join(
                    f"{role} '{fam}' also on {others}"
                    for role, (fam, others) in shared_with.items()
                )
                + ". Each share is individually within Gate 5's limit, but the theme "
                  "carries no typographic identity. Remedy is a targeted typography "
                  "swap (change display and/or body to an unshared family, then "
                  "regenerate that theme's brand assets and native font packages) — "
                  "not a full regeneration."
            ),
        })

    ok = len(failures) == 0
    _pr()
    _pr('═' * 54)
    if ok:
        _pr('GATE RESULT: PASS ✓ — all constraints met')
    else:
        _pr(f'GATE RESULT: FAIL ✗ — {len(failures)} failure(s)')
        for f in failures:
            _pr(f"  · {f['message']}")
    _pr()

    # Print letter-not-spirit warnings after the gate result
    _print_warnings(warnings)

    result: dict = {
        'ok':                  ok,
        'gate_result':         'pass' if ok else 'fail',
        'theme_count':         len(themes),
        'failures':            failures,
        'regeneration_hints':  hints,
        'warnings':            warnings,
        'table': [
            {k: t[k] for k in (
                'slug', 'slot', 'primary_hex', 'primary_hue', 'primary_chroma',
                'accent_hex', 'accent_hue', 'accent_chroma', 'bg_l', 'display_font',
                'structural_brief', 'signature_type', 'design_language', 'intensity',
                'design_variance', 'motion_intensity', 'visual_density',
                'ambition', 'motion_budget', 'motion_rejected', 'motion_delight',
            ) if k in t}
            for t in themes
        ],
    }

    if want_json or not ok:
        print(json.dumps(result, indent=2))

    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write(f'tf_distinct: unexpected error: {exc}\n')
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'ok': False, 'error': str(exc)}))
        sys.exit(2)
