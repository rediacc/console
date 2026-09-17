#!/usr/bin/env python3
"""Port of `.ci/scripts/test/test-install-sh-config.sh` (gate `check:ci-install-sh-config`).

Unit test for `install.sh`'s `write_install_config` function.

Covers the five scenarios the worker rewrite can land us in when a user runs `curl -fsSL https://<preview>.rediacc.com/install.sh | bash`:

  worker_full                    both rewritten, server unreachable
  worker_channel_only            only CHANNEL rewritten (fail-safe path)
  worker_server_only             only SERVER_URL rewritten
  worker_none                    neither rewritten; no rediacc.json written
  worker_full_with_server_info   both rewritten + reachable server-info
                                 returning a different updateChannel
                                 (regression guard: baked channel must win)

REGISTERED CI GATE: `check:ci-install-sh-config`, step "install.sh config tests" in `.github/workflows/ci-quality.yml`, job `quality-static`.

WHAT MOVES AND WHAT DOES NOT. Only the HARNESS moves: the five cases, the mock server, the assertions, the tally. The SUBJECT is `write_install_config`, a bash function inside the user-facing `packages/www/public/install.sh`, and it is still sourced and called AS BASH, once per case, exactly as the twin does. A Python reimplementation of the installer's config writer would be a
second instrument certifying itself -- the objection that got `.ci/scripts/test/lib/git-fixture.sh` allowlisted rather than ported.

PORT NOTES, each driven before being written down.

THE SUBSHELL INHERITS `set -euo pipefail`, so the port's `bash -c` must set it too. The twin's `( ... )` on `test-install-sh-config.sh:56-80` is a subshell of a script that set those options on :28; a bare `bash -c` would run the same source-and-call under DIFFERENT shell options, and `install.sh` reads
`${REDIACC_CHANNEL:-}`-style defaults whose behaviour under `-u` is the whole
point of the exercise.

`local x; x=$(python3 ...)` IS FATAL UNDER `set -e`, and the twin has no
`|| echo PARSE_ERR` fallback here (unlike its sibling `test-rdc-sh-env.sh:172`). A `rediacc.json` that parses but lacks
`account.updateChannel` therefore kills the twin outright: rc=1, CPython's own
traceback on stderr, and no tally. `read_account_field` below runs the twin's identical `python3 -c` command rather than reading the JSON in-process, precisely so that traceback is produced rather than forged; see its docstring.

THE SUBSHELL'S OWN FAILURE IS FATAL TOO. `run_case` is called at top level, so a non-zero `write_install_config` ends the twin with that status and no "Passed:" summary. Reproduced.

THE MOCK PORT IS THE ONE BYTE THE TWO SIDES CANNOT SHARE. Case five's PASS line quotes `http://127.0.0.1:<port>`, and the port is whatever the kernel handed out; two runs of the SAME implementation disagree on it. The differential normalizes `127\\.0\\.0\\.1:\\d+` on both sides and asserts the rest byte for byte, and the four other cases -- where every planted defect in the ledger
lives -- quote no volatile value at all.

`write_install_config` PRINTS A BARE `echo ""` BEFORE ITS SUCCESS LINE (`install.sh:301`), and the test stubs `success` to a no-op AFTER sourcing, so the blank line survives and the success text does not. Those blank lines are part of the twin's stdout, interleaved with the tally lines, which is why every
`print` here passes `flush=True`: Python fully buffers against a pipe while the
bash child writes to the inherited fd directly, so without the flush the port's own lines land out of order regardless of when they were printed.

Exit: 0 when no case failed, 1 otherwise.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from rediacc_ci import paths

INSTALL_SH_REL = "packages/www/public/install.sh"

SERVER_INFO = '{"updateChannel":"stable","e2e":{"keys":[{"publicKeySpki":"MOCK"}]}}\n'

# The twin's subshell body (`test-install-sh-config.sh:56-80`), minus the
# environment work, which is done through `env=` instead of `export`/`unset`.
CASE_SCRIPT = """set -euo pipefail
source "%s"
success() { :; }
write_install_config
"""


class SilentExitError(Exception):
    """`set -e` killing the twin mid-case: the child's rc, the child's stderr."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


class Tally:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def fail(self, message: str) -> None:
        self.failed += 1
        print("  ✗ %s" % message, file=sys.stderr, flush=True)

    def ok(self, message: str) -> None:
        self.passed += 1
        print("  ✓ %s" % message, flush=True)


def free_port() -> int:
    """`python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); ...'`."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def config_mode(config_file: pathlib.Path) -> str:
    """`stat -c '%a'` / `stat -f '%OLp'`: the octal access rights, no padding."""
    return "%o" % (config_file.stat().st_mode & 0o7777)


def read_account_field(config_file: pathlib.Path, field: str) -> subprocess.CompletedProcess[str]:
    """The twin's own `python3 -c` one-liner, run as a real subprocess.

    NOT reimplemented in-process, and the reason is the FAILURE path. The twin (`test-install-sh-config.sh:98-99`) does NOT redirect the child's stderr, so a config whose `account` has no such key prints CPython's own traceback -- caret ruler, tilde underline and all -- straight onto the gate's stderr, and then `set -e` kills the run. That rendering is a property of the exact
    interpreter, and no reimplementation can forge it byte for byte; running the identical command produces it for free. (Its sibling `test-rdc-sh-env.sh:172` DOES add `2>/dev/null || echo PARSE_ERR`, which is why that port reads the JSON in-process instead.)
    """
    return subprocess.run(
        [
            "python3",
            "-c",
            "import json,sys; print(json.load(open(sys.argv[1]))['account']['%s'])" % field,
            str(config_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def substituted(completed: subprocess.CompletedProcess[str]) -> str:
    """`$(...)`: the child's stdout with every trailing newline removed."""
    return re.sub(r"\n+$", "", completed.stdout)


def run_case(
    tally: Tally,
    install_sh: pathlib.Path,
    name: str,
    channel: str,
    server_url: str,
    expect_file: str,
    expect_channel: str,
    expect_account: str,
) -> None:
    tmp_home = pathlib.Path(tempfile.mkdtemp())
    config_file = tmp_home / ".config" / "rediacc" / "rediacc.json"

    env = dict(os.environ)
    env["HOME"] = str(tmp_home)
    env["XDG_CONFIG_HOME"] = str(tmp_home / ".config")
    # install.sh reads these at top level, then write_install_config uses the CHANNEL/SERVER_URL globals that result.
    if channel and channel != "stable":
        env["REDIACC_CHANNEL"] = channel
    else:
        env.pop("REDIACC_CHANNEL", None)
    if server_url:
        env["REDIACC_SERVER_URL"] = server_url
    else:
        env.pop("REDIACC_SERVER_URL", None)
    env.pop("REDIACC_RELEASES_URL", None)
    env["REDIACC_INSTALL_SH_SOURCE_ONLY"] = "1"

    completed = subprocess.run(
        ["bash", "-c", CASE_SCRIPT % install_sh],
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        shutil.rmtree(tmp_home, ignore_errors=True)
        raise SilentExitError(completed.returncode)

    try:
        if expect_file == "no":
            if config_file.is_file():
                tally.fail(
                    "%s: expected no rediacc.json, but file was written: %s"
                    % (name, config_file.read_text(encoding="utf-8").rstrip("\n"))
                )
            else:
                tally.ok("%s: no rediacc.json written" % name)
            return

        if not config_file.is_file():
            tally.fail("%s: expected rediacc.json, but none was written" % name)
            return

        # `local got_channel; got_channel=$(python3 ...)` under `set -e`: the
        # assignment takes the substitution's status, so a failing read ends the whole run right here, with the child's traceback already on stderr.
        for field in ("updateChannel", "accountServer"):
            probe = read_account_field(config_file, field)
            sys.stderr.write(probe.stderr)
            sys.stderr.flush()
            if probe.returncode != 0:
                raise SilentExitError(probe.returncode)
            if field == "updateChannel":
                got_channel = substituted(probe)
            else:
                got_account = substituted(probe)

        if got_channel == expect_channel and got_account == expect_account:
            tally.ok("%s: channel=%s accountServer=%s" % (name, got_channel, got_account))
        else:
            tally.fail(
                "%s: got channel=%s accountServer=%s; expected channel=%s accountServer=%s"
                % (name, got_channel, got_account, expect_channel, expect_account)
            )

        mode = config_mode(config_file)
        if mode != "600":
            tally.fail("%s: expected mode 600, got %s" % (name, mode))
    finally:
        shutil.rmtree(tmp_home, ignore_errors=True)


class MockServer:
    """`python3 -m http.server` over a directory holding one server-info file."""

    def __init__(self) -> None:
        self.port = free_port()
        self.directory = pathlib.Path(tempfile.mkdtemp())
        well_known = self.directory / "account" / "api" / "v1" / ".well-known"
        well_known.mkdir(parents=True, exist_ok=True)
        (well_known / "server-info").write_text(SERVER_INFO, encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(self.port)],
            cwd=self.directory,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d" % self.port

    def wait(self) -> None:
        """The twin's `for _ in 1 2 3 4 5 6` curl-then-sleep loop."""
        probe = "%s/account/api/v1/.well-known/server-info" % self.url
        for _ in range(6):
            if (
                subprocess.run(
                    ["curl", "-fsS", probe],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode
                == 0
            ):
                return
            time.sleep(0.5)

    def stop(self) -> None:
        """`trap 'kill $mock_pid 2>/dev/null; rm -rf "$mock_dir"' EXIT`."""
        self.process.kill()
        self.process.wait()
        shutil.rmtree(self.directory, ignore_errors=True)


def main(argv: list[str]) -> int:  # noqa: ARG001 -- the twin takes no arguments
    install_sh = paths.repo_root() / INSTALL_SH_REL
    if not install_sh.is_file():
        print("FAIL: install.sh not found at %s" % install_sh, file=sys.stderr, flush=True)
        return 1

    tally = Tally()
    print("install.sh write_install_config matrix:", flush=True)

    server = MockServer()
    try:
        server.wait()
        cases = (
            # worker_full: both rewrites landed -- ideal case
            (
                "worker_full",
                "edge",
                "https://edge.rediacc.com",
                "yes",
                "edge",
                "https://edge.rediacc.com",
            ),
            # worker_channel_only: fail-safe recovery path (the gap we closed)
            ("worker_channel_only", "edge", "", "yes", "edge", "https://www.rediacc.com"),
            # worker_none: neither rewrite landed -- install.sh can't infer origin, leaves no config so rdc update falls back to default stable.
            ("worker_none", "stable", "", "no", "", ""),
            # worker_server_only: SERVER_URL rewritten but CHANNEL not.
            (
                "worker_server_only",
                "stable",
                "https://unreachable-server.invalid",
                "yes",
                "stable",
                "https://unreachable-server.invalid",
            ),
            # worker_full_with_server_info: both baked + a real server-info responding with `updateChannel: stable`. The baked edge channel must NOT be overridden.
            ("worker_full_with_server_info", "edge", server.url, "yes", "edge", server.url),
        )
        for name, channel, server_url, expect_file, expect_channel, expect_account in cases:
            run_case(
                tally,
                install_sh,
                name,
                channel,
                server_url,
                expect_file,
                expect_channel,
                expect_account,
            )
    except SilentExitError as exit_request:
        return exit_request.code
    finally:
        server.stop()

    print(flush=True)  # the twin's bare `echo ""`
    print("Passed: %d" % tally.passed, flush=True)
    print("Failed: %d" % tally.failed, flush=True)
    return 1 if tally.failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
