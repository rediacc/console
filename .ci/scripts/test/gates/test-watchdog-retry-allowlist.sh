#!/bin/bash
# Unit test for the retry policy in .ci/scripts/ci/watchdog-monitor.cjs (issue #537).
#
# WHAT BROKE. The failure classifier returns HTTP 402, so classifyFailure falls
# back to `{ classification: 'transient', confidence: 0 }` on EVERY failure. The
# retry branch only refused to retry on a CONFIDENT code-change verdict, so a
# confidence-0 fallback always landed in the retry path. Net effect: every
# failure in the repo, of every kind, was auto-retried on a judgment nobody made.
#
# That is only defensible while somebody reads the log afterwards -- and nobody
# does, because the retry itself destroys it (attempt 1's job logs stop being
# reachable once attempt 2 starts). The 07-27 nightly is the receipt: `Stage
# Artifacts` failed on a deterministic empty-channel bug and the watchdog spent
# a full second attempt re-proving it before cancelling anyway.
#
# THE FIX. When the classifier cannot speak, retry only jobs whose failures are
# genuinely non-deterministic -- the ones that boot VMs or pull images over the
# network -- and fail everything else fast.
#
# WHY A UNIT TEST AND NOT A MIRROR. This calls the exported decision and reads
# WATCHDOG_RETRY_ALLOWLIST_PATTERNS out of the REAL watchdog-monitor.yml, so a
# rename of a pattern or a quiet widening of the list fails here.
#
# Both directions matter:
#   - Too quiet: retry-everything returns and blind reruns burn ~55 min a time.
#   - Too loud: a genuinely flaky VM leg stops being retried and every E2E
#     network hiccup becomes a red round a human has to babysit.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WATCHDOG="$REPO_ROOT/.ci/scripts/ci/watchdog-monitor.cjs"
CI_WORKFLOW="$REPO_ROOT/.github/workflows/watchdog-monitor.yml"

# The allowlist under test is the one CI actually sets, not a copy: a policy
# that works on invented job names while the real config never matches is the
# exact failure this gate exists to catch.
ALLOWLIST="$(sed -n "s/^ *WATCHDOG_RETRY_ALLOWLIST_PATTERNS: *'\(.*\)'$/\1/p" "$CI_WORKFLOW")"
if [[ -z "$ALLOWLIST" ]]; then
    echo "could not read WATCHDOG_RETRY_ALLOWLIST_PATTERNS from $CI_WORKFLOW" >&2
    exit 1
fi

# verdict <job-name> <classification> <confidence> <available 0|1> [isFailure 0|1] -> "retry" | "no-retry"
verdict() {
    node -e '
const w = require(process.argv[1]);
const v = w.evaluateRetryEligibility({
  jobName: process.argv[2],
  classification: process.argv[3],
  confidence: Number(process.argv[4]),
  classifierAvailable: process.argv[5] === "1",
  isFailure: process.argv[7] !== "0",
  threshold: 0.8,
  retryAllowlistPatterns: process.argv[6].split(",").map(s => s.trim()).filter(Boolean),
});
process.stdout.write(v.retry ? "retry" : "no-retry");
' "$WATCHDOG" "$1" "$2" "$3" "$4" "$ALLOWLIST" "${5:-1}"
}

# down <job-name> -> a FAILED job with the classifier UNAVAILABLE (the live situation)
down() { verdict "$1" transient 0 0 1; }

# cancelled_down <job-name> -> a CANCELLED (not failed) job, classifier unavailable
cancelled_down() { verdict "$1" transient 0 0 0; }

# ---------------------------------------------------------------------------

test_allowlist_is_real() {
    # Anti-vacuity: if the list stopped covering the VM legs, the "flaky jobs
    # still retry" cases below would pass for the wrong reason.
    assert_contains "$ALLOWLIST" "E2E" "watchdog-monitor.yml still allowlists the E2E legs"
    assert_contains "$ALLOWLIST" "OPS" "watchdog-monitor.yml still allowlists the OPS legs"
    log_pass "reading the real WATCHDOG_RETRY_ALLOWLIST_PATTERNS from watchdog-monitor.yml ($ALLOWLIST)"
}

test_classifier_down_fails_fast_for_deterministic_jobs() {
    # THE REGRESSION. Every one of these returned "retry" before the fix, which
    # is what bought the 07-27 nightly a pointless second attempt.
    assert_eq "$(down 'Stage Artifacts / Stage Artifacts')" "no-retry" \
        "the exact 07-27 nightly job must fail fast, not buy a second attempt"
    assert_eq "$(down 'Build (Docker) / Server (amd64)')" "no-retry" "a docker build failure must fail fast"
    assert_eq "$(down 'Build (CLI) / Linux (x64)')" "no-retry" "a CLI build failure must fail fast"
    assert_eq "$(down 'Migration Test')" "no-retry" "a migration failure must fail fast"
    log_pass "with the classifier down, deterministic jobs fail fast instead of retrying blind"
}

test_classifier_down_still_retries_known_flaky_jobs() {
    # The other direction. These boot VMs or pull images; a network hiccup here
    # is a real, observed, non-deterministic failure and deserves one retry.
    assert_eq "$(down 'Tests + Infra / E2E Workers (opensuse-16.0)')" "retry" "E2E worker legs still retry"
    assert_eq "$(down 'Tests + Infra / E2E K8s Multinode')" "retry" "E2E k8s legs still retry"
    assert_eq "$(down 'OPS Tests / OPS Provision (linux-amd64)')" "retry" "OPS provisioning still retries"
    assert_eq "$(down 'Tests + Infra / Concurrent Fork Isolation')" "retry" \
        "Fork Isolation still retries (observed: a live Docker Hub AUTH TIMEOUT)"
    log_pass "with the classifier down, known-flaky VM and image-pull jobs still retry"
}

test_a_cancellation_is_retried_not_used_to_kill_the_run() {
    # THE REGRESSION THIS FILE'S FIRST VERSION SHIPPED, caught by PR #541's own
    # CI within one round. The allowlist must govern FAILURES only.
    #
    # A non-stuck CANCELLATION is not a verdict about the code: the job never
    # reached one. The watchdog's branch-1 comment already states the rule --
    # "nuking a 0-failure run for it is wrong" -- which is exactly why
    # cancellations are routed to the retry path at all.
    #
    # What actually happened: `Quality / Built-www Gates` was CANCELLED, zero
    # jobs had failed anywhere in run 30304346151, and the watchdog force-
    # cancelled the whole pipeline -- 39 green jobs, 16 killed -- because that
    # job is not on the allowlist. Before the change it would have been re-run.
    assert_eq "$(cancelled_down 'Quality / Built-www Gates')" "retry" \
        "a CANCELLED non-allowlisted job must be re-run, not used to kill a zero-failure run"
    assert_eq "$(down 'Quality / Built-www Gates')" "no-retry" \
        "the same job FAILING must still fail fast (the allowlist still governs failures)"
    assert_eq "$(cancelled_down 'Stage Artifacts / Stage Artifacts')" "retry" \
        "any cancellation is a runner/infra flake, whatever the job"
    log_pass "the allowlist governs failures only; cancellations are still retried"
}

test_confident_code_change_never_retries() {
    # Unchanged behaviour, and it must stay unchanged whether or not the
    # classifier is reachable for other jobs.
    assert_eq "$(verdict 'Tests + Infra / E2E Workers (fedora-43)' code-change 0.9 1)" "no-retry" \
        "a confident code-change verdict wins even for an allowlisted job"
    assert_eq "$(verdict 'Tests + Infra / E2E Workers (fedora-43)' code-change 1 1)" "no-retry" \
        "the binary-exec guard's override (confidence 1) must not be retried"
    log_pass "a confident code-change verdict never retries, allowlist or not"
}

test_low_confidence_code_change_still_retries() {
    # Below the threshold the model is not sure, so the old behaviour stands:
    # treat it as transient. This is the case that confidence-sniffing would
    # have conflated with an outage.
    assert_eq "$(verdict 'Build (Docker) / Server (amd64)' code-change 0.5 1)" "retry" \
        "an unsure code-change verdict is still treated as transient"
    log_pass "a sub-threshold code-change verdict still retries"
}

test_available_classifier_governs_non_allowlisted_jobs() {
    # THE DISTINCTION THAT MATTERS. When the classifier IS working and says
    # transient, a non-allowlisted job must still retry -- the allowlist is a
    # fallback for an absent judgment, not a second veto over a real one. If
    # this returned "no-retry" the fix would have quietly narrowed retries far
    # beyond issue #537's intent.
    assert_eq "$(verdict 'Stage Artifacts / Stage Artifacts' transient 0.9 1)" "retry" \
        "a real transient verdict retries even a non-allowlisted job"
    log_pass "the allowlist only governs the classifier-unavailable path"
}

test_confidence_zero_is_not_the_signal() {
    # A real verdict may legitimately carry confidence 0. Availability is the
    # load-bearing field, not the number -- sniffing `confidence === 0` is how
    # retry-everything got mistaken for a judgment in the first place.
    assert_eq "$(verdict 'Stage Artifacts / Stage Artifacts' transient 0 1)" "retry" \
        "confidence 0 from an AVAILABLE classifier is still a verdict"
    assert_eq "$(verdict 'Stage Artifacts / Stage Artifacts' transient 0 0)" "no-retry" \
        "the same numbers with the classifier ABSENT must fail fast"
    log_pass "availability, not confidence 0, is what switches the policy"
}

test_empty_allowlist_fails_closed() {
    # isFailure is explicit here: an empty allowlist only constrains FAILURES,
    # so omitting it would exercise the cancellation path and prove nothing
    # about the allowlist. (That omission is exactly how this case broke when
    # the cancellation branch was added.)
    local out
    out="$(node -e '
const w = require(process.argv[1]);
const v = w.evaluateRetryEligibility({
  jobName: "Tests + Infra / E2E Workers (fedora-43)",
  classification: "transient", confidence: 0, classifierAvailable: false,
  isFailure: true,
  threshold: 0.8, retryAllowlistPatterns: [],
});
process.stdout.write(v.retry ? "retry" : "no-retry");
' "$WATCHDOG")"
    assert_eq "$out" "no-retry" "an empty allowlist must fail closed for a FAILURE"
    log_pass "an empty or missing allowlist fails closed"
}

test_unknown_isFailure_degrades_to_the_safe_direction() {
    # If a future caller forgets the flag, the ambiguity must resolve toward
    # "retry" (the pre-change behaviour), never toward "kill the run". Killing a
    # pipeline on a missing boolean is the failure mode this whole branch exists
    # to prevent, and it cost run 30304346151 its 39 green jobs.
    local out
    out="$(node -e '
const w = require(process.argv[1]);
const v = w.evaluateRetryEligibility({
  jobName: "Quality / Built-www Gates",
  classification: "transient", confidence: 0, classifierAvailable: false,
  threshold: 0.8, retryAllowlistPatterns: ["E2E"],
});
process.stdout.write(v.retry ? "retry" : "no-retry");
' "$WATCHDOG")"
    assert_eq "$out" "retry" "a missing isFailure must degrade to retry, not to killing the run"
    log_pass "an unspecified isFailure resolves to the safe direction"
}

test_allowlist_is_required_config() {
    # Defaulting the allowlist would let a config drift silently restore
    # retry-everything, which is the behaviour #537 is about. Missing config
    # must be loud.
    assert_contains "$(cat "$WATCHDOG")" "WATCHDOG_RETRY_ALLOWLIST_PATTERNS env var is required" \
        "the monitor refuses to run without an explicit allowlist"
    log_pass "the allowlist is required config, not a silent default"
}

log_test "test-watchdog-retry-allowlist"
test_allowlist_is_real
test_classifier_down_fails_fast_for_deterministic_jobs
test_classifier_down_still_retries_known_flaky_jobs
test_a_cancellation_is_retried_not_used_to_kill_the_run
test_confident_code_change_never_retries
test_low_confidence_code_change_still_retries
test_available_classifier_governs_non_allowlisted_jobs
test_confidence_zero_is_not_the_signal
test_empty_allowlist_fails_closed
test_unknown_isFailure_degrades_to_the_safe_direction
test_allowlist_is_required_config
echo ""
log_pass "all tests passed"
