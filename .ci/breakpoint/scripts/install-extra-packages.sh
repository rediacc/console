#!/bin/bash
# Install the operator's list of extra apt packages onto the session box.
#
# The list is BREAKPOINT_EXTRA_PACKAGES in breakpoint.conf. That file is the
# only one excluded from MANIFEST.sha256, which is the whole point: adding a
# tool you keep reaching for is a config edit, not a code change -- no drift
# regeneration, no re-vendor, and each repo keeps its own list.
#
# FAILS LOUDLY on a bad package name, and that is deliberate. The tempting
# behaviour is `|| true` so a typo does not cost you a session. But the cost
# lands later and worse: you SSH into the box, reach for the tool, and it is not
# there, with nothing in the log saying why. Better to lose the boot and know.
# Use `hold-on-failure: true` if you want the box kept alive to debug the boot.
#
# Idempotent: apt-get install on an already-present package is a no-op.
#
# Usage: install-extra-packages.sh [--packages "a b c"]
#        (--packages overrides the conf list; mainly for testing)
# Exit:  0 installed or nothing to do, 1 install failed, 3 unsupported platform.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

PACKAGES="${ARG_PACKAGES:-${BREAKPOINT_EXTRA_PACKAGES:-}}"

if [[ -z "${PACKAGES// /}" ]]; then
    log_info "no extra packages configured (BREAKPOINT_EXTRA_PACKAGES is empty)"
    exit 0
fi

if ! command -v apt-get >/dev/null 2>&1; then
    log_error "BREAKPOINT_EXTRA_PACKAGES is set but this runner has no apt-get"
    log_error "packages requested: $PACKAGES"
    exit 3
fi

log_step "installing extra packages: $PACKAGES"
export DEBIAN_FRONTEND=noninteractive

if ! sudo apt-get update -qq; then
    log_error "apt-get update failed; cannot install $PACKAGES"
    exit 1
fi

# Deliberately NOT --no-install-recommends here, unlike the desktop installer:
# these are operator convenience tools and their recommends are usually the
# reason the tool is pleasant to use.
#
# One apt-get call, not a loop: apt resolves the set together, and a loop would
# report the first failure while leaving the rest unattempted.
# shellcheck disable=SC2086  # word-splitting is the point: PACKAGES is a list
if ! sudo apt-get install -y -qq $PACKAGES; then
    log_error "failed to install one or more of: $PACKAGES"
    log_error "check the exact apt package NAME -- e.g. on Ubuntu 24.04 the"
    log_error "bottom monitor is packaged as 'btm', not 'bottom'."
    log_error "edit BREAKPOINT_EXTRA_PACKAGES in .ci/breakpoint/breakpoint.conf"
    exit 1
fi

# Prove it, do not assume it. apt-get can exit 0 having installed a package
# whose binary is named something else entirely, which is exactly the confusion
# this list is meant to remove.
for pkg in $PACKAGES; do
    if command -v "$pkg" >/dev/null 2>&1; then
        log_info "  $pkg -> $(command -v "$pkg")"
    else
        log_warn "  $pkg installed, but no binary named '$pkg' is on PATH (the package may ship a differently-named command)"
    fi
done

log_info "extra packages installed"
