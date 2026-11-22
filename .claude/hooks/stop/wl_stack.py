"""The stacked development branch (PLAN-two-track-merge-dev LT19): where the development tree's branch stands against the landing branch.

Operator ruling ASKED:2026-11-20T18:46Z: the development branch is STACKED on the landing branch (the landing tip plus development commits), so `git rebase <landing branch>` brings landing's fixes in at once, and commits flow one way, landing into development. After the landing PR rebase-merges, promotion (`./run.sh worktree landing --promote`) rebases the development branch onto origin/main, where landing's copies read absorbed, moves it into the landing tree and rewrites the landing record.

`stack_state(root)` answers one of:

  none     no valid landing record, `root` is the landing tree itself, or the development tree holds no branch of its own (detached, `main`, or the record's branch).
  current  the landing tip is an ancestor of the development branch.
  behind   the landing branch holds commits the development branch lacks: report `git rebase <landing branch>`.
  merged   the landing branch is on origin/main (every commit of it patch-equivalent to one there, or, when it holds none of its own, its PR reads MERGED), and the record still names it: promotion has not run. BLOCKS at every effort level once the merged PR's release is green (`released`); while the release is still in flight or red it is reported, not blocked on (agent/plans/PLAN-simple-two-tree-loop.md D3: promote's premise is a fully green release, and the development tree never waits on landing).

A promoted tree is quiet by construction: promotion rewrites the record to the branch it moved into landing, so the merged branch is no longer the one judged.

The landing tip is the LOCAL branch, which every tree of the repository shares. A development branch rebased onto a landing commit that is not pushed yet is no hazard for the landing push: block_landing_one_way admits a pushed commit the landing branch's reflog shows was made there.

`stack_block` and `stack_report` never raise: a reader failure answers "", because a git blip must not block a stop. The merged block is a FLOOR key (`landing-stack`, wl_floor.FLOOR); the behind report is advisory (`landing-behind`).
"""

from __future__ import annotations

import dataclasses
import importlib.util
import pathlib
import subprocess

GIT_TIMEOUT_S = 60
REMOTE = "origin"
PROMOTE_COMMAND = "./run.sh worktree landing --promote"

NONE = "none"
CURRENT = "current"
BEHIND = "behind"
MERGED = "merged"

BLOCK_KEY = "landing-stack"
REPORT_KEY = "landing-behind"


@dataclasses.dataclass(frozen=True)
class StackState:
    state: str
    landing: str = ""
    landing_path: str = ""
    development: str = ""
    ahead: int = 0
    carried: int = 0
    rebased: bool = False
    how: str = ""
    command: str = ""


def _hooks_pkg():
    """commit_policy from `.claude/rediacc_hooks`, through the canonical sys.path hop loaded by file (this module lives outside that package)."""
    helper = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", helper)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % helper)
    syspath = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(syspath)
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    from rediacc_hooks import commit_policy

    return commit_policy


def _git(cwd, *args) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return r.returncode, r.stdout.strip()


def _resolves(root, ref: str) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")[0] == 0


def _cherry(root, upstream: str, head: str) -> list[str] | None:
    """`git cherry <upstream> <head>` marks, one `+` or `-` per commit of `head` not in `upstream`; None when git fails."""
    rc, out = _git(root, "cherry", upstream, head)
    if rc != 0:
        return None
    return [line[:1] for line in out.splitlines() if line[:1] in "+-"]


def gh_pr_merged(root, branch: str) -> bool:
    """Whether a MERGED PR is headed by `branch`, read through wl_gh; False when gh cannot say."""
    try:
        import wl_gh

        rows, _err = wl_gh.call(
            [
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "merged",
                "--json",
                "number",
                "--limit",
                "1",
            ],
            cwd=str(root),
        )
    except Exception:
        return False
    return bool(rows)


def _fetch(root, branch: str) -> None:
    _git(
        root,
        "fetch",
        "--quiet",
        "--no-tags",
        REMOTE,
        "+refs/heads/%s:refs/remotes/%s/%s" % (branch, REMOTE, branch),
    )


def _landing_merged(root, landing: str, main_ref: str, pr_merged) -> str:
    """How the landing branch reads merged ("" when it does not): every commit absorbed on main, or none of its own and a MERGED PR."""
    marks = _cherry(root, main_ref, "refs/heads/" + landing)
    if marks is None or "+" in marks:
        return ""
    if marks:
        return "its %d commit(s) are absorbed on %s" % (
            len(marks),
            main_ref.removeprefix("refs/remotes/"),
        )
    if pr_merged(root, landing):
        return "its PR is merged"
    return ""


def stack_state(root, fetch: bool = True, pr_merged=gh_pr_merged) -> StackState:
    """Where the development tree at `root` stands against the landing branch. `fetch` refreshes origin/main first (best effort); `pr_merged(root, branch)` answers the PR question for a landing branch with no commits of its own."""
    cp = _hooks_pkg()
    record = cp.landing_record(str(root))
    if record is None or cp.tree_role(str(root)) == cp.ROLE_LANDING:
        return StackState(NONE)
    landing = record["branch"]
    development = cp.current_branch(str(root), foreign=True)
    if not development or development in ("main", landing):
        return StackState(NONE, landing=landing, landing_path=record["path"])
    base = {"landing": landing, "landing_path": record["path"], "development": development}
    if not _resolves(root, "refs/heads/" + landing):
        return StackState(NONE, **base)
    if fetch:
        _fetch(root, "main")
    main_ref = "refs/remotes/%s/main" % REMOTE
    if _resolves(root, main_ref):
        how = _landing_merged(root, landing, main_ref, pr_merged)
        if how:
            marks = _cherry(root, main_ref, "refs/heads/" + development) or []
            rebased = (
                _git(root, "merge-base", "--is-ancestor", main_ref, "refs/heads/" + development)[0]
                == 0
            )
            return StackState(
                MERGED,
                carried=marks.count("-"),
                rebased=rebased,
                how=how,
                command=PROMOTE_COMMAND,
                **base,
            )
    rc, _ = _git(
        root, "merge-base", "--is-ancestor", "refs/heads/" + landing, "refs/heads/" + development
    )
    if rc == 0:
        return StackState(CURRENT, **base)
    rc, count = _git(root, "rev-list", "--count", "%s..%s" % (development, "refs/heads/" + landing))
    ahead = int(count) if rc == 0 and count.isdigit() else 0
    return StackState(BEHIND, ahead=ahead, command="git rebase %s" % landing, **base)


def _merged_text(st: StackState) -> str:
    if st.carried:
        why = "still carries %d landing commit(s) main absorbed" % st.carried
    elif not st.rebased:
        why = "is not rebased onto %s/main" % REMOTE
    else:
        why = (
            "is rebased onto %s/main, and the rest of promotion (the branch moved into landing, the record rewritten, the draft flipped ready) has not run"
            % REMOTE
        )
    return (
        "LANDING MERGED (blocks from effort low; an advisory at quiet): the landing branch %s is on %s/main (%s), "
        "and this tree's development branch %s %s. Promotion runs here before anything else:\n"
        "  %s\n"
        "A development branch built on a merged landing branch would carry the merged PR's commits a second time.\n"
        "(.claude/hooks/stop/wl_stack.py, PLAN-two-track-merge-dev LT19; operator ruling ASKED:2026-11-20T18:46Z)"
        % (st.landing, REMOTE, st.how, st.development, why, st.command)
    )


def _behind_text(st: StackState) -> str:
    return (
        "LANDING AHEAD: the landing branch %s (tree %s) holds %d commit(s) the development branch %s lacks. "
        "The development branch is stacked on it; take them in this tree:\n"
        "  %s\n"
        "(.claude/hooks/stop/wl_stack.py, PLAN-two-track-merge-dev LT19)"
        % (st.landing, st.landing_path, st.ahead, st.development, st.command)
    )


def _release_pending_text(st: StackState) -> str:
    return (
        "LANDING MERGED, RELEASE PENDING: the landing branch %s is on %s/main (%s), and the release at the "
        "merged sha is not green yet. Keep building; promotion (%s) runs once Console CI on main and the "
        "edge deploy are both SUCCESS, and this stop blocks on it then.\n"
        "(.claude/hooks/stop/wl_stack.py, agent/plans/PLAN-simple-two-tree-loop.md D3)"
        % (st.landing, REMOTE, st.how, st.command)
    )


def stack_block(root, released=True, **kw) -> str:
    """The FLOOR stop text while the landing branch is merged, its release is green (`released`, the development tree's `wl_prscope.LoopState.landing_released`) and promotion has not run, else "". Never raises."""
    if not released:
        return ""
    try:
        st = stack_state(root, **kw)
    except Exception:
        return ""
    return _merged_text(st) if st.state == MERGED else ""


def stack_report(root, released=True, **kw) -> str:
    """The advisory text while the landing branch is ahead of the development branch, or merged while its release is not green yet (`released` False), else "". Never raises."""
    try:
        st = stack_state(root, **kw)
    except Exception:
        return ""
    if st.state == MERGED and not released:
        return _release_pending_text(st)
    return _behind_text(st) if st.state == BEHIND else ""


def _development_path(root) -> str:
    """The main checkout, the development tree: the first entry of `git worktree list --porcelain`."""
    rc, out = _git(root, "worktree", "list", "--porcelain")
    if rc != 0:
        return ""
    for line in out.splitlines():
        if line.startswith("worktree "):
            return line[len("worktree ") :]
    return ""


def notify_line(root, event: str, pr: int | None = None, sha: str = "") -> str:
    """The cross-session message the landing session sends the development session, "" with no valid record or an unknown event.

    WHEN. `push`: after each `git push` of the landing branch from the landing tree exits 0 (the post-bash side). `merged`: once `gh pr merge` of the landing PR reads MERGED (/pr-merge, after the merge is confirmed). `cd-done`: once the release at the merged sha (`sha`) is fully green, Console CI on main and the edge deploy both SUCCESS (agent/plans/PLAN-simple-two-tree-loop.md D1 L-RELEASE to L-IDLE): the landing stop names it once per merged sha, and promote is the development session's next step once every plan on its branch is code-complete (D3). The sending itself is the landing session's SendMessage; this is the text.
    """
    try:
        cp = _hooks_pkg()
        record = cp.landing_record(str(root))
    except Exception:
        return ""
    if record is None:
        return ""
    landing = record["branch"]
    where = _development_path(root) or "the main checkout"
    if event == "push":
        rc, sha = _git(root, "rev-parse", "--short", "refs/heads/" + landing)
        tip = sha if rc == 0 and sha else "its new tip"
        return (
            "LANDING PUSH: the landing branch %s is pushed at %s. In the development tree (%s), take it now:\n"
            "  git rebase %s" % (landing, tip, where, landing)
        )
    if event == "merged":
        number = "PR #%d" % pr if pr else "its PR"
        return (
            "LANDING MERGED: the landing branch %s (%s) rebase-merged into main. In the development tree (%s), "
            "promotion runs before anything else (its Stop hook blocks until it does):\n"
            "  %s" % (landing, number, where, PROMOTE_COMMAND)
        )
    if event == "cd-done":
        number = "PR #%d" % pr if pr else "its PR"
        at = " at %s" % sha[:12] if sha else ""
        return (
            "CD DONE: the landing branch %s (%s) is merged and its release%s is green (Console CI on main "
            "and CD - Release to Edge). In the development tree (%s), once every [writer] box of the plans "
            "on its branch is ticked, promote at a commit boundary:\n"
            "  %s" % (landing, number, at, where, PROMOTE_COMMAND)
        )
    return ""
