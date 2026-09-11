#!/usr/bin/env python3
"""tf_schema_check.py -- validate one theme.json against templates/theme.schema.json.

Nothing validated theme.json against its own schema before this script existed
-- theme.schema.json was documentation only. That gap is exactly how field
drift went undetected: motion.signature_type/signature/visual.signature_motion
all existed as "the same concept" in prose and in a defensive three-way
fallback chain in tf_distinct.py, and a stray top-level or composition-level
key (e.g. a retired `density` field resurfacing) would be silently accepted
forever, because nothing ever checked the declared shape.

This is not a general JSON Schema engine -- theme.schema.json only actually
uses a small, fixed subset of draft-2020-12 (confirmed by scanning the file):
type, required, properties, additionalProperties (bool only), enum, pattern,
items, minItems, $ref/$defs, minimum/maximum. This validator implements
exactly that subset, recursively, against any node the schema constrains --
not just the two top-level checks (required keys, unknown top-level/
composition keys) the schema drift discussion asked for, though those are
the two findings every theme should expect to actually see fire in practice
today, since most nested blocks still declare additionalProperties:true.

Usage:
    python3 tf_schema_check.py --theme <dir> --json
    python3 tf_schema_check.py --selftest

Exit 0 on success (findings do not change exit code -- caller decides
severity, same convention as tf_slop.py). Exit 1 on expected failure (missing
files, bad args). Exit 2 on unexpected error.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _schema_path() -> Path:
    scripts_dir = Path(__file__).resolve().parent
    plugin_root = scripts_dir.parent
    return plugin_root / "templates" / "theme.schema.json"


def _resolve_ref(ref: str, root: dict) -> dict:
    # Only "#/$defs/<name>" refs appear in this schema -- no external refs,
    # no nested pointers beyond one segment.
    assert ref.startswith("#/$defs/"), f"unsupported $ref shape: {ref}"
    name = ref[len("#/$defs/"):]
    return root["$defs"][name]


_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def _validate(node, schema: dict, path: str, root: dict, findings: list[dict]) -> None:
    """Recursively validate *node* against *schema*, appending finding dicts.
    Never raises on a malformed theme.json -- a validator that crashes on the
    exact input it exists to catch problems in is worse than useless."""
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], root)

    expected_type = schema.get("type")
    if expected_type is not None:
        # JSON Schema allows "type" as either one string or a list of
        # alternatives (e.g. ["string", "null"]) -- normalize to a list so
        # both forms share one check.
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        matched = False
        for et in expected_types:
            py_type = _TYPE_MAP.get(et)
            if py_type is None:
                continue
            if et in ("integer", "number") and isinstance(node, bool):
                continue  # bool is a subclass of int; must not satisfy integer/number
            if isinstance(node, py_type):
                matched = True
                break
        if not matched:
            findings.append({
                "path": path,
                "rule": "type",
                "message": f"{path}: expected {expected_type}, got {type(node).__name__}",
            })
            return  # further checks on a wrongly-typed node aren't meaningful

    if "enum" in schema:
        if node not in schema["enum"]:
            findings.append({
                "path": path,
                "rule": "enum",
                "message": f"{path}: {node!r} is not one of {schema['enum']}",
            })

    if "pattern" in schema and isinstance(node, str):
        if not re.match(schema["pattern"], node):
            findings.append({
                "path": path,
                "rule": "pattern",
                "message": f"{path}: {node!r} does not match required pattern {schema['pattern']!r}",
            })

    if isinstance(node, (int, float)) and not isinstance(node, bool):
        if "minimum" in schema and node < schema["minimum"]:
            findings.append({
                "path": path, "rule": "minimum",
                "message": f"{path}: {node} is below minimum {schema['minimum']}",
            })
        if "maximum" in schema and node > schema["maximum"]:
            findings.append({
                "path": path, "rule": "maximum",
                "message": f"{path}: {node} is above maximum {schema['maximum']}",
            })

    if isinstance(node, dict):
        for req_key in schema.get("required", []):
            if req_key not in node:
                findings.append({
                    "path": f"{path}.{req_key}" if path else req_key,
                    "rule": "required",
                    "message": f"{path or '(root)'}: missing required field \"{req_key}\"",
                })

        props = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        if additional is False:
            unknown = [k for k in node if k not in props]
            if unknown:
                findings.append({
                    "path": path or "(root)",
                    "rule": "additionalProperties",
                    "message": (
                        f"{path or '(root)'}: unexpected field(s) {unknown} not declared in "
                        f"theme.schema.json — either a retired name resurfacing or a new field "
                        f"that needs adding to the schema, not silently accepted"
                    ),
                })

        for key, value in node.items():
            if key in props:
                child_path = f"{path}.{key}" if path else key
                _validate(value, props[key], child_path, root, findings)
            elif isinstance(additional, dict):
                # additionalProperties as a schema (e.g. color.ramps) -- every
                # extra key must itself satisfy that schema.
                child_path = f"{path}.{key}" if path else key
                _validate(value, additional, child_path, root, findings)

    elif isinstance(node, list):
        item_schema = schema.get("items")
        if item_schema is not None:
            for i, item in enumerate(node):
                _validate(item, item_schema, f"{path}[{i}]", root, findings)
        if "minItems" in schema and len(node) < schema["minItems"]:
            findings.append({
                "path": path, "rule": "minItems",
                "message": f"{path}: has {len(node)} item(s), needs >= {schema['minItems']}",
            })


def check_theme(theme: dict, schema: dict) -> list[dict]:
    findings: list[dict] = []
    _validate(theme, schema, "", schema, findings)
    return findings


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        schema = {
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"type": "string"},
                "b": {
                    "type": "object",
                    "required": ["x"],
                    "properties": {"x": {"type": "string", "enum": ["one", "two"]}},
                    "additionalProperties": False,
                },
            },
            "additionalProperties": True,
        }
        clean = {"a": "hi", "b": {"x": "one"}}
        assert check_theme(clean, schema) == [], check_theme(clean, schema)

        missing_required = {"b": {"x": "one"}}
        f1 = check_theme(missing_required, schema)
        assert any(f["rule"] == "required" and f["path"] == "a" for f in f1), f1

        bad_enum = {"a": "hi", "b": {"x": "three"}}
        f2 = check_theme(bad_enum, schema)
        assert any(f["rule"] == "enum" for f in f2), f2

        unknown_key = {"a": "hi", "b": {"x": "one", "density": 5}}
        f3 = check_theme(unknown_key, schema)
        assert any(f["rule"] == "additionalProperties" and "density" in f["message"] for f in f3), f3

        wrong_type = {"a": 5, "b": {"x": "one"}}
        f4 = check_theme(wrong_type, schema)
        assert any(f["rule"] == "type" for f in f4), f4

        union_schema = {"type": "object", "properties": {"c": {"type": ["string", "null"]}}}
        assert check_theme({"c": "hi"}, union_schema) == []
        assert check_theme({"c": None}, union_schema) == []
        assert any(f["rule"] == "type" for f in check_theme({"c": 5}, union_schema))

        sys.stderr.write("selftest OK\n")
        print(json.dumps({"ok": True, "selftest": True}))
        return 0

    want_json = "--json" in argv
    theme_dir: Path | None = None
    i = 0
    while i < len(argv):
        if argv[i] == "--theme" and i + 1 < len(argv):
            theme_dir = Path(argv[i + 1]); i += 2
        else:
            i += 1

    if theme_dir is None:
        msg = "--theme <dir> required"
        sys.stderr.write(f"tf_schema_check: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    theme_json_path = theme_dir / "theme.json"
    if not theme_json_path.is_file():
        msg = f"theme.json not found: {theme_json_path}"
        sys.stderr.write(f"tf_schema_check: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    schema_path = _schema_path()
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        theme = json.loads(theme_json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        msg = f"cannot read schema or theme.json: {exc}"
        sys.stderr.write(f"tf_schema_check: {msg}\n")
        print(json.dumps({"ok": False, "error": msg}))
        return 1

    findings = check_theme(theme, schema)

    sys.stderr.write(f"\nSCHEMA CHECK — {theme.get('slug', theme_dir.name)}\n")
    sys.stderr.write("─" * 70 + "\n")
    if findings:
        for f in findings:
            sys.stderr.write(f"  ✗ [{f['rule']}] {f['message']}\n")
    else:
        sys.stderr.write("  ✓ no findings\n")
    sys.stderr.write("─" * 70 + "\n")

    result = {
        "ok": True,
        "slug": theme.get("slug", theme_dir.name),
        "clean": len(findings) == 0,
        "findings": findings,
    }
    if want_json or findings:
        print(json.dumps(result, indent=2 if want_json else None))
    else:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover - unexpected
        sys.stderr.write(f"tf_schema_check: unexpected error: {exc}\n")
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
