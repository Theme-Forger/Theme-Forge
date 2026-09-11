#!/usr/bin/env python3
"""tf_color.py -- the color engine. Pure math, standard library only.

Working space is OKLCH. Everything the engine emits carries a hex fallback,
because hex is the only color form React Native reliably accepts.

Pipeline:
    hex <-> sRGB(0..1) <-> linear sRGB <-> OKLab <-> OKLCH

Conversions use the proper piecewise sRGB transfer function (not a 2.2 power
law) and Ottosson's OKLab matrices. Out-of-gamut OKLCH is brought back into
sRGB by binary-searching chroma downward.

Run `python3 tf_color.py --selftest` to verify round-trips, gamut clamping,
and WCAG contrast against known values.
"""
from __future__ import annotations

import json
import math
import sys
from typing import Dict, List, Tuple

Triple = Tuple[float, float, float]

# ---------------------------------------------------------------------------
# hex <-> sRGB
# ---------------------------------------------------------------------------


def hex_to_srgb(hex_str: str) -> Triple:
    """'#rrggbb' or '#rgb' -> (r, g, b) each in 0..1."""
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) == 8:  # allow #rrggbbaa, drop alpha
        s = s[:6]
    if len(s) != 6:
        raise ValueError("bad hex color: %r" % hex_str)
    r = int(s[0:2], 16) / 255.0
    g = int(s[2:4], 16) / 255.0
    b = int(s[4:6], 16) / 255.0
    return (r, g, b)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def srgb_to_hex(srgb: Triple) -> str:
    """(r, g, b) in 0..1 -> '#rrggbb', clamping to the representable range."""
    out = []
    for c in srgb:
        v = int(round(_clamp01(c) * 255.0))
        out.append(v)
    return "#%02x%02x%02x" % (out[0], out[1], out[2])


# ---------------------------------------------------------------------------
# sRGB gamma <-> linear (piecewise IEC 61966-2-1 transfer function)
# ---------------------------------------------------------------------------


def srgb_to_linear(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _srgb_triple_to_linear(srgb: Triple) -> Triple:
    return (srgb_to_linear(srgb[0]), srgb_to_linear(srgb[1]), srgb_to_linear(srgb[2]))


def _linear_triple_to_srgb(lin: Triple) -> Triple:
    return (linear_to_srgb(lin[0]), linear_to_srgb(lin[1]), linear_to_srgb(lin[2]))


# ---------------------------------------------------------------------------
# linear sRGB <-> OKLab  (Bjorn Ottosson, M1/M2 matrices)
# ---------------------------------------------------------------------------


def _cbrt(x: float) -> float:
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def linear_srgb_to_oklab(lin: Triple) -> Triple:
    r, g, b = lin
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_ = _cbrt(l)
    m_ = _cbrt(m)
    s_ = _cbrt(s)

    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return (L, a, bb)


def oklab_to_linear_srgb(lab: Triple) -> Triple:
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l = l_ * l_ * l_
    m = m_ * m_ * m_
    s = s_ * s_ * s_

    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return (r, g, bb)


# ---------------------------------------------------------------------------
# OKLab <-> OKLCH
# ---------------------------------------------------------------------------


def oklab_to_oklch(lab: Triple) -> Triple:
    L, a, b = lab
    C = math.hypot(a, b)
    H = math.degrees(math.atan2(b, a))
    if H < 0:
        H += 360.0
    return (L, C, H)


def oklch_to_oklab(oklch: Triple) -> Triple:
    L, C, H = oklch
    rad = math.radians(H)
    return (L, C * math.cos(rad), C * math.sin(rad))


# ---------------------------------------------------------------------------
# Convenience end-to-end conversions
# ---------------------------------------------------------------------------


def hex_to_oklch(hex_str: str) -> Triple:
    srgb = hex_to_srgb(hex_str)
    lin = _srgb_triple_to_linear(srgb)
    lab = linear_srgb_to_oklab(lin)
    return oklab_to_oklch(lab)


def oklch_to_linear_srgb(oklch: Triple) -> Triple:
    return oklab_to_linear_srgb(oklch_to_oklab(oklch))


def oklch_to_srgb(oklch: Triple) -> Triple:
    return _linear_triple_to_srgb(oklch_to_linear_srgb(oklch))


def oklch_to_hex(oklch: Triple, clamp: bool = True) -> str:
    """OKLCH -> '#rrggbb'. Clamps chroma into sRGB gamut first by default."""
    if clamp:
        oklch = clamp_chroma(oklch)
    return srgb_to_hex(oklch_to_srgb(oklch))


# ---------------------------------------------------------------------------
# Gamut
# ---------------------------------------------------------------------------

# Tolerance absorbs the ~4-decimal rounding applied to stored OKLCH triples
# (worst case ~0.3/255 near a saturated gamut boundary); the emitted hex is
# always hard-clamped to [0,1] in srgb_to_hex regardless.
_GAMUT_EPS = 2e-3


def in_gamut(oklch: Triple, eps: float = _GAMUT_EPS) -> bool:
    """True if the OKLCH color lands inside sRGB [0,1] on all channels."""
    lin = oklch_to_linear_srgb(oklch)
    lo, hi = -eps, 1.0 + eps
    return all(lo <= c <= hi for c in lin)


# clamp_chroma drives to the *true* gamut boundary using a strict tolerance,
# independent of the looser public validation eps. This guarantees its result
# stays inside gamut even after the stored OKLCH is rounded for display.
_CLAMP_EPS = 1e-7


def clamp_chroma(oklch: Triple) -> Triple:
    """Binary-search chroma down until the color is representable in sRGB.

    Lightness and hue are preserved; only chroma is reduced. Returns the input
    unchanged if it is already strictly in gamut.
    """
    L, C, H = oklch
    if L <= 0.0:
        return (0.0, 0.0, H)
    if L >= 1.0:
        return (1.0, 0.0, H)
    if in_gamut((L, C, H), eps=_CLAMP_EPS):
        return (L, C, H)
    lo, hi = 0.0, C
    for _ in range(48):
        mid = (lo + hi) / 2.0
        if in_gamut((L, mid, H), eps=_CLAMP_EPS):
            lo = mid
        else:
            hi = mid
    return (L, lo, H)


# ---------------------------------------------------------------------------
# Ramp generation
# ---------------------------------------------------------------------------

_DEFAULT_STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]

# Perceptual lightness ladder: tighter spacing in the middle where the eye is
# most sensitive, opening up toward the ends.
_LIGHTNESS = {
    50: 0.972, 100: 0.940, 200: 0.882, 300: 0.806, 400: 0.716,
    500: 0.630, 600: 0.548, 700: 0.470, 800: 0.392, 900: 0.312, 950: 0.238,
}

# Chroma taper relative to the base chroma: peaks at 400-600, falls off at both
# ends so the 50 step doesn't look stained and the 950 step doesn't look purple.
_CHROMA_TAPER = {
    50: 0.20, 100: 0.36, 200: 0.58, 300: 0.80, 400: 0.96, 500: 1.00,
    600: 0.98, 700: 0.86, 800: 0.70, 900: 0.55, 950: 0.44,
}


def ramp(
    base_oklch: Triple,
    steps: List[int] = None,
    hue_drift: float = 0.0,
) -> Dict[str, Dict[str, object]]:
    """Build a perceptually even ramp from a base OKLCH color.

    The base supplies hue and the reference (500) chroma. Lightness follows the
    fixed ladder; chroma is tapered and then clamped into gamut per step. An
    optional `hue_drift` (degrees across the whole ramp) warms shadows / cools
    highlights for a subtly richer result.

    Returns {"500": {"oklch": [L, C, H], "hex": "#..."}, ...}.
    """
    steps = steps or _DEFAULT_STEPS
    _, base_c, base_h = base_oklch
    n = len(steps)
    out: Dict[str, Dict[str, object]] = {}
    for i, step in enumerate(steps):
        L = _LIGHTNESS.get(step, base_oklch[0])
        taper = _CHROMA_TAPER.get(step, 1.0)
        C = base_c * taper
        # drift hue linearly from -drift/2 at the light end to +drift/2 at dark
        frac = (i / (n - 1)) - 0.5 if n > 1 else 0.0
        H = (base_h + hue_drift * frac) % 360.0
        L, C, H = clamp_chroma((L, C, H))
        out[str(step)] = {
            "oklch": [round(L, 4), round(C, 4), round(H, 2)],
            "hex": oklch_to_hex((L, C, H), clamp=False),
        }
    return out


# ---------------------------------------------------------------------------
# Contrast
# ---------------------------------------------------------------------------


def relative_luminance(hex_str: str) -> float:
    r, g, b = _srgb_triple_to_linear(hex_to_srgb(hex_str))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_contrast(fg_hex: str, bg_hex: str) -> float:
    """WCAG 2.x contrast ratio, 1.0 .. 21.0."""
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


# APCA-W3 (0.1.9) constants
_APCA = dict(
    trc=2.4,
    Rco=0.2126729, Gco=0.7151522, Bco=0.0721750,
    normBG=0.56, normTXT=0.57, revTXT=0.62, revBG=0.65,
    blkThrs=0.022, blkClmp=1.414,
    scaleBoW=1.14, scaleWoB=1.14,
    loBoWoffset=0.027, loWoBoffset=0.027,
    deltaYmin=0.0005, loClip=0.1,
)


def _apca_luminance(hex_str: str) -> float:
    r, g, b = hex_to_srgb(hex_str)
    Y = (
        _APCA["Rco"] * (r ** _APCA["trc"])
        + _APCA["Gco"] * (g ** _APCA["trc"])
        + _APCA["Bco"] * (b ** _APCA["trc"])
    )
    return Y


def apca_lc(fg_hex: str, bg_hex: str) -> float:
    """APCA lightness contrast (Lc). Directional; roughly -108 .. 106.

    Reported for future-readiness alongside WCAG. Not a gating metric here.
    """
    A = _APCA
    ytxt = _apca_luminance(fg_hex)
    ybg = _apca_luminance(bg_hex)

    def soft_clamp(y: float) -> float:
        if y < A["blkThrs"]:
            return y + (A["blkThrs"] - y) ** A["blkClmp"]
        return y

    ytxt = soft_clamp(ytxt)
    ybg = soft_clamp(ybg)

    if abs(ybg - ytxt) < A["deltaYmin"]:
        return 0.0

    if ybg > ytxt:  # normal polarity: dark text on light bg
        sapc = (ybg ** A["normBG"] - ytxt ** A["normTXT"]) * A["scaleBoW"]
        out = 0.0 if sapc < A["loClip"] else sapc - A["loBoWoffset"]
    else:  # reverse polarity: light text on dark bg
        sapc = (ybg ** A["revBG"] - ytxt ** A["revTXT"]) * A["scaleWoB"]
        out = 0.0 if sapc > -A["loClip"] else sapc + A["loWoBoffset"]

    return out * 100.0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SELFTEST_COLORS = [
    "#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff",
    "#4a63c8", "#767676", "#123456", "#abcdef", "#fedcba",
    "#7f7f7f", "#010203", "#fefefe", "#c0ffee", "#bada55",
    "#1a1a2e", "#f3f5fd", "#ff6b35", "#2ec4b6", "#e71d36",
    "#8338ec", "#ffbe0b", "#3a86ff", "#06d6a0", "#ef476f",
]


def _selftest() -> Tuple[bool, List[str]]:
    notes: List[str] = []
    ok = True

    # 1. hex -> oklch -> hex round-trip within 1/255 per channel.
    max_err = 0
    for hx in _SELFTEST_COLORS:
        back = oklch_to_hex(hex_to_oklch(hx), clamp=False)
        a = hex_to_srgb(hx)
        b = hex_to_srgb(back)
        err = max(abs(round(a[i] * 255) - round(b[i] * 255)) for i in range(3))
        max_err = max(max_err, err)
        if err > 1:
            ok = False
            notes.append("round-trip %s -> %s off by %d/255" % (hx, back, err))
    notes.append("round-trip: %d colors, max error %d/255" % (len(_SELFTEST_COLORS), max_err))

    # 2. transfer function is piecewise, not a naive 2.2 power law.
    #    round-trip linear<->srgb in the dark end must be exact.
    for c in (0.0, 0.001, 0.01, 0.02, 0.04, 0.2, 0.5, 0.99, 1.0):
        rt = linear_to_srgb(srgb_to_linear(c))
        if abs(rt - c) > 1e-9:
            ok = False
            notes.append("transfer round-trip failed at %.4f (got %.6f)" % (c, rt))

    # 3. gamut clamp: an out-of-gamut input is brought into range.
    oog = (0.85, 0.30, 30.0)
    if in_gamut(oog):
        notes.append("warning: expected %r to be out of gamut" % (oog,))
    clamped = clamp_chroma(oog)
    if not in_gamut(clamped):
        ok = False
        notes.append("clamp_chroma failed to bring %r into gamut" % (oog,))
    else:
        notes.append(
            "gamut clamp: chroma %.3f -> %.3f, in gamut" % (oog[1], clamped[1])
        )

    # 4. WCAG against known values.
    c_bw = wcag_contrast("#000000", "#ffffff")
    if abs(c_bw - 21.0) > 0.01:
        ok = False
        notes.append("black/white contrast %.3f != 21.0" % c_bw)
    else:
        notes.append("WCAG #000/#fff = %.2f:1" % c_bw)
    c_gray = wcag_contrast("#767676", "#ffffff")
    if abs(c_gray - 4.54) > 0.05:
        ok = False
        notes.append("#767676/#fff contrast %.3f != ~4.54" % c_gray)
    else:
        notes.append("WCAG #767676/#fff = %.2f:1" % c_gray)

    # 5. APCA runs and is directional.
    lc_dark_on_light = apca_lc("#000000", "#ffffff")
    lc_light_on_dark = apca_lc("#ffffff", "#000000")
    notes.append(
        "APCA #000-on-#fff Lc=%.1f, #fff-on-#000 Lc=%.1f"
        % (lc_dark_on_light, lc_light_on_dark)
    )
    if not (lc_dark_on_light > 95 and lc_light_on_dark < -90):
        ok = False
        notes.append("APCA polarity/magnitude unexpected")

    # 6. ramp produces in-gamut hexes across the ladder.
    r = ramp((0.63, 0.14, 264.0))
    if len(r) != len(_DEFAULT_STEPS):
        ok = False
        notes.append("ramp produced %d steps" % len(r))
    for step, val in r.items():
        if not in_gamut(tuple(val["oklch"])):
            ok = False
            notes.append("ramp step %s out of gamut" % step)
    notes.append("ramp: %d steps, all in gamut" % len(r))

    return ok, notes


def main(argv: List[str]) -> int:
    want_json = "--json" in argv
    if "--selftest" in argv or not argv:
        ok, notes = _selftest()
        for n in notes:
            sys.stderr.write("  %s\n" % n)
        sys.stderr.write("SELFTEST %s\n" % ("PASS" if ok else "FAIL"))
        if want_json or True:
            print(json.dumps({"ok": ok, "selftest": notes}))
        return 0 if ok else 1
    sys.stderr.write("usage: tf_color.py --selftest [--json]\n")
    print(json.dumps({"ok": False, "error": "unknown arguments"}))
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        sys.stderr.write("tf_color: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
