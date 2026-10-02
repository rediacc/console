#!/usr/bin/env python3
"""PostToolUse/Bash: start a detached haiku review for every new commit, and tell the session about each review that finished (agent/plans/PLAN-per-commit-review.md section 3.1; operator ruling 2026-10-02).

TWO JOBS, BOTH CHEAP.

1. TRIGGER. When the command ran `git commit`, `rebase`, `cherry-pick`, `merge`, `revert`, `pull` or `am` at a command position (the shell lexer's own reading, so an `echo` or a commit message quoting the words is not a commit), each repository those invocations ran in is asked `wl_review.uncovered()`: the branch's commits with no review file and no live reviewer. Up to `max_spawn_per_trigger` of them get a
   reviewer started with `wl_review.spawn_detached`, which takes the per-sha lock and detaches the child from this hook's pipes. The hook does not read `tool_response` (it carries no exit code): a failed commit made no new sha, so nothing is uncovered and nothing starts.

2. SURFACE. On EVERY Bash call, the review files that finished since this session last heard of them are reported as `additionalContext`. With the Stop hook disabled (operator, 2026-10-02) this is the channel that brings a review back to the session that made the commit, one tool call after it lands; SessionStart and the push guard are the other two.

Advisory: always exits 0, never blocks the tool call that already ran, and does nothing at all inside a reviewer or a Stop-hook child (`COMMIT_REVIEW_CHILD`, `STOPHOOK_CHILD`).
"""

import importlib.util
import json
import os
import pathlib
import sys

HOOKS = pathlib.Path(__file__).resolve().parents[1]


def _load_syspath():
    """The canonical `.claude` hop, rediacc_hooks/syspath.py, loaded BY PATH: this hook runs as a script, so `rediacc_hooks` is not importable by name until the hop has run."""
    hop_file = HOOKS.parent / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop_file)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SYSPATH = _load_syspath()
_SYSPATH.on_sys_path(_SYSPATH.CLAUDE_DIR)
_SYSPATH.on_sys_path(_SYSPATH.STOP_DIR)

import wl_review as R  # noqa: E402
from rediacc_hooks import hookio, shellscan  # noqa: E402


def commit_repos(cmd, cwd, root):
    """The top levels of every repository a history-writing git invocation in `cmd` ran in, limited to this project and the repositories inside it (its submodules). Empty when there is none.

    A commit in a scratch repository under /tmp is not this branch's work, and reviewing it would file a record into this project's `agent/reviews/` about a commit no push of it ever carries.
    """
    base = pathlib.Path(cwd or root)
    real_root = os.path.realpath(root)
    repos = []
    for run in shellscan._analyse(cmd).runs:
        if run.git_sub not in R.TRIGGER_SUBS:
            continue
        where = base if run.git_dir in (None, "", ".") else base / run.git_dir
        top = R.git_out(where, "rev-parse", "--show-toplevel")
        # AN UNRESOLVABLE `-C` IS NOT "NO REPOSITORY" (#51e1c0cf). `git -C <dir>/$r commit` in a loop names a directory the lexer cannot expand, so rev-parse fails; skipping it left account 654d186 unreviewed until the push guard refused the push. Every project repository is checked instead: uncovered() is cheap, and a covered repository starts nothing.
        candidates = [top] if top else (_project_repos(root) if run.git_dir else [])
        for cand in candidates:
            inside = cand and (
                os.path.realpath(cand) == real_root
                or os.path.realpath(cand).startswith(real_root + os.sep)
            )
            if inside and cand not in repos:
                repos.append(cand)
    return repos


def _project_repos(root):
    """The project and every repository directly inside it or under `private/` (its submodules), as top-level paths."""
    root = pathlib.Path(root)
    found = [str(root)]
    for parent in (root, root / "private"):
        if not parent.is_dir():
            continue
        found.extend(
            str(child)
            for child in sorted(parent.iterdir())
            if child.is_dir() and (child / ".git").exists()
        )
    return found


def trigger_lines(cmd, cwd, root, trigger=R.trigger):
    lines = []
    for repo in commit_repos(cmd, cwd, root):
        try:
            started = trigger(root, pathlib.Path(repo))
        except Exception as exc:  # noqa: BLE001 -- advisory: a broken trigger says so and lets the tool call stand
            lines.append(
                "per-commit review NOT started in %s (%s: %s)"
                % (repo, type(exc).__name__, str(exc)[:160])
            )
            continue
        for sha, pid in started:
            lines.append(
                "per-commit review started for %s %s (pid %s): agent/reviews/%s/%s.md lands in about a minute"
                % (
                    R.repo_label(root, repo),
                    sha[:8],
                    pid,
                    R.branch_slug(R.current_branch(repo)),
                    sha,
                )
            )
    return lines


def main():
    if os.environ.get("COMMIT_REVIEW_CHILD") or os.environ.get("STOPHOOK_CHILD"):
        return 0
    ev = hookio.Event(sys.stdin.read())
    root = R.git_out(pathlib.Path(ev.project_dir).resolve(), "rev-parse", "--show-toplevel")
    if not root:
        return 0
    root = pathlib.Path(root)
    cmd = ev.field("tool_input", "command")
    lines = []
    if cmd and "git" in cmd and any(sub in cmd for sub in R.TRIGGER_SUBS):
        lines += trigger_lines(cmd, ev.field("cwd") or None, root)
    try:
        lines += R.surface_new(root, R.current_branch(root), ev.field("session_id"))
    except Exception as exc:  # noqa: BLE001 -- advisory
        lines.append(
            "per-commit review surfacing failed (%s: %s)" % (type(exc).__name__, str(exc)[:160])
        )
    if lines:
        sys.stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": "\n".join(lines),
                    }
                }
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
