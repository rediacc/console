#!/bin/bash
# Pre-pull the service images the origin stack expects, and NEVER fail the
# session because they were unavailable.
#
# WHY THIS EXISTS
# The services path is: this script -> ci-pull-images.sh (pulls
# ghcr.io/rediacc/server) -> start-origin.sh -> ci-start-elite.sh, which goes
# straight to `up -d` on the assumption that a prior step already pulled the
# images. The breakpoint workflow had no such step, so compose fell back to
# building and died with:
#
#   target account-server: failed to solve: failed to read dockerfile:
#   open Dockerfile: no such file or directory
#
# because the account image's Dockerfile lives in a submodule this workflow
# deliberately does not check out (see the "no GitHub App" decision in README.md).
# Pulling is both faster and the thing every other CI job does.
#
# FAILS LOUDLY. An earlier draft of this script always exited 0, on the theory
# that a box without its app image is still a useful box. That is a fallback,
# and fallbacks hide: the operator asked for --services, the pull silently did
# not happen, the origin stack then could not start anything, and the first
# symptom was "bad gateway" at the tunnel root with nothing in between
# explaining why.
# If the images cannot be pulled, say so HERE, where the reason is still in
# scope, and let the run fail. `hold-on-failure: true` keeps the box alive for
# inspection when you want to debug the boot itself.
#
# Env: GITHUB_TOKEN, GITHUB_ACTOR (both required to reach GHCR)
# Exit: 0 pulled, 1 pull failed, 3 misconfigured.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

REPO_ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
PULLER="$REPO_ROOT/.ci/scripts/infra/ci-pull-images.sh"

if [[ ! -x "$PULLER" ]]; then
    log_error "no $PULLER in this repo, so --services cannot be honoured"
    log_error "dispatch with services: none in a repo without console's infra tree"
    exit 3
fi

if [[ -z "${GITHUB_TOKEN:-}" ]] || [[ -z "${GITHUB_ACTOR:-}" ]]; then
    log_error "GITHUB_TOKEN/GITHUB_ACTOR are required to reach GHCR and are not set"
    exit 3
fi

log_step "pre-pulling service images from GHCR..."

# >&2 for the same reason as in start-origin.sh: this runs in a step whose
# sibling scripts have a one-line-stdout contract, and ci-pull-images.sh is
# chatty. Keeping the habit everywhere is cheaper than remembering where it
# matters.
if ! "$PULLER" >&2; then
    log_error "image pre-pull FAILED -- the origin stack cannot start anything without these images"
    log_error "(it skips 'docker compose build' whenever GITHUB_ACTIONS is set)"
    log_error "re-dispatch with services: none, or with hold-on-failure to debug the pull"
    exit 1
fi

log_info "service images pulled"
