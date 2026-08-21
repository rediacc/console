#!/bin/bash
# Every standalone Go module that `replace`s the renet worktree must stay TIDY
# against it.
#
# WHAT BROKE. .ci/scripts/private/license-mint/ is its own module and pulls renet
# in through `replace github.com/rediacc/renet => ../../../../private/renet`, so
# renet's dependency graph is part of its own. Bumping renet's `go.mod`
# (logrus v1.10.0 -> v1.10.1) left license-mint still pinning v1.10.0 as
# indirect, and `go build` then refuses with:
#
#     go: updates to go.mod needed; to update it:
#             go mod tidy
#
# WHY IT NEEDS A GATE RATHER THAN CARE. Nothing surfaced this until
# `Tests + Infra / License Enforcement`, roughly 25 minutes into CI and well past
# every quality lane, on run 32462755535. The signal is also misleading at first
# read: the job announces "Building license-mint" and then prints a wall of
# `go: downloading ...` lines including the OLD version, so it looks like a
# network step rather than a lockstep violation. The coupling is invisible from
# renet's side, where the bump looks complete and self-contained.
#
# It is DISCOVERED, not hardcoded: any future module that replaces renet is
# covered the day it is added, and a zero-module result is a failure rather than
# a pass, because a discovery gate that finds nothing has verified nothing.
#
# `go mod tidy -diff` reports what tidying WOULD change and exits non-zero
# without writing, so this never mutates the tree it checks.
#
# Exit 0 clean, 1 violation, 2 setup error.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

cd "$ROOT_DIR"

command -v go >/dev/null 2>&1 || {
    log_error "go is required to check module sync"
    exit 2
}

# GOTOOLCHAIN is deliberately NOT forced to `local`. renet's go.mod requires
# >= 1.25.0 and a machine whose local toolchain is older (1.24.0 was observed)
# would fail with "go.mod requires go >= 1.25.0" and read as a module-sync
# defect, which it is not.
mapfile -t MODULES < <(grep -rln "replace github.com/rediacc/renet" --include=go.mod . 2>/dev/null |
    grep -v node_modules | sort)

if [[ ${#MODULES[@]} -eq 0 ]]; then
    log_error "no go.mod replaces the renet worktree, so this gate verified NOTHING."
    log_error "  Either the coupling is gone and this gate should be deleted deliberately,"
    log_error "  or the replace directive moved and the discovery below needs retargeting."
    exit 1
fi

failed=0
for mod in "${MODULES[@]}"; do
    dir="$(dirname "$mod")"
    if out="$(cd "$dir" && go mod tidy -diff 2>&1)"; then
        log_info "$dir is tidy against renet"
    else
        log_error "$dir is OUT OF SYNC with the renet worktree it replaces."
        log_error "  Fix: (cd $dir && go mod tidy)"
        [[ -n "$out" ]] && printf '%s\n' "$out" | head -20 >&2
        failed=1
    fi
done

if ((failed != 0)); then
    log_error "Go module sync FAILED (a renet dependency bump must re-tidy every module that replaces it)"
    exit 1
fi
log_info "Go module sync holds: ${#MODULES[@]} module(s) tidy against the renet worktree"
