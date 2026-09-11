#!/usr/bin/env python3
"""tf_motion_audit.py -- survey an existing project's own animation/motion
code (not a Theme Forge-generated preview) and report findings with file +
line location, so a plan can point at exact spots rather than "somewhere in
this file".

This is the deterministic "recon" half of Theme Forge's post-apply motion
audit (see agents/motion-auditor.md and skills/audit-motion/SKILL.md for the
judgment half: prioritizing findings and writing a self-contained fix plan).
Splitting it this way mirrors how tf_slop.py already works in this codebase:
a script does the free, exact, regex-level detection; an agent does the part
that needs taste (which finding is actually worth fixing, in what order).

Every regex below is IMPORTED from tf_slop.py, not re-written here -- these
are the same compiled patterns tf_slop.py already uses to gate a Theme
Forge-generated preview.html, reused as-is against arbitrary project files
picked up by --root. tf_slop.py's own findings carry no line number (a single
preview.html gate doesn't need one); this script adds that, since a fix plan
pointing at "styles.css" with no line is not actionable.

Scope, stated plainly rather than overclaimed: this scans .css/.scss files
and .js/.jsx/.ts/.tsx files as plain text. It will catch a plain CSS
`transition: ... ease-in` or `cubic-bezier(...)` wherever that text appears,
including inside a template literal or styled-components tag -- but it will
NOT understand CSS-in-JS object syntax (`{ transitionTimingFunction: 'ease-in' }`)
or a UI library's own animation prop API. It is a text-pattern scan, not a
parser for any of the frameworks it happens to run against.

Usage:
    python3 tf_motion_audit.py --root <project-dir> --json
    python3 tf_motion_audit.py --selftest

Exit 0 on success (findings do not change exit code -- caller decides
severity, same convention as tf_slop.py). Exit 1 on expected failure. Exit 2
on unexpected error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import tf_slop  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import tf_slop

_SCAN_EXTENSIONS = frozenset({".css", ".scss", ".js", ".jsx", ".ts", ".tsx"})

_EXCLUDE_DIR_NAMES = frozenset({
    "node_modules", ".git", "dist", "build", ".next", "out", "coverage",
    ".expo", ".turbo", ".cache", "vendor",
})

_MAX_FILE_BYTES = 2_000_000  # skip pathological generated bundles, not source


def _iter_project_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in _SCAN_EXTENSIONS:
            continue
        if any(part in _EXCLUDE_DIR_NAMES for part in p.parts):
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield p


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# Per-match rules: every occurrence gets its own finding with a line number.
# (pattern attribute on tf_slop, rule name, severity, message template taking
# the match object, category)
def _per_match_findings(text: str, rel_path: str) -> list[dict]:
    findings: list[dict] = []

    for m in tf_slop._CUBICBEZ_RE.finditer(text):
        try:
            y2 = float(m.group(4))
        except ValueError:
            continue
        if y2 > 1.0:
            findings.append({
                "rule": "easing-overshoot", "severity": "high", "category": "motion",
                "file": rel_path, "line": _line_of(text, m.start()),
                "snippet": m.group(0)[:80],
                "message": f"cubic-bezier y2={y2} > 1 — overshoot/bounce easing reads as dated on the web.",
            })

    for m in tf_slop._SCALE_ZERO_RE.finditer(text):
        findings.append({
            "rule": "scale-zero-entrance", "severity": "high", "category": "motion",
            "file": rel_path, "line": _line_of(text, m.start()),
            "snippet": m.group(0)[:80],
            "message": "scale(0) as an entrance value — nothing appears from nothing; use scale(0.9–0.97) + opacity.",
        })

    for m in tf_slop._EASE_IN_PROP_RE.finditer(text):
        findings.append({
            "rule": "ease-in-on-transition", "severity": "high", "category": "motion",
            "file": rel_path, "line": _line_of(text, m.start()),
            "snippet": m.group(0)[:80],
            "message": "ease-in on a transition/animation — starts slow, delaying the moment most watched.",
        })

    for m in tf_slop._TRANSITION_ALL_RE.finditer(text):
        findings.append({
            "rule": "transition-all", "severity": "high", "category": "motion",
            "file": rel_path, "line": _line_of(text, m.start()),
            "snippet": m.group(0)[:80],
            "message": "transition: all — animates every property including layout ones; name properties explicitly.",
        })

    return findings


# Per-file rules: these ask "does this whole file have X without Y", so one
# finding per file (with the line of the strongest signal), not per match.
def _per_file_findings(text: str, rel_path: str) -> list[dict]:
    findings: list[dict] = []

    hover_m = tf_slop._BARE_HOVER_RE.search(text)
    if hover_m and not tf_slop._HOVER_MEDIA_RE.search(text):
        findings.append({
            "rule": "ungated-hover", "severity": "high", "category": "motion",
            "file": rel_path, "line": _line_of(text, hover_m.start()),
            "snippet": hover_m.group(0),
            "message": ":hover styles with no @media (hover: hover) gate — touch devices fire false hovers on tap.",
        })

    anim_m = tf_slop._ANIM_PRESENT_RE.search(text)
    if anim_m and not tf_slop._REDUCED_MOTION_RE.search(text):
        findings.append({
            "rule": "missing-reduced-motion", "severity": "medium", "category": "accessibility",
            "file": rel_path, "line": _line_of(text, anim_m.start()),
            "snippet": anim_m.group(0),
            "message": "Transitions/animations present, no @media (prefers-reduced-motion: reduce) block.",
        })

    if anim_m and not tf_slop._CUBICBEZ_RE.search(text):
        findings.append({
            "rule": "weak-easing-only", "severity": "high", "category": "motion",
            "file": rel_path, "line": _line_of(text, anim_m.start()),
            "snippet": anim_m.group(0),
            "message": "Motion present but no custom cubic-bezier() anywhere — running on bare browser-default easing.",
        })

    return findings


def audit(root: Path) -> dict:
    findings: list[dict] = []
    files_scanned = 0
    for path in _iter_project_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files_scanned += 1
        rel = str(path.relative_to(root))
        findings.extend(_per_match_findings(text, rel))
        findings.extend(_per_file_findings(text, rel))
    return {"ok": True, "files_scanned": files_scanned, "finding_count": len(findings), "findings": findings}


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "styles.css").write_text(
            ".a { transition: transform 0.2s ease-in; }\n"
            ".b:hover { color: red; }\n"
            ".c { animation: pop 0.3s cubic-bezier(0.68, -0.6, 0.32, 1.6); }\n",
            encoding="utf-8",
        )
        (d / "node_modules").mkdir()
        (d / "node_modules" / "ignored.css").write_text(".x { scale(0); }", encoding="utf-8")
        result = audit(d)
        assert result["files_scanned"] == 1, result
        rules_found = {f["rule"] for f in result["findings"]}
        assert "ease-in-on-transition" in rules_found, result
        assert "ungated-hover" in rules_found, result
        assert "easing-overshoot" in rules_found, result
        assert "weak-easing-only" not in rules_found, "cubic-bezier present, should not flag weak-easing-only"
        for f in result["findings"]:
            assert isinstance(f["line"], int) and f["line"] >= 1, f
        sys.stderr.write("selftest OK\n")
        print(json.dumps({"ok": True, "selftest": True}))
        return 0

    root_arg: Path | None = None
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root_arg = Path(argv[i + 1]); i += 2
        else:
            i += 1

    if root_arg is None:
        msg = "--root <dir> required"
        sys.stderr.write(f"tf_motion_audit: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1
    if not root_arg.is_dir():
        msg = f"root not found: {root_arg}"
        sys.stderr.write(f"tf_motion_audit: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    result = audit(root_arg)
    sys.stderr.write(
        f"tf_motion_audit: scanned {result['files_scanned']} file(s), "
        f"{result['finding_count']} finding(s)\n"
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover - unexpected
        sys.stderr.write(f"tf_motion_audit: unexpected error: {exc}\n")
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
