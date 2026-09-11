#!/usr/bin/env python3
"""tf_assets.py -- fetch free-licensed assets from verified sources.

Theme Forge generates its own assets. This adds an optional sourced layer on
top, restricted to sources whose license and API terms were verified in
knowledge/14-asset-sources.md. It never becomes a dependency: with no network,
no key, or no suitable asset, every fetcher returns empty and the caller keeps
its generated geometric assets plus ART-DIRECTION.md.

Three rules shape the whole design.

1. LICENSE ENFORCEMENT, NOT TRACKING. A default run may only touch sources that
   impose no visible-credit obligation. Attribution-required sources are opt-in
   per run (--allow-attribution). This is enforced before a request is made,
   not audited afterwards, because the failure mode being prevented is somebody
   discovering an obligation after shipping.

   The trap this guards against: an asset's license and its API's terms are
   different documents. Poly Haven's assets are CC0 -- "You do not need to give
   credit" -- while its API ToS section 2.5 requires a "Powered by Poly Haven"
   credit for content surfaced *via the live API*. We therefore download and
   vendor the CC0 file rather than hotlink it, which leaves only the asset
   license in play. Same shape for Pexels and Pixabay.

2. PROVENANCE PER ASSET. Every fetched file gets an entry recording provider,
   source URL, license, whether attribution is required, the exact attribution
   text, and the fetch date. Written next to the assets, not held in memory.

3. THE FALLBACK STAYS. Failure is not an error. Every entry point returns
   ok:true with an empty result and a stated reason.

    python3 tf_assets.py --theme <dir> [--tiers video,font,pattern,texture]
                         [--query <term>] [--allow-attribution] [--json]
    python3 tf_assets.py --selftest

Python 3.9+, standard library only. Exit 0/1/2.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

# Poly Haven API ToS 2.4: "All API calls must be made with a unique 'Referer'
# header or user-agent that matches your software name." Sent on every request,
# not just theirs -- an identifiable UA is good manners to any free service.
USER_AGENT = "ThemeForge/1.0 (+https://github.com/theme-forge) asset-fetcher"

_TIMEOUT = 25

# Binary downloads get a shorter leash than metadata calls. A corporate filter
# usually *blackholes* a blocked host rather than refusing it, so the socket
# hangs for the full timeout instead of erroring immediately.
# dl.polyhaven.org is blocked on at least one network this runs on.
_DL_TIMEOUT = 12

# Never examine more than this many candidates from a provider listing. Poly
# Haven returns 858 textures; without a cap, a provider whose download host is
# unreachable would be retried 858 times at _DL_TIMEOUT each.
_MAX_CANDIDATES = 12

# Consecutive unreachable downloads that mean "the host is gone", not "this
# asset is bad". Distinguishing the two is what stops a blocked CDN from
# looking like 858 individually broken files.
_UNREACHABLE_STREAK = 3

# ---------------------------------------------------------------------------
# License policy
# ---------------------------------------------------------------------------

# Three tiers, because "attribution" conflates two different obligations.
#
#   attribution_free  Nothing is owed. CC0, Unlicense, and the Pexels License.
#   notice_only       The license text must travel with a redistributed copy,
#                     but no user-visible credit is required. MIT, OFL, Apache.
#                     Allowed on a default run; satisfied by a LICENSES.md in
#                     the theme, and deliberately does NOT populate
#                     licensing.notices, which is for visible credits.
#   attribution_req   A human-visible credit is required. CC-BY and friends.
#                     Opt-in only; populates licensing.notices, which makes the
#                     gallery render credits and THEME.md carry them.
LICENSE_TIERS = {
    "CC0-1.0":      "attribution_free",
    "CC0":          "attribution_free",
    "Unlicense":    "attribution_free",
    "Pexels":       "attribution_free",
    "MIT":          "notice_only",
    "OFL-1.1":      "notice_only",
    "Apache-2.0":   "notice_only",
    "BSD-3-Clause": "notice_only",
    "CC-BY-4.0":    "attribution_req",
    "CC-BY-3.0":    "attribution_req",
}

# Share-alike infects an exported theme: a derivative must carry the same
# license, which Theme Forge cannot promise on the user's behalf. Never allowed,
# not even opt-in. Same for non-commercial and no-derivatives.
LICENSE_FORBIDDEN = {
    "CC-BY-SA-4.0", "CC-BY-SA-3.0", "CC-BY-NC-4.0", "CC-BY-ND-4.0",
    "GPL-3.0", "AGPL-3.0", "LottieSimpleLicense",
}

DEFAULT_ALLOWED_TIERS = ("attribution_free", "notice_only")


def classify_license(spdx: str) -> str:
    """Map an SPDX-ish id to a policy tier. Unknown is treated as forbidden.

    Defaulting unknown to forbidden rather than permitted is the whole point:
    an unrecognised license is exactly the case where nobody has checked what
    it obliges, and that is the discovery-after-shipping scenario.
    """
    if not spdx:
        return "forbidden"
    key = spdx.strip()
    if key in LICENSE_FORBIDDEN:
        return "forbidden"
    return LICENSE_TIERS.get(key, "forbidden")


def license_allowed(spdx: str, allow_attribution: bool = False) -> tuple[bool, str]:
    tier = classify_license(spdx)
    if tier == "forbidden":
        return False, "license %r is not on the allowlist" % spdx
    if tier == "attribution_req" and not allow_attribution:
        return False, ("license %r requires visible attribution; rerun with "
                       "--allow-attribution to opt in" % spdx)
    return True, tier


# ---------------------------------------------------------------------------
# In-band license metadata (DiceBear and any Dublin Core producer)
# ---------------------------------------------------------------------------

_DCTERMS_RE = re.compile(r"<dcterms:license>\s*([^<\s]+)\s*</dcterms:license>", re.I)
_DCRIGHTS_RE = re.compile(r"<dc:rights>\s*(.*?)\s*</dc:rights>", re.I | re.S)
_DCCREATOR_RE = re.compile(r"<dc:creator>\s*(.*?)\s*</dc:creator>", re.I | re.S)

_LICENSE_URL_TO_SPDX = [
    ("publicdomain/zero", "CC0-1.0"),
    ("licenses/by-sa/", "CC-BY-SA-4.0"),
    ("licenses/by-nc/", "CC-BY-NC-4.0"),
    ("licenses/by-nd/", "CC-BY-ND-4.0"),
    ("licenses/by/", "CC-BY-4.0"),
    ("opensource.org/licenses/mit", "MIT"),
]


def license_from_svg(svg_text: str) -> dict:
    """Read license/creator/rights from an SVG's Dublin Core metadata block.

    DiceBear embeds this in every SVG response, so the license travels *with*
    the asset instead of relying on a hardcoded style->license table that can
    silently drift from upstream. Two hazards make this fragile if used
    carelessly, and both are real:

      - `?format=png` responses carry no metadata at all.
      - An SVG minifier deletes <metadata>. svgo's preset-default includes
        removeMetadata, so tf_optimize.py must run with that plugin disabled
        (it does) or this record is destroyed before anyone reads it.

    Returns {} when nothing is present -- absence is not CC0, and the caller
    must not treat it as such.
    """
    out: dict = {}
    m = _DCTERMS_RE.search(svg_text)
    if m:
        url = m.group(1).strip()
        out["license_url"] = url
        low = url.lower()
        for frag, spdx in _LICENSE_URL_TO_SPDX:
            if frag in low:
                out["license"] = spdx
                break
    m = _DCRIGHTS_RE.search(svg_text)
    if m:
        out["attribution_text"] = re.sub(r"\s+", " ", m.group(1)).strip()
    m = _DCCREATOR_RE.search(svg_text)
    if m:
        out["creator"] = re.sub(r"\s+", " ", m.group(1)).strip()
    return out


# ---------------------------------------------------------------------------
# HTTP helpers -- every failure is a return value, never an exception
# ---------------------------------------------------------------------------

def _request(url: str, headers: dict | None = None):
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, headers=hdrs)


def http_json(url: str, headers: dict | None = None):
    try:
        with urllib.request.urlopen(_request(url, headers), timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return None, "unreachable: %s" % type(e).__name__
    except (json.JSONDecodeError, ValueError):
        return None, "malformed JSON"


def http_bytes(url: str, headers: dict | None = None, max_bytes: int = 0,
               timeout: int = _DL_TIMEOUT):
    """Download with a hard size ceiling, enforced while reading.

    The ceiling is checked during the read rather than from Content-Length: a
    missing or lying header would otherwise let a 400 MB HDRI into a gallery
    that has to stay openable as a single file.
    """
    try:
        with urllib.request.urlopen(_request(url, headers), timeout=timeout) as r:
            if max_bytes:
                buf = r.read(max_bytes + 1)
                if len(buf) > max_bytes:
                    return None, "exceeds %d byte ceiling" % max_bytes
                return buf, None
            return r.read(), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        return None, "unreachable: %s" % type(e).__name__


def network_up() -> bool:
    try:
        s = socket.create_connection(("1.1.1.1", 53), timeout=3)
        s.close()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def provenance_entry(path: Path, provider: str, source_url: str, spdx: str,
                     tier: str, blob: bytes, attribution_text: str = "",
                     extra: dict | None = None) -> dict:
    entry = {
        "path": path.name,
        "provider": provider,
        "source_url": source_url,
        "license": spdx,
        "license_tier": tier,
        "attribution_required": tier == "attribution_req",
        "attribution_text": attribution_text,
        "fetched_at": _now(),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    if extra:
        entry.update(extra)
    return entry


def write_provenance(theme_dir: Path, entries: list) -> Path:
    """Write the per-asset provenance manifest, merging with any prior run."""
    out = theme_dir / "assets" / "sourced" / "provenance.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if out.is_file():
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            existing = prev.get("assets", []) if isinstance(prev, dict) else []
        except (json.JSONDecodeError, OSError):
            existing = []
    by_path = {e.get("path"): e for e in existing if isinstance(e, dict)}
    for e in entries:
        by_path[e["path"]] = e
    merged = sorted(by_path.values(), key=lambda e: str(e.get("path")))
    out.write_text(json.dumps({
        "schema": 1,
        "generated_at": _now(),
        "assets": merged,
    }, indent=2) + "\n", encoding="utf-8")
    return out


def notices_from_provenance(entries: list) -> list:
    """Visible-credit strings. Only attribution_req tiers contribute.

    notice_only licenses (MIT/OFL/Apache) are deliberately excluded: they oblige
    a license file to travel with the copy, not a credit shown to a user.
    Conflating the two would put text in the gallery header that nothing
    actually requires, and would make licensing.notices non-empty on a run that
    is genuinely obligation-free to the reader.
    """
    seen, out = set(), []
    for e in entries:
        if not e.get("attribution_required"):
            continue
        txt = e.get("attribution_text") or "%s (%s)" % (
            e.get("provider", "unknown"), e.get("license", "unknown"))
        if txt not in seen:
            seen.add(txt)
            out.append(txt)
    return out


def license_files_from_provenance(entries: list) -> list:
    """notice_only obligations: (license id, provider) needing text in the zip."""
    seen, out = set(), []
    for e in entries:
        if e.get("license_tier") != "notice_only":
            continue
        k = (e.get("license"), e.get("provider"))
        if k not in seen:
            seen.add(k)
            out.append({"license": k[0], "provider": k[1]})
    return out


# ---------------------------------------------------------------------------
# Fetchers -- one per verified source
# ---------------------------------------------------------------------------

# Ceilings per tier. The gallery must stay a single openable file, so these are
# deliberately tight; a source that cannot meet them is not usable here even if
# its license is perfect (this is why ambientCG is excluded -- ZIP-only, 5 MB
# floor, no per-map endpoint).
MAX_BYTES = {"video": 1_600_000, "texture": 700_000, "font": 500_000}


def fetch_pexels_video(query: str, out_dir: Path, count: int = 1) -> dict:
    """Pexels video. Same key as the existing photo search; no attribution.

    Chooses the smallest file at or above 360px wide: a 1080p clip is 7 MB and
    a 240p one looks broken, so the useful band is narrow.
    """
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return {"fetched": [], "reason": "PEXELS_API_KEY not set"}
    url = ("https://api.pexels.com/videos/search?query=%s&per_page=%d"
           % (urllib.parse.quote(query), max(1, min(count * 3, 15))))
    data, err = http_json(url, {"Authorization": key})
    if err:
        return {"fetched": [], "reason": "pexels: %s" % err}

    out_dir.mkdir(parents=True, exist_ok=True)
    got = []
    unreachable_streak = 0
    for vid in (data.get("videos") or [])[:_MAX_CANDIDATES]:
        if len(got) >= count:
            break
        files = [f for f in (vid.get("video_files") or [])
                 if f.get("file_type") == "video/mp4" and (f.get("width") or 0) >= 360]
        if not files:
            continue
        pick = min(files, key=lambda f: f.get("width") or 99999)
        blob, derr = http_bytes(pick["link"], max_bytes=MAX_BYTES["video"])
        if derr:
            sys.stderr.write("tf_assets: skip video %s (%s)\n" % (vid.get("id"), derr))
            if derr.startswith("unreachable"):
                unreachable_streak += 1
                if unreachable_streak >= _UNREACHABLE_STREAK:
                    host = urllib.parse.urlsplit(pick["link"]).netloc
                    return {"fetched": got,
                            "reason": "pexels: download host %s unreachable" % host}
            continue
        unreachable_streak = 0
        dest = out_dir / ("pexels-%s-%dp.mp4" % (vid.get("id"), pick.get("height") or 0))
        dest.write_bytes(blob)
        got.append(provenance_entry(
            dest, "pexels", vid.get("url", pick["link"]), "Pexels",
            "attribution_free", blob,
            extra={"width": pick.get("width"), "height": pick.get("height"),
                   "poster": (vid.get("video_pictures") or [{}])[0].get("picture", "")}))
    return {"fetched": got, "reason": "" if got else "no video within size ceiling"}


def fetch_fontsource(family: str, out_dir: Path, weight: str = "",
                     allow_attribution: bool = False) -> dict:
    """Fontsource TTF. Keyless, and the license is machine-readable per font.

    TTF specifically: tf_outline.py cannot parse WOFF2, and React Native needs
    TTF too, so the woff2 the Google Fonts CSS API serves by default is useless
    to both consumers.
    """
    fid = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
    meta, err = http_json("https://api.fontsource.org/v1/fonts/%s" % fid)
    if err:
        return {"fetched": [], "reason": "fontsource %s: %s" % (fid, err)}

    spdx = (meta.get("license") or "").strip()
    ok, why = license_allowed(spdx, allow_attribution)
    if not ok:
        return {"fetched": [], "reason": "fontsource %s: %s" % (fid, why)}
    tier = classify_license(spdx)

    variants = meta.get("variants") or {}
    weights = [weight] if weight and weight in variants else sorted(
        variants, key=lambda w: abs(int(w) - 700) if w.isdigit() else 999)
    out_dir.mkdir(parents=True, exist_ok=True)
    for w in weights:
        styles = (variants.get(w) or {}).get("normal") or {}
        subset = "latin" if "latin" in styles else (sorted(styles)[0] if styles else None)
        if not subset:
            continue
        ttf = ((styles.get(subset) or {}).get("url") or {}).get("ttf")
        if not ttf:
            continue
        blob, derr = http_bytes(ttf, max_bytes=MAX_BYTES["font"])
        if derr:
            continue
        # sfnt magic: 0x00010000 (TrueType) or OTTO (CFF). wOF2 means we were
        # served the wrong format and the file is useless to opentype.js.
        if blob[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            return {"fetched": [], "reason": "fontsource %s: not a TTF/OTF" % fid}
        dest = out_dir / ("%s-%s.ttf" % (fid, w))
        dest.write_bytes(blob)
        return {"fetched": [provenance_entry(
            dest, "fontsource", "https://fontsource.org/fonts/%s" % fid,
            spdx, tier, blob,
            extra={"family": meta.get("family", family), "weight": w,
                   "subset": subset})], "reason": ""}
    return {"fetched": [], "reason": "fontsource %s: no TTF variant" % fid}


def fetch_polyhaven_texture(query: str, out_dir: Path, count: int = 1) -> dict:
    """Poly Haven 1k JPG colour maps. CC0 assets, keyless.

    Only the Diffuse/diff map at 1k JPG is taken. HDRIs start at 1.73 MB and
    need a WebGL loader; 4k maps are 27 MB. Vendoring the file rather than
    hotlinking is also what keeps this attribution-free -- see the API-terms
    note in this module's docstring.
    """
    listing, err = http_json("https://api.polyhaven.com/assets?t=textures")
    if err:
        return {"fetched": [], "reason": "polyhaven: %s" % err}

    q = (query or "").lower().split()
    def score(item):
        hay = " ".join([item[0]] + [str(t).lower()
                                    for t in (item[1].get("tags") or [])])
        return sum(1 for term in q if term in hay)

    ranked = sorted(listing.items(), key=score, reverse=True)
    if q and score(ranked[0]) == 0:
        return {"fetched": [], "reason": "polyhaven: no texture matching %r" % query}

    out_dir.mkdir(parents=True, exist_ok=True)
    got = []
    unreachable_streak = 0
    for slug, _meta in ranked[:_MAX_CANDIDATES]:
        if len(got) >= count:
            break
        files, ferr = http_json("https://api.polyhaven.com/files/%s" % slug)
        if ferr:
            continue
        node = None
        for map_key in ("Diffuse", "diffuse", "diff", "Color", "col"):
            cand = files.get(map_key)
            if isinstance(cand, dict) and "1k" in cand:
                node = cand["1k"]
                break
        if not node:
            continue
        jpg = node.get("jpg")
        if not isinstance(jpg, dict) or not jpg.get("url"):
            continue
        blob, derr = http_bytes(jpg["url"], max_bytes=MAX_BYTES["texture"])
        if derr:
            sys.stderr.write("tf_assets: skip texture %s (%s)\n" % (slug, derr))
            # An unreachable download host is one problem, not one-per-asset.
            # Poly Haven serves metadata from api.polyhaven.com but files from
            # dl.polyhaven.org, so the API can answer perfectly while every
            # download is blocked -- which is the case on at least one network
            # this runs on. Bail out and name the host instead of grinding
            # through every candidate.
            if derr.startswith("unreachable"):
                unreachable_streak += 1
                if unreachable_streak >= _UNREACHABLE_STREAK:
                    host = urllib.parse.urlsplit(jpg["url"]).netloc
                    return {"fetched": got,
                            "reason": ("polyhaven: download host %s unreachable "
                                       "(API responded, CDN did not — likely "
                                       "network-blocked)" % host)}
            continue
        unreachable_streak = 0
        dest = out_dir / ("polyhaven-%s-1k.jpg" % slug)
        dest.write_bytes(blob)
        got.append(provenance_entry(
            dest, "polyhaven", "https://polyhaven.com/a/%s" % slug,
            "CC0-1.0", "attribution_free", blob,
            extra={"slug": slug, "resolution": "1k", "map": "diffuse"}))
    return {"fetched": got, "reason": "" if got else "no 1k JPG within ceiling"}


# ---------------------------------------------------------------------------
# Patterns -- generated locally, not fetched
# ---------------------------------------------------------------------------
#
# Every SVG-pattern service verified in 14-asset-sources.md is browser-only:
# fffuel, Haikei, BGJar, SVGBackgrounds and coolbackgrounds expose no HTTP API,
# and Pattern Monster's /api/patterns returns 404 -- its patterns live inside a
# Svelte app's internal modules with no data endpoint. Hero Patterns is the only
# substantial reachable set and it is CC BY 4.0, so attribution-required.
#
# Generating them is therefore not a workaround, it is the better answer for
# this tier: zero bytes over the wire, recolored from the theme's own tokens,
# works with no network, and carries no license obligation whatsoever.

_PATTERN_BUILDERS = {
    "diagonal-hatch": lambda s: (
        '<path d="M0,{s} l{s},-{s} M-{h},{h} l{s},-{s} M{h},{d} l{s},-{s}" '
        'stroke="{{fg}}" stroke-width="{w}" fill="none"/>'
    ).format(s=s, h=s // 2, d=s + s // 2, w=max(1, s // 12)),
    "dot-grid": lambda s: (
        '<circle cx="{c}" cy="{c}" r="{r}" fill="{{fg}}"/>'
    ).format(c=s // 2, r=max(1, s // 10)),
    "cross-hatch": lambda s: (
        '<path d="M0,{h} H{s} M{h},0 V{s}" stroke="{{fg}}" '
        'stroke-width="{w}" fill="none"/>'
    ).format(s=s, h=s // 2, w=max(1, s // 16)),
    "concentric-arc": lambda s: (
        '<path d="M0,{s} A{s},{s} 0 0 1 {s},0" stroke="{{fg}}" '
        'stroke-width="{w}" fill="none"/>'
        '<path d="M0,{h} A{h},{h} 0 0 1 {h},0" stroke="{{fg}}" '
        'stroke-width="{w}" fill="none"/>'
    ).format(s=s, h=s // 2, w=max(1, s // 14)),
    "chevron": lambda s: (
        '<path d="M0,{h} L{h},0 L{s},{h}" stroke="{{fg}}" stroke-width="{w}" '
        'fill="none"/>'
    ).format(s=s, h=s // 2, w=max(1, s // 12)),
    "triangle-tile": lambda s: (
        '<path d="M0,{s} L{h},0 L{s},{s} Z" fill="{{fg}}"/>'
    ).format(s=s, h=s // 2),
}

PATTERN_NAMES = tuple(_PATTERN_BUILDERS)


def build_pattern_svg(name: str, fg: str, bg: str = "none", size: int = 32,
                      opacity: float = 1.0) -> str:
    """One tileable SVG pattern, colored from the theme's own tokens."""
    builder = _PATTERN_BUILDERS.get(name)
    if builder is None:
        raise KeyError("unknown pattern %r" % name)
    body = builder(size).replace("{fg}", fg)
    rect = ('<rect width="%d" height="%d" fill="%s"/>' % (size, size, bg)
            if bg and bg != "none" else "")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d">\n'
        '  <defs><pattern id="p-%s" width="%d" height="%d" '
        'patternUnits="userSpaceOnUse">%s%s</pattern></defs>\n'
        '  <rect width="%d" height="%d" fill="url(#p-%s)" opacity="%s"/>\n'
        '</svg>\n'
        % (size, size, size, size, name, size, size, rect, body,
           size, size, name, ("%g" % opacity))
    )


def generate_patterns(out_dir: Path, fg: str, bg: str = "none",
                      names: tuple = (), size: int = 32) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    got = []
    for name in (names or PATTERN_NAMES):
        if name not in _PATTERN_BUILDERS:
            continue
        svg = build_pattern_svg(name, fg=fg, bg=bg, size=size)
        blob = svg.encode("utf-8")
        dest = out_dir / ("pattern-%s.svg" % name)
        dest.write_bytes(blob)
        got.append(provenance_entry(
            dest, "theme-forge-generated", "", "CC0-1.0",
            "attribution_free", blob,
            extra={"pattern": name, "generated": True, "tile_size": size}))
    return {"fetched": got, "reason": ""}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(theme_dir: Path, tiers: tuple, query: str = "",
        allow_attribution: bool = False) -> dict:
    """Fetch the requested tiers. Never raises; never fails the caller."""
    theme_json = theme_dir / "theme.json"
    theme = {}
    if theme_json.is_file():
        try:
            theme = json.loads(theme_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            theme = {}

    base = theme_dir / "assets" / "sourced"
    entries: list = []
    reasons: dict = {}
    offline = not network_up()

    # Patterns are local, so they run even with no network -- this is the tier
    # that makes an offline run still produce something usable.
    if "pattern" in tiers:
        light = ((theme.get("color") or {}).get("light") or {})
        fg = ((light.get("border") or light.get("text") or {}).get("hex")
              or "#333333")
        r = generate_patterns(base / "patterns", fg=fg)
        entries += r["fetched"]
        reasons["pattern"] = r["reason"] or "ok (generated locally)"

    if offline:
        for t in tiers:
            reasons.setdefault(t, "offline — no network")
    else:
        if "video" in tiers:
            q = query or (theme.get("thesis") or theme.get("name") or "abstract")
            r = fetch_pexels_video(q, base / "video")
            entries += r["fetched"]
            reasons["video"] = r["reason"] or "ok"
        if "font" in tiers:
            fam = (((theme.get("typography") or {}).get("display") or {})
                   .get("family") or "")
            if not fam:
                reasons["font"] = "no typography.display.family in theme.json"
            else:
                r = fetch_fontsource(fam, base / "fonts",
                                     allow_attribution=allow_attribution)
                entries += r["fetched"]
                reasons["font"] = r["reason"] or "ok"
        if "texture" in tiers:
            q = query or " ".join(
                str(x) for x in ((theme.get("assets") or {})
                                 .get("decorative_system") or "").split()[:4])
            r = fetch_polyhaven_texture(q or "concrete", base / "textures")
            entries += r["fetched"]
            reasons["texture"] = r["reason"] or "ok"

    manifest = write_provenance(theme_dir, entries) if entries else None
    notices = notices_from_provenance(entries)
    return {
        "ok": True,
        "theme": theme_dir.name,
        "offline": offline,
        "fetched_count": len(entries),
        "tiers": reasons,
        "provenance": str(manifest) if manifest else "",
        "notices": notices,
        "license_files": license_files_from_provenance(entries),
        # A default run must end with no visible-credit obligation. If this is
        # ever non-empty without --allow-attribution, something bypassed the
        # pre-request gate and the caller must surface it rather than ship.
        "attribution_clean": (not notices) or allow_attribution,
        "fallback_intact": len(entries) == 0,
    }


# ---------------------------------------------------------------------------
# Selftest -- no network required
# ---------------------------------------------------------------------------

def _selftest() -> int:
    import tempfile

    # License policy
    assert classify_license("CC0-1.0") == "attribution_free"
    assert classify_license("MIT") == "notice_only"
    assert classify_license("CC-BY-4.0") == "attribution_req"
    assert classify_license("CC-BY-SA-4.0") == "forbidden", "share-alike must be refused"
    assert classify_license("LottieSimpleLicense") == "forbidden"
    assert classify_license("") == "forbidden"
    assert classify_license("Some-New-License-2.0") == "forbidden", \
        "unknown license must default to forbidden, not permitted"

    ok, _ = license_allowed("CC-BY-4.0")
    assert not ok, "CC-BY must be refused on a default run"
    ok, tier = license_allowed("CC-BY-4.0", allow_attribution=True)
    assert ok and tier == "attribution_req"
    assert license_allowed("CC-BY-SA-4.0", allow_attribution=True)[0] is False, \
        "share-alike must stay refused even when opting in"

    # In-band Dublin Core parsing
    svg = ('<svg><metadata><rdf:RDF><rdf:Description>'
           '<dc:creator>Lisa Wischofsky</dc:creator>'
           '<dcterms:license>https://creativecommons.org/licenses/by/4.0/</dcterms:license>'
           '<dc:rights>Remix of "Adventurer" by Lisa Wischofsky, CC BY 4.0</dc:rights>'
           '</rdf:Description></rdf:RDF></metadata></svg>')
    got = license_from_svg(svg)
    assert got["license"] == "CC-BY-4.0", got
    assert got["creator"] == "Lisa Wischofsky", got
    assert "Adventurer" in got["attribution_text"], got
    cc0 = license_from_svg(
        '<svg><metadata><dcterms:license>'
        'https://creativecommons.org/publicdomain/zero/1.0/'
        '</dcterms:license></metadata></svg>')
    assert cc0["license"] == "CC0-1.0", cc0
    # Absence must not read as CC0.
    assert license_from_svg("<svg><rect/></svg>") == {}

    # Patterns build, are well-formed, and carry the theme color
    for name in PATTERN_NAMES:
        svg = build_pattern_svg(name, fg="#ff0000", bg="#ffffff", size=24)
        assert svg.count("<svg") == 1 and "</svg>" in svg, name
        assert "#ff0000" in svg, name
        assert "{fg}" not in svg and "{s}" not in svg, "unsubstituted placeholder in %s" % name
        assert 'patternUnits="userSpaceOnUse"' in svg, name

    # Provenance + notice separation
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        r = generate_patterns(tdir / "assets" / "sourced" / "patterns", fg="#123456")
        assert len(r["fetched"]) == len(PATTERN_NAMES), r
        e = r["fetched"][0]
        for field in ("path", "provider", "source_url", "license",
                      "attribution_required", "attribution_text",
                      "fetched_at", "bytes", "sha256"):
            assert field in e, "provenance missing %s" % field
        p = write_provenance(tdir, r["fetched"])
        assert p.is_file()
        doc = json.loads(p.read_text(encoding="utf-8"))
        assert len(doc["assets"]) == len(PATTERN_NAMES)
        # Re-writing merges rather than duplicating.
        write_provenance(tdir, r["fetched"])
        doc2 = json.loads(p.read_text(encoding="utf-8"))
        assert len(doc2["assets"]) == len(PATTERN_NAMES), "provenance duplicated on rerun"

        # notice_only must NOT produce a visible notice; attribution_req must.
        mit = provenance_entry(tdir / "x.svg", "pattern-monster", "u", "MIT",
                              "notice_only", b"x")
        ccby = provenance_entry(tdir / "y.svg", "dicebear", "u", "CC-BY-4.0",
                               "attribution_req", b"y", attribution_text="Credit X")
        assert notices_from_provenance([mit]) == [], \
            "MIT must not create a visible credit"
        assert notices_from_provenance([ccby]) == ["Credit X"]
        assert license_files_from_provenance([mit]) == [
            {"license": "MIT", "provider": "pattern-monster"}]
        assert license_files_from_provenance([ccby]) == []

        # Offline run: patterns still land, nothing else claimed, never fails.
        (tdir / "theme.json").write_text(json.dumps(
            {"color": {"light": {"border": {"hex": "#abcdef"}}},
             "typography": {"display": {"family": "Inter"}}}), encoding="utf-8")
        res = run(tdir, tiers=("pattern",))
        assert res["ok"] is True and res["fetched_count"] == len(PATTERN_NAMES)
        assert res["attribution_clean"] is True
        assert res["notices"] == []

    sys.stderr.write("selftest OK\n")
    print(json.dumps({"ok": True, "selftest": True}))
    return 0


def main(argv: list) -> int:
    if "--selftest" in argv:
        return _selftest()

    want_json = "--json" in argv
    allow_attr = "--allow-attribution" in argv
    theme_dir = None
    tiers = ("pattern",)
    query = ""
    i = 0
    while i < len(argv):
        if argv[i] == "--theme" and i + 1 < len(argv):
            theme_dir = Path(argv[i + 1]); i += 2
        elif argv[i] == "--tiers" and i + 1 < len(argv):
            tiers = tuple(t.strip() for t in argv[i + 1].split(",") if t.strip()); i += 2
        elif argv[i] == "--query" and i + 1 < len(argv):
            query = argv[i + 1]; i += 2
        else:
            i += 1

    if theme_dir is None or not theme_dir.is_dir():
        msg = "--theme <dir> required (existing directory)"
        sys.stderr.write("tf_assets: %s\n" % msg)
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    result = run(theme_dir, tiers, query=query, allow_attribution=allow_attr)

    sys.stderr.write("\nASSET SOURCING — %s\n" % result["theme"])
    sys.stderr.write("─" * 70 + "\n")
    if result["offline"]:
        sys.stderr.write("  offline — generated assets only, fallback intact\n")
    for t, why in sorted(result["tiers"].items()):
        sys.stderr.write("  %-9s %s\n" % (t, why))
    sys.stderr.write("  fetched: %d\n" % result["fetched_count"])
    if result["notices"]:
        sys.stderr.write("  ⚠ %d visible credit(s) required — gallery and THEME.md "
                         "must render them:\n" % len(result["notices"]))
        for n in result["notices"]:
            sys.stderr.write("      %s\n" % n)
    if result["license_files"]:
        sys.stderr.write("  license text to ship (no visible credit needed): %s\n"
                         % ", ".join(sorted({l["license"] for l in result["license_files"]})))
    if not result["attribution_clean"]:
        sys.stderr.write("  ✗ attribution obligation on a default run — "
                         "this should be impossible; do not ship\n")
    sys.stderr.write("─" * 70 + "\n")

    print(json.dumps(result, indent=2 if want_json else None))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        sys.stderr.write("tf_assets: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
