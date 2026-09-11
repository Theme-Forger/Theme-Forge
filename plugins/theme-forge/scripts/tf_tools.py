#!/usr/bin/env python3
"""tf_tools.py -- capability detection and caching.

Detects available rasterizers, node/npx, browser, opentype.js, svgo, network
reachability, and stock API keys. Caches results to $TF_HOME/current/tools.json
(TTL 24 h).

    python3 tf_tools.py [--json] [--no-cache]

Python 3.9+, standard library only. Exit 0/1/2.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import tf_paths  # noqa: E402

CACHE_TTL = 86400  # 24 hours


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the child *and every descendant*.

    Popen.kill() reaches only the direct child. npx spawns node, which spawns a
    browser; killing npx leaves those running forever. One timed-out probe left
    eight orphaned node/chrome processes behind.
    """
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=15,
            )
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _global_node_modules() -> list[str]:
    """Existing npm global node_modules roots, best candidate first.

    node does NOT search npm's global root on its own, so `require('pkg')` finds
    a globally installed package only when NODE_PATH happens to point there. A
    detector that ignores this reports a globally installed library as absent.

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
    parts = [p for p in env.get("NODE_PATH", "").split(os.pathsep) if p]
    for r in roots:
        if r not in parts:
            parts.append(r)
    env["NODE_PATH"] = os.pathsep.join(parts)
    return env


def _run(cmd: list, timeout: int = 5, env: dict | None = None) -> tuple[bool, str]:
    """Run cmd, return (success, combined_output). Never raises.

    Output is captured to temporary FILES rather than pipes, and the timeout is
    enforced with Popen.wait() rather than subprocess.run().

    subprocess.run(timeout=...) kills only the direct child on expiry and then
    calls communicate() to drain the pipes -- but a surviving grandchild still
    holds the inherited write handles open, so there is no EOF and the parent
    blocks forever on a timeout that has already fired. A capability probe hung
    for 32 minutes at 0.3 s of CPU exactly this way. A file has no writer to
    wait on, so the timeout is real regardless of what the child spawned.

    stdin is /dev/null: a probe that decides to prompt must fail, not wait.
    """
    out_f = err_f = None
    proc = None
    try:
        out_f = tempfile.TemporaryFile()
        err_f = tempfile.TemporaryFile()
        proc = subprocess.Popen(
            cmd,
            stdout=out_f,
            stderr=err_f,
            stdin=subprocess.DEVNULL,
            env=env,
        )
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            return False, ""
        out_f.seek(0)
        err_f.seek(0)
        out = out_f.read().decode("utf-8", errors="replace")
        err = err_f.read().decode("utf-8", errors="replace")
        return rc == 0, (out + " " + err).strip()
    except FileNotFoundError:
        return False, ""
    except OSError:
        return False, ""
    except Exception:
        return False, ""
    finally:
        for f in (out_f, err_f):
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass


def _npx() -> str:
    """Absolute path to npx, or a bare name as a last resort.

    Resolved with shutil.which rather than by probing `npx --version`. The probe
    was wrong twice over: it ran at import time with the default 5 s timeout
    while npx cold start costs 4-11 s here, so npx was intermittently reported
    absent -- which cascades into every npx-backed tool (svgo, resvg-js,
    sharp-cli, playwright) being reported missing too. It also charged that cost
    to *every* import of this module merely to learn a filename.
    """
    return shutil.which("npx") or shutil.which("npx.cmd") or "npx"


# Resolved once at import time (a filename lookup, no subprocess)
_NPX = _npx()


# ---------------------------------------------------------------------------
# Detection functions
# ---------------------------------------------------------------------------

def _detect_node() -> tuple[str | None, bool]:
    """Return (version_str, npx_available)."""
    ok, out = _run(["node", "--version"])
    version = None
    if ok and out.strip():
        raw = out.strip().split()[0].lstrip("v")
        version = raw
    npx_ok, _ = _run([_NPX, "--version"])
    return version, npx_ok


def _detect_rasterizers(node_available: bool) -> tuple[str | None, list]:
    """Rasterizer ladder. Returns (best_key_or_None, all_found_keys)."""
    found: list[str] = []

    # npx.cmd cold-start on Windows can take 8-10 s from a Python subprocess
    # (no shell env pre-loaded, OneDrive latency). Use a generous timeout for
    # all npx-based probes; native CLI tools keep the default 5 s.
    _NPX_TIMEOUT = 30

    # 1. resvg
    ok, _ = _run(["resvg", "--version"])
    if ok:
        found.append("resvg")

    # 2. resvg-js (needs node)
    if node_available:
        ok, _ = _run([_NPX, "--no-install", "@resvg/resvg-js-cli", "--version"],
                     timeout=_NPX_TIMEOUT)
        if ok:
            found.append("resvg-js")

    # 3. rsvg-convert
    ok, _ = _run(["rsvg-convert", "--version"])
    if ok:
        found.append("rsvg-convert")

    # 4. ImageMagick
    ok, _ = _run(["magick", "-version"])
    if ok:
        found.append("magick")

    # 5. Inkscape
    ok, _ = _run(["inkscape", "--version"])
    if ok:
        found.append("inkscape")

    # 6. sharp-cli (needs node)
    if node_available:
        ok, _ = _run([_NPX, "--no-install", "sharp-cli", "--version"],
                     timeout=_NPX_TIMEOUT)
        if ok:
            found.append("sharp-cli")

    # 7. Playwright (last — heaviest)
    ok, _ = _run([_NPX, "--no-install", "playwright", "--version"],
                 timeout=_NPX_TIMEOUT)
    if ok:
        found.append("playwright")

    best = found[0] if found else None
    return best, found


def _detect_browser(rasterizers_found: list) -> str | None:
    if "playwright" in rasterizers_found:
        return "playwright"
    # Python playwright package — check importability + browser binary presence (no launch)
    try:
        import importlib.util
        if importlib.util.find_spec("playwright") is not None:
            # Browser binaries live in %LOCALAPPDATA%\ms-playwright (Win) or ~/.cache/ms-playwright
            local_app = os.environ.get("LOCALAPPDATA", "")
            pw_win = Path(local_app) / "ms-playwright" if local_app else None
            pw_unix = Path.home() / ".cache" / "ms-playwright"
            pw_dir = pw_win if (pw_win and pw_win.exists()) else pw_unix
            if pw_dir and pw_dir.exists() and any(pw_dir.iterdir()):
                return "playwright-python"
    except Exception:
        pass
    for cmd in (["chromium", "--version"], ["chromium-browser", "--version"],
                ["google-chrome", "--version"]):
        ok, _ = _run(cmd)
        if ok:
            return "chromium"
    return None


def _detect_opentype(node_available: bool) -> bool:
    if not node_available:
        return False
    # NODE_PATH must carry npm's global root or a globally installed
    # opentype.js is invisible here and the wordmark silently degrades.
    ok, _ = _run(["node", "-e", "require('opentype.js')"], env=_node_env())
    return ok


def _detect_svgo(node_available: bool) -> bool:
    if not node_available:
        return False
    ok, _ = _run([_NPX, "--no-install", "svgo", "--version"], timeout=30)
    return ok


def _detect_network() -> bool:
    try:
        s = socket.create_connection(("8.8.8.8", 53), timeout=2)
        s.close()
        return True
    except OSError:
        return False


def _detect_stock_api() -> dict:
    # Pexels is the only stock-photo provider tf_imagery.py actually fetches
    # from — no other provider has fetch logic, so no other key is checked.
    return {
        "pexels": bool(os.environ.get("PEXELS_API_KEY")),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect(no_cache: bool = False) -> dict:
    """Run (or load cached) capability detection. Returns the tools dict."""
    paths = tf_paths.resolve(create=True)
    cache_path = paths.current / "tools.json"

    if not no_cache and cache_path.is_file():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            age = time.time() - data.get("_cached_at", 0)
            if age < CACHE_TTL:
                sys.stderr.write("tf_tools: using cached tools.json (age %.0fs)\n" % age)
                return data
        except Exception:
            pass

    sys.stderr.write("tf_tools: detecting capabilities...\n")

    node_version, npx_ok = _detect_node()
    node_available = node_version is not None
    rasterizer, rasterizers_found = _detect_rasterizers(node_available)
    browser = _detect_browser(rasterizers_found)
    opentype = _detect_opentype(node_available)
    svgo = _detect_svgo(node_available)
    network = _detect_network()
    stock_api = _detect_stock_api()

    degraded: list[str] = []
    if rasterizer is None:
        degraded.append("rasterizer")
    if not opentype:
        degraded.append("opentype")
    if not svgo:
        degraded.append("svgo")
    if browser is None:
        degraded.append("browser")
    if not network:
        degraded.append("network")

    result: dict = {
        "ok": True,
        "rasterizer": rasterizer,
        "rasterizers_found": rasterizers_found,
        "node": node_version,
        "npx": npx_ok,
        "browser": browser,
        "opentype": opentype,
        "svgo": svgo,
        "network": network,
        "stock_api": stock_api,
        "degraded": degraded,
        "_cached_at": time.time(),
    }

    try:
        cache_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        sys.stderr.write("tf_tools: cached to %s\n" % cache_path)
    except Exception as exc:
        sys.stderr.write("tf_tools: warning: could not write cache: %s\n" % exc)

    return result


def main(argv: list) -> int:
    want_json = "--json" in argv
    no_cache = "--no-cache" in argv

    result = detect(no_cache=no_cache)

    # Strip internal keys from output
    out = {k: v for k, v in result.items() if not k.startswith("_")}

    if want_json:
        print(json.dumps(out))
    else:
        sys.stderr.write("rasterizer  : %s\n" % out.get("rasterizer"))
        sys.stderr.write("node        : %s\n" % out.get("node"))
        sys.stderr.write("browser     : %s\n" % out.get("browser"))
        sys.stderr.write("degraded    : %s\n" % out.get("degraded"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_tools: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
