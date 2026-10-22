#!/usr/bin/env python3
"""Controls for the Stop hook's fix-in-flight stand-down (`wl_ci.fix_in_flight`, the `fixing` ci_trouble state).

    python3 .claude/hooks/stop/test-ci-fixing.py

Auto-discovered by TAILED in test_hooks_delegates.py (glob over test-*.py here).

THE DEFECT (operator, 2026-10-22). PR #601 run 39685278337 was red on 997fcb58. The fix sat committed locally on top of it, and ci:quick plus the slow gates were running in the background to admit the push. The hook still said "CI IS RED ... AND NOTHING IS WATCHING IT" on two stops. The push pipeline was watching it: its push re-runs every failing job.

The stand-down needs three local facts at once, and each control below removes one of them and shows that the red then blocks:
the pushed head is a strict ancestor of HEAD on the PR branch, an unpushed commit changes a non-paperwork path, and a running background task's command is a push pipeline. A live run never stands down.
"""

import atexit
import importlib.util
import os
import pathlib
import shutil
import subprocess
import tempfile

import wl_ci as W

_SCRATCH = tempfile.mkdtemp(prefix="ci-fixing-")
atexit.register(shutil.rmtree, _SCRATCH, True)
os.environ["XDG_CACHE_HOME"] = _SCRATCH

_CI = pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci"
spec = importlib.util.spec_from_file_location("controls", _CI / "controls.py")
if spec is None or spec.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/controls.py is missing" % __file__)
controls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls)
T = controls.Controls("ci-fixing", floor=12)
check = T.check

BRANCH = "1020-1"
PIPELINE = [{"id": "bza6uy3ls", "command": "npm run ci:quick > /tmp/ciq.txt 2>&1"}]


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t")
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    r = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True, env=env
    )
    if r.returncode != 0:
        raise SystemExit("git %s: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def commit(repo, path, body="x"):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body + "\n")
    git(repo, "add", "--", path)
    git(repo, "commit", "-q", "-m", "c " + path)
    return git(repo, "rev-parse", "HEAD")


N = [0]


def repo_with(*unpushed, branch=BRANCH, root="red"):
    """A repo on `branch` whose red head is its first commit; each path in `unpushed` is one more commit on top. Returns (repo, tip)."""
    N[0] += 1
    repo = pathlib.Path(_SCRATCH) / ("r%d" % N[0])
    repo.mkdir()
    git(repo, "init", "-q", "-b", branch)
    tip = commit(repo, "packages/cli/src/a.ts", root)
    for path in unpushed:
        commit(repo, path, path)
    return repo, tip


# ---- 1. the PR #601 shape: a code fix on top of the red head, ci:quick running ----------------------
repo, tip = repo_with("packages/cli/src/a.ts", "agent/ledgers/turbo-push-reasons.jsonl")
got = W.fix_in_flight(repo, BRANCH, tip, PIPELINE)
check("the #601 shape stands down", bool(got), True)
check("... counting both unpushed commits", (got or {}).get("commits"), 2)
check("... but only the code path as a fix", (got or {}).get("files"), 1)
check("... naming the pipeline task", (got or {}).get("task"), "bza6uy3ls")

# ---- 2. each fact removed, one at a time ------------------------------------------------------------
repo0, tip0 = repo_with()
check(
    "control: no unpushed commit (HEAD is the red head)",
    W.fix_in_flight(repo0, BRANCH, tip0, PIPELINE),
    None,
)
repo, tip = repo_with("agent/d778be9d/STATE.md", "agent/ledgers/turbo-push-reasons.jsonl")
check("control: paperwork only is not a fix", W.fix_in_flight(repo, BRANCH, tip, PIPELINE), None)
repo, tip = repo_with("packages/cli/src/a.ts")
check("control: no background task", W.fix_in_flight(repo, BRANCH, tip, []), None)
check(
    "control: a waiter that only greps a gate log is not a pipeline",
    W.fix_in_flight(
        repo, BRANCH, tip, [{"id": "w", "command": "grep -q check:ci-proxy-image-smoke= out"}]
    ),
    None,
)
check(
    "control: the pipeline named only in a description does not count",
    W.fix_in_flight(
        repo,
        BRANCH,
        tip,
        [{"id": "d", "command": "tail -f gates.log", "description": "npm run ci:quick"}],
    ),
    None,
)
check("control: another branch checked out", W.fix_in_flight(repo, "other", tip, PIPELINE), None)
# The pushed head EXISTS here but is not under HEAD (a rebase, or another session's push): the local commits are not on top of the red.
repo2, root2 = repo_with("packages/cli/src/b.ts")
diverged = git(repo2, "commit-tree", root2 + "^{tree}", "-p", root2, "-m", "diverged")
check(
    "control: a present but diverged red head",
    W.fix_in_flight(repo2, BRANCH, diverged, PIPELINE),
    None,
)

# ---- 3. the other pipeline shapes count -------------------------------------------------------------
for cmd in (
    "npx tsx scripts/ci-runner/run.ts --only check:ci-security-audit",
    "TURBO_PUSH_REASON='red-fix: x' git push origin 1020-1",
    "npm run vm:check -- --changed",
    "cd /x && npm run ci:quick",
    "TURBO_PUSH_REASON='red-fix: a b' git push origin 1020-1",
):
    check(
        "pipeline: %s" % cmd.split()[0][:30],
        bool(W.fix_in_flight(repo, BRANCH, tip, [{"id": "p", "command": cmd}])),
        True,
    )

# ---- 3b. readers and other branches are not this fix's pipeline ------------------------------------
for cmd in (
    "tail -50 scripts/ci-runner/run.ts",
    'grep -n "npm run ci:quick" package.json',
    "git push origin other-branch",
    "git push origin 1020-10",
):
    check(
        "not a pipeline: %s" % cmd,
        W.fix_in_flight(repo, BRANCH, tip, [{"id": "p", "command": cmd}]),
        None,
    )

# ---- 4. ci_trouble: `fixing` on a final red, `trouble` while live or without the pipeline ---------
CASE = [0]


def trouble(repo, tip, live_bg, live=False):
    CASE[0] += 1
    base = pathlib.Path(_SCRATCH) / ("case%d" % CASE[0])
    base.mkdir()
    ctx = {
        "name": "Tests + Infra / E2E Backup Browse-At",
        "conclusion": "FAILURE",
        "run": 39685278337,
        "job": 119525908102,
    }
    ctx["status"] = "IN_PROGRESS" if live else "COMPLETED"
    if live:
        ctx["conclusion"] = "FAILURE"

    def rollup(_root, _ref, _allow_branch=False, _repo=None):
        contexts = [ctx]
        if live:
            contexts.append(
                {
                    "name": "Quality / Static",
                    "conclusion": "",
                    "status": "IN_PROGRESS",
                    "run": 39685278337,
                    "job": 7,
                }
            )
        return "ok", {
            "owner": "rediacc",
            "name": "console",
            "pr": 601,
            "sha": tip,
            "contexts": contexts,
        }

    saved = (W.ci_rollup, W.ci_steps, W.ci_carry_split, W.ci_watch_armed, W._git)
    real_git = W._git
    W.ci_rollup = rollup
    W.ci_steps = lambda *_a, **_k: None
    W.ci_carry_split = lambda _r, _i, _t, hard, _c, **_k: (hard, [])
    W.ci_watch_armed = lambda *_a, **_k: ""
    # origin/<ref> is the red head; every other git read is the scratch repo's own.
    W._git = lambda r, *a: tip if a == ("rev-parse", "origin/%s" % BRANCH) else real_git(r, *a)
    try:
        return W.ci_trouble(repo, base / "wl.md", "deadbeef-t", live_bg, "", ref=BRANCH, owned=True)
    finally:
        W.ci_rollup, W.ci_steps, W.ci_carry_split, W.ci_watch_armed, W._git = saved


state, detail = trouble(repo, tip, PIPELINE)
check("ci_trouble: a final red with its fix in flight is `fixing`", state, "fixing")
note = W.ci_fixing_note(detail)
check(
    "... and the note names the job and the task",
    "E2E Backup Browse-At" in note and "bza6uy3ls" in note,
    True,
)
state, _d = trouble(repo, tip, [])
check("control: the same red with no pipeline still blocks", state, "trouble")
state, _d = trouble(repo, tip, PIPELINE, live=True)
check("control: a live run never stands down", state != "fixing", True)

T.exit()
