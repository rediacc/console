#!/bin/bash
# Verify desktop build by running warmup validation on the built output.
# Validates all externalized modules are resolvable from the package context.
#
# On Linux/macOS: runs Electron with --warmup flag
# On Windows: uses Node.js directly to verify module resolution
#   (Electron binary may not be available due to --ignore-scripts)
#
# Usage: verify-desktop.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
DESKTOP_DIR="$REPO_ROOT/packages/desktop"

# Read externals from the single source of truth
# Note: use relative path in node -e to avoid Git Bash path issues on Windows
# (Unix paths like /d/a/... are misinterpreted by Node.js as drive-relative)
require_file "$DESKTOP_DIR/externals.json"
REQUIRED_EXTERNALS=()
while IFS= read -r mod; do
    [[ -n "$mod" ]] && REQUIRED_EXTERNALS+=("$mod")
done <<< "$(cd "$DESKTOP_DIR" && node -e "
  const cfg = JSON.parse(require('fs').readFileSync('./externals.json', 'utf8'));
  cfg.externals.forEach(m => console.log(m));
")"

log_step "Verifying desktop build (warmup)..."

if [[ "$CI_OS" == "windows" ]]; then
    # On Windows, Electron binary may not be available due to --ignore-scripts.
    # Verify module resolution directly with Node.js from the desktop context.
    log_info "Windows: verifying module resolution with Node.js"

    # Build JSON array of modules to check
    MODS_JSON="[$(printf '"%s",' "${REQUIRED_EXTERNALS[@]}" | sed 's/,$//')]"

    OUTPUT=$(cd "$DESKTOP_DIR" && node -e "
      const mods = JSON.parse(process.argv[1]);
      const results = [];
      for (const mod of mods) {
        try {
          require(mod);
          results.push({ module: mod, status: 'ok' });
        } catch (e) {
          results.push({ module: mod, status: 'fail', error: e.message });
        }
      }
      const failed = results.filter(r => r.status === 'fail');
      const output = { success: failed.length === 0, results };
      process.stdout.write(JSON.stringify(output, null, 2) + '\n');
      process.exit(failed.length === 0 ? 0 : 1);
    " "$MODS_JSON")
    EXIT_CODE=$?
else
    # On Linux/macOS: run Electron with --warmup flag
    OUTPUT=$(cd "$DESKTOP_DIR" && npx electron out/main/index.js --warmup --no-sandbox)
    EXIT_CODE=$?
fi

echo "$OUTPUT"

if [[ $EXIT_CODE -eq 0 ]]; then
    log_info "Desktop warmup verification passed"
else
    log_error "Desktop warmup verification failed - modules missing from package"
    exit 1
fi
