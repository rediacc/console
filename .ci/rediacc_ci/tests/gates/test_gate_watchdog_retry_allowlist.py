"""Port of `.ci/scripts/test/gates/test-watchdog-retry-allowlist.sh`.

Unit test for the retry policy in `.ci/scripts/ci/watchdog-monitor.cjs` (issue #537).

WHAT BROKE. The failure classifier returns HTTP 402, so classifyFailure falls
back to `{ classification: 'transient', confidence: 0 }` on EVERY failure. The
retry branch only refused to retry on a CONFIDENT code-change verdict, so a
confidence-0 fallback always landed in the retry path. Net effect: every failure
in the repo, of every kind, was auto-retried on a judgment nobody made. That is
only defensible while somebody reads the log afterwards, and nobody does,
because the retry itself destroys it.

WHY A UNIT TEST AND NOT A MIRROR. This calls the exported decision and reads
WATCHDOG_RETRY_ALLOWLIST_PATTERNS out of the REAL watchdog-monitor.yml, so a
rename of a pattern or a quiet widening of the list fails here.

WHERE THE ALLOWLIST READER DIFFERS FROM THE TWIN, AND WHY THEY AGREE. The twin
runs `sed -n "s/^ *WATCHDOG_RETRY_ALLOWLIST_PATTERNS: *'\\(.*\\)'$/\\1/p"`, which
prints the capture of EVERY matching line; this module runs the same pattern as a
MULTILINE Python regex and takes the first match. The two answers are the same
string exactly while the workflow carries one such assignment, so this module
also asserts that the count is one rather than assuming it: a second assignment
would give the twin a two-line `$ALLOWLIST` (and therefore a broken `--patterns`
argument) while this side quietly used the first, and a divergence that only
shows up as a weird verdict is the kind this port exists not to introduce.

THE REFUSAL ON AN EMPTY ALLOWLIST IS KEPT AND MOVED. The twin exits 1 at load
time; a module-level `sys.exit` in a pytest file aborts COLLECTION for the whole
session, which would take out every other ported gate for a reason belonging to
this one. So the refusal fires inside each case instead, through `gate.log_fail`,
which is the same claim ("this could not be read, so nothing below was checked")
delivered where a reader can attribute it.

NO `xdist_group`. Every case shells out to a fresh `node -e`, writes nothing at
all, and reads two tracked files without touching them. Nothing is bound and no
module global is mutated.
"""

import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-watchdog-retry-allowlist.sh"

WATCHDOG = paths.from_root(".ci", "scripts", "ci", "watchdog-monitor.cjs")
CI_WORKFLOW = paths.from_root(".github", "workflows", "watchdog-monitor.yml")

ALLOWLIST_RE = re.compile(
    r"^ *WATCHDOG_RETRY_ALLOWLIST_PATTERNS: *'(.*)'$",
    re.MULTILINE,
)

# `verdict`, as the twin spells it: the exported decision, driven with every input explicit so no case depends on a default the module might change.
VERDICT_JS = """
const w = require(process.argv[1]);
const v = w.evaluateRetryEligibility({
  jobName: process.argv[2],
  classification: process.argv[3],
  confidence: Number(process.argv[4]),
  classifierAvailable: process.argv[5] === "1",
  isFailure: process.argv[7] !== "0",
  threshold: 0.8,
  retryAllowlistPatterns: process.argv[6].split(",").map(s => s.trim()).filter(Boolean),
  guardForced: process.argv[8] === "1",
});
process.stdout.write(v.retry ? "retry" : "no-retry");
"""

# `override_fired`. Same call, but reports whether the ALLOWLIST OVERRIDE specifically fired, rather than merely whether a retry happened. Without this a test cannot tell "retried because the allowlist beat the verdict" from "retried because the verdict was sub-threshold anyway", and those are different policies.
OVERRIDE_JS = """
const w = require(process.argv[1]);
const v = w.evaluateRetryEligibility({
  jobName: process.argv[2],
  classification: "code-change",
  confidence: 0.9,
  classifierAvailable: true,
  isFailure: true,
  threshold: 0.8,
  retryAllowlistPatterns: process.argv[3].split(",").map(s => s.trim()).filter(Boolean),
  guardForced: process.argv[4] === "1",
});
process.stdout.write(v.allowlistOverride === true ? "override" : "no-override");
"""

EMPTY_ALLOWLIST_JS = """
const w = require(process.argv[1]);
const v = w.evaluateRetryEligibility({
  jobName: "Tests + Infra / E2E Workers (fedora-43)",
  classification: "transient", confidence: 0, classifierAvailable: false,
  isFailure: true,
  threshold: 0.8, retryAllowlistPatterns: [],
});
process.stdout.write(v.retry ? "retry" : "no-retry");
"""

MISSING_IS_FAILURE_JS = """
const w = require(process.argv[1]);
const v = w.evaluateRetryEligibility({
  jobName: "Quality / Built-www Gates",
  classification: "transient", confidence: 0, classifierAvailable: false,
  threshold: 0.8, retryAllowlistPatterns: ["E2E"],
});
process.stdout.write(v.retry ? "retry" : "no-retry");
"""


class Policy:
    """The real allowlist, plus the two drivers the twin defines as functions."""

    def __init__(self, gate) -> None:
        self.gate = gate
        self.node = harness.require_tool(
            "node",
            "install Node 22 (the lane's setup-workspace step does this in CI)",
        )
        for path in (WATCHDOG, CI_WORKFLOW):
            if not path.is_file():
                gate.log_fail(
                    "%s is missing, so nothing below was checked -- a FAILURE and not a "
                    "pass" % paths.relative_to_root(path)
                )
        found = ALLOWLIST_RE.findall(CI_WORKFLOW.read_text(encoding="utf-8"))
        if not found:
            gate.log_fail(
                "could not read WATCHDOG_RETRY_ALLOWLIST_PATTERNS from %s -- every case "
                "below would then be asserting against an empty policy, which passes for "
                "the wrong reason" % paths.relative_to_root(CI_WORKFLOW)
            )
        if len(found) != 1:
            gate.log_fail(
                "%s carries %d WATCHDOG_RETRY_ALLOWLIST_PATTERNS assignments; the twin's "
                "sed would concatenate them onto separate lines and this reader takes the "
                "first, so the two sides would stop agreeing"
                % (paths.relative_to_root(CI_WORKFLOW), len(found))
            )
        self.allowlist = found[0]

    def _node(self, script: str, *argv: str) -> str:
        result = harness.run([self.node, "-e", script, str(WATCHDOG), *argv])
        if result.rc != 0:
            self.gate.log_fail(
                "the retry-policy probe did not run (rc=%d, stderr: %s)"
                % (result.rc, result.err.strip())
            )
        return result.out

    def verdict(
        self,
        job: str,
        classification: str,
        confidence: str,
        available: str,
        is_failure: str = "1",
        guard_forced: str = "0",
    ) -> str:
        """`verdict <job> <classification> <confidence> <available> [isFailure] [guardForced]`."""
        return self._node(
            VERDICT_JS,
            job,
            classification,
            confidence,
            available,
            self.allowlist,
            is_failure,
            guard_forced,
        )

    def override_fired(self, job: str, guard_forced: str = "0") -> str:
        return self._node(OVERRIDE_JS, job, self.allowlist, guard_forced)

    def down(self, job: str) -> str:
        """A FAILED job with the classifier UNAVAILABLE (the live situation)."""
        return self.verdict(job, "transient", "0", "0", "1")

    def cancelled_down(self, job: str) -> str:
        """A CANCELLED (not failed) job, classifier unavailable."""
        return self.verdict(job, "transient", "0", "0", "0")


def test_allowlist_is_real(gate):
    # Anti-vacuity: if the list stopped covering the VM legs, the "flaky jobs still retry" cases below would pass for the wrong reason.
    policy = Policy(gate)
    gate.assert_contains(
        policy.allowlist, "E2E", "watchdog-monitor.yml still allowlists the E2E legs"
    )
    gate.assert_contains(
        policy.allowlist, "OPS", "watchdog-monitor.yml still allowlists the OPS legs"
    )
    gate.assert_contains(
        policy.allowlist,
        "Migration Test",
        "watchdog-monitor.yml still allowlists Migration Test",
    )
    gate.log_pass(
        "reading the real WATCHDOG_RETRY_ALLOWLIST_PATTERNS from watchdog-monitor.yml (%s)"
        % policy.allowlist
    )


def test_classifier_down_fails_fast_for_deterministic_jobs(gate):
    # THE REGRESSION. Every one of these returned "retry" before the fix, which is what bought the 07-27 nightly a pointless second attempt.
    policy = Policy(gate)
    gate.assert_eq(
        policy.down("Stage Artifacts / Stage Artifacts"),
        "no-retry",
        "the exact 07-27 nightly job must fail fast, not buy a second attempt",
    )
    gate.assert_eq(
        policy.down("Build (Docker) / Server (amd64)"),
        "no-retry",
        "a docker build failure must fail fast",
    )
    gate.assert_eq(
        policy.down("Build (CLI) / Linux (x64)"),
        "no-retry",
        "a CLI build failure must fail fast",
    )
    gate.log_pass(
        "with the classifier down, deterministic jobs fail fast instead of retrying blind"
    )


def test_classifier_down_still_retries_known_flaky_jobs(gate):
    # The other direction. These boot VMs or pull images; a network hiccup here
    # is a real, observed, non-deterministic failure and deserves one retry.
    policy = Policy(gate)
    gate.assert_eq(
        policy.down("Tests + Infra / E2E Workers (opensuse-16.0)"),
        "retry",
        "E2E worker legs still retry",
    )
    gate.assert_eq(
        policy.down("Tests + Infra / E2E K8s Multinode"), "retry", "E2E k8s legs still retry"
    )
    gate.assert_eq(
        policy.down("OPS Tests / OPS Provision (linux-amd64)"),
        "retry",
        "OPS provisioning still retries",
    )
    gate.assert_eq(
        policy.down("Tests + Infra / Concurrent Fork Isolation"),
        "retry",
        "Fork Isolation still retries (observed: a live Docker Hub AUTH TIMEOUT)",
    )
    # MOVED HERE FROM THE DETERMINISTIC SET, and the move is the finding rather than a concession to a failing test. `Migration Test` drives SIX live D1 clones against Cloudflare's API, so its failure mode is the same family as the VM and image-pull legs beside it here. Observed, not theorised: a Cloudflare error 7500 on the sixth of six clones failed the job, and because it was on
    # NEITHER watchdog list it took 23 green jobs down with it.
    gate.assert_eq(
        policy.down("Migration Test"),
        "retry",
        "Migration Test retries: six live D1 clones against a third-party API, not a "
        "deterministic build",
    )
    gate.log_pass(
        "with the classifier down, known-flaky VM, image-pull and third-party-API jobs still retry"
    )


def test_a_cancellation_is_retried_not_used_to_kill_the_run(gate):
    # THE REGRESSION THIS FILE'S FIRST VERSION SHIPPED, caught by PR #541's own CI within one round. The allowlist must govern FAILURES only. A non-stuck CANCELLATION is not a verdict about the code: the job never reached one.
    policy = Policy(gate)
    gate.assert_eq(
        policy.cancelled_down("Quality / Built-www Gates"),
        "retry",
        "a CANCELLED non-allowlisted job must be re-run, not used to kill a zero-failure run",
    )
    gate.assert_eq(
        policy.down("Quality / Built-www Gates"),
        "no-retry",
        "the same job FAILING must still fail fast (the allowlist still governs failures)",
    )
    gate.assert_eq(
        policy.cancelled_down("Stage Artifacts / Stage Artifacts"),
        "retry",
        "any cancellation is a runner/infra flake, whatever the job",
    )
    gate.log_pass("the allowlist governs failures only; cancellations are still retried")


def test_allowlist_overrides_a_confident_code_change_verdict(gate):
    # POLICY REVERSED BY OPERATOR DECISION 2026-07-30. Run 30540751569 job 90867219911: `Tests + Infra / E2E Ceph` failed on an ssh exit-status-6 during Docker install (infrastructure), and the classifier answered code-change at 0.9 reasoning that "a setup error and E2E tests failed suggests a problem with the code under test". That tautology cleared the threshold, suppressed the
    # retry and cost a full red round.
    policy = Policy(gate)
    gate.assert_eq(
        policy.verdict("Tests + Infra / E2E Ceph", "code-change", "0.9", "1"),
        "retry",
        "an allowlisted provisioning leg retries despite a confident code-change verdict",
    )
    gate.assert_eq(
        policy.override_fired("Tests + Infra / E2E Ceph"),
        "override",
        "and it retries BECAUSE the allowlist overrode the verdict, not incidentally",
    )
    gate.log_pass("the allowlist overrides a confident code-change verdict for provisioning legs")


def test_a_non_allowlisted_job_still_fails_fast(gate):
    # THE CONTROL, and the one that keeps the reversal from becoming "always retry". A deterministic gate failure must still cost one attempt.
    policy = Policy(gate)
    gate.assert_eq(
        policy.verdict("Quality / Security", "code-change", "0.9", "1"),
        "no-retry",
        "a confident code-change verdict still wins for a job OFF the allowlist",
    )
    gate.assert_eq(
        policy.override_fired("Quality / Security"),
        "no-override",
        "and no override is claimed for it",
    )
    gate.log_pass("a non-allowlisted confident code-change verdict still fails fast")


def test_the_binary_exec_guard_still_beats_the_allowlist(gate):
    # The guard SYNTHESISES code-change at confidence 1 precisely to block a retry of a job that downloads and executes a released binary. The distinction travels explicitly as guardForced, because a real classifier
    # can also answer 1.0 and a `confidence == 1` proxy would silently hand the
    # guard's authority to any confident model.
    policy = Policy(gate)
    gate.assert_eq(
        policy.verdict("Tests + Infra / E2E Ceph", "code-change", "1", "1", "1", "1"),
        "no-retry",
        "a guard-forced verdict is never overridden, even for an allowlisted job",
    )
    gate.assert_eq(
        policy.override_fired("Tests + Infra / E2E Ceph", "1"),
        "no-override",
        "and the override does not even claim to have fired",
    )
    gate.log_pass("the binary-exec guard's forced verdict outranks the retry allowlist")


def test_low_confidence_code_change_still_retries(gate):
    # Below the threshold the model is not sure, so the old behaviour stands.
    policy = Policy(gate)
    gate.assert_eq(
        policy.verdict("Build (Docker) / Server (amd64)", "code-change", "0.5", "1"),
        "retry",
        "an unsure code-change verdict is still treated as transient",
    )
    gate.log_pass("a sub-threshold code-change verdict still retries")


def test_available_classifier_governs_non_allowlisted_jobs(gate):
    # THE DISTINCTION THAT MATTERS. When the classifier IS working and says transient, a non-allowlisted job must still retry: the allowlist is a fallback for an absent judgment, not a second veto over a real one.
    policy = Policy(gate)
    gate.assert_eq(
        policy.verdict("Stage Artifacts / Stage Artifacts", "transient", "0.9", "1"),
        "retry",
        "a real transient verdict retries even a non-allowlisted job",
    )
    gate.log_pass("the allowlist only governs the classifier-unavailable path")


def test_confidence_zero_is_not_the_signal(gate):
    # A real verdict may legitimately carry confidence 0. Availability is the load-bearing field, not the number.
    policy = Policy(gate)
    gate.assert_eq(
        policy.verdict("Stage Artifacts / Stage Artifacts", "transient", "0", "1"),
        "retry",
        "confidence 0 from an AVAILABLE classifier is still a verdict",
    )
    gate.assert_eq(
        policy.verdict("Stage Artifacts / Stage Artifacts", "transient", "0", "0"),
        "no-retry",
        "the same numbers with the classifier ABSENT must fail fast",
    )
    gate.log_pass("availability, not confidence 0, is what switches the policy")


def test_empty_allowlist_fails_closed(gate):
    # isFailure is explicit here: an empty allowlist only constrains FAILURES, so omitting it would exercise the cancellation path and prove nothing about the allowlist.
    policy = Policy(gate)
    gate.assert_eq(
        policy._node(EMPTY_ALLOWLIST_JS),
        "no-retry",
        "an empty allowlist must fail closed for a FAILURE",
    )
    gate.log_pass("an empty or missing allowlist fails closed")


def test_unknown_isFailure_degrades_to_the_safe_direction(gate):  # noqa: N802 -- the twin's case name; parity compares by name
    # If a future caller forgets the flag, the ambiguity must resolve toward "retry" (the pre-change behaviour), never toward "kill the run". Killing a pipeline on a missing boolean cost run 30304346151 its 39 green jobs.
    policy = Policy(gate)
    gate.assert_eq(
        policy._node(MISSING_IS_FAILURE_JS),
        "retry",
        "a missing isFailure must degrade to retry, not to killing the run",
    )
    gate.log_pass("an unspecified isFailure resolves to the safe direction")


def test_allowlist_is_required_config(gate):
    # Defaulting the allowlist would let a config drift silently restore retry-everything, which is the behaviour #537 is about.
    if not WATCHDOG.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(WATCHDOG))
    gate.assert_contains(
        WATCHDOG.read_text(encoding="utf-8"),
        "WATCHDOG_RETRY_ALLOWLIST_PATTERNS env var is required",
        "the monitor refuses to run without an explicit allowlist",
    )
    gate.log_pass("the allowlist is required config, not a silent default")
