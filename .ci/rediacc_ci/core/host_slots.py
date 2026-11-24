"""`with host_slot(weight):` -- hold `weight` cores of the machine-wide pool for a block of Python (PR-TASK 79b7e92e).

WHY. On 2026-11-24 the host sat at load 134 on 24 cores with about ten lease writers, while `core_lease.py status` reported 24 of 24 tokens free. The pool existed and was sound; the heavy work simply never asked it. `scripts/ci-runner/run.ts` draws from it through its broker and the session pytest wrapper draws through the `pytest` verb, but a Python entry point that starts heavy children itself had only the CLI's `run` verb, which execs and so cannot wrap a block. This is that block form.

THE POOL IS `core_lease`'s, NOT A SECOND ONE. One token per core, each a `flock` on `<i>.lock` under the per-user lease directory (`$XDG_RUNTIME_DIR/rediacc-cores`, else `/run/user/<uid>/rediacc-cores`, else `/tmp/rediacc-cores-<uid>`), which every worktree, lease and push clone of this user on this machine shares; that is wider than a git common directory, which a push clone does not share. Capacity is `REDIACC_CORE_LEASE_TOKENS` when set, else the cores this process may run on. A second limiter beside it would let each believe it owned the machine.

NO DEADLOCK, NO STALE HOLDER. A token is a kernel lock on an open descriptor, so a holder that dies by any signal, `kill -9` included, frees it when the kernel closes its descriptors; nothing counts files, so a crashed holder can never block anyone. Waiting is a poll of a non-blocking `flock` (`Pool.acquire(wait=True)`), never a sleep inside the kernel on one token. A block running under a lease its parent already holds (`CI_CORE_LEASE_HELD=1`, set by `core_lease.py run`, the pytest wrapper and run.ts for every gate) takes nothing and waits for nothing: waiting on its own parent's tokens would be the deadlock.

WAITING PRINTS ONE LINE, naming how many tokens are held, by how many live runs, and the command that names the holders.

A POOL THAT CANNOT BE OPENED IS LOUD, NOT A REFUSAL. An unusable lease directory (another user's, not creatable) prints one line naming the reason and runs the block unthrottled: this is a performance control, never a verdict, and refusing work over a broken throttle would stop every writer on the host. `core_lease.py status` reports the same directory, so the reason is checkable.

`weight` above the pool size is clamped to the pool size, so a request for 32 cores on a 24-token pool takes all 24 rather than waiting forever.

    from rediacc_ci.core.host_slots import host_slot
    with host_slot(4, label="lease seed") as cores:
        subprocess.run([...], env={**os.environ, **cores.env})
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import sys
from typing import TYPE_CHECKING

from rediacc_ci import core_lease

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

# Planted by tests/test_core_host_slots.py: a block that never hands its tokens back. The next block in the same process then waits on tokens its own finished predecessor still holds, which is the leak a context manager exists to rule out.
DEFECT = (
    "            pool.release(tokens)\n",
    "            pass\n",
)


@dataclasses.dataclass(frozen=True)
class Slot:
    """What the block holds: `cores` it may use, `held` when backed by tokens of its own, and the `env` a child must run under so it neither oversizes itself nor leases the same cores again."""

    cores: int
    held: bool
    nested: bool

    @property
    def env(self) -> dict[str, str]:
        out = {core_lease.ENV: str(self.cores)}
        if self.held or self.nested:
            out[core_lease.HELD_ENV] = "1"
        return out


def _say(stream, text: str) -> None:
    print("host_slots: %s" % text, file=stream, flush=True)


def waiting_line(pool: core_lease.Pool, weight: int, label: str) -> str:
    """The one line a waiter prints: what it wants, how much is held and by how many OTHER runs (the waiter's own marker is live too, and holds nothing), and who to ask."""
    held = len(pool.held_indices())
    runs = max(0, pool.live_runs() - 1)
    return (
        "%s waits for %d core slot(s): %d of %d held by %d other live run(s) on this machine "
        "(who: python3 .ci/rediacc_ci/core_lease.py status)"
        % (label or "this block", weight, held, pool.size, runs)
    )


@contextlib.contextmanager
def host_slot(
    weight: int = 1,
    *,
    label: str = "",
    timeout: float | None = None,
    environ: Mapping[str, str] | None = None,
    stream=None,
    pool: core_lease.Pool | None = None,
    on_wait: Callable[[str], None] | None = None,
) -> Iterator[Slot]:
    """Hold `weight` tokens for the `with` block, waiting for them. Raises TimeoutError when `timeout` seconds pass first."""
    env = os.environ if environ is None else environ
    stream = sys.stderr if stream is None else stream
    if weight < 1:
        msg = "host_slot weight must be at least 1, got %r" % (weight,)
        raise ValueError(msg)
    if env.get(core_lease.HELD_ENV) == "1":
        granted = core_lease.granted_cores(env)
        yield Slot(cores=min(weight, granted), held=False, nested=True)
        return
    if pool is None:
        try:
            pool = core_lease.Pool.from_env(env)
        except core_lease.LeaseError as exc:
            _say(
                stream,
                "the core pool is unusable (%s); %s runs UNTHROTTLED"
                % (exc, label or "this block"),
            )
            yield Slot(cores=weight, held=False, nested=False)
            return
    want = min(weight, pool.size)
    marker = pool.register(label)
    try:

        def notice() -> None:
            line = waiting_line(pool, want, label)
            if on_wait is not None:
                on_wait(line)
            _say(stream, line)

        tokens = pool.acquire(want, want, wait=True, timeout=timeout, label=label, on_wait=notice)
        if not tokens:
            msg = "%s: %d core slot(s) were not free within %ss" % (
                label or "host_slot",
                want,
                timeout,
            )
            raise TimeoutError(msg)
        try:
            yield Slot(cores=len(tokens), held=True, nested=False)
        finally:
            pool.release(tokens)
    finally:
        marker.close()
