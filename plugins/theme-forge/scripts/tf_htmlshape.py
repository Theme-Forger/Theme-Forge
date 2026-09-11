#!/usr/bin/env python3
"""tf_htmlshape.py -- shared structural-parsing primitives for HTML that no
longer comes from a shared template.

Before the bespoke-composition rewrite (2026-09-03), several tf_slop.py rules
and the old distinctiveness gate could assume every theme's markup came from
the same fixed partial library — e.g. "count literal <section> tags" was a
safe proxy for "count content sections" because every theme's sections were
literally <section> elements from templates/preview.partials.html. Once each
theme authors its own bespoke HTML, that assumption breaks: a theme might
structure its page with <div role="region">, <article>, or something else
entirely, and a literal-tag count would silently under-count (not crash) on
it. This module provides tag-agnostic, structure-based primitives so a rule
degrades gracefully across genuinely different bespoke markup instead of
silently trusting one convention.

Used by: scripts/tf_structure.py (Gate 18, structural-distinctiveness),
scripts/tf_slop.py (rules 21 eyebrow-density, 22 section-number-eyebrows).

Standard library only. Python 3.9+.
"""
from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# Minimal DOM tree -- stdlib has no queryable tree, so build just enough of
# one: an ordered list of nodes, each knowing its tag, attrs, depth, and
# parent index. Good enough for the structural signals this module computes;
# not a general-purpose HTML parser.
# ---------------------------------------------------------------------------

class _Node:
    __slots__ = ("tag", "attrs", "depth", "parent", "text")

    def __init__(self, tag: str, attrs: dict, depth: int, parent: int):
        self.tag = tag
        self.attrs = attrs
        self.depth = depth
        self.parent = parent
        self.text = ""  # direct text content only, appended as encountered


# Void elements never receive a matching end tag; the parser must not push
# them onto the open-element stack or every subsequent depth count is wrong.
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})

_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

# Tags that plausibly delimit a "logical section" of page content, regardless
# of which specific one a bespoke theme reaches for. Deliberately broad --
# under-matching (missing real sections) is worse for a distinctiveness/
# density signal than over-matching a few generic wrapping divs would be,
# so a role/aria attribute check is included alongside the tag check.
_SECTION_LIKE_TAGS = frozenset({"section", "header", "footer", "article", "aside"})
_SECTION_LIKE_ROLES = frozenset({"region", "banner", "contentinfo", "complementary"})


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[_Node] = []
        self._stack: list[int] = []  # indices into self.nodes

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = dict(attrs_list)
        depth = len(self._stack)
        parent = self._stack[-1] if self._stack else -1
        self.nodes.append(_Node(tag, attrs, depth, parent))
        if tag not in _VOID_TAGS:
            self._stack.append(len(self.nodes) - 1)

    def handle_startendtag(self, tag: str, attrs_list) -> None:
        # Explicit self-closing form (<img/>) -- do not push, matches handle_starttag's void handling.
        attrs = dict(attrs_list)
        depth = len(self._stack)
        parent = self._stack[-1] if self._stack else -1
        self.nodes.append(_Node(tag, attrs, depth, parent))

    def handle_endtag(self, tag: str) -> None:
        # Pop back to (and including) the matching open tag if found; tolerate
        # unbalanced/misnested markup rather than raising, since this module
        # must never crash a gate on real-world-messy authored HTML.
        for i in range(len(self._stack) - 1, -1, -1):
            if self.nodes[self._stack[i]].tag == tag:
                del self._stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if self._stack and data.strip():
            self.nodes[self._stack[-1]].text += data


def parse(html: str) -> list[_Node]:
    """Parse *html* into a flat, depth-annotated node list. Never raises on
    malformed input -- returns whatever was parsed before any failure."""
    builder = _TreeBuilder()
    try:
        builder.feed(html)
    except Exception:  # noqa: BLE001 -- best-effort on hand-authored HTML
        pass
    return builder.nodes


# ---------------------------------------------------------------------------
# Structural signals
# ---------------------------------------------------------------------------

def text_content(nodes: list["_Node"], index: int) -> str:
    """Full text content of the node at *index*, including all descendants --
    mirrors DOM `textContent`, unlike `_Node.text` (direct text only). Needed
    anywhere a node's real text matters more than whether it happens to be a
    leaf: `<a><span>Label</span></a>` is a completely normal, accessible
    pattern and must not read as empty just because the label sits one level
    down. Nodes are a flat pre-order list, so descendants of `nodes[index]`
    are exactly the contiguous run after it whose depth exceeds its own."""
    node = nodes[index]
    parts = [node.text]
    for n in nodes[index + 1:]:
        if n.depth <= node.depth:
            break
        if n.text:
            parts.append(n.text)
    return "".join(parts)


def heading_sequence(nodes: list["_Node"]) -> list[str]:
    """Ordered list of heading tags in document order -- the outline shape."""
    return [n.tag for n in nodes if n.tag in _HEADING_TAGS]


def count_sections(nodes: list["_Node"]) -> int:
    """Structural section count: tag-agnostic, matches _SECTION_LIKE_TAGS or
    an ARIA/role landmark, at any depth <= 3 from the surface root (so a
    deeply nested unrelated <article> inside a card grid doesn't inflate the
    count). Replaces a literal '<section>' count, which silently returns 0
    (and no-ops the calling rule) on any theme that doesn't use that tag."""
    count = 0
    for n in nodes:
        if n.depth > 3:
            continue
        if n.tag in _SECTION_LIKE_TAGS:
            count += 1
            continue
        role = (n.attrs.get("role") or "").strip().lower()
        if role in _SECTION_LIKE_ROLES:
            count += 1
    return count


def dom_depth_histogram(nodes: list["_Node"]) -> Counter:
    """Bucketed nesting-depth histogram of leaf text-bearing nodes -- a cheap
    proxy for how deeply this surface nests its content."""
    hist: Counter = Counter()
    for n in nodes:
        if n.text.strip():
            hist[n.depth] += 1
    return hist


def container_tag_profile(nodes: list["_Node"]) -> Counter:
    """Normalized frequency vector over structural container tags."""
    tags = ("div", "section", "article", "nav", "header", "footer", "ul", "li",
            "table", "form", "aside", "main")
    return Counter(n.tag for n in nodes if n.tag in tags)


_CLASS_WORD_RE = re.compile(r"[a-zA-Z]+")


def class_name_shingles(nodes: list["_Node"]) -> set[str]:
    """Shingle set of class-name word-fragments (split on '-'/'_'), not the
    literal class strings -- bespoke themes are expected to use different
    literal names for the same underlying shape (e.g. 'hero-split' vs
    'split-hero-band'), so comparing literal names would find nothing even
    when two themes converge on the same structure. Fragment overlap catches
    that convergence; numbers/short noise fragments (<3 chars) are dropped."""
    shingles: set[str] = set()
    for n in nodes:
        cls = n.attrs.get("class") or ""
        for token in cls.split():
            for word in _CLASS_WORD_RE.findall(token.lower()):
                if len(word) >= 3:
                    shingles.add(word)
    return shingles


_GRID_TEMPLATE_RE = re.compile(r"grid-template-columns\s*:\s*([^;}{]+)", re.IGNORECASE)
_DISPLAY_GRID_RE = re.compile(r"display\s*:\s*grid\b", re.IGNORECASE)
_DISPLAY_FLEX_RE = re.compile(r"display\s*:\s*flex\b", re.IGNORECASE)


def layout_mode_ratio(css: str) -> dict[str, int]:
    """Count of display:grid vs display:flex declarations in *css* -- a
    coarse signal for which layout mechanism a theme leans on."""
    return {
        "grid": len(_DISPLAY_GRID_RE.findall(css)),
        "flex": len(_DISPLAY_FLEX_RE.findall(css)),
    }


def grid_track_signature(css: str) -> Counter:
    """Multiset of track-count values from every grid-template-columns
    declaration (e.g. 'repeat(3, 1fr)' -> 3, '1fr 2fr' -> 2)."""
    sig: Counter = Counter()
    for m in _GRID_TEMPLATE_RE.finditer(css):
        value = m.group(1).strip()
        repeat_m = re.match(r"repeat\(\s*(\d+)\s*,", value)
        if repeat_m:
            sig[int(repeat_m.group(1))] += 1
            continue
        # Fall back to counting whitespace-separated track tokens.
        tracks = [t for t in value.split() if t]
        if tracks:
            sig[len(tracks)] += 1
    return sig


def screens(nodes: list["_Node"]) -> list[str]:
    """Mobile only: distinct data-screen attribute values, in document order,
    de-duplicated while preserving first-seen order."""
    seen: list[str] = []
    for n in nodes:
        val = n.attrs.get("data-screen")
        if val and val not in seen:
            seen.append(val)
    return seen


def find_by_role(nodes: list["_Node"], role: str) -> list["_Node"]:
    """Elements whose data-tf-role attribute equals *role* -- the semantic
    hook contract (see skills/generate-themes/references/semantic-hooks.md).
    Zero CSS/tag/layout implication; purely a machine-readable label."""
    return [n for n in nodes if (n.attrs.get("data-tf-role") or "") == role]


def find_by_role_suffix(nodes: list["_Node"], suffix: str) -> list["_Node"]:
    """Elements whose data-tf-role attribute ends with *suffix* (e.g. 'cta'
    matches both 'primary-cta' and 'secondary-cta')."""
    return [n for n in nodes if (n.attrs.get("data-tf-role") or "").endswith(suffix)]
