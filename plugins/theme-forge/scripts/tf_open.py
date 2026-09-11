#!/usr/bin/env python3
"""tf_open.py -- open a file in the OS default handler, cross-platform.

Order of attempts:
    1. WSL (microsoft in /proc/version) -> wslview, then explorer.exe via wslpath -w
    2. webbrowser.open()
    3. macOS `open` / Linux `xdg-open` / Windows os.startfile

The absolute path is ALWAYS printed regardless of whether a viewer launched.
Opening the browser is best-effort; a headless environment must not fail the run.

    python3 tf_open.py --path <file> --json [--no-launch]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path


def is_wsl() -> bool:
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def try_open(path: Path):
    """Return (opened: bool, method: str). Never raises."""
    p = str(path)

    if is_wsl():
        if shutil.which("wslview"):
            try:
                subprocess.Popen(["wslview", p])
                return True, "wslview"
            except Exception:
                pass
        if shutil.which("wslpath") and shutil.which("explorer.exe"):
            try:
                win = subprocess.run(["wslpath", "-w", p], capture_output=True, text=True, timeout=5)
                subprocess.Popen(["explorer.exe", win.stdout.strip()])
                return True, "explorer.exe"
            except Exception:
                pass

    uri = path.as_uri()
    try:
        if webbrowser.open(uri):
            return True, "webbrowser"
    except Exception:
        pass

    if sys.platform == "darwin" and shutil.which("open"):
        try:
            subprocess.Popen(["open", p])
            return True, "open"
        except Exception:
            pass
    if sys.platform.startswith("linux") and shutil.which("xdg-open"):
        try:
            subprocess.Popen(["xdg-open", p])
            return True, "xdg-open"
        except Exception:
            pass
    if os.name == "nt":
        try:
            os.startfile(p)  # type: ignore[attr-defined]
            return True, "startfile"
        except Exception:
            pass

    return False, "none"


def main(argv):
    want_json = "--json" in argv
    no_launch = "--no-launch" in argv
    if "--path" not in argv:
        sys.stderr.write("usage: tf_open.py --path <file> --json [--no-launch]\n")
        print(json.dumps({"ok": False, "error": "missing --path"}))
        return 1
    i = argv.index("--path")
    path = Path(argv[i + 1]).resolve()

    opened, method = (False, "skipped") if no_launch else try_open(path)

    result = {"ok": True, "path": str(path), "exists": path.exists(),
              "opened": opened, "method": method}
    sys.stderr.write("tf_open: %s (%s)\n" % (path, method))
    sys.stderr.write("Open it here: %s\n" % path)
    if want_json:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        # Never fail the run because a viewer didn't launch.
        sys.stderr.write("tf_open: %s\n" % exc)
        print(json.dumps({"ok": True, "opened": False, "method": "error", "error": str(exc)}))
        sys.exit(0)
