"""Refuse, before the command runs, a commit the PR freeze would refuse at commit-msg (PLAN-two-track-merge-dev F2, the pre-bash twin of F1; keyed on the landing tree's role since PLAN-simple-two-tree-loop B1).

The verdict is `pr_freeze.check`'s, the same call git/githooks.py makes at commit-msg, so the two cannot disagree; this guard only answers earlier, before `git add` or a message file is spent. The message is read the way block_untagged_commit reads it (`-m` values, a `-F -` heredoc or here-string, `-F <file>` off disk), and the paths are the pathspecs the commit names. A relative `-F` file is looked up beside the tool call's cwd and the repo root. A commit in another repository (a `cd` or `-C` elsewhere), or one whose message cannot be seen or read (an unreadable `-F` file is skipped), is left to the commit-msg hook, which stays the authority: this guard only answers earlier where it can see the whole message.

ORDER is the end of the pre-bash chain: the registry admits no tie, and a position beside block_untagged_commit would renumber every later guard.
"""

import contextlib
import pathlib
import re

from rediacc_hooks import commit_policy, hookio, pr_freeze, shellscan
from rediacc_hooks.guards import tables

__getattr__ = tables(
    "block_pr_freeze_commit",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "_DEV_BRANCH",
    "_FREEZE_BRANCH",
    "_GH_STUB",
    "_bash",
    "_freeze_world",
)

CHAIN = "pre-bash"
ORDER = 70
# The mutation check: with the verdict arm disabled every frozen commit is admitted, and the guard test's refusal cases go red.
DEFECT = (
    "    if not ok:\n        ev.warn_raw(BLOCKED % reason)",
    "    if False:\n        ev.warn_raw(BLOCKED % reason)",
)


COMMIT_AT_COMMAND_POS = re.compile(
    r"(^|[;&|(]|\bthen\b|\bdo\b)\s*(\w+=\S*\s+)*git(\s+-\S+(\s+\S+)?)*\s+commit\b", re.MULTILINE
)
BLOCKED = "BLOCKED: %s\n(block_pr_freeze_commit, the pre-bash twin of the commit-msg freeze; .claude/rediacc_hooks/pr_freeze.py)"


def _message(cmd: str, root: str, cwd: str = "") -> str:
    msg = commit_policy.commit_message_text(cmd, root, files=False)
    for run in commit_policy.git_runs(cmd, "commit"):
        for name in commit_policy.parse_commit_args(commit_policy.git_split(run.argv)[2]).files:
            if name in {"", "-"}:
                continue
            for cand in (name, *(["%s/%s" % (cwd, name)] if cwd else []), "%s/%s" % (root, name)):
                path = pathlib.Path(cand)
                if path.is_file():
                    with contextlib.suppress(OSError):
                        msg += "\n" + path.read_text(encoding="utf-8", errors="surrogateescape")
                    break
    return msg


def _paths(cmd: str, root: str) -> list[str] | None:
    """The pathspecs the commit names, or, with none, the paths git will commit: the staged ones, plus the unstaged tracked changes under `-a`/`--all` (review 84a5679f.1). None when git cannot list them; run() then judges with no paths, which admits only by the message (84a5679f.2, b5f9d11c.1)."""
    named, all_flag = [], False
    for run_ in commit_policy.git_runs(cmd, "commit"):
        args = commit_policy.parse_commit_args(commit_policy.git_split(run_.argv)[2])
        named.extend(args.paths)
        all_flag = all_flag or any(f in ("-a", "--all") for f in args.flags)
    if named:
        return named
    staged = hookio.git_out(["-C", root, "diff", "--cached", "--name-only"], want_rc=True)
    if staged is None:
        return None
    paths = [line for line in staged.splitlines() if line]
    if all_flag:
        unstaged = hookio.git_out(["-C", root, "diff", "--name-only"], want_rc=True)
        if unstaged is None:
            return None
        paths += [line for line in unstaged.splitlines() if line and line not in paths]
    return paths


def run(ev):
    state = shellscan.hook_init(ev.payload)
    if state is None:
        return hookio.ALLOW
    cmd, scan = state
    if not COMMIT_AT_COMMAND_POS.search(scan):
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    if not root or shellscan.target_root(scan, root, verb="commit", cmd=cmd) != "":
        return hookio.ALLOW
    cwd = ev.field("cwd")
    if cwd and cwd != root:
        other = hookio.git_out(["-C", cwd, "rev-parse", "--show-toplevel"], want_rc=True)
        if other is not None and other.strip() not in ("", root):
            return hookio.ALLOW
    msg = _message(cmd, root, cwd or "")
    if not re.sub(r"\s", "", msg):
        return hookio.ALLOW
    branch = hookio.git_out(["-C", root, "branch", "--show-current"], want_rc=True)
    # A failed read (None) or a detached HEAD (empty) is not judged here: pr_freeze.check freezes by the landing record, not by this branch, so the skip is this guard's own choice, and the commit-msg hook skips it too. A detached landing tree is the hotfix on origin/main after the merge (no open PR), and a detached lease is judged when its commits land.
    if branch is None or not branch.strip():
        return hookio.ALLOW
    paths = _paths(cmd, root)
    # Git could not list the paths: judged with none, so the path-dependent admits (records only, gitlinks) cannot apply and the guard fails closed for them; a fix, a chore(reviews) or a focus-fix still passes (review b5f9d11c.1).
    ok, reason = pr_freeze.check(
        root, root, branch.strip(), msg, paths if paths is not None else []
    )
    if not ok:
        ev.warn_raw(BLOCKED % reason)
        return hookio.DENY
    return hookio.ALLOW
