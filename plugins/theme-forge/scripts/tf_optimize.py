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
import re
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

    The four accessibility overrides below exist because svgo cannot see that an
    ARIA attribute consumes an id, and treats an accessible name as dead weight.
    Left at preset-default, a real run stripped `<title>` from 157 icons across
    three themes and left 13 `aria-labelledby` attributes pointing at ids that no
    longer existed -- every one of those files still parsed, still rendered, and
    still passed tf_svgcheck. An SVG carrying `role="img"` with no reachable name
    is worse than one with no role at all, so this is a correctness fix, not a
    size/quality tradeoff:

      removeTitle              `<title>` IS the accessible name.
      removeDesc               `<desc>` is the long description ARIA points at.
      cleanupIds               drops ids it thinks are unreferenced; it does not
                               parse aria-labelledby/aria-describedby, so an
                               ARIA-only id looks unused to it.
      removeUnknownsAndDefaults strips `role="img"` off the root element.
    """
    return {
        "plugins": [
            {"name": "preset-default",
             "params": {"overrides": {
                 "removeMetadata": False,
                 "removeTitle": False,
                 "removeDesc": False,
                 "cleanupIds": False,
                 "removeUnknownsAndDefaults": False,
             }}},
            {"name": "prefixIds", "params": {"prefix": id_prefix}},
        ]
    }


def _animated_config(id_prefix: str) -> dict:
    """svgo config that preserves SMIL / CSS animations.

    prefixIds still runs: with cleanupIds off, authored IDs survive verbatim, so
    prefixIds is what keeps them from colliding if the asset is ever inlined
    alongside another theme's. It rewrites href/url() references along with the
    IDs -- but NOT ARIA ones, which is why optimize() runs _repair_aria_refs()
    afterwards.

    convertShapeToPath is disabled for a specific, silent failure: it rewrites
    `<rect>` into `<path d="...">`, which makes any
    `<animate attributeName="height">` targeting that rect a no-op. The mark
    never draws, the file is still valid SVG, and nothing warns. This cost two
    separate themes their logo animation on a real run -- one of them twice,
    because the first workaround (a transform-scale rewrite) was then broken by
    collapseGroups hoisting the wrapper transform onto the animated element.
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
                        # Animated geometry: see docstring.
                        "convertShapeToPath": False,
                        # Accessible name/description -- see _static_config.
                        "removeTitle": False,
                        "removeDesc": False,
                        # See _static_config: <metadata> carries a sourced
                        # asset's license, and losing it is silent.
                        "removeMetadata": False,
                    }
                },
            },
            {"name": "prefixIds", "params": {"prefix": id_prefix}},
        ]
    }


_ARIA_IDREF_ATTRS = ("aria-labelledby", "aria-describedby")


def _repair_aria_refs(path: Path) -> int:
    """Repoint ARIA id references that prefixIds renamed out from under them.

    svgo's prefixIds rewrites `href="#x"` and `url(#x)` when it renames an id,
    but it does not know that `aria-labelledby="x"` is also a reference. The
    result is an SVG whose accessible name silently stops resolving: the
    `<title>` is still there, still has an id, and nothing points at it.

    Returns the number of attributes repaired.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    ids = set(re.findall(r'\bid="([^"]+)"', text))
    if not ids:
        return 0

    repaired = 0
    for attr in _ARIA_IDREF_ATTRS:
        for raw in set(re.findall(r'\b%s="([^"]+)"' % attr, text)):
            refs = raw.split()
            fixed = []
            for ref in refs:
                if ref in ids:
                    fixed.append(ref)
                    continue
                # prefixIds emits "<prefix>__<original>"; recover by suffix.
                hits = sorted(i for i in ids if i.endswith("__" + ref))
                fixed.append(hits[0] if hits else ref)
            if fixed != refs:
                text = text.replace('%s="%s"' % (attr, raw),
                                    '%s="%s"' % (attr, " ".join(fixed)))
                repaired += 1

    if repaired:
        path.write_text(text, encoding="utf-8")
    return repaired


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

        # prefixIds renames ids but does not rewrite aria-labelledby /
        # aria-describedby, so the accessible name stops resolving silently.
        # Repair before measuring, so size_after reflects what ships.
        aria_repaired = _repair_aria_refs(out_path)
        if aria_repaired:
            sys.stderr.write(
                "tf_optimize: repointed %d ARIA id reference(s) in %s\n"
                % (aria_repaired, out_path.name)
            )

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
            "aria_refs_repaired": aria_repaired,
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
