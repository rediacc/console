#!/bin/bash
# Assert a GitHub Release exists for a version AND carries CLI assets.
#
# WHY: the R2 `.released` sentinel is the commit marker for a version. Writing
# one for a version that was never actually built and published would make the
# release-state bijection gate green over a version users cannot download. The
# presence of at least one `rdc-*` asset on the Release is the cheapest proof
# that the build really happened.
#
# Usage:
#   .ci/scripts/release/verify-release-assets.sh
#
# Required env:
#   VERSION             release tag to check, e.g. v1.1.2
#   GITHUB_REPOSITORY   owner/repo the Release lives in (GitHub sets this)
#   GH_TOKEN            token for `gh release view` (or any working `gh auth`)
#
# Run locally (read-only):
#   VERSION=v1.1.2 GITHUB_REPOSITORY=rediacc/console \
#     .ci/scripts/release/verify-release-assets.sh
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
require_cmd jq
: "${VERSION:?verify-release-assets.sh: VERSION must be set}"
: "${GITHUB_REPOSITORY:?verify-release-assets.sh: GITHUB_REPOSITORY must be set}"

if ! gh release view "$VERSION" --repo "${GITHUB_REPOSITORY}" --json tagName,assets >/tmp/release.json 2>/tmp/release.err; then
    echo "::error::no GitHub Release found for $VERSION"
    cat /tmp/release.err
    exit 1
fi
# Count CLI assets (rdc-*). Filename pattern matches the existing
# release flow's artifact naming.
asset_count="$(jq '[.assets[] | select(.name | startswith("rdc-"))] | length' /tmp/release.json)"
if [[ "$asset_count" -lt 1 ]]; then
    echo "::error::Release $VERSION has no rdc-* CLI assets"
    echo "::error::refusing to seal a version that was never built/published"
    jq '.assets | map(.name)' /tmp/release.json
    exit 1
fi
echo "✓ Release $VERSION has $asset_count rdc-* CLI asset(s)"
