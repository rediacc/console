"""Per-commit review: the post-bash trigger, the detached runner, the file format, the verbs and the SessionStart surfacing (agent/plans/PLAN-per-commit-review.md section 12).

Every case builds a real git repository with an `origin/main`, makes real commits, and replaces only the MODEL: a stub `claude` on PATH that answers with a canned `structured_output`. The stub refuses (exit 3) unless it runs with `STOPHOOK_CHILD=1` and a cwd OUTSIDE the repository, which is the recursion guard the plan's H4 requires, so a reviewer that lost either writes `Verdict: failed`.

Controls run beside the cases they make meaningful: the stub really sleeps (so "the hook returned in under a second" is evidence of detachment, not of a fast stub), the stub really refuses without the child env, and a hand edit really breaks the Body-Sig.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
import types

import pytest

from rediacc_hooks import lifecycle
from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")

HOOK = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "post-bash" / "review_commit.py"
BRANCH = "0930-1"
SID = "deadbeef-1111-2222-3333-444444444444"

STUB = r"""#!/usr/bin/env python3
import json, os, sys, time
repo = os.path.realpath(os.environ["STUB_REPO"])
calls = os.environ.get("STUB_CALLS")
if calls:
    with open(calls, "a") as fh:
        fh.write("call\n")
if os.environ.get("STOPHOOK_CHILD") != "1" or os.environ.get("COMMIT_REVIEW_CHILD") != "1":
    sys.exit(3)
if os.path.realpath(os.getcwd()).startswith(repo):
    sys.exit(3)
prompt = sys.argv[sys.argv.index("-p") + 1] if "-p" in sys.argv else ""
if "COMMIT MESSAGE" not in prompt or "DIFF" not in prompt:
    sys.exit(4)
time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
with open(os.environ["STUB_OUT"]) as fh:
    out = json.load(fh)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.0, "structured_output": out}))
"""


def _git(repo, *args, env=None, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=env, check=check
    )


class World:
    def __init__(self, tmp_path: pathlib.Path):
        self.tmp = tmp_path
        self.repo = tmp_path / "repo"
        self.bin = tmp_path / "bin"
        self.tmpdir = tmp_path / "tmpdir"
        self.out = tmp_path / "stub-out.json"
        self.calls = tmp_path / "stub-calls"
        for d in (self.repo, self.bin, self.tmpdir):
            d.mkdir()
        stub = self.bin / "claude"
        stub.write_text(STUB, encoding="utf-8")
        stub.chmod(0o755)
        self.env = wlfix.scrubbed_environ()
        self.env.update(
            {
                "PATH": "%s%s%s" % (self.bin, os.pathsep, self.env.get("PATH", "")),
                "TMPDIR": str(self.tmpdir),
                "CLAUDE_PROJECT_DIR": str(self.repo),
                "STUB_REPO": str(self.repo),
                "STUB_OUT": str(self.out),
                "STUB_CALLS": str(self.calls),
                "STUB_SLEEP": "0",
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
        self.answer(
            [
                {
                    "severity": "high",
                    "file": "f.py",
                    "line": 2,
                    "claim": "returns None on the empty path",
                },
                {"severity": "medium", "file": "f.py", "line": 3, "claim": "untested branch"},
                {"severity": "high", "file": "not/in/commit.py", "line": 1, "claim": "dropped"},
            ]
        )
        self.init_repo(self.repo)

    def answer(self, findings, bump="patch"):
        self.out.write_text(
            json.dumps(
                {
                    "verdict": "findings" if findings else "clean",
                    "findings": findings,
                    "labels": {"bump": bump, "kind": ["bug"], "why": "fixes a crash"},
                }
            ),
            encoding="utf-8",
        )

    def git(self, *args, repo=None, check=True):
        return _git(repo or self.repo, *args, env=self.env, check=check)

    def init_repo(self, repo):
        origin = self.tmp / ("origin-%s.git" % repo.name)
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, env=self.env)
        self.git("init", "-q", "--initial-branch=main", repo=repo)
        (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        self.git("add", "seed.txt", repo=repo)
        self.git("commit", "-q", "-m", "seed", repo=repo)
        self.git("remote", "add", "origin", str(origin), repo=repo)
        self.git("push", "-q", "origin", "main", repo=repo)
        self.git("checkout", "-q", "-b", BRANCH, repo=repo)

    def commit(self, name="f.py", body="a = 1\nb = 2\nc = 3\n", msg="fix(x): y", repo=None):
        repo = repo or self.repo
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        self.git("add", "--", name, repo=repo)
        self.git("commit", "-q", "-m", msg, "--", name, repo=repo)
        return self.git("rev-parse", "HEAD", repo=repo).stdout.strip()

    def hook(self, command, cwd=None, extra_env=None):
        """Drive the member through lifecycle.run_pattern, the way the harness runs post-bash."""
        payload = json.dumps(
            {
                "session_id": SID,
                "cwd": str(cwd or self.repo),
                "tool_name": "Bash",
                "tool_input": {"command": command},
            }
        )
        member = {
            "command": "%s %s" % (sys.executable, HOOK),
            "timeout": 10,
        }
        env = dict(self.env, **(extra_env or {}))
        started = time.monotonic()
        rc, out, err = lifecycle.run_pattern("post-bash", payload, env=env, members=[member])
        return rc, out, err, time.monotonic() - started

    def review_file(self, sha):
        return R.review_path(self.repo, BRANCH, sha)

    def wait_for(self, path, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if path.exists():
                return True
            time.sleep(0.2)
        return False

    def run_child(self, sha, extra_env=None):
        env = dict(self.env, **(extra_env or {}))
        return subprocess.run(
            [
                sys.executable,
                str(R.SELF),
                "--run",
                sha,
                "--branch",
                BRANCH,
                "--root",
                str(self.repo),
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=60,
        )


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path)
    monkeypatch.setenv("TMPDIR", str(w.tmpdir))
    monkeypatch.setenv("PATH", w.env["PATH"])
    return w


def _context(out):
    if not out.strip():
        return ""
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


# --------------------------------------------------------------------------- 1. a commit produces a review file


def test_a_commit_starts_a_detached_reviewer_and_its_file_lands(world):
    world.env["STUB_SLEEP"] = "3"
    sha = world.commit()
    rc, out, err, took = world.hook("git commit -m 'fix(x): y' -- f.py")
    assert rc == 0, err
    assert took < 1.5, "the hook waited %.1fs: the reviewer is holding its pipes (H3)" % took
    assert "per-commit review started for console %s" % sha[:8] in _context(out)
    path = world.review_file(sha)
    assert world.wait_for(path), "no review file within 20s; log: %s" % (
        world.tmpdir / "claude-worklist" / "reviews" / "logs" / ("%s.log" % sha)
    )
    review = R.parse(path.read_text(encoding="utf-8"))
    assert review.verdict == "findings"
    assert review.repo == "console"
    assert review.branch == BRANCH
    assert review.dropped == 1, "the finding naming a file outside the commit must be dropped"
    assert [(f.id, f.severity, f.file, f.line, f.resolution) for f in review.findings] == [
        ("%s.1" % sha[:8], "high", "f.py", 2, "open"),
        ("%s.2" % sha[:8], "medium", "f.py", 3, "open"),
    ]
    assert review.labels == {"bump": "patch", "kind": ["bug"], "why": "fixes a crash"}
    assert len(review.patch_id) == 40


def test_control_the_stub_really_sleeps_so_the_timing_case_can_fail(world):
    world.env["STUB_SLEEP"] = "3"
    sha = world.commit()
    started = time.monotonic()
    done = world.run_child(sha)
    assert done.returncode == 0, done.stdout + done.stderr
    assert time.monotonic() - started >= 3, (
        "a stub that does not sleep proves nothing about detachment"
    )


def test_control_the_stub_refuses_without_the_child_env(world):
    done = subprocess.run(
        [str(world.bin / "claude"), "-p", "COMMIT MESSAGE DIFF"],
        capture_output=True,
        text=True,
        env=dict(world.env),
        cwd=str(world.tmp),
        check=False,
    )
    assert done.returncode == 3


def test_a_failed_commit_starts_nothing(world):
    sha = world.commit()
    world.run_child(sha)
    assert world.review_file(sha).exists()
    world.calls.unlink()
    nothing = world.git("commit", "-m", "x", check=False)
    assert nothing.returncode != 0
    rc, out, _err, _took = world.hook("git commit -m x")
    assert rc == 0
    assert "started" not in _context(out)
    time.sleep(1)
    assert not world.calls.exists(), "a commit that made no sha reached the model"


def test_a_reviews_only_commit_is_not_reviewed(world):
    sha = world.commit()
    world.run_child(sha)
    rel = str(world.review_file(sha).relative_to(world.repo))
    world.git("add", "--", rel)
    world.git("commit", "-q", "-m", "chore(reviews): record", "--", rel)
    assert R.uncovered(world.repo, world.repo, BRANCH) == []


def test_a_gitlink_only_commit_is_skipped_without_a_model_call(world):
    seed = world.git("rev-parse", "HEAD").stdout.strip()
    world.git("update-index", "--add", "--cacheinfo", "160000,%s,sub" % seed)
    world.git("commit", "-q", "-m", "chore: bump sub")
    sha = world.git("rev-parse", "HEAD").stdout.strip()

    def no_model(*_a):
        raise AssertionError("a pointer bump reached the model")

    path = R.run_review(world.repo, "console", sha, BRANCH, reviewer=no_model, log=lambda _m: None)
    assert R.parse(path.read_text(encoding="utf-8")).verdict == "skipped (gitlink-only)"


def test_the_same_sha_triggered_twice_starts_one_reviewer(world):
    world.env["STUB_SLEEP"] = "3"
    sha = world.commit()
    _rc, out1, _e, _t = world.hook("git commit -m x -- f.py")
    _rc, out2, _e, _t = world.hook("git commit -m x -- f.py")
    assert "started for console %s" % sha[:8] in _context(out1)
    assert "started for" not in _context(out2), "a second trigger for a live sha spawned again"
    assert world.wait_for(world.review_file(sha))
    assert world.calls.read_text().count("call") == 1


def test_two_commits_back_to_back_get_two_files_with_their_own_findings(world):
    a = world.commit("f.py")
    world.answer([{"severity": "low", "file": "g.py", "line": 1, "claim": "naming"}])
    b = world.commit("g.py", body="x = 1\n")

    def fake(sha_findings):
        def reviewer(_prompt, _cfg, _log):
            return sha_findings, ""

        return reviewer

    pa = R.run_review(
        world.repo,
        "console",
        a,
        BRANCH,
        reviewer=fake(
            {
                "verdict": "findings",
                "findings": [{"severity": "high", "file": "f.py", "line": 1, "claim": "a"}],
                "labels": {"bump": "none", "kind": [], "why": ""},
            }
        ),
        log=lambda _m: None,
    )
    pb = R.run_review(
        world.repo,
        "console",
        b,
        BRANCH,
        reviewer=fake(
            {
                "verdict": "findings",
                "findings": [{"severity": "low", "file": "g.py", "line": 1, "claim": "b"}],
                "labels": {"bump": "minor", "kind": ["feature"], "why": ""},
            }
        ),
        log=lambda _m: None,
    )
    ra, rb = R.parse(pa.read_text()), R.parse(pb.read_text())
    assert [f.file for f in ra.findings] == ["f.py"]
    assert [f.file for f in rb.findings] == ["g.py"]
    assert ra.findings[0].id.startswith(a[:8])
    assert rb.findings[0].id.startswith(b[:8])


def test_a_rebased_copy_with_the_same_patch_id_writes_nothing_and_counts_as_covered(world):
    sha = world.commit()
    world.run_child(sha)
    # Move main forward, then rebase the branch: same patch, new sha.
    world.git("checkout", "-q", "main")
    (world.repo / "other.txt").write_text("o\n", encoding="utf-8")
    world.git("add", "other.txt")
    world.git("commit", "-q", "-m", "other")
    world.git("push", "-q", "origin", "main")
    world.git("checkout", "-q", BRANCH)
    world.git("rebase", "-q", "main")
    new = world.git("rev-parse", "HEAD").stdout.strip()
    assert new != sha
    assert R.uncovered(world.repo, world.repo, BRANCH) == []
    assert R.run_review(world.repo, "console", new, BRANCH, log=lambda _m: None) is None


def test_a_commit_in_a_nested_repo_records_its_repo(world):
    sub = world.repo / "sub"
    sub.mkdir()
    world.init_repo(sub)
    sha = world.commit("f.py", repo=sub)
    rc, out, err, _t = world.hook("git -C sub commit -m x -- f.py")
    assert rc == 0, err
    assert "started for sub %s" % sha[:8] in _context(out)
    path = world.review_file(sha)
    assert world.wait_for(path)
    assert R.parse(path.read_text()).repo == "sub"


def test_a_commit_in_a_repository_outside_the_project_starts_nothing(world):
    """A scratch repository next to the project is not this branch's work; reviewing it would file a record about a commit no push of the project carries."""
    outside = world.tmp / "outside"
    outside.mkdir()
    world.init_repo(outside)
    world.commit("f.py", repo=outside)
    _rc, out, _e, _t = world.hook("git -C %s commit -m x -- f.py" % outside)
    assert "started" not in _context(out)
    time.sleep(0.5)
    assert not world.calls.exists()
    assert not (world.repo / "agent").exists()


def test_inside_a_reviewer_the_hook_does_nothing(world):
    world.commit()
    _rc, out, _e, _t = world.hook("git commit -m x -- f.py", extra_env={"COMMIT_REVIEW_CHILD": "1"})
    assert out.strip() == ""
    time.sleep(0.5)
    assert not world.calls.exists()


def test_a_reviewer_without_the_recursion_guard_records_a_failure(world):
    """Mutation control for H4: the real reviewer with `STOPHOOK_CHILD` no longer set makes the stub refuse, and the file says failed rather than nothing."""
    sha = world.commit()
    src = pathlib.Path(R.__file__).read_text(encoding="utf-8")
    planted = 'env["STOPHOOK_CHILD"] = "1"'
    assert planted in src, "the mutation no longer applies to wl_review"
    mutant = types.ModuleType("wl_review_mutant")
    mutant.__file__ = R.__file__
    sys.modules[mutant.__name__] = mutant  # dataclasses resolve annotations through sys.modules
    try:
        exec(compile(src.replace(planted, "pass"), R.__file__, "exec"), mutant.__dict__)  # noqa: S102
    finally:
        del sys.modules[mutant.__name__]
    path = R.run_review(
        world.repo, "console", sha, BRANCH, reviewer=mutant.claude_reviewer, log=lambda _m: None
    )
    review = R.parse(path.read_text())
    assert review.verdict.startswith("failed"), review.verdict
    assert review.attempt == 1


# --------------------------------------------------------------------------- 2. surfacing without the Stop hook


def test_the_next_bash_call_surfaces_a_finished_review_exactly_once(world):
    sha = world.commit()
    world.run_child(sha)
    _rc, out, _e, _t = world.hook("ls")
    text = _context(out)
    assert "review %s (console): findings, 2 open finding(s), 1 at or above high" % sha[:8] in text
    assert "[high] %s.1 f.py:2" % sha[:8] in text
    assert "--review-mark <me> %s.1 fixed" % sha[:8] in text
    _rc, out2, _e, _t = world.hook("ls")
    assert _context(out2) == "", "an unchanged review was surfaced twice"


def test_session_start_names_the_open_high_finding(world):
    sha = world.commit()
    world.run_child(sha)
    done = subprocess.run(
        [sys.executable, str(wlfix.HOOK), "--session-start"],
        input=json.dumps({"session_id": SID, "cwd": str(world.repo), "source": "startup"}),
        capture_output=True,
        text=True,
        env=world.env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    ctx = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Per-commit reviews for %s" % BRANCH in ctx
    assert "OPEN [high] %s.1 f.py:2" % sha[:8] in ctx
    assert "UNRECORDED 1 finished review file(s)" in ctx


def test_session_start_says_nothing_on_a_clean_recorded_branch(world):
    world.answer([])
    sha = world.commit()
    world.run_child(sha)
    rel = str(world.review_file(sha).relative_to(world.repo))
    world.git("add", "--", rel)
    world.git("commit", "-q", "-m", "chore(reviews): record", "--", rel)
    assert R.session_start_line(world.repo, BRANCH) == ""


# --------------------------------------------------------------------------- 3. the format and the verbs


def test_a_hand_edited_severity_or_claim_is_malformed(world):
    sha = world.commit()
    world.run_child(sha)
    text = world.review_file(sha).read_text()
    assert R.parse(text)
    with pytest.raises(R.MalformedReviewError, match="Body-Sig"):
        R.parse(text.replace("[high]", "[low]", 1))
    with pytest.raises(R.MalformedReviewError, match="Body-Sig"):
        R.parse(text.replace("returns None", "returns 0", 1))
    with pytest.raises(R.MalformedReviewError, match="Resolution"):
        R.parse(text.replace("Resolution: open", "Resolution: fixed", 1))


def test_mark_fixed_accepts_a_real_fix_and_refuses_the_rest(world):
    sha = world.commit()
    world.run_child(sha)
    fid = "%s.1" % sha[:8]
    unrelated = world.commit("other.py", body="z = 1\n")
    with pytest.raises(ValueError, match="does not touch"):
        R.mark(world.repo, BRANCH, fid, "fixed", [unrelated], "deadbeef")
    with pytest.raises(ValueError, match="reviewed commit itself"):
        R.mark(world.repo, BRANCH, fid, "fixed", [sha], "deadbeef")
    seed = world.git("rev-parse", "main").stdout.strip()
    with pytest.raises(ValueError, match="does not descend"):
        R.mark(world.repo, BRANCH, fid, "fixed", [seed], "deadbeef")
    fix = world.commit("f.py", body="a = 1\nb = 2\nc = 4\n")
    R.mark(world.repo, BRANCH, fid, "fixed", [fix], "deadbeef")
    review = R.parse(world.review_file(sha).read_text())
    assert review.findings[0].resolution.startswith("fixed %s | deadbeef " % fix)
    st = R.branch_state(world.repo, BRANCH, repos=())
    assert st["blocking"] == []


def test_mark_not_a_bug_needs_a_resolvable_citation(world):
    sha = world.commit()
    world.run_child(sha)
    fid = "%s.1" % sha[:8]
    with pytest.raises(ValueError, match="cite"):
        R.mark(
            world.repo,
            BRANCH,
            fid,
            "not-a-bug",
            ["it", "is", "fine", "honestly", "trust", "me"],
            "deadbeef",
        )
    R.mark(
        world.repo,
        BRANCH,
        fid,
        "not-a-bug",
        ["f.py:2", "returns", "a", "value", "on", "every", "path"],
        "deadbeef",
    )
    assert R.parse(world.review_file(sha).read_text()).findings[0].resolution_kind() == "not-a-bug"


def test_mark_deferred_needs_an_open_item_naming_the_finding_and_reopens_when_it_goes(world):
    sha = world.commit()
    world.run_child(sha)
    fid = "%s.1" % sha[:8]
    with pytest.raises(ValueError, match="does not exist"):
        R.mark(world.repo, BRANCH, fid, "deferred", ["#abcdef12"], "deadbeef", items={})
    with pytest.raises(ValueError, match="does not name"):
        R.mark(
            world.repo,
            BRANCH,
            fid,
            "deferred",
            ["#abcdef12"],
            "deadbeef",
            items={"abcdef12": (" ", "other work")},
        )
    R.mark(
        world.repo,
        BRANCH,
        fid,
        "deferred",
        ["#abcdef12"],
        "deadbeef",
        items={"abcdef12": (" ", "fix %s later" % fid)},
    )
    assert R.branch_state(world.repo, BRANCH, repos=(), items={"abcdef12": " "})["blocking"] == []
    reopened = R.branch_state(world.repo, BRANCH, repos=(), items={})["blocking"]
    assert [f.id for _p, f in reopened] == [fid], "a deferral whose item is gone must reopen"


def test_review_commit_records_only_finished_files_with_the_trailer(world):
    sha = world.commit(msg="fix(x): y\n\nPR-TASK: a1b2c3d4")
    world.run_child(sha)
    rc, text = R.commit_reviews(world.repo, BRANCH)
    assert rc == 0, text
    head = world.git("log", "-1", "--format=%B").stdout
    assert head.startswith("chore(reviews): record reviews for %s" % sha[:8])
    assert "PR-TASK: a1b2c3d4" in head
    files = world.git("show", "--name-only", "--format=", "HEAD").stdout.split()
    assert files == [str(world.review_file(sha).relative_to(world.repo))]
    assert R.branch_state(world.repo, BRANCH, repos=())["uncommitted"] == []


def test_validate_marks_a_line_far_from_any_hunk_outside_diff():
    diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -1,2 +40,3 @@\n+x\n"
    verdict, findings, _labels, dropped = R.validate(
        {
            "findings": [
                {"severity": "high", "file": "f.py", "line": 41, "claim": "near"},
                {"severity": "high", "file": "f.py", "line": 400, "claim": "far"},
                {"severity": "critical", "file": "f.py", "line": 1, "claim": "bad severity"},
            ]
        },
        ["f.py"],
        diff,
        "a" * 40,
    )
    assert verdict == "findings"
    assert [(f.claim, f.anchor) for f in findings] == [("near", "in-diff"), ("far", "outside-diff")]
    assert dropped == 1


def test_a_finding_about_writing_is_capped_at_low_and_code_is_not():
    """The commit policy's own `no_review_eligible` decides what is writing, so a session note or a generated ledger can never refuse a push."""
    policy = R._writing_test(pathlib.Path(__file__).resolve().parents[3])
    assert policy is not None, "the commit policy did not load from the console root"
    diff = (
        "diff --git a/agent/x/STATE.md b/agent/x/STATE.md\n+++ b/agent/x/STATE.md\n@@ -1 +1,2 @@\n+a\n"
        "diff --git a/src/a.py b/src/a.py\n+++ b/src/a.py\n@@ -1 +1,2 @@\n+b\n"
        "diff --git a/CLAUDE.md b/CLAUDE.md\n+++ b/CLAUDE.md\n@@ -1 +1,2 @@\n+c\n"
    )
    _v, findings, _l, _d = R.validate(
        {
            "findings": [
                {"severity": "high", "file": "agent/x/STATE.md", "line": 1, "claim": "stamp"},
                {"severity": "high", "file": "src/a.py", "line": 1, "claim": "crash"},
                {"severity": "high", "file": "CLAUDE.md", "line": 1, "claim": "policy"},
            ]
        },
        ["agent/x/STATE.md", "src/a.py", "CLAUDE.md"],
        diff,
        "a" * 40,
        is_writing=policy,
    )
    assert [(f.file, f.severity) for f in findings] == [
        ("agent/x/STATE.md", "low"),
        ("src/a.py", "high"),
        ("CLAUDE.md", "high"),
    ]
