#!/usr/bin/env python3
"""tf_freshness.py -- read/write FRESHNESS.json and recommend a refresh depth.

Recommendation:
    full_refresh  a domain has never been refreshed, or the last full refresh
                  is older than the delta window (default 30 days), or no
                  last_full_refresh is recorded.
    delta_check   everything has been refreshed at least once but the newest
                  refresh is older than the skip window (default 7 days).
    skip          everything is fresh within the skip window.

    python3 tf_freshness.py --json
    python3 tf_freshness.py --json --mark-refreshed <csv|all> [--sources N] [--full]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin dir
import tf_paths

SKIP_DAYS = 7
DELTA_DAYS = 30

# Must list EVERY domain in knowledge/. _recommend() iterates this list to decide
# full_refresh vs delta_check vs skip, and `--mark-refreshed all` expands to it, so
# a domain missing here is invisible to freshness entirely: it can be arbitrarily
# stale while the recommendation still reads "skip". 12-asset-tooling and
# 13-anti-patterns were absent until 2026-09-09 — the first holds provider licence
# terms and rate limits that change without notice, the second is the AI-slop
# catalog, whose whole value is being current. Individual --mark-refreshed calls
# still wrote them (the writer uses setdefault), which is why FRESHNESS.json looked
# complete and hid the gap.
ALL_DOMAINS = [
    "01-design-tokens", "02-color", "03-typography", "04-aesthetics",
    "05-css-platform", "06-motion", "07-component-systems", "08-logos-graphics",
    "09-mobile", "10-accessibility", "11-native-platform", "12-asset-tooling",
    "13-anti-patterns", "14-asset-sources",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    if not s:
        return None
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load(paths):
    live = paths.freshness_json
    if live.is_file():
        try:
            return json.loads(live.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Fall back to the plugin seed if the live file is missing/corrupt.
    if paths.plugin_knowledge:
        seed = paths.plugin_knowledge / "FRESHNESS.json"
        if seed.is_file():
            try:
                return json.loads(seed.read_text(encoding="utf-8"))
            except Exception:
                pass
    # Synthesize a fresh-install default.
    return {
        "schema": 1,
        "seed_version": "unknown",
        "last_full_refresh": None,
        "domains": {},
    }


def _ensure_domains(data):
    domains = data.setdefault("domains", {})
    for name in ALL_DOMAINS:
        domains.setdefault(name, {"refreshed": None, "sources": 0, "status": "seed"})
    return domains


def _save(paths, data):
    paths.freshness_json.parent.mkdir(parents=True, exist_ok=True)
    paths.freshness_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _recommend(data):
    domains = data.get("domains", {})
    now = datetime.now(timezone.utc)

    # Any domain never refreshed -> full refresh.
    refreshed_dates = []
    for name in ALL_DOMAINS:
        d = domains.get(name, {})
        dt = _parse_iso(d.get("refreshed"))
        if dt is None:
            return "full_refresh", None
        refreshed_dates.append(dt)

    lfr = _parse_iso(data.get("last_full_refresh"))
    if lfr is None:
        return "full_refresh", None

    newest = max(refreshed_dates)
    age_days = (now - newest).total_seconds() / 86400.0
    lfr_age = (now - lfr).total_seconds() / 86400.0

    if lfr_age >= DELTA_DAYS:
        return "full_refresh", round(age_days, 2)
    if age_days >= SKIP_DAYS:
        return "delta_check", round(age_days, 2)
    return "skip", round(age_days, 2)


def main(argv):
    want_json = "--json" in argv
    paths = tf_paths.resolve(create=True)
    data = _load(paths)
    _ensure_domains(data)

    changed = False

    if "--mark-refreshed" in argv:
        i = argv.index("--mark-refreshed")
        spec = argv[i + 1] if i + 1 < len(argv) else "all"
        names = ALL_DOMAINS if spec == "all" else [s.strip() for s in spec.split(",") if s.strip()]
        sources = 0
        if "--sources" in argv:
            j = argv.index("--sources")
            try:
                sources = int(argv[j + 1])
            except Exception:
                sources = 0
        now = _now_iso()
        for name in names:
            data["domains"].setdefault(name, {})
            data["domains"][name]["refreshed"] = now
            data["domains"][name]["sources"] = sources
            data["domains"][name]["status"] = "refreshed"
        # If everything is now refreshed, or --full was passed, stamp a full refresh.
        all_refreshed = all(data["domains"].get(n, {}).get("refreshed") for n in ALL_DOMAINS)
        if "--full" in argv or all_refreshed:
            data["last_full_refresh"] = now
        changed = True

    if changed:
        _save(paths, data)

    recommendation, age = _recommend(data)
    result = {
        "ok": True,
        "recommendation": recommendation,
        "newest_age_days": age,
        "last_full_refresh": data.get("last_full_refresh"),
        "seed_version": data.get("seed_version"),
        "domains": data.get("domains"),
        "skip_days": SKIP_DAYS,
        "delta_days": DELTA_DAYS,
    }
    sys.stderr.write("tf_freshness: recommendation=%s\n" % recommendation)
    if want_json:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        sys.stderr.write("tf_freshness: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
