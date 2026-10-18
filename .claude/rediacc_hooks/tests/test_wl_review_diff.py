"""The reviewed diff leaves out the review records that ride a commit (CLAUDE.md rule 1, Cadence).

A commit that carries `agent/reviews/<branch>/<sha>.md` beside its own change used to send those records to the reviewer, which then filed findings about the records themselves (eight such findings on branch 1008-1, each one closed by hand). `capped_diff` now drops every `agent/reviews/` section and keeps the rest; the control is the same commit's other file, still sent whole.
"""

from __future__ import annotations

import os
import subprocess

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")

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
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=GIT_ENV
    ).stdout.strip()


def _mixed_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "tool.py").write_text("print('changed')\n")
    record = repo / "agent" / "reviews" / "1231-9" / ("a" * 40 + ".md")
    record.parent.mkdir(parents=True)
    record.write_text("# Review aaaaaaaa: a record riding this commit\n\nResolution: open\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: a change with a riding review record")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_a_riding_review_record_is_left_out_of_the_reviewed_diff(tmp_path):
    repo, sha = _mixed_commit(tmp_path)
    diff, _total, files, cut = R.capped_diff(str(repo), sha, 100_000)
    assert "agent/reviews/" not in diff
    assert files == 1
    assert cut == []


def test_control_the_commits_own_change_is_still_sent_whole(tmp_path):
    repo, sha = _mixed_commit(tmp_path)
    diff, _total, _files, _cut = R.capped_diff(str(repo), sha, 100_000)
    assert "diff --git a/tool.py b/tool.py" in diff
    assert "print('changed')" in diff
