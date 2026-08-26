#!/bin/bash
# The bump-none decision must EMIT ITS SIGNAL, and only on the skip path.
#
# WHY THIS EXISTS. Two gates already cover neighbouring ground and neither
# touches this: `check-ci-workflow-invariants.sh` asserts the WIRING in ci.yml
# (that the decision is declared once, threaded, and not re-decided in
# finalize-release-sentinel), and `test-skip-release-channel-pointer.sh` proves
# the UPLOAD script's guard branches correctly. Nothing drove
# `dispatch-release.sh`'s own decision branch, so "Finalize Release emitted the
# skip signal for the right reason" was unobservable by construction. Release
# gates could say a release succeeded or was absent; they could not say WHY.
#
# That distinction is not academic here. A bump-none merge and a broken decision
# both produce "no release". They are indistinguishable from the outside, and the
# only thing that tells them apart is the signal this script emits:
#
#     release SKIPPED: #576 carries 'bump-none'
#     ::notice title=Release skipped::...earns no release...
#     decision: skip
#
# Observed live on 2026-08-26 (run 32961178698, job 98165911876) after merging
# PR #576. This gate keeps that observable.
#
# THE DIRECTION THAT MATTERS MOST is not "does it skip" -- it is that the signal
# must NOT appear when the commit is releasing. A skip notice on a releasing path
# would tell a reader the opposite of what happened, and `dispatch-release.sh`'s
# whole doctrine is that a silently withheld release is worse than an extra one.
#
# HERMETIC: `gh` is shimmed, so this never touches the network and can run in any
# lane. WHAT IT CANNOT SEE: whether the workflow actually CALLS the script (that
# is check-ci-workflow-invariants.sh's subject), and whether a real run's log
# retains the line (only a live bump-none merge shows that).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_error / log_info and get_repo_root are used throughout this gate
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

SUT="${RELEASE_DECIDE_SCRIPT:-.ci/scripts/ci/dispatch-release.sh}"
if [[ ! -f "$SUT" ]]; then
    log_error "release-bump-skip: $SUT does not exist. Nothing to drive is not a clean tree -- if the decision moved, retarget this gate deliberately."
    exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FAILED=0

# drive <label> <gh-rows> -- runs the REAL script with a shimmed gh and prints
# "<rc>|<combined output>". `rows` is what the API would return, one PR per line
# as "<number> <labels,csv>"; the literal FAIL makes the shim exit non-zero.
drive() {
    local rows="$1" bin="$WORK/bin" out rc=0
    rm -rf "$bin"
    mkdir -p "$bin"
    if [[ "$rows" == "FAIL" ]]; then
        printf '#!/bin/bash\necho "api exploded" >&2\nexit 1\n' >"$bin/gh"
    else
        {
            printf '#!/bin/bash\ncat <<'"'"'ROWS'"'"'\n'
            printf '%s\n' "$rows"
            printf 'ROWS\n'
        } >"$bin/gh"
    fi
    chmod +x "$bin/gh"
    out="$(PATH="$bin:$PATH" \
        GITHUB_REPOSITORY="rediacc/console" \
        GITHUB_SHA="1c006e538fe3d33eeb280b809140b0d477a280db" \
        GITHUB_OUTPUT="$WORK/out.txt" \
        bash "$SUT" --decide-only 2>&1)" || rc=$?
    printf '%s|%s' "$rc" "$out"
}

expect() { # expect <label> <rows> <want-decision> <must-contain> <must-not-contain>
    local label="$1" rows="$2" want="$3" needle="$4" anti="$5"
    local res rc out
    res="$(drive "$rows")"
    rc="${res%%|*}"
    out="${res#*|}"

    if ! grep -q "decision: $want" <<<"$out"; then
        log_error "release-bump-skip: $label -- expected 'decision: $want', got:"
        printf '%s\n' "$out" | sed 's/^/      /' | head -6 >&2
        FAILED=1
        return
    fi
    if [[ -n "$needle" ]] && ! grep -qF "$needle" <<<"$out"; then
        log_error "release-bump-skip: $label -- the signal is missing: $needle"
        FAILED=1
        return
    fi
    if [[ -n "$anti" ]] && grep -qF "$anti" <<<"$out"; then
        log_error "release-bump-skip: $label -- emitted a signal it must NOT: $anti"
        FAILED=1
        return
    fi
    log_info "  ok  $label (rc=$rc)"
}

log_info "release-bump-skip: driving the real decision through every branch"

# 1. The case the label exists for: the signal must be emitted, and it must NAME
#    the PR and the label, because "no release" without a reason is the ambiguity
#    this gate exists to remove.
expect "bump-none only -> skips, and says why" \
    "576 ci,bump-none" "skip" "release SKIPPED: #576 carries 'bump-none'" ""

# 2. THE DIRECTION THAT MATTERS MOST. A releasing commit must not carry a skip
#    notice; a reader would conclude the opposite of what happened.
expect "no skip label -> releases, and emits NO skip signal" \
    "576 ci,documentation" "release" "" "release SKIPPED"

# 3. Mixed: one PR asks to skip, another does not. Releasing is correct, and the
#    skip signal must still be withheld.
expect "mixed labels -> releases, still no skip signal" \
    "$(printf '576 ci,bump-none\n577 ci')" "release" "" "release SKIPPED"

# 4. Fail OPEN. An unreadable API must release rather than silently withhold --
#    the script's stated doctrine -- and must not claim a skip.
expect "API failure -> releases (fails open), no skip signal" \
    "FAIL" "release" "" "release SKIPPED"

# 5. No merged PR at all (direct push): releases, no skip signal.
expect "no merged PR -> releases, no skip signal" \
    "" "release" "" "release SKIPPED"

# ANTI-VACUITY. If the shim could not drive the script at all, every `expect`
# above would have failed loudly -- but a future refactor could make the script
# exit 0 printing nothing, and `grep -q "decision: release"` would then fail
# rather than pass, so the suite stays honest. The control here is the opposite
# risk: prove the harness can still produce a SKIP, so case 2's "no skip signal"
# is not passing because the signal is unreachable for everyone.
control="$(drive "999 bump-none")"
if ! grep -q "release SKIPPED" <<<"${control#*|}"; then
    log_error "release-bump-skip: CONTROL FAILED -- the harness cannot produce a skip signal at all, so every 'must not emit' assertion above is vacuous."
    FAILED=1
fi

if ((FAILED != 0)); then
    log_error "release-bump-skip FAILED"
    exit 1
fi

log_info "release-bump-skip: the skip signal is emitted on the skip path and withheld on all four releasing paths"
log_info "  Blind spot: does not prove the workflow CALLS this script (that is"
log_info "  check-ci-workflow-invariants.sh), nor that a live run's log retains the"
log_info "  line -- only a real bump-none merge shows that."
