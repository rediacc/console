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
# EXISTENCE CHECK, BEFORE REACHABILITY. These are two different failures and
# they need two different messages.
#
# `git merge-base --is-ancestor` cannot tell them apart: it answers non-zero
# both for a commit that exists but sits off main, and for a SHA that is not an
# object in this repository at all -- and git's own "Not a valid object name"
# for the second case went to the `2>/dev/null` below, so the operator was told
# "not reachable from origin/main" about a commit that was never here. That
# reads as a real tag pointing somewhere odd, and sends the investigation in
# entirely the wrong direction.
#
# The distinction matters most RIGHT NOW. After the 2026-08-23 history rewrite,
# any SHA copied out of an old release note or an R2 sentinel is exactly case
# two: it no longer exists. That is the likeliest way this branch fires today,
# and it is the case the old message described wrongly.
#
# The `^{commit}` peel is deliberate: a bare `cat-file -e <sha>` accepts a blob
# or a tree, and this variable has to name a commit -- a tree SHA would sail
# past a bare probe and then be reported as a detached tag, which is the same
# misdiagnosis one layer down. `2>/dev/null` here only hides git's own phrasing,
# which the message below states in full: it swallows nothing the operator is
# not told, and the message covers BOTH ways the peel can fail (no such object,
# and an object that is not a commit) because the probe cannot tell them apart
# and neither can be backfilled.
#
# WHY THIS IS SCOPED TO THE OPERATOR-SUPPLIED PATH. It is the only way a
# non-existent SHA can get in. The tag path at :41 derives the SHA from a tag in
# THIS checkout, and filter-repo rewrites tags along with the commits, so it
# always resolves to a live object. Running the probe there could only ever
# produce a false alarm about the tool's own output.
if [[ -n "$INPUT_SHA" ]] && ! git cat-file -e "${SHA}^{commit}" 2>/dev/null; then
    echo "::error::commit $SHA does not name a commit in this repository -- either no such object exists here at all, or the object is not a commit"
    echo "::error::if you took this SHA from an old release note or an R2 sentinel, it no longer exists: the 2026-08-23 git history rewrite renamed every commit. Leave commit_sha/INPUT_SHA EMPTY and let ${VERSION} resolve through the tag instead -- the rewrite moved tags with the commits, so the tag path still works."
    exit 1
fi
# Reachability check: the commit exists; it must also be on main. Sealing a
# detached tag would record a release main never contained.
if ! git merge-base --is-ancestor "$SHA" origin/main 2>/dev/null; then
    echo "::error::commit $SHA is not reachable from origin/main"
    echo "::error::refusing to backfill a sentinel for a detached tag"
    exit 1
fi
echo "commit_sha=$SHA" >>"$GITHUB_OUTPUT"
echo "✓ commit reachable from origin/main"
