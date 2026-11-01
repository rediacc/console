"""`wl_review.py --check` and the merge guard's per-commit review arm (agent/plans/PLAN-per-commit-review.md section 11.6, WP-2).

The precondition both enforce, in the one wording every doc uses: every commit since the base has a per-commit review record in `agent/reviews/<branch>/` with no open finding at or above `block_at`, and every record is committed.

Each case builds a real repository with an `origin/main` and one branch commit, then writes that commit's review record through `wl_review.render`, so no model runs. The fixture's only variable is the record: an open `high` finding (refused), the same record with the finding marked not-a-bug (clean), or no record (unreviewed). The merge arm is driven twice: through `review_refusals` directly, and end to end through
the dispatcher with a stub `gh` that answers `pr view` for a green PR, so the `headRefName` wiring is exercised and not only the helper.
"""

from __future__ import annotations

import io
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


# The finding's Resolution line per `record` kind; `<kind>@<severity>` sets the severity (default high).
RESOLUTIONS = {
    "open": "open",
    "resolved": "not-a-bug | f.py:2 names the second element on purpose | deadbeef 2026-10-02T00:00:00Z",
    "deferred": "deferred #abcdef12 | deadbeef 2026-10-02T00:00:00Z",
    "fixed": "fixed %(sha)s | deadbeef 2026-10-02T00:00:00Z",
    "waived": "waived #abcdef12 ASKED:2026-10-02T00:00Z | deadbeef 2026-10-02T00:00:00Z",
}


def _world(tmp_path, record):
    """A checkout of BRANCH one commit past origin/main. `record` is None (no review), or a RESOLUTIONS kind optionally suffixed `@<severity>`: "open" (an open high finding), "resolved" (the same finding marked not-a-bug), "deferred" (a legacy deferral), "fixed" or "waived"; a written record is committed beside the commit it reviews."""
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
        kind, _, severity = record.partition("@")
        finding = R.Finding(
            id="%s.1" % sha[:8],
            severity=severity or "high",
            file="f.py",
            line=2,
            anchor="in-diff",
            claim="values[1] reads the second element, not the first",
            resolution=RESOLUTIONS[kind] % {"sha": sha},
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


def _refusals(repo, branch=BRANCH):
    """review_refusals with the PR head the way the guard passes it: the fixture's own HEAD."""
    return merge_guard.review_refusals(repo, branch, GH_REPO, _git(repo, "rev-parse", "HEAD"))


def test_merge_arm_refuses_the_open_finding_and_passes_the_clean_branch(tmp_path):
    reasons, lines = _refusals(_world(tmp_path / "a", "open"))
    assert reasons == ["blocking"], (reasons, lines)
    assert any("OPEN [high]" in line for line in lines), lines
    reasons, lines = _refusals(_world(tmp_path / "b", "resolved"))
    assert reasons == [], (reasons, lines)


def test_merge_arm_refuses_when_the_pr_head_sha_is_missing(tmp_path):
    """Finding b18d31bd.5: an empty headRefOid once skipped the stale-tip pin and judged a possibly stale tip silently."""
    repo = _world(tmp_path, "resolved")
    reasons, lines = merge_guard.review_refusals(repo, BRANCH, GH_REPO, "")
    assert reasons == ["unverifiable"], (reasons, lines)
    assert any("headRefOid" in line for line in lines), lines
    # CONTROL: the same clean branch with the head sha passes, so the refusal is the missing sha's doing.
    assert _refusals(repo)[0] == []


def test_merge_arm_fails_closed_when_the_reviewer_does_not_import(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "wl_review", None)
    reasons, lines = merge_guard.review_refusals(tmp_path, BRANCH, GH_REPO, "a" * 40)
    assert reasons == ["unverifiable"], (reasons, lines)
    assert any("ImportError" in line or "could not run" in line for line in lines), lines


def test_merge_arm_fails_closed_on_an_unreadable_head_branch(tmp_path):
    reasons, _lines = _refusals(_world(tmp_path, "resolved"), "")
    assert reasons, "an empty headRefName must refuse, never pass"


GH_STUB = """#!/bin/sh
case "$1 $2" in
  "pr view") printf '%s\\n' '{"number":7,"headRefName":"0930-1","headRefOid":"@HEAD@","statusCheckRollup":[{"name":"CI Complete","conclusion":"SUCCESS"}],"body":"Operational-Reason: the plan gate is a separate suite"}' ;;
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
    gh.write_text(GH_STUB.replace("@HEAD@", _git(repo, "rev-parse", "HEAD")), encoding="utf-8")
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
    reasons, lines = _refusals(_world(tmp_path / "a", "ledger"))
    assert reasons == [], (reasons, lines)
    reasons, lines = _refusals(_world(tmp_path / "b", "ledger-empty"))
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


def test_a_pushed_branch_not_checked_out_is_judged_at_its_pushed_tip(tmp_path):
    """2026-10-08: the operator parked 1007-1's local commits on 1008-1, and block_admin_merge then refused PR #599 as `not-checked-out`. A PR merges what was pushed, so the walk reads origin/<branch>; an unreviewed commit that exists only on the parking branch must not count."""
    for name, record, want in (("clean", "resolved", []), ("unreviewed", None, ["uncovered"])):
        repo = _world(tmp_path / name, record)
        _git(repo, "push", "-q", "origin", BRANCH)
        _git(repo, "fetch", "-q", "origin")
        _git(repo, "checkout", "-q", "-b", "parked")
        (repo / "later.py").write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", "later.py")
        _git(repo, "commit", "-q", "-m", "feat(x): parked, never pushed")
        reasons, lines = R.check_state(repo, BRANCH, label="console")
        assert reasons == want, (name, reasons, lines)


def test_control_a_branch_with_no_pushed_ref_still_refuses_when_not_checked_out(tmp_path):
    repo = _world(tmp_path, "resolved")
    _git(repo, "checkout", "-q", "-b", "elsewhere")
    reasons, _lines = R.check_state(repo, BRANCH, label="console")
    assert reasons == ["not-checked-out"], reasons


def test_an_unchecked_out_main_keeps_the_not_checked_out_refusal(tmp_path):
    """71afd29f.1: `origin/main` always exists, so the pushed-tip stand-in must not apply to main; judged at its own pushed tip, main walks an empty range and reads as clean."""
    repo = _world(tmp_path, "resolved")
    reasons, _lines = R.check_state(repo, "main", label="console")
    assert reasons == ["not-checked-out"], reasons


# --------------------------------------------------------------------------- deferrals (agent/plans/PLAN-deferred-findings-block-merge.md L1, L5)


@pytest.mark.parametrize("severity", ["low", "medium", "high"])
def test_check_refuses_a_deferral_at_any_severity(tmp_path, severity):
    """D1: a legacy deferral is a refusal whatever its severity and whatever state its item is in; no worklist fold is read."""
    got = _check(_world(tmp_path, "deferred@%s" % severity))
    assert got.returncode == 1, got.stdout + got.stderr
    assert "refused (deferred)" in got.stdout, got.stdout
    assert "DEFERRED [%s]" % severity in got.stdout, got.stdout
    assert "worklist.py --triage <me> '" in got.stdout, got.stdout


@pytest.mark.parametrize("kind", ["fixed", "waived", "fixed@low", "waived@low"])
def test_control_the_same_finding_fixed_or_waived_is_clean(tmp_path, kind):
    """CONTROL: only the Resolution line differs from the refused world above."""
    got = _check(_world(tmp_path, kind))
    assert got.returncode == 0, got.stdout + got.stderr
    assert "clean" in got.stdout, got.stdout


def test_a_deferral_refuses_whatever_its_item_state_and_a_lease_changes_no_refusal(tmp_path):
    repo = _world(tmp_path, "deferred@low")
    for items in (None, {}, {"abcdef12": " "}, {"abcdef12": "x"}, {"abcdef12": ">"}):
        st = R.branch_state(repo, BRANCH, repos={"console"}, items=items)
        assert [f.id for _p, f in st["deferred"]], (items, st)
        assert R.push_refusals(st) == ["deferred"], (items, R.push_refusals(st))
        assert not st["blocking"], "a deferral never reopens to open"
        assert not st["advisory"], "a deferral never reopens to open"


def test_merge_arm_refuses_the_deferral_and_passes_the_fixed_branch(tmp_path):
    reasons, lines = _refusals(_world(tmp_path / "a", "deferred"))
    assert reasons == ["deferred"], (reasons, lines)
    assert any(line.startswith("DEFERRED [high]") for line in lines), lines
    reasons, lines = _refusals(_world(tmp_path / "b", "fixed"))
    assert reasons == [], (reasons, lines)


def test_the_merge_message_names_the_deferral_and_the_status_command():
    assert "deferred" in merge_guard.REVIEWS_MESSAGE
    assert "wl_review.py --status" in merge_guard.REVIEWS_MESSAGE


# --------------------------------------------------------------------------- the pushed tip (finding 71afd29f.3)


def _parked(tmp_path, record="resolved"):
    """BRANCH pushed and then left for a `parked` branch, so check_state judges origin/BRANCH."""
    repo = _world(tmp_path, record)
    _git(repo, "push", "-q", "origin", BRANCH)
    _git(repo, "fetch", "-q", "origin")
    _git(repo, "checkout", "-q", "-b", "parked")
    return repo


def test_a_pushed_tip_judgement_names_the_ref_its_sha_and_its_age(tmp_path):
    repo = _parked(tmp_path)
    sha = _git(repo, "rev-parse", "--short=12", "origin/%s" % BRANCH)
    reasons, lines = R.check_state(repo, BRANCH, label="console")
    assert reasons == [], (reasons, lines)
    assert lines, lines
    assert lines[0].startswith("judged at origin/%s %s" % (BRANCH, sha)), lines
    assert "no fetch runs here" in lines[0], lines
    assert "min ago" in lines[0], lines


def test_control_a_checked_out_branch_prints_no_tip_line(tmp_path):
    reasons, lines = R.check_state(_world(tmp_path, "resolved"), BRANCH, label="console")
    assert reasons == [], reasons
    assert not any(line.startswith("judged at") for line in lines), lines


def test_a_stale_tracking_ref_is_refused_against_the_pr_head(tmp_path):
    """The PR head moved on in another clone: this clone's origin/<branch> lacks it, so the walk would miss commits the PR merges."""
    repo = _parked(tmp_path)
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", "-q", "-b", BRANCH, str(tmp_path / "origin.git"), str(other)],
        check=True,
        capture_output=True,
        env=GIT_ENV,
    )
    (other / "later.py").write_text("y = 2\n", encoding="utf-8")
    _git(other, "add", "later.py")
    _git(other, "commit", "-q", "-m", "feat(x): pushed from another clone")
    _git(other, "push", "-q", "origin", BRANCH)
    head = _git(other, "rev-parse", "HEAD")
    reasons, lines = R.check_state(repo, BRANCH, label="console", expected_tip=head)
    assert reasons == ["stale-tip"], (reasons, lines)
    assert any("git fetch origin %s" % BRANCH in line for line in lines), lines
    # CONTROL: the same check against the tip this clone does hold passes, so the refusal is the pin's doing.
    held = _git(repo, "rev-parse", "origin/%s" % BRANCH)
    reasons, _lines = R.check_state(repo, BRANCH, label="console", expected_tip=held)
    assert reasons == [], reasons
    _git(repo, "fetch", "-q", "origin")
    reasons, lines = R.check_state(repo, BRANCH, label="console", expected_tip=head)
    assert reasons == ["uncovered"], (reasons, lines)


def test_the_cli_takes_expect_tip(tmp_path):
    repo = _world(tmp_path, "resolved")
    got = _check(repo, "--expect-tip", "0" * 40)
    assert got.returncode == 1, got.stdout
    assert "refused (stale-tip)" in got.stdout, got.stdout
    got = _check(repo, "--expect-tip", _git(repo, "rev-parse", "HEAD"))
    assert got.returncode == 0, got.stdout + got.stderr


def test_the_merge_guard_pins_the_walk_to_the_pr_head_oid():
    good = json.dumps({"headRefOid": "a" * 40})
    assert merge_guard._jq_head_oid(good) == "a" * 40
    assert merge_guard._jq_head_oid(json.dumps({"headRefOid": "nope"})) == ""
    assert merge_guard._jq_head_oid("") == ""


def test_the_guard_end_to_end_refuses_a_head_oid_the_clone_lacks(tmp_path):
    """The `gh pr view` the guard already makes carries headRefOid; a clean branch whose walked tip lacks it is refused as stale-tip."""
    repo = _world(tmp_path, "resolved")
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    gh = stub_bin / "gh"
    gh.write_text(GH_STUB.replace("@HEAD@", "0" * 40), encoding="utf-8")
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
    assert got.returncode != 0, got.stderr
    assert "stale-tip" in got.stderr, got.stderr


def test_a_submodule_label_ignores_the_console_tip_pin(tmp_path):
    """Finding b18d31bd.4, by design: a submodule is walked at its own HEAD, so the PR head sha (a commit of ANOTHER repository) is never compared with the console's tip; the console label with the same sha is refused."""
    repo, _sha = _submodule_world(tmp_path)
    foreign = "0" * 40
    reasons, _lines = R.check_state(repo, BRANCH, label="private/sub", expected_tip=foreign)
    assert "stale-tip" not in reasons, reasons
    reasons, _lines = R.check_state(repo, BRANCH, label="console", expected_tip=foreign)
    assert reasons == ["stale-tip"], reasons


def test_a_submodule_citation_may_name_the_console_root_path(tmp_path, monkeypatch):
    """A submodule finding's evidence read from the console root names `private/account/src/x.ts:1` (worklist #37f915ff); it resolves inside the submodule, while a path under another prefix, a line past the end, and a prefix that climbs out to a file that does exist still cite nothing."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "x.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "x.ts").write_text("outside\n", encoding="utf-8")
    monkeypatch.setattr(R, "_superproject_prefix", lambda _repo: "private/account/")
    assert R._citation_ok(str(repo), "the rule is private/account/src/x.ts:1 as written")
    assert R._citation_ok(str(repo), "the rule is src/x.ts:1 as written")
    assert not R._citation_ok(str(repo), "the rule is private/renet/src/x.ts:1 as written")
    assert not R._citation_ok(str(repo), "the rule is private/account/src/x.ts:9 past the end")
    assert not R._citation_ok(str(repo), "the rule is private/account/../x.ts:1 outside")
    monkeypatch.setattr(R, "_superproject_prefix", lambda _repo: "")
    assert not R._citation_ok(str(repo), "the rule is private/account/src/x.ts:1 as written")


def test_a_directory_named_like_the_prefix_still_resolves_as_written(tmp_path, monkeypatch):
    (tmp_path / "private" / "account").mkdir(parents=True)
    (tmp_path / "private" / "account" / "y.ts").write_text("y\n", encoding="utf-8")
    monkeypatch.setattr(R, "_superproject_prefix", lambda _repo: "private/account/")
    assert R._citation_ok(str(tmp_path), "the rule is private/account/y.ts:1 as written")


def test_the_superproject_prefix_of_a_plain_repo_is_empty(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert R._superproject_prefix(str(tmp_path)) == ""


def test_the_superproject_prefix_of_a_real_submodule(tmp_path):
    """Through git itself: a submodule checked out at private/account reports `private/account/`, and a console-root citation into it resolves."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x",
    }
    sub_src = tmp_path / "sub_src"
    subprocess.run(["git", "init", "-q", str(sub_src)], check=True, env=env)
    (sub_src / "a.ts").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(sub_src), "add", "a.ts"], check=True, env=env)
    subprocess.run(["git", "-C", str(sub_src), "commit", "-qm", "a"], check=True, env=env)
    sup = tmp_path / "sup"
    subprocess.run(["git", "init", "-q", str(sup)], check=True, env=env)
    subprocess.run(
        [
            "git",
            "-C",
            str(sup),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(sub_src),
            "private/account",
        ],
        check=True,
        env=env,
    )
    sub = sup / "private" / "account"
    assert R._superproject_prefix(str(sub)) == "private/account/"
    assert R._citation_ok(str(sub), "see private/account/a.ts:1 for it")
    assert R._superproject_prefix(str(sup)) == ""


def test_a_citation_may_name_an_extensionless_file(tmp_path):
    """`Dockerfile:83` is a path:line like any other (worklist item on the refused not-a-bug mark, 2026-10-11); a line past the file's end, a missing file and a bare clock time still cite nothing."""
    (tmp_path / "Dockerfile").write_text("FROM x\nRUN y\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert R._citation_ok(str(tmp_path), "the consumer is Dockerfile:2, after the install")
    assert R._citation_ok(str(tmp_path), "see pkg/a.py:1 for the binding")
    assert not R._citation_ok(str(tmp_path), "the consumer is Dockerfile:9, past the end")
    assert not R._citation_ok(str(tmp_path), "the consumer is Makefile:1, which is not there")
    assert not R._citation_ok(
        str(tmp_path), "measured at 10:35 with a ratio of 3:1 and nothing else"
    )
    # A citation is of this repository: an absolute path and a `..` climb name a file outside it.
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x\n", encoding="utf-8")
    assert not R._citation_ok(str(tmp_path), "the proof is %s:1, outside the tree" % outside)
    assert not R._citation_ok(str(tmp_path), "the proof is ../outside.txt:1, outside the tree")
    assert not R._citation_ok(str(tmp_path), "the proof is /etc/hosts:1, outside the tree")
    # The path token is found by a single-class split and string operations, no pattern over the path, so the scan is linear by construction: the tokens are counted, which a clock cannot be.
    assert not R._citation_ok(str(tmp_path), "a" * 200000 + " and nothing cited")
    assert R._cited_paths("see pkg/a.py:1, Dockerfile:2. and x") == [
        ("pkg/a.py", 1),
        ("Dockerfile", 2),
    ]
    assert R._cited_paths("at 10:35, ratio 3:1") == []
    assert not R._citation_ok(
        str(tmp_path), "at 10:35, ratio 3:1, http://host:80/x and nothing else"
    )
    assert len(R.CITE_SEPARATORS.split("a" * 200000 + " b:1")) == 2
    # A tracked symlink whose target lies outside is still a path of this repository.
    (tmp_path / "linked.txt").symlink_to(outside)
    assert R._citation_ok(str(tmp_path), "the link is linked.txt:1 in the tree")
    # A token with no letter is a time or a ratio, even when a file of that name exists.
    (tmp_path / "10").write_text("a\n" * 40, encoding="utf-8")
    assert not R._citation_ok(str(tmp_path), "measured at 10:35 and nothing else")
    # The usual spellings all cite: a column, a range, and a label glued on with a colon.
    assert R._citation_ok(str(tmp_path), "see pkg/a.py:1:5 for the column")
    assert R._citation_ok(str(tmp_path), "see Dockerfile:1-2 for the range")
    assert R._citation_ok(str(tmp_path), "Evidence:pkg/a.py:1")
    assert ("pkg/a.py", 1) in R._cited_paths("Evidence:pkg/a.py:1:5")
    # Lines are counted as str.splitlines counts them (a form feed ends a line too).
    (tmp_path / "ff.txt").write_text("a\x0cb\n", encoding="utf-8")
    assert R._has_line(str(tmp_path / "ff.txt"), 2)
    assert not R._has_line(str(tmp_path / "ff.txt"), 3)


def test_a_cited_line_is_looked_for_only_within_the_read_bound(tmp_path, monkeypatch):
    """The bound is what keeps a tracked link to a very large file cheap, so it is asserted directly: with the cap at 10 characters a line inside it cites and one beyond it does not, though the file holds both."""
    target = tmp_path / "long.txt"
    target.write_text("a\n" * 5000, encoding="utf-8")
    assert R._has_line(str(target), 5000)
    monkeypatch.setattr(R, "CITE_READ_CAP", 10)
    assert R._has_line(str(target), 5)
    assert not R._has_line(str(target), 6)


def test_a_line_number_ends_its_token_or_is_followed_by_a_column_or_range(tmp_path):
    """A port is not a line number: `http://host:80/x` cites nothing even when a file named `host` exists, while a column, a range and closing punctuation after the digits still cite."""
    (tmp_path / "host").write_text("a\n" * 100, encoding="utf-8")
    assert R._cited_paths("see http://host:80/x for the page") == []
    # A URL cites nothing, with a path after its port or without one.
    assert R._cited_paths("see http://host:80 for it") == []
    assert not R._citation_ok(str(tmp_path), "see http://host:80 for it and nothing else here")
    assert not R._citation_ok(str(tmp_path), "see http://host:80/x for the page and nothing else")
    assert ("host", 80) in R._cited_paths("the file is host:80, and host:80:3, and host:80-90).")
    assert R._citation_ok(str(tmp_path), "the proof sits at host:80-90 in the tree")


def test_one_token_yields_a_bounded_number_of_candidates():
    """A token is cut into at most CITE_PARTS_CAP parts, exactly: a line number in the ninth colon-part is past the cut, so it yields no candidate, while one in the eighth still does."""
    assert R.CITE_PARTS_CAP == 8
    assert R._cited_paths("a:b:c:d:e:f:g:h:7") == []
    assert ("g", 7) in R._cited_paths("a:b:c:d:e:f:g:7")


def test_a_cited_line_stops_the_read_at_its_chunk(monkeypatch):
    """The read is chunked and stops at the cited line: line 1 of a large text costs one chunk, not the whole bound, and a `\\r\\n` split across two chunks is one line boundary, not two."""
    big = io.StringIO("a\n" * 1_000_000)
    found, read = R._lines_upto(big, 1, R.CITE_READ_CAP)
    assert found
    assert read <= R.CITE_CHUNK
    # A boundary split across chunks: with a 2-character chunk, "a\r" then "\nb" is two lines, not three.
    monkeypatch.setattr(R, "CITE_CHUNK", 2)
    found, _read = R._lines_upto(io.StringIO("a\r\nb"), 3, 100)
    assert not found
    assert R._lines_upto(io.StringIO("a\r\nb"), 2, 100)[0]


def test_a_long_unterminated_line_is_counted_once_across_chunks(monkeypatch):
    """Only two facts cross a chunk boundary, so a line far longer than a chunk is one line however many chunks it spans, and the line after it is found."""
    monkeypatch.setattr(R, "CITE_CHUNK", 7)
    text = "x" * 100 + "\n" + "y" * 50
    assert R._lines_upto(io.StringIO(text), 2, 10_000)[0]
    assert not R._lines_upto(io.StringIO(text), 3, 10_000)[0]
    assert not R._lines_upto(io.StringIO("x" * 100), 2, 10_000)[0]
    # The bound is in characters: a line that starts past it is not found.
    assert not R._lines_upto(io.StringIO(text), 2, 50)[0]


def test_module_file_prefers_the_hit_sharing_the_most_directory_components():
    """The tie-break counts whole path components: `a/bc` and `a/bd` share the one directory `a`, not the characters `a/b`, so the hit under the nearer directory tree wins and the length only breaks a true tie."""
    tree = R._Tree("/nonexistent", "0" * 40)
    tree._files = ["a/bd/util.py", "a/util.py"]
    # By characters `a/bd/util.py` shares `a/b` with `a/bc/y.py` and wins; by components both share only `a`, and the shorter path wins.
    assert tree.module_file("util", "a/bc/y.py") == "a/util.py"
    # A deeper shared directory beats a shorter path.
    tree._files = ["a/bc/deep/util.py", "a/util.py"]
    assert tree.module_file("util", "a/bc/deep/y.py") == "a/bc/deep/util.py"
    # Root-level files share the empty directory with each other, the unchanged edge.
    tree._files = ["util.py", "pkg/util.py"]
    assert tree.module_file("util", "main.py") == "util.py"


def test_patch_ids_batch_equals_patch_id_per_commit(tmp_path):
    """`patch_ids` is the batched `patch_id`: the records' `Patch-Id:` lines come from the latter, so a different value would map nothing."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }

    def run(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True, env=env
        ).stdout.strip()

    run("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("a\n")
    run("add", "a.txt")
    run("commit", "-q", "-m", "base")
    base = run("rev-parse", "HEAD")
    for i in range(3):
        (tmp_path / ("f%d.txt" % i)).write_text("%d\n" % i)
        run("add", "f%d.txt" % i)
        run("commit", "-q", "-m", "c%d" % i)
    run("commit", "-q", "--allow-empty", "-m", "empty")
    shas = run("rev-list", "%s..HEAD" % base).split()
    batch = R.patch_ids(tmp_path, "%s..HEAD" % base)
    assert len(batch) == 3
    for sha in shas:
        assert batch.get(sha, "") == R.patch_id(tmp_path, sha)
    # CONTROL: the empty commit has no diff, so neither form gives it a patch-id.
    assert R.patch_id(tmp_path, shas[0]) == ""
    assert shas[0] not in batch


def test_patch_ids_agrees_on_a_root_commit_under_either_show_root_and_reports_a_failed_call(
    tmp_path,
):
    """`git show` and `git log` both honour log.showRoot, so the batch and the per-commit patch-id of a root commit agree with it on and off; a failed git call is None (a caller falls back), never an empty map that reads as nothing reviewed."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }

    def run(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True, env=env
        ).stdout.strip()

    run("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("a\n")
    run("add", "a.txt")
    run("commit", "-q", "-m", "root")
    root = run("rev-parse", "HEAD")
    for show_root in ("true", "false"):
        run("config", "log.showRoot", show_root)
        assert R.patch_ids(tmp_path, "HEAD").get(root, "") == R.patch_id(tmp_path, root), show_root
    run("config", "log.showRoot", "true")
    # CONTROL: with the root diff shown, the value is a real patch-id, not two empty strings agreeing.
    assert R.patch_id(tmp_path, root) != ""
    assert R.patch_ids(tmp_path, "no-such-ref..HEAD") is None


def test_patch_ids_prefetches_a_partial_clone_and_skips_a_gitlink(tmp_path, monkeypatch):
    """In a partial clone the batch names both sides of every change and no gitlink, since a gitlink's commit lives in another repository and naming one fails the whole fetch. Outside a partial clone it fetches nothing."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }

    def run(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True, env=env
        ).stdout.strip()

    run("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("one\n")
    run("add", "a.txt")
    run("commit", "-q", "-m", "base")
    base = run("rev-parse", "HEAD")
    old = run("rev-parse", "HEAD:a.txt")
    (tmp_path / "a.txt").write_text("two\n")
    gitlink = "1" * 40
    run("update-index", "--add", "--cacheinfo", "160000,%s,sub" % gitlink)
    run("add", "a.txt")
    run("commit", "-q", "-m", "change")
    new = run("rev-parse", "HEAD:a.txt")
    real_git = R.git
    fetched = []

    def spy(repo, *args, **kwargs):
        if "fetch" in args:
            fetched.append(kwargs["stdin"].split())
            return 0, ""
        return real_git(repo, *args, **kwargs)

    monkeypatch.setattr(R, "git", spy)
    R.patch_ids(tmp_path, "%s..HEAD" % base)
    assert fetched == [], "CONTROL: a full clone fetches nothing"
    run("config", "remote.origin.promisor", "true")
    R.patch_ids(tmp_path, "%s..HEAD" % base)
    assert fetched == [sorted([old, new])]
