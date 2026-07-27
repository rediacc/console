#!/bin/bash
# Unit test for .ci/scripts/ci/assert-channel-for-event.sh.
#
# WHAT THIS GUARDS. The channel decides whether a run uploads to R2. A previous
# design resolved a `dryrun-<sha>` channel for non-publishing events and
# produced roughly 5 GB of orphan R2 bytes per trigger. This script is the
# assertion that stops that returning, so it is load-bearing for cost, not just
# for tidiness.
#
# WHY IT NEEDED A TEST NOW. Wave A adds `workflow_dispatch` to ci.yml as the
# nightly rehearsal. The script's final `*)` arm WARNS AND ACCEPTS ANY CHANNEL,
# so a new event type lands exempt from the guard unless someone remembers to
# add an arm -- a new, human-triggerable, full-pipeline entry point silently
# outside the one check that exists to stop orphan uploads. That is exactly the
# shape of bug this whole wave is about: a check that looks present and is not
# reached.
#
# The fall-through arm is deliberately KEPT (failing closed on an unknown event
# would break CI the moment GitHub adds one), which is precisely why every event
# the repo actually uses needs an explicit arm and a test pinning it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

ASSERT="$REPO_ROOT/.ci/scripts/ci/assert-channel-for-event.sh"
CI_WORKFLOW="$REPO_ROOT/.github/workflows/ci.yml"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

# check <event> <channel> -> "ok" | "rejected" | "usage"
check() {
    local rc=0
    bash "$ASSERT" "$@" >"$OUT/log.txt" 2>&1 || rc=$?
    case "$rc" in
        0) echo "ok" ;;
        2) echo "usage" ;;
        *) echo "rejected" ;;
    esac
}

# ---------------------------------------------------------------------------

test_publishing_events_keep_their_channels() {
    assert_eq "$(check push edge)" "ok" "push resolves to edge"
    assert_eq "$(check pull_request pr-540)" "ok" "pull_request resolves to pr-N"
    log_pass "the two publishing events accept their own channels"
}

test_publishing_events_reject_wrong_channels() {
    # Anti-vacuity for the two arms above: if these passed, the arms would be
    # asserting nothing and every case in this file would be decoration.
    assert_eq "$(check push '')" "rejected" "push must not resolve to an empty channel"
    assert_eq "$(check push pr-1)" "rejected" "push must not take a PR channel"
    assert_eq "$(check pull_request edge)" "rejected" "pull_request must not take the edge channel"
    assert_eq "$(check pull_request '')" "rejected" "pull_request must not resolve to an empty channel"
    assert_eq "$(check pull_request pr-abc)" "rejected" "pr-N must be numeric"
    log_pass "the publishing arms reject every wrong channel (the arms really fire)"
}

test_schedule_must_not_upload() {
    assert_eq "$(check schedule '')" "ok" "the nightly's empty channel is correct"
    assert_eq "$(check schedule edge)" "rejected" "the nightly must never resolve a publishing channel"
    assert_eq "$(check schedule 'dryrun-abc123')" "rejected" \
        "the dryrun-<sha> fallthrough that orphaned ~5 GB per run must stay rejected"
    log_pass "schedule is held to an empty channel"
}

test_workflow_dispatch_must_not_upload() {
    # THE NEW ARM. Without it these three all land in the `*)` warn-and-accept
    # arm, and the rehearsal becomes a human-triggerable way to upload bytes
    # that nothing asserts on.
    assert_eq "$(check workflow_dispatch '')" "ok" "the rehearsal's empty channel is correct"
    assert_eq "$(check workflow_dispatch edge)" "rejected" \
        "the rehearsal must never resolve a publishing channel"
    assert_eq "$(check workflow_dispatch 'dryrun-abc123')" "rejected" \
        "the rehearsal must reject a dryrun channel too"
    log_pass "workflow_dispatch (the rehearsal) is held to an empty channel"
}

test_the_dispatch_arm_is_explicit_not_the_fallthrough() {
    # Distinguishes "rejected by its own arm" from "accepted by the catch-all".
    # A pass on the empty case alone cannot tell those apart, because the
    # catch-all accepts everything -- including the empty channel.
    bash "$ASSERT" workflow_dispatch '' >"$OUT/log.txt" 2>&1 || true
    assert_not_contains "$(cat "$OUT/log.txt")" "Unknown event" \
        "workflow_dispatch must be handled by its own arm, not the catch-all"
    log_pass "the rehearsal is matched by an explicit arm, not warn-and-accept"
}

test_unknown_event_still_warns_and_accepts() {
    # Documenting the deliberate fall-through: failing closed here would break
    # CI the moment GitHub introduces an event. Pinned so that changing it is a
    # decision rather than an accident.
    assert_eq "$(check merge_group '')" "ok" "an unknown event is accepted"
    assert_contains "$(cat "$OUT/log.txt")" "Unknown event" "and says so out loud"
    log_pass "an unknown event warns and accepts, deliberately"
}

test_missing_event_is_a_usage_error() {
    assert_eq "$(check '' '')" "usage" "an empty event is a usage error, not a silent pass"
    log_pass "a missing event exits 2 rather than passing"
}

test_ci_actually_dispatches() {
    # Anti-vacuity against the real workflow: the new arm is dead code if ci.yml
    # has no workflow_dispatch trigger, and this test would then be pinning
    # behaviour nothing reaches.
    assert_contains "$(cat "$CI_WORKFLOW")" "workflow_dispatch:" \
        "ci.yml still declares the workflow_dispatch rehearsal this arm exists for"
    assert_contains "$(cat "$CI_WORKFLOW")" "Guard the rehearsal dispatch to main" \
        "the rehearsal is still guarded to main"
    log_pass "ci.yml really has the dispatch trigger and its main guard"
}

log_test "test-channel-for-event"
test_publishing_events_keep_their_channels
test_publishing_events_reject_wrong_channels
test_schedule_must_not_upload
test_workflow_dispatch_must_not_upload
test_the_dispatch_arm_is_explicit_not_the_fallthrough
test_unknown_event_still_warns_and_accepts
test_missing_event_is_a_usage_error
test_ci_actually_dispatches
echo ""
log_pass "all tests passed"
