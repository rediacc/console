"""On `git push`, check whether the remote branch has moved past local HEAD and STOP the push before it burns a CI round.

WHY (operator, 2026-07-31): a babysat branch gets rebased on the REMOTE by GitHub's update-branch (strict_required_status_checks_policy keeps PR branches current with main), so a session's local branch silently falls behind its own remote. The session then watches a superseded run, or worse pushes its stale head, minting a non-fast-forward failure or an extra full CI round. One
`git fetch` here is cheaper than either.

Scope: plain `git push` in this superproject only. Submodule pushes name their own remotes and refs too many ways to second-guess; force-pushes are already blocked by block-git-force-push.sh; `--dry-run` is harmless. Fail-open on every environmental error (no network, no upstream, detached HEAD): a drift CHECK must never become a push outage.

ANOTHER REPO'S PUSH IS NOT THIS TREE'S DRIFT. Everything below reads THIS checkout's branch, HEAD and origin ref, so a `git -C <other> push` would be judged against console. Latent rather than live -- it only misfires when console's remote happens to be ahead -- but it is the same defect block-unverified-push.sh had for real, so it is closed the same way, with the shared resolver
rather than a third hand-rolled copy.

PORT NOTE ON WHAT IS HANDED TO THE RESOLVER. The bash calls `hook_target_root "$CMD" ...` with the RAW command, not with `hook_scan_target`'s output, so a `-C` hint inside a quoted span is still found. That is the opposite convention from warn-stale-index.sh next door, and it is carried across unchanged rather than harmonised: widening or narrowing it here would be a behaviour
change made by tidying, which is the one thing a port must not do.

PORT NOTE ON `timeout 15 git fetch`. `timeout(1)` exits 124 when it fires, and the `|| exit 0` treats that identically to any other failure. `subprocess` raises instead of returning a status, so the helper below catches `TimeoutExpired` and folds it into the same fail-open branch. Losing that catch would turn a slow network into a traceback out of a hook, which is the outage this
guard's own header forbids.

PORT NOTE ON THE HEREDOC. `cat >&2 <<EOF ... EOF` emits its body with the final newline included and nothing appended, so it is `ev.warn_raw`, not `ev.warn`. `warn` would add a second newline and the differential compares that byte.
"""

import subprocess

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 19

# Remote strictly behind local is a NORMAL push of new commits. Without this arm every push of anything ever is refused as drift, which makes the guard an outage rather than a check -- the exact failure its own header forbids.
DEFECT = ("if _is_ancestor(remote, local, root):", "if False:")

PUSH = hookio.rx(r"(^|[|;&{S}])git push([{S}]|$)")
DRY_RUN = r"git push[^|;&]*--dry-run"


def _fixture_git(cwd, *args):
    """`git` for the fixture builder, with the ambient config shut out."""
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": "/nonexistent",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )


def _behind_tree(path):
    """A checkout whose origin has one commit it has never seen.

    Built with a LOCAL bare remote and a second clone, never over the network: the fetch this guard performs must succeed deterministically, and a differential that reached github.com would be a network test whose two sides ran seconds apart.

    `nested/` is an independent repository inside the work tree, and it is what makes the `hook_target_root` arm reachable: the resolver turns a relative `-C nested` hint into `<this_root>/nested`, and only a hint that resolves to a DIFFERENT toplevel exempts the push.
    """
    bare = path.parent / (path.name + ".origin.git")
    bare.mkdir(parents=True)
    _fixture_git(bare, "init", "--bare", "--initial-branch=main", "-q")
    path.mkdir(parents=True)
    _fixture_git(path, "init", "--initial-branch=main", "-q")
    _fixture_git(path, "remote", "add", "origin", str(bare))
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _fixture_git(path, "add", "seed.txt")
    _fixture_git(path, "commit", "-q", "-m", "seed")
    # `main` is pushed too, so the bare repo's HEAD resolves and the clone below is not the "cloned an empty repository" shape.
    _fixture_git(path, "push", "-q", "origin", "main")
    _fixture_git(path, "checkout", "-q", "-b", "0831-1")
    _fixture_git(path, "push", "-q", "origin", "0831-1")

    # A peer session pushing onto the same branch: exactly the shape the operator's 2026-07-31 report describes, minus GitHub's rebase.
    peer = path.parent / (path.name + ".peer")
    _fixture_git(path.parent, "clone", "-q", str(bare), str(peer))
    _fixture_git(peer, "checkout", "-q", "0831-1")
    (peer / "peer.txt").write_text("peer\n", encoding="utf-8")
    _fixture_git(peer, "add", "peer.txt")
    _fixture_git(peer, "commit", "-q", "-m", "a commit this checkout has never seen")
    _fixture_git(peer, "push", "-q", "origin", "0831-1")

    nested = path / "nested"
    nested.mkdir()
    _fixture_git(nested, "init", "--initial-branch=main", "-q")
    (nested / "n.txt").write_text("n\n", encoding="utf-8")
    _fixture_git(nested, "add", "n.txt")
    _fixture_git(nested, "commit", "-q", "-m", "nested")
    return path


FIXTURES = {"drift-behind": _behind_tree}

# THREE WORLDS, AND NO LIVE ONE. Every variant points CLAUDE_PROJECT_DIR at a fixture with a local bare origin, so the `git fetch` this guard performs never leaves the temporary directory. Running the default env here would fetch from github.com once per push-shaped payload, twice (bash then Python), which is both slow and a source of disagreement that is not a port defect.
ENVS = [
    ("behind", {"CLAUDE_PROJECT_DIR": "{FIXTURE:drift-behind}"}, {}),
    ("ahead", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    ("synced", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-synced}"}, {}),
]

EDGE_CASES = [
    ("the plain push", "git push"),
    ("a push with arguments", "git push origin HEAD"),
    ("a push after &&", "npm run ci && git push"),
    # `--dry-run` is harmless.
    ("a dry run is harmless", "git push --dry-run"),
    # The resolver's arm: another repository's push is not this tree's drift.
    ("a push in a nested repository", "git -C nested push"),
    ("a cd into a nested repository", "cd nested && git push"),
    ("a push named as a word inside another", "git pushd"),
    ("a different git verb", "git fetch origin"),
]

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

    if not hookio.grep_q_line(PUSH, cmd):
        return hookio.ALLOW
    if hookio.grep_q_line(DRY_RUN, cmd):
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
    ev.warn_raw(MESSAGE % {"branch": branch, "ahead": ahead})
    return hookio.DENY
