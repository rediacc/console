"""`rediacc_ci.testrun.start_account` against its bash twin `.ci/scripts/test/start-account-for-e2e.sh`.

A FAKE `npx` launches `testrun_stub_server.py` (a stub of the account server's test surface) on a free port, so both sides really start a process, poll `/health`, resolve the listener pid from the socket, seed over HTTP and mint a token. Compared: the request sequence the stub saw, `$GITHUB_ENV`, `$GITHUB_OUTPUT`, the recorded pid file, stdout (token masked) and exit code. The REAL account server is exercised by the live run recorded in the porting report, not here.

INTENTIONAL DELTAS (Rule T), each a `test_delta_*` failing on the bash behaviour: an HTTP 500 from the seed routes fails there; a failed leg does not leave its server running; a stale server on the port is refused; `--port` with no value is a usage error.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import signal
import socket
import subprocess
import time

import pytest

from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import testrun_support as ts

# THE HOST'S PORT SPACE IS SHARED: free_port() releases the port before the server binds it, so two xdist workers can draw the same one (a 1-in-4 flake under load on 2026-10-01). Same group as test_core_ports.py and test_core_account.py.
XDIST_GROUP = "ports"

TWIN = ".ci/scripts/test/start-account-for-e2e.sh"
MODULE = "rediacc_ci.testrun.start_account"
STUB = pathlib.Path(__file__).with_name("testrun_stub_server.py")
NPX_BODY = f'#!/bin/bash\nexec python3 "{STUB}" "$PORT" "$STUB_LOG" "$STUB_MODE"\n'


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def reap(directory: pathlib.Path) -> None:
    pid_file = directory / "account-for-e2e.pid"
    if pid_file.exists():
        with contextlib.suppress(OSError, ValueError):
            os.kill(int(pid_file.read_text()), signal.SIGKILL)


def server_up(directory: pathlib.Path) -> bool:
    """Whether the server this side started is still running. The retired twin's answer is the frozen marker `bash-server-up`; the port's is read from its pid file."""
    marker = directory / "bash-server-up"
    if marker.exists():
        return marker.read_text() == "1"
    return alive(int((directory / "account-for-e2e.pid").read_text()))


def side(
    tmp_path: pathlib.Path, name: str, args: list[str], mode: str = "", port: int | None = None
) -> tuple[ts.Outcome, pathlib.Path, int]:
    directory = tmp_path / name
    directory.mkdir()
    port = port or free_port()
    env = {
        "RUNNER_TEMP": str(directory),
        "GITHUB_ENV": str(directory / "gh_env"),
        "GITHUB_OUTPUT": str(directory / "gh_output"),
        "STUB_LOG": str(directory / "stub.jsonl"),
        "STUB_MODE": mode,
        "ACCOUNT_API_PORT": str(port),
    }
    if name == "bash":
        return bash_side(tmp_path, directory, args, mode, env, port), directory, port
    outcome = ts.run_side(
        ts.py_cmd(MODULE, *args),
        directory,
        ("npx",),
        ts.py_env(env),
        bodies={"npx": NPX_BODY},
        timeout=60,
    )
    return outcome, directory, port


def bash_side(
    tmp_path: pathlib.Path,
    directory: pathlib.Path,
    args: list[str],
    mode: str,
    env: dict[str, str],
    port: int,
) -> ts.Outcome:
    """The retired twin's run, from `goldens/twins/test.start-account-for-e2e.jsonl`.

    The port is random per run, so every record carries `<PORT>` and a replay puts this run's port back. The files the twin and its stub wrote, and whether its server outlived it, are records of their own: the files are rewritten into the directory so the assertions read them as they did live.
    """
    cell: dict[str, ts.Outcome] = {}
    unwanted = str(port)

    def sub(text: str) -> str:
        return text.replace(unwanted, "<PORT>")

    def go() -> tuple[int, str, str]:
        out = ts.run_side(
            ts.bash_cmd(TWIN, *args),
            directory,
            ("npx",),
            env,
            bodies={"npx": NPX_BODY},
            timeout=60,
        )
        cell["o"] = out
        return out.code, sub(out.out), sub(out.err)

    def text_of(name: str):
        def read() -> str:
            path = directory / name
            return sub(path.read_text()) if path.exists() else diff.ABSENT

        return read

    def up() -> str:
        pid_file = directory / "account-for-e2e.pid"
        return "1" if pid_file.exists() and alive(int(pid_file.read_text())) else "0"

    names = ("gh_env", "gh_output", "stub.jsonl")
    extras = {n: text_of(n) for n in names}
    extras["calls"] = lambda: sub(json.dumps(cell["o"].calls))
    extras["up"] = up
    rc, out, err, got = diff.twin_run(
        TWIN,
        ["args=%r" % (args,), "mode=%s" % mode],
        go,
        extras=extras,
        work=(str(tmp_path),),
    )
    if diff.regolden_mode(TWIN) is None:
        for n in names:
            if got[n] != diff.ABSENT:
                (directory / n).write_text(got[n].replace("<PORT>", unwanted))
        (directory / "bash-server-up").write_text(got["up"])
        calls = json.loads(got["calls"].replace("<PORT>", unwanted))
    else:
        calls = cell["o"].calls
    return ts.Outcome(rc, out.replace("<PORT>", unwanted), err.replace("<PORT>", unwanted), calls)


def requests(directory: pathlib.Path) -> list[dict]:
    log = directory / "stub.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def trace(directory: pathlib.Path) -> list[tuple]:
    """The seed requests without health probes, as (method, path, body)."""
    return [
        (r["method"], r["path"], r["body"]) for r in requests(directory) if r["path"] != "/health"
    ]


@pytest.fixture
def cleanup(tmp_path: pathlib.Path):
    yield
    for name in ("bash", "py"):
        reap(tmp_path / name)


@pytest.mark.usefixtures("cleanup")
def test_success_matches_the_twin(tmp_path: pathlib.Path) -> None:
    old, od, op = side(
        tmp_path, "bash", ["--plan", "STARTER", "--email", "a@b.io", "--name", "tok"]
    )
    new, nd, np_ = side(tmp_path, "py", ["--plan", "STARTER", "--email", "a@b.io", "--name", "tok"])
    assert (old.code, new.code) == (0, 0), (old.err, new.err)
    assert trace(od) == trace(nd)
    seed = [r for r in requests(nd) if r["path"] != "/health"]
    assert seed[0]["test_mode"] == "true"
    assert seed[0]["key_lengths"] == {"ACCOUNT_SERVER_API_KEY": 64, "ACCOUNT_JWT_SECRET": 64}
    assert seed[0]["has_keys"]
    assert [t[1].rsplit("/", 1)[-1] for t in trace(nd)] == [
        "ensure-login",
        "ensure-subscription",
        "login",
        "subscription",
        "api-tokens",
    ]
    assert trace(nd)[-1][2]["scopes"] == ["license:read", "license:activate", "subscription:read"]
    # The token mint comes after the cookie login and the session cookie rides on it.
    assert [
        r["cookie"] for r in requests(nd) if r["path"].endswith(("/subscription", "/api-tokens"))
    ][-2:] == [True, True]
    for directory, port in ((od, op), (nd, np_)):
        env = (directory / "gh_env").read_text().splitlines()
        assert env == [
            f"REDIACC_ACCOUNT_SERVER=http://127.0.0.1:{port}",
            "E2E_ACCOUNT_API_TOKEN=rdt_stub_token_0123456789",
        ]
        assert (directory / "gh_output").read_text() == f"server-url=http://127.0.0.1:{port}\n"
        assert server_up(directory)

    def norm(out: ts.Outcome, directory: pathlib.Path, port: int) -> str:
        return ts.mask(out.out, directory).replace(str(port), "<PORT>")

    assert norm(old, od, op) == norm(new, nd, np_)
    assert "::add-mask::rdt_stub_token_0123456789" in new.out


@pytest.mark.parametrize(
    ("mode", "needle"),
    [
        ("no-subscription", "no subscription id"),
        ("no-token", "could not mint an API token"),
        ("login-fails", "could not open a session"),
    ],
)
@pytest.mark.usefixtures("cleanup")
def test_failures_match_the_twin(tmp_path: pathlib.Path, mode: str, needle: str) -> None:
    old, od, _ = side(tmp_path, "bash", [], mode)
    new, nd, _ = side(tmp_path, "py", [], mode)
    assert (old.code, new.code) == (1, 1)
    assert needle in old.err
    assert needle in new.err
    assert trace(od) == trace(nd)
    assert not (nd / "gh_env").exists()
    assert not (od / "gh_env").exists()


def test_unknown_option_matches_the_twin(tmp_path: pathlib.Path) -> None:
    old, _, _ = side(tmp_path, "bash", ["--bogus"])
    new, _, _ = side(tmp_path, "py", ["--bogus"])
    assert (old.code, new.code) == (2, 2)
    assert "Unknown option: --bogus" in old.err
    assert "Unknown option: --bogus" in new.err


# ---- intentional deltas ----------------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("cleanup")
def test_delta_http_500_from_a_seed_route_fails_there(tmp_path: pathlib.Path) -> None:
    old, od, _ = side(tmp_path, "bash", [], "ensure-login-500")
    new, nd, _ = side(tmp_path, "py", [], "ensure-login-500")
    assert old.code == 0, "bash read a 500 as success and carried on to mint a token"
    assert len(trace(od)) == 5
    assert new.code == 1
    assert "/test/ensure-login failed with HTTP 500" in new.err
    assert len(trace(nd)) == 1


def test_delta_a_failed_leg_does_not_leave_its_server_running(tmp_path: pathlib.Path) -> None:
    old, od, _ = side(tmp_path, "bash", [], "no-token")
    new, nd, _ = side(tmp_path, "py", [], "no-token")
    try:
        assert old.code == new.code == 1
        assert server_up(od), "bash left the server holding the port"
        assert not server_up(nd)
    finally:
        reap(od)


def test_delta_a_server_already_on_the_port_is_refused(tmp_path: pathlib.Path) -> None:
    port = free_port()
    stale = subprocess.Popen(
        [
            "python3",
            "-c",
            "import http.server,sys\nclass H(http.server.BaseHTTPRequestHandler):\n  def do_GET(s):\n    s.send_response(200);s.end_headers();s.wfile.write(b'ok')\nhttp.server.HTTPServer(('127.0.0.1',int(sys.argv[1])),H).serve_forever()",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1)
        new, nd, _ = side(tmp_path, "py", [], port=port)
        assert new.code == 1
        assert "already answers /health" in new.err
        assert not new.calls
        assert not requests(nd)
    finally:
        stale.kill()
        stale.wait()


def test_delta_port_without_a_value_is_a_usage_error(tmp_path: pathlib.Path) -> None:
    old, _, _ = side(tmp_path, "bash", ["--port"])
    new, _, _ = side(tmp_path, "py", ["--port"])
    assert old.code == 1
    assert "--port needs a value" in old.err
    assert new.code == 2
    assert "--port needs a value" in new.err
