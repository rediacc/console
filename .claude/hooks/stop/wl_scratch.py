"""`worklist.py --prune-scratch <me> [--write] [--older-than <min>]`: list (and with --write, delete) the finished directories under THIS session's scratchpad.

WHY (worklist #edd646a8). /tmp is a tmpfs capped at 1,048,576 inodes, and on 2026-10-09 it filled twice in one session: finished scratch clones (about 10,000 inodes each) and pytest basetemps (70,000-90,000 each) piled up under the session scratchpad, and nothing pruned them. `rediacc_ci.core.tmp_capacity` now refuses a run on a full /tmp and names this verb as the fix.

THE SCOPE IS ONE DIRECTORY, DERIVED, NEVER PASSED: `<tmp>/claude-<uid>/<munged project root>/<session id>/scratchpad`, the layout the harness writes and `wl_liveness` already reads. Only its direct child DIRECTORIES are candidates; a symlink child is never one, and the removal does not follow symlinks inside a candidate either (a clone's `node_modules` link to the checkout is unlinked, its target untouched).

WHICH DIRECTION IS EXPENSIVE. A wrong deletion destroys a writer's undelivered work or a live run's fixture; a wrong keep costs some inodes until the next prune. So a directory is deleted only when EVERY one of these holds, and anything in doubt is kept and listed with the reason:
  - nothing under it changed for `--older-than` minutes (default 120, the longest lease a worklist item can carry);
  - no live lease in the store (any session's `[>]` item) names it in its worker, note or text;
  - no process has its working directory inside it;
  - every git work tree in it (the directory itself, or up to two levels down) is clean and carries no commit missing from its remotes, OR its changes were delivered as `<scratchpad>/<name>.patch` written after the last change. A `git status` that fails is doubt, so it keeps;
  - no regular file sits outside every such work tree. Notes, logs and loose patches have no git status to vouch for them, so a directory with no work tree at all is kept unless it holds only directories and symlinks (review 7850c0c4.1: such a directory used to pass the git rule vacuously and be deleted).

ONE EXEMPTION, BY NAME AND SHAPE: a `pytest-<digits>` child (the name `rediacc_ci.runtmp._BASETEMP` reads) whose top level is the one pytest makes (`basetemp_shaped`) is a pytest `--basetemp`, and pytest itself deletes a given basetemp at the start of its next run (`_pytest/tmpdir.py`, `rm_rf(basetemp)`), so nothing in it is anyone's work. Its fixture repositories are not probed either: they routinely carry commits on no remote. The idle, lease and process rules still apply to it.

GITIGNORED FILES DO NOT KEEP A CLONE, BY DESIGN. Delivery is a `git diff` patch, which never carries an ignored path, so ignored content cannot be undelivered under this protocol; and every clone that ran a build or a test holds ignored output (`__pycache__`, `.pytest_cache`), so keeping on it would keep every clone and starve the /tmp this verb exists to free.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import time

DEFAULT_OLDER_MIN = 120
USAGE = "usage: worklist.py --prune-scratch <me> [--write] [--older-than <minutes>]"
# How deep under a candidate a git work tree is looked for. A clone is normally the candidate itself; one level of nesting (`run1/clone`) is common, two is the cap that keeps the probe cheap.
GIT_DEPTH = 2
# A pytest `--basetemp` directory; the same shape `rediacc_ci.runtmp._BASETEMP` reads.
BASETEMP = re.compile(r"^pytest-[0-9]+$")
# How many loose files the refusal names before it stops listing.
LOOSE_SHOWN = 3


def printable(text):
    """`text` with every undecodable byte as a `\\xNN` escape. A name from `os.scandir`/`os.listdir` that is not UTF-8 arrives with surrogates, and printing one raw raised UnicodeEncodeError on a strict stdout (or leaked the raw byte on a surrogateescape one), so every text this module hands out passes through here (review 30573c81.1)."""
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def scratchpad_for(root, me, session_id, tmp=None, uid=None):
    """(path, why): this session's scratchpad, or (None, why) when it cannot be named. `session_id` is the harness's full id when known; otherwise the one session directory whose name starts with `me`."""
    tmp = tmp or tempfile.gettempdir()
    uid = os.getuid() if uid is None else uid
    munged = re.sub(r"[^A-Za-z0-9]", "-", str(root))
    base = os.path.join(tmp, "claude-%s" % uid, munged)
    if session_id and session_id.startswith(me):
        return os.path.join(base, session_id, "scratchpad"), ""
    try:
        names = sorted(n for n in os.listdir(base) if n.startswith(me))
    except OSError:
        names = []
    if len(names) > 1:
        return None, "%d session directories under %s start with %s (%s); pass a longer <me>" % (
            len(names),
            base,
            me,
            ", ".join(names),
        )
    if not names:
        return None, "no session directory under %s starts with %s" % (base, me)
    return os.path.join(base, names[0], "scratchpad"), ""


def tree_facts(path):
    """(inode count, newest lstat mtime) of everything under `path`, itself included. Symlinks are counted, never followed."""
    count, newest = 0, 0.0
    stack = [path]
    while stack:
        here = stack.pop()
        try:
            st = os.lstat(here)
        except OSError:
            continue
        count += 1
        newest = max(newest, st.st_mtime)
        if stat.S_ISDIR(st.st_mode):
            try:
                with os.scandir(here) as it:
                    stack.extend(entry.path for entry in it)
            except OSError:
                continue
    return count, newest


def git_trees(path, depth=GIT_DEPTH):
    """Every directory at or under `path` (to `depth` levels) that holds a `.git` entry: a clone has a `.git` directory, a `git worktree add` tree a `.git` file."""
    found = []
    frontier = [(path, 0)]
    while frontier:
        here, level = frontier.pop()
        if os.path.lexists(os.path.join(here, ".git")):
            found.append(here)
            continue
        if level >= depth:
            continue
        try:
            with os.scandir(here) as it:
                frontier.extend(
                    (entry.path, level + 1) for entry in it if entry.is_dir(follow_symlinks=False)
                )
        except OSError:
            continue
    return found


def loose_files(path, trees):
    """Every regular file under `path` that no work tree in `trees` contains, as paths. Symlinks are never followed and never counted: removing one cannot lose what it points at."""
    skip = {os.path.normpath(t) for t in trees}
    out = []
    stack = [path]
    while stack:
        here = stack.pop()
        if os.path.normpath(here) in skip:
            continue
        try:
            with os.scandir(here) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(entry.path)
            else:
                out.append(entry.path)
    return sorted(out)


def basetemp_shaped(path):
    """Whether `path`'s top level is the one pytest builds under a basetemp: per-test directories ending in digits (`test_x0`, `<mktemp name>0`, `popen-gw3` under xdist) and `<name>current` symlinks, nothing else. A clone stored under a `pytest-<digits>` name carries `.git` and files at its top, so it fails this and is judged like any directory (review 30573c81.3). Unreadable is not the shape."""
    try:
        with os.scandir(path) as it:
            entries = list(it)
    except OSError:
        return False
    for entry in entries:
        if entry.name == ".git":
            return False
        if entry.is_symlink():
            if not entry.name.endswith("current"):
                return False
        elif not (entry.is_dir(follow_symlinks=False) and entry.name[-1:].isdigit()):
            return False
    return True


def status_paths(raw):
    """The changed paths in `git status --porcelain=v1 -z` output, one per change. A rename or copy writes `XY new NUL old NUL`; its old path is consumed with it, not read as an entry of its own (review 7850c0c4.3)."""
    fields = raw.split(b"\0")
    out = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        out.append(os.fsdecode(entry[3:]))
        if entry[:1] in (b"R", b"C") or entry[1:2] in (b"R", b"C"):
            i += 1
    return out


def git_doubt(tree, patch, label=None):
    """Why the work tree `tree` must be kept, or "" when it is safe to delete. `patch` is the `<scratchpad>/<name>.patch` path that counts as delivery; `label` names the tree in the reason (default: its path)."""

    # `--no-optional-locks` IS LOAD-BEARING: a plain `git status` refreshes `.git/index` when it finds stale stat data, which moves the very mtime the idle rule reads. The first live listing did exactly that to every clone in the scratchpad, so each one read "changed 0 min ago" on the next run and a prune run more often than `--older-than` would never have deleted anything.
    def git(*args):
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", tree, *args],
            capture_output=True,
            text=False,
            timeout=60,
            check=False,
        )

    try:
        status = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
        unpushed = git("rev-list", "-1", "HEAD", "--branches", "--not", "--remotes")
    except (OSError, subprocess.SubprocessError) as exc:
        return "git could not be run in %s (%s)" % (label or tree, exc)
    if status.returncode != 0:
        return "git status failed in %s (rc=%d)" % (label or tree, status.returncode)
    if unpushed.returncode != 0:
        return "git rev-list failed in %s (rc=%d)" % (label or tree, unpushed.returncode)
    if unpushed.stdout.strip():
        return "%s has commits on no remote (%s)" % (
            label or tree,
            unpushed.stdout.decode("utf-8", "replace").strip()[:12],
        )
    entries = status_paths(status.stdout)
    if not entries:
        return ""
    newest = 0.0
    for rel in entries:
        try:
            newest = max(newest, os.lstat(os.path.join(tree, rel)).st_mtime)
        except OSError:
            continue  # a deletion: the path is gone, and the patch below must still postdate the rest
    try:
        st = os.stat(patch)
    except OSError:
        return "%s has %d uncommitted change(s) and no %s" % (
            label or tree,
            len(entries),
            os.path.basename(patch),
        )
    if st.st_size == 0 or st.st_mtime < newest:
        return "%s has %d uncommitted change(s) newer than %s" % (
            label or tree,
            len(entries),
            os.path.basename(patch),
        )
    return ""


def lease_texts(items):
    """[(item id, text)] for every live lease in the store, whoever holds it: the worker, the lease note and the item's text, which is where a lease's note is folded in."""
    out = []
    for rec in items:
        if rec.get("state") != ">":
            continue
        out.append(
            (
                str(rec.get("id", "?")),
                " ".join(
                    str(rec.get(k) or "") for k in ("worker", "lease_note", "lastnote", "text")
                ),
            )
        )
    return out


def lease_holder(name, path, leases):
    """The id of the first live lease whose text names `name` (as a whole token) or `path`, or ""."""
    token = re.compile(r"(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])" % re.escape(name))
    for item_id, text in leases:
        if path in text or token.search(text):
            return item_id
    return ""


def process_cwds(proc="/proc"):
    """Every readable process working directory on this machine. Unreadable entries are skipped; they belong to other users, whose processes cannot be inside this user's scratchpad."""
    out: list[str] = []
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return out
    for pid in pids:
        try:
            out.append(os.readlink(os.path.join(proc, pid, "cwd")))
        except OSError:
            continue
    return out


def plan(scratch, older_min, leases, cwds, now=None):
    """[(name, path, inodes, idle minutes, delete?, reason)] for every child directory of `scratch`, in name order."""
    now = time.time() if now is None else now
    rows: list[tuple[str, str, int, float, bool, str]] = []
    try:
        entries = sorted(os.scandir(scratch), key=lambda e: e.name)
    except OSError:
        return rows
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        path = entry.path
        inodes, newest = tree_facts(path)
        idle = (now - newest) / 60.0
        why = ""
        if idle < older_min:
            why = "changed %d min ago (younger than %d)" % (idle, older_min)
        if not why:
            holder = lease_holder(entry.name, path, leases)
            if holder:
                why = "named by live lease #%s" % holder
        if not why:
            inside = [c for c in cwds if c == path or c.startswith(path + os.sep)]
            if inside:
                why = "%d process(es) work inside it" % len(inside)
        basetemp = bool(BASETEMP.match(entry.name)) and basetemp_shaped(path)
        if not why and not basetemp:
            patch = os.path.join(scratch, entry.name + ".patch")
            trees = git_trees(path)
            for tree in trees:
                why = git_doubt(tree, patch, os.path.relpath(tree, scratch))
                if why:
                    break
            if not why:
                loose = loose_files(path, trees)
                if loose:
                    shown = [os.path.relpath(f, scratch) for f in loose[:LOOSE_SHOWN]]
                    why = "%s holds %d file(s) outside any git work tree (%s%s)" % (
                        entry.name,
                        len(loose),
                        ", ".join(shown),
                        ", ..." if len(loose) > LOOSE_SHOWN else "",
                    )
        fine = (
            "idle, unleased, a pytest basetemp"
            if basetemp
            else "idle, unleased, no undelivered work"
        )
        rows.append((entry.name, path, inodes, idle, not why, why or fine))
    return rows


def _remove(path):
    """Delete `path` without following any symlink in it; read-only directories (a Go module cache) are made writable on the way."""

    def onexc(func, target, _exc):
        parent = os.path.dirname(target)
        for p in (parent, target):
            try:
                if not os.path.islink(p):
                    os.chmod(p, stat.S_IRWXU)
            except OSError:
                pass
        func(target)

    shutil.rmtree(path, onexc=onexc)


def prune(scratch, write, older_min, leases, cwds=None, now=None):
    """(rc, text): the listing, and with `write` the deletion. Refuses anything not a direct, non-symlink child of `scratch`."""
    if not os.path.isdir(scratch):
        return 0, printable("scratch: %s does not exist; nothing to prune" % scratch)
    real_scratch = os.path.realpath(scratch)
    rows = plan(scratch, older_min, leases, process_cwds() if cwds is None else cwds, now)
    lines = ["scratch: %s" % scratch]
    doomed = []
    for name, path, inodes, idle, delete, reason in rows:
        lines.append(
            "  %-6s  %-28s %10s inodes  idle %5d min  %s"
            % ("DELETE" if delete else "KEEP", name, f"{inodes:,}", idle, reason)
        )
        if delete:
            doomed.append((name, path, inodes))
    kept = len(rows) - len(doomed)
    gone = sum(n for _, _, n in doomed)
    head = "%d director%s under the scratchpad: %d deletable (%s inodes), %d kept" % (
        len(rows),
        "y" if len(rows) == 1 else "ies",
        len(doomed),
        f"{gone:,}",
        kept,
    )
    if not write:
        lines.append(head + "; listing only, rerun with --write to delete")
        return 0, printable("\n".join(lines))
    failed = []
    for name, path, _n in doomed:
        if os.path.islink(path) or os.path.dirname(os.path.realpath(path)) != real_scratch:
            failed.append("%s (not a direct child of the scratchpad; refused)" % name)
            continue
        try:
            _remove(path)
        except OSError as exc:
            failed.append("%s (%s)" % (name, exc))
    if failed:
        lines.append(head + "; PARTIAL, could not delete:")
        lines.extend("  " + f for f in failed)
        return 1, printable("\n".join(lines))
    lines.append(head + "; deleted %d, %s inodes freed" % (len(doomed), f"{gone:,}"))
    return 0, printable("\n".join(lines))


def parse_args(args):
    """(write, older_min) or raises ValueError with the usage."""
    write, older = False, DEFAULT_OLDER_MIN
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--write":
            write = True
        elif arg == "--older-than" and rest:
            try:
                older = int(rest.pop(0))
            except ValueError:
                raise ValueError(USAGE) from None
            if older < 0:
                raise ValueError(USAGE)
        else:
            raise ValueError(USAGE)
    return write, older


def verb(root, me, session_id, args, items):
    """(rc, text) for `--prune-scratch <me> ...`, after worklist.py has checked `<me>`. `items` are the store's folded records, read for live leases."""
    try:
        write, older = parse_args(args)
    except ValueError as exc:
        return 2, str(exc)
    scratch, why = scratchpad_for(root, me, session_id)
    if scratch is None:
        if why.startswith("no session directory"):
            return 0, printable("scratch: %s; nothing to prune" % why)
        return 1, printable("refused: %s" % why)
    return prune(scratch, write, older, lease_texts(items))
