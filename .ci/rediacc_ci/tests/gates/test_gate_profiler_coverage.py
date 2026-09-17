"""Port of `.ci/scripts/test/gates/test-profiler-coverage.sh`.

Tests for `.ci/scripts/quality/check-profiler-coverage.sh`: every Linux job uses the runner profiler, and every job that uses it is configured right.

Driven entirely through the gate's env seams (`PROFILER_COVERAGE_WORKFLOW_DIR`, `_ALLOWLIST`, `_ACTION_DIR`, `_WRAPPER_DIRS`, `_COVERING_ACTIONS` and the three floors) against temp fixtures, so no tracked workflow or allowlist is touched. The last twin case is the exception and the important one: it runs the gate SEAM-FREE over the real tree, which is what makes the manifest's
CI-coverage claim true.

Every fire case has its control: the same fixture, one thing changed, and the opposite verdict asserted. A gate that cannot be made to fire is not a gate.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. `gate-test:profiler-coverage` declares `reads: ["tree:repo"]` in `scripts/ci-runner/gates.lock.json`, so the twin is in the set `xdist_groups.real_tree_twins` derives and `real_tree_admission` requires the declaration. It is right on the merits too: `test_real_tree_seam_free` sweeps the real `.github/workflows`,
`test_setup_workspace_is_builtin_coverage` and `test_wrapper_that_lost_the_profiler_refuses` read the real `.github/actions/setup-workspace`, and `test_undeclared_input_fails` is checked against the real `.github/actions/profiler/action.yml`. A battery step rewriting any of those mid-sweep is a divergence that would be blamed on this port. The opt-in is honoured only because this
module declares no `XDIST_GROUP` of its own.

--------------------------------------------------------------------------
IS THIS FILE VISIBLE TO THE SWEEP IT DRIVES? NO, AND IT IS CHECKED
--------------------------------------------------------------------------
The question is owed by any port whose fixtures are the very shapes its subject hunts for, and it was asked before a fixture was written. The subject enumerates `*.yml` under a workflow DIRECTORY and reconciles what it finds against an allowlist; this file is a `.py` under `.ci/rediacc_ci/tests/gates`, so it is outside the sweep on both counts and the fixtures are written out
literally, as the twin writes them.

What replaces that argument with a control is `test_this_module_plants_no_workflow_the_real_sweep_can_see`, added by the port: it points the REAL subject's workflow directory at this very directory and requires it to REFUSE with "ZERO workflow files". A `.yml` appearing beside these ports, or the walker widening, turns that control red HERE, by name, rather than reddening
`check:ci-profiler-coverage` for whoever runs it next.

The twin's own leak check is kept as well: `test_real_tree_seam_free` forbids the string `fixture-` anywhere in the real run's output, so a seam that stopped isolating shows up as this file's job names appearing in a real verdict.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-profiler-coverage.sh"

# test_real_tree_seam_free, test_setup_workspace_is_builtin_coverage, test_wrapper_that_lost_the_profiler_refuses and the added control all read the real tree, and the lock declares `reads: ["tree:repo"]`. See the docstring.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/quality/check-profiler-coverage.sh"
GATE = paths.from_root(*GATE_REL.split("/"))
HERE_REL = ".ci/rediacc_ci/tests/gates"

# The reason string the stale-allowlist case reuses. Long enough to clear the shared BLOCKER validator's bar, which is the point: these three sub-cases are about STALENESS, and a reason that failed validation would red them for the wrong reason.
GOOD_REASON = (
    "# BLOCKER: the runner this job requests is chosen at dispatch time, so there is "
    "no single label to arm the HOST_LEAK check with"
)


def require_gate(gate) -> str:
    """The subject, proved present before anything is claimed."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    return harness.require_tool("bash", "install bash; the subject IS a bash script")


def run_gate(
    gate,
    workflow_dir,
    allowlist,
    minw: int = 1,
    minj: int = 1,
    minl: int = 1,
    **extra: str,
) -> harness.RunResult:
    """`run_gate <workflow-dir> <allowlist> [min-workflows] [min-jobs] [min-linux]`.

    The twin captures `2>&1` into `LAST_OUT` and asserts on the merged text, so every caller below reads `.combined` for the same reason. Env is passed per
    call rather than exported, which is what the twin's inline `VAR=... bash`
    form buys it: one case cannot leak a seam into the next.
    """
    bash = require_gate(gate)
    env = {
        "PROFILER_COVERAGE_WORKFLOW_DIR": os.fspath(workflow_dir),
        "PROFILER_COVERAGE_ALLOWLIST": os.fspath(allowlist),
        "PROFILER_COVERAGE_MIN_WORKFLOWS": str(minw),
        "PROFILER_COVERAGE_MIN_JOBS": str(minj),
        "PROFILER_COVERAGE_MIN_LINUX": str(minl),
    }
    env.update(extra)
    return harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root(), env=env)


def profiled_job(job: str, runner: str, *extra_with: str) -> str:
    """`profiled_job <job-id> <runner> [extra-with-lines...]` -> a covered job."""
    lines = [
        "  %s:" % job,
        "    runs-on: %s" % runner,
        "    steps:",
        "      - uses: ./.github/actions/profiler",
        "        with:",
        "          runner-label: %s" % runner,
    ]
    lines.extend("          " + line for line in extra_with)
    lines.append("      - run: echo work")
    return "".join(line + "\n" for line in lines)


def bare_job(job: str, runner: str) -> str:
    """`bare_job <job-id> <runner>` -> an uncovered job."""
    return "  %s:\n    runs-on: %s\n    steps:\n      - run: echo work\n" % (job, runner)


HEADER = "on:\n  workflow_dispatch:\njobs:\n"


def write_workflow(gate, d, *jobs: str):
    """`$d/wf/fixture.yml` from a header plus job blocks, and the allowlist.

    ANTI-VACUITY. A workflow with NO jobs is the fixture `test_zero_jobs_refuses` builds on purpose, and it builds it directly; every other case passing zero jobs through here would be driving the gate over a file it cannot classify and reading the refusal as whatever it expected. So an empty job list is a FAILURE here rather than a fixture that says nothing.
    """
    if not jobs:
        gate.log_fail(
            "write_workflow was given ZERO job blocks, so the fixture holds no job for "
            "the gate to classify and any verdict from it would be about an empty file."
        )
    wf = d / "wf"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "fixture.yml").write_text(HEADER + "".join(jobs), encoding="utf-8")
    allow = d / "allow"
    if not allow.exists():
        allow.write_text("", encoding="utf-8")
    return wf, allow


def scaffold(gate, d):
    """`scaffold <dir>` -> a workflow dir whose two Linux jobs are both profiled.

    The baseline every fire case mutates.
    """
    wf, allow = write_workflow(
        gate,
        d,
        profiled_job("fixture-slim", "ubuntu-slim", "interval: '10'"),
        profiled_job("fixture-latest", "ubuntu-latest", "interval: '5'", "strict: 'true'"),
    )
    allow.write_text("", encoding="utf-8")
    return wf, allow


def one_profiled_one_bare(gate, d):
    """The fixture the allowlist cases share: one covered job, one not."""
    return write_workflow(
        gate,
        d,
        profiled_job("fixture-slim", "ubuntu-slim", "interval: '10'"),
        bare_job("fixture-latest", "ubuntu-latest"),
    )


# ---------------------------------------------------------------------------


def test_full_coverage_passes(gate):
    with harness.temp_dir() as d:
        wf, allow = scaffold(gate, d)
        result = run_gate(gate, wf, allow, 1, 2, 2)
        gate.assert_exit_code(
            0, result.rc, "a fully covered fixture must pass (output: %s)" % result.combined
        )
        gate.assert_contains(
            result.combined, "2/2 Linux job(s) profiled", "counts both covered jobs"
        )
        gate.log_pass("a fully covered fixture passes")


def test_missing_action_fails(gate):
    """FIRE: drop the profiler from one job. The gate must name job AND file."""
    with harness.temp_dir() as d:
        scaffold(gate, d)
        wf, allow = one_profiled_one_bare(gate, d)
        result = run_gate(gate, wf, allow, 1, 2, 2)
        gate.assert_exit_code(1, result.rc, "an unprofiled Linux job must fail")
        gate.assert_contains(
            result.combined,
            "fixture.yml:fixture-latest",
            "names the workflow file and the job",
        )
        gate.assert_contains(
            result.combined, "runs on ubuntu-latest", "names why the job is in scope"
        )
        gate.log_pass("an unprofiled Linux job fails, naming file and job")


def test_allowlisted_with_good_reason_passes(gate):
    """CONTROL for the case above: same tree, one allowlist line."""
    with harness.temp_dir() as d:
        scaffold(gate, d)
        wf, allow = one_profiled_one_bare(gate, d)
        allow.write_text(
            "# BLOCKER: this job shells out to a hypervisor that pins every core for its "
            "whole\n# duration, so a second sampling process would contend with the "
            "measurement itself\nfixture.yml:fixture-latest\n",
            encoding="utf-8",
        )
        result = run_gate(gate, wf, allow, 1, 2, 2)
        gate.assert_exit_code(
            0,
            result.rc,
            "an allowlisted job with a real reason must pass (output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined, "1 allowlisted", "reports the suppression rather than hiding it"
        )
        gate.log_pass("an allowlist entry with a substantive BLOCKER suppresses the finding")


def test_low_effort_blocker_rejected(gate):
    """The rejection is INHERITED from .ci/scripts/lib/blocker-validator.sh, not re-implemented here: 'tbd' is on the shared banned-phrase list."""
    with harness.temp_dir() as d:
        scaffold(gate, d)
        wf, allow = one_profiled_one_bare(gate, d)
        allow.write_text("# BLOCKER: tbd\nfixture.yml:fixture-latest\n", encoding="utf-8")
        result = run_gate(gate, wf, allow, 1, 2, 2)
        gate.assert_exit_code(1, result.rc, "a low-effort BLOCKER must be rejected")
        gate.assert_contains(
            result.combined, "low-effort placeholder", "uses the shared validator's own wording"
        )
        gate.log_pass("a low-effort BLOCKER is rejected by the shared validator")


def test_missing_blocker_rejected(gate):
    with harness.temp_dir() as d:
        scaffold(gate, d)
        wf, allow = one_profiled_one_bare(gate, d)
        allow.write_text("fixture.yml:fixture-latest\n", encoding="utf-8")
        result = run_gate(gate, wf, allow, 1, 2, 2)
        gate.assert_exit_code(1, result.rc, "an entry with no BLOCKER at all must be rejected")
        gate.assert_contains(
            result.combined, "missing a '# BLOCKER:", "names the missing convention"
        )
        gate.log_pass("an entry without a BLOCKER comment is rejected")


def test_non_linux_jobs_not_required(gate):
    """macOS and Windows runners are out of scope: the sampler is Linux-only (.ci/scripts/ci/profiler/sampler-linux.sh) and slim sizing is a Linux
    question. MIN_LINUX=0 because this fixture deliberately has none."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            bare_job("fixture-mac", "macos-latest"),
            bare_job("fixture-win", "windows-latest"),
            bare_job("fixture-mac-intel", "macos-15-intel"),
        )
        result = run_gate(gate, wf, allow, 1, 3, 0)
        gate.assert_exit_code(
            0,
            result.rc,
            "non-Linux jobs must not be required to be profiled (output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined, "0/0 Linux job(s)", "classifies all three as out of scope"
        )
        gate.log_pass("macos/windows jobs are not required to carry the profiler")


def test_caller_job_not_required(gate):
    """A `uses: ./.github/workflows/...` job has no runner of its own; its steps are the called workflow's jobs, which the gate sees in that file."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-caller:\n    uses: ./.github/workflows/other.yml\n"
            "    with:\n      thing: value\n",
            profiled_job("fixture-slim", "ubuntu-slim", "interval: '10'"),
        )
        result = run_gate(gate, wf, allow, 1, 2, 1)
        gate.assert_exit_code(
            0,
            result.rc,
            "a reusable-workflow caller must not be required (output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined, "1 reusable-workflow caller(s) excluded", "reports the exclusion"
        )
        gate.log_pass("a reusable-workflow caller is excluded from the coverage relation")


def test_matrix_with_linux_leg_is_required(gate):
    """FIRE: `runs-on: ${{ matrix.os }}` where one leg is Linux."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-matrix:\n"
            "    runs-on: ${{ matrix.os }}\n"
            "    strategy:\n"
            "      matrix:\n"
            "        include:\n"
            "          - os: macos-latest\n"
            "          - os: ubuntu-24.04-arm\n"
            "    steps:\n"
            "      - run: echo work\n",
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "a matrix with a Linux leg must be required")
        gate.assert_contains(
            result.combined, "runs on ubuntu-24.04-arm", "resolves the matrix leg by name"
        )
        gate.log_pass("a matrix job with a Linux leg is required to be profiled")


def test_matrix_without_linux_leg_is_not_required(gate):
    """CONTROL for the case above: same shape, no Linux leg."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-matrix:\n"
            "    runs-on: ${{ matrix.os }}\n"
            "    strategy:\n"
            "      matrix:\n"
            "        os: [macos-latest, windows-latest]\n"
            "    steps:\n"
            "      - run: echo work\n",
        )
        result = run_gate(gate, wf, allow, 1, 1, 0)
        gate.assert_exit_code(
            0,
            result.rc,
            "an all-non-Linux matrix must not be required (output: %s)" % result.combined,
        )
        gate.log_pass("a matrix job with no Linux leg is out of scope (inline-list form resolved)")


def test_unresolvable_runs_on_is_required(gate):
    """Fail-CLOSED: "we could not resolve it" must cost an allowlist line, not be silently treated as out of scope."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-dispatch:\n"
            "    runs-on: ${{ inputs.runner }}\n"
            "    steps:\n"
            "      - run: echo work\n",
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "an unresolvable runs-on must fail closed")
        gate.assert_contains(
            result.combined,
            "no static parse can resolve",
            "says it could not resolve, rather than guessing",
        )
        gate.log_pass("an unresolvable runs-on is required, not silently exempted")


def test_bad_interval_fails(gate):
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate, d, profiled_job("fixture-slim", "ubuntu-slim", "interval: '0'")
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "interval 0 must fail")
        gate.assert_contains(result.combined, "outside 1..300s", "names the range")

        write_workflow(gate, d, profiled_job("fixture-slim", "ubuntu-slim", "interval: fast"))
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "a non-numeric interval must fail")
        gate.assert_contains(result.combined, "is not an integer", "names the type problem")

        # CONTROL: the same job with a sane interval passes.
        write_workflow(gate, d, profiled_job("fixture-slim", "ubuntu-slim", "interval: '10'"))
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(
            0, result.rc, "a sane interval must pass (output: %s)" % result.combined
        )
        gate.log_pass("interval is validated as a positive integer in a sane range")


def test_undeclared_input_fails(gate):
    """The declared set is read from the real action.yml, so this cannot drift."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate, d, profiled_job("fixture-slim", "ubuntu-slim", "sampling-rate: '10'")
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "an input the action does not declare must fail")
        gate.assert_contains(
            result.combined, "does not declare", "names the contract it was checked against"
        )
        gate.log_pass("an undeclared input is rejected against the real action.yml")


def test_runner_label_problems_fail(gate):
    with harness.temp_dir() as d:
        # A label that disagrees with runs-on: the HOST_LEAK check would be armed against the wrong runner, which is worse than not arming it.
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-slim:\n"
            "    runs-on: ubuntu-slim\n"
            "    steps:\n"
            "      - uses: ./.github/actions/profiler\n"
            "        with:\n"
            "          runner-label: ubuntu-latest\n"
            "      - run: echo work\n",
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "a runner-label that disagrees with runs-on must fail")
        gate.assert_contains(result.combined, "disagrees with runs-on", "names the disagreement")

        # Omitted entirely: the check cannot fire at all.
        write_workflow(
            gate,
            d,
            "  fixture-slim:\n"
            "    runs-on: ubuntu-slim\n"
            "    steps:\n"
            "      - uses: ./.github/actions/profiler\n"
            "        with:\n"
            "          interval: '10'\n"
            "      - run: echo work\n",
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "a missing runner-label must fail")
        gate.assert_contains(
            result.combined, "without runner-label", "says the HOST_LEAK check is unarmed"
        )
        gate.log_pass("runner-label is required and must agree with runs-on")


def test_malformed_reference_fails(gate):
    """`uses: .github/actions/profiler` (no leading ./) is not a local action reference: GitHub reads it as owner/repo and the workflow fails to parse."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-slim:\n"
            "    runs-on: ubuntu-slim\n"
            "    steps:\n"
            "      - uses: .github/actions/profiler\n"
            "        with:\n"
            "          runner-label: ubuntu-slim\n"
            "      - run: echo work\n",
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "a malformed action reference must fail")
        gate.assert_contains(
            result.combined, "malformed profiler reference", "names the malformed reference"
        )
        gate.log_pass("a local action reference missing its './' is rejected")


NESTED_JOB = (
    "  fixture-nested:\n"
    "    runs-on: ubuntu-slim\n"
    "    steps:\n"
    "      - uses: ./.github/actions/profiler/nest-probe\n"
    "        with:\n"
    "          runner-label: ubuntu-slim\n"
    "      - run: echo work\n"
)


def test_nest_probe_is_not_coverage(gate):
    """Nesting works (run 31252148469), but that did NOT make every composite coverage: only a DECLARED, verified wrapper counts. nest-probe is the probe's own instrument and is deliberately not one, so a job carrying it is still uncovered."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(gate, d, NESTED_JOB)
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "a nested wrapper must not count as coverage")
        gate.assert_contains(
            result.combined,
            "does not use ./.github/actions/profiler",
            "reports it as uncovered",
        )
        gate.assert_not_contains(
            result.combined,
            "malformed profiler reference",
            "the wrapper is a legal reference, just not coverage",
        )
        gate.log_pass("the nest-probe wrapper is neither coverage nor a malformed reference")


def test_declared_wrapper_counts_as_coverage(gate):
    """The UNVERIFIED extension seam, for a wrapper that lives outside this repo's action tree: a ref named in PROFILER_COVERAGE_COVERING_ACTIONS is taken on trust. Exercised here so it is live code rather than a comment that has never run. (The built-in wrapper list is the verified path, and is pinned by test_setup_workspace_is_builtin_coverage below.)"""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(gate, d, NESTED_JOB)
        result = run_gate(
            gate,
            wf,
            allow,
            1,
            1,
            1,
            PROFILER_COVERAGE_COVERING_ACTIONS="./.github/actions/profiler/nest-probe",
        )
        gate.assert_exit_code(
            0,
            result.rc,
            "a declared covering wrapper must count as coverage (output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined, "1/1 Linux job(s) profiled", "counts the wrapped job as covered"
        )
        gate.log_pass("a wrapper declared in COVERING_ACTIONS counts as coverage")


def test_setup_workspace_is_builtin_coverage(gate):
    """THE PHASE-1 INVARIANT. profiler-probe.yml run 31252148469 proved a nested post: hook fires, so ./.github/actions/setup-workspace carries the profiler and every job calling it is covered. Driven with NO wrapper seam at all here:
    if somebody reverts the built-in wrapper list to empty, or deletes the
    profiler step out of setup-workspace, this case goes red -- which is the only thing standing between that edit and ~26 jobs that report as profiled while profiling nothing."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-wrapped:\n"
            "    runs-on: ubuntu-slim\n"
            "    steps:\n"
            "      - uses: ./.github/actions/setup-workspace\n"
            "        with:\n"
            "          natives: 'true'\n"
            "      - run: echo work\n",
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(
            0,
            result.rc,
            "a job using setup-workspace must count as covered with no seam set "
            "(output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined, "1/1 Linux job(s) profiled", "counts the wrapped job as covered"
        )
        gate.log_pass("setup-workspace is built-in coverage, seam-free")


def test_other_composite_is_not_coverage(gate):
    """CONTROL for the case above: a DIFFERENT local composite, same shape. Only a verified wrapper counts; "uses some composite" must not."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-wrapped:\n"
            "    runs-on: ubuntu-slim\n"
            "    steps:\n"
            "      - uses: ./.github/actions/app-token\n"
            "      - run: echo work\n",
        )
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "an unrelated composite must not count as coverage")
        gate.assert_contains(
            result.combined,
            "does not use ./.github/actions/profiler",
            "reports it as uncovered",
        )
        gate.log_pass("a composite that is not a declared wrapper is not coverage")


def test_wrapper_that_lost_the_profiler_refuses(gate):
    """The fail-open this verification exists to stop: deleting one `uses:` line
    from setup-workspace would silently uncover every job that calls it, and the
    gate would still print a clean coverage line. It must REFUSE instead."""
    with harness.temp_dir() as d:
        wf, allow = write_workflow(
            gate,
            d,
            "  fixture-slim:\n"
            "    runs-on: ubuntu-slim\n"
            "    steps:\n"
            "      - uses: ./.github/actions/profiler\n"
            "        with:\n"
            "          runner-label: ubuntu-slim\n"
            "      - run: echo work\n",
        )
        hollow = d / "hollow-wrapper"
        hollow.mkdir(parents=True, exist_ok=True)
        (hollow / "action.yml").write_text(
            "name: Hollow Wrapper\n"
            "description: A composite that used to carry the profiler and no longer does.\n"
            "runs:\n"
            "  using: composite\n"
            "  steps:\n"
            "    - shell: bash\n"
            "      run: echo work\n",
            encoding="utf-8",
        )

        result = run_gate(
            gate, wf, allow, 1, 1, 1, PROFILER_COVERAGE_WRAPPER_DIRS=os.fspath(hollow)
        )
        gate.assert_exit_code(1, result.rc, "a wrapper that does not use the profiler must refuse")
        gate.assert_contains(result.combined, "covering wrapper", "names the wrapper it checked")
        gate.assert_not_contains(
            result.combined, "Linux job(s) profiled", "must not print a success line"
        )

        # A wrapper directory that is not there at all is the same failure one step earlier, and must refuse rather than silently cover nothing.
        result = run_gate(
            gate,
            wf,
            allow,
            1,
            1,
            1,
            PROFILER_COVERAGE_WRAPPER_DIRS=os.fspath(d / "no-such-wrapper"),
        )
        gate.assert_exit_code(1, result.rc, "a wrapper directory with no action.yml must refuse")
        gate.assert_contains(result.combined, "has no action.yml", "names the missing contract")

        # CONTROL: the REAL wrapper, named explicitly, is accepted -- so the two refusals above are the verification working, not the seam being unusable.
        result = run_gate(
            gate,
            wf,
            allow,
            1,
            1,
            1,
            PROFILER_COVERAGE_WRAPPER_DIRS=".github/actions/setup-workspace",
        )
        gate.assert_exit_code(
            0,
            result.rc,
            "the real setup-workspace wrapper must verify (output: %s)" % result.combined,
        )
        gate.log_pass("a wrapper is verified to carry the profiler, and refuses when it does not")


def test_stale_allowlist_entries_fail(gate):
    with harness.temp_dir() as d:
        wf, allow = scaffold(gate, d)

        # (1) names a job that does not exist
        allow.write_text("%s\nfixture.yml:no-such-job\n" % GOOD_REASON, encoding="utf-8")
        result = run_gate(gate, wf, allow, 1, 2, 2)
        gate.assert_exit_code(1, result.rc, "an entry naming no job must fail")
        gate.assert_contains(result.combined, "names no job", "says the entry suppresses nothing")

        # (2) names a job that IS profiled now -- paid-down debt must not linger
        allow.write_text("%s\nfixture.yml:fixture-slim\n" % GOOD_REASON, encoding="utf-8")
        result = run_gate(gate, wf, allow, 1, 2, 2)
        gate.assert_exit_code(1, result.rc, "an entry for a now-covered job must fail as stale")
        gate.assert_contains(
            result.combined, "IS profiled now", "says the exemption exempts nothing"
        )

        # (3) names a job that never needed covering
        write_workflow(
            gate,
            d,
            profiled_job("fixture-slim", "ubuntu-slim", "interval: '10'"),
            bare_job("fixture-mac", "macos-latest"),
        )
        allow.write_text("%s\nfixture.yml:fixture-mac\n" % GOOD_REASON, encoding="utf-8")
        result = run_gate(gate, wf, allow, 1, 2, 1)
        gate.assert_exit_code(1, result.rc, "an entry for a non-Linux job must fail as stale")
        gate.assert_contains(result.combined, "does not run on Linux", "says it was never required")
        gate.log_pass(
            "the allowlist can only shrink: dead, covered and never-required entries all fail"
        )


def test_empty_workflow_dir_refuses(gate):
    """ANTI-VACUITY. An empty scan is a broken instrument, never a clean tree."""
    with harness.temp_dir() as d:
        wf = d / "wf"
        wf.mkdir(parents=True, exist_ok=True)
        allow = d / "allow"
        allow.write_text("", encoding="utf-8")
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(
            1, result.rc, "an empty workflow directory must REFUSE, not report clean"
        )
        gate.assert_contains(result.combined, "ZERO workflow files", "names what went missing")
        gate.assert_not_contains(
            result.combined, "Linux job(s) profiled", "must not print a success line"
        )
        gate.log_pass("an empty workflow directory refuses rather than passing vacuously")


def test_missing_workflow_dir_refuses(gate):
    with harness.temp_dir() as d:
        allow = d / "allow"
        allow.write_text("", encoding="utf-8")
        result = run_gate(gate, d / "nowhere", allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "a missing workflow directory must refuse")
        gate.assert_contains(
            result.combined, "workflow directory not found", "names the missing path"
        )
        gate.log_pass("a missing workflow directory refuses")


def test_zero_jobs_refuses(gate):
    """A workflow file the job parser cannot read looks exactly like a clean tree unless zero is treated as broken."""
    with harness.temp_dir() as d:
        wf = d / "wf"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / "fixture.yml").write_text("on:\n  workflow_dispatch:\n", encoding="utf-8")
        allow = d / "allow"
        allow.write_text("", encoding="utf-8")
        result = run_gate(gate, wf, allow, 1, 1, 1)
        gate.assert_exit_code(1, result.rc, "zero parsed jobs must refuse")
        gate.assert_contains(result.combined, "ZERO jobs", "names what went missing")
        gate.log_pass("zero parsed jobs refuses rather than passing vacuously")


def test_floors_refuse_a_shrunken_sweep(gate):
    with harness.temp_dir() as d:
        wf, allow = scaffold(gate, d)

        # Workflow floor: the real tree has 28 files; a scan that finds 1 is wrong.
        result = run_gate(gate, wf, allow, 5, 2, 2)
        gate.assert_exit_code(1, result.rc, "a workflow count under the floor must refuse")
        gate.assert_contains(result.combined, "the scan surface is wrong", "says broken, not clean")

        # Job floor.
        result = run_gate(gate, wf, allow, 1, 50, 2)
        gate.assert_exit_code(1, result.rc, "a job count under the floor must refuse")
        gate.assert_contains(
            result.combined, "found a layout it does not understand", "blames the parser"
        )

        # Linux-job floor: the classifier, not the parser.
        result = run_gate(gate, wf, allow, 1, 2, 50)
        gate.assert_exit_code(1, result.rc, "a Linux-job count under the floor must refuse")
        gate.assert_contains(
            result.combined, "runner classifier is broken", "blames the classifier"
        )
        gate.log_pass("all three floors refuse a shrunken sweep")


def test_missing_action_yml_refuses(gate):
    """The input contract is DERIVED from action.yml. Without it the gate can assert nothing about configuration, so it must refuse rather than check coverage only and call that a pass."""
    with harness.temp_dir() as d:
        wf, allow = scaffold(gate, d)
        result = run_gate(
            gate,
            wf,
            allow,
            1,
            2,
            2,
            PROFILER_COVERAGE_ACTION_DIR=os.fspath(d / "no-such-action"),
        )
        gate.assert_exit_code(1, result.rc, "a missing action.yml must refuse")
        gate.assert_contains(
            result.combined, "profiler action not found", "names the missing contract"
        )
        gate.log_pass("a missing action.yml refuses rather than half-checking")


def test_real_tree_seam_free(gate):
    """THE LOAD-BEARING CASE. No env seams at all: the real workflow dir, the real allowlist, the real action.yml, the real floors. This is what the manifest's BLOCKER claims runs on every CI run."""
    bash = require_gate(gate)
    result = harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root())
    gate.assert_exit_code(
        0, result.rc, "the real tree must satisfy the gate (output: %s)" % result.combined
    )
    gate.assert_contains(result.combined, "Linux job(s) profiled", "prints the real coverage count")
    gate.assert_not_contains(
        result.combined,
        "fixture-",
        "this test's fixture names leaked into the real sweep: a seam is not isolating",
    )
    gate.log_pass("the real tree passes seam-free, and no fixture leaks into it")


# --------------------------------------------------------------------------- ADDED BY THE PORT. ---------------------------------------------------------------------------


def test_this_module_plants_no_workflow_the_real_sweep_can_see(gate):
    """ADDED BY THE PORT, and it is the control on this port's central claim.

    Every fixture above is a workflow the subject is built to hunt through, and they are written out LITERALLY because the subject cannot see this file: it enumerates `*.yml` under a workflow directory, and this is a `.py` under `.ci/rediacc_ci/tests/gates`. That is an argument, and an argument is not a control.

    So: point the REAL subject's workflow directory at this directory and require it to REFUSE with "ZERO workflow files". A `.yml` appearing beside these ports reds this case BY NAME instead of reddening `check:ci-profiler-coverage` for whoever runs it next.
    """
    here = paths.from_root(*HERE_REL.split("/"))
    if not here.is_dir():
        gate.log_fail("this module's own directory is missing at %s" % HERE_REL)
    modules = sorted(p.name for p in here.glob("*.py"))
    if not modules:
        gate.log_fail(
            "found ZERO python files under %s, so this control swept nothing and its "
            "green would mean nothing." % HERE_REL
        )
    with harness.temp_dir() as d:
        allow = d / "allow"
        allow.write_text("", encoding="utf-8")
        result = run_gate(gate, here, allow, 1, 1, 1)
        gate.assert_exit_code(
            1,
            result.rc,
            "pointing the subject at the ports' own directory must REFUSE as blind "
            "(output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined,
            "ZERO workflow files",
            "the subject must find NO workflow at all under %s; if it now finds one, "
            "this module's literal fixtures are inside the sweep and must be moved or "
            "excluded" % HERE_REL,
        )
    gate.log_pass(
        "%d ported module(s) under %s are invisible to the real sweep: the subject "
        "finds zero workflow files there" % (len(modules), HERE_REL)
    )
