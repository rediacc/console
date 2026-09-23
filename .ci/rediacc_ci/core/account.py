"""The DETERMINISTIC half of `.ci/lib/account.sh`, ported function for function.

PORTED FROM `.ci/lib/account.sh` (1143 lines, 22 functions). The twin still exists, is untouched by this file, and stays sourced at `.ci/legacy/run-legacy.sh:405` (the `account` verb) and `:443` (the `rotation` verb). Nothing is cut over here.
This is a pre-cutover port on the same sequencing every other lib in this campaign used, and `.ci/lib/service.sh` is the worked precedent: its port `rediacc_ci/core/service.py` has carried a K=5 ledger since 2026-09-10 while `run-legacy.sh:48` still sources the bash.

--------------------------------------------------------------------------
WHAT IS HERE AND WHAT IS DELIBERATELY ABSENT
--------------------------------------------------------------------------
ELEVEN FUNCTIONS ARE PORTED, and they are the ones whose whole answer is computation, a file read or a file write: `account_allocate_ports`, `account_wait_port`, `account_rustfs_alive`, `account_generate_crypto_keys`, `account_generate_fresh_env`, `account_env_add_if_missing`, `account_ensure_env_keys`, `account_ensure_env`, `account_banner_row`, `account_totp`, and the decidable half of `account_db`.

ELEVEN ARE NOT, and saying so here rather than leaving an absence is the point. `account_dev`, `account_stop`, `account_test`, `account_test_e2e`, `account_reset` and `account_seed_demo` start or stop long-running dev infrastructure: Docker containers, RustFS, a Vite server, an Astro server, a gateway held in the foreground.
A shadow-gate row comparing two runs of `account_dev` would be comparing two dev-server boot transcripts rather than two reports, which is a different differential technique and a separate ruling.
`account_cleanup` kills the tracked pid set and calls `exit`; `account_docker_ghost_clean` force-removes containers; `account_stripe_auto` starts a background `stripe listen`; `account_dev_credentials` drives the live gateway's provisioning routes; `account_rotation` is a two-line `cd` plus `npx tsx` shim. THERE IS NO PYTHON FUNCTION BELOW FOR ANY OF THOSE ELEVEN.
The bash file is the only implementation of them and remains so.

`account_db`'s LAUNCH is in the second group even though the function as a whole is in the first. Everything up to the launch, meaning argument parsing, the database path, the devbox-derived preferred port, the free-port search, the two refusals and the `sqlite_web` resolution, is decided in `db_plan()` and is what the differential drives.
`db_launch()` below execs a server and is NOT differentially proved; it is written out so the port is complete, and it is named here so nobody reads its green as evidence.

--------------------------------------------------------------------------
TWO FUNCTIONS THIS MODULE DEFINES THAT THE TWIN BORROWS FROM ITS SOURCER
--------------------------------------------------------------------------
`check_node_version` is called at `.ci/lib/account.sh:1048` and defined at `.ci/lib/local-common.sh:418`, the file `run-legacy.sh` sources BEFORE `account.sh`. `devbox_state_get` is called at `:1093` and defined at `.ci/lib/devbox.sh:124`, which `account_db` sources on demand.
A module cannot borrow a function from its importer, so both are re-implemented below, faithful to the definitions named. NEITHER `local-common.sh` NOR `devbox.sh` IS MODIFIED BY THIS CHANGE: both are still live-bridged into `rediacc_ci/setup/bridge.py` and are out of this slice's scope.
This is exactly the shape `service.py` records for `check_docker`, which lives in `run-legacy.sh` for the same reason.

--------------------------------------------------------------------------
FOUR TWIN BEHAVIOURS REPRODUCED ON PURPOSE, NOT FIXED
--------------------------------------------------------------------------
  1. `account_totp` DIES SILENTLY on a state file with no `gateway_port=` line. `gateway_port=$(grep "^gateway_port=" ... | cut -d= -f2)` is a BARE ASSIGNMENT, so it takes the pipeline's status; grep matching nothing exits 1; every sourcer of this file has `pipefail` and `errexit` armed.
  The function stops there, prints NOTHING, and returns 1, so the "Could not read gateway port" message two lines below is reachable ONLY when the line exists with an empty value. Measured 2026-09-23 against the live twin. `state_gateway_port()` raises `StateAbortedError` where the twin dies, and `totp()` maps it to the same silent exit 1.
  2. `account_banner_row` PADS BY BYTES. `printf '%-63s'` counts bytes, so a multibyte glyph shortens the visible field and shifts the closing bar left. The twin's own comment at `:672-674` says the content is kept ASCII for exactly this reason.
  `banner_row()` pads by bytes, not by characters, so a caller that ever passes a non-ASCII string gets the twin's broken box rather than a quietly different one.
  3. `cut -d= -f2` TAKES THE SECOND FIELD ONLY, so a state value containing `=` is truncated. Preserved in `state_gateway_port()`.
  4. `account_db`'s `--studio` arm still parses the REST of the argument list before acting, so `account db --studio --bogus` refuses with exit 2 rather than starting Drizzle. Preserved in `parse_db_args()`.

--------------------------------------------------------------------------
THE ONE PLACE THE PORT REFUSES WHERE THE TWIN WOULD GUESS
--------------------------------------------------------------------------
`account_env_add_if_missing` tests for a key with `grep -q "^${key}="`, which makes the key a BASIC REGULAR EXPRESSION. Every key the twin ever passes is `[A-Z0-9_]+`, where a BRE and a literal agree, so a literal prefix test is equivalent for the whole live corpus.
Rather than silently assume that forever, `env_add_if_missing()` raises on a key carrying a BRE metacharacter: a divergence that is refused is a divergence somebody sees.

--------------------------------------------------------------------------
WHY THE LOGGER IS `rediacc_ci.log`
--------------------------------------------------------------------------
`log_error` / `log_info` / `log_warn` / `log_step` / `log_debug` here are `.ci/scripts/lib/common.sh:35-55`, and `rediacc_ci.log` is already the byte-exact port of those five, tty gating included. The twin writes all five to STDERR; so does this.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

from rediacc_ci import log, paths
from rediacc_ci.core import ports

# `.ci/config/constants.sh:117-120` and `:135,145`. Plain readonly assignments derived from CONSOLE_ROOT_DIR, so they are derived here the same way rather than read from the environment: constants.sh overwrites any inherited value, and a port that honoured an override would answer a question the twin cannot be asked.
ACCOUNT_DEV_PORT_PREFERRED = 4800
ACCOUNT_DEV_PORT_RANGE_END = 5799
DEVBOX_OFFSET_STUDIO = 3

# `.ci/lib/account.sh:1074`. The devbox slot is preferred and then stepped aside from; this is the fallback when no `.devbox-state` exists.
DB_BROWSER_PREFERRED = 4983
DB_BROWSER_SCAN_SPAN = 40

# `.ci/lib/local-common.sh:419`. The twin's default when no argument is passed, which is how `account_db` calls it.
NODE_VERSION_MIN_DEFAULT = "18.0.0"

# `.ci/lib/account.sh:730`.
DEFAULT_TOTP_EMAIL = "dev-user@rediacc.io"

# The six keys `account_ensure_env_keys` mints when any one of them is absent, in the twin's order (`:293`).
CRYPTO_KEYS = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_JWT_SECRET",
)

# A key that is not a literal under `grep`'s BRE. See the module docstring.
BRE_METACHARACTERS = set(".[]*^$\\")


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


def env_path(env: dict[str, str] | None = None) -> str:
    """The `.env` both `account_ensure_env` and `account_dev` read."""
    return os.path.join(account_dir(env), ".env")


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


def check_node_version(min_version: str = NODE_VERSION_MIN_DEFAULT) -> bool:
    """`.ci/lib/local-common.sh:418-436`, which `account.sh` calls and does not define.

    Returns False where the twin returns 1. Under the twin's `errexit` a False here aborts the calling function, which `db_plan()` reproduces.
    """
    if shutil.which("node") is None:
        log.error("Node.js is not installed")
        return False
    proc = subprocess.run(["node", "-v"], capture_output=True, text=True, check=False)
    # `node -v | cut -d'v' -f2`: the SECOND field, so `v22.1.0` gives `22.1.0`.
    current = proc.stdout.strip().split("v")[1] if "v" in proc.stdout else proc.stdout.strip()
    # `sort -V -C` is "already sorted?", which is min <= current under version order.
    if version_tuple(current) < version_tuple(min_version):
        log.error("Node.js version %s is too old (minimum: %s)" % (current, min_version))
        return False
    log.debug("Node.js version: %s" % current)
    return True


def version_tuple(text: str) -> tuple[int, ...]:
    """`sort -V`'s ordering for the dotted-numeric shape these versions take."""
    out: list[int] = []
    for part in text.split("."):
        digits = ""
        for ch in part:
            if not ch.isdigit():
                break
            digits += ch
        out.append(int(digits) if digits else 0)
    return tuple(out)


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
    """`account_allocate_ports`, `.ci/lib/account.sh:53-100`.

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
    """`account_wait_port`, `.ci/lib/account.sh:114-148`. True where the twin returns 0.

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
    """`account_rustfs_alive`, `.ci/lib/account.sh:167-172`.

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


# --------------------------------------------------------------------------- crypto and .env ---------------------------------------------------------------------------

# `.ci/lib/account.sh:194-212`, verbatim apart from the curve name. Kept as node rather than re-derived with a Python crypto library: the DER/pkcs8/spki encodings are what the account server reads, and a second encoder is a second thing that can disagree with it.
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


def keypair(curve: str) -> tuple[str, str]:
    """One `node --eval` producing a private and a public key, `head -1` and `tail -1`."""
    proc = subprocess.run(
        ["node", "--eval", KEYPAIR_JS % curve],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = proc.stdout.split("\n")
    # `tail -1` of a ONE-line capture is that same line, which is what a node failure would produce on both sides.
    return lines[0], lines[-1]


def random_secret() -> str:
    """`openssl rand -base64 48 | tr -d '/+=' | cut -c1-64`."""
    proc = subprocess.run(
        ["openssl", "rand", "-base64", "48"], capture_output=True, text=True, check=False
    )
    out: list[str] = []
    for line in proc.stdout.split("\n"):
        if line == "" and out:
            continue
        stripped = line.translate({ord(c): None for c in "/+="})
        out.append(stripped[:64])
    return "".join(out)


def generate_crypto_keys() -> CryptoKeys:
    """`account_generate_crypto_keys`, `.ci/lib/account.sh:191-219`."""
    ed_priv, ed_pub = keypair("ed25519")
    x_priv, x_pub = keypair("x25519")
    return CryptoKeys(ed_priv, ed_pub, x_priv, x_pub, random_secret(), random_secret())


def fresh_env_text(keys: CryptoKeys, stamp: str, root_email: str) -> str:
    """The heredoc at `.ci/lib/account.sh:225-269`, byte for byte.

    `stamp` is `date -u +%Y-%m-%dT%H:%M:%SZ` and `root_email` is `${ROOT_EMAIL:-}`; both are parameters rather than reads so the differential can freeze them.
    """
    return """# Auto-generated by ./run.sh — %(stamp)s

# Account server URL (used by rdc CLI for subscription commands)
# Updated automatically by dev-gateway on startup with the actual port
REDIACC_ACCOUNT_SERVER=http://localhost:4800

# SQLite database path
DATABASE_PATH=account.db

# Ed25519 key pair (for subscription/license signing)
ACCOUNT_ED25519_PRIVATE_KEY=%(ed_priv)s
ACCOUNT_ED25519_PUBLIC_KEY=%(ed_pub)s

# X25519 key pair (for E2E encryption)
ACCOUNT_X25519_PRIVATE_KEY=%(x_priv)s
ACCOUNT_X25519_PUBLIC_KEY=%(x_pub)s

# Admin API key
ACCOUNT_SERVER_API_KEY=%(api_key)s

# JWT secret for session tokens
ACCOUNT_JWT_SECRET=%(jwt)s

# Stripe sandbox (uncomment and fill to enable Stripe features)
# STRIPE_SANDBOX_SECRET_KEY=sk_test_...
# STRIPE_SANDBOX_WEBHOOK_SECRET is auto-captured from stripe listen

# Fixed webhook secret for E2E webhook simulation tests. Deliberately NOT named
# STRIPE_WEBHOOK_SECRET: Bitwarden holds a real production secret under that
# name, and one fetch-by-name away this fixture slot would have received it.
STRIPE_E2E_WEBHOOK_SECRET=whsec_e2e_test_webhook_secret_for_simulation_only

# Root email (receives alerts for disputes, refunds, etc.)
# Set via GitHub variable ROOT_EMAIL or environment
ROOT_EMAIL="%(root_email)s"

# Server port (used by standalone node entry, not the dev gateway)
PORT=3000

# WebAuthn passkey (for config storage setup)
WEBAUTHN_RP_ID=localhost
WEBAUTHN_RP_NAME=Rediacc
WEBAUTHN_ORIGIN=http://localhost:4800
""" % {
        "stamp": stamp,
        "ed_priv": keys.ed25519_priv,
        "ed_pub": keys.ed25519_pub,
        "x_priv": keys.x25519_priv,
        "x_pub": keys.x25519_pub,
        "api_key": keys.api_key,
        "jwt": keys.jwt,
        "root_email": root_email,
    }


def generate_fresh_env(env: dict[str, str] | None = None, stamp: str | None = None) -> None:
    """`account_generate_fresh_env`, `.ci/lib/account.sh:221-272`."""
    environ = os.environ if env is None else env
    log.step("Generating account .env...")
    keys = generate_crypto_keys()
    if stamp is None:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    target = pathlib.Path(env_path(env))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(fresh_env_text(keys, stamp, environ.get("ROOT_EMAIL", "")), encoding="utf-8")
    log.info("Generated private/account/.env with fresh keys")


def env_add_if_missing(env_file: str, key: str, value: str, comment: str = "") -> bool:
    """`account_env_add_if_missing`, `.ci/lib/account.sh:275-284`.

    True where the twin returns 0, meaning the key was absent and has been appended; False where it returns 1, meaning it was already present and the file is untouched.

    `echo -e "\\n# ${comment}"` writes a BLANK LINE and then the comment, which is where every blank line in a grown `.env` comes from.
    """
    metachars = BRE_METACHARACTERS & set(key)
    if metachars:
        raise ValueError(
            "key %r carries the BRE metacharacter(s) %s; the twin tests for it with "
            '`grep -q "^${key}="`, where that is a pattern and not a literal, so this port '
            "would silently answer a different question. Add a case to test_core_account.py "
            "pinning what the twin actually does before allowing it."
            % (key, "".join(sorted(metachars)))
        )
    path = pathlib.Path(env_file)
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    prefix = key + "="
    for line in text.split("\n"):
        if line.startswith(prefix):
            return False
    with open(env_file, "a", encoding="utf-8") as handle:
        if comment:
            handle.write("\n# %s\n" % comment)
        handle.write("%s=%s\n" % (key, value))
    return True


def ensure_env_keys(env: dict[str, str] | None = None) -> None:
    """`account_ensure_env_keys`, `.ci/lib/account.sh:287-331`.

    Crypto is minted only when at least ONE of the six is absent, and then every absent one is filled. The non-crypto defaults are added when missing and never overridden. ROOT_EMAIL, STRIPE_SANDBOX_SECRET_KEY and AWS_SES_* are deliberately NOT here: they are user-set and only ever written by a fresh generation.
    """
    environ = os.environ if env is None else env
    target = env_path(env)
    added = False

    text = ""
    if os.path.isfile(target):
        text = pathlib.Path(target).read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    need_gen = any(not any(line.startswith(name + "=") for line in lines) for name in CRYPTO_KEYS)

    if need_gen:
        keys = generate_crypto_keys()
        for name, value, comment in (
            (
                "ACCOUNT_ED25519_PRIVATE_KEY",
                keys.ed25519_priv,
                "Ed25519 key pair (for subscription/license signing)",
            ),
            ("ACCOUNT_ED25519_PUBLIC_KEY", keys.ed25519_pub, ""),
            (
                "ACCOUNT_X25519_PRIVATE_KEY",
                keys.x25519_priv,
                "X25519 key pair (for E2E encryption)",
            ),
            ("ACCOUNT_X25519_PUBLIC_KEY", keys.x25519_pub, ""),
            ("ACCOUNT_SERVER_API_KEY", keys.api_key, "Admin API key"),
            ("ACCOUNT_JWT_SECRET", keys.jwt, "JWT secret for session tokens"),
        ):
            if env_add_if_missing(target, name, value, comment):
                added = True

    gateway = environ.get("GATEWAY_PORT", "") or "4800"
    for name, value, comment in (
        ("REDIACC_ACCOUNT_SERVER", "http://localhost:4800", "Account server URL"),
        ("DATABASE_PATH", "account.db", "SQLite database path"),
        (
            "STRIPE_E2E_WEBHOOK_SECRET",
            "whsec_e2e_test_webhook_secret_for_simulation_only",
            "E2E webhook-simulation fixture (not a credential)",
        ),
        ("PORT", "3000", "Server port"),
        ("OTEL_ENDPOINT", "https://otlp.rediacc.io", "OTel OTLP endpoint"),
        ("WEBAUTHN_RP_ID", "localhost", "WebAuthn Relying Party ID"),
        ("WEBAUTHN_RP_NAME", "Rediacc", "WebAuthn display name"),
        ("WEBAUTHN_ORIGIN", "http://localhost:%s" % gateway, "WebAuthn origin URL"),
    ):
        if env_add_if_missing(target, name, value, comment):
            added = True

    if added:
        log.info("Added missing keys to existing .env")


def ensure_env(env: dict[str, str] | None = None, stamp: str | None = None) -> None:
    """`account_ensure_env`, `.ci/lib/account.sh:333-341`.

    `stamp` exists only so a differential can freeze the clock on THIS path too. The twin's clock seam is a `date` earlier on PATH, and reaching the fresh-generation branch through here rather than directly must not quietly use a different one: a case that compared a frozen stamp against a live one would fail for a reason that is the harness.
    """
    if not os.path.isfile(env_path(env)):
        generate_fresh_env(env, stamp)
        return
    ensure_env_keys(env)


# --------------------------------------------------------------------------- banner and TOTP ---------------------------------------------------------------------------


def banner_row(text: str) -> str:
    """`account_banner_row`, `.ci/lib/account.sh:722-724`.

    PADS BY BYTES, because `printf '%-63s'` does. See defect 2 in the module docstring. The trailing newline is the caller's: `printf` adds it and so does `print()`.
    """
    width = 63 - len(text.encode("utf-8"))
    return "  │  %s%s│" % (text, " " * max(width, 0))


def state_gateway_port(state_text: str) -> str:
    """`grep "^gateway_port=" | cut -d= -f2` as the twin's bare assignment runs it.

    Raises `StateAbortedError` where grep matches nothing, because that is what the twin does: exit 1 from grep, through `pipefail`, into `errexit`. Defect 1.
    """
    for line in state_text.split("\n"):
        if line.startswith("gateway_port="):
            # `cut -d= -f2` takes the SECOND field only, so `gateway_port=a=b` gives `a`.
            fields = line.split("=")
            return fields[1] if len(fields) > 1 else ""
    raise StateAbortedError(
        "grep '^gateway_port=' matched nothing, and the twin's bare assignment takes that "
        "exit 1 through pipefail into errexit; it dies here printing nothing"
    )


def totp_fields(body: str) -> tuple[str, str]:
    """The twin's `node -e` JSON read at `.ci/lib/account.sh:754`.

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
    """`account_totp`, `.ci/lib/account.sh:729-761`. Returns the twin's exit code.

    THE SILENT EXIT 1 IS DELIBERATE. A state file with no `gateway_port=` line at all makes the twin die inside its own assignment with nothing on either stream; this returns 1 having printed nothing, for the same input.
    """
    address = email or DEFAULT_TOTP_EMAIL
    path = state_file(env)
    if not os.path.isfile(path):
        log.error("No running dev gateway (state file absent). Start it: ./run.sh account dev")
        return 1
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        gateway_port = state_gateway_port(text)
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


# --------------------------------------------------------------------------- the database browser ---------------------------------------------------------------------------


def parse_db_args(argv: list[str]) -> bool:
    """`account_db`'s option loop, `.ci/lib/account.sh:1051-1062`.

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
    """`${DATABASE_PATH:-$ACCOUNT_DIR/account.db}`, `.ci/lib/account.sh:1064`."""
    environ = os.environ if env is None else env
    value = environ.get("DATABASE_PATH", "")
    return value or os.path.join(account_dir(env), "account.db")


def db_preferred_port(env: dict[str, str] | None = None) -> int:
    """`.ci/lib/account.sh:1074-1097`: this worktree's devbox studio slot, else 4983.

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
    """`.ci/lib/account.sh:1122-1137`, resolution only; the `uv` install is in `db_launch`.

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
    if not check_node_version():
        # The twin's bare `check_node_version` under `errexit` aborts the function.
        raise AccountError("node version check failed", code=1)
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
    """`account_db`'s tail, `.ci/lib/account.sh:1106-1143`. NOT differentially proved.

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
            # S104: `0.0.0.0` is an ARGUMENT to another program here, copied from the twin at `.ci/lib/account.sh:1118`, not a bind in this process.
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
    argv = [binary, "--host", "0.0.0.0", "--port", str(plan.port), "--no-browser", plan.database]  # noqa: S104 -- the twin's own literal argument at `.ci/lib/account.sh:1142`
    os.execv(binary, argv)  # noqa: S606 -- forwarding exec, same shape as the twin's
    raise AssertionError("execv returned")  # pragma: no cover


def db(argv: list[str], env: dict[str, str] | None = None) -> int:
    """`account_db`, `.ci/lib/account.sh:1047-1143`."""
    try:
        plan = db_plan(argv, env)
    except AccountError as exc:
        return exc.code
    return db_launch(plan, env)


# --------------------------------------------------------------------------- argv ---------------------------------------------------------------------------

USAGE = """rediacc_ci.core.account -- the deterministic half of .ci/lib/account.sh

  totp [email]      print the running dev gateway's TOTP code for a dev user
  db [--studio]     browse the dev database

The dev, stop, test, reset and seed-demo verbs are NOT here: they live in
.ci/lib/account.sh and start long-running infrastructure. See the module
docstring for why they are a separate slice."""


def main(argv: list[str]) -> int:
    """The two public account verbs this slice covers."""
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
    log.error("Unknown account command: %s" % verb)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
