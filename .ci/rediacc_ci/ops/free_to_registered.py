"""Bench drill: an anonymous FREE user becomes a registered COMMUNITY user, driven from the CLI side.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.free_to_registered [--dry-run]

BENCH ONLY. The target is `BENCH_ORIGIN`; no other server is accepted. The run re-executes itself under the `deploy-bench` Bitwarden profile (it needs `CF_GLOBAL_API_KEY` and `CF_EMAIL` for the captured-email and cleanup queries) unless that profile is already bound.

THE STEPS, each printing one evidence line `STEP <n> <name> rc=<rc> <detail>`:

  1. allowlist  `bench_access add-current`, so this host passes the bench WAF rule.
  2. config     A throwaway named config `ftr-<stamp>` whose account server is the bench origin (`rdc config init`). The operator's eu-bench config is never touched; the config is deleted in the cleanup. (A temp XDG_CONFIG_HOME is not usable: `rdc.sh` reads the Bitwarden token from the same directory.)
  3. anonymous  `subscription status -o json` under that config before any account exists. It must refuse with "Not logged in" (exit 2): an anonymous machine has no account view. Issuing a FREE licence (`POST /licenses/free`) needs a machine and a repository, so this drill asserts the anonymous status only.
  4. register   `POST /auth/register` with a throwaway `ftr+<stamp>@rediacc.io` address (the bench email allowlist is `ALLOWED_EMAIL_DOMAINS`, rediacc.com and rediacc.io) and a random password. A password registration opens a session at once and sends NO verification email: the server has no verify-email step for it.
  5. email      The email loop is proved with the magic link instead: `POST /auth/magic-link`, the `magic-link` mail read from the D1 `captured_emails` table (an absent mail refuses), then `POST /auth/magic-link/verify` with its token. The token never reaches output.
  6. login      `subscription login --server <bench>` under the throwaway config with REDIACC_LOGIN_EMAIL and REDIACC_LOGIN_PASSWORD in the child environment, then `subscription status -o json`: the plan is COMMUNITY and the reported monthly repo-licence limit equals `PLAN_LIMITS.COMMUNITY` (parsed from packages/shared/src/subscription/constants.ts). The D1 subscription row is read as well: plan COMMUNITY and every non-null override equal to the plan's limits.
  7. cleanup    Always runs. Deletes the rows of that one user, its organizations and subscriptions (found by the user id of the exact email) and the captured emails of that exact recipient, then proves the user is gone. The throwaway config is deleted. No account-deletion API exists, so the rows go through D1.

The password and every token travel only in a child environment or a request body, never on argv and never printed. Exit 0 only when every step held; cleanup failing is a failure.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import secrets
import string
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rediacc_ci import paths
from rediacc_ci.ops import deploy_bench
from rediacc_ci.well_known import BENCH_ORIGIN

PROFILE = "deploy-bench"
EMAIL_DOMAIN = "rediacc.io"
ADDRESS = re.compile(r"^ftr\+\d{14}@" + re.escape(EMAIL_DOMAIN) + "$")
API = "/account/api/v1"
MAIL_ATTEMPTS = 6
MAIL_WAIT_S = 3.0
CLOCK_SKEW_S = 60
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAGIC_TOKEN = re.compile(r"magic-link/verify\?token=([A-Za-z0-9_\-]+)")
CONSTANTS_REL = ("packages", "shared", "src", "subscription", "constants.ts")
LOGIN_EMAIL_ENV = "REDIACC_LOGIN_EMAIL"
LOGIN_PW_ENV = "REDIACC_LOGIN_PASSWORD"
SCRUBBED = ("RDC_DEV", "REDIACC_CONFIG", "REDIACC_TOKEN", "REDIACC_ACCOUNT_SERVER")
STEP_NAMES = ("allowlist", "config", "anonymous", "register", "email", "login", "cleanup")

Http = Callable[[str, dict], "tuple[int, dict]"]
Rows = Callable[[str], "list[dict]"]
Rdc = Callable[[Sequence[str], Mapping[str, str]], "tuple[int, str]"]


class DrillError(RuntimeError):
    """A step that cannot continue. The message never carries a secret."""


def stamp_now(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S")


def address_for(stamp: str) -> str:
    """The throwaway address of one run."""
    return "ftr+%s@%s" % (stamp, EMAIL_DOMAIN)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def q(template: str, **values: str) -> str:
    """A statement from `$name` placeholders filled with already-quoted literals (wrangler d1 execute has no bind parameters)."""
    return string.Template(template).substitute(values)


def community_limits(root=None) -> dict[str, int]:
    """PLAN_LIMITS.COMMUNITY parsed from the shared constants: maxRepositorySizeGb, maxRepoLicenseIssuancesPerMonth, storageQuotaBytes."""
    path = (root or paths.repo_root()).joinpath(*CONSTANTS_REL)
    text = path.read_text(encoding="utf-8")
    block = re.search(r"PLAN_LIMITS\b.*?\n> = \{.*?\bCOMMUNITY:\s*\{(.*?)\}", text, re.DOTALL)
    if not block:
        raise DrillError("PLAN_LIMITS.COMMUNITY not found in %s" % path)
    out: dict[str, int] = {}
    for key, num, exp in re.findall(
        r"(\w+):\s*(\d+)(?:\s*\*\s*1024\s*\*\*\s*(\d+))?", block.group(1)
    ):
        out[key] = int(num) * (1024 ** int(exp) if exp else 1)
    for need in ("maxRepositorySizeGb", "maxRepoLicenseIssuancesPerMonth", "storageQuotaBytes"):
        if need not in out:
            raise DrillError("PLAN_LIMITS.COMMUNITY has no %s in %s" % (need, path))
    return out


def extract_magic_token(body: str) -> str:
    found = MAGIC_TOKEN.search(body)
    return found.group(1) if found else ""


def mail_query(email: str, since: str) -> str:
    return q(
        "SELECT text_body FROM captured_emails WHERE recipient = $r AND kind = 'magic-link' "
        "AND created_at >= $since ORDER BY created_at DESC LIMIT 1",
        r=sql_literal(email),
        since=sql_literal(since),
    )


def wait_for_token(email: str, since: str, rows: Rows, sleep: Callable[[float], None]) -> str:
    """The magic-link token of the newest captured mail; DrillError when none arrives."""
    for attempt in range(MAIL_ATTEMPTS):
        if attempt:
            sleep(MAIL_WAIT_S)
        for row in rows(mail_query(email, since)):
            token = extract_magic_token(str(row.get("text_body") or ""))
            if token:
                return token
    raise DrillError(
        "no magic-link mail for %s reached captured_emails after %d reads" % (email, MAIL_ATTEMPTS)
    )


def cleanup_sql(
    email: str, user_id: str, org_ids: Sequence[str], sub_ids: Sequence[str]
) -> list[str]:
    """Delete statements scoped to one user id, its org ids, its subscription ids and one exact recipient. Ids are validated UUIDs."""
    for ident in (user_id, *org_ids, *sub_ids):
        if not UUID.match(ident):
            raise DrillError("refusing a non-UUID id in a delete: %r" % ident)
    uid = sql_literal(user_id)
    orgs = ", ".join(sql_literal(o) for o in org_ids) or "''"
    subs = ", ".join(sql_literal(s) for s in sub_ids) or "''"
    teams = q("SELECT id FROM teams WHERE org_id IN ($o)", o=orgs)
    return [
        q("DELETE FROM api_tokens WHERE subscription_id IN ($s)", s=subs),
        q("DELETE FROM subscription_activations WHERE subscription_id IN ($s)", s=subs),
        q("DELETE FROM issuance_ledger WHERE subscription_id IN ($s)", s=subs),
        q("DELETE FROM subscription_shards WHERE subscription_id IN ($s)", s=subs),
        q("DELETE FROM event_log WHERE user_id = $u OR customer_id = $u", u=uid),
        q("DELETE FROM refresh_tokens WHERE user_id = $u", u=uid),
        q("DELETE FROM magic_links WHERE user_id = $u", u=uid),
        q("DELETE FROM password_resets WHERE user_id = $u", u=uid),
        q("DELETE FROM elevated_sessions WHERE user_id = $u", u=uid),
        q("DELETE FROM user_communication_preferences WHERE user_id = $u", u=uid),
        q("DELETE FROM team_memberships WHERE user_id = $u OR team_id IN ($t)", u=uid, t=teams),
        q("DELETE FROM teams WHERE org_id IN ($o)", o=orgs),
        q("DELETE FROM org_memberships WHERE org_id IN ($o) OR user_id = $u", o=orgs, u=uid),
        q("DELETE FROM subscriptions WHERE id IN ($s)", s=subs),
        q("DELETE FROM organizations WHERE id IN ($o)", o=orgs),
        q("DELETE FROM users WHERE id = $u AND email = $e", u=uid, e=sql_literal(email)),
        q("DELETE FROM captured_emails WHERE recipient = $e", e=sql_literal(email)),
    ]


@dataclass
class Evidence:
    lines: list[str] = field(default_factory=list)
    failed: bool = False

    def add(self, number: int, name: str, rc: int, detail: str = "") -> None:
        if rc != 0:
            self.failed = True
        line = "STEP %d %s rc=%d%s" % (number, name, rc, (" " + detail) if detail else "")
        self.lines.append(line)
        print(line, flush=True)


def _http(path: str, body: dict) -> tuple[int, dict]:
    status, answer = deploy_bench._post_json(BENCH_ORIGIN + path, body)
    if status == 0:
        raise DrillError("no HTTP answer from %s%s" % (BENCH_ORIGIN, path))
    return status, answer


def _rdc(argv: Sequence[str], env: Mapping[str, str]) -> tuple[int, str]:
    proc = subprocess.run(
        [str(paths.repo_root() / "rdc.sh"), *argv],
        env=dict(env),
        cwd=str(paths.repo_root()),
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout or ""


def _allowlist() -> int:
    env = dict(os.environ)
    ci = str(paths.repo_root() / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.ops.bench_access", "add-current"], env=env, check=False
    ).returncode


def _envelope(out: str) -> dict:
    try:
        decoded = json.loads(out)
    except ValueError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _error_text(out: str) -> str:
    errors = _envelope(out).get("errors") or []
    return " ".join(str(e.get("message", "")) for e in errors if isinstance(e, dict))


def plan_check(report: dict, limits: dict[str, int]) -> list[str]:
    """Reasons the status report is not COMMUNITY with COMMUNITY limits; empty when it holds."""
    bad: list[str] = []
    if report.get("plan") != "COMMUNITY":
        bad.append("plan=%r" % report.get("plan"))
    issued = report.get("repoLicenseIssuances") or {}
    want = limits["maxRepoLicenseIssuancesPerMonth"]
    if issued.get("limit") != want:
        bad.append("repoLicenseIssuances.limit=%r want %d" % (issued.get("limit"), want))
    return bad


def row_check(row: dict, limits: dict[str, int]) -> list[str]:
    """Reasons the D1 subscription row differs from COMMUNITY; a null override means the plan default."""
    bad: list[str] = []
    if row.get("plan_code") != "COMMUNITY":
        bad.append("plan_code=%r" % row.get("plan_code"))
    for col, key in (
        ("max_repository_size_gb", "maxRepositorySizeGb"),
        ("max_repo_license_issuances_per_month", "maxRepoLicenseIssuancesPerMonth"),
        ("storage_quota_bytes", "storageQuotaBytes"),
    ):
        if row.get(col) is not None and row[col] != limits[key]:
            bad.append("%s=%r want %d" % (col, row[col], limits[key]))
    return bad


def cleanup(email: str, rows: Rows, log: Callable[[str], None]) -> None:
    """Delete the rows of `email` only and prove the user is gone. DrillError on a leftover."""
    lit = sql_literal(email)
    mails = rows(q("SELECT count(*) AS n FROM captured_emails WHERE recipient = $e", e=lit))
    log("captured emails of the address: %s" % (mails[0].get("n") if mails else "?"))
    user_ids = [str(u["id"]) for u in rows(q("SELECT id FROM users WHERE email = $e", e=lit))]
    if not user_ids:
        log("no users row for the address")
        rows(q("DELETE FROM captured_emails WHERE recipient = $e", e=lit))
    for user_id in user_ids:
        if not UUID.match(user_id):
            raise DrillError("refusing a non-UUID user id %r" % user_id)
        uid = sql_literal(user_id)
        org_ids = [
            str(r["id"])
            for r in rows(q("SELECT id FROM organizations WHERE owner_user_id = $u", u=uid))
        ]
        sub_ids = [
            str(r["id"])
            for r in rows(q("SELECT id FROM subscriptions WHERE customer_id = $u", u=uid))
        ]
        log(
            "deleted user %s, %d organization(s) %s, %d subscription(s) %s"
            % (user_id, len(org_ids), ",".join(org_ids), len(sub_ids), ",".join(sub_ids))
        )
        for sql in cleanup_sql(email, user_id, org_ids, sub_ids):
            rows(sql)
    if rows(q("SELECT id FROM users WHERE email = $e", e=lit)):
        raise DrillError("the user row is still present after the delete")


def token_file(config: str) -> pathlib.Path:
    """The api-token file `rdc config delete` leaves behind: `api-token-<config>.json` beside the config."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(pathlib.Path.home() / ".config")
    return pathlib.Path(base) / "rediacc" / ("api-token-%s.json" % config)


def _drop_token_file(config: str) -> bool:
    path = token_file(config)
    if not path.is_file():
        return False
    path.unlink()
    return True


@dataclass
class Deps:
    http: Http = _http
    rows: Rows = deploy_bench._d1_rows
    rdc: Rdc = _rdc
    drop_token_file: Callable[[str], bool] = _drop_token_file
    allowlist: Callable[[], int] = _allowlist
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    password: Callable[[], str] = lambda: secrets.token_urlsafe(24)


def _step_anonymous(d: Deps, ev: Evidence, base: Mapping[str, str], config: str) -> None:
    rc, out = d.rdc(["--config", config, "subscription", "status", "-o", "json"], base)
    refused = "Not logged in" in _error_text(out)
    ok = rc == 2 and refused
    ev.add(
        3,
        "anonymous",
        0 if ok else 1,
        "status exit=%d refused=%s; FREE licence not issued (needs a machine and a repo)"
        % (rc, refused),
    )
    if not ok:
        raise DrillError("anonymous status did not refuse with Not logged in")


def _step_email(d: Deps, ev: Evidence, email: str, since_iso: str) -> None:
    status, _ = d.http(API + "/auth/magic-link", {"email": email})
    if status != 200:
        ev.add(5, "email", 1, "magic-link request http=%d" % status)
        raise DrillError("magic-link request refused")
    try:
        token = wait_for_token(email, since_iso, d.rows, d.sleep)
    except DrillError as exc:
        ev.add(5, "email", 1, str(exc))
        raise
    status, answer = d.http(API + "/auth/magic-link/verify", {"token": token})
    match = (answer.get("user") or {}).get("email") == email
    ok = status == 200 and match
    ev.add(
        5,
        "email",
        0 if ok else 1,
        "captured mail read, verify http=%d email_match=%s" % (status, match),
    )
    if not ok:
        raise DrillError("magic-link verify failed")


def _step_login(
    d: Deps,
    ev: Evidence,
    base: Mapping[str, str],
    config: str,
    creds: tuple[str, str],
    limits: dict[str, int],
) -> None:
    login_env = dict(base)
    login_env[LOGIN_EMAIL_ENV], login_env[LOGIN_PW_ENV] = creds
    rc, _ = d.rdc(
        ["--config", config, "subscription", "login", "--server", BENCH_ORIGIN], login_env
    )
    if rc != 0:
        ev.add(6, "login", rc, "subscription login failed")
        raise DrillError("subscription login failed")
    rc, out = d.rdc(["--config", config, "subscription", "status", "-o", "json"], base)
    report = _envelope(out).get("data") or {}
    bad = plan_check(report, limits) if rc == 0 else ["status exit=%d" % rc]
    sub = d.rows(
        q(
            "SELECT plan_code, max_repository_size_gb, max_repo_license_issuances_per_month, "
            "storage_quota_bytes FROM subscriptions WHERE customer_email = $e",
            e=sql_literal(creds[0]),
        )
    )
    bad += row_check(sub[0], limits) if len(sub) == 1 else ["subscription rows=%d" % len(sub)]
    ev.add(
        6,
        "login",
        1 if bad else 0,
        "plan=%s issuance_limit=%s want=%d d1_plan=%s%s"
        % (
            report.get("plan"),
            (report.get("repoLicenseIssuances") or {}).get("limit"),
            limits["maxRepoLicenseIssuancesPerMonth"],
            sub[0].get("plan_code") if sub else None,
            ("; " + "; ".join(bad)) if bad else "",
        ),
    )
    if bad:
        raise DrillError("COMMUNITY assertions failed")


def run(dry_run: bool, deps: Deps | None = None, env: Mapping[str, str] | None = None) -> int:
    d = deps or Deps()
    base = {k: v for k, v in (os.environ if env is None else env).items() if k not in SCRUBBED}
    ev = Evidence()
    started = d.now()
    stamp = stamp_now(started)
    email = address_for(stamp)
    config = "ftr-" + stamp
    if dry_run:
        for n, name in enumerate(STEP_NAMES, 1):
            print("DRY-RUN STEP %d %s config=%s email=%s" % (n, name, config, email))
        return 0
    limits = community_limits()
    password = d.password()
    since_iso = datetime.fromtimestamp(started.timestamp() - CLOCK_SKEW_S, UTC).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    config_made = registered = False
    try:
        rc = d.allowlist()
        ev.add(1, "allowlist", rc)
        if rc != 0:
            raise DrillError("bench allowlist refresh failed")

        rc, _ = d.rdc(["config", "init", config, "--server", BENCH_ORIGIN], base)
        config_made = rc == 0
        ev.add(2, "config", rc, "name=%s server=%s" % (config, BENCH_ORIGIN))
        if rc != 0:
            raise DrillError("config init failed")

        _step_anonymous(d, ev, base, config)

        status, answer = d.http(API + "/auth/register", {"email": email, "password": password})
        registered = status in (201, 409)
        plan = (answer.get("subscription") or {}).get("planCode")
        ok = status == 201 and plan == "COMMUNITY"
        hint = "; " + deploy_bench._blocked_hint(status).lstrip("; ") if status == 403 else ""
        ev.add(
            4,
            "register",
            0 if ok else 1,
            "http=%d email=%s plan=%s%s" % (status, email, plan, hint),
        )
        if not ok:
            raise DrillError("registration did not return 201 with COMMUNITY")

        _step_email(d, ev, email, since_iso)
        _step_login(d, ev, base, config, (email, password), limits)
    except DrillError as exc:
        print("drill: %s" % exc, file=sys.stderr)
    finally:
        notes: list[str] = []
        crc = 0
        if registered:
            try:
                cleanup(email, d.rows, notes.append)
            except DrillError as exc:
                crc = 1
                notes.append(str(exc))
        if config_made:
            rc, _ = d.rdc(["config", "delete", config, "-y"], base)
            notes.append("config %s deleted rc=%d" % (config, rc))
            crc = crc or rc
            if d.drop_token_file(config):
                notes.append("token file of %s removed" % config)
        ev.add(7, "cleanup", crc, "; ".join(notes) or "nothing to clean")
    return 1 if ev.failed else 0


def _reexec_under_profile(argv: Sequence[str]) -> int | None:
    if PROFILE in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(","):
        return None
    env = dict(os.environ)
    ci = str(paths.repo_root() / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
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
            "rediacc_ci.ops.free_to_registered",
            *argv,
        ],
        env=env,
        check=False,
    ).returncode


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    if any(a != "--dry-run" for a in args):
        print("usage: free_to_registered [--dry-run]", file=sys.stderr)
        return 2
    dry = "--dry-run" in args
    if not dry:
        rebound = _reexec_under_profile(args)
        if rebound is not None:
            return rebound
    return run(dry)


if __name__ == "__main__":
    sys.exit(main())
