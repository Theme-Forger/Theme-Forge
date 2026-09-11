#!/usr/bin/env python3
"""tf_imagery.py -- art direction brief and optional stock image search.

Usage:
    python3 tf_imagery.py --theme <dir> [--json]

Reads theme.json for palette, thesis, and direction.
Always writes brand/imagery/ART-DIRECTION.md.
Fetches stock images if PEXELS_API_KEY is set.
Writes brand/imagery/sources.json.

Python 3.9+, standard library only. Exit 0/1/2.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Slot -> image vocabulary mapping
# ---------------------------------------------------------------------------

SLOT_VOCAB = {
    "A": {
        "mood": "understated, refined, quietly confident",
        "lighting": "soft diffused light, muted contrast",
        "avoid": "loud colours, busy backgrounds, casual settings",
        "hero_subject": "professional workspace or architectural detail",
        "feature_subject": "clean product or service in context",
    },
    "B": {
        "mood": "bold, energetic, high-impact",
        "lighting": "strong directional light, vivid contrast",
        "avoid": "muted or greyed palettes, generic stock smiles",
        "hero_subject": "dynamic action or striking product hero shot",
        "feature_subject": "product in use with saturated environmental colour",
    },
    "C": {
        "mood": "editorial, curated, typographic",
        "lighting": "high-key or dramatic, editorial-magazine quality",
        "avoid": "candid snapshots, over-processed filters",
        "hero_subject": "editorial flat-lay or curated object composition",
        "feature_subject": "detail shot with strong typographic overlay potential",
    },
    "D": {
        "mood": "technical, precise, dark-mode-native",
        "lighting": "low-key, spotlight accents on dark backgrounds",
        "avoid": "bright white backgrounds, lifestyle photography",
        "hero_subject": "abstract technical texture or code/circuit motif",
        "feature_subject": "interface or tool in dark environment",
    },
    "E": {
        "mood": "warm, human, approachable",
        "lighting": "warm golden-hour or window light, soft shadows",
        "avoid": "cold blue tones, corporate stiffness, looking at camera",
        "hero_subject": "candid moment of human connection or craft",
        "feature_subject": "hands-on activity or person in natural setting",
    },
    "F": {
        "mood": "modular, playful, eclectic",
        "lighting": "bright and even, adaptable to multiple card sizes",
        "avoid": "single dominant focal point, cinematic crops",
        "hero_subject": "collage or grid of contrasting elements",
        "feature_subject": "isolated object on coloured background, card-ready",
    },
}

DEFAULT_VOCAB = SLOT_VOCAB["A"]


# ---------------------------------------------------------------------------
# Art direction writer
# ---------------------------------------------------------------------------

def _art_direction_md(theme: dict, slug: str) -> str:
    name = theme.get("name", "Theme")
    thesis = theme.get("thesis") or theme.get("description") or "A distinctive visual identity."
    slot = (theme.get("slot") or "A").upper()[:1]
    direction = theme.get("direction") or ""
    vocab = SLOT_VOCAB.get(slot, DEFAULT_VOCAB)

    color = theme.get("color") or {}
    light = color.get("light") or {}

    def _hex(key: str, fallback: str) -> str:
        v = light.get(key)
        if isinstance(v, dict):
            return v.get("hex", fallback)
        return fallback if not isinstance(v, str) else v

    primary = _hex("primary", "#6366f1")
    accent = _hex("accent", "#a78bfa")
    neutral = _hex("neutral", "#64748b")
    surface = _hex("surface", "#f8fafc")
    background = _hex("background", "#ffffff")

    mood = vocab["mood"]
    lighting = vocab["lighting"]
    avoid = vocab["avoid"]
    hero_subj = vocab["hero_subject"]
    feat_subj = vocab["feature_subject"]

    return """\
# Art Direction — {name}

Thesis: {thesis}

Direction: {direction}

---

## Palette reference

| Role       | Hex       |
|------------|-----------|
| Primary    | {primary} |
| Accent     | {accent}  |
| Neutral    | {neutral} |
| Surface    | {surface} |
| Background | {background} |

---

## Image slots

### Hero
- Subject: {hero_subj}
- Composition: landscape 16:9, 1920×1080 px minimum
- Lighting: {lighting}
- Dominant palette: {primary}, {neutral}
- Mood: {mood}
- Avoid: {avoid}; faces looking directly at camera; harsh cropping

### Feature 1
- Subject: {feat_subj}
- Composition: landscape 4:3, 800×600 px
- Lighting: {lighting}, consistent with Hero
- Dominant palette: {accent}, {surface}
- Mood: {mood}, slightly quieter than hero

### Feature 2
- Subject: Close-up detail that embodies the brand vocabulary
- Composition: square 1:1, 800×800 px
- Lighting: {lighting}
- Dominant palette: {primary}, {background}
- Mood: refined, deliberate

### Feature 3
- Subject: Context or environment that anchors the brand
- Composition: landscape 3:2, 800×533 px
- Lighting: {lighting}
- Mood: {mood}

### Testimonial avatar
- Subject: Portrait of a person (real or illustrated)
- Composition: square 1:1, 400×400 px
- Background: solid {surface} or very soft blur
- Style: natural, not staged; avoid direct gaze at camera
- Mood: relatable, warm

### Empty state illustration
- Subject: Abstract or geometric motif drawn from the brand vocabulary
- Composition: landscape 4:3, 400×300 px
- Style: flat illustration, uses {primary}, {accent}, {surface}
- Avoid: clip art, generic sad-robot clichés

---

## Placeholder URLs

The URLs below are deterministic picsum.photos placeholders.
**Replace before launch.**

- Hero: https://picsum.photos/seed/{slug}-hero/1920/1080
- Feature 1: https://picsum.photos/seed/{slug}-f1/800/600
- Feature 2: https://picsum.photos/seed/{slug}-f2/800/800
- Feature 3: https://picsum.photos/seed/{slug}-f3/800/533
- Avatar: https://picsum.photos/seed/{slug}-avatar/400/400

---

## Sourcing checklist

- [ ] Brief reviewed by designer
- [ ] Usage rights confirmed (CC0, royalty-free, or licensed)
- [ ] Colour-graded to match palette (subtle overlay or LUT)
- [ ] Faces not cropped at chin or crown
- [ ] WebP version exported alongside JPEG/PNG
- [ ] `alt` text written for every image
""".format(
        name=name,
        thesis=thesis,
        direction=direction,
        primary=primary,
        accent=accent,
        neutral=neutral,
        surface=surface,
        background=background,
        mood=mood,
        lighting=lighting,
        avoid=avoid,
        hero_subj=hero_subj,
        feat_subj=feat_subj,
        slug=slug,
    )


# ---------------------------------------------------------------------------
# Pexels fetch
# ---------------------------------------------------------------------------

def _fetch_pexels(api_key: str, query: str, per_page: int = 3) -> list[dict]:
    url = (
        "https://api.pexels.com/v1/search?query=%s&per_page=%d"
        % (urllib.request.quote(query), per_page)
    )
    req = urllib.request.Request(url, headers={"Authorization": api_key})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [
                {
                    "id": p.get("id"),
                    "url": p.get("url"),
                    "src": (p.get("src") or {}).get("large2x"),
                    "alt": p.get("alt"),
                    "photographer": p.get("photographer"),
                }
                for p in (data.get("photos") or [])
            ]
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError) as exc:
        sys.stderr.write("tf_imagery: pexels fetch failed: %s\n" % exc)
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_imagery(theme_dir: Path) -> dict:
    theme_json_path = theme_dir / "theme.json"
    theme: dict = {}
    if theme_json_path.is_file():
        try:
            theme = json.loads(theme_json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    slug = theme.get("slug", "theme")
    name = theme.get("name", "Theme")

    # Determine a stock search keyword from theme name/direction/thesis
    direction = theme.get("direction") or ""
    keyword_parts = [name]
    if direction:
        keyword_parts.append(direction.split()[0] if direction else "")
    keyword = " ".join(p for p in keyword_parts if p).strip() or "professional"

    imagery_dir = theme_dir / "brand" / "imagery"
    imagery_dir.mkdir(parents=True, exist_ok=True)

    # Write ART-DIRECTION.md
    md_content = _art_direction_md(theme, slug)
    md_path = imagery_dir / "ART-DIRECTION.md"
    md_path.write_text(md_content, encoding="utf-8")
    sys.stderr.write("tf_imagery: wrote %s\n" % md_path)

    # Placeholder URLs (never fetched at build time)
    placeholder_urls = {
        "hero": "https://picsum.photos/seed/%s-hero/1920/1080" % slug,
        "feature_1": "https://picsum.photos/seed/%s-f1/800/600" % slug,
        "feature_2": "https://picsum.photos/seed/%s-f2/800/800" % slug,
        "feature_3": "https://picsum.photos/seed/%s-f3/800/533" % slug,
        "avatar": "https://picsum.photos/seed/%s-avatar/400/400" % slug,
    }

    # Stock search
    pexels_key = os.environ.get("PEXELS_API_KEY")
    stock_results: list[dict] = []
    provider = None

    if pexels_key:
        sys.stderr.write("tf_imagery: searching Pexels for %r...\n" % keyword)
        stock_results = _fetch_pexels(pexels_key, keyword, per_page=3)
        if stock_results:
            provider = "pexels"
            sys.stderr.write("tf_imagery: got %d Pexels results\n" % len(stock_results))

    strategy = "brief" if not provider else "stock+brief"

    sources = {
        "strategy": strategy,
        "provider": provider,
        "attribution_required": False,
        "placeholder_urls": placeholder_urls,
        "brief": str(md_path),
        "stock_results": stock_results if stock_results else [],
    }
    sources_path = imagery_dir / "sources.json"
    sources_path.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    sys.stderr.write("tf_imagery: wrote %s\n" % sources_path)

    return {
        "ok": True,
        "strategy": strategy,
        "art_direction": str(md_path),
        "sources_json": str(sources_path),
        "stock_results": len(stock_results),
    }


def main(argv: list) -> int:
    want_json = "--json" in argv

    if "--theme" not in argv:
        sys.stderr.write("usage: tf_imagery.py --theme <dir> [--json]\n")
        print(json.dumps({"ok": False, "error": "missing --theme"}))
        return 1

    theme_dir = Path(argv[argv.index("--theme") + 1])
    result = generate_imagery(theme_dir)

    if want_json:
        print(json.dumps(result))
    else:
        sys.stderr.write("tf_imagery: strategy=%s, stock=%d\n"
                         % (result["strategy"], result["stock_results"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_imagery: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
