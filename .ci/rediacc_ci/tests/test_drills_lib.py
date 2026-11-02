"""`rediacc_ci.drills.lib` against its bash twin `scripts/drills/lib.sh`.

DIFFERENTIALS drive the real `lib.sh` and the port through the same scripted run (commands, assertions, summary) and compare stdout, stderr and exit status with the random work directory and the elapsed seconds masked. The summary verdict matrix extends the one `quality/drill_verdicts.py` pins for the bash. `test_delta_*` cases pin a Rule T difference, asserting the bash behaviour first as the control.

Nothing here starts a real gateway: the gateway cases use a fake `run.sh` and a stub `/health` server on loopback. The live runs of the drills are the acceptance and are recorded by the lead.
"""

from __future__ import annotations

import http.cookiejar
import http.server
import io
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.drills import lib, wire
from rediacc_ci.tests import differential as diff
from rediacc_ci.well_known import ACCOUNT_DEV_PORT

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
BASH = shutil.which("bash") or "/bin/bash"


def _mask(text: str) -> str:
    text = re.sub(r"/[^\s]*rediacc-drill-[A-Za-z0-9_-]+", "<WORK>", text)
    return re.sub(r"\(\d+s\)", "(Ns)", text)


TWIN = "scripts/drills/lib.sh"


def _run_bash(
    script: str,
    env: dict[str, str] | None = None,
    work: tuple[str, ...] = (),
    files: tuple[pathlib.Path, ...] = (),
) -> tuple[int, str, str]:
    """The retired twin's run of `script`, from `goldens/twins/scripts.drills.lib.jsonl` (PLAN-retire-bash-oracles B3).

    `work` lists the scratch roots the script names (they fold to tokens in the key and the answer); `files` are what the script writes, restored from the golden so the test reads them as it did live. Only a re-freeze runs bash.
    """

    def go() -> tuple[int, str, str]:
        full = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LC_ALL": "C",
        }
        full.update(env or {})
        proc = subprocess.run(
            [BASH, "-c", script],
            capture_output=True,
            text=True,
            env=full,
            cwd=str(ROOT),
            check=False,
            timeout=60,
        )
        return proc.returncode, proc.stdout, proc.stderr

    rc, out, err, _ = diff.twin_run(
        TWIN,
        ["script=%s" % script, "env=%r" % (sorted((env or {}).items()),)],
        go,
        files=tuple(str(f) for f in files),
        work=work,
    )
    return rc, out, err


PRELUDE = """
set -euo pipefail
source .ci/scripts/lib/common.sh
source scripts/drills/lib.sh
"""

SCRIPTED_BASH = (
    PRELUDE
    + """
drill_init t
drill_step "Phase 1: assertions"
drill_run echo '{"data":{"name":"x","ok":true,"n":3},"errors":[{"code":"E1"}]}'
assert_exit 0 "printf succeeds"
assert_stdout_json 'd.data.name' x "string field"
assert_stdout_json 'd.data.ok' true "boolean field"
assert_stdout_json 'd.data.n' 3 "number field"
assert_stdout_json 'd.errors[0].code' E1 "indexed field"
assert_stdout_json 'd.data.name' y "a failing json assertion"
assert_stdout_contains name "contains passes"
assert_stdout_contains zzz "contains fails"
assert_stdout_not_contains zzz "not-contains passes"
assert_stdout_not_contains name "not-contains fails"
drill_run sh -c 'echo oops >&2; exit 3'
assert_exit 0 "a failing exit assertion"
assert_exit 3 "exit 3 passes"
assert_stderr_contains oops "stderr contains passes"
assert_stderr_not_contains oops "stderr not-contains fails"
assert_stdout_empty "stdout empty passes"
drill_run echo data
assert_stdout_empty "stdout empty fails"
assert_equal a a "equal passes"
assert_equal a b "equal fails"
assert_not_equal a b "not-equal passes"
assert_not_equal a a "not-equal fails"
assert_file_exists /etc/hostname "file exists passes"
assert_file_exists /nonexistent/x "file exists fails"
assert_file_absent /nonexistent/x "file absent passes"
assert_file_absent /etc/hostname "file absent fails"
drill_note "a note"
rc=0
drill_summary || rc=$?
exit $rc
"""
)

PORT_SCRIPTED = """
import sys
sys.path.insert(0, %(ci)r)
from rediacc_ci.drills import lib
d = lib.Drill('t', selftest=%(selftest)s)
d.init()
%(body)s
rc = d.summary()
d.teardown()
sys.exit(rc)
"""

SCRIPTED_PORT_BODY = """
d.step("Phase 1: assertions")
d.run(["echo", '{"data":{"name":"x","ok":true,"n":3},"errors":[{"code":"E1"}]}'])
d.assert_exit(0, "printf succeeds")
d.assert_stdout_json("data.name", "x", "string field")
d.assert_stdout_json("data.ok", "true", "boolean field")
d.assert_stdout_json("data.n", "3", "number field")
d.assert_stdout_json("errors[0].code", "E1", "indexed field")
d.assert_stdout_json("data.name", "y", "a failing json assertion")
d.assert_stdout_contains("name", "contains passes")
d.assert_stdout_contains("zzz", "contains fails")
d.assert_stdout_not_contains("zzz", "not-contains passes")
d.assert_stdout_not_contains("name", "not-contains fails")
d.run(["sh", "-c", "echo oops >&2; exit 3"])
d.assert_exit(0, "a failing exit assertion")
d.assert_exit(3, "exit 3 passes")
d.assert_stderr_contains("oops", "stderr contains passes")
d.assert_stderr_not_contains("oops", "stderr not-contains fails")
d.assert_stdout_empty("stdout empty passes")
d.run(["echo", "data"])
d.assert_stdout_empty("stdout empty fails")
d.assert_equal("a", "a", "equal passes")
d.assert_equal("a", "b", "equal fails")
d.assert_not_equal("a", "b", "not-equal passes")
d.assert_not_equal("a", "a", "not-equal fails")
d.assert_file_exists("/etc/hostname", "file exists passes")
d.assert_file_exists("/nonexistent/x", "file exists fails")
d.assert_file_absent("/nonexistent/x", "file absent passes")
d.assert_file_absent("/etc/hostname", "file absent fails")
d.note("a note")
"""


def _run_port(body: str, selftest: bool = False) -> tuple[int, str, str]:
    code = PORT_SCRIPTED % {"ci": str(ROOT / ".ci"), "selftest": selftest, "body": body}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LC_ALL": "C",
        },
        cwd=str(ROOT),
        check=False,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_the_scripted_run_matches_bash() -> None:
    b = _run_bash(SCRIPTED_BASH)
    p = _run_port(SCRIPTED_PORT_BODY)
    assert b[0] == p[0] == 1
    assert _mask(b[1]) == _mask(p[1])
    assert _mask(b[2]) == _mask(p[2])
    assert "drill t FAILED" in p[1]
    assert "--- assertion 06 FAILED: a failing json assertion" in p[2]


@pytest.mark.parametrize(
    ("count", "failures", "selftest", "rc", "word", "forbidden"),
    [
        (0, 0, 0, 0, "SKIPPED", "PASSED"),
        (3, 0, 0, 0, "PASSED", ""),
        (3, 1, 0, 1, "FAILED", ""),
        (3, 0, 1, 1, "SELFTEST DID NOT FIRE", ""),
        (3, 2, 1, 1, "selftest fired as designed", ""),
    ],
)
def test_summary_verdicts_match_bash(
    count: int, failures: int, selftest: int, rc: int, word: str, forbidden: str
) -> None:
    bash = (
        PRELUDE + "DRILL_NAME=t; DRILL_STARTED_AT=$(date +%%s); DRILL_COUNT=%d; DRILL_FAILURES=%d; "
        "DRILL_SELFTEST=%d; DRILL_ROWS=()\n"
        "r=0; drill_summary || r=$?; exit $r\n" % (count, failures, selftest)
    )
    b = _run_bash(bash)
    drill = lib.Drill("t", selftest=bool(selftest))
    drill.started_at = int(time.time())
    drill.count, drill.failures = count, failures
    buffer = io.StringIO()
    drill.out = buffer
    assert drill.summary() == b[0] == rc
    assert _mask(b[1]) == _mask(buffer.getvalue())
    assert word in buffer.getvalue()
    if forbidden:
        assert forbidden not in buffer.getvalue()


def test_the_selftest_probe_matches_bash() -> None:
    bash = (
        PRELUDE
        + "DRILL_SELFTEST=1\ndrill_init t\ndrill_selftest_probe\nrc=0\ndrill_summary || rc=$?\nexit $rc\n"
    )
    b = _run_bash(bash)
    p = _run_port("d.selftest_probe()", selftest=True)
    assert b[0] == p[0] == 1
    assert _mask(b[1]) == _mask(p[1])
    assert _mask(b[2]) == _mask(p[2])


@pytest.mark.parametrize(
    ("raw", "path", "expression", "want"),
    [
        ('{"a":{"b":[{"c":1}]}}', "a.b[0].c", "d.a.b[0].c", "1"),
        ('{"a":true}', "a", "d.a", "true"),
        ('{"a":false}', "a", "d.a", "false"),
        ('{"a":null}', "a", "d.a", ""),
        ('{"a":1}', "b", "d.b", ""),
        ('{"a":{"b":1}}', "a.c.d", "d.a.c.d", ""),
        ('{"a":[]}', "a[3]", "d.a[3]", ""),
        ("", "a", "d.a", ""),
    ],
)
def test_json_get_matches_the_node_expressions_it_replaces(
    raw: str, path: str, expression: str, want: str
) -> None:
    assert lib.json_get(raw, path) == want
    got = _run_bash(
        PRELUDE + 'printf "%s" "$RAW" | drill_json "$EXPR"', {"RAW": raw, "EXPR": expression}
    )
    assert got[1] == want


def test_delta_unparseable_input_is_distinguished_from_an_absent_field() -> None:
    assert lib.json_get("not json", "a") == "<unparseable>"
    assert lib.json_get('{"b":1}', "a") == ""
    out = _run_bash(PRELUDE + "printf 'not json' | drill_json 'd.a' || echo \"rc=$?\"")
    # The control: the bash signals it with an exit status the assertion helper then rewrites into the same text.
    assert out[1].strip() == "rc=3"


def test_md5_matches_the_bash_fingerprint(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "f"
    f.write_text("hello")
    b = _run_bash(
        PRELUDE + 'drill_md5 "%s"; drill_md5 "%s/none"' % (f, tmp_path), work=(str(tmp_path),)
    )
    assert b[1] == "5d41402abc4b2a76b9719d911017c592\nabsent\n"
    assert lib.md5(f) + "\n" + lib.md5(tmp_path / "none") + "\n" == b[1]


# ---------------------------------------------------------------- gateway lifecycle


def _fake_root(tmp_path: pathlib.Path, run_sh: str) -> pathlib.Path:
    root = tmp_path / "root"
    (root / "scripts/drills").mkdir(parents=True)
    (root / ".ci/scripts/lib").mkdir(parents=True)
    if (ROOT / "scripts/drills/lib.sh").is_file():  # only a re-freeze from bash sources it
        shutil.copy2(ROOT / "scripts/drills/lib.sh", root / "scripts/drills/lib.sh")
    (root / ".ci/config").mkdir(parents=True)
    shutil.copy2(ROOT / ".ci/config/well-known.env", root / ".ci/config/well-known.env")
    # common.sh sources the generated projection (de630e818); without it the twin died on its first line.
    shutil.copy2(
        ROOT / ".ci/config/well-known.generated.sh", root / ".ci/config/well-known.generated.sh"
    )
    run = root / "run.sh"
    run.write_text(run_sh)
    run.chmod(run.stat().st_mode | stat.S_IEXEC)
    return root


def test_delta_the_gateway_does_not_inherit_the_sandbox_config_home(tmp_path: pathlib.Path) -> None:
    probe = tmp_path / "seen"
    run_sh = '#!/bin/bash\nprintf "%%s" "${XDG_CONFIG_HOME:-unset}" >"%s"\nexit 0\n' % probe
    root = _fake_root(tmp_path, run_sh)
    sandbox = str(tmp_path / "sandbox")
    bash = (
        "set -euo pipefail\n"
        'source "%s/.ci/scripts/lib/common.sh"\nsource "%s/scripts/drills/lib.sh"\n'
        'export XDG_CONFIG_HOME="%s"\n'
        "drill_init t\ndrill_gateway_wait_started() { return 0; }\n"
        "drill_gateway_restart >/dev/null\nwait\n" % (root, root, sandbox)
    )
    _run_bash(bash, {"XDG_CONFIG_HOME": "/real/config"}, work=(str(tmp_path),), files=(probe,))
    assert probe.read_text() == sandbox  # the control: the bash gateway saw the throwaway directory
    probe.unlink()

    code = (
        "import sys\nsys.path.insert(0, %r)\n"
        "from rediacc_ci.drills import lib\n"
        "d = lib.Drill('t'); d.init()\n"
        "d.extra_env['XDG_CONFIG_HOME'] = %r\n"
        "d.wait_gateway_started = lambda *_a: None\n"
        "d.restart_gateway(); d.gateway_proc.wait(); d.teardown()\n"
    ) % (str(ROOT / ".ci"), sandbox)
    subprocess.run(
        [sys.executable, "-c", code],
        env={
            "PATH": os.environ.get("PATH", ""),
            "XDG_CONFIG_HOME": "/real/config",
            "REDIACC_CI_ROOT": str(root),
        },
        capture_output=True,
        check=True,
        timeout=60,
    )
    assert probe.read_text() == "/real/config"


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args: object) -> None:
        return


def test_gateway_port_takes_the_last_line_as_rdc_sh_does(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIACC_CI_ROOT", str(tmp_path))
    (tmp_path / ".account-state").write_text("gateway_port=4833\nstarted=1\ngateway_port=4834\n")
    assert lib.Drill("t").gateway_port() == "4834"


def test_gateway_port_alive_and_wait_started_read_the_state_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        monkeypatch.setenv("REDIACC_CI_ROOT", str(tmp_path))
        drill = lib.Drill("t")
        assert drill.gateway_port() == ""
        assert not drill.gateway_alive()
        (tmp_path / ".account-state").write_text(
            "gateway_port=%d\nstarted=%d\n" % (port, int(time.time()) + 5)
        )
        assert drill.gateway_port() == str(port)
        assert drill.gateway_alive()
        monkeypatch.setattr(drill, "note", lambda *_a: None)
        drill.wait_gateway_started(int(time.time()))
        assert drill.gateway_port_cached == str(port)
        assert drill.server_url() == "http://127.0.0.1:%d" % port
    finally:
        server.shutdown()
        server.server_close()


def test_a_stale_state_file_with_a_dead_port_is_not_alive(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]
    (tmp_path / ".account-state").write_text("gateway_port=%d\nstarted=1\n" % dead)
    monkeypatch.setenv("REDIACC_CI_ROOT", str(tmp_path))
    assert not lib.Drill("t").gateway_alive()


def test_stop_gateway_kills_the_whole_process_group(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child_pid = tmp_path / "child.pid"
    run_sh = '#!/bin/bash\nsleep 15 &\necho $! >"%s"\nwait\n' % child_pid
    root = _fake_root(tmp_path, run_sh)
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    drill = lib.Drill("t")
    drill.init()
    monkeypatch.setattr(drill, "note", lambda *_a: None)
    monkeypatch.setattr(drill, "step", lambda *_a: None)
    monkeypatch.setattr(drill, "wait_gateway_started", lambda *_a: None)
    try:
        drill.restart_gateway()
        for _ in range(50):
            if child_pid.exists() and child_pid.read_text().strip():
                break
            time.sleep(0.1)
        pid = int(child_pid.read_text())
        os.kill(pid, 0)
        drill.stop_gateway()
        time.sleep(0.5)
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        drill.teardown()


class _FakePopen:
    """Records the launch and answers like a live child; `pid` is never a real process group."""

    launched: typing.ClassVar[list[dict[str, object]]] = []

    def __init__(self, argv: list[str], **kwargs: object) -> None:
        self.pid = 424242
        self.launched.append({"argv": argv, **kwargs})

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0

    def poll(self) -> int | None:
        return None


def _fake_gateway_drill(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[lib.Drill, list[tuple[int, int]]]:
    """A drill whose gateway start is a `_FakePopen` and whose `os.killpg` only records."""
    _FakePopen.launched = []
    killed: list[tuple[int, int]] = []
    root = _fake_root(tmp_path, "#!/bin/bash\nexit 0\n")
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setattr(lib.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    drill = lib.Drill("t")
    drill.init()
    monkeypatch.setattr(drill, "note", lambda *_a: None)
    monkeypatch.setattr(drill, "step", lambda *_a: None)
    monkeypatch.setattr(drill, "wait_gateway_started", lambda *_a: None)
    return drill, killed


def test_teardown_stops_a_gateway_this_run_started(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the detach case: without `detach_gateway` the teardown signals the process group."""
    drill, killed = _fake_gateway_drill(tmp_path, monkeypatch)
    drill.restart_gateway()
    drill.teardown()
    assert killed
    assert {pid for pid, _sig in killed} == {424242}
    assert drill.gateway_proc is None


def test_a_detached_gateway_survives_teardown(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drill, killed = _fake_gateway_drill(tmp_path, monkeypatch)
    drill.restart_gateway()
    assert drill.gateway_proc is not None
    drill.detach_gateway()
    assert drill.gateway_proc is None
    drill.teardown()
    assert killed == []


def test_restart_gateway_writes_to_log_path_and_the_log_outlives_the_work_dir(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fake_root(tmp_path, "#!/bin/bash\necho gateway-says-hello\nexit 0\n")
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    drill = lib.Drill("t")
    drill.init()
    monkeypatch.setattr(drill, "note", lambda *_a: None)
    monkeypatch.setattr(drill, "step", lambda *_a: None)
    monkeypatch.setattr(drill, "wait_gateway_started", lambda *_a: None)
    # The parent does not exist yet: restart_gateway creates it (review a0dabc98.3).
    log_path = tmp_path / "kept" / "gateway.log"
    default_log = drill.gateway_log
    try:
        drill.restart_gateway(log_path=log_path)
        assert drill.gateway_proc is not None
        drill.gateway_proc.wait(timeout=30)
        assert drill.active_gateway_log == log_path
        # The work-directory default is not overwritten by a one-call log_path (review a0dabc98.2).
        assert drill.gateway_log == default_log
        drill.detach_gateway()
    finally:
        drill.teardown()
    assert "gateway-says-hello" in log_path.read_text()
    assert default_log is not None
    assert not default_log.exists()


def test_a_bare_restart_after_a_log_path_restart_logs_to_the_work_dir_again(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review a0dabc98.2: `log_path` used to overwrite `gateway_log`, so the next bare restart wrote into the kept path."""
    drill, _killed = _fake_gateway_drill(tmp_path, monkeypatch)
    kept = tmp_path / "kept" / "gateway.log"
    try:
        default_log = drill.gateway_log
        drill.restart_gateway(log_path=kept)
        drill.restart_gateway()
        assert drill.active_gateway_log == default_log
        assert drill.gateway_log == default_log
    finally:
        drill.teardown()


def test_an_unwritable_log_path_fails_before_the_running_gateway_is_stopped(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review a0dabc98.3: the log is opened before `stop_gateway`, so a bad path leaves the old gateway up."""
    drill, _killed = _fake_gateway_drill(tmp_path, monkeypatch)
    stopped: list[bool] = []
    monkeypatch.setattr(drill, "stop_gateway", lambda: stopped.append(True))
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    try:
        with pytest.raises(FileExistsError):
            drill.restart_gateway(log_path=blocker / "gateway.log")
        assert stopped == []
    finally:
        drill.teardown()


def test_restart_gateway_without_log_path_keeps_the_work_dir_log(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    drill, _killed = _fake_gateway_drill(tmp_path, monkeypatch)
    try:
        default_log = drill.gateway_log
        drill.restart_gateway()
        assert drill.gateway_log == default_log
        assert default_log is not None
        assert default_log.parent == drill.work
    finally:
        drill.teardown()


def test_wait_started_names_a_gateway_that_exited(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fake_root(tmp_path, "#!/bin/bash\necho 'bws-env: no token'\nexit 3\n")
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    drill = lib.Drill("t")
    drill.init()
    monkeypatch.setattr(drill, "note", lambda *_a: None)
    monkeypatch.setattr(drill, "step", lambda *_a: None)
    try:
        with pytest.raises(lib.GatewayError):
            drill.restart_gateway()
    finally:
        drill.teardown()
    err = capsys.readouterr().err
    assert "The dev gateway exited during startup" in err
    assert "bws-env: no token" in err


# ---------------------------------------------------------------- offline shim


def _echo_server() -> tuple[socket.socket, int]:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()

    def serve() -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            conn.sendall(b"hello-%d" % srv.getsockname()[1])
            conn.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv, srv.getsockname()[1]


def test_the_shim_forwards_retargets_and_refuses_when_stopped() -> None:
    one, port_one = _echo_server()
    two, port_two = _echo_server()
    shim_port = lib.free_port()
    shim = lib.Shim(shim_port, port_one)
    shim.start()
    try:
        with socket.create_connection(("127.0.0.1", shim_port), timeout=5) as conn:
            assert conn.recv(64) == b"hello-%d" % port_one
        shim.target_port = port_two
        with socket.create_connection(("127.0.0.1", shim_port), timeout=5) as conn:
            assert conn.recv(64) == b"hello-%d" % port_two
    finally:
        shim.stop()
        one.close()
        two.close()
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", shim_port), timeout=2)


# ---------------------------------------------------------------- account helpers


class _Account(http.server.BaseHTTPRequestHandler):
    seen: typing.ClassVar[list[tuple[str, str, str]]] = []
    twofa: typing.ClassVar[bool] = False

    def _body(self) -> str:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length).decode() if length else ""

    def _reply(self, payload: dict, cookie: str | None = None) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(200)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        body = self._body()
        self.seen.append(("POST", self.path, body))
        if self.path.endswith("/auth/login"):
            if self.twofa:
                self._reply({"challengeToken": "chal"})
            else:
                self._reply({"user": {"id": "u1"}}, "session=abc; Path=/")
        elif self.path.endswith("/auth/2fa/verify"):
            self._reply({"user": {"id": "u1"}}, "session=abc; Path=/")
        elif self.path.endswith("/api-tokens"):
            ok = bool(self.headers.get("Cookie"))
            self._reply({"token": "rdt_xyz"} if ok else {"error": "no session"})
        else:
            self._reply({"ok": True})

    def do_GET(self) -> None:
        self.seen.append(("GET", self.path, self.headers.get("Cookie") or ""))
        if "totp-code" in self.path:
            self._reply({"code": "123456"})
        elif self.path.endswith("/portal/subscription"):
            self._reply({"id": "sub-1"})
        else:
            self._reply({})

    def do_PUT(self) -> None:
        self.seen.append(("PUT", self.path, self._body()))
        self._reply({"ok": True})

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture
def account(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> typing.Iterator[tuple[lib.Drill, http.cookiejar.CookieJar]]:
    _Account.seen = []
    _Account.twofa = False
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Account)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    (tmp_path / ".account-state").write_text(
        "gateway_port=%d\nstarted=1\n" % server.server_address[1]
    )
    monkeypatch.setenv("REDIACC_CI_ROOT", str(tmp_path))
    drill = lib.Drill("t")
    jar = http.cookiejar.MozillaCookieJar(str(tmp_path / "jar.txt"))
    yield drill, jar
    server.shutdown()
    server.server_close()


def test_the_headless_login_chain_without_two_factor(
    account: tuple[lib.Drill, http.cookiejar.CookieJar],
) -> None:
    drill, jar = account
    assert drill.account_session("a@b.c", "pw", jar)
    assert drill.twofa_used is False
    assert drill.account_subscription_id(jar) == "sub-1"
    assert drill.account_mint_token(jar, "sub-1", "tok", ["license:read"]) == "rdt_xyz"
    mint = next(body for _m, path, body in _Account.seen if path.endswith("/api-tokens"))
    assert json.loads(mint) == {
        "subscriptionId": "sub-1",
        "name": "tok",
        "scopes": ["license:read"],
    }


def test_the_headless_login_chain_completes_a_two_factor_challenge(
    account: tuple[lib.Drill, http.cookiejar.CookieJar],
) -> None:
    drill, jar = account
    _Account.twofa = True
    assert drill.account_session("a@b.c", "pw", jar)
    assert drill.twofa_used is True
    verify = next(body for _m, path, body in _Account.seen if path.endswith("/auth/2fa/verify"))
    assert json.loads(verify) == {"challengeToken": "chal", "code": "123456"}


def test_a_token_mint_without_a_session_raises(
    account: tuple[lib.Drill, http.cookiejar.CookieJar],
) -> None:
    drill, jar = account
    with pytest.raises(lib.GatewayError):
        drill.account_mint_token(jar, "sub-1", "tok", [])


def test_the_dev_only_routes_and_the_admin_chain(
    account: tuple[lib.Drill, http.cookiejar.CookieJar],
) -> None:
    drill, jar = account
    drill.account_ensure_login("a@b.c", "pw")
    drill.account_ensure_subscription("a@b.c", "PROFESSIONAL")
    drill.account_ensure_subscription("a@b.c", "PROFESSIONAL", 7)
    assert drill.account_admin_session("a@b.c", "pw", jar)
    drill.account_patch_subscription(jar, "sub-1", {"status": "suspended"})
    posted = [p.split("/v1")[1] for m, p, _b in _Account.seen if m == "POST"]
    assert posted[:3] == [
        "/test/ensure-login",
        "/test/ensure-subscription",
        "/test/ensure-subscription",
    ]
    assert "/test/promote-admin" in posted
    assert "/test/elevate" in posted
    caps = [json.loads(b) for _m, p, b in _Account.seen if p.endswith("/ensure-subscription")]
    assert caps[0] == {"email": "a@b.c", "planCode": "PROFESSIONAL"}
    assert caps[1]["maxActivations"] == 7
    assert (
        "PUT",
        "/account/api/v1/admin/subscriptions/sub-1",
        '{"status": "suspended"}',
    ) in _Account.seen


def test_common_args_match_the_bash_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DRILL_KEEP_WORK", raising=False)
    assert lib.parse_common_args(["--selftest", "--no-restart", "--keep-work"]) == (
        True,
        True,
        ["--no-restart"],
    )
    assert lib.parse_common_args([]) == (False, False, [])
    monkeypatch.setenv("DRILL_KEEP_WORK", "1")
    assert lib.parse_common_args([])[1] is True


def test_run_captures_the_streams_separately_and_setup_run_aborts_with_both(
    capsys: pytest.CaptureFixture[str],
) -> None:
    drill = lib.Drill("t")
    drill.init()
    try:
        drill.run(["sh", "-c", "echo out; echo err >&2; exit 4"])
        assert (drill.code, drill.stdout_text(), drill.stderr_text()) == (4, "out\n", "err\n")
        with pytest.raises(SystemExit) as exc:
            drill.setup_run(["sh", "-c", "echo out; echo err >&2; exit 4"])
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "setup command failed (exit 4)" in err
        drill.run(["/nonexistent/binary"])
        assert drill.code == 127
    finally:
        drill.teardown()


def test_delta_evidence_lines_are_always_newline_terminated() -> None:
    body = 'd.run(["printf", "no-newline"])\nd.assert_equal("a", "b", "fails with unterminated stdout")'
    bash = (
        PRELUDE
        + "drill_init t\ndrill_run printf no-newline\n"
        + 'assert_equal a b "fails with unterminated stdout"\nrc=0\ndrill_summary || rc=$?\nexit $rc\n'
    )
    b = _run_bash(bash)
    p = _run_port(body)
    assert (
        "| no-newline    stderr  |" in b[2]
    )  # the control: sed leaves the final newline off and glues the next label on
    assert "| no-newline\n    stderr  |" in p[2]


def test_a_drill_request_does_not_follow_a_redirect_to_ftp():
    """`wire.http_bytes` and the drill client opened through an opener of their own, so only the first URL was checked and a redirect to ftp was followed; both now open through `https.build_opener`. The case lives here, not beside the core https tests, so those tests never import the drills package."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/to-ftp":
                self.send_response(302)
                self.send_header("Location", "ftp://example.invalid/x")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = "http://127.0.0.1:%d" % server.server_address[1]
        with pytest.raises(OSError, match="may not open"):
            wire.http_bytes("GET", base + "/to-ftp")
        # CONTROL: a plain request through the same function still answers.
        assert wire.http_bytes("GET", base + "/") == (200, b"ok")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------- licence state purge

PURGE_A = "0f3c5a52-1b2d-4c3e-9f40-5a6b7c8d9e0f"
PURGE_B = "1f3c5a52-1b2d-4c3e-9f40-5a6b7c8d9e0f"


def _run_purge(tmp_path: pathlib.Path, guids: list[str], listing: str, renet_rc: int = 0):
    """Run the purge script under a fake `sudo` that answers `renet ...` with `listing` and records every `rm`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    rm_log = tmp_path / "rm.log"
    (bin_dir / "sudo").write_text(
        "#!/bin/bash\n"
        'if [ "$1" = renet ]; then printf "%%s" "$FAKE_LISTING"; exit %d; fi\n'
        'if [ "$1" = rm ]; then shift; echo "$*" >> "%s"; exit 0; fi\n'
        "exit 99\n" % (renet_rc, rm_log)
    )
    (bin_dir / "sudo").chmod(0o755)
    env = {"PATH": "%s:/usr/bin:/bin" % bin_dir, "FAKE_LISTING": listing}
    proc = subprocess.run(
        ["bash", "-s"],
        input=lib.purge_license_state_script(guids),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    removed = rm_log.read_text().splitlines() if rm_log.exists() else []
    return proc.returncode, proc.stdout, removed


def test_purge_removes_an_unlisted_guid_by_its_exact_paths(tmp_path: pathlib.Path) -> None:
    code, out, removed = _run_purge(tmp_path, [PURGE_A], '[{"repositoryGuid":"%s"}]' % PURGE_B)
    assert code == 0
    assert "PURGED %s" % PURGE_A in out
    expected = (
        f"-rf /var/lib/rediacc/license/repos/{PURGE_A} "
        f"/var/lib/rediacc/license/datastores/*/repos/{PURGE_A} "
        f"/var/lib/rediacc/license/failed/{PURGE_A}.json"
    )
    assert removed == [expected]


def test_purge_keeps_a_guid_renet_still_lists(tmp_path: pathlib.Path) -> None:
    code, out, removed = _run_purge(
        tmp_path, [PURGE_A, PURGE_B], '[{"repositoryGuid":"%s"}]' % PURGE_A
    )
    assert code == 1
    assert "KEPT %s" % PURGE_A in out
    assert "PURGED %s" % PURGE_B in out
    assert all(PURGE_A not in line for line in removed)


def test_purge_removes_nothing_when_renet_cannot_enumerate(tmp_path: pathlib.Path) -> None:
    code, out, removed = _run_purge(tmp_path, [PURGE_A], "", renet_rc=1)
    assert code == 1
    assert "nothing is proven dead" in out
    assert removed == []


@pytest.mark.parametrize("bad", ["", "../etc", "%s; rm -rf /" % PURGE_A, PURGE_A.upper(), "*"])
def test_purge_refuses_anything_but_a_lowercase_guid(bad: str) -> None:
    with pytest.raises(ValueError, match="not a repository guid"):
        lib.purge_license_state_script([PURGE_A, bad])


@pytest.mark.parametrize(
    ("state", "healthy", "expect_stop"),
    [(True, True, True), (True, False, False), (False, True, False)],
)
def test_restart_stops_a_live_worktree_stack_first(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    state: bool,
    healthy: bool,
    expect_stop: bool,
) -> None:
    """`./run.sh account dev` reuses a live stack (d681d61c2), so the drill's fresh restart first runs `./run.sh account stop` when this worktree records a healthy stack, and never otherwise (2026-10-24: the full vm:check stopped at account-gateway because the restart was handed the running 4800 stack)."""
    calls = tmp_path / "calls"
    run_sh = '#!/bin/bash\necho "$*" >>"%s"\nexit 0\n' % calls
    root = _fake_root(tmp_path, run_sh)
    if state:
        (root / ".account-state").write_text(f"gateway_port={ACCOUNT_DEV_PORT}\n")
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    drill = lib.Drill("t")
    drill.init()
    monkeypatch.setattr(drill, "gateway_alive", lambda: healthy and not calls.exists())
    drill.stop_worktree_stack()
    seen = calls.read_text().split("\n") if calls.exists() else []
    assert ("account stop" in seen) is expect_stop


@pytest.mark.parametrize("run_sh_body", ["exit 1", "exit 0", "sleep 5"])
def test_a_stop_that_leaves_the_stack_answering_is_an_error_not_a_reuse(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, run_sh_body: str
) -> None:
    """A failed, ineffective or timed-out `account stop` must not fall through to `account dev`, which would reuse the stale stack (review 93157dbc.1, .3, .4)."""
    root = _fake_root(tmp_path, "#!/bin/bash\n%s\n" % run_sh_body)
    (root / ".account-state").write_text(f"gateway_port={ACCOUNT_DEV_PORT}\n")
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.setattr(lib, "GATEWAY_POLL_SECONDS", 0)
    drill = lib.Drill("t")
    drill.init()
    monkeypatch.setattr(drill, "gateway_alive", lambda: True)
    if run_sh_body == "sleep 5":
        real = lib.subprocess.run
        monkeypatch.setattr(
            lib.subprocess, "run", lambda *a, **k: real(*a, **{**k, "timeout": 0.2})
        )
    with pytest.raises(lib.GatewayError, match="did not stop"):
        drill.stop_worktree_stack()
