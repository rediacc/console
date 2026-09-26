#!/usr/bin/env python3
"""Both sides of the `core.account` port differential, in one file.

WHAT THIS IS FOR. `scripts/lib/shadow-gate.ts` compares two commands and rules on whether a port kept the verdict. It needs each side to PRINT what it observed, because the thing being compared is a finding multiset and not a return value. This module is the printer, and it can print either side:

    PYTHONPATH=.ci python3 -m rediacc_ci.core.shadow_driver --side old --twin .ci/lib/account.sh --port .ci/rediacc_ci/core/account.py <scenario>
        drives the BASH: sources `.ci/lib/account.sh` through the same prelude `.ci/legacy/run-legacy.sh` uses, and calls the twin's own functions.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.shadow_driver --side new --twin .ci/lib/account.sh --port .ci/rediacc_ci/core/account.py <scenario>
        drives the PYTHON: `rediacc_ci.core.account`.

RUN AS A MODULE AND NEVER BY PATH, which is not a style choice. A by-path invocation puts `.ci/rediacc_ci/core` on `sys.path[0]` and nothing on it can find `rediacc_ci`, so the file would have to open with a hand-written `sys.path.insert` hop. `test_canonical_sys_path_hop.py` refuses exactly that, it refused this file on its first run, and `PYTHONPATH=.ci` plus `-m` removes
the need rather than baselining it.

ONE FILE AND NOT TWO, on the `rediacc_ci/dev/shadow_driver.py` and `rediacc_ci/setup/shadow_driver.py` precedent, and for the reason those files record: `.ci/rediacc_ci/quality/dead_python.py:280` admits a pre-cutover port as alive only when it is named in a `.ci/shadow/*.jsonl` record, so a separate old-side module would be reported dead the day it landed.
`--twin` and `--port` carry the two paths for the same reason, and BOTH are checked to exist before anything runs: a row whose `old.cmd` names a twin that is gone reads as expired, and a row naming a port that is gone is a row about nothing.

-----------------------------------------------------------------------------
THE SANDBOX, AND WHY EACH SIDE BUILDS ITS OWN
-----------------------------------------------------------------------------
`account.sh` reads and WRITES real paths under `$CONSOLE_ROOT_DIR`: `private/account/account.db`, `.account-state`, `.devbox-state`, `.account-logs/`. A differential pointing both sides at one directory would have the first side leave the tree in the state that makes the second take a different branch, and the comparison would then be between two different programs.

So each side builds its OWN temporary `CONSOLE_ROOT_DIR`: a real directory holding the writable state, with `.devcontainer`, `scripts`, `.ci/config`, `.ci/scripts`, `.ci/lib` and `.ci/rediacc_ci` SYMLINKED to the checkout this driver was invoked from.
Symlinks rather than copies because `constants.sh` derives `CI_LIB_DIR` from `CONSOLE_ROOT_DIR` and `account.sh` reaches back out through `$CI_LIB_DIR/../..` for `scripts/lib/env-file.sh`, so the sandbox has to have the whole shape; and because the code under comparison must be the TRACKED code, which is what the recorded tree id claims.
Every path either command names is relative, so `shadow-gate`'s `reachesOutside` check passes honestly rather than by accident.

The temporary directory differs between the two sides, so every observation is normalised: the sandbox root becomes `<work>` and `$HOME` becomes `<home>` before anything is printed.

-----------------------------------------------------------------------------
EVERY PORT NUMBER IS FIXED, AND A BUSY ONE IS A REFUSAL
-----------------------------------------------------------------------------
The two sides run as two processes, minutes apart, so an ephemeral port chosen at runtime would differ between them and land in a message text as a mismatch that says nothing about the port.
Every port below is therefore a CONSTANT, and the driver refuses to run when the machine is not in the state the scenario needs: a port that must be free and is not, or a window that must be fully occupied and cannot be, exits 77 with the reason. Drifting to the next free port instead would silently measure a different branch on one side than on the other.

-----------------------------------------------------------------------------
WHY THE BANNER ROWS ARE PRINTED WITH DOTS INSTEAD OF SPACES
-----------------------------------------------------------------------------
`shadow-gate`'s own normaliser collapses internal whitespace runs, on the reasonable ground that a port which re-indents a continuation line has not changed which thing it objects to. `account_banner_row` is a padding function: its entire output is a whitespace run, and under that collapse a port padding to 40 columns instead of 63 would compare EQUAL.
So banner observations replace every space with a dot, on both sides, by the same substitution. Nothing else is rewritten.

-----------------------------------------------------------------------------
THE FOUR SCENARIOS, AND WHAT EACH ONE WOULD CATCH
-----------------------------------------------------------------------------
  probe       `account_banner_row` over five widths including a multibyte
              string, `account_rustfs_alive` against a dead port AND against a
              live HTTP server this driver runs, `account_wait_port` in both
              directions, and `account_allocate_ports` on a free pinned base and
              on one whose MIDDLE port this driver holds open. The live-server
              and held-port halves are the controls: without them every case in
              the group is a refusal, and two identical refusals prove nothing.
  keys        `account_generate_crypto_keys`, reduced to a claim per value: the
              four key encodings by LENGTH, which is fixed-width and so a real
              assertion, and the two random secrets by SHAPE (non-empty,
              alphanumeric, at most 64 characters), because their length is not
              fixed. No value is ever printed.
  totp        Five state-file shapes, including the one with no `gateway_port=`
              line at all, where the twin dies inside its own assignment and
              prints NOTHING. A port that helpfully explained itself there would
              be caught here.
  db          The two refusals, plus TWO no-free-port refusals, one of them
              through a `.devbox-state` file. That is the only way to observe the
              devbox-derived preferred port without launching a server: the
              driver holds every port in the scanned window open, and the twin
              names the port it wanted in its refusal.

THE `env` AND `fresh-env` SCENARIOS ARE GONE, with the four `.env` writers they drove (`account_generate_fresh_env`, `account_env_add_if_missing`, `account_ensure_env_keys`, `account_ensure_env`), which were deleted from BOTH sides when `private/account/.env` was retired. Their rows in `.ci/shadow/w7p5b-account.observations.jsonl` are history, not a claim about any code that still exists.

WHAT IS NEVER DRIVEN HERE: `account_dev`, `account_stop`, `account_test`, `account_test_e2e`, `account_reset`, `account_seed_demo`, `account_cleanup`, `account_docker_ghost_clean`, `account_stripe_auto`, `account_dev_credentials`, `account_rotation`, `account_bws_exec`, `account_load_defaults`, `account_state_gateway_port`, and `account_db`'s launch. `account_stop`, `account_rotation` and `account_bws_exec` are ported but real-run verified (see `rediacc_ci.core.account`); the rest are not ported. A ledger row is a claim of equivalence, and none of these has one.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import io
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

from rediacc_ci import log, runtmp
from rediacc_ci.core import account, ports

# The prefix `shadow-gate --finding-re '^obs '` is pointed at. Deliberately not a cross or a FAIL: those already mean "a finding" to the comparator's marker table, and an observation that AGREES is not a failure.
OBS = "obs"

EXIT_CANNOT_RUN = 77

# The fixed ports. See the header for why none of them is ephemeral.
LIVE_PORT = 45210
DEAD_PORT = 45211
FREE_BASE = 45220
PINNED_BASE = 45230
DEVBOX_STUDIO_PORT = 45300
# `account_db` scans `preferred .. preferred+40`, so a window is 41 ports wide.
SCAN_WINDOW = account.DB_BROWSER_SCAN_SPAN + 1

# What the sandbox symlinks. `.devcontainer` carries the toolchain pins `constants.sh` refuses to load without; `scripts` is here because `account.sh` sources `scripts/lib/env-file.sh` through `$CI_LIB_DIR/../..`; `.ci/scripts` because the prelude sources `toolchain.sh` and, through `local-common.sh`, `common.sh`.
SANDBOX_LINKS = (
    (".devcontainer",),
    ("scripts",),
    (".ci", "config"),
    (".ci", "scripts"),
    (".ci", "lib"),
    (".ci", "rediacc_ci"),
)

# The prelude `.ci/legacy/run-legacy.sh:41-48` runs before it sources `account.sh` at its line 405, minus `service.sh`, which `account.sh` does not touch. `local-common.sh` is here because `account_db` calls `check_node_version`, which that file defines and `account.sh` does not; the same late binding `service.py` records for `check_docker`.
PRELUDE = r"""
set -euo pipefail
source "$W/.ci/config/constants.sh"
source "$W/.ci/scripts/lib/toolchain.sh"
source "$W/.ci/lib/local-common.sh"
source "$W/.ci/lib/account.sh"

norm() {
    local s="$1"
    s="${s//$W/<work>}"
    s="${s//$HOME/<home>}"
    printf '%s' "$s"
}

emit() { printf 'obs %s\n' "$(norm "$1")"; }

# rc first, then stdout, then stderr, so the two sides cannot differ on ORDER
# for a reason that is the harness rather than the subject. The subshell keeps a
# twin function's `exit 1` from taking this driver down with it.
step() {
    local name="$1"
    shift
    local o e rc l
    o="$(mktemp)"
    e="$(mktemp)"
    # NOT `if ( set -e; "$@" ); then`, and that spelling cost a wrong measurement before it was fixed.
    # A command in an `if` CONDITION runs with errexit suppressed, and the suppression propagates into a subshell created there, so the inner `set -e` is INERT: the trap `docs/agent-reference/TRAPS.md` calls errexit-rearmed-in-a-tested-command. Under it the twin's `account_totp` survived the bare assignment that really kills it and printed a message it never prints in production.
    # `set +e` around a PLAIN subshell keeps this driver alive while leaving errexit genuinely armed inside it.
    set +e
    ( set -e; "$@" ) >"$o" 2>"$e"
    rc=$?
    set -e
    emit "rc $name=$rc"
    while IFS= read -r l; do emit "out $name| $l"; done <"$o"
    while IFS= read -r l; do emit "err $name| $l"; done <"$e"
    rm -f "$o" "$e"
}

banner() {
    local row
    row="$(account_banner_row "$1")"
    emit "banner| ${row// /.}"
}
"""


class RefusalError(RuntimeError):
    """The driver cannot run, so its silence would not be evidence."""


# --------------------------------------------------------------------------- the sandbox ---------------------------------------------------------------------------


def build_sandbox(repo: pathlib.Path) -> pathlib.Path:
    """One `CONSOLE_ROOT_DIR` for one side of one scenario."""
    for parts in SANDBOX_LINKS:
        source = repo.joinpath(*parts)
        if not source.exists():
            raise RefusalError(
                "the sandbox cannot be built: %s is missing from %s, so neither side would "
                "have the code under comparison" % ("/".join(parts), repo)
            )
    work = pathlib.Path(
        tempfile.mkdtemp(prefix="acct-shadow-", dir=runtmp.shared("shadow-driver-"))
    )
    for parts in SANDBOX_LINKS:
        target = work.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(repo.joinpath(*parts))
    (work / "private" / "account").mkdir(parents=True, exist_ok=True)
    return work


def sandbox_env(work: pathlib.Path) -> dict[str, str]:
    """The environment both sides run under, built the same way for each."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "CONSOLE_ROOT_DIR": str(work),
        "REDIACC_CI_ROOT": str(work),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


# --------------------------------------------------------------------------- the controls ---------------------------------------------------------------------------


class LiveServer:
    """A real HTTP server, so the alive probes have something to find.

    THE CONTROL THIS IS. `account_rustfs_alive` and `account_wait_port` both answer "no" for a closed port, and a driver that only ever asked about closed ports would compare two refusals and call that equivalence. This gives each side a port that really is serving, answering the same shape of probe RustFS answers.
    """

    class Quiet(http.server.SimpleHTTPRequestHandler):
        """SILENT, because the default handler logs every request to stderr.

        On the old side that lands on the driver's own stderr and is discarded; on the new side the request is served by a thread inside `contextlib.redirect_stderr`, so the access line landed in the captured observation and the two sides disagreed about a line neither implementation wrote.
        """

        def log_message(self, _format, *_args):
            return

    def __init__(self, port: int) -> None:
        handler = functools.partial(
            LiveServer.Quiet, directory=tempfile.mkdtemp(dir=runtmp.shared("shadow-driver-"))
        )
        try:
            self.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError as exc:
            raise RefusalError(
                "port %d is taken, so the live-server control cannot be set up and the "
                "alive probes would compare two refusals: %s" % (port, exc)
            ) from exc
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def require_free(base: int, count: int, why: str) -> None:
    """Refuse unless `count` ports from `base` are all free right now."""
    busy = [base + i for i in range(count) if ports.is_port_in_use(base + i)]
    if busy:
        raise RefusalError(
            "%s needs %d free port(s) from %d and these are listening: %s. This driver does "
            "not drift to another port, because the two sides run as two processes and a "
            "drift on one of them compares two different branches."
            % (why, count, base, ", ".join(str(p) for p in busy))
        )


def occupy(base: int, count: int, why: str) -> list[socket.socket]:
    """Make `count` ports from `base` busy, and prove every one of them is.

    A port already held by something else counts, which is why this verifies rather than trusting its own binds: the scenarios using it are ABOUT the no-free-port branch, and one free port in the window silently measures the opposite thing.
    """
    held: list[socket.socket] = []
    for offset in range(count):
        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", base + offset))
            sock.listen(1)
        except OSError:
            sock.close()
            continue
        held.append(sock)
    free = [base + i for i in range(count) if not ports.is_port_in_use(base + i)]
    if free:
        for sock in held:
            sock.close()
        raise RefusalError(
            "%s needs every port in %d..%d busy and these stayed free: %s"
            % (why, base, base + count - 1, ", ".join(str(p) for p in free))
        )
    return held


# --------------------------------------------------------------------------- printing ---------------------------------------------------------------------------


def text_lines(text: str) -> list[str]:
    """The lines `while IFS= read -r` would see: none at all for empty text."""
    if text == "":
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


class Printer:
    """The one emitter the new side goes through, matching the bash helpers above."""

    def __init__(self, work: pathlib.Path) -> None:
        self.work = str(work)
        self.home = os.environ.get("HOME", "/tmp")

    def norm(self, text: str) -> str:
        return text.replace(self.work, "<work>").replace(self.home, "<home>")

    def emit(self, text: str) -> None:
        print("%s %s" % (OBS, self.norm(text)))

    def step(self, name: str, rc: int, out: str, err: str) -> None:
        self.emit("rc %s=%d" % (name, rc))
        for line in text_lines(out):
            self.emit("out %s| %s" % (name, line))
        for line in text_lines(err):
            self.emit("err %s| %s" % (name, line))

    def banner(self, row: str) -> None:
        self.emit("banner| %s" % row.replace(" ", "."))


# --------------------------------------------------------------------------- the old side ---------------------------------------------------------------------------

BASH_SCENARIOS = {
    "probe": r"""
banner "hello"
banner ""
banner "$(printf '%063d' 0)"
banner "$(printf '%070d' 0)"
banner "héllo, ünicode"

step rustfs-dead account_rustfs_alive "$DEAD_PORT"
step rustfs-live account_rustfs_alive "$LIVE_PORT"
step wait-dead account_wait_port "$DEAD_PORT" "Thing" 0
step wait-live account_wait_port "$LIVE_PORT" "Live" 5

allocate() {
    account_allocate_ports
    echo "gateway=$GATEWAY_PORT vite=$VITE_PORT astro=$ASTRO_PORT"
}
REDIACC_DEV_PORT_BASE="$FREE_BASE" step allocate-free allocate
REDIACC_DEV_PORT_BASE="$PINNED_BASE" step allocate-busy allocate
""",
    "keys": r"""
crypto_claims() {
    account_generate_crypto_keys
    local name value
    for name in ED25519_PRIV ED25519_PUB X25519_PRIV X25519_PUB; do
        value="${!name}"
        echo "$name len=${#value}"
    done
    for name in JWT_SEC API_K; do
        value="${!name}"
        if [[ -n "$value" && "$value" != *[!A-Za-z0-9]* && ${#value} -le 64 ]]; then
            echo "$name shape=ok"
        else
            echo "$name shape=bad"
        fi
    done
}
step keys crypto_claims
""",
    "totp": r"""
rm -f "$ACCOUNT_STATE_FILE"
step no-state account_totp

printf 'started=1\n' >"$ACCOUNT_STATE_FILE"
step no-key account_totp

printf 'gateway_port=\n' >"$ACCOUNT_STATE_FILE"
step empty-value account_totp

printf 'gateway_port=a=b\n' >"$ACCOUNT_STATE_FILE"
step equals-in-value account_totp

printf 'gateway_port=%s\n' "$DEAD_PORT" >"$ACCOUNT_STATE_FILE"
step closed-port account_totp
step closed-port-email account_totp other@rediacc.io
""",
    "db": r"""
step unknown-option account_db --bogus
step studio-then-unknown account_db --studio --bogus
step no-database account_db
DATABASE_PATH="$ACCOUNT_DIR/nowhere.db" step no-database-env account_db

: >"$ACCOUNT_DIR/account.db"
rm -f "$DEVBOX_STATE_FILE"
step no-port-plain account_db

printf 'base_port=%s\n' "$DEVBOX_BASE" >"$DEVBOX_STATE_FILE"
step no-port-devbox account_db
""",
}


def run_old(work: pathlib.Path, scenario: str, env: dict[str, str]) -> int:
    """Source the twin through `run-legacy.sh`'s own prelude and call its functions."""
    script = work / "driver.sh"
    script.write_text(
        'W="%s"\n%s\n%s' % (work, PRELUDE, BASH_SCENARIOS[scenario]),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


# --------------------------------------------------------------------------- the new side ---------------------------------------------------------------------------


def call(printer: Printer, name: str, fn) -> int:
    """Run one port call with its two streams captured, and print the same shape.

    The return-value mapping is the twin's: False is exit 1, True and None are exit 0, and an `AccountError` carries the code the twin's `exit` would have used.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        log.reset(colour=False)
        try:
            result = fn()
        except account.AccountError as exc:
            result = exc.code
        if result is False:
            rc = 1
        elif result is True or result is None:
            rc = 0
        else:
            rc = int(result)
    log.reset(colour=False)
    printer.step(name, rc, out.getvalue(), err.getvalue())
    return rc


def run_new(scenario: str, printer: Printer, env: dict[str, str]) -> int:
    """Drive `rediacc_ci.core.account` through the same scenario."""
    account_directory = pathlib.Path(account.account_dir(env))
    state = pathlib.Path(account.state_file(env))
    devbox_state = pathlib.Path(account.devbox_state_file(env))
    dead = int(env["DEAD_PORT"])

    if scenario == "probe":
        for text in ("hello", "", "%063d" % 0, "%070d" % 0, "héllo, ünicode"):
            printer.banner(account.banner_row(text))
        live = int(env["LIVE_PORT"])
        call(printer, "rustfs-dead", lambda: account.rustfs_alive(dead))
        call(printer, "rustfs-live", lambda: account.rustfs_alive(live))
        call(printer, "wait-dead", lambda: account.wait_port(dead, "Thing", 0, env=env))
        call(printer, "wait-live", lambda: account.wait_port(live, "Live", 5, env=env))

        def allocate(base: str) -> int:
            gateway, vite, astro = account.allocate_ports(dict(env, REDIACC_DEV_PORT_BASE=base))
            print("gateway=%d vite=%d astro=%d" % (gateway, vite, astro))
            return 0

        call(printer, "allocate-free", lambda: allocate(env["FREE_BASE"]))
        call(printer, "allocate-busy", lambda: allocate(env["PINNED_BASE"]))
        return 0

    if scenario == "keys":

        def crypto_claims() -> int:
            keys = account.generate_crypto_keys()
            for name, value in (
                ("ED25519_PRIV", keys.ed25519_priv),
                ("ED25519_PUB", keys.ed25519_pub),
                ("X25519_PRIV", keys.x25519_priv),
                ("X25519_PUB", keys.x25519_pub),
            ):
                print("%s len=%d" % (name, len(value)))
            for name, value in (("JWT_SEC", keys.jwt), ("API_K", keys.api_key)):
                ok = bool(value) and value.isascii() and value.isalnum() and len(value) <= 64
                print("%s shape=%s" % (name, "ok" if ok else "bad"))
            return 0

        call(printer, "keys", crypto_claims)
        return 0

    if scenario == "totp":
        state.unlink(missing_ok=True)
        call(printer, "no-state", lambda: account.totp(None, env))
        for name, body in (
            ("no-key", "started=1\n"),
            ("empty-value", "gateway_port=\n"),
            ("equals-in-value", "gateway_port=a=b\n"),
            ("closed-port", "gateway_port=%d\n" % dead),
        ):
            state.write_text(body, encoding="utf-8")
            call(printer, name, lambda: account.totp(None, env))
        call(printer, "closed-port-email", lambda: account.totp("other@rediacc.io", env))
        return 0

    if scenario == "db":
        call(printer, "unknown-option", lambda: account.db(["--bogus"], env))
        call(printer, "studio-then-unknown", lambda: account.db(["--studio", "--bogus"], env))
        call(printer, "no-database", lambda: account.db([], env))
        nowhere = str(account_directory / "nowhere.db")
        call(printer, "no-database-env", lambda: account.db([], dict(env, DATABASE_PATH=nowhere)))
        (account_directory / "account.db").write_text("", encoding="utf-8")
        devbox_state.unlink(missing_ok=True)
        call(printer, "no-port-plain", lambda: account.db([], env))
        devbox_state.write_text("base_port=%s\n" % env["DEVBOX_BASE"], encoding="utf-8")
        call(printer, "no-port-devbox", lambda: account.db([], env))
        return 0

    raise RefusalError("unknown scenario %r" % scenario)


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="one side of the core.account differential")
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--twin", required=True, help="the bash file under comparison")
    parser.add_argument("--port", required=True, help="the Python module under comparison")
    parser.add_argument("scenario", choices=sorted(BASH_SCENARIOS))
    args = parser.parse_args(argv)

    repo = pathlib.Path.cwd().resolve()
    for label, rel in (("twin", args.twin), ("port", args.port)):
        if not (repo / rel).is_file():
            sys.stderr.write(
                "shadow_driver: the %s %s does not exist under %s. A ledger row naming a "
                "file that is not there attests to nothing.\n" % (label, rel, repo)
            )
            return EXIT_CANNOT_RUN

    server = None
    held: list[socket.socket] = []
    work = None
    try:
        require_free(DEAD_PORT, 1, "the dead-port probe")
        require_free(FREE_BASE, 3, "the free pinned base")
        require_free(PINNED_BASE, 1, "the pinned base itself")
        require_free(PINNED_BASE + 2, 1, "the third port of the pinned triple")
        server = LiveServer(LIVE_PORT)
        # The MIDDLE port of the pinned triple, so the twin's loop has to reach offset 1 before it refuses. Holding offset 0 would also pass for an implementation that only ever probed the base.
        held.extend(occupy(PINNED_BASE + 1, 1, "the busy pinned triple"))
        held.extend(occupy(DEVBOX_STUDIO_PORT, SCAN_WINDOW, "the devbox studio scan window"))
        held.extend(occupy(account.DB_BROWSER_PREFERRED, SCAN_WINDOW, "the default scan window"))

        work = build_sandbox(repo)
        printer = Printer(work)
        env = sandbox_env(work)
        env.update(
            {
                "DEAD_PORT": str(DEAD_PORT),
                "LIVE_PORT": str(LIVE_PORT),
                "FREE_BASE": str(FREE_BASE),
                "PINNED_BASE": str(PINNED_BASE),
                "DEVBOX_BASE": str(DEVBOX_STUDIO_PORT - account.DEVBOX_OFFSET_STUDIO),
            }
        )
        if args.side == "old":
            return run_old(work, args.scenario, env)
        return run_new(args.scenario, printer, env)
    except RefusalError as exc:
        sys.stderr.write("shadow_driver: %s\n" % exc)
        return EXIT_CANNOT_RUN
    finally:
        if server is not None:
            server.close()
        for sock in held:
            sock.close()
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
