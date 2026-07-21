#!/bin/bash
# Produce the CLI npm tarball, plus a stable rediacc-cli-latest.tgz alias.
#
# npm names the tarball from package.json's version, so the version must be
# injected BEFORE `npm pack`. The 0.0.0-dev placeholder is left alone: that is
# the value the repo carries in git, and a dev build should not masquerade as a
# release.
#
# Usage (from anywhere):
#   VERSION=1.2.3 .ci/scripts/build/pack-cli-npm.sh
#
# Optional env:
#   VERSION    version to inject (default 0.0.0-dev, which skips injection)
#   OUT_DIR    where the tarball lands (default /tmp/cli-npm)
#
# It cd's to packages/cli itself. It previously relied on the caller doing
# `working-directory: packages/cli`, and the workflow step ALSO addressed the
# script by a repo-root-relative path -- so the two combined into
# `packages/cli/.ci/scripts/build/pack-cli-npm.sh`, which does not exist, and CI
# died with exit 127. Being self-locating removes the coupling entirely rather
# than trading one path assumption for another.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd jq
require_cmd npm

cd "$(get_repo_root)/packages/cli"

VERSION="${VERSION:-0.0.0-dev}"
OUT_DIR="${OUT_DIR:-/tmp/cli-npm}"

if [[ "$VERSION" != "0.0.0-dev" ]]; then
    jq --arg v "$VERSION" '.version = $v' package.json >package.json.tmp &&
        mv package.json.tmp package.json
    log_info "Injected version $VERSION into package.json"
fi

mkdir -p "$OUT_DIR"
npm pack --pack-destination "$OUT_DIR"

cd "$OUT_DIR"
CLI_PKG="$(ls rediacc-cli-*.tgz 2>/dev/null | head -1)"
if [[ -n "$CLI_PKG" ]]; then
    cp "$CLI_PKG" rediacc-cli-latest.tgz
    log_info "Packed $CLI_PKG (+ rediacc-cli-latest.tgz alias)"
else
    log_error "npm pack produced no rediacc-cli-*.tgz in $OUT_DIR"
    exit 1
fi
