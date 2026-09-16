"""Port of `.ci/scripts/test/gates/test-scrub-sentinel-empty.sh`.

Subject: `scripts/dev/scrub-sentinel.sh`. Regression test for its empty-prefix
hang.

Before commit 27e9a49ab the dry-run plan loop called `aws s3 ls --recursive`
inside `count="$(... | wc -l)"`. `aws s3 ls` returns exit 1 when the prefix is
empty, and `set -eo pipefail` made the whole script abort right after `count=0`
was assigned -- silently, with the operator seeing only the "sentinel: absent"
line and no exit message. This pins the fix: a dry-run against a guaranteed-empty
version must print the cli plan AND exit 0, regardless of whether the underlying
R2 list call succeeds.

THE TOOL-ABSENT BRANCH IS TRANSCRIBED, NOT IMPROVED, AND THAT IS DELIBERATE.
`harness.require_tool` would refuse loudly on a machine with no `aws`, which is
this directory's standing rule and is the RIGHT rule for a case that could
otherwise be checked. It is the wrong rule HERE for one reason: the twin does not
refuse, it reports NOT VERIFIED and exits 0, and `test_twin_parity.py` compares
VERDICTS. A port that refused where the twin passes would diverge on every
developer machine without `aws` and the divergence would say nothing about the
subject.

So the branch is copied exactly, including the half that matters most: under
`CI` a missing `aws` is a FAILURE, because a missing tool there is a broken lane
and a suite that quietly passes over it is the gate-that-cannot-fail shape this
repo keeps paying for. Locally it is announced as NOT VERIFIED rather than
skipped silently, which is what keeps the absence visible.

MEASURED 2026-08-27 by the twin, and reproduced here 2026-09-09: without `aws`,
`scrub-sentinel.sh` exits 1 with `Required command 'aws' is not available` on
stderr and prints nothing on stdout, and the suite reported "dry-run must succeed
even with bad credentials: expected 0, got 1" -- indistinguishable from the
pipefail bug coming back. Saying WHICH one it is is the whole point of the branch.

NOT A REAL-TREE TWIN. `gate-test:scrub-sentinel-empty` carries no `tree:` claim in
`gates.lock.json`, so `REAL_TREE_TWIN` is deliberately NOT set: `real_tree_admission`
refuses an over-claim, because an opt-in that costs nothing to declare stops
meaning anything. The subject is executed read-only against an unreachable
endpoint and writes nothing.
"""

import os
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-scrub-sentinel-empty.sh"

ROOT = paths.repo_root()
SUBJECT = ROOT / "scripts" / "dev" / "scrub-sentinel.sh"
VERSION = "v9.99.99"

# Credentials that cannot work, on an endpoint that cannot resolve. The point is
# an EMPTY/unreachable prefix, which is what the regression is about.
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
    """The subject's dry run, streams merged as the twin merges them."""
    if not SUBJECT.is_file():
        gate.log_fail(
            "%s is gone; both cases below drive it and would then be asserting about "
            "nothing" % paths.relative_to_root(SUBJECT)
        )
    bash = harness.require_tool("bash", "install bash; the subject is a shell script")
    return harness.run([bash, str(SUBJECT), VERSION], env=dict(BAD_CREDENTIALS), timeout=600)


# ---------------------------------------------------------------------------


def test_dry_run_completes_with_no_credentials(gate):
    """No R2 credentials means `aws s3api list-objects-v2` errors, the helper
    returns 0, and the dry-run plan emits "objects: 0" for the cli product.

    CRITICALLY: the script must reach the "dry-run: pass --execute" final line. If
    pipefail kills it after the count assignment there is no exit message, and
    that silence is the whole bug.
    """
    if not tool_gate(gate):
        return
    result = dry_run(gate)
    gate.assert_exit_code(0, result.rc, "dry-run must succeed even with bad credentials")
    gate.assert_contains(
        result.combined, "s3://rediacc-releases/cli/%s/" % VERSION, "cli plan line printed"
    )
    gate.assert_contains(
        result.combined, "dry-run: pass --execute", "script reached its final exit message"
    )
    gate.log_pass("empty-prefix dry-run completes without hanging")


def test_dry_run_emits_zero_object_count(gate):
    """Cosmetic but important: the operator relies on the "objects: N" count to
    decide whether the scrub is safe. If the helper falls back to a malformed
    value (e.g. "None"), the count must still normalise to 0."""
    if not tool_gate(gate):
        return
    result = dry_run(gate)
    # One product (cli), one count line.
    zero = len([line for line in result.combined.splitlines() if "objects: 0" in line])
    gate.assert_eq(zero, 1, "objects: 0 emitted for the cli product")
    gate.log_pass("object count normalises to 0 on empty/unreachable prefix")


def test_the_tool_branch_is_announced_and_not_a_silent_skip(gate):
    """ADDED BY THE PORT, and it is the case that keeps the branch above honest.

    Both real cases return early when `aws` is absent, which is exactly the shape
    a reader should distrust: two functions that assert nothing and a green run.
    The refusal that makes it legitimate is the CI half, and nothing else here
    exercises it. This drives `tool_gate`'s decision table directly -- present,
    absent-locally, absent-in-CI -- so the branch cannot silently become
    "absent is always fine".

    The CI arm is driven by SETTING the variable rather than by reading whatever
    the environment happens to hold, because on a developer machine `CI` is unset
    and the arm that must never pass would never be reached.
    """
    gate.assert_eq(SUBJECT.is_file(), True, "the subject must exist even when the cases cannot run")
    previous = os.environ.get("CI")
    os.environ["CI"] = "1"
    try:
        fired = False
        try:
            # `tool_gate` calls `gate.log_fail`, which RAISES. A separate harness
            # is used so the refusal is observed rather than failing this case.
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
