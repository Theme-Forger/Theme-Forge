#!/usr/bin/env python3
"""tf_shot.py -- render HTML or SVG to PNG for visual review.

Usage:
    python3 tf_shot.py [--html <f>] [--svg <f>] --out <png>
                       [--width N] [--height N] [--wait N]
                       [--full-page] [--viewports web,mobile] [--json]

Returns ok:true regardless of whether rendering succeeded. A missing renderer
is degraded mode, not a fatal error.

`--out` is always resolved into `$TF_HOME/current/screenshots` — a relative
name by file name, and an absolute path outside TF_HOME likewise, so no
screenshot can be written somewhere the run's wipe will not reach. The
resolved destination is echoed to stderr when it differs from what was asked
for.

  --width N    Viewport width in pixels (default 1280)
  --height N   Viewport height in pixels (default 800)
  --wait N     Extra milliseconds to wait after networkidle before screenshot
               (default 2000; use 0 to skip)
  --full-page  Capture full scrollable page instead of viewport only

Python 3.9+, standard library only. Exit 0/1/2.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import tf_paths  # noqa: E402
import tf_tools  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svg_to_html(svg_path: Path, width: int, height: int) -> str:
    """Wrap an SVG file's content in a minimal HTML page for screenshotting."""
    try:
        svg_content = svg_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        svg_content = "<svg xmlns='http://www.w3.org/2000/svg'><rect width='100' height='100' fill='red'/></svg>"
    return (
        "<!DOCTYPE html><html><head>"
        "<meta charset='utf-8'/>"
        "<style>*{{margin:0;padding:0;box-sizing:border-box}}"
        "body{{background:#fff;width:{w}px;overflow:hidden}}"
        "svg{{display:block;max-width:100%}}</style></head>"
        "<body>{svg}</body></html>"
    ).format(w=width, svg=svg_content)


def _html_to_html(html_path: Path) -> str:
    """Read an HTML file."""
    try:
        return html_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Playwright via Python package (preferred on Windows where npx.cmd != npx)
# ---------------------------------------------------------------------------

def _try_playwright_python(html_path: Path, out: Path, width: int,
                            height: int, wait_ms: int = 2000,
                            full_page: bool = False) -> tuple[bool, str]:
    """Use the installed Python playwright package to screenshot an HTML file."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return False, "playwright Python package not installed"
    try:
        url = html_path.as_uri()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url)
            page.wait_for_load_state("networkidle")
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)
            page.screenshot(path=str(out), full_page=full_page)
            browser.close()
        return True, ""
    except Exception as exc:
        return False, str(exc)[:300]


# ---------------------------------------------------------------------------
# Playwright via npx CLI
# ---------------------------------------------------------------------------

def _try_playwright_npx(html_path: Path, out: Path, width: int,
                         height: int) -> tuple[bool, str]:
    url = html_path.as_uri()
    # Resolve npx to a real path: on Windows the executable is npx.CMD, and a
    # bare "npx" raises FileNotFoundError from a Python subprocess.
    npx = shutil.which("npx")
    if npx is None:
        return False, "npx not found on PATH"
    try:
        r = subprocess.run(
            [npx, "--no-install", "playwright", "screenshot",
             "--viewport-size", "%d,%d" % (width, height),
             url, str(out)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # npx cold-start alone runs 7-9 s on Windows before the browser launches.
            timeout=180,
        )
        ok = r.returncode == 0 and out.is_file()
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        return ok, err
    except FileNotFoundError:
        return False, "npx/playwright not found"
    except subprocess.TimeoutExpired:
        return False, "playwright CLI timed out"
    except OSError as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Playwright via inline Node.js script
# ---------------------------------------------------------------------------

def _try_playwright_node(html_path: Path, out: Path, width: int,
                          height: int, wait_ms: int = 2000,
                          full_page: bool = False) -> tuple[bool, str]:
    """Write a tiny Node.js script that drives Playwright, then run it."""
    url_str = str(html_path).replace("\\", "/")
    out_str = str(out).replace("\\", "/")
    wait_line = (
        f"  await p.waitForTimeout({wait_ms});\n"
        if wait_ms > 0 else ""
    )
    full_page_js = "true" if full_page else "false"
    script = (
        "const {{ chromium }} = require('playwright');\n"
        "(async () => {{\n"
        "  const b = await chromium.launch();\n"
        "  const p = await b.newPage();\n"
        "  await p.setViewportSize({{width: {w}, height: {h}}});\n"
        "  await p.goto('file:///{url}');\n"
        "  await p.waitForLoadState('networkidle');\n"
        "{wait}"
        "  await p.screenshot({{path: '{out}', fullPage: {fp}}});\n"
        "  await b.close();\n"
        "}})().catch(e => {{ console.error(e.message); process.exit(1); }});\n"
    ).format(w=width, h=height, url=url_str, out=out_str,
             wait=wait_line, fp=full_page_js)

    tmp_js = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".js", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(script)
            tmp_js = Path(f.name)

        r = subprocess.run(
            ["node", str(tmp_js)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        ok = r.returncode == 0 and out.is_file()
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        return ok, err
    except FileNotFoundError:
        return False, "node not found"
    except subprocess.TimeoutExpired:
        return False, "node playwright script timed out"
    except OSError as e:
        return False, str(e)
    finally:
        if tmp_js is not None:
            try:
                tmp_js.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Raster fallback (for SVG inputs)
# ---------------------------------------------------------------------------

def _try_raster_fallback(svg_path: Path, out: Path, width: int) -> tuple[bool, str]:
    try:
        import tf_raster  # noqa: PLC0415
        tools = tf_tools.detect()
        result = tf_raster.rasterize_one(svg_path, out, width, None, tools)
        return result.get("rasterized", False), str(result.get("rasterize_md", ""))
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Main render logic
# ---------------------------------------------------------------------------

def render(html_path: Path | None, svg_path: Path | None,
           out: Path, width: int, height: int,
           wait_ms: int = 2000, full_page: bool = False) -> dict:
    """Try all renderers in order. Always returns ok:true."""
    out.parent.mkdir(parents=True, exist_ok=True)

    tmp_html = None
    try:
        # Build a temp HTML page if needed
        if html_path is None and svg_path is not None:
            content = _svg_to_html(svg_path, width, height)
            with tempfile.NamedTemporaryFile(
                suffix=".html", delete=False, mode="w", encoding="utf-8"
            ) as f:
                f.write(content)
                tmp_html = Path(f.name)
            html_path = tmp_html

        target_html = html_path

        if target_html is not None:
            # 1. Python playwright (preferred — available without npx on Windows)
            ok, err = _try_playwright_python(
                target_html, out, width, height, wait_ms=wait_ms, full_page=full_page
            )
            if ok:
                return {"ok": True, "rendered": True, "tool": "playwright-python",
                        "path": str(out), "width": width, "height": height}
            sys.stderr.write("tf_shot: playwright-python: %s\n" % err[:300])

            # 2. npx playwright screenshot (viewport-only; no wait support in CLI)
            ok, err = _try_playwright_npx(target_html, out, width, height)
            if ok:
                return {"ok": True, "rendered": True, "tool": "playwright-npx",
                        "path": str(out), "width": width, "height": height}
            sys.stderr.write("tf_shot: playwright-npx: %s\n" % err[:300])

            # 3. node playwright script (supports wait + fullPage param)
            ok, err = _try_playwright_node(
                target_html, out, width, height, wait_ms=wait_ms, full_page=full_page
            )
            if ok:
                return {"ok": True, "rendered": True, "tool": "playwright-node",
                        "path": str(out), "width": width, "height": height}
            sys.stderr.write("tf_shot: playwright-node: %s\n" % err[:300])

        # 3. Raster fallback (SVG only)
        if svg_path is not None:
            ok, info = _try_raster_fallback(svg_path, out, width)
            if ok:
                return {"ok": True, "rendered": True, "tool": "raster-fallback",
                        "path": str(out), "width": width, "height": height}
            sys.stderr.write("tf_shot: raster-fallback: %s\n" % str(info)[:300])

        return {"ok": True, "rendered": False, "reason": "no renderer available"}

    finally:
        if tmp_html is not None:
            try:
                tmp_html.unlink()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list) -> int:
    want_json = "--json" in argv

    if "--html" not in argv and "--svg" not in argv:
        sys.stderr.write(
            "usage: tf_shot.py [--html <f>] [--svg <f>] --out <png> "
            "[--width N] [--viewports web,mobile] [--json]\n"
        )
        print(json.dumps({"ok": False, "error": "must supply --html or --svg"}))
        return 1

    if "--out" not in argv:
        print(json.dumps({"ok": False, "error": "missing --out"}))
        return 1

    html_path = None
    svg_path = None
    if "--html" in argv:
        html_path = Path(argv[argv.index("--html") + 1])
    if "--svg" in argv:
        svg_path = Path(argv[argv.index("--svg") + 1])

    # Force the destination into $TF_HOME/current/screenshots. A relative
    # --out would otherwise land wherever the caller happened to be, and an
    # absolute path outside TF_HOME would survive the wipe.
    requested_out = Path(argv[argv.index("--out") + 1])
    out = tf_paths.resolve_screenshot_path(requested_out)
    if out != requested_out:
        sys.stderr.write("tf_shot: writing to %s (canonical screenshots dir)\n"
                         % out)
    width = 1280
    height = 800
    wait_ms = 2000
    full_page = "--full-page" in argv
    if "--width" in argv:
        width = int(argv[argv.index("--width") + 1])
    if "--height" in argv:
        height = int(argv[argv.index("--height") + 1])
    if "--wait" in argv:
        wait_ms = int(argv[argv.index("--wait") + 1])

    result = render(html_path, svg_path, out, width, height,
                    wait_ms=wait_ms, full_page=full_page)

    if want_json:
        print(json.dumps(result))
    else:
        sys.stderr.write("tf_shot: rendered=%s tool=%s\n"
                         % (result.get("rendered"), result.get("tool")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_shot: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
