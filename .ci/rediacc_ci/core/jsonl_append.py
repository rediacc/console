"""Append JSON lines to a shared file under a blocking flock: ONE implementation for every appender on this machine.

LIFTED FROM `.claude/hooks/stop/wl_store.py` `_append_lines` (PLAN-gate-scheduling-learned T2). The worklist event store, the reggate, hint and census ledgers and now the gate outcome ledger (`rediacc_ci.ci.gate_ledger`) all append to files several processes write at once. Two copies of the same three rules drift, so the hook module loads this file BY PATH and calls it; there is no second copy.

THE THREE RULES, each paid for:
  1. A blocking `flock` on a SEPARATE lock file. The data file is opened O_APPEND, so the lock does not have to cover the open, and a reader never takes it.
  2. One `os.write` per BATCH. A batch is serialised in memory first, so the lines of one call land contiguously even if another process's write follows immediately; there is no per-line write a peer could interleave with.
  3. A TORN TAIL IS HEALED. If the file's last byte is not a newline, a writer crashed mid-line; one newline is prepended, so the torn fragment stays its own unparseable line instead of merging with (and corrupting) the first line of this batch.

STDLIB ONLY, on purpose: the Stop hook loads this module by file path (`importlib.util.spec_from_file_location`, the `wl_ci._load_diagnose` shape) because a hook may not hop `sys.path` into `.ci` (test_canonical_sys_path_hop.py), so nothing here may import the rest of `rediacc_ci`.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

try:
    import fcntl
except ImportError:  # Windows: no POSIX advisory locking
    fcntl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# POSIX's values, kept so a caller that passes its own lock shim reads the same with or without fcntl present.
LOCK_EX = getattr(fcntl, "LOCK_EX", 2)


def flock(handle: Any, flags: int) -> None:
    """flock, or a NAMED refusal on a platform without one (never an ImportError raised from a file nobody was looking at)."""
    if fcntl is None:
        raise RuntimeError(
            "JSONL appends need file locking, which this platform does not provide (fcntl is POSIX-only)."
        )
    fcntl.flock(handle, flags)


def encode(payloads: Iterable[Any]) -> bytes:
    """Compact JSON, one line per payload. The caller passes DICTS: a pre-encoded string would be double-encoded into a JSON string (wl_reggate.py's own note)."""
    return "".join(json.dumps(p, separators=(",", ":")) + "\n" for p in payloads).encode("utf-8")


def append_lines(
    path: str | os.PathLike[str],
    lock_path: str | os.PathLike[str],
    payloads: Iterable[Any],
    *,
    lock: Callable[[Any, int], None] | None = None,
) -> int:
    """Append `payloads` as JSON lines to `path` under an exclusive flock on `lock_path`. Returns the bytes written.

    `lock` replaces `flock` for a caller with its own refusal wording (wl_store passes its `_flock`, so a worklist write on a lockless platform still names the worklist).
    """
    take = flock if lock is None else lock
    with open(lock_path, "w") as handle:
        take(handle, LOCK_EX)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            size = os.fstat(fd).st_size
            blob = b""
            if size and os.pread(fd, 1, size - 1) != b"\n":
                blob = b"\n"
            blob += encode(payloads)
            view = memoryview(blob)
            written = 0
            while written < len(view):
                # os.write may write fewer bytes than asked (a signal, a full pipe, a quota edge); the remainder is a torn line unless it is looped.
                written += os.write(fd, view[written:])
            return written
        finally:
            os.close(fd)
