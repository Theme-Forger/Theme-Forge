#!/usr/bin/env python3
"""tf_native.py -- the translation gate between a theme and React Native.

It walks a theme.json's native resolution and rejects anything React Native
cannot consume: CSS color/length functions where a resolved value is required,
unit-suffixed dimension strings, a multiplier lineHeight, em letter-spacing, a
fontWeight on a custom family with no correspondingly-named family, a CSS
box-shadow string, an Android elevation carrying a color or offset, and web-only
style properties.

With --emit it writes native/theme.ts, native/tailwind.config.js, and
native/useTheme.ts deterministically from the validated resolution, so the
designer agent supplies values, not files.

    python3 tf_native.py --theme <theme-dir> --json [--emit]

Writes native.json. Exit 1 on violations.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Substring checks are safe here: 'rgb(' is not a substring of 'rgba(', and
# 'hsl(' is not a substring of 'hsla(' -- so rgba()/hsla() stay allowed.
FORBIDDEN_FUNCS = ["oklch(", "color-mix(", "light-dark(", "clamp(", "var(",
                   "calc(", "env(", "hsl(", "rgb("]

# Web-only style properties that must never appear in a native resolution.
FORBIDDEN_PROPS = ["backdropFilter", "backdrop-filter", "filter", "transition",
                   "cursor", "boxSizing", "box-sizing", "float",
                   "gridTemplateColumns", "gridTemplateRows", "grid", "gridColumn",
                   "gridRow", "gridArea"]

UNIT_RE = re.compile(r"^-?\d*\.?\d+(px|rem|em|vw|vh|vmin|vmax|pt|ch|ex|cm|mm|in|pc)$", re.I)
HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
RGBA_RE = re.compile(r"^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*(0|1|0?\.\d+)\s*\)$", re.I)


def _has_forbidden_func(s: str):
    low = s.lower()
    for f in FORBIDDEN_FUNCS:
        if f in low:
            return f
    return None


class Report:
    def __init__(self):
        self.checked = 0
        self.violations = []
        self.warnings = []
        self.requires_packages = set()
        self.requires_dev_build = False
        self.native_rasterized = []  # [{source, reason}]

    def check(self):
        self.checked += 1

    def violate(self, token, rule, note):
        self.violations.append({"token": token, "rule": rule, "note": note})

    def warn(self, token, note):
        self.warnings.append({"token": token, "note": note})


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def check_color(rep: Report, token, value):
    """A native color must be a resolved hex (or rgba string)."""
    rep.check()
    hexv = value.get("hex") if isinstance(value, dict) else value
    rgba = value.get("rgba") if isinstance(value, dict) else None
    if hexv is None and rgba is None:
        rep.violate(token, "native-color-unresolved", "no hex/rgba resolution present")
        return
    for candidate in (hexv, rgba):
        if candidate is None:
            continue
        if not isinstance(candidate, str):
            rep.violate(token, "native-color-unresolved", "color is not a string: %r" % candidate)
            continue
        bad = _has_forbidden_func(candidate)
        if bad:
            rep.violate(token, "native-color-unresolved",
                        "color contains CSS function %r; must be resolved hex/rgba (got %r)" % (bad, candidate))
            continue
        if not (HEX_RE.match(candidate) or RGBA_RE.match(candidate)):
            rep.violate(token, "native-color-unresolved",
                        "color %r is neither a hex nor an rgba() literal" % candidate)


def check_dimension(rep: Report, token, value, kind="dimension"):
    """A native dimension must be a unitless number."""
    rep.check()
    if isinstance(value, str):
        if UNIT_RE.match(value.strip()):
            rep.violate(token, "dimension-string-with-unit",
                        "%s is a unit-suffixed string %r; React Native takes unitless numbers" % (kind, value))
        else:
            rep.violate(token, "dimension-not-number",
                        "%s is a string %r; React Native takes unitless numbers" % (kind, value))
        return None
    if not _is_number(value):
        rep.violate(token, "dimension-not-number", "%s is not a number: %r" % (kind, value))
        return None
    return value


def check_lineheight(rep: Report, token, value, font_px=None):
    """React Native lineHeight is absolute px, never a multiplier."""
    rep.check()
    if not _is_number(value):
        rep.violate(token, "lineheight-not-number", "lineHeight %r is not a number" % value)
        return
    if value < 4:
        rep.violate(token, "lineheight-multiplier",
                    "lineHeight %r looks like a multiplier; RN lineHeight is absolute px (pre-multiply)" % value)
    if font_px is not None and _is_number(font_px) and value <= font_px:
        rep.warn(token, "absolute lineHeight %s is not greater than font size %s" % (value, font_px))


def check_tracking(rep: Report, token, value):
    """React Native letterSpacing is absolute; em is not allowed."""
    rep.check()
    if isinstance(value, str):
        if "em" in value.lower() or UNIT_RE.match(value.strip()):
            rep.violate(token, "letterspacing-em",
                        "letterSpacing %r uses a unit; RN letterSpacing is an absolute number" % value)
        else:
            rep.violate(token, "letterspacing-not-number", "letterSpacing %r is not a number" % value)
        return
    if not _is_number(value):
        rep.violate(token, "letterspacing-not-number", "letterSpacing %r is not a number" % value)


def check_typography(rep: Report, typ):
    for role in ("display", "body", "mono"):
        r = typ.get(role)
        if not isinstance(r, dict):
            continue
        weights = r.get("weights", [])
        native = r.get("native", {})
        families = native.get("families", {}) if isinstance(native, dict) else {}
        source = r.get("source")
        pkg = native.get("package") if isinstance(native, dict) else None
        for w in weights:
            rep.check()
            key = str(w)
            if key not in families:
                rep.violate("typography.%s.weight.%s" % (role, key), "fontweight-without-family",
                            "weight %s has no registered native family; RN will not synthesize it "
                            "(one family name per weight)" % key)
            else:
                fam = families[key]
                if not isinstance(fam, str) or not fam:
                    rep.violate("typography.%s.families.%s" % (role, key), "fontweight-without-family",
                                "family name for weight %s is empty" % key)
        # A custom (non-system) font needs an install package.
        if source and source not in ("system",) and pkg:
            rep.requires_packages.add(pkg)

    scale = typ.get("scale", {})
    for name, step in (scale.get("steps", {}) or {}).items():
        if isinstance(step, dict):
            check_dimension(rep, "typography.scale.%s" % name, step.get("px"), "font size")

    # base font size, for the lineHeight sanity comparison
    base_px = None
    base = (scale.get("steps", {}) or {}).get("base")
    if isinstance(base, dict) and _is_number(base.get("px")):
        base_px = base["px"]

    for name, val in (typ.get("leading", {}) or {}).items():
        if isinstance(val, dict):
            check_lineheight(rep, "typography.leading.%s" % name, val.get("px_at_base"), base_px)
    for name, val in (typ.get("tracking", {}) or {}).items():
        if isinstance(val, dict):
            check_tracking(rep, "typography.tracking.%s" % name, val.get("px_at_base"))


def check_elevation(rep: Report, elev):
    levels = elev.get("levels", {})
    for name, lvl in levels.items():
        rep.check()
        if not isinstance(lvl, dict):
            rep.violate("elevation.%s" % name, "shadow-css-string",
                        "elevation level is not a split object")
            continue
        ios = lvl.get("ios")
        android = lvl.get("android")
        if isinstance(ios, str) or isinstance(android, str):
            rep.violate("elevation.%s" % name, "shadow-css-string",
                        "elevation is a CSS box-shadow string; needs split ios{} / android{}")
            continue
        if ios is None:
            rep.violate("elevation.%s.ios" % name, "shadow-missing-platform", "no ios shadow object")
        if android is None:
            rep.violate("elevation.%s.android" % name, "shadow-missing-platform", "no android elevation object")
        if isinstance(android, dict):
            for k in android:
                if "color" in k.lower():
                    rep.violate("elevation.%s.android.%s" % (name, k), "android-shadow-color",
                                "Android elevation cannot be colored")
                if "offset" in k.lower():
                    rep.violate("elevation.%s.android.%s" % (name, k), "android-shadow-offset",
                                "Android elevation cannot be offset")
            if "elevation" not in android:
                rep.warn("elevation.%s.android" % name, "android object has no 'elevation' integer")
            elif not _is_number(android.get("elevation")):
                rep.violate("elevation.%s.android.elevation" % name, "dimension-not-number",
                            "elevation must be an integer")
    # glass strategy implies a native module + dev build
    glass = elev.get("glass")
    if isinstance(glass, dict):
        nat = glass.get("native", {})
        pkg = nat.get("package")
        if pkg:
            rep.requires_packages.add(pkg)
            rep.requires_dev_build = True
        if "fallback" not in nat:
            rep.warn("elevation.glass.native", "glass has no designed non-blur fallback")


def scan_forbidden_props(rep: Report, obj, path="native"):
    """Catch web-only style properties anywhere in the native resolution."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_PROPS:
                rep.violate("%s.%s" % (path, k), "forbidden-native-property",
                            "%s has no React Native equivalent" % k)
            if k == "zIndex" and not (isinstance(v, int) and not isinstance(v, bool)):
                rep.violate("%s.zIndex" % path, "forbidden-native-property", "zIndex must be an integer")
            if k in ("gap", "rowGap", "columnGap") and isinstance(v, str) and v.strip().endswith("%"):
                rep.violate("%s.%s" % (path, k), "forbidden-native-property",
                            "percentage gap is not supported in React Native")
            scan_forbidden_props(rep, v, "%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            scan_forbidden_props(rep, v, "%s[%d]" % (path, i))


def build_native_resolution(theme):
    """Extract the flat, RN-facing view used for emit and generic scanning."""
    color = theme.get("color", {})
    typ = theme.get("typography", {})

    def colmap(d):
        out = {}
        for k, v in (d or {}).items():
            if isinstance(v, dict) and ("hex" in v or "rgba" in v):
                out[k] = v.get("rgba") or v.get("hex")
        return out

    ramps = {}
    for rname, steps in (color.get("ramps", {}) or {}).items():
        ramps[rname] = {str(s): (v.get("hex") if isinstance(v, dict) else v) for s, v in steps.items()}

    radius = {k: (v.get("px") if isinstance(v, dict) else v) for k, v in (theme.get("radius", {}) or {}).items()}

    scale = {}
    lead_mult = None
    steps = (typ.get("scale", {}) or {}).get("steps", {}) or {}
    for name, step in steps.items():
        if isinstance(step, dict) and _is_number(step.get("px")):
            scale[name] = step["px"]
    leading = typ.get("leading", {}) or {}
    if isinstance(leading.get("normal"), dict):
        lm = leading["normal"].get("css")
        if _is_number(lm):
            lead_mult = lm

    def role(role_name):
        r = typ.get(role_name, {})
        native = r.get("native", {}) if isinstance(r, dict) else {}
        return {
            "families": native.get("families", {}),
            "fallback_ios": native.get("fallback_ios"),
            "fallback_android": native.get("fallback_android"),
        }

    # Elevation: keep ONLY the native-facing parts (ios/android split, glass.native).
    # The `css` string is the web resolution and must not be scanned as native.
    raw_elev = theme.get("elevation", {}) or {}
    native_elev = {"strategy": raw_elev.get("strategy"), "native_strategy": raw_elev.get("native_strategy"),
                   "levels": {}}
    for n, lvl in (raw_elev.get("levels", {}) or {}).items():
        if isinstance(lvl, dict):
            native_elev["levels"][n] = {"ios": lvl.get("ios"), "android": lvl.get("android")}
    if isinstance(raw_elev.get("glass"), dict):
        native_elev["glass"] = {"native": raw_elev["glass"].get("native")}

    # Motion: keep the reanimated easing forms and durations, drop css strings.
    raw_motion = theme.get("motion", {}) or {}
    native_motion = {"character": raw_motion.get("character"), "duration": raw_motion.get("duration", {})}
    reanimated = {}
    for k, v in (raw_motion.get("easing", {}) or {}).items():
        if isinstance(v, dict) and "reanimated" in v:
            reanimated[k] = v["reanimated"]
    native_motion["easing"] = reanimated

    return {
        "colors": {"light": colmap(color.get("light")), "dark": colmap(color.get("dark")),
                   "semantic": colmap(color.get("semantic")), "ramps": ramps},
        "radius": radius,
        "space": theme.get("space", {}).get("scale", []),
        "scale": scale,
        "leading_multiplier": lead_mult,
        "typography": {"display": role("display"), "body": role("body"), "mono": role("mono")},
        "elevation": native_elev,
        "motion": native_motion,
    }


def scan_native_leaves(rep: Report, native):
    """Generic backstop: no CSS function may survive into a native value."""
    def walk(o, path):
        if isinstance(o, str):
            bad = _has_forbidden_func(o)
            if bad:
                rep.violate(path, "native-color-unresolved",
                            "value contains CSS function %r: %r" % (bad, o))
            elif UNIT_RE.match(o.strip()):
                rep.violate(path, "dimension-string-with-unit",
                            "unit-suffixed string %r in native resolution" % o)
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, "%s.%s" % (path, k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, "%s[%d]" % (path, i))
    walk(native, "native")


# ---------------------------------------------------------------------------
# SVG asset checks (Phase 9 extension)
# ---------------------------------------------------------------------------

def _check_svg_assets(rep: Report, theme: dict, theme_dir: "Path | None") -> None:
    """Validate platform_assets.native SVG entries against PNG counterpart rules."""
    platform_assets = theme.get("platform_assets") or {}
    assets = theme.get("assets") or {}

    native_list = platform_assets.get("native") or []
    if not isinstance(native_list, list):
        return

    for path_str in native_list:
        if not isinstance(path_str, str) or not path_str.endswith(".svg"):
            continue

        rep.check()

        if theme_dir is None:
            rep.warn(
                "platform_assets.native",
                "SVG in native asset list: %s (cannot verify PNG counterparts without theme dir)"
                % path_str,
            )
            continue

        svg_path = theme_dir / path_str
        stem = Path(path_str).stem
        native_dir = theme_dir / "brand" / "native"
        counterparts = [
            native_dir / ("%s@1x.png" % stem),
            native_dir / ("%s@2x.png" % stem),
            native_dir / ("%s@3x.png" % stem),
        ]
        has_all = all(p.is_file() for p in counterparts)

        if not has_all:
            rep.violate(
                "platform_assets.native",
                "native-svg-without-png",
                "SVG in platform_assets.native without PNG counterparts: %s" % path_str,
            )
        else:
            # Has PNG counterparts -- warn if mask or pattern present
            if svg_path.is_file():
                try:
                    content = svg_path.read_text(encoding="utf-8", errors="replace")
                    if "<mask" in content or "<pattern" in content:
                        rep.warn(
                            "platform_assets.native.%s" % path_str,
                            "mask/pattern in native-bound SVG: %s" % path_str,
                        )
                except Exception:
                    pass

            # Infer rasterization reason
            native_rast_reasons = (
                platform_assets.get("native_rasterized_reason") or {}
            )
            reason = native_rast_reasons.get(path_str)
            if not reason and svg_path.is_file():
                try:
                    content = svg_path.read_text(encoding="utf-8", errors="replace")
                    if "<filter" in content or any(
                        fe in content
                        for fe in ("feGaussianBlur", "feTurbulence", "feDropShadow",
                                   "feBlend", "feFlood", "feOffset")
                    ):
                        reason = "SVG filter unsupported in react-native-svg"
                    else:
                        reason = "rasterized for native compatibility"
                except Exception:
                    reason = "rasterized for native compatibility"
            if not reason:
                reason = "rasterized for native compatibility"
            rep.native_rasterized.append({"source": path_str, "reason": reason})

    # Check for stray .svg paths inside native/theme.ts
    if theme_dir is not None:
        theme_ts = theme_dir / "native" / "theme.ts"
        if theme_ts.is_file():
            try:
                ts_content = theme_ts.read_text(encoding="utf-8", errors="replace")
                import re as _re
                svg_refs = _re.findall(r'["\'][^"\']*\.svg["\']', ts_content)
                for ref in svg_refs:
                    rep.violate(
                        "native/theme.ts",
                        "svg-in-native-theme-ts",
                        "SVG path in native/theme.ts -- use Reanimated, not SVG animation: %s"
                        % ref,
                    )
            except Exception:
                pass


def validate(theme, theme_dir=None):
    rep = Report()
    color = theme.get("color", {})
    for mode in ("light", "dark"):
        for k, v in (color.get(mode, {}) or {}).items():
            check_color(rep, "color.%s.%s" % (mode, k), v)
    for k, v in (color.get("semantic", {}) or {}).items():
        check_color(rep, "color.semantic.%s" % k, v)
    for rname, steps in (color.get("ramps", {}) or {}).items():
        for s, v in steps.items():
            check_color(rep, "color.ramps.%s.%s" % (rname, s), v)

    for k, v in (theme.get("radius", {}) or {}).items():
        if isinstance(v, dict):
            check_dimension(rep, "radius.%s" % k, v.get("px"), "radius")

    check_typography(rep, theme.get("typography", {}))
    check_elevation(rep, theme.get("elevation", {}))

    native = build_native_resolution(theme)
    scan_native_leaves(rep, native)
    scan_forbidden_props(rep, native)

    # SVG asset checks (schema v3 additions; old themes may not have these keys)
    _check_svg_assets(rep, theme, theme_dir)

    # packages declared on the theme itself
    for p in theme.get("requires_packages", []) or []:
        rep.requires_packages.add(p)
    if theme.get("requires_dev_build"):
        rep.requires_dev_build = True

    return rep, native


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------


def _ts_obj(o, indent=1):
    pad = "  " * indent
    if isinstance(o, dict):
        if not o:
            return "{}"
        lines = ["{"]
        for k, v in o.items():
            key = k if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", str(k)) else json.dumps(str(k))
            lines.append("%s%s: %s," % (pad, key, _ts_obj(v, indent + 1)))
        lines.append("%s}" % ("  " * (indent - 1)))
        return "\n".join(lines)
    if isinstance(o, list):
        return "[" + ", ".join(_ts_obj(x, indent) for x in o) + "]"
    if isinstance(o, bool):
        return "true" if o else "false"
    if o is None:
        return "null"
    if isinstance(o, (int, float)):
        return repr(o)
    return json.dumps(o)


def emit(theme, native, theme_dir: Path):
    slug = theme.get("slug", "theme")
    name = theme.get("name", slug)
    native_dir = theme_dir / "native"
    native_dir.mkdir(parents=True, exist_ok=True)

    lead_mult = native.get("leading_multiplier") or 1.5

    # Build type styles with absolute lineHeight (always > font size).
    type_styles = {}
    for step_name, px in native["scale"].items():
        type_styles[step_name] = {"fontSize": px, "lineHeight": int(round(px * lead_mult))}

    def role_families(role):
        fams = native["typography"][role]["families"] or {}
        # default family: the middle/regular weight if present
        default = None
        for pref in ("400", "500", "600", "700"):
            if pref in fams:
                default = fams[pref]
                break
        if default is None and fams:
            default = list(fams.values())[0]
        return {"families": fams, "default": default,
                "fallbackIOS": native["typography"][role]["fallback_ios"],
                "fallbackAndroid": native["typography"][role]["fallback_android"]}

    elevation = native["elevation"]
    levels_ios = {}
    levels_android = {}
    for lname, lvl in (elevation.get("levels", {}) or {}).items():
        if isinstance(lvl, dict):
            if isinstance(lvl.get("ios"), dict):
                levels_ios[lname] = lvl["ios"]
            if isinstance(lvl.get("android"), dict):
                levels_android[lname] = lvl["android"]

    motion = native.get("motion", {})
    durations = motion.get("duration", {})

    theme_obj = {
        "name": name,
        "slug": slug,
        "colors": {"light": native["colors"]["light"], "dark": native["colors"]["dark"]},
        "semantic": native["colors"]["semantic"],
        "ramps": native["colors"]["ramps"],
        "radius": native["radius"],
        "space": native["space"],
        "type": type_styles,
        "fonts": {"display": role_families("display"), "body": role_families("body"), "mono": role_families("mono")},
        "elevation": {"ios": levels_ios, "android": levels_android,
                      "strategy": elevation.get("native_strategy", elevation.get("strategy"))},
        "motion": {"duration": durations,
                   "easing": motion.get("easing", {}),
                   "spring": motion.get("easing", {}).get("spring")},
    }

    header = ("// %s -- generated by tf_native.py. Do not edit by hand.\n"
              "// Flat React Native theme: unitless numbers, resolved hex colors,\n"
              "// absolute lineHeight, one family name per weight.\n\n" % name)
    theme_ts = header + "export const theme = " + _ts_obj(theme_obj, 1) + " as const;\n\n" \
        "export type Theme = typeof theme;\nexport default theme;\n"
    (native_dir / "theme.ts").write_text(theme_ts, encoding="utf-8")

    # useTheme.ts backed by useColorScheme()
    use_theme = (
        "// useTheme.ts -- generated by tf_native.py. Do not edit by hand.\n"
        "import { useColorScheme } from 'react-native';\n"
        "import { theme } from './theme';\n\n"
        "export function useTheme() {\n"
        "  const scheme = useColorScheme() ?? 'light';\n"
        "  const colors = scheme === 'dark' ? theme.colors.dark : theme.colors.light;\n"
        "  return {\n"
        "    scheme,\n"
        "    colors,\n"
        "    semantic: theme.semantic,\n"
        "    ramps: theme.ramps,\n"
        "    radius: theme.radius,\n"
        "    space: theme.space,\n"
        "    type: theme.type,\n"
        "    fonts: theme.fonts,\n"
        "    elevation: scheme === 'dark' ? theme.elevation.android : theme.elevation.ios,\n"
        "    elevationIOS: theme.elevation.ios,\n"
        "    elevationAndroid: theme.elevation.android,\n"
        "    motion: theme.motion,\n"
        "  } as const;\n"
        "}\n\nexport default useTheme;\n"
    )
    (native_dir / "useTheme.ts").write_text(use_theme, encoding="utf-8")

    # NativeWind v4 config fragment (Tailwind v3-shaped, NOT v4 @theme).
    tw_colors = {}
    for k, v in native["colors"]["light"].items():
        tw_colors[k] = v
    for rname, steps in native["colors"]["ramps"].items():
        tw_colors[rname] = steps
    tw = {
        "theme": {
            "extend": {
                "colors": tw_colors,
                "borderRadius": {k: str(v) for k, v in native["radius"].items()},
                "fontFamily": {
                    "display": [role_families("display")["default"] or "System"],
                    "body": [role_families("body")["default"] or "System"],
                    "mono": [role_families("mono")["default"] or "monospace"],
                },
            }
        }
    }
    tw_js = ("// tailwind.config.js fragment -- generated by tf_native.py.\n"
             "// NativeWind v4 consumes a Tailwind v3-shaped config (NOT the web v4 @theme block).\n"
             "// Merge `theme.extend` into your project's tailwind.config.js.\n"
             "/** @type {import('tailwindcss').Config} */\n"
             "module.exports = " + _ts_obj(tw, 1) + ";\n")
    (native_dir / "tailwind.config.js").write_text(tw_js, encoding="utf-8")

    return [str(native_dir / "theme.ts"), str(native_dir / "useTheme.ts"),
            str(native_dir / "tailwind.config.js")]


def main(argv):
    want_json = "--json" in argv
    do_emit = "--emit" in argv
    if "--theme" not in argv:
        sys.stderr.write("usage: tf_native.py --theme <dir> --json [--emit]\n")
        print(json.dumps({"ok": False, "error": "missing --theme"}))
        return 1
    i = argv.index("--theme")
    theme_dir = Path(argv[i + 1])
    theme_json = theme_dir / "theme.json"
    if not theme_json.is_file():
        sys.stderr.write("tf_native: no theme.json in %s\n" % theme_dir)
        print(json.dumps({"ok": False, "error": "no theme.json"}))
        return 1

    theme = json.loads(theme_json.read_text(encoding="utf-8"))
    rep, native = validate(theme, theme_dir=theme_dir)

    emitted = []
    if do_emit and not rep.violations:
        emitted = emit(theme, native, theme_dir)

    report = {
        "ok": len(rep.violations) == 0,
        "checked": rep.checked,
        "violations": rep.violations,
        "warnings": rep.warnings,
        "requires_packages": sorted(rep.requires_packages),
        "requires_dev_build": rep.requires_dev_build,
        "native_rasterized": rep.native_rasterized,
        "emitted": emitted,
    }
    (theme_dir / "native.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    sys.stderr.write("tf_native: %d checked, %d violations, %d warnings\n"
                     % (rep.checked, len(rep.violations), len(rep.warnings)))
    for v in rep.violations:
        sys.stderr.write("  VIOLATION [%s] %s: %s\n" % (v["rule"], v["token"], v["note"]))
    if do_emit and rep.violations:
        sys.stderr.write("tf_native: not emitting -- fix violations first\n")
    if want_json:
        print(json.dumps(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        sys.stderr.write("tf_native: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
