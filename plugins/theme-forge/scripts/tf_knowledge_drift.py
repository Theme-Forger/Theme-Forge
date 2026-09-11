#!/usr/bin/env python3
"""tf_knowledge_drift.py -- detect plugin-seed knowledge stranded outside the live base.

Theme Forge's design knowledge lives in two places that silently diverge:

    plugins/theme-forge/knowledge/   hand-authored seed (shipped with the plugin)
            |  tf_seed_knowledge.py -- SessionStart hook, COPY-IF-ABSENT
            v
    $TF_HOME/knowledge/              live base -- the ONLY copy agents read
            ^  design-researcher rewrites files here

tf_seed_knowledge.py never overwrites an existing live file, deliberately: a
refresh may have improved it. The consequence is that any edit to the plugin
seed made *after* a domain was first seeded is invisible to every agent,
forever, with nothing reporting it. That is how `06-motion.md` came to have
zero mentions of `motion_budget` -- a field theme.schema.json *requires* --
while the seed documented the policy in full.

This script reports seed paragraphs with no counterpart in the live file, and
classifies each one, because the two channels carry different kinds of truth:

  internal  References Theme Forge's own machinery (tf_*.py, theme.json fields,
            plugin policy, licence attribution). A web refresh cannot
            regenerate these, so the seed is authoritative and a gap here is a
            real defect -- an agent is being asked to honour a contract it
            cannot read.
  external  A claim about the outside world (library versions, browser support,
            licence terms). The refresh is newer and may have deliberately
            superseded it, so a gap here needs a human read, not a port.

Matching is deliberately lenient. A refresh rewrites prose freely, so
comparing text would report everything. Instead each seed paragraph is reduced
to its distinctive tokens -- code spans and identifiers, the parts a rewrite
tends to preserve verbatim -- and is only reported when most of those tokens
appear nowhere in the live file.

    python3 tf_knowledge_drift.py [--json] [--internal-only] [--domain <file>]
    python3 tf_knowledge_drift.py --selftest

Findings do not change the exit code -- the caller decides severity, same
convention as tf_slop.py and tf_schema_check.py. Exit 0 on success, 1 on
expected failure (missing directories, bad args), 2 on unexpected error.

Python 3.9+, standard library only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import tf_paths  # noqa: E402

# A paragraph shorter than this carries too little signal to judge.
_MIN_PARA_CHARS = 80

# Fraction of a paragraph's distinctive tokens that must be absent from the
# live file before it counts as stranded. Below 1.0 so that a refresh which
# reworded around one or two identifiers is not reported. Applied as a ratio
# with no absolute floor: a single-token paragraph whose one token is absent
# has lost all of its distinctive content and must still be reported.
_ABSENT_RATIO = 0.6

# Markers that make a paragraph a statement about Theme Forge itself rather
# than about the outside world.
_INTERNAL_MARKERS = re.compile(
    r"tf_[a-z_]+|theme\.json|theme\.schema\.json|\$TF_HOME|Theme Forge|"
    r"motion_budget|signature_type|design_language|platform_assets|"
    r"structural_brief|layout_signature|render_suspect|"
    r"design-critic|theme-designer|surface-composer|brand-asset-designer|"
    r"design-researcher|theme-applier|theme-fixer|"
    r"NOTICE|MIT License|Copyright"
)

# Code spans, dotted identifiers, and tf_* names: the tokens a rewrite keeps.
_TOKEN_RE = re.compile(r"`[^`\n]+`")
_IDENT_RE = re.compile(r"\btf_[a-z_]+\b|\b[a-z_]{3,}\.py\b|\b[a-z_]+\.[a-z]{2,3}\b")


def _paragraphs(text: str):
    """Yield (heading, paragraph) for each prose block, tracking its heading.

    Blank lines inside a fence do not split it, and a fence is re-attached to
    the sentence that introduces it. Both matter for detection: fenced content
    on its own rarely carries a token this script can match (a raw JSON example
    has no backticks), so an example separated from the prose naming it would
    be silently unmatchable and never reported as stranded.
    """
    heading = "(top)"
    buf: list[str] = []
    in_fence = False
    out = []

    def flush():
        if buf:
            para = "\n".join(buf).strip()
            if para:
                out.append((heading, para))
            buf.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if not in_fence and not buf and out and out[-1][0] == heading:
                # Re-attach: pull the introducing paragraph back into the buffer.
                buf.extend(out.pop()[1].splitlines())
            in_fence = not in_fence
            buf.append(line)
            continue
        if in_fence:
            buf.append(line)
            continue
        if line.startswith("#"):
            flush()
            heading = line.strip()
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)
    flush()
    return out


def _tokens(para: str) -> set:
    """Distinctive tokens: code spans plus bare identifiers."""
    toks = set(_TOKEN_RE.findall(para))
    toks |= set(_IDENT_RE.findall(para))
    # Strip the backticks for comparison; the live file may format differently.
    return {t.strip("`").strip() for t in toks if len(t.strip("`").strip()) > 2}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def compare_domain(seed_text: str, live_text: str):
    """Return findings for one domain: seed paragraphs stranded from live."""
    live = _normalise(live_text)
    findings = []
    for heading, para in _paragraphs(seed_text):
        if len(para) < _MIN_PARA_CHARS:
            continue
        toks = _tokens(para)
        if not toks:
            continue
        absent = sorted(t for t in toks if t not in live)
        if not absent or len(absent) < len(toks) * _ABSENT_RATIO:
            continue
        kind = "internal" if _INTERNAL_MARKERS.search(para) else "external"
        findings.append({
            "kind": kind,
            "seed_heading": heading,
            "absent_tokens": absent[:8],
            "token_count": len(toks),
            "excerpt": _normalise(para)[:200],
        })
    return findings


def scan(domain: str = "", internal_only: bool = False):
    paths = tf_paths.resolve(create=False)
    seed_dir = paths.plugin_knowledge
    live_dir = paths.knowledge

    if not seed_dir or not seed_dir.is_dir():
        return {"ok": False, "error": "plugin knowledge dir not found"}
    if not live_dir.is_dir():
        # Nothing seeded yet is not drift: the hook simply has not run.
        return {"ok": True, "domains": [], "total_findings": 0,
                "internal_findings": 0, "clean": True,
                "note": "live knowledge dir does not exist yet (nothing seeded)"}

    domains = []
    total = 0
    internal_total = 0
    for seed_file in sorted(seed_dir.glob("*.md")):
        if domain and seed_file.name != domain:
            continue
        live_file = live_dir / seed_file.name
        if not live_file.is_file():
            # The seed will be copied on the next SessionStart; not drift.
            domains.append({"domain": seed_file.name, "live_present": False,
                            "findings": []})
            continue
        try:
            findings = compare_domain(
                seed_file.read_text(encoding="utf-8", errors="replace"),
                live_file.read_text(encoding="utf-8", errors="replace"),
            )
        except OSError as exc:
            return {"ok": False, "error": "cannot read %s: %s" % (seed_file.name, exc)}
        if internal_only:
            findings = [f for f in findings if f["kind"] == "internal"]
        n_internal = sum(1 for f in findings if f["kind"] == "internal")
        total += len(findings)
        internal_total += n_internal
        if findings:
            domains.append({
                "domain": seed_file.name,
                "live_present": True,
                "seed_bytes": seed_file.stat().st_size,
                "live_bytes": live_file.stat().st_size,
                "findings": findings,
            })

    return {
        "ok": True,
        "seed_dir": str(seed_dir),
        "live_dir": str(live_dir),
        "domains": domains,
        "total_findings": total,
        "internal_findings": internal_total,
        # Only internal gaps make a run unclean: those are contracts an agent
        # cannot read. External gaps may be a deliberate supersede.
        "clean": internal_total == 0,
    }


def _selftest() -> int:
    seed = (
        "# Motion\n\n"
        "## Per-surface motion budget\n\n"
        "Declare `motion_budget` in theme.json with `near-imperceptible` for the "
        "webapp surface, because a dashboard is high-frequency by definition.\n\n"
        "## Libraries\n\n"
        "Motion is at `v13.1.1` and `@emotion/is-prop-valid` was removed as a "
        "peer dependency in the v13 line.\n\n"
        "## Shared\n\n"
        "Entrances decelerate using `cubic-bezier(0, 0, 0.2, 1)` on every "
        "surface without exception.\n"
    )
    live = (
        "# Motion\n\n## Libraries\n\nMotion sits at `v13.1.1`; note that "
        "`@emotion/is-prop-valid` is no longer an optional peer dependency.\n\n"
        "## Principles\n\nEntrances decelerate using `cubic-bezier(0, 0, 0.2, 1)`.\n"
    )

    findings = compare_domain(seed, live)
    kinds = {f["kind"] for f in findings}
    headings = [f["seed_heading"] for f in findings]

    # The motion_budget paragraph is stranded AND references internals.
    assert any("motion budget" in h.lower() for h in headings), headings
    assert "internal" in kinds, findings
    # The libraries paragraph was reworded but kept its tokens -> not a gap.
    assert not any("Libraries" in h for h in headings), headings
    # The shared paragraph is present verbatim -> not a gap.
    assert not any("Shared" in h for h in headings), headings

    # A paragraph with no distinctive tokens must never be reported.
    assert compare_domain("# H\n\n" + ("plain prose with no identifiers " * 5), "") == []

    # Fenced code stays attached to its paragraph rather than splitting.
    fenced = "# H\n\nUse `motion_budget` in theme.json:\n\n```json\n{\"a\": 1}\n```\n"
    paras = _paragraphs(fenced)
    assert len(paras) == 1, paras
    assert "```json" in paras[0][1], paras

    # An empty live file strands everything it should, and nothing more.
    all_gaps = compare_domain(seed, "")
    assert len(all_gaps) == 3, all_gaps

    # internal_only filtering.
    assert all(f["kind"] == "internal"
               for f in [g for g in all_gaps if g["kind"] == "internal"])

    sys.stderr.write("selftest OK\n")
    print(json.dumps({"ok": True, "selftest": True}))
    return 0


def main(argv: list) -> int:
    if "--selftest" in argv:
        return _selftest()

    want_json = "--json" in argv
    internal_only = "--internal-only" in argv
    domain = ""
    if "--domain" in argv:
        i = argv.index("--domain")
        if i + 1 >= len(argv):
            msg = "--domain requires a file name, e.g. 06-motion.md"
            sys.stderr.write("tf_knowledge_drift: %s\n" % msg)
            print(json.dumps({"ok": False, "error": msg}))
            return 1
        domain = argv[i + 1]

    result = scan(domain=domain, internal_only=internal_only)
    if not result.get("ok"):
        sys.stderr.write("tf_knowledge_drift: %s\n" % result.get("error"))
        print(json.dumps(result))
        return 1

    sys.stderr.write("\nKNOWLEDGE DRIFT — seed vs live\n")
    sys.stderr.write("─" * 70 + "\n")
    if result.get("note"):
        sys.stderr.write("  %s\n" % result["note"])
    for d in result["domains"]:
        if not d.get("live_present"):
            sys.stderr.write("  · %s — not seeded yet (hook will copy it)\n"
                             % d["domain"])
            continue
        sys.stderr.write("  %s  (seed %d b / live %d b)\n"
                         % (d["domain"], d["seed_bytes"], d["live_bytes"]))
        for f in d["findings"]:
            mark = "✗" if f["kind"] == "internal" else "·"
            sys.stderr.write("    %s [%s] under %s\n"
                             % (mark, f["kind"], f["seed_heading"]))
            sys.stderr.write("        absent: %s\n"
                             % ", ".join(f["absent_tokens"]))
    if result["total_findings"] == 0:
        sys.stderr.write("  ✓ no stranded seed content\n")
    else:
        sys.stderr.write(
            "\n  %d stranded paragraph(s); %d reference Theme Forge internals.\n"
            % (result["total_findings"], result["internal_findings"]))
        if result["internal_findings"]:
            sys.stderr.write(
                "  Internal gaps are defects: agents read only the live copy, so\n"
                "  edit $TF_HOME/knowledge/<domain>.md to land them. Do NOT run\n"
                "  tf_seed_knowledge.py --force -- it discards researched content.\n")
    sys.stderr.write("─" * 70 + "\n")

    print(json.dumps(result, indent=2 if want_json else None))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover - unexpected
        sys.stderr.write("tf_knowledge_drift: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
