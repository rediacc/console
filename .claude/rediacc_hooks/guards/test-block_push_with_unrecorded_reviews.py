#!/usr/bin/env python3
"""Control harness for block_push_with_unrecorded_reviews.

Each case is a REAL repository with an `origin/main` and a branch, in a state the guard has to judge: an unreviewed commit, a review that is not committed, an open high finding, a hand-edited record, a reviewer in flight, a review that failed once and twice, and the clean branch the guard must let through. The guard runs through dispatch.py exactly as settings.json runs it. The model is never called: review files are written by `wl_review.run_review` with
an in-process fake reviewer, and the hand edit is a byte change of the kind `block_review_file_edit` exists to refuse.

Then the guard's DEFECT is planted in-process and the refusal cases MUST fail, which is the proof they can.

    test-block_push_with_unrecorded_reviews.py
"""

import importlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import typing

HERE = pathlib.Path(__file__).resolve()
DISPATCH = str(HERE.parents[1] / "dispatch.py")
STEM = "block_push_with_unrecorded_reviews"
STOP_DIR = HERE.parents[2] / "hooks" / "stop"
# The canonical sys.path hop, through rediacc_hooks/syspath.py loaded by file (the pattern test-block_commit_on_main.py uses).
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parent.parent / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
BRANCH = "0930-1"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _load_reviewer():
    _syspath.on_sys_path(str(STOP_DIR))
    return importlib.import_module("wl_review")


def git(repo, *args):
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=dict(os.environ, **GIT_ENV),
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit("fixture git %s failed: %s" % (" ".join(args), done.stderr))
    return done.stdout.strip()


def make_repo(base, name):
    repo = base / name
    origin = base / (name + "-origin.git")
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "--bare", str(origin)], check=True, env=dict(os.environ, **GIT_ENV)
    )
    git(repo, "init", "-q", "--initial-branch=main")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    git(repo, "add", "seed.txt")
    git(repo, "commit", "-q", "-m", "seed")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", BRANCH)
    (repo / "f.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    git(repo, "add", "f.py")
    git(repo, "commit", "-q", "-m", "fix(x): y")
    return repo, git(repo, "rev-parse", "HEAD")


def fake(findings, verdict=None):
    def reviewer(_prompt, _cfg, _log):
        if verdict == "fail":
            return None, "model unreachable"
        return {
            "verdict": "findings" if findings else "clean",
            "findings": findings,
            "labels": {"bump": "patch", "kind": ["bug"], "why": "x"},
        }, ""

    return reviewer


HIGH = [{"severity": "high", "file": "f.py", "line": 1, "claim": "breaks on the empty path"}]
LOW = [{"severity": "low", "file": "f.py", "line": 1, "claim": "naming"}]


def record(rv, repo, sha):
    path = rv.review_path(repo, BRANCH, sha)
    rel = str(path.relative_to(repo))
    git(repo, "add", "--", rel)
    git(repo, "commit", "-q", "-m", "chore(reviews): record", "--", rel)


def world_unreviewed(_rv, _repo, _sha):
    return None


def world_unrecorded(rv, repo, sha):
    rv.run_review(repo, "console", sha, BRANCH, reviewer=fake(LOW), log=lambda _m: None)


def world_clean(rv, repo, sha):
    rv.run_review(repo, "console", sha, BRANCH, reviewer=fake(LOW), log=lambda _m: None)
    record(rv, repo, sha)


def world_high(rv, repo, sha):
    rv.run_review(repo, "console", sha, BRANCH, reviewer=fake(HIGH), log=lambda _m: None)
    record(rv, repo, sha)


def world_high_fixed(rv, repo, sha):
    world_high(rv, repo, sha)
    (repo / "f.py").write_text("a = 1\nb = 3\n", encoding="utf-8")
    git(repo, "add", "f.py")
    git(repo, "commit", "-q", "-m", "fix(x): the empty path [no-review]")
    fix = git(repo, "rev-parse", "HEAD")
    rv.run_review(repo, "console", fix, BRANCH, reviewer=fake([]), log=lambda _m: None)
    rv.mark(repo, BRANCH, "%s.1" % sha[:8], "fixed", [fix], "deadbeef")
    rels = [str(p.relative_to(repo)) for p in rv.branch_dir(repo, BRANCH).glob("*.md")]
    git(repo, "add", "--", *rels)
    git(repo, "commit", "-q", "-m", "chore(reviews): record", "--", *rels)


def world_hand_edited(rv, repo, sha):
    world_high(rv, repo, sha)
    path = rv.review_path(repo, BRANCH, sha)
    path.write_text(path.read_text(encoding="utf-8").replace("[high]", "[low]"), encoding="utf-8")
    record(rv, repo, sha)


def world_in_flight(rv, _repo, sha):
    # A live process whose command line names the reviewer holds the sha's lock.
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "wl_review"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    rv.acquire_lock(sha, BRANCH, pid=proc.pid)
    return proc


def world_outside(_rv, repo, _sha):
    """A second, unreviewed repository next to the project (not inside it): its push is not this branch's."""
    make_repo(repo.parent, "outside")


def world_failed_once(rv, repo, sha):
    rv.run_review(repo, "console", sha, BRANCH, reviewer=fake([], "fail"), log=lambda _m: None)


def world_failed_twice(rv, repo, sha):
    world_failed_once(rv, repo, sha)
    rv.run_review(repo, "console", sha, BRANCH, reviewer=fake([], "fail"), log=lambda _m: None)
    record(rv, repo, sha)


CASES = [
    # (name, world, command, expected substring in the refusal, or None when allowed)
    ("an unreviewed commit", world_unreviewed, "git push", "UNREVIEWED console"),
    ("a finished review not committed", world_unrecorded, "git push origin 0930-1", "UNRECORDED 1"),
    ("an open high finding", world_high, "git push", "--review-mark <me>"),
    ("a hand-edited record", world_hand_edited, "git push", "MALFORMED"),
    ("a reviewer in flight", world_in_flight, "git push", "IN FLIGHT console"),
    ("a review that failed once", world_failed_once, "git push", "FAILED console"),
    ("reviewed, recorded, clear", world_clean, "git push", None),
    ("a high finding marked fixed", world_high_fixed, "git push", None),
    ("a review that failed twice no longer blocks", world_failed_twice, "git push", None),
    ("a dry run publishes nothing", world_unreviewed, "git push --dry-run", None),
    ("a delete-only push", world_unreviewed, "git push origin --delete old", None),
    ("prose naming a push", world_unreviewed, "echo 'git push later'", None),
    ("not a push", world_unreviewed, "git status", None),
    ("a push of a repository outside the project", world_outside, "git -C {outside} push", None),
]


def payload(repo, cmd):
    return json.dumps({"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": cmd}})


def via_dispatch(repo, cmd):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
    p = subprocess.run(
        [sys.executable, DISPATCH, STEM],
        input=payload(repo, cmd),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
    )
    return p.returncode, p.stdout + p.stderr


def defect_runner():
    _syspath.on_sys_path(str(HERE.parents[2]))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards." + STEM)
    old, new = good.DEFECT
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if old not in src:
        raise SystemExit("the DEFECT no longer applies to the guard")
    ns: dict[str, typing.Any] = {"__name__": "broken_" + STEM, "__file__": good.__file__}
    exec(compile(src.replace(old, new), str(good.__file__), "exec"), ns)  # noqa: S102

    def run(repo, cmd):
        event = hookio.Event(
            payload(repo, cmd), cwd=str(repo), env={"CLAUDE_PROJECT_DIR": str(repo)}
        )
        rc = ns["run"](event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def run_all(base, rv, runner, quiet=False):
    fails = 0
    for n, (name, world, cmd, want) in enumerate(CASES):
        case_dir = base / ("case%02d" % n)
        case_dir.mkdir()
        repo, sha = make_repo(case_dir, "repo")
        held = world(rv, repo, sha)
        try:
            rc, text = runner(repo, cmd.replace("{outside}", str(case_dir / "outside")))
        finally:
            if isinstance(held, subprocess.Popen):
                held.kill()
                held.wait()
                rv.release_lock(sha)
        blocked = rc != 0
        ok = (not blocked) if want is None else (blocked and want in text)
        fails += not ok
        if not quiet:
            print(
                "%-46s want=%-8s %s"
                % (
                    name,
                    "allowed" if want is None else "BLOCKED",
                    "ok" if ok else "*** FAIL *** " + text[:300],
                )
            )
    return fails


def main():
    scratch = tempfile.mkdtemp(prefix="push-reviews-")
    old_tmp = os.environ.get("TMPDIR")
    try:
        # The reviewer's locks, slots and logs live under TMPDIR; give the whole run its own, removed afterwards.
        os.environ["TMPDIR"] = os.path.join(scratch, "tmp")
        os.makedirs(os.environ["TMPDIR"])
        rv = _load_reviewer()
        real = pathlib.Path(scratch, "real")
        real.mkdir()
        fails = run_all(real, rv, via_dispatch)
        refusals = sum(1 for c in CASES if c[3] is not None)
        print("%d refusal case(s), %d allow case(s)" % (refusals, len(CASES) - refusals))
        planted_dir = pathlib.Path(scratch, "planted")
        planted_dir.mkdir()
        planted = run_all(planted_dir, rv, defect_runner(), quiet=True)
        print(
            "DEFECT planted: %d case(s) fail%s"
            % (planted, "" if planted else "  *** the suite cannot fail ***")
        )
        fails += planted == 0
    finally:
        if old_tmp is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = old_tmp
        shutil.rmtree(scratch, ignore_errors=True)
    print("FAILURES: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
