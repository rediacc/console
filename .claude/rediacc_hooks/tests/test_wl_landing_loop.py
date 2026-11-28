"""The landing state machine of agent/plans/PLAN-simple-two-tree-loop.md D1 (box B2): `wl_prscope.landing_loop` and `landing_step`, the stand-down profile the tree role picks (`wl_standdown.profile_for`), and the development tree's release read (`landing_released`).

Each of the seven states is driven from fixture gh answers (a fake `wl_gh.call` that answers `gh pr view --json mergeCommit` and `gh run list --workflow <file>`) and asserts its one named step; L-IDLE asserts no block. Each fire case has a control one planted fact away, and the mutation control runs a PRIVATE COPY of wl_prscope with the box condition removed, which must then read L-MERGE with a box open.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import types

import pytest

from rediacc_hooks.tests import wlfix

P = wlfix.import_wl("wl_prscope")
SD = wlfix.import_wl("wl_standdown")

SHA = "feedface00000000000000000000000000000001"
LATER = "feedface00000000000000000000000000000002"


def run(sha, conclusion, created="2026-11-21T10:00:00Z", status="completed", rid=4242):
    return {
        "databaseId": rid,
        "headSha": sha,
        "status": status,
        "conclusion": conclusion,
        "createdAt": created,
    }


class FakeGh:
    """`wl_gh.call`'s shape (argv, cwd) -> (data, error), answering from planted rows; every call is logged."""

    def __init__(self, sha=SHA, ci=(), edge=(), down=False):
        self.sha, self.ci, self.edge, self.down = sha, list(ci), list(edge), down
        self.calls: list[list[str]] = []

    def __call__(self, argv, _cwd):
        self.calls.append(list(argv))
        if self.down:
            return None, "`gh %s` exited 1: planted outage" % " ".join(argv[:2])
        if argv[:2] == ["pr", "view"]:
            return {"mergeCommit": {"oid": self.sha}}, ""
        if argv[:2] == ["run", "list"]:
            wf = argv[argv.index("--workflow") + 1]
            return (self.ci if wf == "ci.yml" else self.edge), ""
        return None, "unexpected gh call %r" % argv


def node(state, number=7, body="Plan: agent/plans/PLAN-own.md\n"):
    return {"number": number, "state": state, "body": body}


def loop(nodes, ci=P.CI_PENDING, reviews=True, boxes=0, gh=None, detail=""):
    return P.landing_loop(
        pathlib.Path("."), nodes, ci, reviews, boxes_open=boxes, gh=gh or FakeGh(), ci_detail=detail
    )


# ---- the open PR: L-CI, L-FIX, L-REVIEW, L-MERGE ---------------------------------------------


def test_l_ci_checks_in_flight():
    step = loop([node("OPEN")], ci=P.CI_PENDING)
    assert step.state == P.L_CI
    assert step.blocks
    assert "ci-watch skill" in step.text


def test_l_fix_a_required_check_red():
    step = loop([node("OPEN")], ci=P.CI_RED, detail="Quality / Static")
    assert step.state == P.L_FIX
    assert step.blocks
    assert "Quality / Static" in step.text
    assert "D4" in step.text


def test_l_review_ci_green_and_a_box_open():
    step = loop([node("OPEN")], ci=P.CI_GREEN, boxes=1)
    assert step.state == P.L_REVIEW
    assert step.blocks
    assert "1 open box" in step.text


def test_l_review_ci_green_and_a_review_open():
    step = loop([node("OPEN")], ci=P.CI_GREEN, reviews=False)
    assert step.state == P.L_REVIEW
    assert "wl_prreview.py" in step.text


def test_l_review_unreadable_boxes_never_merge():
    assert loop([node("OPEN")], ci=P.CI_GREEN, boxes=-1).state == P.L_REVIEW


def test_l_merge_all_clear():
    step = loop([node("OPEN", number=9)], ci=P.CI_GREEN)
    assert step.state == P.L_MERGE
    assert step.blocks
    assert "gh pr merge 9 --rebase --auto" in step.text


def test_open_pr_reads_no_release():
    gh = FakeGh()
    loop([node("OPEN")], ci=P.CI_GREEN, gh=gh)
    assert gh.calls == []


def test_open_pr_wins_over_an_older_merged_one():
    step = loop([node("MERGED", number=5), node("OPEN", number=9)], ci=P.CI_PENDING)
    assert (step.state, step.pr) == (P.L_CI, 9)


def _mutant_prscope():
    """A PRIVATE COPY of wl_prscope whose L-REVIEW branch ignores the open boxes."""
    path = pathlib.Path(P.__file__)
    src = path.read_text(encoding="utf-8")
    old = "        if boxes_open != 0 or not reviews_clean:\n"
    assert src.count(old) == 1
    name = "wl_prscope_mutant"
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    # dataclasses resolve string annotations through sys.modules, so the copy is registered while it runs.
    sys.modules[name] = mod
    try:
        code = compile(src.replace(old, "        if not reviews_clean:\n"), str(path), "exec")
        exec(code, mod.__dict__)
    finally:
        sys.modules.pop(name, None)
    return mod


def test_mutant_box_check_removed_merges_with_a_box_open():
    """The control: without the box condition the open-box world reads L-MERGE, so test_l_review_ci_green_and_a_box_open goes red."""
    mutant = _mutant_prscope()
    step = mutant.landing_step("OPEN", 7, mutant.CI_GREEN, 1, True)
    assert step.state == mutant.L_MERGE
    assert P.landing_step("OPEN", 7, P.CI_GREEN, 1, True).state == P.L_REVIEW


# ---- after the merge: L-RELEASE, L-HOTFIX, L-IDLE --------------------------------------------


def test_l_release_no_main_run_yet():
    gh = FakeGh()
    step = loop([node("MERGED")], gh=gh)
    assert step.state == P.L_RELEASE
    assert step.blocks
    assert step.sha == SHA
    assert SHA[:12] in step.text
    assert ["pr", "view", "7", "--json", "mergeCommit"] in gh.calls


def test_l_release_edge_deploy_in_flight():
    gh = FakeGh(ci=[run(SHA, "success")], edge=[run(SHA, "", status="in_progress")])
    step = loop([node("MERGED")], gh=gh)
    assert step.state == P.L_RELEASE
    assert "CD - Release to Edge" in step.text


def test_l_hotfix_main_only_red():
    gh = FakeGh(ci=[run(SHA, "failure", rid=91)], edge=[run(SHA, "success")])
    step = loop([node("MERGED")], gh=gh)
    assert step.state == P.L_HOTFIX
    assert step.blocks
    assert "run 91" in step.text
    assert "[hotfix]" in step.text
    assert "Hotfix-Evidence:" in step.text


def test_l_hotfix_edge_deploy_red():
    gh = FakeGh(ci=[run(SHA, "success")], edge=[run(SHA, "failure")])
    assert loop([node("MERGED")], gh=gh).state == P.L_HOTFIX


def test_l_idle_after_a_green_release():
    gh = FakeGh(ci=[run(SHA, "success")], edge=[run(SHA, "success")])
    step = loop([node("MERGED")], gh=gh)
    assert step.state == P.L_IDLE
    assert not step.blocks
    assert step.release
    assert step.sha == SHA


def test_l_idle_no_pr():
    step = loop([])
    assert step.state == P.L_IDLE
    assert not step.blocks
    assert not step.release


def test_l_idle_only_a_closed_pr():
    assert loop([node("CLOSED")]).state == P.L_IDLE


def test_a_later_green_main_run_supersedes_the_red_merged_one():
    """A hotfix on main: the newest Console CI run is green after the merged sha's red one."""
    gh = FakeGh(
        ci=[
            run(LATER, "success", created="2026-11-21T12:00:00Z"),
            run(SHA, "failure", created="2026-11-21T10:00:00Z"),
        ],
        edge=[run(SHA, "success")],
    )
    assert loop([node("MERGED")], gh=gh).state == P.L_IDLE


def test_control_red_merged_run_without_a_later_one_stays_hotfix():
    gh = FakeGh(ci=[run(SHA, "failure")], edge=[run(SHA, "success")])
    assert loop([node("MERGED")], gh=gh).state == P.L_HOTFIX


def test_skipped_edge_deploy_is_not_green():
    gh = FakeGh(ci=[run(SHA, "success")], edge=[run(SHA, "skipped")])
    assert loop([node("MERGED")], gh=gh).state == P.L_RELEASE


def test_unreadable_world_never_blocks():
    step = loop([node("MERGED")], gh=FakeGh(down=True))
    assert step.state == ""
    assert not step.blocks
    assert "planted outage" in step.text


@pytest.mark.parametrize("state", P.LANDING_STATES)
def test_every_state_has_one_step_text(state):
    assert state in P.LANDING_STEP_TEXT
    assert ("LANDING %s:" % state) in P.LANDING_STEP_TEXT[state] % {
        "state": state,
        "pr": 1,
        "sha": "x",
        "detail": "",
    }


# ---- the development tree's release read -----------------------------------------------------


def test_landing_released_green():
    gh = FakeGh(ci=[run(SHA, "success")], edge=[run(SHA, "success")])
    assert P.landing_released(pathlib.Path("."), [node("MERGED", number=12)], gh) == 12


def test_control_landing_released_red_main():
    gh = FakeGh(ci=[run(SHA, "failure")], edge=[run(SHA, "success")])
    assert P.landing_released(pathlib.Path("."), [node("MERGED", number=12)], gh) == 0


def test_landing_released_unreadable_is_not_pending():
    # Review a77a0f9e.1: a gh outage after the merge reads UNREADABLE_RELEASE, never 0 ("pending") and never a PR number ("released").
    gh = FakeGh(ci=[run(SHA, "success")], edge=[run(SHA, "success")], down=True)
    value = P.landing_released(pathlib.Path("."), [node("MERGED", number=12)], gh)
    assert value == P.UNREADABLE_RELEASE
    assert value < 0


def test_control_landing_released_open_pr_reads_nothing():
    gh = FakeGh(ci=[run(SHA, "success")], edge=[run(SHA, "success")])
    assert P.landing_released(pathlib.Path("."), [node("OPEN", number=12)], gh) == 0
    assert gh.calls == []


def test_control_landing_released_gh_down():
    assert (
        P.landing_released(pathlib.Path("."), [node("MERGED")], FakeGh(down=True))
        == P.UNREADABLE_RELEASE
    )


# ---- the tree role decides the parks and the stand-down --------------------------------------


def _state(role):
    return P.LoopState(P.LIVE, role=role)


def test_tree_parks_follow_the_role_alone():
    assert P.tree_parks(_state(P.LANDING)) == P.LANDING_PARKS
    assert P.tree_parks(_state(P.DEVELOPMENT)) == P.DEVELOPMENT_PARKS
    assert P.tree_parks(_state("")) == frozenset()
    with pytest.raises(TypeError):
        P.tree_parks(_state(P.DEVELOPMENT), {"mode": "babysit"})


def test_profile_landing_tree_by_role():
    assert SD.profile_for("landing", False, False) is SD.LANDING_TREE
    assert SD.profile_for("landing", True, True) is SD.LANDING_TREE


def test_profile_development_tree_builds():
    assert SD.profile_for("development", False, True) is SD.PR_LOOP
    assert SD.profile_for("development", True, True) is SD.CONC_WAIT
    assert SD.profile_for("development", False, False) is None


def test_control_profile_no_record_follows_the_loop():
    assert SD.profile_for("", False, True) is SD.PR_LOOP
    assert SD.profile_for("", True, True) is SD.CONC_WAIT
    assert SD.profile_for("", False, False) is None
    assert not hasattr(SD, "FOCUS"), "the FOCUS profile went with the phase verb (B10)"


def test_landing_tree_profile_keeps_the_pr_and_parks_new_work():
    prof = SD.LANDING_TREE
    for key in ("loop-next", "ci-red", "pr-review", "pr-finish", "open-items", "agent-state"):
        assert SD.keeps(prof, key, False, False), key
    for key in ("plan-unimplemented", "idle-stall", "plan-adopted", "unblocked-claim"):
        assert not SD.keeps(prof, key, False, False), key
        assert SD.keeps(SD.PR_LOOP, key, False, False), key


# ---- the wl_checks side: the CI verdict and the development tree's code-complete read ----------

CHECKS = wlfix.import_wl("wl_checks")


@pytest.mark.parametrize(
    ("cistate", "want"),
    [
        ("ok", P.CI_GREEN),
        ("trouble", P.CI_RED),
        ("fixing", P.CI_RED),
        ("watched", P.CI_RED),
        ("cancelled", P.CI_RED),
        ("pending", P.CI_PENDING),
        ("unreadable", P.CI_PENDING),
        ("unset", P.CI_PENDING),
        ("soft", P.CI_PENDING),
    ],
)
def test_ci_verdict(cistate, want):
    assert CHECKS.ci_verdict(cistate, {}) == want


def _git(cwd, *args):
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _branch_with_plan(tmp, writer_box):
    repo = tmp / "repo"
    (repo / "agent" / "plans").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    (repo / "agent" / "plans" / "PLAN-x.md").write_text(
        "# PLAN x\n\n## Tasks\n\n%s- [ ] B9 [lead] a lead box stays open\n" % writer_box,
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feat: x\n\nPlan-Box: PLAN-x.md#0123abcd clauses=all")
    return repo


def test_branch_writer_boxes_names_an_open_writer_box(tmp_path):
    repo = _branch_with_plan(tmp_path, "- [ ] B1 [writer] a writer box is open\n")
    assert CHECKS.branch_writer_boxes(repo) == ["PLAN-x.md:B1"]


def test_control_branch_writer_boxes_ticked_and_lead_only(tmp_path):
    repo = _branch_with_plan(tmp_path, "- [x] B1 [writer] a writer box is ticked\n")
    assert CHECKS.branch_writer_boxes(repo) == []


def test_branch_writer_boxes_is_none_when_the_log_read_fails(tmp_path):
    """69e02bd5.3: a failed log read (no origin/main here) is None, not an empty list that reads as no open writer box."""
    repo = tmp_path / "plain"
    repo.mkdir()
    _git(repo, "init", "-q")
    assert CHECKS.branch_writer_boxes(repo) is None
