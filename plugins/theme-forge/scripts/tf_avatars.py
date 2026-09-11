#!/usr/bin/env python3
"""tf_avatars.py -- generate theme-colored geometric identicons + avatar config.

Usage:
    python3 tf_avatars.py --theme <dir> [--json]

Reads theme.json for slot, direction, and color palette.
Generates 8 SVG samples in brand/avatars/samples/ and avatar-config.json.

Python 3.9+, standard library only. Exit 0/1/2.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Style selection by slot
# ---------------------------------------------------------------------------

# DiceBear API version. Pinned to 9.x deliberately: 10.x is live and serves
# ~61 styles, of which ~30 are new and their artwork licenses are unaudited.
# The table below covers exactly the 31 styles of 9.x.
DICEBEAR_VERSION = "9.x"

# Per-style ARTWORK license. Each DiceBear style wraps a third-party artist's
# work under that artist's terms; the wrapper's code is MIT regardless.
#
# NEVER read this from the npm package's `package.json` "license" field: it says
# MIT for every style, because it describes Körner's code and not the artwork.
# A naive read marks all 13 CC-BY styles as MIT. The authority is the style's
# exported `meta.license`, which is also embedded in every SVG response as
# Dublin Core metadata (see tf_assets.license_from_svg).
STYLE_LICENSES = {
    # CC0 1.0 — no attribution, redistribution permitted. Safe by default.
    "glass": "CC0-1.0", "identicon": "CC0-1.0", "initials": "CC0-1.0",
    "lorelei": "CC0-1.0", "lorelei-neutral": "CC0-1.0",
    "notionists": "CC0-1.0", "notionists-neutral": "CC0-1.0",
    "open-peeps": "CC0-1.0", "pixel-art": "CC0-1.0",
    "pixel-art-neutral": "CC0-1.0", "rings": "CC0-1.0", "shapes": "CC0-1.0",
    "thumbs": "CC0-1.0",
    # MIT — notice must travel with a redistributed copy, no visible credit.
    "icons": "MIT",
    # CC BY 4.0 — visible credit required. Opt-in only, never a default slot.
    "adventurer": "CC-BY-4.0", "adventurer-neutral": "CC-BY-4.0",
    "big-ears": "CC-BY-4.0", "big-ears-neutral": "CC-BY-4.0",
    "big-smile": "CC-BY-4.0", "croodles": "CC-BY-4.0",
    "croodles-neutral": "CC-BY-4.0", "dylan": "CC-BY-4.0",
    "fun-emoji": "CC-BY-4.0", "micah": "CC-BY-4.0", "miniavs": "CC-BY-4.0",
    "personas": "CC-BY-4.0", "toon-head": "CC-BY-4.0",
}

# Hard-blocked. Upstream terms are the single line "Free for personal and
# commercial use. 😇" with no sublicensing, redistribution, or attribution
# clause, so bundling the output into a zip handed to a third party is
# unconfirmable. Both source domains also currently serve expired TLS
# certificates, so even that one sentence cannot be retrieved reliably.
STYLE_BLOCKED = {
    "avataaars": "terms do not address redistribution; source TLS expired",
    "avataaars-neutral": "terms do not address redistribution; source TLS expired",
    "bottts": "terms do not address redistribution; source TLS expired",
    "bottts-neutral": "terms do not address redistribution; source TLS expired",
}

# All CC0, one per slot, so a default run owes nothing to anyone.
SLOT_STYLES = {
    "A": "rings",
    "B": "shapes",
    "C": "notionists",
    "D": "pixel-art",
    "E": "lorelei",
    "F": "open-peeps",
}


def style_license(style: str) -> str:
    """Artwork license for a style, or '' if unknown.

    Unknown returns empty rather than a guess: an unrecognised style is exactly
    the case where nobody has checked what its artwork obliges.
    """
    return STYLE_LICENSES.get(style, "")


def style_allowed(style: str, allow_attribution: bool = False) -> tuple[bool, str]:
    """Gate a style before it is written into a theme."""
    if style in STYLE_BLOCKED:
        return False, "style %r is blocked: %s" % (style, STYLE_BLOCKED[style])
    lic = style_license(style)
    if not lic:
        return False, ("style %r has no verified artwork license — refusing "
                       "rather than assuming CC0" % style)
    if lic == "CC-BY-4.0" and not allow_attribution:
        return False, ("style %r is CC BY 4.0 and requires a visible credit; "
                       "opt in explicitly to use it" % style)
    return True, lic


# ---------------------------------------------------------------------------
# Identicon generation (5x5 symmetric grid, SHA-256 based)
# ---------------------------------------------------------------------------

def _grid_from_seed(seed: str) -> list[list[bool]]:
    """Return a 5x5 boolean grid from a string seed (SHA-256, vertically symmetric)."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    # We need 15 bits for unique cells (5 rows x 3 cols: 0,1,2)
    # Use the first 2 bytes (16 bits)
    bits_0 = digest[0]
    bits_1 = digest[1]
    # bits: byte0 b7..b0, byte1 b7..b2 (we use 15 bits total)
    all_bits = (bits_0 << 8) | bits_1  # 16 bits, we use low 15

    grid = [[False] * 5 for _ in range(5)]
    bit_idx = 14  # start from MSB of our 15-bit window
    for row in range(5):
        for col in range(3):  # only fill cols 0,1,2
            on = bool((all_bits >> bit_idx) & 1)
            grid[row][col] = on
            grid[row][4 - col] = on  # mirror: col 4=col0, col 3=col1
            bit_idx -= 1

    return grid


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse #rrggbb or #rgb hex to (r, g, b) ints."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) == 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 100, 100, 100  # fallback gray


def _generate_identicon_svg(seed: str, colors: list[str],
                             bg_color: str, radius_px: int) -> str:
    """Generate a 5x5 identicon SVG (50x50 viewBox, 10-unit cells)."""
    grid = _grid_from_seed(seed)
    cell = 10
    vb_size = cell * 5  # 50
    pad = 0

    # Cycle through colors for filled cells
    color_cycle = colors if colors else ["#6366f1", "#a78bfa"]
    rects: list[str] = []
    color_idx = 0

    for row in range(5):
        for col in range(5):
            x = pad + col * cell
            y = pad + row * cell
            if grid[row][col]:
                fill = color_cycle[color_idx % len(color_cycle)]
                color_idx += 1
                rx_attr = (' rx="%d"' % radius_px) if radius_px > 0 else ""
                rects.append(
                    '  <rect x="%d" y="%d" width="%d" height="%d"%s fill="%s"/>'
                    % (x, y, cell, cell, rx_attr, fill)
                )

    inner = "\n".join(rects) if rects else (
        '  <rect width="%d" height="%d" fill="%s"/>' % (vb_size, vb_size, color_cycle[0])
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        'role="img" aria-label="Avatar for {seed}">\n'
        '  <rect width="{size}" height="{size}" fill="{bg}"/>\n'
        '{inner}\n'
        '</svg>\n'
    ).format(size=vb_size, seed=seed, bg=bg_color, inner=inner)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_avatars(theme_dir: Path) -> dict:
    theme_json_path = theme_dir / "theme.json"
    theme: dict = {}
    if theme_json_path.is_file():
        try:
            theme = json.loads(theme_json_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    slug = theme.get("slug", "theme")
    slot = (theme.get("slot") or "A").upper()[:1]
    style = SLOT_STYLES.get(slot, "shapes")

    # Gate before writing anything. A blocked or unverified style must not be
    # able to reach a theme via an edited SLOT_STYLES table.
    ok, verdict = style_allowed(style)
    if not ok:
        sys.stderr.write("tf_avatars: %s — falling back to 'shapes' (CC0)\n" % verdict)
        style = "shapes"
        ok, verdict = style_allowed(style)
    style_lic = verdict if ok else "CC0-1.0"
    # notice_only (MIT) still needs its text shipped; only CC0 owes nothing.
    attribution_required = style_lic == "CC-BY-4.0"
    notice_required = style_lic in ("MIT", "OFL-1.1", "Apache-2.0")

    # Extract colors from theme
    color = theme.get("color", {})
    light = color.get("light") or {}

    def _get_hex(key: str, fallback: str) -> str:
        val = light.get(key)
        if isinstance(val, dict):
            return val.get("hex", fallback)
        if isinstance(val, str):
            return val
        return fallback

    primary_hex = _get_hex("primary", "#6366f1")
    accent_hex = _get_hex("accent", "#a78bfa")
    surface_hex = _get_hex("surface", "#f8f9fa")
    bg_hex = _get_hex("background", "#ffffff")

    # Border radius
    radius = theme.get("radius") or {}
    radius_sm = radius.get("sm") or {}
    radius_px = 0
    if isinstance(radius_sm, dict):
        radius_px = int(radius_sm.get("px", 0))
    elif isinstance(radius_sm, (int, float)):
        radius_px = int(radius_sm)

    fill_colors = [primary_hex, accent_hex, surface_hex]
    samples_dir = theme_dir / "brand" / "avatars" / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    seeds = ["user%d" % i for i in range(1, 9)]
    for seed in seeds:
        svg = _generate_identicon_svg(seed, fill_colors, bg_hex, radius_px)
        (samples_dir / ("%s.svg" % seed)).write_text(svg, encoding="utf-8")
        sys.stderr.write("tf_avatars: wrote %s.svg\n" % seed)

    # Palette hex list for config
    palette_colors = [c.lstrip("#") for c in fill_colors]

    # avatar-config.json
    config = {
        "system": "dicebear",
        "style": style,
        "version": DICEBEAR_VERSION,
        "license": style_lic,
        "license_source": "style meta.license (never package.json, which "
                          "reports MIT for every style — that is the code, "
                          "not the artwork)",
        "attribution_required": attribution_required,
        "notice_required": notice_required,
        "palette_applied": True,
        "colors": palette_colors,
        "seed_function": "stable-hash-of-user-identifier",
        "api_url": (
            "https://api.dicebear.com/%s/%s/svg"
            "?seed={seed}&backgroundColor={color}" % (DICEBEAR_VERSION, style)
        ),
    }
    config_path = theme_dir / "brand" / "avatars" / "avatar-config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    # AVATARS.md
    avatars_md = """\
# Avatars

This project uses DiceBear for user avatar generation.

## Style: {style}

Artwork license: **{style_lic}**. {license_note}

DiceBear's own code is MIT, but each style wraps a third-party artist's work
under that artist's terms — the two are different licenses. Do not read a
style's license from `package.json`, which reports `MIT` for every style
because it describes the code, not the artwork. The authority is the style's
`meta.license`, which DiceBear also embeds in every SVG response as Dublin
Core metadata (`dcterms:license`). Note that an SVG minifier will delete
`<metadata>` — capture the license before optimizing, and never with
`?format=png`, which carries no metadata at all.

## DiceBear API

```
https://api.dicebear.com/{version}/{style}/svg?seed={{userIdentifier}}&backgroundColor={colors}
```

Deterministic: the same seed always produces the same avatar.

Pinned to `{version}` on purpose. DiceBear 10.x is live with roughly 61 styles,
about 30 of them new and their artwork licenses unaudited. Four styles are
blocked outright (`avataaars`, `avataaars-neutral`, `bottts`, `bottts-neutral`):
their upstream terms never address redistribution, so bundling them into a
delivered zip cannot be justified.

## Self-hosting (Docker)

```bash
docker run -p 3000:3000 dicebear/api:{version}
```
Then use `http://localhost:3000/{version}/{style}/svg?seed={{seed}}`.

## React Native

```bash
npm install @dicebear/collection @dicebear/core
```
```ts
import {{ createAvatar }} from '@dicebear/core';
import {{ {style_camel} }} from '@dicebear/collection';
const svg = createAvatar({style_camel}, {{ seed: userId }}).toString();
```

## Alternative: boring-avatars (MIT, React)

```bash
npm install boring-avatars
```
```jsx
import Avatar from 'boring-avatars';
<Avatar name={{userId}} variant="beam" colors={{['{primary}', '{accent}', '{surface}']}} />
```

## Offline fallback

8 sample identicons (5x5 symmetric grid, SHA-256 seed) are in `brand/avatars/samples/`.
These are CC0 and can be used directly.
""".format(
        style=style,
        style_camel=style.replace("-", ""),
        colors=",".join(palette_colors),
        primary=primary_hex,
        accent=accent_hex,
        surface=surface_hex,
        version=DICEBEAR_VERSION,
        style_lic=style_lic,
        license_note=(
            "No attribution and no notice required."
            if style_lic == "CC0-1.0" else
            "No visible credit required, but the license text must ship with "
            "any redistributed copy."
            if notice_required else
            "**A visible credit is required** — it must appear in the product, "
            "not only in a file."
        ),
    )
    (theme_dir / "brand" / "avatars" / "AVATARS.md").write_text(
        avatars_md, encoding="utf-8"
    )

    return {
        "ok": True,
        "style": style,
        "license": style_lic,
        "attribution_required": attribution_required,
        "notice_required": notice_required,
        "version": DICEBEAR_VERSION,
        "samples": len(seeds),
        "offline_fallback": True,
        "dir": str(samples_dir),
    }


def main(argv: list) -> int:
    want_json = "--json" in argv

    if "--theme" not in argv:
        sys.stderr.write("usage: tf_avatars.py --theme <dir> [--json]\n")
        print(json.dumps({"ok": False, "error": "missing --theme"}))
        return 1

    theme_dir = Path(argv[argv.index("--theme") + 1])
    result = generate_avatars(theme_dir)

    if want_json:
        print(json.dumps(result))
    else:
        sys.stderr.write("tf_avatars: %d samples, style=%s\n"
                         % (result["samples"], result["style"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_avatars: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
