"""Headless root-admin access to the production account Workers (stable and edge), by root API token.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target stable|edge --region eu \
        [--check | --probe stats|audit | --control | --rotate | --password]

WHY. Stable and edge share ONE production root (operator ruling 2026-11-15) and there is no separate stable Worker set (`docs/agent-reference/release-process.md`), so both targets resolve to the same origin, `https://<regions.json domain>`; the target stays in the command so a caller says which channel it means. The password sign-in `/auth/login` answers 400 "Captcha verification required" there, so the default is the root API token kind (`PLAN-root-api-token.md` Design 1-3): the operator mints `ROOT_API_TOKEN` once in the portal, and every use proves TOTP through a short token session. The bench root has its own credentials and tool (`rediacc_ci.ops.login_bench`).

THE STEPS of the default mode, in order:

  1. Re-execute under the `root-login` Bitwarden profile (`rediacc_ci.core.bws_env exec`), unless it is already bound. The profile binds ROOT_API_TOKEN and ROOT_TOTP_SEED.
  2. Refuse a value that is unset, still the placeholder `PLACEHOLDER-operator-fills`, or (for the token) not starting `rdr_`, naming its Bitwarden entry, before any request.
  3. `POST /admin/root-token/session` with the bearer token and a six-digit code derived in memory from the seed (`rediacc_ci.ops.totp`).
  4. On 403 `ROOT_TOKEN_IP_MISMATCH` (the nightly address change): `POST /admin/root-token/bind` with a code, wait for the next 30 s step (the account spends a code once), then `session` again; `ip rebound (<family>)` is printed.
  5. A code refused (`TOTP_INVALID` or `TOTP_REPLAYED`) is retried once with the next window's code; a second refusal is a named failure with no third try. A 429 or 5xx is a fault, not a refusal.
  6. Print `root session opened (<target> <region>, token, session until HH:MMZ, token expires in N days)`.

FLAGS. `--check` makes no request: it validates the vault values and the seed. `--probe stats|audit` makes one read-only GET from a fixed allowlist. `--control` proves two refusals live: the session-less call answers 403 `ROOT_TOKEN_SESSION_REQUIRED`, and `/auth/login` without a captcha token still answers 400 "Captcha verification required". `--rotate` (or `ROOT_LOGIN_AUTOROTATE=1` with fewer than 14 days left) calls `rotate` and writes the successor to the same Bitwarden entry. `--password` is the older sign-in with ROOT_EMAIL, ROOT_PASSWORD and the seed, kept for an origin that does not demand a captcha.

REGIONS. Tokens live in one regional database, so `ROOT_API_TOKEN` is the eu token; `us` and `asia` are refused until `ROOT_API_TOKEN_<SUFFIX>` exists (Q1).

Nothing here is a Turnstile workaround: where `/auth/login` demands a captcha token the answer is the named refusal, never a bypass.

SECRETS. The token, password, seed, every code and every session cookie stay in memory: none is put on argv, printed or logged (the rotation hands the successor to the vault writer through its child environment only). Exit 0 success, 1 a refusal or failed step, 2 a refusal before any request (usage, missing value).
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import NamedTuple
from urllib.parse import urlsplit

from rediacc_ci import log, paths
from rediacc_ci.ops import login_bench, totp

PROFILE = "root-login"
TARGETS = ("stable", "edge")
REGIONS = ("eu", "us", "asia")
EMAIL_ENV = "ROOT_EMAIL"
PW_ENV = "ROOT_PASSWORD"
SEED_ENV = "ROOT_TOTP_SEED"
VAULT_ENTRY = "ROOT_API_TOKEN"
VAULT_ENTRY_NEW = "ROOT_API_TOKEN_NEW"
AUTOROTATE_ENV = "ROOT_LOGIN_AUTOROTATE"
SOURCE_NAMES = (EMAIL_ENV, PW_ENV, SEED_ENV)
VALUE_PREFIX = "rdr_"
PLACEHOLDER = "PLACEHOLDER-operator-fills"
API_ROOT = "/account/api/v1"
API_PATH = API_ROOT + "/auth/"
HTTP_TIMEOUT_S = 30
MIN_WINDOW_LEFT = 5
ROTATE_BELOW_DAYS = 14
# Read-only calls `--probe` may make: a fixed allowlist, GET only.
PROBES = {
    "stats": "/admin/stats",
    "audit": "/admin/activity?type=root_token.session_opened,root_token.call,root_token.ip_bound&pageSize=5",
}
CAPTCHA_REFUSAL = "Captcha verification required"
USAGE = (
    "usage: root_login --target %s --region %s [--check | --probe %s | --control | --rotate | --password]"
    % ("|".join(TARGETS), "|".join(REGIONS), "|".join(PROBES))
)

Runner = Callable[[Sequence[str], Mapping[str, str]], int]


class RootLoginError(RuntimeError):
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


class Options(NamedTuple):
    target: str
    region: str
    check: bool = False
    probe: str = ""
    control: bool = False
    rotate: bool = False
    password: bool = False


def parse_args(argv: Sequence[str]) -> Options:
    """The parsed command; RootLoginError rc 2 for anything else."""
    args = list(argv)
    found: dict[str, str] = {}
    switches: set[str] = set()
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in ("--target", "--region", "--probe") and i + 1 < len(args):
            found[flag[2:]] = args[i + 1]
            i += 2
        elif flag in ("--check", "--control", "--rotate", "--password"):
            switches.add(flag[2:])
            i += 1
        else:
            raise RootLoginError("unknown argument %r\n%s" % (flag, USAGE), rc=2)
    target, region = found.get("target", ""), found.get("region", "")
    if target not in TARGETS:
        raise RootLoginError("--target must be one of %s\n%s" % (", ".join(TARGETS), USAGE), rc=2)
    if region not in REGIONS:
        raise RootLoginError("--region must be one of %s\n%s" % (", ".join(REGIONS), USAGE), rc=2)
    probe = found.get("probe", "")
    if probe and probe not in PROBES:
        raise RootLoginError("--probe must be one of %s\n%s" % (", ".join(PROBES), USAGE), rc=2)
    if len(switches) + (1 if probe else 0) > 1:
        raise RootLoginError(
            "--check, --probe, --control, --rotate and --password exclude each other\n%s" % USAGE,
            rc=2,
        )
    return Options(
        target,
        region,
        check="check" in switches,
        probe=probe,
        control="control" in switches,
        rotate="rotate" in switches,
        password="password" in switches,
    )


def token_entry(region: str) -> str:
    """The vault name holding the token of `region`: `ROOT_API_TOKEN` for eu (Q1); another region is refused with the name its token would take."""
    if region == "eu":
        return VAULT_ENTRY
    rows = json.loads(paths.from_root("regions.json").read_text(encoding="utf-8"))["regions"]
    suffix = next((str(r["secretSuffix"]) for r in rows if str(r["id"]) == region), region.upper())
    raise RootLoginError(
        "no root token for region %s: mint one on %s.rediacc.cloud and store it as %s_%s"
        % (region, region, VAULT_ENTRY, suffix),
        rc=2,
    )


def origin_for(target: str, region: str) -> str:
    """The account origin of a production region: `https://<regions.json domain>`, the same for stable and edge."""
    if target not in TARGETS:
        raise RootLoginError("target %r is not one of %s" % (target, ", ".join(TARGETS)), rc=2)
    rows = json.loads(paths.from_root("regions.json").read_text(encoding="utf-8"))["regions"]
    for row in rows:
        if str(row["id"]) == region:
            return "https://%s" % row["domain"]
    raise RootLoginError("no region %r in regions.json" % region, rc=2)


def read_values(env: Mapping[str, str]) -> dict[str, str]:
    """The three root values, each refused when unset or still the placeholder, naming its vault entry."""
    values: dict[str, str] = {}
    for name in SOURCE_NAMES:
        value = env.get(name) or ""
        if not value or value == PLACEHOLDER:
            raise RootLoginError(
                "%s is unset or still a placeholder: fill the Bitwarden entry %s and run under "
                "the %s profile" % (name, _bws_entry(name), PROFILE),
                rc=2,
            )
        values[name] = value
    try:
        totp.decode_seed(values[SEED_ENV])
    except totp.TotpError as exc:
        raise RootLoginError("%s: %s" % (_bws_entry(SEED_ENV), exc), rc=2) from None
    return values


class Session:
    """The `/auth` routes of one origin under one cookie store. `post` returns (HTTP status, decoded object); tokens in the answer are never printed."""

    def __init__(self, origin: str):
        parts = urlsplit(origin)
        self.scheme = parts.scheme
        self.host = parts.netloc
        self.cookies: dict[str, str] = {}

    def post(self, route: str, body: dict) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if self.cookies:
            headers["Cookie"] = "; ".join("%s=%s" % kv for kv in self.cookies.items())
        factory = (
            http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        )
        conn = factory(self.host, timeout=HTTP_TIMEOUT_S)
        try:
            conn.request("POST", API_PATH + route, json.dumps(body), headers)
            resp = conn.getresponse()
            status, raw = resp.status, resp.read()
            for header in resp.headers.get_all("Set-Cookie") or []:
                name, _, rest = header.partition("=")
                self.cookies[name.strip()] = rest.partition(";")[0]
        except OSError as exc:
            raise RootLoginError(
                "POST %s%s reached no answer (%s)" % (API_PATH, route, type(exc).__name__)
            ) from None
        finally:
            conn.close()
        try:
            decoded = json.loads(raw)
        except ValueError:
            decoded = {}
        return status, decoded if isinstance(decoded, dict) else {}


def _is_fault(status: int) -> bool:
    return status == 429 or status >= 500


def _answer_challenge(
    api: Session,
    challenge: str,
    seed: str,
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> None:
    """Spend one code on the challenge, and one more from the next window after a first 4xx."""
    if totp.STEP - (now() % totp.STEP) < MIN_WINDOW_LEFT:
        sleep(totp.STEP - (now() % totp.STEP) + 0.5)
    asked = now()
    first, _ = api.post(
        "2fa/verify", {"challengeToken": challenge, "code": totp.code(seed, at=asked)}
    )
    if first == 200:
        return
    if _is_fault(first):
        raise RootLoginError(
            "POST /auth/2fa/verify answered HTTP %d: a rate-limit or server fault, not a refusal "
            "of the code; rerun later" % first
        )
    wait = totp.STEP - (asked % totp.STEP) + 0.5
    sleep(wait)
    second, _ = api.post(
        "2fa/verify", {"challengeToken": challenge, "code": totp.code(seed, at=asked + wait)}
    )
    if second == 200:
        return
    if _is_fault(second):
        raise RootLoginError(
            "POST /auth/2fa/verify answered HTTP %d: a rate-limit or server fault, not a refusal "
            "of the code; rerun later" % second
        )
    raise RootLoginError(
        "the code from %s was refused in two consecutive 30 s windows (HTTP %d, then HTTP %d): "
        "the seed is stale or wrong; not retrying" % (_bws_entry(SEED_ENV), first, second)
    )


def open_session(
    origin: str,
    values: Mapping[str, str],
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Sign in and answer the TOTP challenge; return when a session cookie is held, raise RootLoginError otherwise."""
    api = Session(origin)
    now = now or time.time
    sleep = sleep or time.sleep
    status, answer = api.post("login", {"email": values[EMAIL_ENV], "password": values[PW_ENV]})
    if status != 200:
        # The server's own code and message carry no secret and say why (a captcha requirement, a lockout, a refused password); guessing "password refused" for every non-200 hid that.
        err = answer.get("error")
        if isinstance(err, str):
            code, message = "", err
        else:
            body = err if isinstance(err, dict) else answer
            code, message = str(body.get("code") or ""), str(body.get("message") or "")
        raise RootLoginError(
            "POST /auth/login answered HTTP %d%s%s"
            % (status, " %s" % code if code else "", ": %s" % message[:200] if message else "")
        )
    if answer.get("requiresTwoFactor"):
        challenge = answer.get("challengeToken")
        if not isinstance(challenge, str):
            raise RootLoginError("POST /auth/login reported two-factor but named no challengeToken")
        _answer_challenge(api, challenge, values[SEED_ENV], now, sleep)
    if not api.cookies:
        raise RootLoginError("the sign-in answered 200 but set no session cookie")


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    return subprocess.run(list(argv), env=dict(env), check=False).returncode


def read_token_values(env: Mapping[str, str]) -> dict[str, str]:
    """The token and the seed, each refused when unset or still the placeholder, the token also when it is not an `rdr_` value; no request has been made."""
    values: dict[str, str] = {}
    for name in (VAULT_ENTRY, SEED_ENV):
        value = env.get(name) or ""
        if not value or value == PLACEHOLDER:
            raise RootLoginError(
                "%s is unset or still a placeholder: fill the Bitwarden entry %s and run under "
                "the %s profile" % (name, _bws_entry(name), PROFILE),
                rc=2,
            )
        values[name] = value
    if not values[VAULT_ENTRY].startswith(VALUE_PREFIX):
        raise RootLoginError(
            "%s is not a root API token (it must start with %s): mint one in the portal and "
            "store it in the Bitwarden entry %s"
            % (VAULT_ENTRY, VALUE_PREFIX, _bws_entry(VAULT_ENTRY)),
            rc=2,
        )
    try:
        totp.decode_seed(values[SEED_ENV])
    except totp.TotpError as exc:
        raise RootLoginError("%s: %s" % (_bws_entry(SEED_ENV), exc), rc=2) from None
    return values


def _answer_error(answer: dict) -> tuple[str, str]:
    """(code, message) of an `{error, code}` answer, tolerating the nested form."""
    err = answer.get("error")
    body = err if isinstance(err, dict) else answer
    message = err if isinstance(err, str) else body.get("message")
    return str(body.get("code") or ""), str(message or "")


def _describe(status: int, answer: dict) -> str:
    code, message = _answer_error(answer)
    return "HTTP %d%s%s" % (
        status,
        " %s" % code if code else "",
        ": %s" % message[:200] if message else "",
    )


def _instant(value: object) -> datetime | None:
    """A server timestamp as a UTC datetime: epoch milliseconds or an ISO 8601 string; None when it is neither."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000, UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


class AdminClient:
    """The `/admin` routes of one origin under one root token session. `get` is GET only; the token rides as a bearer header and is never printed."""

    def __init__(self, origin: str, token: str):
        parts = urlsplit(origin)
        self.scheme = parts.scheme
        self.host = parts.netloc
        self._token = token
        self.session_expires_at: datetime | None = None
        self.token_expires_at: datetime | None = None
        self.rebound: list[str] = []

    def _call(self, method: str, route: str, body: dict | None = None) -> tuple[int, dict]:
        headers = {"Authorization": "Bearer " + self._token}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body)
        factory = (
            http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        )
        conn = factory(self.host, timeout=HTTP_TIMEOUT_S)
        try:
            conn.request(method, API_ROOT + route, payload, headers)
            resp = conn.getresponse()
            status, raw = resp.status, resp.read()
        except OSError as exc:
            raise RootLoginError(
                "%s %s%s reached no answer (%s)"
                % (method, API_ROOT, route.split("?", 1)[0], type(exc).__name__)
            ) from None
        finally:
            conn.close()
        try:
            decoded = json.loads(raw)
        except ValueError:
            decoded = {}
        return status, decoded if isinstance(decoded, dict) else {}

    def get(self, route: str) -> tuple[int, dict]:
        return self._call("GET", route)

    def post(self, route: str, body: dict) -> tuple[int, dict]:
        return self._call("POST", route, body)

    def delete(self, route: str) -> tuple[int, dict]:
        return self._call("DELETE", route)

    def days_left(self, now: Callable[[], float]) -> int | None:
        if self.token_expires_at is None:
            return None
        return int((self.token_expires_at.timestamp() - now()) // 86400)


def _code_refused(status: int, answer: dict) -> bool:
    return status != 200 and _answer_error(answer)[0] in ("TOTP_INVALID", "TOTP_REPLAYED")


def _fault(what: str, status: int) -> RootLoginError:
    return RootLoginError(
        "%s answered HTTP %d: a rate-limit or server fault, not a refusal of the code; "
        "rerun later" % (what, status)
    )


def _spend_code(
    send: Callable[[str], tuple[int, dict]],
    seed: str,
    what: str,
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> tuple[int, dict]:
    """Send one code through `send`; a refused code (TOTP_INVALID, TOTP_REPLAYED) is retried once from the next window, a second refusal raises. Any other answer, 200 or not, is returned for the caller to judge; a 429 or 5xx raises as a fault."""
    if totp.STEP - (now() % totp.STEP) < MIN_WINDOW_LEFT:
        sleep(totp.STEP - (now() % totp.STEP) + 0.5)
    asked = now()
    first = send(totp.code(seed, at=asked))
    if _is_fault(first[0]):
        raise _fault(what, first[0])
    if not _code_refused(*first):
        return first
    wait = totp.STEP - (asked % totp.STEP) + 0.5
    sleep(wait)
    second = send(totp.code(seed, at=asked + wait))
    if _is_fault(second[0]):
        raise _fault(what, second[0])
    if _code_refused(*second):
        raise RootLoginError(
            "the code from %s was refused in two consecutive 30 s windows (%s, then %s): the "
            "seed is stale or wrong; not retrying"
            % (_bws_entry(SEED_ENV), _describe(*first), _describe(*second))
        )
    return second


def _open_token(
    origin: str,
    values: Mapping[str, str],
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> AdminClient:
    """Open a token session; on ROOT_TOKEN_IP_MISMATCH bind this address once (a fresh code), wait for the next step and open again."""
    client = AdminClient(origin, values[VAULT_ENTRY])
    seed = values[SEED_ENV]
    session = "POST /admin/root-token/session"
    bind = "POST /admin/root-token/bind"
    status, answer = _spend_code(
        lambda code: client.post("/admin/root-token/session", {"code": code}),
        seed,
        session,
        now,
        sleep,
    )
    if status != 200 and _answer_error(answer)[0] == "ROOT_TOKEN_IP_MISMATCH":
        status, answer = _spend_code(
            lambda code: client.post("/admin/root-token/bind", {"code": code}),
            seed,
            bind,
            now,
            sleep,
        )
        if status != 200:
            raise RootLoginError("%s answered %s" % (bind, _describe(status, answer)))
        family = answer.get("family")
        client.rebound.append(family if isinstance(family, str) else "?")
        # The account spends a code once per user: the session call needs the next step's.
        sleep(totp.STEP - (now() % totp.STEP) + 0.5)
        status, answer = _spend_code(
            lambda code: client.post("/admin/root-token/session", {"code": code}),
            seed,
            session,
            now,
            sleep,
        )
    if status != 200:
        raise RootLoginError("%s answered %s" % (session, _describe(status, answer)))
    client.session_expires_at = _instant(answer.get("sessionExpiresAt"))
    client.token_expires_at = _instant(answer.get("tokenExpiresAt"))
    return client


def open_token_session(
    target: str, region: str, env: Mapping[str, str] | None = None
) -> AdminClient:
    """Open a root token session on a production region for another tool; `get(path)` is GET only. The values come from `env` (default the process environment, bound by the root-login profile)."""
    token_entry(region)
    values = read_token_values(os.environ if env is None else env)
    return _open_token(origin_for(target, region), values, time.time, time.sleep)


def describe_session(opts: Options, client: AdminClient, now: Callable[[], float]) -> str:
    until = client.session_expires_at
    days = client.days_left(now)
    return "root session opened (%s %s, token, session until %s, token expires in %s)" % (
        opts.target,
        opts.region,
        until.strftime("%H:%MZ") if until else "an unreported time",
        "%d days" % days if days is not None else "an unreported time",
    )


def probe(client: AdminClient, name: str) -> None:
    """One allowlisted GET, printing the status and the shape only: a key count for stats, types and times for audit."""
    route = PROBES[name]
    status, answer = client.get(route)
    label = "GET %s %d" % (route.split("?", 1)[0], status)
    if status != 200:
        raise RootLoginError("%s: %s" % (label, _describe(status, answer)))
    print(label)
    if name == "stats":
        print("%d keys" % len(answer))
        return
    rows = next((v for v in answer.values() if isinstance(v, list)), [])
    for row in rows:
        if isinstance(row, dict):
            when = next((row[k] for k in ("createdAt", "timestamp", "at") if k in row), "")
            print("%s %s" % (row.get("type", "?"), when))


def control(origin: str, client: AdminClient) -> None:
    """Two live refusals: the session-less call is refused, and the password sign-in still demands its captcha."""
    status, answer = client.delete("/admin/root-token/session")
    if status != 200:
        raise RootLoginError("control: DELETE session answered %s" % _describe(status, answer))
    status, answer = client.get("/admin/stats")
    if status != 403 or _answer_error(answer)[0] != "ROOT_TOKEN_SESSION_REQUIRED":
        raise RootLoginError(
            "control FAILED: GET /admin/stats without a session answered %s, expected HTTP 403 "
            "ROOT_TOKEN_SESSION_REQUIRED" % _describe(status, answer)
        )
    print("control ok: GET /admin/stats without a session answered 403 ROOT_TOKEN_SESSION_REQUIRED")
    status, answer = Session(origin).post(
        "login", {"email": "control@invalid.example", "password": "control"}
    )
    if status != 400 or CAPTCHA_REFUSAL not in _describe(status, answer):
        raise RootLoginError(
            "control FAILED: POST /auth/login without a captcha token answered %s, expected "
            "HTTP 400 %s" % (_describe(status, answer), CAPTCHA_REFUSAL)
        )
    print("control ok: POST /auth/login without a captcha token answered 400 %s" % CAPTCHA_REFUSAL)


def rotate(
    client: AdminClient,
    env: Mapping[str, str],
    capture: Callable[[Sequence[str], Mapping[str, str]], tuple[int, str]],
) -> None:
    """Mint the successor, then write it to the same Bitwarden entry through the vault writer's child environment (never argv). The old token lives an hour more, so a failed write is recoverable by a rerun."""
    status, answer = client.post("/admin/root-token/rotate", {})
    token = answer.get("token")
    if status != 201 or not isinstance(token, str) or not token.startswith(VALUE_PREFIX):
        raise RootLoginError(
            "POST /admin/root-token/rotate answered %s" % _describe(status, answer)
        )
    child = login_bench._with_ci_path(env)
    child[VAULT_ENTRY_NEW] = token
    log.step("Storing the rotated token as %s (bws_env store-from-env)" % VAULT_ENTRY)
    rc, out = capture(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "store-from-env",
            "%s > %s" % (VAULT_ENTRY, VAULT_ENTRY_NEW),
        ],
        child,
    )
    if rc != 0:
        raise RootLoginError(
            "the successor token was minted but writing %s to Bitwarden failed (exit %d); the old "
            "token stays valid for about an hour: rerun --rotate" % (_bws_entry(VAULT_ENTRY), rc)
        )
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    print("token rotated and stored as %s" % VAULT_ENTRY)


def _reexec_under_profile(argv: Sequence[str], run: Runner) -> int | None:
    """This entry point under the root-login profile; None when the profile is already bound."""
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
            "rediacc_ci.ops.root_login",
            *argv,
        ],
        env,
    )


def _clock() -> tuple[Callable[[], float], Callable[[float], None]]:
    """The wall clock and sleep `main` runs on; a test replaces this one seam."""
    return time.time, time.sleep


def main(
    argv: Sequence[str] | None = None,
    run: Runner = _subprocess_runner,
    capture: Callable[
        [Sequence[str], Mapping[str, str]], tuple[int, str]
    ] = login_bench._subprocess_capture,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    try:
        opts = parse_args(args)
        if not opts.password:
            token_entry(opts.region)
        rebound = _reexec_under_profile(args, run)
        if rebound is not None:
            return rebound
        origin = origin_for(opts.target, opts.region)
        if opts.password:
            open_session(origin, read_values(os.environ))
            print("root session opened (%s %s)" % (opts.target, opts.region))
            return 0
        values = read_token_values(os.environ)
        if opts.check:
            print("root login values ok (%s %s)" % (opts.target, opts.region))
            return 0
        now, sleep = _clock()
        client = _open_token(origin, values, now, sleep)
        for family in client.rebound:
            print("ip rebound (%s)" % family)
        print(describe_session(opts, client, now))
        days = client.days_left(now)
        auto = (
            os.environ.get(AUTOROTATE_ENV) == "1" and days is not None and days < ROTATE_BELOW_DAYS
        )
        if opts.probe:
            probe(client, opts.probe)
        if opts.control:
            control(origin, client)
        if opts.rotate or auto:
            rotate(client, os.environ, capture)
    except RootLoginError as exc:
        log.error(str(exc))
        return exc.rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
