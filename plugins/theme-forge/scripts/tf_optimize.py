#!/usr/bin/env python3
"""tf_optimize.py -- SVG optimization via svgo (if available).

Usage:
    python3 tf_optimize.py --in <file.svg> --out <file.svg>
                           [--animated] [--id-prefix <str>] [--json]

If svgo is not available: copies input to output unchanged and returns
ok:true, optimized:false.

IDs are prefixed with `<theme-slug>-<file-stem>` rather than svgo's default of
the file name alone, so two themes' assets can share a document without their
ids colliding. Override with --id-prefix.

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

def _static_config(id_prefix: str) -> dict:
    """svgo config safe for all non-animated SVGs.

    removeMetadata is disabled. `preset-default` strips `<metadata>`, and for a
    sourced asset that block is where the license lives: DiceBear embeds Dublin
    Core RDF (`dcterms:license`, `dc:creator`, `dc:rights`) in every SVG it
    serves, which is what lets tf_assets.license_from_svg read an asset's terms
    from the asset itself instead of trusting a hardcoded style->license table.
    Optimizing that away destroys the only in-band provenance record, and it
    does so silently -- the file still renders identically.

    The cost is a few hundred bytes on assets that carry metadata at all;
    authored SVGs have none, so for them this override changes nothing.
    """
    return {
        "plugins": [
            {"name": "preset-default",
             "params": {"overrides": {"removeMetadata": False}}},
            {"name": "prefixIds", "params": {"prefix": id_prefix}},
        ]
    }


def _animated_config(id_prefix: str) -> dict:
    """svgo config that preserves SMIL / CSS animations.

    prefixIds still runs: with cleanupIds off, authored IDs survive verbatim, so
    prefixIds is what keeps them from colliding if the asset is ever inlined
    alongside another theme's. It rewrites references along with the IDs.
    """
    return {
        "plugins": [
            {
                "name": "preset-default",
                "params": {
                    "overrides": {
                        "cleanupIds": False,
                        "inlineStyles": False,
                        "minifyStyles": False,
                        "removeHiddenElems": False,
                        "mergePaths": False,
                        "collapseGroups": False,
                        "removeUnknownsAndDefaults": False,
                        # See _static_config: <metadata> carries a sourced
                        # asset's license, and losing it is silent.
                        "removeMetadata": False,
                    }
                },
            },
            {"name": "prefixIds", "params": {"prefix": id_prefix}},
        ]
    }


def _sanitize_prefix(text: str) -> str:
    """Reduce to characters legal and safe in an SVG id / CSS selector."""
    out = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in text)
    out = out.strip("-")
    # An id must not start with a digit to stay usable as a CSS selector.
    if out and out[0].isdigit():
        out = "id" + out
    return out or "tf"


def _theme_root(path: Path):
    """Nearest ancestor containing theme.json, or None."""
    for parent in path.resolve().parents:
        if (parent / "theme.json").is_file():
            return parent
    return None


def id_prefix_for(in_path: Path, explicit: str | None = None) -> str:
    """Build a prefix that is unique across themes *and* across files.

    svgo's prefixIds defaults to the file name alone, so every theme's
    pattern.svg yields the same `pattern_svg__a`. Those ids collide the moment
    two themes' assets share a document, and because each file is optimized in
    isolation nothing in svgo can notice. Scoping the prefix with the theme slug
    removes the collision at the source.
    """
    if explicit:
        return _sanitize_prefix(explicit)
    root = _theme_root(in_path)
    stem = in_path.stem
    if root is None:
        # Not inside a theme (ad-hoc call): file-scoped only, as svgo would do.
        return _sanitize_prefix(stem)
    # Stem first, then theme slug: theme slugs start with a digit ("01-…") and a
    # leading digit is illegal in a CSS identifier, so leading with the stem
    # keeps the id usable as a selector without needing a synthetic guard.
    return _sanitize_prefix("%s-%s" % (stem, root.name))


# npx cold-start from a Python subprocess (no pre-loaded shell env) runs 7-9 s
# on Windows before svgo even begins parsing.
_NPX_TIMEOUT = 30
_SVGO_TIMEOUT = 120


def _svgo_argv() -> list:
    """Return the argv prefix that runs svgo.

    Prefers the globally-installed `svgo` shim on PATH over `npx svgo`: npx adds
    roughly 20 s of resolution overhead per invocation. Falls back to npx so a
    project-local svgo still works.
    """
    direct = shutil.which("svgo")
    if direct:
        return [direct]
    return [shutil.which("npx") or "npx", "--no-install", "svgo"]


_SVGO = _svgo_argv()


def _svgo_available() -> bool:
    """Return True if svgo is callable."""
    try:
        r = subprocess.run(
            _SVGO + ["--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_NPX_TIMEOUT,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def optimize(in_path: Path, out_path: Path, animated: bool = False,
             id_prefix: str | None = None) -> dict:
    """Optimize in_path -> out_path. Returns result dict."""
    if not in_path.is_file():
        return {"ok": False, "error": "input file not found: %s" % in_path}

    size_before = in_path.stat().st_size
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not _svgo_available():
        sys.stderr.write("tf_optimize: svgo not available, copying unchanged\n")
        if str(in_path) != str(out_path):
            shutil.copy2(str(in_path), str(out_path))
        return {
            "ok": True,
            "optimized": False,
            "reason": "svgo not available",
            "size_before": size_before,
            "size_after": size_before,
        }

    prefix = id_prefix_for(in_path, id_prefix)
    config = _animated_config(prefix) if animated else _static_config(prefix)

    tmp_cfg = None
    try:
        # svgo v4 loads its config as an ES module. A .json config fails on
        # Node 22+ with ERR_IMPORT_ATTRIBUTE_MISSING (strict import attributes),
        # so emit .mjs with a default export instead.
        with tempfile.NamedTemporaryFile(
            suffix=".mjs", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write("export default " + json.dumps(config) + ";\n")
            tmp_cfg = Path(f.name)

        r = subprocess.run(
            _SVGO + ["--config", str(tmp_cfg),
                     "-i", str(in_path),
                     "-o", str(out_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_SVGO_TIMEOUT,
        )
        if r.returncode != 0:
            err = (r.stderr or b"").decode("utf-8", errors="replace")
            sys.stderr.write("tf_optimize: svgo failed: %s\n" % err[:300])
            # Copy unchanged so out_path always exists
            if str(in_path) != str(out_path):
                shutil.copy2(str(in_path), str(out_path))
            return {
                "ok": False,
                "error": "svgo exited %d: %s" % (r.returncode, err[:200]),
            }

        size_after = out_path.stat().st_size if out_path.is_file() else size_before
        savings = round(100.0 * (1 - size_after / size_before), 1) if size_before else 0

        sys.stderr.write(
            "tf_optimize: %s -> %s (%.1f%% savings)\n"
            % (in_path.name, out_path.name, savings)
        )
        return {
            "ok": True,
            "optimized": True,
            "size_before": size_before,
            "size_after": size_after,
            "savings_pct": savings,
            "id_prefix": prefix,
        }
    except FileNotFoundError:
        if str(in_path) != str(out_path):
            shutil.copy2(str(in_path), str(out_path))
        return {
            "ok": True,
            "optimized": False,
            "reason": "npx not found",
            "size_before": size_before,
            "size_after": size_before,
        }
    except subprocess.TimeoutExpired:
        if str(in_path) != str(out_path):
            shutil.copy2(str(in_path), str(out_path))
        return {
            "ok": True,
            "optimized": False,
            "reason": "svgo timed out",
            "size_before": size_before,
            "size_after": size_before,
        }
    finally:
        if tmp_cfg is not None:
            try:
                tmp_cfg.unlink()
            except Exception:
                pass


def main(argv: list) -> int:
    want_json = "--json" in argv
    animated = "--animated" in argv

    if "--in" not in argv or "--out" not in argv:
        sys.stderr.write(
            "usage: tf_optimize.py --in <file.svg> --out <file.svg> "
            "[--animated] [--id-prefix <str>] [--json]\n"
        )
        print(json.dumps({"ok": False, "error": "missing --in or --out"}))
        return 1

    in_path = Path(argv[argv.index("--in") + 1])
    out_path = Path(argv[argv.index("--out") + 1])
    id_prefix = None
    if "--id-prefix" in argv:
        id_prefix = argv[argv.index("--id-prefix") + 1]

    result = optimize(in_path, out_path, animated=animated, id_prefix=id_prefix)

    if want_json:
        print(json.dumps(result))
    else:
        sys.stderr.write("tf_optimize: %s\n" % result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        sys.stderr.write("tf_optimize: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
