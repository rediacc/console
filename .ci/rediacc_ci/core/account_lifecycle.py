"""The SIDE-EFFECTING half of `.ci/lib/account.sh`, ported function for function.

PORTED FROM `.ci/lib/account.sh`, the twelve functions `rediacc_ci.core.account` left out because each one starts, stops or talks to real infrastructure: `account_load_defaults`, `account_state_gateway_port`, `account_spawn` (as `spawn_background()`), `account_cleanup`, `account_docker_ghost_clean`, `account_stripe_auto`, `account_dev`, `account_dev_credentials`, `account_test`, `account_test_e2e`, `account_reset` and `account_seed_demo`.
With `rediacc_ci.core.account` this covers all twenty-two of the twin's functions. The twin still exists and is still what `.ci/legacy/run-legacy.sh:405` and `:443` source; nothing is cut over here (that is W7P5-c).

A SIBLING MODULE AND NOT MORE OF `account.py`, because that file is the deterministic half with its own K=5 ledger (`w7p5b-account`) and its own driver; this half is proved a different way, by `core/account_lifecycle_shadow_driver.py` under the pair `w7p5b-account-lifecycle`.

--------------------------------------------------------------------------
HOW IT IS PROVED: A STUB-FARM TRANSCRIPT, NOT A LIVE STACK
--------------------------------------------------------------------------
`core/stubfarm.py` puts a directory of scripted programs first on PATH for BOTH sides (`docker`, `curl`, `npx`, `npm`, `stripe`, `lsof`, `pgrep`, `kill`, `sleep`, `ss`, `openssl`, `hostname`, `python3` for the Bitwarden calls), each appending its argv to one transcript. The driver compares rc, both streams, the ordered transcript and the files left behind, so this port has to make the same calls with the same arguments in the same order as the twin.
That is why it calls PROGRAMS where a Python programmer would reach for a library: `sleep`, `kill` (where the twin reaches it through `xargs`), `date +%s`, `jq` and `python3 -m rediacc_ci.core.bws_env` are the twin's calls, and a scenario answers them through the stubs. `kill` the BUILTIN (a bare `kill "$pid"`) has no program behind it, so those stay `os.kill`.

THE SHELL ENVIRONMENT IS `os.environ`. Every `export` in the twin is an assignment to it, and every child inherits it, which is what a bash child inherits. `ACCOUNT_PIDS` is `PIDS` below.

--------------------------------------------------------------------------
ERREXIT
--------------------------------------------------------------------------
Every sourcer of the twin arms `set -euo pipefail`, so a bare command that fails ENDS THE PROCESS with its status rather than returning. `ErrexitError` is that: it carries the status, `main()` exits with it, and `dev()`'s cleanup maps it to the exit code its EXIT trap would have seen. `rediacc_ci.core.local_common.LocalCommonError` and `rediacc_ci.core.account.AccountError` are the same thing raised by the functions this module borrows, and `code_of()` reads all three.

--------------------------------------------------------------------------
TWIN BEHAVIOURS REPRODUCED ON PURPOSE, NOT FIXED
--------------------------------------------------------------------------
  1. `account_seed_demo`'s "Could not reach the account gateway" branch is DEAD CODE. `body=$(curl ...)` is a bare assignment, so a failing curl kills the function under errexit before `curl_exit=$?` is ever read; what the user sees is curl's own `-sS` diagnostic and curl's exit status. `seed_demo()` dies the same way.
  2. `account_seed_demo`, `account_dev` and `account_stop` read the state file with the same bare `grep | cut` assignment `account_totp` does (`rediacc_ci.core.account`, defect 1), so a state file missing the key is a SILENT exit 1.
  3. `account_dev_credentials` DIES SILENTLY when the seed-config-store answer is not a JSON object node can read. The three `read -r` calls sit in a `{ ... } < <(node ...)` group whose own `|| true` is inside the process substitution, so a node that prints nothing leaves the first `read` at end of file, and that failing `read` is a bare command under errexit. The login banner is never printed. `seed_fields()` raises where node prints nothing.
  4. `account_dev_credentials` also dies silently when `hostname -I` fails (macOS has no `-I`): `lan_ip=$(hostname -I 2>/dev/null | awk ...)` is a bare assignment whose pipeline status is hostname's under pipefail.
  5. `account_stripe_auto` dies with npx's status when `scripts/stripe-sync.ts` fails, because `(... npx tsx ... 2>&1 | tail -5)` is a bare subshell and pipefail carries npx's status out of the pipe.
  6. `account_dev`, `account_test_e2e` and `account_stripe_auto` all `tail` an install or sync log, so a failing `npm install` shows only its last line (or five) before the process ends with npm's status.
  7. `account_dev` writes `pids=` SPACE-separated. `${ACCOUNT_PIDS[*]// /,}` applies the substitution to each ELEMENT (none of which holds a space) and only then joins them with the first character of IFS, so the commas the line was written for never appear: `A=(101 202 303); echo "${A[*]// /,}"` prints `101 202 303`. Harmless today, because both readers (`account_dev`'s previous-instance stop and `account_stop`) turn commas into spaces and then split on whitespace, so either spelling works; the comma form is the obvious cleanup once this port is the only writer (W7P5-c).

--------------------------------------------------------------------------
WHAT THE DIFFERENTIAL DOES NOT REACH, SAID HERE RATHER THAN LEFT TO A READER
--------------------------------------------------------------------------
  * The INT and TERM arms of `account_dev`'s trap. `dev()` installs handlers that run the same cleanup with `128 + signal`, and no scenario sends a signal.
  * The account-dev and account-e2e `bws_exec()` re-execution. Every scenario runs with the profile already hydrated (`REDIACC_BWS_PROFILES`), because the other branch replaces the process with a live Bitwarden read; `rediacc_ci.core.account` records how that function is real-run verified instead.
  * A NON-NUMERIC port in bash arithmetic (`$((old_gateway + offset))`) or in `is-port-in-use`: the twin evaluates the first as a variable name and prints a Python traceback for the second. Both raise `ErrexitError(1)` here, silently; no scenario feeds either.
  * The dev servers' OWN descendants beyond one level. `cleanup()` signals each job's whole process group, which the `cleanup-kills-tree` case proves for a job with a grandchild; a server that moves a child into a new session of its own would still escape both sides alike.
  * `account_stripe_auto` with `GATEWAY_PORT` unset, which the twin survives only by accident (the unbound variable kills two subshells, not the function). `stripe_auto()` reads it as empty. Every real caller sets it.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

from rediacc_ci import log
from rediacc_ci.core import account, env, local_common, ports

# `ACCOUNT_PIDS`, `.ci/lib/account.sh:39`: every background process `account_dev` starts, killed by `account_cleanup`.
PIDS: list[int] = []
_PROCS: dict[int, subprocess.Popen] = {}

# `.ci/lib/account.sh:404`, the canonical RustFS port the reuse path probes.
RUSTFS_PORT = 9100

# `.ci/lib/account.sh:524-526`.
DEFAULT_ROOT_EMAIL = "root@rediacc.dev"
DEV_USER_EMAIL = "dev-user@rediacc.io"
DEV_PARTNER_EMAIL = "dev-partner@rediacc.io"
# `.ci/lib/account.sh:558`. A CONSTANT on purpose: an idempotent re-seed cannot re-wrap the CEK without the prior password.
STORE_PASSWORD = "DevConsole123!"  # noqa: S105 -- the twin's published dev constant, printed in the banner

# The six Bitwarden specs `account_reset` pushes (`.ci/lib/account.sh:802-807`) and the two it caches (`:816-817`).
RESET_STORE_SPECS = (
    "ACCOUNT_ED25519_PRIVATE_KEY_DEV > ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY_DEV > ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY_DEV > ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY_DEV > ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_JWT_SECRET_DEV > ACCOUNT_JWT_SECRET",
    "ACCOUNT_SERVER_API_KEY_DEV > ACCOUNT_SERVER_API_KEY",
)
RESET_CACHE_SPECS = (
    "ACCOUNT_ED25519_PUBLIC_KEY_DEV > ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY_DEV > ACCOUNT_X25519_PUBLIC_KEY",
)

SEED_USAGE = "Usage: ./run.sh account seed-demo <email> [--port N]"

RUSTFS_GHOST_HINT = (
    "RustFS failed to start (config storage disabled). If 'docker compose' is stuck on a ghost container, run: "
    "docker run -d --name rediacc-config-rustfs-dev -p 9100:9000 -e RUSTFS_VOLUMES=/data -e RUSTFS_ADDRESS=0.0.0.0:9000 "
    "-e RUSTFS_ACCESS_KEY=configadmin -e RUSTFS_SECRET_KEY=configadmin rustfs/rustfs:latest"
)

# `grep -oE 'whsec_[^[:space:]]+'`. `[:space:]` in the C locale is exactly these six bytes, which Python's `\s` is not.
WEBHOOK_SECRET_RE = re.compile(r"whsec_[^ \t\n\v\f\r]+")


class ErrexitError(Exception):
    """A bare command failing under the twin's errexit: the process ends with `code`."""

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message or "exit %d" % code)
        self.code = code


def code_of(exc: BaseException) -> int:
    """The exit status an errexit death, a twin refusal or a `sys.exit` carries."""
    if isinstance(exc, (ErrexitError, local_common.LocalCommonError, account.AccountError)):
        return exc.code
    if isinstance(exc, SystemExit):
        return exc.code if isinstance(exc.code, int) else 1
    raise exc


# Every way the twin's process can end that has a status.
DEATHS = (ErrexitError, SystemExit, local_common.LocalCommonError, account.AccountError)


# --------------------------------------------------------------------------- running the twin's programs ---------------------------------------------------------------------------


def _flush() -> None:
    """Flush both streams before a child writes to the same descriptors, so the twin's line order survives."""
    sys.stdout.flush()
    sys.stderr.flush()


def _run(
    argv: list[str],
    *,
    cwd: str | None = None,
    quiet_out: bool = False,
    quiet_err: bool = False,
    extra_env: dict[str, str] | None = None,
) -> int:
    """A bare command line of the twin's: streams inherited unless it redirects them. 127 where bash says "command not found"."""
    _flush()
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            stdout=subprocess.DEVNULL if quiet_out else None,
            stderr=subprocess.DEVNULL if quiet_err else None,
            env={**os.environ, **extra_env} if extra_env else None,
            check=False,
        ).returncode
    except FileNotFoundError:
        if not quiet_err:
            sys.stderr.write("%s: command not found\n" % argv[0])
        return 127


def _must(argv: list[str], **kwargs) -> None:
    """A bare command under errexit: a non-zero status ends the process with that status."""
    status = _run(argv, **kwargs)
    if status != 0:
        raise ErrexitError(status, "%s exited %d under errexit" % (argv[0], status))


def _capture(argv: list[str], *, quiet_err: bool = False) -> tuple[int, str]:
    """`$(argv)`: stdout captured and trailing newlines dropped, stderr inherited unless discarded."""
    _flush()
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet_err else None,
            text=True,
            errors="surrogateescape",
            check=False,
        )
    except FileNotFoundError:
        if not quiet_err:
            sys.stderr.write("%s: command not found\n" % argv[0])
        return 127, ""
    return proc.returncode, proc.stdout.rstrip("\n")


def _sleep(seconds: int) -> None:
    """`sleep N`, the PROGRAM, as a bare command."""
    _must(["sleep", str(seconds)])


def _cd_or_die(path: str, *, stream=None) -> None:
    """`cd "$path"` as the first command of a `(cd ... && ...)` subshell: bash's diagnostic, then the subshell's status 1."""
    message = local_common.cd_error(path)
    if message is None:
        return
    (stream or sys.stderr).write(message + "\n")
    raise ErrexitError(1, message)


def _tail(
    argv: list[str], count: int, *, cwd: str, extra_env: dict[str, str] | None = None
) -> None:
    """`(cd CWD && ARGV 2>&1 | tail -COUNT)` under pipefail: the last lines, then ARGV's status as a death."""
    _cd_or_die(cwd)
    _flush()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, **extra_env} if extra_env else None,
            check=False,
        )
        out, status = proc.stdout, proc.returncode
    except FileNotFoundError:
        out, status = ("%s: command not found\n" % argv[0]).encode(), 127
    lines = out.splitlines(keepends=True)
    sys.stdout.buffer.write(b"".join(lines[-count:]) if lines else b"")
    sys.stdout.flush()
    if status != 0:
        raise ErrexitError(status, "%s exited %d inside a pipefail pipeline" % (argv[0], status))


def _newer(one: str, two: str) -> bool:
    """`[[ ONE -nt TWO ]]`: ONE's mtime is later, or ONE exists and TWO does not."""
    try:
        first = os.stat(one).st_mtime_ns
    except OSError:
        return False
    try:
        second = os.stat(two).st_mtime_ns
    except OSError:
        return True
    return first > second


def _pad_bytes(text: str, width: int) -> str:
    """`printf '%-Ns'`, which pads by BYTES. See `rediacc_ci.core.account`, defect 2."""
    return text + " " * max(width - len(text.encode("utf-8")), 0)


def _check_node() -> None:
    """A bare `check_node_version`: its `return 1` is the caller's death."""
    if not local_common.check_node_version():
        raise ErrexitError(1, "check_node_version failed")


def spawn_background(
    argv: list[str], *, cwd: str | None = None, log_path: str | None = None
) -> int:
    """`account_spawn`, `.ci/lib/account.sh:74-82`: `( cd CWD && ARGV ) >LOG 2>&1 &`, remembered in `PIDS`. Returns the pid, `$!`.

    THE JOB LEADS ITS OWN PROCESS GROUP (`process_group=0`, the `setpgid` the twin's `set -m` performs), so `cleanup()` can end the whole tree and not only the pid it holds.

    REAPED BY A THREAD THE MOMENT IT EXITS, because bash reaps its background jobs and `account_wait_port`'s `kill -0 "$pid"` therefore sees a finished job as gone. A Popen nobody waits on stays a zombie that still answers `kill -0`, and `wait_port` would wait for it forever.
    """
    _flush()
    handle = open(log_path, "wb") if log_path else None  # noqa: SIM115 -- handed to the child and closed below
    try:
        if cwd is not None and local_common.cd_error(cwd) is not None:
            # The subshell's `cd` fails: its diagnostic lands in the log, and the job ends with status 1.
            if handle is not None:
                handle.write((local_common.cd_error(cwd) + "\n").encode())
            proc = subprocess.Popen(
                ["false"], stdout=handle, stderr=subprocess.STDOUT, process_group=0
            )
        else:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                stdout=handle,
                stderr=subprocess.STDOUT if handle is not None else None,
                process_group=0,
            )
    finally:
        if handle is not None:
            handle.close()
    threading.Thread(target=proc.wait, daemon=True).start()
    PIDS.append(proc.pid)
    _PROCS[proc.pid] = proc
    return proc.pid


# --------------------------------------------------------------------------- the small helpers ---------------------------------------------------------------------------


def load_defaults() -> int:
    """`account_load_defaults`, `.ci/lib/account.sh:60-62`. The shell wins over `private/account/dev.defaults.env`.

    `env_file_load` runs `python3 -m rediacc_ci.core.env export` and evals the result, so an unreadable file is that module's one-line refusal followed by the shim's own, and nothing is exported.
    """
    path = os.path.join(account.account_dir(), "dev.defaults.env")
    try:
        env.apply(path, os.environ)
    except env.EnvFileError as err:
        sys.stderr.write("env: %s\n" % err)
        sys.stderr.write(
            "env_file_load: refusing to continue; '%s' could not be read (rc=1)\n" % path
        )
        return 1
    return 0


def grep_cut(text: str, key: str) -> str:
    """`grep "^KEY=" FILE | cut -d= -f2` as a bare assignment: EVERY matching line's second field, joined as `$(...)` joins them.

    Raises `account.StateAbortedError` where grep matches nothing, which under pipefail and errexit is the twin's silent death.
    """
    prefix = key + "="
    values = [line.split("=")[1] for line in text.split("\n") if line.startswith(prefix)]
    if not values:
        raise account.StateAbortedError("grep '^%s' matched nothing" % prefix)
    return "\n".join(values)


def state_gateway_port() -> tuple[int, str]:
    """`account_state_gateway_port`, `.ci/lib/account.sh:65-68`. Returns (status, stdout).

    1 with nothing printed when the state file is absent, and 1 from grep, again with nothing printed, when it has no `gateway_port=` line.
    """
    path = account.state_file()
    if not os.path.isfile(path):
        return 1, ""
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="surrogateescape")
    try:
        value = grep_cut(text, "gateway_port")
    except account.StateAbortedError:
        return 1, ""
    return 0, value + "\n"


def cleanup(exit_code: int) -> int:
    """`account_cleanup`, `.ci/lib/account.sh:84-99`. Returns the code the twin `exit`s with.

    `kill -- -$pid || kill $pid`, then `wait "$pid"`, all silenced. THE GROUP FIRST: every job `spawn_background()` starts leads its own process group, so the signal reaches whatever the tracked pid started (the dev server behind `npx`) instead of orphaning it on its port. A pid that leads no group falls back to the pid alone.
    A child is then waited for; anything else is skipped, exactly as bash's `wait` refuses a pid that is not its child.
    """
    for pid in PIDS:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)
        proc = _PROCS.pop(pid, None)
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.wait()
    PIDS.clear()
    with contextlib.suppress(FileNotFoundError):
        os.remove(account.state_file())
    return exit_code


def docker_ghost_clean() -> int:
    """`account_docker_ghost_clean`, `.ci/lib/account.sh:207-214`. Always 0.

    `echo "$ids" | xargs docker rm -f`: xargs splits on whitespace and, being GNU xargs without `-r`, runs the command once even when that leaves no ids.
    """
    if shutil.which("docker") is None:
        return 0
    if _run(["docker", "info"], quiet_out=True, quiet_err=True) != 0:
        return 0
    _, ids = _capture(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "name=account-config-rustfs",
            "--filter",
            "name=rediacc-config-rustfs-dev",
        ],
        quiet_err=True,
    )
    if ids:
        _run(["docker", "rm", "-f", *ids.split()], quiet_out=True, quiet_err=True)
    return 0


# --------------------------------------------------------------------------- stripe ---------------------------------------------------------------------------


def stripe_auto() -> int:
    """`account_stripe_auto`, `.ci/lib/account.sh:257-319`. Always 0 unless errexit ends it.

    Starts `stripe listen` in the background, remembered in `PIDS` like every other job `account_dev` starts, and waits up to thirty one-second `sleep`s for its `whsec_` line; the secret is exported as `STRIPE_SANDBOX_WEBHOOK_SECRET`.
    """
    key = os.environ.get("STRIPE_SANDBOX_SECRET_KEY", "")
    if not key:
        return 0
    if shutil.which("stripe") is None:
        log.warn("STRIPE_SANDBOX_SECRET_KEY is set but stripe CLI not found")
        log.info("Install from: https://docs.stripe.com/stripe-cli")
        log.info("Continuing without webhook forwarding")
        return 0

    log.step("Setting up Stripe sandbox...")
    gateway_port = os.environ.get("GATEWAY_PORT", "")
    _, stale = _capture(
        ["pgrep", "-f", "stripe listen.*--forward-to http://localhost:%s/" % gateway_port],
        quiet_err=True,
    )
    if stale:
        log.info("Cleaning up stale stripe listen (PIDs: %s)" % stale)
        _run(["kill", *stale.split()], quiet_err=True)
        _sleep(1)

    log.info("Syncing Stripe products/prices...")
    _tail(
        ["npx", "tsx", "scripts/stripe-sync.ts"],
        5,
        cwd=account.account_dir(),
        extra_env={"STRIPE_SECRET_KEY": key},
    )

    fd, stripe_log = tempfile.mkstemp()
    os.close(fd)
    spawn_background(
        [
            "stripe",
            "listen",
            "--api-key",
            key,
            "--forward-to",
            "http://localhost:%s/account/api/v1/webhooks/stripe" % gateway_port,
        ],
        log_path=stripe_log,
    )

    secret = ""
    elapsed = 0
    while elapsed < 30:
        with contextlib.suppress(OSError):
            text = pathlib.Path(stripe_log).read_text(encoding="utf-8", errors="surrogateescape")
            secret = "\n".join(WEBHOOK_SECRET_RE.findall(text))
        if secret:
            break
        _sleep(1)
        elapsed += 1
    with contextlib.suppress(FileNotFoundError):
        os.remove(stripe_log)

    if not secret:
        log.warn("stripe listen did not output webhook secret within 30s")
        log.info("Stripe features may not work -- check stripe CLI auth")
        return 0
    os.environ["STRIPE_SANDBOX_WEBHOOK_SECRET"] = secret
    log.info("Stripe webhook forwarding active (secret: %s...)" % secret[:12])
    return 0


# --------------------------------------------------------------------------- dev logins ---------------------------------------------------------------------------


def js_truthy(value) -> bool:
    """JavaScript truthiness for a parsed JSON value: `[]` and `{}` are TRUE there and false in Python."""
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value != ""
    return True


def _refuse_constant(name: str):
    raise ValueError("JSON.parse has no %s" % name)


def seed_fields(body: str) -> tuple[str, str, str]:
    """The twin's `node -e` read of the seed-config-store answer, `.ci/lib/account.sh:567`.

    `d.existing?1:0`, `d.recoveryCode||""`, `d.totpSecret||""`. Raises `ErrexitError(1)` where node prints NOTHING, which is where the twin's first `read` hits end of file and errexit ends the job (defect 3): an answer that is not JSON, and `null`, whose `.existing` throws.
    """
    try:
        data = json.loads(body + "\n", parse_constant=_refuse_constant)
    except ValueError:
        raise ErrexitError(1, "node could not parse the seed answer") from None
    if data is None:
        raise ErrexitError(1, "null.existing throws in node")
    if not isinstance(data, dict):
        return "0", "", ""
    existing = "1" if js_truthy(data.get("existing")) else "0"
    recovery = data.get("recoveryCode")
    totp = data.get("totpSecret")
    return (
        existing,
        account.js_str(recovery) if js_truthy(recovery) else "",
        account.js_str(totp) if js_truthy(totp) else "",
    )


def _first_fields(text: str) -> str:
    """`awk '{print $1}'` over TEXT, then `$(...)`'s trailing-newline strip."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join((line.split() or [""])[0] for line in lines).rstrip("\n")


def _post(url: str, payload: str) -> bool:
    """`curl -sf -X POST URL -H 'Content-Type: application/json' -d PAYLOAD >/dev/null 2>&1`."""
    argv = ["curl", "-sf", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", payload]
    return _run(argv, quiet_out=True, quiet_err=True) == 0


def dev_credentials(gateway_port: str) -> int:
    """`account_dev_credentials`, `.ci/lib/account.sh:507-616`. 0 unless errexit ends it.

    Waits up to sixty two-second `sleep`s for the gateway's health route, provisions the three dev logins with fresh `openssl rand -hex 8` passwords through the dev-only `/test` routes, seeds the dev user's config store, and prints the credentials box.
    """
    base = "http://127.0.0.1:%s/account/api/v1" % gateway_port
    healthy = False
    for _ in range(60):
        health = ["curl", "-sf", "-m", "2", "http://127.0.0.1:%s/health" % gateway_port]
        if _run(health, quiet_out=True, quiet_err=True) == 0:
            healthy = True
            break
        _sleep(2)
    if not healthy:
        log.warn("Gateway not healthy after 120s; skipped dev login provisioning")
        return 0

    root_email = os.environ.get("ROOT_EMAIL") or DEFAULT_ROOT_EMAIL
    passwords = []
    for _ in range(3):
        status, value = _capture(["openssl", "rand", "-hex", "8"])
        if status != 0:
            raise ErrexitError(status, "openssl rand failed under errexit")
        passwords.append(value)
    root_pw, user_pw, partner_pw = passwords

    ok = True
    for email, password in (
        (root_email, root_pw),
        (DEV_USER_EMAIL, user_pw),
        (DEV_PARTNER_EMAIL, partner_pw),
    ):
        payload = '{"email":"%s","password":"%s"}' % (email, password)
        ok = _post(base + "/test/ensure-login", payload) and ok
    ok = (
        _post(
            base + "/test/ensure-subscription",
            '{"email":"%s","planCode":"PROFESSIONAL"}' % DEV_USER_EMAIL,
        )
        and ok
    )
    ok = _post(base + "/test/seed-demo-partner", '{"email":"%s"}' % DEV_PARTNER_EMAIL) and ok
    if not ok:
        log.warn("Dev login provisioning failed (see gateway log); logins may be stale")
        return 0

    _, seed_json = _capture(
        [
            "curl",
            "-sf",
            "-X",
            "POST",
            base + "/test/seed-config-store",
            "-H",
            "Content-Type: application/json",
            "-d",
            '{"email":"%s","password":"%s"}' % (DEV_USER_EMAIL, STORE_PASSWORD),
        ],
        quiet_err=True,
    )
    seed_existing = seed_recovery = seed_totp = ""
    if seed_json:
        seed_existing, seed_recovery, seed_totp = seed_fields(seed_json)

    rule = "─" * 65
    if seed_existing == "1":
        recovery_display = "issued on first seed (unchanged)"
    else:
        recovery_display = seed_recovery or "<unavailable>"

    status, hostnames = _capture(["hostname", "-I"], quiet_err=True)
    if status != 0:
        raise ErrexitError(status, "hostname -I failed inside a pipefail assignment")
    lan_ip = _first_fields(hostnames + "\n" if hostnames else "")

    rows = [
        "",
        "  ┌%s┐" % rule,
        account.banner_row("Dev logins (fresh passwords each start)"),
        "  ├%s┤" % rule,
        account.banner_row("root     %s %s" % (_pad_bytes(root_email, 32), root_pw)),
        account.banner_row("user     %s %s" % (_pad_bytes(DEV_USER_EMAIL, 32), user_pw)),
        account.banner_row("partner  %s %s" % (_pad_bytes(DEV_PARTNER_EMAIL, 32), partner_pw)),
        "  ├%s┤" % rule,
        account.banner_row("Portal:   http://localhost:%s/account/login" % gateway_port),
        account.banner_row("Console:  http://localhost:%s/account/console" % gateway_port),
    ]
    if lan_ip:
        rows.append(
            account.banner_row("Network:  http://%s:%s/account/login" % (lan_ip, gateway_port))
        )
        rows.append(account.banner_row("          (LAN reachable; no passkeys over LAN)"))
    rows += [
        "  ├%s┤" % rule,
        account.banner_row("Store password:  %s" % STORE_PASSWORD),
        account.banner_row("Recovery code:   %s" % recovery_display),
    ]
    if seed_totp:
        rows.append(account.banner_row("2FA code:        ./run.sh account totp"))
        rows.append(account.banner_row("2FA secret:      %s" % seed_totp))
    else:
        rows.append(account.banner_row("2FA:             config storage disabled (Docker needed)"))
    rows += [
        "  ├%s┤" % rule,
        account.banner_row("root    -> /account/admin    (operator)"),
        account.banner_row("partner -> /account/partner  (seeded demo data)"),
        account.banner_row("user    -> /account/console  (PROFESSIONAL + config store)"),
        "  └%s┘" % rule,
        "",
    ]
    sys.stdout.write("".join(r + "\n" for r in rows))
    sys.stdout.flush()
    return 0


# --------------------------------------------------------------------------- account dev ---------------------------------------------------------------------------


def _arith(value: str) -> int:
    """`$((value))` for the decimal a state file carries. Anything else is outside the differential; see the module docstring."""
    if not value.isdigit():
        raise ErrexitError(1, "non-numeric port %r in bash arithmetic" % value)
    return int(value)


def _stop_previous(state: str) -> None:
    """`.ci/lib/account.sh:330-360`: the previous instance from this worktree's state file."""
    text = pathlib.Path(state).read_text(encoding="utf-8", errors="surrogateescape")
    try:
        old_gateway = grep_cut(text, "gateway_port")
        old_pids = grep_cut(text, "pids")
    except account.StateAbortedError:
        raise ErrexitError(1, "a bare state-file assignment matched nothing") from None
    log.step("Stopping previous account instance (gateway:%s)..." % (old_gateway or "?"))
    for pid in old_pids.replace(",", " ").split():
        with contextlib.suppress(ValueError, OSError):
            os.kill(int(pid), signal.SIGTERM)
    if old_gateway:
        base = _arith(old_gateway)
        for offset in (0, 1, 2):
            _, port_pids = _capture(["lsof", "-ti:%d" % (base + offset)], quiet_err=True)
            if port_pids:
                _run(["kill", "-9", *port_pids.split()], quiet_err=True)
    _sleep(2)
    with contextlib.suppress(FileNotFoundError):
        os.remove(state)
    log.info("Previous instance stopped")


def _install_if_stale(directory: str, message: str, *, marker: str | None = None) -> None:
    """`[[ ! -d node_modules ]] || [[ lock -nt node_modules ]]` and then the tailed `npm install`."""
    modules = os.path.join(directory, "node_modules")
    stale = not os.path.isdir(modules)
    if not stale and marker is not None:
        stale = not os.path.isdir(os.path.join(modules, marker))
    if not stale:
        stale = _newer(os.path.join(directory, "package-lock.json"), modules)
    if stale:
        log.step(message)
        _tail(["npm", "install", "--prefer-offline", "--no-audit", "--no-fund"], 1, cwd=directory)


def _docker_usable() -> bool:
    """`command -v docker &>/dev/null && docker info &>/dev/null 2>&1`."""
    if shutil.which("docker") is None:
        return False
    return _run(["docker", "info"], quiet_out=True, quiet_err=True) == 0


def _start_rustfs() -> None:
    """`.ci/lib/account.sh:402-444`: reuse or start the config blob store, then export its coordinates."""
    if not _docker_usable():
        log.info("Docker not available -- config blob storage disabled")
        return
    log.step("Starting config blob storage (RustFS)...")
    rustfs_key = os.environ.get("CONFIG_R2_ACCESS_KEY_ID") or "configadmin"
    rustfs_secret = os.environ.get("CONFIG_R2_SECRET_ACCESS_KEY") or "configadmin"
    endpoint = "http://127.0.0.1:%d" % RUSTFS_PORT

    if account.rustfs_alive(RUSTFS_PORT):
        log.info("Reusing RustFS already serving on port %d" % RUSTFS_PORT)
    else:
        docker_ghost_clean()
        os.environ["CONFIG_RUSTFS_PORT"] = str(RUSTFS_PORT)
        directory = account.account_dir()
        with open(os.path.join(account.log_directory(), "rustfs.log"), "wb") as handle:
            message = local_common.cd_error(directory)
            if message is not None:
                handle.write((message + "\n").encode())
            else:
                _flush()
                with contextlib.suppress(FileNotFoundError):
                    subprocess.run(
                        ["docker", "compose", "up", "-d", "config-rustfs", "config-rustfs-init"],
                        cwd=directory,
                        stdout=handle,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
        account.wait_port(RUSTFS_PORT, "RustFS", 30, sleep=_sleep)

    if account.rustfs_alive(RUSTFS_PORT):
        os.environ["CONFIG_R2_ENDPOINT"] = endpoint
        os.environ["CONFIG_R2_BUCKET"] = "rediacc-configs"
        os.environ["CONFIG_R2_ACCESS_KEY_ID"] = rustfs_key
        os.environ["CONFIG_R2_SECRET_ACCESS_KEY"] = rustfs_secret
        _run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "host",
                "-e",
                "AWS_ACCESS_KEY_ID=%s" % rustfs_key,
                "-e",
                "AWS_SECRET_ACCESS_KEY=%s" % rustfs_secret,
                "-e",
                "AWS_DEFAULT_REGION=us-east-1",
                "amazon/aws-cli",
                "s3api",
                "create-bucket",
                "--bucket",
                "rediacc-configs",
                "--endpoint-url",
                endpoint,
            ],
            quiet_out=True,
            quiet_err=True,
        )
        log.info("Config blob storage: %s/rediacc-configs" % endpoint)
    else:
        log.warn(RUSTFS_GHOST_HINT)


def _fork_credentials(gateway_port: str) -> None:
    """`account_dev_credentials "$GATEWAY_PORT" &`: a forked copy of this process, NOT remembered in `PIDS`, exactly as the twin leaves it out of `ACCOUNT_PIDS`."""
    _flush()
    if os.fork() != 0:
        return
    code = 1
    try:
        code = dev_credentials(gateway_port)
    except DEATHS as exc:
        code = code_of(exc)
    finally:
        # Whatever ended the job, the fork never returns into the parent's code path.
        _flush()
        os._exit(code)


def _serve(gateway_port: int, vite_port: int, astro_port: int) -> int:
    """`.ci/lib/account.sh:446-499`: everything after the trap is armed. Returns the gateway's status, or dies."""
    os.makedirs(account.log_directory(), exist_ok=True)
    _start_rustfs()

    dev_bind = os.environ.get("REDIACC_DEV_BIND") or "127.0.0.1"
    root = account.console_root()
    log_dir = account.log_directory()
    log.step("Starting Astro dev server on :%d..." % astro_port)
    astro_pid = spawn_background(
        ["npx", "astro", "dev", "--port", str(astro_port), "--host", dev_bind],
        cwd=os.path.join(root, "packages", "www"),
        log_path=os.path.join(log_dir, "astro.log"),
    )
    log.step("Starting Vite dev server on :%d..." % vite_port)
    vite_pid = spawn_background(
        ["npx", "vite", "--port", str(vite_port), "--host", dev_bind],
        cwd=os.path.join(account.account_dir(), "web"),
        log_path=os.path.join(log_dir, "vite.log"),
    )
    if not account.wait_port(astro_port, "Astro", 90, astro_pid, sleep=_sleep):
        raise ErrexitError(1, "Astro did not start")
    if not account.wait_port(vite_port, "Vite", 60, vite_pid, sleep=_sleep):
        raise ErrexitError(1, "Vite did not start")

    stripe_auto()

    _, started = _capture(["date", "+%s"])
    lines = [
        "gateway_port=%d" % gateway_port,
        # Twin behaviour 7: SPACES, not the commas the substitution was written for.
        "pids=%s" % " ".join(str(p) for p in PIDS),
        "worktree=%s" % root,
        "started=%s" % started,
    ]
    pathlib.Path(account.state_file()).write_text(
        "".join(x + "\n" for x in lines), encoding="utf-8"
    )

    _fork_credentials(str(gateway_port))

    log.step("Starting dev gateway on :%d..." % gateway_port)
    directory = account.account_dir()
    _cd_or_die(directory)
    status = _run(
        ["npx", "tsx", "src/entry/dev-gateway.ts"],
        cwd=directory,
        extra_env={
            "GATEWAY_PORT": str(gateway_port),
            "VITE_PORT": str(vite_port),
            "ASTRO_PORT": str(astro_port),
            "CONFIG_R2_ENDPOINT": os.environ.get("CONFIG_R2_ENDPOINT", ""),
            "CONFIG_R2_BUCKET": os.environ.get("CONFIG_R2_BUCKET", ""),
            "CONFIG_R2_ACCESS_KEY_ID": os.environ.get("CONFIG_R2_ACCESS_KEY_ID", ""),
            "CONFIG_R2_SECRET_ACCESS_KEY": os.environ.get("CONFIG_R2_SECRET_ACCESS_KEY", ""),
            "WEBAUTHN_RP_ID": "localhost",
            "WEBAUTHN_ORIGIN": "http://localhost:%d" % gateway_port,
        },
    )
    if status != 0:
        raise ErrexitError(status, "the dev gateway exited %d" % status)
    return 0


def _on_signal(signum, _frame) -> None:
    raise ErrexitError(128 + signum, "signal %d" % signum)


def dev() -> int:
    """`account_dev`, `.ci/lib/account.sh:325-500`. Returns the exit status the twin's process ends with.

    FIRST `bws_exec("account-dev", ...)`: outside a hydrated profile this does not return, it re-runs `./run.sh account dev` under `bws_env exec`.

    FROM THE TRAP ON, EVERY EXIT RUNS `cleanup()`. The twin arms `trap account_cleanup EXIT INT TERM` after the shared packages are built, so a death before that point just ends the process, and every exit after it (a normal return included, because the process then exits) kills the remembered jobs and removes the state file.
    """
    account.bws_exec("account-dev", ["account", "dev"])
    _check_node()

    state = account.state_file()
    if os.path.isfile(state):
        _stop_previous(state)

    log.step("Starting account development environment")
    gateway_port, vite_port, astro_port = account.allocate_ports()
    os.environ["GATEWAY_PORT"] = str(gateway_port)
    os.environ["VITE_PORT"] = str(vite_port)
    os.environ["ASTRO_PORT"] = str(astro_port)
    log.info("Ports: gateway=%d vite=%d astro=%d" % (gateway_port, vite_port, astro_port))

    if load_defaults() != 0:
        return 1
    local_common.ensure_deps()

    directory = account.account_dir()
    _install_if_stale(directory, "Installing account dependencies...")
    _install_if_stale(
        os.path.join(directory, "web"),
        "Installing account web dependencies...",
        marker="react-router-dom",
    )
    local_common.ensure_packages_built()

    previous = {sig: signal.signal(sig, _on_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
    code = 0
    try:
        code = _serve(gateway_port, vite_port, astro_port)
    except DEATHS as exc:
        code = code_of(exc)
    except BaseException:
        # Not a death the twin has a spelling for: the trap still runs, and the defect still surfaces.
        cleanup(1)
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return cleanup(code)


# --------------------------------------------------------------------------- tests ---------------------------------------------------------------------------


def test(args: list[str]) -> int:
    """`account_test`, `.ci/lib/account.sh:708-715`: vitest in `private/account`, its status as the process's."""
    _check_node()
    local_common.ensure_packages_built()
    log.step("Running account tests")
    directory = account.account_dir()
    _cd_or_die(directory)
    status = _run(["npx", "vitest", "run", *args], cwd=directory)
    if status != 0:
        raise ErrexitError(status, "vitest exited %d" % status)
    return 0


def server_ports(server: str) -> str:
    """`echo "$SERVER" | grep -oP ':\\K[0-9]+' || echo ""`: every `:digits` run, one per line, as `$(...)` keeps them."""
    return "\n".join(re.findall(r":([0-9]+)", server))


def test_e2e(args: list[str]) -> int:
    """`account_test_e2e`, `.ci/lib/account.sh:717-782`. Playwright against the RUNNING dev gateway.

    The gateway port comes from an exported `GATEWAY_PORT`, then an exported `REDIACC_ACCOUNT_SERVER`, then this worktree's `.account-state`; the shell wins over `dev.defaults.env` as everywhere else.
    """
    account.bws_exec("account-e2e", ["account", "test", "e2e", *args])
    _check_node()
    if load_defaults() != 0:
        return 1

    gateway_port = os.environ.get("GATEWAY_PORT", "")
    if not gateway_port:
        gateway_port = server_ports(os.environ.get("REDIACC_ACCOUNT_SERVER", ""))
    if not gateway_port:
        status, out = state_gateway_port()
        gateway_port = out.rstrip("\n") if status == 0 else ""
    if not gateway_port:
        log.error("Cannot determine gateway port")
        log.info("Start the dev gateway first: ./run.sh account dev")
        raise ErrexitError(1, "no gateway port")

    try:
        running = ports.is_port_in_use(int(gateway_port))
    except ValueError:
        running = False
    if not running:
        log.error("Dev gateway not running on port %s" % gateway_port)
        log.info("Start it first: ./run.sh account dev")
        raise ErrexitError(1, "gateway not running")

    os.environ["E2E_PORT"] = gateway_port
    os.environ["E2E_BASE_URL"] = "http://localhost:%s/account/" % gateway_port
    os.environ["ROOT_EMAIL"] = os.environ.get("ROOT_EMAIL", "")

    webhook = os.environ.get("STRIPE_E2E_WEBHOOK_SECRET", "")
    if webhook:
        os.environ["E2E_WEBHOOK_SECRET"] = webhook
        log.info("Webhook simulation: enabled (STRIPE_E2E_WEBHOOK_SECRET)")
    else:
        log.warn("Webhook simulation: disabled (STRIPE_E2E_WEBHOOK_SECRET not set)")
    if os.environ.get("STRIPE_SANDBOX_SECRET_KEY", ""):
        log.info("Stripe sandbox E2E: enabled")
    else:
        log.warn("Stripe sandbox E2E: disabled (STRIPE_SANDBOX_SECRET_KEY not set)")

    local_common.ensure_packages_built()

    e2e_dir = os.path.join(account.account_dir(), "e2e")
    _install_if_stale(e2e_dir, "Installing E2E dependencies...")

    log.step("Running account E2E tests (gateway on :%s)" % gateway_port)
    _cd_or_die(e2e_dir)
    status = _run(
        ["npx", "playwright", "test", "--project=chromium", "--reporter=list", *args], cwd=e2e_dir
    )
    if status != 0:
        raise ErrexitError(status, "playwright exited %d" % status)
    return 0


# --------------------------------------------------------------------------- reset ---------------------------------------------------------------------------


def _bws(verb: str, *args: str, extra_env: dict[str, str] | None = None) -> int:
    """`PYTHONPATH="$ACCOUNT_CI_DIR..." python3 -m rediacc_ci.core.bws_env VERB ARGS...`, as a PROGRAM like the twin's, so the secrets it pushes live in that child's environment and nowhere else."""
    existing = os.environ.get("PYTHONPATH", "")
    pythonpath = account.ci_dir() + (":" + existing if existing else "")
    return _run(
        ["python3", "-m", "rediacc_ci.core.bws_env", verb, *args],
        extra_env={**(extra_env or {}), "PYTHONPATH": pythonpath},
    )


def reset() -> int:
    """`account_reset`, `.ci/lib/account.sh:784-836`.

    Mints a fresh DEV keypair and session secrets, pushes them to the six `ACCOUNT_*_DEV` Bitwarden entries, refreshes this machine's public-key cache, and deletes the dev database. A failed push is a refusal BEFORE anything is deleted.
    """
    _check_node()
    log.step("Resetting account development environment")
    log.info("Generating a fresh DEV keypair and session secrets...")
    keys = account.generate_crypto_keys(strict=True)
    pushed = _bws(
        "store-from-env",
        *RESET_STORE_SPECS,
        extra_env={
            "ACCOUNT_ED25519_PRIVATE_KEY": keys.ed25519_priv,
            "ACCOUNT_ED25519_PUBLIC_KEY": keys.ed25519_pub,
            "ACCOUNT_X25519_PRIVATE_KEY": keys.x25519_priv,
            "ACCOUNT_X25519_PUBLIC_KEY": keys.x25519_pub,
            "ACCOUNT_JWT_SECRET": keys.jwt,
            "ACCOUNT_SERVER_API_KEY": keys.api_key,
        },
    )
    del keys
    if pushed != 0:
        log.error("Pushing the DEV keys to Bitwarden failed; the database was NOT reset")
        raise ErrexitError(1, "store-from-env failed")

    directory = account.account_dir()
    os.makedirs(os.path.join(directory, ".cache"), exist_ok=True)
    if (
        _bws("cache-to", os.path.join(directory, ".cache", "public-keys.env"), *RESET_CACHE_SPECS)
        != 0
    ):
        log.warn("Could not refresh the public-key cache; run ./run.sh setup")
    log.warn("The DEV keys are shared: every machine's dev database holds licences")
    log.warn("signed by the OLD key, and every OTHER machine's cached public key is now stale.")
    log.warn("On each of them: ./run.sh setup")

    db_path = os.path.join(directory, "account.db")
    for path in (db_path, db_path + "-shm", db_path + "-wal", db_path + "-journal"):
        if os.path.isfile(path):
            log.info("Removing %s" % os.path.basename(path))
            with contextlib.suppress(FileNotFoundError):
                os.remove(path)

    print()
    log.info("Account reset complete!")
    log.info("")
    log.info("Start dev server with: ./run.sh account dev")
    return 0


# --------------------------------------------------------------------------- seed-demo ---------------------------------------------------------------------------


def _usage_refusal(message: str) -> None:
    log.error(message)
    print(SEED_USAGE)
    raise ErrexitError(1, message)


def parse_seed_args(args: list[str]) -> tuple[str, str]:
    """`account_seed_demo`'s option loop, `.ci/lib/account.sh:844-876`. Returns (email, port)."""
    email = port = ""
    rest = list(args)
    while rest:
        arg = rest[0]
        if arg == "--port":
            if len(rest) < 2:
                # `port="$2"` under `set -u` with no `$2`: bash's own diagnostic, and the shell ends with 1.
                sys.stderr.write("$2: unbound variable\n")
                raise ErrexitError(1, "--port without a value")
            port = rest[1]
            rest = rest[2:]
        elif arg.startswith("--port="):
            port = arg.split("=", 1)[1]
            rest = rest[1:]
        elif arg.startswith("-"):
            _usage_refusal("Unknown option: %s" % arg)
        else:
            if email:
                _usage_refusal("Unexpected argument: %s" % arg)
            email = arg
            rest = rest[1:]
    if not email:
        _usage_refusal("Missing email")
    return email, port


def _pretty(body: str) -> None:
    """`echo "$body" | jq . 2>/dev/null || echo "$body"`, jq's stdout inherited, exactly as the twin runs it."""
    _flush()
    try:
        status = subprocess.run(
            ["jq", "."],
            input=(body + "\n").encode("utf-8", "surrogateescape"),
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
    except FileNotFoundError:
        status = 127
    if status != 0:
        print(body)


def seed_demo(args: list[str]) -> int:
    """`account_seed_demo`, `.ci/lib/account.sh:842-913`. A demo partner org against the running dev gateway.

    The port is `--port`, else the state file's (a bare assignment, so a state file without the key is a silent death), else `ACCOUNT_DEV_PORT_PREFERRED`.
    """
    email, port = parse_seed_args(args)
    state = account.state_file()
    if not port and os.path.isfile(state):
        text = pathlib.Path(state).read_text(encoding="utf-8", errors="surrogateescape")
        try:
            port = grep_cut(text, "gateway_port")
        except account.StateAbortedError:
            raise ErrexitError(1, "a bare state-file assignment matched nothing") from None
    port = port or str(account.ACCOUNT_DEV_PORT_PREFERRED)

    url = "http://127.0.0.1:%s/account/api/v1/test/seed-demo-partner" % port
    log.step("Seeding demo partner '%s' via %s" % (email, url))

    status, payload = _capture(["jq", "-n", "--arg", "email", email, "{email: $email}"])
    if status != 0:
        raise ErrexitError(status, "jq failed under errexit")
    status, body = _capture(
        [
            "curl",
            "-sS",
            "-m",
            "60",
            "-w",
            "\n%{http_code}",
            "-H",
            "Content-Type: application/json",
            "-d",
            payload,
            url,
        ]
    )
    if status != 0:
        # Defect 1: the twin's "Could not reach" branch is unreachable, because this assignment is where errexit ends it.
        raise ErrexitError(status, "curl failed under errexit")
    http_code = body.rsplit("\n", 1)[-1]
    body = body.rsplit("\n", 1)[0]

    if http_code != "200":
        log.error("Seed failed (HTTP %s)" % http_code)
        _pretty(body)
        log.info("Is the dev gateway running? Start it with: ./run.sh account dev")
        raise ErrexitError(1, "seed failed")
    log.info("Demo partner seeded")
    _pretty(body)
    return 0


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------

USAGE = """rediacc_ci.core.account_lifecycle -- the side-effecting half of .ci/lib/account.sh

  dev                 start the account dev stack (gateway + portal + www)
  test [args]         run the account vitest suite
  test e2e [args]     run the account Playwright suite against the running gateway
  reset               fresh DEV keys to Bitwarden, then delete the dev database
  seed-demo <email> [--port N]
                      seed a demo partner org through the running gateway

The twin, .ci/lib/account.sh, is still what ./run.sh dispatches to."""


def main(argv: list[str]) -> int:
    """The `account` verbs this half covers, dispatched the way `.ci/legacy/run-legacy.sh:403-435` dispatches them."""
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if argv else 2
    verb, rest = argv[0], argv[1:]
    try:
        if verb == "dev":
            return dev()
        if verb == "test":
            if rest[:1] == ["e2e"]:
                return test_e2e(rest[1:])
            return test(rest)
        if verb == "reset":
            return reset()
        if verb == "seed-demo":
            return seed_demo(rest)
    except DEATHS as exc:
        return code_of(exc)
    log.error("Unknown account command: %s" % verb)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
