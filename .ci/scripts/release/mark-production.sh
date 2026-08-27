#!/bin/bash
# Record what is ACTUALLY in production, because nothing did.
#
# THE GAP THIS CLOSES. GitHub's "Latest release" badge tracks whatever was
# published most recently, and the edge lane publishes on every release-worthy
# merge to main. Production is a different thing entirely: it is whatever
# survived the 7-day soak and was promoted by "Release to Production". So the
# badge a human reads as "what is live" has been naming the EDGE build, and
# there was no marker anywhere that named the production one.
#
# TWO MARKERS, deliberately, because they answer different questions:
#
#   1. `production` -- a MOVING annotated tag. Answers "what is in production
#      right now" for anyone with a clone: `git show production`.
#   2. `--latest` on that version's GitHub Release. Answers the same question
#      for anyone looking at the repo page, which is where the wrong answer was
#      being displayed.
#
# WHY THE TAG IS NAMED `production` AND NOT `prod-vX.Y.Z`. Every version reader
# in this repo globs `v*` -- resolve-version.sh:46, initialize.sh:218,
# derive-image-tag.sh:92, detect-bump-type.sh:105. A tag named `prod-v1.3.1`
# would be invisible to that glob (it does not start with `v`), but the moment
# someone "tidied" it to `v-prod-1.3.1` or similar it would start colliding with
# the version resolver and could silently become "the latest tag". A single
# fixed name that cannot ever look like a version is the safe shape.
#
# IDEMPOTENT: re-running for the same version is a no-op that still exits 0, so
# a re-dispatched promotion does not fail here.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: shared logging helpers used by every .ci/scripts entry point
source "$ROOT_DIR/.ci/scripts/lib/common.sh" 2>/dev/null || {
    log_info() { echo "$*"; }
    log_error() { echo "$*" >&2; }
    # A fallback for "common.sh is missing" cannot call common.sh's own
    # require_cmd. Define a minimal one here, or this branch dies at 127 while
    # reporting nothing about the missing dependency it exists to report.
    require_cmd() {
        command -v "$1" >/dev/null 2>&1 || {
            log_error "Required command '$1' is not available"
            exit 1
        }
    }
}

require_cmd gh

VERSION="${1:-${VERSION:-}}"

if [[ -z "$VERSION" ]]; then
    log_error "mark-production: no version given (argv[1] or \$VERSION)"
    exit 1
fi

# Normalise to a leading v exactly once, then demand strict semver. A malformed
# version must NOT become a tag: `production` is the thing humans will trust.
VERSION="v${VERSION#v}"
if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    log_error "mark-production: '$VERSION' is not strict semver (expected vX.Y.Z)"
    exit 1
fi

# THE VERSION MUST ALREADY BE A REAL RELEASE. Marking production is a claim
# about reality, so it is verified, never assumed -- and "could not tell" is a
# failure, not a pass: a 403 or a network fault means the check did not run.
if ! out="$(gh release view "$VERSION" --json tagName 2>&1)"; then
    case "$out" in
        *"release not found"* | *"Not Found"*)
            log_error "mark-production: no GitHub Release for $VERSION; refusing to mark a version that was never published"
            ;;
        *)
            log_error "mark-production: could not read the release for $VERSION, so the check did NOT run: $out"
            ;;
    esac
    exit 1
fi

log_info "mark-production: $VERSION is a published release"

# 1. the moving tag -- VIA THE API, NOT git.
#
# The caller (promote-stable.yml's verify-stable job) does a SPARSE, shallow
# checkout with no tags at all. `git tag -f -a production "$VERSION^{commit}"`
# would fail there with "unknown revision" on a perfectly good tag, because the
# ref was never fetched. That is the same trap assert-edge-tag-exists.sh already
# documents, one script over: reach for the API whenever the question is "what
# does this tag point at" and the checkout is not guaranteed complete.
REPO="${GITHUB_REPOSITORY:-rediacc/console}"

if ! sha="$(gh api "repos/$REPO/git/ref/tags/$VERSION" --jq '.object.sha' 2>&1)"; then
    log_error "mark-production: could not resolve $VERSION to a commit: $sha"
    exit 1
fi

# An ANNOTATED tag points at a tag object, not a commit. Deref it, or
# `production` would point at a tag object and `git show production` would give
# the annotation rather than the code.
obj_type="$(gh api "repos/$REPO/git/ref/tags/$VERSION" --jq '.object.type' 2>/dev/null || echo "")"
if [[ "$obj_type" == "tag" ]]; then
    sha="$(gh api "repos/$REPO/git/tags/$sha" --jq '.object.sha' 2>/dev/null || echo "$sha")"
fi

if gh api "repos/$REPO/git/refs/tags/production" >/dev/null 2>&1; then
    gh api --method PATCH "repos/$REPO/git/refs/tags/production" \
        -f sha="$sha" -F force=true >/dev/null
else
    gh api --method POST "repos/$REPO/git/refs" \
        -f ref="refs/tags/production" -f sha="$sha" >/dev/null
fi
log_info "mark-production: moved the 'production' tag to $VERSION ($sha)"

# 2. the badge humans actually read
gh release edit "$VERSION" --latest
log_info "mark-production: marked $VERSION as the latest GitHub Release"
