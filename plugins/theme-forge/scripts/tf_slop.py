#!/usr/bin/env python3
"""tf_slop.py -- detect AI-slop design anti-patterns in generated theme previews.

Wraps `npx impeccable detect --json` (https://impeccable.style) on each
theme's preview.html.  When impeccable is unavailable the script degrades
cleanly: it reports ok:true with available:false rather than failing the
generation run.

Usage:
    python3 tf_slop.py --json                   # all themes in TF_HOME/current/
    python3 tf_slop.py --theme <dir> --json     # one theme directory
    python3 tf_slop.py --selftest               # verify JSON round-trip works

Exit 0 on success (findings do not change exit code).
Exit 1 on expected failure ({"ok": false, "error": "..."}).
Exit 2 on unexpected / unhandled error.

Output: writes <theme-dir>/slop.json, prints summary JSON to stdout.
Human-readable progress goes to stderr.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tf_paths  # type: ignore
    import tf_htmlshape  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import tf_paths
    import tf_htmlshape


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def _ok(payload: dict) -> None:
    print(json.dumps({"ok": True, **payload}))


def _fail(msg: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(code)


def _npx_cmd() -> str:
    """Return the full path to npx (handles Windows .CMD extension)."""
    return shutil.which("npx") or "npx"


def _impeccable_argv() -> list[str]:
    """Return argv prefix for impeccable subcommands.

    Prefers the directly-installed binary (instant, no npm registry round-trip)
    over `npx impeccable` (which resolves the package from the registry and hangs
    when the network is unavailable or slow).
    """
    direct = shutil.which("impeccable")
    if direct:
        return [direct]
    return [_npx_cmd(), "--yes", "impeccable"]


def _needs_shell(cmd: str = "") -> bool:
    """On Windows, .CMD wrappers cannot be executed with shell=False."""
    target = cmd or shutil.which("impeccable") or shutil.which("npx") or ""
    return sys.platform == "win32" and target.lower().endswith(".cmd")


def _check_npx() -> bool:
    """Return True if impeccable is reachable (direct binary or via npx)."""
    return shutil.which("impeccable") is not None or shutil.which("npx") is not None


def _check_impeccable() -> bool:
    """Return True if impeccable is available.

    Tries the direct binary first (no network); falls back to npx if absent.
    """
    direct = shutil.which("impeccable")
    if direct:
        try:
            r = subprocess.run(
                [direct, "--version"],
                capture_output=True, text=True, timeout=10,
                shell=_needs_shell(direct),
            )
            return r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    # Fall back to npx (may require network for first-run download)
    if shutil.which("npx") is None:
        return False
    try:
        npx = _npx_cmd()
        r = subprocess.run(
            [npx, "--yes", "impeccable", "--version"],
            capture_output=True, text=True, timeout=30,
            shell=_needs_shell(npx),
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _run_impeccable(html_path: Path) -> dict:
    """Run impeccable detect on one HTML file.

    Returns parsed JSON (or a synthesised error dict if it fails).
    """
    argv = _impeccable_argv() + ["detect", "--json", str(html_path)]
    try:
        r = subprocess.run(
            argv,
            capture_output=True, text=True, timeout=60,
            shell=_needs_shell(argv[0]),
        )
        if r.returncode not in (0, 1, 2):
            # exit 1 or 2 from impeccable means "findings found", not an error
            return {"error": f"impeccable exited {r.returncode}", "stderr": r.stderr[:500]}
        try:
            parsed = json.loads(r.stdout)
            # impeccable may output a bare array instead of {"findings": [...]}
            if isinstance(parsed, list):
                parsed = {"findings": parsed}
            return parsed
        except json.JSONDecodeError:
            return {"error": "impeccable output was not valid JSON", "raw": r.stdout[:200]}
    except subprocess.TimeoutExpired:
        return {"error": "impeccable timed out after 60s"}
    except OSError as exc:
        return {"error": str(exc)}


def _ai_slop_findings(raw: dict) -> list[dict]:
    """Extract findings that impeccable classifies in an AI-slop category.

    Impeccable's JSON output has a "findings" array; each finding has at minimum
    {"rule": str, "message": str, "category": str, "severity": str}.
    We treat any finding in a category listed in the 13-anti-patterns knowledge
    file as an AI-slop finding.  If the schema changes, we fall back to returning
    all findings.
    """
    findings = raw.get("findings") or raw.get("results") or []
    if not findings:
        return []
    # Category names as used by impeccable (lower-case match).
    # impeccable v3 uses "category": "quality" and "antipattern" field.
    slop_categories = {
        "design-system", "visual-details", "typography", "color",
        "color-contrast", "layout", "space", "motion", "copy",
        "imagery", "general-quality", "quality",
    }
    slop = [f for f in findings
            if isinstance(f, dict)
            and f.get("category", "").lower().replace("/", "-") in slop_categories]
    # If the filter produces nothing (schema drift), return all findings
    return slop if slop else findings


# Severities that block assembly and trigger constrained regeneration.
# Everything else is advisory (shown in gallery drawer, does not block).
_HARD_STOP_SEVERITIES = {"error", "critical", "high"}


def _split_tiers(findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split findings into (hard_stop, advisory).

    hard_stop  — severity error/critical/high → triggers constrained regen
    advisory   — severity warning/info/low or unknown → shown in gallery drawer
    """
    hard_stop = [f for f in findings
                 if f.get("severity", "").lower() in _HARD_STOP_SEVERITIES]
    advisory = [f for f in findings
                if f not in hard_stop]
    return hard_stop, advisory


# ---------------------------------------------------------------------------
# Stdlib fallback rules — static CSS/HTML analysis, no browser required
# Run when impeccable CLI is unavailable.  Checks 35 of impeccable's 59 rules.
# ---------------------------------------------------------------------------

_IMPECCABLE_TOTAL_RULES = 59
_STDLIB_RULE_COUNT = 37

# Marketing buzzwords checked in heading-level elements only (h1/h2/h3/hero text).
# unleash/delve/tapestry added from skills/taste-skill/SKILL.md's cliche-copy list
# (github.com/Leonxlnx/taste-skill, MIT) — refreshed 2026-09-03.
_BUZZWORDS: frozenset[str] = frozenset({
    "streamline", "streamlines", "streamlined",
    "empower", "empowers", "empowering",
    "seamless", "seamlessly",
    "unlock", "unlocks", "unlocking",
    "unleash", "unleashes", "unleashing",
    "elevate", "elevates", "elevating",
    "revolutionize", "revolutionizes", "revolutionizing",
    "leverage", "leverages", "leveraging",
    "synergy", "synergies", "synergize",
    "cutting-edge", "next-generation", "game-changing",
    "disrupt", "disrupts", "disrupting",
    "delve", "delves", "delving",
    "tapestry",
})
# Phrase-level clichés — checked separately since they're not single tokens.
_CLICHE_PHRASES: frozenset[str] = frozenset({
    "in the world of",
})

# Selectors that contain these keywords are exempt from extreme-radius check.
# Includes pills/tags (by design) and device-frame elements (hardware mockup shapes
# whose radius reflects physical device geometry, not a design card choice).
_PILL_EXEMPT_WORDS: frozenset[str] = frozenset({
    "pill", "tag", "chip", "badge", "label", "tab", "btn", "button",
    "token", "category", "status", "dot", "indicator", "avatar",
    "device", "frame", "screen", "bezel", "chrome", "shell",
})

_CSS_BLOCK_RE = re.compile(r'([^{}/]+)\{([^}]*)\}', re.DOTALL)
_CUBICBEZ_RE = re.compile(
    r'cubic-bezier\s*\(\s*'
    r'([\d.eE+-]+)\s*,\s*([\d.eE+-]+)\s*,\s*([\d.eE+-]+)\s*,\s*([\d.eE+-]+)\s*\)'
)
_RADIUS_RE = re.compile(r'border-radius\s*:\s*([\d.]+)(px|rem|em)', re.IGNORECASE)
_OKLCH_BG_RE = re.compile(
    r'background(?:-color)?\s*:[^;]*oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)',
    re.IGNORECASE,
)
_HEADING_TEXT_RE = re.compile(
    r'<(h[123]|[^>]*class="[^"]*(?:hero|headline|cta|title)[^"]*")[^>]*>'
    r'([^<]{3,120})<',
    re.IGNORECASE,
)
# Rule 6: scale(0) — must never appear as an entrance value (HIGH)
_SCALE_ZERO_RE = re.compile(r'scale\s*\(\s*0\s*\)', re.IGNORECASE)

# CSS /* ... */ and HTML <!-- ... --> comments. Both are stripped before any
# rule scans the document -- see _stdlib_check for why this is load-bearing.
_CSS_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
_HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)


def _strip_comments(text: str) -> str:
    """Remove HTML and CSS comments, preserving everything else verbatim.

    HTML comments go first: a `<!-- ... /* ... */ ... -->` block would
    otherwise leave a dangling fragment once the inner CSS comment was cut.
    """
    return _CSS_COMMENT_RE.sub("", _HTML_COMMENT_RE.sub("", text))
# Rule 26: gpt-thin-border-wide-shadow — 1px border AND diffuse box-shadow (HIGH)
_THIN_BORDER_RE = re.compile(r'border(?:-width)?\s*:\s*1px\b', re.IGNORECASE)
# Match box-shadow blur: h-offset v-offset BLUR (third length value)
_BOX_SHADOW_BLUR_RE = re.compile(
    r'box-shadow\s*:[^;]*?(?:inset\s+)?-?[\d.]+\w*\s+-?[\d.]+\w*\s+([\d.]+)px',
    re.IGNORECASE,
)
# Rule 7: ungated hover — :hover without @media (hover: hover) wrapper (HIGH)
# Promoted from MEDIUM: a run that regressed from 3 gated hover blocks to 0
# shipped touch devices firing false hovers on every tap with nothing to
# catch it, since MEDIUM findings are advisory-only. Detect bare :hover
# rules that are NOT inside a hover media query block.
_BARE_HOVER_RE = re.compile(r':hover\s*\{', re.IGNORECASE)
_HOVER_MEDIA_RE = re.compile(
    r'@media\s*\([^)]*hover\s*:\s*hover[^)]*\)',
    re.IGNORECASE,
)
# Rule 8: ease-in on transition/animation property — applies to UI (HIGH)
_EASE_IN_PROP_RE = re.compile(
    r'(?:transition|animation)\s*:[^;]*\bease-in\b(?!\s*-out)',
    re.IGNORECASE,
)
# Rule 9: missing prefers-reduced-motion when transitions/animations exist (MEDIUM)
_ANIM_PRESENT_RE = re.compile(
    r'(?:transition|animation)\s*:',
    re.IGNORECASE,
)
_REDUCED_MOTION_RE = re.compile(
    r'prefers-reduced-motion',
    re.IGNORECASE,
)
# Rule 13: transition:all — always HIGH (animates layout props off-GPU, broad catch-all)
_TRANSITION_ALL_RE = re.compile(
    r'\btransition\s*:\s*all\b',
    re.IGNORECASE,
)


# ── Taste-Skill categorical rules ────────────────────────────────────────────
# Premium-consumer palette: background cluster (OKLCH L≈0.95-0.98, C≈0.01-0.03,
# H≈60-90). Reject hexes within deltaE 8 of these anchors.
# Anchor lists hardened against skills/taste-skill/SKILL.md's exact ban list
# (github.com/Leonxlnx/taste-skill, MIT) — refreshed 2026-09-03.
_PREMIUM_BG_ANCHORS = [
    "#f5f1ea", "#f7f5f1", "#fbf8f1", "#efeae0",
    "#ece6db", "#faf7f1", "#e8dfcb",
]
_PREMIUM_ACCENT_ANCHORS = [
    "#b08947", "#b6553a", "#9a2436",
    "#9c6e2a", "#bc7c3a", "#7d5621",
]
_PREMIUM_TEXT_ANCHORS = ["#1a1714", "#1a1814", "#1b1814"]

def _hex_to_srgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))

def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def _lab_from_hex(h: str):
    """Approximate CIE L*a*b* from hex for deltaE comparison."""
    import math
    r, g, b = (_srgb_to_linear(c) for c in _hex_to_srgb(h))
    # D65 XYZ
    X = r * 0.4124 + g * 0.3576 + b * 0.1805
    Y = r * 0.2126 + g * 0.7152 + b * 0.0722
    Z = r * 0.0193 + g * 0.1192 + b * 0.9505
    X /= 0.95047; Z /= 1.08883
    def f(t): return t ** (1/3) if t > 0.008856 else 7.787 * t + 16/116
    L = 116 * f(Y) - 16
    a = 500 * (f(X) - f(Y))
    b_ = 200 * (f(Y) - f(Z))
    return L, a, b_

def _delta_e(h1: str, h2: str) -> float:
    """CIE76 deltaE between two hex colours."""
    import math
    L1, a1, b1 = _lab_from_hex(h1)
    L2, a2, b2 = _lab_from_hex(h2)
    return math.sqrt((L1-L2)**2 + (a1-a2)**2 + (b1-b2)**2)

def _near_premium_bg(hex_color: str) -> bool:
    """True if hex_color is within deltaE 8 of a premium-consumer BACKGROUND anchor."""
    try:
        return any(_delta_e(hex_color, a) < 8.0 for a in _PREMIUM_BG_ANCHORS)
    except Exception:
        return False

def _near_premium_accent(hex_color: str) -> bool:
    """True if hex_color is within deltaE 8 of a premium-consumer ACCENT anchor."""
    try:
        return any(_delta_e(hex_color, a) < 8.0 for a in _PREMIUM_ACCENT_ANCHORS)
    except Exception:
        return False

def _hex_to_hsl_hue(h: str) -> float:
    """HSL hue (0–360°) from a 6-digit hex colour."""
    r, g, b = _hex_to_srgb(h)
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        return 0.0
    if mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return (hue * 60.0) % 360.0

def _hex_to_hsl_sat(h: str) -> float:
    """HSL saturation (0–1) from a 6-digit hex colour."""
    r, g, b = _hex_to_srgb(h)
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    d = mx - mn
    denom = 1 - abs(2 * l - 1)
    return d / denom if denom else 0.0

# Categorical (Taste-Skill) rules 17–27 — name → severity. Used by the gate table.
# Motion rules 28–31 (Emil Kowalski animation standards) appended below.
_CATEGORICAL_RULES = [
    ("premium-consumer-palette",    "HIGH"),
    ("accent-consistency",          "HIGH"),
    ("radius-system",               "HIGH"),
    ("screen-pane-redeclared",      "HIGH"),
    ("em-dash-in-copy",             "MEDIUM"),
    ("eyebrow-density",             "MEDIUM"),
    ("section-number-eyebrows",     "MEDIUM"),
    ("decorative-status-dots",      "MEDIUM"),
    ("all-caps-body",               "MEDIUM"),
    ("marquee-overuse",             "MEDIUM"),
    ("gpt-thin-border-wide-shadow", "HIGH"),
    ("undersized-ui-text",          "MEDIUM"),
    ("transition-all",              "HIGH"),    # Rule 28
    ("keyframe-enters-exits",       "MEDIUM"),  # Rule 29
    ("asymmetric-timing-absent",    "MEDIUM"),  # Rule 30
    ("blur-crossfade-missing",      "LOW"),     # Rule 31
    ("button-state-missing",        "MEDIUM"),  # Rule 32
    ("duplicate-cta-intent",        "MEDIUM"),  # Rule 33 (Taste Skill, refreshed 2026-09-03)
    ("dark-mode-pure-black-white",  "MEDIUM"),  # Rule 34 (Taste Skill, refreshed 2026-09-03)
    ("orphan-css-class",            "MEDIUM"),  # Rule 35 (Theme Forge-specific, added 2026-09-03)
]

# Motion fix-ladder ordering — lower number = higher priority in the advisory list.
_MOTION_FIX_ORDER: dict[str, int] = {
    # easing
    "weak-easing": 1, "ease-in-ui": 1,
    # origin/physicality
    "scale-zero-entrance": 2,
    # interruptibility
    "keyframe-enters-exits": 3,
    # gpu
    "layout-property-animation": 4,
    # asymmetric
    "asymmetric-timing-absent": 5,
    # polish
    "blur-crossfade-missing": 6, "transition-all": 6,
    # a11y + cohesion
    "reduced-motion-missing": 7,
}


def _motion_sort_key(finding: dict) -> int:
    return _MOTION_FIX_ORDER.get(finding.get("rule", ""), 99)

_HEX6_RE = re.compile(r'#([0-9a-fA-F]{6})\b')


def _print_categorical_gate_table(theme_name: str, findings: list[dict]) -> None:
    """Print a compact PASS/FAIL table of categorical rules 17–35 to stderr."""
    fired = {f.get("rule") for f in findings}
    _cat_rule_names = {r for r, _ in _CATEGORICAL_RULES}
    _eprint(f"  categorical gate (rules 17–35) — {theme_name}:")
    for i, (rule, sev) in enumerate(_CATEGORICAL_RULES, start=17):
        status = "FAIL" if rule in fired else "PASS"
        _eprint(f"    {i:>2d}  {rule:<28s} {sev:<6s} {status}")
    # Surface any impeccable HIGH findings that are not in the categorical set
    _imp_high = [f for f in findings
                 if f.get("severity") in ("high", "HIGH", "error")
                 and f.get("rule") not in _cat_rule_names]
    if _imp_high:
        _eprint(f"  ── impeccable HIGH findings: {len(_imp_high)} "
                f"(threshold 0: any HIGH blocks approval)")


def _motion_metrics(html: str) -> dict:
    """Measured motion counts, printed every run whether or not a rule fires.

    A PASS/FAIL column alone hides a regression that stays inside the
    threshold: transform-origin falling 12 -> 7 is a real loss of physicality
    and still passes a `>= 6` check. Printing the number makes the trend
    visible the run it happens instead of the run it finally crosses the line.
    """
    return {
        "scale_zero": len(re.findall(r'scale\(\s*0\s*(?:,\s*0\s*)?\)', html,
                                     re.IGNORECASE)),
        "transform_origin": len(re.findall(r'transform-origin\s*:', html,
                                           re.IGNORECASE)),
    }


# (rule, severity, label, metric key, minimum -- None means "must be zero")
_MOTION_METRIC_RULES = [
    ("scale-zero-entrance",     "HIGH",   "scale(0)",         "scale_zero",       None),
    ("transform-origin-sparse", "MEDIUM", "transform-origin", "transform_origin", 6),
]


def _print_motion_gate_table(theme_name: str, findings: list[dict],
                             html: str) -> None:
    """Print measured motion metrics for the stdlib motion rules.

    These are rules 1-13, which are separate from the categorical 17-35 table.
    They were invisible in stderr entirely before: the categorical table starts
    at 17, so a HIGH scale(0) finding never appeared in any printed gate output.
    """
    fired = {f.get("rule") for f in findings}
    metrics = _motion_metrics(html)
    _eprint(f"  motion gate (stdlib rules 1-13) — {theme_name}:")
    for rule, sev, label, key, minimum in _MOTION_METRIC_RULES:
        n = metrics.get(key, 0)
        if minimum is None:
            want, ok = "must be 0", n == 0
        else:
            want, ok = f"need >= {minimum}", n >= minimum
        status = "FAIL" if (rule in fired or not ok) else "PASS"
        _eprint(f"    {rule:<28s} {sev:<6s} {status}   {label} = {n} ({want})")


def _stdlib_rules_1_13(html: str) -> list[dict]:
    """Run Rules 1-13 (motion / visual / copy) on an already-read HTML string.
    Returns finding dicts. Called by _stdlib_check when categorical_only=False."""
    findings: list[dict] = []

    # --- Rule 1: easing-overshoot (severity: high) ----------------------------
    # cubic-bezier with y2 > 1 is banned from CSS (rule 39 in 13-anti-patterns).
    for m in _CUBICBEZ_RE.finditer(html):
        try:
            y2 = float(m.group(4))
        except ValueError:
            continue
        if y2 > 1.0:
            findings.append({
                "rule": "easing-overshoot",
                "severity": "high",
                "category": "motion",
                "source": "stdlib",
                "message": (
                    f"cubic-bezier y2={y2} > 1 — overshoot/bounce easing banned in CSS "
                    f"(rule 39). Use ease-out-expo cubic-bezier(0.19,1,0.22,1) instead."
                ),
                "element": m.group(0)[:80],
            })

    # --- Rule 2: marketing-buzzword (severity: medium) ------------------------
    # Flag buzzwords (and cliche phrases) appearing inside heading-level text nodes.
    for m in _HEADING_TEXT_RE.finditer(html):
        text = m.group(2)
        text_lower = text.lower()
        words = re.split(r'\W+', text_lower)
        hit = next((w for w in words if w in _BUZZWORDS), None)
        if hit is None:
            hit = next((p for p in _CLICHE_PHRASES if p in text_lower), None)
        if hit is not None:
            findings.append({
                "rule": "marketing-buzzword",
                "severity": "medium",
                "category": "copy",
                "source": "stdlib",
                "message": (
                    f"Cliche \"{hit}\" in heading copy — reads as AI-generated "
                    f"marketing register. Use concrete, specific language."
                ),
                "element": text[:80].strip(),
            })

    # --- Rule 3: extreme-radius-card (severity: medium) ----------------------
    # border-radius > 16px on non-pill, non-button selectors (anti-pattern rule 41).
    for m in _CSS_BLOCK_RE.finditer(html):
        selector = m.group(1).strip().lower()
        # Skip selectors that are clearly pills/tags/buttons
        if any(ex in selector for ex in _PILL_EXEMPT_WORDS):
            continue
        # Also skip variable declarations and @-rules
        if selector.startswith(('@', '--', '/*', '*')):
            continue
        for rm in _RADIUS_RE.finditer(m.group(2)):
            try:
                val = float(rm.group(1))
            except ValueError:
                continue
            unit = rm.group(2).lower()
            threshold = 16 if unit == 'px' else (1.0 if unit == 'rem' else 0)
            if threshold and val > threshold:
                findings.append({
                    "rule": "extreme-radius-card",
                    "severity": "medium",
                    "category": "layout",
                    "source": "stdlib",
                    "message": (
                        f"border-radius {val}{unit} > 16px on \"{selector[:60]}\" "
                        f"— card/container radii cap at 16px. "
                        f"Full-pill (9999px) is permitted only on pills, tags, chips, badges, buttons."
                    ),
                    "element": selector[:80],
                })

    # --- Rule 4: cream-ground-overflow (severity: medium) --------------------
    # More than one theme slot with warm cream background (OKLCH L>0.88, H 40–80°).
    # Here we flag the presence per preview (set-level enforcement is tf_distinct.py).
    for m in _OKLCH_BG_RE.finditer(html):
        try:
            L, _C, H = float(m.group(1)), float(m.group(2)), float(m.group(3))
        except ValueError:
            continue
        if L > 0.88 and 40 <= H <= 80:
            findings.append({
                "rule": "cream-ground",
                "severity": "medium",
                "category": "color",
                "source": "stdlib",
                "message": (
                    f"Warm cream background oklch({L:.2f} {_C:.3f} {H:.0f}) — "
                    f"this palette reads as AI-generated (rule 29 in 13-anti-patterns). "
                    f"Shift to a cooler or darker neutral unless this slot owns the cream lane."
                ),
                "element": m.group(0)[:80],
            })
            break  # one finding per theme

    # --- Rule 5: gradient-text-missing-fallback (severity: medium) -----------
    # background-clip: text without -webkit-text-fill-color fallback is invisible on some browsers.
    if re.search(r'background-clip\s*:\s*text', html, re.IGNORECASE):
        if not re.search(r'-webkit-text-fill-color', html, re.IGNORECASE):
            findings.append({
                "rule": "gradient-text-no-fallback",
                "severity": "medium",
                "category": "visual-details",
                "source": "stdlib",
                "message": (
                    "background-clip: text found without -webkit-text-fill-color: transparent — "
                    "gradient text is invisible in Firefox without the vendor prefix fallback."
                ),
                "element": "background-clip: text",
            })

    # --- Rule 6: scale-zero-entrance (severity: high) -------------------------
    # scale(0) as an entrance value — nothing appears from nothing (Emil Kowalski).
    # Detect scale(0) in CSS; flag once per theme since it likely appears in a keyframe
    # or transition start state.
    if _SCALE_ZERO_RE.search(html):
        findings.append({
            "rule": "scale-zero-entrance",
            "severity": "high",
            "category": "motion",
            "source": "stdlib",
            "message": (
                "scale(0) detected — entrance from zero looks like it comes from nowhere. "
                "Use scale(0.95) + opacity: 0 instead. Nothing in the real world appears from nothing."
            ),
            "element": "scale(0)",
        })

    # --- Rule 7: ungated-hover (severity: high) --------------------------------
    # :hover motion without @media (hover: hover) fires false hovers on touch devices.
    # Flag if bare :hover rules exist AND no hover media query is present.
    if _BARE_HOVER_RE.search(html) and not _HOVER_MEDIA_RE.search(html):
        findings.append({
            "rule": "ungated-hover",
            "severity": "high",
            "category": "motion",
            "source": "stdlib",
            "message": (
                ":hover styles found without @media (hover: hover) and (pointer: fine) gating — "
                "touch devices fire false hovers on tap. Wrap all :hover motion in the media query."
            ),
            "element": ":hover {}",
        })

    # --- Rule 8: ease-in-on-transition (severity: high) -----------------------
    # ease-in on a CSS transition/animation starts slow, delaying the moment the user watches.
    # This is always a finding on UI elements (Emil Kowalski: "ease-in on UI is always a finding").
    m8 = _EASE_IN_PROP_RE.search(html)
    if m8:
        findings.append({
            "rule": "ease-in-on-transition",
            "severity": "high",
            "category": "motion",
            "source": "stdlib",
            "message": (
                "ease-in easing on transition/animation — starts slow, delaying the exact moment "
                "the user is watching most. Use ease-out or cubic-bezier(0.23, 1, 0.32, 1) instead."
            ),
            "element": m8.group(0)[:80],
        })

    # --- Rule 9: missing-reduced-motion (severity: medium) --------------------
    # If the file has transitions or animations but no prefers-reduced-motion media query,
    # vestibular accessibility is unhandled. Gentler-not-zero: keep opacity, drop movement.
    if _ANIM_PRESENT_RE.search(html) and not _REDUCED_MOTION_RE.search(html):
        findings.append({
            "rule": "missing-reduced-motion",
            "severity": "medium",
            "category": "accessibility",
            "source": "stdlib",
            "message": (
                "Transitions/animations found but no @media (prefers-reduced-motion: reduce) block. "
                "Reduced motion means gentler-not-zero: keep opacity crossfades, drop movement."
            ),
            "element": "transition / animation",
        })

    # --- Rule 10: active-sparse (severity: medium) --------------------------------
    # Ratio-based, not an absolute count: a fixed "need >= 25" threshold was tuned
    # to the old shared component library's interactive-element inventory. A
    # genuinely bespoke, minimalist surface can legitimately have far fewer total
    # interactive elements, and an absolute count would false-positive on it.
    # Instead compare :active rule count against a coarse interactive-element
    # count (button/a/input/select/textarea tags) -- skip entirely on surfaces
    # with too few interactive elements to make a ratio meaningful.
    _active_count = len(re.findall(r':active\s*\{', html, re.IGNORECASE))
    _interactive_count = len(re.findall(
        r'<(?:button|a|input|select|textarea)\b', html, re.IGNORECASE))
    _ACTIVE_RATIO_MIN = 0.5
    _ACTIVE_MIN_SAMPLE = 3
    if _interactive_count >= _ACTIVE_MIN_SAMPLE:
        _active_ratio = _active_count / _interactive_count
        if _active_ratio < _ACTIVE_RATIO_MIN:
            findings.append({
                "rule": "active-sparse",
                "severity": "medium",
                "category": "motion",
                "source": "stdlib",
                "message": (
                    f"{_active_count} :active rule(s) for {_interactive_count} interactive "
                    f"element(s) (ratio {_active_ratio:.2f}, need ≥ {_ACTIVE_RATIO_MIN:.2f}) — "
                    "most interactive elements lack press feedback. "
                    "Every button, card, nav item, table row, tab item, and list row "
                    "needs transform: scale(0.97) with transition: transform 160ms ease-out on :active."
                ),
                "element": f":active={_active_count}, interactive={_interactive_count}",
            })

    # --- Rule 11: transform-origin-sparse (severity: medium) ----------------------
    # Fewer than 6 transform-origin declarations means overlays don't scale from their trigger.
    # Popovers, menus, and dropdowns should expand from the point of the trigger element.
    _to_count = len(re.findall(r'transform-origin\s*:', html, re.IGNORECASE))
    if _to_count < 6:
        findings.append({
            "rule": "transform-origin-sparse",
            "severity": "medium",
            "category": "motion",
            "source": "stdlib",
            "message": (
                f"Only {_to_count} transform-origin declaration(s) found (need ≥ 6) — "
                "popovers, menus, and dropdowns should scale from transform-origin set "
                "at their trigger point, not from element center."
            ),
            "element": f"transform-origin count = {_to_count}",
        })

    # --- Rule 12: entrance-feedback-ratio (severity: medium) ----------------------
    # Entrance-style transitions vs press-feedback declarations. Ratio > 4:1 means the
    # theme animates entrances heavily but ignores press response.
    # (Hover-gating absence is already covered by rule 7 ungated-hover.)
    _trans_count = len(re.findall(r'\btransition\s*:', html, re.IGNORECASE))
    _active_count_fb = len(re.findall(r':active\s*\{', html, re.IGNORECASE))
    _ratio = _trans_count / max(1, _active_count_fb)
    if _ratio > 4.0:
        findings.append({
            "rule": "entrance-feedback-ratio",
            "severity": "medium",
            "category": "motion",
            "source": "stdlib",
            "message": (
                f"Entrance-to-feedback ratio {_trans_count}:{_active_count_fb} "
                f"({_ratio:.0f}:1 — threshold 4:1). "
                "Far more transition declarations than :active press-feedback rules. "
                "Add transform: scale(0.97) on :active to all interactive elements."
            ),
            "element": f"transition:{_trans_count} vs :active:{_active_count_fb}",
        })

    # --- Rule 13: transition-all (severity: high) ---------------------------------
    # transition:all animates unintended properties (width, height, margin, padding)
    # off the GPU compositor. Every occurrence is a finding; no threshold.
    for _m in _TRANSITION_ALL_RE.finditer(html):
        findings.append({
            "rule": "transition-all",
            "severity": "high",
            "category": "motion",
            "source": "stdlib",
            "message": (
                "transition: all found — animates every CSS property including layout "
                "properties (width, height, margin) off the GPU. Name the property "
                "explicitly: transition: transform, opacity, clip-path."
            ),
            "element": "transition: all",
        })
        break  # one finding per theme is enough

    # --- Rule 36: weak-easing-only (severity: high) ---------------------------
    # A theme with real transitions/animations but zero custom cubic-bezier
    # curves anywhere is running entirely on browser-default timing functions
    # (bare `ease`/`ease-in-out`/`linear`, or no easing declared at all) --
    # a regression from an engineered motion system back to unstyled defaults.
    # Flag only when motion actually exists (an intentionally near-static
    # surface with no transitions/animations at all is not this bug).
    if _ANIM_PRESENT_RE.search(html) and not _CUBICBEZ_RE.search(html):
        findings.append({
            "rule": "weak-easing-only",
            "severity": "high",
            "category": "motion",
            "source": "stdlib",
            "message": (
                "Transitions/animations are present but no custom cubic-bezier() curve "
                "appears anywhere in the file -- every one of them is relying on a bare "
                "browser-default easing (ease, ease-in-out, linear, or none declared). "
                "Name an explicit curve matching this theme's motion.character "
                "(e.g. cubic-bezier(0.23, 1, 0.32, 1) for a strong ease-out)."
            ),
            "element": "no cubic-bezier() found",
        })

    return findings


def _stdlib_check(preview: Path, categorical_only: bool = False) -> list[dict]:
    """Run 35 static rules on preview.html. Returns finding dicts (same schema as impeccable).
    Pass categorical_only=True to run only Rules 14-35 (theme.json + categorical patterns)."""
    try:
        html = preview.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # Comments are stripped before any rule runs. A surface that correctly
    # documents its own compliance in a comment must not trip the very rule it
    # is confirming it passes -- matching raw text flags the explanation, not
    # the code. Confirmed live: three themes hard-stopped on
    # `scale-zero-entrance` whose ONLY occurrence of `scale(0)` was a CSS
    # comment reading "Never from scale(0): nothing in the real world appears
    # from nothing" -- i.e. the rule fired on the sentence stating the rule was
    # obeyed, while no such transform existed anywhere in the file.
    # tf_content.py's document-wrapper check already carries this same fix for
    # the same reason; this is that lesson applied to the anti-slop rules.
    # Applied once here rather than per rule so no future rule reintroduces it,
    # and safe for the copy-scanning rules too (em-dash, all-caps, buzzwords):
    # comment prose is never user-visible copy, so it should not be judged as
    # copy either. No finding in this file reports a line number, so removing
    # spans cannot desynchronise reported locations.
    html = _strip_comments(html)

    findings: list[dict] = []

    if not categorical_only:
        findings += _stdlib_rules_1_13(html)

    # --- Rule 14: webapp-duration-over-budget (severity: medium) ------------------
    # If the theme declares motion_budget.webapp = "near-imperceptible" but
    # motion.duration.normal > 300ms, the app surface exceeds its budget.
    # Reads theme.json from the same directory as preview.html.
    _theme_json = preview.parent / "theme.json"
    if _theme_json.is_file():
        try:
            _tj = json.loads(_theme_json.read_text(encoding="utf-8"))
            _mb = (_tj.get("motion") or {}).get("motion_budget") or {}
            _webapp_budget = _mb.get("webapp", "")
            _dur = (_tj.get("motion") or {}).get("duration") or {}
            _dur_normal = _dur.get("normal", 0)
            if (
                _webapp_budget in ("near-imperceptible", "feedback-only")
                and isinstance(_dur_normal, (int, float))
                and _dur_normal > 300
            ):
                findings.append({
                    "rule": "webapp-duration-over-budget",
                    "severity": "medium",
                    "category": "motion",
                    "source": "stdlib",
                    "message": (
                        f"motion.duration.normal = {_dur_normal}ms exceeds the 300ms webapp "
                        f"budget (motion_budget.webapp = \"{_webapp_budget}\"). "
                        f"Daily-tool surfaces must stay under 300ms — reduce to 150–250ms."
                    ),
                    "element": f"motion.duration.normal = {_dur_normal}ms",
                })
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    # --- Rule 15: opacity-zero-rest-state (severity: high) --------------------
    # opacity: 0 as a CSS rest-state on text-bearing elements, without
    # animation-fill-mode: backwards/both or @starting-style, hides content
    # permanently when animations don't fire (JS off, reduced-motion, slow network,
    # Playwright screenshots). Content must default to visible at rest.
    # Strip @keyframes AND @starting-style block BODIES first: opacity:0 inside
    # either is the documented, correct mechanism for a "before" state, not a
    # rest-state bug. This must be a strip, not a file-wide presence check —
    # a single @starting-style block anywhere used to add a flat +1000 to the
    # protected count, vacuously passing the file regardless of how many
    # genuinely unprotected opacity:0 rest-states existed elsewhere in the same
    # file. That let real rest-state bugs through as long as the file also
    # happened to use @starting-style correctly once, somewhere unrelated.
    _html_no_kf = re.sub(
        r'@keyframes\s+\S+\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        '', html, flags=re.DOTALL | re.IGNORECASE,
    )
    _html_no_kf_no_ss = re.sub(
        r'@starting-style\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        '', _html_no_kf, flags=re.DOTALL | re.IGNORECASE,
    )
    # Strip @media (prefers-reduced-motion: reduce) block BODIES too: turning a
    # purely decorative effect off under this media query (opacity:0 on a
    # scan-line sweep, a shimmer, a parallax layer) is the a11y-correct
    # response to the user's stated preference, not a "content permanently
    # hidden" bug -- it is the opposite failure mode Rule 15 exists to catch.
    _html_no_kf_no_ss = re.sub(
        r'@media\s*\([^{}]*prefers-reduced-motion[^{}]*\)\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        '', _html_no_kf_no_ss, flags=re.DOTALL | re.IGNORECASE,
    )
    # Per-selector, not whole-file: a real theme legitimately has toasts,
    # native <dialog>/[popover], and JS/attribute-driven dropdowns that start
    # at opacity:0 and are shown by a controlled state change, not a
    # permanently-hidden-content bug. Checked against six real generated
    # themes: every remaining hit after the @keyframes/@starting-style strip
    # was exactly one of these three legitimate patterns -- a naive file-wide
    # count would hard-fail 100% of themes on correct code.
    _NATIVE_TOGGLE_SELECTOR_RE = re.compile(
        r'popover|dialog|::backdrop|dropdown|\[data-state|:not\(\[open\]\)|'
        r':not\(:popover-open\)|\[aria-hidden|\[aria-expanded',
        re.IGNORECASE,
    )
    # (?![.\d]) rather than \b: \b sits between "0" and "." too, so a bare \b
    # boundary let "opacity: 0.3" / "opacity: 0.03" miscount as opacity:0 --
    # inflating the count with legitimate partial-opacity values that were
    # never a rest-state-hiding bug in the first place.
    _OPACITY0_RE = re.compile(r'opacity\s*:\s*0(?![.\d])', re.IGNORECASE)
    _OPACITY1_RE = re.compile(r'opacity\s*:\s*1(?![.\d])', re.IGNORECASE)
    _STATE_SUFFIX_RE = re.compile(
        r'\.is-[\w-]+|\.[\w-]*-open\b|\.[\w-]*-active\b|\.[\w-]*-visible\b|'
        r'\.[\w-]*-revealed\b|\.[\w-]*-shown\b|\.[\w-]*-expanded\b|'
        r'\[open\]|:popover-open|:checked|:hover|:focus(?:-visible|-within)?|'
        r'data-state\s*=\s*["\'](?:open|visible)["\']',
        re.IGNORECASE,
    )
    # A native <input type="checkbox"/"radio"> visually hidden behind a custom
    # control (a switch, a tab, a segmented option) is legitimately opacity:0
    # forever -- the whole point is that it never becomes visible; the box it
    # occupies is exactly overlaid by its own custom-styled sibling/label. This
    # is a different failure mode entirely from "content stuck invisible": the
    # element is functional (focusable, clickable, screen-reader-visible) even
    # though visually opacity:0. Recognized by the well-established shape of
    # the pattern -- opacity:0 alongside a near-zero physical footprint.
    _HIDDEN_INPUT_SIZE_RE = re.compile(
        r'(?:width|height)\s*:\s*(?:0(?:px)?|1px)\b', re.IGNORECASE,
    )
    # A second, equally common shape of the same pattern: instead of shrinking
    # the native input to ~0px, it's stretched to fully cover its custom-styled
    # sibling (inset:0 or 100%/100%) so the whole visible control is clickable,
    # not just a hidden 1px corner. Gated on the selector itself plausibly
    # naming a real form control (contains "input"), since a full-cover
    # opacity:0 overlay with no such naming signal could instead be a modal
    # scrim that genuinely needs a companion toggle -- unlike the tiny-box
    # shape above, "covers 100% of its parent" alone isn't a safe signal.
    _HIDDEN_INPUT_COVER_RE = re.compile(
        r'inset\s*:\s*0\b|(?=.*width\s*:\s*100%)(?=.*height\s*:\s*100%)',
        re.IGNORECASE | re.DOTALL,
    )
    _INPUT_NAME_RE = re.compile(r'input', re.IGNORECASE)
    _FIRST_CLASS_RE = re.compile(r'\.([a-zA-Z_][\w-]*)')

    def _r15_on_form_control(cls: str) -> bool:
        """Is *cls* actually carried by a form control in this document?

        Ground truth from the markup, replacing a guess about the class NAME.
        The full-cover branch of the visually-hidden-input exemption used to
        require the selector to contain the literal substring "input", which
        is a naming-convention assumption rather than a fact -- and two real
        themes hard-stopped on it by abbreviating: `.dp-chip-in` and
        `.agecell-in` are both genuine <input> elements stretched over their
        own custom-styled label (`position:absolute; inset:0; opacity:0;
        cursor:pointer`), with their visible state carried by a companion
        `:checked + .sibling` / `:has(.x:checked)` rule. That is the correct,
        accessible custom-control pattern: the input must stay hit-testable and
        focusable, so `pointer-events:none` would be wrong, and its opacity
        never returns to 1 by design -- so none of the rule's other escape
        hatches apply either. Asking the HTML whether the class sits on an
        <input>/<select>/<textarea> settles it without guessing at names.
        """
        if not cls:
            return False
        return re.search(
            r'<(?:input|select|textarea)\b[^>]*\bclass\s*=\s*["\'][^"\']*\b%s\b'
            % re.escape(cls),
            html, re.IGNORECASE,
        ) is not None

    _r15_unprotected: list[str] = []
    for _r15m in _CSS_BLOCK_RE.finditer(_html_no_kf_no_ss):
        _r15_sel, _r15_body = _r15m.group(1).strip(), _r15m.group(2)
        if _r15_sel.startswith(('@', '--', '/*', '*')):
            continue  # at-rule wrapper (e.g. @supports (...) {) or var decl, not a real selector --
            # _CSS_BLOCK_RE has no concept of nested at-rules, so a naive brace
            # match on "@supports (animation-timeline: scroll()) {" would
            # otherwise misread the at-rule's own opening line as if it were
            # a selector whose "body" is the first nested rule's insides.
        if not _OPACITY0_RE.search(_r15_body):
            continue
        if re.search(r'animation-fill-mode\s*:\s*(backwards|both)\b', _r15_body, re.IGNORECASE):
            continue  # protected via the longhand property
        if re.search(r'animation\s*:[^;]*\b(?:backwards|both)\b', _r15_body, re.IGNORECASE):
            continue  # protected via "both"/"backwards" inside the animation SHORTHAND --
            # e.g. "animation: reveal-in 400ms ease-out both;" is exactly as
            # protected as the longhand form and is the more common way real
            # authored CSS actually writes this.
        if re.search(r'pointer-events\s*:\s*none', _r15_body, re.IGNORECASE):
            continue  # toast/scrim: inert until a controlled state shows it
        if _NATIVE_TOGGLE_SELECTOR_RE.search(_r15_sel):
            continue  # native or explicit-state show/hide primitive
        _r15_first_cls_m = _FIRST_CLASS_RE.search(_r15_sel)
        _r15_first_cls = _r15_first_cls_m.group(1) if _r15_first_cls_m else ""
        if re.search(r'position\s*:\s*absolute', _r15_body, re.IGNORECASE) and (
            _HIDDEN_INPUT_SIZE_RE.search(_r15_body)
            or (
                _HIDDEN_INPUT_COVER_RE.search(_r15_body)
                and (
                    _INPUT_NAME_RE.search(_r15_sel)
                    or _r15_on_form_control(_r15_first_cls)
                )
            )
        ):
            continue  # visually-hidden native form control (see note above) --
            # opacity:0 is the permanent, correct state here, not a bug
        _r15_base = _FIRST_CLASS_RE.search(_r15_sel)
        if _r15_base:
            # Does this same base class have a companion "shown" rule
            # elsewhere in the file that resolves opacity to 1? Two real
            # shapes both count: a compound toggle on the same token
            # (".foo.is-visible { opacity: 1 }") and an ancestor-state
            # descendant selector (".scrim.is-open .foo { opacity: 1 }",
            # e.g. a modal shown via its scrim's state class) -- the state
            # class and the target class don't have to be the same token,
            # so this checks "does the base class appear as a whole word
            # anywhere in a selector that also carries a state suffix
            # anywhere, in a rule that sets opacity:1", not just adjacency.
            _r15_class_word_re = re.compile(
                r'\.' + re.escape(_r15_base.group(1)) + r'\b', re.IGNORECASE,
            )
            _r15_has_toggle = any(
                _r15_class_word_re.search(_cm.group(1))
                and _STATE_SUFFIX_RE.search(_cm.group(1))
                and _OPACITY1_RE.search(_cm.group(2))
                for _cm in _CSS_BLOCK_RE.finditer(_html_no_kf_no_ss)
            )
            if _r15_has_toggle:
                continue
        else:
            # No class anywhere in the selector -- a bare tag/combinator chain
            # such as "details > p" (the native disclosure-widget pattern,
            # resolved by "details[open] > p" elsewhere). Match on the last
            # simple selector segment (the "p") combined with a state suffix
            # anywhere in that companion rule's selector.
            _r15_tail = re.search(r'([a-zA-Z][\w-]*)\s*$', _r15_sel)
            if _r15_tail:
                _r15_tail_re = re.compile(
                    r'\b' + re.escape(_r15_tail.group(1)) + r'\b', re.IGNORECASE,
                )
                _r15_has_toggle = any(
                    _r15_tail_re.search(_cm.group(1))
                    and _STATE_SUFFIX_RE.search(_cm.group(1))
                    and _OPACITY1_RE.search(_cm.group(2))
                    for _cm in _CSS_BLOCK_RE.finditer(_html_no_kf_no_ss)
                )
                if _r15_has_toggle:
                    continue
        _r15_unprotected.append(_r15_sel[:60])

    if _r15_unprotected:
        findings.append({
            "rule": "opacity-zero-rest-state",
            "severity": "high",
            "category": "motion",
            "source": "stdlib",
            "message": (
                f"{len(_r15_unprotected)} selector(s) set opacity:0 at rest with no "
                f"animation-fill-mode:backwards/both, no pointer-events:none inert-until-shown "
                f"signal, and no companion .is-visible/[open]-style selector that resolves it "
                f"back to opacity:1 anywhere in the file: {', '.join(_r15_unprotected[:5])}. "
                "Content must default to visible. Remove opacity:0 from rest state; "
                "use animation-fill-mode:backwards, or move the opacity:0 declaration "
                "into an @starting-style block instead."
            ),
            "element": ", ".join(_r15_unprotected[:3]),
        })

    # --- Rule 16: motion-budget-missing (severity: high) ----------------------
    # motion_budget must be declared in theme.json. Without it the webapp surface
    # receives the same full-delight treatment as the marketing site, which contradicts
    # Emil Kowalski's frequency gate: tens-of-times-daily earns near-imperceptible only.
    if _theme_json.is_file():
        try:
            _tj2 = json.loads(_theme_json.read_text(encoding="utf-8"))
            _mb2 = (_tj2.get("motion") or {}).get("motion_budget")
            if not _mb2:
                findings.append({
                    "rule": "motion-budget-missing",
                    "severity": "high",
                    "category": "motion",
                    "source": "stdlib",
                    "message": (
                        "motion.motion_budget not declared in theme.json. "
                        "Required: website='full', webapp='near-imperceptible', "
                        "mobile per-screen (onboarding/success/empty='delight', feed/detail='feedback-only')."
                    ),
                    "element": "motion.motion_budget",
                })
            elif (_mb2.get("webapp") or "") not in ("near-imperceptible", "feedback-only", "minimal"):
                findings.append({
                    "rule": "motion-budget-webapp",
                    "severity": "high",
                    "category": "motion",
                    "source": "stdlib",
                    "message": (
                        f"motion_budget.webapp = \"{_mb2.get('webapp')}\" — "
                        "webapp surface must be near-imperceptible or feedback-only. "
                        "No decorative entrances on data the user is reading; "
                        "feedback micro-interactions only."
                    ),
                    "element": f"motion_budget.webapp = {_mb2.get('webapp')!r}",
                })
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # Taste-Skill categorical rules (17–25) — adapted from Taste Skill v2
    # (github.com/Leonxlnx/taste-skill, MIT). HIGH: 17–19; MEDIUM: 20–25.
    # ══════════════════════════════════════════════════════════════════════════
    _cat_tj: dict = {}
    if _theme_json.is_file():
        try:
            _cat_tj = json.loads(_theme_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError):
            _cat_tj = {}
    _cat_color = _cat_tj.get("color") or {}
    _cat_light = _cat_color.get("light") or {}
    _cat_dark  = _cat_color.get("dark") or {}

    # --- Rule 17: premium-consumer-palette (severity: high) -------------------
    # The tell is the COMBINATION: warm-beige/cream BACKGROUND with brass/clay/oxblood
    # ACCENT. Role-partitioned — background checked only against BG anchors, accent only
    # against ACCENT anchors. Both must match to fire (AND-gate). This prevents dark
    # backgrounds matching the near-black espresso text anchor, and cool near-whites
    # matching cream BG anchors.
    _cat_bg_hex  = (_cat_light.get("background") or {}).get("hex") or ""
    _cat_acc_hex = (_cat_light.get("accent") or {}).get("hex") or ""
    _bg_is_premium  = bool(_cat_bg_hex  and len(_cat_bg_hex.lstrip("#"))  == 6
                           and _near_premium_bg(_cat_bg_hex))
    _acc_is_premium = bool(_cat_acc_hex and len(_cat_acc_hex.lstrip("#")) == 6
                           and _near_premium_accent(_cat_acc_hex))
    if _bg_is_premium and _acc_is_premium:
        findings.append({
            "rule": "premium-consumer-palette",
            "severity": "high",
            "category": "color",
            "source": "stdlib",
            "message": (
                "Premium-consumer palette detected: warm beige/cream background + "
                "brass/clay/oxblood accent is the most overused AI-generated luxury "
                "aesthetic. Choose a background that cannot be mistaken for warm "
                "off-white paper, or choose an accent that reads as a real brand colour."
            ),
            "element": f"bg={_cat_bg_hex}, accent={_cat_acc_hex}",
        })

    # --- Rule 18: accent-consistency (severity: high) -------------------------
    _acc_light_hex = (_cat_light.get("accent") or {}).get("hex") or ""
    _acc_dark_hex  = (_cat_dark.get("accent") or {}).get("hex") or ""
    if (_acc_light_hex and _acc_dark_hex
            and len(_acc_light_hex.lstrip("#")) == 6
            and len(_acc_dark_hex.lstrip("#")) == 6):
        try:
            _sat_l = _hex_to_hsl_sat(_acc_light_hex)
            _sat_d = _hex_to_hsl_sat(_acc_dark_hex)
            # Exclude near-neutrals — a hue value on a grey accent is meaningless.
            if _sat_l >= 0.05 and _sat_d >= 0.05:
                _hue_l = _hex_to_hsl_hue(_acc_light_hex)
                _hue_d = _hex_to_hsl_hue(_acc_dark_hex)
                _hue_diff = abs(_hue_l - _hue_d) % 360.0
                _hue_diff = min(_hue_diff, 360.0 - _hue_diff)
                if _hue_diff > 30.0:
                    findings.append({
                        "rule": "accent-consistency",
                        "severity": "high",
                        "category": "color",
                        "source": "stdlib",
                        "message": (
                            f"Multiple accent hues at rest across surfaces "
                            f"(light {_acc_light_hex} hue {_hue_l:.0f}°, dark "
                            f"{_acc_dark_hex} hue {_hue_d:.0f}°, Δ{_hue_diff:.0f}° > 30°). "
                            f"A theme must have one accent hue that stays consistent "
                            f"across light and dark modes; the value can lighten/darken "
                            f"but the hue must not shift more than 30°."
                        ),
                        "element": f"{_acc_light_hex} / {_acc_dark_hex}",
                    })
        except Exception:
            pass

    # --- Rule 19: radius-system (severity: high) ------------------------------
    _cat_radius = _cat_tj.get("radius") or {}
    _radius_vals: set[float] = set()
    if isinstance(_cat_radius, dict):
        for _rv in _cat_radius.values():
            if isinstance(_rv, dict):
                _px = _rv.get("px")
                if isinstance(_px, (int, float)):
                    _radius_vals.add(float(_px))
    _radius_vals.discard(0.0)
    # A "full/pill" stadium-shape sentinel isn't a real corner-radius step --
    # it's a "fully round" designation, conventionally written as 999px or
    # 9999px (either renders identically once the value exceeds half the
    # element's height). Discarding only the literal 9999.0 missed every
    # theme in this run, which all wrote 999 -- undercounting nothing but
    # inflating the "distinct steps" count by one for every theme that uses
    # the equally common 999px spelling. Any value this large is never a
    # legitimate small-radius step, so treat the whole range as the sentinel.
    _radius_vals = {v for v in _radius_vals if v < 100.0}
    if len(_radius_vals) > 5:
        findings.append({
            "rule": "radius-system",
            "severity": "high",
            "category": "layout",
            "source": "stdlib",
            "message": (
                f"{len(_radius_vals)} distinct radius values — no coherent radius "
                f"system. A radius system has ≤5 steps (none/sm/md/lg/xl/full); values "
                f"beyond that are ad hoc and break the spatial grammar."
            ),
            "element": str(sorted(_radius_vals)),
        })

    # --- Rule 19b: screen-pane-redeclared (severity: high) --------------------
    # .screen-pane is shared device-frame geometry owned by templates/gallery.css
    # (safe-area padding, flex layout, and -- as of the fix this rule exists to
    # protect -- overflow-y:auto + hidden scrollbars, so a theme's mobile screen
    # scrolls instead of silently clipping content taller than the device frame,
    # with no visible browser-chrome scrollbar). surface-composer.md already
    # tells agents never to redeclare it, but that was instruction only until
    # this rule existed -- a theme's own mobile.css is assembled INTO THE SAME
    # DOCUMENT after templates/gallery.css (see gallery.shell.html's placeholder
    # order), so a theme rule at equal CSS specificity silently wins the
    # cascade tie by simply coming later, undoing the shared fix for that one
    # theme with no visible error anywhere. Scoped to the @scope(...screen-pane)
    # block tf_gallery.py wraps each theme's own mobile.css in, so the shared
    # rule in templates/gallery.css itself is never the thing being flagged.
    _scope_m = re.search(
        r'@scope\s*\([^)]*\.screen-pane[^)]*\)\s*\{', html, re.IGNORECASE,
    )
    if _scope_m:
        _depth = 1
        _pos = _scope_m.end()
        while _depth > 0 and _pos < len(html):
            _ch = html[_pos]
            if _ch == '{':
                _depth += 1
            elif _ch == '}':
                _depth -= 1
            _pos += 1
        _scope_body = html[_scope_m.end():_pos - 1]
        _redecl_m = re.search(
            r'(?:^|\})\s*\.screen-pane\s*\{([^{}]*)\}', _scope_body, re.DOTALL,
        )
        if _redecl_m and re.search(
            r'\boverflow(?:-[xy])?\s*:|scrollbar-width\s*:',
            _redecl_m.group(1), re.IGNORECASE,
        ):
            findings.append({
                "rule": "screen-pane-redeclared",
                "severity": "high",
                "category": "layout",
                "source": "stdlib",
                "message": (
                    "This theme's own mobile.css redeclares .screen-pane's overflow/"
                    "scrollbar-width -- .screen-pane is shared device-frame geometry "
                    "(see agents/surface-composer.md) and must not be touched. Because "
                    "theme CSS is assembled after templates/gallery.css, this silently "
                    "wins the cascade tie and can reintroduce clipped, unreachable "
                    "content or a visible non-native scrollbar on this theme's mobile "
                    "screens. Remove the .screen-pane rule from this theme's mobile.css."
                ),
            })

    # --- Rule 20: em-dash-in-copy (severity: medium) --------------------------
    _emdash_re = re.compile(r'—|&mdash;|&#8212;')
    _emdash_hit: str | None = None
    for _mm in _HEADING_TEXT_RE.finditer(html):
        if _emdash_re.search(_mm.group(2)):
            _emdash_hit = _mm.group(2)[:80].strip()
            break
    if _emdash_hit is None:
        for _mm in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.IGNORECASE | re.DOTALL):
            if _emdash_re.search(_mm.group(1)):
                _emdash_hit = re.sub(r'<[^>]+>', '', _mm.group(1))[:80].strip()
                break
    if _emdash_hit is not None:
        findings.append({
            "rule": "em-dash-in-copy",
            "severity": "medium",
            "category": "copy",
            "source": "stdlib",
            "message": (
                "Em-dash found in UI copy. Replace with a comma, colon, or restructure "
                "the sentence. Em-dashes in UI copy are a copywriting tic, not punctuation."
            ),
            "element": _emdash_hit or "—",
        })

    # --- Rule 21: eyebrow-density (severity: medium) --------------------------
    # Structural section count, not a literal '<section>' tag count: a bespoke
    # theme may landmark its content sections with <div role="region">,
    # <article>, or another tag entirely. A literal-tag count silently returns
    # 0 (and no-ops this whole rule) on any theme that doesn't use <section>.
    _section_count = tf_htmlshape.count_sections(tf_htmlshape.parse(html))
    _eyebrow_class = len(re.findall(
        r'class="[^"]*(?:eyebrow|kicker|overline|label)[^"]*"', html, re.IGNORECASE))
    _eyebrow_caps = len(re.findall(r'>\s*[A-Z][A-Z\s·]{1,}[A-Z]\s*<', html))
    _eyebrow_count = _eyebrow_class + _eyebrow_caps
    if _section_count > 0:
        _eyebrow_limit = (_section_count + 2) // 3  # ceil(section_count / 3)
        if _eyebrow_count > _eyebrow_limit:
            findings.append({
                "rule": "eyebrow-density",
                "severity": "medium",
                "category": "layout",
                "source": "stdlib",
                "message": (
                    f"{_eyebrow_count} eyebrows for {_section_count} sections "
                    f"(max ceil({_section_count}/3)={_eyebrow_limit}). Eyebrow labels "
                    f"signal hierarchy — used on every section they become noise. "
                    f"Reserve them for 1 in 3 sections."
                ),
                "element": f"eyebrow_count={_eyebrow_count}, section_count={_section_count}",
            })

    # --- Rule 22: section-number-eyebrows (severity: medium) ------------------
    # Structural pattern, not a class-keyword dependency: a short element whose
    # ENTIRE text content is just "0N" (optionally with a trailing separator),
    # immediately followed by a heading -- regardless of what class name (if
    # any) that element carries. Catches the same decorative-numbering tell on
    # bespoke markup that doesn't use 'eyebrow'/'kicker'/'overline'/'label'.
    _secnum_re = re.compile(
        r'<(?:span|p|div)(?:\s[^>]*)?>\s*0[1-9]\s*[./·]?\s*</(?:span|p|div)>'
        r'\s*(?:<[^>]+>\s*){0,2}<h[1-6]\b',
        re.IGNORECASE | re.DOTALL,
    )
    if _secnum_re.search(html):
        findings.append({
            "rule": "section-number-eyebrows",
            "severity": "medium",
            "category": "layout",
            "source": "stdlib",
            "message": (
                "Section-number eyebrows (01 / 02 / Features) detected. Numbering "
                "implies a sequence or process — use only when the content is an actual "
                "ordered process. Decorative numbering is a template tell."
            ),
            "element": "0N eyebrow label",
        })

    # --- Rule 23: decorative-status-dots (severity: medium) -------------------
    _dot_glyphs = len(re.findall(r'●|•', html))
    _dot_css = 0
    for _mm in _CSS_BLOCK_RE.finditer(html):
        _sel = _mm.group(1).strip().lower()
        if any(x in _sel for x in
               ("nav", "avatar", "badge", "status", "toggle", "switch", "dot-live")):
            continue
        _body = _mm.group(2)
        if re.search(r'border-radius\s*:\s*50%', _body, re.IGNORECASE):
            _wm = re.search(r'width\s*:\s*([0-9.]+)px', _body, re.IGNORECASE)
            if _wm:
                try:
                    if 4 <= float(_wm.group(1)) <= 8:
                        _dot_css += 1
                except ValueError:
                    pass
    _dot_total = _dot_glyphs + _dot_css
    if _dot_total > 3:
        findings.append({
            "rule": "decorative-status-dots",
            "severity": "medium",
            "category": "visual-details",
            "source": "stdlib",
            "message": (
                "Decorative status dots with no state meaning. Small filled circles that "
                "indicate nothing are visual filler. Use a status dot only when it "
                "communicates a real state (online/offline, success/error)."
            ),
            "element": f"decorative dot count={_dot_total}",
        })

    # --- Rule 24: all-caps-body (severity: medium) ----------------------------
    _uppercase_rules = len(re.findall(r'text-transform\s*:\s*uppercase', html, re.IGNORECASE))
    _long_text_blocks = len([
        _t for _t in re.findall(r'<p[^>]*>(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
        if len(re.sub(r'<[^>]+>', '', _t).strip()) > 40
    ])
    if _uppercase_rules > 3 and _long_text_blocks > 0:
        findings.append({
            "rule": "all-caps-body",
            "severity": "medium",
            "category": "typography",
            "source": "stdlib",
            "message": (
                "All-caps text outside labels/badges. text-transform:uppercase on body "
                "copy degrades readability at scale. Reserve all-caps for labels, tabs, "
                "and eyebrows (≤4 words)."
            ),
            "element": f"uppercase rules={_uppercase_rules}, body blocks>40ch={_long_text_blocks}",
        })

    # --- Rule 25: marquee-overuse (severity: medium) --------------------------
    _marquee_count = len(re.findall(r'<marquee\b', html, re.IGNORECASE))
    _marquee_count += len(re.findall(
        r'animation\s*:[^;]*translate[^;]*infinite', html, re.IGNORECASE))
    if _marquee_count > 1:
        findings.append({
            "rule": "marquee-overuse",
            "severity": "medium",
            "category": "motion",
            "source": "stdlib",
            "message": (
                "More than one marquee/ticker element on a single surface. One scrolling "
                "element can create energy; two or more creates a carnival. Remove all but "
                "the most purposeful one."
            ),
            "element": f"ticker-like count={_marquee_count}",
        })

    # --- Rule 26: gpt-thin-border-wide-shadow (severity: high) ----------------
    # Hairline 1px border AND diffuse box-shadow (blur > 12px) on the same element.
    # This is the "AI UI signature": applying both on one element means no single
    # elevation strategy was chosen. Each theme picks ONE: border OR shadow.
    _r26_hits: list[str] = []
    # Check CSS blocks (selector + body pairs)
    for _r26m in _CSS_BLOCK_RE.finditer(html):
        _r26_sel = _r26m.group(1).strip()
        _r26_body = _r26m.group(2)
        if _THIN_BORDER_RE.search(_r26_body):
            _r26_bsm = _BOX_SHADOW_BLUR_RE.search(_r26_body)
            if _r26_bsm:
                try:
                    if float(_r26_bsm.group(1)) > 12:
                        _r26_hits.append(_r26_sel[:60])
                except ValueError:
                    pass
    # Check inline style attributes
    for _r26_inlm in re.finditer(r'style=["\']([^"\']+)["\']', html, re.IGNORECASE):
        _r26_inl = _r26_inlm.group(1)
        if _THIN_BORDER_RE.search(_r26_inl):
            _r26_bsm = _BOX_SHADOW_BLUR_RE.search(_r26_inl)
            if _r26_bsm:
                try:
                    if float(_r26_bsm.group(1)) > 12:
                        _r26_hits.append("inline style")
                except ValueError:
                    pass
    if _r26_hits:
        findings.append({
            "rule": "gpt-thin-border-wide-shadow",
            "severity": "high",
            "category": "visual-details",
            "source": "stdlib",
            "message": (
                "Hairline 1px border AND diffuse box-shadow (blur > 12px) on the same "
                "element. Each theme picks ONE elevation strategy: border OR shadow. "
                f"Found on: {', '.join(_r26_hits[:3])}."
            ),
            "element": _r26_hits[0][:80],
        })

    # --- Rule 27: undersized-ui-text (severity: medium) -----------------------
    # typography.scale.steps.xs.px < 12 fails WCAG SC 1.4.4 at common viewing distances.
    _theme_json_r27 = preview.parent / "theme.json"
    if _theme_json_r27.is_file():
        try:
            _r27_tj = json.loads(_theme_json_r27.read_text(encoding="utf-8"))
            _r27_xs = (
                (_r27_tj.get("typography") or {})
                .get("scale", {})
                .get("steps", {})
                .get("xs", {})
                .get("px")
            )
            if isinstance(_r27_xs, (int, float)) and _r27_xs < 12:
                findings.append({
                    "rule": "undersized-ui-text",
                    "severity": "medium",
                    "category": "typography",
                    "source": "stdlib",
                    "message": (
                        f"xs type step is {_r27_xs}px — below 12px minimum. UI text under "
                        "12px fails WCAG SC 1.4.4 at common viewing distances. "
                        "Raise typography.scale.steps.xs.px to at least 12."
                    ),
                    "element": f"typography.scale.steps.xs.px = {_r27_xs}",
                })
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    # ══════════════════════════════════════════════════════════════════════════
    # Motion rules 28–31 (Emil Kowalski animation standards)
    # ══════════════════════════════════════════════════════════════════════════

    # --- Rule 28: transition-all outside prefers-reduced-motion (severity: high) ---
    # transition: all watches every animatable property, causes unnecessary style
    # recalculations, makes reasoning about what transitions impossible, and is a
    # GPU thrash risk. Strip @media (prefers-reduced-motion) blocks first so that
    # intentional no-animation fallbacks are not penalised.
    _r28_html_stripped = re.sub(
        r'@media\s*\([^)]*prefers-reduced-motion[^)]*\)\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        '', html, flags=re.DOTALL | re.IGNORECASE,
    )
    if _TRANSITION_ALL_RE.search(_r28_html_stripped):
        findings.append({
            "rule": "transition-all",
            "severity": "high",
            "category": "motion",
            "source": "stdlib",
            "message": (
                "transition: all found outside @media (prefers-reduced-motion) — "
                "watches every animatable CSS property, causes unnecessary style "
                "recalculations, and is a GPU thrash risk. "
                "Name the property explicitly: transition: transform, opacity, clip-path."
            ),
            "element": "transition: all",
        })

    # --- Rule 29: keyframe-enters-exits (severity: medium) --------------------
    # @keyframes applied to toggled elements (modal, drawer, dropdown …) cannot be
    # interrupted mid-flight — rapid toggling causes them to restart from zero instead
    # of retargeting. CSS transitions are interruptible and should be used instead.
    _r29_toggle_re = re.compile(
        r'\.(?:modal|drawer|dropdown|toast|collapse|slide|overlay|popover|tooltip|menu|panel)\b',
        re.IGNORECASE,
    )
    _r29_data_re = re.compile(
        r'\[data-(?:open|expanded)\]|\[aria-expanded',
        re.IGNORECASE,
    )
    _r29_kf_names = set(re.findall(r'@keyframes\s+(\S+)', html, re.IGNORECASE))
    _r29_violations = 0
    if _r29_kf_names:
        for _r29m in _CSS_BLOCK_RE.finditer(html):
            _r29_sel = _r29m.group(1).strip()
            _r29_body = _r29m.group(2)
            if not re.search(r'animation\s*:', _r29_body, re.IGNORECASE):
                continue
            if _r29_toggle_re.search(_r29_sel) or _r29_data_re.search(_r29_sel):
                _r29_violations += 1
    if _r29_violations > 0:
        findings.append({
            "rule": "keyframe-enters-exits",
            "severity": "medium",
            "category": "motion",
            "source": "stdlib",
            "message": (
                f"{_r29_violations} @keyframes animation(s) applied to toggled elements "
                "(modal, drawer, dropdown, toast, collapse, overlay, popover, tooltip, "
                "menu, panel). Keyframe animations cannot be interrupted mid-flight — "
                "rapid toggling makes them restart from zero instead of retargeting. "
                "Use CSS transitions instead, which are interruptible."
            ),
            "element": f"keyframe-on-toggle count={_r29_violations}",
        })

    # --- Rule 30: asymmetric-timing-absent (severity: medium) -----------------
    # Hold-to-confirm and press-release interactions should slow the deliberate phase
    # and snap the response. :active blocks that exist but do not override the
    # transition with a longer duration miss this physicality cue. Only fire on clear
    # cases; note in the message that a human should confirm.
    _r30_has_active = bool(re.search(r':active\s*\{', html, re.IGNORECASE))
    _r30_violations = 0
    if _r30_has_active:
        _r30_active_blocks = re.findall(r':active\s*\{([^}]*)\}', html, re.IGNORECASE)
        _r30_with_duration = sum(
            1 for _b in _r30_active_blocks
            if re.search(r'(?:transition|animation)[^;]*\d+m?s', _b, re.IGNORECASE)
        )
        if _r30_with_duration == 0:
            _r30_violations += 1
    _r30_has_hold = bool(re.search(
        r'class="[^"]*\bhold\b[^"]*"|\.hold\b|\.hold-confirm\b|\[data-hold\]',
        html, re.IGNORECASE,
    ))
    if _r30_has_hold:
        _r30_hold_blocks = re.findall(
            r'(?:\.hold(?:-confirm)?|\[data-hold\])\s*\{([^}]*)\}',
            html, re.IGNORECASE,
        )
        _r30_hold_timed = sum(
            1 for _b in _r30_hold_blocks
            if re.search(r'transition[^;]*\d+m?s', _b, re.IGNORECASE)
        )
        if not _r30_hold_timed:
            _r30_violations += 1
    if _r30_violations > 0:
        findings.append({
            "rule": "asymmetric-timing-absent",
            "severity": "medium",
            "category": "motion",
            "source": "stdlib",
            "message": (
                ":active or hold-confirm elements found without asymmetric transition timing. "
                "The deliberate press phase should use a longer duration and the release "
                "should snap back quickly (≥ 5× ratio). "
                "Note: static analysis may be a false positive — confirm that no "
                "transition-duration override is set on :active."
            ),
            "element": ":active without duration override",
        })

    # --- Rule 31: blur-crossfade-missing (severity: low) ----------------------
    # When two states overlap during a crossfade (opacity 0→1 while another goes 1→0),
    # a subtle filter: blur(2px) during the transition blends them into one perceived
    # transformation. Without it, the double-image flicker is distracting.
    # Only fire when there is a clear crossfade setup (both opacity:0 and opacity:1
    # transitions present) with no blur.
    _r31_has_opacity_transition = bool(re.search(
        r'transition\s*:[^;]*\bopacity\b', html, re.IGNORECASE,
    ))
    _r31_has_dual_state = bool(
        # (?![.\d]) not \b: \b sits between "0"/"1" and "." too, so a bare \b
        # boundary let "opacity: 0.3" or "opacity: 1.5" miscount as the exact
        # 0/1 endpoints this rule is actually looking for.
        re.search(r'\bopacity\s*:\s*0(?![.\d])', html, re.IGNORECASE)
        and re.search(r'\bopacity\s*:\s*1(?![.\d])', html, re.IGNORECASE)
    )
    _r31_has_blur = bool(re.search(
        r'transition\s*:[^;]*\bfilter\b|filter\s*:\s*blur\s*\(', html, re.IGNORECASE,
    ))
    if _r31_has_opacity_transition and _r31_has_dual_state and not _r31_has_blur:
        findings.append({
            "rule": "blur-crossfade-missing",
            "severity": "low",
            "category": "motion",
            "source": "stdlib",
            "message": (
                "Opacity crossfade detected (opacity:0 and opacity:1 with transition) "
                "without filter: blur transition. A subtle blur(2px) during the crossfade "
                "blends both states into one perceived transformation — without it, "
                "the double-image flicker during overlap is distracting."
            ),
            "element": "opacity crossfade without blur",
        })

    # --- Rule 32: button-state-missing (severity: medium) ----------------------
    # Buttons and inputs must visually distinguish their disabled and loading
    # states. The webapp microstate strip (Part C) adds the HTML elements, but
    # the CSS must actually style them. Fires when <button> is present but no
    # :disabled selector appears in the stylesheet.
    _r32_has_buttons = bool(re.search(r'<button\b', html, re.IGNORECASE))
    _r32_has_disabled_style = bool(re.search(r':disabled\b', html, re.IGNORECASE))
    _r32_has_loading_style = bool(re.search(
        r'\.(?:tf-loading-demo|loading|btn-loading|is-loading)\b|aria-busy',
        html, re.IGNORECASE,
    ))
    if _r32_has_buttons and not _r32_has_disabled_style:
        findings.append({
            "rule": "button-state-missing",
            "severity": "medium",
            "category": "interactive",
            "source": "stdlib",
            "message": (
                "Preview contains <button> elements but no :disabled CSS selector. "
                "Disabled state must be visually distinct (opacity, cursor, color). "
                "Also check that a loading state is styled"
                + (" — no loading class/aria-busy found either." if not _r32_has_loading_style else ".")
            ),
            "element": "<button> without :disabled style",
        })

    # ══════════════════════════════════════════════════════════════════════════
    # Rules 33–34 (Taste Skill, github.com/Leonxlnx/taste-skill, MIT) —
    # refreshed 2026-09-03 against the current skills/taste-skill/SKILL.md.
    # ══════════════════════════════════════════════════════════════════════════

    # --- Rule 33: duplicate-cta-intent (severity: medium) ---------------------
    # Two CTAs with the same underlying intent (contact / signup / portfolio) read
    # as if no single decision was made about what the page wants the user to do.
    # Matches the data-tf-role="*-cta" semantic hook (see
    # skills/generate-themes/references/semantic-hooks.md) rather than a
    # 'btn'/'cta' class-name substring -- bespoke themes are not required to use
    # either literal word in their class names, but the hook is required.
    _cta_text_re = re.compile(
        r'<(?:button|a)[^>]*data-tf-role="[^"]*cta"[^>]*>\s*([^<]{1,60})\s*<',
        re.IGNORECASE,
    )
    _cta_intents: dict[str, set[str]] = {
        "contact": {
            "contact us", "get in touch", "let's talk", "lets talk",
            "start a project", "reach out", "start something", "talk to us",
            "book a call", "schedule a call", "contact",
        },
        "signup": {
            "sign up", "get started", "start free trial", "join now",
            "create account", "start now", "try it free", "start your trial",
        },
        "portfolio": {
            "view our work", "see our work", "view work", "view projects",
            "see projects", "our portfolio", "view portfolio",
        },
    }
    _cta_hits_by_intent: dict[str, list[str]] = {k: [] for k in _cta_intents}
    for _ctam in _cta_text_re.finditer(html):
        _cta_norm = re.sub(r'\s+', ' ', _ctam.group(1)).strip().lower()
        for _intent, _phrases in _cta_intents.items():
            if _cta_norm in _phrases:
                _cta_hits_by_intent[_intent].append(_ctam.group(1).strip())
                break
    for _intent, _hits in _cta_hits_by_intent.items():
        if len(_hits) > 1:
            findings.append({
                "rule": "duplicate-cta-intent",
                "severity": "medium",
                "category": "copy",
                "source": "stdlib",
                "message": (
                    f"{len(_hits)} CTAs share the same \"{_intent}\" intent "
                    f"({', '.join(repr(h) for h in _hits[:4])}). Pick one label for "
                    f"one intent; a page with several differently-worded buttons that "
                    f"all mean the same thing reads as unplanned."
                ),
                "element": f"{_intent} intent count={len(_hits)}",
            })

    # --- Rule 34: dark-mode-pure-black-white (severity: medium) ---------------
    # Pure #000000 / #ffffff as a surface color kills depth — use off-black/off-white.
    if _theme_json.is_file():
        try:
            _r34_tj = json.loads(_theme_json.read_text(encoding="utf-8"))
            _r34_pure_hits: list[str] = []
            for _mode in ("light", "dark"):
                _r34_role = (_r34_tj.get("color") or {}).get(_mode) or {}
                for _role_name in ("background", "bg", "surface"):
                    _r34_hex = (_r34_role.get(_role_name) or {}).get("hex") or ""
                    if _r34_hex.lower() in ("#000000", "#ffffff", "#000", "#fff"):
                        _r34_pure_hits.append(f"color.{_mode}.{_role_name}={_r34_hex}")
            if _r34_pure_hits:
                findings.append({
                    "rule": "dark-mode-pure-black-white",
                    "severity": "medium",
                    "category": "color",
                    "source": "stdlib",
                    "message": (
                        "Pure #000000 or #ffffff used as a surface color: "
                        f"{', '.join(_r34_pure_hits)}. Pure values kill depth — use "
                        "an off-black (e.g. zinc-950 / near-black warm gray) or "
                        "off-white instead."
                    ),
                    "element": ", ".join(_r34_pure_hits),
                })
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    # --- Rule 35: orphan-css-class (severity: medium) --------------------------
    # A class used in markup with zero matching CSS selector anywhere in the
    # embedded stylesheet renders unstyled — this is exactly how the warm-bistro
    # hero-card / webapp skeleton-state / button-spinner bugs shipped:
    # theme-designer invented markup class names that the shared gallery.css
    # composition rules never defined, so the element collapsed to an unstyled
    # block with no layout, sizing, or visual treatment. preview.html embeds its
    # full stylesheet (gallery.css + theme CSS + motion.css) in one <style>
    # block, so both sides of this check are in the same file being scanned here.
    #
    # Per-element grouping avoids flagging semantic/hook-only co-classes: a class
    # is only reported if EVERY element it appears on has no other class with a
    # CSS match AND no inline style with a real (non-custom-property) declaration
    # either — i.e. the element has no visual styling from any source. A class
    # like "app-empty-state" that always co-occurs with a styled "tf-card" is not
    # an orphan even though it has no rule of its own; an element styled entirely
    # via style="font-weight:700;..." is not an orphan either. style="--i:1"
    # (a stagger-delay custom-property hook, not a visual declaration) does NOT
    # count as real inline styling. A class like "hero-body" or "btn-spinner"
    # that is the only class on its element, has no CSS match, and no real
    # inline style anywhere is a genuine orphan.
    _style_block_m = re.search(r'<style[^>]*>(.*?)</style>', html, re.DOTALL | re.IGNORECASE)
    _css_text = _style_block_m.group(1) if _style_block_m else ""
    _css_classes: set[str] = set(re.findall(r'\.([a-zA-Z_][\w-]*)', _css_text))

    def _has_real_inline_style(attrs: str) -> bool:
        _sm = re.search(r'style=["\']([^"\']*)["\']', attrs)
        if not _sm:
            return False
        for _decl in _sm.group(1).split(";"):
            _prop = _decl.split(":", 1)[0].strip()
            if _prop and not _prop.startswith("--"):
                return True
        return False

    _unstyled_group_classes: set[str] = set()
    _styled_anywhere: set[str] = set()
    for _tag_m in re.finditer(r'<[a-zA-Z][\w-]*\s+([^>]*?)/?>', html):
        _attrs = _tag_m.group(1)
        _cls_m = re.search(r'class=["\']([^"\']+)["\']', _attrs)
        if not _cls_m:
            continue
        _group = _cls_m.group(1).split()
        if any(c in _css_classes for c in _group) or _has_real_inline_style(_attrs):
            _styled_anywhere.update(_group)
        else:
            _unstyled_group_classes.update(_group)
    # Verified-harmless: pure grouping wrappers from the shared gallery template
    # whose children carry all real styling (checked manually 2026-09-03).
    _ORPHAN_EXEMPT = {"app-empty-desc", "app-nonideal"}
    _orphans = sorted(
        c for c in _unstyled_group_classes
        if c not in _css_classes and c not in _styled_anywhere and c not in _ORPHAN_EXEMPT
    )
    if _orphans:
        findings.append({
            "rule": "orphan-css-class",
            "severity": "medium",
            "category": "design-system",
            "source": "stdlib",
            "message": (
                f"{len(_orphans)} class name(s) are never styled and never co-occur "
                f"with a styled class — these elements render unstyled (no layout, "
                f"sizing, or visual treatment) on every occurrence: "
                f"{', '.join(_orphans[:10])}"
                + (f" (+{len(_orphans) - 10} more)" if len(_orphans) > 10 else "") + ". "
                "Either add the missing CSS rule to the relevant stylesheet, or use an "
                "existing styled class instead of inventing a new one. Verify each "
                "manually — this is a strong signal, not a guaranteed bug."
            ),
            "element": ", ".join(_orphans[:10]),
        })

    return findings


def run_theme(theme_dir: Path, available: bool) -> dict:
    """Run impeccable on one theme and write slop.json.  Returns a summary."""
    preview = theme_dir / "preview.html"
    if not preview.is_file():
        _eprint(f"  ⚠  no preview.html in {theme_dir.name} — skipped")
        return {"theme": theme_dir.name, "skipped": True, "reason": "no preview.html"}

    result: dict = {
        "theme": theme_dir.name,
        "available": available,
        "preview": str(preview),
    }

    if not available:
        stdlib_findings = _stdlib_check(preview)
        _print_categorical_gate_table(theme_dir.name, stdlib_findings)
        _print_motion_gate_table(
            theme_dir.name, stdlib_findings,
            preview.read_text(encoding="utf-8", errors="replace"))
        hard_stop, advisory = _split_tiers(stdlib_findings)
        advisory = sorted(advisory, key=_motion_sort_key)
        result.update({
            "findings": stdlib_findings,
            "hard_stop": hard_stop,
            "advisory": advisory,
            "hard_stop_count": len(hard_stop),
            "advisory_count": len(advisory),
            "finding_count": len(stdlib_findings),
            "ok": len(hard_stop) == 0,
            "source": "stdlib",
            "rules_checked": _STDLIB_RULE_COUNT,
            "rules_total": _IMPECCABLE_TOTAL_RULES,
            "note": (
                f"impeccable CLI unavailable — stdlib fallback ran "
                f"{_STDLIB_RULE_COUNT} of {_IMPECCABLE_TOTAL_RULES} rules. "
                f"Install impeccable for full coverage: npm i -g impeccable"
            ),
        })
        (theme_dir / "slop.json").write_text(json.dumps(result, indent=2))
        return result

    _eprint(f"  ↪  running impeccable on {theme_dir.name}/preview.html …")
    raw = _run_impeccable(preview)

    if "error" in raw and "findings" not in raw:
        _eprint(f"  ✗  impeccable error for {theme_dir.name}: {raw['error']}")
        result.update({"error": raw["error"], "findings": [],
                        "hard_stop": [], "advisory": [],
                        "hard_stop_count": 0, "advisory_count": 0,
                        "finding_count": 0, "ok": True})
    else:
        findings = _ai_slop_findings(raw)
        # Run the FULL stdlib set (rules 1-35), not categorical_only.
        #
        # This used to pass categorical_only=True, which skipped
        # _stdlib_rules_1_13 whenever impeccable was available -- i.e. on every
        # normal run. The assumption was that impeccable covers the motion
        # rules. It does not: scale(0) entrances climbed 0 -> 2 -> 4 across
        # three consecutive runs while the header read "59 of 59 rules
        # (impeccable)", and transform-origin fell 12 -> 4, both undetected,
        # because Rule 6 (HIGH) and Rule 11 (MEDIUM) only ever ran in the
        # no-impeccable fallback. Rule 6 is HIGH, so it lands in hard_stop and
        # blocks assembly -- but only if it runs. Overlap with an impeccable
        # finding is cheap; a missed HIGH is not.
        _cat = _stdlib_check(preview)
        _print_categorical_gate_table(theme_dir.name, _cat)
        _print_motion_gate_table(
            theme_dir.name, _cat,
            preview.read_text(encoding="utf-8", errors="replace"))
        findings = findings + _cat
        hard_stop, advisory = _split_tiers(findings)
        advisory = sorted(advisory, key=_motion_sort_key)
        slop_count = len(findings)
        tier_label = (f"{len(hard_stop)} hard-stop, {len(advisory)} advisory"
                      if slop_count else "clean")
        _eprint(f"  {'✓' if not hard_stop else '✗'}  {theme_dir.name}: "
                f"{slop_count} slop finding(s) — {tier_label}")
        result.update({
            "findings": findings,           # combined, kept for backward compat
            "hard_stop": hard_stop,         # blocks assembly → constrained regen
            "advisory": advisory,           # shown in gallery drawer, does not block
            "hard_stop_count": len(hard_stop),
            "advisory_count": len(advisory),
            "finding_count": slop_count,
            "raw_count": len(raw.get("findings") or raw.get("results") or []),
            "ok": len(hard_stop) == 0,      # ok = no hard-stop findings
            "source": "impeccable",
            "rules_checked": _IMPECCABLE_TOTAL_RULES,
            "rules_total": _IMPECCABLE_TOTAL_RULES,
        })

    (theme_dir / "slop.json").write_text(json.dumps(result, indent=2))
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]

    # --selftest
    if "--selftest" in args:
        test = {"ok": True, "theme": "selftest", "findings": [], "finding_count": 0}
        assert json.loads(json.dumps(test)) == test
        _eprint("selftest OK")
        _ok({"selftest": True})
        return

    json_mode = "--json" in args
    if not json_mode:
        _fail("pass --json to get structured output", 1)

    # Resolve theme dirs
    theme_dirs: list[Path] = []
    if "--theme" in args:
        idx = args.index("--theme")
        if idx + 1 >= len(args):
            _fail("--theme requires a directory argument")
        theme_dirs = [Path(args[idx + 1])]
    else:
        paths = tf_paths.resolve(create=False)
        themes_root = Path(paths.current_themes)
        if not themes_root.is_dir():
            _fail(f"themes directory not found: {themes_root}")
        theme_dirs = sorted(d for d in themes_root.iterdir() if d.is_dir())

    if not theme_dirs:
        _fail("no theme directories found")

    # Check tool availability once
    _eprint("tf_slop: checking impeccable availability …")
    available = _check_npx() and _check_impeccable()
    if not available:
        _eprint("  impeccable not available — results will be empty (not an error)")

    results: list[dict] = []
    for td in theme_dirs:
        r = run_theme(td, available)
        results.append(r)
        _eprint("")

    total_findings = sum(r.get("finding_count", 0) for r in results)
    themes_clean = sum(1 for r in results if r.get("finding_count", 0) == 0 and not r.get("skipped"))

    # Hard-stops are surfaced at the TOP level and in the exit code.
    #
    # Both were previously absent: the summary reported only `total_findings`
    # (which mixes 600 advisories with 1 blocker) and `_ok()` exited 0 no matter
    # what, so a HIGH severity finding was discoverable only by opening each
    # theme's own slop.json. A blocker nobody is shown is a blocker nobody
    # fixes -- which is how the same HIGH finding survives run after run.
    total_hard_stops = sum(r.get("hard_stop_count", 0) for r in results)
    hard_stop_rules = sorted({
        f.get("rule") or f.get("antipattern") or "?"
        for r in results for f in (r.get("hard_stop") or [])
    })
    themes_with_hard_stops = sorted(
        r.get("theme", "?") for r in results if r.get("hard_stop_count", 0)
    )

    source = "impeccable" if available else "stdlib"
    rules_checked = _IMPECCABLE_TOTAL_RULES if available else _STDLIB_RULE_COUNT
    payload = {
        "available": available,
        "source": source,
        "rules_checked": rules_checked,
        "rules_total": _IMPECCABLE_TOTAL_RULES,
        "themes_checked": len(results),
        "themes_clean": themes_clean,
        "total_findings": total_findings,
        "total_hard_stops": total_hard_stops,
        "hard_stop_rules": hard_stop_rules,
        "themes_with_hard_stops": themes_with_hard_stops,
        "results": results,
    }

    if total_hard_stops and "--no-fail" not in sys.argv:
        _eprint("")
        _eprint("tf_slop: %d HIGH-severity hard-stop finding(s) across %d theme(s): %s"
                % (total_hard_stops, len(themes_with_hard_stops), ", ".join(hard_stop_rules)))
        _eprint("  themes: %s" % ", ".join(themes_with_hard_stops))
        _eprint("  These block gallery assembly (tf_gallery.py refuses to build over a current")
        _eprint("  hard-stop). Fix them, then re-run this script to clear the finding.")
        _eprint("  Pass --no-fail only to inspect without failing the exit code.")
        print(json.dumps(dict(payload, ok=False,
                              error="%d hard-stop finding(s)" % total_hard_stops)))
        sys.exit(1)

    _ok(payload)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"unhandled: {exc}"}))
        sys.exit(2)
