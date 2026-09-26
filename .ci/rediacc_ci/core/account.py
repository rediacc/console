"""The DETERMINISTIC half of `.ci/lib/account.sh`, ported function for function -- plus three more, `account_stop`, `account_rotation` and `account_bws_exec`, proved a different way. See below.

PORTED FROM `.ci/lib/account.sh` (1046 lines, 21 functions). The twin still exists, is untouched by this file, and stays sourced at `.ci/legacy/run-legacy.sh:405` (the `account` verb) and `:443` (the `rotation` verb). Nothing is cut over here.
This is a pre-cutover port on the same sequencing every other lib in this campaign used, and `.ci/lib/service.sh` is the worked precedent: its port `rediacc_ci/core/service.py` has carried a K=5 ledger since 2026-09-10 while `run-legacy.sh:48` still sources the bash.

--------------------------------------------------------------------------
WHAT IS HERE AND WHAT IS DELIBERATELY ABSENT
--------------------------------------------------------------------------
SEVEN FUNCTIONS ARE PORTED AND SHADOW-DIFFERENTIALLY PROVED, and they are the ones whose whole answer is computation or a file read: `account_allocate_ports`, `account_wait_port`, `account_rustfs_alive`, `account_generate_crypto_keys`, `account_banner_row`, `account_totp`, and the decidable half of `account_db`. `shadow_driver.py`'s four scenarios drive these against the live twin.

THERE IS NO `.env` WRITER HERE ANY MORE. The twin's four (`account_generate_fresh_env`, `account_env_add_if_missing`, `account_ensure_env_keys`, `account_ensure_env`) were deleted from BOTH sides when `private/account/.env` was retired (`agent/plans/PLAN-account-env-to-bws.md`): secrets reach `account_dev` through `bws_env exec`, and the non-secret constants come from the committed `private/account/dev.defaults.env`.
The ledger rows for the `env` and `fresh-env` scenarios in `.ci/shadow/w7p5b-account.observations.jsonl` are history about functions that no longer exist on either side. `mint_dev_keys()` below is new rather than ported: it has no twin, and its tests prove it directly.

THREE MORE ARE PORTED, `account_stop`, `account_rotation` and `account_bws_exec`, but proved by a REAL RUN instead of a shadow differential, because all three genuinely start and stop real infrastructure: `stop()` kills tracked dev pids and tears down real Docker containers, and `rotation()` dispatches to a real TypeScript CLI (`private/account/scripts/rotation/`) that mints and deletes real credentials at AWS IAM and Cloudflare, and pushes them to Bitwarden Secrets Manager (see `private/account/CLAUDE.md`, "Secret Rotation").
`bws_exec()` re-executes `./run.sh` under `bws_env exec`, which reads the live Bitwarden store; it is reached through `rotation()`, exactly as the twin reaches it.
An input/output differential compares two ANSWERS; these produce SIDE EFFECTS, so `test_core_account.py` instead drives each one for real -- `stop()` against a real tracked process and a real (sandboxed, compose-file-less) Docker daemon, confirmed by process and port checks rather than by exit code alone; `rotation()` only through the manifest-only, credential-free subcommands it shares with the twin (`list`, `status`, `history`).
`rotate`/`check`/`deactivate`/`delete`/`sweep`/`init` need live production credentials and are never invoked, by anything, from this port or its tests. None of the three joins `PORTED_FUNCTIONS` in `shadow_driver.py`'s sense: that module's own docstring still lists them under "WHAT IS NEVER DRIVEN HERE", and that is correct -- the differential technique genuinely does not apply to them.
`test_core_account.py`'s `PORTED_FUNCTIONS`/`NOT_PORTED_FUNCTIONS` tuple is the one that moved.

THE OTHER ELEVEN ARE IN `rediacc_ci.core.account_lifecycle`, not here: `account_dev`, `account_dev_credentials`, `account_stripe_auto`, `account_cleanup`, `account_docker_ghost_clean`, `account_test`, `account_test_e2e`, `account_reset`, `account_seed_demo`, `account_load_defaults` and `account_state_gateway_port`.
Each of them starts, stops or talks to real infrastructure (Docker, RustFS, a Vite and an Astro server, a foreground gateway, `stripe listen`, Bitwarden), so they are proved by a STUB-FARM TRANSCRIPT differential instead (`core/account_lifecycle_shadow_driver.py`, pair `w7p5b-account-lifecycle`), which compares the ordered calls each side makes to a directory of scripted programs rather than two runs of a live stack.
`stop()` below still inlines `account_docker_ghost_clean` rather than calling the lifecycle module's `docker_ghost_clean()`, because `stop()` is real-run verified against its own inlined body and that proof would not transfer. `gateway_port_from_state()` below is `account_totp`'s and `account_stop`'s INLINE pipeline; `account_state_gateway_port`, the named helper, is the lifecycle module's.

`account_db`'s LAUNCH is grouped with the eleven even though the function as a whole is ported. Everything up to the launch, meaning argument parsing, the database path, the devbox-derived preferred port, the free-port search, the two refusals and the `sqlite_web` resolution, is decided in `db_plan()` and is what the differential drives.
`db_launch()` below execs a server and is NOT differentially proved; it is written out so the port is complete, and it is named here so nobody reads its green as evidence.

--------------------------------------------------------------------------
TWO FUNCTIONS THE TWIN BORROWS FROM ITS SOURCER
--------------------------------------------------------------------------
`check_node_version` is called at `.ci/lib/account.sh:958` and defined at `.ci/lib/local-common.sh:391`, the file `run-legacy.sh` sources BEFORE `account.sh`. It is IMPORTED from `rediacc_ci.core.local_common`, the port of that file, which carries the twin's own `sort -V` comparator. This module used to carry a second copy with a simpler `version_tuple` compare, pinned to the first by a test; the copy is deleted, so there is one Python implementation of one bash function.
`devbox_state_get` is called at `:1004` and defined at `.ci/lib/devbox.sh:124`, which `account_db` sources on demand. It is re-implemented below rather than imported, because `rediacc_ci.core.devbox` builds a whole `Devbox` context to answer it and this reader needs one key; `test_core_account.py` compares the two against the live bash.

--------------------------------------------------------------------------
FIVE TWIN BEHAVIOURS REPRODUCED ON PURPOSE, NOT FIXED
--------------------------------------------------------------------------
  1. `account_totp` DIES SILENTLY on a state file with no `gateway_port=` line. `gateway_port=$(grep "^gateway_port=" ... | cut -d= -f2)` is a BARE ASSIGNMENT, so it takes the pipeline's status; grep matching nothing exits 1; every sourcer of this file has `pipefail` and `errexit` armed.
  The function stops there, prints NOTHING, and returns 1, so the "Could not read gateway port" message two lines below is reachable ONLY when the line exists with an empty value. Measured 2026-09-23 against the live twin. `gateway_port_from_state()` raises `StateAbortedError` where the twin dies, and `totp()` maps it to the same silent exit 1.
  2. `account_banner_row` PADS BY BYTES. `printf '%-63s'` counts bytes, so a multibyte glyph shortens the visible field and shifts the closing bar left. The twin's own comment at `:570-572` says the content is kept ASCII for exactly this reason.
  `banner_row()` pads by bytes, not by characters, so a caller that ever passes a non-ASCII string gets the twin's broken box rather than a quietly different one.
  3. `cut -d= -f2` TAKES THE SECOND FIELD ONLY, so a state value containing `=` is truncated. Preserved in `gateway_port_from_state()`.
  4. `account_db`'s `--studio` arm still parses the REST of the argument list before acting, so `account db --studio --bogus` refuses with exit 2 rather than starting Drizzle. Preserved in `parse_db_args()`.
  5. `account_stop` DIES THE SAME SILENT WAY, TWICE. Both `old_gateway=$(grep "^gateway_port=" ... | cut ...)` and `old_pids=$(grep "^pids=" ... | cut ...)` are the same bare, non-`local` pipeline as defect 1.
  A state file that EXISTS but is missing either key kills the function under errexit before Docker teardown or `rm -f "$ACCOUNT_STATE_FILE"` ever run, leaving stale containers and a stale state file behind. Measured 2026-09-23 against a live bash reproduction (`set -euo pipefail`, a hand-crafted state file carrying only the other key).
  `stop()` reproduces both dead ends: `gateway_port_from_state()`/`state_pids()` each raise `StateAbortedError` and `stop()` returns 1 having done nothing further, same as the twin.

--------------------------------------------------------------------------
WHY THE LOGGER IS `rediacc_ci.log`
--------------------------------------------------------------------------
`log_error` / `log_info` / `log_warn` / `log_step` / `log_debug` here are `.ci/scripts/lib/common.sh:35-55`, and `rediacc_ci.log` is already the byte-exact port of those five, tty gating included. The twin writes all five to STDERR; so does this.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time

from rediacc_ci import log, paths
from rediacc_ci.core import local_common, ports

# `.ci/config/constants.sh:117-120` and `:135,145`. Plain readonly assignments derived from CONSOLE_ROOT_DIR, so they are derived here the same way rather than read from the environment: constants.sh overwrites any inherited value, and a port that honoured an override would answer a question the twin cannot be asked.
ACCOUNT_DEV_PORT_PREFERRED = 4800
ACCOUNT_DEV_PORT_RANGE_END = 5799
DEVBOX_OFFSET_STUDIO = 3

# `.ci/lib/account.sh:977`. The devbox slot is preferred and then stepped aside from; this is the fallback when no `.devbox-state` exists.
DB_BROWSER_PREFERRED = 4983
DB_BROWSER_SCAN_SPAN = 40

# `.ci/lib/account.sh:628`.
DEFAULT_TOTP_EMAIL = "dev-user@rediacc.io"

# The six environment names the account server reads its DEV keypair and session secrets under, the six `account_reset` pushes to Bitwarden (`.ci/lib/account.sh:794-799`). `mint_dev_keys()` writes exactly these, in this order.
CRYPTO_KEYS = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_JWT_SECRET",
)


class AccountError(RuntimeError):
    """A refusal the twin reports and then exits on."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class StateAbortedError(RuntimeError):
    """Where the twin's bare assignment takes errexit down. See defect 1."""


# --------------------------------------------------------------------------- paths ---------------------------------------------------------------------------


def console_root(env: dict[str, str] | None = None) -> str:
    """`CONSOLE_ROOT_DIR`, the single seam both implementations read.

    `constants.sh:76` honours an inherited value and otherwise derives the repository root from its own location, which is what `paths.repo_root()` already answers for the Python side.
    """
    environ = os.environ if env is None else env
    value = environ.get("CONSOLE_ROOT_DIR", "")
    return value or str(paths.repo_root())


def account_dir(env: dict[str, str] | None = None) -> str:
    """`.ci/lib/account.sh:38`."""
    return os.path.join(console_root(env), "private", "account")


def state_file(env: dict[str, str] | None = None) -> str:
    """`constants.sh:119`."""
    return os.path.join(console_root(env), ".account-state")


def log_directory(env: dict[str, str] | None = None) -> str:
    """`constants.sh:120`."""
    return os.path.join(console_root(env), ".account-logs")


def devbox_state_file(env: dict[str, str] | None = None) -> str:
    """`constants.sh:135`."""
    return os.path.join(console_root(env), ".devbox-state")


# --------------------------------------------------------------------------- borrowed from the sourcer ---------------------------------------------------------------------------


def node_version_ok() -> int:
    """A bare `check_node_version` (`rediacc_ci.core.local_common`), as the status errexit would end the caller with: 0 to carry on.

    `local_common.check_node_version` returns False where the twin returns 1 and raises `LocalCommonError` where a failing `node -v` kills it through pipefail; both are the caller's death.
    """
    try:
        return 0 if local_common.check_node_version() else 1
    except local_common.LocalCommonError as exc:
        return exc.code


def devbox_state_get(key: str, env: dict[str, str] | None = None) -> str | None:
    """`.ci/lib/devbox.sh:124-128`, which `account_db` sources on demand.

    `sed -n "s/^${key}=//p" | head -1` takes the FIRST matching line, value only. None where the twin returns 1, which is only the missing-state-file case: `sed` printing nothing still exits 0, so a state file without the key leaves the twin's capture EMPTY rather than failed, and the caller's `[[ -n "$base" ]]` is what rejects it.
    """
    path = devbox_state_file(env)
    if not os.path.isfile(path):
        return None
    prefix = key + "="
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith(prefix):
                return line[len(prefix) :].rstrip("\n")
    return ""


# --------------------------------------------------------------------------- ports ---------------------------------------------------------------------------


def allocate_ports(env: dict[str, str] | None = None) -> tuple[int, int, int]:
    """`account_allocate_ports`, `.ci/lib/account.sh:82-129`.

    Returns `(GATEWAY_PORT, VITE_PORT, ASTRO_PORT)`. Raises `AccountError` with code 1 where the twin calls `exit 1`.

    THE PINNED BRANCH IS NOT AN OPTIMISATION. Inside the devbox the reverse proxy routes to these ports through STATIC container labels, so drifting to the next free triple turns into a 502 that blames the backend.
    A container is an isolated network namespace with nothing to collide with, so a port that IS busy in there means a leftover process, and that is surfaced rather than routed around.
    """
    environ = os.environ if env is None else env
    pinned = environ.get("REDIACC_DEV_PORT_BASE", "")
    if pinned:
        base = int(pinned)
        for offset in (0, 1, 2):
            if ports.is_port_in_use(base + offset):
                log.error("Port %d is already in use inside this environment" % (base + offset))
                log.info(
                    "REDIACC_DEV_PORT_BASE pins the ports so the proxy labels stay valid; free it rather than drifting"
                )
                log.info(
                    "Leftovers: pkill -f 'astro dev'; pkill -f 'vite --port'; pkill -f dev-gateway.ts"
                )
                raise AccountError("pinned port %d busy" % (base + offset), code=1)
        return base, base + 1, base + 2

    found = ports.find_consecutive_free_ports(
        3, ACCOUNT_DEV_PORT_PREFERRED, ACCOUNT_DEV_PORT_RANGE_END
    )
    if found is None:
        log.error(
            "Cannot find 3 consecutive free ports in range %d-%d"
            % (ACCOUNT_DEV_PORT_PREFERRED, ACCOUNT_DEV_PORT_RANGE_END)
        )
        raise AccountError("no consecutive free ports", code=1)
    return found, found + 1, found + 2


def wait_port(
    port: int,
    name: str,
    timeout: int | None = None,
    watch_pid: int | None = None,
    env: dict[str, str] | None = None,
    sleep=time.sleep,
) -> bool:
    """`account_wait_port`, `.ci/lib/account.sh:143-177`. True where the twin returns 0.

    THE TIMEOUT IS A FLOOR, NOT A VERDICT. While the watched process is alive the wait continues past the budget, saying so ONCE, because a fixed ceiling produces a false failure on slow hardware: an arm64 Crostini box took 114.8s on an Astro content sync against a 90s wait, and `account dev` reported "Astro failed to start" about a server that came up seconds later.
    """
    environ = os.environ if env is None else env
    if timeout is None:
        timeout = int(environ.get("REDIACC_STARTUP_TIMEOUT", "30"))
    elapsed = 0
    announced = False
    while True:
        if ports.is_port_in_use(port):
            return True
        if elapsed >= timeout:
            if watch_pid is not None and pid_alive(watch_pid):
                if not announced:
                    log.warn(
                        "%s is slower than %ds on this machine; still starting (pid %d)"
                        % (name, timeout, watch_pid)
                    )
                    log.info("Set REDIACC_STARTUP_TIMEOUT to raise the initial budget")
                    announced = True
            else:
                log.error("%s failed to start on port %d within %ds" % (name, port, timeout))
                if watch_pid is not None:
                    log.error("its process (pid %d) is no longer running" % watch_pid)
                log.info("Check logs: %s/" % log_directory(env))
                return False
        sleep(1)
        elapsed += 1


def pid_alive(pid: int) -> bool:
    """`kill -0 "$pid" 2>/dev/null`."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def rustfs_alive(port: int) -> bool:
    """`account_rustfs_alive`, `.ci/lib/account.sh:196-201`.

    RustFS answers 403 on `GET /`, so ANY http status means alive; a closed port yields curl's `000`.

    DO NOT ADD A `|| echo 000` FALLBACK, which is what the twin's comment spends thirteen lines on. curl ALREADY prints `000` on a refused connection and exits non-zero, so the fallback appended a second one, the captured value became `000000`, that is not equal to `000`, and this reported ALIVE for a dead port.
    `account_dev` then logged "Reusing RustFS already serving", never started the container, still exported `CONFIG_R2_*`, and the gateway advertised a config store that answered ECONNREFUSED on first use.
    """
    # `|| true`: the exit status is discarded on both sides, the BODY decides.
    code = curl_body(
        [
            "curl",
            "-s",
            "-o",
            "/dev/null",
            "-m",
            "2",
            "-w",
            "%{http_code}",
            "http://127.0.0.1:%d/" % port,
        ]
    )
    return code not in {"", "000"}


def curl_body(argv: list[str]) -> str:
    """`$(curl ... || true)`, including the case where curl is NOT INSTALLED.

    MEASURED 2026-09-23 WITH CURL OFF PATH, because the port raised where the twin degraded. The twin's `|| true` swallows bash's own `curl: command not found`, leaves the capture EMPTY, and `account_rustfs_alive` returns 1; the port called `subprocess.run` and died with `FileNotFoundError`, which is a traceback in place of a verdict.

    THE VERDICT IS EQUIVALENT AND THE TEXT IS NOT, which is the same trade `rediacc_ci/dev/shadow_driver.py` records for its `no-npm` scenario. Bash reports a missing command as `<file>: line <n>: curl: command not found`, and a line number inside `account.sh` is neither reproducible by a port nor worth reproducing, so this is silent and only the empty body is preserved.

    STDOUT IS THE WHOLE ANSWER, and the exit status is deliberately discarded. That is what `$(curl ... || true)` does at both call sites: `-s` with `-w '%{http_code}'` prints `000` on a refused connection, and `-sf` prints NOTHING on any failure, so an empty capture already means failure in both shapes and a second test on the return code would be a rule the twin does not have.
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except (FileNotFoundError, PermissionError):
        return ""
    return proc.stdout


# --------------------------------------------------------------------------- crypto ---------------------------------------------------------------------------

# `.ci/lib/account.sh:226-244`, verbatim apart from the curve name. Kept as node rather than re-derived with a Python crypto library: the DER/pkcs8/spki encodings are what the account server reads, and a second encoder is a second thing that can disagree with it.
KEYPAIR_JS = """
        const crypto = require('crypto');
        const { privateKey, publicKey } = crypto.generateKeyPairSync('%s');
        const priv = privateKey.export({ type: 'pkcs8', format: 'der' }).toString('base64');
        const pub = publicKey.export({ type: 'spki', format: 'der' }).toString('base64');
        process.stdout.write(priv + '\\n' + pub);
    """


class CryptoKeys:
    """The six values `account_generate_crypto_keys` leaves in the shell."""

    __slots__ = ("api_key", "ed25519_priv", "ed25519_pub", "jwt", "x25519_priv", "x25519_pub")

    def __init__(
        self,
        ed25519_priv: str,
        ed25519_pub: str,
        x25519_priv: str,
        x25519_pub: str,
        jwt: str,
        api_key: str,
    ) -> None:
        self.ed25519_priv = ed25519_priv
        self.ed25519_pub = ed25519_pub
        self.x25519_priv = x25519_priv
        self.x25519_pub = x25519_pub
        self.jwt = jwt
        self.api_key = api_key


def _keygen_child(argv: list[str], strict: bool) -> str:
    """Run one keygen program and return its stdout.

    STRICT IS THE TWIN, and the default is not. `keys=$(node --eval ...)` and `JWT_SEC=$(openssl ... | tr ... | cut ...)` are bare assignments under errexit and pipefail, so a failing `node` or `openssl` ends `account_reset` before anything is pushed to Bitwarden. `strict=True` raises `AccountError` with that status, and `account_lifecycle.reset()` uses it: without it a missing `node` would reach `store-from-env` with six empty values.
    `mint_dev_keys()` keeps the lenient default and refuses empty values itself, because it has no twin to die the same way as.
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        if strict:
            sys.stderr.write("%s: command not found\n" % argv[0])
            raise AccountError("%s is not installed" % argv[0], code=127) from None
        return ""
    if strict and proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise AccountError("%s exited %d" % (argv[0], proc.returncode), code=proc.returncode)
    return proc.stdout


def keypair(curve: str, strict: bool = False) -> tuple[str, str]:
    """One `node --eval` producing a private and a public key, `head -1` and `tail -1`."""
    lines = _keygen_child(["node", "--eval", KEYPAIR_JS % curve], strict).split("\n")
    # `tail -1` of a ONE-line capture is that same line, which is what a node failure would produce on both sides.
    return lines[0], lines[-1]


def random_secret(strict: bool = False) -> str:
    """`openssl rand -base64 48 | tr -d '/+=' | cut -c1-64`."""
    stdout = _keygen_child(["openssl", "rand", "-base64", "48"], strict)
    out: list[str] = []
    for line in stdout.split("\n"):
        if line == "" and out:
            continue
        stripped = line.translate({ord(c): None for c in "/+="})
        out.append(stripped[:64])
    return "".join(out)


def generate_crypto_keys(strict: bool = False) -> CryptoKeys:
    """`account_generate_crypto_keys`, `.ci/lib/account.sh:223-251`. `strict` is the twin's errexit; see `_keygen_child`."""
    ed_priv, ed_pub = keypair("ed25519", strict)
    x_priv, x_pub = keypair("x25519", strict)
    return CryptoKeys(ed_priv, ed_pub, x_priv, x_pub, random_secret(strict), random_secret(strict))


# --------------------------------------------------------------------------- banner and TOTP ---------------------------------------------------------------------------


def banner_row(text: str) -> str:
    """`account_banner_row`, `.ci/lib/account.sh:620-622`.

    PADS BY BYTES, because `printf '%-63s'` does. See defect 2 in the module docstring. The trailing newline is the caller's: `printf` adds it and so does `print()`.
    """
    width = 63 - len(text.encode("utf-8"))
    return "  │  %s%s│" % (text, " " * max(width, 0))


def grep_cut(state_text: str, key: str) -> str:
    """`grep "^KEY=" FILE | cut -d= -f2` as the twin's bare assignment runs it.

    EVERY matching line, each cut to its SECOND `=`-field (defect 3), joined by the newlines `$(...)` keeps between them. Raises `StateAbortedError` where grep matches nothing, because that is what the twin does: exit 1 from grep, through `pipefail`, into `errexit`. Defect 1.
    Until 2026-09-24 this returned the FIRST match only; a state file with the key twice gave the twin both values and the port one. Every state-file read in both account modules now goes through here.
    """
    prefix = key + "="
    values = [line.split("=")[1] for line in state_text.split("\n") if line.startswith(prefix)]
    if not values:
        raise StateAbortedError(
            "grep '^%s' matched nothing, and the twin's bare assignment takes that "
            "exit 1 through pipefail into errexit; it dies here printing nothing" % prefix
        )
    return "\n".join(values)


def gateway_port_from_state(state_text: str) -> str:
    """`grep "^gateway_port=" | cut -d= -f2`, `account_totp`'s and `account_stop`'s bare assignment. See `grep_cut`."""
    return grep_cut(state_text, "gateway_port")


def state_pids(state_text: str) -> str:
    """`grep "^pids=" | cut -d= -f2`, `account_stop`'s other bare assignment (defect 5). `.ci/lib/account.sh:668`."""
    return grep_cut(state_text, "pids")


def writer_stamp() -> str:
    """`account_writer_stamp`: `<hostname>/<pid namespace>`, the identity every `.account-state` carries.

    The host and the devbox share the worktree, so they share the file, and a pid is only meaningful inside the pid namespace that recorded it. The hostname is read from `/proc/sys/kernel/hostname` (the UTS name, which is the container's own inside the devbox), with `uname -n` where there is no /proc.
    """
    try:
        host = pathlib.Path("/proc/sys/kernel/hostname").read_text(encoding="utf-8").rstrip("\n")
    except OSError:
        host = os.uname().nodename
    try:
        ns = os.readlink("/proc/self/ns/pid")
    except OSError:
        ns = ""
    return "%s/%s" % (host, ns or "no-pid-ns")


def state_owned(state_text: str, path: str) -> bool:
    """`account_state_owned`: True when the state file carries THIS writer's stamp.

    Otherwise warns whose pids they are and returns False, and the caller signals none of them. An unstamped file is refused the same way, because there is no telling which namespace its pids came from.
    """
    writer = ""
    for line in state_text.splitlines():
        if line.startswith("writer="):
            writer = line[len("writer=") :]
            break
    me = writer_stamp()
    if writer and writer == me:
        return True
    log.warn(
        "Not signalling the pids in %s: written by %s, not by this host and pid namespace (%s). "
        "Skipping them." % (path, writer or "an unstamped writer", me)
    )
    return False


def totp_fields(body: str) -> tuple[str, str]:
    """The twin's `node -e` JSON read at `.ci/lib/account.sh:652`.

    `d.code||""` and `d.secondsRemaining??""` are DIFFERENT operators: `secondsRemaining: 0` survives `??` and would be erased by `||`. Both are reproduced. A parse failure yields two empty strings because the twin's `|| true` swallows node's throw and leaves both reads empty.
    """
    try:
        data = json.loads(body or "{}")
    except ValueError:
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    code = data.get("code")
    code_out = "" if not code else js_str(code)
    seconds = data.get("secondsRemaining", None)
    seconds_out = "" if seconds is None else js_str(seconds)
    return code_out, seconds_out


def js_str(value) -> str:
    """`console.log(x)` for the scalar shapes this endpoint returns."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def totp(email: str | None = None, env: dict[str, str] | None = None) -> int:
    """`account_totp`, `.ci/lib/account.sh:627-659`. Returns the twin's exit code.

    THE SILENT EXIT 1 IS DELIBERATE. A state file with no `gateway_port=` line at all makes the twin die inside its own assignment with nothing on either stream; this returns 1 having printed nothing, for the same input.
    """
    address = email or DEFAULT_TOTP_EMAIL
    path = state_file(env)
    if not os.path.isfile(path):
        log.error("No running dev gateway (state file absent). Start it: ./run.sh account dev")
        return 1
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        gateway_port = gateway_port_from_state(text)
    except StateAbortedError:
        return 1
    if gateway_port == "":
        log.error("Could not read gateway port from %s" % path)
        return 1

    url = "http://127.0.0.1:%s/account/api/v1/test/totp-code" % gateway_port
    # `|| true`: a failed curl, and a curl that is not installed at all, leave the capture EMPTY rather than aborting. See `curl_body`.
    body = curl_body(
        ["curl", "-sf", "-m", "5", "-G", url, "--data-urlencode", "email=%s" % address]
    )
    if body == "":
        log.error(
            "No TOTP code for '%s'. Has ./run.sh account dev seeded a config store?" % address
        )
        return 1
    code, seconds = totp_fields(body)
    if code == "":
        log.error(
            "No TOTP code for '%s'. Has ./run.sh account dev seeded a config store?" % address
        )
        return 1
    log.info("TOTP for %s: %s  (%ss remaining)" % (address, code, seconds))
    return 0


# --------------------------------------------------------------------------- stop and rotation (real infrastructure, real-run verified) ---------------------------------------------------------------------------
#
# `stop()` and `rotation()` are NOT part of the shadow differential above -- see the module docstring's "TWO MORE ARE PORTED" section. `test_core_account.py` proves them with an actual run instead: a real tracked process and a real Docker daemon for `stop()`, and the real, credential-free, manifest-only subcommands for `rotation()`.


def _kill_quiet(pid: str, sig: int) -> None:
    """`kill [-9] "$pid" 2>/dev/null || true`. A non-numeric or already-gone pid is silent on both sides."""
    with contextlib.suppress(ValueError, ProcessLookupError, PermissionError):
        os.kill(int(pid), sig)


def _lsof_port_pid(port: str) -> str:
    """`lsof -ti:"$old_gateway" 2>/dev/null | head -1`. Empty on a closed port, a missing `lsof`, or no match."""
    try:
        proc = subprocess.run(
            ["lsof", "-ti:%s" % port], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return ""
    return proc.stdout.split("\n")[0]


def stop(env: dict[str, str] | None = None) -> int:
    """`account_stop`, `.ci/lib/account.sh:661-706`.

    Kills the dev pids and gateway-port occupant tracked in the state file, tears down the `account-server` container and any RustFS config-store ghosts, and removes the state file. Starts and stops REAL infrastructure, so this is real-run verified rather than shadow-differentially proved; see the module docstring.

    Returns 1 where the twin's bare `old_gateway=$(...)` or `old_pids=$(...)` assignment matches nothing and dies under errexit/pipefail before Docker teardown or the `rm -f` ever run (defect 5). Returns 0 otherwise, same as the twin having nothing further to report.
    """
    log.step("Stopping account services")
    path = state_file(env)
    if os.path.isfile(path):
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        try:
            old_gateway = gateway_port_from_state(text)
        except StateAbortedError:
            return 1
        try:
            old_pids = state_pids(text)
        except StateAbortedError:
            return 1

        if old_pids and state_owned(text, path):
            # `for pid in ${old_pids//,/ }`: unquoted, so word-splitting drops any empty field the comma substitution leaves behind.
            pids = old_pids.replace(",", " ").split()
            for pid in pids:
                _kill_quiet(pid, signal.SIGTERM)
            time.sleep(1)
            for pid in pids:
                _kill_quiet(pid, signal.SIGKILL)

        if old_gateway:
            port_pid = _lsof_port_pid(old_gateway)
            if port_pid:
                _kill_quiet(port_pid, signal.SIGKILL)

    # `(cd "$ACCOUNT_DIR" && docker compose down --remove-orphans) 2>/dev/null || true` and the container stop/rm loop below both run unconditionally in the twin, relying on `2>/dev/null || true` to swallow even a missing `docker` binary.
    # Gating the whole section on `shutil.which("docker")` produces the identical observable outcome (no output, nothing torn down) without needing to catch `FileNotFoundError` at every one of the four call sites below.
    if shutil.which("docker") is not None:
        subprocess.run(
            ["docker", "compose", "down", "--remove-orphans"],
            cwd=account_dir(env),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

        for container in ("account-server",):
            names_proc = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=False,
            )
            names = names_proc.stdout.split("\n")
            if container in names:
                subprocess.run(
                    ["docker", "stop", container],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                subprocess.run(
                    ["docker", "rm", container],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )

        # `account_docker_ghost_clean`, `.ci/lib/account.sh:207-214`. Inlined here rather than a named function -- see the module docstring.
        info = subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
        if info.returncode == 0:
            ids_proc = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    "name=account-config-rustfs",
                    "--filter",
                    "name=rediacc-config-rustfs-dev",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            ids = [line for line in ids_proc.stdout.split("\n") if line]
            if ids:
                subprocess.run(
                    ["docker", "rm", "-f", *ids],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )

    with contextlib.suppress(FileNotFoundError):
        os.remove(path)
    log.info("Account services stopped")
    return 0


# The profile list `bws_env exec` leaves in the child's environment. `rediacc_ci.core.bws_env.PROFILES_ENV` names the same string; it is spelled out here so this module does not import the Bitwarden client merely to read a constant.
BWS_PROFILES_ENV = "REDIACC_BWS_PROFILES"


def ci_dir(env: dict[str, str] | None = None) -> str:
    """`ACCOUNT_CI_DIR`, `.ci/lib/account.sh:19-20`: `$REDIACC_CI_ROOT/.ci` when set, else the `.ci` this module lives in."""
    environ = os.environ if env is None else env
    override = environ.get("REDIACC_CI_ROOT", "")
    if override:
        return os.path.join(override, ".ci")
    return str(pathlib.Path(__file__).resolve().parents[2])


def bws_exec(profile: str, run_sh_args: list[str], env: dict[str, str] | None = None) -> None:
    """`account_bws_exec`, `.ci/lib/account.sh:48-56`. Returns only when PROFILE is already hydrated.

    Otherwise REPLACES this process with `python3 -m rediacc_ci.core.bws_env exec --profile PROFILE -- $CONSOLE_ROOT_DIR/run.sh RUN_SH_ARGS...`, exactly the twin's `exec`, so the profile's secrets reach the re-run through its ENVIRONMENT and never through a file.
    The re-run finds PROFILE in `REDIACC_BWS_PROFILES` and carries on; an absent token or store entry is `bws_env`'s refusal, with no fallback.

    THE RE-RUN IS `./run.sh`, NOT THIS MODULE, because that is what the twin re-executes and the twin is what `run.sh` still dispatches to. Real-run verified through `rotation()`, never differentially: it reads the live store.
    """
    environ = dict(os.environ if env is None else env)
    if profile in environ.get(BWS_PROFILES_ENV, "").split(","):
        return
    existing = environ.get("PYTHONPATH", "")
    environ["PYTHONPATH"] = ci_dir(environ) + (":" + existing if existing else "")
    argv = [
        "python3",
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        profile,
        "--",
        os.path.join(console_root(environ), "run.sh"),
        *run_sh_args,
    ]
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvpe("python3", argv, environ)  # noqa: S606 -- forwarding exec, same shape as the twin's


def rotation(argv: list[str], env: dict[str, str] | None = None) -> int:
    """`account_rotation`, `.ci/lib/account.sh:920-925`.

    A thin dispatcher to the real TypeScript rotation CLI (`private/account/scripts/rotation/index.ts`), which mints, rotates and deletes REAL credentials at AWS IAM and Cloudflare, and pushes them to Bitwarden Secrets Manager (see `private/account/CLAUDE.md`, "Secret Rotation").
    This function only decides whether node is new enough and where to run the subprocess from; every side effect belongs to the TypeScript CLI, which this port does not touch.

    NOT part of the shadow differential (see the module docstring): the twin itself is two lines with nothing computational to compare, and the mutating subcommands (`rotate`, `check`, `deactivate`, `delete`, `sweep`, `init`) need live production credentials that neither this port nor its tests may exercise.
    The read-only, manifest-only subcommands (`list`, `status`, `history`) are credential-free and are what `test_core_account.py`'s real run actually drives.

    FIRST `bws_exec("rotation", ...)`, as the twin's first line is `account_bws_exec rotation rotation "$@"`: outside a hydrated `rotation` profile this call does not return, it re-executes `./run.sh rotation ARGV...` under `bws_env exec`.

    Returns 1 where the twin's bare `check_node_version` call, or its `cd "$ACCOUNT_DIR" || exit 1`, aborts under errexit. Otherwise the dispatched subprocess's exit code, or 127 -- matching the shell's own "command not found" convention, since the twin does not swallow this one with `|| true` -- if `npx` itself is not on PATH.
    """
    bws_exec("rotation", ["rotation", *argv], env)
    status = node_version_ok()
    if status != 0:
        return status
    directory = account_dir(env)
    if not os.path.isdir(directory):
        log.error("cd to %s failed: not a directory" % directory)
        return 1
    try:
        proc = subprocess.run(
            ["npx", "tsx", "scripts/rotation/index.ts", *argv], cwd=directory, check=False
        )
    except FileNotFoundError:
        log.error("npx: command not found")
        return 127
    return proc.returncode


# --------------------------------------------------------------------------- the database browser ---------------------------------------------------------------------------


def parse_db_args(argv: list[str]) -> bool:
    """`account_db`'s option loop, `.ci/lib/account.sh:954-966`.

    True for `--studio`. Raises `AccountError(code=2)` on anything else, INCLUDING an unknown option that follows `--studio`, because the twin's loop keeps parsing after setting the flag. Defect 4.
    """
    use_studio = False
    for arg in argv:
        if arg == "--studio":
            use_studio = True
            continue
        log.error("Unknown option for account db: %s" % arg)
        raise AccountError("unknown option %s" % arg, code=2)
    return use_studio


def db_path(env: dict[str, str] | None = None) -> str:
    """`${DATABASE_PATH:-$ACCOUNT_DIR/account.db}`, `.ci/lib/account.sh:967`."""
    environ = os.environ if env is None else env
    value = environ.get("DATABASE_PATH", "")
    return value or os.path.join(account_dir(env), "account.db")


def db_preferred_port(env: dict[str, str] | None = None) -> int:
    """`.ci/lib/account.sh:977-1000`: this worktree's devbox studio slot, else 4983.

    ONE PARSER FOR `.devbox-state`, which is the twin's own point: it used to hand-roll `sed -n 's/^base_port=//p'` beside `devbox_state_get`, and a format with two independent readers is one edit away from them disagreeing. A `slug=` key was in fact added later.
    """
    environ = os.environ if env is None else env
    preferred = DB_BROWSER_PREFERRED
    if os.path.isfile(devbox_state_file(env)):
        base = devbox_state_get("base_port", env)
        if base:
            offset = int(environ.get("DEVBOX_OFFSET_STUDIO", str(DEVBOX_OFFSET_STUDIO)))
            preferred = int(base) + offset
    return preferred


def sqlite_web_path(env: dict[str, str] | None = None) -> str | None:
    """`.ci/lib/account.sh:1025-1040`, resolution only; the `uv` install is in `db_launch`.

    `~/.local/bin/sqlite_web` first, then PATH. None when neither answers, which is the point at which the twin reaches for `uv`.
    """
    environ = os.environ if env is None else env
    home = environ.get("HOME", "")
    candidate = os.path.join(home, ".local", "bin", "sqlite_web")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    return shutil.which("sqlite_web")


class DbPlan:
    """Everything `account_db` decides before it launches anything."""

    __slots__ = ("database", "port", "sqlite_web", "use_studio")

    def __init__(self, use_studio: bool, database: str, port: int, sqlite_web: str | None) -> None:
        self.use_studio = use_studio
        self.database = database
        self.port = port
        self.sqlite_web = sqlite_web


def db_plan(argv: list[str], env: dict[str, str] | None = None) -> DbPlan:
    """`account_db` up to but NOT including the launch. This is the proved half.

    Raises `AccountError` carrying the twin's own exit codes: 2 for an unknown option, 1 for a missing database or no free port.
    """
    status = node_version_ok()
    if status != 0:
        # The twin's bare `check_node_version` under `errexit` aborts the function.
        raise AccountError("node version check failed", code=status)
    use_studio = parse_db_args(argv)
    database = db_path(env)
    if not os.path.isfile(database):
        log.error("No dev database at %s" % database)
        log.info("Start the stack once so it gets created and migrated: ./run.sh account dev")
        raise AccountError("no database at %s" % database, code=1)
    preferred = db_preferred_port(env)
    port = ports.find_preferred_port(preferred, preferred + 1, preferred + DB_BROWSER_SCAN_SPAN)
    if port is None:
        log.error("No free port near %d for the database browser" % preferred)
        raise AccountError("no free port near %d" % preferred, code=1)
    return DbPlan(use_studio, database, port, sqlite_web_path(env))


def db_launch(plan: DbPlan, env: dict[str, str] | None = None) -> int:
    """`account_db`'s tail, `.ci/lib/account.sh:1009-1046`. NOT differentially proved.

    This starts a server. It is written out so the port is complete, and it is excluded from every ledger row and from every differential case in `test_core_account.py`: a row is a claim of equivalence, and nothing here has been compared against the twin under a real launch.
    """
    environ = os.environ if env is None else env
    log.warn("Note: ./run.sh account reset DELETES this database.")
    directory = account_dir(env)
    if plan.use_studio:
        if not os.path.isdir(os.path.join(directory, "node_modules")):
            log.step("Installing account dependencies (drizzle-kit)...")
            subprocess.run(
                ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund"],
                cwd=directory,
                check=False,
            )
        log.step("Drizzle Studio (API only) on %s" % plan.database)
        log.info(
            "UI: https://local.drizzle.studio/?port=%d&host=<the host you reach this on>"
            % plan.port
        )
        log.warn("Chrome blocks that hosted page from reaching a local server unless you enable")
        log.warn('"Local network access" for local.drizzle.studio in Site information.')
        child = subprocess.run(
            # S104: `0.0.0.0` is an ARGUMENT to another program here, copied from the twin at `.ci/lib/account.sh:1021`, not a bind in this process.
            ["npx", "drizzle-kit", "studio", "--port", str(plan.port), "--host", "0.0.0.0"],  # noqa: S104 -- the twin's own literal argument
            cwd=directory,
            env={**environ, "DATABASE_PATH": plan.database},
            check=False,
        )
        return child.returncode

    binary = plan.sqlite_web
    if binary is None:
        if shutil.which("uv") is None:
            log.error("sqlite-web is not installed and uv is unavailable")
            log.info("Use ./run.sh account db --studio instead")
            return 1
        log.step("Installing sqlite-web (one-time)")
        install = subprocess.run(
            ["uv", "tool", "install", "sqlite-web"], capture_output=True, check=False
        )
        if install.returncode != 0:
            log.error("Could not install sqlite-web; retry with: ./run.sh account db --studio")
            return 1
        binary = sqlite_web_path(env) or "sqlite_web"

    log.step("Database browser on %s" % plan.database)
    log.info("Port: %d" % plan.port)
    print()
    argv = [binary, "--host", "0.0.0.0", "--port", str(plan.port), "--no-browser", plan.database]  # noqa: S104 -- the twin's own literal argument at `.ci/lib/account.sh:1045`
    os.execv(binary, argv)  # noqa: S606 -- forwarding exec, same shape as the twin's
    raise AssertionError("execv returned")  # pragma: no cover


def db(argv: list[str], env: dict[str, str] | None = None) -> int:
    """`account_db`, `.ci/lib/account.sh:950-1046`."""
    try:
        plan = db_plan(argv, env)
    except AccountError as exc:
        return exc.code
    return db_launch(plan, env)


# --------------------------------------------------------------------------- throwaway dev keys for CI ---------------------------------------------------------------------------


def mint_dev_keys(env: dict[str, str] | None = None) -> int:
    """`mint-dev-keys`: append a THROWAWAY set of the six `CRYPTO_KEYS` to the file `$GITHUB_ENV` names. Returns an exit code.

    NEW, NOT PORTED: the twin has no counterpart. It exists for CI legs with no Bitwarden access, the Drills job in `.github/workflows/ct-tests.yml` first, which used to get a throwaway key set from `account_ensure_env` writing `private/account/.env`.
    That file is gone. With no token, `bws_env exec` proceeds when every REQUIRED name of the profile is already in the environment and names the optional ones it left unset (`rediacc_ci.core.bws_env.hydrate`); the `account-dev` profile's six required names are exactly `CRYPTO_KEYS`, so six freshly minted values in the JOB environment let `./run.sh account dev` run with no token, and with no file in the tree.
    GitHub reads `$GITHUB_ENV` into the environment of every LATER step of the job, which is the only place these values go.

    REFUSES WITH 2 when `GITHUB_ENV` is unset or empty: without it there is nowhere to put the values that is not a stream or a file in the tree, and printing them is exactly what this must never do.

    REFUSES WITH 1, WRITING NOTHING, when any generated value is empty (a missing `node` or `openssl` yields an empty capture, not an error) or carries a line break, which would inject a second assignment into the file.

    Reports the six NAMES and a count on stderr. Never a value, and never anything on stdout.
    """
    environ = os.environ if env is None else env
    target = environ.get("GITHUB_ENV", "")
    if not target:
        log.error(
            "mint-dev-keys: GITHUB_ENV is not set; it only writes to a GitHub Actions job environment"
        )
        return 2
    keys = generate_crypto_keys()
    values = (
        keys.ed25519_priv,
        keys.ed25519_pub,
        keys.x25519_priv,
        keys.x25519_pub,
        keys.api_key,
        keys.jwt,
    )
    bad = [
        name
        for name, value in zip(CRYPTO_KEYS, values, strict=True)
        if not value or "\n" in value or "\r" in value
    ]
    if bad:
        log.error(
            "mint-dev-keys: generated an empty or multi-line value for %s; nothing written"
            % " ".join(bad)
        )
        return 1
    with open(target, "a", encoding="utf-8") as handle:
        handle.write("".join("%s=%s\n" % pair for pair in zip(CRYPTO_KEYS, values, strict=True)))
    for name in CRYPTO_KEYS:
        log.info("mint-dev-keys: %s" % name)
    log.info("mint-dev-keys: %d throwaway dev key(s) appended to $GITHUB_ENV" % len(CRYPTO_KEYS))
    return 0


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------

USAGE = """rediacc_ci.core.account -- the deterministic half of .ci/lib/account.sh

  totp [email]      print the running dev gateway's TOTP code for a dev user
  db [--studio]     browse the dev database
  mint-dev-keys     append a throwaway DEV keypair and session secrets to
                    $GITHUB_ENV, for a CI job with no Bitwarden access

The dev, stop, test, reset and seed-demo verbs are NOT here: they live in
.ci/lib/account.sh and start long-running infrastructure. See the module
docstring for why they are a separate slice."""


def main(argv: list[str]) -> int:
    """The two public account verbs this slice covers, plus the CI-only `mint-dev-keys`."""
    if not argv:
        print(USAGE)
        return 2
    if argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    verb, rest = argv[0], argv[1:]
    if verb == "totp":
        return totp(rest[0] if rest else None)
    if verb == "db":
        return db(rest)
    if verb == "mint-dev-keys":
        if rest:
            log.error("mint-dev-keys takes no arguments")
            return 2
        return mint_dev_keys()
    log.error("Unknown account command: %s" % verb)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
