#!/bin/bash
# Tests for .ci/scripts/quality/check_runner_advice.py: a job whose own profile
# says it fits ubuntu-slim must actually be on ubuntu-slim, and a job already on
# slim must not be sitting at slim's edge.
#
# Driven through the gate's env seams (RUNNER_ADVICE_BASELINE,
# _WORKFLOW_DIR, _ALLOWLIST) against temp fixtures, so no tracked baseline,
# workflow or allowlist is touched. Two cases are the exception and they are the
# load-bearing ones: the awk/python parity case runs the REAL report.awk and
# requires the REAL classify() to reproduce its verdict token, and the last case
# runs the gate SEAM-FREE against the real tree.
#
# Every fire case has its control: the same fixture, one thing changed, and the
# opposite verdict asserted. A gate that cannot be made to fire is not a gate,
# and a gate that fires on everything is not one either.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
GATE="$REPO_ROOT/.ci/scripts/quality/check_runner_advice.py"
REPORT_AWK="$REPO_ROOT/.ci/scripts/ci/profiler/report.awk"
VALIDATOR="$REPO_ROOT/.ci/scripts/lib/blocker-validator.sh"
REAL_ALLOWLIST="$REPO_ROOT/.runner-advice-allowlist"

LAST_OUT=""

# run_gate <baseline> <workflow-dir> <allowlist>
run_gate() {
    local rc=0
    LAST_OUT="$(RUNNER_ADVICE_BASELINE="$1" \
        RUNNER_ADVICE_WORKFLOW_DIR="$2" \
        RUNNER_ADVICE_ALLOWLIST="$3" \
        python3 "$GATE" 2>&1)" || rc=$?
    return "$rc"
}

# workflow <dir> <runner-for-waster> -- five jobs, one of which is the subject.
# The other four exist so the baseline clears the vacuity floor with records
# that must stay SILENT: a CPU-bound job, a job already on slim, a job too close
# to the time cap, and a job whose runner is chosen at dispatch time.
workflow() {
    local dir="$1" runner="$2"
    mkdir -p "$dir"
    cat >"$dir/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  waster:
    runs-on: __RUNNER__
    steps:
      - run: echo work
  heavy:
    runs-on: ubuntu-latest
    steps:
      - run: echo work
  slimfit:
    runs-on: ubuntu-slim
    steps:
      - run: echo work
  longish:
    runs-on: ubuntu-latest
    steps:
      - run: echo work
  dynamic:
    runs-on: ${{ inputs.runner }}
    steps:
      - run: echo work
YAML
    sed -i "s/__RUNNER__/$runner/" "$dir/fixture.yml"
}

# baseline <file> <refreshed_at> [waster-observed-runs]
#
# `waster` is 0.20 cores and 900 MiB over two minutes on a 4-vCPU VM: the
# textbook MOVE_TO_SLIM. Everything else classifies to a verdict that must not
# fire.
baseline() {
    local file="$1" stamp="$2" observed="${3:-3}"
    cat >"$file" <<JSON
{
  "refreshed_at": "$stamp",
  "jobs": {
    "fixture.yml:waster": {
      "workflow": "fixture.yml", "runner_label": "ubuntu-latest", "tier": "PROC_HOST",
      "cpu_peak_milli": 200, "mem_peak_bytes": 943718400, "wall_s": 120,
      "cpu_ceil_milli": 4000, "mem_ceil_bytes": 16000000000, "observed_runs": $observed
    },
    "fixture.yml:heavy": {
      "workflow": "fixture.yml", "runner_label": "ubuntu-latest", "tier": "PROC_HOST",
      "cpu_peak_milli": 3200, "mem_peak_bytes": 943718400, "wall_s": 120,
      "cpu_ceil_milli": 4000, "mem_ceil_bytes": 16000000000, "observed_runs": 6
    },
    "fixture.yml:slimfit": {
      "workflow": "fixture.yml", "runner_label": "ubuntu-slim", "tier": "CGROUP_V2",
      "cpu_peak_milli": 400, "mem_peak_bytes": 1073741824, "wall_s": 300,
      "cpu_ceil_milli": 1000, "mem_ceil_bytes": 5368709120, "observed_runs": 6
    },
    "fixture.yml:longish": {
      "workflow": "fixture.yml", "runner_label": "ubuntu-latest", "tier": "PROC_HOST",
      "cpu_peak_milli": 200, "mem_peak_bytes": 943718400, "wall_s": 800,
      "cpu_ceil_milli": 4000, "mem_ceil_bytes": 16000000000, "observed_runs": 6
    },
    "fixture.yml:dynamic": {
      "workflow": "fixture.yml", "runner_label": "ubuntu-latest", "tier": "PROC_HOST",
      "cpu_peak_milli": 200, "mem_peak_bytes": 943718400, "wall_s": 120,
      "cpu_ceil_milli": 4000, "mem_ceil_bytes": 16000000000, "observed_runs": 6
    }
  }
}
JSON
}

fresh_stamp() { date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ; }

test_oversized_job_fails() {
    # FIRE: measured at 0.20 cores / 900 MiB, sitting on a 4-vCPU VM.
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    baseline "$d/base.json" "$(fresh_stamp)"
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a job that fits slim on a bigger runner must fail"
    assert_contains "$LAST_OUT" "fixture.yml:waster" "names the workflow file and the job"
    assert_contains "$LAST_OUT" "runs-on ubuntu-latest" "names the runner it is on"
    assert_not_contains "$LAST_OUT" "fixture.yml:heavy" "a CPU-bound job must not be swept up"
    assert_not_contains "$LAST_OUT" "fixture.yml:longish" "a job near the time cap must not be swept up"
    assert_not_contains "$LAST_OUT" "fixture.yml:dynamic" "a dispatch-time runner must never be fired on"
    log_pass "an oversized job fails, naming file, job and runner"
}

test_same_job_on_slim_passes() {
    # CONTROL: identical measurement, one word changed in the workflow.
    local d="$1"
    workflow "$d/wf" ubuntu-slim
    baseline "$d/base.json" "$(fresh_stamp)"
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 0 "$rc" "the same job already on slim must pass (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "5 measured job(s)" "reports what it actually compared"
    log_pass "the same job already on ubuntu-slim is silent"
}

test_allowlisted_with_good_reason_passes() {
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    baseline "$d/base.json" "$(fresh_stamp)"
    cat >"$d/allow" <<'ALLOW'
# BLOCKER: this job builds a disk image with qemu-img and needs the 75 GB of scratch
# space an ubuntu-latest VM has; slim's whole filesystem is 14 GB, image included, and
# the profiler measures CPU and RAM rather than the space a single step needs at once
fixture.yml:waster
ALLOW
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 0 "$rc" "an allowlisted job with a real reason must pass (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "1 allowlisted" "reports the suppression rather than hiding it"
    log_pass "an allowlist entry with a BLOCKER suppresses the cost finding"
}

test_entry_without_blocker_fails() {
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    baseline "$d/base.json" "$(fresh_stamp)"
    printf 'fixture.yml:waster\n' >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "an entry with no BLOCKER at all must be rejected"
    assert_contains "$LAST_OUT" "missing a '# BLOCKER:" "names the missing convention"
    log_pass "an allowlist entry without a BLOCKER is rejected"
}

test_stale_allowlist_entries_fail() {
    local d="$1"
    local reason='# BLOCKER: this job builds a disk image with qemu-img and needs more scratch space than slim has in total'
    baseline "$d/base.json" "$(fresh_stamp)"

    # (1) the job has already been moved -- paid-down debt must not linger.
    workflow "$d/wf" ubuntu-slim
    printf '%s\nfixture.yml:waster\n' "$reason" >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "an entry for a job now on slim must fail as stale"
    assert_contains "$LAST_OUT" "ALREADY on ubuntu-slim" "says the exemption exempts nothing"

    # (2) the entry names no job at all.
    workflow "$d/wf" ubuntu-latest
    printf '%s\nfixture.yml:no-such-job\n' "$reason" >"$d/allow"
    rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "an entry naming no job must fail"
    assert_contains "$LAST_OUT" "names no job in any workflow" "says the entry suppresses nothing"

    # (3) the job exists but the profile no longer advises a move.
    printf '%s\nfixture.yml:heavy\n' "$reason" >"$d/allow"
    rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "an entry for a job that no longer fits slim must fail as stale"
    assert_contains "$LAST_OUT" "now classifies as KEEP" "names the verdict that replaced MOVE_TO_SLIM"
    log_pass "the allowlist can only shrink: moved, dead and no-longer-applicable entries all fail"
}

test_slim_job_at_its_limit_fails() {
    # THE OTHER DIRECTION, and it is not allowlistable. A job on slim that is at
    # or past its declared timeout is about to be reported as `cancelled`.
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    baseline "$d/base.json" "$(fresh_stamp)"
    python3 - "$d/base.json" <<'PY'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))
data["jobs"]["fixture.yml:slimfit"]["wall_s"] = 860
json.dump(data, open(p, "w", encoding="utf-8"))
PY
    cat >"$d/allow" <<'ALLOW'
# BLOCKER: this job builds a disk image with qemu-img and needs the 75 GB of scratch
# space an ubuntu-latest VM has, which slim cannot provide at any runner size
fixture.yml:slimfit
ALLOW
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a slim job at its time cap must fail even when allowlisted"
    assert_contains "$LAST_OUT" "fixture.yml:slimfit" "names the job about to be cancelled"
    assert_contains "$LAST_OUT" "not allowlistable" "says why the waiver did not apply"
    log_pass "the reliability direction fires on a slim job at its cap, and ignores the allowlist"
}

test_orphan_baseline_record_fails() {
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    baseline "$d/base.json" "$(fresh_stamp)"
    python3 - "$d/base.json" <<'PY'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))
data["jobs"]["fixture.yml:renamed-away"] = data["jobs"].pop("fixture.yml:waster")
json.dump(data, open(p, "w", encoding="utf-8"))
PY
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a baseline record matching no workflow job must fail"
    assert_contains "$LAST_OUT" "names no job in any workflow" "says the measurement is unfalsifiable"
    log_pass "a renamed-away baseline record is a defect, not a comment"
}

test_under_observed_move_is_an_advisory() {
    # One quiet afternoon is not evidence. Loud, but not red.
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    baseline "$d/base.json" "$(fresh_stamp)" 1
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 0 "$rc" "a MOVE seen once must not fail the build (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "ADVISORY (not yet a failure)" "says it is not yet a failure"
    assert_contains "$LAST_OUT" "fixture.yml:waster" "still names the job"
    log_pass "a MOVE observed once is an advisory; three observations make it a failure"
}

test_empty_baseline_refuses() {
    # ANTI-VACUITY. Zero jobs compared exits 0 and reads exactly like coverage.
    # `refreshed_at` is SET here, so this is not the pristine shape: something
    # wrote this file and left no jobs behind, which is a defect.
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    printf '{"refreshed_at": "%s", "jobs": {}}\n' "$(fresh_stamp)" >"$d/base.json"
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "an empty baseline with a refresh stamp must REFUSE, not report clean"
    assert_contains "$LAST_OUT" "VACUOUS INPUT" "names the refusal"
    assert_not_contains "$LAST_OUT" "sit on the runner their own profile justifies" "must not print a success line"
    # The refusal EXPLAINS the bootstrap exception, so the annotation is what
    # must be absent, not the word.
    assert_not_contains "$LAST_OUT" "::warning title=Runner sizing (bootstrap)::" \
        "a stamped file must not reach the bootstrap exception"
    log_pass "an empty baseline that has been written to refuses rather than passing vacuously"
}

test_pristine_baseline_warns_and_passes() {
    # THE BOOTSTRAP EXCEPTION. Without it the gate is unsatisfiable: it goes red
    # on an unseeded baseline, the seed can only come from a run whose profiled
    # jobs finished, and this gate failing ~5 minutes in is what stops them
    # finishing. Two rounds of that yielded 3 jobs against a floor of 5.
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    printf '{"refreshed_at": null, "jobs": {}}\n' >"$d/base.json"
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 0 "$rc" "the pristine as-committed baseline must pass (output: $LAST_OUT)"
    # The warning is the FIRE direction for this arm. A pristine run that exits
    # 0 SILENTLY is the failure this whole gate exists to prevent, so passing
    # without saying so must fail this test.
    assert_contains "$LAST_OUT" "::warning title=Runner sizing (bootstrap)::" "emits the annotation, so CI shows it"
    assert_contains "$LAST_OUT" "UNENFORCED" "says plainly that nothing was checked"
    assert_contains "$LAST_OUT" "--refresh --branch main" "names the command that fixes it"
    log_pass "a pristine baseline warns loudly and passes, rather than blocking its own bootstrap"
}

test_pristine_shape_is_exact() {
    # Every near-miss must still REFUSE. "Below the floor" and "never seeded"
    # are different states and only the second one is innocent; forgiving the
    # first would make truncating this file a way to silence a real finding.
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    : >"$d/allow"
    local rc

    # (1) null stamp, but jobs present and below the floor.
    printf '{"refreshed_at": null, "jobs": {"fixture.yml:waster": {"workflow": "fixture.yml", "runner_label": "ubuntu-latest", "tier": "PROC_HOST", "cpu_peak_milli": 200, "mem_peak_bytes": 943718400, "wall_s": 120, "cpu_ceil_milli": 4000, "mem_ceil_bytes": 16000000000, "observed_runs": 3}}}\n' >"$d/base.json"
    rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a null stamp with SOME jobs is not pristine"
    assert_contains "$LAST_OUT" "VACUOUS INPUT" "refuses rather than bootstrapping"

    # (2) stamp set, zero jobs -- already covered above, asserted here as part
    # of the shape matrix so the two halves of the predicate are both pinned.
    printf '{"refreshed_at": "%s", "jobs": {}}\n' "$(fresh_stamp)" >"$d/base.json"
    rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a stamped baseline with zero jobs is not pristine"

    # (3) no refreshed_at key at all: a file somebody has edited, not the
    # committed shape.
    printf '{"jobs": {}}\n' >"$d/base.json"
    rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a baseline missing refreshed_at entirely is not pristine"

    # (4) no jobs key at all.
    printf '{"refreshed_at": null}\n' >"$d/base.json"
    rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a baseline missing jobs entirely is not pristine"
    log_pass "the pristine exception is shape-exact: four near-misses all still refuse"
}

test_refresh_refuses_a_partial_harvest() {
    # ALL OR NOTHING. This is what keeps the pristine exception honest: if a
    # harvest could write 2 jobs, "seeded" would stop meaning "enforceable" and
    # the gate would refuse every run afterwards with no way back.
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    printf '{"refreshed_at": null, "jobs": {}}\n' >"$d/base.json"
    local before after out rc=0
    before="$(md5sum <"$d/base.json")"
    out="$(
        python3 - "$GATE" "$d/base.json" "$d/wf" 2>&1 <<'PY'
import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location("check_runner_advice", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NUMS = "runner_label=ubuntu-latest tier=PROC_HOST env=github-hosted cpu_peak_milli=200 mem_peak_bytes=943718400 wall_s=120 cpu_ceil_milli=4000 mem_ceil_bytes=16000000000 samples=12 findings=0 verdict=MOVE_TO_SLIM"
# Two of the fixture workflow's own jobs, so the workflow index resolves them
# and the refusal under test is the FLOOR rather than an unresolvable job id.
rows = [
    ("1", module.parse_row("PROFILER_BASELINE_V1 job=%s %s" % (job, NUMS)))
    for job in ("waster", "heavy")
]

# The network half is stubbed; the REFUSAL under test is everything after it.
workflow_dir = pathlib.Path(sys.argv[3])
module.harvest = lambda *a, **k: (["9001"], rows)
sys.exit(
    module.refresh(
        workflow_dir.parent, pathlib.Path(sys.argv[2]), workflow_dir, "main", "", 8
    )
)
PY
    )" || rc=$?
    after="$(md5sum <"$d/base.json")"
    assert_exit_code 1 "$rc" "a harvest below the floor must refuse (output: $out)"
    assert_contains "$out" "harvest yielded 2 job(s)" "says exactly what it found"
    assert_contains "$out" "baseline left untouched" "says what it did about it"
    assert_eq "$after" "$before" "the baseline must be byte-identical after a refused harvest"
    log_pass "a partial harvest is refused and leaves the file untouched"
}

test_stale_baseline_fails() {
    local d="$1"
    workflow "$d/wf" ubuntu-slim
    baseline "$d/base.json" "2024-01-01T00:00:00Z"
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a baseline older than the age limit must fail"
    assert_contains "$LAST_OUT" "the baseline itself is stale" "names the staleness"

    # A missing stamp is the same failure, and must not read as "fresh".
    python3 - "$d/base.json" <<'PY'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))
data.pop("refreshed_at")
json.dump(data, open(p, "w", encoding="utf-8"))
PY
    rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a baseline with no refreshed_at must fail"
    assert_contains "$LAST_OUT" "missing or unparseable" "says the stamp itself is the problem"
    log_pass "a stale or unstamped baseline fails rather than being trusted"
}

test_empty_workflow_dir_refuses() {
    local d="$1"
    mkdir -p "$d/wf"
    baseline "$d/base.json" "$(fresh_stamp)"
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "a workflow directory with no parseable jobs must refuse"
    assert_contains "$LAST_OUT" "CANNOT READ THE WORKFLOWS" "refuses a verdict instead of guessing"
    log_pass "zero parsed job/runs-on pairs refuses rather than passing vacuously"
}

# synth_tsv <out> <tier> <cpu_ceil> <mem_ceil> <label> <src> <hint> <samples> <cpu_milli> <mem_base> [env]
#
# The schema is sampler-linux.sh's, field for field:
#   #META  tier cpu_milli mem_bytes interval_s start_ms runner_label cpu_src mem_src container_hint runner_env
#   S      t_ms cpu_milli mem_bytes rx_bytes   tx_bytes disk_ws_kb   disk_tmp_kb
# RAM is walked by one byte per sample so the degenerate-series finding (all
# readings identical) does not fire on a synthetic capture. `env` defaults to
# empty, which writes a 10-field META -- the pre-2026-08-09 shape, kept as a
# fixture so the back-compat default is exercised rather than assumed.
synth_tsv() {
    local out="$1" tier="$2" cceil="$3" mceil="$4" label="$5" src="$6" hint="$7"
    local n="$8" cpu="$9" mem="${10}" env="${11:-}"
    local i=1 t=1700000000000
    if [ -n "$env" ]; then
        printf '#META\t%s\t%s\t%s\t10\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$tier" "$cceil" "$mceil" "$t" "$label" "$src" "$src" "$hint" "$env" >"$out"
    else
        printf '#META\t%s\t%s\t%s\t10\t%s\t%s\t%s\t%s\t%s\n' \
            "$tier" "$cceil" "$mceil" "$t" "$label" "$src" "$src" "$hint" >"$out"
    fi
    while [ "$i" -le "$n" ]; do
        t=$((t + 10000))
        printf 'S\t%s\t%s\t%s\t100\t200\t1000\t1000\n' "$t" "$cpu" "$((mem + i))" >>"$out"
        i=$((i + 1))
    done
}

# assert_parity <dir> <name> <expected-verdict> <synth_tsv args...>
assert_parity() {
    local d="$1" name="$2" want="$3"
    shift 3
    local tsv="$d/$name.tsv" machine="$d/$name.row"
    synth_tsv "$tsv" "$@"
    # After the shift the tail is synth_tsv's own argument list, so the sample
    # count is its 7th: tier cceil mceil label src hint SAMPLES cpu mem.
    local samples="$7"
    local rc=0
    awk -v wall_s=$((samples * 10)) -v job="$name" -v machine_file="$machine" \
        -f "$REPORT_AWK" "$tsv" >"$d/$name.md" || rc=$?
    assert_exit_code 0 "$rc" "report.awk must produce a clean profile for '$name' (output: $(cat "$d/$name.md"))"
    [ -s "$machine" ] || log_fail "report.awk wrote no machine row for '$name'"

    local row awk_verdict py_verdict
    row="$(cat "$machine")"
    awk_verdict="${row##*verdict=}"
    assert_eq "$awk_verdict" "$want" "report.awk's verdict for '$name'"
    py_verdict="$(
        python3 - "$GATE" "$row" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("check_runner_advice", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.classify(module.parse_row(sys.argv[2])))
PY
    )"
    assert_eq "$py_verdict" "$awk_verdict" "classify() must reproduce report.awk's verdict for '$name' (row: $row)"
}

test_awk_and_python_agree_on_the_verdict() {
    # THE COHERENCE CASE. Two implementations of the same thresholds, in two
    # languages, in two files. The panel's advisory and this gate's verdict are
    # only the same claim for as long as these agree, and nothing else in the
    # tree would notice them drifting apart.
    local d="$1"
    assert_parity "$d" move MOVE_TO_SLIM PROC_HOST 4000 16000000000 ubuntu-latest PROC_HOST HOST 12 200 943718400
    assert_parity "$d" keepcpu KEEP PROC_HOST 4000 16000000000 ubuntu-latest PROC_HOST HOST 12 3200 943718400
    assert_parity "$d" slimfit SLIM_FIT CGROUP_V2 1000 5368709120 ubuntu-slim CGROUP_V2 CONTAINER 30 400 1073741824
    log_pass "report.awk and classify() reach the same verdict on MOVE, KEEP and SLIM_FIT profiles"
}

# advise_once <dir> <name> <synth_tsv args...> -> sets ADVISORY and ROW.
advise_once() {
    local d="$1" name="$2"
    shift 2
    synth_tsv "$d/$name.tsv" "$@"
    local samples="$7"
    local rc=0
    awk -v wall_s=$((samples * 10)) -v job="$name" -v machine_file="$d/$name.row" \
        -f "$REPORT_AWK" "$d/$name.tsv" >"$d/$name.md" || rc=$?
    assert_exit_code 0 "$rc" "report.awk must produce a clean profile for '$name'"
    ADVISORY="$(sed -n 's/^\*\*Advisory:\*\* //p' "$d/$name.md" | head -n 1)"
    ROW="$(cat "$d/$name.row")"
}

test_github_hosted_vm_is_trusted() {
    # THE 2026-08-09 REGRESSION, as a test. The first real harvest seeded ZERO
    # jobs because every ubuntu-latest row came back verdict=NONE: PROC_HOST
    # with no runner-label, which the advisor refused to attribute. A
    # github-hosted VM with no container fingerprint is an exclusive machine, so
    # its /proc numbers ARE the job's.
    local d="$1"
    local shape=(PROC_HOST 4000 16000000000 unknown PROC_HOST HOST 12 200 943718400)

    advise_once "$d" hosted "${shape[@]}" github-hosted
    assert_contains "$ADVISORY" "MOVE TO ubuntu-slim" "a hosted VM that fits slim must be told to move"
    assert_contains "$ADVISORY" "github-hosted VM (label unknown)" "the prose names what it trusted, and admits the label is unknown"
    assert_contains "$ROW" "env=github-hosted" "the row carries the evidence"
    assert_contains "$ROW" "verdict=MOVE_TO_SLIM" "the row carries a real verdict, not NONE"

    # CONTROL 1: identical capture, no github-hosted evidence.
    advise_once "$d" selfhosted "${shape[@]}" self-hosted
    assert_contains "$ADVISORY" "a VM cannot be told from a container" "a self-hosted PROC_HOST box still says nothing"
    assert_contains "$ROW" "verdict=NONE" "and its row stays NONE"

    # CONTROL 2: github-hosted, but the PID 1 fingerprint says container. The
    # fingerprint must win, or slim's container gets sized off host numbers.
    #
    # The second assertion is the load-bearing one and looks pedantic on
    # purpose. verdict=NONE alone does NOT pin the fingerprint clause inside
    # hosted_vm: the older PROC_HOST-plus-container arm refuses this input
    # independently, so deleting the clause leaves the verdict unchanged and a
    # verdict-only control passes over the mutation (measured, not assumed).
    # WHICH arm spoke does change, so the wording is what proves the clause is
    # still there -- and the clause is worth keeping because it makes the trust
    # condition self-contained rather than dependent on the order of the arms
    # below it.
    advise_once "$d" hostedcontainer PROC_HOST 4000 16000000000 unknown PROC_HOST CONTAINER 12 200 943718400 github-hosted
    assert_contains "$ROW" "verdict=NONE" "a container fingerprint beats github-hosted"
    assert_contains "$ADVISORY" "a VM cannot be told from a container" \
        "the trust arm must exclude containers itself, not lean on the arm below it"

    # CONTROL 3: a pre-2026-08-09 TSV with no env field at all must keep the OLD
    # behaviour rather than being retroactively trusted.
    advise_once "$d" legacy "${shape[@]}"
    assert_contains "$ROW" "env=unknown" "a 10-field META defaults to the untrusted side"
    assert_contains "$ROW" "verdict=NONE" "and an archived capture is not retroactively believed"
    log_pass "a github-hosted VM is trusted; self-hosted, containers and legacy captures are not"
}

test_harvester_skip_rule() {
    # merge_rows is the only place a row becomes a baseline number, so the skip
    # rule is driven directly rather than inferred from a --refresh run.
    local d="$1"
    local out
    out="$(
        python3 - "$GATE" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("check_runner_advice", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NUMS = "cpu_peak_milli=200 mem_peak_bytes=943718400 wall_s=120 cpu_ceil_milli=4000 mem_ceil_bytes=16000000000 samples=12"


def row(job, **kw):
    parts = ["PROFILER_BASELINE_V1", "job=%s" % job, "runner_label=unknown", NUMS]
    parts.extend("%s=%s" % (k, v) for k, v in kw.items())
    return module.parse_row(" ".join(parts))


rows = [
    ("1", row("hosted", tier="PROC_HOST", env="github-hosted", findings=0, verdict="MOVE_TO_SLIM")),
    ("1", row("unattributable", tier="PROC_HOST", env="unknown", findings=0, verdict="NONE")),
    ("1", row("hostednone", tier="PROC_HOST", env="github-hosted", findings=0, verdict="NONE")),
    ("1", row("starved", tier="PROC_HOST", env="github-hosted", findings=2, verdict="MOVE_TO_SLIM")),
    ("1", row("leaked", tier="HOST_LEAK", env="github-hosted", findings=0, verdict="MOVE_TO_SLIM")),
    ("1", row("noenv", tier="CGROUP_V2", findings=0, verdict="SLIM_FIT")),
]
where = {f[1]["job"]: {"fixture.yml"} for f in rows}
merged, _contributing, _warnings = module.merge_rows(rows, where)
print(",".join(sorted(k.split(":")[1] for k in merged)))
print(module.parse_row("PROFILER_BASELINE_V1 job=x verdict=KEEP")["env"])
print(merged["fixture.yml:hosted"]["env"])
PY
    )"
    local accepted default_env stored_env
    accepted="$(printf '%s\n' "$out" | sed -n 1p)"
    default_env="$(printf '%s\n' "$out" | sed -n 2p)"
    stored_env="$(printf '%s\n' "$out" | sed -n 3p)"

    assert_eq "$accepted" "hosted,noenv" "only the attributable, finding-free rows may enter the baseline"
    assert_eq "$default_env" "unknown" "a row with no env= parses, defaulting to the untrusted side"
    assert_eq "$stored_env" "github-hosted" "the record keeps the evidence classify() re-derives from"
    log_pass "the harvester accepts github-hosted PROC_HOST rows and skips NONE, starved and leaked ones"
}

test_hosted_vm_record_fires_the_gate() {
    # END TO END, and the reason classify() had to learn about env: an
    # ubuntu-latest job's record carries runner_label=unknown, so without the
    # env evidence the gate would re-derive NONE and quietly fire on nothing --
    # the same blindness, one layer down.
    local d="$1"
    workflow "$d/wf" ubuntu-latest
    baseline "$d/base.json" "$(fresh_stamp)"
    python3 - "$d/base.json" <<'PY'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))
rec = data["jobs"]["fixture.yml:waster"]
rec["runner_label"] = "unknown"
rec["env"] = "github-hosted"
json.dump(data, open(p, "w", encoding="utf-8"))
PY
    : >"$d/allow"
    local rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 1 "$rc" "an unlabelled github-hosted record that fits slim must fail"
    assert_contains "$LAST_OUT" "fixture.yml:waster" "names the job"

    # CONTROL: same record, evidence removed. The gate must go quiet rather than
    # guess from numbers nobody can attribute.
    python3 - "$d/base.json" <<'PY'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))
data["jobs"]["fixture.yml:waster"]["env"] = "unknown"
json.dump(data, open(p, "w", encoding="utf-8"))
PY
    rc=0
    run_gate "$d/base.json" "$d/wf" "$d/allow" || rc=$?
    assert_exit_code 0 "$rc" "without github-hosted evidence the same record must be silent (output: $LAST_OUT)"
    log_pass "an unlabelled github-hosted record fires the gate; the same record without the evidence does not"
}

test_real_allowlist_blockers_are_substantive() {
    # The PROSE bar is the shared validator's, applied to the real file here so
    # the banned-phrase list lives in exactly one place.
    local d="$1"
    local rc=0
    LAST_OUT="$(bash -c '
        source "$1"
        declare -A entries=() reasons=()
        parse_blockered_list "$2" entries reasons
        verify_all_blockers "$2" reasons
    ' _ "$VALIDATOR" "$REAL_ALLOWLIST" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "every BLOCKER in $REAL_ALLOWLIST must be substantive (output: $LAST_OUT)"

    # CONTROL: the same machinery on a planted low-effort reason must reject it,
    # so the pass above is the validator working rather than the validator being
    # pointed at nothing.
    printf '# BLOCKER: tbd\nfixture.yml:waster\n' >"$d/bad"
    rc=0
    LAST_OUT="$(bash -c '
        source "$1"
        declare -A entries=() reasons=()
        parse_blockered_list "$2" entries reasons
        verify_all_blockers "$2" reasons
    ' _ "$VALIDATOR" "$d/bad" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a low-effort BLOCKER must be rejected"
    assert_contains "$LAST_OUT" "low-effort placeholder" "uses the shared validator's own wording"
    log_pass "the real allowlist's BLOCKERs pass the shared validator, which can still fire"
}

test_real_tree_seam_free() {
    # THE LOAD-BEARING CASE. No env seams: the real baseline, the real
    # .github/workflows, the real allowlist. Two outcomes are correct here and
    # the test asserts WHICH one it got rather than accepting any exit code:
    # once the baseline is seeded the gate passes, and until it is, the vacuity
    # floor must refuse. Anything else -- a crash, a silent 0 over an empty
    # baseline -- fails this case.
    local rc=0
    LAST_OUT="$(python3 "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real tree must not fail: it is either pristine or seeded (output: $LAST_OUT)"
    case "$LAST_OUT" in
        *"Runner sizing (bootstrap)"*)
            # PRISTINE. Exit 0 is only acceptable WITH the warning: a silent
            # pass over an unseeded baseline is the exact shape this gate
            # exists to prevent, so the annotation is asserted, not tolerated.
            assert_contains "$LAST_OUT" "::warning title=Runner sizing (bootstrap)::" \
                "a pristine real tree must annotate, not pass quietly"
            assert_contains "$LAST_OUT" "UNENFORCED" "and must say the word"
            log_pass "the real tree is pristine and says so loudly (expected until the harvest lands)"
            ;;
        *)
            assert_contains "$LAST_OUT" "sit on the runner their own profile justifies" \
                "a seeded real tree must print the count it compared"
            assert_not_contains "$LAST_OUT" "UNENFORCED" "a seeded baseline must not claim to be unenforced"
            log_pass "the real tree passes seam-free with a seeded baseline"
            ;;
    esac
    case "$LAST_OUT" in
        *fixture.yml*) log_fail "this test's fixture names leaked into the real run: a seam is not isolating" ;;
        *) ;;
    esac
}

log_test "test-runner-advice"
with_temp_dir test_oversized_job_fails
with_temp_dir test_same_job_on_slim_passes
with_temp_dir test_allowlisted_with_good_reason_passes
with_temp_dir test_entry_without_blocker_fails
with_temp_dir test_stale_allowlist_entries_fail
with_temp_dir test_slim_job_at_its_limit_fails
with_temp_dir test_orphan_baseline_record_fails
with_temp_dir test_under_observed_move_is_an_advisory
with_temp_dir test_empty_baseline_refuses
with_temp_dir test_pristine_baseline_warns_and_passes
with_temp_dir test_pristine_shape_is_exact
with_temp_dir test_refresh_refuses_a_partial_harvest
with_temp_dir test_stale_baseline_fails
with_temp_dir test_empty_workflow_dir_refuses
with_temp_dir test_awk_and_python_agree_on_the_verdict
with_temp_dir test_github_hosted_vm_is_trusted
with_temp_dir test_harvester_skip_rule
with_temp_dir test_hosted_vm_record_fires_the_gate
with_temp_dir test_real_allowlist_blockers_are_substantive
test_real_tree_seam_free
echo ""
log_pass "all tests passed"
