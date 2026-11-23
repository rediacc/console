"""The test tables of `warn_remote_drift`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

import subprocess


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
