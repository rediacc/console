#!/usr/bin/env bash
# Best-effort submodule initialization for Codespaces.
# Tries each submodule individually so developers get whichever ones
# they have access to, without blocking on the rest.

set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT" || exit 0

if [ ! -f .gitmodules ]; then
  echo "No .gitmodules found, skipping submodule init."
  exit 0
fi

# Parse submodule paths from .gitmodules
mapfile -t SUBMODULES < <(git config --file .gitmodules --get-regexp path | awk '{print $2}')

if [ ${#SUBMODULES[@]} -eq 0 ]; then
  echo "No submodules configured, skipping."
  exit 0
fi

echo "Initializing submodules (best-effort)..."
echo ""

success=0
total=${#SUBMODULES[@]}

for sub in "${SUBMODULES[@]}"; do
  if git submodule update --init --recursive "$sub" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} $sub"
    ((success++))
  else
    echo -e "  ${RED}✗${NC} $sub (no access, skipping)"
  fi
done

echo ""
echo "Initialized $success/$total submodules."

# Always exit 0 so the rest of postCreateCommand continues
exit 0
