# Backup and rollback

The applier backs up **every file it will modify** before the first write. This is the safety
net; it is not optional.

## Backup layout

```
$TF_HOME/current/backups/<timestamp>/        e.g. 2026-08-20T05-14-02Z/
├── THEME-ROLLBACK.md            exact restore commands
├── app/globals.css              copies preserve the project-relative path
├── app/_layout.tsx
└── app.json
```

Only files that existed and are being modified are copied. Files the apply *creates* have no
backup entry — rollback deletes them instead.

## THEME-ROLLBACK.md

Write concrete, copy-pasteable commands. Two forms:

**Clean git tree** — the simplest, most reliable revert:

```sh
# restore modified files and remove created ones
git checkout -- app/globals.css app/_layout.tsx app.json
rm -f src/styles/theme.css theme/theme.ts theme/useTheme.ts THEME.md
```

**No git / dirty tree** — restore from the backup copies:

```sh
BK="$HOME/.theme-forge/current/backups/2026-08-20T05-14-02Z"
cp "$BK/app/globals.css" app/globals.css
cp "$BK/app/_layout.tsx" app/_layout.tsx
cp "$BK/app.json" app.json
rm -f src/styles/theme.css theme/theme.ts theme/useTheme.ts THEME.md
```

List every created file in the `rm` line so a rollback returns the project **exactly** to its
prior state (verify with `git diff` returning empty on a clean tree).

## Notes

- The backup lives under `TF_HOME`, so it survives in place but is wiped on the next
  generate run. If the user may want to revert later, mention that exporting or copying the
  backup elsewhere preserves it.
- Never back up or restore `node_modules/`, lockfiles, `.git/`, or `.env*` — those are never
  touched in the first place.
