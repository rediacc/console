#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: submodules
# lane: quality-security
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# why: Integration test for private/renet/.ci/scripts/quality/pipefail-grep-q.sh
# ---- end gate ----

# Integration test for private/renet/.ci/scripts/quality/pipefail-grep-q.sh.
#
# renet carries its own bash copy of the pipefail/`grep -q` detector because it
# must work standalone (see that file's header). A third implementation of a
# detector this repo already keeps as a bash/Python twin pair drifts unless
# something holds it, and THIS FILE IS THAT SOMETHING. It pins two things:
#
#   1. the detector's contract, driven from console against the renet script's
#      own `offenders()` (sourced under its BASH_SOURCE main guard), so the
#      twelve directions its in-script controls assert are asserted here too and
#      a renet-side regression reds console CI rather than only renet's stage;
#
#   2. PRODUCER-LIST PARITY, one-directional on purpose: renet's
#      SCALING_PRODUCERS must be a SUPERSET of console's. Superset, not equality,
#      because renet may legitimately be AHEAD (it was, by `tee` and `docker`,
#      between the commit that added it and the console widening that followed).
#      The direction that costs a MISSED DEFECT is console widening and renet not
#      following, and that is the one this reds on.
#
# Console's list is read by IMPORTING the shipped port
# (.ci/rediacc_ci/quality/pipefail_grep_q.py), never by re-parsing its source: a
# test that re-derives the value from the same text it is checking can agree with
# a typo.
#
# Fixtures are mktemp-only and never touch the real tree, so this test needs no
# mutex/reads claim in the battery's isolation lock.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

RENET_GATE="$REPO_ROOT/private/renet/.ci/scripts/quality/pipefail-grep-q.sh"

if [[ ! -f "$RENET_GATE" ]]; then
    echo "renet submodule not present -- skipping renet pipefail/grep -q gate test"
    exit 0
fi

# Sourcing skips main (BASH_SOURCE guard) but pulls in offenders, join_logical,
# SCALING_PRODUCERS, RENET_EXTRA_PRODUCERS, and renet's common.sh helpers.
# renet's common.sh sets `set -euo pipefail` and the gate then sets `set +e`
# because it counts failures; this test wants errexit, so restore it after.
# shellcheck source=/dev/null
source "$RENET_GATE"
set -e

FIXTURES="$(mktemp -d)"
trap 'rm -rf "$FIXTURES"' EXIT

# THE FIXTURES ARE ASSEMBLED AT RUNTIME, exactly as the renet gate's own are and
# for the same reason: written out literally, THIS file's text would carry the
# racing shape contiguously and console's own check:ci-pipefail-grep-q would flag
# it -- correctly, since the shape is here on purpose. `.ci/scripts/**/*.sh` is in
# that gate's corpus, so this is not hypothetical.
GQ_="grep -q"
PF_='set -o pipefail'

# write_fixture <name> <line>... -> prints the path
write_fixture() {
    local name="$1"
    shift
    local path="$FIXTURES/$name.sh"
    printf '%s\n' "$@" >"$path"
    echo "$path"
}

# assert_flagged <name> <message> <line>...
assert_flagged() {
    local name="$1" message="$2"
    shift 2
    local path hits=""
    path="$(write_fixture "$name" "$@")"
    # `|| true` IS REQUIRED, not defensive noise: offenders() returns the status
    # of its LAST inner grep, which is non-zero exactly when the file is CLEAN.
    # The renet gate never notices because it runs under `set +e`. Without this,
    # every silent-direction assertion below would kill this test with exit 1 and
    # no message -- which is how this file failed on its first run.
    hits="$(offenders "$path")" || true
    if [[ -z "$hits" ]]; then
        printf '    %s\n' "$@" >&2
        log_fail "$message -- renet's offenders() returned nothing for the lines above"
    fi
    log_pass "$message"
}

# assert_silent <name> <message> <line>...
assert_silent() {
    local name="$1" message="$2"
    shift 2
    local path hits=""
    path="$(write_fixture "$name" "$@")"
    # See assert_flagged: a CLEAN file makes offenders() exit non-zero.
    hits="$(offenders "$path")" || true
    if [[ -n "$hits" ]]; then
        log_fail "$message -- renet's offenders() flagged it: $hits"
    fi
    log_pass "$message"
}

test_detector_contract() {
    # The FLAGGED half.
    assert_flagged local-fn "a local function piped into grep -q is detected" \
        "$PF_" 'body() { cat "$1"; }' "if body \"\$1\" | $GQ_ x; then :; fi"
    assert_flagged builtin-printf "a printf producer is detected" \
        "$PF_" "if printf \"%s\" \"\$x\" | $GQ_ y; then :; fi"
    assert_flagged builtin-echo "an echo producer is detected" \
        "$PF_" "if echo \"\$x\" | $GQ_ y; then :; fi"
    assert_flagged command-producer "a scaling COMMAND producer is detected" \
        "$PF_" "if grep -vE \"^x\" \"\$1\" | $GQ_ needle; then :; fi"
    # No single LINE holds both the producer and grep -q. This is the direction
    # that let console's real offender survive every run of its own gate.
    assert_flagged multiline "a pipeline SPANNING LINES is detected" \
        "$PF_" 'grep -vE "^x" "$1" |' "    ${GQ_}E needle"
    assert_flagged tee-extra "the \`tee\` extra is detected" \
        "$PF_" "if cmd 2>&1 | tee \"\$LOG\" | $GQ_ ok; then :; fi"
    assert_flagged docker-extra "the \`docker\` extra is detected" \
        "$PF_" "if docker ps --format \"{{.Names}}\" | $GQ_ x; then :; fi"

    # The SILENT half. Each of these is a way the gate could be OVER-BROAD, and
    # an over-broad gate gets suppressed, which is how a gate dies.
    assert_silent sanctioned-fix "the sanctioned command-substitution fix is NOT flagged" \
        "$PF_" 'body() { cat "$1"; }' 'if [ -n "$(body "$1" | grep x)" ]; then :; fi'
    assert_silent no-pipefail "without pipefail the same shape is not flagged" \
        'body() { cat "$1"; }' "if body \"\$1\" | $GQ_ x; then :; fi"
    assert_silent in-comment "the shape inside a # COMMENT is not code" \
        "$PF_" 'body() { cat "$1"; }' "# never write: body \"\$1\" | $GQ_ x"
    assert_silent in-squote "the shape inside a SINGLE-quoted string is not code" \
        "$PF_" 'body() { cat "$1"; }' "advice='run body \"\$1\" | $GQ_ x instead'"
    assert_silent in-dquote "the shape inside a DOUBLE-quoted string is not code" \
        "$PF_" 'body() { cat "$1"; }' "advice=\"run body \\\$1 | $GQ_ x instead\""
}

# console_producers -- console's SCALING_PRODUCERS, IMPORTED from the shipped
# port rather than re-parsed out of its source text.
console_producers() {
    (cd "$REPO_ROOT" && python3 -c "import sys; sys.path.insert(0, '.ci'); from rediacc_ci.quality.pipefail_grep_q import SCALING_PRODUCERS; print(' '.join(SCALING_PRODUCERS))")
}

test_renet_list_is_a_superset_of_consoles() {
    local console_list missing=()
    console_list="$(console_producers)"

    # ANTI-VACUITY: an empty import would make the superset check trivially true,
    # which is precisely the "a check that cannot fail" shape this whole gate
    # family exists to prevent.
    # Counted with the shell, and membership tested with `case`, so this file
    # contains NO `producer | grep -q` of its own. It is scanned by console's
    # check:ci-pipefail-grep-q like every other .ci/scripts/**/*.sh, and a gate
    # test that commits the defect it polices is not a test.
    local -a console_arr=()
    read -ra console_arr <<<"$console_list"
    local console_count=${#console_arr[@]}
    if ((console_count < 10)); then
        log_fail "imported only $console_count producer(s) from console's port -- the import is broken, so the superset assertion below would pass vacuously"
    fi

    local p
    for p in "${console_arr[@]}"; do
        case " $SCALING_PRODUCERS " in
            *" $p "*) ;;
            *) missing+=("$p") ;;
        esac
    done
    if ((${#missing[@]} > 0)); then
        # log_fail EXITS, so the advice goes out first or it is never seen.
        {
            echo "  Console widened its list and renet did not follow. That is the drift"
            echo "  direction that costs a missed defect: the class is now detected in"
            echo "  console and invisible in the submodule."
            echo "  Fix: add them to CONSOLE_SCALING_PRODUCERS in"
            echo "  private/renet/.ci/scripts/quality/pipefail-grep-q.sh, convert whatever"
            echo "  sites the widening surfaces there, and bump the submodule pointer."
        } >&2
        log_fail "renet's SCALING_PRODUCERS is MISSING ${#missing[@]} name(s) console has: ${missing[*]}"
    fi
    log_pass "renet's producer list is a superset of console's ($console_count console name(s) all present)"
}

test_declared_extras_are_real() {
    # RENET_EXTRA_PRODUCERS is documentation that the parity message and the
    # renet header both lean on. If an extra rots into prose -- removed from the
    # live list but still named as an extra -- the two disagree silently.
    if [[ -z "${RENET_EXTRA_PRODUCERS// /}" ]]; then
        log_fail "RENET_EXTRA_PRODUCERS is empty, so this assertion would be vacuous"
    fi
    local p bad=()
    for p in $RENET_EXTRA_PRODUCERS; do
        case " $SCALING_PRODUCERS " in
            *" $p "*) ;;
            *) bad+=("$p") ;;
        esac
    done
    if ((${#bad[@]} > 0)); then
        log_fail "RENET_EXTRA_PRODUCERS declares ${bad[*]} but SCALING_PRODUCERS does not contain them"
    fi
    log_pass "every name in RENET_EXTRA_PRODUCERS (${RENET_EXTRA_PRODUCERS}) is really in the list"
}

log_test "test-renet-pipefail-grep-q"
test_detector_contract
test_renet_list_is_a_superset_of_consoles
test_declared_extras_are_real
echo ""
log_pass "all tests passed"
