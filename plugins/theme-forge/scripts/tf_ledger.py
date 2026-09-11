#!/usr/bin/env python3
"""tf_ledger.py -- mechanically record the current run's six themes into
$TF_HOME/used.md, the cross-run ledger that theme-designer reads to avoid
recycling a prior hue/font/composition.

This exists because `current/` is wiped at the start of every generate run
(tf_reset.py) -- used.md is the ONLY thing that survives to give future runs
any memory of past ones. Recording it by asking an LLM orchestrator to
hand-author a markdown table row is exactly the kind of step that silently
gets skipped under context pressure. This script makes it deterministic:
call it once after Gate A (tf_distinct.py) has passed, and it does the same
thing every time, with no reliance on anyone remembering the format.

Idempotent: matches on (slug, run-date) pairs already present in used.md and
only appends rows that are missing, so calling this multiple times in one
run (e.g. gallery gets rebuilt after design-critic, after manual fixes) never
duplicates entries.

Usage:
    python3 tf_ledger.py --json                 # record current/themes/* into used.md
    python3 tf_ledger.py --json --check         # report only, do not write
    python3 tf_ledger.py --selftest             # verify JSON round-trip works

Exit 0 on success (including "nothing new to record"). Exit 1 on expected
failure. Exit 2 on unexpected error.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import tf_paths  # type: ignore
    import tf_distinct  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import tf_paths
    import tf_distinct


# "signature_type", not "signature_motion": renamed to match the actual
# theme.json field it records (motion.signature_type) after a real bug where
# the old name and a motion.character-first fallback chain meant this column
# recorded the wrong field entirely for every historical row (see the writer
# below). Column parsing elsewhere (tf_distinct.py's _parse_used_md) reads
# this header row dynamically rather than assuming a fixed list, so renaming
# it here is safe -- new code always defers to whatever header is actually
# present in the file.
_COLUMNS = [
    "slug", "run-date", "primary_hex", "primary_hue", "accent_hex", "accent_hue",
    "bg_hex", "bg_lightness", "display_font", "layout_family_website",
    "layout_family_webapp", "layout_family_mobile", "signature_type",
]

_ENTRIES_HEADER_RE = re.compile(
    r'(\|\s*slug\s*\|.*?\|\n\|[-\s|]+\|\n)', re.DOTALL
)


def _eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def _fail(msg: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(code)


def _hue_from_color(color_obj: dict) -> tuple[str, float | None]:
    """Return (hex, hue) from a {"css": "oklch(...)", "hex": "#..."} value."""
    hexv = color_obj.get("hex") or "#??????"
    lch = tf_distinct._parse_oklch(color_obj.get("css") or "")
    if lch:
        return hexv, round(lch[2], 1)
    return hexv, None


def _bg_lightness(color_obj: dict) -> float:
    lch = tf_distinct._parse_oklch(color_obj.get("css") or "")
    if lch:
        return round(lch[0], 3)
    hexv = color_obj.get("hex")
    if hexv:
        return round(tf_distinct._hex_to_lum(hexv), 3)
    return 1.0


def _row_for_theme(theme_json: dict, run_date: str) -> dict:
    color = theme_json.get("color", {}) or {}
    light = color.get("light", {}) or {}
    primary = light.get("primary", {}) or {}
    accent = light.get("accent", {}) or {}
    bg = light.get("background", {}) or light.get("bg", {}) or {}
    comp = theme_json.get("composition", {}) or {}
    motion = theme_json.get("motion", {}) or {}
    typ = (theme_json.get("typography", {}) or {}).get("display", {}) or {}

    primary_hex, primary_hue = _hue_from_color(primary)
    accent_hex, accent_hue = _hue_from_color(accent)

    return {
        "slug": theme_json.get("slug", "?"),
        "run-date": run_date,
        "primary_hex": primary_hex,
        "primary_hue": "" if primary_hue is None else f"{primary_hue}",
        "accent_hex": accent_hex,
        "accent_hue": "" if accent_hue is None else f"{accent_hue}",
        "bg_hex": bg.get("hex", "#??????"),
        "bg_lightness": f"{_bg_lightness(bg)}",
        "display_font": typ.get("family", "unknown"),
        "layout_family_website": (comp.get("layout_signature", {}) or {}).get("website", {}).get("layout_family", ""),
        "layout_family_webapp": (comp.get("layout_signature", {}) or {}).get("webapp", {}).get("layout_family", ""),
        "layout_family_mobile": (comp.get("layout_signature", {}) or {}).get("mobile", {}).get("layout_family", ""),
        # Canonical field is motion.signature_type (a short kebab-slug for
        # exact-match gating -- see theme.schema.json). motion.character is a
        # closed 4-value enum (crisp/springy/calm/mechanical) and motion.signature
        # is a multi-sentence prose description; neither is a substitute for
        # signature_type, and both are the WRONG shape for this column's
        # purpose (spotting a repeated exact signature across runs). This
        # used to read "motion.get('character') or motion.get('signature_type')
        # or ...", which meant every row ever written recorded motion.character
        # (always non-empty, so the `or` chain never reached signature_type)
        # -- confirmed against the real used.md, where every historical
        # "signature_motion" entry is one of exactly 4 values, not a real
        # signature slug. No fallback: if signature_type is missing, that is
        # itself the finding (a required schema field silently absent), not
        # something to paper over with a differently-shaped value.
        "signature_type": motion.get("signature_type") or "",
    }


def _row_to_md(row: dict) -> str:
    return "| " + " | ".join(row[c] for c in _COLUMNS) + " |"


def _existing_keys(used_md_text: str) -> set[tuple[str, str]]:
    """Return the set of (slug, run-date) pairs already present as rows."""
    keys: set[tuple[str, str]] = set()
    for line in used_md_text.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|--") or line.startswith("|-"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(_COLUMNS):
            continue
        if cells[0] == "slug":  # header row
            continue
        keys.add((cells[0], cells[1]))
    return keys


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        test = {"ok": True, "selftest": True}
        assert json.loads(json.dumps(test)) == test
        _eprint("selftest OK")
        print(json.dumps(test))
        return 0

    want_json = "--json" in argv
    check_only = "--check" in argv

    # Reject unknown flags instead of ignoring them. This script's default mode
    # WRITES to $TF_HOME/used.md, and `--check` is the only thing standing
    # between "inspect" and "append rows to a ledger". A silently-ignored typo
    # therefore does not degrade to a no-op -- it degrades to a mutation.
    # Confirmed live on 2026-09-10: `--check-only` (a plausible spelling of a
    # flag that is actually `--check`) was dropped on the floor, the script ran
    # in write mode, and it re-appended six rows to a ledger that had just been
    # deliberately cleared. Fail loudly and name the valid flags.
    _KNOWN = {"--json", "--check", "--selftest"}
    unknown = [a for a in argv if a.startswith("-") and a not in _KNOWN]
    if unknown:
        _fail(
            "unknown flag(s): %s — valid flags are %s. Refusing to run: this "
            "script writes to used.md by default, so an ignored flag would "
            "silently mutate the ledger."
            % (", ".join(unknown), ", ".join(sorted(_KNOWN))),
            1,
        )

    if not want_json:
        _fail("pass --json to get structured output", 1)

    paths = tf_paths.resolve(create=True)
    themes_root = Path(paths.current_themes)
    if not themes_root.is_dir():
        _fail(f"themes directory not found: {themes_root}")

    run = {}
    if paths.run_json.is_file():
        try:
            run = json.loads(paths.run_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            run = {}
    run_date = (run.get("generated_at") or "")[:10]
    if not run_date:
        import datetime
        run_date = datetime.date.today().isoformat()

    theme_dirs = sorted(d for d in themes_root.iterdir() if d.is_dir())
    if not theme_dirs:
        _fail(f"no theme directories found under {themes_root}")

    rows: list[dict] = []
    for td in theme_dirs:
        tj_path = td / "theme.json"
        if not tj_path.is_file():
            _eprint(f"tf_ledger: skipping {td.name} — no theme.json")
            continue
        try:
            tj = json.loads(tj_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _eprint(f"tf_ledger: skipping {td.name} — unreadable theme.json ({exc})")
            continue
        rows.append(_row_for_theme(tj, run_date))

    used_md_path = paths.home / "used.md"
    if not used_md_path.is_file():
        _fail(f"used.md not found at {used_md_path} — expected the seeded ledger to exist")

    existing_text = used_md_path.read_text(encoding="utf-8")
    existing_keys = _existing_keys(existing_text)

    to_append = [r for r in rows if (r["slug"], r["run-date"]) not in existing_keys]

    # A row already present for THIS (slug, run-date) is refreshed in place when
    # the theme's data has since changed, rather than left as-is.
    #
    # tf_gallery.py calls this on every rebuild, so the first build of a run
    # writes the row and every later build used to skip it forever. Any change
    # made to a theme after its first gallery build therefore never reached the
    # ledger. Confirmed live: a theme's display font was swapped mid-run
    # (Gabarito -> Unbounded) to fix a Gate 21 font-identity finding, and the
    # stale row kept asserting Gabarito -- which then raised a false
    # `ledger_font_conflict` against the *sibling* theme that legitimately owns
    # Gabarito, while also telling future runs that Unbounded was still free.
    # A cross-run avoidance record that lags the run it is recording is worse
    # than no record, because both of its answers are wrong.
    #
    # Scoped deliberately to the current run-date: earlier runs' rows are
    # history and must never be rewritten.
    to_update: list[dict] = []
    lines = existing_text.splitlines()
    for r in rows:
        if (r["slug"], r["run-date"]) not in existing_keys:
            continue
        fresh = _row_to_md(r)
        for i, line in enumerate(lines):
            s = line.strip()
            if not s.startswith("|") or s.startswith("|-"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) != len(_COLUMNS) or cells[0] == "slug":
                continue
            if (cells[0], cells[1]) == (r["slug"], r["run-date"]) and s != fresh:
                lines[i] = fresh
                to_update.append(r)
                break
    if to_update:
        existing_text = "\n".join(lines) + "\n"

    skipped = len(rows) - len(to_append) - len(to_update)

    if check_only:
        print(json.dumps({
            "ok": True, "check_only": True,
            "themes_found": len(rows), "already_recorded": skipped,
            "would_append": len(to_append),
        }))
        return 0

    if to_append or to_update:
        new_text = existing_text
        if not new_text.endswith("\n"):
            new_text += "\n"
        if to_append:
            new_text += "\n".join(_row_to_md(r) for r in to_append) + "\n"
        used_md_path.write_text(new_text, encoding="utf-8")
        if to_append:
            _eprint(f"tf_ledger: appended {len(to_append)} row(s) to {used_md_path}")
        if to_update:
            _eprint(
                "tf_ledger: refreshed %d existing row(s) whose theme changed this run: %s"
                % (len(to_update), ", ".join(r["slug"] for r in to_update))
            )
    else:
        _eprint(f"tf_ledger: nothing new — all {len(rows)} theme(s) already recorded")

    print(json.dumps({
        "ok": True, "path": str(used_md_path),
        "appended": len(to_append), "updated": len(to_update),
        "skipped_existing": skipped,
        "slugs_appended": [r["slug"] for r in to_append],
        "slugs_updated": [r["slug"] for r in to_update],
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"unhandled: {exc}"}))
        sys.exit(2)
