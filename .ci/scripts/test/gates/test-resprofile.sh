#!/bin/bash
# Drives .ci/scripts/quality/check_resprofile.py through its three states and a mutant.
#
# WHY. The gate judges process-tree captures nobody has looked at by hand, so its
# own honesty is the whole question: pristine must WARN not pass silently, a seeded
# baseline must let a planted structural defect FIRE, and the dilation control must
# refuse a predicate that reads wall-clock. The mutant is the control on the
# control: strip the wall-only scaling out of dilate() and the gate must go red on
# its own captures, or the control was decoration.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"
GATE="$REPO_ROOT/.ci/scripts/quality/check_resprofile.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# A fixture repo root: the gate resolves everything under RESPROFILE_ROOT, so the
# real baseline is never touched.
mkdir -p "$WORK/root/.ci/config" "$WORK/root/.ci/cache" "$WORK/root/.claude/hooks/stop" "$WORK/caps"
cp "$REPO_ROOT"/.claude/hooks/stop/wl_profile.py "$REPO_ROOT"/.claude/hooks/stop/wl_ressample.py "$WORK/root/.claude/hooks/stop/"
cp "$GATE" "$WORK/root/.ci/scripts_gate.py" 2>/dev/null || true

# Plant an E6 capture: a live parent with 4 zombies across consecutive samples.
python3 - "$WORK/caps/zombies.jsonl" <<'PY'
import json, sys
procs = lambda: [{"pid": 1, "ppid": 0, "comm": "bash", "state": "S", "wchan": "do_wait", "utime": 1, "stime": 0, "hwm_kb": 4000, "wfd": [], "depth": 0}] + \
    [{"pid": 10 + i, "ppid": 1, "comm": "true", "state": "Z", "wchan": None, "utime": 0, "stime": 0, "hwm_kb": 0, "wfd": [], "depth": 1} for i in range(4)]
lines = [json.dumps({"v": 1, "k": "S", "run": "r", "t_ms": t, "p": procs()}) for t in (0, 500, 1000, 1500)]
lines.append(json.dumps({"v": 1, "k": "RUN", "run": "r", "root_pid": 1, "interval_ms": 500, "samples_n": 4, "expected_n": 4, "wall_ms": 2000, "unsampled": False}))
open(sys.argv[1], "w").write("\n".join(lines) + "\n")
PY
# And enough quiet captures that the class is admissible once seeded.
# 80, not 24: admission is a one-sided 95% Wilson bound on F/J <= 0.05, and at F=0
# that needs J of roughly 60 before the bound drops under the line (0/24 bounds at
# ~0.10). The first draft seeded 24 and the gate CORRECTLY kept E6 report-only --
# the fixture was under-powered, not the gate. "J >= 20" is necessary, not sufficient.
for i in $(seq 1 80); do
    python3 - "$WORK/caps/quiet$i.jsonl" <<'PY'
import json, sys
p = [{"pid": 1, "ppid": 0, "comm": "bash", "state": "R", "wchan": None, "utime": 5, "stime": 0, "hwm_kb": 3000, "wfd": [], "depth": 0}]
lines = [json.dumps({"v": 1, "k": "S", "run": "q", "t_ms": t, "p": p}) for t in (0, 500, 1000)]
lines.append(json.dumps({"v": 1, "k": "RUN", "run": "q", "root_pid": 1, "interval_ms": 500, "samples_n": 3, "expected_n": 3, "wall_ms": 1500, "unsampled": False}))
open(sys.argv[1], "w").write("\n".join(lines) + "\n")
PY
done

run_gate() { (cd "$REPO_ROOT" && RESPROFILE_ROOT="$WORK/root" python3 "$GATE" "$@" 2>&1); }

test_pristine_warns_not_passes_silently() {
    local rc=0 out
    out="$(run_gate --captures "$WORK/caps")" || rc=$?
    assert_exit_code 0 "$rc" "pristine (no baseline) exits 0"
    assert_contains "$out" "pristine" "and SAYS it is pristine"
    assert_contains "$out" "E6" "and still names the planted finding as report"
    log_pass "pristine warns and names findings without enforcing"
}

test_seeded_then_enforces() {
    local rc=0 out
    # Seed from a QUIET corpus so the class becomes admissible with F=0.
    mkdir -p "$WORK/quiet"
    cp "$WORK"/caps/quiet*.jsonl "$WORK/quiet/"
    out="$(run_gate --seed "$WORK/quiet")" || rc=$?
    assert_exit_code 0 "$rc" "seeding from a quiet corpus succeeds"
    test -f "$WORK/root/.ci/config/resprofile-baseline.json" || {
        log_fail "no baseline written"
        return 1
    }
    rc=0
    out="$(run_gate --captures "$WORK/caps")" || rc=$?
    assert_exit_code 1 "$rc" "seeded: the planted E6 is ENFORCED"
    assert_contains "$out" "E6" "and named"
    log_pass "a seeded baseline lets a planted structural defect fire"
}

test_seed_refuses_empty_corpus() {
    local rc=0 out
    out="$(run_gate --seed "$WORK/caps")" || rc=$? # F rises, J rises: allowed
    assert_exit_code 0 "$rc" "accumulating is the silent direction"
    # An EMPTY corpus must be refused: a baseline seeded from nothing enshrines nothing.
    # (The first draft asserted a "silent shrink" refusal that could never fire, because
    # seeds accumulate -- this test is what exposed that vacuous control.)
    mkdir -p "$WORK/empty"
    rc=0
    out="$(run_gate --seed "$WORK/empty")" || rc=$?
    assert_exit_code 2 "$rc" "seeding from zero judgeable captures is refused"
    assert_contains "$out" "0 judgeable" "and says why"
    log_pass "an empty seed is refused; accumulation is the only silent direction"
}

test_mutant_wall_scaling_removed() {
    # Strip the wall-only scaling so dilate() becomes a no-op. The deriver's own
    # "dilate really moves wall" control must then FAIL, the gate runs that selftest
    # first, and an instrument-control failure is exit 2. THE MUTATION IS ASSERTED
    # BEFORE THE RUN: the first draft's sed silently matched nothing after a
    # formatter re-wrap, the gate ran unmutated, enforced the planted E6 (exit 1),
    # and the case read that as "wrong exit code" rather than "no mutant".
    local rc=0 out mod="$WORK/root/.claude/hooks/stop/wl_profile.py"
    python3 - "$mod" <<'PY2'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text()
old = 'int(s["t_ms"] * k)'
if s.count(old) != 1:
    print("MUTATION DID NOT APPLY (%d hits)" % s.count(old)); sys.exit(9)
p.write_text(s.replace(old, 's["t_ms"]'))
PY2
    rc=$?
    assert_exit_code 0 "$rc" "the mutation was applied (exactly one site)"
    if ! grep -q 's2\["t_ms"\] = s\["t_ms"\]' "$mod"; then
        log_fail "mutant text not present after write"
        return 1
    fi
    rc=0
    out="$(run_gate --captures "$WORK/caps")" || rc=$?
    assert_exit_code 2 "$rc" "a no-op dilate is refused as an instrument failure (exit 2)"
    assert_contains "$out" "dilate really moves wall" "and the deriver's own control is what named it"
    log_pass "MUTANT: removing wall scaling reds the gate's own control"
}

test_pristine_warns_not_passes_silently
test_seeded_then_enforces
test_seed_refuses_empty_corpus
test_mutant_wall_scaling_removed
log_pass "all resprofile gate tests passed"
