"""One lock per checkout between the builders of the shared preparation (`npm install`, the `packages/shared` build) and the readers of what they build.

THE RACE IT CLOSES (worklist #6fbf7fa3, 2026-11-11). `rediacc_ci.setup.build_packages` deletes `packages/shared/dist` before `tsc` writes it again, and `ensure_deps` runs `npm install` over the live `node_modules`. `ensure_packages_built` and `ensure_deps` decide to do that from a stamp, check then build, with nothing held.
vm:check runs its A1 suites on a thread beside A0, and A0's `./run.sh account dev` reached both builders while A1.1's vitest was importing: the run vmc-11111054 has vitest starting at 10:54:52Z, `npm install` rewriting the lockfile at 10:54:58Z and `packages/shared/dist` rebuilt at 10:55:17Z, and two suites failing with `Cannot find package '@rediacc/shared/config-crypto'`.

THE RULE. A builder takes the lock EXCLUSIVE and re-reads its stamp under it, so a second builder that waited finds the work done and builds nothing. A reader that must not see a half-built tree (a test suite importing `@rediacc/shared`) holds it SHARED, so a builder waits until it has finished.
A builder whose stamp is current takes no lock at all, which is what keeps a reader's own children (whose preparation the reader did first) from waiting on their parent.

A BOUNDED WAIT. A child that finds its stamp stale while an ancestor holds the lock shared would wait on its own parent; `flock` cannot tell the two apart. The wait ends after `WAIT_S` with `PrepareLockTimeoutError`, naming the lock, instead of hanging until a suite timeout kills it.

THE PATH is outside the checkout, keyed by the checkout's real path, so the lock file is never a tree write and every process that resolves the same root meets the same lock.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
import tempfile
import time
from typing import TYPE_CHECKING

from rediacc_ci import log

if sys.platform != "win32":
    import fcntl

if TYPE_CHECKING:  # annotation-only import
    from collections.abc import Iterator

# A builder that waits on readers waits for at most a full A1 battery (about 150 s measured), and a reader that waits on a builder waits for `npm install` plus the shared build.
WAIT_S = 600.0
POLL_S = 0.2


class PrepareLockTimeoutError(RuntimeError):
    """The lock stayed held by another process for longer than the wait allows."""


def lock_path(root: str) -> str:
    """The lock file of the checkout at `root`: one per real path, in the temporary directory."""
    digest = hashlib.sha256(os.path.realpath(root).encode("utf-8", "surrogateescape")).hexdigest()
    return os.path.join(tempfile.gettempdir(), "rediacc-prepare-%s.lock" % digest[:16])


@contextlib.contextmanager
def held(root: str, *, shared: bool, wait_s: float = WAIT_S) -> Iterator[None]:
    """Hold the checkout's lock, shared for a reader and exclusive for a builder, for the body of the `with`."""
    if sys.platform == "win32":
        # No `flock` on Windows; the builders and readers this lock orders (vm:check, the account suites) run on Linux and macOS only.
        yield
        return
    path = lock_path(root)
    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    with open(path, "a", encoding="utf-8") as handle:
        deadline = time.monotonic() + wait_s
        announced = False
        while True:
            try:
                fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not announced:
                    log.step(
                        "Waiting for %s: another process is %s the shared packages"
                        % (path, "building" if shared else "building or reading")
                    )
                    announced = True
                if time.monotonic() >= deadline:
                    raise PrepareLockTimeoutError(
                        "%s stayed held for %d s; a process %s the shared packages for that long, or this one is a child of the reader holding it"
                        % (path, int(wait_s), "building" if shared else "building or reading")
                    ) from None
                time.sleep(POLL_S)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
