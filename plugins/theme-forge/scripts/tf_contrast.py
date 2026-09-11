#!/usr/bin/env python3
"""tf_contrast.py -- validate a theme against WCAG 2.2 AA, write a11y.json.

Checks every semantic pair in both light and dark. For each failure it computes
a suggested fix: the nearest OKLCH lightness (hue and chroma preserved) that
actually passes, verified before it is emitted, so the designer agent can
self-correct.

Exit 1 on any failure, 0 if the theme passes.

    python3 tf_contrast.py --theme <theme-dir> --json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin dir
import tf_color

# (foreground key, background key, required ratio)
TEXT_PAIRS = [
    ("text", "background", 4.5),
    ("text-muted", "background", 4.5),
    ("text", "surface", 4.5),
    ("on-primary", "primary", 4.5),
    ("on-accent", "accent", 4.5),
    ("border", "background", 3.0),
    ("focus-ring", "background", 3.0),
]
SEMANTIC_KEYS = ["success", "warning", "danger", "info"]  # each on background, >= 3:1


def get_hex(val):
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("hex")
    return None


def suggest_fix(fg_hex, bg_hex, required):
    """Nearest OKLCH lightness (C, H preserved) that reaches `required`.

    Returns {"hex", "L", "ratio"} or None if nothing in [0,1] passes (it always
    should, since pure black or white bracket the range).
    """
    L0, C, H = tf_color.hex_to_oklch(fg_hex)
    best = None
    # Sample lightness finely; pick the passing candidate closest to the original.
    for i in range(0, 1001):
        L = i / 1000.0
        cand = tf_color.oklch_to_hex((L, C, H))  # chroma clamped into gamut
        ratio = tf_color.wcag_contrast(cand, bg_hex)
        if ratio >= required:
            dist = abs(L - L0)
            if best is None or dist < best[0]:
                best = (dist, cand, L, ratio)
    if best is None:
        return None
    return {"hex": best[1], "L": round(best[2], 4), "ratio": round(best[3], 2)}


def check_mode(colors, semantic, mode):
    passes, failures, skipped = [], [], []

    def evaluate(fg_key, bg_key, fg_hex, bg_hex, required):
        if fg_hex is None or bg_hex is None:
            skipped.append({"mode": mode, "pair": "%s on %s" % (fg_key, bg_key),
                            "reason": "missing color"})
            return
        ratio = tf_color.wcag_contrast(fg_hex, bg_hex)
        lc = tf_color.apca_lc(fg_hex, bg_hex)
        entry = {
            "mode": mode, "pair": "%s on %s" % (fg_key, bg_key),
            "fg": fg_hex, "bg": bg_hex,
            "ratio": round(ratio, 2), "required": required,
            "apca_lc": round(lc, 1),
        }
        if ratio >= required:
            passes.append(entry)
        else:
            entry["suggestion"] = suggest_fix(fg_hex, bg_hex, required)
            failures.append(entry)

    for fg_key, bg_key, required in TEXT_PAIRS:
        evaluate(fg_key, bg_key, get_hex(colors.get(fg_key)), get_hex(colors.get(bg_key)), required)

    bg_hex = get_hex(colors.get("background"))
    for name in SEMANTIC_KEYS:
        evaluate(name, "background", get_hex(semantic.get(name)), bg_hex, 3.0)

    return passes, failures, skipped


def validate(theme_dir: Path):
    theme_json = theme_dir / "theme.json"
    if not theme_json.is_file():
        return {"ok": False, "error": "no theme.json in %s" % theme_dir}
    theme = json.loads(theme_json.read_text(encoding="utf-8"))
    color = theme.get("color", {})
    semantic = color.get("semantic", {})

    all_passes, all_failures, all_skipped = [], [], []
    for mode in ("light", "dark"):
        colors = color.get(mode, {})
        if not colors:
            all_skipped.append({"mode": mode, "reason": "no %s colors" % mode})
            continue
        p, f, s = check_mode(colors, semantic, mode)
        all_passes += p
        all_failures += f
        all_skipped += s

    report = {
        "ok": len(all_failures) == 0,
        "standard": "WCAG 2.2 AA",
        "checked": len(all_passes) + len(all_failures),
        "passed": len(all_passes),
        "failed": len(all_failures),
        "failures": all_failures,
        "passes": all_passes,
        "skipped": all_skipped,
    }
    (theme_dir / "a11y.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv):
    want_json = "--json" in argv
    if "--theme" not in argv:
        sys.stderr.write("usage: tf_contrast.py --theme <dir> --json\n")
        print(json.dumps({"ok": False, "error": "missing --theme"}))
        return 1
    i = argv.index("--theme")
    theme_dir = Path(argv[i + 1])
    report = validate(theme_dir)
    if "error" in report:
        sys.stderr.write("tf_contrast: %s\n" % report["error"])
        if want_json:
            print(json.dumps(report))
        return 1

    sys.stderr.write(
        "tf_contrast: %d checked, %d passed, %d failed\n"
        % (report["checked"], report["passed"], report["failed"])
    )
    for f in report["failures"]:
        sug = f.get("suggestion")
        sug_s = ("-> try %s (%.2f:1)" % (sug["hex"], sug["ratio"])) if sug else "(no fix found)"
        sys.stderr.write(
            "  FAIL [%s] %s: %.2f:1 < %.1f  %s\n"
            % (f["mode"], f["pair"], f["ratio"], f["required"], sug_s)
        )
    if want_json:
        print(json.dumps(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        sys.stderr.write("tf_contrast: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
