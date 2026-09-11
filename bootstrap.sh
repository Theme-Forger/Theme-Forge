#!/usr/bin/env sh
# Run once after cloning to wire the repository's commit hooks.
#   sh bootstrap.sh
set -e

git config core.hooksPath .githooks
echo "Hooks wired: .githooks/pre-commit, commit-msg, pre-push are now active."

if [ ! -f .githooks/.blocked ]; then
  echo ""
  echo "Next step: copy the pattern template and add your own identifiers."
  echo "  cp .githooks/.blocked.example .githooks/.blocked"
fi
