"""`wl_checks.green_receipt_on_unpushed_head`: a lease waits while a passing receipt for HEAD's tree (directly or through its `advances`) still owes its push. `worktree_check` holds for a running vm:check and no longer for a running ci:quick.

The control row is the one that holds (green receipt, HEAD unpushed); every other row turns one condition off and must not hold, so a False below is that condition's doing.
"""

from __future__ import annotations

import datetime
import json
import subprocess
import types

import pytest

from rediacc_hooks import proc as hook_proc
from rediacc_hooks.tests import wlfix

CK = wlfix.import_wl("wl_checks")


def _git(repo, *args) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A checkout with a bare upstream, one pushed commit, and one commit on top of it."""
    bare = tmp_path / "up.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    _git(work, "config", "user.email", "t@example.org")
    _git(work, "config", "user.name", "t")
    (work / "a").write_text("1", encoding="utf-8")
    _git(work, "add", "a")
    _git(work, "commit", "-q", "-m", "one")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "-u", "origin", "main")
    (work / "a").write_text("2", encoding="utf-8")
    _git(work, "commit", "-q", "-am", "two")
    (work / ".ci" / "cache").mkdir(parents=True)
    return work


def _tree(repo, rev="HEAD") -> str:
    return _git(repo, "rev-parse", "%s^{tree}" % rev)


def _receipt(repo, **fields):
    path = repo / ".ci" / "cache" / "prepush-receipt.json"
    path.write_text(json.dumps(fields), encoding="utf-8")


def _green(repo, rev="HEAD", **extra):
    """A green whole-run receipt that judged the tree of `rev`."""
    _receipt(repo, exitCode=0, whole=True, headTree=_tree(repo, rev), **extra)


def _record_only_commit(repo) -> tuple[str, str]:
    """One more commit on top of HEAD; returns (the tree before it, the tree after it)."""
    before = _tree(repo)
    (repo / "record.md").write_text("r", encoding="utf-8")
    _git(repo, "add", "record.md")
    _git(repo, "commit", "-q", "-m", "record")
    return before, _tree(repo)


def test_control_a_green_receipt_for_an_unpushed_head_holds(repo):
    _green(repo)
    assert CK.green_receipt_on_unpushed_head(str(repo)) is True


def test_a_red_receipt_does_not_hold(repo):
    _receipt(repo, exitCode=1, headTree=_tree(repo))
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_a_receipt_for_another_tree_does_not_hold(repo):
    _green(repo, "HEAD~1")
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_a_record_only_commit_after_a_green_run_still_reads_as_a_receipt(repo):
    """The advance chain carries the receipt from the judged tree to HEAD's tree; the commit sha no longer matters."""
    before, after = _record_only_commit(repo)
    _green_at = {"exitCode": 0, "whole": True, "headTree": before}
    _receipt(repo, advances=[{"from": before, "to": after}], **_green_at)
    assert CK.green_receipt_on_unpushed_head(str(repo)) is True


def test_a_commit_the_advances_do_not_reach_does_not_hold(repo):
    """Control for the chain: the same commit with no advance, or an advance that does not start from a reached tree."""
    before, after = _record_only_commit(repo)
    _receipt(repo, exitCode=0, whole=True, headTree=before)
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False
    _receipt(
        repo,
        exitCode=0,
        whole=True,
        headTree=before,
        advances=[{"from": "f" * 40, "to": after}],
    )
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_the_archive_copy_for_head_tree_is_read_before_the_latest_file(repo):
    """A later run at another tree overwrote the latest file; the archive copy still speaks for HEAD's tree."""
    tree = _tree(repo)
    archive = repo / ".ci" / "cache" / "receipts"
    archive.mkdir()
    (archive / ("%s.json" % tree)).write_text(
        json.dumps({"exitCode": 0, "whole": True, "headTree": tree}), encoding="utf-8"
    )
    _receipt(repo, exitCode=0, whole=True, headTree=_tree(repo, "HEAD~1"))
    assert CK.green_receipt_on_unpushed_head(str(repo)) is True


def test_a_misfiled_archive_copy_does_not_hold(repo):
    """Control: an archive copy that is not a whole run at its own tree is refused, not read past to the latest file."""
    tree = _tree(repo)
    archive = repo / ".ci" / "cache" / "receipts"
    archive.mkdir()
    (archive / ("%s.json" % tree)).write_text(
        json.dumps({"exitCode": 0, "whole": False, "headTree": tree}), encoding="utf-8"
    )
    _green(repo)
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_a_pushed_head_does_not_hold(repo):
    _green(repo)
    _git(repo, "push", "-q", "origin", "main")
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_a_missing_or_malformed_receipt_does_not_hold(repo):
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False
    (repo / ".ci" / "cache" / "prepush-receipt.json").write_text("{not json", encoding="utf-8")
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_no_upstream_is_a_doubt_and_does_not_hold(repo):
    _git(repo, "branch", "--unset-upstream")
    _green(repo)
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False


def test_a_boolean_exit_code_is_not_a_green_receipt(repo):
    """JSON `false` compares equal to 0 in Python, so a bare `!= 0` read a malformed receipt as green."""
    tree = _tree(repo)
    _receipt(repo, exitCode=False, headTree=tree)
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False
    _receipt(repo, exitCode=0.0, headTree=tree)
    assert CK.green_receipt_on_unpushed_head(str(repo)) is False
    _receipt(repo, exitCode=0, headTree=tree)
    assert CK.green_receipt_on_unpushed_head(str(repo)) is True


WT = wlfix.import_wl("wl_worktrees")


def _worktree_check(monkeypatch, repo, vm_check=False):
    """`wl_checks.worktree_check` over one unlanded lease; the vm:check hold is on when `vm_check` is True and release:local is off; returns (queued, blocked)."""
    lease = {"id": "w1", "path": "/x/w1", "unlanded": 1}
    monkeypatch.setattr(CK.C, "project_start", lambda _event: str(repo))
    monkeypatch.setattr(CK.C, "project_root", lambda _start: str(repo))
    monkeypatch.setattr(CK, "vm_check_running", lambda: vm_check)
    monkeypatch.setattr(CK, "release_local_running", lambda _root: False)
    monkeypatch.setattr(
        WT, "survey", lambda *_a, **_k: {"unlanded": [lease], "cache": {}, "orphans": []}
    )
    monkeypatch.setattr(WT, "live_work", lambda *_a, **_k: [])
    monkeypatch.setattr(WT, "unlanded_lines", lambda _got: "    w1")
    monkeypatch.setattr(WT, "report_lines", lambda _got: "")
    queued, blocked = [], []
    monkeypatch.setattr(CK, "outq_add", lambda *a, **_k: queued.append(a[4]))
    CK.worktree_check(
        {}, "sid", {}, types_fold(), [], {"cwd": str(repo)}, lambda *a, **_k: blocked.append(a)
    )
    return queued, blocked


def types_fold():
    return types.SimpleNamespace(items=[])


def test_a_green_receipt_reports_the_lease_instead_of_blocking(repo, monkeypatch):
    _green(repo)
    queued, blocked = _worktree_check(monkeypatch, repo)
    assert blocked == []
    assert any("held for the push" in text for text in queued)
    assert any("w1" in text for text in queued)


def test_without_a_green_receipt_the_unlanded_lease_blocks(repo, monkeypatch):
    """Control: a red receipt leaves the block in place and queues no hold report."""
    _receipt(repo, exitCode=1, headTree=_tree(repo))
    queued, blocked = _worktree_check(monkeypatch, repo)
    assert [b[0] for b in blocked] == ["worktree-unlanded"]
    assert not any("held for the push" in text for text in queued)


def test_a_running_vm_check_still_holds_the_lease(repo, monkeypatch):
    queued, blocked = _worktree_check(monkeypatch, repo, vm_check=True)
    assert blocked == []
    assert any("running vm:check" in text and "w1" in text for text in queued)


def test_a_running_ci_quick_no_longer_holds_the_lease(repo, tmp_path, monkeypatch):
    """A live ci:quick lock changes nothing: the lease still blocks.

    THE OWNER IS A REAL ci:quick SHAPE (aff2b777.2): an interpreter running `scripts/ci-runner/quick-clone.ts` from this checkout with a fresh `at`, the very process the removed reader (`ci_quick_running`, dropped by 65f35528be) held the lease for. A lock owned by the pytest process could not tell a reintroduced reader from none.
    """
    script = repo / "scripts" / "ci-runner" / "quick-clone.ts"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    proc = subprocess.Popen(["python3", "scripts/ci-runner/quick-clone.ts"], cwd=repo)
    try:
        words = hook_proc.argv(proc.pid)
        assert words, "the planted owner has no readable argv"
        # Control: the hook's own argv reader takes the planted owner for a ci:quick run.
        assert CK.argv_runs(words, ("scripts/ci-runner/quick-clone.ts",)), words
        monkeypatch.setenv("CI_QUICK_CLONE_DIR", str(tmp_path / "ciq-clone"))
        now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        (tmp_path / "ciq-clone.lock").write_text(
            json.dumps({"pid": proc.pid, "at": now}), encoding="utf-8"
        )
        queued, blocked = _worktree_check(monkeypatch, repo)
    finally:
        proc.kill()
        proc.wait()
    assert [b[0] for b in blocked] == ["worktree-unlanded"]
    assert not any("ci:quick" in text for text in queued)


def test_a_malformed_advance_step_reads_false_instead_of_raising():
    """aff2b777.1: a list or dict `from` is unhashable; the receipt reads False. The well-formed step is the control."""
    armed = wlfix.import_wl("wl_armed")
    good = {"headTree": "a", "advances": [{"from": "a", "to": "b"}]}
    assert armed.receipt_vouches_for_tree(good, "b") is True
    for bad_from in ([1], {"x": 1}):
        bad = {"headTree": "a", "advances": [{"from": bad_from, "to": "b"}]}
        assert armed.receipt_vouches_for_tree(bad, "b") is False
