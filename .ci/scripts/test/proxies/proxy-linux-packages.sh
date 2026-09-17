#!/bin/bash
# Local proxy for the CI job "Tests + Infra / Linux Packages".
#
# CI runs .ci/scripts/test/test-linux-packages.sh with no flags, in the
# `package-tests` job of .github/workflows/ci.yml (the "Run Linux package tests"
# step). That job is NOT in the parity surface (which is ci.yml#quality plus the
# reusable workflows it calls), so `npm run ci` has never exercised any of it:
# nfpm packaging, the deb/rpm/apk/archlinux metadata, or the repo-metadata
# builder underneath it.
#
# WHY --dry-run IS THE RIGHT REDUCTION, and what it costs. Without the flag the
# subject installs each package inside eight distro containers, which is minutes
# of docker pulls per run. With it, phases 1 and 4 still do the REAL work -- nfpm
# really builds all four package formats and build-pkg-repo.sh really generates
# APT/RPM/APK/Arch metadata -- and only the container-install and full-APT-flow
# phases become stubs. Measured on this host: 312 ms, 10 of 21 subtests really
# executed.
#
# So the proxy PRINTS THAT SPLIT rather than a bare OK. "21 passed" alone would
# look identical whether ten subtests ran or zero did, and a dry run that
# stubbed everything is exactly the failure this file exists to notice.
#
# The expected subtest total is DERIVED from the subject's own `run_test` call
# sites, never hand-typed: a phase deleted from the subject then reds here
# instead of quietly shrinking the run.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

SUBJECT="$ROOT_DIR/.ci/scripts/test/test-linux-packages.sh"

if [[ "${1:-}" == "--selftest" ]]; then
    proxy_lib_selftest
    exit $?
fi

proxy_init linux-packages ".ci/scripts/test/test-linux-packages.sh --dry-run"

# nfpm is FETCHED at its pin by ensure-nfpm.sh, which both the subject and CI
# call. Resolve it here too, so a host without it reports one clear cannot-run
# instead of dying inside phase 1 with a bare "command not found".
if ! command -v nfpm >/dev/null 2>&1; then
    NFPM_DIR="$("$ROOT_DIR/.ci/scripts/build/ensure-nfpm.sh" 2>/dev/null || true)"
    [[ -n "$NFPM_DIR" ]] && PATH="$NFPM_DIR:$PATH" && export PATH
fi

proxy_need_exec "$SUBJECT" "the subject script is missing from this checkout"
proxy_need_cmd nfpm ".ci/scripts/build/ensure-nfpm.sh (needs network on first run)"
proxy_need_cmd dpkg-deb "sudo apt-get install -y dpkg-dev"
proxy_need_cmd rpmbuild "sudo apt-get install -y rpm"
proxy_need_cmd createrepo_c "sudo apt-get install -y createrepo-c"
proxy_need_cmd gpg "sudo apt-get install -y gnupg"
proxy_preflight

# The corpus-derived expectation: every `run_test` call site in the subject.
EXPECTED_TESTS=$(grep -cE '^run_test "' "$SUBJECT")
if [[ "$EXPECTED_TESTS" -eq 0 ]]; then
    echo "${PROXY_RED}proxy linux-packages: found ZERO run_test call sites in the subject${PROXY_OFF}" >&2
    echo "  The expectation is derived from the subject and the derivation collapsed," >&2
    echo "  so any comparison against it would be vacuous. Check the grep in this file" >&2
    echo "  against $SUBJECT." >&2
    exit 1
fi

OUT="$(mktemp)"
ERR="$(mktemp)"
trap 'rm -f "$OUT" "$ERR"' EXIT

# Streams read SEPARATELY: this subject writes its log_* lines to stderr and
# nfpm's own chatter to stdout, so a merged capture hides which side spoke.
"$SUBJECT" --dry-run >"$OUT" 2>"$ERR"
RC=$?
BOTH="$(cat "$OUT" "$ERR")"

if [[ $RC -eq 0 ]]; then
    proxy_pass "test-linux-packages.sh --dry-run exited 0"
else
    proxy_fail "test-linux-packages.sh --dry-run exited $RC"
    echo "  --- subject stdout (last 30) ---" >&2
    tail -30 "$OUT" >&2
    echo "  --- subject stderr (last 30) ---" >&2
    tail -30 "$ERR" >&2
fi

RESULTS_LINE="$(printf '%s\n' "$BOTH" | grep -oE 'Results: [0-9]+ passed, [0-9]+ failed \(total [0-9]+\)' | tail -1)"
if [[ -z "$RESULTS_LINE" ]]; then
    proxy_fail "the subject printed no 'Results:' summary line, so nothing can be read from this run"
else
    PASSED=$(printf '%s' "$RESULTS_LINE" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
    FAILED=$(printf '%s' "$RESULTS_LINE" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+')
    TOTAL=$(printf '%s' "$RESULTS_LINE" | grep -oE 'total [0-9]+' | grep -oE '[0-9]+')

    if [[ "$TOTAL" -eq "$EXPECTED_TESTS" ]]; then
        proxy_pass "ran all $EXPECTED_TESTS subtests the subject declares (corpus-derived, not hand-typed)"
    else
        proxy_fail "subject declares $EXPECTED_TESTS run_test call sites but reported total $TOTAL; a phase was skipped or added without this proxy noticing"
    fi

    if [[ "$FAILED" -eq 0 ]]; then
        proxy_pass "0 subtest failures ($PASSED passed)"
    else
        proxy_fail "$FAILED subtest(s) failed"
    fi
fi

# THE ANTI-VACUITY CHECK THAT MATTERS HERE. --dry-run turns some subtests into
# stubs that print "[DRY-RUN] Would ..." and pass unconditionally. If that set
# ever grew to cover everything, the run above would still say "21 passed".
#
# THE MARKER IS CORROBORATED AGAINST THE SUBJECT'S SOURCE FIRST, and that is
# the whole reason this block is more than one subtraction. "[DRY-RUN] Would"
# is a LITERAL matched out of the subject's RUNTIME OUTPUT, and an absent
# marker has two causes that the output cannot tell apart: nothing was stubbed,
# or the string was renamed out from under this check. Read only from the
# output, the second one silently becomes `EXPECTED_TESTS - 0`, and this
# registered gate prints its STRONGEST claim -- "21 of 21 subtests really
# executed" -- at the exact moment the evidence for it disappeared, exiting 0.
# So the two causes are told apart at the SOURCE: the marker must still exist
# in the subject for a count derived from it to mean anything, which is the
# same corroboration EXPECTED_TESTS gets from `^run_test "` above.
DRY_MARKER='[DRY-RUN] Would'
MARKER_SITES=$(grep -cF -- "$DRY_MARKER" "$SUBJECT" || true)
STUBBED=$(printf '%s\n' "$BOTH" | grep -cE 'TEST: ' || true)
DRYSTUB=$(printf '%s\n' "$BOTH" | grep -cF -- "$DRY_MARKER" || true)
if [[ "$MARKER_SITES" -eq 0 ]]; then
    proxy_fail "VACUOUS: the dry-run stub marker '$DRY_MARKER' appears 0 times in ${SUBJECT#"$ROOT_DIR"/}, so the stub count below is derived from nothing. Expected: at least one call site in the subject printing that marker. Found: none, which means it was renamed, and the subtraction would then read all $EXPECTED_TESTS subtests as really executed. Re-derive the marker from the subject's dry-run branch; do not delete this check and do not allowlist the subject."
else
    REAL=$((EXPECTED_TESTS - $(printf '%s\n' "$BOTH" | grep -B1 -F -- "$DRY_MARKER" | grep -cE 'TEST: ' || true)))
    if [[ "$REAL" -gt 0 ]]; then
        proxy_pass "$REAL of $EXPECTED_TESTS subtests really executed (nfpm build + repo metadata); $((EXPECTED_TESTS - REAL)) are dry-run stubs, $DRYSTUB stub lines, $STUBBED TEST banners, marker corroborated at $MARKER_SITES site(s) in the subject"
    else
        proxy_fail "every subtest was a dry-run stub; this run asserted nothing about packaging"
    fi
fi

proxy_finish
