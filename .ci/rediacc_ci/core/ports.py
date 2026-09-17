"""Port availability and the deterministic per-worktree port block.

PORTED FROM `.ci/lib/find-port.sh`, which delegated here and is now DELETED (W7P5-b): a shim is a delay, not an exit. Its three callers -- `.ci/lib/ devbox.sh`, `.ci/lib/account.sh` and `.ci/lib/service.sh` -- name this module directly, and `.ci/rediacc_ci/tests/test_core_ports.py` carries the assertion that devbox.sh really reaches it rather than having grown a local copy. The
original header said what it was for in two lines: find an available port
for test infrastructure, and avoid the conflicts that appear when several
worktrees run at once or the conventional port is already taken. Everything below is the reasoning that accumulated under those two lines.

--------------------------------------------------------------------------
WHY A DERIVED SLOT AND NOT A SCAN FROM A BASE
--------------------------------------------------------------------------
A scan-from-a-base allocator gives a worktree a different port after every reboot, which breaks bookmarks and makes "which checkout am I looking at?" unanswerable. `derive_slot` and `find_port_block` instead derive a STABLE slot
from a key -- the worktree's absolute path -- then fall back through
slot-aligned candidates, so the fallback stays block-aligned instead of colliding with a neighbour's block.

Walking ALL slots rather than giving up after the derived one is deliberate: a busy machine still gets a devbox.

--------------------------------------------------------------------------
WHY THE DIGEST IS SHA-256 TRUNCATED TO 8 HEX DIGITS
--------------------------------------------------------------------------
The bash original computed `sha256(key) | cut -c1-8` and reduced it modulo the slot count, with the comment "first 8 hex digits are plenty of entropy for <1k slots". That is preserved EXACTLY here, byte for byte in its effect, because the value is user-visible: it decides the port a bookmark points at. A "better" hash would silently move every existing worktree's devbox.

The bash file carried `_sha256sum_portable`, which chose `sha256sum` when present and `shasum -a 256` otherwise -- the macOS fallback. Python's `hashlib` makes that whole function disappear, and its disappearance is the single clearest argument for the port: the portability branch existed only because bash has no hash function.

`_sha256sum_portable` also carried a correction worth keeping, because it records a comment that was WRONG and was fixed by measurement. It said the
function must not depend on `local-common.sh` because find-port.sh is sourced
standalone by `check-account-probes.sh`. It is not. The gate that sourced it standalone was `.ci/scripts/quality/check-setup-idempotency.sh`, whose control C
ran `bash -c "source '$fp'; derive_slot ..."`; check-account-probes.sh sources
`.ci/lib/account.sh`, and account.sh was what pulled find-port.sh in. Both call sites now run this module directly (control C through PYTHONPATH, which is what the shim was setting anyway) and the shim is deleted. The constraint is real either way -- this module must stay importable on its own -- and the misattribution is recorded so nobody re-derives it from the wrong gate.

--------------------------------------------------------------------------
WHY THE PROBE STILL SHELLS OUT TO ss / lsof / netstat
--------------------------------------------------------------------------
This is the one place where a "pure Python" port would have been a behaviour change dressed as a cleanup, so it is argued rather than assumed.

The obvious Python spelling is to bind a socket and see whether it fails. That
asks a DIFFERENT QUESTION. `ss -tlnH "sport = :N"` reports a listener on ANY
address; a bind probe on 127.0.0.1 succeeds while something listens on
0.0.0.0, and a bind probe on 0.0.0.0 fails against a listener on 127.0.0.1 on some platforms and not others. Either direction produces a devbox that starts and then cannot be reached, which is precisely the failure the block allocator exists to prevent.

So the probe order is preserved exactly as the original had it:

    ss        Linux, the fast path
    lsof      macOS fallback
    netstat   Windows Git Bash fallback; the Windows listing format is
              "TCP  0.0.0.0:port  ...  LISTENING", hence the LISTEN|LISTENING
              alternation
    none      cannot determine, ASSUME THE PORT IS FREE

That last rung is a fail-OPEN, and the original chose it: with no tool at all, refusing every port would make the devbox unstartable on a machine where it would in fact work. Docker's own bind is the backstop. It is written down here so the next reader knows it was a decision and not an oversight.

--------------------------------------------------------------------------
COMMAND-LINE ENTRY POINT (what the bash shim calls)
--------------------------------------------------------------------------
    python3 -m rediacc_ci.core.ports derive-slot <key> [slots]
    python3 -m rediacc_ci.core.ports is-port-in-use <port>      exit 0 = in use
    python3 -m rediacc_ci.core.ports find-available-port [start] [end]
    python3 -m rediacc_ci.core.ports find-preferred-port <pref> [start] [end]
    python3 -m rediacc_ci.core.ports find-consecutive-free <n> [start] [end]
    python3 -m rediacc_ci.core.ports find-port-block <key> [start] [end] [block]

Every verb prints a bare number on stdout and exits 0, or prints nothing and exits 1, which is exactly what the bash functions did. `is-port-in-use` is the exception and carries the meaning in the exit code alone, as the bash predicate did.

`find-port-block` is a SINGLE verb rather than a loop the shim drives, for the reason in the subpackage docstring: the block search probes up to `slots x block` ports, and one interpreter per probe would cost tens of seconds.
"""

from __future__ import annotations

import hashlib
import re
import sys

from rediacc_ci import proc

# The bash defaults, kept as named constants so a call site that omits an argument and this module cannot drift apart. They are the values the devbox port block and every `run.sh` caller have been using.
DEFAULT_RANGE_START = 3000
DEFAULT_RANGE_END = 3999
DEFAULT_SLOTS = 100
DEFAULT_BLOCK_RANGE_START = 17000
DEFAULT_BLOCK_RANGE_END = 17999
DEFAULT_BLOCK_SIZE = 10

# How many hex digits of the digest feed the modulo. Named because it is the number that must never change: it decides which port an existing bookmark resolves to.
DIGEST_HEX_DIGITS = 8


def derive_slot(key: str, slots: int = DEFAULT_SLOTS) -> int:
    """A stable slot index in [0, slots) derived from an arbitrary key.

    sha256 of the key; the first 8 hex digits are plenty of entropy for fewer
    than a thousand slots. Identical in result to the bash `printf '%s' "$key" | sha256sum | cut -c1-8` followed by `$((0x... % n))`: no trailing newline is hashed, the digest is lowercase hex, and the modulo is taken over the truncated value rather than the whole digest.
    """
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:DIGEST_HEX_DIGITS]
    return int(digest, 16) % slots


def is_port_in_use(port: int) -> bool:
    """True when something is LISTENING on `port`, by the same probe bash used.

    See the module docstring for why this is not a socket bind. The final rung -- no tool available -- returns False, i.e. assume free, matching the bash `return 1`.
    """
    if proc.which("ss"):
        # -H suppresses the header so a match is a real row rather than the
        # column titles; the bash form piped to `grep -q .` for the same reason.
        result = proc.run(["ss", "-tlnH", f"sport = :{port}"])
        return bool(result.stdout.strip())
    if proc.which("lsof"):
        result = proc.run(["lsof", "-iTCP:%d" % port, "-sTCP:LISTEN"])
        return result.returncode == 0
    if proc.which("netstat"):
        result = proc.run(["netstat", "-an"])
        pattern = re.compile(rf":{port}\b.*(LISTEN|LISTENING)")
        return any(pattern.search(line) for line in result.stdout.splitlines())
    return False


def find_available_port(
    start_port: int = DEFAULT_RANGE_START, end_port: int = DEFAULT_RANGE_END
) -> int | None:
    """The first free port in [start_port, end_port], or None.

    None rather than an exception because the bash twin returned exit 1 and every caller already handles "no port".
    """
    for port in range(start_port, end_port + 1):
        if not is_port_in_use(port):
            return port
    return None


def find_preferred_port(
    preferred_port: int,
    fallback_start: int | None = None,
    fallback_end: int | None = None,
) -> int | None:
    """`preferred_port` when it is free, otherwise the first free fallback.

    The bash defaults for the fallback window were `preferred+1` and
    `preferred+999`, computed at call time from the preferred port; they are
    reproduced here rather than turned into constants, because they are RELATIVE to the argument.
    """
    if fallback_start is None:
        fallback_start = preferred_port + 1
    if fallback_end is None:
        fallback_end = preferred_port + 999
    if not is_port_in_use(preferred_port):
        return preferred_port
    return find_available_port(fallback_start, fallback_end)


def find_consecutive_free_ports(
    count: int,
    range_start: int = DEFAULT_RANGE_START,
    range_end: int = DEFAULT_RANGE_END,
) -> int | None:
    """The first base in [range_start, range_end] with `count` consecutive free ports.

    NEW IN THE PORT, AND IT IS A FIX RATHER THAN AN ADDITION, so it is argued here. `.ci/lib/account.sh::account_allocate_ports` needs three consecutive ports and did it with a bash loop over `seq 4800 5799` calling `is_port_in_use` up to three times per candidate. That was ~5.7 ms per probe
    while the probe was bash. Once the probe delegates to Python it is ~66 ms,
    measured on this host, because each call starts an interpreter -- so the worst case went from about 17 seconds to about 200. One verb that does the
    whole scan in one process removes the interpreter-per-probe cost entirely;
    the loop is the same loop.

    THE SEARCH WINDOW IS DELIBERATELY ASYMMETRIC and matches the bash exactly: `base` ranges over [range_start, range_end], and the ports it CHECKS are base .. base+count-1, which may run past range_end. The bash `for candidate in $(seq $START $END)` then testing `candidate+1` and `candidate+2` had the same shape, and preserving it is the point of a port.

    Equivalent to the whole of the bash block it replaces, including the `find_preferred_port` that ran first: a candidate below the first free port cannot start a free run, so scanning from `range_start` reaches the same base.
    """
    for base in range(range_start, range_end + 1):
        if not any(is_port_in_use(base + offset) for offset in range(count)):
            return base
    return None


def find_port_block(
    key: str,
    range_start: int = DEFAULT_BLOCK_RANGE_START,
    range_end: int = DEFAULT_BLOCK_RANGE_END,
    block: int = DEFAULT_BLOCK_SIZE,
) -> int | None:
    """The base port of a free, slot-aligned block of `block` consecutive ports.

    Tries the slot `key` derives to first, then every other slot in order, so a busy machine still gets a block rather than a refusal. Returns None when the range cannot hold a single block, or when every block has something listening in it -- the two `return 1` cases in the bash twin.
    """
    slots = (range_end - range_start + 1) // block
    if slots < 1:
        return None

    preferred_slot = derive_slot(key, slots)
    for i in range(slots):
        slot = (preferred_slot + i) % slots
        base = range_start + slot * block
        if not any(is_port_in_use(base + offset) for offset in range(block)):
            return base
    return None


# ---------------------------------------------------------------------------
# argv dispatch -- the surface .ci/lib/{devbox,account,service}.sh call, and
# what the deleted .ci/lib/find-port.sh shim used to call on their behalf ---------------------------------------------------------------------------


def _emit(value: int | None) -> int:
    """Print a number and exit 0, or print nothing and exit 1.

    The bash functions all had this shape and their callers read it with
    `port="$(...)" || handle-failure`, so an empty stdout on failure is part of
    the contract, not an accident of the implementation.
    """
    if value is None:
        return 1
    print(value)
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 -m rediacc_ci.core.ports <verb> [args]", file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]

    if verb == "derive-slot":
        key = rest[0]
        slots = int(rest[1]) if len(rest) > 1 and rest[1] else DEFAULT_SLOTS
        print(derive_slot(key, slots))
        return 0
    if verb == "is-port-in-use":
        # Exit code IS the answer, matching the bash predicate: 0 in use, 1 free.
        return 0 if is_port_in_use(int(rest[0])) else 1
    if verb == "find-available-port":
        start = int(rest[0]) if rest and rest[0] else DEFAULT_RANGE_START
        end = int(rest[1]) if len(rest) > 1 and rest[1] else DEFAULT_RANGE_END
        return _emit(find_available_port(start, end))
    if verb == "find-preferred-port":
        preferred = int(rest[0])
        start = int(rest[1]) if len(rest) > 1 and rest[1] else None
        end = int(rest[2]) if len(rest) > 2 and rest[2] else None
        return _emit(find_preferred_port(preferred, start, end))
    if verb == "find-consecutive-free":
        count = int(rest[0])
        start = int(rest[1]) if len(rest) > 1 and rest[1] else DEFAULT_RANGE_START
        end = int(rest[2]) if len(rest) > 2 and rest[2] else DEFAULT_RANGE_END
        return _emit(find_consecutive_free_ports(count, start, end))
    if verb == "find-port-block":
        key = rest[0]
        start = int(rest[1]) if len(rest) > 1 and rest[1] else DEFAULT_BLOCK_RANGE_START
        end = int(rest[2]) if len(rest) > 2 and rest[2] else DEFAULT_BLOCK_RANGE_END
        size = int(rest[3]) if len(rest) > 3 and rest[3] else DEFAULT_BLOCK_SIZE
        return _emit(find_port_block(key, start, end, size))

    print(f"unknown verb: {verb}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
