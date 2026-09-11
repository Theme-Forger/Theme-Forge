#!/usr/bin/env python3
"""tf_paths.py -- resolve and create the Theme Forge runtime directory tree.

This is the single source of truth for every path the tool touches. Every other
script imports it rather than re-deriving paths, so the wipe/backup/export logic
can trust that a path is under TF_HOME before it deletes anything.

TF_HOME resolution order:
    1. $THEME_FORGE_HOME
    2. $CLAUDE_PLUGIN_DATA
    3. $HOME/.theme-forge   (or %USERPROFILE% on Windows)

Standard library only. Python 3.9+.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


def _home_dir() -> Path:
    """The user's home directory, cross-platform."""
    h = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if h:
        return Path(h)
    return Path(os.path.expanduser("~"))


def resolve_home() -> Path:
    """Resolve TF_HOME per the documented order. Does not create it."""
    for var in ("THEME_FORGE_HOME", "CLAUDE_PLUGIN_DATA"):
        val = os.environ.get(var)
        if val:
            return Path(val).expanduser()
    return _home_dir() / ".theme-forge"


def find_plugin_root(start: Path | None = None) -> Path | None:
    """Walk up from this file looking for the plugin root.

    The plugin root is the directory that contains `.claude-plugin/plugin.json`.
    Returns None if not found (e.g. the scripts were copied elsewhere).
    """
    here = (start or Path(__file__).resolve()).parent
    for candidate in [here, *here.parents]:
        if (candidate / ".claude-plugin" / "plugin.json").is_file():
            return candidate
    # Fallback: scripts/ sits directly under the plugin root.
    parent = (start or Path(__file__).resolve()).parent.parent
    if (parent / "knowledge").is_dir() or (parent / "scripts").is_dir():
        return parent
    return None


@dataclass
class TFPaths:
    home: Path
    knowledge: Path
    current: Path
    current_themes: Path
    current_backups: Path
    current_screenshots: Path
    current_visual_review: Path
    current_build_shots: Path
    logs: Path
    run_json: Path
    brief_product_json: Path
    brief_design_json: Path
    gallery_html: Path
    critique_md: Path
    freshness_json: Path
    plugin_root: Path | None
    plugin_knowledge: Path | None
    templates: Path | None

    @property
    def brief_json(self) -> Path:
        """Backward-compat shim — returns brief_product_json."""
        return self.brief_product_json

    def to_json(self) -> dict:
        d = {}
        for k, v in asdict(self).items():
            d[k] = str(v) if v is not None else None
        return d


def resolve(create: bool = True) -> TFPaths:
    """Resolve every path and (by default) create the base tree.

    `current/` is created here but is expected to be wiped by tf_reset.py at the
    start of every generate run.
    """
    home = resolve_home()
    knowledge = home / "knowledge"
    current = home / "current"
    current_themes = current / "themes"
    current_backups = current / "backups"
    # The ONLY place any Theme Forge screenshot may be written. It lives under
    # current/ so the wipe clears it with everything else; anywhere outside
    # TF_HOME (the project workspace, a bare CWD, /tmp, or the MCP server's own
    # .playwright-mcp/ scratch dir) leaves review images behind after the run
    # that produced them is gone.
    current_screenshots = current / "screenshots"
    # Two children, split by who writes them: `visual review/` is design-critic's
    # and IS the gallery header's "N shots" claim; `build/` is every other
    # agent's own verification evidence and is deliberately uncounted. Exposed
    # separately so an agent reading `tf_paths.py --json` can pick the right one
    # instead of defaulting into the counted folder.
    current_visual_review = current_screenshots / "visual review"
    current_build_shots = current_screenshots / "build"
    logs = home / "logs"

    plugin_root = find_plugin_root()
    plugin_knowledge = (plugin_root / "knowledge") if plugin_root else None
    templates = (plugin_root / "templates") if plugin_root else None

    paths = TFPaths(
        home=home,
        knowledge=knowledge,
        current=current,
        current_themes=current_themes,
        current_backups=current_backups,
        current_screenshots=current_screenshots,
        current_visual_review=current_visual_review,
        current_build_shots=current_build_shots,
        logs=logs,
        run_json=current / "run.json",
        brief_product_json=current / "brief.product.json",
        brief_design_json=current / "brief.design.json",
        gallery_html=current / "gallery.html",
        critique_md=current / "critique.md",
        freshness_json=knowledge / "FRESHNESS.json",
        plugin_root=plugin_root,
        plugin_knowledge=plugin_knowledge,
        templates=templates,
    )

    if create:
        for d in (home, knowledge, current, current_themes, current_backups,
                  current_screenshots, current_visual_review,
                  current_build_shots, logs):
            d.mkdir(parents=True, exist_ok=True)

    return paths


def screenshots_dir(create: bool = True) -> Path:
    """**design-critic's** shots only — $TF_HOME/current/screenshots/visual review.

    `tf_gallery.py` counts every PNG in this folder and renders the total as
    the gallery header's "visual critique: N shots" pill, so this folder's
    contents ARE that claim. Anything else written here silently overstates how
    much visual review actually happened.

    That is not hypothetical. This docstring used to say "design-critic and
    other visual-capture agents", and on a real six-theme run the folder
    accumulated 86 PNGs — brand-asset contact sheets, theme-fixer before/after
    geometry checks, font-candidate comparisons, MCP scratch files — while
    `critique.md` recorded the critic's own count as **10**. The header claimed
    86. An earlier version of the same bug claimed 138 shots on a run with no
    browser at all; that fix narrowed the *path* but never restricted the
    *writers*, which is the half that actually matters.

    Every other agent that captures an image for its own verification —
    brand-asset-designer, surface-composer, theme-fixer, any ad-hoc check —
    uses `build_shots_dir()` instead. Both live under `screenshots/` so the
    generate wipe still clears them together.
    """
    d = resolve_home() / "current" / "screenshots" / "visual review"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def build_shots_dir(create: bool = True) -> Path:
    """Verification shots from any agent that is NOT design-critic.

    Returns $TF_HOME/current/screenshots/build. Brand-asset contact sheets,
    a theme-fixer's before/after geometry proof, font specimen comparisons,
    rasterizer read-backs — all the images an agent captures to check its own
    work. Uncounted by the gallery header on purpose: they are evidence of
    building, not of reviewing.

    Sits beside `visual review/` under the same `screenshots/` parent so
    `tf_reset.py` clears both and `tf_verify_wipe.py` allowlists both.
    """
    d = resolve_home() / "current" / "screenshots" / "build"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_screenshot_path(out: Path | str, create_parent: bool = True,
                            critique: bool = False) -> Path:
    """Force a screenshot path into the canonical directory.

    A bare or relative name resolves inside the screenshots tree instead of the
    process CWD -- a relative path is how images end up scattered in the
    project root. An absolute path already under TF_HOME is honoured as-is;
    an absolute path outside TF_HOME is redirected by file name, because
    writing review images outside the run directory means they outlive the wipe.

    Defaults to `build_shots_dir()` (uncounted). Pass `critique=True` only from
    design-critic's own capture path, which is the one place whose shots the
    gallery header is entitled to count. The default is deliberately the
    uncounted folder: over-counting is the failure this split exists to stop,
    so a caller that hasn't thought about it should not land in the counted
    folder by accident -- see screenshots_dir() for what that cost twice.
    """
    out = Path(out)
    shots = screenshots_dir(create=create_parent) if critique \
        else build_shots_dir(create=create_parent)
    if not out.is_absolute():
        resolved = shots / out.name
    else:
        home = resolve_home().resolve()
        try:
            out.resolve().relative_to(home)
            resolved = out
        except ValueError:
            resolved = shots / out.name
    if create_parent:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def assert_under_home(target: Path, home: Path | None = None) -> Path:
    """Refuse to operate on any path that is not inside TF_HOME.

    Raises ValueError otherwise. This is the guard every destructive operation
    must call before removing a file or directory.
    """
    home = (home or resolve_home()).resolve()
    target = Path(target).resolve()
    try:
        target.relative_to(home)
    except ValueError:
        raise ValueError(
            "refusing to operate on %s: not under TF_HOME (%s)" % (target, home)
        )
    if target == home:
        raise ValueError("refusing to operate on TF_HOME itself: %s" % home)
    return target


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    no_create = "--no-create" in argv
    paths = resolve(create=not no_create)
    if want_json:
        print(json.dumps({"ok": True, "paths": paths.to_json()}))
    else:
        sys.stderr.write("TF_HOME = %s\n" % paths.home)
        for k, v in paths.to_json().items():
            sys.stderr.write("  %-18s %s\n" % (k, v))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover - unexpected
        sys.stderr.write("tf_paths: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
