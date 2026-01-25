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
OPTIONAL_EXTERNALS=()
while IFS= read -r mod; do
    [[ -n "$mod" ]] && REQUIRED_EXTERNALS+=("$mod")
done <<< "$(cd "$DESKTOP_DIR" && node -e "
  const cfg = JSON.parse(require('fs').readFileSync('./externals.json', 'utf8'));
  cfg.externals.forEach(m => console.log(m));
")"
while IFS= read -r mod; do
    [[ -n "$mod" ]] && OPTIONAL_EXTERNALS+=("$mod")
done <<< "$(cd "$DESKTOP_DIR" && node -e "
  const cfg = JSON.parse(require('fs').readFileSync('./externals.json', 'utf8'));
  (cfg.optional || []).forEach(m => console.log(m));
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

# ==============================================================================
# Verify packaged app.asar contains all required modules
# ==============================================================================

log_step "Verifying packaged app.asar..."

# Find the unpacked directory (electron-builder creates platform-specific names)
# Examples: win-unpacked, linux-unpacked, mac-arm64, mac-x64, mac (universal)
UNPACKED_DIR=""

# First try platform-specific unpacked directories
for pattern in win-unpacked linux-unpacked mac-arm64 mac-x64 mac; do
    if [[ -d "$REPO_ROOT/dist/desktop/$pattern" ]]; then
        UNPACKED_DIR="$REPO_ROOT/dist/desktop/$pattern"
        break
    fi
done

# Check for macOS .app bundle if no unpacked dir found
if [[ -z "$UNPACKED_DIR" ]]; then
    APP_BUNDLE=$(find "$REPO_ROOT/dist/desktop" -maxdepth 1 -type d -name '*.app' 2>/dev/null | head -1)
    if [[ -n "$APP_BUNDLE" ]]; then
        UNPACKED_DIR="$APP_BUNDLE/Contents"
    fi
fi

if [[ -z "$UNPACKED_DIR" ]]; then
    log_warn "Unpacked directory not found - skipping packaged verification"
    log_info "This is expected if only installers were built (no unpacked output)"
else
    ASAR_PATH="$UNPACKED_DIR/resources/app.asar"
    ASAR_UNPACKED="$UNPACKED_DIR/resources/app.asar.unpacked"

    if [[ -f "$ASAR_PATH" ]]; then
        # Extract and verify app.asar contains required modules
        TEMP_DIR=$(mktemp -d)
        if [[ ! -d "$TEMP_DIR" ]]; then
            log_error "Failed to create temporary directory"
            exit 1
        fi
        # Clean up temp dir on exit
        trap 'rm -rf "$TEMP_DIR"' EXIT

        log_info "Extracting app.asar for verification..."
        npx asar extract "$ASAR_PATH" "$TEMP_DIR"

        # Check for required externals in extracted app
        MISSING_MODS=()
        for mod in "${REQUIRED_EXTERNALS[@]}"; do
            if [[ ! -d "$TEMP_DIR/node_modules/$mod" ]]; then
                MISSING_MODS+=("$mod")
            else
                log_info "  Found in app.asar: $mod"
            fi
        done

        if [[ ${#MISSING_MODS[@]} -gt 0 ]]; then
            log_error "Modules missing from app.asar: ${MISSING_MODS[*]}"
            exit 1
        fi

        # Verify native modules are unpacked (required for native bindings)
        # Only native modules need unpacking - pure JS modules (like electron-updater) don't
        # These match the asarUnpack config in electron-builder.yml
        NATIVE_MODULES=(ssh2 node-pty)
        OPTIONAL_NATIVE=(cpu-features)

        if [[ -d "$ASAR_UNPACKED" ]]; then
            log_info "Checking unpacked native modules..."
            MISSING_UNPACKED=()
            for native_mod in "${NATIVE_MODULES[@]}"; do
                if [[ -d "$ASAR_UNPACKED/node_modules/$native_mod" ]]; then
                    log_info "  Unpacked: $native_mod"
                else
                    MISSING_UNPACKED+=("$native_mod")
                fi
            done
            # Check optional native modules (don't fail if missing)
            for native_mod in "${OPTIONAL_NATIVE[@]}"; do
                if [[ -d "$ASAR_UNPACKED/node_modules/$native_mod" ]]; then
                    log_info "  Unpacked (optional): $native_mod"
                else
                    log_info "  Not found (optional): $native_mod"
                fi
            done
            if [[ ${#MISSING_UNPACKED[@]} -gt 0 ]]; then
                log_error "Native modules missing from asar.unpacked: ${MISSING_UNPACKED[*]}"
                exit 1
            fi
        fi

        log_info "Packaged app.asar verification passed"
    else
        log_warn "app.asar not found at $ASAR_PATH"
    fi
fi
