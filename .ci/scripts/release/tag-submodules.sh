#!/bin/bash
# Tag each release-carrying submodule with the parent repo's release version.
#
# WHY: renet ships inside the CLI, so "which renet is in v1.2.3" has to be
# answerable from renet's own history. Tagging the submodule at the exact commit
# the parent pointer references makes that a one-command lookup.
#
# Drift is a hard failure, not a silent retag: if the tag already exists in the
# submodule but points somewhere other than the checked-out HEAD, the release
# would be claiming a version maps to two different commits. That must be
# resolved by a human. When the tag already points AT HEAD we reuse it, and the
# push is idempotent, so retries are safe.
#
# Usage:
#   .ci/scripts/release/tag-submodules.sh
#
# Required env:
#   VERSION       release semver, no leading v (e.g. 1.2.3)
#
# Optional env:
#   GITHUB_PAT    token used by the checkout's submodule credential helper
#   GITHUB_WORKSPACE  repo root to return to between submodules; defaults to
#                     the directory the script was invoked from
#
# NOTE: this PUSHES tags to the submodule remotes. Do not run it locally
# against a real release version unless you intend to publish those tags.
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd git
VERSION="${VERSION:?tag-submodules.sh: VERSION must be set}"
WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"

# BLOCKER: the single-element list is deliberate and moved verbatim out of cd-v2.yml -- private/renet is the only submodule whose commits ship inside a release today, and keeping the loop shape means adding the next one is a one-word edit rather than a restructure
# shellcheck disable=SC2043
for sub in private/renet; do
    if [[ ! -d "$sub/.git" ]] && [[ ! -f "$sub/.git" ]]; then
        echo "::notice::Skipping $sub (not initialized)"
        continue
    fi
    cd "$sub"
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    head_sha="$(git rev-parse HEAD)"
    existing_sha="$(git rev-list -n1 "v${VERSION}" 2>/dev/null || true)"
    if [[ -n "$existing_sha" ]]; then
        if [[ "$existing_sha" != "$head_sha" ]]; then
            echo "::error::Submodule $sub tag v${VERSION} already points to $existing_sha but HEAD is $head_sha. Drift must be resolved manually before this release can proceed."
            exit 1
        fi
        echo "::notice::Submodule $sub tag v${VERSION} already at HEAD ($head_sha); reusing"
    else
        git tag -a "v${VERSION}" -m "v${VERSION}"
    fi
    # Push is idempotent for existing tags pointing at the same SHA.
    git push origin "v${VERSION}"
    cd "$WORKSPACE"
done
