"""Headless login of the eu-bench config into the bench origin (`BENCH_ORIGIN`) with the operator's own bench account.

    npm run login:bench
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.login_bench [--server URL] [--config NAME]

BENCH ONLY (operator order 2026-10-27). The run refuses, with a named error and exit 2, any server other than the bench origin (`BENCH_ORIGIN`) and any rdc config other than eu-bench, before it reads a credential. Edge and stable keep human login; no profile binds an account for them.

THE STEPS, in order:

  1. Re-execute under the `bench-login` Bitwarden profile (`rediacc_ci.core.bws_env exec`), unless it is already bound. The profile binds REDIACC_BENCH_EMAIL, REDIACC_BENCH_PASSWORD, REDIACC_BENCH_TOTP_SEED and REDIACC_BENCH_MASTER_PASSWORD.
  2. Refuse a value that is unset or still the placeholder `PLACEHOLDER-operator-fills`, naming its Bitwarden entry, before anything else runs.
  3. Refresh the bench IP allowlist (`rediacc_ci.ops.bench_access add-current`, which binds its own `bench-access` profile). The four bench values are removed from that child's environment.
  3b. Probe the account with its own password login (`POST /auth/login`, the same route the CLI uses). Three outcomes:
      - A TOTP challenge: the code from the seed is spent on `POST /auth/2fa/verify`; a first refusal is retried once with the next window's code (the account refuses a code already spent, so a second run inside one window is refused with a good seed), and a second refusal is the STALE-SEED refusal (TOTP is on but the seed in `REDIACC_BENCH_TOTP_SEED` is not the one the account holds, because the mirror cleared it and it was re-enrolled elsewhere), a LoginError that names the remedy and does not retry again.
      - No challenge, because TOTP is off (`mirror_config_store` copies the operator row with TOTP cleared, since `users.totp_secret` is sealed per Worker): the run RE-ENROLS through the account's own API with the session the probe just opened. `POST /auth/2fa/setup` and `/auth/2fa/enable` need an elevated session, and the only headless elevation is the reauth mail: `POST /auth/reauth`, the link read from the bench D1 `captured_emails` (kind `reauth`, a child under `bws_env exec --profile deploy-bench` that prints only the token to this process), `POST /auth/reauth/verify`. The new seed is written to Bitwarden as `REDIACC_BENCH_TOTP_SEED` (`bws_env store-from-env`, the value on the writer's stdin, never argv) BEFORE `/auth/2fa/enable`, so a failed write leaves TOTP off and the next run enrols again, never an enabled account whose seed was lost. The backup codes the enable answers are dropped unread.
  3c. In the same session, accept the current Terms of Service when the account's acceptance does not satisfy them (`GET`/`POST /portal/terms[/accept]`, the version and digest the server reports; operator ruling ASKED:2026-11-11T17:38Z, bench only).
  4. Compute the six-digit TOTP code in memory (`rediacc_ci.ops.totp`), waiting for the next 30 s window when fewer than `MIN_WINDOW_LEFT` seconds remain, then run `./rdc.sh --config eu-bench subscription login --server <BENCH_ORIGIN>` with REDIACC_LOGIN_EMAIL, REDIACC_LOGIN_PASSWORD and REDIACC_LOGIN_TOTP in the child environment.
  5. Always run `./rdc.sh --config eu-bench config remote enable --master-password --config-id <CONFIG_ID> --api-url <BENCH_ORIGIN>` with REDIACC_STORE_MASTER_PASSWORD in the child environment; `config remote status` is not consulted, because it reports "connected" even when this device has lost its key for the store (the Linux kernel keyring is empty after a restart; measured 2026-11-10). Exit 0 is done: a first link, or this device enrolled again against the same store. Exit 2 is done only when the output says the config is linked and this device can already open it (the CLI's "this device can open it, so there is nothing to enable" refusal); any other failure exits 1 naming the step.
  6. Print `./rdc.sh --config eu-bench config remote status`.

WHOSE STEP IT IS. Running this is an agent's own step, never an operator one: when an eu-bench command answers that its login is "tied to another network address", that the IP address changed, or "Not logged in", the remedy is `npm run login:bench` and a rerun, not a request for an authenticator code. `rediacc_ci.ops.live_proof` does that itself (`login_needed`, `targets_config`, `REMEDY_ARGV`).

SECRETS. Every value travels by name in a child's environment: never on argv, never printed, never logged. Each `rdc` child gets only the values its own step needs, and `RDC_DEV`, `REDIACC_CONFIG`, `REDIACC_TOKEN` and `REDIACC_ACCOUNT_SERVER` are dropped from it, so an inherited dev selection cannot redirect the login to another server or config. A failed step exits 1 naming the step.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit

from rediacc_ci import log, paths
from rediacc_ci.core import wrangler
from rediacc_ci.ops import deploy_bench, totp
from rediacc_ci.well_known import BENCH_ORIGIN

PROFILE = "bench-login"
SERVER = BENCH_ORIGIN
CONFIG = "eu-bench"
# Every CLI config name that reaches bench, and the one place a consumer reads it from (ops_health's bench hint, the post-bash bench hint `.claude/hooks/stop/wl_benchblock.py`): this script's own config and rdc.sh's `./rdc.sh --config bench <cmd>`.
BENCH_CONFIGS = (CONFIG, "bench")
CONFIG_ID = "1880812c-2086-4daa-a620-8f84aa3b6e7c"
PLACEHOLDER = "PLACEHOLDER-operator-fills"
MIN_WINDOW_LEFT = 5

EMAIL_ENV = "REDIACC_BENCH_EMAIL"
PW_ENV = "REDIACC_BENCH_PASSWORD"
TOTP_SEED_ENV = "REDIACC_BENCH_TOTP_SEED"
MASTER_PW_ENV = "REDIACC_BENCH_MASTER_PASSWORD"
SOURCE_NAMES = (EMAIL_ENV, PW_ENV, TOTP_SEED_ENV, MASTER_PW_ENV)

# The names the CLI reads (packages/cli/src/services/account/subscription-password-auth.ts, packages/cli/src/commands/config-remote-master-password.ts).
LOGIN_EMAIL_ENV = "REDIACC_LOGIN_EMAIL"
LOGIN_PW_ENV = "REDIACC_LOGIN_PASSWORD"
LOGIN_TOTP_ENV = "REDIACC_LOGIN_TOTP"
# The CLI refusal for a config that is linked and whose device can open it (no distinct error code exists).
# packages/cli/src/i18n/locales/en/cli.json `commands.config.remote.enable.alreadyEnabled`, with {{name}} as the quoted config name.
ENABLE_ALREADY_OPEN = re.compile(
    r'Config "[^"]+" is already linked to remote storage and this device can open it, so there is nothing to enable\.'
)
# The CLI refusal carries no error code, so its text is matched; the child's language is pinned to the English catalogue the template comes from (packages/cli/src/i18n/config.ts and config-base.ts `getLanguage` read this variable first).
CLI_LANG_ENV = "REDIACC_LANG"
CLI_LANG = "en"
CLI_STORE_MASTER_PW_ENV = "REDIACC_STORE_MASTER_PASSWORD"
CHILD_SECRET_NAMES = (
    *SOURCE_NAMES,
    LOGIN_EMAIL_ENV,
    LOGIN_PW_ENV,
    LOGIN_TOTP_ENV,
    CLI_STORE_MASTER_PW_ENV,
)
# Inherited selections that would point `./rdc.sh` somewhere other than eu-bench on bench.
SCRUBBED_SELECTORS = ("RDC_DEV", "REDIACC_CONFIG", "REDIACC_TOKEN", "REDIACC_ACCOUNT_SERVER")

TOTP_SEED_NEW_ENV = "REDIACC_BENCH_TOTP_SEED_NEW"
API_PATH = "/account/api/v1/auth/"
HTTP_TIMEOUT_S = 30
# `<base>/account/reauth/verify?token=<raw>` (AuthService.createReauthToken).
REAUTH_TOKEN = re.compile(r"reauth/verify\?token=([A-Za-z0-9_\-]+)")
TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_\-]+")
MAIL_ATTEMPTS = 6
MAIL_WAIT_S = 3.0
CLOCK_SKEW = timedelta(seconds=60)
MAIL_MODE = "--mail-token"
MAIL_QUERY = (
    "SELECT text_body FROM captured_emails WHERE recipient = %s AND kind = 'reauth' "
    "AND created_at >= %s ORDER BY created_at DESC LIMIT 1"
)
D1_PROFILE = "deploy-bench"

USAGE = "usage: login_bench [--server %s] [--config %s]" % (SERVER, CONFIG)

# THE LOGIN IS THE AGENT'S OWN STEP (operator order 2026-10-30). When an eu-bench command fails because the login is tied to another network address, the CLI tells a human to type an authenticator code in a terminal; an agent read that as an operator step and asked for the code. This run is the remedy, so callers that drive eu-bench (`rediacc_ci.ops.live_proof`) run it once and retry.
REMEDY = "npm run login:bench"
REMEDY_ARGV = ("npm", "run", "--silent", "login:bench")
# What the CLI prints for a login bound to another IP (packages/cli/src/i18n/locales/en/cli.json `loginIpMismatch`, `errors.subscription.ipRebind.nonInteractive` and `reloginOnly`), and for no login at all (`errors.subscription.notLoggedIn`). `.claude/hooks/trapguard/dispatch.py` keeps a copy it cannot import.
LOGIN_NEEDED_MARKERS = (
    "tied to another network address",
    "Your IP address changed",
    "this login only works from the old one",
    "Not logged in. Humans should run",
)


def login_needed(text: str) -> bool:
    """True when `text` is the CLI saying the login must be redone or moved, which `npm run login:bench` does for eu-bench."""
    return any(marker in text for marker in LOGIN_NEEDED_MARKERS)


def targets_config(argv: Sequence[str]) -> bool:
    """True when `argv` is an rdc run against the eu-bench config (`--config eu-bench` or `--config=eu-bench`)."""
    args = list(argv)
    return any(
        (a == "--config" and i + 1 < len(args) and args[i + 1] == CONFIG)
        or a == "--config=" + CONFIG
        for i, a in enumerate(args)
    )


Runner = Callable[[Sequence[str], Mapping[str, str]], int]
Capture = Callable[[Sequence[str], Mapping[str, str]], tuple[int, str]]


class LoginError(RuntimeError):
    """A refusal or a failed step; `rc` is the exit status. The message never carries a secret."""

    def __init__(self, message: str, rc: int = 1):
        super().__init__(message)
        self.rc = rc


def _bws_entry(name: str) -> str:
    """`NAME (<uuid>)` from the vault map, for a refusal that names the entry to fill."""
    try:
        secrets = json.loads(
            paths.from_root(".ci", "config", "bws-secret-map.json").read_text(encoding="utf-8")
        )["secrets"]
        return "%s (%s)" % (name, secrets[name]["id"])
    except (OSError, ValueError, KeyError):
        return name


def parse_args(argv: Sequence[str]) -> tuple[str, str]:
    """(server, config). Anything but bench and eu-bench is a LoginError with rc 2."""
    server, config = SERVER, CONFIG
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg in ("--server", "--config") and rest:
            value = rest.pop(0)
        elif arg.startswith(("--server=", "--config=")):
            arg, value = arg.split("=", 1)
        else:
            raise LoginError("%s (unexpected argument %r)" % (USAGE, arg), rc=2)
        if arg == "--server":
            server = value
        else:
            config = value
    if server.rstrip("/") != SERVER:
        raise LoginError(
            "login:bench refuses server %r: it logs in to %s only; edge and stable keep human login"
            % (server, SERVER),
            rc=2,
        )
    if config != CONFIG:
        raise LoginError(
            "login:bench refuses config %r: it writes the %s config only" % (config, CONFIG), rc=2
        )
    return SERVER, CONFIG


def read_values(env: Mapping[str, str]) -> dict[str, str]:
    """The four bench values; a missing one or the placeholder is a LoginError (rc 2) naming the Bitwarden entry."""
    values: dict[str, str] = {}
    for name in SOURCE_NAMES:
        value = env.get(name) or ""
        if not value.strip():
            raise LoginError(
                "%s is not set: run under `bws_env exec --profile %s` (npm run login:bench does)"
                % (_bws_entry(name), PROFILE),
                rc=2,
            )
        if value.strip() == PLACEHOLDER:
            raise LoginError(
                "%s still holds the placeholder %r: the operator fills that Bitwarden entry first"
                % (_bws_entry(name), PLACEHOLDER),
                rc=2,
            )
        values[name] = value.strip()
    try:
        totp.decode_seed(values[TOTP_SEED_ENV])
    except totp.TotpError as exc:
        raise LoginError("%s: %s" % (_bws_entry(TOTP_SEED_ENV), exc), rc=2) from None
    return values


def base_env(env: Mapping[str, str]) -> dict[str, str]:
    """The inherited environment with every bench secret and every config or server selector removed."""
    child = {k: v for k, v in env.items() if k not in CHILD_SECRET_NAMES}
    for name in SCRUBBED_SELECTORS:
        child.pop(name, None)
    return child


def fresh_code(
    seed: str, now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep
) -> str:
    """The current TOTP code, taken from the next window when the current one is about to close."""
    left = totp.STEP - (now() % totp.STEP)
    if left < MIN_WINDOW_LEFT:
        sleep(left + 0.5)
    return totp.code(seed, at=now())


class Poster(Protocol):
    def post(self, route: str, body: dict | None = None) -> tuple[int, dict]: ...

    def get(self, route: str) -> tuple[int, dict]: ...


class AccountApi:
    """The bench account's `/auth` routes under one cookie store: the probe login opens the session the enrolment then uses. `post` returns (HTTP status, decoded object); the passwords, tokens and seeds it carries are never printed."""

    def __init__(self, server: str):
        parts = urlsplit(server)
        self.host = parts.netloc
        self.base = API_PATH
        self.cookies: dict[str, str] = {}

    def post(self, route: str, body: dict | None = None) -> tuple[int, dict]:
        return self._call("POST", route, json.dumps(body or {}))

    def get(self, route: str) -> tuple[int, dict]:
        return self._call("GET", route, None)

    def _call(self, method: str, route: str, payload: str | None) -> tuple[int, dict]:
        """`route` is under `/auth/`, or an absolute API path when it starts with `/` (the portal Terms routes)."""
        headers = {"Content-Type": "application/json"}
        if self.cookies:
            headers["Cookie"] = "; ".join("%s=%s" % kv for kv in self.cookies.items())
        path = route if route.startswith("/") else self.base + route
        conn = http.client.HTTPSConnection(self.host, timeout=HTTP_TIMEOUT_S)
        try:
            conn.request(method, path, payload, headers)
            resp = conn.getresponse()
            status, raw = resp.status, resp.read()
            for header in resp.headers.get_all("Set-Cookie") or []:
                name, _, rest = header.partition("=")
                self.cookies[name.strip()] = rest.partition(";")[0]
        except OSError as exc:
            raise LoginError(
                "%s %s reached no answer (%s)" % (method, path, type(exc).__name__)
            ) from None
        finally:
            conn.close()
        try:
            decoded = json.loads(raw)
        except ValueError:
            decoded = {}
        return status, decoded if isinstance(decoded, dict) else {}


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _d1_rows(sql: str) -> list[dict]:
    """`wrangler d1 execute` against the bench D1 with the Global API Key pair the deploy-bench profile binds; stdout is never printed (it holds live links)."""
    key, mail = os.environ.get("CF_GLOBAL_API_KEY"), os.environ.get("CF_EMAIL")
    if not (key and mail):
        raise LoginError("CF_GLOBAL_API_KEY and CF_EMAIL are required to read the captured email")
    env = dict(os.environ)
    for name in ("CLOUDFLARE_API_TOKEN", "CF_API_KEY"):
        env.pop(name, None)
    env["CLOUDFLARE_API_KEY"], env["CLOUDFLARE_EMAIL"] = key, mail
    env["CLOUDFLARE_ACCOUNT_ID"] = deploy_bench.ACCOUNT_ID
    argv = [
        *wrangler.ARGV,
        "d1",
        "execute",
        deploy_bench.DB_NAME,
        "--remote",
        "--config",
        deploy_bench.CONFIG,
        "--json",
        "--command",
        sql,
    ]
    proc = subprocess.run(
        argv,
        cwd=str(paths.repo_root() / "workers" / "account"),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise LoginError("wrangler d1 execute failed (exit %d)" % proc.returncode)
    try:
        rows = json.loads(proc.stdout)[0]["results"]
    except (ValueError, LookupError, TypeError):
        raise LoginError("wrangler d1 execute printed no result rows") from None
    return [r for r in rows if isinstance(r, dict)]


def mail_token_main(email: str, since: str) -> int:
    """`--mail-token`, run under the deploy-bench profile: print the newest reauth token mailed to `email` since `since` (and nothing else), or exit 1. The stdout is read by the parent process only."""
    sql = MAIL_QUERY % (_sql_literal(email), _sql_literal(since))
    for attempt in range(MAIL_ATTEMPTS):
        if attempt:
            time.sleep(MAIL_WAIT_S)
        for row in _d1_rows(sql):
            found = REAUTH_TOKEN.search(str(row.get("text_body") or ""))
            if found:
                print(found.group(1))
                return 0
    return 1


def _with_ci_path(env: Mapping[str, str]) -> dict[str, str]:
    child = dict(env)
    ci = str(paths.repo_root() / ".ci")
    child["PYTHONPATH"] = ci + (os.pathsep + child["PYTHONPATH"] if child.get("PYTHONPATH") else "")
    return child


def _mail_token(email: str, since: str, env: Mapping[str, str], capture: Capture) -> str:
    """The reauth token from bench's captured mail, through a child under the deploy-bench profile."""
    child = _with_ci_path(env)
    child[EMAIL_ENV] = email
    rc, out = capture(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "exec",
            "--profile",
            D1_PROFILE,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.login_bench",
            MAIL_MODE,
            since,
        ],
        child,
    )
    token = out.strip()
    if rc != 0 or not TOKEN_SHAPE.fullmatch(token):
        raise LoginError(
            "no reauth mail for the bench account reached captured_emails (exit %d)" % rc
        )
    return token


def distinct_code(
    seed: str,
    avoid: str | None,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """The current code, taken from a later window when it equals `avoid` (the account refuses a spent code)."""
    started = now()
    code = fresh_code(seed, now, sleep)
    if avoid is None or code != avoid:
        return code
    left = totp.STEP - (started % totp.STEP)
    sleep(left + 0.5)
    return totp.code(seed, at=started + left + 0.5)


def reenrol(
    api: Poster,
    email: str,
    env: Mapping[str, str],
    capture: Capture,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, str]:
    """Turn TOTP on for the bench account and store the new seed. Returns (seed, the code `enable` spent). The session in `api` is the one the probe login opened."""
    since = (datetime.fromtimestamp(now(), UTC) - CLOCK_SKEW).strftime("%Y-%m-%dT%H:%M:%S")
    status, _ = api.post("reauth")
    if status != 200:
        raise LoginError("POST /auth/reauth answered HTTP %d" % status)
    token = _mail_token(email, since, env, capture)
    status, _ = api.post("reauth/verify", {"token": token})
    if status != 200:
        raise LoginError("POST /auth/reauth/verify answered HTTP %d" % status)
    status, answer = api.post("2fa/setup")
    secret = answer.get("secret")
    if status != 200 or not isinstance(secret, str) or not secret:
        raise LoginError("POST /auth/2fa/setup answered HTTP %d with no secret" % status)
    try:
        totp.decode_seed(secret)
    except totp.TotpError as exc:
        raise LoginError("POST /auth/2fa/setup answered an unusable secret: %s" % exc) from None
    # Stored first: a failed write leaves TOTP off, so the next run enrols again.
    write_env = _with_ci_path(env)
    write_env[TOTP_SEED_NEW_ENV] = secret
    log.step("Storing the new TOTP seed as %s (bws_env store-from-env)" % TOTP_SEED_ENV)
    rc, out = capture(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "store-from-env",
            "%s > %s" % (TOTP_SEED_ENV, TOTP_SEED_NEW_ENV),
        ],
        write_env,
    )
    if rc != 0:
        raise LoginError(
            "writing %s to Bitwarden failed (exit %d); TOTP stays off on the account"
            % (_bws_entry(TOTP_SEED_ENV), rc)
        )
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    code = fresh_code(secret, now, sleep)
    status, _ = api.post("2fa/enable", {"code": code})
    if status != 200:
        raise LoginError(
            "POST /auth/2fa/enable answered HTTP %d; the new seed is already stored, so a rerun "
            "enrols again" % status
        )
    return secret, code


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    return subprocess.run(
        list(argv), env=dict(env), cwd=str(paths.repo_root()), check=False
    ).returncode


def _subprocess_capture(argv: Sequence[str], env: Mapping[str, str]) -> tuple[int, str]:
    proc = subprocess.run(
        list(argv),
        env=dict(env),
        cwd=str(paths.repo_root()),
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout or ""


def enable_settled(rc: int, out: str) -> bool:
    """True when `config remote enable` left this device able to open the store: exit 0 (enrolled, or enrolled again after the device lost its key), or exit 2 with the CLI's refusal that the config is linked and this device can already open it. The refusal is a plain ValidationError with no distinct error code (packages/cli/src/commands/config-remote.ts, `commands.config.remote.enable.alreadyEnabled`), so its text is the only handle."""
    return rc == 0 or (rc == 2 and any(ENABLE_ALREADY_OPEN.search(m) for m in _error_messages(out)))


def _is_json(out: str) -> bool:
    try:
        json.loads(out)
    except ValueError:
        return False
    return True


def _error_messages(out: str) -> list[str]:
    """errors[].message of a JSON envelope on stdout; nothing when stdout is not one, so plain text never counts as the refusal."""
    try:
        envelope = json.loads(out)
    except ValueError:
        return []
    errors = envelope.get("errors") if isinstance(envelope, dict) else None
    if not isinstance(errors, list):
        return []
    return [
        e["message"] for e in errors if isinstance(e, dict) and isinstance(e.get("message"), str)
    ]


def _rdc(config: str, *args: str) -> list[str]:
    return [str(paths.repo_root() / "rdc.sh"), "--config", config, *args]


def _step(run: Runner, label: str, argv: Sequence[str], env: Mapping[str, str]) -> None:
    log.step(label)
    rc = run(argv, env)
    if rc != 0:
        raise LoginError("%s failed (exit %d)" % (label, rc), rc=1)


TERMS_STATUS = "/account/api/v1/portal/terms"
TERMS_ACCEPT = "/account/api/v1/portal/terms/accept"


def accept_terms(account: Poster) -> None:
    """Accept the current Terms of Service for the bench account when its acceptance does not satisfy them, in the session the probe opened.

    Operator ruling ASKED:2026-11-11T17:38Z, "Agents use the flag on bench": agents accept the Terms on bench only, and this module refuses every other server before it reads a credential. A registered account accepts only through the portal route (`RDC_ACCEPT_TERMS=1` does not reach `repo create`), and the mirror and a fresh version both leave the bench account unaccepted, after which every eu-bench `repo create` is refused. The acceptance names the version and digest the server itself reports as current, so it never accepts a text the server does not publish.
    """
    status, answer = account.get(TERMS_STATUS)
    if status != 200:
        raise LoginError(
            "GET %s answered HTTP %d: the Terms status is unreadable" % (TERMS_STATUS, status)
        )
    satisfied = answer.get("satisfied")
    if not isinstance(satisfied, bool):
        raise LoginError(
            "GET %s answered no boolean `satisfied`: the Terms status is unreadable" % TERMS_STATUS
        )
    if satisfied:
        log.step("The bench account's Terms acceptance satisfies the current version")
        return
    current = answer.get("current") or {}
    version, digest = current.get("version"), current.get("sha256")
    if not isinstance(version, str) or not isinstance(digest, str):
        raise LoginError("GET %s named no current version and digest" % TERMS_STATUS)
    log.step(
        "Accepting the Terms of Service %s for the bench account (operator ruling 2026-11-11)"
        % version
    )
    status, _ = account.post(
        TERMS_ACCEPT,
        {"version": version, "sha256": digest, "locale": "en", "method": "web-checkbox"},
    )
    # The route answers 201 Created for a recorded acceptance (measured on bench 2026-11-12).
    if status not in (200, 201):
        raise LoginError(
            "POST %s answered HTTP %d: the acceptance was refused" % (TERMS_ACCEPT, status)
        )
    # The status is read again, so an answer that recorded nothing never passes as an acceptance.
    status, answer = account.get(TERMS_STATUS)
    if status != 200:
        raise LoginError(
            "POST %s answered but the re-read GET %s answered HTTP %d"
            % (TERMS_ACCEPT, TERMS_STATUS, status)
        )
    reread = (answer.get("current") or {}).get("version")
    if answer.get("satisfied") is not True or reread != version:
        raise LoginError(
            "POST %s answered but GET %s does not report version %s satisfied (it reports %r)"
            % (TERMS_ACCEPT, TERMS_STATUS, version, reread)
        )


def login(
    argv: Sequence[str],
    env: Mapping[str, str],
    run: Runner = _subprocess_runner,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    capture: Capture = _subprocess_capture,
    api: Poster | None = None,
) -> None:
    """Steps 2-6 of the module docstring, with the profile already bound. Raises LoginError."""
    server, config = parse_args(argv)
    values = read_values(env)
    clean = base_env(env)

    ci = str(paths.repo_root() / ".ci")
    access_env = dict(clean)
    access_env["PYTHONPATH"] = ci + (
        os.pathsep + access_env["PYTHONPATH"] if access_env.get("PYTHONPATH") else ""
    )
    _step(
        run,
        "Refreshing the bench IP allowlist (bench_access add-current)",
        [sys.executable, "-m", "rediacc_ci.ops.bench_access", "add-current"],
        access_env,
    )

    log.step("Probing the bench account's two-factor state (POST /auth/login)")
    account = api if api is not None else AccountApi(server)
    status, answer = account.post("login", {"email": values[EMAIL_ENV], "password": values[PW_ENV]})
    if status != 200:
        raise LoginError(
            "POST /auth/login answered HTTP %d: the bench password was refused" % status
        )
    seed = values[TOTP_SEED_ENV]
    challenge = answer.get("challengeToken")
    if answer.get("requiresTwoFactor") and isinstance(challenge, str):
        spent = fresh_code(seed, now, sleep)
        status, _ = account.post("2fa/verify", {"challengeToken": challenge, "code": spent})
        if status != 200:
            # The account refuses a code it already spent (replay protection), so a run inside
            # the window of an earlier run is refused with a good seed. The challenge survives a
            # refused verify (it only counts an attempt), so wait for the next window and retry once.
            refused = status
            asked = now()
            left = totp.STEP - (asked % totp.STEP)
            log.step(
                "The code was refused (HTTP %d); retrying once with the next window's code"
                % refused
            )
            sleep(left + 0.5)
            spent = totp.code(seed, at=asked + left + 0.5)
            status, _ = account.post("2fa/verify", {"challengeToken": challenge, "code": spent})
        if status != 200:
            raise LoginError(
                "TOTP is on for the bench account but the code from %s was refused in two "
                "consecutive 30 s windows (HTTP %d, then HTTP %d): the seed is stale, most likely "
                "because the mirror cleared TOTP and it was enrolled again elsewhere. Clear "
                "totp_secret, totp_backup_hashes and totp_enabled on the bench user (or disable 2FA "
                "with a backup code) and rerun to enrol a fresh seed; not retrying."
                % (_bws_entry(TOTP_SEED_ENV), refused, status)
            )
    else:
        log.step("TOTP is off on the bench account: enrolling a new seed")
        seed, spent = reenrol(account, values[EMAIL_ENV], clean, capture, now, sleep)

    accept_terms(account)

    login_env = dict(clean)
    login_env[LOGIN_EMAIL_ENV] = values[EMAIL_ENV]
    login_env[LOGIN_PW_ENV] = values[PW_ENV]
    login_env[LOGIN_TOTP_ENV] = distinct_code(seed, spent, now, sleep)
    _step(
        run,
        "Logging %s in to %s (subscription login)" % (config, server),
        _rdc(config, "subscription", "login", "--server", server),
        login_env,
    )

    enable_env = dict(clean)
    enable_env[CLI_LANG_ENV] = CLI_LANG
    enable_env[CLI_STORE_MASTER_PW_ENV] = values[MASTER_PW_ENV]
    log.step("Enabling the remote config store (config remote enable)")
    enable_rc, enable_out = capture(
        _rdc(
            config,
            "-o",
            "json",
            "config",
            "remote",
            "enable",
            "--master-password",
            "--config-id",
            CONFIG_ID,
            "--api-url",
            server,
        ),
        enable_env,
    )
    if enable_out:
        print(enable_out, end="" if enable_out.endswith("\n") else "\n")
    if not enable_settled(enable_rc, enable_out):
        detail = ""
        if enable_rc == 2 and not _is_json(enable_out):
            detail = "; stdout was not a JSON envelope: %r" % enable_out[:300]
        raise LoginError(
            "Enabling the remote config store (config remote enable) failed (exit %d)%s"
            % (enable_rc, detail),
            rc=1,
        )

    _step(
        run,
        "Remote config store status",
        _rdc(config, "config", "remote", "status"),
        dict(clean),
    )
    log.success("%s is logged in to %s" % (config, server))


def _reexec_under_profile(argv: Sequence[str], run: Runner) -> int | None:
    """This entry point under the bench-login profile; None when the profile is already bound."""
    if PROFILE in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(","):
        return None
    env = dict(os.environ)
    ci = str(paths.repo_root() / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return run(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "exec",
            "--profile",
            PROFILE,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.login_bench",
            *argv,
        ],
        env,
    )


def main(argv: Sequence[str] | None = None, run: Runner = _subprocess_runner) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == MAIL_MODE:
        email = os.environ.get(EMAIL_ENV) or ""
        return mail_token_main(email, args[1]) if email else 2
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    try:
        # The bench-only refusal runs before the profile is entered, so a wrong target never reads a credential.
        parse_args(args)
        rebound = _reexec_under_profile(args, run)
        if rebound is not None:
            return rebound
        login(args, os.environ, run)
    except LoginError as exc:
        log.error(str(exc))
        return exc.rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
