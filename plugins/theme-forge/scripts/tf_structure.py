#!/usr/bin/env python3
"""tf_structure.py -- structural-distinctiveness gate for a generated theme set.

Before the bespoke-composition rewrite (2026-09-03), `tf_distinct.py`'s
composition gates compared self-reported `theme.json` metadata labels
(hero_archetype, grid_strategy, nav_pattern) for exact equality. That worked
only because those labels were drawn from a shared, closed enum -- with
exactly six themes and six hero_archetype values, uniqueness was guaranteed
by the pigeonhole principle, not measured. Once composition is free-form and
authored per theme, that check becomes meaningless: two themes could declare
different labels while rendering near-identically, and nothing would catch
it.

This script measures actual rendered structure instead of self-reported
labels. For each pair of themes, it extracts a structural feature vector from
that theme's own authored `surfaces/<surface>.html`/`.css` (heading shape,
section count, DOM depth, layout mechanism, class-name-fragment overlap, grid
track counts) and computes a similarity score. Two themes scoring above the
threshold get flagged -- not because they used the same words, but because
their rendered structure actually converges.

Advisory-only in this phase (website, webapp, and mobile surfaces all
covered as of phase 3). Findings are surfaced as warnings, never hard-stops,
until thresholds are calibrated against real runs -- see the phasing note in
the project's implementation plan. Promote to a hard gate only after that
calibration.

Usage:
    python3 tf_structure.py --themes-dir <dir> --json [--surfaces website]
    python3 tf_structure.py --selftest

Standard library only. Python 3.9+.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

try:
    import tf_htmlshape as shape  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import tf_htmlshape as shape


# ---------------------------------------------------------------------------
# Similarity threshold and per-feature weights -- named constants so future
# calibration (per the phasing plan) is a one-line change, not a hunt through
# the scoring logic.
# ---------------------------------------------------------------------------

STRUCTURAL_SIMILARITY_MAX = 0.55  # advisory threshold; conservative starting point

_WEIGHTS = {
    "heading_sequence": 0.20,
    "section_count": 0.10,
    "class_shingles": 0.30,   # heaviest -- catches convergent structure under divergent names
    "container_tags": 0.20,
    "layout_mode": 0.10,
    "grid_tracks": 0.10,
}


def _counter_cosine(a: Counter, b: Counter) -> float:
    """Cosine similarity between two sparse count vectors. 1.0 if both empty."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    norm_a = sum(v * v for v in a.values()) ** 0.5
    norm_b = sum(v * v for v in b.values()) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sequence_ratio(a: list, b: list) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def feature_vector(html: str, css: str, surface: str) -> dict:
    nodes = shape.parse(html)
    vec: dict = {
        "heading_sequence": shape.heading_sequence(nodes),
        "section_count": shape.count_sections(nodes),
        "dom_depth_histogram": shape.dom_depth_histogram(nodes),
        "layout_mode": shape.layout_mode_ratio(css),
        "container_tags": shape.container_tag_profile(nodes),
        "class_shingles": shape.class_name_shingles(nodes),
        "grid_tracks": shape.grid_track_signature(css),
    }
    if surface == "mobile":
        screen_names = shape.screens(nodes)
        vec["screen_count"] = len(screen_names)
        vec["screen_names"] = Counter(screen_names)
    return vec


def pairwise_similarity(vec_a: dict, vec_b: dict) -> tuple[float, dict]:
    """Returns (overall similarity 0-1, {feature: sub-score}) for one surface."""
    sub: dict = {}
    sub["heading_sequence"] = _sequence_ratio(vec_a["heading_sequence"], vec_b["heading_sequence"])
    max_sections = max(vec_a["section_count"], vec_b["section_count"], 1)
    sub["section_count"] = 1.0 - abs(vec_a["section_count"] - vec_b["section_count"]) / max_sections
    sub["class_shingles"] = _jaccard(vec_a["class_shingles"], vec_b["class_shingles"])
    sub["container_tags"] = _counter_cosine(vec_a["container_tags"], vec_b["container_tags"])
    layout_a = Counter(vec_a["layout_mode"])
    layout_b = Counter(vec_b["layout_mode"])
    sub["layout_mode"] = _counter_cosine(layout_a, layout_b)
    sub["grid_tracks"] = _counter_cosine(vec_a["grid_tracks"], vec_b["grid_tracks"])

    overall = sum(sub[k] * w for k, w in _WEIGHTS.items())
    return overall, sub


def _read_surface(theme_dir: Path, surface: str) -> tuple[str, str] | None:
    html_path = theme_dir / "surfaces" / f"{surface}.html"
    css_path = theme_dir / "surfaces" / f"{surface}.css"
    if not html_path.is_file() or not css_path.is_file():
        return None
    try:
        return html_path.read_text(encoding="utf-8"), css_path.read_text(encoding="utf-8")
    except OSError:
        return None


def check(themes_dir: Path, surfaces: tuple[str, ...] = ("website", "webapp", "mobile")) -> dict:
    """Compute pairwise structural similarity for each surface across all
    themes under *themes_dir*. Exit-free, importable entry point -- callers
    (tf_distinct.py) decide whether findings are advisory or blocking.

    Returns {"ok": bool, "surfaces_checked": [...], "findings": [...],
    "skipped": [...]}. "ok" is True unless a pair exceeds
    STRUCTURAL_SIMILARITY_MAX -- callers in advisory mode should still
    proceed regardless of "ok", per the phasing plan.
    """
    theme_dirs = sorted(d for d in themes_dir.iterdir() if d.is_dir())
    findings: list[dict] = []
    skipped: list[str] = []

    for surface in surfaces:
        vectors: dict[str, dict] = {}
        for td in theme_dirs:
            surf = _read_surface(td, surface)
            if surf is None:
                skipped.append(f"{td.name}/{surface} (no surfaces/{surface}.html+.css yet)")
                continue
            html, css = surf
            vectors[td.name] = feature_vector(html, css, surface)

        slugs = sorted(vectors)
        for i in range(len(slugs)):
            for j in range(i + 1, len(slugs)):
                a, b = slugs[i], slugs[j]
                score, sub = pairwise_similarity(vectors[a], vectors[b])
                if score > STRUCTURAL_SIMILARITY_MAX:
                    driving = sorted(sub.items(), key=lambda kv: -kv[1])[:3]
                    findings.append({
                        "surface": surface,
                        "slug_a": a,
                        "slug_b": b,
                        "similarity": round(score, 3),
                        "driving_signals": {k: round(v, 3) for k, v in driving},
                        "message": (
                            f"'{a}' and '{b}' score {score:.2f} structural similarity on "
                            f"{surface} (threshold {STRUCTURAL_SIMILARITY_MAX}) -- strongest "
                            f"overlap: {', '.join(f'{k}={v:.2f}' for k, v in driving)}"
                        ),
                    })

    return {
        "ok": len(findings) == 0,
        "surfaces_checked": list(surfaces),
        "findings": findings,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        test = {"ok": True, "selftest": True}
        assert json.loads(json.dumps(test)) == test
        # Round-trip a tiny real comparison too, not just JSON shape.
        html_a = "<h1>A</h1><section class='hero-a'><p>x</p></section>"
        html_b = "<h1>A</h1><section class='hero-a'><p>x</p></section>"
        vec_a = feature_vector(html_a, "", "website")
        vec_b = feature_vector(html_b, "", "website")
        score, _ = pairwise_similarity(vec_a, vec_b)
        assert score >= 0.9, f"expected near-identical markup to score high, got {score}"
        sys.stderr.write("selftest OK\n")
        print(json.dumps(test))
        return 0

    want_json = "--json" in argv
    if not want_json:
        print(json.dumps({"ok": False, "error": "pass --json to get structured output"}))
        return 1

    themes_dir: Path | None = None
    surfaces: tuple[str, ...] = ("website", "webapp", "mobile")
    i = 0
    while i < len(argv):
        if argv[i] == "--themes-dir" and i + 1 < len(argv):
            themes_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--surfaces" and i + 1 < len(argv):
            surfaces = tuple(s.strip() for s in argv[i + 1].split(",") if s.strip()); i += 2
        else:
            i += 1

    if themes_dir is None:
        try:
            import tf_paths  # type: ignore
            paths = tf_paths.resolve(create=False)
            themes_dir = Path(paths.current_themes)
        except Exception:
            print(json.dumps({"ok": False, "error": "--themes-dir required (tf_paths unavailable)"}))
            return 1

    if not themes_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"themes-dir not found: {themes_dir}"}))
        return 1

    result = check(themes_dir, surfaces)
    if result["skipped"]:
        sys.stderr.write(
            "tf_structure: skipped (no authored surface yet): %s\n" % ", ".join(result["skipped"])
        )
    for f in result["findings"]:
        sys.stderr.write("tf_structure: %s\n" % f["message"])
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"unhandled: {exc}"}))
        sys.exit(2)
