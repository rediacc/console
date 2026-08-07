#!/bin/bash
# Build CLI as a Node.js Single Executable Application (SEA)
# Runs on each native platform/arch runner to produce a self-contained binary.
#
# Usage:
#   build-cli-executables.sh --platform linux --arch x64
#   build-cli-executables.sh --platform mac --arch arm64
#   build-cli-executables.sh --platform win --arch x64
#   build-cli-executables.sh                          # Auto-detect platform/arch
#   build-cli-executables.sh --dry-run                # Preview without building
#
# Options:
#   --platform PLATFORM  Target platform: linux, mac, win (auto-detected if omitted)
#   --arch ARCH          Target architecture: x64, arm64 (auto-detected if omitted)
#   --output DIR         Output directory (default: dist/cli/)
#   --dry-run            Preview without building

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
PLATFORM=""
ARCH=""
OUTPUT_DIR=""
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --arch)
            ARCH="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 [--platform PLATFORM] [--arch ARCH] [--output DIR] [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Auto-detect platform if not specified
if [[ -z "$PLATFORM" ]]; then
    case "$(uname -s)" in
        Linux*) PLATFORM="linux" ;;
        Darwin*) PLATFORM="mac" ;;
        MINGW* | MSYS* | CYGWIN*) PLATFORM="win" ;;
        *)
            log_error "Cannot detect platform from: $(uname -s)"
            exit 1
            ;;
    esac
    log_info "Auto-detected platform: $PLATFORM"
fi

# Auto-detect architecture if not specified
if [[ -z "$ARCH" ]]; then
    case "$(uname -m)" in
        x86_64 | amd64) ARCH="x64" ;;
        aarch64 | arm64) ARCH="arm64" ;;
        *)
            log_error "Cannot detect architecture from: $(uname -m)"
            exit 1
            ;;
    esac
    log_info "Auto-detected arch: $ARCH"
fi

# Set output directory
REPO_ROOT="$(get_repo_root)"
if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="$REPO_ROOT/dist/cli"
fi

# Binary name
BINARY_NAME="rdc-${PLATFORM}-${ARCH}"
if [[ "$PLATFORM" == "win" ]]; then
    BINARY_NAME="${BINARY_NAME}.exe"
fi

CLI_DIR="$REPO_ROOT/packages/cli"
NODE_BIN="$(command -v node)"

log_step "Building CLI SEA executable: $BINARY_NAME"
log_info "  Platform: $PLATFORM"
log_info "  Arch: $ARCH"
log_info "  Node: $NODE_BIN ($(node --version))"
log_info "  Output: $OUTPUT_DIR/$BINARY_NAME"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would build $BINARY_NAME"
    exit 0
fi

# Step 1: Build the CJS bundle
log_step "Building CLI bundle..."
# Version resolution goes through the single injector rather than being spelled
# `${CLI_VERSION:-0.0.0-dev}` here, so the placeholder fallback exists in ONE
# place and can be refused where it matters.
#
# THE SEAM IS THE RELEASE PATH, not "CI". ci-build-cli.yml sets
# RELEASE_BUILD=true only on push-to-main, which is the only CI whose artifacts
# CD ever promotes; there --strict refuses an empty, placeholder, or malformed
# version and the build dies before a single byte is stamped. PR CI, forks and
# local `./rdc.sh --native` leave RELEASE_BUILD unset and keep the 0.0.0-dev
# fallback, so dev iteration needs no ceremony.
if [[ "${RELEASE_BUILD:-}" == "true" ]]; then
    if [[ -z "${CLI_VERSION:-}" ]]; then
        log_error "RELEASE_BUILD=true but CLI_VERSION is empty; refusing to build a publishable artifact without a version"
        exit 1
    fi
    # shellcheck source=../version/inject-env.sh
    if ! source "$SCRIPT_DIR/../version/inject-env.sh" --version "$CLI_VERSION" --strict; then
        log_error "Release build refused: CLI_VERSION='$CLI_VERSION' is not a publishable version"
        exit 1
    fi
else
    # shellcheck source=../version/inject-env.sh
    source "$SCRIPT_DIR/../version/inject-env.sh" --version "${CLI_VERSION:-0.0.0-dev}"
fi
# The version this build was TOLD to produce. Kept in its own variable because
# the doctor smoke test below parses a value into $CLI_VERSION and used to
# clobber this one, leaving nothing to compare against.
EXPECTED_CLI_VERSION="$CLI_VERSION"
log_info "CLI version: $EXPECTED_CLI_VERSION"
cd "$CLI_DIR"
node bundle.mjs
require_file "$CLI_DIR/dist/cli-bundle.cjs"
log_info "Bundle created: $(wc -c <dist/cli-bundle.cjs) bytes"

# Step 1.5: Prepare embedded assets (renet binaries)
log_step "Preparing embedded renet assets..."
"$SCRIPT_DIR/prepare-cli-assets.sh" --platform "$PLATFORM" --arch "$ARCH"

# Step 2: Generate SEA blob
log_step "Generating SEA blob..."
node --experimental-sea-config sea-config.generated.json
require_file "$CLI_DIR/dist/sea-prep.blob"
log_info "SEA blob created: $(wc -c <dist/sea-prep.blob) bytes"

# Step 3: Copy node binary
log_step "Copying node binary..."
mkdir -p "$OUTPUT_DIR"
cp "$NODE_BIN" "$OUTPUT_DIR/$BINARY_NAME"
chmod +x "$OUTPUT_DIR/$BINARY_NAME"

# Step 4: Remove existing signature (macOS only, must happen before strip)
if [[ "$PLATFORM" == "mac" ]]; then
    log_step "Removing existing code signature..."
    codesign --remove-signature "$OUTPUT_DIR/$BINARY_NAME"
fi

# Step 5: Strip debug symbols (before injection to avoid corrupting SEA section)
# Note: macOS strip is incompatible with Node.js binaries (__LINKEDIT segment issues)
# so we only strip on Linux where it works reliably.
if [[ "$PLATFORM" == "linux" ]]; then
    log_step "Stripping debug symbols..."
    strip --strip-all "$OUTPUT_DIR/$BINARY_NAME"
    log_info "Stripped binary: $(wc -c <"$OUTPUT_DIR/$BINARY_NAME") bytes"
fi

# Step 6: Inject SEA blob
#
# We inject with our own streaming injector on EVERY platform, not `npx postject`
# (#525). postject's binary surgery is LIEF compiled to wasm32, so the executable
# and the blob must both fit in a 4GB address space, and it amplifies the blob
# ~11.6x in memory: our ~561MB blob needs ~7.4GB and simply cannot be injected.
# Upstream is dead (last release 2023-05) and its wasm memory is already at the
# architectural maximum, so this is not fixable there. sea-inject/ streams the
# blob in fixed-size chunks, so peak RSS is flat (~64MB) regardless of blob size,
# and has ELF / Mach-O / PE backends dispatched by magic bytes.
#
# The --macho-segment-name argument is retained for argv parity; the Mach-O
# backend fixes the segment name to NODE_SEA internally (what node's runtime
# lookup expects, and what the ad-hoc re-signing below must cover on ARM64).
log_step "Injecting SEA blob into binary..."
INJECT_ARGS=(
    "$OUTPUT_DIR/$BINARY_NAME"
    NODE_SEA_BLOB
    "$CLI_DIR/dist/sea-prep.blob"
    --sentinel-fuse NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2
)
if [[ "$PLATFORM" == "mac" ]]; then
    INJECT_ARGS+=(--macho-segment-name NODE_SEA)
fi
node "$SCRIPT_DIR/sea-inject/cli.mjs" "${INJECT_ARGS[@]}"

# Step 7: Integrity gate — re-extract the embedded blob and SHA256-compare it to
# the source blob, on EVERY platform (this only parses the container, it does not
# execute it, so it runs for cross-compiled mac/win/arm64 too). This is the check
# that catches a corrupt or truncated injection before release: the native-only
# `--version`/doctor smoke tests below exercise the SEA *main script* but not the
# asset bytes, so a blob whose main is intact but whose payload is corrupt would
# otherwise pass them (#525).
log_step "Verifying embedded SEA blob integrity..."
node "$SCRIPT_DIR/sea-inject/verify.mjs" \
    "$OUTPUT_DIR/$BINARY_NAME" \
    "$CLI_DIR/dist/sea-prep.blob" \
    --sentinel-fuse NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2

# Step 8: Re-sign (macOS only)
if [[ "$PLATFORM" == "mac" ]]; then
    log_step "Re-signing binary..."
    codesign -s - "$OUTPUT_DIR/$BINARY_NAME"
fi

# Verify
log_step "Verifying executable..."
BINARY_SIZE=$(wc -c <"$OUTPUT_DIR/$BINARY_NAME")
log_info "Binary size: $((BINARY_SIZE / 1024 / 1024))MB ($BINARY_SIZE bytes)"

# Generate SHA256 checksum
log_step "Generating SHA256 checksum..."
if command -v sha256sum &>/dev/null; then
    (cd "$OUTPUT_DIR" && sha256sum "$BINARY_NAME" >"${BINARY_NAME}.sha256")
elif command -v shasum &>/dev/null; then
    (cd "$OUTPUT_DIR" && shasum -a 256 "$BINARY_NAME" >"${BINARY_NAME}.sha256")
else
    log_warn "No sha256sum or shasum available - skipping checksum"
fi
if [[ -f "$OUTPUT_DIR/${BINARY_NAME}.sha256" ]]; then
    log_info "Checksum: $(cat "$OUTPUT_DIR/${BINARY_NAME}.sha256")"
fi

# Quick smoke tests (skip on cross-platform CI where binary may not run)
if [[ "$PLATFORM" == "$(detect_os | sed 's/macos/mac/; s/windows/win/')" ]] &&
    [[ "$ARCH" == "$(detect_arch)" ]]; then

    # Test 1: --version
    log_step "Running smoke test: --version"
    if "$OUTPUT_DIR/$BINARY_NAME" --version; then
        log_info "Smoke test (--version) passed"
    else
        log_error "Smoke test (--version) failed (exit code: $?)"
        exit 1
    fi

    # Test 2: doctor --output json
    log_step "Running smoke test: doctor --output json"
    DOCTOR_OUTPUT=""
    DOCTOR_EXIT=0
    DOCTOR_OUTPUT=$("$OUTPUT_DIR/$BINARY_NAME" doctor --output json 2>/dev/null) || DOCTOR_EXIT=$?

    if [[ $DOCTOR_EXIT -le 2 ]] && [[ -n "$DOCTOR_OUTPUT" ]]; then
        log_info "Doctor exited with code $DOCTOR_EXIT (expected in CI without auth/renet)"

        # Validate JSON
        if echo "$DOCTOR_OUTPUT" | jq empty 2>/dev/null; then
            log_info "Doctor JSON output is valid"

            # Validate key checks
            INSTALL_METHOD=$(echo "$DOCTOR_OUTPUT" | jq -r '.Environment[] | select(.name == "Install method") | .value')
            REPORTED_CLI_VERSION=$(echo "$DOCTOR_OUTPUT" | jq -r '.Environment[] | select(.name == "CLI version") | .value')
            NODE_STATUS=$(echo "$DOCTOR_OUTPUT" | jq -r '.Environment[] | select(.name == "Node.js") | .status')

            if [[ "$INSTALL_METHOD" == "SEA binary" ]]; then
                log_info "Install method: $INSTALL_METHOD"
            else
                log_error "SEA mode check failed: '$INSTALL_METHOD'"
                exit 1
            fi

            # THE ONLY point in the whole pipeline that reads a version out of
            # freshly built bytes. It used to assert only "non-empty and not
            # null", so a SEA built as 0.0.0-dev -- or as any version other
            # than the one CD would later label it -- passed with a cheerful
            # "CLI version: 0.0.0-dev". Release 31154305287 published binaries
            # built as 1.2.16 under the label 1.2.17 and this step said nothing.
            # Compare, or the check is decorative.
            if [[ -z "$REPORTED_CLI_VERSION" ]] || [[ "$REPORTED_CLI_VERSION" == "null" ]]; then
                log_error "CLI version check failed: doctor reported '$REPORTED_CLI_VERSION'"
                exit 1
            fi
            if [[ "$REPORTED_CLI_VERSION" != "$EXPECTED_CLI_VERSION" ]]; then
                log_error "CLI version mismatch: built for '$EXPECTED_CLI_VERSION' but the binary reports '$REPORTED_CLI_VERSION'"
                exit 1
            fi
            log_info "CLI version: $REPORTED_CLI_VERSION (matches build version)"

            if [[ "$NODE_STATUS" == "ok" ]]; then
                log_info "Node.js status: $NODE_STATUS"
            else
                log_error "Node.js check failed: status='$NODE_STATUS'"
                exit 1
            fi

            # Runtime embedded-asset integrity: `doctor` reads the host renet
            # binary back out of the SEA and sha256-checks it against the
            # build-time metadata. This is the ONE runtime check a corrupt or
            # unreachable blob cannot pass — --version never touches an asset, and
            # the build-time verify.mjs only parses the container without running
            # it. On failure the check's value is prefixed "corrupt — " (a literal
            # emitted by verifyEmbeddedRenetIntegrity, so this match is
            # locale-independent). Any such check fails the build.
            EMBED_CORRUPT=$(echo "$DOCTOR_OUTPUT" | jq -r \
                '[.Renet[]? | select(.value | startswith("corrupt"))] | length')
            if [[ "$EMBED_CORRUPT" == "0" ]]; then
                log_info "Embedded renet asset read back and sha256-verified"
            else
                log_error "Embedded renet asset integrity check FAILED (corrupt/unreachable blob)"
                echo "$DOCTOR_OUTPUT" | jq -r '.Renet[]? | select(.value | startswith("corrupt")) | "  \(.name): \(.value)"'
                exit 1
            fi

            log_info "Smoke test (doctor) passed"
        else
            log_error "Doctor output is not valid JSON"
            echo "$DOCTOR_OUTPUT"
            exit 1
        fi
    else
        log_error "Doctor command failed unexpectedly (exit code: $DOCTOR_EXIT)"
        [[ -n "$DOCTOR_OUTPUT" ]] && echo "$DOCTOR_OUTPUT"
        exit 1
    fi
else
    log_info "Skipping smoke tests (cross-platform build)"
fi

log_info "CLI SEA build complete: $OUTPUT_DIR/$BINARY_NAME"
