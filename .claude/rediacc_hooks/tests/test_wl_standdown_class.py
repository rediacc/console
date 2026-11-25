"""The PR loop parks nothing silently (agent/plans/PLAN-writers-now-cadence.md, operator ruling #ac2de21f).

ROOT CAUSE this file pins: the operator ordered that at effort `high` a /writers-now round runs at least hourly, and `writers-now-due` (effort.json: block `high`) fired correctly in `wl_writersnow.due`. But the development tree stops under `wl_standdown.PR_LOOP`, a KEEP-list in which a key named in no set stands down, and `writers-now-due` sat in none of CORE, _PR_GUARD, _LOOP_DUTIES or _BUILD_ONLY. Every stop parked it: "Stood down: ... writers-now-due x81" (session ace763dd, last round 3595e029 at 2026-11-23T20:01:30Z).

Three layers: the class guard (every effort.json key blocking at `high` or below is kept by PR_LOOP or named in `wl_standdown.PARKED_BY_DESIGN`, never both), the cadence through the real hook on a live development loop with its controls, and the replay of the 2026-11-23 shape. The mutation case runs a private copy of the hook with the keep line removed, which is the old code, and must see the check stand down again.
"""

from __future__ import annotations

import datetime
import json

from rediacc_hooks.tests import prloop_world as F
from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_cap_wait import mutated_hook
from rediacc_hooks.tests.test_wl_pr_scope_stop import (
    PR_SCOPE,
    epic_for,
    keys_of,
    loop_world,
    pr_node,
    reason,
)
from rediacc_hooks.tests.test_wl_roster import plant_item, stamp

STD = wlfix.import_wl("wl_standdown")
K = wlfix.import_wl("wl_checks")
E = wlfix.import_wl("wl_effort")
WN = wlfix.import_wl("wl_writersnow")
PS = wlfix.import_wl("wl_prscope")
M = wlfix.import_wl("worklist_messages")

KEY = "writers-now-due"
NEEDLE = "WRITERS-NOW DUE"
HIGH = "high"


# ---- the class guard -------------------------------------------------------------------------


def blocking_at_high() -> dict[str, str]:
    """{key: its block level} for every effort.json key that blocks at `high`: a level at or below it, or a FLOOR key."""
    table, problems = E.load()
    assert not problems, problems
    levels = list(table["levels"])
    out = {}
    for key, row in table["checks"].items():
        if row == "floor":
            out[key] = "floor"
        elif (
            isinstance(row, dict)
            and row.get("block") in levels
            and levels.index(row["block"]) <= levels.index(HIGH)
        ):
            out[key] = row["block"]
    assert len(out) > 40, "SETUP: the effort table yielded only %d blocking keys" % len(out)
    return out


def kept_by_pr_loop(key: str) -> bool:
    """The stop's own predicate (wl_checks.stand_down_keeps). A key produced only per subject (`agent-pushback:<id>`) is kept when its `<key>:` form is."""
    return K.stand_down_keeps(STD.PR_LOOP, key, False, False) or K.stand_down_keeps(
        STD.PR_LOOP, key + ":subject", False, False
    )


def test_class_every_key_blocking_at_high_is_kept_by_pr_loop_or_parked_by_design() -> None:
    silent = sorted(
        k for k in blocking_at_high() if not kept_by_pr_loop(k) and k not in STD.PARKED_BY_DESIGN
    )
    assert not silent, (
        "these keys block at effort high but PR_LOOP stands them down with no reason: %s. "
        "Keep each in a wl_standdown set the development tree acts on, or name it in "
        "PARKED_BY_DESIGN with the reason it is out of the one-PR scope." % silent
    )


def test_class_a_parked_key_is_never_also_kept_and_every_parked_key_is_live() -> None:
    both = sorted(k for k in STD.PARKED_BY_DESIGN if kept_by_pr_loop(k))
    assert not both, "kept by PR_LOOP and parked by design at once: %s" % both
    table, _problems = E.load()
    stale = sorted(k for k in STD.PARKED_BY_DESIGN if k not in table["checks"])
    assert not stale, "PARKED_BY_DESIGN names keys effort.json no longer has: %s" % stale
    blank = sorted(k for k, why in STD.PARKED_BY_DESIGN.items() if len(str(why).strip()) < 20)
    assert not blank, "a parked key needs its reason: %s" % blank


def test_class_guard_catches_the_old_keep_lists() -> None:
    """The guard is not vacuous: PR_LOOP without this change's keep leaves writers-now-due neither kept nor parked, which is the guard's failing shape."""
    old = STD.PR_LOOP._replace(keeps=STD.PR_LOOP.keeps - {KEY})
    assert KEY in blocking_at_high()
    assert not K.stand_down_keeps(old, KEY, False, False)
    assert KEY not in STD.PARKED_BY_DESIGN


def test_writers_now_due_is_a_build_duty_parked_in_the_landing_tree() -> None:
    assert K.stand_down_keeps(STD.PR_LOOP, KEY, False, False)
    # Control: the landing tree finishes the one PR and starts nothing.
    assert STD.profile_for(STD.ROLE_LANDING, False, True) is STD.LANDING_TREE
    assert not K.stand_down_keeps(STD.LANDING_TREE, KEY, False, False)


def test_the_block_message_names_writers_now_as_the_action_to_run_now() -> None:
    text = M.V_WRITERS_NOW_DUE % {"window": 60, "last": "x", "open": 3, "who": "deadbeef"}
    assert text.startswith(NEEDLE + ": run /writers-now now."), text


# ---- only a recorded round counts ------------------------------------------------------------


def test_hand_spawned_writers_are_not_a_round(tmp_path) -> None:
    """`due` reads only the round rows `--writers-now-start` appends (wl_writersnow.read_rounds over LEDGER_REL); a session whose writers were spawned by hand, with no round row, still fires."""
    now = datetime.datetime(2026, 11, 24, 3, 15, tzinfo=datetime.UTC)
    dev = PS.LoopState(kind=PS.LIVE, role=PS.DEVELOPMENT)
    fires, facts = WN.due([], "ace763dd", now, 588, dev, root=tmp_path)
    assert fires
    assert facts["last"] is None
    # Control: one round row of this session inside the hour silences it. The round needs a survey written after its start (wl_writersnow.judge_round, 913af37d87): a row naming a survey that was never written stops counting SURVEY_GRACE_MIN minutes after the start.
    # Past the missing-survey grace and still inside the window, so the two assertions below differ only by the survey; derived from the module's own numbers so a change to either keeps that true.
    back = WN.SURVEY_GRACE_MIN + 5
    assert back < WN.WINDOW_MIN
    start = now - datetime.timedelta(minutes=back)
    survey = write_survey(tmp_path / "survey.md", start + datetime.timedelta(minutes=5))
    row = {
        "round": "r1",
        "session": "ace763dd",
        "at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "survey": str(survey),
    }
    assert WN.due([row], "ace763dd", now, 588, dev, root=tmp_path)[0] is False
    # And the same row with its survey gone is not a round, so the control above is the survey and not the row alone.
    survey.unlink()
    assert WN.due([row], "ace763dd", now, 588, dev, root=tmp_path)[0] is True


def plant_live_lease(fix, item_id: str, worker: str) -> None:
    """An open item leased an hour ahead to a hand-spawned writer: the shape a writer spawned outside /writers-now leaves."""
    ahead = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=60)).strftime(
        "%Y-%m-%dT%H:%MZ"
    )
    plant_item(fix, item_id, "(deadbeef) a hand-spawned writer's item")
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "lease",
                    "id": item_id,
                    "at": stamp(1),
                    "by": wlfix.ME,
                    "until": ahead,
                    "worker": worker,
                    "note": "hand-spawned writer",
                    "worker_verified": True,
                }
            )
            + "\n"
        )


def test_stop_hook_live_writer_leases_with_no_round_row_still_fire(wl) -> None:
    loop_world(wl)
    plant_live_lease(wl, "ffff0006", "a1b2c3d4e5f60718")
    got = F.stop(wl)
    assert KEY in keys_of(wl, got), reason(got)[:1500]
    assert not WN.ledger_path(wl.proj).exists()


# ---- the cadence through the real hook on the live development loop ---------------------------


def other_check_outstanding(fix, own: str) -> None:
    """An open item on the PR plan's epic, so `open-items` blocks beside the cadence."""
    plant_item(fix, "aaaa0001", "(deadbeef) the PR plan's own item")
    epic_for(fix, own.rsplit("/", 1)[-1], "aaaa0001")


def write_survey(path, at):
    """A survey file whose mtime is `at`: written after its round started, so wl_writersnow.judge_round counts the round (913af37d87)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# survey\n\n| box | group |\n|---|---|\n| B1 | CODE |\n", encoding="utf-8")
    WN.os.utime(path, (at.timestamp(), at.timestamp()))
    return path


def round_minutes_ago(fix, minutes: float) -> None:
    start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes)
    survey = write_survey(fix.proj / "surveys" / "round.md", start + datetime.timedelta(minutes=1))
    WN.append_round(fix.proj, wlfix.ME, str(survey), start)


def stood_down_line(got) -> str:
    return next((ln for ln in reason(got).splitlines() if PR_SCOPE in ln), "")


def test_pr_loop_a_61_minute_old_round_blocks_and_is_not_stood_down(wl) -> None:
    own = loop_world(wl)
    other_check_outstanding(wl, own)
    round_minutes_ago(wl, 61)
    got = F.stop(wl)
    keys = keys_of(wl, got)
    assert KEY in keys, reason(got)[:1500]
    assert "open-items" in keys, reason(got)[:1500]
    line = stood_down_line(got)
    assert line, "SETUP: the stop is not on the PR loop: %s" % got.out[:1200]
    assert KEY not in line, line


def test_pr_loop_control_a_59_minute_old_round_is_silent(wl) -> None:
    own = loop_world(wl)
    other_check_outstanding(wl, own)
    round_minutes_ago(wl, 59)
    got = F.stop(wl)
    keys = keys_of(wl, got)
    assert "open-items" in keys, reason(got)[:1500]
    assert KEY not in keys
    assert NEEDLE not in got.out


def test_pr_loop_control_the_merge_phase_is_silent(wl) -> None:
    own = loop_world(wl)
    F.merged_nodes(wl, [pr_node("MERGED", "Plan: %s\n\nsummary" % own)])
    round_minutes_ago(wl, 61)
    got = F.stop(wl)
    assert KEY not in keys_of(wl, got), reason(got)[:1500]
    assert NEEDLE not in got.out


def test_pr_loop_m_without_the_keep_line_the_cadence_stands_down_again(wl) -> None:
    """The old code: writers-now-due named in no PR_LOOP set. The same world stands it down and names it in the Stood down phrase."""
    own = loop_world(wl)
    other_check_outstanding(wl, own)
    round_minutes_ago(wl, 61)
    mutated_hook(wl, "wl_standdown.py", '        "writers-now-due",\n', "")
    got = F.stop(wl)
    assert KEY not in keys_of(wl, got), reason(got)[:1500]
    assert KEY in stood_down_line(got), reason(got)[:1500]


# ---- the replay of 2026-11-23 ------------------------------------------------------------------

SESSION = "ace763dd"
LAST_ROUND_AT = datetime.datetime(2026, 11, 23, 20, 1, 30, tzinfo=datetime.UTC)
REPLAY_NOW = datetime.datetime(2026, 11, 24, 3, 15, tzinfo=datetime.UTC)
REPLAY_AGE_MIN = (REPLAY_NOW - LAST_ROUND_AT).total_seconds() / 60


def test_replay_2026_11_23_the_hourly_round_blocks_under_pr_loop() -> None:
    """Session ace763dd: a manual round started 19:48Z, the recorded round 3595e029 at 20:01:30Z, 588 open Promoted boxes, and a stop 81 stops later at 03:15Z. The cadence fires with no stand-down reason, and PR_LOOP, the profile the development tree stops under, keeps it."""
    rows = [
        {"round": "3595e029", "session": SESSION, "at": "2026-11-23T20:01:30Z", "survey": "/tmp/s"}
    ]
    dev = PS.LoopState(kind=PS.LIVE, role=PS.DEVELOPMENT)
    fires, facts = WN.due(rows, SESSION, REPLAY_NOW, 588, dev)
    assert fires, facts
    assert facts["why"] == ""
    assert int(facts["age"]) == int(REPLAY_AGE_MIN) == 433
    profile = STD.profile_for(dev.role, False, True)
    assert profile is STD.PR_LOOP
    assert K.stand_down_keeps(profile, KEY, False, False)


def test_replay_2026_11_23_through_the_hook(wl) -> None:
    """The same shape through the real hook: the newest round 433 minutes old, open Promoted boxes, another check outstanding."""
    own = loop_world(wl)
    other_check_outstanding(wl, own)
    round_minutes_ago(wl, REPLAY_AGE_MIN)
    got = F.stop(wl)
    assert KEY in keys_of(wl, got), reason(got)[:1500]
    assert "/writers-now" in got.out
