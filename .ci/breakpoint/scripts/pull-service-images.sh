#!/bin/bash
# Pre-pull the service images ci-start.sh expects, and NEVER fail the session
# because they were unavailable.
#
# WHY THIS EXISTS
# `.ci/scripts/infra/ci-start.sh` skips `docker compose build` whenever
# GITHUB_ACTIONS is set (ci-start.sh:33-38) and goes straight to `up -d`, on the
# assumption that a prior CI step already pulled the images. The breakpoint
# workflow had no such step, so compose fell back to building and died with:
#
#   target account-server: failed to solve: failed to read dockerfile:
#   open Dockerfile: no such file or directory
#
# because the account image's Dockerfile lives in a submodule this workflow
# deliberately does not check out (see the no-app-token decision in README.md).
# Pulling is both faster and the thing every other CI job does.
#
# ALWAYS EXITS 0. A debug box whose application image is missing is still a
# perfectly good debug box -- you still get the tunnel, the desktop and the
# shell. start-origin.sh already reports the degraded state loudly, so failing
# here would throw away a working session over an optional extra.
#
# Env: GITHUB_TOKEN, GITHUB_ACTOR (both required to reach GHCR)
# Exit: 0, always.

set -uo pipefail # NOT -e: a pull failure must not end the session
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

REPO_ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
PULLER="$REPO_ROOT/.ci/scripts/infra/ci-pull-images.sh"

if [[ ! -x "$PULLER" ]]; then
    # Normal for a repo that vendored breakpoint without console's infra tree.
    log_warn "no $PULLER in this repo; skipping the image pre-pull"
    exit 0
fi

if [[ -z "${GITHUB_TOKEN:-}" ]] || [[ -z "${GITHUB_ACTOR:-}" ]]; then
    log_warn "GITHUB_TOKEN/GITHUB_ACTOR not set; skipping the image pre-pull"
    log_warn "services will start only if the images are already on this runner"
    exit 0
fi

log_step "pre-pulling service images from GHCR..."

# >&2 for the same reason as in start-origin.sh: this runs in a step whose
# sibling scripts have a one-line-stdout contract, and ci-pull-images.sh is
# chatty. Keeping the habit everywhere is cheaper than remembering where it
# matters.
if "$PULLER" >&2; then
    log_info "service images pulled"
else
    log_warn "image pre-pull FAILED; the session continues without the app stack"
    log_warn "the tunnel, desktop and shell are unaffected -- only --services is degraded"
fi

exit 0
