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

CHAIN = "pre-bash"
ORDER = 19

# Remote strictly behind local is a NORMAL push of new commits. Without this arm every push of anything ever is refused as drift, which makes the guard an outage rather than a check -- the exact failure its own header forbids.
DEFECT = ("if _is_ancestor(remote, local, root):", "if False:")


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
            # Pinned dates make every fixture commit id the same on every run, and the lease refusal names one of them.
            "GIT_AUTHOR_DATE": "2026-08-31T12:00:00Z",
            "GIT_COMMITTER_DATE": "2026-08-31T12:00:00Z",
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


def _rebased_tree(path, peer_commit=False):
    """A checkout whose branch was rebased locally after it was pushed, so origin holds the pre-rebase commits.

    `main` gains a commit after `0831-1` is pushed, and `0831-1` is then rebased onto it: `HEAD..origin/0831-1` is the two pre-rebase commits, each patch-equivalent to a rebased one. With `peer_commit` a second clone also pushes a commit onto the pre-rebase branch, which no local commit matches.
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
    _fixture_git(path, "push", "-q", "origin", "main")
    _fixture_git(path, "checkout", "-q", "-b", "0831-1")
    for name in ("one", "two"):
        (path / ("%s.txt" % name)).write_text("%s\n" % name, encoding="utf-8")
        _fixture_git(path, "add", "%s.txt" % name)
        _fixture_git(path, "commit", "-q", "-m", "branch work %s" % name)
    _fixture_git(path, "push", "-q", "origin", "0831-1")

    _fixture_git(path, "checkout", "-q", "main")
    (path / "main.txt").write_text("main moved\n", encoding="utf-8")
    _fixture_git(path, "add", "main.txt")
    _fixture_git(path, "commit", "-q", "-m", "main moves on")
    _fixture_git(path, "push", "-q", "origin", "main")
    _fixture_git(path, "checkout", "-q", "0831-1")
    _fixture_git(path, "rebase", "-q", "main")

    if peer_commit:
        peer = path.parent / (path.name + ".peer")
        _fixture_git(path.parent, "clone", "-q", str(bare), str(peer))
        _fixture_git(peer, "checkout", "-q", "0831-1")
        (peer / "peer.txt").write_text("peer\n", encoding="utf-8")
        _fixture_git(peer, "add", "peer.txt")
        _fixture_git(peer, "commit", "-q", "-m", "a peer commit no rebase produced")
        _fixture_git(peer, "push", "-q", "origin", "0831-1")
    return path


def _peer_plus_rebase_tree(path):
    """`_rebased_tree` with a peer commit on the remote branch that has no local equivalent."""
    return _rebased_tree(path, peer_commit=True)


FIXTURES = {
    "drift-behind": _behind_tree,
    "drift-rebased": _rebased_tree,
    "drift-peer-plus-rebase": _peer_plus_rebase_tree,
}

# THREE WORLDS, AND NO LIVE ONE. Every variant points CLAUDE_PROJECT_DIR at a fixture with a local bare origin, so the `git fetch` this guard performs never leaves the temporary directory. Running the default env here would fetch from github.com once per push-shaped payload, twice (bash then Python), which is both slow and a source of disagreement that is not a port defect.
ENVS = [
    ("behind", {"CLAUDE_PROJECT_DIR": "{FIXTURE:drift-behind}"}, {}),
    ("ahead", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    ("synced", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-synced}"}, {}),
    ("rebased", {"CLAUDE_PROJECT_DIR": "{FIXTURE:drift-rebased}"}, {}),
    ("peer-plus-rebase", {"CLAUDE_PROJECT_DIR": "{FIXTURE:drift-peer-plus-rebase}"}, {}),
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
    # The lease republish: allowed on a pure rebase, refused when the remote holds work no local commit matches.
    ("a lease push of the branch", "git push --force-with-lease origin 0831-1"),
    (
        "a lease push with an expected sha",
        "git push --force-with-lease=0831-1:abc123 origin 0831-1",
    ),
    ("a lease push of HEAD to the branch", "git push --force-with-lease origin HEAD:0831-1"),
    ("a lease push after &&", "npm run ci && git push --force-with-lease origin 0831-1"),
    # The words inside a program's string are not a push (#a1ac21ce).
    ("a python program naming a push", "python3 -c \"print('git push origin 0831-1')\""),
    # The 2026-10-03 republish: a redirect and a pipe after the push are not positionals.
    (
        "a lease push with a redirect and a pipe",
        "git push --force-with-lease origin 0831-1 2>&1 | tail -3",
    ),
    # A plain push of a rebase must not slip through on the lease arm.
    ("a plain push of the branch", "git push origin 0831-1"),
    ("a lease push to another remote", "git push --force-with-lease upstream 0831-1"),
    ("a lease push of another branch", "git push --force-with-lease origin main"),
    ("a lease push with a plain force too", "git push --force --force-with-lease origin 0831-1"),
    # git's own parse of the push (#9de9a8e9): the last of a flag and its negation wins, a unique prefix is the option, a bundle carries a short one.
    ("a dry run undone by --no-dry-run", "git push --dry-run --no-dry-run"),
    ("a dry run, short flag", "git push -n"),
    ("a dry run by unique prefix", "git push --dry"),
    ("a lease by unique prefix", "git push --force-with origin 0831-1"),
    ("a lease push with a bundled force", "git push -uf --force-with-lease origin 0831-1"),
    (
        "a lease taken back by --no-force-with-lease",
        "git push --force-with-lease --no-force-with-lease origin 0831-1",
    ),
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
        if commit_policy.run_repo(r, this_root) == this_root
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
