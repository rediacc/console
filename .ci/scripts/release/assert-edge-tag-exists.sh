#!/bin/bash
# Assert that the version an R2 channel pointer advertises is a version that
# REALLY EXISTS: git tag, GitHub Release, and R2 release sentinel.
#
# WHY THIS EXISTS. On 2026-08-24 `cli/edge/manifest.json` advertised 1.3.1 while
# no `v1.3.1` tag, no GitHub Release and no `cli/v1.3.1/.released` existed: two
# `bump-none` merges had run the R2 upload loop anyway. promote-stable.yml would
# have promoted those bytes to stable and to the `:stable` Docker tag FIRST
# (promote-stable.yml:70-100) and only then failed on `ref: v1.3.1` when checking
# out for the worker/account deploys (:133, :159) -- a half-applied release
# across three regions. This script is the precondition that turns that ordering
# into a loud no-op: it runs before ANY promotion write.
#
# It deliberately duplicates the upstream uploader guard. Different cause,
# different blast radius, different failure time; its oracle (git refs + the
# Releases API + the R2 sentinel) is independent of its subject (the manifest).
#
# THREE RULES IT IS BUILT AROUND
#   1. FAIL, never skip. A skip is how a guard silently never fires. A daily red
#      cron is a correct alarm; a daily silent no-op is not.
#   2. "Could not tell" is a FAILURE. A 404 confirms absence; a 403, a 5xx or a
#      network error means the check did NOT RUN, and a check that did not run
#      must not read as a pass. Those exit 1 too, with a distinguishable message.
#   3. Use the GitHub API for the tag, NOT `git rev-parse`. The caller's checkout
#      is shallow with no tags, so `git rev-parse` would report a perfectly good
#      tag as missing.
#
# Usage:
#   .ci/scripts/release/assert-edge-tag-exists.sh --version 1.3.0
#   .ci/scripts/release/assert-edge-tag-exists.sh v1.3.0
#
# Required env:
#   GH_TOKEN / GITHUB_TOKEN   for `gh` (repo contents: read is enough)
#   CLOUDFLARE_R2_ACCESS_KEY_ID / CLOUDFLARE_R2_SECRET_ACCESS_KEY / CLOUDFLARE_R2_ENDPOINT   for the sentinel read
# Optional env:
#   GITHUB_REPOSITORY   owner/repo (default: rediacc/console)
#   RELEASES_BUCKET     R2 bucket   (default: rediacc-releases)
#
# Exit codes: 0 = all three present. 1 = anything missing, unprovable, or misused.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

VERSION=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="${2:-}"
            shift 2
            ;;
        -h | --help)
            echo "Usage: $0 --version VERSION      (VERSION may be 1.3.0 or v1.3.0)"
            exit 0
            ;;
        -*)
            log_error "assert-edge-tag-exists.sh: unknown option: $1"
            exit 1
            ;;
        *)
            VERSION="$1"
            shift
            ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    log_error "assert-edge-tag-exists.sh: a version is required (--version 1.3.0)"
    exit 1
fi

VERSION="${VERSION#v}"
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$ ]]; then
    log_error "assert-edge-tag-exists.sh: '$VERSION' is not a semver version"
    exit 1
fi
TAG="v${VERSION}"

require_cmd gh
require_cmd aws
: "${CLOUDFLARE_R2_ENDPOINT:?assert-edge-tag-exists.sh: CLOUDFLARE_R2_ENDPOINT must be set}"
: "${CLOUDFLARE_R2_ACCESS_KEY_ID:?assert-edge-tag-exists.sh: CLOUDFLARE_R2_ACCESS_KEY_ID must be set}"
: "${CLOUDFLARE_R2_SECRET_ACCESS_KEY:?assert-edge-tag-exists.sh: CLOUDFLARE_R2_SECRET_ACCESS_KEY must be set}"
# The aws CLI reads AWS_*; the workflow passes R2_*. Every sibling that talks to
# R2 bridges the two names here (assert-r2-sentinel.sh:47, write-release-sentinel.sh:83,
# upload-to-r2.sh:154) and this script was the one that did not -- so `aws s3api
# head-object` below died on NoCredentials, the sentinel probe answered `unknown`,
# and promote-stable failed all 7 runs from 2026-08-27 onward, never once green.
export AWS_ACCESS_KEY_ID="$CLOUDFLARE_R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$CLOUDFLARE_R2_SECRET_ACCESS_KEY"
REPO="${GITHUB_REPOSITORY:-rediacc/console}"
BUCKET="${RELEASES_BUCKET:-rediacc-releases}"

# Every probe answers with exactly one of:
#   present            the thing is there
#   absent             the thing is provably NOT there (an authoritative 404)
#   unknown:<detail>   the probe did not run to a verdict -- treated as failure
one_line() { tr '\n' ' ' | sed 's/  */ /g'; }

probe_gh_api() {
    local path="$1" out rc=0
    out="$(gh api "$path" 2>&1)" || rc=$?
    if ((rc == 0)); then
        echo "present"
        return 0
    fi
    if grep -qE 'HTTP 404|Not Found' <<<"$out"; then
        echo "absent"
        return 0
    fi
    printf 'unknown:%s\n' "$(one_line <<<"$out")"
}

probe_gh_release() {
    local tag="$1" out rc=0
    out="$(gh release view "$tag" --json tagName 2>&1)" || rc=$?
    if ((rc == 0)); then
        echo "present"
        return 0
    fi
    if grep -qE 'HTTP 404|Not Found|release not found|^release not found' <<<"$out"; then
        echo "absent"
        return 0
    fi
    printf 'unknown:%s\n' "$(one_line <<<"$out")"
}

# NOTE: this deliberately does NOT reuse rsv_sentinel_exists() from
# release-state-validator.sh. That helper collapses EVERY failure -- expired
# credentials, a 5xx, a DNS failure -- into "the sentinel does not exist", which
# is the opposite of rule 2 above: it can only ever answer present/absent, never
# "could not tell".
probe_r2_sentinel() {
    local key="$1" out rc=0
    out="$(aws s3api head-object \
        --bucket "$BUCKET" \
        --key "$key" \
        --endpoint-url "$CLOUDFLARE_R2_ENDPOINT" 2>&1)" || rc=$?
    if ((rc == 0)); then
        echo "present"
        return 0
    fi
    if grep -qE '\(404\)|Not Found|NoSuchKey' <<<"$out"; then
        echo "absent"
        return 0
    fi
    printf 'unknown:%s\n' "$(one_line <<<"$out")"
}

FAILED=0
# Tracked separately from FAILED because the two states need OPPOSITE advice, and
# conflating them cost real cycles: the NoCredentials failure above printed
# "cut the release, then Backfill Release Sentinel" at an operator whose sentinel
# was already fine. `absent` is a verdict about the release; `unknown` is the
# absence of a verdict, and nothing about the release follows from it.
COULD_NOT_TELL=0
judge() {
    local what="$1" state="$2"
    case "$state" in
        present)
            log_info "OK      ${what}"
            return 0
            ;;
        absent)
            log_error "MISSING ${what} -- the channel pointer advertises a version that does not exist"
            FAILED=1
            return 1
            ;;
        # COULD_NOT_TELL_ARM_BEGIN (anchor for the gate test's planted defect --
        # .ci/scripts/test/gates/test-assert-edge-tag-exists.sh rebuilds this arm
        # as `return 0` and requires the 403 case to go green; do not remove the
        # markers)
        unknown:*)
            log_error "COULD NOT TELL ${what} -- the probe did not reach a verdict: ${state#unknown:}"
            log_error "  A check that did not run must not read as a pass. Treating it as a failure."
            FAILED=1
            COULD_NOT_TELL=1
            return 1
            ;;
        # COULD_NOT_TELL_ARM_END
        *)
            log_error "INTERNAL assert-edge-tag-exists.sh: unclassifiable probe result '${state}' for ${what}"
            FAILED=1
            return 1
            ;;
    esac
}

log_step "Asserting ${TAG} really exists before any promotion write"

judge "git tag ${TAG} (${REPO})" "$(probe_gh_api "repos/${REPO}/git/ref/tags/${TAG}")" || true
judge "GitHub Release ${TAG}" "$(probe_gh_release "$TAG")" || true
judge "R2 sentinel s3://${BUCKET}/cli/${TAG}/.released" "$(probe_r2_sentinel "cli/${TAG}/.released")" || true

if ((FAILED != 0)); then
    log_error ""
    log_error "REFUSING TO PROMOTE ${TAG}."
    if ((COULD_NOT_TELL != 0)); then
        log_error "  At least one probe COULD NOT REACH A VERDICT (see COULD NOT TELL above)."
        log_error "  This says nothing about whether ${TAG} is published -- it says the check"
        log_error "  did not run. Do NOT cut a release and do NOT backfill a sentinel on the"
        log_error "  strength of this; fix the probe first, then re-run."
        log_error "  'NoCredentials' means the aws CLI got no AWS_ACCESS_KEY_ID: check that"
        log_error "  the calling workflow passes CLOUDFLARE_R2_ACCESS_KEY_ID / CLOUDFLARE_R2_SECRET_ACCESS_KEY in."
    else
        log_error "  The edge channel pointer names a version that is not fully published."
        log_error "  Promoting it would copy unreleased bytes to stable and then fail on"
        log_error "  'ref: ${TAG}' halfway through, leaving a half-applied release."
        log_error "  Remediate first: cut the release for ${TAG} (Release workflow), then"
        log_error "  seal it (Backfill Release Sentinel), then re-run this promotion."
    fi
    exit 1
fi

log_info "All three exist: git tag, GitHub Release, and R2 sentinel for ${TAG}."
