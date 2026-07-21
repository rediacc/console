#!/bin/bash
# Version guard: refuse to publish a version that already exists.
#
# WHY: cd-v2.yml computes next_version from the latest tag plus a bump. If a
# previous release got as far as tagging (or a human tagged by hand), running
# again would produce a duplicate tag and a second GitHub Release for the same
# semver. Failing in the init job costs nothing; failing after Docker/R2 have
# already been mutated costs a manual cleanup.
#
# Usage:
#   .ci/scripts/release/check-existing-release.sh
#
# Required env:
#   VERSION            semver WITHOUT the leading v (e.g. 1.2.3)
#   GITHUB_REPOSITORY  owner/repo to query for an existing GitHub Release
#   GH_TOKEN           token for `gh release view`
#
# Run locally (read-only, safe -- it only fetches tags and queries the API):
#   VERSION=1.2.3 GITHUB_REPOSITORY=rediacc/console \
#     .ci/scripts/release/check-existing-release.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; the one pipeline (`git tag -l | grep -q .`) is an `if`
# condition whose left side cannot fail, so pipefail cannot change the outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
require_cmd git
VERSION="${VERSION:?check-existing-release.sh: VERSION must be set}"
: "${GITHUB_REPOSITORY:?check-existing-release.sh: GITHUB_REPOSITORY must be set}"

git fetch --tags --quiet
if git tag -l "v${VERSION}" | grep -q .; then
    echo "::error::Git tag v${VERSION} already exists. Aborting to prevent duplicate publish."
    exit 1
fi
if gh release view "v${VERSION}" --repo "${GITHUB_REPOSITORY}" &>/dev/null; then
    echo "::error::Release v${VERSION} already exists. Aborting to prevent duplicate publish."
    exit 1
fi
echo "Version v${VERSION} is available for publishing."
