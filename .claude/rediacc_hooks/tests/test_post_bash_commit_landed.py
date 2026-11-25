"""A filtered `git commit` that did not land is said out loud (agent/plans/PLAN-stop-hook-retro-20261125.md R20261125.4, friction 4).

On 2026-11-25 a commit run as `... 2>&1 | grep -E '^\\[|BLOCK' | cut -c1-60` printed nothing: the commit-policy hook had refused it with lines starting `commit-policy:`, the deletions stayed staged, and a cherry-pick failed 10 minutes later. The post-bash member `review_commit.py` now compares HEAD with the HEAD it recorded after the session's previous Bash call and, when HEAD did not move and paths are still staged, emits `COMMIT DID NOT LAND`.

Every world is a real repository driven through `lifecycle.run_pattern`, the way the harness runs post-bash. The refusal is a real failing pre-commit hook, and the commit really runs through the filter. A stub `claude` that exits 3 stands in for the model, so a successful commit's detached reviewer never reaches a real one.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_hooks import lifecycle
from rediacc_hooks.tests import wlfix

HOOK = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "post-bash" / "review_commit.py"
SID = "deadbeef-1111-2222-3333-444444444444"
FILTERED = "git commit -q -m 'feat(x): add f' 2>&1 | grep '^\\['"
REFUSAL = "#!/bin/sh\necho 'commit-policy: this commit leaves a generated doc region stale.' >&2\nexit 1\n"


class World:
    def __init__(self, tmp_path: pathlib.Path):
        self.repo = tmp_path / "repo"
        self.tmpdir = tmp_path / "tmpdir"
        stub_bin = tmp_path / "bin"
        for d in (self.repo, self.tmpdir, stub_bin):
            d.mkdir()
        stub = stub_bin / "claude"
        stub.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        stub.chmod(0o755)
        self.env = wlfix.scrubbed_environ()
        self.env.update(
            {
                "PATH": "%s%s%s" % (stub_bin, os.pathsep, self.env.get("PATH", "")),
                "TMPDIR": str(self.tmpdir),
                "CLAUDE_PROJECT_DIR": str(self.repo),
                "GIT_AUTHOR_NAME": "Fixture",
                "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                "GIT_COMMITTER_NAME": "Fixture",
                "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
            }
        )
        self.env.pop("COMMIT_REVIEW_CHILD", None)
        self.env.pop("STOPHOOK_CHILD", None)
        self.git("init", "-q", "--initial-branch=1125-1")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        self.git("add", "seed.txt")
        self.git("commit", "-q", "-m", "seed")

    def git(self, *args, check=True):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
            env=self.env,
            check=check,
        )

    def head(self):
        return self.git("rev-parse", "HEAD").stdout.strip()

    def stage(self, name="f.py"):
        (self.repo / name).write_text("a = 1\n", encoding="utf-8")
        self.git("add", "--", name)

    def shell(self, command):
        """Run `command` in the repository as the Bash tool would, and return its stdout."""
        return subprocess.run(
            ["bash", "-c", command],
            cwd=self.repo,
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        ).stdout

    def hook(self, command):
        """The post-bash member's additionalContext for `command`, "" when it says nothing."""
        payload = json.dumps(
            {
                "session_id": SID,
                "cwd": str(self.repo),
                "tool_name": "Bash",
                "tool_input": {"command": command},
            }
        )
        member = {"command": "%s %s" % (sys.executable, HOOK), "timeout": 20}
        rc, out, _err = lifecycle.run_pattern("post-bash", payload, env=self.env, members=[member])
        assert rc == 0
        if not out.strip():
            return ""
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path)
    monkeypatch.setenv("TMPDIR", str(w.tmpdir))
    # The session's previous Bash call: it records the HEAD the next command starts from.
    w.hook("git status")
    return w


def test_a_commit_refused_by_a_failing_hook_through_a_filter_gives_the_notice(world):
    before = world.head()
    world.stage()
    hook = world.repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(REFUSAL, encoding="utf-8")
    hook.chmod(0o755)
    assert world.shell(FILTERED) == "", "the filter must hide the refusal, as in the incident"
    assert world.head() == before
    ctx = world.hook(FILTERED)
    assert "COMMIT DID NOT LAND in %s: HEAD is still %s" % (world.repo, before[:10]) in ctx, ctx
    assert "1 path(s) are staged" in ctx, ctx
    assert "without the output filter" in ctx, ctx


def test_control_a_successful_commit_gives_no_notice(world):
    before = world.head()
    world.stage()
    world.shell(FILTERED)
    assert world.head() != before, "the control commit must really land"
    ctx = world.hook(FILTERED)
    assert "COMMIT DID NOT LAND" not in ctx, ctx


def test_control_echo_git_commit_gives_no_notice(world):
    world.stage()
    ctx = world.hook("echo git commit")
    assert "COMMIT DID NOT LAND" not in ctx, ctx


def test_control_with_no_record_yet_nothing_is_claimed(tmp_path, monkeypatch):
    """The session's first Bash call has no `before`, so the hook cannot know HEAD did not move."""
    w = World(tmp_path)
    monkeypatch.setenv("TMPDIR", str(w.tmpdir))
    w.stage()
    assert "COMMIT DID NOT LAND" not in w.hook(FILTERED)


def test_a_commit_whose_subject_is_heads_landed_even_when_the_record_already_moved(world):
    """A parallel Bash call can record the new HEAD before this call's hook reads it: the commit's own subject is the witness."""
    world.stage()
    world.shell(FILTERED)
    world.hook("git status")
    world.stage("g.py")
    ctx = world.hook(FILTERED)
    assert "COMMIT DID NOT LAND" not in ctx, ctx
