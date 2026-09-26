"""A guard's fallback directory is the dispatcher's `ev.cwd`, never the process's inherited `$PWD` (#ab3018c9).

`block_stale_pr_branch_date` fell back to `os.environ["PWD"]` when the payload carried no `cwd`. That variable is neither the payload nor what the dispatcher was handed, so the same payload judged a different checkout depending on where the caller stood: running `test_guards_differential` from `.claude/` instead of the repo root changed 28 of this guard's messages.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess

from rediacc_hooks import dispatch


def _git(repo, *args):
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _stale_branch():
    today = datetime.datetime.now().strftime("%m%d")  # noqa: DTZ005 -- the guard reads local time
    return "%s-1" % ("0102" if today == "0101" else "0101")


def test_stale_pr_branch_date_without_payload_cwd_judges_ev_cwd(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    branch = _stale_branch()
    _git(repo, "init", "-q", "--initial-branch=%s" % branch)
    (repo / "seed").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")

    # The caller stands somewhere else entirely: not a repository, so a `$PWD` fallback finds no branch and allows.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("PWD", str(elsewhere))
    monkeypatch.delenv("PR_BRANCH_DATE_OK", raising=False)

    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "gh pr create --draft --fill"}}
    )
    rc, _out, err = dispatch.run_one(
        "block_stale_pr_branch_date", payload, cwd=str(repo), env=dict(os.environ)
    )
    assert rc == 2, err
    assert "branch '%s' carries an OLD date" % branch in err
    assert '-C "%s"' % repo in err

    # A payload that DOES carry a cwd still wins over ev.cwd.
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr create --draft --fill"},
            "cwd": str(elsewhere),
        }
    )
    rc, _out, err = dispatch.run_one(
        "block_stale_pr_branch_date", payload, cwd=str(repo), env=dict(os.environ)
    )
    assert rc == 0, err
