"""Refuse a console `git push` whose commits pin a submodule commit that submodule's remote does not have.

THE INCIDENT, 2026-09-28. Console `6a94a96a9` bumped the `private/renet` gitlink to `6f715a0` and was pushed before renet `6f715a0` was. CI's Initialize job checked out the pushed commit, ran the submodule update, and failed with "Failed to initialize submodules" right after `private/homebrew-tap` (job 109008042592): the runner cannot fetch a commit no remote branch reaches. A whole CI round was lost, and nothing local caught it. `git config push.recurseSubmodules check` makes git itself refuse such a push, but it is per-clone config that nothing sets and nothing enforces; this guard is the enforced copy of that check.

WHAT "THE COMMITS BEING PUSHED" MEANS HERE. CI checks out the TIP of the pushed ref and initializes the submodules at the gitlinks that tip records, so the tip's gitlinks are the whole question. Each is compared against the same path in the remote-tracking ref the push updates (`refs/remotes/<remote>/<dst>`, falling back to `<remote>/main` for a branch's first push, which is where every `MMDD-N` branch forks from). Only a gitlink that CHANGED is checked: an unchanged one was already reachable when the remote ref was last pushed, and checking every submodule on every push would pay for five repositories to learn about one.

WHAT "THE REMOTE HAS IT" MEANS, and why no fetch. The pinned sha must be an ancestor of some remote-tracking branch in the submodule clone: `git -C <sub> for-each-ref --contains <sha> --count=1 refs/remotes/`, one local ref walk (measured at 3 ms on private/renet). That is the same test `push.recurseSubmodules=check` applies, and it is correct in the direction that matters: a sha this clone's own `git push` published is in a remote-tracking ref at once, because the push updates it. The residual is the opposite direction -- a pin that ANOTHER machine pushed and this clone never fetched -- and the refusal names the `git fetch` that clears it. A fetch inside the guard was rejected: it writes refs, it would put the network on the path of every console push, and a PreToolUse hook that can hang on a slow remote is an outage in waiting.

ONLY THIS REPOSITORY'S PUSHES. A push whose git invocation resolves (through its own `cd`/`-C`, or the payload's cwd) to any other toplevel -- a submodule under `private/`, a scratch repo in /tmp -- is not this guard's business, the same scoping `block_unverified_push` and `block_second_branch` apply.

TESTED BY `test-block_unpushed_submodule_pin.py` beside this file, which rebuilds the 6a94a96a9 shape on disk and walks it through publish, first push, detached HEAD and deinitialized-submodule worlds.

FAILS OPEN on every environmental error: git missing or failing, a detached HEAD on a bare `git push`, a source that does not resolve, no remote-tracking ref to diff against, a submodule directory that is not an initialized clone, a pinned object absent from that clone. Each is a question this machine cannot answer, and a guard against a lost CI round must never become an outage that stops every push.
"""

import os

from rediacc_hooks import commit_policy, hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
# Last in the chain. A pin the submodule remote lacks fails CI whatever the receipt says, but moving it ahead of block_unverified_push would re-key eleven guards for an ordering nothing depends on: the dispatcher reports every refusal, and this one's message stands on its own.
ORDER = 50

# The containment verdict is the whole guard. With it gone every pin passes, which is the state that let 6a94a96a9 reach CI.
DEFECT = ("if missing:", "if False:")

GITLINK_MODE = "160000"
DRY_RUN_FLAGS = frozenset(("--dry-run", "-n"))
NO_TIP_FLAGS = frozenset(("--delete", "-d", "--tags"))
PUSH_WITH_VALUE = frozenset(("--repo", "-o", "--push-option", "--receive-pack", "--exec"))

_FIXTURE_DATE = "2026-01-01T00:00:00+00:00"


def _fixture_git(cwd, *args):
    import subprocess  # noqa: PLC0415 -- fixture-only; the guard's own path forks through hookio

    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_AUTHOR_DATE=_FIXTURE_DATE,
        GIT_COMMITTER_DATE=_FIXTURE_DATE,
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    done = subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True, env=env
    )
    return done.stdout.strip()


def _pinned_world(path, published):
    """The 6a94a96a9 shape: branch `0923-1` bumps `private/renet` from a published sha to a local-only one.

    Remote-tracking refs are written with `update-ref`, never by pushing: a fixture that pushed would itself be a push this chain judges. `published=True` is the same world after `git -C private/renet push`: the pinned sha is then reachable from a remote-tracking branch.
    """
    path.mkdir(parents=True)
    _fixture_git(path, "init", "-q", "--initial-branch=main")
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _fixture_git(path, "add", "seed.txt")
    sub = path / "private" / "renet"
    sub.mkdir(parents=True)
    _fixture_git(sub, "init", "-q", "--initial-branch=main")
    _fixture_git(sub, "commit", "-q", "--allow-empty", "-m", "published")
    old = _fixture_git(sub, "rev-parse", "HEAD")
    _fixture_git(sub, "update-ref", "refs/remotes/origin/main", old)
    _fixture_git(sub, "checkout", "-q", "-b", "0923-1")
    _fixture_git(sub, "commit", "-q", "--allow-empty", "-m", "local only")
    new = _fixture_git(sub, "rev-parse", "HEAD")
    if published:
        _fixture_git(sub, "update-ref", "refs/remotes/origin/0923-1", new)
    _fixture_git(
        path, "update-index", "--add", "--cacheinfo", "%s,%s,private/renet" % (GITLINK_MODE, old)
    )
    _fixture_git(path, "commit", "-q", "-m", "pin published")
    _fixture_git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    _fixture_git(path, "checkout", "-q", "-b", "0923-1")
    _fixture_git(path, "update-index", "--cacheinfo", "%s,%s,private/renet" % (GITLINK_MODE, new))
    _fixture_git(path, "commit", "-q", "-m", "bump renet")
    return path


FIXTURES = {
    "submodule-pin-unpushed": lambda p: _pinned_world(p, published=False),
    "submodule-pin-pushed": lambda p: _pinned_world(p, published=True),
}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("pin-unpushed", {"CLAUDE_PROJECT_DIR": "{FIXTURE:submodule-pin-unpushed}"}, {}),
    ("pin-pushed", {"CLAUDE_PROJECT_DIR": "{FIXTURE:submodule-pin-pushed}"}, {}),
    ("no-submodule", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]

EDGE_CASES = [
    ("a plain push of the branch", "git push origin 0923-1"),
    ("a bare push", "git push"),
    ("an explicit refspec", "git push origin HEAD:0923-1"),
    ("a forced push is still a push", "git push --force-with-lease origin 0923-1"),
    ("a wrapper payload is still scanned", "sh -c 'git push origin 0923-1'"),
    # Controls: none of these publish a console tip.
    ("a dry run", "git push --dry-run origin 0923-1"),
    ("a delete", "git push origin --delete 0923-1"),
    ("tags only", "git push --tags origin"),
    ("prose about pushing", "echo 'git push origin 0923-1 once renet is up'"),
    ("git pull is not git push", "git pull --rebase"),
    ("a push inside the submodule, by -C", "git -C private/renet push origin 0923-1"),
    ("a push inside the submodule, by cd", "cd private/renet && git push origin 0923-1"),
    ("a push in another tree", "cd /tmp && git push"),
]


def _git(args, cwd):
    return hookio.git_out(args, cwd=cwd, want_rc=True)


def _same(a, b):
    return os.path.realpath(a) == os.path.realpath(b)


def _remote_and_refspecs(args):
    """`(remote, refspecs)` for `git push <args>`; remote "" when none is named."""
    positionals = []
    k = 0
    while k < len(args):
        arg = args[k]
        if arg == "--":
            positionals.extend(args[k + 1 :])
            break
        if arg in PUSH_WITH_VALUE:
            k += 2
            continue
        if not arg.startswith("-"):
            positionals.append(arg)
        k += 1
    return (positionals[0] if positionals else ""), positionals[1:]


def _targets(root, args):
    """`[(remote, src, dst)]` the push would publish, or [] when it publishes no branch tip."""
    if any(a in DRY_RUN_FLAGS or a in NO_TIP_FLAGS for a in args):
        return []
    branch = commit_policy.current_branch(root)
    remote, specs = _remote_and_refspecs(args)
    if remote == "":
        remote = (
            (_git(["config", "branch.%s.remote" % branch], root) or "origin")
            if branch
            else "origin"
        )
    if not specs:
        # `--all`/`--mirror` and a bare push both publish the checked-out branch, which is the tip a session is judged on; other local branches are not what CI runs for this push.
        return [(remote, "HEAD", branch)] if branch else []
    out = []
    for raw in specs:
        src, colon, dst = raw.removeprefix("+").partition(":")
        if src == "":
            continue
        if not colon:
            dst = branch if src == "HEAD" else src
        if dst.startswith("refs/") and not dst.startswith("refs/heads/"):
            continue
        dst = dst.removeprefix("refs/heads/")
        if dst:
            out.append((remote, src, dst))
    return out


def _base_ref(root, remote, dst):
    for ref in ("refs/remotes/%s/%s" % (remote, dst), "refs/remotes/%s/main" % remote):
        if _git(["rev-parse", "-q", "--verify", ref + "^{commit}"], root):
            return ref
    return None


def _changed_gitlinks(root, base, tip):
    """`[(path, sha)]` for every gitlink `tip` records that differs from `base`'s."""
    out = _git(["diff-tree", "-r", "-z", "--no-commit-id", base, tip], root)
    if not out:
        return []
    fields = out.split("\0")
    pins = []
    for k in range(0, len(fields) - 1, 2):
        meta, path = fields[k].split(" "), fields[k + 1]
        if len(meta) >= 4 and meta[1] == GITLINK_MODE and meta[3] != "0" * len(meta[3]):
            pins.append((path, meta[3]))
    return pins


def _unpublished(root, path, sha):
    """True when submodule `path` has `sha` and no remote-tracking branch reaches it; False on any doubt."""
    sub = os.path.join(root, path)
    top = _git(["rev-parse", "--show-toplevel"], sub) if os.path.isdir(sub) else None
    # An uninitialized submodule directory resolves to the SUPERPROJECT, whose refs say nothing about the submodule's remote.
    if not top or not _same(top, sub):
        return False
    if _git(["cat-file", "-e", sha + "^{commit}"], sub) is None:
        return False
    found = _git(
        ["for-each-ref", "--contains", sha, "--count=1", "--format=%(refname)", "refs/remotes/"],
        sub,
    )
    return found == ""


def _refusal(missing):
    lines = [
        "BLOCKED: this push pins submodule commit(s) that the submodule's remote does not have.",
        "",
    ]
    for path, sha, _, _ in missing:
        lines.append(
            "  %s -> %s (not reachable from any refs/remotes/* branch there)" % (path, sha)
        )
    lines += [
        "",
        "CI checks out the pushed tip and initializes submodules at these gitlinks, and a",
        "commit no remote branch reaches cannot be fetched: Initialize fails with",
        "'Failed to initialize submodules' and the whole round is lost (console 6a94a96a9,",
        "2026-09-28, renet 6f715a0 pushed after the pointer bump).",
        "",
        "Push each submodule commit first, then this push:",
    ]
    for path, sha, dst, sub_branch in missing:
        lines.append("  git -C %s push origin %s:refs/heads/%s" % (path, sha, sub_branch or dst))
    lines += [
        "",
        "If the commit IS already on the remote (pushed from another clone), refresh the",
        "remote-tracking refs and retry:",
    ]
    for path in dict.fromkeys(m[0] for m in missing):
        lines.append("  git -C %s fetch origin" % path)
    return "\n".join(lines) + "\n"


def run(ev):
    cmd = ev.raw("tool_input", "command")
    # Cheap pre-filter: this hook runs on every Bash call, and the walk below is only worth paying for a command that could be a push at all.
    if cmd in ("", "null") or "push" not in cmd:
        return hookio.ALLOW
    state = shellscan.hook_init(ev.payload)
    if state is None:
        return hookio.ALLOW
    cmd, _ = state

    root = ev.project_dir
    top = _git(["rev-parse", "--show-toplevel"], root)
    if not top:
        return hookio.ALLOW
    root = top
    base_dir = ev.raw("cwd")
    if base_dir in ("", "null") or not os.path.isdir(base_dir):
        base_dir = root

    missing = []
    for run_ in commit_policy.git_runs(cmd, "push"):
        repo = commit_policy.run_repo(run_, base_dir)
        if not repo or not _same(repo, root):
            continue
        _, _, args = commit_policy.git_split(run_.argv)
        for remote, src, dst in _targets(root, args):
            tip = _git(["rev-parse", "-q", "--verify", src + "^{commit}"], root)
            base = _base_ref(root, remote, dst)
            if not tip or not base:
                continue
            for path, sha in _changed_gitlinks(root, base, tip):
                if _unpublished(root, path, sha):
                    sub_branch = commit_policy.current_branch(os.path.join(root, path))
                    missing.append((path, sha, dst, sub_branch))

    if missing:
        ev.warn_raw(_refusal(missing))
        return hookio.DENY
    return hookio.ALLOW
