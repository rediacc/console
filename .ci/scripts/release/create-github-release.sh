#!/bin/bash
# Create the GitHub Release for a version and upload every built asset to it.
#
# WHY: the GitHub Release is the human-facing distribution surface (and what
# Homebrew's formula URLs point at). It is created LAST in cd-v2.yml, after
# edge deploys, smoke tests and post-publish install validation have all passed,
# so a broken release never gets a Release page pointing at it.
#
# Fails rather than publishes an empty Release when dist/{cli,packages} matched
# nothing: an assetless Release looks published but installs nothing.
#
# Usage:
#   .ci/scripts/release/create-github-release.sh
#
# Expects the release artifacts already downloaded into dist/cli and
# dist/packages relative to the repo root.
#
# Required env:
#   VERSION            release semver, no leading v (e.g. 1.2.3)
#   GITHUB_SHA         commit the Release tag targets
#   GITHUB_REPOSITORY  owner/repo to create the Release in
#   GH_TOKEN           token for `gh release create`
#
# NOTE: this PUBLISHES a GitHub Release. Do not run it locally against a real
# version unless you intend to publish.
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
VERSION="${VERSION:?create-github-release.sh: VERSION must be set}"
: "${GITHUB_SHA:?create-github-release.sh: GITHUB_SHA must be set}"
: "${GITHUB_REPOSITORY:?create-github-release.sh: GITHUB_REPOSITORY must be set}"

cd "$(get_repo_root)"

shopt -s globstar nullglob
assets=(dist/cli/**/* dist/packages/**/*)
files=()
for f in "${assets[@]}"; do [[ -f "$f" ]] && files+=("$f"); done
if [[ ${#files[@]} -eq 0 ]]; then
    echo "::error::No release assets matched dist/{cli,packages}/**/*"
    exit 1
fi
gh release create "v${VERSION}" \
    --title "v${VERSION}" \
    --target "${GITHUB_SHA}" \
    --generate-notes \
    --repo "${GITHUB_REPOSITORY}" \
    "${files[@]}"
