"""rediacc_ci.ops.sched_freshness: a scheduled workflow GitHub stopped firing is named with its fix, against a fake history; every positive case sits beside a control that differs in the one thing under test."""

from __future__ import annotations

import datetime
import re

import pytest

from rediacc_ci.ops import sched_freshness as F

SLUG = "fake/repo"
NOW = datetime.datetime(2026, 11, 21, 12, 0, tzinfo=datetime.UTC).timestamp()
H = 3600
D = 24 * H

DAILY = {
    "file": "housekeeping.yml",
    "name": "Housekeeping",
    "crons": ["0 3 * * *"],
    "dispatchable": True,
}
WEEKLY = {
    "file": "ct-backup-perf.yml",
    "name": "CT Backup Perf",
    "crons": ["30 2 * * 6"],
    "dispatchable": True,
}
MONTHLY = {
    "file": "ci-vm-bake.yml",
    "name": "CI - VM Bake",
    "crons": ["0 2 1 * *"],
    "dispatchable": False,
}


def iso(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def reg(file, wid, state="active", created=NOW - 400 * D):
    return {
        "id": wid,
        "path": ".github/workflows/%s" % file,
        "state": state,
        "created_at": iso(created),
    }


def run(file, rid, created, event="schedule", status="completed"):
    return {
        "id": rid,
        "path": ".github/workflows/%s" % file,
        "event": event,
        "status": status,
        "created_at": iso(created),
    }


class FakeGh:
    """A routing fake of `wl_gh.call`: each call is logged, so a read is COUNTED, and each answer is chosen by a substring of the path."""

    def __init__(self):
        self.calls: list[str] = []
        self.routes: list[tuple[str, object, str]] = []

    def route(self, needle, out=None, err=""):
        self.routes.append((needle, out, err))
        return self

    def __call__(self, argv):
        path = " ".join(argv)
        self.calls.append(path)
        for needle, out, err in self.routes:
            if needle in path:
                return (None, err) if err else (out, "")
        return None, "no route for %s" % path

    def count(self, needle):
        return len([c for c in self.calls if needle in c])


def history(workflows, runs, fallback=None, enabled=True, registry=None):
    gh = FakeGh()
    gh.route("actions/permissions", {"enabled": enabled})
    for needle, out in (fallback or {}).items():
        gh.route(needle, out)
    gh.route("/runs?event=schedule&per_page=1", {"workflow_runs": []})
    gh.route("actions/runs?event=schedule", {"workflow_runs": runs})
    regs = (
        registry
        if registry is not None
        else [reg(w["file"], 100 + i) for i, w in enumerate(workflows)]
    )
    gh.route("actions/workflows?per_page=100", {"total_count": len(regs), "workflows": regs})
    return gh


def verdicts(doc):
    return {r["file"]: r["verdict"] for r in doc["rows"]}


# --------------------------------------------------------------------------- the window


@pytest.mark.parametrize(
    ("crons", "hours"),
    [
        (["0 3 * * *"], 48),
        (["23 */6 * * *"], 48),
        (["30 2 * * 6"], 8 * 24),
        (["0 2 1 * *"], 32 * 24),
        # A weekly and a daily cron on one file: the union fires daily.
        (["0 1 * * *", "0 1 * * 0"], 48),
        # Both day fields restricted: Vixie cron fires on EITHER, so the 1st or any Monday, a week at most.
        (["0 0 1 * 1"], 8 * 24),
        (["0 9 * * mon-fri"], 3 * 24 + 24),
    ],
)
def test_window_scales_with_the_cron_period(crons, hours):
    assert F.window_s(crons) == hours * H


@pytest.mark.parametrize(
    ("bad", "why"),
    [
        ("0 3 * *", "has 4 fields"),
        ("61 3 * * *", "minute: 61 is outside"),
        ("0 3 * * fri-mon", "runs backwards"),
        ("x 3 * * *", "is not a number"),
        ("*/0 * * * *", "bad step"),
    ],
)
def test_a_cron_that_does_not_parse_raises_naming_it(bad, why):
    with pytest.raises(ValueError, match=re.escape(why)):
        F.window_s([bad])
    # Control: one parseable cron beside the bad one carries the file.
    assert F.window_s([bad, "0 3 * * *"]) == 48 * H


# --------------------------------------------------------------------------- the verdict


def test_fresh_is_silent():
    gh = history([DAILY], [run(DAILY["file"], 1, NOW - 20 * H)])
    doc = F.read(gh, SLUG, [DAILY], NOW)
    assert doc["state"] == "ok"
    assert verdicts(doc) == {"housekeeping.yml": "fresh"}
    assert F.advisory(doc) == ""
    assert gh.count("actions/permissions") == 0, "nothing actionable reads no permissions"


def test_49h_stale_names_the_workflow_and_the_fix_command():
    gh = history([DAILY], [run(DAILY["file"], 7, NOW - 49 * H)])
    doc = F.read(gh, SLUG, [DAILY], NOW)
    assert verdicts(doc) == {"housekeeping.yml": "stale"}
    text = F.advisory(doc, "abcd1234")
    assert "STALE: Housekeeping (housekeeping.yml), cron 0 3 * * *" in text
    assert "no scheduled run on main for 49 h" in text
    assert "gh workflow run housekeeping.yml --repo fake/repo --ref main" in text
    assert "gh workflow enable housekeeping.yml --repo fake/repo" in text
    assert "worklist.py --add abcd1234 'sched-stale:housekeeping" in text
    assert "operator" in text
    assert "nothing is sent to the operator" in text
    # Control: 47 h is inside the 48 h window, so the same workflow is silent.
    doc = F.read(history([DAILY], [run(DAILY["file"], 7, NOW - 47 * H)]), SLUG, [DAILY], NOW)
    assert verdicts(doc) == {"housekeeping.yml": "fresh"}
    assert F.advisory(doc) == ""


def test_a_workflow_without_dispatch_gets_no_dispatch_command():
    gh = history([dict(DAILY, dispatchable=False)], [run(DAILY["file"], 7, NOW - 60 * H)])
    text = F.advisory(F.read(gh, SLUG, [dict(DAILY, dispatchable=False)], NOW))
    assert "STALE" in text
    assert "gh workflow run" not in text


def test_a_weekly_cron_is_judged_on_its_own_period():
    six_days = [run(WEEKLY["file"], 3, NOW - 6 * D)]
    doc = F.read(history([WEEKLY], six_days), SLUG, [WEEKLY], NOW)
    assert verdicts(doc) == {"ct-backup-perf.yml": "fresh"}
    # Control 1: the same six-day age on a DAILY cron is stale, so the weekly pass is the period and not a lax window.
    daily_six = [run(DAILY["file"], 3, NOW - 6 * D)]
    assert verdicts(F.read(history([DAILY], daily_six), SLUG, [DAILY], NOW)) == {
        "housekeeping.yml": "stale"
    }
    # Control 2: nine days misses a weekly firing plus its day of grace.
    nine = [run(WEEKLY["file"], 3, NOW - 9 * D)]
    assert verdicts(F.read(history([WEEKLY], nine), SLUG, [WEEKLY], NOW)) == {
        "ct-backup-perf.yml": "stale"
    }


def test_a_monthly_cron_missing_from_the_page_is_read_by_registry_id():
    """The real 2026-11-21 case: ci-vm-bake's last scheduled run was 2026-10-01, its 2026-11-01 firing fell in the outage."""
    gh = history(
        [DAILY, MONTHLY],
        [run(DAILY["file"], 1, NOW - 5 * H)],
        fallback={"workflows/101/runs": {"workflow_runs": [run(MONTHLY["file"], 9, NOW - 51 * D)]}},
    )
    doc = F.read(gh, SLUG, [DAILY, MONTHLY], NOW)
    assert verdicts(doc) == {"housekeeping.yml": "fresh", "ci-vm-bake.yml": "stale"}
    assert gh.count("workflows/101/runs") == 1
    assert gh.count("workflows/100/runs") == 0
    text = F.advisory(doc)
    assert "CI - VM Bake (ci-vm-bake.yml)" in text
    assert "51 days" in text
    assert "window 32 days" in text
    # Control: a run 20 days ago is inside the monthly window.
    gh = history(
        [DAILY, MONTHLY],
        [run(DAILY["file"], 1, NOW - 5 * H)],
        fallback={"workflows/101/runs": {"workflow_runs": [run(MONTHLY["file"], 9, NOW - 20 * D)]}},
    )
    assert verdicts(F.read(gh, SLUG, [DAILY, MONTHLY], NOW))["ci-vm-bake.yml"] == "fresh"


def test_an_unreadable_history_is_named_unreadable_not_fresh():
    gh = FakeGh().route(
        "actions/workflows?per_page=100", err="gh: API rate limit exceeded (HTTP 403)"
    )
    doc = F.read(gh, SLUG, [DAILY], NOW)
    assert doc["state"] == "unreadable"
    assert "rate limit" in doc["error"]
    text = F.advisory(doc)
    assert "UNREADABLE" in text
    assert "UNCHECKED, not fine" in text
    assert F.actionable(doc) == []
    # The runs page failing is the same blindness.
    gh = history([DAILY], [])
    gh.routes.insert(0, ("actions/runs?event=schedule", None, "HTTP 502"))
    doc = F.read(gh, SLUG, [DAILY], NOW)
    assert doc["state"] == "unreadable"
    assert "scheduled runs" in doc["error"]
    # Control: the same workflow with a readable history is judged.
    assert (
        F.read(history([DAILY], [run(DAILY["file"], 1, NOW - H)]), SLUG, [DAILY], NOW)["state"]
        == "ok"
    )


def test_one_failed_fallback_makes_only_that_row_unreadable():
    gh = history([DAILY, MONTHLY], [run(DAILY["file"], 1, NOW - H)])
    gh.routes.insert(0, ("workflows/101/runs", None, "HTTP 500"))
    doc = F.read(gh, SLUG, [DAILY, MONTHLY], NOW)
    assert doc["state"] == "ok"
    assert verdicts(doc) == {"housekeeping.yml": "fresh", "ci-vm-bake.yml": "unreadable"}
    text = F.advisory(doc)
    assert "UNCHECKED: CI - VM Bake (ci-vm-bake.yml)" in text, "a blind row is never silent"


def test_a_registry_larger_than_one_page_is_unreadable_not_half_judged():
    regs = [reg(DAILY["file"], 100)]
    gh = history([DAILY], [run(DAILY["file"], 1, NOW - H)])
    gh.routes.insert(
        0, ("actions/workflows?per_page=100", {"total_count": 150, "workflows": regs}, "")
    )
    assert F.read(gh, SLUG, [DAILY], NOW)["state"] == "unreadable"


def test_disabled_inactivity_is_actionable_whatever_the_last_run():
    regs = [reg(DAILY["file"], 100, state="disabled_inactivity")]
    doc = F.read(
        history([DAILY], [run(DAILY["file"], 1, NOW - H)], registry=regs), SLUG, [DAILY], NOW
    )
    assert verdicts(doc) == {"housekeeping.yml": "disabled"}
    text = F.advisory(doc)
    assert "DISABLED" in text
    assert "disabled_inactivity" in text
    assert "fix: gh workflow enable housekeeping.yml --repo fake/repo" in text


def test_never_run_is_waiting_inside_the_window_and_stale_past_it():
    young = [reg(DAILY["file"], 100, created=NOW - 20 * H)]
    doc = F.read(history([DAILY], [], registry=young), SLUG, [DAILY], NOW)
    assert verdicts(doc) == {"housekeeping.yml": "waiting"}
    assert F.advisory(doc) == ""
    old = [reg(DAILY["file"], 100, created=NOW - 10 * D)]
    doc = F.read(history([DAILY], [], registry=old), SLUG, [DAILY], NOW)
    assert verdicts(doc) == {"housekeeping.yml": "stale"}
    assert "no scheduled run on record" in F.advisory(doc)


def test_a_file_github_does_not_register_is_unregistered():
    doc = F.read(history([DAILY], [], registry=[]), SLUG, [DAILY], NOW)
    assert verdicts(doc) == {"housekeeping.yml": "unregistered"}
    assert "UNREGISTERED" in F.advisory(doc)


def test_actions_disabled_on_the_repo_is_named_as_the_cause_with_its_fix():
    gh = history([DAILY], [run(DAILY["file"], 1, NOW - 3 * D)], enabled=False)
    text = F.advisory(F.read(gh, SLUG, [DAILY], NOW))
    assert "CAUSE: GitHub Actions is DISABLED for fake/repo" in text
    assert "gh api -X PUT repos/fake/repo/actions/permissions -F enabled=true" in text
    # Control: enabled says so and prints no PUT.
    gh = history([DAILY], [run(DAILY["file"], 1, NOW - 3 * D)], enabled=True)
    text = F.advisory(F.read(gh, SLUG, [DAILY], NOW))
    assert "enabled (actions/permissions read)" in text
    assert "-X PUT" not in text


def test_an_unread_permissions_answer_is_said_and_points_at_the_read():
    gh = history([DAILY], [run(DAILY["file"], 1, NOW - 3 * D)])
    gh.routes.insert(0, ("actions/permissions", None, "HTTP 403"))
    text = F.advisory(F.read(gh, SLUG, [DAILY], NOW))
    assert "Actions on the repo: unread (HTTP 403)" in text


def test_the_real_outage_replayed_reads_every_workflow_stale_at_once():
    """The last scheduled runs before the 2026-10-30T13:14Z .. 2026-11-18T15:20Z outage, judged on 2026-11-17: every workflow stale, which names the repo-wide cause."""
    last = {
        "ci-obs-mirror.yml": "2026-10-30T13:12:29Z",
        "housekeeping.yml": "2026-10-30T09:45:47Z",
        "ci.yml": "2026-10-30T06:49:05Z",
        "pins-soaked.yml": "2026-10-30T06:06:37Z",
        "promote-stable.yml": "2026-10-30T12:23:23Z",
    }
    crons = {
        "ci-obs-mirror.yml": "23 */6 * * *",
        "housekeeping.yml": "0 3 * * *",
        "ci.yml": "0 1 * * *",
        "pins-soaked.yml": "30 0 * * *",
        "promote-stable.yml": "0 6 * * *",
    }
    wfs = [{"file": f, "name": f, "crons": [c], "dispatchable": True} for f, c in crons.items()]
    runs = [run(f, i, F.parse_iso(t) or 0.0) for i, (f, t) in enumerate(last.items(), start=1)]
    during = datetime.datetime(2026, 11, 17, 12, 0, tzinfo=datetime.UTC).timestamp()
    doc = F.read(history(wfs, runs), SLUG, wfs, during)
    assert set(verdicts(doc).values()) == {"stale"}
    assert F.everything_stale(doc["rows"])
    assert "EVERY judged workflow is stale at once" in F.advisory(doc)
    # Control: the day after the last runs, nothing is stale.
    before = datetime.datetime(2026, 10, 31, 12, 0, tzinfo=datetime.UTC).timestamp()
    doc = F.read(history(wfs, runs), SLUG, wfs, before)
    assert set(verdicts(doc).values()) == {"fresh"}
    assert F.advisory(doc) == ""


def test_dispatch_and_push_runs_do_not_count_as_the_scheduler_firing():
    runs = [
        run(DAILY["file"], 2, NOW - H, event="workflow_dispatch"),
        run(DAILY["file"], 1, NOW - 3 * D),
    ]
    assert verdicts(F.read(history([DAILY], runs), SLUG, [DAILY], NOW)) == {
        "housekeeping.yml": "stale"
    }
    # Control: the same recent run as a SCHEDULED one, in flight, counts: the scheduler fired.
    runs[0] = run(DAILY["file"], 2, NOW - H, status="in_progress")
    assert verdicts(F.read(history([DAILY], runs), SLUG, [DAILY], NOW)) == {
        "housekeeping.yml": "fresh"
    }


def test_the_call_budget():
    gh = history(
        [DAILY, WEEKLY], [run(DAILY["file"], 1, NOW - H), run(WEEKLY["file"], 2, NOW - 2 * D)]
    )
    F.read(gh, SLUG, [DAILY, WEEKLY], NOW)
    assert len(gh.calls) == 2, gh.calls
    # A stale row adds exactly the permissions read.
    gh = history([DAILY], [run(DAILY["file"], 1, NOW - 4 * D)])
    F.read(gh, SLUG, [DAILY], NOW)
    assert len(gh.calls) == 3
    assert gh.count("actions/permissions") == 1


@pytest.mark.parametrize(
    ("expr", "dom_any", "dow_any"),
    [("0 0 */2 * 1", True, False), ("0 0 1 * */2", False, True), ("0 0 1 * 1", False, False)],
)
def test_a_day_field_starting_with_a_star_is_unrestricted(expr, dom_any, dow_any):
    spec = F.parse_cron(expr)
    assert (spec["dom_any"], spec["dow_any"]) == (dom_any, dow_any)
