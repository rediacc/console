"""The writers-now seeds carry fired armed actions (agent/plans/PLAN-armed-actions.md box AA5).

A survey `## Armed` BOX row is driven through the real survey reader, token parser, arm-time validator and evaluator against a throwaway git repo. Each positive has its control: the arm is silent while the box is open at HEAD, silent when it fired before `since`, silent for another session's item, and silent once started.
"""

from __future__ import annotations

import datetime
import pathlib
import subprocess

import pytest
import wl_armed as A
import wl_core as C

from rediacc_hooks.tests import wlfix

WN = wlfix.import_wl("wl_writersnow")

ME = "cafe0005"
SIG = "e1d00ffe"
PLAN = """# PLAN: widgets
Status: approved

## Boxes

- [%s] B1 [writer] build the first widget carefully
- [ ] B2 [writer] build the second widget carefully
"""
SURVEY = """# survey

## 10. Armed

| blocker | dependent sigs | trigger | brief draft path |
|---|---|---|---|
| B1 | 11111111 | `BOX:agent/plans/PLAN-w.md#%s` | /tmp/draft.md |
"""
SINCE = datetime.datetime(2026, 11, 24, 6, 0, 0, tzinfo=datetime.UTC)
HOUR = datetime.timedelta(hours=1)


def git(repo, *args):
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "agent" / "plans").mkdir(parents=True)
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "agent" / "plans" / "PLAN-w.md").write_text(PLAN % " ", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "plan")
    return root


def survey_arm(repo):
    rows, problems = A.survey_rows(SURVEY % SIG)
    assert problems == []
    when = A.parse_when(
        A.trigger_tokens(rows[0]["trigger"]),
        A.ArmWorld(root=repo, now=C.utcnow(), by_id={}),
    )
    return {
        "aid": "0123abcd",
        "when": when,
        "at": A.stamp(SINCE),
        "exp": A.stamp(SINCE + 24 * HOUR),
        "verdict": "",
        "started_at": "",
        "fired_at": "",
    }


def item(arm, owner=ME):
    return {"id": "aaaa1111", "state": " ", "owner": owner, "text": "land B2", "arm": arm}


def latch(repo, arm, when):
    """The arm as the Stop hook's sweep leaves it after evaluating at `when`."""
    ctx = A.Ctx(root=repo, now=when, by_id={}, show_head=lambda p: A.show_head(repo, p))
    verdict, why = A.evaluate(arm, ctx)
    if verdict == A.ARMED:
        return arm
    return dict(arm, verdict=verdict, why=why, fired_at=A.stamp(when))


def fired_arm(repo, minutes=60):
    return dict(
        survey_arm(repo),
        verdict=A.FIRED,
        fired_at=A.stamp(SINCE + datetime.timedelta(minutes=minutes)),
    )


REPORT = {"id": "r1", "agent": "w", "session": ME, "at": "2026-11-24T07:00:00Z"}
PLAIN = {
    "id": "bbbb2222",
    "state": " ",
    "owner": ME,
    "text": "plain item",
    "upd": "2026-11-24T07:00:00Z",
}


def test_box_arm_is_silent_while_open_then_first_seed_once_a_commit_ticks_it(repo):
    arm = survey_arm(repo)
    open_arm = latch(repo, arm, SINCE + HOUR)
    assert open_arm["verdict"] == ""
    assert WN.armed_seeds([item(open_arm)], ME, SINCE) == []
    (repo / "agent" / "plans" / "PLAN-w.md").write_text(PLAN % "x", encoding="utf-8")
    git(repo, "commit", "-qam", "tick")
    fired = latch(repo, arm, SINCE + 2 * HOUR)
    assert fired["verdict"] == A.FIRED
    seeds = WN.collect_seeds([item(fired), PLAIN], [], [(REPORT, "owed=B2\n")], ME, SINCE)
    kinds = [s["kind"] for s in seeds]
    assert kinds[0] == "armed"
    assert seeds[0]["ref"] == "#aaaa1111"
    assert "fired" in seeds[0]["text"]
    assert 0 < kinds.index("report") < kinds.index("item")


def test_an_arm_fired_before_since_is_not_a_seed(repo):
    fired = fired_arm(repo, minutes=0)
    assert WN.armed_seeds([item(fired)], ME, SINCE) == []
    assert len(WN.armed_seeds([item(fired_arm(repo, minutes=1))], ME, SINCE)) == 1


def test_another_sessions_or_a_started_arm_is_not_a_seed(repo):
    fired = fired_arm(repo)
    assert len(WN.armed_seeds([item(fired)], ME, SINCE)) == 1
    assert WN.armed_seeds([item(fired, owner="beef0001")], ME, SINCE) == []
    started = dict(fired, started_at=A.stamp(SINCE + 2 * HOUR))
    assert WN.armed_seeds([item(started)], ME, SINCE) == []


def test_armed_seeds_are_capped_with_a_more_seed_naming_armed_list(repo):
    fired = fired_arm(repo)
    count = WN.KIND_MAX + 2
    items = [dict(item(fired), id="%08x" % n) for n in range(count)]
    seeds = WN.collect_seeds(items, [], [], ME, SINCE)
    more = [s for s in seeds if s["kind"] == "more"]
    assert len(more) == 1
    assert "worklist.py --armed-list <me>" in more[0]["text"]
    assert "2 more armed seed(s)" in more[0]["text"]
    one = WN.collect_seeds(items[: WN.KIND_MAX], [], [], ME, SINCE)
    assert not [s for s in one if s["kind"] == "more"]


def test_the_skill_and_the_plan_records_name_the_armed_step():
    root = pathlib.Path(__file__).resolve().parents[3]
    skill = (root / ".claude" / "commands" / "writers-now.md").read_text(encoding="utf-8")
    assert "--arm-from-survey" in skill
    assert "## Armed" in skill
    docs = (root / "docs" / "agent-reference" / "plan-records.md").read_text(encoding="utf-8")
    assert "armed_seeds" in docs
