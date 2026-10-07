"""`wl_review.py --check` and the merge guard's per-commit review arm (agent/plans/PLAN-per-commit-review.md section 11.6, WP-2).

The precondition both enforce, in the one wording every doc uses: every commit since the base has a per-commit review record in `agent/reviews/<branch>/` with no open finding at or above `block_at`, and every record is committed.

Each case builds a real repository with an `origin/main` and one branch commit, then writes that commit's review record through `wl_review.render`, so no model runs. The fixture's only variable is the record: an open `high` finding (refused), the same record with the finding marked not-a-bug (clean), or no record (unreviewed). The merge arm is driven twice: through `review_refusals` directly, and end to end through
the dispatcher with a stub `gh` that answers `pr view` for a green PR, so the `headRefName` wiring is exercised and not only the helper.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_hooks.guards import block_admin_merge as merge_guard
from rediacc_hooks.tests import wlfix
from rediacc_hooks.wellknown import GH_REPO

R = wlfix.import_wl("wl_review")

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = HERE.parent / "dispatch.py"
WL_REVIEW = HERE.parents[1] / "hooks" / "stop" / "wl_review.py"
BRANCH = "0930-1"

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=GIT_ENV, check=True
    ).stdout.strip()


def _world(tmp_path, record):
    """A checkout of BRANCH one commit past origin/main. `record` is None (no review), "open" (an open high finding) or "resolved" (the same finding marked not-a-bug); a written record is committed beside the commit it reviews."""
    repo = tmp_path / "repo"
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", str(origin)], check=True, capture_output=True, env=GIT_ENV
    )
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-q", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "checkout", "-q", "-b", BRANCH)
    (repo / "f.py").write_text("values = [1, 2]\nfirst = values[1]\n", encoding="utf-8")
    _git(repo, "add", "f.py")
    _git(repo, "commit", "-q", "-m", "fix(x): first value")
    sha = _git(repo, "rev-parse", "HEAD")
    if record in ("ledger", "ledger-dirty", "ledger-garbled", "ledger-empty"):
        _ledger_record(repo, sha, record)
    elif record is not None:
        finding = R.Finding(
            id="%s.1" % sha[:8],
            severity="high",
            file="f.py",
            line=2,
            anchor="in-diff",
            claim="values[1] reads the second element, not the first",
            resolution="open"
            if record == "open"
            else "not-a-bug | f.py:2 names the second element on purpose | deadbeef 2026-10-02T00:00:00Z",
        )
        review = R.Review(
            sha=sha,
            subject="fix(x): first value",
            branch=BRANCH,
            reviewed_at="2026-10-02T00:00:00Z",
            model="m",
            verdict="findings",
            findings=[finding],
        )
        target = R.review_path(repo, BRANCH, sha)
        R.write_atomic(target, R.render(review))
        _git(repo, "add", "--", str(target.relative_to(repo)))
        _git(repo, "commit", "-q", "-m", "chore(reviews): record")
    return repo


def _ledger_record(repo, sha, record):
    """The commit's clean verdict as ONE ledger line (PLAN-clean-review-ledger): committed (`ledger`), left uncommitted (`ledger-dirty`), committed beside a garbled line (`ledger-garbled`), or a committed ledger without this commit's line (`ledger-empty`)."""
    review = R.Review(
        sha=sha,
        subject="fix(x): first value",
        branch=BRANCH,
        parent=_git(repo, "rev-parse", "HEAD^"),
        patch_id=R.patch_id(repo, sha),
        reviewed_at="2026-10-02T00:00:00Z",
        model="m",
        labels={"bump": "patch", "kind": ["bug"], "why": "x"},
    )
    path = R.ledger_path(repo, BRANCH)
    if record == "ledger-empty":
        other = R.Review(sha="e" * 40, subject="s", branch=BRANCH, model="m", reviewed_at="x")
        R.append_clean(repo, BRANCH, other)
    else:
        assert R.append_clean(repo, BRANCH, review)
    if record == "ledger-garbled":
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"sha": "garbled"\n')
    if record != "ledger-dirty":
        _git(repo, "add", "--", str(path.relative_to(repo)))
        _git(repo, "commit", "-q", "-m", "chore(reviews): record")


def _check(repo, *extra):
    return subprocess.run(
        [sys.executable, str(WL_REVIEW), "--check", "--root", str(repo), *extra],
        capture_output=True,
        text=True,
        check=False,
        env=dict(GIT_ENV, COMMIT_REVIEW_CHILD=""),
    )


def test_control_the_resolution_is_the_only_variable(tmp_path):
    """CONTROL: the two worlds differ only in the finding's Resolution line, so a check that passed or refused both would show up here, not hide."""
    open_st = R.branch_state(_world(tmp_path / "a", "open"), BRANCH, repos={"console"})
    done_st = R.branch_state(_world(tmp_path / "b", "resolved"), BRANCH, repos={"console"})
    assert [f.id for _p, f in open_st["blocking"]], open_st
    assert not done_st["blocking"], done_st
    for st in (open_st, done_st):
        assert not st["uncovered"], st
        assert not st["malformed"], st


def test_check_exits_1_on_an_open_high_finding(tmp_path):
    repo = _world(tmp_path, "open")
    got = _check(repo)
    assert got.returncode == 1, got.stdout + got.stderr
    assert "refused (blocking)" in got.stdout, got.stdout
    assert "OPEN [high]" in got.stdout, got.stdout


def test_check_exits_0_when_every_finding_is_settled(tmp_path):
    repo = _world(tmp_path, "resolved")
    got = _check(repo)
    assert got.returncode == 0, got.stdout + got.stderr
    assert "clean" in got.stdout, got.stdout


def test_check_exits_1_on_an_unreviewed_commit(tmp_path):
    repo = _world(tmp_path, None)
    got = _check(repo, "--branch", BRANCH)
    assert got.returncode == 1, got.stdout
    assert "UNREVIEWED console" in got.stdout, got.stdout


def test_check_refuses_a_branch_that_is_not_checked_out(tmp_path):
    """The coverage walk reads HEAD, so judging another branch would judge the wrong commits."""
    repo = _world(tmp_path, "resolved")
    got = _check(repo, "--branch", "0930-2")
    assert got.returncode == 1, got.stdout
    assert "not-checked-out" in got.stdout, got.stdout


def test_merge_arm_refuses_the_open_finding_and_passes_the_clean_branch(tmp_path):
    reasons, lines = merge_guard.review_refusals(_world(tmp_path / "a", "open"), BRANCH, GH_REPO)
    assert reasons == ["blocking"], (reasons, lines)
    assert any("OPEN [high]" in line for line in lines), lines
    reasons, lines = merge_guard.review_refusals(
        _world(tmp_path / "b", "resolved"), BRANCH, GH_REPO
    )
    assert reasons == [], (reasons, lines)


def test_merge_arm_fails_closed_when_the_reviewer_does_not_import(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "wl_review", None)
    reasons, lines = merge_guard.review_refusals(tmp_path, BRANCH, GH_REPO)
    assert reasons == ["unverifiable"], (reasons, lines)


def test_merge_arm_fails_closed_on_an_unreadable_head_branch(tmp_path):
    reasons, _lines = merge_guard.review_refusals(_world(tmp_path, "resolved"), "", GH_REPO)
    assert reasons, "an empty headRefName must refuse, never pass"


GH_STUB = """#!/bin/sh
case "$1 $2" in
  "pr view") printf '%s\\n' '{"number":7,"headRefName":"0930-1","statusCheckRollup":[{"name":"CI Complete","conclusion":"SUCCESS"}],"body":"Operational-Reason: the plan gate is a separate suite"}' ;;
  "api graphql") echo 0 ;;
  "auth token") echo token ;;
  *) exit 1 ;;
esac
"""


@pytest.mark.parametrize(("record", "denied"), [("open", True), ("resolved", False)])
def test_the_guard_end_to_end_reads_the_head_branch(tmp_path, record, denied):
    repo = _world(tmp_path, record)
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    gh = stub_bin / "gh"
    gh.write_text(GH_STUB, encoding="utf-8")
    gh.chmod(0o755)
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 7 --repo %s --rebase --auto" % GH_REPO},
            "cwd": str(repo),
        }
    )
    env = dict(
        GIT_ENV,
        CLAUDE_PROJECT_DIR=str(repo),
        PATH="%s%s%s" % (stub_bin, os.pathsep, os.environ.get("PATH", "")),
    )
    got = subprocess.run(
        [sys.executable, str(DISPATCH), "block_admin_merge"],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(repo),
    )
    if denied:
        assert got.returncode != 0, got.stderr
        assert "per-commit review precondition" in got.stderr, got.stderr
        assert "head branch 0930-1" in got.stderr, got.stderr
    else:
        assert got.returncode == 0, got.stderr


# --------------------------------------------------------------------------- the clean ledger (agent/plans/PLAN-clean-review-ledger.md T5, T7)


def test_a_ledger_only_branch_passes_check(tmp_path):
    repo = _world(tmp_path, "ledger")
    assert not R.review_path(repo, BRANCH, _git(repo, "rev-parse", "HEAD^")).exists()
    got = _check(repo)
    assert got.returncode == 0, got.stdout + got.stderr
    assert "clean" in got.stdout, got.stdout


def test_control_without_the_ledger_line_the_same_branch_is_unreviewed(tmp_path):
    """CONTROL: the committed ledger holds another sha only, so the pass above is the line's doing."""
    got = _check(_world(tmp_path, "ledger-empty"))
    assert got.returncode == 1, got.stdout
    assert "UNREVIEWED console" in got.stdout, got.stdout


def test_a_dirty_ledger_is_refused_as_uncommitted(tmp_path):
    got = _check(_world(tmp_path, "ledger-dirty"))
    assert got.returncode == 1, got.stdout
    assert "refused (uncommitted)" in got.stdout, got.stdout


def test_a_garbled_ledger_line_is_refused_as_malformed_with_its_line(tmp_path):
    got = _check(_world(tmp_path, "ledger-garbled"))
    assert got.returncode == 1, got.stdout
    assert "malformed" in got.stdout, got.stdout
    assert "MALFORMED clean.jsonl" in got.stdout, got.stdout
    assert "(line 2)" in got.stdout, got.stdout


def test_a_rebased_copy_whose_patch_id_is_in_the_ledger_counts_as_covered(tmp_path):
    repo = _world(tmp_path, "ledger")
    _git(repo, "checkout", "-q", "main")
    (repo / "other.txt").write_text("o\n", encoding="utf-8")
    _git(repo, "add", "other.txt")
    _git(repo, "commit", "-q", "-m", "other")
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "checkout", "-q", BRANCH)
    _git(repo, "rebase", "-q", "main")
    assert R.uncovered(repo, repo, BRANCH) == []
    got = _check(repo)
    assert got.returncode == 0, got.stdout + got.stderr


def test_merge_arm_passes_the_ledger_branch_and_refuses_it_without_the_line(tmp_path):
    reasons, lines = merge_guard.review_refusals(_world(tmp_path / "a", "ledger"), BRANCH, GH_REPO)
    assert reasons == [], (reasons, lines)
    reasons, lines = merge_guard.review_refusals(
        _world(tmp_path / "b", "ledger-empty"), BRANCH, GH_REPO
    )
    assert reasons == ["uncovered"], (reasons, lines)


def _submodule_world(tmp_path):
    """A clean console (reviewed) plus a nested repository `private/sub` on the same branch whose one commit has no review file, as a submodule whose reviewer is still running."""
    repo = _world(tmp_path, "resolved")
    sub = repo / "private" / "sub"
    sub.mkdir(parents=True)
    _git(sub, "init", "-q", "--initial-branch=main")
    (sub / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(sub, "add", "seed.txt")
    _git(sub, "commit", "-q", "-m", "seed")
    origin = tmp_path / "sub-origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", str(origin)], check=True, capture_output=True, env=GIT_ENV
    )
    _git(sub, "remote", "add", "origin", str(origin))
    _git(sub, "push", "-q", "origin", "main")
    _git(sub, "checkout", "-q", "-b", BRANCH)
    (sub / "g.py").write_text("b = 2\n", encoding="utf-8")
    _git(sub, "add", "g.py")
    _git(sub, "commit", "-q", "-m", "fix(sub): b")
    (repo / ".gitmodules").write_text(
        '[submodule "private/sub"]\n\tpath = private/sub\n\turl = %s\n' % origin, encoding="utf-8"
    )
    return repo, _git(sub, "rev-parse", "HEAD")


def _status(repo, tmp_path, sha):
    """`--status` while a spawn lock for `sha` is inside its grace window (start now, no pid), the state a just-started reviewer leaves."""
    env = dict(GIT_ENV, COMMIT_REVIEW_CHILD="", TMPDIR=str(tmp_path / "tmp"))
    locks = tmp_path / "tmp" / "claude-worklist" / "reviews" / "locks"
    locks.mkdir(parents=True)
    (locks / ("%s.lock" % sha)).write_text(
        json.dumps({"pid": None, "start": __import__("time").time(), "branch": BRANCH}),
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(WL_REVIEW), "--status", "--root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_status_names_a_submodule_review_in_flight_while_the_console_is_clean(tmp_path):
    """The push guard judges `branch_state(..., repos={label})` per pushed repository and refused with IN FLIGHT for a submodule while `--status`, which advice names, printed `clean`. `--status` and `--check` now walk every repository on the branch."""
    repo, sha = _submodule_world(tmp_path)
    console_only = R.branch_state(repo, BRANCH, repos={"console"})
    assert not R.describe(console_only), "CONTROL: the console alone must be clean"
    guard_view = R.branch_state(repo, BRANCH, repos={"private/sub"})
    assert guard_view["in_flight"] or guard_view["uncovered"], "CONTROL: the push guard's view"
    got = _status(repo, tmp_path, sha)
    assert got.returncode == 0, got.stdout + got.stderr
    assert "IN FLIGHT private/sub %s" % sha[:8] in got.stdout, got.stdout
    assert "clean" not in got.stdout, got.stdout
