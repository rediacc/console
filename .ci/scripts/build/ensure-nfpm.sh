#!/usr/bin/env bash
# Install the pinned nfpm if it is not already usable, and print the directory
# holding it. Idempotent: a second run downloads nothing.
#
# WHY A SCRIPT. The same six lines lived in ci.yml and cd-stage.yml, and they
# had already drifted once: cd-stage.yml's own comment records that its copy
# kept the `curl | sudo tar` form after ci.yml was fixed, so the pinned
# NFPM_SHA256_LINUX_X86_64 was verified on one of the two installs and not the
# other. Two copies of an integrity check is one copy of an integrity check.
#
# AND IT IS WHY THE PACKAGE TEST COULD NOT RUN OFF A RUNNER AT ALL. Both copies
# lived in workflow YAML, so `.ci/scripts/test/test-linux-packages.sh` had no
# way to obtain nfpm on a developer machine or inside the devbox: the tool was
# installed by the job, never by the thing that needs it. Measured 2026-09-04 on
# this host -- the test died in phase 1 with nothing built.
#
# THE PIN STAYS IN ONE PLACE. .ci/config/constants.sh is the single source for
# the version and the checksum; this script reads it and never carries its own
# copy, which is what stops a second pin site drifting from the first.
#
# Usage:
#   PATH="$(.ci/scripts/build/ensure-nfpm.sh):$PATH"     # local / devbox
#   .ci/scripts/build/ensure-nfpm.sh >>"$GITHUB_PATH"    # CI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../../config/constants.sh
# BLOCKER: the single pin site for NFPM_VERSION and its checksum
source "$REPO_ROOT/.ci/config/constants.sh"

BIN_DIR="$REPO_ROOT/.ci/cache/bin"

# ALREADY USABLE? Answer by asking the binary, not by testing for the file.
# A truncated download and an interrupted extraction both leave a path that
# `test -x` is happy with, and the next thing to notice would be nfpm failing
# mid-build with something that does not name this script.
if command -v nfpm >/dev/null 2>&1 && nfpm --version >/dev/null 2>&1; then
    dirname "$(command -v nfpm)"
    exit 0
fi
if [ -x "$BIN_DIR/nfpm" ] && "$BIN_DIR/nfpm" --version >/dev/null 2>&1; then
    printf '%s\n' "$BIN_DIR"
    exit 0
fi

# ONE ARCH IS PINNED, and saying so beats installing something unverified.
# constants.sh carries NFPM_SHA256_LINUX_X86_64 only. Every consumer today is
# an x86_64 runner or an x86_64 dev box; an arm64 caller gets a refusal that
# names the missing pin rather than a silently unchecked download.
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64 | amd64)
        TARBALL="nfpm_${NFPM_VERSION}_Linux_x86_64.tar.gz"
        WANT="$NFPM_SHA256_LINUX_X86_64"
        ;;
    *)
        echo "ensure-nfpm: no pinned checksum for $ARCH in .ci/config/constants.sh -- add one rather than downloading unverified bytes" >&2
        exit 1
        ;;
esac

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
URL="https://github.com/goreleaser/nfpm/releases/download/v${NFPM_VERSION}/${TARBALL}"
echo "ensure-nfpm: fetching nfpm ${NFPM_VERSION} for ${ARCH}" >&2
curl -sfL --retry 3 --retry-delay 2 --retry-all-errors -o "$TMP/$TARBALL" "$URL"
# VERIFY BEFORE EXTRACTING, which is the whole reason the pin exists: the
# release job that consumes this also holds signing secrets.
echo "${WANT}  ${TMP}/${TARBALL}" | sha256sum -c - >/dev/null
mkdir -p "$BIN_DIR"
tar xzf "$TMP/$TARBALL" -C "$BIN_DIR" nfpm
chmod +x "$BIN_DIR/nfpm"
printf '%s\n' "$BIN_DIR"
