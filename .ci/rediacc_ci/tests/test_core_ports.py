"""`rediacc_ci.core.ports` against the bash it replaced, and against its shim.

THE TWIN IS FROZEN IN THIS FILE, and that needs saying out loud because it looks
like duplication. `.ci/lib/find-port.sh` no longer contains an implementation --
it delegates -- so running "the bash original" against the port cannot mean
sourcing that file any more. `FROZEN_DERIVE_SLOT` below is the pre-port body,
copied verbatim out of the commit that preceded the port, and it is the thing
the differential runs. A frozen twin keeps working after the shim lands, which a
live one does not; the cost is that it can rot, and the answer to that is that
its output is pinned by every case here.

WHAT THE CASES ACTUALLY GUARD.

  derive_slot        The value is USER-VISIBLE: it decides which port a
                     bookmarked devbox URL resolves to. A hash change moves
                     every existing worktree silently, so the differential runs
                     the real sha256 pipeline, not a stub.
  is_port_in_use     Asserted in BOTH DIRECTIONS against a REAL listener bound
                     in-process. A probe that always answers "free" passes any
                     one-directional test and then hands out an occupied port.
  find_consecutive_free_ports
                     Compared against the TWO-STAGE bash algorithm it replaced,
                     on a fixture whose first free port deliberately has no run
                     of three after it -- which is the only branch where the two
                     algorithms could have disagreed.
  the shim           Proved to FAIL CLOSED. Point REDIACC_CI_ROOT at a directory
                     with no package and sourcing must refuse, because the
                     alternative to refusing is answering with a plausible wrong
                     port.
"""

import shutil
import socket
import textwrap

import pytest

from rediacc_ci import paths
from rediacc_ci.core import ports
from rediacc_ci.tests import differential as diff

# The pre-port body of `.ci/lib/find-port.sh`, frozen. Copied from the file as
# it stood immediately before W7 phase 1, including `_sha256sum_portable` --
# whose macOS branch is the single clearest thing the port deleted, since
# hashlib has no such branch to write.
FROZEN_DERIVE_SLOT = textwrap.dedent("""
    derive_slot() {
        local key="$1"
        local slots="${2:-100}"
        local digest
        digest="$(printf '%s' "$key" | _sha256sum_portable | cut -c1-8)"
        echo $((0x$digest % slots))
    }
    _sha256sum_portable() {
        if command -v sha256sum >/dev/null 2>&1; then
            sha256sum
        else
            shasum -a 256
        fi
    }
""")

# The pre-port body of the probe, for the same reason.
FROZEN_IS_PORT_IN_USE = textwrap.dedent("""
    is_port_in_use() {
        local port="$1"
        if command -v ss &>/dev/null; then
            ss -tlnH "sport = :$port" 2>/dev/null | grep -q .
        elif command -v lsof &>/dev/null; then
            lsof -iTCP:"$port" -sTCP:LISTEN &>/dev/null
        elif command -v netstat &>/dev/null; then
            netstat -an 2>/dev/null | grep -qE ":$port\\b.*(LISTEN|LISTENING)"
        else
            return 1
        fi
    }
""")

SHIM = ".ci/lib/find-port.sh"

# A corpus rather than two hand-picked strings. Paths with spaces, a trailing
# slash, unicode and an empty component are all real worktree names somebody
# will eventually create, and each is a place a bash pipeline and a Python
# encode could diverge.
KEYS = [
    "/home/dev/console",
    "/home/dev/console/.worktrees/0824-1",
    "/home/dev/my console/with spaces",
    "/home/dev/console/",
    "/home/dev/console/ünïcode-ワークツリー",
    "/",
    "a",
    "",
    "/home/dev/console/.worktrees/" + "x" * 200,
    "/home/dev/console/tab\tinside",
]
SLOT_COUNTS = [1, 7, 100, 997]


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("slots", SLOT_COUNTS)
def test_derive_slot_matches_the_frozen_bash(key: str, slots: int) -> None:
    """The ported digest agrees with the bash pipeline it replaced, exactly."""
    script = FROZEN_DERIVE_SLOT + '\nderive_slot "$1" "$2"\n'
    rc, out, err = diff.bash_streams(
        f"set -- {_q(key)} {slots}\n{script}",
        env=diff.env_for(),
    )
    assert rc == 0, err
    assert out.strip() == str(ports.derive_slot(key, slots))


def test_derive_slot_is_stable_across_processes() -> None:
    """Five runs, one answer.

    Not a tautology about a pure function: the value has to survive being
    computed in a FRESH interpreter, because that is how the shim computes it,
    and Python's `hash()` -- the obvious wrong implementation -- is salted per
    process and would pass an in-process comparison while failing this.
    """
    samples = {
        diff.bash_streams(
            f"source {_q(str(paths.from_root(SHIM)))}; derive_slot /home/x/console 100",
            env=diff.env_for(),
        )[1].strip()
        for _ in range(5)
    }
    assert samples == {str(ports.derive_slot("/home/x/console", 100))}


def test_two_worktrees_get_different_slots() -> None:
    """The property the whole allocator exists for, asserted rather than assumed."""
    a = ports.derive_slot("/home/x/console", 100)
    b = ports.derive_slot("/home/x/console/.worktrees/0824-1", 100)
    assert a != b


def test_slot_is_always_in_range() -> None:
    for key in KEYS:
        for slots in SLOT_COUNTS:
            assert 0 <= ports.derive_slot(key, slots) < slots


@pytest.fixture
def listener():
    """A real TCP listener on a real ephemeral port, closed on teardown."""
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


def test_is_port_in_use_sees_a_real_listener(listener: int) -> None:
    assert ports.is_port_in_use(listener) is True


def test_is_port_in_use_control_the_same_port_is_free_once_closed() -> None:
    """CONTROL, and the direction that matters.

    Without it, an implementation that returns True unconditionally passes the
    case above. The socket is bound and closed inside the test so the assertion
    is about the same port in two states, not about two different ports.
    """
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    assert ports.is_port_in_use(port) is True
    sock.close()
    assert ports.is_port_in_use(port) is False


def test_is_port_in_use_matches_the_frozen_bash(listener: int) -> None:
    """Both directions, against the bash probe, in one case."""
    for port, expected in ((listener, 0), (_free_port(), 1)):
        rc, _, err = diff.bash_streams(
            FROZEN_IS_PORT_IN_USE + f"\nis_port_in_use {port}\n",
            env=diff.env_for(),
        )
        assert rc == expected, err
        assert ports.is_port_in_use(port) is (expected == 0)


def test_find_port_block_lands_on_the_derived_slot() -> None:
    """A free range must yield exactly range_start + slot * block."""
    slots = (17999 - 17000 + 1) // 10
    expected = 17000 + ports.derive_slot("/home/x/console", slots) * 10
    assert ports.find_port_block("/home/x/console", 17000, 17999, 10) == expected


def test_find_port_block_refuses_a_range_smaller_than_one_block() -> None:
    """The bash `[[ "$slots" -lt 1 ]] && return 1`, preserved."""
    assert ports.find_port_block("/home/x/console", 17000, 17004, 10) is None


def test_find_consecutive_free_matches_the_two_stage_bash() -> None:
    """The replaced algorithm and the replacement agree on the awkward case.

    The fixture occupies a port and the one two above it, so the FIRST free port
    has no run of three after it and the old code's fallback loop is the branch
    that produces the answer. On the easy case both are trivially right, which
    is why the easy case is not the one asserted.
    """
    base = _free_range_base(4)
    socks = []
    try:
        for offset in (0, 2):
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", base + offset))
            s.listen(1)
            socks.append(s)

        old = FROZEN_IS_PORT_IN_USE + textwrap.dedent(f"""
            b=""
            for c in $(seq {base} {base + 40}); do
              if ! is_port_in_use $c && ! is_port_in_use $((c+1)) && ! is_port_in_use $((c+2)); then
                b=$c; break
              fi
            done
            echo "$b"
        """)
        rc, out, err = diff.bash_streams(old, env=diff.env_for())
        assert rc == 0, err
        assert out.strip() == str(ports.find_consecutive_free_ports(3, base, base + 40))
        # And it is not the trivial answer: the planted listeners moved it.
        assert out.strip() != str(base)
    finally:
        for s in socks:
            s.close()


def test_shim_fails_closed_when_the_package_is_unreachable(tmp_path) -> None:
    """Sourcing the shim with no package must REFUSE, not fall back.

    A bash fallback would be a second implementation of the value that decides
    which port a bookmark resolves to, and two implementations drift. The
    contract is that `source` returns non-zero and defines nothing, so a caller
    gets `derive_slot: command not found` instead of a plausible number.
    """
    shim = str(paths.from_root(SHIM))
    rc, out, err = diff.bash_streams(
        f"source {_q(shim)}; derive_slot /home/x/console 100",
        env=diff.env_for(REDIACC_CI_ROOT=str(tmp_path)),
    )
    assert rc != 0
    assert out.strip() == ""
    assert "cannot find rediacc_ci" in err


def test_shim_control_the_same_command_works_against_the_real_root() -> None:
    """CONTROL for the case above: without it, a typo in the script would pass."""
    shim = str(paths.from_root(SHIM))
    rc, out, err = diff.bash_streams(
        f"source {_q(shim)}; derive_slot /home/x/console 100",
        env=diff.env_for(),
    )
    assert rc == 0, err
    assert out.strip() == str(ports.derive_slot("/home/x/console", 100))


def test_shim_delegation_is_real_not_a_reimplementation(tmp_path) -> None:
    """Break the PYTHON and the bash must break with it.

    This is the assertion that a shim is a shim. `.ci/scripts/quality/
    check-setup-idempotency.sh` control C makes the same one against the real
    gate; it is duplicated here so the package's own suite catches a shim that
    quietly grew a local implementation.
    """
    root = tmp_path / "broken-root"
    (root / ".ci").mkdir(parents=True)
    shutil.copytree(paths.from_root(".ci/rediacc_ci"), root / ".ci" / "rediacc_ci")
    target = root / ".ci" / "rediacc_ci" / "core" / "ports.py"
    text = target.read_text()
    assert "digest = hashlib.sha256" in text, "the line the control mutates has moved"
    target.write_text(
        text.replace(
            '    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:DIGEST_HEX_DIGITS]',
            '    digest = __import__("random").randbytes(4).hex()',
        )
    )

    shim = str(paths.from_root(SHIM))
    seen = {
        diff.bash_streams(
            f"source {_q(shim)}; derive_slot /home/x/console 100",
            env=diff.env_for(REDIACC_CI_ROOT=str(root)),
        )[1].strip()
        for _ in range(6)
    }
    assert len(seen) > 1, "the shim answered stably from a randomised module"


def _q(value: str) -> str:
    """Single-quote for bash. Small, and here rather than imported, because the
    two callers need exactly this and nothing more."""
    return "'" + value.replace("'", "'\\''") + "'"


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _free_range_base(count: int) -> int:
    """A base with `count` consecutive currently-free ports, found by asking."""
    base = ports.find_consecutive_free_ports(count + 3, 20000, 30000)
    assert base is not None, "no free run of ports on this host"
    return base
