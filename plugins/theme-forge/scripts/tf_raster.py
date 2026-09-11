#!/usr/bin/env python3
"""tf_raster.py -- SVG-to-PNG rasterization with multi-tool fallback.

Usage:
    python3 tf_raster.py --in <svg> --out <png> --width N [--height N]
                         [--force-browser] [--json]
    python3 tf_raster.py --theme <dir> --native-set [--json]
    python3 tf_raster.py --ico --in <svg> --out <favicon.ico> [--sizes 16,32] [--json]
    python3 tf_raster.py --ico --from-pngs a.png,b.png --out <favicon.ico> [--json]
    python3 tf_raster.py --selftest

Tries rasterizers in the order detected by tf_tools.py. If none are available,
writes RASTERIZE.md in the output directory and returns ok:true with
rasterized:false -- not a fatal error.

--ico writes a real favicon.ico without ImageMagick: an ICO is a container
around image payloads rather than its own codec, and Vista+ accepts embedded
PNGs, so the packer is pure stdlib.

Python 3.9+, standard library only. Exit 0/1/2.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import tf_tools  # noqa: E402

# ---------------------------------------------------------------------------
# Native asset set: (svg_relative, png_relative, width, height_or_None)
# ---------------------------------------------------------------------------
NATIVE_SET = [
    ("brand/logo.svg",     "brand/native/logo@1x.png",     128, None),
    ("brand/logo.svg",     "brand/native/logo@2x.png",     256, None),
    ("brand/logo.svg",     "brand/native/logo@3x.png",     384, None),
    ("brand/logomark.svg", "brand/native/logomark@1x.png",  64, None),
    ("brand/logomark.svg", "brand/native/logomark@2x.png", 128, None),
    ("brand/logomark.svg", "brand/native/logomark@3x.png", 192, None),
    ("brand/pattern.svg",  "brand/native/pattern.png",     512, None),
]


# ---------------------------------------------------------------------------
# npx resolution and timeouts
# ---------------------------------------------------------------------------

def _npx() -> str:
    """Resolve npx to a real path. A bare "npx" raises FileNotFoundError from a
    Python subprocess on Windows, where the executable is npx.CMD."""
    return shutil.which("npx") or "npx"


_NPX = _npx()

# npx cold-start from a Python subprocess (no pre-loaded shell env) runs 7-9 s
# on Windows before the rasterizer even begins work; a browser screenshot needs
# more still.
_RASTER_TIMEOUT = 120
_BROWSER_TIMEOUT = 180


def _node_cli(binary: str, package: str) -> list:
    """Return the argv prefix for a node CLI tool.

    Prefers the globally-installed shim on PATH over `npx <package>`: npx adds
    roughly 20 s of resolution overhead per invocation, which the per-file
    rasterizer loop pays on every single asset.
    """
    direct = shutil.which(binary)
    if direct:
        return [direct]
    return [_NPX, "--no-install", package]


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------

def _build_cmd(rasterizer: str, svg: Path, png: Path,
               width: int, height: int | None) -> list:
    """Return the subprocess command list for the given rasterizer."""
    w = str(width)
    if rasterizer == "resvg":
        cmd = ["resvg", "--width", w]
        if height:
            cmd += ["--height", str(height)]
        cmd += [str(svg), str(png)]
    elif rasterizer == "resvg-js":
        # resvg-js-cli names these --fit-width/--fit-height; a bare --width is
        # rejected outright ("Unkonw option ==> --width").
        cmd = _node_cli("resvg-js", "@resvg/resvg-js-cli") + ["--fit-width", w]
        if height:
            cmd += ["--fit-height", str(height)]
        cmd += [str(svg), str(png)]
    elif rasterizer == "rsvg-convert":
        cmd = ["rsvg-convert", "-w", w]
        if height:
            cmd += ["-h", str(height)]
        cmd += ["-o", str(png), str(svg)]
    elif rasterizer == "magick":
        size = "%sx%s" % (w, str(height)) if height else w
        cmd = ["magick", "-background", "none", "-resize", size,
               str(svg), str(png)]
    elif rasterizer == "inkscape":
        cmd = ["inkscape",
               "--export-type=png",
               "--export-width=%s" % w,
               "--export-filename=%s" % str(png),
               str(svg)]
    elif rasterizer == "sharp-cli":
        # sharp-cli installs its shim as `sharp`, and takes dimensions as
        # positionals on its `resize` subcommand; --width/--height are not
        # recognized flags.
        cmd = _node_cli("sharp", "sharp-cli") + [
            "-i", str(svg), "-o", str(png), "resize", w]
        if height:
            cmd += [str(height)]
    else:
        return []
    return cmd


# Features no non-browser rasterizer in the ladder renders correctly. Each one
# fails *silently* -- a valid PNG comes out, just wrong -- so detect them up
# front and route to the browser rather than discovering it downstream.
#
#   var(--x)   resvg does not parse CSS custom properties at all. It does not
#              honour the var() fallback either, so an unresolved fill falls
#              back to SVG's initial paint: black for fill, none for stroke
#              (i.e. a blank render). Measured, not assumed.
#   filters    feTurbulence / feGaussianBlur and friends are unsupported or
#              approximated outside a browser engine.
_BROWSER_ONLY_FEATURES = (
    (re.compile(r"var\(\s*--"),
     "CSS custom properties (resvg renders fill as black, stroke as nothing)"),
    (re.compile(r"<(?:filter|feTurbulence|feGaussianBlur|feDropShadow|feDisplacementMap)\b"),
     "SVG filter primitives"),
)


def _browser_only_reason(svg: Path):
    """Return why this SVG needs a browser renderer, or None if any tool will do."""
    try:
        txt = svg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for pattern, reason in _BROWSER_ONLY_FEATURES:
        if pattern.search(txt):
            return reason
    return None


# A raster is a fixed-pixel artifact: it cannot respond to
# prefers-color-scheme, so the only sensible value for a custom property is the
# declared default. Baking that in lets resvg render the correct colour without
# a browser, which matters because the browser rung is both the slowest and the
# one most likely to be missing.
_VAR_DECL_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;}\"']+)")
_VAR_USE_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*?)\s*)?\)")
# Declarations inside an @media block are conditional, not defaults.
_MEDIA_BLOCK_RE = re.compile(r"@media[^{]*\{.*?\}\s*\}", re.DOTALL)


def _resolve_css_vars(text: str):
    """Substitute default custom-property values into var() uses.

    Returns the rewritten SVG, or None if nothing could be resolved. Only
    declarations outside @media blocks are treated as defaults; a var() with no
    resolvable declaration falls back to its own inline fallback if it has one.
    """
    if not _VAR_USE_RE.search(text):
        return None

    # Strip @media blocks before harvesting declarations so a dark-mode
    # override cannot be mistaken for the default.
    defaults = {}
    for name, value in _VAR_DECL_RE.findall(_MEDIA_BLOCK_RE.sub("", text)):
        defaults[name] = value.strip()

    resolved = [0]

    def repl(m):
        name, fallback = m.group(1), m.group(2)
        value = defaults.get(name) or (fallback.strip() if fallback else None)
        if not value or _VAR_USE_RE.search(value):
            return m.group(0)          # unresolvable or nested; leave alone
        resolved[0] += 1
        return value

    out = _VAR_USE_RE.sub(repl, text)
    return out if resolved[0] else None


def _viewbox_aspect(svg: Path) -> float | None:
    """Return height/width from the SVG's viewBox, or None if unreadable."""
    try:
        head = svg.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return None
    m = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', head)
    if not m:
        return None
    parts = m.group(1).replace(",", " ").split()
    if len(parts) != 4:
        return None
    try:
        vw, vh = float(parts[2]), float(parts[3])
    except ValueError:
        return None
    if vw <= 0 or vh <= 0:
        return None
    return vh / vw


def _rasterize_playwright(svg: Path, png: Path, width: int,
                           height: int | None) -> tuple[bool, str]:
    """Screenshot an SVG wrapped in HTML via Playwright npx CLI."""
    # Without a height, derive one from the viewBox so the screenshot keeps the
    # artwork's aspect ratio. A fixed fallback would pad every asset to the same
    # height — a 64px-wide logomark rendered 64x800, mostly transparency.
    if height:
        h = height
    else:
        aspect = _viewbox_aspect(svg)
        h = max(1, round(width * aspect)) if aspect else width
    # Write a temp HTML wrapper
    html_content = (
        "<!DOCTYPE html><html><head>"
        "<style>*{margin:0;padding:0}body{background:transparent;width:%dpx}"
        "svg{display:block;width:100%%;height:auto}</style></head>"
        "<body><img src='%s' width='%d' height='%d'/></body></html>"
    ) % (width, svg.as_uri(), width, h)

    tmp_html = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(html_content)
            tmp_html = Path(f.name)

        r = subprocess.run(
            [_NPX, "--no-install", "playwright", "screenshot",
             "--viewport-size", "%d,%d" % (width, h),
             tmp_html.as_uri(), str(png)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_BROWSER_TIMEOUT,
        )
        ok = r.returncode == 0 and png.is_file()
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        return ok, err
    except FileNotFoundError:
        return False, "playwright not found"
    except subprocess.TimeoutExpired:
        return False, "playwright timed out"
    except OSError as e:
        return False, str(e)
    finally:
        if tmp_html is not None:
            try:
                tmp_html.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ICO packing
# ---------------------------------------------------------------------------
#
# An .ico is a thin container, not an image codec: a 6-byte ICONDIR, one
# 16-byte ICONDIRENTRY per image, then the payloads. Windows Vista and later
# accept PNG payloads verbatim, so the PNGs the rasterizer already produces can
# be embedded without re-encoding. That keeps favicon.ico inside the stdlib-only
# rule instead of requiring ImageMagick just for this one artifact.

# ICO stores each dimension in a single byte, with 0 meaning 256.
ICO_MAX_DIM = 256

DEFAULT_ICO_SIZES = (16, 32)


def _png_ihdr(data: bytes):
    """Return (width, height) from a PNG IHDR, or None if not a PNG."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return (int.from_bytes(data[16:20], "big"),
            int.from_bytes(data[20:24], "big"))


def build_ico(payloads: list) -> bytes:
    """Pack a list of PNG byte strings into ICO container bytes.

    Entries are emitted smallest-first, which is the conventional order and the
    one picky consumers are happiest with.
    """
    if not payloads:
        raise ValueError("no PNG payloads to pack")

    images = []
    for data in payloads:
        dims = _png_ihdr(data)
        if dims is None:
            raise ValueError("payload is not a valid PNG")
        w, h = dims
        if w > ICO_MAX_DIM or h > ICO_MAX_DIM:
            raise ValueError(
                "ICO cannot represent %dx%d; maximum is %dpx per side"
                % (w, h, ICO_MAX_DIM))
        images.append((w, h, data))

    images.sort(key=lambda t: (t[0], t[1]))

    count = len(images)
    out = bytearray()
    out += (0).to_bytes(2, "little")      # reserved, must be 0
    out += (1).to_bytes(2, "little")      # resource type: 1 = icon
    out += count.to_bytes(2, "little")

    offset = 6 + 16 * count               # payloads begin after the directory
    directory = bytearray()
    for w, h, data in images:
        directory.append(0 if w == ICO_MAX_DIM else w)
        directory.append(0 if h == ICO_MAX_DIM else h)
        directory.append(0)                            # palette entries (0 = none)
        directory.append(0)                            # reserved
        directory += (1).to_bytes(2, "little")         # color planes
        directory += (32).to_bytes(2, "little")        # bits per pixel
        directory += len(data).to_bytes(4, "little")   # payload size
        directory += offset.to_bytes(4, "little")      # payload offset
        offset += len(data)

    out += directory
    for _, _, data in images:
        out += data
    return bytes(out)


def pack_ico_from_pngs(png_paths: list, out_path: Path) -> dict:
    """Pack existing PNG files into out_path. Always returns a result dict."""
    payloads = []
    used = []
    for p in png_paths:
        p = Path(p)
        if not p.is_file():
            return {"ok": False, "error": "PNG not found: %s" % p}
        payloads.append(p.read_bytes())
        used.append(str(p))
    try:
        blob = build_ico(payloads)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    sizes = sorted(_png_ihdr(d)[0] for d in payloads)
    sys.stderr.write("tf_raster: packed %s (%d entries: %s)\n"
                     % (out_path.name, len(payloads),
                        ", ".join("%dpx" % s for s in sizes)))
    return {
        "ok": True,
        "packed": True,
        "path": str(out_path),
        "entries": len(payloads),
        "sizes": sizes,
        "sources": used,
    }


def make_ico(svg: Path, out_path: Path, sizes, tools: dict) -> dict:
    """Rasterize svg at each size and pack the results into out_path.

    Returns rasterized:false (never a hard failure) when no rasterizer could
    produce the intermediate PNGs, matching rasterize_one's contract.
    """
    bad = [s for s in sizes if not (1 <= s <= ICO_MAX_DIM)]
    if bad:
        return {"ok": False,
                "error": "ICO sizes must be 1-%d; got %s" % (ICO_MAX_DIM, bad)}

    tmpdir = Path(tempfile.mkdtemp(prefix="tf_raster_ico_"))
    payloads = []
    failed = []
    try:
        for s in sorted(set(sizes)):
            png = tmpdir / ("icon-%d.png" % s)
            r = rasterize_one(svg, png, s, s, tools)
            if r.get("rasterized") and png.is_file():
                payloads.append(png.read_bytes())
            else:
                failed.append(s)

        if not payloads:
            sys.stderr.write(
                "tf_raster: no rasterizer could render %s; ICO not written\n"
                % svg.name)
            return {"ok": True, "packed": False, "rasterized": False,
                    "reason": "no rasterizer available", "failed_sizes": failed}

        try:
            blob = build_ico(payloads)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(blob)
        packed = sorted(_png_ihdr(d)[0] for d in payloads)
        sys.stderr.write("tf_raster: %s -> %s (%d entries: %s)\n"
                         % (svg.name, out_path.name, len(payloads),
                            ", ".join("%dpx" % s for s in packed)))
        return {
            "ok": True,
            "packed": True,
            "rasterized": True,
            "path": str(out_path),
            "entries": len(payloads),
            "sizes": packed,
            "failed_sizes": failed,
        }
    finally:
        # Only ever removes files this function created in its own temp dir.
        try:
            for f in tmpdir.iterdir():
                f.unlink()
            tmpdir.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# RASTERIZE.md writer
# ---------------------------------------------------------------------------

def _write_rasterize_md(out_dir: Path,
                         items: list[tuple[str, str, int, int | None]]) -> Path:
    """Write RASTERIZE.md with manual resvg commands for each item."""
    lines = [
        "# Manual rasterization steps",
        "",
        "No rasterizer was available when Theme Forge ran.",
        "Install resvg (https://github.com/RazrFalcon/resvg/releases) and run:",
        "",
    ]
    for svg, png, w, h in items:
        if h:
            lines.append("resvg --width %d --height %d %s %s" % (w, h, svg, png))
        else:
            lines.append("resvg --width %d %s %s" % (w, svg, png))
    lines += [
        "",
        "Alternative: ImageMagick",
        "",
    ]
    for svg, png, w, h in items:
        size = "%dx%d" % (w, h) if h else "%d" % w
        lines.append("magick -background none -resize %s %s %s" % (size, svg, png))
    lines.append("")
    md_path = out_dir / "RASTERIZE.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


# ---------------------------------------------------------------------------
# Core rasterization
# ---------------------------------------------------------------------------

def rasterize_one(svg: Path, png: Path, width: int, height: int | None,
                  tools: dict, force_browser: bool = False) -> dict:
    """Rasterize one SVG to PNG. Always returns ok:true.

    Thin wrapper so the temp SVG written for custom-property resolution is
    cleaned up regardless of which branch returns.
    """
    scratch: list = []
    try:
        return _rasterize_one(svg, png, width, height, tools,
                              force_browser, scratch)
    finally:
        for p in scratch:
            try:
                p.unlink()
            except OSError:
                pass


def _rasterize_one(svg: Path, png: Path, width: int, height: int | None,
                   tools: dict, force_browser: bool, scratch: list) -> dict:
    png.parent.mkdir(parents=True, exist_ok=True)

    rasterizers = tools.get("rasterizers_found", [])
    browser = tools.get("browser")

    # Some SVG features only a browser engine renders correctly, and getting
    # them wrong is silent: the fast rasterizers still emit a valid PNG.
    # Unlike an explicit --force-browser, a detected need degrades to the normal
    # ladder if the browser fails -- a wrong-coloured icon beats no icon.
    prefer_browser = False
    degraded_reason = None
    if not force_browser:
        reason = _browser_only_reason(svg)
        if reason:
            # Custom properties don't actually need a browser -- they need
            # resolving. Bake the declared defaults in and any rasterizer will
            # render the right colour. Filters genuinely need the engine.
            rewritten = None
            if "custom propert" in reason:
                try:
                    rewritten = _resolve_css_vars(
                        svg.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    rewritten = None

            if rewritten is not None:
                fd, tmp_name = tempfile.mkstemp(suffix=".svg",
                                                prefix="tf_raster_vars_")
                os.close(fd)
                tmp_svg = Path(tmp_name)
                tmp_svg.write_text(rewritten, encoding="utf-8")
                scratch.append(tmp_svg)
                sys.stderr.write(
                    "tf_raster: %s uses custom properties; resolved defaults "
                    "in-place so any rasterizer renders correct colours\n"
                    % svg.name)
                svg = tmp_svg
            elif browser == "playwright":
                sys.stderr.write("tf_raster: %s needs a browser (%s)\n"
                                 % (svg.name, reason))
                prefer_browser = True
            else:
                degraded_reason = reason
                sys.stderr.write(
                    "tf_raster: warning: %s uses %s but no browser is available; "
                    "colours/effects in %s may be wrong\n"
                    % (svg.name, reason, png.name))

    if prefer_browser:
        ok, err = _rasterize_playwright(svg, png, width, height)
        if ok:
            return {"ok": True, "rasterized": True, "tool": "playwright",
                    "path": str(png), "browser_required": True}
        sys.stderr.write(
            "tf_raster: playwright failed for %s (%s); falling back to the "
            "ladder -- output may render incorrectly\n" % (svg.name, err[:200]))
        degraded_reason = _browser_only_reason(svg)

    if force_browser:
        if browser == "playwright":
            ok, err = _rasterize_playwright(svg, png, width, height)
            if ok:
                return {"ok": True, "rasterized": True, "tool": "playwright",
                        "path": str(png)}
            sys.stderr.write("tf_raster: playwright: %s\n" % err[:300])
        # Fall through to RASTERIZE.md
    else:
        for rast in rasterizers:
            if rast == "playwright":
                continue  # playwright only via --force-browser
            cmd = _build_cmd(rast, svg, png, width, height)
            if not cmd:
                continue
            try:
                r = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=_RASTER_TIMEOUT,
                )
                if r.returncode == 0 and png.is_file():
                    sys.stderr.write("tf_raster: %s -> %s (via %s)\n"
                                     % (svg.name, png.name, rast))
                    out = {"ok": True, "rasterized": True, "tool": rast,
                           "path": str(png)}
                    if degraded_reason:
                        # Rendered, but by a tool that cannot handle this file.
                        out["render_suspect"] = degraded_reason
                    return out
                sys.stderr.write(
                    "tf_raster: %s failed (rc=%d): %s\n" % (
                        rast, r.returncode,
                        (r.stderr or b"").decode("utf-8", errors="replace")[:200])
                )
            except FileNotFoundError:
                sys.stderr.write("tf_raster: %s not on PATH\n" % rast)
            except subprocess.TimeoutExpired:
                sys.stderr.write("tf_raster: %s timed out\n" % rast)

        # Try playwright as last resort
        if browser == "playwright":
            ok, err = _rasterize_playwright(svg, png, width, height)
            if ok:
                return {"ok": True, "rasterized": True, "tool": "playwright",
                        "path": str(png)}

    # Nothing worked -- write RASTERIZE.md
    md_path = _write_rasterize_md(
        png.parent,
        [(str(svg), str(png), width, height)],
    )
    return {
        "ok": True,
        "rasterized": False,
        "manual_steps": 1,
        "rasterize_md": str(md_path),
    }


def rasterize_native_set(theme_dir: Path, tools: dict) -> dict:
    """Process the full set of native assets for a theme directory."""
    results = []
    manual_items: list[tuple[str, str, int, int | None]] = []

    # Standard set
    for rel_svg, rel_png, w, h in NATIVE_SET:
        svg_path = theme_dir / rel_svg
        png_path = theme_dir / rel_png
        if not svg_path.is_file():
            sys.stderr.write("tf_raster: skipping missing %s\n" % svg_path)
            continue
        r = rasterize_one(svg_path, png_path, w, h, tools)
        if not r.get("rasterized"):
            manual_items.append((str(svg_path), str(png_path), w, h))
        results.append({"source": rel_svg, "dest": rel_png, **r})

    # Illustrations
    illus_src = theme_dir / "brand" / "illustrations"
    illus_dst = theme_dir / "brand" / "native" / "illustrations"
    if illus_src.is_dir():
        for svg_path in sorted(illus_src.glob("*.svg")):
            png_path = illus_dst / (svg_path.stem + ".png")
            r = rasterize_one(svg_path, png_path, 800, None, tools)
            rel_svg = str(svg_path.relative_to(theme_dir)).replace("\\", "/")
            rel_png = str(png_path.relative_to(theme_dir)).replace("\\", "/")
            if not r.get("rasterized"):
                manual_items.append((str(svg_path), str(png_path), 800, None))
            results.append({"source": rel_svg, "dest": rel_png, **r})

    md_path = None
    if manual_items:
        out_dir = theme_dir / "brand" / "native"
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = _write_rasterize_md(out_dir, manual_items)

    return {
        "ok": True,
        "processed": len(results),
        "rasterized": sum(1 for r in results if r.get("rasterized")),
        "manual": len(manual_items),
        "rasterize_md": str(md_path) if md_path else None,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

_SELFTEST_SVGS = {
    # name: (svg source, requested width, expected (w, h))
    "square": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
               '<rect width="100" height="100" fill="#c02447"/></svg>', 64, (64, 64)),
    "wide":   ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 80">'
               '<rect width="320" height="80" fill="#2447c0"/></svg>', 128, (128, 32)),
}


def _png_dimensions(png: Path) -> tuple[int, int] | None:
    """Read (width, height) from a PNG IHDR, or None if not a valid PNG."""
    try:
        head = png.read_bytes()[:24]
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    w = int.from_bytes(head[16:20], "big")
    h = int.from_bytes(head[20:24], "big")
    return w, h


def _parse_ico(blob: bytes):
    """Parse ICO bytes into [(w, h, payload_is_png, payload_len)], or None.

    Deliberately re-reads the container from raw bytes rather than trusting
    build_ico's bookkeeping, so a wrong offset or size field is caught.
    """
    if len(blob) < 6:
        return None
    reserved = int.from_bytes(blob[0:2], "little")
    rtype = int.from_bytes(blob[2:4], "little")
    count = int.from_bytes(blob[4:6], "little")
    if reserved != 0 or rtype != 1 or count < 1:
        return None
    if len(blob) < 6 + 16 * count:
        return None
    entries = []
    for i in range(count):
        off = 6 + 16 * i
        w = blob[off] or ICO_MAX_DIM
        h = blob[off + 1] or ICO_MAX_DIM
        size = int.from_bytes(blob[off + 8:off + 12], "little")
        pos = int.from_bytes(blob[off + 12:off + 16], "little")
        if pos + size > len(blob):
            return None
        payload = blob[pos:pos + size]
        entries.append((w, h, payload[:8] == b"\x89PNG\r\n\x1a\n", size))
    return entries


def _dominant_opaque_color(png: Path):
    """Most common fully-opaque RGB in an 8-bit RGB/RGBA PNG, as #rrggbb."""
    import zlib
    bpp_for = {2: 3, 6: 4}
    try:
        d = png.read_bytes()
    except OSError:
        return None
    if d[:8] != b"\x89PNG\r\n\x1a\n" or d[12:16] != b"IHDR":
        return None
    w = int.from_bytes(d[16:20], "big")
    h = int.from_bytes(d[20:24], "big")
    bd, ct = d[24], d[25]
    if bd != 8 or ct not in bpp_for:
        return None
    bpp = bpp_for[ct]

    idat = b""
    i = 8
    while i < len(d):
        ln = int.from_bytes(d[i:i + 4], "big")
        if d[i + 4:i + 8] == b"IDAT":
            idat += d[i + 8:i + 8 + ln]
        i += 12 + ln
    try:
        data = zlib.decompress(idat)
    except zlib.error:
        return None

    stride = w * bpp
    prev = bytearray(stride)
    pos = 0
    counts = {}
    for _ in range(h):
        if pos >= len(data):
            break
        f = data[pos]
        pos += 1
        line = bytearray(data[pos:pos + stride])
        pos += stride
        if len(line) < stride:
            break
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        for x in range(0, stride, bpp):
            if bpp == 4 and line[x + 3] != 255:
                continue
            key = (line[x], line[x + 1], line[x + 2])
            counts[key] = counts.get(key, 0) + 1
        prev = line

    if not counts:
        return "BLANK"
    # Ignore the white page the browser wrapper paints behind the artwork.
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    for (r, g, b), _ in ranked:
        if (r, g, b) != (255, 255, 255):
            return "#%02x%02x%02x" % (r, g, b)
    return "#ffffff"


def _selftest_css_vars(tools: dict, tmpdir: Path, failures: list) -> int:
    """A var()-coloured SVG must rasterize to its declared colour.

    resvg cannot resolve custom properties and silently paints fill black /
    stroke nothing, so this asserts the browser-routing in rasterize_one
    actually kicks in. Both fill and stroke are covered: they degrade
    differently (black vs blank), so one passing does not imply the other.
    """
    checked = 0
    target = "#25170c"
    cases = {
        "fill": '<rect x="4" y="4" width="24" height="24" fill="var(--fg)"/>',
        "stroke": ('<rect x="6" y="6" width="20" height="20" fill="none" '
                   'stroke="var(--fg)" stroke-width="6"/>'),
    }
    for prop, shape in cases.items():
        svg = tmpdir / ("var-%s.svg" % prop)
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" style="--fg:%s" '
            'viewBox="0 0 32 32">'
            '<style>@media (prefers-color-scheme:dark){:root{--fg:#f79643}}</style>'
            '%s</svg>' % (target, shape), encoding="utf-8")
        png = tmpdir / ("var-%s.png" % prop)
        r = rasterize_one(svg, png, 32, 32, tools)
        checked += 1
        if not r.get("rasterized"):
            failures.append("css-var/%s: no PNG produced" % prop)
            continue
        got = _dominant_opaque_color(png)
        if got == target:
            sys.stderr.write("tf_raster selftest: css-var/%s -> %s OK (via %s)\n"
                             % (prop, got, r.get("tool")))
        elif r.get("render_suspect"):
            # No browser on this machine: flagged rather than silently wrong.
            sys.stderr.write(
                "tf_raster selftest: css-var/%s -> %s, correctly flagged "
                "render_suspect (no browser available)\n" % (prop, got))
        else:
            failures.append(
                "css-var/%s: expected %s, got %s via %s with no render_suspect flag"
                % (prop, target, got, r.get("tool")))
    return checked


def _selftest_ico(tools: dict, tmpdir: Path, failures: list) -> int:
    """Check ICO packing: structure, entry geometry, and the size guard."""
    checked = 0
    svg = tmpdir / "ico-src.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
        '<rect width="48" height="48" fill="#2447c0"/></svg>',
        encoding="utf-8")

    ico = tmpdir / "favicon.ico"
    res = make_ico(svg, ico, [16, 32], tools)
    checked += 1
    if not res.get("packed"):
        failures.append("ico/make: not packed (%s)"
                        % (res.get("error") or res.get("reason")))
    else:
        entries = _parse_ico(ico.read_bytes())
        if entries is None:
            failures.append("ico/structure: container failed to parse")
        else:
            got = sorted((w, h) for w, h, _, _ in entries)
            if got != [(16, 16), (32, 32)]:
                failures.append("ico/geometry: expected 16+32, got %s" % got)
            elif not all(is_png for _, _, is_png, _ in entries):
                failures.append("ico/payload: an entry is not PNG data")
            else:
                sys.stderr.write(
                    "tf_raster selftest: ico 16+32 -> %d entries OK\n" % len(entries))

    # Oversize must be refused, not silently truncated to a 0 dimension byte.
    checked += 1
    over = make_ico(svg, tmpdir / "over.ico", [512], tools)
    if over.get("ok") is not False:
        failures.append("ico/guard: 512px should be rejected (max %d)" % ICO_MAX_DIM)
    else:
        sys.stderr.write("tf_raster selftest: ico oversize guard OK\n")

    return checked


def selftest() -> int:
    """Rasterize known SVGs and assert the output geometry matches the request.

    Guards the failure mode that flag errors and fallback defaults produce: a
    valid PNG at the wrong size. Every rasterizer in the ladder is checked
    individually so one broken command builder can't hide behind a working
    tool later in the ladder. Also covers ICO packing.
    """
    tools = tf_tools.detect()
    found = tools.get("rasterizers_found", [])
    browser = tools.get("browser")
    if not found and not browser:
        sys.stderr.write("tf_raster selftest: no rasterizer available, nothing to test\n")
        print(json.dumps({"ok": True, "skipped": "no rasterizer"}))
        return 0

    failures = []
    checked = 0
    tmpdir = Path(tempfile.mkdtemp(prefix="tf_raster_selftest_"))
    try:
        for name, (src, width, expected) in _SELFTEST_SVGS.items():
            svg = tmpdir / ("%s.svg" % name)
            svg.write_text(src, encoding="utf-8")

            # Each ladder entry on its own, plus the browser path. "playwright"
            # can appear in both, so build an order-preserving unique list.
            candidates = list(found)
            if browser == "playwright" and "playwright" not in candidates:
                candidates.append("playwright")
            for tool in candidates:
                png = tmpdir / ("%s-%s.png" % (name, tool))
                if tool == "playwright":
                    ok, err = _rasterize_playwright(svg, png, width, None)
                else:
                    cmd = _build_cmd(tool, svg, png, width, None)
                    if not cmd:
                        continue
                    try:
                        r = subprocess.run(cmd, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           timeout=_RASTER_TIMEOUT)
                        ok = r.returncode == 0 and png.is_file()
                        err = (r.stderr or b"").decode("utf-8", errors="replace")[:200]
                    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
                        ok, err = False, str(e)
                checked += 1
                if not ok:
                    failures.append("%s/%s: did not produce a PNG (%s)" % (tool, name, err))
                    continue
                dims = _png_dimensions(png)
                if dims is None:
                    failures.append("%s/%s: output is not a valid PNG" % (tool, name))
                elif dims != expected:
                    failures.append("%s/%s: expected %dx%d, got %dx%d" % (
                        tool, name, expected[0], expected[1], dims[0], dims[1]))
                else:
                    sys.stderr.write("tf_raster selftest: %s/%s -> %dx%d OK\n"
                                     % (tool, name, dims[0], dims[1]))

        checked += _selftest_css_vars(tools, tmpdir, failures)
        checked += _selftest_ico(tools, tmpdir, failures)
    finally:
        try:
            for f in tmpdir.iterdir():
                f.unlink()
            tmpdir.rmdir()
        except OSError:
            pass

    for f in failures:
        sys.stderr.write("tf_raster selftest: FAIL %s\n" % f)
    sys.stderr.write("tf_raster selftest: %d checks, %d failures\n"
                     % (checked, len(failures)))
    print(json.dumps({"ok": not failures, "checks": checked,
                      "failures": failures}))
    return 0 if not failures else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list) -> int:
    want_json = "--json" in argv
    force_browser = "--force-browser" in argv
    no_cache = "--no-cache" in argv

    if "--selftest" in argv:
        return selftest()

    tools = tf_tools.detect(no_cache=no_cache)

    if "--ico" in argv:
        if "--out" not in argv:
            sys.stderr.write(
                "usage: tf_raster.py --ico --in <svg> --out <favicon.ico> "
                "[--sizes 16,32] [--json]\n"
                "       tf_raster.py --ico --from-pngs a.png,b.png "
                "--out <favicon.ico> [--json]\n")
            print(json.dumps({"ok": False, "error": "missing --out"}))
            return 1
        out_path = Path(argv[argv.index("--out") + 1])

        if "--from-pngs" in argv:
            raw = argv[argv.index("--from-pngs") + 1]
            pngs = [Path(p) for p in raw.split(",") if p.strip()]
            if not pngs:
                print(json.dumps({"ok": False, "error": "no PNGs given"}))
                return 1
            result = pack_ico_from_pngs(pngs, out_path)
        else:
            if "--in" not in argv:
                print(json.dumps({"ok": False,
                                  "error": "missing --in (or --from-pngs)"}))
                return 1
            svg = Path(argv[argv.index("--in") + 1])
            if not svg.is_file():
                print(json.dumps({"ok": False,
                                  "error": "input SVG not found: %s" % svg}))
                return 1
            sizes = list(DEFAULT_ICO_SIZES)
            if "--sizes" in argv:
                try:
                    sizes = [int(s) for s in
                             argv[argv.index("--sizes") + 1].split(",") if s.strip()]
                except ValueError:
                    print(json.dumps({"ok": False,
                                      "error": "--sizes must be comma-separated integers"}))
                    return 1
            result = make_ico(svg, out_path, sizes, tools)

        if want_json:
            print(json.dumps(result))
        else:
            sys.stderr.write("tf_raster: %s\n" % result)
        return 0 if result.get("ok") else 1

    if "--native-set" in argv:
        if "--theme" not in argv:
            sys.stderr.write("usage: tf_raster.py --theme <dir> --native-set [--json]\n")
            print(json.dumps({"ok": False, "error": "missing --theme"}))
            return 1
        theme_dir = Path(argv[argv.index("--theme") + 1])
        result = rasterize_native_set(theme_dir, tools)
    else:
        if "--in" not in argv or "--out" not in argv or "--width" not in argv:
            sys.stderr.write(
                "usage: tf_raster.py --in <svg> --out <png> --width N "
                "[--height N] [--force-browser] [--json]\n"
            )
            print(json.dumps({"ok": False, "error": "missing required args"}))
            return 1

        svg = Path(argv[argv.index("--in") + 1])
        png = Path(argv[argv.index("--out") + 1])
        width = int(argv[argv.index("--width") + 1])
        height = None
        if "--height" in argv:
            height = int(argv[argv.index("--height") + 1])

        if not svg.is_file():
            print(json.dumps({"ok": False,
                               "error": "input SVG not found: %s" % svg}))
            return 1

        result = rasterize_one(svg, png, width, height, tools,
                               force_browser=force_browser)

    if want_json:
        print(json.dumps(result))
    else:
        sys.stderr.write("tf_raster: %s\n" % result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_raster: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
