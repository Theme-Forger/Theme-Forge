#!/usr/bin/env python3
"""tf_seed_knowledge.py -- seed the live knowledge base from the plugin.

Copies plugin_root/knowledge/* into $TF_HOME/knowledge/ for any file that does
not already exist. It NEVER overwrites a live file, because a refresh may have
improved it. `--force` overwrites. Idempotent, silent, fast.

Invoked by the SessionStart hook with --quiet. In that mode it must never fail
the session: any error is swallowed and the process exits 0 regardless.

    python3 tf_seed_knowledge.py [--json] [--force] [--quiet]
"""
from __future__ import annotations

import json
import shutil
import sys

sys.dont_write_bytecode = True  # never leave __pycache__ inside the plugin dir
import tf_paths


def seed(force: bool):
    paths = tf_paths.resolve(create=True)
    src = paths.plugin_knowledge
    dst = paths.knowledge
    copied, skipped = [], []
    if not src or not src.is_dir():
        return {"ok": True, "copied": [], "skipped": [], "note": "no plugin knowledge dir found"}
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if not item.is_file():
            continue
        target = dst / item.name
        if target.exists() and not force:
            skipped.append(item.name)
            continue
        shutil.copy2(item, target)
        copied.append(item.name)
    return {"ok": True, "copied": copied, "skipped": skipped, "knowledge_dir": str(dst)}


def main(argv):
    want_json = "--json" in argv
    force = "--force" in argv
    quiet = "--quiet" in argv
    try:
        result = seed(force)
    except Exception as exc:
        # Hook safety: with --quiet we must never fail the session.
        if quiet:
            return 0
        sys.stderr.write("tf_seed_knowledge: %s\n" % exc)
        if want_json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    if not quiet:
        sys.stderr.write(
            "tf_seed_knowledge: copied %d, skipped %d\n"
            % (len(result["copied"]), len(result["skipped"]))
        )
    if want_json:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    _quiet = "--quiet" in sys.argv[1:]
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        if _quiet:
            sys.exit(0)
        sys.stderr.write("tf_seed_knowledge: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
