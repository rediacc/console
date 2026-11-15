"""Headless root-admin login for the production account Workers (stable and edge).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_login --target stable|edge --region eu|us|asia

WHY. Stable and edge share ONE production root pair in every region (operator ruling 2026-11-15): the root address `ROOT_EMAIL`, its password `ROOT_PASSWORD` and the 2FA seed `ROOT_TOTP_SEED`. There is no separate stable Worker set (`docs/agent-reference/release-process.md`), so both targets resolve to the same origin, `https://<regions.json domain>`; the target stays in the command so a caller says which channel it means. The bench root has its own credentials and its own tool (`rediacc_ci.ops.login_bench`).

THE STEPS, in order:

  1. Re-execute under the `root-login` Bitwarden profile (`rediacc_ci.core.bws_env exec`), unless it is already bound. The profile binds ROOT_EMAIL, ROOT_PASSWORD and ROOT_TOTP_SEED.
  2. Refuse a value that is unset or still the placeholder `PLACEHOLDER-operator-fills`, naming its Bitwarden entry, before any request.
  3. `POST /account/api/v1/auth/login` with the address and password. A 200 that asks for two-factor carries a `challengeToken`; any other answer is a named refusal.
  4. Answer the challenge with `POST /auth/2fa/verify` and the six-digit code derived in memory from the seed (`rediacc_ci.ops.totp`). A first 4xx is retried once with the next 30 s window's code (the account refuses a code already spent); a second refusal is a named failure that does not retry again. A 429 or 5xx is a fault, not a refusal of the code.
  5. A root session is open when the sign-in answered 200 and set a session cookie. Print that one fact.

Nothing here is a Turnstile workaround: where `/auth/login` demands a captcha token the answer is the named refusal, never a bypass.

SECRETS. The password, the seed, every code and every session token stay in memory: none is put on argv, printed or logged, and the only output is the `root session opened` line. Exit 0 a session opened, 1 a refusal or failed step, 2 a refusal before any request (usage, missing value).
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from urllib.parse import urlsplit

from rediacc_ci import log, paths
from rediacc_ci.ops import totp

PROFILE = "root-login"
TARGETS = ("stable", "edge")
REGIONS = ("eu", "us", "asia")
EMAIL_ENV = "ROOT_EMAIL"
PW_ENV = "ROOT_PASSWORD"
SEED_ENV = "ROOT_TOTP_SEED"
SOURCE_NAMES = (EMAIL_ENV, PW_ENV, SEED_ENV)
PLACEHOLDER = "PLACEHOLDER-operator-fills"
API_PATH = "/account/api/v1/auth/"
HTTP_TIMEOUT_S = 30
MIN_WINDOW_LEFT = 5
USAGE = "usage: root_login --target %s --region %s" % ("|".join(TARGETS), "|".join(REGIONS))

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


def parse_args(argv: Sequence[str]) -> tuple[str, str]:
    """(target, region); RootLoginError rc 2 for anything else."""
    args = list(argv)
    found: dict[str, str] = {}
    i = 0
    while i < len(args):
        flag = args[i]
        if flag in ("--target", "--region") and i + 1 < len(args):
            found[flag[2:]] = args[i + 1]
            i += 2
        else:
            raise RootLoginError("unknown argument %r\n%s" % (flag, USAGE), rc=2)
    target, region = found.get("target", ""), found.get("region", "")
    if target not in TARGETS:
        raise RootLoginError("--target must be one of %s\n%s" % (", ".join(TARGETS), USAGE), rc=2)
    if region not in REGIONS:
        raise RootLoginError("--region must be one of %s\n%s" % (", ".join(REGIONS), USAGE), rc=2)
    return target, region


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


def main(argv: Sequence[str] | None = None, run: Runner = _subprocess_runner) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    try:
        target, region = parse_args(args)
        rebound = _reexec_under_profile(args, run)
        if rebound is not None:
            return rebound
        values = read_values(os.environ)
        open_session(origin_for(target, region), values)
    except RootLoginError as exc:
        log.error(str(exc))
        return exc.rc
    print("root session opened (%s %s)" % (target, region))
    return 0


if __name__ == "__main__":
    sys.exit(main())
