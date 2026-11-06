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
import signal
import subprocess
import sys
import time
from typing import NamedTuple

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
CONSOLE = "."
DEFAULT_OWNER = "cli"
SHOWN_ESCAPES = 5

LEASE_HELP = """\
Usage: ./run.sh worktree lease [--name <slug>] [--owner <id8>]

Make one detached tree under .claude/worktrees at the live branch's tip, with
each submodule at its gitlink and dependencies seeded. Uncommitted work in the
main checkout is not in it. The last stdout line is the tree's absolute path.
A submodule with no module store is refused, since no tree can hold its gitlink:
`git submodule update --init -- <path>` in the main checkout brings the store.

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
        # The directory comes last: no `try` covers this function, and an empty one left behind holds a slot `trees_on_disk` counts.
        _add_exclude_lines(git_dir)
        path.mkdir()
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
    """Whatever state the lease reached. Locks go first, because a locked tree refuses removal. The signals are held for the rollback and restored after, so an ignored SIGTERM never outlives it."""
    before = _signal_handlers()
    spike.hold_signals()
    try:
        return _rollback_held(repo, path)
    finally:
        _restore_signal_handlers(before)


def _rollback_held(repo, path):
    for store, tree in (
        *((repo.store(sub), path / sub) for sub in repo.submodules),
        (repo.root / ".git", path),
    ):
        spike.git(store, "worktree", "unlock", str(tree))
    survived = spike.remove_lease(repo, path)
    for suffix in (".deps.json", ".builds.json"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    return survived


def _holding_checkout(root):
    """The main checkout whose holder contains the lease tree `root` sits in, or None. `lease_root` answers only for a linked tree of that checkout's own stores."""
    lease = spike.load_commit_policy().lease_root(str(root))
    return pathlib.Path(lease).parents[len(spike.HOLDER.parts)] if lease else None


def _main_checkout(root):
    """`root` normalized, or a refusal when it is no main checkout or its holder is a symlink."""
    root = pathlib.Path(os.path.realpath(root))
    if not (root / ".git").is_dir():
        message = "%s is not a main checkout" % root
        main = _holding_checkout(root)
        if main is not None:
            message += ": it is a lease tree, so run this in the main checkout %s" % main
        raise LeaseRefusedError(message)
    for link in (root / ".claude", root / spike.HOLDER):
        if link.is_symlink():
            message = "%s is a symlink, which the harness refuses" % link
            raise LeaseRefusedError(message)
    return root


def _store_of(root, sub):
    """The module store of `sub`, or None. `Repo.store` asks git from inside the directory, and from an uninitialized submodule's empty one git walks up and answers the console's own store."""
    store = pathlib.Path(os.path.realpath(spike.Repo(root, []).store(sub)))
    return store if store.is_dir() and store != root / ".git" else None


def make_lease(root, *, name="", owner="", agent=""):
    """Make one tree and return its normalized absolute path. Raises `LeaseRefusedError`, with nothing left behind, when it cannot."""
    root = _main_checkout(root)
    tip = live_tip(root)
    held = gitlinks_at(root, tip)
    # Design 2 step 4 names no exception, and an empty directory would pass `_verify` while the writer reads no code there.
    absent = sorted(sub for sub, _ in held if _store_of(root, sub) is None)
    if absent:
        message = (
            "no module store for %s, so no tree can hold the gitlink: git submodule update --init -- %s"
            % (", ".join(absent), " ".join(absent))
        )
        raise LeaseRefusedError(message)
    repo = spike.Repo(root, [sub for sub, _ in held])
    lease_id, path = _reserve(root, name, owner)
    # The lease's own handler for the build, then each signal goes back to what the caller had (as _remove_row does): left armed, a caller's later SIGINT raised the lease's InterruptedRunError long after the lease was made.
    before = _signal_handlers()
    spike.arm_signals()
    try:
        return _make_lease_armed(root, repo, held, tip, path, lease_id, owner, agent)
    finally:
        _restore_signal_handlers(before)


def _signal_handlers():
    """The current SIGINT, SIGTERM and SIGHUP dispositions, for `_restore_signal_handlers`."""
    return {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}


def _restore_signal_handlers(before):
    for signum, handler in before.items():
        signal.signal(signum, handler)


def _make_lease_armed(root, repo, held, tip, path, lease_id, owner, agent):
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
                "base": {CONSOLE: tip, **dict(held)},
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
    """This session's id prefix. It becomes a path component through `_next_id`, so it passes the rule `--owner` passes."""
    owner = _hook_module("wl_core").resolve_session_id()[:8]
    if owner and (not ID_RE.match(owner) or owner.startswith(spike.PREFIX)):
        message = "the session id prefix %r is no path component, so name one with --owner" % owner
        raise LeaseRefusedError(message)
    return owner or DEFAULT_OWNER


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
Usage: ./run.sh worktree land <id> [--ticks [--run]]

Read-only. Check that every unlanded commit of the lease carries a PR-TASK
trailer and a valid Plan-Box trailer and touches no gitlink and no agent/**
path, then print the commands that land them, submodules first: the
cherry-picks (-x, so the source sha is read as landed after a conflict), the
gitlink commit, then the console's own cherry-picks. Nothing is run. A
refusal prints nothing to stdout and exits 1.

A Plan-Box trailer names the plan box the commit serves, one per box:
  Plan-Box: <PLAN-file>.md#<sig8> clauses=<C1,C2,...|all>
  Plan-Box: none -- <reason, at least 12 characters>
The plan must exist under agent/plans/, the sig must name an open box, and a
named clause must exist in the box's clause map (agent/ledgers/
plan-box-progress.jsonl). The boxes each admitted commit names go to stderr.

--ticks, after the picks: map each lease commit to its landed commit by the
-x line, read the landed commit's Plan-Box trailers, and print per box the
clause-progress rows, a post-landing --plan-investigate line when the box has
no investigation row, and a ready --plan-tick line when every clause is landed
or proved and a row recorded before the work exists. --run writes the
progress rows and runs only the printed --plan-tick lines; it never writes an
investigation row. No tick line ever names a lease sha.
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


def _plan_box_problems(root, message):
    """The Plan-Box refusals of one commit message against the main checkout `root` (PLAN-tick-tracking T2), by the one reader the lease commit-msg hook also runs."""
    return _hook_module("wl_planbox").message_problems(root, message)


def _boxes_named(message):
    """The `Plan-Box:` values of an admitted commit, for the stderr listing."""
    parsed = _hook_module("wl_planbox").parse_plan_box(message)
    if parsed.none_reason is not None:
        return ["none -- %s" % parsed.none_reason]
    return [
        "%s#%s clauses=%s"
        % (b.plan, b.sig, b.clauses if b.clauses == "all" else ",".join(b.clauses))
        for b in parsed.boxes
    ]


def _problems(tree, sha, root=None):
    """What makes `sha` refused for landing, one phrase each. `root` is the main checkout whose plans the Plan-Box trailer is judged against."""
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
    if root is not None:
        found += _plan_box_problems(root, trailers)
    raw = spike.must(tree, "diff-tree", "-r", "--root", "-m", "--no-commit-id", "--raw", "-z", sha)
    fields = raw.split("\0")
    for meta, rel in zip(fields[0::2], fields[1::2], strict=False):
        modes = meta.lstrip(":").split()[:2]
        if GITLINK_MODE in modes:
            found.append("touches the gitlink %s" % rel)
        if rel.startswith(AGENT_PREFIX):
            found.append("touches %s" % rel)
    return found


def _merges(tree, tip, key, lease_id):
    """A merge in the lease, refused by name. `git cherry` omits merges, so the landed reader never lists one, and picking the commits around it would silently lose whatever the merge resolved."""
    tips = [spike.out(tree, "rev-parse", "HEAD")]
    pin = spike.out(
        tree, "rev-parse", "--verify", "-q", "%s%s^{commit}" % (spike.PIN_SPACE, lease_id)
    )
    tips += [pin] if pin else []
    listed = spike.must(tree, "rev-list", "--merges", *tips, "--not", tip)
    return ["%s %s: is a merge" % (key, sha[:12]) for sha in listed.splitlines()]


def _repo_plan(root, record, key):
    """`(lease tree, live tip, shas oldest first)` for one repo of a lease, or None when the lease holds none there."""
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
    return tree, tip, _ordered(tree, shas, tip)


def land_plan(root, lease_id, notes=None):
    """The lines to run, or raises `LeaseRefusedError` naming every refused commit. Nothing is written. `notes`, when a list, gains one line per admitted commit naming the boxes its Plan-Box trailers serve."""
    root = _main_checkout(root)
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
            if (why := _problems(plan[0], sha, root))
        ]
    if refused:
        raise LeaseRefusedError("; ".join(refused))
    if notes is not None:
        for key in keys:
            for sha in plans.get(key, (None, None, []))[2]:
                message = spike.must(plans[key][0], "show", "-s", "--format=%B", sha)
                notes.append("%s %s serves %s" % (key, sha[:12], "; ".join(_boxes_named(message))))
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


TICKS_NOTE = (
    "post-landing: %s#%s landed in %s from lease %s, clauses %s; the box text was read "
    "against that diff"
)
WORKLIST_REL = pathlib.PurePath(".claude", "hooks", "stop", "worklist.py")


class BoxLanding(NamedTuple):
    """One box `land --ticks` speaks for: the landed commits its trailers name, in lease order."""

    plan: str
    sig: str
    picks: list  # [(key, lease sha, landed sha, clauses)]


def _lease_commits(root, record, key):
    """`(live repo, live tip, lease shas oldest first)` of one repo of a lease, landed or not: what HEAD and the pin hold past the lease's base. The tree may be gone; the pin outlives it."""
    live = root if key == "." else root / key
    if not live.is_dir():
        return None
    tree = pathlib.Path(record["path"]) if key == "." else pathlib.Path(record["path"]) / key
    tips = []
    if tree.is_dir():
        head = spike.out(tree, "rev-parse", "HEAD")
        tips += [head] if head else []
    pin = spike.out(
        live, "rev-parse", "--verify", "-q", "%s%s^{commit}" % (spike.PIN_SPACE, record["id"])
    )
    tips += [pin] if pin else []
    base = record.get("base", {}).get(key, "")
    tip = live_tip(root) if key == "." else spike.out(live, "rev-parse", "HEAD")
    if not tips or not base:
        return live, tip, []
    listed = spike.out(
        live, "rev-list", "--reverse", "--topo-order", "--no-merges", *tips, "--not", base
    )
    return live, tip, [s for s in listed.splitlines() if s]


def landed_boxes(root, lease_id):
    """[BoxLanding] for every box a LANDED commit of the lease names, mapped lease sha -> landed sha by the `-x` line. Commits not yet landed are left out; a lease sha never stands in for a landed one."""
    root = _main_checkout(root)
    path = root / ".git" / RECORD_DIR / ("%s.json" % lease_id)
    if not ID_RE.match(lease_id) or not path.is_file():
        message = "no lease record %s" % lease_id
        raise LeaseRefusedError(message)
    record = json.loads(path.read_text(encoding="utf-8"))
    pb = _hook_module("wl_planbox")
    keys = [*sorted(k for k in record.get("base", {}) if k != "."), "."]
    boxes: dict[tuple[str, str], BoxLanding] = {}
    for key in keys:
        found = _lease_commits(root, record, key)
        if found is None or not found[2]:
            continue
        live, tip, shas = found
        mapping = pb.landed_map(live, shas, rev=tip)
        if mapping is None:
            message = "git could not map the lease commits of %s to landed ones" % key
            raise LeaseRefusedError(message)
        for sha in shas:
            landed = mapping.get(sha)
            if not landed:
                continue
            message = spike.must(live, "show", "-s", "--format=%B", landed)
            for box in pb.parse_plan_box(message).boxes:
                entry = boxes.setdefault((box.plan, box.sig), BoxLanding(box.plan, box.sig, []))
                entry.picks.append((key, sha, landed, box.clauses))
    return list(boxes.values())


def _first_path(root, key, landed):
    """A `fileline:` token for the first file the landed commit adds or changes, or "" when it only deletes."""
    live = root if key == "." else root / key
    out = spike.out(
        live, "diff-tree", "--no-commit-id", "--name-only", "--diff-filter=AM", "-r", landed
    )
    first = next((x for x in out.splitlines() if x), "")
    if not first:
        return ""
    return "fileline:%s:1" % (first if key == "." else "%s/%s" % (key, first))


def tick_report(root, lease_id, me):
    """`(lines, progress rows, ticks)` for `land <id> --ticks` (PLAN-tick-tracking Design 2). Nothing is written. `ticks` is [(rel, sig, evidence)], printed only where every clause is covered and an investigation row recorded before the work exists."""
    root = _main_checkout(root)
    pb = _hook_module("wl_planbox")
    rec = _hook_module("wl_planrec")
    rows = pb.read_progress(root)
    lines, progress, ticks = [], [], []
    for box in landed_boxes(root, lease_id):
        resolved = pb.resolve_plan(root, box.plan)
        rel = resolved[0] if resolved else pb.plan_rel_of(box.plan)
        cmap = pb.clause_map(root, box.plan, box.sig, rows)
        ids = [c["id"] for c in cmap] if cmap else []
        covered, every = set(), False
        for *_pick, clauses in box.picks:
            if clauses == "all":
                every = True
            else:
                covered.update(clauses)
        for r in rows:
            if (
                r.get("kind") == "progress"
                and r.get("sig") == box.sig
                and pb.same_plan(r.get("plan"), box.plan)
                and r.get("state") in ("landed", "proved")
            ):
                covered.add(r.get("clause"))
        done = every or "all" in covered or bool(ids and set(ids) <= covered)
        last = box.picks[-1][2]
        named = ",".join(
            "all" if c == "all" else ",".join(c) for c in dict.fromkeys(p[3] for p in box.picks)
        )
        lines.append(
            "BOX %s#%s landed %s clauses=%s"
            % (box.plan, box.sig, " ".join(p[2][:12] for p in box.picks), named)
        )
        for _key, _sha, landed, clauses in box.picks:
            for clause in ("all",) if clauses == "all" else clauses:
                row = {
                    "kind": "progress",
                    "by": me,
                    "plan": rel,
                    "sig": box.sig,
                    "clause": clause,
                    "state": "landed",
                    "ref": landed,
                }
                progress.append(row)
                lines.append("  progress %s %s landed %s" % (box.sig, clause, landed[:12]))
        inv = rec.investigation_for(root, rel, box.sig)
        if inv is None:
            pointers = " ".join(
                x for x in ("commit:%s" % last[:12], _first_path(root, box.picks[-1][0], last)) if x
            )
            note = TICKS_NOTE % (box.plan, box.sig, last[:12], lease_id, named)
            lines.append(
                "  worklist.py --plan-investigate %s %s %s %s %s -- %s --write"
                % (me, rel, box.sig, "present" if done else "partial", pointers, note)
            )
            if not done:
                lines.append(_owed_line(ids, covered))
            continue
        if not done:
            lines.append(_owed_line(ids, covered))
            continue
        evidence = "commit:%s landed from lease %s" % (last[:12], lease_id)
        if inv.get("retro") or rec.clause1_ordering(root, inv, evidence):
            lines.append(
                "  no tick: the investigation row of %s is not recorded before %s; write a fresh "
                "--plan-investigate first" % (box.sig, last[:12])
            )
            continue
        ticks.append((rel, box.sig, evidence))
        lines.append(
            "  worklist.py --plan-tick %s %s %s '%s' --write" % (me, rel, box.sig, evidence)
        )
    return lines, progress, ticks


def _owed_line(ids, covered):
    """The `owed:` line of a box with an uncovered clause."""
    owed = [i for i in ids if i not in covered]
    return "  owed: %s (no tick until every clause is landed or proved)" % ",".join(owed)


def _run_tick(root, me, rel, sig, evidence):
    """One `--plan-tick ... --write` as a process, the verb's own refusals intact. Returns its exit code."""
    done = subprocess.run(
        [
            sys.executable,
            str(root / WORKLIST_REL),
            "--plan-tick",
            me,
            rel,
            sig,
            evidence,
            "--write",
        ],
        cwd=str(root),
        check=False,
    )
    return done.returncode


def land_ticks(root, lease_id, *, run=False, me=None, tick=None):
    """`(lines, exit code)` for `land <id> --ticks [--run]`. With `run`, the progress rows are appended and `--plan-tick` runs only where a tick line was printed; an investigation row is never written."""
    root = _main_checkout(root)
    me = me or _default_owner()
    lines, progress, ticks = tick_report(root, lease_id, me)
    if not run:
        return lines, 0
    pb = _hook_module("wl_planbox")
    for row in progress:
        _stored, written = pb.append_progress(root, row)
        lines.append(
            "%s progress %s %s %s"
            % ("wrote" if written else "kept", row["sig"], row["clause"], row["ref"][:12])
        )
    tick = tick or _run_tick
    rc = 0
    for rel, sig, evidence in ticks:
        code = tick(root, me, rel, sig, evidence)
        lines.append("ticked %s %s rc=%d" % (rel, sig, code))
        rc = rc or (1 if code else 0)
    return lines, rc


def _cmd_ticks(lease_id, flags):
    try:
        lines, rc = land_ticks(paths.repo_root(), lease_id, run="--run" in flags)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    if not lines:
        log.info("no landed commit of %s names a plan box" % lease_id)
    sys.stdout.write("".join(line + "\n" for line in lines))
    sys.stdout.flush()
    return rc


def cmd_land(args):
    ids = [a for a in args if not a.startswith("-")]
    flags = [a for a in args if a.startswith("-")]
    if len(ids) != 1 or any(f not in ("--ticks", "--run") for f in flags):
        log.error("land takes one lease id, and --ticks [--run] after the picks")
        return 1
    if "--run" in flags and "--ticks" not in flags:
        log.error("--run belongs to --ticks")
        return 1
    if "--ticks" in flags:
        return _cmd_ticks(ids[0], flags)
    args = ids
    notes: list[str] = []
    try:
        lines = land_plan(paths.repo_root(), args[0], notes)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    if not lines:
        log.info("nothing to land in %s" % args[0])
    for note in notes:
        log.info(note)
    sys.stdout.write("".join(line + "\n" for line in lines))
    sys.stdout.flush()
    return 0


LEASES_HELP = """\
Usage: ./run.sh worktree leases [--json]

Read-only. List every lease with its owner, base, dirty count and unlanded
commits per repo.
"""
GC_HELP = """\
Usage: ./run.sh worktree gc [--write] [--id <id>]

List every lease tree and pin as DELETE or KEEP with the rule that keeps it.
Nothing changes without --write, which deletes what passes every rule:

  1. the tree is a direct child of .claude/worktrees and a linked tree of this
     checkout's store, its record names that path, and it is no symlink;
  2. no live writer, live worklist item or process holds it, and a sweep of every
     tree also keeps one made in the last 10 minutes with no finished writer, and
     one whose unfinished writer's transcript moved in that window: naming a tree
     with --id drops these two, since a writer starting leaves no other trace;
  3. the tree and each submodule have no uncommitted or untracked path, a moved
     gitlink row (SC..) excepted, since the submodule is judged on its own;
  4. every commit of HEAD and of the pin, in each repo, is landed on the live tip.

Ignored files do not keep a tree and die with it, so a result worth keeping goes
in a report or a commit. A pin of a removed tree goes with its record once its
commits are landed. `--write --id <id>` exits 1 when that lease was kept.
"""
RULE_PLACE = "rule 1"
RULE_LIVE = "rule 2"
RULE_CLEAN = "rule 3"
RULE_LANDED = "rule 4"
PER_TREE_REFS = ("refs/worktree", "refs/bisect", "refs/rewritten")
SHA_SHOWN = 12
ROSTER_ERRORS = (OSError, ValueError, RuntimeError, AttributeError, TypeError, KeyError)
# How long a sweep believes a writer may be on a tree with nothing else to show for it. The harness writes an agent's meta 1 to 3 seconds after the record (measured 2026-11-05), and a lead hands a `./run.sh worktree lease` tree to a writer it has yet to spawn.
WRITER_DOUBT_S = 600
IGNORED_NOTE = "ignored files do not keep a tree and are deleted with it"


class World(NamedTuple):
    """The one reading of git's lease facts a listing rests on."""

    root: pathlib.Path
    tip: str
    stores: dict
    pins: dict
    listed: dict
    records: dict
    policy: object


class Facts(NamedTuple):
    """One lease read across its repos: `repos` is {key: {"dirty", "commits"}}, `problems` the phrases that keep it, `subs` the submodule trees it holds."""

    repos: dict
    problems: list
    subs: list


class GcRow(NamedTuple):
    lease_id: str
    path: str
    why: list
    subs: list
    # "tree" on disk, "gone" for a pin or record whose tree is removed, "outside" for what this verb never touches.
    kind: str


@contextlib.contextmanager
def _project_env(root):
    """The hook modules find the worklist and the transcripts from this variable, so a listing of `root` reads the worklist of `root`."""
    # The whole environment is saved and put back, so this module never reads the variable by name: the root conftest pops it for every test, and a reader outside `.claude/` would see it vanish.
    saved = dict(os.environ)
    os.environ["CLAUDE_PROJECT_DIR"] = str(root)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _quiet(cwd, *args):
    """stdout, or None when git failed. `--no-optional-locks` keeps a listing from rewriting a tree's index, which the Stop hook's signature reads."""
    done = spike.git(cwd, "--no-optional-locks", *args)
    return done.stdout if done.returncode == 0 else None


def _under(path, parent):
    return path == parent or path.startswith(parent + os.sep)


def _read_records(root):
    """{file stem: record}. An unreadable record stays as None, because it is still a claim on a tree."""
    found = {}
    for path in sorted((root / ".git" / RECORD_DIR).glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = None
        found[path.stem] = record if isinstance(record, dict) else None
    return found


def _read_world(root):
    """Stores, pins, linked trees and records. A store git cannot read refuses the whole run, since a pin not seen is a pin not judged."""
    watch = _hook_module("wl_worktrees")
    stores = dict(watch.stores(root / ".git"))
    pins: dict = {}
    listed = {}
    for key, store in stores.items():
        refs = _quiet(store, "for-each-ref", "--format=%(objectname) %(refname)", spike.PIN_SPACE)
        trees = _quiet(store, "worktree", "list", "--porcelain")
        if refs is None or trees is None:
            message = "git could not read the store %s" % store
            raise LeaseRefusedError(message)
        for line in refs.splitlines():
            sha, _, ref = line.partition(" ")
            pins.setdefault(ref[len(spike.PIN_SPACE) :], {})[key] = sha
        listed[key] = watch.parse_list(trees)[1:]
    return World(
        root=root,
        tip=live_tip(root),
        stores=stores,
        pins=pins,
        listed=listed,
        records=_read_records(root),
        policy=spike.load_commit_policy(),
    )


def _is_moved_gitlink(row):
    """A `--porcelain=v2` row of a gitlink whose commit moved and nothing else: unstaged, and `SC..` says the submodule holds no modified and no untracked path."""
    fields = row.split(" ", 8)
    return (
        len(fields) == 9
        and fields[:3] == ["1", ".M", _hook_module("wl_worktrees").GITLINK_MOVED]
        and fields[3:6] == [GITLINK_MODE] * 3
    )


def _dirty_rows(tree):
    """The status rows that keep `tree`, or None when git could not say. Both flags are spelled out, because `status.showUntrackedFiles` and a `.gitmodules` `ignore` line would otherwise hide rows."""
    text = _quiet(
        tree, "status", "--porcelain=v2", "--untracked-files=all", "--ignore-submodules=none"
    )
    flags = _quiet(tree, "ls-files", "-v", "-z")
    if text is None or flags is None:
        return None
    rows = [row for row in text.splitlines() if row and not _is_moved_gitlink(row)]
    # `status` skips a modified file flagged skip-worktree (`S`) or assume-unchanged (lowercase), so the flag itself keeps the tree.
    rows += [
        "flag %s" % entry[2:]
        for entry in flags.split("\0")
        if entry[:1] and (entry[0] == "S" or entry[0].islower())
    ]
    return rows


def _hidden_tips(tree, known):
    """Commits only this tree's reflog or per-worktree refs hold, which die with its admin directory: a second rewrite leaves its first attempt in neither HEAD nor the pin. None when git could not say."""
    logged = _quiet(tree, "log", "-g", "--format=%H", "HEAD")
    refs = _quiet(tree, "for-each-ref", "--format=%(objectname)", *PER_TREE_REFS)
    if logged is None or refs is None:
        return None
    tips = list(dict.fromkeys((logged + refs).split()))
    if not tips:
        return []
    alone = _quiet(tree, "rev-list", *tips, "--not", *known)
    if alone is None:
        return None
    reached = set(alone.split())
    return [sha for sha in tips if sha in reached]


def _commit_problems(tree, key, tips, tip, base):
    """(unlanded shas, problems) over every (head, pin) pair. `git cherry` omits a merge, so a merge not on the live tip is its own problem: the reader would call what it resolved landed."""
    found = []
    for head, pin in tips:
        shas = unlanded(tree, head, pin, tip, base)
        if shas is None:
            return [], ["%s: %s: git could not say what is landed" % (RULE_LANDED, key)]
        found += [sha for sha in shas if sha not in found]
    problems = []
    if found:
        shown = " ".join(sha[:SHA_SHOWN] for sha in found)
        problems.append(
            "%s: %s holds %d unlanded commit(s): %s" % (RULE_LANDED, key, len(found), shown)
        )
    named = [ref for pair in tips for ref in pair if ref]
    merges = _quiet(tree, "rev-list", "--merges", *named, "--not", tip)
    if merges is None:
        problems.append("%s: %s: git could not list its merges" % (RULE_LANDED, key))
    elif merges.strip():
        problems.append(
            "%s: %s holds the merge %s" % (RULE_LANDED, key, merges.split()[0][:SHA_SHOWN])
        )
    return found, problems


def _repo_facts(tree, key, tip, pin, base):
    """(entry, problems) for one repo with a tree on disk. HEAD and the pin are both judged: after a rewrite HEAD no longer descends from the pin, and either can hold the only copy."""
    if not tip:
        return {"dirty": 0, "commits": []}, ["%s: %s has no live tip" % (RULE_LANDED, key)]
    problems = []
    rows = _dirty_rows(tree)
    dirty = len(rows or ())
    if rows is None:
        problems.append("%s: git status failed in %s" % (RULE_CLEAN, key))
    elif rows:
        problems.append(
            "%s: %s has %d uncommitted path(s), first %s"
            % (RULE_CLEAN, key, dirty, rows[0].rsplit(" ", 1)[-1])
        )
    head = (_quiet(tree, "rev-parse", "--verify", "HEAD^{commit}") or "").strip()
    if not head:
        problems.append("%s: %s has no readable HEAD" % (RULE_LANDED, key))
        return {"dirty": dirty, "commits": []}, problems
    hidden = _hidden_tips(tree, [head, *([pin] if pin else []), tip])
    if hidden is None:
        problems.append("%s: git could not read the reflog of %s" % (RULE_LANDED, key))
        hidden = []
    commits, more = _commit_problems(
        tree, key, [(head, pin), *((sha, "") for sha in hidden)], tip, base
    )
    problems += more
    apart = pin and spike.git(tree, "merge-base", "--is-ancestor", pin, head).returncode != 0
    if apart and commits:
        problems.append(
            "%s: %s HEAD %s does not descend from its pin %s, so both tips stay"
            % (RULE_LANDED, key, head[:SHA_SHOWN], pin[:SHA_SHOWN])
        )
    return {"dirty": dirty, "commits": commits}, problems


def _base_of(record):
    base = (record or {}).get("base")
    return base if isinstance(base, dict) else {}


def _sub_keys(world, path, record):
    """(submodule keys, problems): what the record, the tree's index and the stores' lists each say lives in this tree."""
    keys = {key for key in _base_of(record) if key != CONSOLE}
    problems = []
    stage = _quiet(path, "ls-files", "--stage")
    if stage is None:
        problems.append("%s: git could not read the index of %s" % (RULE_CLEAN, path))
    else:
        keys |= {
            row.split("\t", 1)[1]
            for row in stage.splitlines()
            if row.startswith(GITLINK_MODE + " ")
        }
    for key, rows in world.listed.items():
        for row in rows:
            tree = row.get("worktree", "")
            if not tree.startswith(str(path) + os.sep):
                continue
            if key == CONSOLE:
                problems.append("%s: %s nests the console tree %s" % (RULE_PLACE, path, tree))
            else:
                keys.add(os.path.relpath(tree, path))
    for key in sorted(keys):
        rel = pathlib.PurePath(key)
        if rel.is_absolute() or ".." in rel.parts:
            problems.append("%s: the submodule key %s leaves the tree" % (RULE_PLACE, key))
            keys.discard(key)
    return sorted(keys), problems


def _is_linked_to_store(world, tree, key):
    common = _quiet(tree, "rev-parse", "--path-format=absolute", "--git-common-dir")
    own = _quiet(tree, "rev-parse", "--absolute-git-dir")
    store = _store_of(world.root, key)
    if not common or not own or store is None:
        return False
    return os.path.realpath(common.strip()) == str(store) and common.strip() != own.strip()


def _sub_tree_problem(world, tree, key):
    """Why the submodule directory `tree` holds no repo to judge, or "". Git reports nothing about files in a gitlink directory with no `.git`, so a phrase here is the only thing that sees them."""
    if tree.is_symlink():
        return "%s: %s is a symlink" % (RULE_CLEAN, key)
    if not tree.is_dir():
        return ""
    if not os.path.lexists(tree / ".git"):
        if any(tree.iterdir()):
            return "%s: %s holds files in a gitlink directory with no .git" % (RULE_CLEAN, key)
        return ""
    if not _is_linked_to_store(world, tree, key):
        return "%s: %s is no linked tree of its module store" % (RULE_CLEAN, key)
    return ""


def _store_facts(world, key, pin, head, base):
    """(entry, problems) for a repo with no tree on disk: its pin and the HEAD git still lists, read in its store."""
    store = world.stores[key]
    tip = world.tip if key == CONSOLE else spike.out(store, "rev-parse", "HEAD")
    if not tip:
        return {"dirty": 0, "commits": []}, ["%s: %s has no live tip" % (RULE_LANDED, key)]
    commits, problems = _commit_problems(store, key, [(head, pin)], tip, base)
    return {"dirty": 0, "commits": commits}, problems


def _lease_facts(world, lease_id, path, record):
    """Every repo of one lease. A tree on disk is read in the tree, and whatever pin or listed HEAD no tree answered for is read in its store."""
    pins = world.pins.get(lease_id, {})
    base = _base_of(record)
    repos, problems, subs = {}, [], []
    if path.is_dir() and not path.is_symlink():
        keys, problems = _sub_keys(world, path, record)
        repos[CONSOLE], more = _repo_facts(
            path, CONSOLE, world.tip, pins.get(CONSOLE, ""), base.get(CONSOLE, "")
        )
        problems += more
        for key in keys:
            tree = path / key
            why = _sub_tree_problem(world, tree, key)
            if why:
                problems.append(why)
            elif os.path.lexists(tree / ".git"):
                subs.append(key)
                tip = spike.out(world.root / key, "rev-parse", "HEAD")
                repos[key], more = _repo_facts(tree, key, tip, pins.get(key, ""), base.get(key, ""))
                problems += more
    heads = {
        key: row.get("HEAD", "")
        for key, rows in world.listed.items()
        for row in rows
        if _under(row.get("worktree", ""), str(path))
    }
    for key in sorted(set(pins) | set(heads)):
        if key not in repos:
            repos[key], more = _store_facts(
                world, key, pins.get(key, ""), heads.get(key, ""), base.get(key, "")
            )
            problems += more
    return Facts(repos=repos, problems=problems, subs=subs)


def _place_problem(world, lease_id, path, record):
    """Why rule 1 keeps this id, or "". No git runs in a path this answers for, since it is no lease."""
    if not ID_RE.match(lease_id):
        return "%s: %s is no lease id" % (RULE_PLACE, lease_id)
    if any(pin.startswith(lease_id + "/") for pin in world.pins):
        return "%s: a pin sits below refs/worktrees/%s" % (RULE_PLACE, lease_id)
    if record is not None:
        if str(record.get("id") or lease_id) != lease_id:
            return "%s: its record names the id %s" % (RULE_PLACE, record.get("id"))
        named = os.path.realpath(str(record.get("path") or ""))
        if named != str(path):
            return "%s: its record names %s, outside %s" % (RULE_PLACE, named, spike.HOLDER)
    if not os.path.lexists(path):
        return ""
    if path.is_symlink():
        return "%s: a symlink in the holder" % RULE_PLACE
    if not path.is_dir():
        return "%s: not a directory" % RULE_PLACE
    if os.path.realpath(path) != str(path):
        return "%s: its realpath leaves %s" % (RULE_PLACE, spike.HOLDER)
    if lease_id not in world.records:
        return "%s: no record, so it may be a lease still being made" % RULE_LIVE
    if record is None:
        return "%s: its record cannot be read, and is still a claim on the tree" % RULE_LIVE
    if world.policy.lease_root(str(path)) != str(path):
        return "%s: no linked tree of this checkout's store" % RULE_PLACE
    return ""


def _spawned_nothing(root, owner):
    """Whether `owner` is a session with a transcript and no agent directory: an honest zero, which an unknown or ambiguous prefix is not."""
    report = _hook_module("wl_report")
    project = report._projects_dir() / report._munged(root)
    if any(p.is_dir() for p in project.glob(owner + "*")):
        return False
    return any(project.glob(owner + "*.jsonl"))


def _roster_of(root, owner):
    """[{"id", "tree", "prompt"}] of the session's live agents, or None when nothing can say, which keeps the tree."""
    if owner == DEFAULT_OWNER:
        return []
    if not owner or not ID_RE.match(owner):
        return None
    roster = _hook_module("wl_roster")
    try:
        if roster.session_subagents_dir(str(root), owner) is None:
            return [] if _spawned_nothing(root, owner) else None
        rows, metas = roster.live_estimate(str(root), owner)
    except ROSTER_ERRORS:
        return None
    if rows is None:
        return None
    first_prompt = _hook_module("wl_leasehelp").first_prompt
    return [
        {
            "id": row["id"],
            "tree": (metas.get(row["id"]) or {}).get("worktree") or "",
            "prompt": first_prompt((metas.get(row["id"]) or {}).get("jsonl")),
        }
        for row in rows
    ]


def _read_live(root, *, named=False):
    """What rule 2 reads once per run. A worklist that cannot be read is None, which keeps every tree. `named` is a run about one tree someone named, which `_unproven_idle` leaves alone."""
    scratch = _hook_module("wl_scratch")
    core = _hook_module("wl_core")
    try:
        worklist = core.worklist_for(core.project_start({"cwd": str(root)}))
        leases = scratch.lease_texts(_hook_module("wl_store").load(worklist, sync=False).items)
    except ROSTER_ERRORS:
        leases = None
    return {
        "leases": leases,
        "cwds": scratch.process_cwds(),
        "me": core.resolve_session_id(),
        "rosters": {},
        "named": named,
        "metas": {},
    }


def _agent_holding(rows, lease_id, path, record):
    """The live agent on this tree: by the record, by the harness's own meta, or by a first prompt naming it, the way a lead hands a lease to a writer."""
    scratch = _hook_module("wl_scratch")
    agent = str(record.get("agent") or "")
    for row in rows:
        on_tree = row["tree"] and os.path.realpath(row["tree"]) == path
        named = scratch.lease_holder(lease_id, path, [(row["id"], row["prompt"])])
        if row["id"] == agent or on_tree or named:
            return row["id"]
    return ""


def _metas_of(root, live, owner):
    """{agent id: meta} from the harness's files, read once per owner. No readable owner is {}: the roster has already spoken about that doubt."""
    if owner not in live["metas"]:
        metas = {}
        if owner and owner != DEFAULT_OWNER and ID_RE.match(owner):
            roster = _hook_module("wl_roster")
            try:
                metas = roster.load_metas(roster.session_subagents_dir(str(root), owner))
            except ROSTER_ERRORS:
                metas = {}
        live["metas"][owner] = metas
    return live["metas"][owner]


def _made_at(record):
    """The record's `created_at` as an epoch, or None when it does not read as one."""
    try:
        made = datetime.datetime.strptime(str(record.get("created_at")), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
    return made.timestamp()


def _unproven_idle(world, live, path, record):
    """Rule 2's phrase for a tree nothing proves idle yet, or "". The roster only ESTIMATES who runs, and a clean tree with no agent on file passed every rule, so a sweep needs the harness's own `finished` mark or the time for a writer to have shown up."""
    if live["named"] or record is None or not os.path.lexists(path):
        return ""
    now = time.time()
    agent = str(record.get("agent") or "")
    mine = [
        (aid, meta)
        for aid, meta in _metas_of(world.root, live, str(record.get("owner") or "")).items()
        if aid == agent or (meta["worktree"] and os.path.realpath(meta["worktree"]) == str(path))
    ]
    for aid, meta in mine:
        if meta["finished"]:
            continue
        try:
            quiet = now - meta["jsonl"].stat().st_mtime
        except OSError:
            continue
        if quiet < WRITER_DOUBT_S:
            return "%s: the writer %s has no finished mark and its transcript moved %ds ago" % (
                RULE_LIVE,
                aid,
                quiet,
            )
    if mine and all(meta["finished"] for _, meta in mine):
        return ""
    made = _made_at(record)
    if made is None:
        return "%s: its record names no time it was made" % RULE_LIVE
    if now - made < WRITER_DOUBT_S:
        return "%s: made %ds ago, so its writer may still be starting" % (RULE_LIVE, now - made)
    return ""


def _in_use(world, live, lease_id, path, record):
    """Rule 2's phrases. A subagent's shell does not live between tool calls, so the roster and the worklist speak beside the process list."""
    scratch = _hook_module("wl_scratch")
    text = str(path)
    found = []
    if live["leases"] is None:
        found.append("%s: the worklist cannot be read" % RULE_LIVE)
    else:
        item = scratch.lease_holder(lease_id, text, live["leases"])
        if item:
            found.append("%s: live worklist item #%s names it" % (RULE_LIVE, item))
    inside = [cwd for cwd in live["cwds"] if _under(cwd, text)]
    if inside:
        found.append("%s: %d process(es) work inside it" % (RULE_LIVE, len(inside)))
    owner = str((record or {}).get("owner") or "")
    me = live["me"]
    for session in [owner, *([me] if me and not (owner and me.startswith(owner)) else [])]:
        if session not in live["rosters"]:
            live["rosters"][session] = _roster_of(world.root, session)
        rows = live["rosters"][session]
        if rows is None:
            # An unknown owner is a doubt about this lease; an unknown running session says nothing about it.
            if session == owner and record is not None:
                found.append(
                    "%s: the roster of session %s cannot say" % (RULE_LIVE, owner or "(none)")
                )
            continue
        holder = _agent_holding(rows, lease_id, text, record or {})
        if holder:
            found.append("%s: the live writer %s holds it" % (RULE_LIVE, holder))
    unproven = _unproven_idle(world, live, path, record)
    if unproven and not found:
        found.append(unproven)
    return found


def _judge(world, live, lease_id):
    """One lease tree or leftover pin. An empty `why` passes every rule."""
    path = world.root / spike.HOLDER / lease_id
    record = world.records.get(lease_id)
    place = _place_problem(world, lease_id, path, record)
    if place:
        return GcRow(lease_id, str(path), [place], [], "outside")
    facts = _lease_facts(world, lease_id, path, record)
    why = _in_use(world, live, lease_id, path, record)
    kind = "tree" if os.path.lexists(path) else "gone"
    return GcRow(
        lease_id, str(path), [*why, *facts.problems], facts.subs if kind == "tree" else [], kind
    )


def _holder_entries(root):
    holder = root / spike.HOLDER
    return sorted(p.name for p in holder.iterdir()) if holder.is_dir() else []


def _outside_rows(world):
    """Console trees git lists elsewhere, such as an operator's `.worktrees/<MMDD-N>`, each kept by rule 1 and never read."""
    holder = str(world.root / spike.HOLDER)
    claimed = {
        os.path.realpath(str(record.get("path") or ""))
        for record in world.records.values()
        if record
    }
    rows = []
    for row in world.listed.get(CONSOLE, []):
        tree = row.get("worktree", "")
        if os.path.dirname(tree) != holder and tree not in claimed:
            why = "%s: %s is no direct child of %s" % (RULE_PLACE, tree, spike.HOLDER)
            rows.append(GcRow(os.path.basename(tree), tree, [why], [], "outside"))
    return rows


def _remove_row(world, row):
    """Unlock, submodule trees, console tree, pins, then the record, only when nothing else survived. Returns what survived. The predicate is the only guard: `--force` is unavoidable, because git refuses any tree with a submodule without it.

    The signals are held for the removal and each goes back to the handler it had before (not forced to the lease's `interrupted`, which would change the disposition for every caller). Left ignored, SIGTERM stayed ignored for the rest of the process and for every child it started afterwards, because an ignored disposition survives exec: a pytest worker that ran a gc test then spawned servers that no `terminate()` could stop.
    """
    signums = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    before = {signum: signal.getsignal(signum) for signum in signums}
    spike.hold_signals()
    try:
        return _remove_row_held(world, row)
    finally:
        for signum, handler in before.items():
            signal.signal(signum, handler)


def _remove_row_held(world, row):
    path = pathlib.Path(row.path)
    holder = world.root / spike.HOLDER
    if row.kind == "tree":
        _rollback(spike.Repo(world.root, row.subs), path)
    else:
        for key, rows in world.listed.items():
            for listed in rows:
                tree = listed.get("worktree", "")
                if _under(tree, row.path):
                    spike.git(world.stores[key], "worktree", "unlock", tree)
                    spike.unregister(world.stores[key], tree, holder)
    ref = spike.PIN_SPACE + row.lease_id
    survived = [row.path] if os.path.lexists(path) else []
    for store in world.stores.values():
        survived += [tree for tree in spike.listed_trees(store) if _under(tree, row.path)]
    if survived:
        # A pin is the only ref protecting the HEAD of a tree that is still there.
        return survived
    for store in world.stores.values():
        spike.drop_pins(store, ref)
        survived += spike.out(store, "for-each-ref", "--format=%(refname)", ref).splitlines()
    if not survived:
        (world.root / ".git" / RECORD_DIR / ("%s.json" % row.lease_id)).unlink(missing_ok=True)
    return survived


def _gc_rows(world, live, only):
    """Rows in id order, judged lazily so `--write` judges each tree immediately before removing it."""
    rows = _outside_rows(world)
    ids = {*world.records, *world.pins, *_holder_entries(world.root)}
    if only and only not in ids and only not in {row.lease_id for row in rows}:
        message = "no lease, tree or pin named %s" % only
        raise LeaseRefusedError(message)
    merged = [(row.lease_id, row) for row in rows] + [(lease_id, None) for lease_id in ids]
    for lease_id, row in sorted(merged, key=lambda pair: pair[0]):
        if not only or lease_id == only:
            yield row or _judge(world, live, lease_id)


def run_gc(root, *, write=False, only=""):
    """(rc, lines): the listing, and with `write` the deletion."""
    root = _main_checkout(root)
    lines = []
    deletable, kept, failed = 0, 0, 0
    with _project_env(root):
        world = _read_world(root)
        live = _read_live(root, named=bool(only))
        for row in _gc_rows(world, live, only):
            if row.why:
                kept += 1
                lines.append("  %-6s  %-24s %s" % ("KEEP", row.lease_id, "; ".join(row.why)))
                continue
            lines.append("  %-6s  %-24s every rule holds" % ("DELETE", row.lease_id))
            survived = _remove_row(world, row) if write else []
            if survived:
                failed += 1
                log.error("%s not fully removed: %s" % (row.lease_id, ", ".join(survived)))
            else:
                deletable += 1
    tail = "deleted %d" % deletable if write else "listing only, rerun with --write to delete"
    stuck = ", %d not fully removed" % failed if failed else ""
    lines.append(
        "%d row(s): %d deletable, %d kept%s; %s; %s"
        % (deletable + kept + failed, deletable, kept, stuck, IGNORED_NOTE, tail)
    )
    return (1 if failed or (write and only and kept) else 0), lines


def _parse_gc(args):
    """`(write, id)`, or None after an error line."""
    write, only = False, ""
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--write":
            write = True
        elif arg == "--id" and rest and ID_RE.match(rest[0]):
            only = rest.pop(0)
        else:
            log.error("Unknown or incomplete option: %s" % arg)
            return None
    return write, only


def _hook_input():
    """The hook's JSON object on stdin. Valid JSON of another shape is a refusal like any other bad input."""
    data = json.loads(sys.stdin.read() or "{}")
    if not isinstance(data, dict):
        message = "the hook input is %s, not a JSON object" % type(data).__name__
        raise LeaseRefusedError(message)
    return data


def cmd_lease_hook(args):
    """`WorktreeCreate`: make the tree the harness asked for and print its path as the last stdout line. Any non-zero exit fails the creation, so a refusal reaches the spawn."""
    if args:
        log.error("Unknown option: %s" % args[0])
        return 1
    root = pathlib.Path(paths.repo_root())
    try:
        data = _hook_input()
        name = str(data.get("name") or "")
        agent = name[len("agent-") :] if name.startswith("agent-") else ""
        path = make_lease(
            root,
            name=name,
            owner=str(data.get("session_id") or "")[:8] or _default_owner(),
            agent=agent,
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    sys.stdout.write(path + "\n")
    sys.stdout.flush()
    return 0


def cmd_gc_hook(args):
    """`WorktreeRemove`: exit 0 counts as removed whether or not anything was deleted, so anything `gc` keeps exits non-zero with the tree in place."""
    if args:
        log.error("Unknown option: %s" % args[0])
        return 1
    root = pathlib.Path(paths.repo_root())
    try:
        data = _hook_input()
        path = pathlib.Path(str(data.get("worktree_path") or ""))
        main = _main_checkout(root)
        if path.parent != pathlib.Path(main) / spike.HOLDER or not ID_RE.match(path.name):
            log.error("refused: %s is no lease tree of %s" % (path, main))
            return 1
        code, lines = run_gc(root, write=True, only=path.name)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    sys.stderr.write("".join(line + "\n" for line in lines))
    return code


def cmd_gc(args):
    parsed = _parse_gc(args)
    if parsed is None:
        return 1
    try:
        code, lines = run_gc(paths.repo_root(), write=parsed[0], only=parsed[1])
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    sys.stdout.write("".join(line + "\n" for line in lines))
    sys.stdout.flush()
    return code


def lease_rows(root):
    """One dict per lease: what `leases --json` prints."""
    root = pathlib.Path(os.path.realpath(root))
    root = _main_checkout(_holding_checkout(root) or root)
    world = _read_world(root)
    rows = []
    for lease_id in sorted({*world.records, *world.pins, *_holder_entries(root)}):
        record = world.records.get(lease_id) or {}
        path = root / spike.HOLDER / lease_id
        named = str(path)
        # The same rule 1 gate as `gc`: a path it refuses is no lease, and no git runs in it.
        place = _place_problem(world, lease_id, path, world.records.get(lease_id))
        facts = (
            Facts(repos={}, problems=[place], subs=[])
            if place
            else _lease_facts(world, lease_id, path, record)
        )
        rows.append(
            {
                "id": lease_id,
                "path": named,
                "exists": path.is_dir() and not path.is_symlink(),
                "owner": str(record.get("owner") or ""),
                "agent": str(record.get("agent") or ""),
                "created_at": str(record.get("created_at") or ""),
                "base": _base_of(record),
                "dirty": sum(entry["dirty"] for entry in facts.repos.values()),
                "unlanded": {
                    key: entry["commits"] for key, entry in facts.repos.items() if entry["commits"]
                },
                "problems": facts.problems,
            }
        )
    return rows


def _lease_line(row):
    commits = ", ".join(
        "%s %d (%s)" % (key, len(shas), " ".join(sha[:SHA_SHOWN] for sha in shas))
        for key, shas in sorted(row["unlanded"].items())
    )
    base = str(row["base"].get(CONSOLE) or "unknown")[:SHA_SHOWN]
    tree = "" if row["exists"] else "  (no tree on disk)"
    return "  %-24s owner %-10s base %-12s dirty %d  unlanded: %s%s" % (
        row["id"],
        row["owner"] or "unknown",
        base,
        row["dirty"],
        commits or "none",
        tree,
    )


def cmd_leases(args):
    if args not in ([], ["--json"]):
        log.error("Unknown option: %s" % " ".join(args))
        return 1
    try:
        rows = lease_rows(paths.repo_root())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    if args:
        sys.stdout.write(json.dumps(rows, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write("".join(_lease_line(row) + "\n" for row in rows) or "no leases\n")
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
