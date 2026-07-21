#!/bin/bash
# Resolve (and sanity-check) the commit SHA a backfilled release sentinel records.
#
# WHY: the sentinel payload names the commit the version was built from. An
# operator may pass one explicitly, but the normal path derives it from the
# version tag in the checkout. Either way the commit must be reachable from
# origin/main -- sealing a detached tag would record a release that main never
# contained, and the bijection gate would then defend a lie.
#
# Usage:
#   .ci/scripts/release/resolve-backfill-commit.sh
#
# Required env:
#   VERSION         version tag to resolve, e.g. v1.1.2
#   GITHUB_OUTPUT   step-output file to append commit_sha to
#
# Optional env:
#   INPUT_SHA       operator-supplied commit SHA; empty means derive from the tag
#
# Run locally (read-only; needs a checkout with tags + origin/main):
#   VERSION=v1.1.2 GITHUB_OUTPUT=/dev/stdout \
#     .ci/scripts/release/resolve-backfill-commit.sh
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd git
: "${VERSION:?resolve-backfill-commit.sh: VERSION must be set}"
: "${GITHUB_OUTPUT:?resolve-backfill-commit.sh: GITHUB_OUTPUT must be set}"

INPUT_SHA="${INPUT_SHA:-}"

if [[ -n "$INPUT_SHA" ]]; then
    SHA="$INPUT_SHA"
    echo "→ using operator-supplied commit_sha: $SHA"
else
    SHA="$(git rev-list -n1 "$VERSION" 2>/dev/null || true)"
    if [[ -z "$SHA" ]]; then
        echo "::error::tag $VERSION not found in this checkout; pass commit_sha explicitly"
        exit 1
    fi
    echo "→ resolved $VERSION → $SHA"
fi
# Reachability check: tag must point at something on main.
if ! git merge-base --is-ancestor "$SHA" origin/main 2>/dev/null; then
    echo "::error::commit $SHA is not reachable from origin/main"
    echo "::error::refusing to backfill a sentinel for a detached tag"
    exit 1
fi
echo "commit_sha=$SHA" >>"$GITHUB_OUTPUT"
echo "✓ commit reachable from origin/main"
