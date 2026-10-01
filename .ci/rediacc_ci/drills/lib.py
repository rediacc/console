"""Port of `scripts/drills/lib.sh` (847 lines): the shared harness for the campaign drills.

A drill is a script with explicit setup, numbered assertions, teardown, and a non-zero exit on any failure. This module holds everything the drills share: the work directory and its teardown, command capture, the assertions, the summary table and its verdicts, the dev-gateway lifecycle, the offline shim and the account-server helpers.

    from rediacc_ci.drills import lib
    drill = lib.Drill("universe", selftest=False)

WHAT THE ASSERTIONS CAPTURE. Every command under test runs through `Drill.run`, which sends stdout and stderr to SEPARATE files and records the exit code. The separation is the point: this campaign's surfaces put the machine-readable answer on stdout and the human warning on stderr, so a merged capture cannot tell a correct implementation from one that writes the warning onto stdout and corrupts every `-o json` consumer.

THE TWO DEV-GATEWAY FOOTGUNS ARE BAKED IN. `npx tsx src/entry/dev-gateway.ts` does not hot-reload, so the drills restart the gateway themselves rather than trust one they find running (`restart_gateway`). A restart rotates every dev password and may land on a different port, so nothing here remembers a port or a credential between calls: `gateway_port()` re-reads `.account-state` on every call and the drills mint their own logins through the dev-only `/test` routes.

PROVE THE INSTRUMENT. Every drill accepts `--selftest`, which plants exactly one assertion that cannot pass. A selftest run MUST exit non-zero; if no assertion failed, `summary` fails the run for that reason specifically.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_drills_lib.py` that fails on the bash behaviour).

  1. THE GATEWAY DOES NOT INHERIT THE SANDBOX. `universe.sh` exported its throwaway `XDG_CONFIG_HOME` before restarting the gateway, and the gateway's secret loader (`bws_env`) looks for the Bitwarden bootstrap token under `${XDG_CONFIG_HOME}/rediacc/`: it found none and the drill died with "The dev gateway exited during startup" on every run since secrets moved to Bitwarden (run live 2026-10-01; the bash passes only when `BWS_ACCESS_TOKEN` happens to be exported). The sandbox applies to the `rdc` commands under test (`Drill.cli_env`); the gateway is started with the environment the drill itself was started with (`Drill.gateway_env`).
  2. JSON EXPRESSIONS ARE PATHS, NOT EVALUATED CODE. `drill_json` ran the caller's expression through node's `new Function`, and every failure inside it (a parse error, a typo) collapsed to an empty string indistinguishable from an absent field. `json_get` takes a path (`data.name`, `errors[0].code`) and distinguishes "absent" (empty string, the bash's answer) from "unparseable input" (`<unparseable>`), which an assertion reports as such.
  3. THE TEARDOWN REPORTS WHAT IT COULD NOT STOP. The bash swallowed every failure (`|| true`) so a surviving gateway left no trace; each step now records its failure on stderr and the teardown still completes.
  4. GATEWAY IS NEVER KILLED. `drill_gateway_stop` swept `lsof -ti:<port>` .. `<port>+2` with `kill -9` whenever `DRILL_GATEWAY_PORT` was set, and the `--no-restart` path sets it for a gateway the operator started: every `--no-restart` drill ended by SIGKILLing the gateway it had been told to reuse (or whatever else listened on those ports). The sweep now runs only after this run stopped a process group of its own.
  5. STAYS OUT OF THE FAILURE REPORT. `drill_run env REDIACC_TOKEN=<token> REDIACC_CONFIG_PASSWORD=<password> rdc ...` recorded the whole `env` line as the command, and every failed assertion printed it ("command : ...") to stderr, which in CI is a log: the account token and the store password landed there. `run_with` passes the variables through the child's environment and records only the command.
  6. `urllib`, NOT `curl` AND `node`. The API helpers, the port probe (`free_port`) and the offline shim (`Shim`, an in-process threaded TCP forwarder) no longer need curl, node or a generated `proxy.js`.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

from rediacc_ci import log, paths

if TYPE_CHECKING:
    import http.cookiejar

GATEWAY_START_TIMEOUT = 300
GATEWAY_POLL_SECONDS = 2


def _colours(stream) -> tuple[str, str, str, str]:
    """GREEN, RED, YELLOW, NC: set only when the stream common.sh tests (stderr) is a terminal and NO_COLOR is unset."""
    try:
        tty = stream.isatty()
    except (AttributeError, ValueError):
        tty = False
    if tty and not os.environ.get("NO_COLOR"):
        return "\033[0;32m", "\033[0;31m", "\033[1;33m", "\033[0m"
    return "", "", "", ""


def json_get(raw: str, path: str) -> str:
    """The field at `path` in the JSON text `raw`, stringified the way node's `String(v)` did.

    `""` for an absent field (and for null), `"<unparseable>"` when `raw` is not JSON. Paths are `a.b`, `a[0].b` and `a.length`-free; booleans print `true`/`false`.
    """
    try:
        value: object = json.loads(raw or "{}")
    except ValueError:
        return "<unparseable>"
    for key, index in re.findall(r"([A-Za-z0-9_$-]+)|\[(\d+)\]", path):
        if key:
            if not isinstance(value, dict) or key not in value:
                return ""
            value = value[key]
        else:
            if not isinstance(value, list) or int(index) >= len(value):
                return ""
            value = value[int(index)]
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def md5(path: str | os.PathLike) -> str:
    """A content fingerprint, or the sentinel `absent`. A distinct sentinel, not an empty string: isolation assertions compare two fingerprints, and a vanished file must not read as unchanged."""
    p = pathlib.Path(path)
    if not p.is_file():
        return "absent"
    return hashlib.md5(p.read_bytes(), usedforsecurity=False).hexdigest()


def free_port() -> int:
    """A TCP port that is free right now (bind to 0, read, close)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Shim:
    """An in-process TCP forwarder in front of the gateway.

    A config records the server URL it is bound to, and the dev gateway does not guarantee the same port twice, so the offline drills point their configs at this shim: going offline is stopping the shim, and a gateway that comes back elsewhere needs only `retarget`. The target port is re-read per connection.
    """

    def __init__(self, listen_port: int, target_port: int) -> None:
        self.listen_port = listen_port
        self.target_port = target_port
        self._server: socketserver.ThreadingTCPServer | None = None

    def start(self) -> None:
        shim = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                try:
                    upstream = socket.create_connection(("127.0.0.1", shim.target_port), timeout=5)
                except OSError:
                    return
                _pipe_pair(self.request, upstream)

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", self.listen_port), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def _pipe_pair(a: socket.socket, b: socket.socket) -> None:
    def pump(src: socket.socket, dst: socket.socket) -> None:
        try:
            while data := src.recv(65536):
                dst.sendall(data)
        except OSError:
            pass
        finally:
            with contextlib.suppress(OSError):
                dst.shutdown(socket.SHUT_WR)

    t = threading.Thread(target=pump, args=(b, a), daemon=True)
    t.start()
    pump(a, b)
    t.join(timeout=5)
    a.close()
    b.close()


class Drill:
    """One drill run: work directory, captured command, assertion ledger, gateway and shim."""

    def __init__(
        self,
        name: str,
        selftest: bool = False,
        keep_work: bool | None = None,
        stdout=None,
    ) -> None:
        self.name = name
        self._original_env: dict[str, str] = dict(os.environ)
        self.selftest = selftest
        self.keep_work = (
            bool(os.environ.get("DRILL_KEEP_WORK") == "1") if keep_work is None else keep_work
        )
        self.host = os.environ.get("DRILL_HOST") or "127.0.0.1"
        self.out = stdout if stdout is not None else sys.stdout
        self.root = paths.repo_root()
        self.work: pathlib.Path | None = None
        self.stdout_file: pathlib.Path | None = None
        self.stderr_file: pathlib.Path | None = None
        self.gateway_log: pathlib.Path | None = None
        self.gateway_proc: subprocess.Popen | None = None
        self.gateway_port_cached = ""
        self.shim: Shim | None = None
        self.shim_port = 0
        self.code = 0
        self.count = 0
        self.failures = 0
        self.rows: list[tuple[str, str, str]] = []
        self.last_cmd = ""
        self.started_at = 0
        self.twofa_used = False
        self.extra_env: dict[str, str] = {}
        self.green, self.red, self.yellow, self.nc = _colours(sys.stderr)

    # ------------------------------------------------------------------ environment

    def cli_env(self) -> dict[str, str]:
        """The environment the commands under test run in: this process's, plus the drill's sandbox variables."""
        env = dict(os.environ)
        env.update(self.extra_env)
        return env

    def gateway_env(self) -> dict[str, str]:
        """The environment the dev gateway starts in: the one the drill itself was started with (Rule T 1)."""
        return dict(self._original_env)

    # ------------------------------------------------------------------ lifecycle

    def init(self) -> None:
        """Create the per-run work directory and print the header."""
        self.started_at = int(time.time())
        self.work = pathlib.Path(tempfile.mkdtemp(prefix="rediacc-drill-%s-" % self.name))
        self.stdout_file = self.work / "stdout.txt"
        self.stderr_file = self.work / "stderr.txt"
        self.gateway_log = self.work / "gateway.log"
        self.stdout_file.write_text("")
        self.stderr_file.write_text("")
        self._print("\n=== drill %s ===" % self.name)
        self._print("work dir : %s" % self.work)
        self._print(
            "selftest : %s\n" % ("ON (one planted failure expected)" if self.selftest else "off")
        )

    def teardown(self) -> None:
        """Best-effort cleanup, every step reported if it fails: shim, gateway, work directory."""
        for label, action in (("shim", self.stop_shim), ("gateway", self.stop_gateway)):
            try:
                action()
            except Exception as exc:  # noqa: BLE001 -- teardown must finish
                log.warn("teardown: stopping the %s failed: %s" % (label, exc))
        work = self.work
        if work and work.is_dir() and not self.keep_work:
            shutil.rmtree(work, ignore_errors=True)
        elif work:
            self._print("work dir kept: %s" % work)

    def _print(self, text: str = "") -> None:
        print(text, file=self.out)
        self.out.flush()

    def step(self, text: str) -> None:
        """A phase header, on stdout with the assertion stream."""
        self._print("\n-- %s" % text)

    def note(self, text: str) -> None:
        """An aside that is neither a phase nor an assertion."""
        self._print("   %s" % text)

    # ------------------------------------------------------------------ command execution

    def run(self, argv: list[str], env: dict[str, str] | None = None) -> None:
        """Run a command with stdout and stderr captured to SEPARATE files; the exit code lands in `self.code`. Never aborts the drill."""
        if self.stdout_file is None or self.stderr_file is None:
            raise RuntimeError("Drill.init() must run before Drill.run()")
        self.last_cmd = " ".join(argv)
        with self.stdout_file.open("wb") as out, self.stderr_file.open("wb") as err:
            try:
                self.code = subprocess.run(
                    argv, stdout=out, stderr=err, env=env or self.cli_env(), check=False
                ).returncode
            except OSError as exc:
                err.write(("%s: %s\n" % (argv[0], exc.strerror or exc)).encode())
                self.code = 127

    def run_with(self, argv: list[str], **env: str) -> None:
        """`run` with per-command environment overrides (the bash `env K=V cmd ...`). The overrides are NOT part of `last_cmd`, so a token or password passed this way never reaches a failure report (Rule T: the bash printed the whole `env ...` line, secrets included)."""
        merged = self.cli_env()
        merged.update(env)
        self.run(argv, env=merged)

    def setup_run(self, argv: list[str], env: dict[str, str] | None = None) -> None:
        """A SETUP command that must succeed: on failure both captured streams and the exit code are printed and the drill aborts with exit 2."""
        self.run(argv, env)
        if self.code != 0:
            log.error("setup command failed (exit %d): %s" % (self.code, self.last_cmd))
            log.error("--- captured stdout ---")
            sys.stderr.write(self.stdout_text())
            log.error("--- captured stderr ---")
            sys.stderr.write(self.stderr_text())
            raise SystemExit(2)

    def stdout_text(self) -> str:
        return self.stdout_file.read_text(errors="replace") if self.stdout_file else ""

    def stderr_text(self) -> str:
        return self.stderr_file.read_text(errors="replace") if self.stderr_file else ""

    # ------------------------------------------------------------------ assertions

    def _record(self, status: str, desc: str) -> None:
        self.count += 1
        self.rows.append(("%02d" % self.count, status, desc))
        if status == "PASS":
            self._print("  %02d  %sPASS%s  %s" % (self.count, self.green, self.nc, desc))
        else:
            self.failures += 1
            self._print("  %02d  %sFAIL%s  %s" % (self.count, self.red, self.nc, desc))

    def _fail(self, desc: str, *details: str) -> None:
        """Record a failure and dump the evidence to stderr, so a piped stdout stays a readable table."""
        self._record("FAIL", desc)
        err = sys.stderr
        err.write("\n--- assertion %02d FAILED: %s\n" % (self.count, desc))
        err.write("    command : %s\n" % (self.last_cmd or "<none>"))
        err.write("    exit    : %s\n" % self.code)
        for line in details:
            err.write("    %s\n" % line)
        for label, text in (("stdout", self.stdout_text()), ("stderr", self.stderr_text())):
            if text:
                err.write("    %s  |\n" % label)
                for line in text.splitlines()[-20:]:
                    err.write("    | %s\n" % line)
            else:
                err.write("    %s  | <empty>\n" % label)
        err.flush()

    def assert_exit(self, expected: int, desc: str) -> None:
        if str(self.code) == str(expected):
            self._record("PASS", desc)
        else:
            self._fail(desc, "expected exit %s, got %s" % (expected, self.code))

    def assert_stdout_contains(self, needle: str, desc: str) -> None:
        if needle in self.stdout_text():
            self._record("PASS", desc)
        else:
            self._fail(desc, "stdout does not contain: %s" % needle)

    def assert_stdout_not_contains(self, needle: str, desc: str) -> None:
        if needle in self.stdout_text():
            self._fail(desc, "stdout unexpectedly contains: %s" % needle)
        else:
            self._record("PASS", desc)

    def assert_stderr_contains(self, needle: str, desc: str) -> None:
        if needle in self.stderr_text():
            self._record("PASS", desc)
        else:
            self._fail(desc, "stderr does not contain: %s" % needle)

    def assert_stderr_not_contains(self, needle: str, desc: str) -> None:
        if needle in self.stderr_text():
            self._fail(desc, "stderr unexpectedly contains: %s" % needle)
        else:
            self._record("PASS", desc)

    def assert_stdout_empty(self, desc: str) -> None:
        if self.stdout_text():
            self._fail(desc, "stdout is not empty")
        else:
            self._record("PASS", desc)

    def assert_stdout_json(self, path: str, expected: str, desc: str) -> None:
        actual = json_get(self.stdout_text(), path)
        if actual == expected:
            self._record("PASS", desc)
        else:
            self._fail(desc, 'd.%s: expected "%s", got "%s"' % (path, expected, actual))

    def assert_equal(self, expected: str, actual: str, desc: str) -> None:
        if expected == actual:
            self._record("PASS", desc)
        else:
            self._fail(desc, 'expected "%s", got "%s"' % (expected, actual))

    def assert_not_equal(self, unexpected: str, actual: str, desc: str) -> None:
        if unexpected != actual:
            self._record("PASS", desc)
        else:
            self._fail(desc, 'expected a value different from "%s"' % unexpected)

    def assert_file_exists(self, path: str | os.PathLike, desc: str) -> None:
        if pathlib.Path(path).is_file():
            self._record("PASS", desc)
        else:
            self._fail(desc, "file missing: %s" % path)

    def assert_file_absent(self, path: str | os.PathLike, desc: str) -> None:
        if pathlib.Path(path).exists():
            self._fail(desc, "file unexpectedly present: %s" % path)
        else:
            self._record("PASS", desc)

    def selftest_probe(self) -> None:
        """No-op unless `--selftest`; then plants exactly one assertion that cannot pass."""
        if not self.selftest:
            return
        self.step("selftest: planting one assertion that cannot pass")
        self.last_cmd = "<selftest control: no command>"
        self.assert_equal(
            "this-value-is-planted",
            "and-this-one-differs",
            "selftest control (planted failure — this drill MUST exit non-zero)",
        )

    # ------------------------------------------------------------------ summary

    def summary(self) -> int:
        """Print the table and return the exit status: non-zero on any failure, and under selftest ALSO when nothing failed."""
        elapsed = int(time.time()) - self.started_at
        passed = self.count - self.failures
        self._print("\n=== drill %s summary ===" % self.name)
        self._print("  %-4s %-6s %s" % ("##", "RESULT", "ASSERTION"))
        for number, status, desc in self.rows:
            self._print("  %-4s %-6s %s" % (number, status, desc))
        self._print("  %s" % ("-" * 61))
        self._print(
            "  %d assertions: %d passed, %d failed  (%ds)"
            % (self.count, passed, self.failures, elapsed)
        )
        if self.selftest:
            if self.failures == 0:
                self._print(
                    "  %sSELFTEST DID NOT FIRE%s: a planted failure went unnoticed, so this"
                    % (self.red, self.nc)
                )
                self._print(
                    "  harness is not measuring anything. Fix the accounting before trusting a green run."
                )
                return 1
            self._print(
                "  %sselftest fired as designed%s (exit is non-zero on purpose)"
                % (self.green, self.nc)
            )
            return 1
        if self.failures > 0:
            self._print("  %sdrill %s FAILED%s" % (self.red, self.name, self.nc))
            return 1
        if self.count == 0:
            # A run that asserted nothing is not a pass: a declared skip exits 0, but must not print the word a dashboard greps for.
            self._print(
                "  %sdrill %s SKIPPED%s (0 assertions ran — nothing was proven)"
                % (self.yellow, self.name, self.nc)
            )
            return 0
        self._print("  %sdrill %s PASSED%s" % (self.green, self.name, self.nc))
        return 0

    # ------------------------------------------------------------------ dev gateway

    def gateway_port(self) -> str:
        """The CURRENT port, re-read from `.account-state` every call; empty when there is none."""
        state = self.root / ".account-state"
        try:
            lines = state.read_text(errors="replace").splitlines()
        except OSError:
            return ""
        for line in lines:
            if line.startswith("gateway_port="):
                return line.split("=", 1)[1]
        return ""

    def _health(self, port: str | int, timeout: float = 2.0) -> bool:
        try:
            with urllib.request.urlopen(  # noqa: S310 -- constant http loopback URL
                "http://127.0.0.1:%s/health" % port, timeout=timeout
            ) as r:
                return 200 <= r.status < 300
        except (OSError, urllib.error.URLError, ValueError):
            return False

    def gateway_alive(self) -> bool:
        port = self.gateway_port()
        return bool(port) and self._health(port)

    def restart_gateway(self) -> None:
        """Stop what this run started and start a fresh `./run.sh account dev`, waiting until it is healthy."""
        self.step(
            "Restarting the dev gateway (tsx does not hot-reload — a long-running gateway serves stale server code)"
        )
        self.stop_gateway()
        started = int(time.time())
        assert self.gateway_log is not None  # noqa: S101
        # Its own process group (setsid): the tsx child must not survive a kill of the run.sh wrapper and keep the port bound.
        with self.gateway_log.open("wb") as log_file:
            self.gateway_proc = subprocess.Popen(
                [str(self.root / "run.sh"), "account", "dev"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=self.gateway_env(),
                start_new_session=True,
            )
        self.note("gateway log: %s" % self.gateway_log)
        self.wait_gateway_started(started)

    def wait_gateway_started(self, since: int) -> None:
        """Wait for a state file NEWER than `since` (account_dev writes `started=` last), then for /health."""
        waited = 0
        while waited < GATEWAY_START_TIMEOUT:
            state = self.root / ".account-state"
            started = ""
            if state.is_file():
                for line in state.read_text(errors="replace").splitlines():
                    if line.startswith("started="):
                        started = line.split("=", 1)[1]
            if started.isdigit() and int(started) >= since and self.gateway_alive():
                self.gateway_port_cached = self.gateway_port()
                self.note(
                    "gateway healthy on port %s after %ds" % (self.gateway_port_cached, waited)
                )
                return
            if self.gateway_proc is not None and self.gateway_proc.poll() is not None:
                log.error(
                    "The dev gateway exited during startup. Last 40 lines of %s:" % self.gateway_log
                )
                self._tail_gateway_log()
                raise GatewayError("the dev gateway exited during startup")
            time.sleep(GATEWAY_POLL_SECONDS)
            waited += GATEWAY_POLL_SECONDS
        log.error(
            "Dev gateway did not become healthy within %ds. Last 40 lines of %s:"
            % (waited, self.gateway_log)
        )
        self._tail_gateway_log()
        raise GatewayError("the dev gateway did not become healthy")

    def _tail_gateway_log(self) -> None:
        if self.gateway_log and self.gateway_log.is_file():
            for line in self.gateway_log.read_text(errors="replace").splitlines()[-40:]:
                sys.stderr.write(line + "\n")

    def stop_gateway(self) -> None:
        """Stop the gateway this run started, and only that one: its process group, then a port sweep for survivors of THAT group.

        A gateway this run merely reused (`--no-restart`) is never touched: the sweep runs only after this run stopped a process group of its own.
        """
        port = self.gateway_port_cached
        proc = self.gateway_proc
        if proc is None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=15)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        self.gateway_proc = None
        if port.isdigit() and shutil.which("lsof"):
            for offset in (0, 1, 2):
                listed = subprocess.run(
                    ["lsof", "-ti:%d" % (int(port) + offset)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                for pid in listed.stdout.split():
                    with contextlib.suppress(ProcessLookupError, PermissionError, ValueError):
                        os.kill(int(pid), signal.SIGKILL)

    def wait_gateway_down(self) -> None:
        """Wait for the recorded port to stop answering, so the offline leg cannot race a draining socket."""
        for _ in range(30):
            if not self.gateway_alive():
                return
            time.sleep(1)
        log.error("Gateway port %s still answering after 30s" % (self.gateway_port_cached or "?"))
        raise GatewayError("the gateway kept answering")

    # ------------------------------------------------------------------ offline shim

    def shim_url(self) -> str:
        return "http://127.0.0.1:%d" % self.shim_port

    def retarget_shim(self) -> None:
        if self.shim is not None:
            self.shim.target_port = int(self.gateway_port())

    def start_shim(self) -> None:
        """Start (or restart) the shim on its stable port."""
        if not self.shim_port:
            self.shim_port = free_port()
        self.stop_shim()
        self.shim = Shim(self.shim_port, int(self.gateway_port()))
        self.shim.start()
        for _ in range(20):
            if self._health(self.shim_port):
                self.note(
                    "offline shim listening on %s -> gateway :%s"
                    % (self.shim_url(), self.gateway_port())
                )
                return
            time.sleep(1)
        log.error("Offline shim did not come up on port %d" % self.shim_port)
        raise GatewayError("the offline shim did not come up")

    def stop_shim(self) -> None:
        """Take the shim down; connections are then refused, the shape of "server unreachable"."""
        if self.shim is not None:
            self.shim.stop()
            self.shim = None

    # ------------------------------------------------------------------ account server

    def api_base(self) -> str:
        return "http://%s:%s/account/api/v1" % (self.host, self.gateway_port())

    def server_url(self) -> str:
        return "http://%s:%s" % (self.host, self.gateway_port())

    def api_post(
        self, path: str, body: dict | str, jar: http.cookiejar.CookieJar | None = None
    ) -> str:
        """POST JSON and return the response body. A transport failure raises; an HTTP error status does NOT, because the account server puts its reason in the body."""
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
        return self._request("POST", self.api_base() + path, data, jar)

    def _request(
        self,
        method: str,
        url: str,
        data: bytes | None,
        jar: http.cookiejar.CookieJar | None,
    ) -> str:
        handlers: list[urllib.request.BaseHandler] = []
        if jar is not None:
            handlers.append(urllib.request.HTTPCookieProcessor(jar))
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 -- the drill's own http gateway URL
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with opener.open(request, timeout=30) as response:
                return response.read().decode(errors="replace")
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.read().decode(errors="replace")

    def account_ensure_login(self, email: str, password: str) -> None:
        """Mint (or repoint) a dev login with a password the drill chooses; the banner's passwords rotate on every restart."""
        self.api_post("/test/ensure-login", {"email": email, "password": password})

    def account_ensure_subscription(
        self, email: str, plan: str, max_activations: int | None = None
    ) -> None:
        """Seed a subscription. A SEEDING lever only: it deletes the customer's existing subscriptions, so calling it mid-drill orphans every licence issued under the old one."""
        body: dict = {"email": email, "planCode": plan}
        if max_activations is not None:
            body["maxActivations"] = max_activations
        self.api_post("/test/ensure-subscription", body)

    def account_session(self, email: str, password: str, jar: http.cookiejar.CookieJar) -> bool:
        """The headless auth chain: login, and when TOTP is enabled complete the challenge from the dev-only `/test/totp-code`. Sets `twofa_used`."""
        self.twofa_used = False
        body = self.api_post("/auth/login", {"email": email, "password": password}, jar)
        challenge = json_get(body, "challengeToken")
        if challenge:
            self.twofa_used = True
            query = urllib.parse.urlencode({"email": email})
            code_body = self._request(
                "GET", "%s/test/totp-code?%s" % (self.api_base(), query), None, None
            )
            code = json_get(code_body, "code")
            if not code:
                log.error("No TOTP code for %s (is the config store seeded?)" % email)
                return False
            body = self.api_post(
                "/auth/2fa/verify", {"challengeToken": challenge, "code": code}, jar
            )
        if not json_get(body, "user.id"):
            log.error("Headless login failed for %s: %s" % (email, body))
            return False
        return True

    def account_subscription_id(self, jar: http.cookiejar.CookieJar) -> str:
        return json_get(
            self._request("GET", self.api_base() + "/portal/subscription", None, jar), "id"
        )

    def account_mint_token(
        self, jar: http.cookiejar.CookieJar, subscription_id: str, name: str, scopes: list[str]
    ) -> str:
        """Mint an API token and return it; an empty answer raises."""
        body = self.api_post(
            "/api-tokens",
            {"subscriptionId": subscription_id, "name": name, "scopes": scopes},
            jar,
        )
        token = json_get(body, "token")
        if not token:
            log.error("API token mint failed: %s" % body)
            raise GatewayError("API token mint failed")
        return token

    def account_admin_session(
        self, email: str, password: str, jar: http.cookiejar.CookieJar
    ) -> bool:
        """A root session with an elevated window, which the admin subscription routes require."""
        self.api_post("/test/promote-admin", {"email": email})
        self.api_post("/test/elevate", {"email": email})
        return self.account_session(email, password, jar)

    def account_patch_subscription(
        self, jar: http.cookiejar.CookieJar, subscription_id: str, patch: dict
    ) -> str:
        return self._request(
            "PUT",
            "%s/admin/subscriptions/%s" % (self.api_base(), subscription_id),
            json.dumps(patch).encode(),
            jar,
        )


class GatewayError(RuntimeError):
    """The dev gateway (or something this run needed from it) could not be brought up."""


def parse_common_args(argv: list[str]) -> tuple[bool, bool, list[str]]:
    """Consume the flags every drill shares: returns (selftest, keep_work, remaining arguments)."""
    selftest = False
    keep_work = os.environ.get("DRILL_KEEP_WORK") == "1"
    rest: list[str] = []
    for arg in argv:
        if arg == "--selftest":
            selftest = True
        elif arg == "--keep-work":
            keep_work = True
        else:
            rest.append(arg)
    return selftest, keep_work, rest
