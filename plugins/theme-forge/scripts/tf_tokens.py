#!/usr/bin/env python3
"""tf_tokens.py -- silently-inert-CSS gate for a theme's authored surfaces.

Three checks, one theme: CSS that parses, is well-formed, and does nothing.

1. `tokens.dead_custom_property` -- `var(--tf-x)` with no fallback that nothing
   defines, neither `tf_gallery.py`'s injected token block nor the stylesheet
   itself. **This is the one `tf_gallery.py` hard-aborts on**; the other two are
   reported for the composer to fix.
2. `tokens.android_elevation_on_web` -- a website/webapp stylesheet reaching for
   `--tf-elev-<level>` (the synthesized *Android* elevation, meaningful only
   inside the mobile device frame) where it means `--tf-shadow-<level>` (the
   theme's own CSS shadow).
3. `tokens.unmatchable_scoped_selector` -- a mobile selector whose leftmost
   compound is the device-frame class, which can never match once the sheet is
   wrapped in `@scope (... .screen-pane)`.

All three share a failure mode: the page still renders, and renders plausibly,
so nothing looks broken enough to investigate.

Why this needs a gate of its own
--------------------------------
An undefined custom property is the quietest failure mode in the whole
pipeline. `var(--tf-nope)` in a non-shorthand property does not raise, does not
warn, and does not fall back to anything visible -- the declaration is thrown
out at computed-value time and the property keeps its inherited or initial
value. The page still renders. It renders *plausibly*. A heading whose
`font-size: var(--tf-text-4xl)` died is not blank; it is body-sized, which
looks like a design decision rather than a bug.

Every previous instance of this was found the same way: by eye, late, usually
by a design-critic screenshot pass, and usually after someone had already
spent time debugging the wrong layer. `tf_gallery.py`'s own token block is
scarred with the evidence -- dual `--tf-t-*`/`--tf-text-*` spellings, dual
`--tf-r-*`/`--tf-radius-*`, dual `--tf-dur-*`/`--tf-duration-*`, a dense
`--tf-space-N` index, a generic "any other declared key" pass -- each one added
after a real run shipped with something silently unstyled. A confirmed live
audit of one six-theme run found **496** bare dead references across 10 of 12
surfaces, including an entire theme whose surfaces used a `--tf-color-*` prefix
the gallery never emitted, so essentially all of its color resolved to
inherited values.

That is a mechanical check, and mechanical checks belong in a script rather
than in the reviewer's eye. The failure is invisible precisely where humans
look and obvious precisely where a parser looks.

What counts as a finding
------------------------
Only a **bare** dead reference -- `var(--tf-x)` with no fallback. A reference
written `var(--tf-x, 2px)` is explicitly designed to survive the property being
absent, which is a legitimate authoring choice, so it is reported as
informational and never as a finding.

A property defined by the surface's own stylesheet counts as defined. Surfaces
are allowed, and encouraged, to declare their own locals for anything with no
source in `theme.json` (`--tf-press-travel`, `--tf-keyline`, a grid measure) --
the contract is that it must be defined *somewhere*, not that it must come
from the theme.

Usage:
    python3 tf_tokens.py --theme <dir> [--surface website] --json
    python3 tf_tokens.py --all --json
    python3 tf_tokens.py --selftest

Exit 0 on success (findings do not change the exit code -- the caller decides
severity, same convention as tf_content.py). Exit 1 on expected failure
(missing files, bad args). Exit 2 on unexpected error.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import tf_paths  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import tf_paths


SURFACES = ("website", "webapp", "mobile")

# A definition is `--tf-name:` appearing anywhere (in the injected block or in
# the surface's own CSS). A use is `var(--tf-name` followed by either `)` (bare)
# or `,` (has a fallback).
_DEF_RE = re.compile(r"(--tf-[A-Za-z0-9_-]+)\s*:")
_USE_RE = re.compile(r"var\(\s*(--tf-[A-Za-z0-9_-]+)\s*([,)])")
# Strip comments before scanning so a token named only inside an explanatory
# /* ... */ block is not counted as either a definition or a use.
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def emitted_names(theme: dict, theme_dir: Path) -> set:
    """Every --tf-* name tf_gallery.py injects for this theme.

    Derived by actually running the emitter rather than by maintaining a
    parallel list of what it is believed to emit -- a hand-kept list would
    drift from the generator, and drifting from the generator is the exact
    class of bug this file exists to catch.

    tf_gallery is imported HERE rather than at module scope on purpose:
    tf_gallery imports this module to run the gate inline during assembly, so
    a module-level import in both directions is a cycle. Deferring it to call
    time means neither module needs the other to finish initializing, and the
    selftest (which never reaches this function) stays importable on its own.
    """
    try:
        import tf_gallery  # type: ignore
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent))
        import tf_gallery
    block = tf_gallery.theme_style_block(1, theme, theme_dir)
    return set(_DEF_RE.findall(block))


def scan_css(css_text: str, defined: set) -> dict:
    """Split every --tf-* use in *css_text* into dead / fallback / resolved."""
    text = _COMMENT_RE.sub("", css_text)
    local = set(_DEF_RE.findall(text))
    known = defined | local

    dead: dict = {}
    fallback: dict = {}
    for m in _USE_RE.finditer(text):
        name, nxt = m.group(1), m.group(2)
        if name in known:
            continue
        bucket = fallback if nxt == "," else dead
        bucket[name] = bucket.get(name, 0) + 1
    return {"dead": dead, "fallback": fallback, "local_count": len(local)}


# A selector whose LEFTMOST compound is the device-frame class. tf_gallery.py
# wraps mobile CSS in `@scope ([data-tf-theme="N"] .screen-pane)`, and inside an
# @scope block every selector that does not already name :scope is implicitly
# prefixed with `:scope `. The device frame is an ANCESTOR of .screen-pane
# (.device.ios > ... > .screens > .screen-pane), so `.device.ios .card` becomes
# `:scope .device.ios .card` and can never match anything.
_DEVICE_ANCESTOR_RE = re.compile(r"^\.device\b")


def _split_selectors(css_text: str):
    """Yield each comma-separated selector that precedes a `{` block.

    Deliberately crude -- it only needs to see selector text, not parse CSS.
    At-rule preludes (@media, @supports) are skipped because they contain no
    element selectors to misread.
    """
    for chunk in re.split(r"}", css_text):
        if "{" not in chunk:
            continue
        prelude = chunk.rsplit("{", 1)[0]
        # keep only the part after the last } or { that opened a nesting level
        prelude = prelude.split("{")[-1] if "{" in prelude else prelude
        for sel in prelude.split(","):
            sel = sel.strip()
            if sel and not sel.startswith("@"):
                yield sel


def scan_scoped_selectors(css_text: str) -> dict:
    """Selectors in a MOBILE stylesheet that can never match once @scope'd.

    Returns {selector: count}. See _DEVICE_ANCESTOR_RE for the mechanism.

    This silently defeats the "Native honesty" requirement in
    agents/surface-composer.md, which tells every composer to write exactly the
    `.device.ios .x` / `.device.android .x` form. Confirmed live in a browser by
    three independent agents in one run: of six themes, three shipped platform
    rules that matched nothing at all, so iOS and Android rendered identically
    while every gate reported clean. Nothing about the CSS is invalid -- it
    parses, it is well-formed, and it is inert.

    Two forms DO work and either is acceptable:
      .card:where(.device.android *)   -- subject in scope, ancestor in :where()
      .device.android :scope .card     -- explicit :scope, so no re-prefixing
    """
    text = _COMMENT_RE.sub("", css_text)
    bad: dict = {}
    for sel in _split_selectors(text):
        if _DEVICE_ANCESTOR_RE.match(sel) and ":scope" not in sel:
            bad[sel] = bad.get(sel, 0) + 1
    return bad


def check_theme(theme_dir: Path, only_surface: str = None) -> dict:
    theme_path = theme_dir / "theme.json"
    if not theme_path.is_file():
        return {"ok": False, "error": "no theme.json at %s" % theme_dir}
    theme = json.loads(theme_path.read_text(encoding="utf-8"))
    defined = emitted_names(theme, theme_dir)

    findings = []
    notes = []
    checked = []
    for surface in SURFACES:
        if only_surface and surface != only_surface:
            continue
        css = theme_dir / "surfaces" / ("%s.css" % surface)
        if not css.is_file():
            continue
        checked.append(surface)
        css_text = css.read_text(encoding="utf-8", errors="replace")
        res = scan_css(css_text, defined)
        for name, n in sorted(res["dead"].items(), key=lambda kv: -kv[1]):
            findings.append({
                "check": "tokens.dead_custom_property",
                "surface": surface,
                "property": name,
                "uses": n,
                "severity": "high",
                "message": (
                    "%s is used %d time(s) with no fallback in %s.css, and nothing "
                    "defines it -- not tf_gallery.py's injected token block and not "
                    "this stylesheet. Every declaration using it is silently dropped "
                    "at computed-value time. Either use the token this theme actually "
                    "emits, or declare it locally in this stylesheet."
                    % (name, n, surface)
                ),
            })
        for name, n in sorted(res["fallback"].items(), key=lambda kv: -kv[1]):
            notes.append({
                "surface": surface, "property": name, "uses": n,
                "message": "%s is undefined but always written with a fallback -- "
                           "renders as authored, no action needed." % name,
            })

        # --tf-elev-* is the synthesized ANDROID elevation for a level. It is
        # only meaningful inside a device frame, and the device frame exists
        # only on the mobile surface -- so on website/webapp it is always the
        # wrong half of the pair, silently substituting a neutral Material blur
        # (or `none`, on a border-strategy theme) for the theme's own shadow.
        # Confirmed live: one theme's website and webapp used it exclusively,
        # 70 references against zero to --tf-shadow-*, so its signature
        # zero-blur hard offset never rendered on either surface.
        if surface in ("website", "webapp"):
            elev_uses = len(re.findall(r"var\(\s*--tf-elev-", _COMMENT_RE.sub("", css_text)))
            if elev_uses:
                findings.append({
                    "check": "tokens.android_elevation_on_web",
                    "surface": surface,
                    "uses": elev_uses,
                    "severity": "high",
                    "message": (
                        "%s.css references --tf-elev-* %d time(s). That family is the "
                        "synthesized ANDROID elevation and only means anything inside the "
                        "mobile device frame; on a web surface it silently replaces this "
                        "theme's own shadow with a neutral blur, or with `none` when the "
                        "theme's Android strategy is a border. Use --tf-shadow-<level>, "
                        "which is elevation.levels.<level>.css verbatim."
                        % (surface, elev_uses)
                    ),
                })

        # Only the mobile surface is scoped to .screen-pane, which is the sole
        # case where the device-frame class sits outside the scope root.
        if surface == "mobile":
            for sel, n in sorted(scan_scoped_selectors(css_text).items(),
                                 key=lambda kv: -kv[1]):
                findings.append({
                    "check": "tokens.unmatchable_scoped_selector",
                    "surface": surface,
                    "selector": sel,
                    "uses": n,
                    "severity": "high",
                    "message": (
                        "`%s` starts with the device-frame class, which is an ANCESTOR "
                        "of this stylesheet's @scope root (.screen-pane). Inside "
                        "@scope it is read as `:scope %s` and matches nothing, so this "
                        "rule is inert and the iOS/Android treatments render "
                        "identically. Rewrite it with the platform condition attached "
                        "to an in-scope subject -- `.your-class:where(%s *)` -- or name "
                        ":scope explicitly (`%s :scope .your-class`)."
                        % (sel, sel, sel.split()[0], sel.split()[0])
                    ),
                })

    return {
        "ok": True,
        "theme": theme_dir.name,
        "surfaces_checked": checked,
        "emitted_count": len(defined),
        "finding_count": len(findings),
        "findings": findings,
        "notes": notes,
    }


def _selftest() -> int:
    fake_defined = {"--tf-bg", "--tf-text"}

    css_dead = ".a { color: var(--tf-nope); }"
    r = scan_css(css_dead, fake_defined)
    assert r["dead"] == {"--tf-nope": 1}, r
    assert r["fallback"] == {}, r

    css_fallback = ".a { border-width: var(--tf-nope, 2px); }"
    r = scan_css(css_fallback, fake_defined)
    assert r["dead"] == {}, r
    assert r["fallback"] == {"--tf-nope": 1}, r

    # defined locally in the same sheet -> not a finding
    css_local = ".a { --tf-mine: 4px; } .b { gap: var(--tf-mine); }"
    r = scan_css(css_local, fake_defined)
    assert r["dead"] == {}, r

    # emitted by the gallery -> not a finding
    r = scan_css(".a { color: var(--tf-text); }", fake_defined)
    assert r["dead"] == {}, r

    # a token named only in a comment is neither a definition nor a use
    r = scan_css("/* --tf-ghost: nope; var(--tf-ghost) */ .a { color: red; }", fake_defined)
    assert r["dead"] == {} and r["fallback"] == {}, r

    # a commented-out definition must NOT rescue a real use
    r = scan_css("/* --tf-ghost: 1px; */ .a { gap: var(--tf-ghost); }", fake_defined)
    assert r["dead"] == {"--tf-ghost": 1}, r

    # repeated uses are counted, whitespace inside var() tolerated
    r = scan_css(".a{gap:var( --tf-x )}.b{gap:var(--tf-x)}", fake_defined)
    assert r["dead"] == {"--tf-x": 2}, r

    # --- unmatchable scoped selectors (mobile) ---------------------------
    # leftmost .device compound, no :scope -> inert once @scope'd
    bad = scan_scoped_selectors(".device.android .card { box-shadow: none; }")
    assert bad == {".device.android .card": 1}, bad

    # the two working forms must NOT be flagged
    assert scan_scoped_selectors(".card:where(.device.android *) { color: red; }") == {}
    assert scan_scoped_selectors(".device.android :scope .card { color: red; }") == {}

    # a selector merely CONTAINING .device later is not leftmost -> fine
    assert scan_scoped_selectors(".card .device-note { color: red; }") == {}

    # comma-separated: only the offending branch is flagged
    bad = scan_scoped_selectors(".device.ios .a, .b:where(.device.ios *) { gap: 0; }")
    assert bad == {".device.ios .a": 1}, bad

    # commented-out rules are not flagged
    assert scan_scoped_selectors("/* .device.ios .a { gap: 0 } */ .b { gap: 0 }") == {}

    print("tf_tokens selftest: ok", file=sys.stderr)
    return 0


def main(argv: list) -> int:
    if "--selftest" in argv:
        return _selftest()

    want_json = "--json" in argv

    only_surface = None
    if "--surface" in argv:
        i = argv.index("--surface")
        if i + 1 < len(argv):
            only_surface = argv[i + 1]
            if only_surface not in SURFACES:
                print(json.dumps({"ok": False, "error": "unknown surface %r" % only_surface}))
                return 1

    targets = []
    if "--all" in argv:
        themes_root = Path(tf_paths.resolve(create=False).current) / "themes"
        if not themes_root.is_dir():
            print(json.dumps({"ok": False, "error": "no themes dir at %s" % themes_root}))
            return 1
        targets = [d for d in sorted(themes_root.iterdir()) if (d / "theme.json").is_file()]
    elif "--theme" in argv:
        i = argv.index("--theme")
        if i + 1 < len(argv):
            targets = [Path(argv[i + 1])]
    if not targets:
        print(json.dumps({"ok": False, "error": "pass --theme <dir> or --all"}))
        return 1

    results = [check_theme(t, only_surface) for t in targets]
    bad = [r for r in results if not r.get("ok")]
    if bad:
        print(json.dumps({"ok": False, "error": bad[0].get("error"), "results": results}))
        return 1

    total = sum(r["finding_count"] for r in results)
    out = {
        "ok": True,
        "theme_count": len(results),
        "finding_count": total,
        "results": results,
    }
    if want_json:
        print(json.dumps(out))
    else:
        for r in results:
            if r["finding_count"]:
                sys.stderr.write("%s: %d finding(s)\n" % (r["theme"], r["finding_count"]))
                for f in r["findings"]:
                    # each check names its subject under a different key
                    subject = f.get("property") or f.get("selector") or f["check"]
                    sys.stderr.write("  %-40s %-8s x%d  [%s]\n" % (
                        subject[:40], f["surface"], f["uses"], f["check"]))
        sys.stderr.write("tf_tokens: %d finding(s) across %d theme(s)\n" % (total, len(results)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": "unhandled: %s" % exc}))
        sys.exit(2)
