#!/usr/bin/env python3
"""tf_content.py -- content-completeness gate for a theme's authored surfaces.

Before the bespoke-composition rewrite (2026-09-03), `tf_gallery.py` aborted
assembly if any `{{SC_*}}` token in the shared partial templates went
unsubstituted -- a check that only proved every named slot in someone else's
template got *some* string. It never proved the rendered page actually had a
footer, a non-empty heading, or an error state; it only proved a string was
present somewhere in the file.

Now that each theme authors its own `surfaces/<surface>.html`, there is no
fixed slot list to check token-by-token. This script checks structural
presence instead, using the `data-tf-role` semantic-hook contract (see
skills/generate-themes/references/semantic-hooks.md) -- strictly stronger
than the old check, because it proves the actual element exists and is
non-empty, not that a placeholder string was filled in.

Website, webapp, and mobile checks are all live (Phases 1-3 of the
implementation plan).

Usage:
    python3 tf_content.py --theme <dir> --json [--surface website]
    python3 tf_content.py --selftest

Exit 0 on success (findings do not change exit code -- caller decides
severity). Exit 1 on expected failure (missing files, bad args). Exit 2 on
unexpected error.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import tf_htmlshape as shape  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import tf_htmlshape as shape


def _has_nonempty_text(nodes, index) -> bool:
    """True if the node at *index* has any non-whitespace text anywhere in its
    subtree -- not just direct text. A CTA/heading whose label sits inside a
    child <span> (a completely normal, accessible pattern) is not empty."""
    return bool(shape.text_content(nodes, index).strip())


_DOC_WRAPPER_RE = re.compile(r"<!DOCTYPE\s+html|<html\b|<head\b|<body\b", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _check_document_wrapper(html: str) -> list[dict]:
    """A surface file is a bare markup FRAGMENT by contract (see
    agents/surface-composer.md) -- no <!DOCTYPE>, <html>, <head>, or <body>.
    tf_gallery.py defensively strips a wrapper if it finds one (so a run
    doesn't visibly break), but that strip happens silently at final assembly,
    long after this theme's own surface-composer invocation has ended -- the
    agent that made the mistake never finds out, and the discarded <head>
    content (any per-file <style> shim, stray <link>) is just gone. Confirmed
    live: 13 of 18 surface files in one real run shipped a full document, and
    one dark-court theme's toggle state leaked a stray attribute onto the
    REAL page <html> element because of it (HTML5's parser merges a nested
    <html> tag's attributes onto the existing root). Catching it here, at the
    same content-completeness gate surface-composer already self-validates
    against, turns a silent tf_gallery.py workaround into an immediate,
    attributable finding. Comments are stripped before matching -- a file
    correctly documenting its own compliance in a comment (e.g. "no <html>/
    <head>/<body> here") must not trip the very check it's confirming it
    passes; matching raw text would flag the explanation, not a real tag."""
    if _DOC_WRAPPER_RE.search(_HTML_COMMENT_RE.sub("", html)):
        return [{
            "check": "surface.document_wrapper",
            "message": "This file contains a <!DOCTYPE>/<html>/<head>/<body> tag. A surface "
                       "file must be a bare markup fragment (no document wrapper) -- see "
                       "agents/surface-composer.md. tf_gallery.py will strip the wrapper at "
                       "assembly time regardless, but any <head> content (styles, links) is "
                       "discarded silently when it does, and a stray <html ...> attribute can "
                       "leak onto the real assembled page's root element.",
        }]
    return []


def check_website(html: str) -> list[dict]:
    """Structural-presence checks for the website surface. Returns a list of
    finding dicts (empty if everything required is present)."""
    findings: list[dict] = _check_document_wrapper(html)
    nodes = shape.parse(html)

    h1s = [n for i, n in enumerate(nodes) if n.tag == "h1" and _has_nonempty_text(nodes, i)]
    if not h1s:
        findings.append({
            "check": "website.h1",
            "message": "No non-empty <h1> found. Every website surface needs one real, "
                       "non-empty top-level heading.",
        })

    section_count = shape.count_sections(nodes)
    if section_count < 4:
        findings.append({
            "check": "website.section_count",
            "message": f"Only {section_count} distinct top-level content section(s) found "
                       "(need >= 4). A section is a landmark element or role='region', not "
                       "a plain <div> wrapper.",
        })

    footers = shape.find_by_role(nodes, "site-footer")
    if not footers:
        findings.append({
            "check": "website.footer",
            "message": "No element carrying data-tf-role=\"site-footer\" found. See "
                       "skills/generate-themes/references/semantic-hooks.md.",
        })

    by_index = {id(n): i for i, n in enumerate(nodes)}
    ctas = [n for n in shape.find_by_role(nodes, "primary-cta")
            if _has_nonempty_text(nodes, by_index[id(n)])]
    if not ctas:
        findings.append({
            "check": "website.primary_cta",
            "message": "No non-empty element carrying data-tf-role=\"primary-cta\" found.",
        })

    return findings


_INPUT_LIKE_TAGS = frozenset({"input", "textarea", "select"})


def check_webapp(html: str) -> list[dict]:
    """Structural-presence checks for the webapp surface. Returns a list of
    finding dicts (empty if everything required is present). Mirrors the
    per-surface floor documented in agents/surface-composer.md."""
    findings: list[dict] = _check_document_wrapper(html)
    nodes = shape.parse(html)
    by_index = {id(n): i for i, n in enumerate(nodes)}

    displays = [n for n in shape.find_by_role(nodes, "data-display")]
    if not displays:
        findings.append({
            "check": "webapp.data_display",
            "message": "No element carrying data-tf-role=\"data-display\" found. A table, "
                       "chart, or prominent stat is required.",
        })

    forms = [n for n in nodes if n.tag == "form"]
    form_has_input = False
    if forms:
        form_indices = {by_index[id(n)] for n in forms}
        for n in nodes:
            if n.tag not in _INPUT_LIKE_TAGS:
                continue
            p = n.parent
            while p != -1:
                if p in form_indices:
                    form_has_input = True
                    break
                p = nodes[p].parent
            if form_has_input:
                break
    if not forms or not form_has_input:
        findings.append({
            "check": "webapp.form",
            "message": "No <form> with at least one real input (input/textarea/select) found.",
        })

    for role in ("empty-state", "loading-state", "error-state"):
        if not shape.find_by_role(nodes, role):
            findings.append({
                "check": f"webapp.{role.replace('-', '_')}",
                "message": f"No element carrying data-tf-role=\"{role}\" found. This is a "
                           "real product state, not decoration -- see "
                           "skills/generate-themes/references/semantic-hooks.md.",
            })

    return findings


_PLACEHOLDER_SCREEN_RE = re.compile(r"^\d+$")


def check_mobile(html: str) -> list[dict]:
    """Structural-presence checks for the mobile surface. Returns a list of
    finding dicts (empty if everything required is present). Mirrors the
    per-surface floor documented in agents/surface-composer.md."""
    findings: list[dict] = _check_document_wrapper(html)
    nodes = shape.parse(html)
    screen_names = shape.screens(nodes)

    if len(screen_names) < 4:
        findings.append({
            "check": "mobile.screen_count",
            "message": f"Only {len(screen_names)} distinct data-screen element(s) found "
                       "(need >= 4). Each screen needs its own data-screen=\"<name>\" attribute.",
        })

    placeholder_names = [n for n in screen_names if _PLACEHOLDER_SCREEN_RE.match(n)]
    if placeholder_names:
        findings.append({
            "check": "mobile.placeholder_screen_names",
            "message": "data-screen value(s) %s are bare numbers, not descriptive names -- "
                       "use short descriptive names (e.g. data-screen=\"onboarding\") per "
                       "skills/generate-themes/references/semantic-hooks.md." % ", ".join(placeholder_names),
        })

    return findings


_CHECKS = {
    "website": check_website,
    "webapp": check_webapp,
    "mobile": check_mobile,
}


def check_theme(theme_dir: Path, surfaces: tuple[str, ...] = ("website", "webapp", "mobile")) -> dict:
    """Exit-free, importable entry point. Returns {"ok", "findings", "skipped"}."""
    findings: list[dict] = []
    skipped: list[str] = []

    for surface in surfaces:
        checker = _CHECKS.get(surface)
        if checker is None:
            skipped.append(f"{surface} (no content-completeness check defined yet)")
            continue
        html_path = theme_dir / "surfaces" / f"{surface}.html"
        if not html_path.is_file():
            skipped.append(f"{surface} (no surfaces/{surface}.html yet)")
            continue
        try:
            html = html_path.read_text(encoding="utf-8")
        except OSError as exc:
            skipped.append(f"{surface} (unreadable: {exc})")
            continue
        for f in checker(html):
            f["surface"] = surface
            findings.append(f)

    return {"ok": len(findings) == 0, "findings": findings, "skipped": skipped}


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        test = {"ok": True, "selftest": True}
        assert json.loads(json.dumps(test)) == test
        complete_html = (
            '<h1>Real Headline</h1>'
            '<div role="region"><h2>A</h2></div><div role="region"><h2>B</h2></div>'
            '<div role="region"><h2>C</h2></div><div role="region"><h2>D</h2></div>'
            '<button data-tf-role="primary-cta">Go</button>'
            '<footer data-tf-role="site-footer">footer</footer>'
        )
        assert check_website(complete_html) == [], check_website(complete_html)
        incomplete_html = "<div>nothing here</div>"
        findings = check_website(incomplete_html)
        assert len(findings) == 4, findings  # h1, section_count, footer, primary_cta all missing

        complete_webapp_html = (
            '<div data-tf-role="data-display">table</div>'
            '<form><input type="text"></form>'
            '<div data-tf-role="empty-state">nothing yet</div>'
            '<div data-tf-role="loading-state">loading</div>'
            '<div data-tf-role="error-state">failed</div>'
        )
        assert check_webapp(complete_webapp_html) == [], check_webapp(complete_webapp_html)
        incomplete_webapp_html = "<div>nothing here</div>"
        webapp_findings = check_webapp(incomplete_webapp_html)
        assert len(webapp_findings) == 5, webapp_findings  # data_display, form, 3 states
        # form present but with no real input still fails the form check
        form_no_input_html = '<form><button>Submit</button></form>'
        assert any(f["check"] == "webapp.form" for f in check_webapp(form_no_input_html))

        complete_mobile_html = (
            '<div data-screen="onboarding">a</div>'
            '<div data-screen="home">b</div>'
            '<div data-screen="detail">c</div>'
            '<div data-screen="settings">d</div>'
        )
        assert check_mobile(complete_mobile_html) == [], check_mobile(complete_mobile_html)
        incomplete_mobile_html = '<div data-screen="1">a</div><div data-screen="2">b</div>'
        mobile_findings = check_mobile(incomplete_mobile_html)
        assert len(mobile_findings) == 2, mobile_findings  # screen_count, placeholder_names
        sys.stderr.write("selftest OK\n")
        print(json.dumps(test))
        return 0

    want_json = "--json" in argv
    if not want_json:
        print(json.dumps({"ok": False, "error": "pass --json to get structured output"}))
        return 1

    theme_dir: Path | None = None
    surfaces: tuple[str, ...] = ("website", "webapp", "mobile")
    i = 0
    while i < len(argv):
        if argv[i] == "--theme" and i + 1 < len(argv):
            theme_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--surface" and i + 1 < len(argv):
            surfaces = (argv[i + 1],); i += 2
        else:
            i += 1

    if theme_dir is None:
        print(json.dumps({"ok": False, "error": "--theme <dir> required"}))
        return 1
    if not theme_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"theme dir not found: {theme_dir}"}))
        return 1

    result = check_theme(theme_dir, surfaces)
    for f in result["findings"]:
        sys.stderr.write(f"tf_content: [{f['surface']}] {f['message']}\n")
    if result["skipped"]:
        sys.stderr.write("tf_content: skipped: %s\n" % ", ".join(result["skipped"]))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"unhandled: {exc}"}))
        sys.exit(2)
