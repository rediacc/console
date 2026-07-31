#!/bin/bash
# Unit test for the parallel gate runner: scripts/ci-runner/{run,pool,exec,report}.ts.
#
# WHAT THIS GUARDS. `npm run ci` used to be a 93-step `&&` string. Replacing it
# with a scheduler moves four properties out of the shell and into TypeScript,
# and every one of them is silent when it breaks:
#
#   1. A failing gate must make the run exit non-zero AND print its complete
#      captured output. A runner that swallowed either would report green over
#      a red tree, which is worse than the chain it replaced.
#   2. stdout and stderr are captured SEPARATELY. Merging them hides
#      progress-text-on-stdout and swallowed-output defects, a class this repo
#      has been bitten by; the house rule exists because of it.
#   3. A gate whose dependency FAILED is reported skipped, never passed, and
#      makes the run non-zero. "Skipped" silently becoming "ok" is exactly the
#      shape of rediacc/console#549.
#   4. mutex and jobs really constrain overlap. These cannot be verified by
#      reading; the pool has to be observed, so every concurrency case records
#      real start/end timestamps from the gate processes themselves.
#
# CONTROL-PROVEN. Cases 4 and 6 each carry an inverted leg: the same probe over
# the same fixture with the constraint removed must observe the OPPOSITE
# concurrency. Without that, a probe hardcoded to report 1 (or a runner that
# accidentally serialises everything) would pass the mutex case while proving
# nothing at all.
#
# Every case drives a SYNTHETIC manifest via CI_RUNNER_MANIFEST. The real
# manifest is not the subject here: what is under test is the scheduler, and a
# fixture is the only way to plant a failing gate without breaking the tree.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

TSX="$REPO_ROOT/node_modules/.bin/tsx"
RUNNER="$REPO_ROOT/scripts/ci-runner/run.ts"

[[ -x "$TSX" ]] || log_fail "tsx not installed at $TSX (run npm install)"
[[ -f "$RUNNER" ]] || log_fail "runner not found at $RUNNER"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

OUT="$WORK/stdout"
ERR="$WORK/stderr"
RC=0

# manifest <name> -- read a JSON fixture from stdin, substituting @WORK@ for the
# temp dir, and echo the path it was written to.
manifest() {
    local path="$WORK/$1.json"
    sed "s|@WORK@|$WORK|g" >"$path"
    echo "$path"
}

# run_ci <manifest> [args...] -- drive the real runner, capturing the two
# streams to separate files. Never merged: case 2 asserts on the split.
run_ci() {
    local mf="$1"
    shift
    RC=0
    (
        cd "$REPO_ROOT" || exit 1
        CI_RUNNER_MANIFEST="$mf" "$TSX" "$RUNNER" "$@"
    ) >"$OUT" 2>"$ERR" || RC=$?
}

# max_concurrency <logfile> -- replay S/E events in timestamp order and report
# the high-water mark. The gates write these lines themselves, so this measures
# real process overlap rather than the scheduler's own bookkeeping.
max_concurrency() {
    sort -k2,2n "$1" | awk '$1=="S"{c++; if(c>m)m=c} $1=="E"{c--} END{print m+0}'
}

# first_ts <marker> <logfile> -- the earliest timestamp for a marker, or empty.
# `|| true` is load-bearing: under `set -eo pipefail` a grep that matches
# nothing would abort the whole test with no diagnostic, whereas an empty
# result reaches the explicit check in case 5 and reports what went wrong.
first_ts() { grep "^$1 " "$2" | head -1 | cut -d' ' -f2 || true; }

# ---------------------------------------------------------------- case 1
test_all_pass_is_quiet() {
    local mf
    mf="$(
        manifest case1 <<'JSON'
[
  {"id":"g1","run":"echo one-output","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"g2","run":"echo two-output","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"g3","run":"echo three-output","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 2
    assert_exit_code 0 "$RC" "an all-pass manifest must exit 0"
    for id in g1 g2 g3; do
        assert_contains "$(cat "$OUT")" "  ok    $id" "every gate reports a line"
    done
    assert_not_contains "$(cat "$OUT")" "one-output" "a passing gate's output stays quiet"
    assert_contains "$(cat "$OUT")" "3 gates: 3 ok, 0 failed, 0 skipped" "summary counts every gate"
    log_pass "case 1: all-pass run is quiet, exits 0, one line per gate"
}

# ---------------------------------------------------------------- case 2
test_failure_prints_both_streams() {
    local mf out stdout_block stderr_block
    mf="$(
        manifest case2 <<'JSON'
[
  {"id":"ok-a","run":"echo ran-a >> @WORK@/case2.probe","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"boom","run":"echo BOOM-ON-STDOUT; echo BOOM-ON-STDERR >&2; exit 7","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"ok-b","run":"echo ran-b >> @WORK@/case2.probe","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 2
    out="$(cat "$OUT")"
    assert_exit_code 1 "$RC" "one failing gate must make the run exit 1"
    assert_contains "$out" "FAIL  boom" "the failing gate is named"
    assert_contains "$out" "exit 7" "the real exit code is reported"
    assert_contains "$out" "--- stdout ---" "captured stdout has its own header"
    assert_contains "$out" "--- stderr ---" "captured stderr has its own header"
    # Asserting only that both markers appear SOMEWHERE would pass on a runner
    # that merged the two streams, which is the defect the separation exists to
    # prevent. So each marker is required in its own block and forbidden in the
    # other.
    # The stderr slice stops at the blank line that closes the failure block:
    # the footer's "rerun all failures" line quotes the whole gate body, both
    # markers included, and would defeat a naive to-end-of-file slice.
    stdout_block="$(sed -n '/--- stdout ---/,/--- stderr ---/p' "$OUT")"
    stderr_block="$(awk '/--- stderr ---/{f=1;next} f&&/^$/{exit} f' "$OUT")"
    assert_contains "$stdout_block" "BOOM-ON-STDOUT" "captured stdout is printed under the stdout header"
    assert_not_contains "$stdout_block" "BOOM-ON-STDERR" "stderr must not leak into the stdout block"
    assert_contains "$stderr_block" "BOOM-ON-STDERR" "captured stderr is printed under the stderr header"
    assert_not_contains "$stderr_block" "BOOM-ON-STDOUT" "stdout must not leak into the stderr block"
    assert_contains "$out" "rerun: echo BOOM-ON-STDOUT" "the rerun command is printed"
    # keep-going is the default for the same reason CI puts !cancelled() on
    # every quality step: one run has to surface every failure.
    assert_contains "$(cat "$WORK/case2.probe")" "ran-a" "gates before the failure still ran"
    assert_contains "$(cat "$WORK/case2.probe")" "ran-b" "gates after the failure still ran"
    log_pass "case 2: a failure prints both streams separately and the rest still runs"
}

# ---------------------------------------------------------------- case 3
test_fail_fast_stops_the_run() {
    local mf
    mf="$(
        manifest case3 <<'JSON'
[
  {"id":"boom","run":"exit 1","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"after-1","run":"echo ran >> @WORK@/case3.probe","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"after-2","run":"echo ran >> @WORK@/case3.probe","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 1 --fail-fast
    assert_exit_code 1 "$RC" "--fail-fast still exits 1"
    assert_contains "$(cat "$OUT")" "not run (--fail-fast)" "the remaining gates say why they did not run"
    [[ -f "$WORK/case3.probe" ]] && log_fail "--fail-fast let a later gate execute"
    log_pass "case 3: --fail-fast stops the run and the remaining gates never execute"
}

# ---------------------------------------------------------------- case 4
test_mutex_serialises() {
    local mf conc
    mf="$(
        manifest case4 <<'JSON'
[
  {"id":"m1","run":"echo S $(date +%s%N) >> @WORK@/case4.log; sleep 0.4; echo E $(date +%s%N) >> @WORK@/case4.log","gate":true,"mutex":["shared"],"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"m2","run":"echo S $(date +%s%N) >> @WORK@/case4.log; sleep 0.4; echo E $(date +%s%N) >> @WORK@/case4.log","gate":true,"mutex":["shared"],"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 4
    assert_exit_code 0 "$RC" "the mutex fixture passes"
    conc="$(max_concurrency "$WORK/case4.log")"
    assert_eq "$conc" "1" "two gates sharing a mutex group must never overlap"

    # CONTROL: the same probe, the same two gates, no mutex. If this does not
    # observe an overlap the assertion above proves nothing.
    mf="$(
        manifest case4b <<'JSON'
[
  {"id":"f1","run":"echo S $(date +%s%N) >> @WORK@/case4b.log; sleep 0.4; echo E $(date +%s%N) >> @WORK@/case4b.log","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"f2","run":"echo S $(date +%s%N) >> @WORK@/case4b.log; sleep 0.4; echo E $(date +%s%N) >> @WORK@/case4b.log","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 4
    conc="$(max_concurrency "$WORK/case4b.log")"
    assert_eq "$conc" "2" "CONTROL: without a mutex the same two gates do overlap"
    log_pass "case 4: mutex serialises, and the control proves the probe sees overlap"
}

# ---------------------------------------------------------------- case 5
test_needs_orders_and_skips() {
    local mf out prep_end user_start
    mf="$(
        manifest case5 <<'JSON'
[
  {"id":"prep","run":"echo S $(date +%s%N) >> @WORK@/case5.log; sleep 0.3; echo E $(date +%s%N) >> @WORK@/case5.log","gate":false,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"user","run":"echo U $(date +%s%N) >> @WORK@/case5.log","gate":true,"needs":["prep"],"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"badprep","run":"echo prep-failed >&2; exit 2","gate":false,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"victim","run":"echo victim-ran >> @WORK@/case5.probe","gate":true,"needs":["badprep"],"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 4
    out="$(cat "$OUT")"
    assert_exit_code 1 "$RC" "a skipped gate makes the run non-zero"
    prep_end="$(first_ts E "$WORK/case5.log")"
    user_start="$(first_ts U "$WORK/case5.log")"
    [[ -n "$prep_end" && -n "$user_start" ]] || log_fail "case 5 probe did not record both timestamps"
    ((user_start > prep_end)) || log_fail "a dependent started before its dependency finished"
    assert_contains "$out" "SKIP  victim" "a dependent of a failed gate is reported skipped"
    assert_contains "$out" "needs badprep" "the skip names the dependency that failed"
    assert_not_contains "$out" "ok    victim" "a skipped gate is never reported as passed"
    [[ -f "$WORK/case5.probe" ]] && log_fail "a dependent of a failed gate executed anyway"
    log_pass "case 5: needs orders execution, and a failed dependency skips rather than passes"
}

# ---------------------------------------------------------------- case 6
test_jobs_bounds_concurrency() {
    local mf conc
    mf="$(
        manifest case6 <<'JSON'
[
  {"id":"j1","run":"echo S $(date +%s%N) >> @WORK@/case6.log; sleep 0.3; echo E $(date +%s%N) >> @WORK@/case6.log","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"j2","run":"echo S $(date +%s%N) >> @WORK@/case6.log; sleep 0.3; echo E $(date +%s%N) >> @WORK@/case6.log","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"j3","run":"echo S $(date +%s%N) >> @WORK@/case6.log; sleep 0.3; echo E $(date +%s%N) >> @WORK@/case6.log","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"j4","run":"echo S $(date +%s%N) >> @WORK@/case6.log; sleep 0.3; echo E $(date +%s%N) >> @WORK@/case6.log","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"j5","run":"echo S $(date +%s%N) >> @WORK@/case6.log; sleep 0.3; echo E $(date +%s%N) >> @WORK@/case6.log","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"j6","run":"echo S $(date +%s%N) >> @WORK@/case6.log; sleep 0.3; echo E $(date +%s%N) >> @WORK@/case6.log","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 2
    assert_exit_code 0 "$RC" "the concurrency fixture passes"
    conc="$(max_concurrency "$WORK/case6.log")"
    assert_eq "$conc" "2" "--jobs 2 admits exactly two gates at a time"

    # CONTROL: the same six gates at --jobs 5 must exceed 2, or the assertion
    # above would also pass on a runner that serialises everything.
    rm -f "$WORK/case6.log"
    run_ci "$mf" --jobs 5
    conc="$(max_concurrency "$WORK/case6.log")"
    ((conc > 2)) || log_fail "CONTROL: --jobs 5 observed only $conc concurrent gates"
    log_pass "case 6: --jobs bounds concurrency exactly, proven against a wider budget"
}

# ---------------------------------------------------------------- case 7
test_empty_manifest_refuses() {
    local mf
    mf="$(
        manifest case7 <<'JSON'
[]
JSON
    )"
    run_ci "$mf"
    [[ "$RC" -ne 0 ]] || log_fail "an empty manifest must not exit 0"
    assert_contains "$(cat "$ERR")" "Refusing to run" "the diagnostic uses the house refusal wording"
    log_pass "case 7: an empty manifest refuses to run and exits non-zero"
}

# ---------------------------------------------------------------- case 8
test_missing_duration_cache() {
    local mf cache
    cache="$WORK/no/such/dir/gate-durations.json"
    mf="$(
        manifest case8 <<'JSON'
[
  {"id":"c1","run":"true","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"c2","run":"true","gate":true,"weight":2,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    RC=0
    (
        cd "$REPO_ROOT" || exit 1
        CI_RUNNER_MANIFEST="$mf" CI_RUNNER_CACHE="$cache" "$TSX" "$RUNNER" --jobs 2
    ) >"$OUT" 2>"$ERR" || RC=$?
    assert_exit_code 0 "$RC" "a missing duration cache must not fail the run"
    [[ -f "$cache" ]] || log_fail "the run did not write the duration cache it was pointed at"
    grep -q '"c1"' "$cache" || log_fail "the duration cache recorded no timing for c1"
    log_pass "case 8: a missing duration cache is created, not fatal"
}

# ---------------------------------------------------------------- case 9
test_summary_is_deterministic() {
    local mf first_summary second_summary first_rc
    mf="$(
        manifest case9 <<'JSON'
[
  {"id":"d1","run":"true","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"d2","run":"exit 1","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"d3","run":"sleep 0.2","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"d4","run":"true","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"d5","run":"exit 1","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"d6","run":"true","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 4
    first_rc="$RC"
    first_summary="$(sed -n '/^FAILED:/,/^====/p' "$OUT")"
    run_ci "$mf" --jobs 4
    second_summary="$(sed -n '/^FAILED:/,/^====/p' "$OUT")"
    assert_exit_code "$first_rc" "$RC" "the exit code is stable across runs"
    assert_eq "$second_summary" "$first_summary" "the failure summary ordering is stable across runs"
    assert_contains "$first_summary" "d2" "the summary names the failing gates"
    log_pass "case 9: exit code and summary ordering are stable across runs"
}

# ---------------------------------------------------------------- case 10
test_json_matches_what_was_printed() {
    local mf
    mf="$(
        manifest case10 <<'JSON'
[
  {"id":"jok","run":"echo fine","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"jbad","run":"echo JSON-STDOUT-MARKER; echo JSON-STDERR-MARKER >&2; exit 4","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    # Under --json the machine document owns stdout and the human stream moves
    # to stderr, so an agent can consume one and tail the other.
    run_ci "$mf" --jobs 2 --json
    assert_exit_code 1 "$RC" "--json does not change the exit code"
    node -e '
const fs = require("fs");
const doc = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
const bad = doc.gates.find((g) => g.id === "jbad");
const fail = (m) => { console.error("FAIL: " + m); process.exit(1); };
if (doc.exitCode !== 1) fail("json exitCode is " + doc.exitCode);
if (doc.partial !== false) fail("a full run must not report partial:true");
if (!bad) fail("the failing gate is missing from the json");
if (!bad.stdout.includes("JSON-STDOUT-MARKER")) fail("json stdout does not carry the captured stdout");
if (!bad.stderr.includes("JSON-STDERR-MARKER")) fail("json stderr does not carry the captured stderr");
if (bad.status !== "fail") fail("json status is " + bad.status);
if (bad.rerun !== "echo JSON-STDOUT-MARKER; echo JSON-STDERR-MARKER >&2; exit 4") fail("json rerun is wrong");
' "$OUT" || log_fail "--json document did not match the captured output"
    # The same bytes must appear in the human stream, or the two views disagree.
    assert_contains "$(cat "$ERR")" "JSON-STDOUT-MARKER" "the human stream carries the captured stdout"
    assert_contains "$(cat "$ERR")" "JSON-STDERR-MARKER" "the human stream carries the captured stderr"
    log_pass "case 10: --json parses and agrees with the printed output"
}

# ---------------------------------------------------------------- case 11
test_selftest_is_wired_into_the_npm_key() {
    local ci_key
    # The control has to run on every real invocation. A --selftest that sits
    # behind a flag nothing passes is the exact failure check-gate-reachability
    # recorded for check-i18n-cross-locale, which shipped broken for months.
    ci_key="$(node -e 'process.stdout.write(require("./package.json").scripts.ci)' 2>/dev/null)"
    assert_contains "$ci_key" "--selftest" "the ci npm key must invoke the runner's control"
    RC=0
    (cd "$REPO_ROOT" && "$TSX" "$RUNNER" --selftest) >"$OUT" 2>"$ERR" || RC=$?
    assert_exit_code 0 "$RC" "--selftest passes on a healthy runner"
    assert_contains "$(cat "$OUT")" "selftest ok" "--selftest reports its assertion count"
    log_pass "case 11: the anti-vacuity control is wired into the ci npm key and fires"
}

# ---------------------------------------------------------------- case 12
test_missing_tool_fails_loudly() {
    local mf out
    # A gate whose tool does not resolve must FAIL, never pass quietly. This is
    # not hypothetical: during this work an `npx biome` in a directory with no
    # node_modules link exited 0 on a deliberately misformatted file, and the
    # green came from a tool that never really ran. A runner that swallowed a
    # 127 would turn that class of accident into a green CI report.
    mf="$(
        manifest case12 <<'JSON'
[
  {"id":"missing-tool","run":"definitely-not-a-real-command --check","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}},
  {"id":"real","run":"true","gate":true,"leaves":[],"ci":{"kind":"local-only","blocker":"BLOCKER: synthetic fixture"}}
]
JSON
    )"
    run_ci "$mf" --jobs 2
    out="$(cat "$OUT")"
    assert_exit_code 1 "$RC" "a gate whose command does not exist must fail the run"
    assert_contains "$out" "FAIL  missing-tool" "the unresolvable gate is named"
    assert_contains "$out" "exit 127" "the shell's command-not-found status is reported"
    assert_contains "$out" "command not found" "the shell's diagnostic reaches the operator"
    assert_contains "$out" "  ok    real" "CONTROL: a resolvable gate in the same run still passes"
    log_pass "case 12: a gate whose tool does not resolve fails loudly, never silently"
}

cd "$REPO_ROOT"
test_all_pass_is_quiet
test_failure_prints_both_streams
test_fail_fast_stops_the_run
test_mutex_serialises
test_needs_orders_and_skips
test_jobs_bounds_concurrency
test_empty_manifest_refuses
test_missing_duration_cache
test_summary_is_deterministic
test_json_matches_what_was_printed
test_selftest_is_wired_into_the_npm_key
test_missing_tool_fails_loudly

echo ""
echo "All ci-runner tests passed"
