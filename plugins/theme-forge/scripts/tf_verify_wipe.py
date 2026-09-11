#!/usr/bin/env python3
"""tf_verify_wipe.py -- deterministically prove that a wipe left no trace of
generated theme content: no CSS, no copy/content JSON, no images/SVGs, no
gallery/preview HTML, nothing.

Three independent checks, all allowlist-based (never a blocklist of "known
bad" file types, which could miss something a future plugin version adds):

1. `current/` must be EXACTLY empty of content — the only things allowed to
   exist under it are the three freshly-recreated empty scaffold directories
   (`themes/`, `backups/`, `screenshots/`). Any file anywhere under
   `current/`, or any other subdirectory, is a violation — this alone covers
   every category of generated content (CSS, copy, images, gallery/preview
   HTML, tokens, brand assets) in one check, since none of them should exist
   there at all. `screenshots/` is included in the wipe on purpose: a review
   image of a theme slug that no longer exists is exactly the cross-run trace
   this check is here to catch, and it is the reason every screenshot must be
   written under `current/` rather than to the project workspace.

2. `$TF_HOME` root must contain EXACTLY the five known top-level entries
   (`current/`, `knowledge/`, `logs/`, `fonts/`, `used.md`) and nothing else —
   this catches a leak to the wrong location (e.g. a bug that writes a stray
   gallery.html or theme.json directly under TF_HOME instead of current/).
   `fonts/` is a deliberate survivor of the wipe; see `_check_home_root`.

3. `logs/http.log`, if present, must be empty. Every other line in it is
   nothing but "this URL path was requested at this timestamp" -- diagnostic,
   not generated content -- but the URL path embeds whatever theme slug was
   being previewed when the request fired, so a prior run's theme names can
   otherwise sit there indefinitely. `tf_reset.py` truncates this one file at
   wipe time (see its own comment for why nothing else was ever positioned
   to); this check exists so that's proven, not just trusted, the same as
   the other two.

`knowledge/` is intentionally not walked at all — general design-knowledge
reference material, identical regardless of which brief is running, genuinely
independent, long-lived state that `tf_reset.py` never touches and never
needs to.

Run this after tf_reset.py (it is called automatically from reset(), but can
also be run standalone at any time as an audit):

    python3 tf_verify_wipe.py --json

Exit 0 with `"ok": true` when clean. Exit 1 with `"ok": false` and a
`violations` list (categorized by type) when anything is found.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import tf_paths  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import tf_paths


_IMAGE_EXTS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}
_CSS_EXTS = {".css"}
_GALLERY_EXTS = {".html"}
_CODE_EXTS = {".ts", ".js", ".tsx", ".jsx"}
_CONTENT_EXTS = {".json", ".md"}


def _categorize(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _CSS_EXTS:
        return "css"
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _GALLERY_EXTS:
        return "gallery-or-preview-html"
    if ext in _CODE_EXTS:
        return "code"
    if ext in _CONTENT_EXTS:
        return "copy-or-content-json"
    return "other"


def _check_current_empty(current: Path) -> list[dict]:
    """current/ may contain only the two empty scaffold dirs. Anything else
    (a file at any depth, or any other subdirectory) is a violation."""
    violations: list[dict] = []
    if not current.is_dir():
        return violations  # not created yet — nothing to check, not a violation

    allowed_dirs = {current / "themes", current / "backups",
                    current / "screenshots",
                    current / "screenshots" / "visual review",
                    current / "screenshots" / "build"}
    for entry in sorted(current.rglob("*")):
        if entry.is_dir():
            if entry not in allowed_dirs:
                violations.append({
                    "path": str(entry), "type": "unexpected-directory",
                    "category": "other",
                })
            continue
        # Any file anywhere under current/ is a violation, regardless of depth.
        violations.append({
            "path": str(entry), "type": "file-in-current",
            "category": _categorize(entry),
        })
    return violations


def _check_home_root(home: Path) -> list[dict]:
    """TF_HOME root may contain only current/, knowledge/, logs/, fonts/, used.md.

    `fonts/` holds font binaries fetched for a theme's display family
    (tf_assets.py's Fontsource tier, and tf_outline.py searches it first). It sits
    at the TF_HOME top level *deliberately*, outside `current/`, so a generate
    wipe does not discard files that cost a network round-trip each to refetch —
    unlike screenshots, a cached TTF carries no theme identity, so it is not a
    cross-run trace and there is nothing to clear.
    """
    allowed = {"current", "knowledge", "logs", "fonts", "used.md"}
    violations: list[dict] = []
    if not home.is_dir():
        return violations
    for entry in sorted(home.iterdir()):
        if entry.name in allowed:
            continue
        violations.append({
            "path": str(entry), "type": "unexpected-top-level-entry",
            "category": _categorize(entry) if entry.is_file() else "other",
        })
    return violations


def _check_http_log_empty(home: Path) -> list[dict]:
    """logs/http.log must be empty (zero bytes) if it exists at all -- see
    tf_reset.py's own comment on why it's the one file under logs/ this
    process actively clears, unlike logs/ in general."""
    http_log = home / "logs" / "http.log"
    if not http_log.is_file():
        return []
    try:
        size = http_log.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []
    return [{
        "path": str(http_log), "type": "stale-http-log-not-truncated",
        "category": "other",
    }]


def verify(current: Path, home: Path) -> dict:
    """Reusable, exit-free verification. Safe to call in-process (e.g. from
    tf_reset.py right after a wipe) as well as from this file's own CLI."""
    violations = (
        _check_current_empty(current)
        + _check_home_root(home)
        + _check_http_log_empty(home)
    )
    by_category: dict[str, int] = {}
    for v in violations:
        by_category[v["category"]] = by_category.get(v["category"], 0) + 1
    return {
        "ok": len(violations) == 0,
        "current_checked": str(current),
        "home_checked": str(home),
        "violation_count": len(violations),
        "violations_by_category": by_category,
        "violations": violations[:50],
    }


def main(argv: list[str]) -> int:
    want_json = "--json" in argv

    target_override = None
    if "--target" in argv:
        i = argv.index("--target")
        if i + 1 < len(argv):
            target_override = Path(argv[i + 1])
    home_override = None
    if "--home" in argv:
        i = argv.index("--home")
        if i + 1 < len(argv):
            home_override = Path(argv[i + 1])

    paths = tf_paths.resolve(create=False)
    current = target_override if target_override is not None else Path(paths.current)
    home = home_override if home_override is not None else paths.home

    result = verify(current, home)
    if want_json:
        print(json.dumps(result))
    else:
        if result["ok"]:
            sys.stderr.write("tf_verify_wipe: clean — no trace of prior theme content found\n")
        else:
            sys.stderr.write(
                "tf_verify_wipe: FOUND %d trace(s): %s\n"
                % (result["violation_count"], result["violations_by_category"])
            )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"unhandled: {exc}"}))
        sys.exit(2)
