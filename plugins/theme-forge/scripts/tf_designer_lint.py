#!/usr/bin/env python3
"""tf_designer_lint.py -- mechanical token-level lint for one theme.json.

Checks a handful of rules that agents/theme-designer.md previously stated as
prose for the agent to self-apply by eye, with nothing downstream verifying
compliance before the theme is handed off. All four checks below operate on
theme.json alone -- no rendered surface HTML/CSS is required, so this can run
inside theme-designer's own self-validate step, alongside tf_contrast.py and
tf_native.py, before brand-asset-designer or surface-composer ever run.

Rules:
    banned-font              display/body family matches the demoted list
                              (Inter, Roboto, Arial, Space Grotesk, Geist,
                              Fraunces, Instrument Serif) or is literally
                              "system-ui" as the chosen face (not the
                              fallback-stack tail, which must keep it).
    dark-mode-pure-black-white  color.<mode>.<background|bg|surface>.hex is
                              exactly #000000 or #ffffff. Duplicates
                              tf_slop.py's Rule 34, which fires later in the
                              pipeline (Step 5a) -- running it here catches
                              the same defect a full pipeline stage earlier.
    elevation-strategy-both   elevation.strategy literal string is "both".
                              theme.schema.json's enum already excludes this
                              value, but nothing validates the schema anywhere
                              in the pipeline, so a free-text "both" would
                              otherwise ship unnoticed.
    oklch-percentage-form     an oklch() value in any color.*.*.css field uses
                              percentage lightness (oklch(8% ...)) instead of
                              decimal (oklch(0.08 ...)) -- theme-designer.md's
                              own prose names this as breaking tf_distinct.py's
                              regex parser; nothing previously checked it.

Usage:
    python3 tf_designer_lint.py --theme <dir> --json

Exit 0 always (advisory-only, mirrors tf_contrast.py's fix-and-rerun loop
rather than a hard gate) unless the theme directory or theme.json is missing,
in which case exit 1. Exit 2 on unexpected error.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Rule 1: banned-font
# ---------------------------------------------------------------------------

_BANNED_FONTS = frozenset({
    "inter", "roboto", "arial", "space grotesk",
    "geist", "geist sans",
    "fraunces", "instrument serif",
})


def _check_banned_font(theme: dict) -> list[dict]:
    findings: list[dict] = []
    typo = theme.get("typography") or {}
    for role in ("display", "body"):
        family = ((typo.get(role) or {}).get("family") or "").strip()
        if not family:
            continue
        norm = family.lower()
        if norm == "system-ui":
            findings.append({
                "rule": "banned-font",
                "field": f"typography.{role}.family",
                "message": (
                    f'typography.{role}.family = "system-ui" -- never choose '
                    f"system-ui as the typeface itself; it belongs only at the "
                    f"end of the fallback stack."
                ),
            })
            continue
        if norm in _BANNED_FONTS:
            findings.append({
                "rule": "banned-font",
                "field": f"typography.{role}.family",
                "message": (
                    f'typography.{role}.family = "{family}" is on the demoted '
                    f"list (Inter, Roboto, Arial, Space Grotesk, Geist / Geist "
                    f"Sans, Fraunces, Instrument Serif) -- choose a distinct "
                    f"typeface per knowledge/03-typography.md."
                ),
            })
    return findings


# ---------------------------------------------------------------------------
# Rule 2: dark-mode-pure-black-white (duplicates tf_slop.py Rule 34)
# ---------------------------------------------------------------------------

_PURE_HEXES = frozenset({"#000000", "#ffffff", "#000", "#fff"})


def _check_pure_black_white(theme: dict) -> list[dict]:
    findings: list[dict] = []
    color = theme.get("color") or {}
    for mode in ("light", "dark"):
        role_map = color.get(mode) or {}
        for role_name in ("background", "bg", "surface"):
            hexv = ((role_map.get(role_name) or {}).get("hex") or "").strip()
            if hexv.lower() in _PURE_HEXES:
                findings.append({
                    "rule": "dark-mode-pure-black-white",
                    "field": f"color.{mode}.{role_name}.hex",
                    "message": (
                        f"color.{mode}.{role_name}.hex = {hexv} -- pure black/white "
                        f"kills depth. Use an off-black or off-white instead. "
                        f"(tf_slop.py Rule 34 checks this again after gallery "
                        f"assembly; fixing it now avoids a regeneration cycle.)"
                    ),
                })
    return findings


# ---------------------------------------------------------------------------
# Rule 3: elevation-strategy-both
# ---------------------------------------------------------------------------

def _check_elevation_strategy(theme: dict) -> list[dict]:
    strategy = ((theme.get("elevation") or {}).get("strategy") or "").strip().lower()
    if strategy == "both":
        return [{
            "rule": "elevation-strategy-both",
            "field": "elevation.strategy",
            "message": (
                'elevation.strategy = "both" -- a hairline border AND a wide '
                "diffuse shadow on the same card is the single most recognisable "
                'AI-generated card pattern. Pick one: "shadow", "border", or "glass".'
            ),
        }]
    return []


# ---------------------------------------------------------------------------
# Rule 4: oklch-percentage-form
# ---------------------------------------------------------------------------

_OKLCH_PCT_RE = re.compile(r'oklch\(\s*\d+(?:\.\d+)?%', re.IGNORECASE)


def _check_oklch_percentage_form(theme: dict) -> list[dict]:
    findings: list[dict] = []
    color = theme.get("color") or {}
    for mode in ("light", "dark"):
        role_map = color.get(mode) or {}
        if not isinstance(role_map, dict):
            continue
        for role_name, role_val in role_map.items():
            css = (role_val or {}).get("css") if isinstance(role_val, dict) else None
            if isinstance(css, str) and _OKLCH_PCT_RE.search(css):
                findings.append({
                    "rule": "oklch-percentage-form",
                    "field": f"color.{mode}.{role_name}.css",
                    "message": (
                        f"color.{mode}.{role_name}.css = \"{css}\" uses percentage "
                        f"lightness -- write decimal L (oklch(0.08 0.15 264), not "
                        f"oklch(8% 0.15 264)). The percentage form breaks "
                        f"tf_distinct.py's regex parser and the hue silently "
                        f"registers as unknown."
                    ),
                })
    return findings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_CHECKS = (
    _check_banned_font,
    _check_pure_black_white,
    _check_elevation_strategy,
    _check_oklch_percentage_form,
)


def lint_theme(theme: dict) -> list[dict]:
    findings: list[dict] = []
    for check in _CHECKS:
        findings.extend(check(theme))
    return findings


def main(argv: list[str]) -> int:
    theme_dir: Path | None = None
    i = 0
    while i < len(argv):
        if argv[i] == "--theme" and i + 1 < len(argv):
            theme_dir = Path(argv[i + 1])
            i += 2
        else:
            i += 1

    if theme_dir is None:
        msg = "--theme <dir> required"
        sys.stderr.write(f"tf_designer_lint: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    theme_json = theme_dir / "theme.json"
    if not theme_json.is_file():
        msg = f"theme.json not found: {theme_json}"
        sys.stderr.write(f"tf_designer_lint: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    try:
        theme = json.loads(theme_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        msg = f"cannot read {theme_json}: {exc}"
        sys.stderr.write(f"tf_designer_lint: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    findings = lint_theme(theme)

    sys.stderr.write(f"\nDESIGNER LINT — {theme.get('slug', theme_dir.name)}\n")
    sys.stderr.write("─" * 70 + "\n")
    if findings:
        for f in findings:
            sys.stderr.write(f"  ✗ [{f['rule']}] {f['message']}\n")
    else:
        sys.stderr.write("  ✓ no findings\n")
    sys.stderr.write("─" * 70 + "\n")

    print(json.dumps({
        "ok": True,
        "slug": theme.get("slug", theme_dir.name),
        "clean": len(findings) == 0,
        "findings": findings,
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover - unexpected
        sys.stderr.write(f"tf_designer_lint: unexpected error: {exc}\n")
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
