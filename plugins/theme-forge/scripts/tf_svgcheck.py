#!/usr/bin/env python3
"""tf_svgcheck.py -- SVG validation for Theme Forge assets.

Usage:
    python3 tf_svgcheck.py <file.svg> [--target native] [--json]

Checks: viewBox, duplicate IDs, scripts, xmlns, file size, geometry bounds,
stroke width, legibility, and (with --target native) native-SVG compatibility.

Exit 0 always -- rejections and warnings are informational, not build failures.
Exit 1 for structural errors (malformed XML, missing xmlns, no valid viewBox).

Python 3.9+, standard library only.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"

SHAPE_TAGS = frozenset(
    {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"}
)

# All known fe* filter primitive names (lowercase)
_FE_NAMES = frozenset({
    "feblend", "fecolormatrix", "fecomponenttransfer",
    "fecomposite", "feconvolvematrix", "fediffuselighting",
    "fedisplacementmap", "fedropshadow", "feflood", "fefunca",
    "fefuncb", "fefuncg", "fefuncr", "fegaussianblur", "feimage",
    "femerge", "femergenode", "femorphology", "feoffset",
    "fespecularlighting", "fetile", "feturbulence",
})

ANIMATE_TAGS = frozenset({"animate", "animatetransform", "animatemotion", "set"})


# ---------------------------------------------------------------------------
# Tag helpers
# ---------------------------------------------------------------------------

def _local(tag: str) -> str:
    """Strip XML namespace from a tag."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _local_lower(tag: str) -> str:
    return _local(tag).lower()


# ---------------------------------------------------------------------------
# Minimal path bounding-box parser (conservative overestimate)
# ---------------------------------------------------------------------------

def _tokenize_path(d: str) -> list[tuple[str, list[float]]]:
    """Tokenize SVG path data into list of (command_letter, [floats])."""
    tokens = re.findall(
        r"[MmZzLlHhVvCcSsQqTtAa]"
        r"|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?",
        d,
    )
    result: list[tuple[str, list[float]]] = []
    cur_cmd: str | None = None
    cur_nums: list[float] = []
    for t in tokens:
        if t.isalpha():
            if cur_cmd is not None:
                result.append((cur_cmd, cur_nums))
            cur_cmd = t
            cur_nums = []
        else:
            try:
                cur_nums.append(float(t))
            except ValueError:
                pass
    if cur_cmd is not None:
        result.append((cur_cmd, cur_nums))
    return result


def _path_bbox(d: str) -> tuple[float, float, float, float] | None:
    """Return (min_x, min_y, max_x, max_y) for path data, or None.

    Uses control-point overestimate: all control points are treated as
    bounding-box candidates. This may overestimate but never misses actual
    extents (Bezier curves are contained within their convex hull).
    """
    try:
        tokens = _tokenize_path(d)
    except Exception:
        return None
    if not tokens:
        return None

    pts: list[tuple[float, float]] = []
    cx = cy = 0.0
    sx = sy = 0.0  # path start for Z

    def add(x: float, y: float) -> None:
        pts.append((x, y))

    def a(dx: float, dy: float, rel: bool) -> tuple[float, float]:
        return (cx + dx, cy + dy) if rel else (dx, dy)

    for cmd, nums in tokens:
        up = cmd.upper()
        rel = cmd.islower()

        if up == "M":
            for i in range(0, max(1, len(nums) - 1), 2):
                if i + 1 >= len(nums):
                    break
                ax, ay = a(nums[i], nums[i + 1], rel)
                add(ax, ay)
                if i == 0:
                    sx, sy = ax, ay
                cx, cy = ax, ay

        elif up == "Z":
            cx, cy = sx, sy

        elif up == "L":
            for i in range(0, len(nums) - 1, 2):
                ax, ay = a(nums[i], nums[i + 1], rel)
                add(ax, ay)
                cx, cy = ax, ay

        elif up == "H":
            for x in nums:
                ax = cx + x if rel else x
                add(ax, cy)
                cx = ax

        elif up == "V":
            for y in nums:
                ay = cy + y if rel else y
                add(cx, ay)
                cy = ay

        elif up == "C":
            i = 0
            while i + 5 < len(nums):
                for j in range(3):
                    ax, ay = a(nums[i + j * 2], nums[i + j * 2 + 1], rel)
                    add(ax, ay)
                cx, cy = a(nums[i + 4], nums[i + 5], rel)
                i += 6

        elif up == "S":
            i = 0
            while i + 3 < len(nums):
                for j in range(2):
                    ax, ay = a(nums[i + j * 2], nums[i + j * 2 + 1], rel)
                    add(ax, ay)
                cx, cy = a(nums[i + 2], nums[i + 3], rel)
                i += 4

        elif up == "Q":
            i = 0
            while i + 3 < len(nums):
                for j in range(2):
                    ax, ay = a(nums[i + j * 2], nums[i + j * 2 + 1], rel)
                    add(ax, ay)
                cx, cy = a(nums[i + 2], nums[i + 3], rel)
                i += 4

        elif up == "T":
            for i in range(0, len(nums) - 1, 2):
                ax, ay = a(nums[i], nums[i + 1], rel)
                add(ax, ay)
                cx, cy = ax, ay

        elif up == "A":
            # arc: rx ry x-rotation large-arc-flag sweep-flag x y
            i = 0
            while i + 6 < len(nums):
                rx = abs(nums[i])
                ry = abs(nums[i + 1])
                ex, ey = a(nums[i + 5], nums[i + 6], rel)
                mx = (cx + ex) / 2
                my = (cy + ey) / 2
                add(ex, ey)
                # 4 cardinal approximations from the arc midpoint
                add(mx + rx, my)
                add(mx - rx, my)
                add(mx, my + ry)
                add(mx, my - ry)
                cx, cy = ex, ey
                i += 7

    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Primitive geometry bounds checker
# ---------------------------------------------------------------------------

def _primitive_out_of_bounds(elem, vb_x: float, vb_y: float,
                              vb_w: float, vb_h: float) -> list[str]:
    """Return a list of warning messages for out-of-bounds primitive geometry."""
    tag = _local(elem.tag)
    msgs: list[str] = []
    tol = 0.5

    def oob(x: float, y: float) -> bool:
        return (x < vb_x - tol or x > vb_x + vb_w + tol or
                y < vb_y - tol or y > vb_y + vb_h + tol)

    try:
        if tag == "rect":
            x = float(elem.get("x", 0))
            y = float(elem.get("y", 0))
            w = float(elem.get("width", 0))
            h = float(elem.get("height", 0))
            if oob(x, y) or oob(x + w, y + h):
                msgs.append("rect at (%.1f,%.1f) size %.1fx%.1f extends outside viewBox"
                            % (x, y, w, h))
        elif tag == "circle":
            cx = float(elem.get("cx", 0))
            cy = float(elem.get("cy", 0))
            r = float(elem.get("r", 0))
            if oob(cx - r, cy - r) or oob(cx + r, cy + r):
                msgs.append("circle at (%.1f,%.1f) r=%.1f extends outside viewBox"
                            % (cx, cy, r))
        elif tag == "ellipse":
            cx = float(elem.get("cx", 0))
            cy = float(elem.get("cy", 0))
            rx = float(elem.get("rx", 0))
            ry = float(elem.get("ry", 0))
            if oob(cx - rx, cy - ry) or oob(cx + rx, cy + ry):
                msgs.append("ellipse at (%.1f,%.1f) extends outside viewBox" % (cx, cy))
        elif tag == "line":
            x1 = float(elem.get("x1", 0))
            y1 = float(elem.get("y1", 0))
            x2 = float(elem.get("x2", 0))
            y2 = float(elem.get("y2", 0))
            if oob(x1, y1) or oob(x2, y2):
                msgs.append("line from (%.1f,%.1f) to (%.1f,%.1f) extends outside viewBox"
                            % (x1, y1, x2, y2))
        elif tag in ("polygon", "polyline"):
            pts_str = elem.get("points", "")
            raw = [float(x) for x in
                   re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)", pts_str)]
            for i in range(0, len(raw) - 1, 2):
                if oob(raw[i], raw[i + 1]):
                    msgs.append("%s point (%.1f,%.1f) extends outside viewBox"
                                % (tag, raw[i], raw[i + 1]))
                    break  # one warning per element is enough
    except (ValueError, TypeError):
        pass
    return msgs


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

def check_svg(file_path: Path, target_native: bool = False) -> dict:
    """Run all checks and return a result dict."""
    errors: list[dict] = []
    warnings: list[dict] = []
    rejections: list[dict] = []
    checks_done = 0

    # Parse XML
    checks_done += 1
    try:
        tree = ET.parse(str(file_path))
    except ET.ParseError as exc:
        return {
            "ok": False, "file": file_path.name, "checks": checks_done,
            "errors": [{"check": "xml-parse", "msg": str(exc)}],
            "warnings": [], "rejections": [], "needs_native_fork": False,
        }
    except OSError as exc:
        return {
            "ok": False, "file": file_path.name, "checks": checks_done,
            "errors": [{"check": "file-read", "msg": str(exc)}],
            "warnings": [], "rejections": [], "needs_native_fork": False,
        }

    root = tree.getroot()

    # Check: xmlns declared on root
    checks_done += 1
    root_ns_ok = (
        root.tag == ("{%s}svg" % SVG_NS)
        or root.get("xmlns") == SVG_NS
    )
    if not root_ns_ok:
        errors.append({"check": "xmlns",
                        "msg": "xmlns='http://www.w3.org/2000/svg' not declared on root"})

    # Check: viewBox present and well-formed
    checks_done += 1
    vb_str = root.get("viewBox", "")
    vb_x = vb_y = vb_w = vb_h = 0.0
    vb_valid = False
    if vb_str:
        try:
            parts = re.split(r"[\s,]+", vb_str.strip())
            nums = [float(p) for p in parts if p]
            if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
                vb_x, vb_y, vb_w, vb_h = nums
                vb_valid = True
            else:
                errors.append({"check": "viewBox",
                                "msg": "viewBox not valid (need 4 numbers, w>0, h>0): %r" % vb_str})
        except ValueError:
            errors.append({"check": "viewBox",
                            "msg": "viewBox unparseable: %r" % vb_str})
    else:
        errors.append({"check": "viewBox", "msg": "viewBox attribute missing"})

    # Check: no duplicate IDs
    checks_done += 1
    id_counts: dict[str, int] = {}
    for elem in tree.iter():
        eid = elem.get("id")
        if eid:
            id_counts[eid] = id_counts.get(eid, 0) + 1
    for eid, count in id_counts.items():
        if count > 1:
            errors.append({"check": "duplicate-id",
                            "msg": "duplicate id %r appears %d times" % (eid, count)})

    # Check: no <script>
    checks_done += 1
    for elem in tree.iter():
        if _local_lower(elem.tag) == "script":
            errors.append({"check": "no-script", "msg": "<script> element found"})

    # Check: no opaque background rect (logo/mark must be transparent)
    checks_done += 1
    _transparent_fills = {"none", "transparent", ""}
    root_fill = (root.get("fill") or "").strip().lower()
    if root_fill and root_fill not in _transparent_fills:
        rejections.append({"check": "opaque-bg",
                            "msg": "root <svg fill='%s'> is opaque — logo must be transparent" % root_fill})
    if vb_valid:
        for elem in tree.iter():
            if _local_lower(elem.tag) == "rect":
                fill_val = (elem.get("fill") or "").strip().lower()
                if fill_val and fill_val not in _transparent_fills:
                    try:
                        rx = float(elem.get("x", 0)); ry = float(elem.get("y", 0))
                        rw = float(elem.get("width", 0)); rh = float(elem.get("height", 0))
                        covers_x = rx <= vb_x and (rx + rw) >= (vb_x + vb_w * 0.8)
                        covers_y = ry <= vb_y and (ry + rh) >= (vb_y + vb_h * 0.8)
                        if covers_x and covers_y:
                            rejections.append({"check": "opaque-bg",
                                               "msg": "<rect fill='%s'> covers ≥80%% of viewBox — remove opaque background rect" % fill_val})
                    except (ValueError, TypeError):
                        pass

    # Check: file size < 100 KB
    checks_done += 1
    file_size = file_path.stat().st_size
    if file_size > 100 * 1024:
        warnings.append({"check": "file-size",
                          "msg": "file size %d bytes exceeds 100 KB" % file_size})

    # Check: all geometry inside viewBox
    checks_done += 1
    if vb_valid:
        for elem in tree.iter():
            tag = _local(elem.tag)
            if tag == "path":
                d = elem.get("d", "")
                if d:
                    bbox = _path_bbox(d)
                    if bbox is not None:
                        px1, py1, px2, py2 = bbox
                        if (px1 < vb_x - 1 or px2 > vb_x + vb_w + 1
                                or py1 < vb_y - 1 or py2 > vb_y + vb_h + 1):
                            warnings.append({
                                "check": "geometry-bounds",
                                "msg": (
                                    "path bbox (%.1f,%.1f)..(%.1f,%.1f) extends outside "
                                    "viewBox (%.1f,%.1f)..(%.1f,%.1f)"
                                ) % (px1, py1, px2, py2,
                                     vb_x, vb_y, vb_x + vb_w, vb_y + vb_h),
                            })
            elif tag in SHAPE_TAGS:
                for msg in _primitive_out_of_bounds(elem, vb_x, vb_y, vb_w, vb_h):
                    warnings.append({"check": "geometry-bounds", "msg": msg})

    # Check: minimum stroke-width >= viewBox_width / 16
    checks_done += 1
    if vb_valid and vb_w > 0:
        min_sw = vb_w / 16
        for elem in tree.iter():
            sw_str = elem.get("stroke-width")
            if sw_str is not None:
                try:
                    sw = float(sw_str)
                    stroke = elem.get("stroke", "")
                    if sw > 0 and sw < min_sw and stroke and stroke != "none":
                        warnings.append({
                            "check": "stroke-width",
                            "msg": "stroke-width %.2f < viewBox_width/16 (%.2f); "
                                   "will vanish at small render sizes" % (sw, min_sw),
                        })
                except ValueError:
                    pass

    # Check: legibility for small viewBoxes (logomarks)
    checks_done += 1
    if vb_valid and vb_w > 0 and vb_h > 0 and (vb_w * vb_h) < 100 * 100:
        top_shapes = [e for e in root if _local(e.tag) in SHAPE_TAGS]
        if len(top_shapes) > 8:
            warnings.append({
                "check": "legibility",
                "msg": "%d top-level shape elements (recommend < 8 for small viewBox assets)"
                       % len(top_shapes),
            })

    # -----------------------------------------------------------------------
    # Native checks
    # -----------------------------------------------------------------------
    needs_native_fork = False
    seen_reject_msgs: set[str] = set()

    def add_rejection(check: str, msg: str) -> None:
        nonlocal needs_native_fork
        if msg not in seen_reject_msgs:
            seen_reject_msgs.add(msg)
            rejections.append({"check": check, "msg": msg})
        needs_native_fork = True

    if target_native:
        for elem in tree.iter():
            ltag = _local_lower(elem.tag)
            orig_tag = _local(elem.tag)

            if ltag == "filter":
                add_rejection("native-filter",
                              "<filter> element not supported in react-native-svg")
            elif ltag in _FE_NAMES:
                add_rejection("native-fe-element",
                              "<%s> filter primitive not supported in react-native-svg"
                              % orig_tag)
            elif ltag in ANIMATE_TAGS:
                add_rejection("native-animation",
                              "<%s> not supported in react-native-svg; use Reanimated"
                              % orig_tag)
            elif ltag == "foreignobject":
                add_rejection("native-foreign-object",
                              "<foreignObject> not supported in react-native-svg")
            elif ltag == "mask":
                warnings.append({
                    "check": "native-mask",
                    "msg": "<mask> supported but historically buggy in react-native-svg",
                })
            elif ltag == "style":
                warnings.append({
                    "check": "native-style",
                    "msg": "<style> blocks have limited support in react-native-svg",
                })
            elif ltag == "pattern":
                warnings.append({
                    "check": "native-pattern",
                    "msg": "<pattern> supported but inconsistent in react-native-svg",
                })

    # Structural errors mean ok:false and exit 1
    structural_checks = {"xml-parse", "file-read", "xmlns", "viewBox"}
    has_structural = any(e["check"] in structural_checks for e in errors)

    return {
        "ok": not has_structural,
        "file": file_path.name,
        "checks": checks_done,
        "errors": errors,
        "warnings": warnings,
        "rejections": rejections,
        "needs_native_fork": needs_native_fork,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _file_arg(argv: list) -> str | None:
    """Extract the first positional (non-flag, non-flag-value) argument."""
    skip_next = False
    for a in argv:
        if skip_next:
            skip_next = False
            continue
        if a.startswith("--"):
            if a in ("--target",):
                skip_next = True
            continue
        return a
    return None


def main(argv: list) -> int:
    want_json = "--json" in argv
    target_native = (
        "--target" in argv
        and argv[argv.index("--target") + 1] == "native"
    )

    file_arg = _file_arg(argv)
    if not file_arg:
        sys.stderr.write(
            "usage: tf_svgcheck.py <file.svg> [--target native] [--json]\n"
        )
        print(json.dumps({"ok": False, "error": "missing file argument"}))
        return 1

    svg_file = Path(file_arg)
    if not svg_file.is_file():
        print(json.dumps({"ok": False, "error": "file not found: %s" % svg_file}))
        return 1

    result = check_svg(svg_file, target_native=target_native)

    if want_json:
        print(json.dumps(result))
    else:
        sys.stderr.write(
            "tf_svgcheck: %d checks, %d errors, %d warnings, %d rejections\n"
            % (result["checks"], len(result["errors"]),
               len(result["warnings"]), len(result["rejections"]))
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_svgcheck: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
