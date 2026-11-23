"""On `git push`, check whether the remote branch has moved past local HEAD and STOP the push before it burns a CI round.

WHY (operator, 2026-07-31): a babysat branch gets rebased on the REMOTE by GitHub's update-branch (strict_required_status_checks_policy keeps PR branches current with main), so a session's local branch silently falls behind its own remote. The session then watches a superseded run, or worse pushes its stale head, minting a non-fast-forward failure or an extra full CI round. One
`git fetch` here is cheaper than either.

Scope: plain `git push` in this superproject only. Submodule pushes name their own remotes and refs too many ways to second-guess; `--dry-run` is harmless. Fail-open on every environmental error (no network, no upstream, detached HEAD): a drift CHECK must never become a push outage.

ANOTHER REPO'S PUSH IS NOT THIS TREE'S DRIFT. Everything below reads THIS checkout's branch, HEAD and origin ref, so a `git -C <other> push` would be judged against console. Latent rather than live -- it only misfires when console's remote happens to be ahead -- but it is the same defect block-unverified-push.sh had for real, so it is closed the same way, with the shared resolver
rather than a third hand-rolled copy.

PORT NOTE ON WHAT IS HANDED TO THE RESOLVER. The bash calls `hook_target_root "$CMD" ...` with the RAW command, not with `hook_scan_target`'s output, so a `-C` hint inside a quoted span is still found. That is the opposite convention from warn-stale-index.sh next door, and it is carried across unchanged rather than harmonised: widening or narrowing it here would be a behaviour
change made by tidying, which is the one thing a port must not do.

A LEASE PUSH OF A REBASE IS A REPUBLISH, NOT DRIFT. Since the operator ruling of 2026-10-02 (PLAN-plan-per-pr-loop M3), block_git_force_push admits `git push --force-with-lease origin <live branch>`, so after a local rebase the remote holds the PRE-rebase commits and this guard saw them as commits the checkout lacks. A push that carries `--force-with-lease` (bare or `=<ref>[:<sha>]`) to `origin` naming the current branch is therefore judged by patch equivalence: when every commit in `HEAD..origin/<branch>` has a patch-equivalent commit on the local side (`git cherry HEAD origin/<branch>` prints only `-` lines) and none of them is a merge, the remote side is the rebase's own past and the push is allowed. One `+` line or one merge (a peer push, GitHub's update-branch) is genuinely new remote work, and the refusal stands with one extra line naming that commit. A plain push is judged exactly as before, rebase or not, and a git error during the judgement fails open like every other arm here.

PORT NOTE ON `timeout 15 git fetch`. `timeout(1)` exits 124 when it fires, and the `|| exit 0` treats that identically to any other failure. `subprocess` raises instead of returning a status, so the helper below catches `TimeoutExpired` and folds it into the same fail-open branch. Losing that catch would turn a slow network into a traceback out of a hook, which is the outage this
guard's own header forbids.

PORT NOTE ON THE HEREDOC. `cat >&2 <<EOF ... EOF` emits its body with the final newline included and nothing appended, so it is `ev.warn_raw`, not `ev.warn`. `warn` would add a second newline and the differential compares that byte.
"""

import subprocess

from rediacc_hooks import commit_policy, hookio, shellscan
from rediacc_hooks.guards import _cases

__getattr__ = _cases.lazy(
    "warn_remote_drift",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "_behind_tree",
    "_fixture_git",
    "_peer_plus_rebase_tree",
    "_rebased_tree",
)

CHAIN = "pre-bash"
ORDER = 19

# Remote strictly behind local is a NORMAL push of new commits. Without this arm every push of anything ever is refused as drift, which makes the guard an outage rather than a check -- the exact failure its own header forbids.
DEFECT = ("if _is_ancestor(remote, local, root):", "if False:")


MESSAGE = (
    "❌ BLOCKED: origin/%(branch)s has moved past your local HEAD (%(ahead)s commit(s) you "
    "do not have; likely GitHub's update-branch rebasing onto main, or another session "
    "pushing). Pushing now would fail or waste a full CI round on a stale base. Align "
    "FIRST, then push:\n"
    "  1. Compare: git log --oneline HEAD..origin/%(branch)s  and  git diff HEAD "
    "origin/%(branch)s --stat\n"
    "  2. If your local commits are content-identical to remote ones (a remote rebase), "
    "move the pointer losslessly: git reset --keep origin/%(branch)s  (then git submodule "
    "update -- <path> for any pointer-only submodule diff)\n"
    "  3. Otherwise rebase your unpushed commits: git rebase origin/%(branch)s  (never "
    "force-push the result)\n"
)


LEASE_JUDGED = (
    "  (--force-with-lease judged as a rebase republish and refused: origin/%(branch)s "
    'commit %(sha)s "%(subject)s" has no patch-equivalent commit in local HEAD.)\n'
)


def _lease_push(cmd, branch):
    """True when the push carries `--force-with-lease` to `origin` and names the current branch."""
    # The lexer's argv, not a regex over the text: a regex up to the next `|` read `git push --force-with-lease origin <b> 2>&1 | tail -3` as three positionals (the redirect among them) and refused the admitted republish (2026-10-03). And git's own parse of it (`shellscan.git_push_args`, #9de9a8e9): `--force-with` is the lease by unique prefix, `-uf` carries a plain force, and the last of `--force-with-lease`/`--no-force-with-lease` wins.
    runs = commit_policy.git_runs(cmd, "push")
    if len(runs) != 1:
        return False
    _, _, words = commit_policy.git_split(runs[0].argv)
    parsed = shellscan.git_push_args(words)
    lease = parsed.last("force-with-lease")
    positional = parsed.operands
    if parsed.on("force") or any(p.startswith("+") for p in positional):
        return False
    if lease is None or lease == "false" or len(positional) != 2 or positional[0] != "origin":
        return False
    names = {branch, "refs/heads/%s" % branch}
    src, sep, dst = positional[1].partition(":")
    if not sep:
        return src in names or src == "HEAD"
    return (src in names or src == "HEAD") and dst in names


def _unmatched_remote(local, remote, root):
    """The first remote-only commit with no local patch-equivalent, "" when there is none, None on a git error."""
    merges = hookio.git_out(
        ["rev-list", "--merges", "%s..%s" % (local, remote)], cwd=root, want_rc=True
    )
    if merges is None:
        return None
    if merges.split():
        return merges.split()[-1]
    cherry = hookio.git_out(["cherry", local, remote], cwd=root, want_rc=True)
    if cherry is None:
        return None
    for line in cherry.splitlines():
        if line.startswith("+ "):
            return line[2:].strip()
    return ""


def _fetch(root, branch):
    """`timeout 15 git fetch --quiet origin "$BRANCH" 2>/dev/null` -- ok or not."""
    try:
        proc = subprocess.run(
            ["git", "fetch", "--quiet", "origin", branch],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _is_ancestor(remote, local, root):
    """`git merge-base --is-ancestor "$REMOTE" "$LOCAL" 2>/dev/null`."""
    return hookio.run_rc(["git", "merge-base", "--is-ancestor", remote, local], cwd=root) == 0


def run(ev):
    cmd = ev.raw("tool_input", "command")

    # The pushes bash would run, read by the lexer: the words inside a quoted string or a `python3 -c` program are not a push (2026-10-03, #a1ac21ce).
    if not commit_policy.git_runs(cmd, "push"):
        return hookio.ALLOW

    root = ev.project_dir
    this_root = hookio.git_out(["rev-parse", "--show-toplevel"], cwd=root)
    # AN EMPTY ROOT IS A FAILED rev-parse, NOT A ROOT AT "". `git_out` without `want_rc` returns "" both when git succeeds with empty output and when it fails, so the two are indistinguishable here -- and the consumer cannot tell either: `shellscan.py:582` joins `this_root + "/" + hint`, so a relative `-C nested` resolves to the absolute `/nested` instead of `<repo>/nested`. It
    # then rev-parses a path outside this tree, and whatever that answers decides whether this guard stays silent. Reproduced 2026-09-08 by calling git_out with a cwd that is not a repository.
    #
    # ALLOW rather than block: this hook is an ADVISORY drift warning, and a guard that cannot establish where it is has no standing to judge a command. Refusing here would fire on every invocation outside a checkout.
    if this_root == "":
        return hookio.ALLOW
    if shellscan.target_root(cmd, this_root, verb="push") != "":
        return hookio.ALLOW
    # Only the pushes that act on THIS checkout: a `git -C <dir> push` whose directory resolves to another repository, or to none (an unexpanded `$VAR`), is not this tree's drift. The lexer reaches pushes the old text match never saw (`eval`, `sh -c`, `git -C`), so the scope has to be explicit.
    pushes = [
        r
        for r in commit_policy.git_runs(cmd, "push")
        if commit_policy.run_repo(r, this_root, root=this_root) == this_root
    ]
    if not pushes:
        return hookio.ALLOW
    if any(
        shellscan.git_push_args(commit_policy.git_split(r.argv)[2]).on("dry-run") for r in pushes
    ):
        return hookio.ALLOW

    branch = hookio.git_out(["symbolic-ref", "--short", "-q", "HEAD"], cwd=root, want_rc=True)
    if branch is None or branch == "":
        return hookio.ALLOW

    # Bounded fetch of just this branch; fail open on timeout or any error.
    if not _fetch(root, branch):
        return hookio.ALLOW

    remote = hookio.git_out(
        ["rev-parse", "-q", "--verify", "origin/%s" % branch], cwd=root, want_rc=True
    )
    if remote is None:
        return hookio.ALLOW
    local = hookio.git_out(["rev-parse", "-q", "--verify", "HEAD"], cwd=root, want_rc=True)
    if local is None:
        return hookio.ALLOW
    if remote == local:
        return hookio.ALLOW

    # Remote strictly behind local = a normal push of new commits; let it through.
    if _is_ancestor(remote, local, root):
        return hookio.ALLOW

    # `$(git rev-list --count ... 2>/dev/null || echo "?")`: the fallback is the literal question mark, and it lands in the message. `want_rc` is what separates "git failed" from "git printed nothing", which the default spelling of git_out collapses.
    ahead = hookio.git_out(
        ["rev-list", "--count", "%s..%s" % (local, remote)], cwd=root, want_rc=True
    )
    if ahead is None:
        ahead = "?"

    if _lease_push(cmd, branch):
        sha = _unmatched_remote(local, remote, root)
        if sha is None or sha == "":
            return hookio.ALLOW
        subject = hookio.git_out(["log", "-1", "--format=%s", sha], cwd=root)
        ev.warn_raw(
            MESSAGE % {"branch": branch, "ahead": ahead}
            + LEASE_JUDGED % {"branch": branch, "sha": sha[:12], "subject": subject}
        )
        return hookio.DENY

    ev.warn_raw(MESSAGE % {"branch": branch, "ahead": ahead})
    return hookio.DENY
