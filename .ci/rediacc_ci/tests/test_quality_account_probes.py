"""`rediacc_ci.quality.account_probes` against the shell shape it reproduces and the Python probe it drives.

WHAT IS WORTH TESTING HERE is the pieces whose exact SHAPE decides whether the gate is measuring anything at all:

  * `historical_capture`, which must reproduce bash's `$(curl ... || echo 000)`
    concatenation. A port that returned a boolean, or that dropped the fallback,
    would make assertion 3 report "the defect no longer reproduces" on a machine
    where it reproduces perfectly.
  * `probe_rc`, whose distinct exit status for "the module never imported" is the
    line standing between "the probe says dead" and "the probe was never called".
  * the fixtures: the defective one must read a closed port as ALIVE and the
    healthy one must not, or the planted-defect controls prove nothing.

`historical_capture` is compared against the real bash rather than against a remembered description of it.
"""

import pathlib
import socket

from rediacc_ci import paths
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
    on a refused connection AND curl exits non-zero, so the `|| echo 000` fallback appends a second one and the value is `000000`.
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

    A live port makes curl exit 0, so the fallback never runs and the value is the real status code with no concatenation.
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


def test_probe_rc_distinguishes_a_missing_function_from_a_dead_port(
    tmp_path: pathlib.Path,
) -> None:
    """Exit 3 and exit non-3 are two different findings, and both must be real."""
    healthy = _fixture(tmp_path / "healthy", ap.FIXTURE_HEALTHY)
    nofn = _fixture(tmp_path / "nofn", ap.FIXTURE_NO_FUNCTION)
    assert ap.probe_rc(nofn, 1) == ap.LOAD_FAILED_RC
    dead = ap.probe_rc(healthy, _free_port())
    assert dead != 0
    assert dead != ap.LOAD_FAILED_RC


def test_the_real_probe_reads_a_closed_port_as_dead_and_a_live_one_as_alive() -> None:
    """The live subject, through the same child-interpreter path the gate uses."""
    root = paths.repo_root()
    assert ap.probe_rc(root, _free_port()) not in (0, ap.LOAD_FAILED_RC)
    port = _free_port()
    server = ap.start_listener(port)
    try:
        assert ap.listener_ready(port) is True
        assert ap.probe_rc(root, port) == 0
    finally:
        server.kill()
        server.wait()


def test_the_defective_fixture_reads_a_closed_port_as_alive(tmp_path: pathlib.Path) -> None:
    """Without this the 2026-08-04 plant would be a no-op and the gate's red would be unearned."""
    defect = _fixture(tmp_path / "defect", ap.FIXTURE_DEFECTIVE)
    healthy = _fixture(tmp_path / "healthy", ap.FIXTURE_HEALTHY)
    closed = _free_port()
    assert ap.probe_rc(defect, closed) == 0
    assert ap.probe_rc(healthy, closed) not in (0, ap.LOAD_FAILED_RC)


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

    Exit 0 with zero controls is a failure, so the floor inside `Controls` is the thing being exercised here as much as the controls themselves.
    """
    assert ap.selftest() == 0


def _fixture(root: pathlib.Path, body: str) -> pathlib.Path:
    """A throwaway tree carrying a minimal `rediacc_ci.core.account`."""
    return ap.fixture_root(root, body)
