#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: node
# lane: quality-security
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# why: Every shrink-only baseline in this repo must enforce shrink-only on the WRITE path
# ---- end gate ----

# Every shrink-only baseline in this repo must enforce shrink-only on the WRITE path.
#
# WHY THIS EXISTS. Seven gates here freeze a backlog and describe it as shrink-only. All
# seven enforced that on the READ path only; `--write-baseline` was an unconditional reseed
# in every one. The difference is not academic:
#
#   as enforced:  the TOTAL cannot grow without someone noticing.
#   as promised:  the SET can only lose members.
#
# A reseed that drains thirty findings and absorbs one satisfies the first, violates the
# second, and prints a SMALLER number while doing it. On 2026-08-20 the guard was added to
# scripts/gates/check-em-dash-surfaces.ts and refused, on its first real run, a reseed that would
# have enshrined two em dashes a background naturalization job had introduced minutes
# earlier. That is the failure this file exists to keep closed.
#
# WHAT IS ASSERTED, and why it is a STRUCTURAL check rather than a behavioural sweep. Driving
# every gate's `--write-baseline` for real would mean rewriting live suppression files, which
# is precisely the operation a session must not perform casually; four of the gates do not
# even accept a `--baseline` override to redirect the write. So the structural half asserts
# that every CLI offering the flag consumes the shared guard, which is what actually stops an
# eighth gate from being written with the old unconditional shape. The behavioural half then
# proves the guard really refuses, end to end, on the one gate that CAN be pointed at a copy.
#
# ANTI-VACUITY. Scanning zero files is a FAILURE, never a pass, and the control below plants
# an unguarded reseed and requires detection. A structural grep that silently matches nothing
# is the exact shape of gate this repo keeps getting burned by.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$REPO_ROOT"

GUARD='scripts/lib/shrink-only-baseline.ts'
GUARD_IMPORT='shrink-only-baseline'

# Files that name the flag but own no CLI branch of their own. Exempt BY NAME, with the
# reason here in the code, and PRINTED on every run so the debt cannot go quiet.
#
#   scripts/lib/shrink-only-baseline.ts  IS the guard; it cannot import itself.
EXEMPT=(
    "scripts/lib/shrink-only-baseline.ts"
)

# The guard reaches a file either DIRECTLY or through the P7 choke point.
#
# packages/www/scripts/lib/p7-backlog.js::writeBacklog now performs the composition check
# itself and exits non-zero on refusal, which covers its four consumers without any of them
# importing the guard by name. So a file that imports p7-backlog IS guarded, and asserting
# otherwise would flag three validators that are in fact protected.
#
# ONE HOP, deliberately, matching the precedent in check-gate-id-convention.sh: a two-hop
# chain would escape this. No such chain exists today. If one appears, plant it as a control
# and widen the resolver THEN, rather than speculatively complicating it now.
GUARDED_VIA=(
    "shrink-only-baseline"
    "p7-backlog"
)

# Known-unguarded CLIs. This list may only SHRINK. A new offender is not added here, it is
# fixed: the whole point is that a new gate must not be born with the old shape.
#
# EMPTY as of 2026-08-20: the P7 choke point closed the last three
# (validate-content-accuracy.js, validate-docs-cli-usage.js, validate-tutorial-cast-output.js).
PENDING=()

is_in() {
    local needle="$1"
    shift
    local x
    for x in "$@"; do [[ "$x" == "$needle" ]] && return 0; done
    return 1
}

# Every file that offers the flag, in EVERY language that can hold a baseline writer.
#
# TWO BLIND SPOTS CLOSED, 2026-09-08 (U3). This enumerator used to read
#   grep -rl -e "--write-baseline" --include=*.ts --include=*.js scripts/ packages/www/scripts/
# which excluded `.py` AND excluded the whole `.ci/` tree. Both halves matter now: ruling 7
# moves gates into Python under `.ci`, and the first Python shrink-only baseline landed on
# 2026-09-07 outside both filters -- `.ci/scripts/quality/check_language_policy.py`, freezing
# 521 paths. THE HOLE WAS SELF-DECLARED: that gate's own comment says the port "names the
# resulting coverage gap in gate-test:shrink-only-composition out loud rather than leaving it
# to be discovered", and it was still open a day later. The green here was never false, just
# scoped to a language and two directories the programme is migrating away from.
# Measured on this tree: 20 file(s) scanned before, 21 after, of which 1 is the Python writer
# that was invisible. No `.ts` or `.js` offerer lives under `.ci/` today, so the root half of
# the widening changes no count -- it removes a way for the count to be wrong later.
#
# ENUMERATED FROM `git ls-files` RATHER THAN FROM A ROOT LIST, which is what makes the root
# half permanent: a directory created next month is in the corpus the day it exists. The
# extension filter is a git PATHSPEC rather than a grep, so a filename can never be read as
# an option.
#
# NOTE THE `-e`. Writing this as `grep -l -- "--write-baseline" ...` looks correct and is
# not: grep here is ugrep, and after the `--` separator it reads the remaining arguments as
# FILENAMES. It warns to stderr, exits 2, and still prints a plausible-looking file list, so
# with stderr suppressed the bug is invisible until `set -o pipefail` turns it into an
# unexplained exit. `-e` passes a pattern that begins with a dash without closing the option
# list.
all_offerers() {
    git ls-files --cached --others --exclude-standard -z -- '*.ts' '*.js' '*.py' |
        xargs -0 -r grep -l -e "--write-baseline" 2>/dev/null | sort
}

# `|| true` on both: grep exits 1 on no match, and under `set -o pipefail` an empty half
# would abort the run instead of being REPORTED as empty, which is the opposite of the
# anti-vacuity rule below. Emptiness is a verdict here, not a crash.
offerers() {
    all_offerers | grep -E '\.(ts|js)$' || true
}

offerers_py() {
    all_offerers | grep -E '\.py$' || true
}

# THE PYTHON HALF HAS NO SHARED GUARD TO IMPORT, and pretending otherwise would make this
# check unsatisfiable. `scripts/lib/shrink-only-baseline.ts` is TypeScript with no Python
# binding, so `check_language_policy.py` carries a faithful PORT of its decision half
# (`baseline_additions`, `write_verdict`, `render_refusal`) and says so in its own comment.
# Until a shared Python guard exists, CONSUMING THE PORT is the contract, and it is stated
# here as one rather than leaving the language uncovered. Three conditions, because any one
# alone is satisfiable while the write path stays unconditional: the file must DEFINE or
# IMPORT `write_verdict`, must CALL it somewhere other than its own definition, and must
# compute `baseline_additions`. A file that only names them in a comment is not guarded,
# which the mention control proves.
#
# `-P`, not `-E`: ugrep returns SILENT FALSE ZEROS when `^` is alternated, and the first
# pattern below alternates exactly that way.
py_reaches_guard() {
    local f="$1"
    grep -qP '^(def write_verdict\(|from [\w.]+ import .*\bwrite_verdict\b)' "$f" || return 1
    grep -qP '(?<!def )\bwrite_verdict\(' "$f" || return 1
    grep -qP '\bbaseline_additions\(' "$f" || return 1
    return 0
}

unguarded_py() {
    local f
    for f in $(offerers_py); do
        py_reaches_guard "$f" || echo "$f"
    done
}

# Files that offer the flag, are not exempt, and reach the guard by no route.
unguarded() {
    local f route hit
    for f in $(offerers); do
        is_in "$f" "${EXEMPT[@]}" && continue
        hit=0
        for route in "${GUARDED_VIA[@]}"; do
            # An IMPORT, not a mention. `grep -q p7-backlog` would count a file that merely
            # names the module in a comment as guarded, which is how an over-permissive
            # matcher turns a gate into decoration. Anchored on the `from '...'` specifier.
            grep -qE "from '[^']*${route}" "$f" && hit=1 && break
        done
        [[ "$hit" -eq 1 ]] || echo "$f"
    done
}

test_guard_module_exists() {
    [[ -f "$GUARD" ]] || log_fail "the shared guard is missing at $GUARD"
    log_pass "the shared composition guard exists at $GUARD"
}

# EACH CORPUS IS REFUSED SEPARATELY. A populated half does not excuse an empty one: with a
# single summed count, the `.py` half could go to zero -- the enumerator broken, the pathspec
# mistyped, the tree reorganised -- and 20 TypeScript offerers would carry the total straight
# past the floor while the language this programme is migrating TO went unchecked. That is
# the exact shape of the blind spot U3 closed, so the fix must not be re-openable by silence.
test_scan_is_not_vacuous() {
    local n m
    n="$(offerers | wc -l)"
    m="$(offerers_py | wc -l)"
    if [[ "$n" -lt 8 ]]; then
        log_fail "only $n TypeScript/JavaScript file(s) offer --write-baseline; the scan is not seeing the tree, so its green would mean nothing"
    fi
    if [[ "$m" -eq 0 ]]; then
        log_fail "ZERO Python file(s) offer --write-baseline. One did on 2026-09-07 (check_language_policy.py, 521 paths). Zero means the enumerator stopped seeing .py, not that the debt went away -- and this half of the gate would be asserting nothing."
    fi
    log_pass "scan sees $n ts/js and $m python file(s) offering --write-baseline"
}

test_every_gate_consumes_the_guard() {
    local bad found=0
    bad="$(unguarded)"
    local f
    for f in $bad; do
        if is_in "$f" "${PENDING[@]}"; then continue; fi
        log_error "  $f offers --write-baseline and does NOT consume $GUARD"
        found=1
    done
    if [[ "$found" -eq 1 ]]; then
        log_error ""
        log_error "  A shrink-only baseline that reseeds unconditionally can drain thirty findings,"
        log_error "  absorb one brand new one, and print a smaller number while doing it."
        log_error "  Import { writeBaselineVerdict, renderRefusal } from '$GUARD' and refuse"
        log_error "  before writing. Do NOT add the file to PENDING in this gate."
        log_fail "at least one baseline writer bypasses the composition guard"
    fi
    local guarded
    guarded="$(offerers | wc -l)"
    log_pass "every non-exempt baseline writer consumes the guard ($guarded offerer(s) scanned)"
}

# The PENDING set may only shrink, and it is EMPTY. Kept as a live check rather than
# deleted, because the next unguarded writer must land in the failure above, never here.
test_pending_set_only_shrinks() {
    if [[ "${#PENDING[@]}" -eq 0 ]]; then
        log_pass "no known-unguarded baseline writers remain (PENDING is empty)"
        return
    fi
    local f
    for f in "${PENDING[@]}"; do
        [[ -f "$f" ]] || log_fail "PENDING names $f, which no longer exists; remove the line"
        local route hit=0
        for route in "${GUARDED_VIA[@]}"; do
            grep -qE "from '[^']*${route}" "$f" && hit=1 && break
        done
        [[ "$hit" -eq 1 ]] && log_fail "$f now reaches the guard; DELETE it from PENDING"
        # Visible every run, on purpose. A quiet exemption is how a gate stops meaning its name.
        log_info "STILL UNGUARDED: $f"
    done
    log_pass "the unguarded set has not grown (${#PENDING[@]} known)"
}

# The Python writers, against the ported guard. Separate from the TypeScript check because
# the routes are different, not because the rule is: one imports a shared module, the other
# consumes a port of it, and both must refuse a reseed that would ABSORB a new finding.
test_every_python_writer_consumes_the_guard() {
    local bad found=0 f
    bad="$(unguarded_py)"
    for f in $bad; do
        log_error "  $f offers --write-baseline and consumes neither a shared guard nor the ported one"
        found=1
    done
    if [[ "$found" -eq 1 ]]; then
        log_error ""
        log_error "  A shrink-only baseline that reseeds unconditionally can drain thirty findings,"
        log_error "  absorb one brand new one, and print a smaller number while doing it."
        log_error "  Port the decision half of $GUARD the way check_language_policy.py did:"
        log_error "  baseline_additions() for the diff, write_verdict() before the write."
        log_fail "at least one Python baseline writer bypasses the composition guard"
    fi
    local n
    n="$(offerers_py | wc -l)"
    log_pass "every Python baseline writer consumes the guard ($n offerer(s) scanned)"
    # VISIBLE EVERY RUN. There is no shared Python guard yet, so each writer carries its own
    # copy of the decision half. That is real duplication and it is stated rather than left
    # to be discovered a second time.
    for f in $(offerers_py); do
        log_info "PORTED GUARD (no shared Python module exists yet): $f"
    done
}

# CONTROL. Plant an unguarded PYTHON writer where the OLD enumerator could not look -- under
# `.ci/`, with a `.py` suffix -- and require detection. This is the control that proves the
# widening is real: run against the previous enumerator it detects nothing at all, because
# neither the extension nor the directory was in scope.
test_control_unguarded_python_reseed_is_detected() {
    local probe=".ci/scripts/quality/zz_composition_control_probe.py"
    cat >"$probe" <<'EOF'
#!/usr/bin/env python3
"""Temporary control fixture. Offers --write-baseline with no composition guard."""

import sys

if "--write-baseline" in sys.argv:
    print("unconditional reseed")
EOF
    local seen=0 detected=0
    [ -n "$(offerers_py | grep -x "$probe")" ] && seen=1
    [ -n "$(unguarded_py | grep -x "$probe")" ] && detected=1
    rm -f "$probe"
    [[ -f "$probe" ]] && log_fail "python control probe was not removed"
    [[ "$seen" -eq 1 ]] || log_fail "CONTROL FAILED: the enumerator did not even SEE a .py offerer under .ci/, so the widening is not in effect"
    [[ "$detected" -eq 1 ]] || log_fail "CONTROL FAILED: an unguarded Python reseed was NOT detected, so this half cannot fail"
    log_pass "CONTROL: a planted unguarded Python reseed under .ci/ is seen and detected"
}

# CONTROL, the other direction. A Python file that only MENTIONS the ported guard in prose
# must NOT count as guarded, and one that genuinely consumes it MUST. Both in one probe file
# so the two answers come from the same scanner on the same run.
test_control_python_mention_is_not_a_guard() {
    local probe=".ci/scripts/quality/zz_composition_mention_probe.py"
    cat >"$probe" <<'EOF'
#!/usr/bin/env python3
"""Temporary control fixture. Names write_verdict( and baseline_additions( in PROSE only."""

import sys

# write_verdict( and baseline_additions( appear here and nowhere else.
if "--write-baseline" in sys.argv:
    print("unconditional reseed")
EOF
    local mentioned=0
    [ -n "$(unguarded_py | grep -x "$probe")" ] && mentioned=1
    cat >"$probe" <<'EOF'
#!/usr/bin/env python3
"""Temporary control fixture. Actually consumes the ported decision half."""

import sys


def baseline_additions(old, new):
    known = set(old)
    return [x for x in new if x not in known]


def write_verdict(*, baseline_exists, first_seed, additions):
    if not baseline_exists and not first_seed:
        return "missing-baseline"
    return "would-grow" if additions else None


if "--write-baseline" in sys.argv:
    added = baseline_additions([], [])
    if write_verdict(baseline_exists=True, first_seed=False, additions=added):
        sys.exit(1)
EOF
    local guarded=1
    [ -n "$(unguarded_py | grep -x "$probe")" ] && guarded=0
    rm -f "$probe"
    [[ -f "$probe" ]] && log_fail "python mention probe was not removed"
    [[ "$mentioned" -eq 1 ]] || log_fail "CONTROL FAILED: a prose mention of write_verdict was accepted as a guard route"
    [[ "$guarded" -eq 1 ]] || log_fail "CONTROL FAILED: a writer that really consumes the ported guard was reported unguarded, so this check flags correct work"
    log_pass "CONTROL: naming the ported guard in a comment does not count, consuming it does"
}

# CONTROL. Plant a file with the OLD unconditional shape and require detection. Without
# this, `unguarded()` returning nothing proves nothing about the scanner.
test_control_unguarded_reseed_is_detected() {
    local probe="scripts/zz-composition-control-probe.ts"
    cat >"$probe" <<'EOF'
// Temporary control fixture. Offers --write-baseline with no composition guard.
if (process.argv.includes('--write-baseline')) {
  console.log('unconditional reseed');
}
EOF
    local detected=0
    [ -n "$(unguarded | grep -x "$probe")" ] && detected=1
    rm -f "$probe"
    [[ -f "$probe" ]] && log_fail "control probe was not removed"
    [[ "$detected" -eq 1 ]] || log_fail "CONTROL FAILED: an unguarded reseed was NOT detected, so this gate cannot fail"
    log_pass "CONTROL: a planted unguarded reseed is detected"
}

# CONTROL. A file that only MENTIONS the choke point in prose must NOT count as guarded.
# Without this, the transitive route above is a substring match masquerading as a check.
test_control_mention_is_not_an_import() {
    local probe="scripts/zz-composition-mention-probe.ts"
    cat >"$probe" <<'EOF'
// Temporary control fixture. Mentions p7-backlog and shrink-only-baseline in PROSE only,
// imports neither, and offers --write-baseline with no guard at all.
if (process.argv.includes('--write-baseline')) {
  console.log('unconditional reseed');
}
EOF
    local detected=0
    [ -n "$(unguarded | grep -x "$probe")" ] && detected=1
    rm -f "$probe"
    [[ -f "$probe" ]] && log_fail "mention probe was not removed"
    [[ "$detected" -eq 1 ]] || log_fail "CONTROL FAILED: a prose mention was accepted as a guard route"
    log_pass "CONTROL: naming the guard in a comment does not count as consuming it"
}

# BEHAVIOURAL. The one gate that accepts --baseline, so the write can be aimed at a copy and
# the live suppression file is never touched. Proven both directions.
test_refusal_end_to_end() {
    local gate="scripts/gates/check-em-dash-surfaces.ts"
    local live="scripts/data/em-dash-surfaces-baseline.json"
    [[ -f "$live" ]] || log_fail "$live is missing"

    local before after tmp rc
    before="$(md5sum "$live" | cut -d' ' -f1)"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' RETURN

    # Snapshot the live id set through the gate itself, so the fixture cannot drift out of
    # date the way a hand-written id list does.
    npx tsx "$gate" --write-baseline --baseline "$tmp/live.json" --first-seed --skip-control \
        >/dev/null 2>&1 || log_fail "could not snapshot the live id set"

    # GROWTH: drop one id from the OLD copy so a real live finding reads as new.
    node -e "
      const fs=require('fs');
      const a=JSON.parse(fs.readFileSync('$tmp/live.json','utf8'));
      fs.writeFileSync('$tmp/grow.json', JSON.stringify(a.slice(1),null,2)+'\n');
    "
    set +e
    npx tsx "$gate" --write-baseline --baseline "$tmp/grow.json" --skip-control >/dev/null 2>&1
    rc=$?
    set -e
    assert_eq "$rc" "1" "a reseed that would GAIN an id exits non-zero"

    # SHRINK: old copy is a strict superset, so the write is a genuine drain.
    node -e "
      const fs=require('fs');
      const a=JSON.parse(fs.readFileSync('$tmp/live.json','utf8'));
      fs.writeFileSync('$tmp/shrink.json', JSON.stringify([...a,'zz/synthetic.json:already.fixed'].sort(),null,2)+'\n');
    "
    set +e
    npx tsx "$gate" --write-baseline --baseline "$tmp/shrink.json" --skip-control >/dev/null 2>&1
    rc=$?
    set -e
    assert_eq "$rc" "0" "a genuine shrink is still allowed"

    # MISSING: deleting the baseline must not be a way to switch the rule off.
    set +e
    npx tsx "$gate" --write-baseline --baseline "$tmp/absent.json" --skip-control >/dev/null 2>&1
    rc=$?
    set -e
    assert_eq "$rc" "1" "a missing baseline is refused without --first-seed"
    [[ -f "$tmp/absent.json" ]] && log_fail "the refused run created the baseline anyway"

    after="$(md5sum "$live" | cut -d' ' -f1)"
    assert_eq "$after" "$before" "the LIVE baseline was never rewritten by this test"
    log_pass "refusal proven end to end; live baseline byte-identical"
}

log_test "test-shrink-only-composition"
test_guard_module_exists
test_scan_is_not_vacuous
test_every_gate_consumes_the_guard
test_every_python_writer_consumes_the_guard
test_pending_set_only_shrinks
test_control_unguarded_reseed_is_detected
test_control_mention_is_not_an_import
test_control_unguarded_python_reseed_is_detected
test_control_python_mention_is_not_a_guard
test_refusal_end_to_end
echo ""
log_pass "all tests passed"
