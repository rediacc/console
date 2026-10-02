"""Refuse a push while a commit on the branch has no per-commit review on record, or while a review blocks it.

WHY (agent/plans/PLAN-per-commit-review.md section 5; operator ruling 2026-10-02). The per-commit haiku review replaced the PR-level Claude review, and the Stop hook that was meant to enforce it is disabled. The push is the one moment every commit must pass, so this guard is where the review is enforced: a branch reaches GitHub only with every commit reviewed, every review committed beside it and
no open finding at or above `block_at` (`.ci/config/commit-review.json`).

WHAT REFUSES, in the order the message lists it:

  malformed    a review file does not parse or its Body-Sig does not match (a hand edit).
  blocking     an open finding at or above `block_at`; the three `--review-mark` commands are printed.
  unreviewed   a commit of the branch has no review file and no live reviewer; the `--run` command is printed.
  in flight    a reviewer is still running: wait for it (about a minute), its file lands, then commit it.
  failed       a review failed once; the retry command is printed. A second failure stops blocking: a model outage is a broken environment, not a verdict, and the failed file still names the commit.
  unrecorded   a finished review file is untracked or modified (console pushes only): `worklist.py --review-commit <me>`.

The scope is the PUSHED repository: `git -C private/account push` judges that repository's commits on the same branch, whose review files live in the console's `agent/reviews/<branch>/` like every other. A dry run and a delete-only push publish no commits and pass. A detached HEAD has no branch to judge and passes.

FAILS OPEN ON A BROKEN ENVIRONMENT, never on a verdict: an unimportable reviewer module or a missing git warns and allows, the rule `block_unverified_push` states.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_push_with_unrecorded_reviews.py` beside it and against its own DEFECT, never against a golden.
"""

import os
import pathlib
import subprocess

from rediacc_hooks import hookio, shellscan, syspath

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 52

# The verdict is the whole guard: with it emptied every push passes.
DEFECT = ('reasons = rv.push_refusals(st, console_push=label == "console")', "reasons = []")

STOP_DIR = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "stop"

HEAD = (
    "BLOCKED: the push of %s (%s) carries commits whose per-commit review is not settled: %s.\n"
    "\n"
    "Every commit of the branch is reviewed by haiku after it is made (the post-bash hook starts\n"
    "the reviewer), and the review file rides the branch. Settle each line below, then push again.\n"
    "\n"
)

TAIL = (
    "\n"
    "Wait for a reviewer in flight with:  python3 .claude/hooks/stop/wl_review.py --status\n"
    "Record finished reviews with:        .claude/hooks/stop/worklist.py --review-commit <me>\n"
)


def _fixture_env():
    return dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )


def _branch_world(path, reviewed):
    """A checkout on branch 0930-1 with one commit past `origin/main`, and, when `reviewed`, a clean committed review of it.

    The review file is written in the reviewer's own format through `wl_review.render`, so the world needs no model. Without these worlds every edge case would be judged against whatever this shared tree holds when the suite runs, and the guard's DEFECT could not be shown to change any answer.
    """
    path = pathlib.Path(path)
    origin = path.parent / (path.name + "-origin.git")
    env = _fixture_env()

    def git(*args):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, env=env)

    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "--bare", str(origin)], check=True, capture_output=True, env=env
    )
    git("init", "-q", "--initial-branch=main")
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    git("add", "seed.txt")
    git("commit", "-q", "-m", "seed")
    git("remote", "add", "origin", str(origin))
    git("push", "-q", "origin", "main")
    git("checkout", "-q", "-b", "0930-1")
    (path / "f.py").write_text("a = 1\n", encoding="utf-8")
    git("add", "f.py")
    git("commit", "-q", "-m", "fix(x): y")
    if reviewed:
        rv = _load_reviewer()
        sha = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout.strip()
        if not sha:
            raise RuntimeError("git rev-parse HEAD printed nothing in the fixture repo")
        review = rv.Review(
            sha=sha,
            subject="fix(x): y",
            branch="0930-1",
            reviewed_at="2026-10-02T00:00:00Z",
            model="m",
        )
        target = rv.review_path(path, "0930-1", sha)
        rv.write_atomic(target, rv.render(review))
        git("add", "--", str(target.relative_to(path)))
        git("commit", "-q", "-m", "chore(reviews): record")
    return path


FIXTURES = {
    "push-unreviewed": lambda p: _branch_world(p, reviewed=False),
    "push-reviewed": lambda p: _branch_world(p, reviewed=True),
}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (name, {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in sorted(FIXTURES)
]

EDGE_CASES = [
    ("a plain push", "git push"),
    ("a push with a refspec", "git push origin 0930-1"),
    ("a push in a submodule", "git -C private/account push origin 0930-1"),
    ("a dry run publishes nothing", "git push --dry-run"),
    ("a delete-only push", "git push origin --delete old-branch"),
    ("prose naming a push", "echo 'git push later'"),
    ("not a push", "git status"),
]


def _push_runs(cmd):
    return [r for r in shellscan._analyse(cmd).runs if r.git_sub == "push"]


def _publishes(run):
    """False for a push that publishes no commits: a dry run, or a delete-only refspec list."""
    args = list(run.argv)
    if "--dry-run" in args or "-n" in args:
        return False
    if "--delete" in args or "-d" in args:
        return False
    refspecs = (
        [a for a in args[args.index("push") + 1 :] if not a.startswith("-")][1:]
        if "push" in args
        else []
    )
    return not (refspecs and all(r.startswith(":") for r in refspecs))


def _load_reviewer():
    syspath.on_sys_path(STOP_DIR)
    import wl_review  # noqa: PLC0415 -- loaded only for a push, never for the rest of the chain

    return wl_review


def run(ev):
    cmd = ev.field("tool_input", "command")
    if "push" not in cmd:
        return hookio.ALLOW
    pushes = [r for r in _push_runs(cmd) if _publishes(r)]
    if not pushes:
        return hookio.ALLOW
    try:
        rv = _load_reviewer()
    except Exception as exc:  # noqa: BLE001 -- a broken environment warns and allows
        ev.warn("per-commit review check skipped: the reviewer module did not load (%s)" % exc)
        return hookio.ALLOW
    project = pathlib.Path(ev.project_dir).resolve()
    root = rv.git_out(project, "rev-parse", "--show-toplevel")
    if not root:
        return hookio.ALLOW
    root = pathlib.Path(root)
    base = pathlib.Path(ev.field("cwd") or root)
    seen = set()
    for push in pushes:
        where = base if push.git_dir in (None, "", ".") else base / push.git_dir
        top = rv.git_out(where, "rev-parse", "--show-toplevel")
        if not top or top in seen:
            continue
        seen.add(top)
        # Only this project and the repositories inside it (its submodules): a scratch repository's push carries none of this branch's commits, and its reviews would never exist.
        real_top, real_root = os.path.realpath(top), os.path.realpath(root)
        if real_top != real_root and not real_top.startswith(real_root + os.sep):
            continue
        repo = pathlib.Path(top)
        branch = rv.current_branch(repo)
        if not branch:
            continue
        label = rv.repo_label(root, repo)
        try:
            st = rv.branch_state(root, branch, repos={label})
        except Exception as exc:  # noqa: BLE001 -- a broken environment warns and allows
            ev.warn(
                "per-commit review check skipped for %s (%s: %s)" % (label, type(exc).__name__, exc)
            )
            continue
        reasons = rv.push_refusals(st, console_push=label == "console")
        if reasons:
            ev.warn_raw(
                HEAD % (branch, label, ", ".join(reasons))
                + "".join("  %s\n" % line for line in rv.describe(st, limit=8))
                + TAIL
            )
            return hookio.DENY
    return hookio.ALLOW
