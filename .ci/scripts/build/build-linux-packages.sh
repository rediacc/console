#!/bin/bash
# Build every Linux package (deb/rpm/apk/archlinux x amd64/arm64) for a version.
#
# WHY: this is the fan-out around build-linux-pkg.sh, which builds exactly one
# (format, arch) pair. Keeping the matrix here means the eight invocations, and
# the Alpine/musl substitution, live in one place instead of being duplicated
# per workflow.
#
# The apk format targets Alpine, which is musl-linked; when a musl build of the
# binary exists it is preferred, otherwise the glibc binary is packaged as-is
# (same fallback the workflow had).
#
# Usage:
#   .ci/scripts/build/build-linux-packages.sh
#
# Required env:
#   NEXT_VERSION      semver to stamp into every package, e.g. 1.2.3
#
# Optional env (consumed by build-linux-pkg.sh when signing):
#   GPG_PRIVATE_KEY   GPG_PASSPHRASE
#
# Expects CLI binaries already present at dist/cli/rdc-linux-{x64,arm64}
# (and optionally rdc-linux-musl-*); writes packages to dist/packages/.
#
# Run locally:
#   NEXT_VERSION=1.2.3 .ci/scripts/build/build-linux-packages.sh
#
# Shell options: the workflow block ran under plain `bash -e`; `-uo pipefail`
# are added here. Neither can change the outcome: every variable read is either
# assigned above or guarded, and the script contains no pipeline.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

: "${NEXT_VERSION:?build-linux-packages.sh: NEXT_VERSION must be set}"

# Paths below are repo-relative, exactly as they were in the workflow step.
cd "$(get_repo_root)"

VERSION="$NEXT_VERSION"
mkdir -p dist/packages
for format in deb rpm apk archlinux; do
    for pair in "dist/cli/rdc-linux-x64:amd64" "dist/cli/rdc-linux-arm64:arm64"; do
        binary="${pair%%:*}"
        arch="${pair##*:}"
        # APK targets Alpine (musl) — use musl-linked binary if available
        if [[ "$format" == "apk" ]]; then
            musl_binary="${binary/rdc-linux-/rdc-linux-musl-}"
            [[ -f "$musl_binary" ]] && binary="$musl_binary"
        fi
        .ci/scripts/build/build-linux-pkg.sh \
            --binary "$binary" --version "$VERSION" \
            --arch "$arch" --format "$format" \
            --output dist/packages
    done
done
