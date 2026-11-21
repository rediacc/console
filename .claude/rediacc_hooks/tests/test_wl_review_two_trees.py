"""The per-commit review verbs with two bound trees (worklist #edb41f10, #688c7385; agent/plans/PLAN-two-track-merge-dev.md).

A fixture main checkout holds the development branch, stacked on the PR branch, which a real linked tree at the sibling `<main>-landing` holds; the landing record binds that tree to the PR branch (`commit_policy.write_landing_record`, the writer the landing verb calls). The PR branch carries one commit A, reviewed into the landing tree's `agent/reviews/<PR>/`; the development branch adds commit B.

THE TWO DEFECTS. `worklist.py --review-commit` typed in the landing tree committed the main checkout's records, since the store's root (the main checkout) doubled as the records' root; and the development branch's range `merge-base(origin/main, tip)..tip` walked A as its own, so A was reviewed a second time into `agent/reviews/<DEV>/`.

THE CONTROLS. The same trees with no record read as before the binding: the development range walks A and B, and a verb resolves its project. The worklist verb is driven end to end through the real `worklist.py`, with `CLAUDE_PROJECT_DIR` naming the main checkout and the cwd in the landing tree, exactly as the 2026-11-21 run did.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")

HERE = pathlib.Path(__file__).resolve().parent
WORKLIST = HERE.parents[1] / "hooks" / "stop" / "worklist.py"
WL_REVIEW = HERE.parents[1] / "hooks" / "stop" / "wl_review.py"
PR, DEV = "0101-1", "0101-2"
SID = "abcdef12-0000-4000-8000-000000000000"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
STRIP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "COMMIT_REVIEW_CHILD", "STOPHOOK_CHILD")


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    for key in STRIP:
        monkeypatch.delenv(key, raising=False)
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    # wl_review's locks live under $TMPDIR/claude-worklist: a private one per case.
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(tree, name, text):
    (tree / name).write_text(text, encoding="utf-8")
    _git(tree, "add", "--", name)
    _git(tree, "commit", "-q", "--no-gpg-sign", "-m", "feat: %s" % name)
    return _git(tree, "rev-parse", "HEAD")


def _clean(tree, branch, sha):
    """Record `sha` clean in `tree`'s agent/reviews/<branch>/ ledger, uncommitted."""
    review = R.Review(
        sha=sha,
        subject="feat",
        branch=branch,
        parent=_git(tree, "rev-parse", "%s^" % sha),
        patch_id=R.patch_id(tree, sha),
        reviewed_at="2026-11-21T00:00:00Z",
        model="m",
        labels={"bump": "patch", "kind": ["bug"], "why": "x"},
    )
    assert R.append_clean(tree, branch, review)
    return R.ledger_path(tree, branch)


def _trees(tmp_path, record=True):
    """(main checkout, landing tree, A, B): A on the PR branch, reviewed and committed in the landing tree; B on the development branch, stacked on A, in the main checkout."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    main = (tmp_path / "console").resolve()
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    _commit(main, "seed.txt", "seed\n")
    _git(main, "remote", "add", "origin", str(origin))
    _git(main, "push", "-q", "origin", "main")
    _git(main, "fetch", "-q", "origin")
    _git(main, "branch", PR)
    landing = pathlib.Path(str(main) + "-landing")
    _git(main, "worktree", "add", "-q", str(landing), PR)
    a = _commit(landing, "a.txt", "a\n")
    ledger = _clean(landing, PR, a)
    _git(landing, "add", "--", str(ledger.relative_to(landing)))
    _git(landing, "commit", "-q", "--no-gpg-sign", "-m", "chore(reviews): record")
    if record:
        policy = R._policy()
        policy.write_landing_record(str(main), str(landing), PR)
    _git(main, "switch", "-q", "-c", DEV, PR)
    b = _commit(main, "b.txt", "b\n")
    return main, landing, a, b


# ---- #688c7385: the stacked development branch's range starts at the landing branch


def test_stacked_dev_range_excludes_the_landing_commits(tmp_path):
    main, _landing, _a, b = _trees(tmp_path)
    assert R.uncovered(main, main, DEV) == [b]
    assert R.in_scope_shas(main, main, DEV) == [b]


def test_control_no_record_walks_both(tmp_path):
    """CONTROL: with no landing record the development range is merge-base(origin/main, tip)..tip, A included, as before the binding."""
    main, _landing, a, b = _trees(tmp_path, record=False)
    assert R.uncovered(main, main, DEV) == [b, a]


def test_landing_branch_range_is_unchanged(tmp_path):
    """The PR branch itself is judged from origin/main: its own record never narrows its range."""
    _main, landing, a, _b = _trees(tmp_path)
    assert R.in_scope_shas(landing, landing, PR) == [a]
    assert R.uncovered(landing, landing, PR) == []


def test_trigger_starts_no_review_of_a_landing_commit(tmp_path):
    main, _landing, _a, b = _trees(tmp_path)
    started = []

    def spawn(_root, _repo, sha, branch):
        started.append((sha, branch))
        return 1

    R.trigger(main, main, spawn=spawn)
    assert started == [(b, DEV)]


def test_check_on_dev_demands_no_landing_record(tmp_path):
    main, _landing, _a, b = _trees(tmp_path)
    ledger = _clean(main, DEV, b)
    _git(main, "add", "--", str(ledger.relative_to(main)))
    _git(main, "commit", "-q", "--no-gpg-sign", "-m", "chore(reviews): record")
    reasons, lines = R.check_state(main, DEV)
    assert reasons == [], lines


def test_merged_landing_branch_leaves_the_main_base(tmp_path):
    """Once origin/main moves past the landing branch's old ref (the PR merged), the newer origin/main base stands."""
    main, _landing, _a, b = _trees(tmp_path)
    _git(main, "push", "-q", "origin", "%s:main" % PR)
    _git(main, "fetch", "-q", "origin")
    c = _commit(main, "c.txt", "c\n")
    _git(main, "push", "-q", "origin", "HEAD:main")
    _git(main, "fetch", "-q", "origin")
    d = _commit(main, "d.txt", "d\n")
    assert R.base_range(main, DEV) == "%s..HEAD" % c
    assert R.uncovered(main, main, DEV) == [d]
    assert b not in R.uncovered(main, main, DEV)


# ---- #edb41f10: the review verbs act on the cwd's bound tree


def test_review_root_follows_the_cwd(tmp_path):
    main, landing, _a, _b = _trees(tmp_path)
    (landing / "sub").mkdir()
    assert R.review_root(main, cwd=str(landing)) == landing
    assert R.review_root(main, cwd=str(landing / "sub")) == landing
    assert R.review_root(main, cwd=str(main)) == main
    assert R.review_root(landing, cwd=str(main)) == main
    assert R.review_root(main, cwd=str(tmp_path)) == main


def test_control_review_root_without_record(tmp_path):
    main, landing, _a, _b = _trees(tmp_path, record=False)
    assert R.review_root(main, cwd=str(landing)) == main


def _landing_with_pending(tmp_path):
    """The trees with a second PR-branch commit whose clean record waits uncommitted in the landing tree, and a development record waiting in the main checkout."""
    main, landing, _a, b = _trees(tmp_path)
    e = _commit(landing, "e.txt", "e\n")
    land_ledger = _clean(landing, PR, e)
    dev_ledger = _clean(main, DEV, b)
    return main, landing, land_ledger, dev_ledger


def _worklist(cwd, main, *args):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(main), WORKLIST_SESSION_ID=SID)
    return subprocess.run(
        [sys.executable, str(WORKLIST), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_worklist_review_commit_from_landing_commits_there(tmp_path):
    main, landing, land_ledger, dev_ledger = _landing_with_pending(tmp_path)
    main_head = _git(main, "rev-parse", "HEAD")
    got = _worklist(landing, main, "--review-commit", SID[:8])
    assert got.returncode == 0, got.stdout + got.stderr
    assert _git(main, "rev-parse", "HEAD") == main_head, "the main checkout took a commit"
    assert _git(landing, "log", "-1", "--format=%s").startswith("chore(reviews)")
    assert not _git(landing, "status", "--porcelain", "--", str(land_ledger.relative_to(landing)))
    assert _git(main, "status", "--porcelain", "--", str(dev_ledger.relative_to(main)))


def test_worklist_review_commit_from_main_commits_there(tmp_path):
    """CONTROL: typed in the main checkout the verb commits the development records there and leaves the landing tree alone."""
    main, landing, land_ledger, _dev = _landing_with_pending(tmp_path)
    landing_head = _git(landing, "rev-parse", "HEAD")
    got = _worklist(main, main, "--review-commit", SID[:8])
    assert got.returncode == 0, got.stdout + got.stderr
    assert _git(landing, "rev-parse", "HEAD") == landing_head
    assert _git(landing, "status", "--porcelain", "--", str(land_ledger.relative_to(landing)))
    assert _git(main, "log", "-1", "--format=%s").startswith("chore(reviews)")


def test_wl_review_check_default_root_follows_the_cwd(tmp_path, monkeypatch, capsys):
    """`wl_review.py --check` with no --root, typed in the landing tree, judges the PR branch's records there (the file's own tree stands in as the main checkout)."""
    main, landing, _land, _dev = _landing_with_pending(tmp_path)
    monkeypatch.setattr(R, "CONSOLE_ROOT", main)
    monkeypatch.chdir(landing)
    assert R.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert "per-commit reviews for %s: refused (uncommitted)" % PR in out, out
    monkeypatch.chdir(main)
    assert R.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert "per-commit reviews for %s: refused (uncommitted)" % DEV in out, out


# ---- #edb41f10, the mark: a landing-branch commit's finding is marked in the landing tree's record


def _finding_record(tree, branch, sha, file):
    """An `.md` record in `tree`'s agent/reviews/<branch>/ holding one open medium finding on `file`:1, uncommitted. Returns (path, finding id)."""
    fid = "%s.1" % sha[:8]
    review = R.Review(
        sha=sha,
        subject="feat",
        branch=branch,
        reviewed_at="2026-11-21T00:00:00Z",
        model="m",
        verdict="findings",
        findings=[
            R.Finding(
                id=fid,
                severity="medium",
                file=file,
                line=1,
                anchor="in-diff",
                claim="the fixture line reads the wrong value for this case",
                resolution="open",
            )
        ],
    )
    path = R.review_path(tree, branch, sha)
    R.write_atomic(path, R.render(review))
    return path, fid


def _resolution(path, fid):
    review, err = R.read_review(path)
    assert review is not None, err
    return next(f for f in review.findings if f.id == fid).resolution_kind()


NOT_A_BUG = "a.txt:1 holds the intended value; the claim misreads the fixture"


def _mark(cwd, main, fid, *rest):
    return R.verb(
        "--review-mark",
        SID[:8],
        [fid, *rest],
        R.review_root(main, cwd=str(cwd)),
        dict,
    )


def test_mark_from_dev_for_a_landing_commit_lands_in_the_landing_record(tmp_path):
    """The 2026-11-21 shape: the landing commit's record exists in both directories (the duplicate the range defect wrote), and the mark is typed in the main checkout."""
    main, landing, a, _b = _trees(tmp_path)
    land_path, fid = _finding_record(landing, PR, a, "a.txt")
    dup_path, _ = _finding_record(main, DEV, a, "a.txt")
    rc, text = _mark(main, main, fid, "not-a-bug", NOT_A_BUG)
    assert rc == 0, text
    assert str(land_path) in text, text
    assert _resolution(land_path, fid) == "not-a-bug"
    assert _resolution(dup_path, fid) == "open"


def test_mark_fixed_on_the_landing_branch_from_dev(tmp_path):
    main, landing, a, _b = _trees(tmp_path)
    land_path, fid = _finding_record(landing, PR, a, "a.txt")
    fix = _commit(landing, "a.txt", "a fixed\n")
    rc, text = _mark(main, main, fid, "fixed", fix)
    assert rc == 0, text
    assert _resolution(land_path, fid) == "fixed"


def test_control_mark_of_a_dev_commit_stays_in_dev(tmp_path):
    main, landing, _a, b = _trees(tmp_path)
    dev_path, fid = _finding_record(main, DEV, b, "b.txt")
    rc, text = _mark(
        main, main, fid, "not-a-bug", "b.txt:1 holds the intended value; the claim misreads it"
    )
    assert rc == 0, text
    assert _resolution(dev_path, fid) == "not-a-bug"
    assert not R.branch_dir(landing, DEV).exists()


def test_control_mark_without_record_stays_in_dev(tmp_path):
    main, landing, a, _b = _trees(tmp_path, record=False)
    land_path, fid = _finding_record(landing, PR, a, "a.txt")
    dup_path, _ = _finding_record(main, DEV, a, "a.txt")
    rc, text = _mark(main, main, fid, "not-a-bug", NOT_A_BUG)
    assert rc == 0, text
    assert _resolution(dup_path, fid) == "not-a-bug"
    assert _resolution(land_path, fid) == "open"


def test_worklist_review_mark_from_dev_marks_the_landing_record(tmp_path):
    main, landing, a, _b = _trees(tmp_path)
    land_path, fid = _finding_record(landing, PR, a, "a.txt")
    dup_path, _ = _finding_record(main, DEV, a, "a.txt")
    got = _worklist(main, main, "--review-mark", SID[:8], fid, "not-a-bug", NOT_A_BUG)
    assert got.returncode == 0, got.stdout + got.stderr
    assert _resolution(land_path, fid) == "not-a-bug"
    assert _resolution(dup_path, fid) == "open"
