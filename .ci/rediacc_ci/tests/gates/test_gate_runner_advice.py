r"""Port of `.ci/scripts/test/gates/test-runner-advice.sh`.

Tests for `.ci/scripts/quality/check_runner_advice.py`: a job whose own profile says it fits ubuntu-slim must actually be on ubuntu-slim, and a job already on slim must not be sitting at slim's edge.

Driven through the gate's env seams (`RUNNER_ADVICE_BASELINE`, `_WORKFLOW_DIR`, `_ALLOWLIST`) against temp fixtures, so no tracked baseline, workflow or allowlist is touched. Two cases are the exception and they are the load-bearing ones: the awk/python parity case runs the REAL `report.awk` and requires the REAL `classify()` to reproduce its verdict token, and the last case runs
the gate SEAM-FREE against the real tree.

Every fire case has its control: the same fixture, one thing changed, and the opposite verdict asserted. A gate that cannot be made to fire is not a gate, and a gate that fires on everything is not one either.

--------------------------------------------------------------------------
WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP
--------------------------------------------------------------------------
Read from the lock, not from a guess about the fixtures. `gates.lock.json` declares `gate-test:runner-advice` with `reads: ["tree:repo"]`, and it is right to: `test_real_tree_seam_free` runs the gate with NO seams at all, so it reads the tracked `.ci/policy/runner-profile-baseline.json`, the real `.github/workflows` and the real allowlist; `test_awk_and_python_agree_on_the_verdict`
runs the real `report.awk`; and `test_real_allowlist_blockers_are_substantive` runs the real `.ci/policy/.runner-advice-allowlist` through the real shared validator. A battery step rewriting any of those mid-sweep would be a divergence blamed on this port.

`REAL_TREE_TWIN = True` buys the serialisation, and it is honoured ONLY because
this module declares no `XDIST_GROUP` of its own -- see `real_tree_admission` in `test_twin_parity.py`, where an own-group declaration makes the opt-in vacuous.

--------------------------------------------------------------------------
WHY THE MODULE-LEVEL CASES STILL SHELL OUT TO python3
--------------------------------------------------------------------------
Four twin cases load `check_runner_advice.py` through `importlib` and, in two of them, REPLACE `module.harvest` with a stub. Doing that in-process would mutate a module global inside the pytest worker, which is exactly the condition that obliges a port to declare its own `XDIST_GROUP` -- and an own group would cancel the real-tree opt-in above. Running each snippet in a fresh
`python3 -` keeps the mutation inside a process that dies with the case, so the two requirements do not fight. It also keeps the port's diff readable against the twin, whose heredocs are carried across verbatim.

--------------------------------------------------------------------------
DOES THE SUBJECT SELF-SCAN? NO
--------------------------------------------------------------------------
Asked before a fixture was written, because a subject that can see this file turns a literal transcription into a tree-wide red for whoever runs the gate next. `check_runner_advice.py` reads exactly three inputs: a JSON baseline, a directory of `*.yml` workflows, and a line-oriented allowlist. It never walks a source tree, and none of those three can resolve to `.ci/rediacc_ci/**`.
The fixtures are therefore written out literally, as the twin writes them. `test_real_tree_seam_free` carries the twin's own control for the other direction: if a fixture name ever leaks into the seam-free run, that case fails by name here rather than reddening the gate elsewhere.
"""

import datetime
import hashlib
import json
import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-runner-advice.sh"

# test_real_tree_seam_free (no seams at all), test_awk_and_python_agree_on_the_verdict (the real report.awk) and test_real_allowlist_blockers_are_substantive (the real allowlist) all read the tracked tree. The lock says so too. See the docstring.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/quality/check_runner_advice.py"
GATE = paths.from_root(*GATE_REL.split("/"))
REPORT_AWK_REL = ".ci/scripts/ci/profiler/report.awk"
REPORT_AWK = paths.from_root(*REPORT_AWK_REL.split("/"))
VALIDATOR_REL = ".ci/scripts/lib/blocker-validator.sh"
VALIDATOR = paths.from_root(*VALIDATOR_REL.split("/"))
REAL_ALLOWLIST_REL = ".ci/policy/.runner-advice-allowlist"
REAL_ALLOWLIST = paths.from_root(*REAL_ALLOWLIST_REL.split("/"))

WORKFLOW_YAML = """on:
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
"""

# `waster` is 0.20 cores and 900 MiB over two minutes on a 4-vCPU VM: the textbook MOVE_TO_SLIM. Everything else classifies to a verdict that must not fire.
BASELINE_JSON = """{
  "format": 1,
  "refreshed_at": %(stamp)s,
  "jobs": {
    "fixture.yml:waster": {
      "workflow": "fixture.yml", "runner_label": "ubuntu-latest", "tier": "PROC_HOST",
      "cpu_peak_milli": 200, "mem_peak_bytes": 943718400, "wall_s": 120,
      "cpu_ceil_milli": 4000, "mem_ceil_bytes": 16000000000, "observed_runs": %(observed)d
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
"""

GOOD_BLOCKER = (
    "# BLOCKER: this job builds a disk image with qemu-img and needs the 75 GB of scratch\n"
    "# space an ubuntu-latest VM has; slim's whole filesystem is 14 GB, image included, and\n"
    "# the profiler measures CPU and RAM rather than the space a single step needs at once\n"
)
STALE_BLOCKER = (
    "# BLOCKER: this job builds a disk image with qemu-img and needs more scratch space "
    "than slim has in total"
)


def require_python(gate) -> str:
    """The subject, proved present before anything is claimed."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    return harness.require_tool("python3", "install python3; the subject IS a python script")


def run_gate(gate, baseline_path, workflow_dir, allowlist) -> harness.RunResult:
    """`run_gate <baseline> <workflow-dir> <allowlist>`, merged streams.

    The twin captures `2>&1` into `LAST_OUT` and asserts on the merged text, so every caller below reads `.combined` for the same reason.
    """
    python3 = require_python(gate)
    return harness.run(
        [python3, os.fspath(GATE)],
        env={
            "RUNNER_ADVICE_BASELINE": os.fspath(baseline_path),
            "RUNNER_ADVICE_WORKFLOW_DIR": os.fspath(workflow_dir),
            "RUNNER_ADVICE_ALLOWLIST": os.fspath(allowlist),
        },
    )


def run_inline(gate, script: str, *args: str) -> harness.RunResult:
    """`python3 - "$GATE" <args> <<'PY'`, one throwaway interpreter per call.

    `sys.argv[1]` is the gate path on the far side, exactly as in the twin, so a snippet carried across needs no index rewriting.
    """
    python3 = require_python(gate)
    return harness.run([python3, "-", os.fspath(GATE), *args], stdin=script)


def workflow(directory, runner: str) -> None:
    """`workflow <dir> <runner-for-waster>` -- five jobs, one of which is the subject.

    The other four exist so the baseline clears the vacuity floor with records that must stay SILENT: a CPU-bound job, a job already on slim, a job too close to the time cap, and a job whose runner is chosen at dispatch time.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "fixture.yml").write_text(
        WORKFLOW_YAML.replace("__RUNNER__", runner), encoding="utf-8"
    )


def baseline(path, stamp: str | None, observed: int = 3) -> None:
    """`baseline <file> <refreshed_at> [waster-observed-runs]`."""
    path.write_text(
        BASELINE_JSON
        % {
            "stamp": "null" if stamp is None else json.dumps(stamp),
            "observed": observed,
        },
        encoding="utf-8",
    )


def fresh_stamp() -> str:
    day_ago = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    return day_ago.strftime("%Y-%m-%dT%H:%M:%SZ")


def edit_baseline(path, mutate) -> None:
    """Load, mutate, dump. The twin's inline `python3 - "$d/base.json"` heredocs."""
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def digest(path) -> str:
    """`md5sum <file>`, spelled in a language that has hashlib.

    The twin only needs "did anything change", so the algorithm is not load-bearing; sha256 is used because nothing here wants md5.
    """
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- The cost direction, and its control. ---------------------------------------------------------------------------


def test_oversized_job_fails(gate):
    """FIRE: measured at 0.20 cores / 900 MiB, sitting on a 4-vCPU VM."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        baseline(d / "base.json", fresh_stamp())
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a job that fits slim on a bigger runner must fail")
        gate.assert_contains(
            result.combined, "fixture.yml:waster", "names the workflow file and the job"
        )
        gate.assert_contains(result.combined, "runs-on ubuntu-latest", "names the runner it is on")
        gate.assert_not_contains(
            result.combined, "fixture.yml:heavy", "a CPU-bound job must not be swept up"
        )
        gate.assert_not_contains(
            result.combined, "fixture.yml:longish", "a job near the time cap must not be swept up"
        )
        gate.assert_not_contains(
            result.combined,
            "fixture.yml:dynamic",
            "a dispatch-time runner must never be fired on",
        )
        gate.log_pass("an oversized job fails, naming file, job and runner")


def test_same_job_on_slim_passes(gate):
    """CONTROL: identical measurement, one word changed in the workflow."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-slim")
        baseline(d / "base.json", fresh_stamp())
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            0, result.rc, "the same job already on slim must pass (output: %s)" % result.combined
        )
        gate.assert_contains(
            result.combined, "5 measured job(s)", "reports what it actually compared"
        )
        gate.log_pass("the same job already on ubuntu-slim is silent")


def test_allowlisted_with_good_reason_passes(gate):
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        baseline(d / "base.json", fresh_stamp())
        (d / "allow").write_text(GOOD_BLOCKER + "fixture.yml:waster\n", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            0,
            result.rc,
            "an allowlisted job with a real reason must pass (output: %s)" % result.combined,
        )
        gate.assert_contains(
            result.combined, "1 allowlisted", "reports the suppression rather than hiding it"
        )
        gate.log_pass("an allowlist entry with a BLOCKER suppresses the cost finding")


def test_entry_without_blocker_fails(gate):
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        baseline(d / "base.json", fresh_stamp())
        (d / "allow").write_text("fixture.yml:waster\n", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "an entry with no BLOCKER at all must be rejected")
        gate.assert_contains(
            result.combined, "missing a '# BLOCKER:", "names the missing convention"
        )
        gate.log_pass("an allowlist entry without a BLOCKER is rejected")


def test_stale_allowlist_entries_fail(gate):
    with harness.temp_dir() as d:
        baseline(d / "base.json", fresh_stamp())

        # (1) the job has already been moved -- paid-down debt must not linger.
        workflow(d / "wf", "ubuntu-slim")
        (d / "allow").write_text("%s\nfixture.yml:waster\n" % STALE_BLOCKER, encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "an entry for a job now on slim must fail as stale")
        gate.assert_contains(
            result.combined, "ALREADY on ubuntu-slim", "says the exemption exempts nothing"
        )

        # (2) the entry names no job at all.
        workflow(d / "wf", "ubuntu-latest")
        (d / "allow").write_text("%s\nfixture.yml:no-such-job\n" % STALE_BLOCKER, encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "an entry naming no job must fail")
        gate.assert_contains(
            result.combined, "names no job in any workflow", "says the entry suppresses nothing"
        )

        # (3) the job exists but the profile no longer advises a move.
        (d / "allow").write_text("%s\nfixture.yml:heavy\n" % STALE_BLOCKER, encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            1, result.rc, "an entry for a job that no longer fits slim must fail as stale"
        )
        gate.assert_contains(
            result.combined,
            "now classifies as KEEP",
            "names the verdict that replaced MOVE_TO_SLIM",
        )
        gate.log_pass(
            "the allowlist can only shrink: moved, dead and no-longer-applicable entries all fail"
        )


def test_slim_job_at_its_limit_fails(gate):
    """THE OTHER DIRECTION, and it is not allowlistable. A job on slim that is at
    or past its declared timeout is about to be reported as `cancelled`."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        baseline(d / "base.json", fresh_stamp())

        def bump_wall(data):
            data["jobs"]["fixture.yml:slimfit"]["wall_s"] = 860

        edit_baseline(d / "base.json", bump_wall)
        (d / "allow").write_text(
            "# BLOCKER: this job builds a disk image with qemu-img and needs the 75 GB of "
            "scratch\n# space an ubuntu-latest VM has, which slim cannot provide at any "
            "runner size\nfixture.yml:slimfit\n",
            encoding="utf-8",
        )
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            1, result.rc, "a slim job at its time cap must fail even when allowlisted"
        )
        gate.assert_contains(
            result.combined, "fixture.yml:slimfit", "names the job about to be cancelled"
        )
        gate.assert_contains(
            result.combined, "not allowlistable", "says why the waiver did not apply"
        )
        gate.log_pass(
            "the reliability direction fires on a slim job at its cap, and ignores the allowlist"
        )


def test_orphan_baseline_record_fails(gate):
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        baseline(d / "base.json", fresh_stamp())

        def rename_away(data):
            data["jobs"]["fixture.yml:renamed-away"] = data["jobs"].pop("fixture.yml:waster")

        edit_baseline(d / "base.json", rename_away)
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a baseline record matching no workflow job must fail")
        gate.assert_contains(
            result.combined, "names no job in any workflow", "says the measurement is unfalsifiable"
        )
        gate.log_pass("a renamed-away baseline record is a defect, not a comment")


def test_under_observed_move_is_an_advisory(gate):
    """One quiet afternoon is not evidence. Loud, but not red."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        baseline(d / "base.json", fresh_stamp(), 1)
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            0, result.rc, "a MOVE seen once must not fail the build (output: %s)" % result.combined
        )
        gate.assert_contains(
            result.combined, "ADVISORY (not yet a failure)", "says it is not yet a failure"
        )
        gate.assert_contains(result.combined, "fixture.yml:waster", "still names the job")
        gate.log_pass("a MOVE observed once is an advisory; three observations make it a failure")


# --------------------------------------------------------------------------- Anti-vacuity, and the one exception to it. ---------------------------------------------------------------------------


def test_empty_baseline_refuses(gate):
    """ANTI-VACUITY. Zero jobs compared exits 0 and reads exactly like coverage.
    `refreshed_at` is SET here, so this is not the pristine shape: something
    wrote this file and left no jobs behind, which is a defect."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        (d / "base.json").write_text(
            '{"format": 1, "refreshed_at": "%s", "jobs": {}}\n' % fresh_stamp(), encoding="utf-8"
        )
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            1, result.rc, "an empty baseline with a refresh stamp must REFUSE, not report clean"
        )
        gate.assert_contains(result.combined, "VACUOUS INPUT", "names the refusal")
        gate.assert_not_contains(
            result.combined,
            "sit on the runner their own profile justifies",
            "must not print a success line",
        )
        # The refusal EXPLAINS the bootstrap exception, so the annotation is what must be absent, not the word.
        gate.assert_not_contains(
            result.combined,
            "::warning title=Runner sizing (bootstrap)::",
            "a stamped file must not reach the bootstrap exception",
        )
        gate.log_pass(
            "an empty baseline that has been written to refuses rather than passing vacuously"
        )


def test_pristine_baseline_warns_and_passes(gate):
    """THE BOOTSTRAP EXCEPTION. Without it the gate is unsatisfiable: it goes red
    on an unseeded baseline, the seed can only come from a run whose profiled jobs finished, and this gate failing ~5 minutes in is what stops them
    finishing. Two rounds of that yielded 3 jobs against a floor of 5."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        (d / "base.json").write_text(
            '{"format": 1, "refreshed_at": null, "jobs": {}}\n', encoding="utf-8"
        )
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            0,
            result.rc,
            "the pristine as-committed baseline must pass (output: %s)" % result.combined,
        )
        # The warning is the FIRE direction for this arm. A pristine run that exits 0 SILENTLY is the failure this whole gate exists to prevent, so passing without saying so must fail this test.
        gate.assert_contains(
            result.combined,
            "::warning title=Runner sizing (bootstrap)::",
            "emits the annotation, so CI shows it",
        )
        gate.assert_contains(result.combined, "UNENFORCED", "says plainly that nothing was checked")
        gate.assert_contains(
            result.combined, "--refresh --branch main", "names the command that fixes it"
        )
        gate.log_pass(
            "a pristine baseline warns loudly and passes, rather than blocking its own bootstrap"
        )


def test_pristine_shape_is_exact(gate):
    """Every near-miss must still REFUSE. "Below the floor" and "never seeded"
    are different states and only the second one is innocent; forgiving the
    first would make truncating this file a way to silence a real finding."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        (d / "allow").write_text("", encoding="utf-8")

        # (1) null stamp, but jobs present and below the floor.
        (d / "base.json").write_text(
            '{"format": 1, "refreshed_at": null, "jobs": {"fixture.yml:waster": {"workflow": '
            '"fixture.yml", "runner_label": "ubuntu-latest", "tier": "PROC_HOST", '
            '"cpu_peak_milli": 200, "mem_peak_bytes": 943718400, "wall_s": 120, '
            '"cpu_ceil_milli": 4000, "mem_ceil_bytes": 16000000000, "observed_runs": 3}}}\n',
            encoding="utf-8",
        )
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a null stamp with SOME jobs is not pristine")
        gate.assert_contains(result.combined, "VACUOUS INPUT", "refuses rather than bootstrapping")

        # (2) stamp set, zero jobs -- already covered above, asserted here as part of the shape matrix so the two halves of the predicate are both pinned.
        (d / "base.json").write_text(
            '{"format": 1, "refreshed_at": "%s", "jobs": {}}\n' % fresh_stamp(), encoding="utf-8"
        )
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a stamped baseline with zero jobs is not pristine")

        # (3) no refreshed_at key at all: a file somebody has edited, not the committed shape. Caught one layer earlier, by the structural validator, which is why the message is about the missing key rather than pristineness.
        (d / "base.json").write_text('{"format": 1, "jobs": {}}\n', encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            1, result.rc, "a baseline missing refreshed_at entirely is not pristine"
        )
        gate.assert_contains(
            result.combined,
            "missing required top-level key 'refreshed_at'",
            "names the missing key",
        )

        # (4) no jobs key at all.
        (d / "base.json").write_text('{"format": 1, "refreshed_at": null}\n', encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a baseline missing jobs entirely is not pristine")
        gate.assert_contains(
            result.combined, "missing required top-level key 'jobs'", "names the missing key"
        )
        gate.log_pass("the pristine exception is shape-exact: four near-misses all still refuse")


def test_unknown_format_refuses(gate):
    """A baseline with no machine-checked version reaches the gate as a KeyError
    traceback or, worse, as a silent misparse that reports a clean tree over
    numbers it misunderstood. Both are replaced by a NAMED incompatibility."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        (d / "allow").write_text("", encoding="utf-8")

        # (1) a FUTURE format this gate does not speak.
        baseline(d / "base.json", fresh_stamp())
        (d / "base.json").write_text(
            (d / "base.json").read_text(encoding="utf-8").replace('"format": 1,', '"format": 2,'),
            encoding="utf-8",
        )
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a baseline in an unknown format must refuse")
        gate.assert_contains(result.combined, "declares format 2", "names what it found")
        gate.assert_contains(result.combined, "this gate speaks format 1", "names what it speaks")
        gate.assert_not_contains(
            result.combined, "Traceback", "must be a named failure, never a stack trace"
        )
        gate.assert_not_contains(
            result.combined,
            "sit on the runner their own profile justifies",
            "must not report a verdict",
        )

        # (2) no version at all.
        baseline(d / "base.json", fresh_stamp())
        (d / "base.json").write_text(
            "".join(
                line + "\n"
                for line in (d / "base.json").read_text(encoding="utf-8").splitlines()
                if '"format": 1,' not in line
            ),
            encoding="utf-8",
        )
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a baseline with no format must refuse")
        gate.assert_contains(result.combined, 'declares no "format"', "names the missing version")
        gate.assert_not_contains(
            result.combined, "Traceback", "must be a named failure, never a stack trace"
        )

        # (3) not JSON at all -- the other way a hand-edit ends in a traceback.
        (d / "base.json").write_text('{"format": 1, "jobs": {,}\n', encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a corrupt baseline must refuse")
        gate.assert_contains(result.combined, "is not valid JSON", "names the syntax problem")
        gate.assert_not_contains(
            result.combined, "Traceback", "must be a named failure, never a stack trace"
        )

        # CONTROL: the same file, untouched, is read fine -- so the three refusals above are the version check working rather than the fixture being broken.
        baseline(d / "base.json", fresh_stamp())
        workflow(d / "wf", "ubuntu-slim")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            0,
            result.rc,
            "a valid format-1 baseline must still be read (output: %s)" % result.combined,
        )
        gate.log_pass(
            "an unknown, missing or corrupt baseline format refuses by NAME, never by traceback"
        )


def test_bad_record_names_the_job_and_field(gate):
    """The failure this replaces was `KeyError: 'mem_peak_bytes'` pointing at a
    line of the gate, which tells the reader nothing about which record is
    wrong. Every message names the job and the field."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        (d / "allow").write_text("", encoding="utf-8")

        baseline(d / "base.json", fresh_stamp())

        def bad_number(data):
            data["jobs"]["fixture.yml:waster"]["mem_peak_bytes"] = "lots"

        edit_baseline(d / "base.json", bad_number)
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a non-integer numeric must refuse")
        gate.assert_contains(result.combined, "fixture.yml:waster", "names the job")
        gate.assert_contains(result.combined, "'mem_peak_bytes'", "names the field")
        gate.assert_contains(result.combined, "must be a whole number", "says what was expected")
        gate.assert_not_contains(
            result.combined, "Traceback", "must be a named failure, never a stack trace"
        )

        # A missing field is the same class and must read the same way.
        baseline(d / "base.json", fresh_stamp())

        def drop_tier(data):
            del data["jobs"]["fixture.yml:heavy"]["tier"]

        edit_baseline(d / "base.json", drop_tier)
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a missing record field must refuse")
        gate.assert_contains(
            result.combined,
            "job 'fixture.yml:heavy' is missing required field 'tier'",
            "names job and field",
        )

        # `true` is the interesting one: bool is a subclass of int in Python, so a naive isinstance check would arithmetic it as 1 rather than reject it.
        baseline(d / "base.json", fresh_stamp())

        def boolean_count(data):
            data["jobs"]["fixture.yml:waster"]["observed_runs"] = True

        edit_baseline(d / "base.json", boolean_count)
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a boolean where a count belongs must refuse")
        gate.assert_contains(result.combined, "'observed_runs'", "names the field")
        gate.log_pass("a malformed record is refused by job name and field name, not by traceback")


IS_PRISTINE_PY = """import importlib.util
import pathlib
import sys

# THE SUBJECT'S OWN DIRECTORY, because `_cipath` is a SIBLING module and only a path
# INVOCATION puts that directory on `sys.path[0]`. `spec_from_file_location` does not,
# so once the 81 quality entry points started routing their `.ci` hop through
# `import _cipath` (W7 P4), every by-path probe of one of them began dying with
# `ModuleNotFoundError: No module named '_cipath'` before reaching its assertion.
# Measured 2026-09-08: 5 of the 24 cases in this file, all five for that reason.
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))

spec = importlib.util.spec_from_file_location("check_runner_advice", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

print(module.is_pristine({"format": 1, "refreshed_at": None, "jobs": {}}))
print(module.is_pristine({"format": 2, "refreshed_at": None, "jobs": {}}))
print(module.is_pristine({"refreshed_at": None, "jobs": {}}))
"""


def test_is_pristine_requires_the_format(gate):
    """The format clause inside is_pristine is redundant when the predicate is
    reached through load_baseline, so no end-to-end fixture can pin it. Driven
    directly here instead, rather than left as a claim in a comment."""
    result = run_inline(gate, IS_PRISTINE_PY)
    if result.rc != 0:
        gate.log_fail(
            "the is_pristine probe did not run at all (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )
    lines = result.out.splitlines()
    gate.assert_eq(len(lines), 3, "the probe must print exactly three verdicts: %r" % result.out)
    gate.assert_eq(lines[0], "True", "the committed shape is pristine")
    gate.assert_eq(lines[1], "False", "a format this gate cannot read is never pristine")
    gate.assert_eq(lines[2], "False", "an unversioned file is never pristine")
    gate.log_pass("is_pristine requires the format it can read, not only the shape")


REFRESH_UNREADABLE_PY = """import importlib.util
import pathlib
import pathlib
import sys

# THE SUBJECT'S OWN DIRECTORY, because `_cipath` is a SIBLING module and only a path
# INVOCATION puts that directory on `sys.path[0]`. `spec_from_file_location` does not,
# so once the 81 quality entry points started routing their `.ci` hop through
# `import _cipath` (W7 P4), every by-path probe of one of them began dying with
# `ModuleNotFoundError: No module named '_cipath'` before reaching its assertion.
# Measured 2026-09-08: 5 of the 24 cases in this file, all five for that reason.
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))

spec = importlib.util.spec_from_file_location("check_runner_advice", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def exploded(*_a, **_k):
    raise AssertionError("the network was reached despite an unreadable format")


module.harvest = exploded
workflow_dir = pathlib.Path(sys.argv[3])
sys.exit(
    module.refresh(
        workflow_dir.parent, pathlib.Path(sys.argv[2]), workflow_dir, "main", "", 8
    )
)
"""


def test_refresh_refuses_an_unreadable_format(gate):
    """A refresh MERGES into the file it is given. A format it cannot read is a
    file whose meaning is unknown, so nothing may be written into it -- and the
    check runs before the network, so a refused refresh costs no API call."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        baseline(d / "base.json", fresh_stamp())
        (d / "base.json").write_text(
            (d / "base.json").read_text(encoding="utf-8").replace('"format": 1,', '"format": 2,'),
            encoding="utf-8",
        )
        before = digest(d / "base.json")
        result = run_inline(
            gate, REFRESH_UNREADABLE_PY, os.fspath(d / "base.json"), os.fspath(d / "wf")
        )
        after = digest(d / "base.json")
        gate.assert_exit_code(
            1,
            result.rc,
            "a refresh onto an unreadable format must refuse (output: %s)" % result.combined,
        )
        gate.assert_contains(result.combined, "REFUSING TO REFRESH", "says what it declined to do")
        gate.assert_contains(result.combined, "declares format 2", "names the format it found")
        gate.assert_not_contains(
            result.combined, "the network was reached", "must refuse BEFORE spending an API call"
        )
        gate.assert_eq(after, before, "the baseline must be byte-identical after a refused refresh")
        gate.log_pass(
            "a refresh onto an unreadable format refuses before the network and touches nothing"
        )


REFRESH_PARTIAL_PY = """import importlib.util
import pathlib
import pathlib
import sys

# THE SUBJECT'S OWN DIRECTORY, because `_cipath` is a SIBLING module and only a path
# INVOCATION puts that directory on `sys.path[0]`. `spec_from_file_location` does not,
# so once the 81 quality entry points started routing their `.ci` hop through
# `import _cipath` (W7 P4), every by-path probe of one of them began dying with
# `ModuleNotFoundError: No module named '_cipath'` before reaching its assertion.
# Measured 2026-09-08: 5 of the 24 cases in this file, all five for that reason.
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))

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
"""


def test_refresh_refuses_a_partial_harvest(gate):
    """ALL OR NOTHING. This is what keeps the pristine exception honest: if a
    harvest could write 2 jobs, "seeded" would stop meaning "enforceable" and the
    gate would refuse every run afterwards with no way back."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        (d / "base.json").write_text(
            '{"format": 1, "refreshed_at": null, "jobs": {}}\n', encoding="utf-8"
        )
        before = digest(d / "base.json")
        result = run_inline(
            gate, REFRESH_PARTIAL_PY, os.fspath(d / "base.json"), os.fspath(d / "wf")
        )
        after = digest(d / "base.json")
        gate.assert_exit_code(
            1, result.rc, "a harvest below the floor must refuse (output: %s)" % result.combined
        )
        gate.assert_contains(
            result.combined, "harvest yielded 2 job(s)", "says exactly what it found"
        )
        gate.assert_contains(
            result.combined, "baseline left untouched", "says what it did about it"
        )
        gate.assert_eq(after, before, "the baseline must be byte-identical after a refused harvest")
        gate.log_pass("a partial harvest is refused and leaves the file untouched")


def test_stale_baseline_fails(gate):
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-slim")
        baseline(d / "base.json", "2024-01-01T00:00:00Z")
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a baseline older than the age limit must fail")
        gate.assert_contains(result.combined, "the baseline itself is stale", "names the staleness")

        # A stamp that is PRESENT but not a date must not read as "fresh". This is the staleness path's own failure; a stamp that is missing entirely is caught one layer earlier by the structural validator, which is asserted separately in test_pristine_shape_is_exact.
        def bad_stamp(data):
            data["refreshed_at"] = "some time last week"

        edit_baseline(d / "base.json", bad_stamp)
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(1, result.rc, "a baseline whose refreshed_at is not a date must fail")
        gate.assert_contains(
            result.combined, "missing or unparseable", "says the stamp itself is the problem"
        )
        gate.log_pass("a stale or unparseably-stamped baseline fails rather than being trusted")


def test_empty_workflow_dir_refuses(gate):
    with harness.temp_dir() as d:
        (d / "wf").mkdir(parents=True, exist_ok=True)
        baseline(d / "base.json", fresh_stamp())
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            1, result.rc, "a workflow directory with no parseable jobs must refuse"
        )
        gate.assert_contains(
            result.combined, "CANNOT READ THE WORKFLOWS", "refuses a verdict instead of guessing"
        )
        gate.log_pass("zero parsed job/runs-on pairs refuses rather than passing vacuously")


# --------------------------------------------------------------------------- awk / python coherence, and the trust rule they share. ---------------------------------------------------------------------------


def synth_tsv(out, tier, cceil, mceil, label, src, hint, n, cpu, mem, env: str = "") -> None:
    """`synth_tsv <out> <tier> <cpu_ceil> <mem_ceil> <label> <src> <hint> <samples>
    <cpu_milli> <mem_base> [env]`.

    The schema is sampler-linux.sh's, field for field:
      #META  tier cpu_milli mem_bytes interval_s start_ms runner_label cpu_src mem_src
             container_hint runner_env
      S      t_ms cpu_milli mem_bytes rx_bytes   tx_bytes disk_ws_kb   disk_tmp_kb
    RAM is walked by one byte per sample so the degenerate-series finding (all readings identical) does not fire on a synthetic capture. `env` defaults to empty, which writes a 10-field META -- the pre-2026-08-09 shape, kept as a fixture so the back-compat default is exercised rather than assumed.
    """
    t = 1700000000000
    head = ["#META", str(tier), str(cceil), str(mceil), "10", str(t), label, src, src, hint]
    if env:
        head.append(env)
    lines = ["\t".join(head)]
    for i in range(1, int(n) + 1):
        t += 10000
        lines.append(
            "\t".join(["S", str(t), str(cpu), str(int(mem) + i), "100", "200", "1000", "1000"])
        )
    pathlib.Path(out).write_text("".join(line + "\n" for line in lines), encoding="utf-8")


CLASSIFY_PY = """import importlib.util
import pathlib
import sys

# THE SUBJECT'S OWN DIRECTORY, because `_cipath` is a SIBLING module and only a path
# INVOCATION puts that directory on `sys.path[0]`. `spec_from_file_location` does not,
# so once the 81 quality entry points started routing their `.ci` hop through
# `import _cipath` (W7 P4), every by-path probe of one of them began dying with
# `ModuleNotFoundError: No module named '_cipath'` before reaching its assertion.
# Measured 2026-09-08: 5 of the 24 cases in this file, all five for that reason.
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))

spec = importlib.util.spec_from_file_location("check_runner_advice", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.classify(module.parse_row(sys.argv[2])))
"""


def run_report_awk(gate, d, name, args):
    """`awk -v wall_s=... -f report.awk <tsv>`, returning (result, machine-row-path).

    The sample count is `args[6]`: the twin reads its 7th positional after the shift, over the same `tier cceil mceil label src hint SAMPLES cpu mem` tail.
    """
    awk = harness.require_tool("awk", "install gawk or mawk; report.awk is an awk program")
    if not REPORT_AWK.is_file():
        gate.log_fail("the real report.awk is missing: %s" % REPORT_AWK_REL)
    tsv = d / ("%s.tsv" % name)
    machine = d / ("%s.row" % name)
    synth_tsv(tsv, *args)
    samples = int(args[6])
    result = harness.run(
        [
            awk,
            "-v",
            "wall_s=%d" % (samples * 10),
            "-v",
            "job=%s" % name,
            "-v",
            "machine_file=%s" % machine,
            "-f",
            os.fspath(REPORT_AWK),
            os.fspath(tsv),
        ]
    )
    (d / ("%s.md" % name)).write_text(result.out, encoding="utf-8")
    return result, machine


def assert_parity(gate, d, name, want, *args) -> None:
    """`assert_parity <dir> <name> <expected-verdict> <synth_tsv args...>`."""
    result, machine = run_report_awk(gate, d, name, args)
    gate.assert_exit_code(
        0,
        result.rc,
        "report.awk must produce a clean profile for '%s' (output: %s)" % (name, result.out),
    )
    if not machine.is_file() or machine.stat().st_size == 0:
        gate.log_fail("report.awk wrote no machine row for '%s'" % name)

    row = machine.read_text(encoding="utf-8").strip("\n")
    awk_verdict = row.rsplit("verdict=", 1)[-1]
    gate.assert_eq(awk_verdict, want, "report.awk's verdict for '%s'" % name)
    probe = run_inline(gate, CLASSIFY_PY, row)
    if probe.rc != 0:
        gate.log_fail(
            "classify() could not be driven for '%s' (rc=%s): %s"
            % (name, harness.describe_exit(probe.rc), probe.combined)
        )
    gate.assert_eq(
        probe.out.strip("\n"),
        awk_verdict,
        "classify() must reproduce report.awk's verdict for '%s' (row: %s)" % (name, row),
    )


def test_awk_and_python_agree_on_the_verdict(gate):
    """THE COHERENCE CASE. Two implementations of the same thresholds, in two
    languages, in two files. The panel's advisory and this gate's verdict are only the same claim for as long as these agree, and nothing else in the tree
    would notice them drifting apart."""
    with harness.temp_dir() as d:
        assert_parity(
            gate,
            d,
            "move",
            "MOVE_TO_SLIM",
            "PROC_HOST",
            4000,
            16000000000,
            "ubuntu-latest",
            "PROC_HOST",
            "HOST",
            12,
            200,
            943718400,
        )
        assert_parity(
            gate,
            d,
            "keepcpu",
            "KEEP",
            "PROC_HOST",
            4000,
            16000000000,
            "ubuntu-latest",
            "PROC_HOST",
            "HOST",
            12,
            3200,
            943718400,
        )
        assert_parity(
            gate,
            d,
            "slimfit",
            "SLIM_FIT",
            "CGROUP_V2",
            1000,
            5368709120,
            "ubuntu-slim",
            "CGROUP_V2",
            "CONTAINER",
            30,
            400,
            1073741824,
        )
        gate.log_pass(
            "report.awk and classify() reach the same verdict on MOVE, KEEP and SLIM_FIT profiles"
        )


def advise_once(gate, d, name, *args):
    """`advise_once <dir> <name> <synth_tsv args...>` -> `(advisory, row)`.

    The twin sets two globals, `ADVISORY` and `ROW`; a Python function can hand both back, which is the only difference.
    """
    result, machine = run_report_awk(gate, d, name, args)
    gate.assert_exit_code(0, result.rc, "report.awk must produce a clean profile for '%s'" % name)
    advisory = ""
    for line in result.out.splitlines():
        if line.startswith("**Advisory:** "):
            advisory = line[len("**Advisory:** ") :]
            break
    row = machine.read_text(encoding="utf-8").strip("\n") if machine.is_file() else ""
    return advisory, row


def test_github_hosted_vm_is_trusted(gate):
    """THE 2026-08-09 REGRESSION, as a test. The first real harvest seeded ZERO
    jobs because every ubuntu-latest row came back verdict=NONE: PROC_HOST with
    no runner-label, which the advisor refused to attribute. A github-hosted VM
    with no container fingerprint is an exclusive machine, so its /proc numbers
    ARE the job's."""
    with harness.temp_dir() as d:
        shape = ("PROC_HOST", 4000, 16000000000, "unknown", "PROC_HOST", "HOST", 12, 200, 943718400)

        advisory, row = advise_once(gate, d, "hosted", *shape, "github-hosted")
        gate.assert_contains(
            advisory, "MOVE TO ubuntu-slim", "a hosted VM that fits slim must be told to move"
        )
        gate.assert_contains(
            advisory,
            "github-hosted VM (label unknown)",
            "the prose names what it trusted, and admits the label is unknown",
        )
        gate.assert_contains(row, "env=github-hosted", "the row carries the evidence")
        gate.assert_contains(
            row, "verdict=MOVE_TO_SLIM", "the row carries a real verdict, not NONE"
        )

        # CONTROL 1: identical capture, no github-hosted evidence.
        advisory, row = advise_once(gate, d, "selfhosted", *shape, "self-hosted")
        gate.assert_contains(
            advisory,
            "a VM cannot be told from a container",
            "a self-hosted PROC_HOST box still says nothing",
        )
        gate.assert_contains(row, "verdict=NONE", "and its row stays NONE")

        # CONTROL 2: github-hosted, but the PID 1 fingerprint says container. The fingerprint must win, or slim's container gets sized off host numbers.
        #
        # The second assertion is the load-bearing one and looks pedantic on
        # purpose. verdict=NONE alone does NOT pin the fingerprint clause inside
        # hosted_vm: the older PROC_HOST-plus-container arm refuses this input independently, so deleting the clause leaves the verdict unchanged and a verdict-only control passes over the mutation (measured, not assumed). WHICH arm spoke does change, so the wording is what proves the clause is still there -- and the clause is worth keeping because it makes the trust condition
        # self-contained rather than dependent on the order of the arms below it.
        advisory, row = advise_once(
            gate,
            d,
            "hostedcontainer",
            "PROC_HOST",
            4000,
            16000000000,
            "unknown",
            "PROC_HOST",
            "CONTAINER",
            12,
            200,
            943718400,
            "github-hosted",
        )
        gate.assert_contains(row, "verdict=NONE", "a container fingerprint beats github-hosted")
        gate.assert_contains(
            advisory,
            "a VM cannot be told from a container",
            "the trust arm must exclude containers itself, not lean on the arm below it",
        )

        # CONTROL 3: a pre-2026-08-09 TSV with no env field at all must keep the OLD behaviour rather than being retroactively trusted.
        advisory, row = advise_once(gate, d, "legacy", *shape)
        gate.assert_contains(row, "env=unknown", "a 10-field META defaults to the untrusted side")
        gate.assert_contains(
            row, "verdict=NONE", "and an archived capture is not retroactively believed"
        )
        gate.log_pass(
            "a github-hosted VM is trusted; self-hosted, containers and legacy captures are not"
        )


MERGE_ROWS_PY = """import importlib.util
import pathlib
import sys

# THE SUBJECT'S OWN DIRECTORY, because `_cipath` is a SIBLING module and only a path
# INVOCATION puts that directory on `sys.path[0]`. `spec_from_file_location` does not,
# so once the 81 quality entry points started routing their `.ci` hop through
# `import _cipath` (W7 P4), every by-path probe of one of them began dying with
# `ModuleNotFoundError: No module named '_cipath'` before reaching its assertion.
# Measured 2026-09-08: 5 of the 24 cases in this file, all five for that reason.
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))

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
"""


def test_harvester_skip_rule(gate):
    """merge_rows is the only place a row becomes a baseline number, so the skip
    rule is driven directly rather than inferred from a --refresh run."""
    result = run_inline(gate, MERGE_ROWS_PY)
    if result.rc != 0:
        gate.log_fail(
            "the merge_rows probe did not run at all (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )
    lines = result.out.splitlines()
    gate.assert_eq(len(lines), 3, "the probe must print exactly three lines: %r" % result.out)
    gate.assert_eq(
        lines[0], "hosted,noenv", "only the attributable, finding-free rows may enter the baseline"
    )
    gate.assert_eq(
        lines[1], "unknown", "a row with no env= parses, defaulting to the untrusted side"
    )
    gate.assert_eq(
        lines[2], "github-hosted", "the record keeps the evidence classify() re-derives from"
    )
    gate.log_pass(
        "the harvester accepts github-hosted PROC_HOST rows and skips NONE, starved and leaked ones"
    )


def test_hosted_vm_record_fires_the_gate(gate):
    """END TO END, and the reason classify() had to learn about env: an
    ubuntu-latest job's record carries runner_label=unknown, so without the env
    evidence the gate would re-derive NONE and quietly fire on nothing -- the
    same blindness, one layer down."""
    with harness.temp_dir() as d:
        workflow(d / "wf", "ubuntu-latest")
        baseline(d / "base.json", fresh_stamp())

        def unlabelled_hosted(data):
            rec = data["jobs"]["fixture.yml:waster"]
            rec["runner_label"] = "unknown"
            rec["env"] = "github-hosted"

        edit_baseline(d / "base.json", unlabelled_hosted)
        (d / "allow").write_text("", encoding="utf-8")
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            1, result.rc, "an unlabelled github-hosted record that fits slim must fail"
        )
        gate.assert_contains(result.combined, "fixture.yml:waster", "names the job")

        # CONTROL: same record, evidence removed. The gate must go quiet rather than guess from numbers nobody can attribute.
        def drop_evidence(data):
            data["jobs"]["fixture.yml:waster"]["env"] = "unknown"

        edit_baseline(d / "base.json", drop_evidence)
        result = run_gate(gate, d / "base.json", d / "wf", d / "allow")
        gate.assert_exit_code(
            0,
            result.rc,
            "without github-hosted evidence the same record must be silent (output: %s)"
            % result.combined,
        )
        gate.log_pass(
            "an unlabelled github-hosted record fires the gate; the same record without the "
            "evidence does not"
        )


VALIDATE_BLOCKERS_SH = """
        source "$1"
        declare -A entries=() reasons=()
        parse_blockered_list "$2" entries reasons
        verify_all_blockers "$2" reasons
    """


def run_validator(gate, listfile) -> harness.RunResult:
    bash = harness.require_tool("bash", "install bash; the shared validator IS a bash library")
    if not VALIDATOR.is_file():
        gate.log_fail("the shared BLOCKER validator is missing: %s" % VALIDATOR_REL)
    return harness.run(
        [bash, "-c", VALIDATE_BLOCKERS_SH, "_", os.fspath(VALIDATOR), os.fspath(listfile)]
    )


def test_real_allowlist_blockers_are_substantive(gate):
    """The PROSE bar is the shared validator's, applied to the real file here so
    the banned-phrase list lives in exactly one place."""
    with harness.temp_dir() as d:
        if not REAL_ALLOWLIST.is_file():
            gate.log_fail(
                "the real allowlist is missing: %s -- this case would otherwise validate "
                "nothing and pass" % REAL_ALLOWLIST_REL
            )
        result = run_validator(gate, REAL_ALLOWLIST)
        gate.assert_exit_code(
            0,
            result.rc,
            "every BLOCKER in %s must be substantive (output: %s)"
            % (REAL_ALLOWLIST, result.combined),
        )

        # CONTROL: the same machinery on a planted low-effort reason must reject it, so the pass above is the validator working rather than the validator being pointed at nothing.
        (d / "bad").write_text("# BLOCKER: tbd\nfixture.yml:waster\n", encoding="utf-8")
        result = run_validator(gate, d / "bad")
        gate.assert_exit_code(1, result.rc, "a low-effort BLOCKER must be rejected")
        gate.assert_contains(
            result.combined, "low-effort placeholder", "uses the shared validator's own wording"
        )
        gate.log_pass(
            "the real allowlist's BLOCKERs pass the shared validator, which can still fire"
        )


def test_real_tree_seam_free(gate):
    """THE LOAD-BEARING CASE. No env seams: the real baseline, the real
    .github/workflows, the real allowlist. Two outcomes are correct here and the test asserts WHICH one it got rather than accepting any exit code: once the baseline is seeded the gate passes, and until it is, the vacuity floor must refuse. Anything else -- a crash, a silent 0 over an empty baseline -- fails
    this case."""
    python3 = require_python(gate)
    # The seams must be ABSENT, not merely unset in this process: `harness.run` overlays os.environ, so a `RUNNER_ADVICE_*` inherited from an outer shell would silently make this case seam-BEARING and its name a lie.
    seamless = {k: v for k, v in os.environ.items() if not k.startswith("RUNNER_ADVICE_")}
    result = harness.run([python3, os.fspath(GATE)], env=seamless, env_replace=True)
    gate.assert_exit_code(
        0,
        result.rc,
        "the real tree must not fail: it is either pristine or seeded (output: %s)"
        % result.combined,
    )
    if "Runner sizing (bootstrap)" in result.combined:
        # PRISTINE. Exit 0 is only acceptable WITH the warning: a silent pass over an unseeded baseline is the exact shape this gate exists to prevent, so the annotation is asserted, not tolerated.
        gate.assert_contains(
            result.combined,
            "::warning title=Runner sizing (bootstrap)::",
            "a pristine real tree must annotate, not pass quietly",
        )
        gate.assert_contains(result.combined, "UNENFORCED", "and must say the word")
        gate.log_pass(
            "the real tree is pristine and says so loudly (expected until the harvest lands)"
        )
    else:
        gate.assert_contains(
            result.combined,
            "sit on the runner their own profile justifies",
            "a seeded real tree must print the count it compared",
        )
        gate.assert_not_contains(
            result.combined, "UNENFORCED", "a seeded baseline must not claim to be unenforced"
        )
        gate.log_pass("the real tree passes seam-free with a seeded baseline")
    if "fixture.yml" in result.combined:
        gate.log_fail("this test's fixture names leaked into the real run: a seam is not isolating")
