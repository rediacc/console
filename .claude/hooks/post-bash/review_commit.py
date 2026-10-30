#!/usr/bin/env python3
"""PostToolUse/Bash: start a detached haiku review for every new commit, and tell the session about each review that finished (agent/plans/PLAN-per-commit-review.md section 3.1; operator ruling 2026-10-02).

TWO JOBS, BOTH CHEAP.

1. TRIGGER. When the command ran `git commit`, `rebase`, `cherry-pick`, `merge`, `revert`, `pull` or `am` at a command position (the shell lexer's own reading, so an `echo` or a commit message quoting the words is not a commit), each repository those invocations ran in is asked `wl_review.uncovered()`: the branch's commits with no review record and no live reviewer. Up to `max_spawn_per_trigger` of them get a
   reviewer started with `wl_review.spawn_detached`, which takes the per-sha lock and detaches the child from this hook's pipes. The hook does not read `tool_response` (it carries no exit code): a failed commit made no new sha, so nothing is uncovered and nothing starts.

2. SURFACE. On EVERY Bash call, the review records (ledger lines and `.md` files) that finished since this session last heard of them are reported as `additionalContext`. With the Stop hook disabled (operator, 2026-10-02) this is the channel that brings a review back to the session that made the commit, one tool call after it lands; SessionStart and the push guard are the other two.

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

R = importlib.import_module("wl_review")
hookio = importlib.import_module("rediacc_hooks.hookio")
shellscan = importlib.import_module("rediacc_hooks.shellscan")


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
        members = {real_root, *(os.path.realpath(p) for p in _submodule_paths(root))}
        for cand in candidates:
            # MEMBERSHIP IS `.gitmodules`, NOT LOCATION (operator 2026-10-08). private/growth is a separate, gitignored repository inside the tree; reviewing its commits filed the operator's private documents into this project's agent/reviews/.
            inside = bool(cand) and os.path.realpath(cand) in members
            if inside and cand not in repos:
                repos.append(cand)
    return repos


def _submodule_paths(root):
    """The checkouts `.gitmodules` registers, as absolute paths; a repository that merely sits inside the tree (gitignored, cloned beside the submodules) is not one."""
    root = pathlib.Path(root)
    out = R.git_out(root, "config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$")
    paths = []
    for line in (out or "").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and (root / parts[1].strip() / ".git").exists():
            paths.append(str(root / parts[1].strip()))
    return paths


def _project_repos(root):
    """The project and its registered submodules, as top-level paths."""
    return [str(pathlib.Path(root)), *_submodule_paths(root)]


def trigger_lines(cmd, cwd, root, trigger=R.trigger):
    lines = []
    for repo in commit_repos(cmd, cwd, root):
        try:
            started = trigger(root, pathlib.Path(repo))
        except Exception as exc:
            lines.append(
                "per-commit review NOT started in %s (%s: %s)"
                % (repo, type(exc).__name__, str(exc)[:160])
            )
            continue
        if not started:
            # trigger() started nothing: every in-scope commit is covered or has a live reviewer, the command made no commit (a failed or empty commit), the repository has no branch, or a miss (#52978244). The HEAD is named so the next miss can be diagnosed from this result: it is the commit made only when the command made one.
            head = R.git_out(pathlib.Path(repo), "rev-parse", "--short", "HEAD") or "?"
            lines.append(
                "per-commit review: none due for %s, HEAD %s (covered, no new commit, or a miss: run wl_review.py --check)"
                % (R.repo_label(root, repo), head)
            )
        for sha, pid in started:
            lines.append(
                "per-commit review started for %s %s (pid %s): its record lands in about a minute, in agent/reviews/%s/clean.jsonl or as %s.md"
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
    except Exception as exc:
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
