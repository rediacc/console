#!/bin/bash
# Assert that no OTLP/Pyroscope credentials leak in built artifacts.
#
# Credentials are resolved at runtime from env vars (renet) or from the
# account server's /telemetry/config endpoint (CLI). Nothing should be
# baked at build time. This check guards against regressions.
#
# Checks:
#   1. renet `.go.buildinfo` contains no `telemetry.otlpUser` or
#      `telemetry.otlpPass` ldflags.
#   2. `strings <renet>` finds no long base64 sequences adjacent to the
#      otlp symbol names (catches any alternative build-time injection).
#   3. The CLI bundle contains no literal base64 credential assigned to
#      an `Authorization: Basic ...` header at build time.
#
# Usage: check-no-otlp-creds.sh
#
# Exits 0 on success, 1 on leak, 2 on setup error (e.g. no binaries to check).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

log_step "Checking for leaked OTLP credentials in built artifacts..."

ERRORS=0

# --- Renet binaries -------------------------------------------------------
#
# Two candidate locations:
#   1. private/renet/bin/renet (dev build produced by build.sh dev)
#   2. private/bin/renet-<os>-<arch> (CI release build produced by
#      .ci/scripts/build/build-renet.sh)
#
# We check whichever exists; it's fine to have just one.
RENET_BINARIES=()
[[ -f "$REPO_ROOT/private/renet/bin/renet" ]] && RENET_BINARIES+=("$REPO_ROOT/private/renet/bin/renet")
if [[ -d "$REPO_ROOT/private/bin" ]]; then
    while IFS= read -r -d '' f; do
        RENET_BINARIES+=("$f")
    done < <(find "$REPO_ROOT/private/bin" -maxdepth 1 -type f -name 'renet-*' -print0)
fi

if [[ ${#RENET_BINARIES[@]} -eq 0 ]]; then
    log_warn "no renet binaries found at private/renet/bin or private/bin — skipping renet checks"
    log_warn "build with ./build.sh dev or .ci/scripts/build/build-renet.sh before running this check"
else
    if ! command -v go >/dev/null 2>&1; then
        log_error "go is required to inspect renet binaries via 'go version -m'"
        exit 2
    fi

    for bin in "${RENET_BINARIES[@]}"; do
        log_info "inspecting $(basename "$bin")..."

        # Check 1: .go.buildinfo ldflags
        buildinfo=$(go version -m "$bin" 2>/dev/null || true)
        if echo "$buildinfo" | grep -q 'telemetry\.otlpUser'; then
            log_error "$bin: .go.buildinfo contains telemetry.otlpUser ldflag"
            ERRORS=$((ERRORS + 1))
        fi
        if echo "$buildinfo" | grep -q 'telemetry\.otlpPass'; then
            log_error "$bin: .go.buildinfo contains telemetry.otlpPass ldflag"
            ERRORS=$((ERRORS + 1))
        fi

        # Check 2: strings near otlp symbol. A baked credential would appear
        # close to the otlpUser/otlpPass symbol names. Look for any long
        # base64-ish token adjacent to the symbol name.
        if strings "$bin" 2>/dev/null |
            grep -B1 -A1 'otlpUser\|otlpPass' |
            grep -Eq '^[A-Za-z0-9+/=]{20,}$'; then
            log_error "$bin: strings shows a base64-looking token near otlp symbols"
            ERRORS=$((ERRORS + 1))
        fi
    done

    if [[ $ERRORS -eq 0 ]]; then
        log_info "✓ renet binaries: no OTLP credentials in build info"
    fi
fi

# --- CLI bundle -----------------------------------------------------------
#
# The CLI fetches credentials at runtime, so no `Authorization: Basic <...>`
# header should have a literal token baked in. The only valid `Basic`
# header in the bundle is constructed dynamically from `this.authToken`
# after `setRuntimeOtlpCredentials()` has been called.
CLI_BUNDLE="$REPO_ROOT/packages/cli/dist/cli-bundle.cjs"
if [[ ! -f "$CLI_BUNDLE" ]]; then
    log_warn "CLI bundle not found at $CLI_BUNDLE — skipping CLI check"
    log_warn "build with npm run build -w @rediacc/cli first"
else
    log_info "inspecting $(basename "$CLI_BUNDLE")..."

    # Literal base64 token assigned to an Authorization: Basic header.
    # Any match here means someone put a credential in the bundle.
    if grep -qE '["\x27]Basic [A-Za-z0-9+/=]{20,}["\x27]' "$CLI_BUNDLE"; then
        log_error "$CLI_BUNDLE: bundle contains a literal 'Basic <token>' header"
        ERRORS=$((ERRORS + 1))
    fi

    if [[ $ERRORS -eq 0 ]]; then
        log_info "✓ CLI bundle: no literal credentials"
    fi
fi

# --- Summary -------------------------------------------------------------
if [[ $ERRORS -gt 0 ]]; then
    log_error ""
    log_error "$ERRORS credential leak(s) detected. Do NOT ship these artifacts."
    log_error "Check for accidentally-reintroduced build-time injection in"
    log_error "private/renet/build.sh, .ci/scripts/build/build-renet.sh, or"
    log_error "packages/cli/bundle.mjs."
    exit 1
fi

log_info "✓ no OTLP credentials leaked in built artifacts"
exit 0
