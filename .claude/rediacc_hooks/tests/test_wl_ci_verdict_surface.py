"""wl_civerdict: the CI-published `CI Verdict` reaches every session exactly once per (sha, run, attempt), and reading it costs nothing it should not (agent/plans/PLAN-ci-verdict.md, box D).

The unit cases drive `wl_civerdict` directly with a recording `gh` shim on PATH, so a network call is COUNTED rather than assumed absent. The Stop cases drive the real hook to prove the wiring in `wl_checks`: the note appears on the first stop, not on the second, and for a second session once more.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401
from rediacc_hooks.wellknown import GH_ORIGIN, GH_REPO

CV = wlfix.import_wl("wl_civerdict")
CI = wlfix.import_wl("wl_ci")

SHA = "a7f305585530b61da88faf297b9d5805e5eb2b98"
RUN = 36953549081
BRANCH = "0930-1"
TITLE = "cancelled by watchdog budget: 'Tests + Infra / E2E Workers (fedora-43, 1/8)' ran 20.1m (budget 20m)"


def verdict(attempt=1, sha=SHA, run=RUN, kind="watchdog-budget"):
    return {
        "schema": "ci-verdict/v1",
        "head_sha": sha,
        "run_id": run,
        "attempt": attempt,
        "workflow": "Console CI",
        "conclusion": "cancelled",
        "verdict": "cancelled",
        "cause": {
            "kind": kind,
            "detail": "x",
            "job": "J",
            "minutes": 20.1,
            "budget_min": 20,
            "watchdog_run": 1,
        },
        "first_failure": None,
        "gaps": [],
        "next": "",
    }


def check_run(doc, title=TITLE, slug="github-actions"):
    return {
        "app": {"slug": slug},
        "output": {
            "title": title,
            "summary": "CANCELLED  line one\n  cause: x",
            "text": json.dumps(doc),
        },
    }


@pytest.fixture
def shim(tmp_path, monkeypatch):
    """A `gh` that logs every call and serves `answer.json`; returns (log path, answer path)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "gh.log"
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"check_runs": []}), encoding="utf-8")
    gh = bindir / "gh"
    gh.write_text('#!/bin/bash\necho "$*" >> "%s"\ncat "%s"\n' % (log, answer), encoding="utf-8")
    gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir), prepend=os.pathsep)
    return log, answer


def calls(log):
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.fixture
def repo(tmp_path):
    """A git repo with origin pointing at github and an origin/<BRANCH> ref at HEAD."""
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init", "-q", "-b", BRANCH)
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("remote", "add", "origin", GH_ORIGIN + "/" + GH_REPO + ".git")
    (root / "a").write_text("a\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    head = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/%s" % BRANCH, head)
    return root, head


# --------------------------------------------------------------------------- once per session per key


def test_two_sessions_are_each_notified_once(tmp_path, shim):
    wlp = tmp_path / "wl.md"
    CV.write_cache(wlp, BRANCH, SHA, verdict(), TITLE, "CANCELLED  line one")
    a1 = CV.note(tmp_path, wlp, "aaaaaaaa-1", branch=BRANCH)
    assert TITLE in a1
    assert "run %s, attempt 1" % RUN in a1
    assert CV.note(tmp_path, wlp, "aaaaaaaa-1", branch=BRANCH) == "", (
        "the same key must stay silent for the same session"
    )
    b1 = CV.note(tmp_path, wlp, "bbbbbbbb-2", branch=BRANCH)
    assert TITLE in b1, "a second session gets its own one notice"
    assert CV.note(tmp_path, wlp, "bbbbbbbb-2", branch=BRANCH) == ""
    assert calls(shim[0]) == [], "no ref: the cache alone is read"


@pytest.mark.usefixtures("shim")
def test_a_new_attempt_renotifies(tmp_path):
    wlp = tmp_path / "wl.md"
    CV.write_cache(wlp, BRANCH, SHA, verdict(attempt=1), TITLE)
    assert CV.note(tmp_path, wlp, "aaaaaaaa", branch=BRANCH)
    CV.write_cache(wlp, BRANCH, SHA, verdict(attempt=2), "green: rerun passed")
    again = CV.note(tmp_path, wlp, "aaaaaaaa", branch=BRANCH)
    assert "attempt 2" in again
    assert "green: rerun passed" in again


@pytest.mark.usefixtures("shim")
def test_a_miss_recorded_in_the_cache_is_silent(tmp_path):
    wlp = tmp_path / "wl.md"
    CV.write_cache(wlp, BRANCH, SHA, None)
    assert CV.note(tmp_path, wlp, "aaaaaaaa", branch=BRANCH) == ""


@pytest.mark.usefixtures("shim")
def test_a_broken_cache_never_raises(tmp_path):
    wlp = tmp_path / "wl.md"
    CV.cache_path(wlp, BRANCH).write_text("{not json", encoding="utf-8")
    assert CV.note(tmp_path, wlp, "aaaaaaaa", branch=BRANCH) == ""
    assert CV.session_start_line(wlp, BRANCH) == ""


# --------------------------------------------------------------------------- SessionStart is network-free


def test_session_start_makes_zero_gh_calls(tmp_path, shim):
    wlp = tmp_path / "wl.md"
    CV.write_cache(wlp, BRANCH, SHA, verdict(), TITLE)
    line = CV.session_start_line(wlp, BRANCH)
    assert line.startswith("Last CI verdict for %s @ %s" % (BRANCH, SHA[:8]))
    assert TITLE in line
    assert "\n" not in line
    assert calls(shim[0]) == []
    assert CV.session_start_line(wlp, "other-branch") == "", (
        "branch-keyed: another branch's verdict is not this one's"
    )


# --------------------------------------------------------------------------- the network read, when opted in


def test_an_opted_in_read_fetches_once_then_serves_the_ttl(repo, tmp_path, shim):
    root, head = repo
    log, answer = shim
    answer.write_text(json.dumps({"check_runs": [check_run(verdict(sha=head))]}), encoding="utf-8")
    wlp = tmp_path / "wl.md"
    first = CV.note(root, wlp, "aaaaaaaa", ref=BRANCH)
    assert TITLE in first
    assert len(calls(log)) == 1
    assert "commits/%s/check-runs" % head in calls(log)[0]
    assert "check_name=CI%20Verdict" in calls(log)[0]
    assert CV.note(root, wlp, "bbbbbbbb", ref=BRANCH), (
        "the second session is served from the shared cache"
    )
    assert len(calls(log)) == 1, "inside the TTL nobody re-asks GitHub"
    assert json.loads(CV.cache_path(wlp, BRANCH).read_text(encoding="utf-8"))["sha"] == head


def test_a_missing_verdict_is_recorded_so_the_ttl_holds(repo, tmp_path, shim):
    root, _head = repo
    log, _answer = shim
    wlp = tmp_path / "wl.md"
    assert CV.note(root, wlp, "aaaaaaaa", ref=BRANCH) == ""
    assert CV.note(root, wlp, "aaaaaaaa", ref=BRANCH) == ""
    assert len(calls(log)) == 1


def test_an_expired_ttl_reads_again(repo, tmp_path, shim):
    root, head = repo
    log, answer = shim
    wlp = tmp_path / "wl.md"
    CV.write_cache(wlp, BRANCH, head, None, now=0)
    answer.write_text(json.dumps({"check_runs": [check_run(verdict(sha=head))]}), encoding="utf-8")
    assert TITLE in CV.note(root, wlp, "aaaaaaaa", ref=BRANCH)
    assert len(calls(log)) == 1


def test_fetch_takes_the_newest_attempt_and_only_github_actions_documents(repo, shim):
    root, head = repo
    _log, answer = shim
    runs = [
        check_run(verdict(attempt=2, sha=head), title="attempt two"),
        check_run(verdict(attempt=1, sha=head), title="attempt one"),
        check_run(verdict(attempt=9, sha=head), title="impostor", slug="someone-else"),
        {
            "app": {"slug": "github-actions"},
            "output": {"title": "not ours", "text": '{"schema": "other"}'},
        },
    ]
    answer.write_text(json.dumps({"check_runs": runs}), encoding="utf-8")
    doc, title, _summary = CV.fetch(root, head)
    assert (doc["attempt"], title) == (2, "attempt two")


# --------------------------------------------------------------------------- the context never blocks


def _ctx(name, status, conclusion):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "databaseId": 1,
        "detailsUrl": "",
        "checkSuite": {"workflowRun": {"databaseId": RUN}},
    }


@pytest.mark.parametrize(
    ("status", "conclusion"),
    [("IN_PROGRESS", None), ("COMPLETED", "FAILURE"), ("COMPLETED", "NEUTRAL")],
)
@pytest.mark.parametrize("name", ["CI Verdict", "Publish CI Verdict"])
def test_the_verdict_context_never_makes_a_head_live_or_red(name, status, conclusion):
    info = {
        "rollup": "PENDING",
        "contexts": [_ctx("CI Complete", "COMPLETED", "SUCCESS"), _ctx(name, status, conclusion)],
    }
    live, hard, soft = CI.ci_classify(info)
    assert (live, hard, soft) == (False, [], [])


# --------------------------------------------------------------------------- the Stop hook wiring


def _stop_env(extra=None):
    env = {"WORKLIST_AGENT_BRANCH": BRANCH, "WORKLIST_PUBLISH_REF": ""}
    env.update(extra or {})
    return env


def test_the_stop_hook_shows_the_verdict_once_per_session(wl):  # noqa: F811
    wl.setup()
    wl.brief_now()
    CV.write_cache(
        wl.wl, BRANCH, SHA, verdict(), TITLE, "CANCELLED  line one\n  cause: watchdog-budget"
    )
    first = wl.run(_stop_env())
    assert "CI VERDICT for %s @ %s" % (BRANCH, SHA[:8]) in first.out, first.out[:1500]
    assert TITLE in first.out
    second = wl.run(_stop_env())
    assert "CI VERDICT for" not in second.out, "shown once: %s" % second.out[:800]
    peer = wl.run_as("cafe1234", _stop_env())
    assert "CI VERDICT for" in peer.out, "a second session gets its own notice: %s" % peer.out[:800]


def test_the_stop_hook_stays_silent_without_a_verdict(wl):  # noqa: F811
    wl.setup()
    wl.brief_now()
    got = wl.run(_stop_env())
    assert "CI VERDICT for" not in got.out


# --------------------------------------------------------------------------- box G: the push arms one watcher per head


_spec = importlib.util.spec_from_file_location(
    "arm_ci_watch", wlfix.STOP_DIR.parent / "post-bash" / "arm_ci_watch.py"
)
assert _spec is not None
assert _spec.loader is not None
AW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AW)

SID = "deadbeef-1111-2222-3333-444444444444"


class Fakes:
    """The worklist CLI, the spawner and the liveness probe, recorded."""

    def __init__(self, lease_rc=0):
        self.cli_calls = []
        self.spawned = []
        self.killed = []
        self.lease_rc = lease_rc
        self.next_pid = 4242

    def cli(self, _root, _sid, *argv):
        self.cli_calls.append(argv)
        if argv[0] == "--add":
            return 0, "added #c1a0be11: %s\n" % argv[2]
        if argv[0] == "--lease":
            return self.lease_rc, ""
        return 1, ""

    def spawn(self, _root, _sid, branch, item, _log_path):
        self.next_pid += 1
        self.spawned.append((branch, item, self.next_pid))
        return self.next_pid

    def alive(self, pid):
        return any(p == pid for _b, _i, p in self.spawned) and pid not in self.killed

    def arm(self, root):
        return AW.arm(root, SID, cli=self.cli, spawn=self.spawn, alive=self.alive)


@pytest.fixture
def armenv(tmp_path, monkeypatch, repo):
    root, _head = repo
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmpdir"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setattr(AW, "_kill", lambda _pid: None)
    return root


def _new_head(root):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    (root / "b").write_text("b\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "next")
    head = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/%s" % BRANCH, head)
    return head


def test_a_push_arms_exactly_one_watcher(armenv):
    f = Fakes()
    line = f.arm(armenv)
    assert line.startswith("CI watch armed for %s @ " % BRANCH), line
    assert len(f.spawned) == 1
    assert [c[0] for c in f.cli_calls] == ["--add", "--lease"]
    add, lease = f.cli_calls
    assert add[1] == "deadbeef"
    assert add[2].startswith("(deadbeef) CI verdict for %s" % BRANCH)
    assert lease[1:] == ("deadbeef", "c1a0be11", "+180", "worker:%d" % f.spawned[0][2])
    state = json.loads(AW.state_path(AW.C.worklist_for(armenv), BRANCH).read_text(encoding="utf-8"))
    assert state["pid"] == f.spawned[0][2]
    assert state["item"] == "c1a0be11"


def test_a_second_push_for_the_same_head_arms_none(armenv):
    f = Fakes()
    f.arm(armenv)
    again = f.arm(armenv)
    assert again.startswith("CI watch already running"), again
    assert len(f.spawned) == 1
    assert len(f.cli_calls) == 2


def test_a_new_head_arms_a_new_watcher_on_the_same_item(armenv):
    f = Fakes()
    f.arm(armenv)
    _new_head(armenv)
    f.arm(armenv)
    assert len(f.spawned) == 2
    assert [c[0] for c in f.cli_calls] == ["--add", "--lease", "--lease"], "the open item is reused"
    assert f.spawned[1][1] == "c1a0be11"


def test_a_dead_watcher_for_the_same_head_is_replaced(armenv):
    f = Fakes()
    f.arm(armenv)
    f.killed.append(f.spawned[0][2])
    f.arm(armenv)
    assert len(f.spawned) == 2


def test_a_ticked_item_gets_a_fresh_one(armenv):
    f = Fakes()
    f.arm(armenv)
    _new_head(armenv)
    f.lease_rc = 1
    f.arm(armenv)
    assert [c[0] for c in f.cli_calls] == ["--add", "--lease", "--lease", "--add", "--lease"]


def test_a_push_that_did_not_move_the_branch_arms_nothing(armenv):
    # A local commit the push never delivered: origin/<branch> stays on the old head.
    (armenv / "c").write_text("c\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(armenv), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(armenv), "commit", "-qm", "local only"], check=True)
    f = Fakes()
    assert f.arm(armenv) == ""
    assert f.spawned == []
    assert f.cli_calls == []


def test_main_is_never_watched(armenv):
    subprocess.run(["git", "-C", str(armenv), "checkout", "-q", "-b", "main"], check=True)
    f = Fakes()
    assert f.arm(armenv) == ""
    assert f.spawned == []


@pytest.mark.usefixtures("armenv")
def test_the_hook_ignores_a_command_without_git_push():
    payload = json.dumps({"session_id": SID, "tool_input": {"command": "ls -la"}})
    done = subprocess.run(
        [sys.executable, str(wlfix.STOP_DIR.parent / "post-bash" / "arm_ci_watch.py")],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0
    assert done.stdout == ""


# --------------------------------------------------------------------------- box G: SessionStart reads the cache, never the network


def test_session_start_shows_the_cached_verdict_with_a_gh_that_fails_on_any_call(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "gh-called"
    gh = bindir / "gh"
    gh.write_text('#!/bin/bash\ntouch "%s"\nexit 3\n' % marker, encoding="utf-8")
    gh.chmod(0o755)
    env = wlfix.scrubbed_environ()
    env.update(
        {
            "PATH": "%s%s%s" % (bindir, os.pathsep, env.get("PATH", "")),
            "TMPDIR": str(tmp_path / "tmpdir"),
            "CLAUDE_PROJECT_DIR": str(proj),
            "WORKLIST_AGENT_BRANCH": BRANCH,
        }
    )
    (tmp_path / "tmpdir").mkdir()
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, %r); import wl_core; print(wl_core.worklist_for(%r))"
            % (str(wlfix.STOP_DIR), str(proj)),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    worklist = probe.stdout.strip()
    CV.write_cache(worklist, BRANCH, SHA, verdict(), TITLE, "CANCELLED  line one")
    done = subprocess.run(
        [sys.executable, str(wlfix.HOOK), "--session-start"],
        input=json.dumps({"session_id": SID, "cwd": str(proj), "source": "startup"}),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "Last CI verdict for %s @ %s" % (BRANCH, SHA[:8]) in done.stdout, done.stdout[:800]
    assert TITLE in done.stdout
    assert not marker.exists(), "SessionStart reached gh"


def test_the_real_worklist_accepts_the_item_and_the_lease(armenv, monkeypatch):
    """The --add text and the --lease shape pass the REAL worklist CLI, run as the session."""
    monkeypatch.setenv("WORKLIST_SESSION_ID", SID)
    spawned = []

    def spawn(_root, _sid, _branch, item, _log):
        spawned.append(item)
        return 999999

    line = AW.arm(armenv, SID, spawn=spawn, alive=lambda _pid: False)
    assert line.startswith("CI watch armed"), line
    rc, out = AW.worklist_cli(armenv, SID, "--list", "--open", "deadbeef")
    assert rc == 0, out
    assert "#%s" % spawned[0] in out, out[-800:]
    assert "worker:999999" in out, out[-800:]
