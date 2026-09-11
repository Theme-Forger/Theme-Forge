#!/usr/bin/env python3
"""tf_detect_stack.py -- inspect a project and emit a stack profile. No writes.

    python3 tf_detect_stack.py --root . --json

Returns {"ok", "confidence", "platforms", "profile", "targets"}. `platforms`
drives which surfaces the preview emphasizes and which files an apply writes.
Confidence "low" means the applier must ask before doing anything.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_text(p: Path):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def all_deps(pkg):
    deps = {}
    if not isinstance(pkg, dict):
        return deps
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        d = pkg.get(key)
        if isinstance(d, dict):
            deps.update(d)
    return deps


def major_version(spec):
    if not spec or not isinstance(spec, str):
        return None
    m = re.search(r"(\d+)", spec)
    return int(m.group(1)) if m else None


def exists_any(root: Path, names):
    for n in names:
        if (root / n).exists():
            return n
    return None


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------


def detect_web(root: Path, deps, targets, notes):
    framework = "unknown"
    router = None
    if "next" in deps:
        framework = "nextjs"
        if (root / "app").is_dir() or (root / "src" / "app").is_dir():
            router = "app"
        elif (root / "pages").is_dir() or (root / "src" / "pages").is_dir():
            router = "pages"
    elif "@remix-run/react" in deps or "@remix-run/node" in deps:
        framework = "remix"
    elif "@sveltejs/kit" in deps:
        framework = "sveltekit"
    elif "nuxt" in deps:
        framework = "nuxt"
    elif "astro" in deps:
        framework = "astro"
    elif "react-scripts" in deps:
        framework = "cra"
    elif "vite" in deps or exists_any(root, ["vite.config.js", "vite.config.ts", "vite.config.mjs"]):
        framework = "vite"
    elif (root / "index.html").is_file():
        framework = "plain"

    # styling
    styling = "unknown"
    tw_major = major_version(deps.get("tailwindcss"))
    # scan a couple of likely stylesheets for the v4 CSS-first import
    css_candidates = []
    for pat in ("app/globals.css", "src/app/globals.css", "src/index.css", "styles/globals.css",
                "src/styles/globals.css", "src/main.css", "app.css", "styles.css", "index.css",
                "src/App.css", "src/styles.css"):
        p = root / pat
        if p.is_file():
            css_candidates.append(p)
    v4_import = False
    for p in css_candidates:
        if '@import "tailwindcss"' in read_text(p) or "@import 'tailwindcss'" in read_text(p):
            v4_import = True

    has_tw_config = exists_any(root, ["tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs", "tailwind.config.mjs"])

    if v4_import or (tw_major == 4):
        styling = "tailwind-v4"
    elif has_tw_config or (tw_major == 3):
        styling = "tailwind-v3"
    elif "styled-components" in deps:
        styling = "styled-components"
    elif "@emotion/react" in deps or "@emotion/styled" in deps:
        styling = "emotion"
    elif "sass" in deps or "node-sass" in deps:
        styling = "sass"
    elif css_candidates or (framework == "plain"):
        styling = "vanilla-css"

    # component system
    components = "none"
    if (root / "components.json").is_file():
        components = "shadcn"
    elif "@mui/material" in deps:
        components = "mui"
    elif "@chakra-ui/react" in deps:
        components = "chakra"
    elif "@mantine/core" in deps:
        components = "mantine"
    elif "@base-ui-components/react" in deps or "@base_ui/react" in deps:
        components = "base-ui"
    elif "radix-ui" in deps or any(k.startswith("@radix-ui/") for k in deps):
        components = "radix"

    # targets
    for p in css_candidates:
        targets.append({"path": str(p.relative_to(root)), "role": "global-stylesheet"})
    for lay in ("app/layout.tsx", "src/app/layout.tsx", "app/layout.jsx", "pages/_app.tsx", "src/pages/_app.tsx"):
        p = root / lay
        if p.is_file():
            targets.append({"path": lay, "role": "root-layout"})
    if (root / "index.html").is_file():
        targets.append({"path": "index.html", "role": "html-entry"})
    if components == "shadcn":
        cj = read_json(root / "components.json")
        if isinstance(cj, dict):
            css = (cj.get("tailwind") or {}).get("css")
            if css and not any(t["path"] == css for t in targets):
                targets.append({"path": css, "role": "global-stylesheet"})

    return {
        "framework": framework,
        "router": router,
        "styling": styling,
        "components": components,
        "tailwind_major": tw_major,
    }


# ---------------------------------------------------------------------------
# Native
# ---------------------------------------------------------------------------


def detect_native(root: Path, deps, targets, notes):
    app_json_path = exists_any(root, ["app.json", "app.config.js", "app.config.ts"])
    has_expo = "expo" in deps or (app_json_path and app_json_path.startswith("app.config")) or \
        (app_json_path == "app.json" and isinstance(read_json(root / "app.json"), dict)
         and "expo" in (read_json(root / "app.json") or {}))
    bare = (root / "ios").is_dir() and (root / "android").is_dir() and \
        exists_any(root, ["metro.config.js", "metro.config.ts"]) is not None
    has_rn = "react-native" in deps

    if not (has_expo or bare or has_rn):
        return None

    kind = "expo" if has_expo else ("bare" if bare else "react-native")
    sdk = major_version(deps.get("expo")) if has_expo else None

    # router / navigation
    router = None
    if "expo-router" in deps and ((root / "app").is_dir() or (root / "src" / "app").is_dir()):
        router = "expo-router"
    elif any(k.startswith("@react-navigation/") for k in deps):
        router = "react-navigation"

    # styling
    styling = "stylesheet"
    nw_major = major_version(deps.get("nativewind"))
    if "nativewind" in deps:
        styling = "nativewind"
    elif "tamagui" in deps or "@tamagui/core" in deps:
        styling = "tamagui"
    elif "@gluestack-ui/themed" in deps or "@gluestack-style/react" in deps:
        styling = "gluestack"
    elif "@shopify/restyle" in deps:
        styling = "restyle"

    dev_client = "expo-dev-client" in deps
    has_fonts = "expo-font" in deps or any(k.startswith("@expo-google-fonts/") for k in deps)

    # app.json icon / splash / adaptive fields
    icon_fields = {}
    if app_json_path == "app.json":
        aj = read_json(root / "app.json") or {}
        expo_cfg = aj.get("expo", aj)
        if isinstance(expo_cfg, dict):
            for f in ("icon", "userInterfaceStyle"):
                if f in expo_cfg:
                    icon_fields[f] = expo_cfg[f]
            if isinstance(expo_cfg.get("splash"), dict):
                icon_fields["splash"] = expo_cfg["splash"]
            android = expo_cfg.get("android", {})
            if isinstance(android, dict) and "adaptiveIcon" in android:
                icon_fields["adaptiveIcon"] = android["adaptiveIcon"]
            targets.append({"path": "app.json", "role": "expo-config",
                            "fields": ["icon", "splash", "android.adaptiveIcon", "userInterfaceStyle"]})

    # root layout target
    for lay in ("app/_layout.tsx", "src/app/_layout.tsx", "app/_layout.js"):
        p = root / lay
        if p.is_file():
            targets.append({"path": lay, "role": "native-root-layout"})

    return {
        "kind": kind,
        "expo_sdk": sdk,
        "router": router,
        "styling": styling,
        "nativewind_major": nw_major,
        "dev_client": dev_client,
        "has_fonts": has_fonts,
        "icon_fields": icon_fields,
    }


# ---------------------------------------------------------------------------
# Monorepo
# ---------------------------------------------------------------------------


def parse_pnpm_workspace(root: Path):
    p = root / "pnpm-workspace.yaml"
    if not p.is_file():
        return None
    globs = []
    in_pkgs = False
    for line in read_text(p).splitlines():
        s = line.strip()
        if s.startswith("packages:"):
            in_pkgs = True
            continue
        if in_pkgs:
            m = re.match(r"-\s*['\"]?([^'\"]+)['\"]?", s)
            if m:
                globs.append(m.group(1))
            elif s and not s.startswith("-"):
                in_pkgs = False
    return globs


def classify_package(pkg_dir: Path):
    pkg = read_json(pkg_dir / "package.json")
    if not isinstance(pkg, dict):
        return None
    deps = all_deps(pkg)
    name = pkg.get("name", pkg_dir.name)
    is_native = "expo" in deps or "react-native" in deps
    is_web = any(k in deps for k in ("next", "vite", "react-dom", "astro", "@remix-run/react", "nuxt")) \
        or (pkg_dir / "index.html").is_file()
    if is_native:
        kind = "native-app"
    elif is_web:
        kind = "web-app"
    elif pkg.get("main") or pkg.get("module") or pkg.get("exports"):
        kind = "shared-lib"
    else:
        kind = "unknown"
    return {"name": name, "path": pkg_dir.name if pkg_dir.parent == pkg_dir.parent else str(pkg_dir),
            "kind": kind}


def detect_monorepo(root: Path):
    tool = None
    globs = []
    pnpm = parse_pnpm_workspace(root)
    if pnpm is not None:
        tool = "pnpm"
        globs = pnpm
    else:
        pkg = read_json(root / "package.json") or {}
        ws = pkg.get("workspaces")
        if isinstance(ws, list):
            tool = "npm/yarn"
            globs = ws
        elif isinstance(ws, dict) and isinstance(ws.get("packages"), list):
            tool = "npm/yarn"
            globs = ws["packages"]
    if (root / "turbo.json").is_file():
        tool = (tool + "+turbo") if tool else "turbo"
    if (root / "nx.json").is_file():
        tool = (tool + "+nx") if tool else "nx"

    if not globs and not tool:
        return None

    packages = []
    for g in globs:
        g = g.rstrip("/")
        if g.endswith("/*"):
            base = root / g[:-2]
            if base.is_dir():
                for child in sorted(base.iterdir()):
                    if child.is_dir() and (child / "package.json").is_file():
                        info = classify_package(child)
                        if info:
                            info["path"] = str(child.relative_to(root)).replace(os.sep, "/")
                            packages.append(info)
        else:
            child = root / g
            if child.is_dir() and (child / "package.json").is_file():
                info = classify_package(child)
                if info:
                    info["path"] = str(child.relative_to(root)).replace(os.sep, "/")
                    packages.append(info)

    kinds = {p["kind"] for p in packages}
    cross_platform = "web-app" in kinds and "native-app" in kinds
    return {"tool": tool, "packages": packages, "cross_platform": cross_platform}


# ---------------------------------------------------------------------------
# Git + assembly
# ---------------------------------------------------------------------------


def detect_git(root: Path):
    if not (root / ".git").exists():
        return {"present": False, "clean": None}
    try:
        out = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                             capture_output=True, text=True, timeout=5)
        clean = (out.returncode == 0 and out.stdout.strip() == "")
        return {"present": True, "clean": clean}
    except Exception:
        return {"present": True, "clean": None}


def detect(root: Path):
    root = root.resolve()
    pkg = read_json(root / "package.json")
    deps = all_deps(pkg)
    targets = []
    notes = []

    monorepo = detect_monorepo(root)
    web = detect_web(root, deps, targets, notes)
    native = detect_native(root, deps, targets, notes)

    # Normalize path separators and drop duplicates (keep first-seen order).
    seen = set()
    deduped = []
    for t in targets:
        t["path"] = str(t["path"]).replace(os.sep, "/").replace("\\", "/")
        key = (t["path"], t.get("role"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    targets = deduped

    platforms = []
    if monorepo:
        kinds = {p["kind"] for p in monorepo["packages"]}
        if "web-app" in kinds:
            platforms.append("web")
        if "native-app" in kinds:
            platforms.append("native")
    if native and "native" not in platforms:
        platforms.append("native")
    if web and web.get("framework") not in (None, "unknown") and "web" not in platforms:
        platforms.append("web")
    if not platforms and web:
        platforms.append("web")

    # confidence
    confidence = "high"
    web_known = web and web.get("framework") not in ("unknown", "plain")
    if native or monorepo or web_known:
        confidence = "high"
    if web and web.get("framework") == "plain":
        confidence = "low"
    if not deps and not native and not monorepo and not (root / "index.html").is_file():
        confidence = "low"
    if web and web.get("framework") == "unknown" and not native and not monorepo:
        confidence = "low"

    profile = {"web": web, "native": native, "monorepo": monorepo,
               "git": detect_git(root),
               "has_theme_md": (root / "THEME.md").is_file(),
               "package_json": bool(pkg)}

    return {"ok": True, "confidence": confidence, "platforms": platforms,
            "profile": profile, "targets": targets, "notes": notes}


def main(argv):
    want_json = "--json" in argv
    root = Path(".")
    if "--root" in argv:
        i = argv.index("--root")
        root = Path(argv[i + 1])
    result = detect(root)
    sys.stderr.write("tf_detect_stack: confidence=%s platforms=%s\n"
                     % (result["confidence"], result["platforms"]))
    if want_json:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # pragma: no cover
        sys.stderr.write("tf_detect_stack: unexpected error: %s\n" % exc)
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)
