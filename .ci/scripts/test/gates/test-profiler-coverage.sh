#!/bin/bash
# Tests for .ci/scripts/quality/check-profiler-coverage.sh: every Linux job
# uses the runner profiler, and every job that uses it is configured right.
#
# Driven entirely through the gate's env seams (PROFILER_COVERAGE_WORKFLOW_DIR,
# _ALLOWLIST, _ACTION_DIR and the three floors) against temp fixtures, so no
# tracked workflow or allowlist is touched. The last case is the exception and
# the important one: it runs the gate SEAM-FREE over the real tree, which is
# what makes the manifest's CI-coverage claim true.
#
# Every fire case has its control: the same fixture, one thing changed, and the
# opposite verdict asserted. A gate that cannot be made to fire is not a gate.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$SCRIPT_DIR/../../quality/check-profiler-coverage.sh"

LAST_OUT=""

# run_gate <workflow-dir> <allowlist> [min-workflows] [min-jobs] [min-linux]
run_gate() {
    local dir="$1" allow="$2" minw="${3:-1}" minj="${4:-1}" minl="${5:-1}" rc=0
    LAST_OUT="$(PROFILER_COVERAGE_WORKFLOW_DIR="$dir" \
        PROFILER_COVERAGE_ALLOWLIST="$allow" \
        PROFILER_COVERAGE_MIN_WORKFLOWS="$minw" \
        PROFILER_COVERAGE_MIN_JOBS="$minj" \
        PROFILER_COVERAGE_MIN_LINUX="$minl" \
        bash "$GATE" 2>&1)" || rc=$?
    return "$rc"
}

# profiled_job <job-id> <runner> [extra-with-lines...] -> a covered job
profiled_job() {
    local job="$1" runner="$2"
    shift 2
    cat <<YAML
  $job:
    runs-on: $runner
    steps:
      - uses: ./.github/actions/profiler
        with:
          runner-label: $runner
$(for l in "$@"; do echo "          $l"; done)
      - run: echo work
YAML
}

# bare_job <job-id> <runner> -> an uncovered job
bare_job() {
    cat <<YAML
  $1:
    runs-on: $2
    steps:
      - run: echo work
YAML
}

# scaffold <dir> [extra-job-yaml] -> a workflow dir whose two Linux jobs are
# both profiled. The baseline every fire case mutates.
scaffold() {
    local d="$1"
    mkdir -p "$d/wf"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: '10'"
        profiled_job fixture-latest ubuntu-latest "interval: '5'" "strict: 'true'"
    } >"$d/wf/fixture.yml"
    : >"$d/allow"
}

test_full_coverage_passes() {
    local d="$1"
    scaffold "$d"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 2 2 || rc=$?
    assert_exit_code 0 "$rc" "a fully covered fixture must pass (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "2/2 Linux job(s) profiled" "counts both covered jobs"
    log_pass "a fully covered fixture passes"
}

test_missing_action_fails() {
    # FIRE: drop the profiler from one job. The gate must name job AND file.
    local d="$1"
    scaffold "$d"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: '10'"
        bare_job fixture-latest ubuntu-latest
    } >"$d/wf/fixture.yml"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 2 2 || rc=$?
    assert_exit_code 1 "$rc" "an unprofiled Linux job must fail"
    assert_contains "$LAST_OUT" "fixture.yml:fixture-latest" "names the workflow file and the job"
    assert_contains "$LAST_OUT" "runs on ubuntu-latest" "names why the job is in scope"
    log_pass "an unprofiled Linux job fails, naming file and job"
}

test_allowlisted_with_good_reason_passes() {
    # CONTROL for the case above: same tree, one allowlist line.
    local d="$1"
    scaffold "$d"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: '10'"
        bare_job fixture-latest ubuntu-latest
    } >"$d/wf/fixture.yml"
    cat >"$d/allow" <<'ALLOW'
# BLOCKER: this job shells out to a hypervisor that pins every core for its whole
# duration, so a second sampling process would contend with the measurement itself
fixture.yml:fixture-latest
ALLOW
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 2 2 || rc=$?
    assert_exit_code 0 "$rc" "an allowlisted job with a real reason must pass (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "1 allowlisted" "reports the suppression rather than hiding it"
    log_pass "an allowlist entry with a substantive BLOCKER suppresses the finding"
}

test_low_effort_blocker_rejected() {
    # The rejection is INHERITED from .ci/scripts/lib/blocker-validator.sh, not
    # re-implemented here: 'tbd' is on the shared banned-phrase list.
    local d="$1"
    scaffold "$d"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: '10'"
        bare_job fixture-latest ubuntu-latest
    } >"$d/wf/fixture.yml"
    printf '# BLOCKER: tbd\nfixture.yml:fixture-latest\n' >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 2 2 || rc=$?
    assert_exit_code 1 "$rc" "a low-effort BLOCKER must be rejected"
    assert_contains "$LAST_OUT" "low-effort placeholder" "uses the shared validator's own wording"
    log_pass "a low-effort BLOCKER is rejected by the shared validator"
}

test_missing_blocker_rejected() {
    local d="$1"
    scaffold "$d"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: '10'"
        bare_job fixture-latest ubuntu-latest
    } >"$d/wf/fixture.yml"
    printf 'fixture.yml:fixture-latest\n' >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 2 2 || rc=$?
    assert_exit_code 1 "$rc" "an entry with no BLOCKER at all must be rejected"
    assert_contains "$LAST_OUT" "missing a '# BLOCKER:" "names the missing convention"
    log_pass "an entry without a BLOCKER comment is rejected"
}

test_non_linux_jobs_not_required() {
    # macOS and Windows runners are out of scope: the sampler is Linux-only
    # (.ci/scripts/ci/profiler/sampler-linux.sh) and slim sizing is a Linux
    # question. MIN_LINUX=0 because this fixture deliberately has none.
    local d="$1"
    mkdir -p "$d/wf"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        bare_job fixture-mac macos-latest
        bare_job fixture-win windows-latest
        bare_job fixture-mac-intel macos-15-intel
    } >"$d/wf/fixture.yml"
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 3 0 || rc=$?
    assert_exit_code 0 "$rc" "non-Linux jobs must not be required to be profiled (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "0/0 Linux job(s)" "classifies all three as out of scope"
    log_pass "macos/windows jobs are not required to carry the profiler"
}

test_caller_job_not_required() {
    # A `uses: ./.github/workflows/...` job has no runner of its own; its steps
    # are the called workflow's jobs, which the gate sees in that file.
    local d="$1"
    mkdir -p "$d/wf"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        echo "  fixture-caller:"
        echo "    uses: ./.github/workflows/other.yml"
        echo "    with:"
        echo "      thing: value"
        profiled_job fixture-slim ubuntu-slim "interval: '10'"
    } >"$d/wf/fixture.yml"
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 2 1 || rc=$?
    assert_exit_code 0 "$rc" "a reusable-workflow caller must not be required (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "1 reusable-workflow caller(s) excluded" "reports the exclusion"
    log_pass "a reusable-workflow caller is excluded from the coverage relation"
}

test_matrix_with_linux_leg_is_required() {
    # FIRE: `runs-on: ${{ matrix.os }}` where one leg is Linux.
    local d="$1"
    mkdir -p "$d/wf"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-matrix:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        include:
          - os: macos-latest
          - os: ubuntu-24.04-arm
    steps:
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "a matrix with a Linux leg must be required"
    assert_contains "$LAST_OUT" "runs on ubuntu-24.04-arm" "resolves the matrix leg by name"
    log_pass "a matrix job with a Linux leg is required to be profiled"
}

test_matrix_without_linux_leg_is_not_required() {
    # CONTROL for the case above: same shape, no Linux leg.
    local d="$1"
    mkdir -p "$d/wf"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-matrix:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [macos-latest, windows-latest]
    steps:
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 0 || rc=$?
    assert_exit_code 0 "$rc" "an all-non-Linux matrix must not be required (output: $LAST_OUT)"
    log_pass "a matrix job with no Linux leg is out of scope (inline-list form resolved)"
}

test_unresolvable_runs_on_is_required() {
    # Fail-CLOSED: "we could not resolve it" must cost an allowlist line, not
    # be silently treated as out of scope.
    local d="$1"
    mkdir -p "$d/wf"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-dispatch:
    runs-on: ${{ inputs.runner }}
    steps:
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "an unresolvable runs-on must fail closed"
    assert_contains "$LAST_OUT" "no static parse can resolve" "says it could not resolve, rather than guessing"
    log_pass "an unresolvable runs-on is required, not silently exempted"
}

test_bad_interval_fails() {
    local d="$1"
    mkdir -p "$d/wf"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: '0'"
    } >"$d/wf/fixture.yml"
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "interval 0 must fail"
    assert_contains "$LAST_OUT" "outside 1..300s" "names the range"

    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: fast"
    } >"$d/wf/fixture.yml"
    rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "a non-numeric interval must fail"
    assert_contains "$LAST_OUT" "is not an integer" "names the type problem"

    # CONTROL: the same job with a sane interval passes.
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: '10'"
    } >"$d/wf/fixture.yml"
    rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 0 "$rc" "a sane interval must pass (output: $LAST_OUT)"
    log_pass "interval is validated as a positive integer in a sane range"
}

test_undeclared_input_fails() {
    # The declared set is read from the real action.yml, so this cannot drift.
    local d="$1"
    mkdir -p "$d/wf"
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "sampling-rate: '10'"
    } >"$d/wf/fixture.yml"
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "an input the action does not declare must fail"
    assert_contains "$LAST_OUT" "does not declare" "names the contract it was checked against"
    log_pass "an undeclared input is rejected against the real action.yml"
}

test_runner_label_problems_fail() {
    local d="$1"
    mkdir -p "$d/wf"
    # A label that disagrees with runs-on: the HOST_LEAK check would be armed
    # against the wrong runner, which is worse than not arming it.
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-slim:
    runs-on: ubuntu-slim
    steps:
      - uses: ./.github/actions/profiler
        with:
          runner-label: ubuntu-latest
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "a runner-label that disagrees with runs-on must fail"
    assert_contains "$LAST_OUT" "disagrees with runs-on" "names the disagreement"

    # Omitted entirely: the check cannot fire at all.
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-slim:
    runs-on: ubuntu-slim
    steps:
      - uses: ./.github/actions/profiler
        with:
          interval: '10'
      - run: echo work
YAML
    rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "a missing runner-label must fail"
    assert_contains "$LAST_OUT" "without runner-label" "says the HOST_LEAK check is unarmed"
    log_pass "runner-label is required and must agree with runs-on"
}

test_malformed_reference_fails() {
    # `uses: .github/actions/profiler` (no leading ./) is not a local action
    # reference: GitHub reads it as owner/repo and the workflow fails to parse.
    local d="$1"
    mkdir -p "$d/wf"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-slim:
    runs-on: ubuntu-slim
    steps:
      - uses: .github/actions/profiler
        with:
          runner-label: ubuntu-slim
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "a malformed action reference must fail"
    assert_contains "$LAST_OUT" "malformed profiler reference" "names the malformed reference"
    log_pass "a local action reference missing its './' is rejected"
}

test_nest_probe_is_not_coverage() {
    # Nesting works (run 31252148469), but that did NOT make every composite
    # coverage: only a DECLARED, verified wrapper counts. nest-probe is the
    # probe's own instrument and is deliberately not one, so a job carrying it
    # is still uncovered.
    local d="$1"
    mkdir -p "$d/wf"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-nested:
    runs-on: ubuntu-slim
    steps:
      - uses: ./.github/actions/profiler/nest-probe
        with:
          runner-label: ubuntu-slim
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "a nested wrapper must not count as coverage"
    assert_contains "$LAST_OUT" "does not use ./.github/actions/profiler" "reports it as uncovered"
    assert_not_contains "$LAST_OUT" "malformed profiler reference" "the wrapper is a legal reference, just not coverage"
    log_pass "the nest-probe wrapper is neither coverage nor a malformed reference"
}

test_declared_wrapper_counts_as_coverage() {
    # The UNVERIFIED extension seam, for a wrapper that lives outside this
    # repo's action tree: a ref named in PROFILER_COVERAGE_COVERING_ACTIONS is
    # taken on trust. Exercised here so it is live code rather than a comment
    # that has never run. (The built-in wrapper list is the verified path, and
    # is pinned by test_setup_workspace_is_builtin_coverage below.)
    local d="$1"
    mkdir -p "$d/wf"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-nested:
    runs-on: ubuntu-slim
    steps:
      - uses: ./.github/actions/profiler/nest-probe
        with:
          runner-label: ubuntu-slim
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    LAST_OUT="$(PROFILER_COVERAGE_WORKFLOW_DIR="$d/wf" \
        PROFILER_COVERAGE_ALLOWLIST="$d/allow" \
        PROFILER_COVERAGE_COVERING_ACTIONS="./.github/actions/profiler/nest-probe" \
        PROFILER_COVERAGE_MIN_WORKFLOWS=1 PROFILER_COVERAGE_MIN_JOBS=1 \
        PROFILER_COVERAGE_MIN_LINUX=1 bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "a declared covering wrapper must count as coverage (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "1/1 Linux job(s) profiled" "counts the wrapped job as covered"
    log_pass "a wrapper declared in COVERING_ACTIONS counts as coverage"
}

test_setup_workspace_is_builtin_coverage() {
    # THE PHASE-1 INVARIANT. profiler-probe.yml run 31252148469 proved a nested
    # post: hook fires, so ./.github/actions/setup-workspace carries the
    # profiler and every job calling it is covered. Driven with NO seam at all
    # here: if somebody reverts the built-in wrapper list to empty, or deletes
    # the profiler step out of setup-workspace, this case goes red -- which is
    # the only thing standing between that edit and ~26 jobs that report as
    # profiled while profiling nothing.
    local d="$1"
    mkdir -p "$d/wf"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-wrapped:
    runs-on: ubuntu-slim
    steps:
      - uses: ./.github/actions/setup-workspace
        with:
          natives: 'true'
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 0 "$rc" "a job using setup-workspace must count as covered with no seam set (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "1/1 Linux job(s) profiled" "counts the wrapped job as covered"
    log_pass "setup-workspace is built-in coverage, seam-free"
}

test_other_composite_is_not_coverage() {
    # CONTROL for the case above: a DIFFERENT local composite, same shape. Only
    # a verified wrapper counts; "uses some composite" must not.
    local d="$1"
    mkdir -p "$d/wf"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-wrapped:
    runs-on: ubuntu-slim
    steps:
      - uses: ./.github/actions/app-token
      - run: echo work
YAML
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "an unrelated composite must not count as coverage"
    assert_contains "$LAST_OUT" "does not use ./.github/actions/profiler" "reports it as uncovered"
    log_pass "a composite that is not a declared wrapper is not coverage"
}

test_wrapper_that_lost_the_profiler_refuses() {
    # The fail-open this verification exists to stop: deleting one `uses:` line
    # from setup-workspace would silently uncover every job that calls it, and
    # the gate would still print a clean coverage line. It must REFUSE instead.
    local d="$1"
    mkdir -p "$d/wf" "$d/hollow-wrapper"
    cat >"$d/wf/fixture.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  fixture-slim:
    runs-on: ubuntu-slim
    steps:
      - uses: ./.github/actions/profiler
        with:
          runner-label: ubuntu-slim
      - run: echo work
YAML
    cat >"$d/hollow-wrapper/action.yml" <<'YAML'
name: Hollow Wrapper
description: A composite that used to carry the profiler and no longer does.
runs:
  using: composite
  steps:
    - shell: bash
      run: echo work
YAML
    : >"$d/allow"

    local rc=0
    LAST_OUT="$(PROFILER_COVERAGE_WORKFLOW_DIR="$d/wf" \
        PROFILER_COVERAGE_ALLOWLIST="$d/allow" \
        PROFILER_COVERAGE_WRAPPER_DIRS="$d/hollow-wrapper" \
        PROFILER_COVERAGE_MIN_WORKFLOWS=1 PROFILER_COVERAGE_MIN_JOBS=1 \
        PROFILER_COVERAGE_MIN_LINUX=1 bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a wrapper that does not use the profiler must refuse"
    assert_contains "$LAST_OUT" "covering wrapper" "names the wrapper it checked"
    assert_not_contains "$LAST_OUT" "Linux job(s) profiled" "must not print a success line"

    # A wrapper directory that is not there at all is the same failure one step
    # earlier, and must refuse rather than silently cover nothing.
    rc=0
    LAST_OUT="$(PROFILER_COVERAGE_WORKFLOW_DIR="$d/wf" \
        PROFILER_COVERAGE_ALLOWLIST="$d/allow" \
        PROFILER_COVERAGE_WRAPPER_DIRS="$d/no-such-wrapper" \
        PROFILER_COVERAGE_MIN_WORKFLOWS=1 PROFILER_COVERAGE_MIN_JOBS=1 \
        PROFILER_COVERAGE_MIN_LINUX=1 bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a wrapper directory with no action.yml must refuse"
    assert_contains "$LAST_OUT" "has no action.yml" "names the missing contract"

    # CONTROL: the REAL wrapper, named explicitly, is accepted -- so the two
    # refusals above are the verification working, not the seam being unusable.
    rc=0
    LAST_OUT="$(PROFILER_COVERAGE_WORKFLOW_DIR="$d/wf" \
        PROFILER_COVERAGE_ALLOWLIST="$d/allow" \
        PROFILER_COVERAGE_WRAPPER_DIRS=".github/actions/setup-workspace" \
        PROFILER_COVERAGE_MIN_WORKFLOWS=1 PROFILER_COVERAGE_MIN_JOBS=1 \
        PROFILER_COVERAGE_MIN_LINUX=1 bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real setup-workspace wrapper must verify (output: $LAST_OUT)"
    log_pass "a wrapper is verified to carry the profiler, and refuses when it does not"
}

test_stale_allowlist_entries_fail() {
    local d="$1"
    scaffold "$d"
    local reason='# BLOCKER: the runner this job requests is chosen at dispatch time, so there is no single label to arm the HOST_LEAK check with'

    # (1) names a job that does not exist
    printf '%s\nfixture.yml:no-such-job\n' "$reason" >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 2 2 || rc=$?
    assert_exit_code 1 "$rc" "an entry naming no job must fail"
    assert_contains "$LAST_OUT" "names no job" "says the entry suppresses nothing"

    # (2) names a job that IS profiled now -- paid-down debt must not linger
    printf '%s\nfixture.yml:fixture-slim\n' "$reason" >"$d/allow"
    rc=0
    run_gate "$d/wf" "$d/allow" 1 2 2 || rc=$?
    assert_exit_code 1 "$rc" "an entry for a now-covered job must fail as stale"
    assert_contains "$LAST_OUT" "IS profiled now" "says the exemption exempts nothing"

    # (3) names a job that never needed covering
    {
        echo "on:"
        echo "  workflow_dispatch:"
        echo "jobs:"
        profiled_job fixture-slim ubuntu-slim "interval: '10'"
        bare_job fixture-mac macos-latest
    } >"$d/wf/fixture.yml"
    printf '%s\nfixture.yml:fixture-mac\n' "$reason" >"$d/allow"
    rc=0
    run_gate "$d/wf" "$d/allow" 1 2 1 || rc=$?
    assert_exit_code 1 "$rc" "an entry for a non-Linux job must fail as stale"
    assert_contains "$LAST_OUT" "does not run on Linux" "says it was never required"
    log_pass "the allowlist can only shrink: dead, covered and never-required entries all fail"
}

test_empty_workflow_dir_refuses() {
    # ANTI-VACUITY. An empty scan is a broken instrument, never a clean tree.
    local d="$1"
    mkdir -p "$d/wf"
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "an empty workflow directory must REFUSE, not report clean"
    assert_contains "$LAST_OUT" "ZERO workflow files" "names what went missing"
    assert_not_contains "$LAST_OUT" "Linux job(s) profiled" "must not print a success line"
    log_pass "an empty workflow directory refuses rather than passing vacuously"
}

test_missing_workflow_dir_refuses() {
    local d="$1"
    : >"$d/allow"
    local rc=0
    run_gate "$d/nowhere" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "a missing workflow directory must refuse"
    assert_contains "$LAST_OUT" "workflow directory not found" "names the missing path"
    log_pass "a missing workflow directory refuses"
}

test_zero_jobs_refuses() {
    # A workflow file the job parser cannot read looks exactly like a clean
    # tree unless zero is treated as broken.
    local d="$1"
    mkdir -p "$d/wf"
    printf 'on:\n  workflow_dispatch:\n' >"$d/wf/fixture.yml"
    : >"$d/allow"
    local rc=0
    run_gate "$d/wf" "$d/allow" 1 1 1 || rc=$?
    assert_exit_code 1 "$rc" "zero parsed jobs must refuse"
    assert_contains "$LAST_OUT" "ZERO jobs" "names what went missing"
    log_pass "zero parsed jobs refuses rather than passing vacuously"
}

test_floors_refuse_a_shrunken_sweep() {
    local d="$1"
    scaffold "$d"

    # Workflow floor: the real tree has 28 files; a scan that finds 1 is wrong.
    local rc=0
    run_gate "$d/wf" "$d/allow" 5 2 2 || rc=$?
    assert_exit_code 1 "$rc" "a workflow count under the floor must refuse"
    assert_contains "$LAST_OUT" "the scan surface is wrong" "says broken, not clean"

    # Job floor.
    rc=0
    run_gate "$d/wf" "$d/allow" 1 50 2 || rc=$?
    assert_exit_code 1 "$rc" "a job count under the floor must refuse"
    assert_contains "$LAST_OUT" "found a layout it does not understand" "blames the parser"

    # Linux-job floor: the classifier, not the parser.
    rc=0
    run_gate "$d/wf" "$d/allow" 1 2 50 || rc=$?
    assert_exit_code 1 "$rc" "a Linux-job count under the floor must refuse"
    assert_contains "$LAST_OUT" "runner classifier is broken" "blames the classifier"
    log_pass "all three floors refuse a shrunken sweep"
}

test_missing_action_yml_refuses() {
    # The input contract is DERIVED from action.yml. Without it the gate can
    # assert nothing about configuration, so it must refuse rather than check
    # coverage only and call that a pass.
    local d="$1"
    scaffold "$d"
    local rc=0
    LAST_OUT="$(PROFILER_COVERAGE_WORKFLOW_DIR="$d/wf" \
        PROFILER_COVERAGE_ALLOWLIST="$d/allow" \
        PROFILER_COVERAGE_ACTION_DIR="$d/no-such-action" \
        PROFILER_COVERAGE_MIN_WORKFLOWS=1 PROFILER_COVERAGE_MIN_JOBS=2 \
        PROFILER_COVERAGE_MIN_LINUX=2 bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a missing action.yml must refuse"
    assert_contains "$LAST_OUT" "profiler action not found" "names the missing contract"
    log_pass "a missing action.yml refuses rather than half-checking"
}

test_real_tree_seam_free() {
    # THE LOAD-BEARING CASE. No env seams at all: the real workflow dir, the
    # real allowlist, the real action.yml, the real floors. This is what the
    # manifest's BLOCKER claims runs on every CI run.
    local rc=0
    LAST_OUT="$(bash "$GATE" 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the real tree must satisfy the gate (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "Linux job(s) profiled" "prints the real coverage count"
    case "$LAST_OUT" in
        *fixture-*) log_fail "this test's fixture names leaked into the real sweep: a seam is not isolating" ;;
        *) ;;
    esac
    log_pass "the real tree passes seam-free, and no fixture leaks into it"
}

log_test "test-profiler-coverage"
with_temp_dir test_full_coverage_passes
with_temp_dir test_missing_action_fails
with_temp_dir test_allowlisted_with_good_reason_passes
with_temp_dir test_low_effort_blocker_rejected
with_temp_dir test_missing_blocker_rejected
with_temp_dir test_non_linux_jobs_not_required
with_temp_dir test_caller_job_not_required
with_temp_dir test_matrix_with_linux_leg_is_required
with_temp_dir test_matrix_without_linux_leg_is_not_required
with_temp_dir test_unresolvable_runs_on_is_required
with_temp_dir test_bad_interval_fails
with_temp_dir test_undeclared_input_fails
with_temp_dir test_runner_label_problems_fail
with_temp_dir test_malformed_reference_fails
with_temp_dir test_nest_probe_is_not_coverage
with_temp_dir test_declared_wrapper_counts_as_coverage
with_temp_dir test_setup_workspace_is_builtin_coverage
with_temp_dir test_other_composite_is_not_coverage
with_temp_dir test_wrapper_that_lost_the_profiler_refuses
with_temp_dir test_stale_allowlist_entries_fail
with_temp_dir test_empty_workflow_dir_refuses
with_temp_dir test_missing_workflow_dir_refuses
with_temp_dir test_zero_jobs_refuses
with_temp_dir test_floors_refuse_a_shrunken_sweep
with_temp_dir test_missing_action_yml_refuses
test_real_tree_seam_free
echo ""
log_pass "all tests passed"
