#!/usr/bin/env python3
"""tf_icons.py -- generate a themed 24-icon SVG set.

Usage:
    python3 tf_icons.py --theme <dir> [--library lucide] [--json]

Reads theme.json for stroke width, cap style, join style, corner radius.
Generates 24 SVGs to brand/icons/set/<name>.svg, plus icons.json and ICONS.md.

Python 3.9+, standard library only. Exit 0/1/2.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Icon definitions
# Each icon is a list of SVG element strings on a 24x24 unit viewBox.
# All use {stroke}, {cap}, {join} template variables.
# ---------------------------------------------------------------------------

ICON_DEFS: dict[str, list[str]] = {
    "home": [
        '<polyline points="3,10 12,3 21,10" fill="none"/>',
        '<rect x="5" y="10" width="14" height="11" rx="1" fill="none"/>',
        '<rect x="9" y="15" width="6" height="6" rx="0" fill="none"/>',
    ],
    "search": [
        '<circle cx="11" cy="11" r="7" fill="none"/>',
        '<line x1="16.5" y1="16.5" x2="22" y2="22"/>',
    ],
    "settings": [
        '<circle cx="12" cy="12" r="3" fill="none"/>',
        '<path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12'
        'M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" fill="none"/>',
    ],
    "user": [
        '<circle cx="12" cy="8" r="4" fill="none"/>',
        '<path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" fill="none"/>',
    ],
    "bell": [
        '<path d="M6 9a6 6 0 0 1 12 0v5l2 2H4l2-2V9Z" fill="none"/>',
        '<path d="M10 19a2 2 0 0 0 4 0" fill="none"/>',
    ],
    "plus": [
        '<line x1="12" y1="4" x2="12" y2="20"/>',
        '<line x1="4" y1="12" x2="20" y2="12"/>',
    ],
    "close": [
        '<line x1="4" y1="4" x2="20" y2="20"/>',
        '<line x1="20" y1="4" x2="4" y2="20"/>',
    ],
    "check": [
        '<polyline points="4,12 9,17 20,6" fill="none"/>',
    ],
    "chevron-up": [
        '<polyline points="5,15 12,8 19,15" fill="none"/>',
    ],
    "chevron-down": [
        '<polyline points="5,9 12,16 19,9" fill="none"/>',
    ],
    "chevron-left": [
        '<polyline points="15,5 8,12 15,19" fill="none"/>',
    ],
    "chevron-right": [
        '<polyline points="9,5 16,12 9,19" fill="none"/>',
    ],
    "menu": [
        '<line x1="3" y1="7" x2="21" y2="7"/>',
        '<line x1="3" y1="12" x2="21" y2="12"/>',
        '<line x1="3" y1="17" x2="21" y2="17"/>',
    ],
    "trash": [
        '<polyline points="3,6 21,6" fill="none"/>',
        '<path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" fill="none"/>',
        '<rect x="5" y="7" width="14" height="13" rx="1" fill="none"/>',
        '<line x1="10" y1="11" x2="10" y2="17"/>',
        '<line x1="14" y1="11" x2="14" y2="17"/>',
    ],
    "edit": [
        '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"'
        ' fill="none"/>',
        '<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 7.5-7.5Z"'
        ' fill="none"/>',
    ],
    "download": [
        '<line x1="12" y1="3" x2="12" y2="15"/>',
        '<polyline points="7,10 12,15 17,10" fill="none"/>',
        '<line x1="4" y1="20" x2="20" y2="20"/>',
    ],
    "upload": [
        '<line x1="12" y1="21" x2="12" y2="9"/>',
        '<polyline points="7,14 12,9 17,14" fill="none"/>',
        '<line x1="4" y1="4" x2="20" y2="4"/>',
    ],
    "external-link": [
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"'
        ' fill="none"/>',
        '<polyline points="15,3 21,3 21,9" fill="none"/>',
        '<line x1="10" y1="14" x2="21" y2="3"/>',
    ],
    "calendar": [
        '<rect x="3" y="4" width="18" height="18" rx="2" fill="none"/>',
        '<line x1="3" y1="9" x2="21" y2="9"/>',
        '<line x1="8" y1="2" x2="8" y2="6"/>',
        '<line x1="16" y1="2" x2="16" y2="6"/>',
    ],
    "clock": [
        '<circle cx="12" cy="12" r="9" fill="none"/>',
        '<polyline points="12,6 12,12 16,14" fill="none"/>',
    ],
    "mail": [
        '<rect x="2" y="5" width="20" height="14" rx="2" fill="none"/>',
        '<polyline points="2,5 12,13 22,5" fill="none"/>',
    ],
    "lock": [
        '<rect x="5" y="11" width="14" height="10" rx="2" fill="none"/>',
        '<path d="M8 11V7a4 4 0 0 1 8 0v4" fill="none"/>',
        '<circle cx="12" cy="16" r="1" fill="currentColor" stroke="none"/>',
    ],
    "eye": [
        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z" fill="none"/>',
        '<circle cx="12" cy="12" r="3" fill="none"/>',
    ],
    "filter": [
        '<path d="M4 4h16l-6 8v6l-4-2V12L4 4Z" fill="none"/>',
    ],
}


# ---------------------------------------------------------------------------
# SVG builder
# ---------------------------------------------------------------------------

def _build_icon_svg(name: str, elements: list[str],
                    stroke: float, cap: str, join: str) -> str:
    inner_lines = []
    for elem in elements:
        # Inject stroke attributes onto elements that need them
        if 'stroke="none"' in elem:
            inner_lines.append("  " + elem)
        else:
            inner_lines.append("  " + elem)

    inner = "\n".join(inner_lines)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'width="24" height="24" fill="none" '
        'stroke="currentColor" stroke-width="{sw}" '
        'stroke-linecap="{cap}" stroke-linejoin="{join}" '
        'role="img" aria-label="{name}">\n'
        '{inner}\n'
        '</svg>\n'
    ).format(sw=stroke, cap=cap, join=join, name=name, inner=inner)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_icons(theme_dir: Path, library: str = "lucide") -> dict:
    theme_json_path = theme_dir / "theme.json"
    theme: dict = {}
    if theme_json_path.is_file():
        try:
            theme = json.loads(theme_json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Read icon style from theme
    icons_cfg = theme.get("icons") or {}
    stroke = float(icons_cfg.get("stroke", 1.5))
    direction = theme.get("direction", "")

    # Cap style from direction heuristic
    if "Editorial" in direction or "Technical" in direction:
        cap = "square"
        join = "miter"
    elif "Warm" in direction or "Human" in direction:
        cap = "round"
        join = "round"
    else:
        cap = "round"
        join = "round"

    # Override from theme if explicit
    cap = icons_cfg.get("stroke_linecap", cap)
    join = icons_cfg.get("stroke_linejoin", join)

    icons_dir = theme_dir / "brand" / "icons" / "set"
    icons_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for name, elements in ICON_DEFS.items():
        svg = _build_icon_svg(name, elements, stroke, cap, join)
        p = icons_dir / ("%s.svg" % name)
        p.write_text(svg, encoding="utf-8")
        written.append(name)
        sys.stderr.write("tf_icons: wrote %s.svg\n" % name)

    # icons.json
    icons_json = {
        "library": library,
        "source_license": "ISC",
        "stroke": stroke,
        "stroke_linecap": cap,
        "stroke_linejoin": join,
        "count": len(written),
        "restyled": True,
        "attribution_required": False,
        "fallback_generated": True,
    }
    icons_json_path = theme_dir / "brand" / "icons" / "icons.json"
    icons_json_path.write_text(json.dumps(icons_json, indent=2) + "\n",
                                encoding="utf-8")

    # ICONS.md
    icons_md = """\
# Icons

This icon set was generated by tf_icons.py using fallback geometry.
The icons follow the Lucide design language (24x24 grid, {stroke}px stroke).

## Using the real Lucide set

**React (web):**
```
npm install lucide-react
```
```jsx
import {{ Home, Search }} from 'lucide-react';
```

**React Native:**
```
npm install lucide-react-native react-native-svg
```
```jsx
import {{ Home }} from 'lucide-react-native';
```

## License

Lucide is ISC licensed. Attribution is not required.
See https://lucide.dev/license

## Restyling

The icons in `brand/icons/set/` have been restyled with the project's
stroke width ({stroke}px), linecap ({cap}), and linejoin ({join}).
""".format(stroke=stroke, cap=cap, join=join)

    (theme_dir / "brand" / "icons" / "ICONS.md").write_text(
        icons_md, encoding="utf-8"
    )

    return {
        "ok": True,
        "count": len(written),
        "library": library,
        "generated_from": "fallback",
        "dir": str(icons_dir),
        "stroke": stroke,
    }


def main(argv: list) -> int:
    want_json = "--json" in argv
    library = "lucide"
    if "--library" in argv:
        library = argv[argv.index("--library") + 1]

    if "--theme" not in argv:
        sys.stderr.write("usage: tf_icons.py --theme <dir> [--library lucide] [--json]\n")
        print(json.dumps({"ok": False, "error": "missing --theme"}))
        return 1

    theme_dir = Path(argv[argv.index("--theme") + 1])
    result = generate_icons(theme_dir, library=library)

    if want_json:
        print(json.dumps(result))
    else:
        sys.stderr.write("tf_icons: %d icons written to %s\n"
                         % (result["count"], result["dir"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_icons: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
