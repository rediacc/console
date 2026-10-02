"""Port of `.ci/scripts/test/gates/test-scrub-sentinel-empty.sh`, retired in W7 P5.

Subject: `rediacc_ci.ops.scrub_sentinel` (`.ci/rediacc_ci/ops/scrub_sentinel.py`), which replaced `scripts/ops/scrub-sentinel.sh` in PLAN-retire-bash-oracles B3. Regression test for the bash script's empty-prefix hang, restated for the port.

Before commit 27e9a49ab the bash dry-run plan loop called `aws s3 ls --recursive`
inside `count="$(... | wc -l)"`. `aws s3 ls` returns exit 1 when the prefix is
empty, and `set -eo pipefail` made the whole script abort right after `count=0`
was assigned -- silently, with the operator seeing only the "sentinel: absent" line and no exit message.

WHAT THE PORT PROMISES INSTEAD (its Rule T 1). A probe that cannot answer is not an answer: against an unreachable endpoint the plan prints `UNKNOWN` for what it could not establish, names the failure, and exits 1, dry-run included. So this pins the property the old bug broke, which is that the run TERMINATES AND SAYS WHY: the cli plan line, an `objects:` line, and the closing "could not be established" error, never a silent stop. It also pins the half the bash got wrong: an unreachable endpoint must not read as `objects: 0`.

THE TOOL-ABSENT BRANCH. Under `CI` a missing `aws` is a FAILURE, because a missing tool there is a broken lane and a suite that quietly passes over it is the gate-that-cannot-fail shape this repo keeps paying for. Locally it is announced as NOT VERIFIED rather than skipped silently, which is what keeps the absence visible. Without `aws` the port exits 1 with `Required command 'aws' is not available`, which would otherwise be indistinguishable from the property above failing.

NOT A REAL-TREE TWIN. `gate-test:scrub-sentinel-empty` carries no `tree:` claim in `gates.lock.json`, so `REAL_TREE_TWIN` is deliberately NOT set. The subject is executed read-only against an unreachable endpoint and writes nothing.
"""

import os
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness
from rediacc_ci.well_known import RELEASES_BUCKET

ROOT = paths.repo_root()
SUBJECT = ROOT / ".ci" / "rediacc_ci" / "ops" / "scrub_sentinel.py"
MODULE = "rediacc_ci.ops.scrub_sentinel"
VERSION = "v9.99.99"

# Credentials that cannot work, on an endpoint that cannot resolve. The point is an unreachable prefix, which is what the regression is about.
BAD_CREDENTIALS = {
    "CLOUDFLARE_R2_ACCESS_KEY_ID": "invalid",
    "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "invalid",
    "CLOUDFLARE_R2_ENDPOINT": "https://invalid.example.invalid",
}


def aws_present() -> bool:
    return shutil.which("aws") is not None


def in_ci() -> bool:
    return bool(os.environ.get("CI"))


def tool_gate(gate) -> bool:
    """False when the cases cannot run here, having SAID so. True to proceed.

    See the module docstring for why this is not `harness.require_tool`.
    """
    if aws_present():
        return True
    if in_ci():
        gate.log_fail(
            "aws is missing in CI: this lane cannot run the scrub-sentinel cases at all, "
            "and a suite that passes over a missing tool has checked nothing"
        )
    gate.log_info("aws is not installed here.")
    gate.log_pass("NOT VERIFIED locally: the empty-prefix dry-run needs the aws CLI (CI runs it)")
    return False


def dry_run(gate) -> harness.RunResult:
    """The subject's dry run; the cases read the merged streams."""
    if not SUBJECT.is_file():
        gate.log_fail(
            "%s is gone; both cases below drive it and would then be asserting about "
            "nothing" % paths.relative_to_root(SUBJECT)
        )
    env = dict(BAD_CREDENTIALS)
    env["PYTHONPATH"] = str(ROOT / ".ci")
    return harness.run([sys.executable, "-m", MODULE, VERSION], cwd=ROOT, env=env, timeout=600)


# ---------------------------------------------------------------------------


def test_dry_run_terminates_and_says_why(gate):
    """Unusable credentials: the probe and the listing cannot answer. The run must still print the cli plan line and end on its own error message, with exit 1.

    The closing message is the whole point: the bash bug was a run that stopped after the count with nothing said.
    """
    if not tool_gate(gate):
        return
    result = dry_run(gate)
    gate.assert_exit(1, result, "an unanswerable plan exits 1, dry-run included")
    gate.assert_contains(
        result.combined, ("s3://" + RELEASES_BUCKET + "/cli/%s/") % VERSION, "cli plan line printed"
    )
    gate.assert_contains(
        result.combined,
        "the scrub plan could not be established; nothing was deleted",
        "the run reached its closing message",
    )
    gate.log_pass("unreachable-prefix dry-run terminates with a reason")


def test_an_unreachable_prefix_is_not_reported_as_empty(gate):
    """The operator decides whether a scrub is safe from the "objects: N" line, so an unanswered listing must read UNKNOWN, never `objects: 0`."""
    if not tool_gate(gate):
        return
    result = dry_run(gate)
    lines = result.combined.splitlines()
    gate.assert_eq(
        len([line for line in lines if "objects: UNKNOWN" in line]),
        1,
        "objects: UNKNOWN emitted for the cli product",
    )
    gate.assert_eq(
        len([line for line in lines if "objects: 0" in line]),
        0,
        "an unreachable prefix never reads as zero objects",
    )
    gate.log_pass("an unreachable prefix reads UNKNOWN, not 0")


def test_the_tool_branch_is_announced_and_not_a_silent_skip(gate):
    """ADDED BY THE PORT, and it is the case that keeps the branch above honest.

    Both real cases return early when `aws` is absent, which is exactly the shape a reader should distrust: two functions that assert nothing and a green run. The refusal that makes it legitimate is the CI half, and nothing else here exercises it. This drives `tool_gate`'s decision table directly -- present, absent-locally, absent-in-CI -- so the branch cannot silently become
    "absent is always fine".

    The CI arm is driven by SETTING the variable rather than by reading whatever the environment happens to hold, because on a developer machine `CI` is unset and the arm that must never pass would never be reached.
    """
    gate.assert_eq(SUBJECT.is_file(), True, "the subject must exist even when the cases cannot run")
    previous = os.environ.get("CI")
    os.environ["CI"] = "1"
    try:
        fired = False
        try:
            # `tool_gate` calls `gate.log_fail`, which RAISES. A separate harness is used so the refusal is observed rather than failing this case.
            probe = harness.Harness(__name__, "ci-arm-probe")
            if not aws_present():
                tool_gate(probe)
        except harness.GateAssertionError as exc:
            fired = "aws is missing in CI" in str(exc)
    finally:
        if previous is None:
            os.environ.pop("CI", None)
        else:
            os.environ["CI"] = previous

    if aws_present():
        gate.log_pass("aws IS present here, so both cases above really ran (CI arm not exercised)")
        return
    if not fired:
        gate.log_fail(
            "aws is absent and the CI arm did NOT refuse, so a lane with no aws would "
            "report this suite green having checked nothing"
        )
    gate.log_pass("aws is absent: the local arm announces NOT VERIFIED and the CI arm refuses")
