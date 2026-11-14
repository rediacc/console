#!/usr/bin/env python3
"""PLAN-worktree-lease W0: submodule worktrees against shared clones, timed, with one decision.

    python3 .ci/rediacc_ci/dev/worktree_spike.py --fixture [--plant-missing-gitlink]
    python3 .ci/rediacc_ci/dev/worktree_spike.py --live

Candidate A makes each submodule tree with `git -C <module> worktree add --detach`. Candidate B makes it with `git clone --shared --no-checkout <module>` and a detached checkout. Each run builds one throwaway lease per candidate under `<root>/.claude/worktrees`, answers the plan's questions, and removes the lease.

Exit 0: a decision exists and nothing is left behind. Exit 1: no candidate passes, a tree or pin survived, or a shared file changed.

`block_worktree_add` refuses this file while it is untracked or differs from HEAD, whichever flag it is given, so every run happens from a committed copy.

SIDE EFFECTS ON THE LIVE STORES. The hook probe commits on a detached HEAD, and the pin carries that commit into the module store. The pin is deleted, so the commit stays as an unreachable object until `git gc`. Disk and inode deltas come from `statvfs`, so a peer writing to the same filesystem shows up in them.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[3]
HOLDER = pathlib.PurePath(".claude", "worktrees")
PREFIX = "spike-"
PIN_SPACE = "refs/worktrees/"
GIT_TIMEOUT = 1800
SLOWER_LIMIT = 2.0
SEED_DEPTH = 4
SEED_SKIP = (".git", ".worktrees", ".claude/worktrees", ".ci/cache")
SEED_EXTRA = ("private/bin", "private/renet/bin")
SCRUBBED_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX")
PROBE_MESSAGE = "chore(spike): W0 hook probe\n\nPR-TASK: 1f877343\n"
MISSING_SHA = "deadbeef" * 5
CONSOLE = "(console)"
CONSOLE_QUESTIONS = ("console_detached", "console_status_clean", "seed_ok")
SUBMODULE_QUESTIONS = (
    "gitlink_checks_out",
    "core_worktree_ignored",
    "superproject_names_lease",
    "submodule_status_works",
    "hooks_path_applies",
    "hook_fires",
    "status_reads_gitlink",
    "pin_reaches_store",
    "fsck_clean_after_removal",
)


class InterruptedRunError(Exception):
    """A signal arrived, so the removal path runs and the exit is 1."""


def git(cwd, *args, env=None):
    merged = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
    merged["GIT_TERMINAL_PROMPT"] = "0"
    merged.update(env or {})
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=merged,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
        timeout=GIT_TIMEOUT,
    )


def out(cwd, *args):
    done = git(cwd, *args)
    return done.stdout.strip() if done.returncode == 0 else ""


def must(cwd, *args):
    done = git(cwd, *args)
    if done.returncode != 0:
        message = "git %s failed in %s: %s" % (" ".join(args), cwd, done.stderr.strip())
        raise RuntimeError(message)
    return done.stdout.strip()


def real(path):
    return os.path.realpath(str(path))


def load_commit_policy():
    path = ROOT / ".claude" / "rediacc_hooks" / "commit_policy.py"
    spec = importlib.util.spec_from_file_location("commit_policy", path)
    if spec is None or spec.loader is None:
        message = "cannot load %s" % path
        raise RuntimeError(message)
    module = importlib.util.module_from_spec(spec)
    sys.modules["commit_policy"] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class Repo:
    root: pathlib.Path
    submodules: list[str]

    @property
    def holder(self):
        return self.root / HOLDER

    def store(self, sub):
        """The module store git names after the submodule NAME, which differs from its path in a renamed or moved submodule."""
        tree = self.root / sub
        # An uninitialised submodule is an empty directory, and git there walks up to the parent repository, whose store is not this one.
        top = out(tree, "rev-parse", "--show-toplevel") if tree.is_dir() else ""
        found = ""
        if top and os.path.realpath(top) == os.path.realpath(tree):
            found = out(tree, "rev-parse", "--absolute-git-dir")
        return pathlib.Path(found) if found else self.root / ".git" / "modules" / sub


@dataclass
class Result:
    name: str
    steps: dict = field(default_factory=dict)
    answers: dict = field(default_factory=dict)
    gitlinks: dict = field(default_factory=dict)
    leftovers: list = field(default_factory=list)

    def answer(self, sub, question, ok, detail=""):
        self.answers["%s/%s" % (sub, question)] = {"ok": bool(ok), "detail": str(detail).strip()}

    def fill_unreached(self, submodules):
        for question in CONSOLE_QUESTIONS:
            self.answers.setdefault(
                "%s/%s" % (CONSOLE, question), {"ok": False, "detail": "not reached"}
            )
        for sub in submodules:
            for question in SUBMODULE_QUESTIONS:
                self.answers.setdefault(
                    "%s/%s" % (sub, question), {"ok": False, "detail": "not reached"}
                )

    def passed(self):
        return bool(self.answers) and all(a["ok"] for a in self.answers.values())

    def submodule_seconds(self):
        return sum(s["seconds"] for n, s in self.steps.items() if n.startswith("submodule:"))

    def total_seconds(self):
        return sum(s["seconds"] for s in self.steps.values())


@contextlib.contextmanager
def measured(result, name, where):
    before = os.statvfs(where)
    started = time.monotonic()
    try:
        yield
    finally:
        after = os.statvfs(where)
        result.steps[name] = {
            "seconds": round(time.monotonic() - started, 3),
            "disk_kib": (before.f_bfree - after.f_bfree) * after.f_frsize // 1024,
            "inodes": before.f_ffree - after.f_ffree,
        }


def remove_dir(path, holder):
    """Delete a directory inside the holder. Only directories get a mode change, because a file here may be a hard link into the live tree and shares its inode."""
    path = pathlib.Path(path)
    if holder not in path.parents:
        message = "refusing to delete %s outside %s" % (path, holder)
        raise RuntimeError(message)
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if not path.exists():
        return
    for dirpath, _dirnames, _filenames in os.walk(path):
        pathlib.Path(dirpath).chmod(0o700)
    shutil.rmtree(path)


def listed_trees(store):
    lines = out(store, "worktree", "list", "--porcelain").splitlines()
    return {line.split(" ", 1)[1] for line in lines if line.startswith("worktree ")}


def unregister(store, tree, holder):
    """Drop one linked tree from a store: the git verb first, then the directory and a prune when git refuses."""
    if str(tree) in listed_trees(store):
        git(store, "worktree", "remove", "--force", str(tree))
    if pathlib.Path(tree).exists():
        remove_dir(tree, holder)
    if str(tree) in listed_trees(store):
        git(store, "worktree", "prune")


def drop_pins(store, pattern):
    for ref in out(store, "for-each-ref", "--format=%(refname)", pattern).splitlines():
        git(store, "update-ref", "-d", ref)


def remove_lease(repo, lease):
    """Remove one lease whatever state it reached: seeds, submodule trees, console tree, pins. Returns what survived."""
    holder = repo.holder
    if lease.is_symlink() or not lease.is_dir():
        remove_dir(lease, holder)
        return [str(lease)] if lease.is_symlink() or lease.exists() else []
    for rel in seed_targets(repo.root):
        remove_dir(lease / rel, holder)
    pattern = PIN_SPACE + lease.name
    for sub in repo.submodules:
        unregister(repo.store(sub), lease / sub, holder)
        drop_pins(repo.store(sub), pattern)
    unregister(repo.root / ".git", lease, holder)
    drop_pins(repo.root / ".git", pattern)
    survived = []
    if lease.exists():
        survived.append(str(lease))
    for store in (repo.root / ".git", *(repo.store(s) for s in repo.submodules)):
        survived += [
            p for p in listed_trees(store) if p == str(lease) or p.startswith("%s/" % lease)
        ]
        survived += out(store, "for-each-ref", "--format=%(refname)", pattern).splitlines()
    return survived


def sweep_stale(repo):
    """A SIGKILLed run cannot clean up, so the next one removes what it left."""
    if not repo.holder.is_dir():
        return []
    survived = []
    for stale in sorted(repo.holder.glob(PREFIX + "*")):
        survived += remove_lease(repo, stale)
    return survived


def seed_targets(root):
    """Every node_modules to SEED_DEPTH, plus the build output a real seed links, as paths relative to the root."""
    found = []
    for dirpath, dirnames, _filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        kept = []
        for name in sorted(dirnames):
            child = name if rel == "." else os.path.join(rel, name)
            if child in SEED_SKIP or (root / child).is_symlink():
                continue
            if name == "node_modules":
                found.append(child)
            elif depth < SEED_DEPTH - 1:
                kept.append(name)
        dirnames[:] = kept
    found += [rel for rel in SEED_EXTRA if (root / rel).is_dir() and rel not in found]
    return found


def seed(repo, lease, result):
    ok = True
    details = []
    for rel in seed_targets(repo.root):
        target = lease / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with measured(result, "seed:%s" % rel, repo.root):
            done = subprocess.run(
                ["cp", "-al", str(repo.root / rel), str(target)],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                timeout=GIT_TIMEOUT,
            )
        if done.returncode != 0:
            ok = False
            details.append("%s: %s" % (rel, done.stderr.strip()[:200]))
    result.answer(CONSOLE, "seed_ok", ok, "; ".join(details))


def make_linked(repo, tree, sha):
    return git(repo.store(tree.sub), "worktree", "add", "--detach", str(tree.path), sha)


def make_shared_clone(repo, tree, sha):
    store = repo.store(tree.sub)
    cloned = git(repo.root, "clone", "--shared", "--no-checkout", str(store), str(tree.path))
    if cloned.returncode != 0:
        return cloned
    hooks = out(store, "config", "--get", "core.hooksPath")
    if hooks:
        git(tree.path, "config", "core.hooksPath", hooks)
    return git(tree.path, "checkout", "--detach", sha)


def pin_linked(_repo, tree, ref):
    return git(tree.path, "update-ref", ref, "HEAD")


def pin_shared_clone(repo, tree, ref):
    return git(
        repo.store(tree.sub), "fetch", "--no-write-fetch-head", str(tree.path), "+HEAD:%s" % ref
    )


CANDIDATES = {"A": (make_linked, pin_linked), "B": (make_shared_clone, pin_shared_clone)}


@dataclass
class Tree:
    sub: str
    path: pathlib.Path
    lease: pathlib.Path
    sha: str


def probe_identity(tree, policy, result):
    head = out(tree.path, "rev-parse", "HEAD")
    detached = git(tree.path, "symbolic-ref", "-q", "HEAD").returncode != 0
    result.answer(tree.sub, "gitlink_checks_out", head == tree.sha and detached, "HEAD %s" % head)
    top = out(tree.path, "rev-parse", "--show-toplevel")
    value = out(tree.path, "config", "--get", "core.worktree")
    detail = "toplevel %s, core.worktree %s" % (top, value or "(unset)")
    result.answer(tree.sub, "core_worktree_ignored", real(top) == real(tree.path), detail)
    named = policy.superproject(str(tree.path))
    result.answer(tree.sub, "superproject_names_lease", real(named) == real(tree.lease), named)


def probe_submodule_status(tree, result):
    line = git(tree.lease, "submodule", "status", "--", tree.sub).stdout.rstrip("\n")
    ok = line.startswith(" ") and line.split()[:2] == [tree.sha, tree.sub]
    result.answer(tree.sub, "submodule_status_works", ok, line)


def probe_hooks(tree, expected, result):
    value = out(tree.path, "config", "--get", "core.hooksPath")
    result.answer(tree.sub, "hooks_path_applies", bool(expected) and value == expected, value)
    done = git(
        tree.path,
        *("commit", "--allow-empty", "--no-gpg-sign", "-m", PROBE_MESSAGE),
        env={"GIT_TRACE": "1"},
    )
    wanted = "%s/pre-commit" % expected.rstrip("/")
    said = [line for line in done.stderr.splitlines() if " trace: " not in line]
    detail = "commit rc %d %s" % (done.returncode, " ".join(said)[:200])
    exact = re.compile(re.escape(wanted) + r"(\s|$)")
    ran = any("run_command:" in line and exact.search(line) for line in done.stderr.splitlines())
    result.answer(tree.sub, "hook_fires", bool(expected) and ran, detail)


def probe_gitlink_row(tree, result):
    row = out(tree.lease, "status", "--porcelain=v2", "--", tree.sub)
    fields = row.split()
    moved = out(tree.path, "rev-parse", "HEAD") != tree.sha
    ok = moved and len(fields) > 2 and fields[2] == "SC.."
    result.answer(tree.sub, "status_reads_gitlink", ok, row)


def probe_pin(repo, tree, pin, result):
    ref = PIN_SPACE + tree.lease.name
    done = pin(repo, tree, ref)
    head = out(tree.path, "rev-parse", "HEAD")
    seen = out(repo.store(tree.sub), "rev-parse", "--verify", "-q", ref)
    detail = "rc %d, store reads %s" % (done.returncode, seen or "(nothing)")
    result.answer(tree.sub, "pin_reaches_store", bool(head) and seen == head, detail)
    drop_pins(repo.store(tree.sub), ref)


def record_gitlink(repo, sub, sha, result):
    store = repo.store(sub)
    done = git(store, "for-each-ref", "--contains", sha, "--format=%(refname)", "refs/remotes")
    if done.returncode != 0:
        result.gitlinks[sub] = {"sha": sha, "on_a_remote": None}
    else:
        result.gitlinks[sub] = {"sha": sha, "on_a_remote": bool(done.stdout.strip())}


def build_submodules(repo, lease, tip, make, result):
    made = []
    for sub in repo.submodules:
        sha = must(repo.root, "rev-parse", "%s:%s" % (tip, sub))
        record_gitlink(repo, sub, sha, result)
        tree = Tree(sub, lease / sub, lease, sha)
        with measured(result, "submodule:%s" % sub, repo.root):
            done = make(repo, tree, sha)
        if done.returncode == 0:
            made.append(tree)
        else:
            result.answer(sub, "gitlink_checks_out", ok=False, detail=done.stderr[:300])
    return made


def build_and_probe(repo, lease, tip, candidate, result):
    make, pin = CANDIDATES[candidate]
    policy = load_commit_policy()
    with measured(result, "console", repo.root):
        added = git(repo.root, "worktree", "add", "--detach", str(lease), tip)
    if added.returncode != 0:
        result.answer(CONSOLE, "console_detached", ok=False, detail=added.stderr[:300])
        return
    head = out(lease, "rev-parse", "HEAD")
    detached = git(lease, "symbolic-ref", "-q", "HEAD").returncode != 0
    result.answer(CONSOLE, "console_detached", head == tip and detached, head)
    trees = build_submodules(repo, lease, tip, make, result)
    seed(repo, lease, result)
    if len(trees) == len(repo.submodules):
        status = out(lease, "status", "--porcelain")
        result.answer(CONSOLE, "console_status_clean", not status, status[:300])
    for tree in trees:
        expected = out(repo.store(tree.sub), "config", "--get", "core.hooksPath")
        probe_identity(tree, policy, result)
        probe_submodule_status(tree, result)
        probe_hooks(tree, expected, result)
        probe_gitlink_row(tree, result)
        probe_pin(repo, tree, pin, result)


def run_candidate(repo, tip, candidate):
    result = Result(candidate)
    lease = repo.holder / ("%s%s-%d" % (PREFIX, candidate, os.getpid()))
    repo.holder.mkdir(parents=True, exist_ok=True)
    try:
        build_and_probe(repo, lease, tip, candidate, result)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        result.answer(CONSOLE, "run_error", ok=False, detail=exc)
    finally:
        hold_signals()
        with measured(result, "removal", repo.root):
            result.leftovers = remove_lease(repo, lease)
        arm_signals()
    for sub in repo.submodules:
        done = git(repo.store(sub), "fsck", "--no-progress")
        detail = "rc %d %s" % (done.returncode, done.stderr.strip()[:200])
        result.answer(sub, "fsck_clean_after_removal", done.returncode == 0, detail)
    result.fill_unreached(repo.submodules)
    return result


def decide(results):
    """The plan's rule: A, unless an answer fails or its submodule time exceeds B's by more than 2x. The console tree and the seed do not depend on the candidate, so they stay out of the ratio."""
    a, b = results["A"], results["B"]
    if not a.passed():
        return ("B", "A failed an answer") if b.passed() else (None, "no candidate passed")
    limit = SLOWER_LIMIT * b.submodule_seconds()
    if b.passed() and a.submodule_seconds() > limit:
        return "B", "A took more than %.1fx B" % SLOWER_LIMIT
    return "A", "every answer passed and A is within %.1fx B" % SLOWER_LIMIT


def snapshot(repo):
    """The shared files a lease must leave byte-identical, plus the branch names and linked trees of each store."""
    git_dir = repo.root / ".git"
    stores = [git_dir, *(repo.store(s) for s in repo.submodules)]
    state = {}
    for store in stores:
        for rel in ("config", "info/exclude"):
            path = store / rel
            state[str(path)] = path.read_bytes() if path.exists() else None
        state["%s branches" % store] = out(
            store, "for-each-ref", "--format=%(refname)", "refs/heads"
        )
        state["%s trees" % store] = sorted(listed_trees(store))
    return state


def changed_between(before, after):
    return sorted(key for key in before if before[key] != after[key])


def report(results, decision, why, changed, stale):
    for name, result in results.items():
        print("\n## Candidate %s" % name)
        print("| step | seconds | disk KiB | inodes |\n|---|---|---|---|")
        for step, row in result.steps.items():
            print("| %s | %s | %s | %s |" % (step, row["seconds"], row["disk_kib"], row["inodes"]))
        print(
            "submodule seconds %.3f, total %.3f"
            % (result.submodule_seconds(), result.total_seconds())
        )
        print("\n| answer | ok | detail |\n|---|---|---|")
        for key, row in result.answers.items():
            print("| %s | %s | %s |" % (key, "yes" if row["ok"] else "NO", row["detail"][:160]))
        print("gitlinks: %s" % json.dumps(result.gitlinks, sort_keys=True))
        print("leftovers: %s" % (result.leftovers or "none"))
    raw = {name: vars(result) for name, result in results.items()}
    print("\nRAW: %s" % json.dumps(raw, sort_keys=True))
    print("shared state changed: %s" % (changed or "none"))
    print("stale trees the sweep could not remove: %s" % (stale or "none"))
    print("Decision: %s -- %s" % (decision or "none", why))


def run_spike(repo):
    if not (repo.root / ".git").is_dir():
        print("refused: %s is not a main checkout" % repo.root, file=sys.stderr)
        return 1
    repo.holder.mkdir(parents=True, exist_ok=True)
    with open(repo.holder / ".spike.lock", "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("refused: another spike run holds %s" % lock.name, file=sys.stderr)
            return 1
        return run_locked(repo)


def run_locked(repo):
    stale = sweep_stale(repo)
    tip = must(repo.root, "rev-parse", "HEAD")
    before = snapshot(repo)
    results = {name: run_candidate(repo, tip, name) for name in CANDIDATES}
    changed = changed_between(before, snapshot(repo))
    decision, why = decide(results)
    report(results, decision, why, changed, stale)
    survived = [path for result in results.values() for path in result.leftovers]
    return 0 if decision and not survived and not changed and not stale else 1


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_all(cwd, subject):
    must(cwd, "add", "-A")
    must(cwd, "commit", "--no-gpg-sign", "-m", subject)


def build_fixture(base, *, plant):
    """A console with one submodule whose gitlink sits on a commit no remote holds, with hooks on and seedable dirs."""
    origin = base / "sub-origin"
    must(base, "init", "-q", "-b", "main", str(origin))
    write(origin / ".gitignore", "node_modules/\n")
    write(origin / "code.txt", "pushed\n")
    commit_all(origin, "sub: first")

    root = base / "console"
    must(base, "init", "-q", "-b", "main", str(root))
    hooks = base / "hooks"
    write(hooks / "pre-commit", "#!/bin/sh\nexit 0\n")
    (hooks / "pre-commit").chmod(0o755)
    must(root, "config", "core.hooksPath", str(hooks))
    write(root / ".gitignore", "node_modules/\nbin/\n.claude/worktrees/\n")
    write(root / "code.txt", "console\n")
    sub = "private/sub"
    must(root, "-c", "protocol.file.allow=always", "submodule", "add", str(origin), sub)
    commit_all(root, "console: first")

    live_sub = root / sub
    must(live_sub, "config", "core.hooksPath", str(hooks))
    write(live_sub / "code.txt", "local only\n")
    commit_all(live_sub, "sub: local only")
    commit_all(root, "console: gitlink on a local commit")
    sha = must(live_sub, "rev-parse", "HEAD")
    if out(live_sub, "for-each-ref", "--contains", sha, "refs/remotes"):
        message = (
            "fixture control: the gitlink commit is on a remote, so the fixture proves nothing"
        )
        raise RuntimeError(message)

    write(root / "node_modules" / "x" / "a.js", "1\n")
    write(root / "packages" / "a" / "node_modules" / "y" / "b.js", "2\n")
    write(live_sub / "node_modules" / "z" / "c.js", "3\n")

    if plant:
        must(root, "update-index", "--cacheinfo", "160000,%s,%s" % (MISSING_SHA, sub))
        must(root, "commit", "--no-gpg-sign", "-m", "console: planted missing gitlink")
    return Repo(root, [sub])


def run_fixture(*, plant):
    base = pathlib.Path(tempfile.mkdtemp(prefix="worktree-spike-")).resolve()
    try:
        return run_spike(build_fixture(base, plant=plant))
    finally:
        hold_signals()
        shutil.rmtree(base, ignore_errors=True)
        arm_signals()


def live_repo():
    listed = out(ROOT, "config", "-f", ".gitmodules", "--get-regexp", r"\.path$").splitlines()
    return Repo(ROOT, sorted(line.split(" ", 1)[1] for line in listed))


def interrupted(signum, _frame):
    message = "signal %d" % signum
    raise InterruptedRunError(message)


def arm_signals():
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)


def hold_signals():
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, signal.SIG_IGN)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", action="store_true", help="run in a throwaway fixture")
    mode.add_argument("--live", action="store_true", help="run on the real tree")
    parser.add_argument(
        "--plant-missing-gitlink",
        action="store_true",
        help="with --fixture: point the gitlink at a commit the store lacks, which must exit 1",
    )
    args = parser.parse_args(argv)
    if args.plant_missing_gitlink and not args.fixture:
        parser.error("--plant-missing-gitlink needs --fixture")
    arm_signals()
    try:
        return (
            run_fixture(plant=args.plant_missing_gitlink)
            if args.fixture
            else run_spike(live_repo())
        )
    except InterruptedRunError as exc:
        print("interrupted: %s; every tree made so far was removed" % exc, file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
