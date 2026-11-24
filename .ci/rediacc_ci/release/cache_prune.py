"""Prune `.ci/cache/release`, the store `release:local` clones into.

Every release run clones the repository to `.ci/cache/release/<tree sha>` (`local.CLONE_REL`) and writes `out-<run id>/` and `run-<run id>.json` beside it. Nothing removed them: by 2026-11-24 six stale clones held 24 GB.

WHAT STAYS. The newest clone by mtime, and every `out-*` directory and `run-*.json` record newer than the age limit (14 days). Older clones, and old out directories and records, are deleted.

WHILE A RELEASE RUNS NOTHING IS DELETED. `release:local` holds an exclusive flock on `.run.lock` in this directory for the length of a real run, and the prune refuses while it cannot take that lock itself, so the clone of a running release is never touched.

WHAT IT CANNOT DELETE IS REPORTED. A release step that wrote as root leaves root-owned files an unprivileged prune cannot remove; each such top-level path is printed with the exact `sudo rm -rf` line, and the exit code is 1.

`PYTHONPATH=.ci python3 -m rediacc_ci.release.cache_prune [--dry-run] [--days N]` from the repository root. It has no package.json key: the hand-written half of that file only shrinks (`check:ci-package-key-budget`).
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import os
import re
import shlex
import shutil
import sys
import time
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Iterator

CLONE_REL = ".ci/cache/release"
LOCK_NAME = ".run.lock"
MAX_AGE_DAYS = 14
CLONE_RE = re.compile(r"^[0-9a-f]{40}$")
OUT_RE = re.compile(r"^out-.+$")
RECORD_RE = re.compile(r"^run-.+\.json$")
DAY = 86400


class PruneRefusedError(Exception):
    """A release:local run holds the lock."""


@contextlib.contextmanager
def run_lock(store: pathlib.Path, *, wait: bool = False) -> Iterator[None]:
    """The exclusive lock a real release run holds. `wait=False` raises PruneRefusedError when another process holds it."""
    store.mkdir(parents=True, exist_ok=True)
    with (store / LOCK_NAME).open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError as err:
            message = "a release:local run holds %s/%s" % (store, LOCK_NAME)
            raise PruneRefusedError(message) from err
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _mtime(path: pathlib.Path) -> float:
    return path.lstat().st_mtime


def candidates(store: pathlib.Path, now: float, days: int = MAX_AGE_DAYS) -> list[pathlib.Path]:
    """The paths a prune deletes: every clone but the newest, and each out directory or run record older than `days`."""
    if not store.is_dir():
        return []
    entries = [p for p in store.iterdir() if not p.is_symlink()]
    clones = sorted((p for p in entries if p.is_dir() and CLONE_RE.match(p.name)), key=_mtime)
    doomed = clones[:-1]
    cutoff = now - days * DAY
    for entry in entries:
        named = (entry.is_dir() and OUT_RE.match(entry.name)) or (
            entry.is_file() and RECORD_RE.match(entry.name)
        )
        if named and _mtime(entry) < cutoff:
            doomed.append(entry)
    return doomed


def _remove(path: pathlib.Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        with contextlib.suppress(OSError):
            path.unlink()


def sudo_line(path: pathlib.Path) -> str:
    return "sudo rm -rf %s" % shlex.quote(str(path))


def prune(
    store: pathlib.Path,
    *,
    now: float | None = None,
    days: int = MAX_AGE_DAYS,
    dry_run: bool = False,
    remover: Callable[[pathlib.Path], None] = _remove,
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """`(deleted, stuck)`. Raises PruneRefusedError while a release run holds the lock. `stuck` lists the paths still present after the delete."""
    doomed = candidates(store, time.time() if now is None else now, days)
    if dry_run:
        return doomed, []
    with run_lock(store):
        deleted: list[pathlib.Path] = []
        stuck: list[pathlib.Path] = []
        for path in doomed:
            remover(path)
            (stuck if os.path.lexists(path) else deleted).append(path)
    return deleted, stuck


def main(argv: list[str] | None = None, *, root: pathlib.Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rediacc_ci.release.cache_prune")
    parser.add_argument("--dry-run", action="store_true", help="list what would be deleted")
    parser.add_argument("--days", type=int, default=MAX_AGE_DAYS)
    args = parser.parse_args(argv)
    store = (root or paths.repo_root()) / CLONE_REL
    try:
        deleted, stuck = prune(store, days=args.days, dry_run=args.dry_run)
    except PruneRefusedError as err:
        print("cache_prune: refused: %s" % err, file=sys.stderr)
        return 2
    verb = "would delete" if args.dry_run else "deleted"
    for path in deleted:
        print("cache_prune: %s %s" % (verb, path))
    for path in stuck:
        print("cache_prune: cannot delete %s; run: %s" % (path, sudo_line(path)))
    print("cache_prune: %s %d path(s), %d stuck" % (verb, len(deleted), len(stuck)))
    return 1 if stuck else 0


if __name__ == "__main__":
    sys.exit(main())
