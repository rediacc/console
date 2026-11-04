"""`./run.sh worktree lease`: one detached tree for one writer, under `.claude/worktrees` (PLAN-worktree-lease Design 2).

The console tree is a detached linked worktree at the live tip. Each submodule is a detached linked worktree of its module store (W0's `Decision: A`), so a gitlink on a local-only commit resolves and no shared config is written. Dependencies and build output come from `scripts/ci-runner/lease-seed.ts`. No branch, no devbox, no tmux.

Only the last stdout line is data: the tree's normalized absolute path. Everything else goes to stderr. A lease that cannot be finished is removed in W0's order and the exit is 1.

`worktree_spike` is the shared base: its git wrappers, its removal path, its refusal to delete outside the holder and its signal handling are the ones W0 proved on the live tree.
"""

from __future__ import annotations

import contextlib
import datetime
import fcntl
import importlib
import json
import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.dev import worktree_spike as spike

BASE_BRANCH = "main"
RECORD_DIR = "rediacc-worktrees"
SEED_ENTRY = pathlib.PurePath("scripts", "ci-runner", "lease-seed.ts")
TSX = pathlib.PurePath("node_modules", ".bin", "tsx")
# A link is not a directory, so a `.venv/` ignore rule misses it. These stay anchored, because a linked tree reads the main checkout's info/exclude.
EXCLUDE_LINES = ("/.ci/cache/toolchain", "/.ci/cache/bin", "/.venv")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GITLINK_MODE = "160000"
DEFAULT_OWNER = "cli"
SHOWN_ESCAPES = 5

LEASE_HELP = """\
Usage: ./run.sh worktree lease [--name <slug>] [--owner <id8>]

Make one detached tree under .claude/worktrees at the live branch's tip, with
each submodule at its gitlink and dependencies seeded. Uncommitted work in the
main checkout is not in it. The last stdout line is the tree's absolute path.

Options:
  --name <slug>   Tree id; default <owner>-<n>
  --owner <id8>   Owning session; default this session's id prefix
"""


class LeaseRefusedError(RuntimeError):
    """The lease was not made, and the message says why."""


@contextlib.contextmanager
def _locked(records):
    """One lease at a time through the cap and the name, so same-message spawns cannot both take the last slot."""
    records.mkdir(parents=True, exist_ok=True)
    with (records / ".lock").open("w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _hook_module(name):
    paths.on_sys_path(paths.hooks_stop_dir(paths.CI_DIR.parent))
    return importlib.import_module(name)


def live_tip(root):
    """The checked-out branch's commit, or on `main` or a detached HEAD the one live branch's, or `main` between branches."""
    branch = spike.out(root, "symbolic-ref", "-q", "--short", "HEAD")
    if not branch or branch == BASE_BRANCH:
        live = spike.load_commit_policy().live_branches(str(root), gh=False)
        if len(live) > 1:
            message = "several live branches, so no single tip: %s" % ", ".join(live)
            raise LeaseRefusedError(message)
        branch = live[0] if live else BASE_BRANCH
    return spike.must(root, "rev-parse", "--verify", "refs/heads/%s^{commit}" % branch)


def gitlinks_at(root, tip):
    """`(path, sha)` of every gitlink in `tip`."""
    found = []
    for line in spike.must(root, "ls-tree", "-r", "--full-tree", tip).splitlines():
        meta, _, rel = line.partition("\t")
        fields = meta.split()
        if fields and fields[0] == GITLINK_MODE:
            found.append((rel, fields[2]))
    return found


def trees_on_disk(holder):
    if not holder.is_dir():
        return []
    return sorted(p.name for p in holder.iterdir() if p.is_dir() and not p.is_symlink())


def _next_id(owner, trees, records):
    pattern = re.compile(r"^%s-(\d+)$" % re.escape(owner))
    names = [*trees, *(p.stem for p in records.glob("*.json"))]
    numbers = [int(m.group(1)) for m in map(pattern.match, names) if m]
    return "%s-%d" % (owner, max(numbers, default=0) + 1)


def _add_exclude_lines(git_dir):
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    text = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    missing = [line for line in EXCLUDE_LINES if line not in text.splitlines()]
    if missing:
        lead = "" if not text or text.endswith("\n") else "\n"
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write("%s%s\n" % (lead, "\n".join(missing)))


def _reserve(root, name, owner):
    """Under the lock: the cap, the id, and the empty directory that holds the slot."""
    holder = root / spike.HOLDER
    git_dir = root / ".git"
    records = git_dir / RECORD_DIR
    with _locked(records):
        holder.mkdir(parents=True, exist_ok=True)
        trees = trees_on_disk(holder)
        cap = _hook_module("wl_roster").writer_cap(root)
        if len(trees) >= cap:
            message = (
                "%d tree(s) on disk at writer_cap %d: land the finished ones, then ./run.sh worktree gc"
                % (
                    len(trees),
                    cap,
                )
            )
            raise LeaseRefusedError(message)
        lease_id = name or _next_id(owner, trees, records)
        path = holder / lease_id
        if os.path.lexists(path) or (records / ("%s.json" % lease_id)).exists():
            message = "lease %s already exists" % lease_id
            raise LeaseRefusedError(message)
        path.mkdir()
        _add_exclude_lines(git_dir)
    return lease_id, path


def _add_tree(store, path, sha, lease_id):
    spike.must(
        store,
        *("worktree", "add", "--detach", "--lock", "--reason", "lease:%s" % lease_id),
        *(str(path), sha),
    )


def _run_seed(path, root, tip):
    code = paths.CI_DIR.parent
    tsx, entry = code / TSX, code / SEED_ENTRY
    for needed in (tsx, entry):
        if not needed.exists():
            message = "the seed needs %s" % needed
            raise LeaseRefusedError(message)
    env = {k: v for k, v in os.environ.items() if k not in spike.SCRUBBED_ENV}
    done = subprocess.run(
        [str(tsx), str(entry), str(path), str(root), tip],
        cwd=str(code),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        check=False,
        timeout=spike.GIT_TIMEOUT,
    )
    if done.returncode != 0:
        message = "lease-seed.ts exited %d" % done.returncode
        raise LeaseRefusedError(message)


def _packages(modules):
    """Top-level package names in a `node_modules`: `name` and `@scope/name`, never a dot entry."""
    found = []
    for entry in sorted(modules.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name.startswith("@") and entry.is_dir():
            found += ["%s/%s" % (entry.name, child.name) for child in sorted(entry.iterdir())]
        else:
            found.append(entry.name)
    return found


def upward_escapes(root, path):
    """What a lease would read from the live tree: Node's upward walk from `<main>/.claude/worktrees/<id>` passes three outer `node_modules`, and only the live root's is expected to exist."""
    found = [
        str(outer)
        for outer in (
            root / ".claude" / "node_modules",
            root / spike.HOLDER / "node_modules",
        )
        if os.path.lexists(outer)
    ]
    live = root / "node_modules"
    if live.is_dir():
        inside = path / "node_modules"
        found += [p for p in _packages(live) if not os.path.lexists(inside / p)]
    return found


def _verify(path, root, tip, shas):
    """What the writer is promised, read back from the finished tree."""
    trees = [(path, tip), *((path / sub, sha) for sub, sha in shas.items())]
    for tree, sha in trees:
        head = spike.out(tree, "rev-parse", "HEAD")
        if head != sha or spike.git(tree, "symbolic-ref", "-q", "HEAD").returncode == 0:
            message = "%s is not detached at %s (HEAD %s)" % (tree, sha, head or "unreadable")
            raise LeaseRefusedError(message)
    status = spike.must(path, "status", "--porcelain")
    if status:
        message = "the tree is not clean after the seed: %s" % " | ".join(status.splitlines()[:3])
        raise LeaseRefusedError(message)
    escapes = upward_escapes(root, path)
    if escapes:
        shown = ", ".join(escapes[:SHOWN_ESCAPES])
        message = (
            "%d name(s) would resolve upward to the live tree, because the seed left them out of the lease: %s. An `npm install` in the main checkout brings the live install back to the lockfile"
            % (len(escapes), shown)
        )
        raise LeaseRefusedError(message)


def _write_record(root, record):
    records = root / ".git" / RECORD_DIR
    target = records / ("%s.json" % record["id"])
    partial = records / (".%s.partial" % record["id"])
    partial.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(target)


def _rollback(repo, path):
    """Whatever state the lease reached. Locks go first, because a locked tree refuses removal."""
    spike.hold_signals()
    for store, tree in (
        *((repo.store(sub), path / sub) for sub in repo.submodules),
        (repo.root / ".git", path),
    ):
        spike.git(store, "worktree", "unlock", str(tree))
    survived = spike.remove_lease(repo, path)
    for suffix in (".deps.json", ".builds.json"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    return survived


def make_lease(root, *, name="", owner="", agent=""):
    """Make one tree and return its normalized absolute path. Raises `LeaseRefusedError`, with nothing left behind, when it cannot."""
    root = pathlib.Path(os.path.realpath(root))
    if not (root / ".git").is_dir():
        message = "%s is not a main checkout" % root
        raise LeaseRefusedError(message)
    for link in (root / ".claude", root / spike.HOLDER):
        if link.is_symlink():
            message = "%s is a symlink, which the harness refuses" % link
            raise LeaseRefusedError(message)
    tip = live_tip(root)
    links = gitlinks_at(root, tip)
    held = [(sub, sha) for sub, sha in links if (root / ".git" / "modules" / sub).is_dir()]
    for sub in sorted({sub for sub, _ in links} - {sub for sub, _ in held}):
        log.warn("%s has no module store, so its directory stays empty in the lease" % sub)
    repo = spike.Repo(root, [sub for sub, _ in held])
    lease_id, path = _reserve(root, name, owner)
    spike.arm_signals()
    try:
        _add_tree(root, path, tip, lease_id)
        for sub, sha in held:
            _add_tree(repo.store(sub), path / sub, sha, lease_id)
        _run_seed(path, root, tip)
        _verify(path, root, tip, dict(held))
        _write_record(
            root,
            {
                "id": lease_id,
                "path": str(path),
                "owner": owner,
                "agent": agent,
                "base": {".": tip, **dict(held)},
                "created_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
    except (OSError, RuntimeError, subprocess.SubprocessError, spike.InterruptedRunError) as exc:
        survived = _rollback(repo, path)
        left = "; left behind: %s" % ", ".join(survived) if survived else ""
        message = "lease %s not made: %s%s" % (lease_id, exc, left)
        raise LeaseRefusedError(message) from exc
    return str(path)


def _default_owner():
    return _hook_module("wl_core").resolve_session_id()[:8] or DEFAULT_OWNER


def _parse(args):
    """`{"name": ..., "owner": ...}`, or None after an error line (D4: anything else is refused)."""
    values = {"name": "", "owner": ""}
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        key = arg[2:] if arg in ("--name", "--owner") else ""
        if not key:
            log.error("Unknown option: %s" % arg)
            return None
        if not rest:
            log.error("%s needs a value" % arg)
            return None
        value = rest.pop(0)
        if not ID_RE.match(value) or value.startswith(spike.PREFIX):
            log.error("Invalid %s: %s (one path component, never %s*)" % (key, value, spike.PREFIX))
            return None
        values[key] = value
    return values


def cmd_lease(args):
    values = _parse(args)
    if values is None:
        return 1
    try:
        path = make_lease(
            paths.repo_root(),
            name=values["name"],
            owner=values["owner"] or _default_owner(),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    sys.stdout.write(path + "\n")
    sys.stdout.flush()
    return 0


PIN_HELP = """\
Usage: ./run.sh worktree pin

Move this lease tree's pin, refs/worktrees/<id>, forward to its HEAD. The
post-commit hook runs this after every commit in a lease; a HEAD the pin is not
an ancestor of leaves the pin in place.
"""


def move_pin(directory):
    """Move the pin of the lease tree `directory` sits in to that tree's HEAD, and return the ref's value afterwards.

    The ref lands in the store of the repository `directory` belongs to: the console's refs for the console tree, the module store for a submodule tree, since each is a linked tree of that store (W0's `Decision: A`).

    FORWARD ONLY. A HEAD the pin is not an ancestor of leaves the pin in place, so the commits it holds stay reachable, and the HEAD is a second tip for GC to judge. The old value is passed to `update-ref`, so a concurrent move fails instead of being overwritten.
    """
    lease_tree = spike.load_commit_policy().lease_root(str(directory))
    if not lease_tree:
        message = "%s is in no lease tree, so it holds no pin" % directory
        raise LeaseRefusedError(message)
    ref = spike.PIN_SPACE + os.path.basename(lease_tree)
    head = spike.must(directory, "rev-parse", "--verify", "HEAD^{commit}")
    old = spike.out(directory, "rev-parse", "--verify", "-q", "%s^{commit}" % ref)
    if old == head:
        return head
    if old and spike.git(directory, "merge-base", "--is-ancestor", old, head).returncode != 0:
        log.warn("%s stays at %s: HEAD %s does not descend from it" % (ref, old, head))
        return old
    spike.must(directory, "update-ref", ref, head, old)
    return head


def cmd_pin(args):
    if args:
        log.error("Unknown option: %s" % args[0])
        return 1
    try:
        move_pin(os.getcwd())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    return 0


LAND_HELP = """\
Usage: ./run.sh worktree land <id>

Read-only. Check that every unlanded commit of the lease carries a PR-TASK
trailer and touches no gitlink and no agent/** path, then print the commands
that land them, submodules first: the cherry-picks (-x, so the source sha is
read as landed after a conflict), the gitlink commit, then the console's own
cherry-picks. Nothing is run. A refusal prints nothing to stdout and exits 1.
"""
AGENT_PREFIX = "agent/"
TRAILER_KEY = "PR-TASK"


def unlanded(tree, head, pin, tip, base):
    """The commits of `head` and `pin` the live `tip` does not hold, by the Stop hook's own reader (patch-id, then the `-x` line), or None when git could not say."""
    return _hook_module("wl_worktrees").unlanded_commits(tree, head, pin, tip, base)


def _ordered(tree, shas, tip):
    """`shas` oldest first, in the order a pick must run."""
    if not shas:
        return []
    listed = spike.must(tree, "rev-list", "--reverse", "--topo-order", *shas, "--not", tip)
    return [sha for sha in listed.splitlines() if sha in shas]


def _problems(tree, sha):
    """What makes `sha` refused for landing, one phrase each."""
    found = []
    trailers = spike.must(tree, "show", "-s", "--format=%B", sha)
    parsed = subprocess.run(
        ["git", "-C", str(tree), "interpret-trailers", "--parse"],
        input=trailers,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    if not any(line.startswith(TRAILER_KEY + ":") for line in parsed.splitlines()):
        found.append("no %s trailer" % TRAILER_KEY)
    raw = spike.must(tree, "diff-tree", "-r", "--root", "-m", "--no-commit-id", "--raw", "-z", sha)
    fields = raw.split("\0")
    for meta, rel in zip(fields[0::2], fields[1::2], strict=False):
        modes = meta.lstrip(":").split()[:2]
        if GITLINK_MODE in modes:
            found.append("touches the gitlink %s" % rel)
        if rel.startswith(AGENT_PREFIX):
            found.append("touches %s" % rel)
    return found


def _merges(tree, live, key, lease_id):
    """A merge in the lease, refused by name. `git cherry` omits merges, so the landed reader never lists one, and picking the commits around it would silently lose whatever the merge resolved."""
    tips = [spike.out(tree, "rev-parse", "HEAD")]
    pin = spike.out(
        tree, "rev-parse", "--verify", "-q", "%s%s^{commit}" % (spike.PIN_SPACE, lease_id)
    )
    tips += [pin] if pin else []
    tip = spike.out(live, "rev-parse", "HEAD")
    listed = spike.out(tree, "rev-list", "--merges", *tips, "--not", tip)
    return ["%s %s: is a merge" % (key, sha[:12]) for sha in listed.splitlines()]


def _repo_plan(root, record, key):
    """`(lease tree, live checkout, shas oldest first)` for one repo of a lease, or None when the lease holds none there."""
    tree = pathlib.Path(record["path"]) if key == "." else pathlib.Path(record["path"]) / key
    live = root if key == "." else root / key
    if not tree.is_dir() or not live.is_dir():
        return None
    tip = live_tip(root) if key == "." else spike.out(live, "rev-parse", "HEAD")
    head = spike.out(tree, "rev-parse", "HEAD")
    pin = spike.out(
        tree, "rev-parse", "--verify", "-q", "%s%s^{commit}" % (spike.PIN_SPACE, record["id"])
    )
    shas = unlanded(tree, head, pin, tip, record.get("base", {}).get(key, ""))
    if shas is None:
        message = "git could not say what %s holds that %s lacks" % (tree, tip[:12])
        raise LeaseRefusedError(message)
    return tree, live, _ordered(tree, shas, tip)


def land_plan(root, lease_id):
    """The lines to run, or raises `LeaseRefusedError` naming every refused commit. Nothing is written."""
    root = pathlib.Path(os.path.realpath(root))
    path = root / ".git" / RECORD_DIR / ("%s.json" % lease_id)
    if not ID_RE.match(lease_id) or not path.is_file():
        message = "no lease record %s" % lease_id
        raise LeaseRefusedError(message)
    record = json.loads(path.read_text(encoding="utf-8"))
    keys = [*sorted(k for k in record.get("base", {}) if k != "."), "."]
    plans = {}
    refused = []
    for key in keys:
        plan = _repo_plan(root, record, key)
        if plan is None:
            continue
        plans[key] = plan
        refused += _merges(plan[0], plan[1], key, record["id"])
        refused += [
            "%s %s: %s" % (key, sha[:12], ", ".join(why))
            for sha in plan[2]
            if (why := _problems(plan[0], sha))
        ]
    if refused:
        raise LeaseRefusedError("; ".join(refused))
    lines = []
    for key in keys:
        if key not in plans or not plans[key][2]:
            continue
        shas = " ".join(plans[key][2])
        if key == ".":
            lines.append("git cherry-pick -x %s" % shas)
        else:
            # A pick on a detached checkout moves no branch, so the submodule takes the console's name first, which `_judge_local` admits (Design 3).
            if not spike.out(root / key, "symbolic-ref", "-q", "HEAD"):
                branch = spike.must(root, "symbolic-ref", "--short", "HEAD")
                lines.append("git -C %s switch -c %s" % (key, branch))
            lines += [
                "git -C %s cherry-pick -x %s" % (key, shas),
                "git add -- %s" % key,
                "git commit -F <msg> -- %s" % key,
            ]
    return lines


def cmd_land(args):
    if len(args) != 1 or args[0].startswith("-"):
        log.error("land takes one lease id")
        return 1
    try:
        lines = land_plan(paths.repo_root(), args[0])
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    if not lines:
        log.info("nothing to land in %s" % args[0])
    sys.stdout.write("".join(line + "\n" for line in lines))
    sys.stdout.flush()
    return 0


def main(argv):
    """The hook's way in, since a hook loaded by file has no package to import this from."""
    if argv[:1] == ["pin"]:
        return cmd_pin(argv[1:])
    if argv[:1] == ["land"]:
        return cmd_land(argv[1:])
    log.error("Unknown command: %s" % " ".join(argv))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
