"""Port of `.ci/scripts/test/gates/test-slim-timeout.sh`, retired in W7 P5.

Both-ways test for CHECK 3 in `.ci/scripts/security/check-workflow-gates.sh`.

WHY THIS CLASS NEEDS A GATE AT ALL: ubuntu-slim is a 1-vCPU runner with a HARD 15-minute job cap enforced by the platform. A job that reaches it is not failed, it is CANCELLED with no failed step -- which reads as neither pass nor fail. CI Complete is poisoned, the watchdog has no error to classify, and the log's last line is a successful post-step. quality-security hit this twice
in three runs during the 0722-1 wave, and the only clue was a job that "just stopped". An explicit timeout-minutes below the cap converts that silent kill into an ordinary timeout failure naming the step that hung.

Both directions matter:
  - Too quiet: a slim job with no timeout, or one whose declared timeout is above
    the cap, keeps the silent-cancellation failure mode.
  - Too loud: ubuntu-latest jobs (no such cap) and matrix-expression runners (not
    resolvable from YAML) must NOT be reported.

The check is driven against fixture trees via `WORKFLOWS_DIR`, so every case but the last is independent of the real `.github/workflows` census.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

CHECK = paths.from_root(".ci", "scripts", "security", "check-workflow-gates.sh")


def run_check(gate, directory, *, coverage: str = "true") -> harness.RunResult:
    """CHECK 3 over `directory`.

    `SLIM_TIMEOUT_REQUIRE_COVERAGE` defaults to true here: these fixtures exist to exercise CHECK 3, so a tree with nothing to check must read as BLIND even though the real script relaxes that for OTHER checks' fixture trees.
    """
    if not CHECK.is_file():
        gate.log_fail("subject under test is missing: %s" % CHECK)
    return harness.run(
        ["bash", str(CHECK)],
        env={
            "CI": "true",
            "WORKFLOWS_DIR": str(directory),
            "SLIM_TIMEOUT_REQUIRE_COVERAGE": coverage,
        },
    )


def write_job(directory, name: str, job_id: str, runs_on: str, timeout: str | None = None) -> None:
    """A minimal single-job workflow.

    No `needs:` and no reusable-workflow call, so CHECK 1 and CHECK 2 are satisfied trivially and only CHECK 3 can decide the verdict.
    """
    lines = ["name: %s" % name, "on: push", "jobs:", "  %s:" % job_id, "    runs-on: %s" % runs_on]
    if timeout is not None:
        lines.append("    timeout-minutes: %s" % timeout)
    lines += ["    steps:", "      - run: echo hi"]
    (directory / ("%s.yml" % name)).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_slim_without_timeout_fails(gate, tmp_path):
    write_job(tmp_path, "wf", "slim_job", "ubuntu-slim")
    result = run_check(gate, tmp_path)
    gate.assert_exit(1, result, "no-timeout slim job must fail")
    gate.assert_contains(
        result.combined, "without timeout-minutes", "names the missing declaration"
    )
    gate.assert_contains(result.combined, "slim_job", "names the offending job")
    gate.log_pass("slim job with no timeout-minutes is reported")


def test_slim_over_ceiling_fails(gate, tmp_path):
    write_job(tmp_path, "wf", "slow_job", "ubuntu-slim", "30")
    result = run_check(gate, tmp_path)
    gate.assert_exit(1, result, "timeout-minutes: 30 on slim must fail")
    gate.assert_contains(result.combined, "above the 14-minute ceiling", "explains the ceiling")
    # The fix is a different runner, not a bigger number. If this wording ever drifts to "raise the timeout", the gate is teaching the wrong lesson.
    gate.assert_contains(result.combined, "ubuntu-latest", "points at the real fix")
    gate.log_pass("slim job with a timeout above the ceiling is reported")


def test_slim_at_ceiling_passes(gate, tmp_path):
    write_job(tmp_path, "wf", "ok_job", "ubuntu-slim", "14")
    result = run_check(gate, tmp_path)
    gate.assert_exit(0, result, "timeout-minutes: 14 on slim must pass")
    gate.log_pass("slim job exactly at the ceiling passes")


def test_non_slim_runner_ignored(gate, tmp_path):
    # A slim job is required or the anti-vacuity guard fires, so pair the untimed latest job with a compliant slim one.
    write_job(tmp_path, "wf1", "fat_job", "ubuntu-latest")
    write_job(tmp_path, "wf2", "thin_job", "ubuntu-slim", "5")
    result = run_check(gate, tmp_path)
    gate.assert_exit(0, result, "ubuntu-latest has no 15-minute cap, so no timeout is required")
    gate.assert_not_contains(result.combined, "fat_job", "must not report a non-slim job")
    gate.log_pass("ubuntu-latest without a timeout is NOT reported")


def test_matrix_runner_ignored(gate, tmp_path):
    write_job(tmp_path, "wf1", "matrix_job", "${{ matrix.runner }}")
    write_job(tmp_path, "wf2", "thin_job", "ubuntu-slim", "5")
    result = run_check(gate, tmp_path)
    gate.assert_exit(0, result, "an unresolvable runner label cannot be judged here")
    gate.assert_not_contains(result.combined, "matrix_job", "must not report an expression runner")
    gate.log_pass("matrix-expression runner is NOT reported")


def test_no_slim_jobs_is_blind(gate, tmp_path):
    write_job(tmp_path, "wf", "fat_job", "ubuntu-latest")
    result = run_check(gate, tmp_path)
    # Nothing to check is a failure, not a pass -- the same anti-vacuity rule the rest of this file follows. A renamed runner label must not silently turn this gate into a no-op that still reports success.
    gate.assert_exit(1, result, "zero slim jobs must not report success")
    gate.assert_contains(result.combined, "this check is blind", "says why it refused")
    gate.log_pass("a tree with zero slim jobs fails as blind, not green")


def test_real_workflows_pass(gate):
    """The seam-free case: no WORKFLOWS_DIR, so the real census is what is judged.

    A READ of `.github/workflows` and nothing else. It writes nowhere, which is what keeps this module admissible to the parity driver.
    """
    result = harness.run(["bash", str(CHECK)], env={"CI": "true"})
    gate.assert_exit(0, result, "every real ubuntu-slim job declares a compliant timeout")
    gate.log_pass("the repo's own .github/workflows satisfies the rule")
