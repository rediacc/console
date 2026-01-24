#!/bin/bash
# Resolve externalized modules and their transitive dependencies
# for Windows desktop packaging.
#
# On Windows, --ignore-scripts prevents install-app-deps from running,
# so hoisted modules aren't available in the desktop package's node_modules.
# This script copies them from the workspace root.
#
# Usage: resolve-desktop-externals.sh
#
# The externals list is sourced from packages/desktop/externals.json
# (single source of truth for all externalized module consumers).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
DESKTOP_DIR="$REPO_ROOT/packages/desktop"
ROOT_NM="$REPO_ROOT/node_modules"
LOCAL_NM="$DESKTOP_DIR/node_modules"

# Read externals from the single source of truth
EXTERNALS_JSON="$DESKTOP_DIR/externals.json"
require_file "$EXTERNALS_JSON"
EXTERNALS=()
while IFS= read -r mod; do
    [[ -n "$mod" ]] && EXTERNALS+=("$mod")
done <<< "$(node -e "
  const cfg = JSON.parse(require('fs').readFileSync('$EXTERNALS_JSON', 'utf8'));
  cfg.externals.forEach(m => console.log(m));
")"

log_step "Resolving externalized modules for packaging..."
mkdir -p "$LOCAL_NM"

# Track copied modules to avoid duplicates
declare -A COPIED_MODULES

# Recursively copy a module and its production dependencies
copy_module_tree() {
    local mod="$1"

    # Skip if already processed
    if [[ -n "${COPIED_MODULES[$mod]:-}" ]]; then
        return
    fi

    if [[ ! -d "$ROOT_NM/$mod" ]]; then
        log_warn "Module not found at root: $mod (skipping)"
        return
    fi

    if [[ -d "$LOCAL_NM/$mod" ]]; then
        COPIED_MODULES[$mod]=1
        return  # Already exists
    fi

    cp -r "$ROOT_NM/$mod" "$LOCAL_NM/$mod"
    COPIED_MODULES[$mod]=1
    log_info "  Copied: $mod"

    # Resolve production dependencies recursively
    local pkg_json="$LOCAL_NM/$mod/package.json"
    if [[ -f "$pkg_json" ]]; then
        local deps
        deps=$(node -e "
          const pkg = JSON.parse(require('fs').readFileSync('$pkg_json', 'utf8'));
          Object.keys(pkg.dependencies || {}).forEach(d => console.log(d));
        " || true)
        for dep in $deps; do
            # Only copy if not already nested inside the module itself
            if [[ ! -d "$LOCAL_NM/$mod/node_modules/$dep" ]]; then
                copy_module_tree "$dep"
            fi
        done
    fi
}

for mod in "${EXTERNALS[@]}"; do
    copy_module_tree "$mod"
done

log_info "External module resolution complete (${#COPIED_MODULES[@]} modules copied)"
