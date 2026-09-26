"""Pre-bash guards that judge state an EARLIER clause of the same command is about to change (PLAN-stop-hook-retro-20260924 #3, box R20260924.22).

WHAT HAPPENED, 2026-09-24. Every pre-bash guard runs once, before the first clause of the command runs. Four refusals in one hour judged a world the command itself was about to change:

  * the bulk-transform guard refused `P="..."; git commit -F $M -- $P` citing "54 staged file(s)": `$P` did not resolve, so it fell back to the SHARED index, which held another writer's deletions. The commit that landed had 17 files.
  * the untagged-commit guard refused a trailer as "names no epic" when the same command ran `worklist.py --publish` first, the clause that would have written the epic.
  * the push guard refused on `carried-reds.json` at the pre-commit HEAD when the same command committed the carry-file fix first.

The fixes these tests pin: `shellscan.earlier_mutators` names the clause, the three guards refuse with `shellscan.V_SPLIT` naming it, the bulk guard expands same-command `$VAR` pathspecs and never presents the shared index as the commit's own count, and `worklist.py --publish <me>` defaults its branch to HEAD's.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

from rediacc_hooks import dispatch, shellscan
from rediacc_hooks.guards import block_unverified_push as PUSH
from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

STALE_UNRELATED = 60
TS_FILES = 25
LONG_REASON = (
    "A reason of at least eighty characters, because the carried-reds bar refuses a bare "
    "'known issue' and this fixture has to clear it to reach the stale-entry arm."
)


def _git_env():
    return dict(
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
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=_git_env(),
    ).stdout


def _repo(path, branch="main"):
    path.mkdir(parents=True)
    _git(path, "init", "-q", "--initial-branch=%s" % branch)
    return path


def _bulk_world(path, extra_ts):
    """A repo whose index carries 60 unrelated staged deletions, the shared-tree shape.

    `extra_ts` tracked `.ts` files are committed and then modified in the WORKTREE only, so a pathspec commit of them is exactly that many files and the index knows nothing of them.
    """
    repo = _repo(path)
    for i in range(STALE_UNRELATED):
        (repo / ("unrelated-%02d.txt" % i)).write_text("u\n", encoding="utf-8")
    for name in extra_ts:
        (repo / name).write_text("export const x = 1;\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    _git(repo, "rm", "-q", "--", *("unrelated-%02d.txt" % i for i in range(STALE_UNRELATED)))
    for name in extra_ts:
        (repo / name).write_text("export const x = 2;\n", encoding="utf-8")
    (repo / "m").write_text("fix: two files\n", encoding="utf-8")
    return repo


def _payload(cmd, cwd):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)})


def _run(stem, cmd, repo, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    for name in ("PR_HEAD_REF", "GITHUB_HEAD_REF", "GIT_INDEX_FILE", "GIT_DIR"):
        monkeypatch.delenv(name, raising=False)
    return dispatch.run_one(stem, _payload(cmd, repo), cwd=str(repo), env=dict(os.environ))


# --------------------------------------------------------------------------- earlier_mutators ---------------------------------------------------------------------------


def test_earlier_mutators_names_the_clauses_before_the_verb_in_order():
    cmd = (
        "printf 'fix\\n' > c11-msg.txt; git add a.ts && git commit -F c11-msg.txt -- a.ts; "
        "npm run ci:quick && .claude/hooks/stop/worklist.py --publish d778be9d && git push"
    )
    got = shellscan.earlier_mutators(cmd, "git push")
    assert [m.kind for m in got] == ["redirect", "stage", "commit", "ci", "publish"]
    assert [m.label for m in got][2:] == ["git commit", "npm run ci:quick", "worklist.py --publish"]
    assert got[0].target == "c11-msg.txt"
    # Only what runs BEFORE the verb: nothing after it can have changed what the guard read.
    assert shellscan.earlier_mutators("git push; git commit -m x -- a", "git push") == []
    # A verb the command does not run has nothing before it.
    assert shellscan.earlier_mutators("git add a; ls", "git push") == []
    # `kinds` narrows to what a given guard reads, and /dev/null is not a file anyone judges.
    assert shellscan.earlier_mutators("git add a >/dev/null; git commit -m x", "git commit") != []
    assert (
        shellscan.earlier_mutators(
            "git add a >/dev/null; git commit -m x", "git commit", {"redirect"}
        )
        == []
    )


# --------------------------------------------------------------------------- the bulk-transform guard ---------------------------------------------------------------------------


def test_bulk_guard_expands_a_same_command_pathspec_variable(tmp_path, monkeypatch):
    """`P="a.ts b.ts"; git commit -F m -- $P` is a two-file commit, whatever the shared index holds.

    Before the fix `$P` did not resolve, the guard fell back to the index, and refused citing 60 files the commit would never touch.
    """
    repo = _bulk_world(tmp_path / "r", ["a.ts", "b.ts"])
    rc, _out, err = _run(
        "block_unproven_bulk_transform", 'P="a.ts b.ts"; git commit -F m -- $P', repo, monkeypatch
    )
    assert rc == 0, err
    # The braced form and a quoted use expand the same way.
    rc, _out, err = _run(
        "block_unproven_bulk_transform", 'P="a.ts b.ts"; git commit -F m -- ${P}', repo, monkeypatch
    )
    assert rc == 0, err


def test_bulk_guard_still_refuses_an_expanded_bulk_pathspec_with_its_own_count(
    tmp_path, monkeypatch
):
    """The inverse: expanding a pathspec must not become a way past the guard."""
    names = ["f%02d.ts" % i for i in range(TS_FILES)]
    repo = _bulk_world(tmp_path / "r", names)
    rc, _out, err = _run(
        "block_unproven_bulk_transform",
        "P=\"$(git ls-files '*.ts')\"; git commit -F m -- $P",
        repo,
        monkeypatch,
    )
    assert rc == 2
    assert "%d file(s)" % TS_FILES in err, err
    assert str(STALE_UNRELATED) not in err, err


def test_bulk_guard_never_calls_the_shared_index_the_commits_own(tmp_path, monkeypatch):
    """An unexpandable pathspec still refuses (fail closed), but says whose count it is."""
    repo = _bulk_world(tmp_path / "r", ["a.ts", "b.ts"])
    rc, _out, err = _run(
        "block_unproven_bulk_transform", "git commit -F m -- $UNSET_HERE", repo, monkeypatch
    )
    assert rc == 2
    assert "`$UNSET_HERE` could not be expanded" in err, err
    assert "%d is the shared index, not this commit" % STALE_UNRELATED in err, err


# --------------------------------------------------------------------------- V_SPLIT ---------------------------------------------------------------------------


def _split_head():
    return shellscan.V_SPLIT.split("\n", 1)[0].split("%", 1)[0]


def test_push_guard_names_the_commit_that_would_have_changed_head(tmp_path, monkeypatch):
    """The 19:28:10 shape: the carry-file fix is committed by an EARLIER clause, the guard judges the pre-commit HEAD."""
    repo = PUSH._repo_with_receipt(
        tmp_path / "r",
        {"whole": True, "exitCode": 1, "failed": ["check:ci-parity"]},
        carried={
            "carried": [
                {"gate": "check:ci-parity", "reason": LONG_REASON},
                {"gate": "check:ci-paths-origin", "reason": LONG_REASON},
            ]
        },
    )
    (repo / "x").write_text("x\n", encoding="utf-8")
    cmd = "printf 'fix: carry\\n' > m; git commit -F m -- x; git push"
    rc, _out, err = _run("block_unverified_push", cmd, repo, monkeypatch)
    assert rc == 2
    assert _split_head() in err, err
    assert "`git commit`" in err, err
    # The original finding is still there under the split notice, so nothing is hidden.
    assert "NOT failing" in err, err
    # Without the earlier clause the same state refuses WITHOUT the split notice.
    rc, _out, err = _run("block_unverified_push", "git push", repo, monkeypatch)
    assert rc == 2
    assert _split_head() not in err, err


def test_untagged_guard_names_the_publish_that_would_have_written_the_epic(tmp_path, monkeypatch):
    """The 19:02:10 shape: `worklist.py --publish` runs first, the guard reads the snapshot as it was."""
    repo = _repo(tmp_path / "r", branch="0923-1")
    snap = repo / "agent" / "pr"
    snap.mkdir(parents=True)
    (snap / "0923-1.md").write_text("### Old epic\n\n`PR-TASK: 5d0c1a2b`\n", encoding="utf-8")
    (repo / "a").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    trailer = 'git commit -m "feat: x\n\nPR-TASK: e4eaf80b" -- a'
    cmd = ".claude/hooks/stop/worklist.py --publish d778be9d 0923-1 && " + trailer
    rc, _out, err = _run("block_untagged_commit", cmd, repo, monkeypatch)
    assert rc == 2
    assert _split_head() in err, err
    assert "`worklist.py --publish`" in err, err
    assert "names no epic" in err, err
    rc, _out, err = _run("block_untagged_commit", trailer, repo, monkeypatch)
    assert rc == 2
    assert _split_head() not in err, err


# --------------------------------------------------------------------------- worklist.py --publish ---------------------------------------------------------------------------


def test_publish_defaults_to_heads_branch(wl, tmp_path):  # noqa: F811
    repo = _repo(tmp_path / "pub", branch="t-1")
    (repo / "seed").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    env = dict(wl.env)
    env["WORKLIST_PUBLISH_ROOT"] = str(repo)
    env["WORKLIST_JUDGE"] = "off"
    got = wl.python(["--publish", wlfix.ME], env=env)
    assert got.rc == 0, got.out + got.err
    written = repo / "agent" / "pr" / "t-1.md"
    assert written.is_file(), got.out + got.err
    assert "# Work in t-1" in written.read_text(encoding="utf-8")

    # DETACHED: there is no branch to default to, so the verb still asks for one.
    _git(repo, "checkout", "-q", "--detach")
    got = wl.python(["--publish", wlfix.ME], env=env)
    assert got.rc == 2
    assert "usage: worklist.py --publish" in got.err
    assert not (repo / "agent" / "pr" / "HEAD.md").exists()


def test_publish_explicit_branch_still_wins(wl, tmp_path):  # noqa: F811
    repo = _repo(tmp_path / "pub", branch="t-1")
    (repo / "seed").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    env = dict(wl.env)
    env["WORKLIST_PUBLISH_ROOT"] = str(repo)
    env["WORKLIST_JUDGE"] = "off"
    got = wl.python(["--publish", wlfix.ME, "other-2"], env=env)
    assert got.rc == 0, got.out + got.err
    assert (repo / "agent" / "pr" / "other-2.md").is_file()
    assert not (pathlib.Path(repo) / "agent" / "pr" / "t-1.md").exists()
