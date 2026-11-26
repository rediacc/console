"""The one reader for a quality gate's test seams: a scan-root override and a lowered corpus floor.

WHY THIS EXISTS. A gate that reads `*_ROOT`, `*_DIR` or `*_MIN` from the environment lets any process that sets it make a plain gate run scan another tree, or accept an empty corpus, and pass. Review findings d31194f4.1 and e626e6ae.1 found the same shape in two gates; this module is the shared fix, so the rule lives once.

THE RULE. A seam is honoured only for a path inside a PRIVATE scratch directory under the system temp base, which is where every test fixture lives (pytest's `tmp_path` and `tempfile.mkdtemp` both create 0700 directories owned by the user). Two conditions, both required (review findings 321c4189.1, a66ada74.1, a66ada74.2):

  (a) the path, symlinks followed, lies under the system temp base computed WITHOUT the environment: the first of `/tmp`, `/var/tmp`, `/usr/tmp` that is a writable directory, the order `tempfile` falls back to when TMPDIR, TEMP and TMP are unset. `tempfile.gettempdir()` honours TMPDIR, so whoever sets the seam could otherwise move "temp" onto the repository;
  (b) every directory from the path (its parent, for a file) up to but excluding that base is owned by the current uid and is neither group- nor other-writable. `/tmp` itself is world-writable, so (a) alone would honour a tree another user planted there.

Anything else is ignored with one note on stderr, so a plain run scans the repository. A floor override is honoured only together with a honoured scratch root, and a floor below one is refused whatever it says: a zero-file corpus is the shape these gates exist to reject.

THE READ STAYS AT THE CALL SITE. This module reads no environment variable. The env registry (`python_env_registry`) derives `<module>:<NAME>` pairs from a literal `os.environ.get("NAME")`, so each caller keeps that spelling and passes the value in: `seams.scratch_root("X_ROOT", os.environ.get("X_ROOT"))`.
"""

from __future__ import annotations

import os
import pathlib
import stat
import sys

# The POSIX fallback order of `tempfile._candidate_tempdir_list` with the environment entries (TMPDIR, TEMP, TMP) and the current directory left out: the current directory is usually the repository.
SYSTEM_TEMP_CANDIDATES = ("/tmp", "/var/tmp", "/usr/tmp")


#: Filesystem types that live in memory, which a pytest run's scratch must not fill.
RAM_FILESYSTEMS = ("tmpfs", "ramfs")

#: Where the kernel lists mounts; a module constant so a test can point it at a fixture.
PROC_MOUNTS = "/proc/mounts"


def _on_ram_filesystem(path: pathlib.Path) -> bool:
    """Whether the longest mount point above `path` is a RAM filesystem; False when the mount table cannot be read."""
    try:
        with open(PROC_MOUNTS, encoding="utf-8", errors="replace") as handle:
            rows = [line.split() for line in handle]
    except OSError:
        return False
    best_length = -1
    ram = False
    for row in rows:
        if len(row) < 3:
            continue
        # /proc/mounts escapes a space in a mount point as \040.
        mount = pathlib.Path(row[1].replace("\\040", " "))
        if path.is_relative_to(mount) and len(mount.parts) > best_length:
            best_length = len(mount.parts)
            ram = row[2] in RAM_FILESYSTEMS
    return ram


def system_temp_base() -> pathlib.Path | None:
    """The temp base `tempfile` uses when no environment variable names one, resolved; None when none is usable.

    The first usable candidate wins, except that one on a RAM filesystem (a tmpfs /tmp) yields to the next usable candidate on disk, so a pytest run's scratch stays off memory. When every usable candidate is in memory, or the mount table is unreadable, the first usable one is used.
    """
    usable = []
    for candidate in SYSTEM_TEMP_CANDIDATES:
        path = pathlib.Path(candidate)
        if path.is_dir() and os.access(path, os.W_OK | os.X_OK):
            usable.append(path.resolve())
    for path in usable:
        if not _on_ram_filesystem(path):
            return path
    return usable[0] if usable else None


def _refusal(path: str | pathlib.Path) -> str | None:
    """Why `path` is not a private scratch path, or None when it is one (rules (a) and (b) in the module docstring)."""
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return "this platform has no POSIX uid, so the scratch directory's owner cannot be checked"
    base = system_temp_base()
    if base is None:
        return "no system temp directory (%s) is usable" % ", ".join(SYSTEM_TEMP_CANDIDATES)
    resolved = pathlib.Path(path).resolve()
    if resolved == base or not resolved.is_relative_to(base):
        return "it is not inside the system temp directory %s; TMPDIR is not consulted" % base
    uid = getuid()
    # The deepest existing directory: the path itself, its parent for a file, or the nearest existing ancestor for a path not yet created.
    current = resolved
    while not current.is_dir():
        current = current.parent
    while current != base:
        info = os.stat(current)
        if info.st_uid != uid:
            return "%s is owned by uid %d, not the current uid %d" % (current, info.st_uid, uid)
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            return "%s is group- or other-writable (mode %o)" % (
                current,
                stat.S_IMODE(info.st_mode),
            )
        current = current.parent
    return None


def inside_temp(path: str | pathlib.Path) -> bool:
    """Whether `path` is a private scratch path: under the system temp base, symlinks followed, through directories only the current user owns and can write."""
    return _refusal(path) is None


def scratch_root(name: str, raw: str | None) -> pathlib.Path | None:
    """The resolved override when `raw` names a private scratch path, else None.

    None means the variable is unset or was ignored; an ignored one is reported on stderr, naming the variable and the reason, so a plain run says what it scanned.
    """
    if not raw:
        return None
    reason = _refusal(raw)
    if reason is None:
        return pathlib.Path(raw).resolve()
    print(
        "NOTE: %s=%s is not a private scratch path in the temp directory (%s), so it is ignored "
        "and the repository is scanned." % (name, raw, reason),
        file=sys.stderr,
    )
    return None


def floor(name: str, raw: str | None, default: int, *, honoured: bool) -> int:
    """A corpus floor: `raw` replaces `default` only when `honoured`, and the result is never below one.

    `honoured` is the caller's statement that a scratch root is in force. Without it a lowered floor is ignored with a note; a raised one needs no permission and is kept. A non-integer `raw` raises ValueError.
    """
    if default < 1:
        raise ValueError("%s: the default floor must be at least 1, got %d" % (name, default))
    if not raw:
        return default
    value = int(raw)
    if value >= default:
        return value
    if not honoured:
        print(
            "NOTE: %s=%s lowers the floor without a scratch root, so it is ignored (floor %d)."
            % (name, raw, default),
            file=sys.stderr,
        )
        return default
    return max(1, value)
