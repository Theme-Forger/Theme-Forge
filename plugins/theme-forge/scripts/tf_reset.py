#!/usr/bin/env python3
"""tf_reset.py -- wipe and recreate $TF_HOME/current/ at the start of a run.

`current/` is the ONLY theme set retained on disk. Nothing else is ever
auto-deleted. Before wiping, any existing run.json is read and returned as
`previous_run` so the orchestrator can warn about an unexported set.

Safety: the target is asserted to be under TF_HOME before anything is removed.
Point it anywhere else and it refuses.

    python3 tf_reset.py --json [--force] [--target <path>]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin dir
import tf_paths
import tf_verify_wipe


def _read_previous(run_json: Path):
    if run_json.is_file():
        try:
            return json.loads(run_json.read_text(encoding="utf-8"))
        except Exception:
            return {"unreadable": True}
    return None


def reset(target: Path, home: Path) -> None:
    # Never remove anything that isn't provably under TF_HOME.
    tf_paths.assert_under_home(target, home)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    (target / "themes").mkdir(parents=True, exist_ok=True)
    (target / "backups").mkdir(parents=True, exist_ok=True)
    # screenshots/visual review/ is scaffolded here, not created ad hoc by
    # whoever writes the first image. It sits under current/ specifically so
    # the rmtree above clears last run's review images -- a screenshot of a
    # theme that no longer exists is exactly the kind of cross-run trace the
    # wipe exists to remove. The parent screenshots/ is created implicitly.
    (target / "screenshots" / "visual review").mkdir(parents=True, exist_ok=True)
    # screenshots/build/ holds every non-critic verification shot. Kept separate
    # because tf_gallery.py counts "visual review" PNGs as the header's critique
    # shot total -- mixing the two made that number claim 86 shots on a run
    # whose critic took 10. See tf_paths.build_shots_dir().
    (target / "screenshots" / "build").mkdir(parents=True, exist_ok=True)

    # logs/http.log is the local preview server's access log -- no dedicated
    # script owns writing it (generate-themes's documented server-start
    # command doesn't even redirect to it; a session simply chooses that
    # path when it wants the output captured), so nothing else in the
    # pipeline was ever positioned to clear it. Its lines are nothing but
    # "this URL path was requested at this timestamp," but the URL path
    # embeds the theme slug that was being previewed -- confirmed live, a
    # log from a prior session still had a past run's theme slug in it after
    # every documented wipe step had run, precisely because logs/ is
    # deliberately never walked by the wipe-verification check below (it is
    # long-lived, cross-run diagnostic state, unlike current/). Truncating
    # it here, at the one place every run already passes through before any
    # new preview server starts, closes that gap without touching logs/'s
    # own directory or any future, genuinely-cross-run log file that might
    # live alongside it.
    http_log = home / "logs" / "http.log"
    if http_log.is_file():
        http_log.write_text("", encoding="utf-8")


def main(argv):
    want_json = "--json" in argv
    force = "--force" in argv

    target_override = None
    if "--target" in argv:
        i = argv.index("--target")
        if i + 1 < len(argv):
            target_override = Path(argv[i + 1])

    paths = tf_paths.resolve(create=True)
    target = target_override if target_override is not None else paths.current

    previous = _read_previous(paths.run_json)

    # Warn (don't block) if there's an unexported previous set and no --force.
    unexported = bool(previous) and not previous.get("unreadable") and not previous.get("exported")

    try:
        reset(Path(target), paths.home)
    except ValueError as exc:
        sys.stderr.write("tf_reset: %s\n" % exc)
        if want_json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    # Deterministically prove the wipe actually left no trace — never just
    # trust that shutil.rmtree did what it was asked. Checks the exact target
    # just wiped (not necessarily paths.home/current, if --target overrode it)
    # plus TF_HOME's top level for any leak to the wrong location.
    verify_result = tf_verify_wipe.verify(Path(target), paths.home)
    if not verify_result["ok"]:
        sys.stderr.write(
            "tf_reset: WARNING — post-wipe verification found %d trace(s): %s\n"
            % (verify_result["violation_count"], verify_result["violations_by_category"])
        )

    result = {
        "ok": True,
        "reset": str(Path(target).resolve()),
        "previous_run": previous,
        "previous_unexported": unexported,
        "forced": force,
        "verified_clean": verify_result["ok"],
        "verification": verify_result,
    }
    sys.stderr.write("tf_reset: wiped and recreated %s\n" % target)
    if want_json:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        sys.stderr.write("tf_reset: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
