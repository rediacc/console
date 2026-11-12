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
  3b. free-refused  A direct `POST /licenses/free` with no `termsAcceptance`. It must answer 403 `TERMS_ACCEPTANCE_REQUIRED` whose details name `--accept-terms`, and the count of `free_license_ip_window` rows of the last minute must not change.
  3c. free-accepted The same request with `termsAcceptance{method: cli-flag-unattended}` (the manifest's version and sha256), fresh UUIDs and `x-cli-version`. It must be issued, and exactly one `terms_acceptances` row must exist for the `free:` subject with that version and sha256, `client_ip IS NULL`, a non-empty `cli_version` and a non-empty `notice_text`.
  4b. terms-gate    After the register, a login with a cookie jar, then with those cookies `GET /portal/terms` reports not satisfied, a gated read (`GET /portal/subscription`) returns 403 `TERMS_ACCEPTANCE_REQUIRED`, `POST /portal/terms/accept` returns 201, and the row has method `web-checkbox` and a non-empty `client_ip` and `user_agent`.
  6b. handoff   The browser handoff of `rdc subscription register --email <addr>`: the command runs in the background under the throwaway config and its printed verification URL is captured. The URL must carry the device code and the URL-encoded email; the anonymous `/account/authorize?code=..&email=..` route must answer 200 (the SPA then sends the visitor to `/account/login?email=..`, a client-side redirect that the portal's vitest suite covers). Sign-up is completed through a magic-link mail requested with `next` set to that authorize path, and the captured link must carry the same `next`. With that session the Terms are accepted if not yet, the device code is approved (`POST /device-codes/<code>/approve`), the register process must exit 0 and `subscription status` must report COMMUNITY.
  7. cleanup    Always runs. Deletes the device-code row of 6b by its exact user code, the rows of that one user, its organizations and subscriptions (found by the user id of the exact email), the acceptance rows of the user and of the 3c `free:` subject, the 3c issuance and its window row (same `issued_at`, so the IP quota is restored), and the captured emails of that exact recipient, then proves the user is gone. The throwaway config is deleted. No account-deletion API exists, so the rows go through D1.

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
import tempfile
import time
import urllib.parse
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rediacc_ci import paths
from rediacc_ci.ops import deploy_bench
from rediacc_ci.well_known import BENCH_ORIGIN, INFRA_DOMAIN

PROFILE = "deploy-bench"
EMAIL_DOMAIN = INFRA_DOMAIN
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
STEPS = (
    ("1", "allowlist"),
    ("2", "config"),
    ("3", "anonymous"),
    ("3b", "free-refused"),
    ("3c", "free-accepted"),
    ("4", "register"),
    ("4b", "terms-gate"),
    ("5", "email"),
    ("6", "login"),
    ("6b", "handoff"),
    ("7", "cleanup"),
)
USER_CODE = re.compile(r"^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{2}$")
AUTHORIZE_PATH = "/account/authorize"
VERIFY_URL = re.compile(r"https?://\S+" + re.escape(AUTHORIZE_PATH) + r"\S*")
MAGIC_LINK = re.compile(r"magic-link/verify\?token=([A-Za-z0-9_\-]+)(?:&next=([^\s&]+))?")
URL_WAIT_S = 90.0
REGISTER_WAIT_S = 120.0
LEGAL_MANIFEST_REL = (".ci", "config", "legal-documents.json")
TERMS_DOCUMENT = "terms-of-service"
TERMS_REQUIRED = "TERMS_ACCEPTANCE_REQUIRED"
CLI_VERSION = "0.0.0-drill"
FREE_SUBJECT = re.compile(r"^free:[0-9a-f]{32}$")
WINDOW_S = 60

Http = Callable[[str, dict], "tuple[int, dict]"]
# method, path, body (or None), extra headers, cookie jar path (or None) -> (status, decoded object)
Call = Callable[[str, str, "dict | None", Mapping[str, str], "str | None"], "tuple[int, dict]"]
Rows = Callable[[str], "list[dict]"]
Rdc = Callable[[Sequence[str], Mapping[str, str]], "tuple[int, str]"]


class Background:
    """A command running in the background whose output carries one URL line the drill needs."""

    def read_url(self) -> str:
        raise NotImplementedError

    def finish(self, timeout: float) -> int:
        raise NotImplementedError

    def kill(self) -> None:
        raise NotImplementedError


Spawn = Callable[[Sequence[str], Mapping[str, str]], Background]


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


def terms_manifest(root=None) -> dict[str, str]:
    """{version, sha256} of the newest terms-of-service version in .ci/config/legal-documents.json."""
    path = (root or paths.repo_root()).joinpath(*LEGAL_MANIFEST_REL)
    versions = json.loads(path.read_text(encoding="utf-8"))["documents"][TERMS_DOCUMENT]["versions"]
    if not versions:
        raise DrillError("no %s version in %s" % (TERMS_DOCUMENT, path))
    newest = versions[-1]
    return {"version": str(newest["version"]), "sha256": str(newest["sha256"])}


def extract_magic_token(body: str) -> str:
    found = MAGIC_TOKEN.search(body)
    return found.group(1) if found else ""


def extract_magic_link(body: str) -> tuple[str, str]:
    """(token, next) of the magic link in a mail body; next is URL-decoded, empty when the link carries none."""
    found = MAGIC_LINK.search(body)
    if not found:
        return "", ""
    return found.group(1), urllib.parse.unquote(found.group(2) or "")


def handoff_url_check(url: str, email: str) -> list[str]:
    """Reasons a printed verification URL is not the registration handoff for `email`; empty when it holds."""
    bad: list[str] = []
    parsed = urllib.parse.urlsplit(url)
    if parsed.path != AUTHORIZE_PATH:
        bad.append("path=%r want %s" % (parsed.path, AUTHORIZE_PATH))
    query = urllib.parse.parse_qs(parsed.query)
    code = (query.get("code") or [""])[0]
    if not USER_CODE.match(code):
        bad.append("device code %r is not a user code" % code)
    if (query.get("email") or [""])[0] != email:
        bad.append("email param is not %s" % email)
    if "email=" + urllib.parse.quote(email, safe="") not in parsed.query:
        bad.append("email is not URL-encoded in the query")
    return bad


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
        q("DELETE FROM terms_acceptances WHERE subject_id = $u", u=uid),
        q("DELETE FROM team_memberships WHERE user_id = $u OR team_id IN ($t)", u=uid, t=teams),
        q("DELETE FROM teams WHERE org_id IN ($o)", o=orgs),
        q("DELETE FROM org_memberships WHERE org_id IN ($o) OR user_id = $u", o=orgs, u=uid),
        q("DELETE FROM subscriptions WHERE id IN ($s)", s=subs),
        q("DELETE FROM organizations WHERE id IN ($o)", o=orgs),
        q("DELETE FROM users WHERE id = $u AND email = $e", u=uid, e=sql_literal(email)),
        q("DELETE FROM captured_emails WHERE recipient = $e", e=sql_literal(email)),
    ]


def device_code_cleanup_sql(user_codes: Sequence[str]) -> list[str]:
    """One delete per captured device user code, by exact code. A malformed code is refused."""
    out: list[str] = []
    for code in user_codes:
        if not USER_CODE.match(code):
            raise DrillError("refusing a malformed device user code in a delete: %r" % code)
        out.append(q("DELETE FROM device_codes WHERE user_code = $c", c=sql_literal(code)))
    return out


@dataclass
class FreeIssued:
    """What the 3c issuance wrote, so the cleanup can remove exactly it."""

    repository_guid: str
    subject: str = ""
    issued_at: str = ""


def free_cleanup_sql(item: FreeIssued) -> list[str]:
    """Deletes scoped to the 3c issuance: its acceptance rows, its window row (same `issued_at`) and the issuance itself."""
    if not UUID.match(item.repository_guid):
        raise DrillError(
            "refusing a non-UUID repository guid in a delete: %r" % item.repository_guid
        )
    out: list[str] = []
    if item.subject:
        if not FREE_SUBJECT.match(item.subject):
            raise DrillError("refusing a malformed free subject in a delete: %r" % item.subject)
        out.append(
            q("DELETE FROM terms_acceptances WHERE subject_id = $s", s=sql_literal(item.subject))
        )
    if item.issued_at:
        out.append(
            q(
                "DELETE FROM free_license_ip_window WHERE issued_at = $t",
                t=sql_literal(item.issued_at),
            )
        )
    out.append(
        q(
            "DELETE FROM free_license_issuances WHERE repository_guid = $g",
            g=sql_literal(item.repository_guid),
        )
    )
    return out


def cleanup_free(item: FreeIssued, rows: Rows, log: Callable[[str], None]) -> None:
    """Fill in the subject and `issued_at` from the issuance row, delete, and prove nothing is left. DrillError on a leftover."""
    guid = sql_literal(item.repository_guid)
    found = rows(
        q(
            "SELECT free_subscription_id, issued_at FROM free_license_issuances "
            "WHERE repository_guid = $g",
            g=guid,
        )
    )
    if found:
        item.subject = str(found[0].get("free_subscription_id") or item.subject)
        item.issued_at = str(found[0].get("issued_at") or item.issued_at)
    log("free issuance %s subject=%s" % (item.repository_guid, item.subject or "?"))
    for sql in free_cleanup_sql(item):
        rows(sql)
    left = rows(q("SELECT id FROM free_license_issuances WHERE repository_guid = $g", g=guid))
    if item.subject:
        left += rows(
            q(
                "SELECT id FROM terms_acceptances WHERE subject_id = $s",
                s=sql_literal(item.subject),
            )
        )
    if left:
        raise DrillError(
            "the free issuance or its acceptance row is still present after the delete"
        )


@dataclass
class Evidence:
    lines: list[str] = field(default_factory=list)
    failed: bool = False

    def add(self, number: int | str, name: str, rc: int, detail: str = "") -> None:
        if rc != 0:
            self.failed = True
        line = "STEP %s %s rc=%d%s" % (number, name, rc, (" " + detail) if detail else "")
        self.lines.append(line)
        print(line, flush=True)


def _http(path: str, body: dict) -> tuple[int, dict]:
    status, answer = deploy_bench._post_json(BENCH_ORIGIN + path, body)
    if status == 0:
        raise DrillError("no HTTP answer from %s%s" % (BENCH_ORIGIN, path))
    return status, answer


def _call(
    method: str, path: str, body: dict | None, headers: Mapping[str, str], jar: str | None
) -> tuple[int, dict]:
    """curl with optional headers and a cookie jar (read and written). The body travels on stdin."""
    argv = ["curl", "-sS", "--connect-timeout", "20", "--max-time", "60", "-X", method]
    argv.append(BENCH_ORIGIN + path)
    argv += ["-H", "Content-Type: application/json", "-w", "\n%{http_code}"]
    for name, value in headers.items():
        argv += ["-H", "%s: %s" % (name, value)]
    if jar:
        argv += ["-b", jar, "-c", jar]
    if body is not None:
        argv += ["--data", "@-"]
    proc = subprocess.run(
        argv,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    text, _, status = (proc.stdout or "").rpartition("\n")
    try:
        code = int(status)
    except ValueError:
        raise DrillError("no HTTP answer from %s%s" % (BENCH_ORIGIN, path)) from None
    try:
        decoded = json.loads(text) if text.strip() else {}
    except ValueError:
        decoded = {}
    return code, decoded if isinstance(decoded, dict) else {}


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


def cleanup(
    email: str,
    rows: Rows,
    log: Callable[[str], None],
    device_codes: Sequence[str] = (),
) -> None:
    """Delete the rows of `email` and of the captured device codes only, and prove the user is gone. DrillError on a leftover."""
    lit = sql_literal(email)
    for sql in device_code_cleanup_sql(device_codes):
        rows(sql)
    for code in device_codes:
        if rows(
            q("SELECT device_code FROM device_codes WHERE user_code = $c", c=sql_literal(code))
        ):
            raise DrillError("the device-code row %s is still present after the delete" % code)
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


class _Process(Background):
    """The CLI prints the verification URL as a human line, which it writes to stderr (outputService.info), so stderr is merged into the stream read here."""

    def __init__(
        self, argv: Sequence[str], env: Mapping[str, str], program: pathlib.Path | None = None
    ) -> None:
        self.proc = subprocess.Popen(
            [str(program or paths.repo_root() / "rdc.sh"), *argv],
            env=dict(env),
            cwd=str(paths.repo_root()),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def read_url(self) -> str:
        stream = self.proc.stdout
        if stream is None:
            raise DrillError("the register command has no output stream")
        deadline = time.monotonic() + URL_WAIT_S
        for line in stream:
            found = VERIFY_URL.search(line)
            if found:
                return found.group(0)
            if time.monotonic() > deadline:
                break
        raise DrillError("the register command printed no verification URL")

    def finish(self, timeout: float) -> int:
        try:
            self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.kill()
            raise DrillError("the register command did not finish in %ds" % timeout) from None
        return self.proc.returncode

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()


def _spawn(argv: Sequence[str], env: Mapping[str, str]) -> Background:
    return _Process(argv, env)


@dataclass
class Deps:
    spawn: Spawn = _spawn
    http: Http = _http
    call: Call = _call
    new_uuid: Callable[[], str] = lambda: str(uuid.uuid4())
    jar_path: Callable[[str], str] = lambda stamp: str(
        pathlib.Path(tempfile.gettempdir()) / ("ftr-jar-%s-%s.txt" % (stamp, secrets.token_hex(4)))
    )
    unlink: Callable[[str], None] = lambda path: pathlib.Path(path).unlink(missing_ok=True)
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


def _window_count(d: Deps, now: datetime) -> int:
    since = datetime.fromtimestamp(now.timestamp() - WINDOW_S, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    got = d.rows(
        q(
            "SELECT count(*) AS window_rows FROM free_license_ip_window WHERE issued_at >= $t",
            t=sql_literal(since),
        )
    )
    return int(got[0].get("window_rows") or 0) if got else -1


def _free_body(item: FreeIssued, stamp: str, extra: dict | None = None) -> dict:
    body: dict = {
        "machineId": "ftr-%s-m" % stamp,
        "clientMachineId": "ftr-%s-c" % stamp,
        "repositoryGuid": item.repository_guid,
        "kind": "grand",
    }
    body.update(extra or {})
    return body


def _step_free_refused(d: Deps, ev: Evidence, item: FreeIssued, stamp: str) -> None:
    before = _window_count(d, d.now())
    status, answer = d.call(
        "POST",
        API + "/licenses/free",
        _free_body(item, stamp),
        {"x-cli-version": CLI_VERSION},
        None,
    )
    after = _window_count(d, d.now())
    # private/account/src/middleware/error-handler.ts spreads an AppError's details beside `error`
    # (the message) and `code`; it writes no nested `details` object for an AppError.
    code, flag = answer.get("code"), answer.get("flag")
    bad: list[str] = []
    if status != 403:
        bad.append("http=%d want 403" % status)
    if code != TERMS_REQUIRED:
        bad.append("code=%r want %s" % (code, TERMS_REQUIRED))
    if flag != "--accept-terms":
        bad.append("flag=%r want --accept-terms" % flag)
    if before != after or before < 0:
        bad.append("window rows %d -> %d" % (before, after))
    ev.add(
        "3b",
        "free-refused",
        1 if bad else 0,
        "http=%d code=%s window_rows=%d->%d%s"
        % (status, code, before, after, ("; " + "; ".join(bad)) if bad else ""),
    )
    if bad:
        raise DrillError("a free licence without terms acceptance was not refused cleanly")


def terms_row_check(row: dict, version: str, sha256: str, method: str) -> list[str]:
    """Reasons an acceptance row differs from the one the step expects."""
    bad: list[str] = []
    if row.get("version") != version:
        bad.append("version=%r want %s" % (row.get("version"), version))
    if row.get("text_sha256") != sha256:
        bad.append("text_sha256 differs from the manifest")
    if row.get("method") != method:
        bad.append("method=%r want %s" % (row.get("method"), method))
    return bad


def _step_free_accepted(
    d: Deps, ev: Evidence, item: FreeIssued, stamp: str, manifest: dict[str, str]
) -> None:
    acceptance = {
        "version": manifest["version"],
        "sha256": manifest["sha256"],
        "locale": "en",
        "method": "cli-flag-unattended",
    }
    status, answer = d.call(
        "POST",
        API + "/licenses/free",
        _free_body(item, stamp, {"termsAcceptance": acceptance}),
        {"x-cli-version": CLI_VERSION},
        None,
    )
    if status != 200 or not answer.get("license"):
        ev.add("3c", "free-accepted", 1, "http=%d no licence issued" % status)
        raise DrillError("the accepted free licence was not issued")
    issued = d.rows(
        q(
            "SELECT free_subscription_id, issued_at FROM free_license_issuances "
            "WHERE repository_guid = $g",
            g=sql_literal(item.repository_guid),
        )
    )
    if len(issued) != 1:
        ev.add("3c", "free-accepted", 1, "issuance rows=%d" % len(issued))
        raise DrillError("the free issuance row is missing")
    item.subject = str(issued[0].get("free_subscription_id") or "")
    item.issued_at = str(issued[0].get("issued_at") or "")
    if not FREE_SUBJECT.match(item.subject):
        ev.add("3c", "free-accepted", 1, "subject=%r is not free:<hmac>" % item.subject)
        raise DrillError("the free subject is malformed")
    found = d.rows(
        q(
            "SELECT version, text_sha256, method, client_ip, cli_version, notice_text "
            "FROM terms_acceptances WHERE subject_id = $s",
            s=sql_literal(item.subject),
        )
    )
    bad: list[str] = []
    if len(found) != 1:
        bad.append("acceptance rows=%d want 1" % len(found))
    else:
        row = found[0]
        bad += terms_row_check(row, manifest["version"], manifest["sha256"], "cli-flag-unattended")
        if row.get("client_ip") is not None:
            bad.append("client_ip is not NULL")
        if not str(row.get("cli_version") or ""):
            bad.append("cli_version empty")
        if not str(row.get("notice_text") or ""):
            bad.append("notice_text empty")
    ev.add(
        "3c",
        "free-accepted",
        1 if bad else 0,
        "issued subject=%s version=%s%s"
        % (item.subject, manifest["version"], ("; " + "; ".join(bad)) if bad else ""),
    )
    if bad:
        raise DrillError("the free acceptance row is wrong")


def _step_terms_gate(d: Deps, ev: Evidence, creds: tuple[str, str], stamp: str) -> None:
    jar = d.jar_path(stamp)
    bad: list[str] = []
    detail = ""
    try:
        status, _ = d.call(
            "POST", API + "/auth/login", {"email": creds[0], "password": creds[1]}, {}, jar
        )
        if status != 200:
            bad.append("login http=%d" % status)
        else:
            _, state = d.call("GET", API + "/portal/terms", None, {}, jar)
            if state.get("satisfied") is not False:
                bad.append("terms.satisfied=%r want False" % state.get("satisfied"))
            gstatus, gate = d.call("GET", API + "/portal/subscription", None, {}, jar)
            err = gate.get("error") if isinstance(gate.get("error"), dict) else gate
            gcode = err.get("code") if isinstance(err, dict) else None
            if gstatus != 403 or gcode != TERMS_REQUIRED:
                bad.append("gated read http=%d code=%r" % (gstatus, gcode))
            manifest = terms_manifest()
            astatus, _ = d.call(
                "POST",
                API + "/portal/terms/accept",
                {
                    "version": manifest["version"],
                    "sha256": manifest["sha256"],
                    "locale": "en",
                    "method": "web-checkbox",
                },
                {},
                jar,
            )
            if astatus != 201:
                bad.append("accept http=%d want 201" % astatus)
            rows = d.rows(
                q(
                    "SELECT t.version, t.text_sha256, t.method, t.client_ip, t.user_agent "
                    "FROM terms_acceptances t JOIN users u ON u.id = t.subject_id "
                    "WHERE u.email = $e",
                    e=sql_literal(creds[0]),
                )
            )
            if len(rows) != 1:
                bad.append("acceptance rows=%d want 1" % len(rows))
            else:
                bad += terms_row_check(
                    rows[0], manifest["version"], manifest["sha256"], "web-checkbox"
                )
                if not str(rows[0].get("client_ip") or ""):
                    bad.append("client_ip empty")
                if not str(rows[0].get("user_agent") or ""):
                    bad.append("user_agent empty")
            detail = "gate=%s accept=%d" % (gstatus, astatus)
    finally:
        d.unlink(jar)
    ev.add(
        "4b",
        "terms-gate",
        1 if bad else 0,
        (detail + "; " if detail else "") + "; ".join(bad) if bad else detail,
    )
    if bad:
        raise DrillError("the portal terms gate did not hold")


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


def _step_handoff(
    d: Deps,
    ev: Evidence,
    base: Mapping[str, str],
    config: str,
    email: str,
    stamp: str,
    limits: dict[str, int],
    codes: list[str],
) -> None:
    bad: list[str] = []
    job = d.spawn(
        [
            "--config",
            config,
            "subscription",
            "register",
            "--email",
            email,
            "--server",
            BENCH_ORIGIN,
        ],
        base,
    )
    jar = d.jar_path(stamp)
    detail = ""
    try:
        url = job.read_url()
        bad += handoff_url_check(url, email)
        parsed = urllib.parse.urlsplit(url)
        code = (urllib.parse.parse_qs(parsed.query).get("code") or [""])[0]
        if USER_CODE.match(code):
            codes.append(code)
        if bad:
            raise DrillError("the printed handoff URL is wrong")
        route = parsed.path + "?" + parsed.query
        rstatus, _ = d.call("GET", route, None, {}, None)
        if rstatus != 200:
            bad.append("anonymous authorize route http=%d want 200" % rstatus)
        since = datetime.fromtimestamp(d.now().timestamp() - CLOCK_SKEW_S, UTC).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        mstatus, _ = d.http(API + "/auth/magic-link", {"email": email, "next": route})
        if mstatus != 200:
            bad.append("magic-link request http=%d" % mstatus)
        token, got_next = "", ""
        for attempt in range(MAIL_ATTEMPTS):
            if token or bad:
                break
            if attempt:
                d.sleep(MAIL_WAIT_S)
            for row in d.rows(mail_query(email, since)):
                token, got_next = extract_magic_link(str(row.get("text_body") or ""))
                if token:
                    break
        if not token:
            bad.append("no magic-link mail reached captured_emails")
        elif got_next != route:
            bad.append("magic link next=%r want %r" % (got_next, route))
        if bad:
            raise DrillError("the sign-up handoff did not hold")
        vstatus, _ = d.call("POST", API + "/auth/magic-link/verify", {"token": token}, {}, jar)
        if vstatus != 200:
            bad.append("magic-link verify http=%d" % vstatus)
            raise DrillError("the handoff sign-up did not open a session")
        _, state = d.call("GET", API + "/portal/terms", None, {}, jar)
        accepted = "already"
        if state.get("satisfied") is not True:
            manifest = terms_manifest()
            astatus, _ = d.call(
                "POST",
                API + "/portal/terms/accept",
                {
                    "version": manifest["version"],
                    "sha256": manifest["sha256"],
                    "locale": "en",
                    "method": "web-checkbox",
                },
                {},
                jar,
            )
            accepted = "http=%d" % astatus
            if astatus != 201:
                bad.append("terms accept http=%d want 201" % astatus)
        pstatus, approved = d.call("POST", API + "/device-codes/%s/approve" % code, None, {}, jar)
        if pstatus != 200 or approved.get("approved") is not True:
            bad.append("approve http=%d approved=%r" % (pstatus, approved.get("approved")))
        rc = job.finish(REGISTER_WAIT_S)
        if rc != 0:
            bad.append("register exit=%d want 0" % rc)
        src, out = d.rdc(["--config", config, "subscription", "status", "-o", "json"], base)
        report = _envelope(out).get("data") or {}
        bad += plan_check(report, limits) if src == 0 else ["status exit=%d" % src]
        detail = "url ok route=200 next ok terms=%s approve=%d register exit=%d plan=%s" % (
            accepted,
            pstatus,
            rc,
            report.get("plan"),
        )
    except DrillError as exc:
        if str(exc) not in "; ".join(bad):
            bad.append(str(exc))
    finally:
        job.kill()
        d.unlink(jar)
    ev.add("6b", "handoff", 1 if bad else 0, (detail + "; " if detail else "") + "; ".join(bad))
    if bad:
        raise DrillError("the browser handoff failed")


def run(dry_run: bool, deps: Deps | None = None, env: Mapping[str, str] | None = None) -> int:
    d = deps or Deps()
    base = {k: v for k, v in (os.environ if env is None else env).items() if k not in SCRUBBED}
    ev = Evidence()
    started = d.now()
    stamp = stamp_now(started)
    email = address_for(stamp)
    config = "ftr-" + stamp
    if dry_run:
        for label, name in STEPS:
            print("DRY-RUN STEP %s %s config=%s email=%s" % (label, name, config, email))
        return 0
    limits = community_limits()
    password = d.password()
    since_iso = datetime.fromtimestamp(started.timestamp() - CLOCK_SKEW_S, UTC).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    config_made = registered = False
    free_item = FreeIssued(repository_guid=d.new_uuid())
    free_started = False
    handoff_codes: list[str] = []
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
        manifest = terms_manifest()
        _step_free_refused(d, ev, free_item, stamp)
        free_started = True
        _step_free_accepted(d, ev, free_item, stamp, manifest)

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

        _step_terms_gate(d, ev, (email, password), stamp)
        _step_email(d, ev, email, since_iso)
        _step_login(d, ev, base, config, (email, password), limits)
        _step_handoff(d, ev, base, config, email, stamp, limits, handoff_codes)
    except DrillError as exc:
        # A refusal raised before its STEP line (no HTTP answer, a missing config) must still fail the run (review 23c783db.1).
        ev.failed = True
        print("drill: %s" % exc, file=sys.stderr)
    finally:
        notes: list[str] = []
        crc = 0
        if free_started:
            try:
                cleanup_free(free_item, d.rows, notes.append)
            except DrillError as exc:
                crc = 1
                notes.append(str(exc))
        if registered or handoff_codes:
            try:
                cleanup(email, d.rows, notes.append, handoff_codes)
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
