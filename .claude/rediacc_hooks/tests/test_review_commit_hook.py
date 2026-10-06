"""Per-commit review: the post-bash trigger, the detached runner, the file format, the verbs and the SessionStart surfacing (agent/plans/PLAN-per-commit-review.md section 12).

Every case builds a real git repository with an `origin/main`, makes real commits, and replaces only the MODEL: a stub `claude` on PATH that answers with a canned `structured_output`. The stub refuses (exit 3) unless it runs with `STOPHOOK_CHILD=1` and a cwd OUTSIDE the repository, which is the recursion guard the plan's H4 requires, so a reviewer that lost either writes `Verdict: failed`.

Controls run beside the cases they make meaningful: the stub really sleeps (so "the hook returned in under a second" is evidence of detachment, not of a fast stub), the stub really refuses without the child env, and a hand edit really breaks the Body-Sig.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
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
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": float(os.environ.get("STUB_COST", "0.0")), "structured_output": out}))
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
        # A repo-local identity, not only the GIT_AUTHOR_* env of self.git: R.commit_reviews runs `git commit` in-process with the test runner's own environment, and a CI runner has no global identity ("Author identity unknown", run 37037695303).
        self.git("config", "user.name", "Fixture", repo=repo)
        self.git("config", "user.email", "fixture@example.invalid", repo=repo)
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

    def ledger(self):
        return R.ledger_path(self.repo, BRANCH)

    def ledger_shas(self):
        reviews, errors = R.read_ledger(self.ledger())
        assert errors == [], errors
        return [r.sha for r in reviews]

    def wait_for(self, path, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if path.exists():
                return True
            time.sleep(0.2)
        return False

    def wait_for_line(self, sha, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.ledger().exists() and sha in self.ledger_shas():
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
    assert not world.ledger().exists(), "a findings verdict wrote a ledger line"


def test_a_clean_commit_starts_a_detached_reviewer_and_its_ledger_line_lands(world):
    """PLAN-clean-review-ledger T3: a clean full-coverage verdict is one line of clean.jsonl and no `.md` file."""
    world.answer([])
    world.env["STUB_SLEEP"] = "1"
    sha = world.commit()
    rc, _out, err, took = world.hook("git commit -m 'fix(x): y' -- f.py")
    assert rc == 0, err
    assert took < 1.5, "the hook waited %.1fs: the reviewer is holding its pipes (H3)" % took
    assert world.wait_for_line(sha), "no ledger line within 20s"
    assert world.ledger_shas() == [sha]
    assert not world.review_file(sha).exists(), "a clean verdict also wrote a review file"
    (review,) = R.read_ledger(world.ledger())[0]
    assert (review.verdict, review.repo, review.branch) == ("clean", "console", BRANCH)
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
    assert path == world.ledger()
    assert world.ledger_shas() == [sha]
    assert not world.review_file(sha).exists(), "a gitlink-only verdict also wrote a review file"
    assert R.read_ledger(path)[0][0].verdict == "skipped (gitlink-only)"


def test_a_clean_retry_replaces_the_failed_file_with_a_ledger_line(world):
    """T3: a retry that comes back clean appends the line and unlinks the failed `.md`; the attempt counter carries over."""
    sha = world.commit()

    def failing(*_a):
        return None, "model unreachable"

    def clean(*_a):
        return {"verdict": "clean", "findings": [], "labels": None}, ""

    path = R.run_review(world.repo, "console", sha, BRANCH, reviewer=failing, log=lambda _m: None)
    assert path == world.review_file(sha)
    assert R.parse(path.read_text()).verdict.startswith("failed")
    assert R.run_review(
        world.repo, "console", sha, BRANCH, reviewer=clean, log=lambda _m: None
    ) == (world.ledger())
    assert not world.review_file(sha).exists(), "the failed record survived a clean retry"
    (review,) = R.read_ledger(world.ledger())[0]
    assert (review.sha, review.verdict, review.attempt) == (sha, "clean", 2)


def test_a_clean_result_never_unlinks_a_findings_file(world):
    """T3: a findings `.md` is the stricter state, so a later clean verdict rewrites the file and writes no line."""
    sha = world.commit()
    world.run_child(sha)
    assert R.parse(world.review_file(sha).read_text()).verdict == "findings"

    def clean(*_a):
        return {"verdict": "clean", "findings": [], "labels": None}, ""

    path = R.run_review(world.repo, "console", sha, BRANCH, reviewer=clean, log=lambda _m: None)
    assert path == world.review_file(sha)
    assert R.parse(path.read_text()).verdict == "clean"
    assert not world.ledger().exists()


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


def test_a_record_carries_the_review_models_cost(world):
    """Operator 2026-10-03: every record names what its review cost. The stub reports total_cost_usd; the record's Cost line carries it with the call count and duration."""
    world.env["STUB_COST"] = "0.0696275"
    sha = world.commit()
    world.run_child(sha)
    text = world.review_file(sha).read_text()
    line = next(ln for ln in text.splitlines() if ln.startswith("Cost: "))
    assert re.match(r"^Cost: \$0\.0696 USD, 1 call\(s\), \d+\.\ds$", line), line
    assert R.parse(text).cost["usd"] == 0.0696


def test_a_skipped_commit_records_no_cost():
    review = R.Review(sha="a" * 40, subject="s", verdict="skipped (gitlink-only)", model="(none)")
    text = R.render(review)
    assert "\nCost: (none)\n" in text
    assert R.parse(text).cost is None


def test_a_record_written_before_the_cost_line_still_parses():
    """112 records on 0930-1 (now on main) predate the Cost header; they stay readable."""
    review = R.Review(sha="b" * 40, subject="s", cost={"usd": 0.01, "calls": 1, "seconds": 2.0})
    text = R.render(review)
    old = "\n".join(ln for ln in text.splitlines() if not ln.startswith("Cost: ")) + "\n"
    assert R.parse(old).cost is None
    assert R.parse(text).cost == {"usd": 0.01, "calls": 1, "seconds": 2.0}


def test_a_malformed_cost_line_is_refused():
    text = R.render(R.Review(sha="c" * 40, subject="s"))
    with pytest.raises(R.MalformedReviewError, match="Cost:"):
        R.parse(text.replace("Cost: (none)", "Cost: about a dime"))


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


def test_check_without_a_repo_judges_the_submodule_reviews_too(world):
    """`wl_review.py --check` passes no repo and must judge every repository a review names: scoped to the console it printed "clean" while a submodule commit's review was unsettled, which the push guard then refused (renet 3ca4821f, 2026-10-02)."""
    world.answer([])  # a clean review, so only coverage can make the branch unclean
    sub = world.repo / "sub"
    sub.mkdir()
    world.init_repo(sub)
    sha = world.commit("f.py", repo=sub)
    rc, _out, err, _t = world.hook("git -C sub commit -m x -- f.py")
    assert rc == 0, err
    assert world.wait_for_line(sha)
    rc, text = R.commit_reviews(world.repo, BRANCH)
    assert rc == 0, text
    world.commit("g.py", repo=sub)  # a second submodule commit, never reviewed
    reasons, lines = R.check_state(world.repo, BRANCH, label=None)
    assert reasons, "an unreviewed submodule commit read as clean: %r" % (lines,)
    assert any("sub" in line for line in lines), lines
    scoped, _l = R.check_state(world.repo, BRANCH, label="console")
    assert scoped == [], "CONTROL: scoped to the console the submodule is not walked: %r" % (
        scoped,
    )


def test_a_commit_behind_an_unresolvable_dash_c_still_starts_its_review(world):
    """#51e1c0cf: `git -C <dir>/$r commit` (a loop variable) is a path the lexer cannot expand; the commit's repository must still be reviewed, not skipped."""
    sub = world.repo / "sub"
    sub.mkdir()
    world.init_repo(sub)
    sha = world.commit("f.py", repo=sub)
    rc, out, err, _t = world.hook('for r in sub; do git -C "$r" commit -m x -- f.py; done')
    assert rc == 0, err
    assert "started for sub %s" % sha[:8] in _context(out)
    assert world.wait_for(world.review_file(sha))


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


def test_fresh_ledger_lines_share_one_surfaced_line_and_each_surfaces_once(world):
    """T8: every fresh clean entry is named on ONE line, and a later append surfaces only the new sha (seen is keyed per `clean.jsonl:<sha>`, not by the ledger's mtime)."""
    world.answer([])
    first = world.commit()
    world.run_child(first)
    _rc, out, _e, _t = world.hook("ls")
    text = _context(out)
    assert (
        "1 clean review(s) appended to agent/reviews/%s/clean.jsonl: %s"
        % (
            BRANCH,
            first[:8],
        )
        in text
    ), text
    assert "review %s" % first[:8] not in text, "a clean entry got a per-record line"
    _rc, out2, _e, _t = world.hook("ls")
    assert _context(out2) == "", "an unchanged ledger was surfaced twice"
    second = world.commit("g.py", body="x = 1\n")
    world.run_child(second)
    _rc, out3, _e, _t = world.hook("ls")
    text3 = _context(out3)
    assert "1 clean review(s) appended" in text3, text3
    assert second[:8] in text3, text3
    assert first[:8] not in text3, "the earlier ledger line was surfaced again"


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
    assert world.ledger_shas() == [sha]
    rel = str(world.ledger().relative_to(world.repo))
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


def test_mark_fixed_accepts_a_fix_on_a_rebased_copy_of_the_reviewed_commit(world):
    """2026-10-06: 1006-2 was rebased onto a new main, so the reviewed commit e2a16724 became a copy with a new sha and the same patch-id, and the fix on top of it was refused as "does not descend". The descent check now follows the patch-id to the copy."""
    sha = world.commit()
    world.run_child(sha)
    fid = "%s.1" % sha[:8]
    world.git("checkout", "-q", "main")
    world.commit("unrelated_on_main.py", body="m = 1\n", msg="chore(main): move main")
    world.git("checkout", "-q", BRANCH)
    world.git("rebase", "-q", "main")
    copy = world.git("rev-parse", "HEAD").stdout.strip()
    assert copy != sha, "the rebase must rewrite the reviewed commit"
    assert world.git("merge-base", "--is-ancestor", sha, copy, check=False).returncode != 0
    fix = world.commit("f.py", body="a = 1\nb = 2\nc = 4\n")
    R.mark(world.repo, BRANCH, fid, "fixed", [fix], "deadbeef")
    review = R.parse(world.review_file(sha).read_text())
    assert review.findings[0].resolution.startswith("fixed %s | deadbeef " % fix)


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
    # T6: a failed record committed after its second failure, then a clean retry: one --review-commit records the ledger line AND the deletion (`git add -A`).
    world.answer([])
    second = world.commit("g.py", body="x = 1\n", msg="fix(x): z\n\nPR-TASK: a1b2c3d4")

    def failing(*_a):
        return None, "model unreachable"

    for _ in range(2):
        R.run_review(world.repo, "console", second, BRANCH, reviewer=failing, log=lambda _m: None)
    rc, text = R.commit_reviews(world.repo, BRANCH)
    assert rc == 0, text
    failed_rel = str(world.review_file(second).relative_to(world.repo))
    assert world.git("ls-files", "--", failed_rel).stdout.strip() == failed_rel
    world.run_child(second)
    assert not world.review_file(second).exists()
    st = R.branch_state(world.repo, BRANCH, repos=())
    assert sorted(p.name for p in R.recordable(st)) == sorted(
        [R.LEDGER_NAME, world.review_file(second).name]
    )
    rc, text = R.commit_reviews(world.repo, BRANCH)
    assert rc == 0, text
    head = world.git("log", "-1", "--format=%B").stdout
    assert head.startswith("chore(reviews): record reviews for %s" % second[:8]), head
    assert "PR-TASK: a1b2c3d4" in head
    status = world.git("show", "--name-status", "--format=", "HEAD").stdout.split("\n")
    assert sorted(ln for ln in status if ln) == sorted(
        ["A\t" + str(world.ledger().relative_to(world.repo)), "D\t" + failed_rel]
    ), status
    assert world.git("status", "--porcelain", "--", "agent").stdout == ""
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


# ---- T5 of PLAN-per-commit-review: `worklist.py --prune-reviews <me> [--write]` is a thin arm over the archival gate's own pruning, so the retention rule lives in one place.

FAKE_GATE = r"""#!/usr/bin/env python3
import json, os, sys
print("FAKE-GATE " + json.dumps(sys.argv[1:]) + " cwd=" + os.path.realpath(os.getcwd()))
sys.exit(int(os.environ.get("FAKE_GATE_RC", "3")))
"""


def _fake_root(tmp_path):
    root = tmp_path / "fakeroot"
    gate = root / ".ci" / "scripts" / "quality" / "check_agent_session_archival.py"
    gate.parent.mkdir(parents=True)
    gate.write_text(FAKE_GATE, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    ("args", "argv"),
    [([], ["--prune-reviews"]), (["--write"], ["--prune-reviews", "--write"])],
)
def test_prune_reviews_reaches_the_archival_gate_and_returns_its_rc_and_output(
    tmp_path, args, argv
):
    root = _fake_root(tmp_path)
    rc, text = R.verb("--prune-reviews", "deadbeef", args, root, dict, branch=BRANCH)
    assert rc == 3, text
    assert "FAKE-GATE " + json.dumps(argv) in text
    assert "cwd=" + os.path.realpath(root) in text


def test_control_prune_reviews_passes_a_clean_gate_through_as_rc_0(tmp_path, monkeypatch):
    root = _fake_root(tmp_path)
    monkeypatch.setenv("FAKE_GATE_RC", "0")
    rc, text = R.verb("--prune-reviews", "deadbeef", [], root, dict, branch=BRANCH)
    assert (rc, "FAKE-GATE" in text) == (0, True), text


def test_prune_reviews_refuses_an_unknown_argument_without_running_the_gate(tmp_path):
    root = _fake_root(tmp_path)
    rc, text = R.verb("--prune-reviews", "deadbeef", ["--force"], root, dict, branch=BRANCH)
    assert rc == 2, text
    assert "FAKE-GATE" not in text, text
    assert "--prune-reviews" in text, text


def test_worklist_dispatches_prune_reviews_to_the_review_arm(tmp_path):
    """The dispatcher tuple names the verb: a bad prefix is refused by the review arm's own check, not by the unknown-verb refusal."""
    script = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop" / "worklist.py"
    res = subprocess.run(
        [sys.executable, str(script), "--prune-reviews", "NOT-A-PREFIX!"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        cwd=tmp_path,
        timeout=60,
        check=False,
    )
    assert res.returncode == 2
    assert "bad prefix" in res.stderr, res.stderr
    assert "unknown verb" not in res.stderr, res.stderr


# --------------------------------------------------------------------------- 4. the clean ledger (agent/plans/PLAN-clean-review-ledger.md)


def _eligible(verdict="clean", sha="a" * 40, **kw):
    fields = {
        "sha": sha,
        "subject": "fix(x): y — été",
        "branch": BRANCH,
        "parent": "b" * 40,
        "patch_id": ("c" * 39) + sha[0],
        "reviewed_at": "2026-10-04T08:00:00Z",
        "model": "m" if verdict == "clean" else "(none)",
        "diff_bytes": 4210,
        "diff_files": 3,
        "verdict": verdict,
        "labels": {"bump": "minor", "kind": ["feature", "ci"], "why": "adds a verb"}
        if verdict == "clean"
        else None,
        "cost": {"usd": 0.0123, "calls": 1, "seconds": 12.3} if verdict == "clean" else None,
    }
    fields.update(kw)
    return R.Review(**fields)


@pytest.mark.parametrize("verdict", R.LEDGER_VERDICTS)
def test_the_ledger_codec_round_trips_every_eligible_verdict(verdict):
    """T2: the line `ledger_line` writes parses back, through the strict reader, to the same review the `.md` file would."""
    review = _eligible(verdict)
    line = R.ledger_line(review)
    assert line.endswith("\n")
    assert line.count("\n") == 1
    doc = json.loads(line)
    assert list(doc) == sorted(doc), "keys are not sorted"
    assert '", "' not in line, "separators carry spaces"
    assert '": ' not in line, "separators carry spaces"
    back, errors = R.parse_ledger(line)
    assert errors == []
    via_md = R.parse(R.render(review))
    assert back == [via_md], "the ledger and the .md read back differently"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("truncated", True),
        ("unreviewed", ["big.json"]),
        ("dropped", 1),
        (
            "findings",
            [
                R.Finding(
                    id="aaaaaaaa.1", severity="low", file="f", line=1, anchor="in-diff", claim="c"
                )
            ],
        ),
        ("verdict", "failed (model call timed out after 240s)"),
        ("verdict", "findings"),
    ],
)
def test_each_d1_exclusion_is_refused(field, value):
    review = _eligible(**{field: value})
    assert not R.ledger_eligible(review)
    with pytest.raises(ValueError, match="not ledger-eligible"):
        R.ledger_line(review)


def test_control_the_eligible_review_is_accepted():
    """CONTROL: the base review of the exclusion cases is eligible, so each refusal above is the changed field's doing."""
    assert R.ledger_eligible(_eligible())


@pytest.mark.parametrize(
    ("mutate", "words"),
    [
        (lambda d: d.update(extra=1), "unknown key"),
        (lambda d: d.pop("patch_id"), "missing key"),
        (lambda d: d.update(truncated=False), "only a `<sha40>.md`"),
        (lambda d: d.update(findings=[]), "only a `<sha40>.md`"),
        (lambda d: d.update(verdict="findings"), "verdict"),
        (lambda d: d.update(sha="abc"), "sha is not 40 hex"),
        (lambda d: d.update(labels={"bump": "huge", "kind": [], "why": ""}), "labels"),
        (lambda d: d.update(attempt=0), "attempt"),
    ],
)
def test_a_bad_ledger_line_is_malformed_with_its_line_number(mutate, words):
    good = R.ledger_line(_eligible(sha="1" * 40))
    doc = json.loads(R.ledger_line(_eligible(sha="2" * 40)))
    mutate(doc)
    text = good + json.dumps(doc, sort_keys=True) + "\n"
    reviews, errors = R.parse_ledger(text)
    assert [r.sha for r in reviews] == ["1" * 40]
    assert len(errors) == 1, errors
    assert errors[0].line == 2, errors
    assert words in str(errors[0]), errors[0]


def test_garbage_and_a_blank_line_are_malformed_and_a_duplicate_sha_is_not():
    good = R.ledger_line(_eligible(sha="1" * 40))
    reviews, errors = R.parse_ledger(good + "{not json\n" + "\n" + good)
    assert [r.sha for r in reviews] == ["1" * 40]
    assert [(e.line, "not JSON" in str(e) or "empty line" in str(e)) for e in errors] == [
        (2, True),
        (3, True),
    ]


def test_append_clean_writes_once_per_sha(tmp_path):
    review = _eligible()
    assert R.append_clean(tmp_path, BRANCH, review) is True
    assert R.append_clean(tmp_path, BRANCH, review) is False
    path = R.ledger_path(tmp_path, BRANCH)
    assert path.read_text(encoding="utf-8") == R.ledger_line(review)


APPENDER = r"""
import os, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
if sys.argv[5] != "-":
    import types
    src = pathlib.Path(sys.argv[1], "wl_review.py").read_text(encoding="utf-8")
    for old, new in __import__("json").loads(pathlib.Path(sys.argv[5]).read_text()):
        assert old in src, old
        src = src.replace(old, new)
    R = types.ModuleType("wl_review")
    R.__file__ = str(pathlib.Path(sys.argv[1], "wl_review.py"))
    sys.modules["wl_review"] = R
    exec(compile(src, R.__file__, "exec"), R.__dict__)
else:
    import wl_review as R
root, tag, go = sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4])
while not go.exists():
    time.sleep(0.001)
for n in range(50):
    review = R.Review(sha="%s%039x" % (tag, n), subject="s" * 400, branch="0930-1", verdict="clean", model="m", reviewed_at="2026-10-04T08:00:00Z")
    R.append_clean(root, "0930-1", review)
R.append_clean(root, "0930-1", R.Review(sha="%s%039x" % (tag, 0), subject="dup", branch="0930-1", verdict="clean", model="m"))
"""

# The T4 control: the single write split in two (key half, value half) with a yield between them, and the lock gone.
TEAR = [
    ["fcntl.flock(fd, fcntl.LOCK_EX)", "pass"],
    ["fcntl.flock(fd, fcntl.LOCK_UN)", "pass"],
    [
        "            os.write(fd, data)\n",
        "            os.write(fd, data[: len(data) // 2])\n            time.sleep(0.0005)\n            os.write(fd, data[len(data) // 2 :])\n",
    ],
]


def _race(tmp_path, mutation):
    stop_dir = str(pathlib.Path(R.__file__).parent)
    go = tmp_path / "go"
    script = tmp_path / "appender.py"
    script.write_text(APPENDER, encoding="utf-8")
    plan = "-"
    if mutation:
        plan = str(tmp_path / "mutation.json")
        pathlib.Path(plan).write_text(json.dumps(mutation), encoding="utf-8")
    procs = [
        subprocess.Popen(
            [sys.executable, str(script), stop_dir, str(tmp_path), tag, str(go), plan],
            stderr=subprocess.PIPE,
            text=True,
        )
        for tag in ("a", "b")
    ]
    time.sleep(0.5)
    go.write_text("go", encoding="utf-8")
    for proc in procs:
        _out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err
    return R.ledger_path(tmp_path, BRANCH).read_text(encoding="utf-8")


def test_two_processes_appending_fifty_lines_each_tear_nothing(tmp_path):
    """T4: two writers, one ledger: 100 parseable lines, no torn line, and the re-append of an existing sha writes nothing."""
    text = _race(tmp_path, None)
    reviews, errors = R.parse_ledger(text)
    assert errors == [], errors[:3]
    assert len(reviews) == 100
    assert text.count("\n") == 100, "a duplicate sha was written"


def test_control_a_split_write_without_the_lock_tears_a_line(tmp_path):
    """CONTROL for T4: with the lock removed and the write split, the same race produces a line that does not parse, so the case above can fail."""
    text = _race(tmp_path, TEAR)
    _reviews, errors = R.parse_ledger(text)
    assert errors, (
        "the unlocked split write tore nothing in 100 appends: the race case proves nothing"
    )


# ---- T13: `wl_review.py --ledger-migrate [--write]`


def _fixture_tree(root):
    """One directory holding every record kind D1 sorts: clean, gitlink, truncated-clean, dropped-clean, findings, failed."""
    d = R.branch_dir(root, BRANCH)
    d.mkdir(parents=True)
    kinds = {
        "1" * 40: _eligible(sha="1" * 40),
        "2" * 40: _eligible("skipped (gitlink-only)", sha="2" * 40, diff_bytes=0, diff_files=0),
        "3" * 40: _eligible(sha="3" * 40, truncated=True, unreviewed=["big.json"]),
        "4" * 40: _eligible(sha="4" * 40, dropped=1),
        "5" * 40: _eligible(
            sha="5" * 40,
            verdict="findings",
            findings=[
                R.Finding(
                    id="55555555.1", severity="high", file="f", line=1, anchor="in-diff", claim="c"
                )
            ],
        ),
        "6" * 40: _eligible(sha="6" * 40, verdict="failed (queue timeout)", labels=None),
        "7" * 40: _eligible(
            sha="7" * 40, cost=None, labels={"bump": "none", "kind": [], "why": ""}
        ),
    }
    for sha, review in kinds.items():
        (d / ("%s.md" % sha)).write_text(R.render(review), encoding="utf-8")
    return d


def _tree_bytes(root):
    top = root / R.REVIEWS_REL
    return {str(p.relative_to(top)): p.read_bytes() for p in sorted(top.rglob("*")) if p.is_file()}


def test_ledger_migrate_dry_run_changes_nothing(tmp_path):
    _fixture_tree(tmp_path)
    before = _tree_bytes(tmp_path)
    out: list[str] = []
    assert R.ledger_migrate(tmp_path, write=False, log=out.append) == 0
    assert _tree_bytes(tmp_path) == before
    assert any("3 line(s) to append, 3 file(s) to delete, 4 .md kept" in line for line in out), out


def test_ledger_migrate_write_converts_exactly_the_eligible_records_and_reruns_as_a_no_op(tmp_path):
    d = _fixture_tree(tmp_path)
    before = R.migration_snapshot(tmp_path)
    assert R.ledger_migrate(tmp_path, write=True, log=lambda _m: None) == 0
    assert sorted(p.stem[0] for p in d.glob("*.md")) == ["3", "4", "5", "6"]
    assert sorted(r.sha[0] for r in R.read_ledger(d / R.LEDGER_NAME)[0]) == ["1", "2", "7"]
    assert R.migration_snapshot(tmp_path) == before
    after_first = _tree_bytes(tmp_path)
    out: list[str] = []
    assert R.ledger_migrate(tmp_path, write=True, log=out.append) == 0
    assert _tree_bytes(tmp_path) == after_first, "a second run changed the tree"
    assert any("total: 0 line(s)" in line for line in out), out


def test_ledger_migrate_restores_every_file_on_a_snapshot_mismatch(tmp_path):
    _fixture_tree(tmp_path)
    before = _tree_bytes(tmp_path)
    calls = []

    def lying_snapshot(root):
        calls.append(root)
        return {"call": len(calls)}

    out: list[str] = []
    assert R.ledger_migrate(tmp_path, write=True, snapshot=lying_snapshot, log=out.append) == 1
    assert len(calls) == 2
    assert _tree_bytes(tmp_path) == before, "a refused migration left the tree changed"
    assert any("every file was restored" in line for line in out), out


def test_ledger_migrate_refuses_a_codec_that_drops_the_labels_why(tmp_path):
    """The round-trip comparison is what refuses a lossy codec, before anything is written."""
    _fixture_tree(tmp_path)
    before = _tree_bytes(tmp_path)

    def lossy(review):
        doc = json.loads(R.ledger_line(review))
        if doc["labels"]:
            doc["labels"]["why"] = "-"
        return json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n"

    out: list[str] = []
    assert R.ledger_migrate(tmp_path, write=True, codec=lossy, log=out.append) == 1
    assert any("round-trip mismatch on labels" in line for line in out), out
    assert _tree_bytes(tmp_path) == before
