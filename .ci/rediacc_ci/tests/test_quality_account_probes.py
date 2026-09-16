"""`rediacc_ci.quality.account_probes` against the shell shapes it reproduces.

WHAT IS WORTH TESTING HERE, and it is not "does the gate exit 1 on a broken
probe". The shadow ledger `.ci/shadow/w7p2-account-probes.observations.jsonl`
drives the whole gate over five distinct trees carrying a missing library, a
library with no probe, the 2026-08-04 defect, an always-dead probe and an
inverted one. What a ledger row cannot isolate is the three pieces whose exact
SHAPE decides whether the gate is measuring anything at all:

  * `historical_capture`, which must reproduce bash's `$(curl ... || echo 000)`
    concatenation. A port that returned a boolean, or that dropped the fallback,
    would make assertion 3 report "the defect no longer reproduces" on a machine
    where it reproduces perfectly.
  * `probe_script`, whose `set +eu` and `declare -F ... || exit 3` are the two
    lines standing between "the probe says dead" and "the library never loaded".
  * `ci_lib_dir`, which is PRINTED in the load-failure message. The twin exports
    an unresolved `$SCRIPT_DIR/../../lib` and prints it verbatim; the resolved
    spelling names the same directory and different bytes.

Each is compared against the real bash rather than against a remembered
description of it.
"""

import pathlib
import socket
import subprocess

from rediacc_ci.quality import account_probes as ap
from rediacc_ci.tests import differential as diff


def _free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def test_historical_capture_matches_bash_on_a_closed_port() -> None:
    """The 2026-08-04 line, run as bash, must produce what the port produces.

    This is the assertion the whole gate rests on: `%{http_code}` yields `000`
    on a refused connection AND curl exits non-zero, so the `|| echo 000`
    fallback appends a second one and the value is `000000`.
    """
    port = _free_port()
    script = (
        "code=$(curl -s -o /dev/null -m 2 -w '%%{http_code}' "
        '"http://127.0.0.1:%d/" 2>/dev/null || echo 000); printf %%s "$code"' % port
    )
    code, out, _err = diff.bash_streams(script)
    assert code == 0
    assert out == "000000", out
    assert ap.historical_capture(port) == out


def test_historical_capture_matches_bash_on_a_live_port() -> None:
    """The mirror. Without it, a capture hard-wired to '000000' would pass above.

    A live port makes curl exit 0, so the fallback never runs and the value is
    the real status code with no concatenation.
    """
    port = _free_port()
    server = ap.start_listener(port)
    try:
        assert ap.listener_ready(port) is True
        script = (
            "code=$(curl -s -o /dev/null -m 2 -w '%%{http_code}' "
            '"http://127.0.0.1:%d/" 2>/dev/null || echo 000); printf %%s "$code"' % port
        )
        code, out, _err = diff.bash_streams(script)
        assert code == 0
        assert out == "200", out
        assert ap.historical_capture(port) == out
    finally:
        server.kill()
        server.wait()


def test_probe_script_carries_both_letters_of_set_plus_eu(tmp_path: pathlib.Path) -> None:
    """Under strict flags the library never loads, and that reads as "dead".

    `.ci/lib/account.sh:8` is `[[ -n "${ACCOUNT_LIB_LOADED:-}" ]] && return 0`,
    an `&&` list that returns NON-ZERO on a first load. Under `set -e` the
    sourcing shell dies AT THE SOURCE LINE, before `declare -F` can report the
    missing function, so the subshell exits 1 -- which is exactly what a healthy
    probe returns for a closed port. The two states are indistinguishable, and a
    gate that took the strict form would report a PASS on assertion 1 while
    testing nothing at all.

    Shown against a LIVE port, because that is the only place the difference is
    visible: `+eu` says ALIVE and `-eu` says the same thing a dead port says.
    """
    root = _fixture(tmp_path, ap.FIXTURE_HEALTHY)
    port = _free_port()
    server = ap.start_listener(port)
    try:
        assert ap.listener_ready(port) is True
        assert ap.probe_rc(root, port) == 0
        strict = ap.probe_script(port).replace("set +eu", "set -eu")
        proc = subprocess.run(
            ["bash", "-c", strict],
            cwd=str(root),
            env={**diff.env_for(), "CI_LIB_DIR": ap.ci_lib_dir(root)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        assert proc.returncode != 0
        # And the shape of the trap: the strict failure is the SAME status a
        # healthy probe returns for a closed port, so nothing downstream could
        # tell them apart.
        assert proc.returncode == ap.probe_rc(root, _free_port())
    finally:
        server.kill()
        server.wait()


def test_probe_script_distinguishes_a_missing_function_from_a_dead_port(
    tmp_path: pathlib.Path,
) -> None:
    """Exit 3 and exit non-3 are two different findings, and both must be real."""
    healthy = _fixture(tmp_path / "healthy", ap.FIXTURE_HEALTHY)
    nofn = _fixture(tmp_path / "nofn", ap.FIXTURE_NO_FUNCTION)
    assert ap.probe_rc(nofn, 1) == ap.LOAD_FAILED_RC
    dead = ap.probe_rc(healthy, _free_port())
    assert dead != 0
    assert dead != ap.LOAD_FAILED_RC


def test_ci_lib_dir_matches_the_twins_unresolved_spelling() -> None:
    """`$SCRIPT_DIR/../../lib`, evaluated by bash, must equal what the port prints.

    The twin never resolves the path and prints it in the load-failure message,
    so a port that tidied it would report a different finding for the same
    defect. Compared against bash's own expansion rather than against a copy of
    the string, so a change to the twin's layout is visible here.
    """
    root = pathlib.Path("/x/y")
    script = 'SCRIPT_DIR=%s/.ci/scripts/quality; printf %%s "$SCRIPT_DIR/../../lib"' % root
    code, out, _err = diff.bash_streams(script)
    assert code == 0
    assert ap.ci_lib_dir(root) == out


def test_free_port_hands_back_a_bindable_port() -> None:
    """A port the kernel chose and then released, not merely a number."""
    port = ap.free_port()
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
    finally:
        sock.close()


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, driven from pytest.

    Exit 0 with zero controls is a failure, so the floor inside `Controls` is
    the thing being exercised here as much as the controls themselves.
    """
    assert ap.selftest() == 0


def _fixture(root: pathlib.Path, body: str) -> pathlib.Path:
    """A throwaway tree carrying just the two files the probe library needs.

    `.ci/scripts/quality` is created empty because CI_LIB_DIR is the twin's
    unresolved `.../.ci/scripts/quality/../../lib`, and the kernel resolves `..`
    against directories that actually exist.
    """
    (root / ".ci" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "lib" / "account.sh").write_text(body, encoding="utf-8")
    (root / ".ci" / "lib" / "find-port.sh").write_text(ap.FIXTURE_FIND_PORT, encoding="utf-8")
    return root
