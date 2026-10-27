"""Port of `scripts/ops/deploy-bench.sh` (293 lines): deploy the account worker to bench.rediacc.com.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench

Bench is the internal "real Cloudflare D1" environment, deliberately NOT wired into CI or CD: a deploy is an operator running this by hand. The steps are the bash's, in order: re-exec under the `deploy-bench` Bitwarden profile (`rediacc_ci.core.bws_env exec`), resolve Cloudflare auth (`cf_auth`), preflight (`bench_preflight`: lockfile and R2 bucket), build the account portal SPA with the bench Turnstile sitekey, apply D1 migrations to `account-db-bench`, `wrangler deploy --config wrangler.bench.toml`, run `./run.sh rotation check --for=bench`, then push the worker secrets with `wrangler secret bulk`.

THE ROTATION CHECK ALWAYS COMPARES, AND ANYTHING BUT "IN SYNC" REFUSES THE PUSH (operator ruling 2026-10-13). The check reads the observability host's OTLP basicauth user names over plain OpenSSH, through `private/account/scripts/rotation/lib/observability-reader.ts`, with the three `OBS_READER_SSH_*` values this profile binds: the base64 of the machine's existing private key, the pinned known_hosts lines and `user@host[:port]`. No `rdc` login is involved. Exit 1 is drift; exit 2 is a credential that could not be read, which is reported as such with its cause and refuses the push as well, because an unread value is an uncompared one.

Resources: D1 `account-db-bench`, R2 `rediacc-configs-bench`, worker `rediacc-account-bench`, domain `bench.rediacc.com`. The cleanup of the Cloudflare token runs on every way out, a supplied `CF_MANAGEMENT_TOKEN` included, as in the bash.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_deploy_bench.py` that fails on the bash behaviour).

  1. ARGUMENTS ARE REJECTED. The script took no arguments and ignored every one it was given, so `deploy-bench.sh --dry-run` (the natural thing to type before a deploy to a shared environment) performed a real deploy. An argument now exits 2 before anything runs; `-h`/`--help` prints usage.
  2. THE TOKEN-PROPAGATION WAIT IS TAKEN ONLY FOR A TOKEN THIS RUN MINTED (`cf_auth.await_propagation`: GET probes until every slow service the token grants accepts it twice in a row, at most 60 s, then a named error and exit 1). The bash's unconditional `sleep 5` existed because a freshly created management token can race Cloudflare's propagation; an operator-supplied token cannot.
  3. NO `jq`. Every JSON read and the secrets payload are built in-process, so the `require_cmd jq` precondition is gone.
  4. THE SIX REQUIRED SIGNING KEYS REPORT THROUGH THE LOGGER with the same wording, instead of bash's `script: line N: NAME: message` text, which named a line number that no longer meant anything after any edit.
  5. THE SECRETS ARE VALIDATED BEFORE THE FIRST REMOTE WRITE. The six signing keys, the non-empty checks and the OTLP probe ran after the migrations and the deploy, so a missing value left bench on new code with the old secrets, the 2026-09-24 failure shape (state changed, then refused). Only the rotation drift check still runs after the deploy, as it did.
  6. A FAILED STEP NAMES ITSELF. Under `set -e` a failing `npm install`, `vite build`, migration or deploy ended the script silently with that command's status; each exits 1 with `<step> failed (exit N)`.
  7. THE BACKUP CREDENTIAL HAS NO FALLBACK, AND THE BUCKET COMES FROM THE BINDING (`bench_bucket`: `wrangler.bench.toml`'s BACKUP_BUCKET, not an env override or a literal; a differing exported value or a missing binding is a DeployError). The bash filled each empty `ACCOUNT_BACKUP_S3_*` value from the account-wide R2 token, and the profile supplied only that token, so the public bench Worker held a key that reaches every bucket in the account. Only the three `ACCOUNT_BACKUP_S3_*` names are read now, bound from the bench-scoped store entries, and a missing one is a DeployError naming it before the first remote write (agent/plans/PLAN-backup-credential-isolation.md B2).

  8. THE ROOT PRINCIPAL IS SEEDED (`seed_root`, after the secrets push, or alone with `--seed-root`). `reset_bench` drops every table and the deploy sets ROOT_EMAIL as a Worker secret, but nothing created the user, so the console `ExecutorIssuer` refused with ISSUER_OWNER_UNKNOWN and the bench proxy readiness failed (found 2026-10-26, worked around by registering the user by hand). The seed calls the server's own `POST /account/api/v1/auth/register` (bench has no `/test/*` surface and the captcha is off): one atomic batch that creates the user, its org, the owner membership and a live `inactive` COMMUNITY subscription, which is everything `ExecutorIssuerService.issue` checks. The password is the stored secret `BENCH_ROOT_PASSWORD` (operator ruling 2026-10-26: "Store a bench root password"), bound by the deploy-bench profile and sent on curl's stdin, never on argv and never printed; an unset or too-short value is a named SeedError before anything is registered. An answer of 409 EMAIL_EXISTS is the idempotent no-op, since registration is atomic and the user can only exist with its org and subscription; any other answer is a named SeedError. A user registered earlier with another password keeps it: `--set-root-password` moves it to the stored one through the server's own password-reset flow (item 9).

  9. THE STORED PASSWORD IS SET ON AN EXISTING ROOT USER THROUGH THE RESET FLOW (`set_root_password`, `--set-root-password`). The account server has no root route that sets a password, but it has `POST /account/api/v1/auth/forgot` (mails a reset link, kind `password-reset`) and `POST /account/api/v1/auth/reset {token, password}` (sets it, clears the lockout, revokes every session). Bench copies each outgoing email into the D1 table `captured_emails` (EMAIL_CAPTURE_D1, bench only), so the run asks for the link, reads the newest `password-reset` row for ROOT_EMAIL through `wrangler d1 execute` and posts the token with the stored password. The token is extracted in process and never printed, logged or put on argv. Wrangler authenticates with the Global API Key pair, as the documented captured-email read does.

THE SECRET VALUES ARE READ BY NAME FROM THE ENVIRONMENT, as the bash read them, and are never logged; the `OBS_OTLP_CREDENTIALS` validity probe reports only that the value is not a JSON {user, pass} object, never the value.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import string
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.ops import bench_access, bench_preflight, cf_auth, push_backup_credentials
from rediacc_ci.well_known import BENCH_ORIGIN

if TYPE_CHECKING:
    from collections.abc import Callable

BENCH_HOST = BENCH_ORIGIN.removeprefix("https://")

ACCOUNT_ID = cf_auth.DEFAULT_ACCOUNT_ID
WORKER_NAME = "rediacc-account-bench"
CONFIG = "wrangler.bench.toml"
DB_NAME = "account-db-bench"
DOMAIN = BENCH_HOST
# Bench is test-only (operator ruling 2026-10-13): the portal is built with NO site key, so the
# widget never renders, and wrangler.bench.toml sets TURNSTILE_ENABLED=false for the API.
TURNSTILE_SITEKEY = ""
PROFILE = "deploy-bench"
MISSING = "%s missing from the deploy-bench profile"
HELP = (
    """Deploy the account worker to """
    + BENCH_HOST
    + """.

Usage:
  deploy_bench              deploy, then seed the root user
  deploy_bench --seed-root  only seed the root user (idempotent)
  deploy_bench --set-root-password
                            set BENCH_ROOT_PASSWORD on the existing root user (reset flow)

bench is IP-restricted (rediacc_ci.ops.bench_access): a 403 from bench means
run PYTHONPATH=.ci python3 -m rediacc_ci.ops.bench_access add-current first.

Credentials come from the deploy-bench Bitwarden profile; see
.ci/config/secret-supply.json. Cloudflare auth: CF_MANAGEMENT_TOKEN, or
CF_GLOBAL_API_KEY + CF_EMAIL, or an interactive prompt.
"""
)


class DeployError(Exception):
    """A step failed; the message is printed and the run exits 1."""


# The three backup-plane values, read by these names and no others. The deploy-bench profile binds the two credential names from the bench-only store entries (`ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH`, `ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY_BENCH`), a token scoped to object read and write on the bench backup bucket. There is NO fallback: the account-wide R2 token once filled these three slots whenever they were empty, which put an account-wide key on the public bench Worker (agent/plans/PLAN-backup-credential-isolation.md). `check:ci-backup-credential-isolation` refuses that fallback's return.
BACKUP_NAMES: tuple[str, ...] = (
    "ACCOUNT_BACKUP_S3_ENDPOINT",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
)


def _backup_values() -> tuple[str, str, str]:
    """The endpoint, key id and secret for the bench backup bucket. Raises DeployError naming the first one that is missing or empty."""
    endpoint = os.environ.get("ACCOUNT_BACKUP_S3_ENDPOINT") or ""
    key_id = os.environ.get("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID") or ""
    secret = os.environ.get("ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY") or ""
    for name, value in zip(BACKUP_NAMES, (endpoint, key_id, secret), strict=True):
        if not value:
            raise DeployError(
                "%s is EMPTY for bench. The deploy-bench profile binds it (the key pair from "
                "the bench-scoped store entries, .ci/config/secret-supply.json); the "
                "account-wide R2 token is never a fallback for it" % name
            )
    return endpoint, key_id, secret


def bench_bucket() -> str:
    """The bench backup bucket, read from the BACKUP_BUCKET binding in wrangler.bench.toml, the bucket the Worker reads and sweeps. An exported ACCOUNT_BACKUP_S3_BUCKET that differs from it, or a config with no such binding, is a DeployError."""
    config_path = paths.repo_root().joinpath(*push_backup_credentials.WORKER_DIR, CONFIG)
    try:
        _, bucket, _ = push_backup_credentials._config_binding(config_path)
    except push_backup_credentials.PushError as exc:
        raise DeployError(str(exc)) from exc
    if not bucket:
        raise DeployError("%s binds %s with no bucket_name" % (CONFIG, "BACKUP_BUCKET"))
    override = os.environ.get("ACCOUNT_BACKUP_S3_BUCKET") or ""
    if override and override != bucket:
        raise DeployError(
            "ACCOUNT_BACKUP_S3_BUCKET is %r but %s binds %r: the presign signer and the Worker's "
            "binding must name one bucket. Unset the variable; the bucket comes from the binding"
            % (override, CONFIG, bucket)
        )
    return bucket


def require_nonempty(name: str, value: str) -> None:
    """A secret that reached the push empty would be pushed empty and validated happily by the worker."""
    if not value:
        raise DeployError(
            "%s is EMPTY for bench. Check its entry in Bitwarden (deploy-bench profile, "
            ".ci/config/secret-supply.json)" % name
        )


def otlp_credentials_valid(value: str) -> bool:
    """True when the value is a JSON object whose `user` and `pass` are strings (the one value the worker JSON.parses)."""
    try:
        decoded = json.loads(value)
    except ValueError:
        return False
    return (
        isinstance(decoded, dict)
        and isinstance(decoded.get("user"), str)
        and isinstance(decoded.get("pass"), str)
    )


def secrets_payload() -> dict[str, str]:
    """The `wrangler secret bulk` body, keys in the order the bash emitted them. Raises DeployError on a missing or empty required value."""
    signing = {
        "ACCOUNT_ED25519_PRIVATE_KEY": os.environ.get("ACCOUNT_ED25519_PRIVATE_KEY") or "",
        "ACCOUNT_ED25519_PUBLIC_KEY": os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY") or "",
        "ACCOUNT_X25519_PRIVATE_KEY": os.environ.get("ACCOUNT_X25519_PRIVATE_KEY") or "",
        "ACCOUNT_X25519_PUBLIC_KEY": os.environ.get("ACCOUNT_X25519_PUBLIC_KEY") or "",
        "ACCOUNT_SERVER_API_KEY": os.environ.get("ACCOUNT_SERVER_API_KEY") or "",
        "ACCOUNT_JWT_SECRET": os.environ.get("ACCOUNT_JWT_SECRET") or "",
        # Layer 3 of the config store; the deploy-bench profile binds the bench-only vault entry under this name (agent/plans/PLAN-config-server-key.md K2).
        "ACCOUNT_CONFIG_SERVER_KEY": os.environ.get("ACCOUNT_CONFIG_SERVER_KEY") or "",
    }
    for name, value in signing.items():
        if not value:
            raise DeployError(MISSING % name)
    require_nonempty("ROOT_EMAIL", os.environ.get("ROOT_EMAIL") or "")
    require_nonempty("AWS_SES_ACCESS_KEY_ID", os.environ.get("AWS_SES_ACCESS_KEY_ID") or "")
    require_nonempty("AWS_SES_SECRET_ACCESS_KEY", os.environ.get("AWS_SES_SECRET_ACCESS_KEY") or "")
    require_nonempty(
        "CLOUDFLARE_TURNSTILE_SECRET_KEY", os.environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY") or ""
    )
    endpoint, backup_key, backup_secret = _backup_values()
    otlp = os.environ.get("OBS_OTLP_CREDENTIALS") or ""
    require_nonempty("OBS_OTLP_CREDENTIALS", otlp)
    if not otlp_credentials_valid(otlp):
        raise DeployError(
            'OBS_OTLP_CREDENTIALS is not a JSON {"user","pass"} object for bench: '
            "re-mint it with ./run.sh rotation rotate otlp-bench"
        )
    return {
        "ACCOUNT_ED25519_PRIVATE_KEY": signing["ACCOUNT_ED25519_PRIVATE_KEY"],
        "ACCOUNT_ED25519_PUBLIC_KEY": signing["ACCOUNT_ED25519_PUBLIC_KEY"],
        "ACCOUNT_X25519_PRIVATE_KEY": signing["ACCOUNT_X25519_PRIVATE_KEY"],
        "ACCOUNT_X25519_PUBLIC_KEY": signing["ACCOUNT_X25519_PUBLIC_KEY"],
        "ACCOUNT_SERVER_API_KEY": signing["ACCOUNT_SERVER_API_KEY"],
        "ACCOUNT_JWT_SECRET": signing["ACCOUNT_JWT_SECRET"],
        "ACCOUNT_CONFIG_SERVER_KEY": signing["ACCOUNT_CONFIG_SERVER_KEY"],
        # Stripe is disabled (empty strings) so the worker boots without billing, as edge does.
        "STRIPE_SECRET_KEY": "",
        "STRIPE_WEBHOOK_SECRET": "",
        "ROOT_EMAIL": os.environ.get("ROOT_EMAIL") or "",
        "AWS_SES_ACCESS_KEY_ID": os.environ.get("AWS_SES_ACCESS_KEY_ID") or "",
        "AWS_SES_SECRET_ACCESS_KEY": os.environ.get("AWS_SES_SECRET_ACCESS_KEY") or "",
        "AWS_SES_REGION": os.environ.get("AWS_SES_REGION") or "eu-central-1",
        "AWS_SES_FROM": os.environ.get("AWS_SES_FROM") or "noreply@notify.rediacc.com",
        "AWS_SES_CONFIGURATION_SET": os.environ.get("AWS_SES_CONFIGURATION_SET") or "",
        "CLOUDFLARE_TURNSTILE_SECRET_KEY": os.environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY") or "",
        "ACCOUNT_BACKUP_S3_ENDPOINT": endpoint,
        "ACCOUNT_BACKUP_S3_BUCKET": bench_bucket(),
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": backup_key,
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": backup_secret,
        "OBS_OTLP_CREDENTIALS": otlp,
        "SELLER_NAME": os.environ.get("SELLER_NAME") or "",
        "SELLER_VAT_NUMBER": os.environ.get("SELLER_VAT_NUMBER") or "",
        "SELLER_REGISTRATION_NUMBER": os.environ.get("SELLER_REGISTRATION_NUMBER") or "",
        "SELLER_ADDRESS_LINE1": os.environ.get("SELLER_ADDRESS_LINE1") or "",
        "SELLER_ADDRESS_LINE2": os.environ.get("SELLER_ADDRESS_LINE2") or "",
        "SELLER_CITY": os.environ.get("SELLER_CITY") or "",
        "SELLER_POSTAL_CODE": os.environ.get("SELLER_POSTAL_CODE") or "",
        "SELLER_COUNTRY": os.environ.get("SELLER_COUNTRY") or "",
        "SELLER_EMAIL": os.environ.get("SELLER_EMAIL") or "",
    }


def _run(
    argv: list[str], cwd, what: str, env: dict[str, str] | None = None, stdin: str | None = None
) -> None:
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        input=stdin,
        text=True if stdin is not None else None,
        check=False,
    )
    if proc.returncode != 0:
        raise DeployError("%s failed (exit %d)" % (what, proc.returncode))


# A D1 bookmark as `wrangler d1 time-travel info` prints it: three 8-hex groups and a long hex tail.
BOOKMARK_PATTERN = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{16,}\b")


def restore_command(bookmark: str) -> str:
    return "npx wrangler d1 time-travel restore %s --bookmark=%s --config %s" % (
        DB_NAME,
        bookmark,
        CONFIG,
    )


def capture_bookmark(worker_dir) -> str | None:
    """Print the D1 bookmark taken BEFORE the migrations, with the exact restore command: a Worker rollback does not undo a migration, so the bookmark is the rollback handle. A failed capture is reported loudly and returns None; the deploy goes on (the migrations are not blocked on a read-only query, and the bash had no bookmark at all)."""
    try:
        proc = subprocess.run(
            ["npx", "wrangler", "d1", "time-travel", "info", DB_NAME, "--config", CONFIG],
            cwd=str(worker_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        found = BOOKMARK_PATTERN.search(proc.stdout or "")
        failure = (
            ""
            if proc.returncode == 0 and found
            else "wrangler d1 time-travel info exited %d%s"
            % (proc.returncode, "" if found else " and printed no bookmark")
        )
        detail = (proc.stderr or "").strip()
    except OSError as exc:
        found, failure, detail = None, "wrangler d1 time-travel info could not run", str(exc)
    if failure or not found:
        log.warn(
            "NO D1 BOOKMARK CAPTURED for %s (%s%s): the migrations below cannot be rolled back "
            "to a known point. Continuing."
            % (DB_NAME, failure, "; " + detail.splitlines()[-1] if detail else "")
        )
        return None
    bookmark = found.group(0)
    log.info("D1 bookmark before migrations: %s" % bookmark)
    print("  restore: %s" % restore_command(bookmark))
    return bookmark


def _reexec_under_profile(argv: list[str]) -> int | None:
    """Run the same entry point under the deploy-bench Bitwarden profile and return its exit status; None when already bound."""
    profiles = (os.environ.get("REDIACC_BWS_PROFILES") or "").split(",")
    if PROFILE in profiles:
        return None
    root = paths.repo_root()
    env = dict(os.environ)
    ci = str(root / ".ci")
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
            "rediacc_ci.ops.deploy_bench",
            *argv,
        ],
        env=env,
        check=False,
    ).returncode


# `rotation check` exits 0 in sync, 1 on drift (a live value was read and differs), 2 when nothing drifted but a credential could not be checked (the query failed, so nothing was compared). Pinned to EXIT_COULD_NOT_CHECK in private/account/scripts/rotation/commands/check.ts.
ROTATION_COULD_NOT_CHECK_RC = 2


def _could_not_check_lines(stderr: str) -> list[str]:
    """The `  <credential>: <cause>` lines under the check's "could not check" header, so the refusal names each credential and why."""
    lines: list[str] = []
    collecting = False
    for line in stderr.splitlines():
        if "could not check" in line:
            collecting = True
        elif collecting and line.startswith("  ") and line.strip():
            lines.append(line.strip())
        elif collecting:
            collecting = False
    return lines


def _rotation_check(root) -> None:
    """Refuse the secrets push unless the check read every credential and found it in sync. Drift (exit 1) and a check that could not read a credential (exit 2) both refuse, and are worded apart: an unread value is not drift, and rotating does not fix it."""
    log.step("Rotation preflight: ./run.sh rotation check --for=bench")
    # The check's progress goes to stderr; it is echoed as it arrives and kept to name what could not be checked.
    seen: list[str] = []
    with subprocess.Popen(
        [str(root / "run.sh"), "rotation", "check", "--for=bench"],
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    ) as proc:
        for line in proc.stderr or ():
            sys.stderr.write(line)
            seen.append(line)
    rc = proc.returncode
    if rc == 0:
        return
    if rc == ROTATION_COULD_NOT_CHECK_RC:
        unchecked = _could_not_check_lines("".join(seen)) or ["(the check named no credential)"]
        raise DeployError(
            "rotation check could NOT READ every credential, so refusing to push secrets to bench\n"
            + "\n".join("  not checked, " + line for line in unchecked)
            + "\nthis is NOT drift: nothing was compared for the credentials above, and a rotation does not help.\n"
            "fix: the cause named on each line, then deploy again"
        )
    if rc != 1:
        raise DeployError("rotation check failed with exit %d, so refusing to push secrets" % rc)
    unchecked = _could_not_check_lines("".join(seen))
    raise DeployError(
        "rotation drift detected, so refusing to push stale secrets to bench\n"
        + (
            "".join("  not checked, " + line + "\n" for line in unchecked)
            + "the credentials above were also NOT read, so nothing was compared for them\n"
            if unchecked
            else ""
        )
        + "fix: run `./run.sh rotation rotate <slug>` for the credentials that drifted"
    )


# A Worker that accepts the connection and never answers must read as "no HTTP answer" (retried, then a named SeedError), not hang the deploy.
CURL_CONNECT_TIMEOUT_S = 10
CURL_MAX_TIME_S = 30


class SeedError(DeployError):
    """The root principal could not be created or confirmed."""


def _post_json(url: str, body: dict[str, str]) -> tuple[int, dict]:
    """POST the JSON body on curl's stdin (the password is never on argv) and return (HTTP status, decoded object). Status 0 means no HTTP answer."""
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "--connect-timeout",
            str(CURL_CONNECT_TIMEOUT_S),
            "--max-time",
            str(CURL_MAX_TIME_S),
            "-X",
            "POST",
            url,
            "-H",
            "Content-Type: application/json",
            "--data",
            "@-",
            "-w",
            "\n%{http_code}",
        ],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        check=False,
    )
    text, _, status = (proc.stdout or "").rpartition("\n")
    try:
        code = int(status)
    except ValueError:
        code = 0
    try:
        decoded = json.loads(text) if text.strip() else {}
    except ValueError:
        decoded = {}
    return code, decoded if isinstance(decoded, dict) else {}


ROOT_LOGIN_ENV = "BENCH_ROOT_PASSWORD"
# The server's own bounds on a password (private/account/src/types/user.ts: min 8, max 128).
PASSWORD_MIN, PASSWORD_MAX = 8, 128


def root_password() -> str:
    """The stored bench root password, read by name from the environment (the deploy-bench profile binds it). SeedError naming the variable when it is unset or outside the server's length bounds; the value is never part of a message."""
    value = os.environ.get(ROOT_LOGIN_ENV) or ""
    if not value:
        raise SeedError(
            "%s is not set: the deploy-bench profile binds it from the store entry of the same "
            "name (.ci/config/secret-supply.json), written once with `bws_env store-from-env` "
            "(usage in rediacc_ci/core/bws_env.py)" % ROOT_LOGIN_ENV
        )
    if not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
        raise SeedError(
            "%s must be %d to %d characters (the server's bounds), not %d"
            % (ROOT_LOGIN_ENV, PASSWORD_MIN, PASSWORD_MAX, len(value))
        )
    return value


def _blocked_hint(status: int) -> str:
    """The fix a 403 from bench most likely needs: the zone rule of `bench_access` answered it."""
    return "; " + bench_access.HINT if status == 403 else ""


def seed_root(
    base_url: str = "https://" + DOMAIN,
    email: str | None = None,
    attempts: int = 6,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Create the ROOT_EMAIL user with its org, membership and subscription through POST /account/api/v1/auth/register; return "created" or "exists". The password is `BENCH_ROOT_PASSWORD` (`root_password`). A 409 with code EMAIL_EXISTS is the no-op, and leaves an existing user's password alone (`set_root_password` changes that). A fresh deploy may still be warming up, so no HTTP answer or a 5xx is retried (`attempts`, 5 s apart); every other answer raises SeedError naming the status and the server's message, never the password."""
    root_email = email if email is not None else os.environ.get("ROOT_EMAIL") or ""
    if not root_email:
        raise SeedError("ROOT_EMAIL is not set, so there is no root user to seed on bench")
    password = root_password()
    # The Worker serves its API under /account/api/v1 (private/account/src/routes/index.ts mounts /auth there); a bare /auth/register is a 404.
    url = base_url.rstrip("/") + "/account/api/v1/auth/register"
    last = "no HTTP answer"
    for attempt in range(attempts):
        if attempt:
            sleep(5)
        status, answer = _post_json(url, {"email": root_email, "password": password})
        if status == 201:
            return "created"
        if status == 409 and answer.get("code") == "EMAIL_EXISTS":
            return "exists"
        last = "HTTP %d: %s" % (status, answer.get("error") or "no error text") if status else last
        if 0 < status < 500:
            last += _blocked_hint(status)
            break
    raise SeedError(
        "seeding the bench root user %s failed (%s): the console ExecutorIssuer refuses with "
        "ISSUER_OWNER_UNKNOWN until it exists" % (root_email, last)
    )


# The reset link in the captured email: `<base>/account/reset-password?token=<raw>` (AuthService.createPasswordReset).
RESET_TOKEN = re.compile(r"reset-password\?token=([A-Za-z0-9_\-]+)")
EMAIL_SHAPE = re.compile(r"^[^\s'\"\\;]+@[^\s'\"\\;]+$")
# How long the mail is waited for: the Worker writes the capture before it answers /auth/forgot, so a short window covers D1 read lag.
MAIL_ATTEMPTS = 6
MAIL_WAIT_S = 3.0
CLOCK_SKEW = timedelta(seconds=60)
# wrangler d1 execute has no bind parameters, so the two values are quoted by `_sql_literal` into a fixed template.
MAIL_QUERY = string.Template(
    "SELECT text_body FROM captured_emails WHERE recipient = $recipient AND kind = 'password-reset' "
    "AND created_at >= $since ORDER BY created_at DESC LIMIT 1"
)


def _sql_literal(value: str) -> str:
    """A SQL string literal for `value`: single quotes doubled."""
    return "'" + value.replace("'", "''") + "'"


def _d1_rows(sql: str) -> list[dict]:
    """`wrangler d1 execute account-db-bench --remote --json --command SQL` from the worker dir, authenticated with the Global API Key pair, and the result rows. The stdout is never printed: it holds live links."""
    key, mail = os.environ.get("CF_GLOBAL_API_KEY"), os.environ.get("CF_EMAIL")
    if not (key and mail):
        raise SeedError("CF_GLOBAL_API_KEY and CF_EMAIL are required to read the captured email")
    env = dict(os.environ)
    for name in ("CLOUDFLARE_API_TOKEN", "CF_API_KEY"):
        env.pop(name, None)
    env["CLOUDFLARE_API_KEY"], env["CLOUDFLARE_EMAIL"] = key, mail
    env["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT_ID
    argv = ["npx", "wrangler", "d1", "execute", DB_NAME, "--remote", "--config", CONFIG]
    argv.extend(["--json", "--command", sql])
    proc = subprocess.run(
        argv,
        cwd=str(paths.repo_root() / "workers" / "account"),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SeedError("wrangler d1 execute failed (exit %d)" % proc.returncode)
    try:
        decoded = json.loads(proc.stdout)
        rows = decoded[0]["results"]
    except (ValueError, LookupError, TypeError):
        raise SeedError("wrangler d1 execute printed no result rows") from None
    return [r for r in rows if isinstance(r, dict)]


def set_root_password(
    base_url: str = "https://" + DOMAIN,
    email: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rows: Callable[[str], list[dict]] = _d1_rows,
) -> None:
    """Set `BENCH_ROOT_PASSWORD` on the existing root user through the server's reset flow: POST /auth/forgot, read the `password-reset` mail bench copies into `captured_emails`, POST /auth/reset with the token and the stored password. SeedError names the failing step; neither the token nor the password is printed."""
    root_email = email if email is not None else os.environ.get("ROOT_EMAIL") or ""
    if not root_email:
        raise SeedError("ROOT_EMAIL is not set, so there is no root user to update on bench")
    if not EMAIL_SHAPE.match(root_email):
        raise SeedError("ROOT_EMAIL is not a plain address, so it is not put into a query")
    password = root_password()
    api = base_url.rstrip("/") + "/account/api/v1/auth/"
    since = (datetime.now(UTC) - CLOCK_SKEW).strftime("%Y-%m-%dT%H:%M:%S")
    status, answer = _post_json(api + "forgot", {"email": root_email})
    if status != 200:
        raise SeedError(
            "POST /auth/forgot answered HTTP %d: %s%s"
            % (status, answer.get("error") or "no error text", _blocked_hint(status))
        )
    sql = MAIL_QUERY.substitute(recipient=_sql_literal(root_email), since=_sql_literal(since))
    token = ""
    for attempt in range(MAIL_ATTEMPTS):
        if attempt:
            sleep(MAIL_WAIT_S)
        for row in rows(sql):
            found = RESET_TOKEN.search(str(row.get("text_body") or ""))
            token = found.group(1) if found else token
        if token:
            break
    if not token:
        raise SeedError(
            "no password-reset mail for %s reached captured_emails (is ROOT_EMAIL a registered "
            "user, and the address inside the bench email allowlist?)" % root_email
        )
    status, answer = _post_json(api + "reset", {"token": token, "password": password})
    if status != 200 or answer.get("reset") is not True:
        raise SeedError(
            "POST /auth/reset answered HTTP %d: %s"
            % (status, answer.get("error") or "no error text")
        )


def _set_password_and_report() -> None:
    log.step(
        "Setting the stored root password on %s at https://%s"
        % (os.environ.get("ROOT_EMAIL") or "ROOT_EMAIL (unset)", DOMAIN)
    )
    set_root_password()
    log.info("root password set to %s (every root session was revoked)" % ROOT_LOGIN_ENV)


def _seed_and_report() -> None:
    log.step(
        "Seeding the root user (%s) on https://%s"
        % (os.environ.get("ROOT_EMAIL") or "ROOT_EMAIL (unset)", DOMAIN)
    )
    outcome = seed_root()
    log.info(
        "root user created with its org and subscription"
        if outcome == "created"
        else "root user already present, nothing to do"
    )


def _deploy(auth: cf_auth.Auth, root) -> None:
    worker_dir = root / "workers" / "account"
    if not (worker_dir / CONFIG).is_file():
        raise DeployError("%s missing" % (worker_dir / CONFIG))

    # Validate the secrets before the first remote write: a missing key found after the migrations and the deploy leaves bench on new code with old secrets.
    body = json.dumps(secrets_payload())
    # The seed after the push needs it, and a refusal there would leave the deploy done and the root user unseeded.
    root_password()

    # The wrangler children (and bench_preflight's) inherit this process's environment.
    os.environ["CLOUDFLARE_API_TOKEN"] = auth.token
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT_ID
    for name in ("CF_GLOBAL_API_KEY", "CF_API_KEY", "CF_EMAIL"):
        os.environ.pop(name, None)
    cf_auth.await_propagation(auth)

    log.step("Preflight: installed dependencies match the lockfiles")
    if bench_preflight.lockfile([str(root), str(root / "private" / "account")]) != 0:
        raise DeployError("preflight failed")
    log.step("Preflight: every R2 bucket bound in %s exists" % CONFIG)
    cwd = os.getcwd()
    os.chdir(worker_dir)
    try:
        if bench_preflight.buckets(CONFIG) != 0:
            raise DeployError("preflight failed")
    finally:
        os.chdir(cwd)

    log.step("Building account portal SPA (captcha disabled on bench: no Turnstile sitekey)")
    web_dir = root / "private" / "account" / "web"
    if not (web_dir / "node_modules").is_dir():
        _run(["npm", "install"], web_dir, "npm install")
    build_env = dict(os.environ)
    build_env["VITE_TURNSTILE_SITE_KEY"] = TURNSTILE_SITEKEY
    build_env["VITE_CI_MODE"] = "false"
    _run(
        ["npx", "vite", "build", "--outDir", str(worker_dir / "dist" / "account")],
        web_dir,
        "vite build",
        env=build_env,
    )
    log.info("Account portal built → %s" % (worker_dir / "dist" / "account"))

    if not (worker_dir / "node_modules").is_dir():
        _run(["npm", "install"], worker_dir, "npm install")
    capture_bookmark(worker_dir)
    log.step("Applying D1 migrations to %s (remote)" % DB_NAME)
    _run(
        ["npx", "wrangler", "d1", "migrations", "apply", DB_NAME, "--remote", "--config", CONFIG],
        worker_dir,
        "wrangler d1 migrations apply",
    )
    log.info("Migrations applied")

    log.step("Deploying %s → https://%s" % (WORKER_NAME, DOMAIN))
    _run(["npx", "wrangler", "deploy", "--config", CONFIG], worker_dir, "wrangler deploy")
    log.info("Worker deployed")

    _rotation_check(root)
    _run(
        ["npx", "wrangler", "secret", "bulk", "--name", WORKER_NAME],
        worker_dir,
        "wrangler secret bulk",
        stdin=body,
    )
    log.info("Worker secrets pushed")
    _seed_and_report()

    print()
    log.info("bench is live: https://%s" % DOMAIN)
    print("  D1:     %s (ac45c2de-053b-404c-bc47-9ad9cbd2bb15)" % DB_NAME)
    print("  R2:     rediacc-configs-bench")
    print("  Worker: %s" % WORKER_NAME)
    print()
    print("Test it:")
    print("  ./rdc.sh --config bench subscription login")
    print("  ./rdc.sh --config bench repo create --name my-app -m my-server --size 2G")


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        sys.stdout.write(HELP)
        return 0
    seed_only = argv == ["--seed-root"]
    password_only = argv == ["--set-root-password"]
    if argv and not (seed_only or password_only):
        log.error("Unknown argument: %s" % argv[0])
        log.error(
            "deploy_bench takes no arguments but --seed-root and --set-root-password; "
            "run with --help for usage."
        )
        return 2
    # The seed path only runs curl; npx is for the deploy and the captured-email read.
    for cmd in ("curl",) if seed_only else ("curl", "npx"):
        if shutil.which(cmd) is None:
            log.error("Required command '%s' is not available" % cmd)
            return 1
    rebound = _reexec_under_profile(argv)
    if rebound is not None:
        return rebound
    if seed_only or password_only:
        try:
            _set_password_and_report() if password_only else _seed_and_report()
        except DeployError as exc:
            log.error(str(exc))
            return 1
        return 0
    root = paths.repo_root()
    try:
        auth = cf_auth.resolve(ACCOUNT_ID)
    except cf_auth.CfAuthError as exc:
        log.error(str(exc))
        return 1
    try:
        _deploy(auth, root)
    except (DeployError, cf_auth.CfAuthError) as exc:
        for line in str(exc).splitlines():
            log.error(line)
        return 1
    finally:
        cf_auth.self_destruct(auth)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
