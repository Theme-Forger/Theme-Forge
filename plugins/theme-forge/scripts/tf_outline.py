#!/usr/bin/env python3
"""tf_outline.py -- text-to-SVG-outline generator for wordmarks.

Usage:
    python3 tf_outline.py --text <text> --font-path <ttf> --size N
                          --out <file.svg> [--json]
    python3 tf_outline.py --wordmark <theme-dir> [--json]

Path A: node + opentype.js available  -> outlined paths via JS.
Path B: pure Python struct TTF parser -> outlined paths (stdlib only).
Path C: <text> element fallback       -> RASTERIZE.md note.

Python 3.9+, standard library only. Exit 0/1/2.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# opentype.js inline Node script
# ---------------------------------------------------------------------------

_OUTLINE_MJS = """\
import {{ createRequire }} from 'module';
import fs from 'fs';
const require = createRequire(import.meta.url);
try {{
  const opentype = require('opentype.js');
  // parse(), never loadSync(): v2 deprecated loadSync into returning undefined
  // rather than throwing, so the only symptom is a TypeError one line later --
  // which this script's catch turns into a silent <text> fallback. parse() is
  // public API in both v1 and v2.
  const font = opentype.parse(fs.readFileSync(process.argv[2]));
  if (!font || typeof font.getPath !== 'function') {{
    throw new Error('opentype.parse returned no usable font');
  }}
  const path = font.getPath(process.argv[3], 0, parseInt(process.argv[4]), parseInt(process.argv[4]));
  const bbox = path.getBoundingBox();
  const d = path.toPathData(3);
  // An empty d renders as a valid but blank SVG -- fail loudly instead.
  if (!d || d.length < 2) {{
    throw new Error('empty path data for text: ' + process.argv[3]);
  }}
  // opentype.js v2 emits NaN coordinates for some glyphs (observed on Fredoka
  // and DM Serif Display). An SVG renderer aborts parsing at the bad token and
  // silently drops that glyph AND every one after it -- the file stays valid,
  // so only looking at the image catches it. Reject here so the caller falls
  // through to the pure-Python parser instead of shipping a truncated wordmark.
  if (d.indexOf('NaN') !== -1) {{
    throw new Error('path data contains NaN -- glyph outlines unusable');
  }}
  process.stdout.write(JSON.stringify({{d: d, bbox: bbox}}));
}} catch(e) {{
  process.stderr.write(e.message + '\\n');
  process.exit(1);
}}
"""


def _global_node_modules() -> list[str]:
    """Existing npm global node_modules roots, best candidate first.

    node does NOT search npm's global root on its own -- `require('opentype.js')`
    finds a globally installed package only when NODE_PATH happens to point
    there, so a globally installed library is invisible to any subprocess whose
    environment lacks the variable.

    Locating npm's binary is not enough on Windows: npm.cmd ships *inside* the
    Node installation (C:\\Program Files\\nodejs) while the global prefix
    defaults to %APPDATA%\\npm, so the npm-adjacent guess returns node's own
    bundled modules and misses every user-installed global package.
    """
    cands: list[Path] = []
    prefix = os.environ.get("npm_config_prefix")
    if prefix:
        cands += [Path(prefix) / "node_modules",
                  Path(prefix) / "lib" / "node_modules"]
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            cands.append(Path(appdata) / "npm" / "node_modules")
    else:
        cands += [Path("/usr/local/lib/node_modules"),
                  Path("/usr/lib/node_modules"),
                  Path.home() / ".npm-global" / "lib" / "node_modules"]
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm:
        bin_dir = Path(npm).resolve().parent
        cands += [bin_dir / "node_modules",
                  bin_dir.parent / "lib" / "node_modules"]
    out: list[str] = []
    for p in cands:
        s = str(p)
        if s not in out and p.is_dir():
            out.append(s)
    return out


def _node_env() -> dict:
    """Environment for node with the npm global root appended to NODE_PATH."""
    env = os.environ.copy()
    roots = _global_node_modules()
    if not roots:
        return env
    existing = env.get("NODE_PATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    for r in roots:
        if r not in parts:
            parts.append(r)
    env["NODE_PATH"] = os.pathsep.join(parts)
    return env


def _try_opentype_node(font_path: str, text: str, size: int
                        ) -> dict | None:
    """Return {d, bbox} from opentype.js, or None on failure."""
    script_content = _OUTLINE_MJS.format()  # no format vars, just clean it up
    tmp_mjs = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".mjs", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(script_content)
            tmp_mjs = Path(f.name)

        r = subprocess.run(
            ["node", str(tmp_mjs), font_path, text, str(size)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            env=_node_env(),
        )
        if r.returncode == 0 and r.stdout:
            return json.loads(r.stdout.decode("utf-8"))
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        sys.stderr.write("tf_outline: opentype.js: %s\n" % err[:300])
        return None
    except FileNotFoundError:
        sys.stderr.write("tf_outline: node not found\n")
        return None
    except subprocess.TimeoutExpired:
        sys.stderr.write("tf_outline: node script timed out\n")
        return None
    except (json.JSONDecodeError, OSError) as e:
        sys.stderr.write("tf_outline: %s\n" % e)
        return None
    finally:
        if tmp_mjs is not None:
            try:
                tmp_mjs.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Path B: Pure Python/stdlib TrueType outline extractor
# ---------------------------------------------------------------------------

def _tf_font_cache() -> Path | None:
    """$TF_HOME/fonts -- webfonts fetched for a theme's display family.

    Themes overwhelmingly pick Google Fonts, which are not installed system-wide
    on any of the three platforms below, so a system-only search finds nothing
    and the wordmark degrades to <text>. This directory sits beside current/
    rather than inside it, so a generate run's wipe does not discard fonts that
    are expensive to re-fetch.
    """
    try:
        SCRIPTS_DIR_STR = str(SCRIPTS_DIR)
        if SCRIPTS_DIR_STR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR_STR)
        import tf_paths
        return tf_paths.resolve_home() / 'fonts'
    except Exception:
        return None


def _find_system_font(family_name: str) -> str | None:
    """Search font directories for the best TTF match for *family_name*."""
    stem = family_name.lower().replace(' ', '').replace('-', '')
    dirs: list[Path] = []
    cache = _tf_font_cache()
    if cache is not None:
        dirs.append(cache)  # first: a font fetched for this exact theme wins
    if sys.platform == 'win32':
        dirs += [
            Path(os.environ.get('WINDIR', 'C:\\Windows')) / 'Fonts',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'Windows' / 'Fonts',
        ]
    elif sys.platform == 'darwin':
        dirs += [
            Path('/Library/Fonts'), Path('/System/Library/Fonts'),
            Path.home() / 'Library' / 'Fonts',
        ]
    else:
        dirs += [
            Path('/usr/share/fonts'), Path('/usr/local/share/fonts'),
            Path.home() / '.fonts',
        ]
    for d in dirs:
        if not d.is_dir():
            continue
        for ttf in sorted(d.rglob('*.ttf')):
            s = ttf.stem.lower().replace(' ', '').replace('-', '')
            if s.startswith(stem[:6]) or stem[:6] in s:
                return str(ttf)
    return None


def _cmap4(data: bytes, off: int) -> dict[int, int]:
    """Parse a cmap format-4 subtable at *off*. Returns {char_code: glyph_id}."""
    seg_count = struct.unpack_from('>H', data, off + 6)[0] // 2
    base = off + 14
    ends   = struct.unpack_from('>%dH' % seg_count, data, base)
    base  += seg_count * 2 + 2
    starts = struct.unpack_from('>%dH' % seg_count, data, base)
    base  += seg_count * 2
    deltas = struct.unpack_from('>%dh' % seg_count, data, base)
    iro_base = base + seg_count * 2
    iros   = struct.unpack_from('>%dH' % seg_count, data, iro_base)

    result: dict[int, int] = {}
    for i in range(seg_count):
        s, e, d, iro = starts[i], ends[i], deltas[i], iros[i]
        if s == 0xFFFF:
            break
        for code in range(s, e + 1):
            if iro == 0:
                gid = (code + d) & 0xFFFF
            else:
                idx = iro_base + i * 2 + iro + (code - s) * 2
                if idx + 2 > len(data):
                    continue
                gid = struct.unpack_from('>H', data, idx)[0]
                if gid:
                    gid = (gid + d) & 0xFFFF
            if gid:
                result[code] = gid
    return result


def _contour_to_svg(pts: list[tuple[float, float, bool]]) -> str:
    """Convert a list of (x, y, on_curve) TrueType points to an SVG path fragment."""
    n = len(pts)
    if n < 2:
        return ''

    # Rotate so contour starts at first on-curve point; if all off-curve, inject midpoint.
    start = next((j for j in range(n) if pts[j][2]), None)
    if start is None:
        lx = (pts[0][0] + pts[-1][0]) / 2
        ly = (pts[0][1] + pts[-1][1]) / 2
        pts = [(lx, ly, True)] + list(pts)
        n += 1
        start = 0
    pts = pts[start:] + pts[:start]

    cmds = ['M%.2f %.2f' % (pts[0][0], pts[0][1])]
    i = 1
    while i < n:
        x, y, on = pts[i % n]
        if on:
            cmds.append('L%.2f %.2f' % (x, y))
            i += 1
        else:
            cx, cy = x, y
            nxt = pts[(i + 1) % n]
            if nxt[2]:
                cmds.append('Q%.2f %.2f %.2f %.2f' % (cx, cy, nxt[0], nxt[1]))
                i += 2
            else:
                # Implied on-curve midpoint between two consecutive off-curve points
                ex = (cx + nxt[0]) / 2
                ey = (cy + nxt[1]) / 2
                cmds.append('Q%.2f %.2f %.2f %.2f' % (cx, cy, ex, ey))
                i += 1
    cmds.append('Z')
    return ' '.join(cmds)


def _composite_paths(data: bytes, goff: int, scale: float, tx: float,
                     asc: float, resolve, depth: int) -> str:
    """Expand a composite glyph into its component outlines.

    Only the translation form (ARGS_ARE_XY_VALUES) is honoured. Any scale or
    2x2 transform payload is stepped over rather than applied: in text faces
    components are near-always pure offsets, and applying half an affine would
    distort the glyph more visibly than ignoring it.
    """
    parts: list[str] = []
    off = goff + 10
    for _ in range(16):  # component cap — malformed fonts must not spin here
        if off + 4 > len(data):
            break
        flags, gid = struct.unpack_from('>HH', data, off)
        off += 4
        if flags & 0x0001:  # ARG_1_AND_2_ARE_WORDS
            if off + 4 > len(data):
                break
            a1, a2 = struct.unpack_from('>hh', data, off)
            off += 4
        else:
            if off + 2 > len(data):
                break
            a1, a2 = struct.unpack_from('>bb', data, off)
            off += 2
        if flags & 0x0008:      # WE_HAVE_A_SCALE
            off += 2
        elif flags & 0x0040:    # WE_HAVE_AN_X_AND_Y_SCALE
            off += 4
        elif flags & 0x0080:    # WE_HAVE_A_TWO_BY_TWO
            off += 8
        # Without ARGS_ARE_XY_VALUES the args are point indices to align, which
        # needs the parent's resolved points; treat as no offset.
        dx, dy = (a1, a2) if (flags & 0x0002) else (0, 0)
        sub = resolve(gid)
        if sub is not None:
            frag = _glyph_paths(data, sub, scale,
                                tx + dx * scale, asc - dy * scale,
                                resolve, depth + 1)
            if frag:
                parts.append(frag)
        if not (flags & 0x0020):  # MORE_COMPONENTS
            break
    return ' '.join(parts)


def _glyph_paths(data: bytes, goff: int, scale: float, tx: float, asc: float,
                 resolve=None, depth: int = 0) -> str:
    """Return SVG path data for one TrueType glyph at *goff*."""
    if goff + 10 > len(data):
        return ''
    num_contours = struct.unpack_from('>h', data, goff)[0]
    if num_contours < 0:
        # Composite glyph. 'i' and 'j' (dotless base + separate dot) and every
        # accented letter are built this way, so returning '' here silently
        # drops the character from the wordmark -- a valid SVG missing a letter.
        if resolve is None or depth >= 5:
            return ''
        return _composite_paths(data, goff, scale, tx, asc, resolve, depth)
    if num_contours == 0:
        return ''  # genuinely empty glyph (space)

    end_pts = list(struct.unpack_from('>%dH' % num_contours, data, goff + 10))
    num_pts = end_pts[-1] + 1

    inst_len = struct.unpack_from('>H', data, goff + 10 + num_contours * 2)[0]
    fi = goff + 10 + num_contours * 2 + 2 + inst_len

    # Flags (run-length encoded)
    flags: list[int] = []
    while len(flags) < num_pts:
        if fi >= len(data):
            return ''
        f = data[fi]; fi += 1
        flags.append(f)
        if f & 0x08:
            rpt = data[fi]; fi += 1
            flags.extend([f] * rpt)

    # x coords
    xs: list[int] = []
    cur = 0
    for f in flags:
        if f & 0x02:
            dx = data[fi]; fi += 1
            cur += dx if (f & 0x10) else -dx
        elif not (f & 0x10):
            cur += struct.unpack_from('>h', data, fi)[0]; fi += 2
        xs.append(cur)

    # y coords
    ys: list[int] = []
    cur = 0
    for f in flags:
        if f & 0x04:
            dy = data[fi]; fi += 1
            cur += dy if (f & 0x20) else -dy
        elif not (f & 0x20):
            cur += struct.unpack_from('>h', data, fi)[0]; fi += 2
        ys.append(cur)

    on = [bool(f & 0x01) for f in flags]
    parts: list[str] = []
    sp = 0
    for ep in end_pts:
        idxs = list(range(sp, ep + 1))
        pts = [(tx + xs[i] * scale, asc - ys[i] * scale, on[i]) for i in idxs]
        frag = _contour_to_svg(pts)
        if frag:
            parts.append(frag)
        sp = ep + 1
    return ' '.join(parts)


def _try_python_ttf(font_path: str, text: str, size: int) -> dict | None:
    """Render *text* from a TrueType font file to SVG path data (stdlib only)."""
    if not font_path or not Path(font_path).is_file():
        return None
    try:
        raw = Path(font_path).read_bytes()
    except OSError:
        return None

    try:
        sfv = struct.unpack_from('>I', raw, 0)[0]
        if sfv not in (0x00010000, 0x74727565):  # TrueType signatures
            return None
        num_tables = struct.unpack_from('>H', raw, 4)[0]
        tables: dict[str, tuple[int, int]] = {}
        for i in range(num_tables):
            o = 12 + i * 16
            tag = raw[o:o + 4].decode('ascii', errors='replace')
            tbl_off, tbl_len = struct.unpack_from('>II', raw, o + 8)
            tables[tag] = (tbl_off, tbl_len)

        for req in ('cmap', 'head', 'loca', 'glyf', 'hmtx', 'hhea', 'maxp'):
            if req not in tables:
                return None

        upm  = struct.unpack_from('>H', raw, tables['head'][0] + 18)[0]
        iloc = struct.unpack_from('>h', raw, tables['head'][0] + 50)[0]
        scale = size / upm

        nhm   = struct.unpack_from('>H', raw, tables['hhea'][0] + 34)[0]
        hmtx0 = tables['hmtx'][0]

        def adv(gid: int) -> int:
            g = min(gid, nhm - 1)
            return struct.unpack_from('>H', raw, hmtx0 + g * 4)[0]

        # Find best cmap subtable (prefer Windows Unicode)
        cmap0 = tables['cmap'][0]
        nsub  = struct.unpack_from('>H', raw, cmap0 + 2)[0]
        char_map: dict[int, int] = {}
        for pref in ((3, 1), (3, 10), (0, 3), (0, 4)):
            for i in range(nsub):
                so = cmap0 + 4 + i * 8
                pid, eid, soff = struct.unpack_from('>HHI', raw, so)
                if (pid, eid) == pref:
                    to = cmap0 + soff
                    if struct.unpack_from('>H', raw, to)[0] == 4:
                        char_map = _cmap4(raw, to)
                        break
            if char_map:
                break
        if not char_map:
            return None

        loca0 = tables['loca'][0]
        glyf0 = tables['glyf'][0]

        def glyph_off(gid: int) -> int:
            if iloc == 0:
                return struct.unpack_from('>H', raw, loca0 + gid * 2)[0] * 2
            return struct.unpack_from('>I', raw, loca0 + gid * 4)[0]

        def resolve(gid: int):
            """Absolute glyf offset for *gid*, or None when the glyph is empty.

            loca[gid] == loca[gid+1] means no outline; without this check the
            offset would land on the *next* glyph's data and draw the wrong
            shape into a composite.
            """
            try:
                start, end = glyph_off(gid), glyph_off(gid + 1)
            except Exception:
                return None
            return glyf0 + start if end > start else None

        paths: list[str] = []
        cx = 0.0
        for ch in text:
            if ch == ' ':
                cx += adv(char_map.get(32, 0)) * scale if 32 in char_map else size * 0.28
                continue
            gid = char_map.get(ord(ch))
            if gid is None:
                cx += size * 0.55
                continue
            go = glyf0 + glyph_off(gid)
            p = _glyph_paths(raw, go, scale, cx, size, resolve)
            if p:
                paths.append(p)
            cx += adv(gid) * scale

        if not paths:
            return None
        pad = size * 0.08
        return {
            'd': ' '.join(paths),
            'bbox': {'x1': -pad, 'y1': -pad, 'x2': cx + pad, 'y2': size * 1.2 + pad},
        }
    except Exception as exc:
        sys.stderr.write('tf_outline: python-ttf: %s\n' % exc)
        return None


# ---------------------------------------------------------------------------
# SVG builders
# ---------------------------------------------------------------------------

def _svg_from_path(d: str, bbox: dict, text: str) -> str:
    """Build an SVG from outlined path data."""
    x1 = bbox.get("x1", 0)
    y1 = bbox.get("y1", 0)
    x2 = bbox.get("x2", 100)
    y2 = bbox.get("y2", 50)
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    pad = max(4.0, h * 0.1)
    vb_x = x1 - pad
    vb_y = y1 - pad
    vb_w = w + pad * 2
    vb_h = h + pad * 2
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="%.3f %.3f %.3f %.3f" '
        'width="%.0f" height="%.0f" '
        'role="img" aria-label="%s">\n'
        '  <path d="%s" fill="currentColor"/>\n'
        '</svg>\n'
    ) % (vb_x, vb_y, vb_w, vb_h, vb_w, vb_h, text.replace('"', "&quot;"), d)


def _svg_text_fallback(text: str, size: int, font_path: str) -> str:
    """Build an SVG using a <text> element (no outlining)."""
    family = Path(font_path).stem.split("-")[0] if font_path else "sans-serif"
    w = max(100, len(text) * size * 0.65 + 40)
    h = size * 1.6
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 %.0f %.0f" width="%.0f" height="%.0f" '
        'role="img" aria-label="%s">\n'
        '  <!-- NOT OUTLINED: opentype.js was not available. -->\n'
        '  <text x="%.0f" y="%.0f" '
        'font-family="%s, sans-serif" font-size="%d" '
        'fill="currentColor">%s</text>\n'
        '</svg>\n'
    ) % (w, h, w, h, text.replace('"', "&quot;"),
         20, size * 1.2, family, size, text)


def _append_rasterize_md(theme_dir: Path, font_path: str) -> None:
    """Add a note to RASTERIZE.md about wordmark outlining."""
    md_path = theme_dir / "RASTERIZE.md"
    note = (
        "\n## Wordmark outlining\n\n"
        "The wordmark SVG uses a `<text>` element and must be outlined before shipping.\n\n"
        "**Option A — Python (no Node required):** download the TTF to the theme folder,\n"
        "then run:\n\n"
        "    python plugins/theme-forge/scripts/tf_outline.py \\\n"
        "        --wordmark <theme-dir> --json\n\n"
        "tf_outline.py will find the TTF automatically once it is present.\n\n"
        "**Option B — Node + opentype.js:**\n\n"
        "    npx opentype.js-cli outline --font %s --text 'Your Brand' "
        "--size 72 --output brand/wordmark-outlined.svg\n\n"
        "**Option C:** open `brand/wordmark.svg` in Figma/Illustrator → Text → Create Outlines.\n"
    ) % (font_path or '<path/to/font.ttf>')
    if md_path.is_file():
        existing = md_path.read_text(encoding="utf-8")
        if "Wordmark outlining" not in existing:
            md_path.write_text(existing + note, encoding="utf-8")
    else:
        md_path.write_text("# Manual steps\n" + note, encoding="utf-8")


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def _usable_path(d: str | None) -> bool:
    """Reject path data an SVG renderer cannot consume in full.

    A NaN/Infinity token does not make the file invalid -- the parser simply
    abandons the rest of the path at that point, dropping that glyph and every
    glyph after it while leaving a well-formed SVG behind. That failure is
    invisible to any structural check and only shows up in the rendered image,
    so it has to be caught here.
    """
    if not d or len(d) < 2:
        return False
    low = d.lower()
    return "nan" not in low and "inf" not in low


def generate_outline(text: str, font_path: str, size: int, out_path: Path,
                     theme_dir: Path | None = None,
                     font_family: str = '') -> dict:
    """Generate a wordmark SVG. Always returns ok:true."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve the font binary BEFORE choosing a parser. Discovery and parsing are
    # separate concerns: opentype.js is the higher-fidelity path (CFF/OTF outlines,
    # full cmap) and must get first refusal on every candidate the Python parser
    # would accept -- not only on an explicit --font-path. Searching system fonts
    # inside Path B alone meant a family found by name could only ever be parsed by
    # the weaker fallback.
    ttf_candidates = [font_path] if font_path else []
    if font_family:
        found = _find_system_font(font_family)
        if found and found not in ttf_candidates:
            ttf_candidates.append(found)

    # Path A: node + opentype.js
    for candidate in ttf_candidates:
        result = _try_opentype_node(candidate, text, size)
        if result and _usable_path(result.get("d")):
            svg = _svg_from_path(result["d"], result.get("bbox", {}), text)
            out_path.write_text(svg, encoding="utf-8")
            sys.stderr.write("tf_outline: outlined via opentype.js (%s) -> %s\n"
                             % (Path(candidate).name, out_path))
            return {"ok": True, "outlined": True, "method": "opentype.js",
                    "font_used": candidate, "svg": str(out_path)}

    # Path B: pure Python struct TTF parser, same candidates.
    for candidate in ttf_candidates:
        result = _try_python_ttf(candidate, text, size)
        if result and _usable_path(result.get("d")):
            svg = _svg_from_path(result["d"], result.get("bbox", {}), text)
            out_path.write_text(svg, encoding="utf-8")
            sys.stderr.write("tf_outline: outlined via python-ttf (%s) -> %s\n"
                             % (Path(candidate).name, out_path))
            return {"ok": True, "outlined": True, "method": "python-ttf",
                    "font_used": candidate, "svg": str(out_path)}

    # Path C: <text> fallback
    sys.stderr.write("tf_outline: falling back to <text> element\n")
    svg = _svg_text_fallback(text, size, font_path or font_family)
    out_path.write_text(svg, encoding="utf-8")

    td = theme_dir or out_path.parent
    _append_rasterize_md(td, font_path or font_family)

    return {
        "ok": True,
        "outlined": False,
        "reason": "no TTF available for python-ttf (node also unavailable)",
        "svg": str(out_path),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list) -> int:
    want_json = "--json" in argv

    if "--wordmark" in argv:
        theme_dir = Path(argv[argv.index("--wordmark") + 1])
        theme_json_path = theme_dir / "theme.json"
        if not theme_json_path.is_file():
            print(json.dumps({"ok": False, "error": "no theme.json in %s" % theme_dir}))
            return 1
        theme = json.loads(theme_json_path.read_text(encoding="utf-8"))

        # The wordmark must say the actual product's name (e.g. "Codeway"), never
        # this theme's own internal slot/codename (e.g. "Steady Signal") -- the two
        # are unrelated and theme["name"] is Theme Forge's bookkeeping label, not
        # brand copy. Read the real product name from the brief; theme["name"] is
        # only a last-resort fallback for standalone invocations with no brief.
        name = theme.get("name", "Brand")
        try:
            SCRIPTS_DIR_STR = str(SCRIPTS_DIR)
            if SCRIPTS_DIR_STR not in sys.path:
                sys.path.insert(0, SCRIPTS_DIR_STR)
            import tf_paths
            paths = tf_paths.resolve(create=False)
            brief = json.loads(paths.brief_product_json.read_text(encoding="utf-8"))
            name = brief.get("name") or name
        except Exception:
            pass  # standalone theme dir with no brief -- theme["name"] fallback stands

        typo = theme.get("typography", {})
        display = typo.get("display", {})
        source = display.get("source_file") or display.get("file") or ""
        family = display.get("family", "")
        size = 72

        # Write to wordmark-outlined.svg, never overwrite the original wordmark.svg
        # theme-designer already drew bespoke -- tf_gallery.py's brand_panel_html()
        # already prefers wordmark-outlined.svg and falls back to wordmark.svg, so
        # this is the file it was always meant to produce.
        out_path = theme_dir / "brand" / "wordmark-outlined.svg"
        result = generate_outline(name, source, size, out_path,
                                  theme_dir=theme_dir, font_family=family)
    else:
        missing = [f for f in ("--text", "--font-path", "--size", "--out")
                   if f not in argv]
        if missing:
            sys.stderr.write(
                "usage: tf_outline.py --text <t> --font-path <ttf> "
                "--size N --out <svg> [--json]\n"
            )
            print(json.dumps({"ok": False, "error": "missing: %s" % missing}))
            return 1

        text = argv[argv.index("--text") + 1]
        font_path = argv[argv.index("--font-path") + 1]
        size = int(argv[argv.index("--size") + 1])
        out_path = Path(argv[argv.index("--out") + 1])
        theme_dir = out_path.parent

        result = generate_outline(text, font_path, size, out_path,
                                  theme_dir=theme_dir, font_family='')

    if want_json:
        print(json.dumps(result))
    else:
        sys.stderr.write("tf_outline: %s\n" % result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_outline: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
