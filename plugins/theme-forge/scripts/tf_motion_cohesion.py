#!/usr/bin/env python3
"""tf_motion_cohesion.py -- Gate 20: motion/design_language cohesion check.

Reads every theme.json in a themes-dir and mechanically re-derives the
comparison agents/design-critic.md's own "SS7b-cohesion" section previously
asked the LLM critic to compute by hand each run: does motion.character match
the expected character for this theme's composition.design_language, does
motion.duration.normal stay within 50% of that language's baseline, and is
motion.easing.standard something other than a bare CSS keyword?

None of this requires visual or aesthetic judgment -- it is a fixed lookup
table plus arithmetic and a string-literal check, so it moves here rather
than being computed fresh by design-critic on every run. design-critic still
owns the one thing a table can't answer: whether the built theme's actual
*feel* (from screenshots) matches motion.character at all, and whether a
theme's motion matches what its own composition.ambition claims.

Usage:
    python3 tf_motion_cohesion.py --themes-dir <dir> --json

Findings are advisory-only, same tier as tf_distinct.py's Gate 18/19 -- this
is a re-statement of an existing prose check made mechanical, not a new hard
requirement, so it must not newly block assembly for themes that would have
passed the LLM-judgment version of the same check.

Exit 0 always (advisory). Exit 1 on expected failure (bad themes-dir). Exit 2
on unexpected error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# design_language -> (expected motion.character, max baseline duration ms)
#
# DELIBERATELY EMPTY, and must stay that way. Do not repopulate it.
#
# This held five rows keyed to the closed six-value enum `design_language` used
# to be. That enum was retired on 2026-09-09 and its stock value names were
# struck from every Theme Forge artifact on 2026-09-10 so nothing could fall
# back to them -- they are deliberately not repeated here either, because a
# list of them in a comment is the first thing a future reader would restore.
# The vocabulary is now derived from the brief, so real languages look like
# `neobrutalism`,
# `hand-drawn`, `parallax-scrolling`, `minimalism`. None of those were ever in
# the table, which meant the lookup could only ever fire for names no theme
# produces anymore -- dead weight that could only misfire if someone "helpfully"
# added a guessed row for a live language.
#
# There is no correct table to write here. An expected motion character is only
# knowable from a register someone actually defined, and under an open
# vocabulary that definition lives in the theme's own `composition.ambition`.
# Guessing that `minimalism` implies `crisp` at 200ms would grade a theme
# against a register nobody chose -- exactly the lossy mapping the enum's
# retirement was meant to end.
#
# Consequence, by design: `check()` skips every theme's character/duration
# comparison and Gate 20 contributes only its language-independent
# `_BARE_EASING_KEYWORDS` check. Motion-vs-register cohesion is design-critic's
# judgment, made against each theme's stated ambition. The function below is
# left intact rather than deleted so that a future *brief-derived* expectation
# (one supplied per run, not hardcoded here) has somewhere to plug in.
_EXPECTED: dict[str, tuple[str, int]] = {}

_BARE_EASING_KEYWORDS = frozenset({
    "ease", "ease-in", "ease-out", "ease-in-out", "linear",
})


def _load_theme(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    comp = data.get("composition") or {}
    motion = data.get("motion") or {}
    duration = motion.get("duration") or {}
    easing = motion.get("easing") or {}
    return {
        "slug": data.get("slug", path.parent.name),
        "design_language": comp.get("design_language", ""),
        "character": motion.get("character", ""),
        "duration_normal": duration.get("normal"),
        "easing_standard": easing.get("standard"),
    }


def check(themes_dir: Path) -> dict:
    theme_files = sorted(themes_dir.glob("*/theme.json"))
    themes = [t for f in theme_files if (t := _load_theme(f)) is not None]

    findings: list[dict] = []
    for t in themes:
        lang = t["design_language"]
        expected = _EXPECTED.get(lang)
        if expected is None:
            continue  # every language, now that _EXPECTED is empty by design --
            # motion-vs-register cohesion is design-critic's judgment, made
            # against this theme's own composition.ambition, not a lookup's.
        expected_character, max_duration = expected

        if t["character"] and t["character"] != expected_character:
            findings.append({
                "code": "motion_cohesion_character",
                "slug": t["slug"],
                "message": (
                    f"'{t['slug']}' design_language='{lang}' expects "
                    f"motion.character='{expected_character}' but has "
                    f"'{t['character']}'."
                ),
            })

        dur = t["duration_normal"]
        if isinstance(dur, (int, float)) and dur > max_duration * 1.5:
            findings.append({
                "code": "motion_cohesion_duration",
                "slug": t["slug"],
                "message": (
                    f"'{t['slug']}' motion.duration.normal={dur}ms exceeds "
                    f"design_language='{lang}''s baseline of {max_duration}ms "
                    f"by more than 50% (threshold {max_duration * 1.5:.0f}ms)."
                ),
            })

        easing = t["easing_standard"]
        if isinstance(easing, str) and easing.strip().lower() in _BARE_EASING_KEYWORDS:
            findings.append({
                "code": "motion_cohesion_easing",
                "slug": t["slug"],
                "message": (
                    f"'{t['slug']}' motion.easing.standard=\"{easing}\" is a bare "
                    f"CSS keyword, not a custom curve -- name a cubic-bezier() "
                    f"value that expresses this theme's motion character."
                ),
            })

    return {"ok": True, "theme_count": len(themes), "findings": findings}


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    themes_dir: Path | None = None

    i = 0
    while i < len(argv):
        if argv[i] == "--themes-dir" and i + 1 < len(argv):
            themes_dir = Path(argv[i + 1])
            i += 2
        else:
            i += 1

    if themes_dir is None:
        scripts_dir = Path(__file__).resolve().parent
        sys.path.insert(0, str(scripts_dir))
        try:
            import tf_paths
            themes_dir = tf_paths.resolve(create=False).current_themes
        except Exception:
            msg = "--themes-dir required (tf_paths unavailable)"
            sys.stderr.write(f"tf_motion_cohesion: {msg}\n")
            print(json.dumps({"ok": False, "error": msg}))
            return 1

    if not themes_dir.is_dir():
        msg = f"themes-dir not found: {themes_dir}"
        sys.stderr.write(f"tf_motion_cohesion: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    result = check(themes_dir)

    sys.stderr.write("\nMOTION COHESION GATE (advisory)\n")
    sys.stderr.write("─" * 70 + "\n")
    if result["findings"]:
        for f in result["findings"]:
            sys.stderr.write(f"  ⚠ [{f['code']}] {f['message']}\n")
    else:
        sys.stderr.write("  ✓ no cohesion mismatches\n")
    sys.stderr.write("─" * 70 + "\n")

    if want_json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover - unexpected
        sys.stderr.write(f"tf_motion_cohesion: unexpected error: {exc}\n")
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
