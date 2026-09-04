#!/bin/bash
# ---- gate ----
# step: Shell format
# needs: none
# id: check:ci-shell-format
# ---- end gate ----

# Shell script formatting check using shfmt
# Used by both ./run.sh quality shell and CI
#
# Checks all shell scripts for consistent formatting

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# The gate acquires its own tool AT the pin; see the block in main().
# shellcheck source=/dev/null
. "$ROOT_DIR/.ci/scripts/lib/toolchain.sh"
toolchain_load || exit 1

# Colors (disabled in CI)
if [[ "${CI:-}" == "true" ]]; then
    RED="" GREEN="" NC=""
else
    RED='\033[0;31m' GREEN='\033[0;32m' NC='\033[0m'
fi

log_error() { echo -e "${RED}error: $1${NC}" >&2; }
log_success() { echo -e "${GREEN}success: $1${NC}"; }
log_info() { echo "info: $1"; }

# shfmt options
# -i 4: 4-space indentation
# -ci: indent switch cases
# -d: diff mode (show what would change, exit non-zero if changes needed)
SHFMT_OPTS="-i 4 -ci -d"

main() {
    cd "$ROOT_DIR"

    log_info "Checking shell script formatting"

    # ACQUIRE AT THE PIN, not merely "present". A bare `command -v` accepts any
    # version, so a stale binary on a developer's PATH silently decided this
    # gate's verdict -- measured 2026-08-25: host shellcheck 0.9.0 against CI's
    # 0.10.0, and two unpinned shfmt installs that agreed only by luck.
    if ! SHFMT_BIN="$(toolchain_acquire shfmt)"; then
        log_error "shfmt is unusable for this gate -- CANNOT RUN, not a verdict"
        log_info "Every lane's toolchain: .ci/scripts/lib/toolchain.sh --report"
        log_info "Or run the gate where it is pinned: ./run.sh devbox exec -- .ci/scripts/security/shfmt.sh"
        # 77 = CANNOT_RUN, the convention check-python-lint.sh:170 established
        # for ruff and for the same reason. exit 1 here claimed "shfmt found bad
        # formatting", which is false on a host that has no shfmt at all, and it
        # put this gate in the pre-push lane's FAILED list beside genuine reds --
        # measured 2026-08-27, while the very same check passed inside the devbox.
        # The ci-runner classifies 77 as BLOCKED: counted, named, recorded in the
        # push receipt and warned about, but never a claim about the code.
        # Under CI the pinned toolchain is present, so this never fires there.
        exit 77
    fi

    "$SHFMT_BIN" --version

    # VACUITY FLOOR. Every check below is `find ... -exec shfmt`, and find that
    # matches nothing runs shfmt on nothing and exits 0. A green then means "no
    # formatting problems" and "the enumeration lost its corpus" equally, which is
    # the shape check:ci-enumeration-vacuity exists to refuse. Measured 2026-09-04:
    # 568 .sh files across the four scopes. The floor is well under that so it
    # catches a broken find, not today's file count.
    MIN_SHELL_FILES="${SHFMT_MIN_FILES:-200}"
    shell_seen=$(find .ci .claude scripts -name "*.sh" -type f 2>/dev/null | wc -l || true)
    if [[ "$shell_seen" -lt "$MIN_SHELL_FILES" ]]; then
        log_error "VACUOUS: found $shell_seen shell script(s), floor $MIN_SHELL_FILES."
        log_error "The enumeration lost its corpus; refusing to report formatting clean."
        exit 1
    fi

    # Check all shell scripts in .ci directory
    log_info "Checking .ci/**/*.sh"
    # BLOCKER: SHFMT_OPTS is a space-separated set of CLI flags; word-splitting is intentional so shfmt receives each flag as its own argv entry
    # shellcheck disable=SC2086
    find .ci -name "*.sh" -type f -exec "$SHFMT_BIN" $SHFMT_OPTS {} +

    # Claude hooks carry live PR policy (draft enforcement, --admin ban,
    # merge-time review hygiene) — policy-critical shell gets formatted too.
    #
    # Scope is the whole .claude tree, not .claude/hooks, since 2026-08-15: a
    # helper under .claude/lib passed both shell gates while carrying a blatant
    # SC2086, because neither gate was looking at it.
    #
    # DELIBERATELY NARROWER THAN shellcheck.sh, which now enumerates every
    # tracked *.sh from git. The asymmetry is intentional and is not an
    # oversight to be "fixed": shellcheck reports CORRECTNESS defects (SC2155
    # masking an exit code, SC2068 mangling arguments) and is worth surfacing
    # everywhere, while shfmt reports FORMATTING. Enumerating everything here
    # would demand reformatting 11 files nobody is otherwise touching, including
    # deployed repository templates under packages/json/templates — pure churn
    # in a shared tree, with no defect found. Widen this only alongside an
    # intentional decision to reformat those files.
    log_info "Checking .claude/**/*.sh"
    # BLOCKER: SHFMT_OPTS is a space-separated set of CLI flags; word-splitting is intentional so shfmt receives each flag as its own argv entry
    # shellcheck disable=SC2086
    find .claude -name "*.sh" -type f -exec "$SHFMT_BIN" $SHFMT_OPTS {} +

    # Check the main run.sh script
    log_info "Checking ./run.sh"
    # BLOCKER: SHFMT_OPTS is a space-separated set of CLI flags; word-splitting is intentional so shfmt receives each flag as its own argv entry
    # shellcheck disable=SC2086
    "$SHFMT_BIN" $SHFMT_OPTS ./run.sh

    # Check shell scripts under scripts/dev and scripts/docker subdirectories.
    # The top-level scripts/*.sh files are intentionally excluded — they
    # predate the formatter and reformatting them is out of scope for any
    # given change. Add new helper scripts to scripts/dev/ or scripts/docker/.
    for dir in scripts/dev scripts/docker; do
        if [[ -d "$dir" ]]; then
            log_info "Checking $dir/**/*.sh"
            # BLOCKER: SHFMT_OPTS is a space-separated set of CLI flags; word-splitting is intentional so shfmt receives each flag as its own argv entry
            # shellcheck disable=SC2086
            find "$dir" -name "*.sh" -type f -exec "$SHFMT_BIN" $SHFMT_OPTS {} +
        fi
    done

    log_success "Shell script formatting passed"
}

main "$@"
