"""Port of `.ci/scripts/test/gates/test-channel-for-event.sh`, retired in W7 P5.

Unit test for `.ci/scripts/ci/assert-channel-for-event.sh`.

WHAT THIS GUARDS, unchanged from the twin. The channel decides whether a run uploads to R2. A previous design resolved a `dryrun-<sha>` channel for non-publishing events and produced roughly 5 GB of orphan R2 bytes per trigger. This script is the assertion that stops that returning, so it is load-bearing for cost, not just for tidiness.

The script's final `*)` arm WARNS AND ACCEPTS ANY CHANNEL, so a new event type lands exempt from the guard unless someone remembers to add an arm. The fall-through is deliberately KEPT (failing closed on an unknown event would break CI the moment GitHub adds one), which is precisely why every event the repo actually uses needs an explicit arm and a test pinning it.

THE PORT CHANGES ONE THING AND IT IS NOT A VERDICT. The twin keeps the last run's output in a single `$OUT/log.txt` and two of its cases read it after the fact; here `check()` returns the output alongside the verdict, so a case reads the output of the call it made rather than of whichever call ran last. Same bytes, same assertions, no shared mutable file.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

ASSERT = paths.from_root(".ci", "scripts", "ci", "assert-channel-for-event.sh")
CI_WORKFLOW = paths.from_root(".github", "workflows", "ci.yml")


def check(gate, event: str, channel: str) -> tuple[str, str]:
    """`check <event> <channel>` -> ("ok" | "rejected" | "usage", output).

    Exit 2 is the script's USAGE code and is kept distinct from every other non-zero, because "you called me wrong" and "that channel is illegal for that event" are different findings and collapsing them would let a typo in this test read as a rejection it never made.
    """
    result = harness.run(["bash", str(ASSERT), event, channel])
    if result.rc == 0:
        verdict = "ok"
    elif result.rc == 2:  # the script's own documented usage code
        verdict = "usage"
    else:
        verdict = "rejected"
    gate.log_info("assert-channel-for-event %r %r -> %s" % (event, channel, verdict))
    return verdict, result.combined


def test_publishing_events_keep_their_channels(gate):
    gate.assert_eq(check(gate, "push", "edge")[0], "ok", "push resolves to edge")
    gate.assert_eq(check(gate, "pull_request", "pr-540")[0], "ok", "pull_request resolves to pr-N")
    gate.log_pass("the two publishing events accept their own channels")


def test_publishing_events_reject_wrong_channels(gate):
    # Anti-vacuity for the two arms above: if these passed, the arms would be asserting nothing and every case in this file would be decoration.
    gate.assert_eq(
        check(gate, "push", "")[0], "rejected", "push must not resolve to an empty channel"
    )
    gate.assert_eq(check(gate, "push", "pr-1")[0], "rejected", "push must not take a PR channel")
    gate.assert_eq(
        check(gate, "pull_request", "edge")[0],
        "rejected",
        "pull_request must not take the edge channel",
    )
    gate.assert_eq(
        check(gate, "pull_request", "")[0],
        "rejected",
        "pull_request must not resolve to an empty channel",
    )
    gate.assert_eq(check(gate, "pull_request", "pr-abc")[0], "rejected", "pr-N must be numeric")
    gate.log_pass("the publishing arms reject every wrong channel (the arms really fire)")


def test_schedule_must_not_upload(gate):
    gate.assert_eq(check(gate, "schedule", "")[0], "ok", "the nightly's empty channel is correct")
    gate.assert_eq(
        check(gate, "schedule", "edge")[0],
        "rejected",
        "the nightly must never resolve a publishing channel",
    )
    gate.assert_eq(
        check(gate, "schedule", "dryrun-abc123")[0],
        "rejected",
        "the dryrun-<sha> fallthrough that orphaned ~5 GB per run must stay rejected",
    )
    gate.log_pass("schedule is held to an empty channel")


def test_workflow_dispatch_must_not_upload(gate):
    # THE NEW ARM. Without it these three all land in the `*)` warn-and-accept arm, and the rehearsal becomes a human-triggerable way to upload bytes that nothing asserts on.
    gate.assert_eq(
        check(gate, "workflow_dispatch", "")[0], "ok", "the rehearsal's empty channel is correct"
    )
    gate.assert_eq(
        check(gate, "workflow_dispatch", "edge")[0],
        "rejected",
        "the rehearsal must never resolve a publishing channel",
    )
    gate.assert_eq(
        check(gate, "workflow_dispatch", "dryrun-abc123")[0],
        "rejected",
        "the rehearsal must reject a dryrun channel too",
    )
    gate.log_pass("workflow_dispatch (the rehearsal) is held to an empty channel")


def test_the_dispatch_arm_is_explicit_not_the_fallthrough(gate):
    # Distinguishes "rejected by its own arm" from "accepted by the catch-all". A pass on the empty case alone cannot tell those apart, because the catch-all accepts everything -- including the empty channel.
    _, output = check(gate, "workflow_dispatch", "")
    gate.assert_not_contains(
        output,
        "Unknown event",
        "workflow_dispatch must be handled by its own arm, not the catch-all",
    )
    gate.log_pass("the rehearsal is matched by an explicit arm, not warn-and-accept")


def test_unknown_event_still_warns_and_accepts(gate):
    # Documenting the deliberate fall-through: failing closed here would break CI the moment GitHub introduces an event. Pinned so that changing it is a decision rather than an accident.
    verdict, output = check(gate, "merge_group", "")
    gate.assert_eq(verdict, "ok", "an unknown event is accepted")
    gate.assert_contains(output, "Unknown event", "and says so out loud")
    gate.log_pass("an unknown event warns and accepts, deliberately")


def test_missing_event_is_a_usage_error(gate):
    gate.assert_eq(
        check(gate, "", "")[0], "usage", "an empty event is a usage error, not a silent pass"
    )
    gate.log_pass("a missing event exits 2 rather than passing")


def test_ci_actually_dispatches(gate):
    # Anti-vacuity against the real workflow: the new arm is dead code if ci.yml has no workflow_dispatch trigger, and this test would then be pinning behaviour nothing reaches.
    body = CI_WORKFLOW.read_text(encoding="utf-8")
    gate.assert_contains(
        body,
        "workflow_dispatch:",
        "ci.yml still declares the workflow_dispatch rehearsal this arm exists for",
    )
    gate.assert_contains(
        body, "Guard the rehearsal dispatch to main", "the rehearsal is still guarded to main"
    )
    gate.log_pass("ci.yml really has the dispatch trigger and its main guard")
