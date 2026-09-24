"""CI-queue backpressure and its cache, and the v14 gap set.

Ported from `.claude/hooks/stop/worklist-cases/13-ci-queue-and-mail.sh`, one pytest function per numbered bash case. Case 157's heading sits at the bottom of `12-agent-docs-and-focus.sh` while its whole body is in this file, so it is ported here, beside the rest of the queue battery.

THE OPERATOR'S LIVE INCIDENT (2026-07-31) behind the queue cases: pushes queued runs behind each other and a run sat pending 25+ minutes. The hook must see the jam and tell the session to work locally instead of pushing more.

The operator-request cases (159, 159d, 159g) were removed with cross-session messaging on 2026-09-24.
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING

from rediacc_hooks.tests.test_wl_ci_status import ci_job, ci_rollup, ci_run, ci_setup, write_exec
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

if TYPE_CHECKING:
    from rediacc_hooks.tests import wlfix

# The gh shim the queue cases serve: the freshness graphql query, the rollup query, the runs endpoint and the per-job endpoint, all from files.
QUEUE_SHIM = """#!/bin/bash
for a in "$@"; do
    case "$a" in
        *lastEditedAt*) cat "%(base)s/ci-fresh.json"; exit 0 ;;
        query=*) cat "%(base)s/ci-rollup.json"; exit 0 ;;
    esac
done
case "$*" in
    *actions/runs*) %(runs)s ;;
    *actions/jobs/*) cat "%(base)s/ci-job.json"; exit 0 ;;
esac
echo '{}'
"""

STALE_BODY_FRESH = (
    '{"data":{"repository":{"pullRequests":{"nodes":[{"number":543,'
    '"lastEditedAt":"2000-01-01T00:00:00Z","updatedAt":"2000-01-01T00:00:00Z"}]}}}}'
)


def stamp(minutes_ago: float = 0.0, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> str:
    """A UTC stamp `minutes_ago` in the past, in the format the bash `date -u -d` calls produced."""
    return time.strftime(fmt, time.gmtime(time.time() - minutes_ago * 60))


def plant_event(fix, payload: dict) -> None:
    """Append one raw event to the legacy log."""
    with fix.events.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def added_id(result: wlfix.Result) -> str:
    """The item id `--add` printed."""
    found = re.search(r"^added #([0-9a-f]+)", result.out, re.MULTILINE)
    assert found, "--add printed no item id: %r" % result.out[:200]
    return found.group(1)


def ci_queue_fixture(fix, runs: dict, runs_body: str = "") -> None:
    """The runs payload the shim serves, plus the queue-cache drop every swap needs.

    LOCAL to this module, exactly as the bash helper of the same name was local to `13-ci-queue-and-mail.sh`; the rest of the CI fixture (`ci_setup`, `ci_rollup`, `ci_job`, `ci_run`) comes from the ported case 09 module, which is where the bash kept its single copy too.
    """
    (fix.base / "ci-runs.json").write_text(json.dumps(runs) + "\n", encoding="utf-8")
    fix.stem(".ciqueue-deadbeef").unlink(missing_ok=True)
    body = runs_body or 'cat "%s/ci-runs.json"; exit 0' % fix.base
    write_exec(fix.base / "binonly" / "gh", QUEUE_SHIM % {"base": fix.base, "runs": body})


def ci_queue_ready(fix) -> str:
    """The shared queue prelude: a green rollup on a repo with a published tip, and a 30-minute-old creation stamp for the runs the cases plant."""
    ci_setup(fix)
    ci_rollup(fix, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))
    return stamp(30)


def test_157_a_saturated_queue_says_do_not_push(wl):  # noqa: F811
    """A 30-minute-queued newest run raises the saturation note."""
    qold = ci_queue_ready(wl)
    ci_queue_fixture(
        wl,
        {
            "workflow_runs": [
                {"status": "queued", "created_at": qold},
                {"status": "completed", "created_at": qold},
            ]
        },
    )
    got = ci_run(wl)
    assert "CI QUEUE IS SATURATED" in got.out, "saturation note missing: %s" % got.out[:300]
    assert "DO NOT PUSH" in got.out, got.out[:300]


def test_157b_control_an_in_progress_run_with_an_empty_queue_is_clear(wl):  # noqa: F811
    """CONTROL: a running (not queued) newest run stays quiet."""
    qold = ci_queue_ready(wl)
    ci_queue_fixture(
        wl,
        {
            "workflow_runs": [
                {"status": "in_progress", "created_at": qold},
                {"status": "completed", "created_at": qold},
            ]
        },
    )
    got = ci_run(wl)
    assert "CI QUEUE IS SATURATED" not in got.out, "clear queue raised the note: %s" % got.out[:300]


def test_157c_two_queued_runs_saturate_even_when_fresh(wl):  # noqa: F811
    """Depth trigger: queue depth >= 2 saturates regardless of the newest run's age."""
    qold = ci_queue_ready(wl)
    ci_queue_fixture(
        wl,
        {
            "workflow_runs": [
                {"status": "queued", "created_at": stamp(1)},
                {"status": "queued", "created_at": qold},
            ]
        },
    )
    got = ci_run(wl)
    assert "CI QUEUE IS SATURATED" in got.out, "depth trigger missing: %s" % got.out[:300]
    assert "2 queued run(s)" in got.out, got.out[:300]


def test_157d_failure_mode_a_broken_gh_grants_no_slack(wl):  # noqa: F811
    """FAILURE MODE: the queue read fails toward pressure. A gh that dies on the runs endpoint reads as unknown, the note is absent, and no relaxation is granted."""
    qold = ci_queue_ready(wl)
    ci_queue_fixture(
        wl,
        {"workflow_runs": [{"status": "queued", "created_at": qold}]},
        runs_body='echo "boom" >&2; exit 1',
    )
    got = ci_run(wl)
    assert "CI QUEUE IS SATURATED" not in got.out, (
        "a blind queue check granted slack: %s" % got.out[:300]
    )


def test_157e_pr_stale_folds_into_the_note_only_while_saturated(wl):  # noqa: F811
    """SUPPRESSION PAIR. A stale body is one whose last push came AFTER the PR-body edit (the edit is stamped in 2000 here). Under saturation the nag folds into the queue note, and the pair's control is the same stale body with the queue clear, where the check fires on its own."""
    qold = ci_queue_ready(wl)
    (wl.base / "ci-fresh.json").write_text(STALE_BODY_FRESH + "\n", encoding="utf-8")
    ci_queue_fixture(wl, {"workflow_runs": [{"status": "queued", "created_at": qold}]})
    wl.add_item("- [ ] (deadbeef) open thing")

    got = ci_run(wl, message="answer with work remaining")
    assert "YOU PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" not in got.out, (
        "fold wrong: %s" % got.out[:400]
    )
    assert "the PR body is stale; fold the refresh into that next push" in got.out, got.out[:400]

    ci_queue_fixture(wl, {"workflow_runs": [{"status": "completed", "created_at": qold}]})
    wl.env["WORKLIST_FOCUS"] = "off"
    try:
        control = ci_run(wl, message="answer with work remaining")
    finally:
        wl.env.pop("WORKLIST_FOCUS", None)
    assert "YOU PUSHED AFTER YOUR LAST PR-DESCRIPTION EDIT" in control.out, (
        "157e CONTROL: pr-stale did not fire on a clear queue: %s" % control.out[:300]
    )


def test_157f_the_queue_read_is_cached_two_stops_one_gh_hit(wl):  # noqa: F811
    """Two stops inside the TTL cost exactly one hit on the runs endpoint."""
    qold = ci_queue_ready(wl)
    hits = wl.base / "runs-hits.txt"
    ci_queue_fixture(
        wl,
        {"workflow_runs": [{"status": "queued", "created_at": qold}]},
        runs_body='echo hit >>"%s"; cat "%s/ci-runs.json"; exit 0' % (hits, wl.base),
    )
    hits.unlink(missing_ok=True)
    wl.stem(".ciqueue-deadbeef").unlink(missing_ok=True)

    ci_run(wl)
    ci_run(wl)
    count = len(hits.read_text(encoding="utf-8").splitlines()) if hits.is_file() else 0
    assert count == 1, "expected exactly 1 runs-endpoint hit, got %d" % count


def test_160_displays_show_basetext_and_the_latest_note_never_the_whole_history(wl):  # noqa: F811
    """v14 gap 1. One live item reached ~20 concatenated notes and every block printed them all. brief_line/brief_text keep the full accumulation in the store (`--list`) and render base plus newest only."""
    wl.brief_now()
    wl.hand_now()
    gid = added_id(wl.cli("--add", "deadbeef", "campaign base text for the brief test"))
    justification = (
        "WHY: only the operator can pick between the two tier maps because both are defensible "
        "and the code decides nothing HOW: the operator answers on their next pass"
    )
    wl.cli("--defer", "deadbeef", gid, "first old note DEFAULT: alpha " + justification)
    wl.cli("--defer", "deadbeef", gid, "second old note DEFAULT: beta " + justification)
    wl.cli("--defer", "deadbeef", gid, "newest note wins DEFAULT: gamma " + justification)
    wl.say("answer\n\n## Remaining\n- the deferred campaign item")
    got = wl.run({"WORKLIST_FOCUS": "off"})
    assert "campaign base text for the brief test" in got.out, (
        "brief rendering wrong: %s" % got.out[:400]
    )
    assert "newest note wins" in got.out, got.out[:400]
    assert "first old note" not in got.out, got.out[:400]
    assert "second old note" not in got.out, got.out[:400]

    full = wl.cli("--list").out
    assert "first old note" in full, "160 CONTROL: the store lost history: %s" % full[:300]
    assert "second old note" in full, full[:300]


def test_160b_own_worklist_activity_resets_the_stuck_counter(wl):  # noqa: F811
    """v14 gap 2. A session ticking/leasing/updating items hourly is MOVING even when its long-horizon harness tasks never flip; only a session doing neither counts. STUCK_ROUNDS=2 so tasks-plus-head fires at 2 unchanged stops (1 would fire on every stop by construction: a fresh signature starts its count at 1)."""
    wl.brief_now()
    wl.hand_now()
    wl.env["WORKLIST_STUCK_ROUNDS"] = "2"
    wl.task(7, "pending", "long-horizon watch")
    fired = False
    last = None
    for index in range(1, 5):
        wl.newturn()
        wl.say("answer\n\n## Remaining\n- #7 long-horizon watch (pending)")
        last = wl.run()
        fired = fired or "CONSECUTIVE STOPS" in last.out
        aid = added_id(wl.cli("--add", "deadbeef", "movement item %d" % index))
        wl.cli("--tick", "deadbeef", aid, "done, exit 0")
    assert not fired, "160b: an active session still read as stuck: %s" % last.out[:250]


def test_160b_control_with_no_activity_the_detector_still_fires(wl):  # noqa: F811
    """CONTROL: the identical shape WITHOUT worklist activity fires."""
    wl.brief_now()
    wl.hand_now()
    wl.env["WORKLIST_STUCK_ROUNDS"] = "2"
    wl.task(7, "pending", "long-horizon watch")
    fired = False
    last = None
    for _ in range(4):
        wl.newturn()
        wl.say("answer\n\n## Remaining\n- #7 long-horizon watch (pending)")
        last = wl.run()
        fired = fired or "CONSECUTIVE STOPS" in last.out
    assert fired, "160b CONTROL: the stuck detector never fired: %s" % last.out[:250]


def test_160c_lease_warns_when_the_worker_id_is_not_a_running_task(wl):  # noqa: F811
    """v14 gap 3: a name-not-id lease is warned about, naming the real ids, and the CONTROL is a real task id, which is verified with no warning."""
    wl.brief_now()
    wl.hand_now()
    cid = added_id(wl.cli("--add", "deadbeef", "leased thing"))
    wl.stem(".lastevent-deadbeef.json").write_text(
        json.dumps(
            {
                "background_tasks": [
                    {"id": "bw1", "type": "shell", "status": "running", "description": "real watch"}
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    named = wl.cli("--lease", "deadbeef", cid, "+30", "worker:my-agent-name", "watching")
    both = named.out + named.err
    assert "WARNING: worker:my-agent-name is not among" in both, (
        "160c: no warning for an unverifiable worker: %s" % both[:250]
    )
    assert "bw1" in both, both[:250]

    verified = wl.cli("--lease", "deadbeef", cid, "+30", "worker:bw1", "watching")
    both = verified.out + verified.err
    assert "worker verified against the harness" in both, (
        "160c CONTROL: verification suffix missing: %s" % both[:250]
    )
    assert "WARNING" not in both, both[:250]


def test_160d_an_expired_lease_with_an_os_verified_worker_stays_in_flight(wl):  # noqa: F811
    """v14 gap 4, with its CONTROL: the same expired lease with the worker GONE fails closed as before."""
    wl.brief_now()
    wl.hand_now()
    fresh = stamp()
    past = stamp(5, "%Y-%m-%dT%H:%MZ")
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "dddd0001",
            "at": fresh,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "long CI watch",
        },
    )
    plant_event(
        wl,
        {
            "ev": "lease",
            "id": "dddd0001",
            "at": fresh,
            "by": "deadbeef",
            "until": past,
            "worker": "bw1",
        },
    )
    wl.bg = json.dumps(
        [{"id": "bw1", "type": "shell", "status": "running", "description": "the long CI watch"}]
    )
    wl.say("answer\n\n## Remaining\n- the long CI watch, in flight on bw1")
    got = wl.run({"WORKLIST_FOCUS": "off"})
    assert "lease expired; finish it" not in got.out, (
        "160d: a supervised long job still failed closed: %s" % got.out[:300]
    )
    assert "OPEN worklist item" not in got.out, got.out[:300]

    wl.bg = "[]"
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- the long CI watch, in flight on bw1")
    gone = wl.run({"WORKLIST_FOCUS": "off"})
    assert "lease expired; finish it" in gone.out, (
        "160d CONTROL: the expired lease was tolerated without a live worker: %s" % gone.out[:300]
    )


def test_160e_own_bookkeeping_does_not_stale_the_state_document_but_structure_does(wl):  # noqa: F811
    """v14 gap 5. The lease vehicle exists and is ALREADY `[>]` before the document is written, so the later renewal changes no structure (state stays '>', only until/upd move), which is exactly the bookkeeping-only shape this gap is about."""
    wl.brief_now()
    fid = added_id(wl.cli("--add", "deadbeef", "lease vehicle"))
    wl.cli("--lease", "deadbeef", fid, "+60", "worker:bw9", "watching the long job")
    wl.bg = json.dumps(
        [{"id": "bw9", "type": "shell", "status": "running", "description": "the long job"}]
    )
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.run()

    wl.age_state("deadbeef", 20)
    wl.cli("--lease", "deadbeef", fid, "+90", "worker:bw9", "renewing the watch lease")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    got = wl.run()
    assert "STATE.md is stale" not in got.out, (
        "160e: own bookkeeping staled the document: %s" % got.out[:300]
    )

    wl.cli("--add", "deadbeef", "genuinely new work")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    structural = wl.run({"WORKLIST_FOCUS": "off"})
    assert "STATE.md is stale" in structural.out, (
        "160e CONTROL: structure moved and staleness never fired: %s" % structural.out[:300]
    )


def test_160f_an_unchanged_world_accepts_the_banked_remaining_report(wl):  # noqa: F811
    """v14 gap 6, with its CONTROL: the world moves (a new open item) and the demand returns, so the bank cannot outlive the world it described."""
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.run()

    wl.newturn()
    wl.say("bookkeeping-only turn, nothing moved since the last report")
    got = wl.run()
    assert "no '## Remaining' section" not in got.out, (
        "160f: an unchanged world still demanded a restatement: %s" % got.out[:300]
    )

    wl.cli("--add", "deadbeef", "new work invalidates the bank")
    wl.newturn()
    wl.say("another turn without a remaining section")
    moved = wl.run({"WORKLIST_FOCUS": "off"})
    assert "no '## Remaining' section" in moved.out, (
        "160f CONTROL: the bank outlived the world it described: %s" % moved.out[:300]
    )
