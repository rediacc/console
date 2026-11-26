"""Prove a command leaves no temp behind, and list what the host's temp roots hold.

    python3 -m rediacc_ci.dev.temp_probe -- <cmd> [<args>...]
    python3 -m rediacc_ci.dev.temp_probe census [--all] [--no-source]

PROBE. `<cmd>` runs with TMPDIR set to a fresh 0700 directory. Before and after, the probe lists this uid's top-level entries in /tmp, /var/tmp/r<uid> and `$CLAUDE_CODE_TMPDIR`. It exits 1 when anything survives in the fresh directory, or when an entry appeared in a root outside it, which means the command ignored TMPDIR. Otherwise it exits with the command's own status (0 on a clean run). Every source fix of the host-temp plan cites rc 1 on the parent commit and rc 0 after the fix.

A command that fails by itself and leaks nothing returns its own non-zero status, never a masked 0.

CAVEAT. A second process of the same uid that writes to a shared root while the command runs shows up as a new entry, so the probe is read on a quiet root. The fresh directory is the probe's own and is removed after the report, read-only subdirectories the command left included; a directory that still cannot be removed is named on stderr. Nothing else is ever deleted.

CENSUS. Groups the entries of the roots by name prefix with count, size and inodes, and maps each prefix to the files naming it with `git grep`. By default only entries modified today are counted; `--all` counts every entry. Read-only.
"""

from __future__ import annotations

import datetime
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile

__all__ = ["census", "main", "prefix_of", "probe", "roots", "snapshot"]

IGNORED = "ignored TMPDIR"


def roots(environ=None):
    """The temp roots watched: /tmp, /var/tmp/r<uid> and `$CLAUDE_CODE_TMPDIR`, existing ones only."""
    env = os.environ if environ is None else environ
    found = [pathlib.Path("/tmp"), pathlib.Path("/var/tmp") / f"r{os.getuid()}"]
    claude = env.get("CLAUDE_CODE_TMPDIR")
    if claude:
        found.append(pathlib.Path(claude))
    seen = []
    for root in found:
        if root.is_dir() and root not in seen:
            seen.append(root)
    return seen


def snapshot(watched, skip=()):
    """`{path: mtime_ns}` of this uid's top-level entries in each root, minus `skip` paths."""
    uid = os.getuid()
    skipped = {os.path.realpath(p) for p in skip}
    found = {}
    for root in watched:
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            path = os.path.join(root, name)
            if os.path.realpath(path) in skipped:
                continue
            try:
                info = os.lstat(path)
            except OSError:
                continue
            if info.st_uid == uid:
                found[path] = info.st_mtime_ns
    return found


def probe(argv, watched=None, base=None, environ=None):
    """Run `argv` under a fresh TMPDIR. Returns `(rc, lines)`; rc is 1 on a leak, else the command's status."""
    watched = roots(environ) if watched is None else watched
    fresh = tempfile.mkdtemp(prefix="temp-probe-", dir=base)
    os.chmod(fresh, 0o700)
    try:
        before = snapshot(watched, skip=[fresh])
        env = dict(os.environ if environ is None else environ)
        env["TMPDIR"] = fresh
        try:
            status = subprocess.run(argv, env=env, check=False).returncode
        except OSError as err:
            return 127, [f"temp_probe: cannot run {argv[0]}: {err}"]
        after = snapshot(watched, skip=[fresh])
        survivors = sorted(os.listdir(fresh))
        added = sorted(path for path in after if path not in before)
        lines = [f"leaked in TMPDIR: {fresh}/{name}" for name in survivors]
        lines += [f"{IGNORED}: {path}" for path in added]
        if lines:
            return 1, lines
        return status, [f"temp_probe: clean (command rc {status})"]
    finally:
        _remove_fresh(fresh)


def _remove_fresh(fresh):
    """Remove the probe's own directory even when the command left a read-only subdirectory in it: a failed unlink or rmdir makes the parent writable and retries once. Errors past that are reported on stderr, never swallowed, so a directory left behind is named."""

    def retry(func, path, exc):
        if path == fresh:
            # The parent of the probe's own directory is the shared temp root, which the probe does not own: report instead of chmod.
            raise exc
        parent = os.path.dirname(path)
        os.chmod(parent, stat.S_IRWXU)
        if func is os.rmdir or func is os.unlink:
            func(path)
        elif os.path.isdir(path) and not os.path.islink(path):
            os.chmod(path, stat.S_IRWXU)
            shutil.rmtree(path, onexc=retry)

    try:
        shutil.rmtree(fresh, onexc=retry)
    except OSError as err:
        sys.stderr.write(f"temp_probe: cannot remove {fresh}: {err}\n")


def prefix_of(name):
    """The leading words of an entry name, up to the first random-looking segment: `elite-ab12` -> `elite-`."""
    parts = name.split("-")
    kept = []
    for part in parts[:-1]:
        if not re.fullmatch(r"[a-z]{2,}", part):
            break
        kept.append(part)
    if kept:
        return "-".join(kept) + "-"
    stripped = re.sub(r"[0-9a-zA-Z_]*$", "", name) if "-" in name else re.sub(r"[0-9_]+$", "", name)
    return stripped or name


def _usage(path):
    """`(bytes, inodes)` under `path`, never following links."""
    size = 0
    count = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            info = os.lstat(current)
        except OSError:
            continue
        count += 1
        size += info.st_blocks * 512
        if os.path.isdir(current) and not os.path.islink(current):
            try:
                stack.extend(os.path.join(current, n) for n in os.listdir(current))
            except OSError:
                continue
    return size, count


def _local_date(stamp):
    """The local calendar date of an epoch second, or of now when `stamp` is None."""
    moment = (
        datetime.datetime.now().astimezone()
        if stamp is None
        else datetime.datetime.fromtimestamp(stamp).astimezone()
    )
    return moment.date()


def census(watched=None, today_only=True, now=None):
    """`{prefix: {"count", "bytes", "inodes", "paths"}}` over the roots."""
    watched = roots() if watched is None else watched
    stamp = now or _local_date(None)
    groups = {}
    for path, mtime in snapshot(watched).items():
        if today_only and _local_date(mtime / 1e9) != stamp:
            continue
        size, inodes = _usage(path)
        row = groups.setdefault(
            prefix_of(os.path.basename(path)), {"count": 0, "bytes": 0, "inodes": 0, "paths": []}
        )
        row["count"] += 1
        row["bytes"] += size
        row["inodes"] += inodes
        row["paths"].append(path)
    return groups


def source_of(prefix, cwd=None):
    """The first tracked files naming `prefix`, via `git grep`, or `-` when none does."""
    try:
        done = subprocess.run(
            ["git", "grep", "-l", "-F", "--", prefix],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "-"
    files = done.stdout.split() if done.returncode == 0 else []
    return ", ".join(files[:3]) if files else "-"


def _human(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


USAGE = "Usage: python3 -m rediacc_ci.dev.temp_probe -- <cmd> [<args>...] | census [--all] [--no-source]\n"


def _run_census(args, out):
    groups = census(today_only="--all" not in args)
    rows = sorted(groups.items(), key=lambda item: -item[1]["bytes"])
    out.write(f"{'prefix':<34}{'count':>7}{'size':>12}{'inodes':>10}  source\n")
    for prefix, row in rows:
        source = "-" if "--no-source" in args else source_of(prefix)
        out.write(
            f"{prefix:<34}{row['count']:>7}{_human(row['bytes']):>12}{row['inodes']:>10}  {source}\n"
        )
    return 0


def main(argv=None, out=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    if argv and argv[0] == "census":
        return _run_census(argv[1:], out)
    if argv and argv[0] == "--":
        argv = argv[1:]
    elif argv:
        sys.stderr.write(USAGE)
        return 2
    if not argv:
        sys.stderr.write(USAGE)
        return 2
    status, lines = probe(argv)
    for line in lines:
        out.write(line + "\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
