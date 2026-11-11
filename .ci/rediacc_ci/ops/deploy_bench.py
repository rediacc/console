"""Port of `scripts/ops/deploy-bench.sh` (293 lines): deploy the account worker to bench.rediacc.cloud.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench

Bench is the internal "real Cloudflare D1" environment, deliberately NOT wired into CI or CD: a deploy is an operator running this by hand. The steps are the bash's, in order: re-exec under the `deploy-bench` Bitwarden profile (`rediacc_ci.core.bws_env exec`), resolve Cloudflare auth (`cf_auth`), preflight (`bench_preflight`: lockfile and R2 bucket), build the account portal SPA with the bench Turnstile sitekey, apply D1 migrations to `account-db-bench`, `wrangler deploy --config wrangler.bench.toml`, run `./run.sh rotation check --for=bench`, then push the worker secrets with `wrangler secret bulk`.

THE ROTATION CHECK ALWAYS COMPARES, AND ANYTHING BUT "IN SYNC" REFUSES THE PUSH (operator ruling 2026-10-13). The check reads the observability host's OTLP basicauth user names over plain OpenSSH, through `private/account/scripts/rotation/lib/observability-reader.ts`, with the three `OBS_READER_SSH_*` values this profile binds: the base64 of the machine's existing private key, the pinned known_hosts lines and `user@host[:port]`. No `rdc` login is involved. Exit 1 is drift; exit 2 is a credential that could not be read, which is reported as such with its cause and refuses the push as well, because an unread value is an uncompared one.

Resources: D1 `account-bench`, R2 `configs-bench`, worker `account-bench`, domain `bench.rediacc.cloud`. The cleanup of the Cloudflare token runs on every way out, a supplied `CF_MANAGEMENT_TOKEN` included, as in the bash.

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

  10. BENCH BINDS THE PRODUCTION KEY (operator rulings 2026-10-27 and 2026-10-29). The deploy-bench profile binds the unsuffixed session names and the ED25519 PUBLIC key (`ACCOUNT_ED25519_PUBLIC_KEY`, `ACCOUNT_X25519_*`, `ACCOUNT_SERVER_API_KEY`, `ACCOUNT_JWT_SECRET`) that the edge and stable account-secrets profiles bind (ED25519 fingerprint fb37f1ae16f8b7c0 through `renet_key_gate.key_fingerprint`), so a released renet verifies a bench licence. The ED25519 PRIVATE key is not in the account Worker's secret list: `signer-bench-eu` and `signer-bench-us` hold it (the deploy-signer profile) and `account-bench` signs through its LICENSE_SIGNER binding (agent/plans/PLAN-enterprise-isolation.md S4). The values are still read by name from the environment; only the profile binding changed, and `tests/test_ops_deploy_bench.py` pins it.

  11. A DEPLOY FROM A CLEAN BENCH REPEATS (finding 87f7acb9, `tests/test_deploy_bench_repeatability.py`). `_ensure_signers` creates the control databases (`control_db ensure --bench`) and deploys `signer-bench-eu` and `signer-bench-us` (each under the deploy-signer profile, which binds the private key) before the migrations, since Cloudflare refuses the account deploy with error 10143 while the `LICENSE_SIGNER` target Worker is missing. `_remove_retired_secrets` deletes a leftover `ACCOUNT_ED25519_PRIVATE_KEY` from `account-bench` (the listed names are read first, nothing else is deleted), because `requireSignerOnly` makes a Worker holding it answer 500. `smoke` then GETs `/account/api/v1/.well-known/server-info` and a last status other than 200 exits 1 naming it, so a Worker serving 500 is never a green deploy.

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
import threading
import time
import tomllib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.core import local_common, wrangler
from rediacc_ci.deploy import deploy_account, deploy_record, deploy_signer
from rediacc_ci.enterprise import control_db
from rediacc_ci.ops import bench_access, bench_preflight, cf_auth, push_backup_credentials
from rediacc_ci.proof import receipt
from rediacc_ci.well_known import BENCH_ORIGIN, PRODUCT_DOMAIN

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

BENCH_HOST = BENCH_ORIGIN.removeprefix("https://")

ACCOUNT_ID = cf_auth.DEFAULT_ACCOUNT_ID
WORKER_NAME = "account-bench"
CONFIG = "wrangler.bench.toml"
DB_NAME = "account-bench"
DOMAIN = BENCH_HOST
# Bench is test-only (operator ruling 2026-10-13): the portal is built with NO site key, so the
# widget never renders, and wrangler.bench.toml sets TURNSTILE_ENABLED=false for the API.
TURNSTILE_SITEKEY = ""
# The keyless bench portal is built OUTSIDE the production assets directory (`./dist` in every production and edge config), into the directory wrangler.bench.toml's [assets] names. On 2026-10-28 this tool rebuilt workers/account/dist/account for bench and the next production deploy uploaded that keyless portal to stable eu/us/asia, so no login could pass the captcha. `bench_assets_refusal` and `check:ci-portal-sitekey-guard` hold the separation.
BENCH_ASSETS_REL = ("bench", "dist")
PRODUCTION_ASSETS_REL = ("dist",)
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


# The sender the bench Worker mails from when AWS_SES_FROM is unset: the notify host of the product zone.
DEFAULT_SES_FROM = "noreply@notify.%s" % PRODUCT_DOMAIN


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


TEST_KEY_PREFIXES = ("sk_test_", "rk_test_")


def stripe_pair() -> tuple[str, str]:
    """The (secret key, webhook secret) bound as the bench Worker's Stripe pair, or ("", "") when the sandbox pair is absent.

    The deploy-bench profile aliases STRIPE_SANDBOX_SECRET_KEY / STRIPE_SANDBOX_WEBHOOK_SECRET to the Worker names. Bench never takes a live key: a key without a test prefix is refused by name, and no value is ever printed. One half without the other is refused too, since a key with no webhook secret (or the reverse) would boot a half-working billing path.
    """
    key = os.environ.get("STRIPE_SECRET_KEY") or ""
    hook = os.environ.get("STRIPE_WEBHOOK_SECRET") or ""
    if not key and not hook:
        print(
            "Stripe sandbox pair absent: bench keeps STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET blank"
        )
        return "", ""
    if not key or not hook:
        missing = "STRIPE_SANDBOX_WEBHOOK_SECRET" if key else "STRIPE_SANDBOX_SECRET_KEY"
        raise DeployError(
            "the Stripe sandbox pair is half-set (%s is empty): set both or neither" % missing
        )
    if not key.startswith(TEST_KEY_PREFIXES):
        raise DeployError(
            "STRIPE_SANDBOX_SECRET_KEY is not a Stripe test key (expected the sk_test_ or rk_test_ "
            "prefix): bench never takes a live key"
        )
    print(
        "Stripe sandbox pair bound as the bench Worker's STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET"
    )
    return key, hook


def secrets_payload() -> dict[str, str]:
    """The `wrangler secret bulk` body, keys in the order the bash emitted them. Raises DeployError on a missing or empty required value."""
    signing = {
        "ACCOUNT_ED25519_PUBLIC_KEY": os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY") or "",
        "ACCOUNT_X25519_PRIVATE_KEY": os.environ.get("ACCOUNT_X25519_PRIVATE_KEY") or "",
        "ACCOUNT_X25519_PUBLIC_KEY": os.environ.get("ACCOUNT_X25519_PUBLIC_KEY") or "",
        "ACCOUNT_SERVER_API_KEY": os.environ.get("ACCOUNT_SERVER_API_KEY") or "",
        "ACCOUNT_JWT_SECRET": os.environ.get("ACCOUNT_JWT_SECRET") or "",
        "FREE_LICENSE_HMAC_KEY": os.environ.get("FREE_LICENSE_HMAC_KEY") or "",
        # The Analytics Engine read token the portal's telemetry reads use (agent/plans/PLAN-d1-scaling.md W2).
        "ACCOUNT_AE_READ_TOKEN": os.environ.get("ACCOUNT_AE_READ_TOKEN") or "",
        # Layer 3 of the config store; the deploy-bench profile binds the bench-only vault entry under this name (agent/plans/PLAN-config-server-key.md K2).
        "ACCOUNT_CONFIG_SERVER_KEY": os.environ.get("ACCOUNT_CONFIG_SERVER_KEY") or "",
        # Seals customer backup store credentials; the deploy-bench profile binds the bench-only vault entry under this name.
        "ACCOUNT_BACKUP_STORE_KEK": os.environ.get("ACCOUNT_BACKUP_STORE_KEK") or "",
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
    stripe_key, stripe_hook = stripe_pair()
    otlp = os.environ.get("OBS_OTLP_CREDENTIALS") or ""
    require_nonempty("OBS_OTLP_CREDENTIALS", otlp)
    if not otlp_credentials_valid(otlp):
        raise DeployError(
            'OBS_OTLP_CREDENTIALS is not a JSON {"user","pass"} object for bench: '
            "re-mint it with ./run.sh rotation rotate otlp-bench"
        )
    return {
        "ACCOUNT_ED25519_PUBLIC_KEY": signing["ACCOUNT_ED25519_PUBLIC_KEY"],
        "ACCOUNT_X25519_PRIVATE_KEY": signing["ACCOUNT_X25519_PRIVATE_KEY"],
        "ACCOUNT_X25519_PUBLIC_KEY": signing["ACCOUNT_X25519_PUBLIC_KEY"],
        "ACCOUNT_SERVER_API_KEY": signing["ACCOUNT_SERVER_API_KEY"],
        "ACCOUNT_JWT_SECRET": signing["ACCOUNT_JWT_SECRET"],
        "FREE_LICENSE_HMAC_KEY": signing["FREE_LICENSE_HMAC_KEY"],
        "ACCOUNT_AE_READ_TOKEN": signing["ACCOUNT_AE_READ_TOKEN"],
        # The account whose Analytics Engine datasets the SQL API reads; every regional Worker gets it from the pusher.
        "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID,
        "ACCOUNT_CONFIG_SERVER_KEY": signing["ACCOUNT_CONFIG_SERVER_KEY"],
        "ACCOUNT_BACKUP_STORE_KEK": signing["ACCOUNT_BACKUP_STORE_KEK"],
        # The Stripe SANDBOX pair (test keys only, checked in stripe_pair) when the vault holds it, else empty strings so the worker boots without billing, as edge does.
        "STRIPE_SECRET_KEY": stripe_key,
        "STRIPE_WEBHOOK_SECRET": stripe_hook,
        "ROOT_EMAIL": os.environ.get("ROOT_EMAIL") or "",
        "AWS_SES_ACCESS_KEY_ID": os.environ.get("AWS_SES_ACCESS_KEY_ID") or "",
        "AWS_SES_SECRET_ACCESS_KEY": os.environ.get("AWS_SES_SECRET_ACCESS_KEY") or "",
        "AWS_SES_REGION": os.environ.get("AWS_SES_REGION") or "eu-central-1",
        "AWS_SES_FROM": os.environ.get("AWS_SES_FROM") or DEFAULT_SES_FROM,
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
        "SELLER_REGISTER_NAME": os.environ.get("SELLER_REGISTER_NAME") or "",
        "SELLER_ADDRESS_LINE1": os.environ.get("SELLER_ADDRESS_LINE1") or "",
        "SELLER_ADDRESS_LINE2": os.environ.get("SELLER_ADDRESS_LINE2") or "",
        "SELLER_CITY": os.environ.get("SELLER_CITY") or "",
        "SELLER_POSTAL_CODE": os.environ.get("SELLER_POSTAL_CODE") or "",
        "SELLER_COUNTRY": os.environ.get("SELLER_COUNTRY") or "",
        "SELLER_EMAIL": os.environ.get("SELLER_EMAIL") or "",
    }


def _feed_stdin(popen: subprocess.Popen, stdin: str | None) -> threading.Thread | None:
    """Write `stdin` to the child on a thread, so the output is read meanwhile (a child that fills its stdout before reading its input cannot deadlock) and a child that exits without reading it (BrokenPipeError) leaves its own output and exit status to say why."""
    if stdin is None or popen.stdin is None:
        return None
    pipe = popen.stdin

    def feed() -> None:
        try:
            pipe.write(stdin)
            pipe.close()
        except (BrokenPipeError, OSError):
            pass

    thread = threading.Thread(target=feed, daemon=True)
    thread.start()
    return thread


def _run(
    argv: list[str],
    cwd,
    what: str,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    capture: bool = False,
) -> str:
    """Run one step. With `capture` the combined output is returned and echoed line by line as it arrives, else the return is empty."""
    if capture:
        lines: list[str] = []
        with subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE if stdin is not None else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as popen:
            feeder = _feed_stdin(popen, stdin)
            for line in popen.stdout or ():
                sys.stdout.write(line)
                sys.stdout.flush()
                lines.append(line)
            if feeder is not None:
                feeder.join()
        if popen.returncode != 0:
            raise DeployError("%s failed (exit %d)" % (what, popen.returncode))
        return "".join(lines)
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
    return (proc.stdout or "") if capture else ""


# The surfaces a bench deploy proves live, and where the recorder reads the deployed version.
BENCH_SURFACES = ("account", "account-worker")
VERSION_RECORD = (".ci", "cache", "live-deploys", "bench.json")
VERSION_PATTERN = re.compile(r"Current Version ID:\s*([0-9a-fA-F][0-9a-fA-F-]{7,})")


def record_version(root, output: str, live_version: str) -> dict:
    """Write `.ci/cache/live-deploys/bench.json` from `proof.receipt.identity` plus the version bench serves, and return it. DeployError, with nothing written, when the deploy `output` carries no `Current Version ID:` or `live_version` is empty.

    `version_id` is `live_version`, the 100% version read after the secrets push, because `wrangler secret bulk` creates a newer version than the one `wrangler deploy` printed (measured 2026-10-28: deploy printed 0b4e20ac, bench served bb3e1ba3); `deployed_version_id` keeps the printed one. `live_version` is required: a blank one is an error, never a silent fallback to the printed id."""
    if not (live_version or "").strip():
        raise DeployError("the live bench version is unknown, so no version is recorded")
    match = VERSION_PATTERN.search(output)
    if not match:
        raise DeployError(
            "the wrangler deploy output carries no 'Current Version ID:' line, so the deployed "
            "version is not recorded in %s (the deploy itself is done and not rolled back)"
            % "/".join(VERSION_RECORD)
        )
    record = {
        "version_id": live_version,
        "deployed_version_id": match.group(1),
        **receipt.identity(root, BENCH_SURFACES),
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    receipt.write_atomic(root.joinpath(*VERSION_RECORD), json.dumps(record, indent=2) + "\n")
    return record


# A D1 bookmark as `wrangler d1 time-travel info` prints it: three 8-hex groups and a long hex tail.
BOOKMARK_PATTERN = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{16,}\b")


def restore_command(bookmark: str) -> str:
    return (
        "cd %s && npx --no-install wrangler d1 time-travel restore %s --bookmark=%s --config %s"
        % (
            "workers/account",
            DB_NAME,
            bookmark,
            CONFIG,
        )
    )


def capture_bookmark(worker_dir) -> str | None:
    """Print the D1 bookmark taken BEFORE the migrations, with the exact restore command: a Worker rollback does not undo a migration, so the bookmark is the rollback handle. A failed capture is reported loudly and returns None; the deploy goes on (the migrations are not blocked on a read-only query, and the bash had no bookmark at all)."""
    try:
        proc = subprocess.run(
            [*wrangler.ARGV, "d1", "time-travel", "info", DB_NAME, "--config", CONFIG],
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
    """`wrangler d1 execute account-bench --remote --json --command SQL` from the worker dir, authenticated with the Global API Key pair, and the result rows. The stdout is never printed: it holds live links."""
    key, mail = os.environ.get("CF_GLOBAL_API_KEY"), os.environ.get("CF_EMAIL")
    if not (key and mail):
        raise SeedError("CF_GLOBAL_API_KEY and CF_EMAIL are required to read the captured email")
    env = dict(os.environ)
    for name in ("CLOUDFLARE_API_TOKEN", "CF_API_KEY"):
        env.pop(name, None)
    env["CLOUDFLARE_API_KEY"], env["CLOUDFLARE_EMAIL"] = key, mail
    env["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT_ID
    argv = [*wrangler.ARGV, "d1", "execute", DB_NAME, "--remote", "--config", CONFIG]
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


def portal_out_dir(worker_dir) -> pathlib.Path:
    """Where the keyless bench portal is built: `<worker>/bench/dist/account`, served at /account/ by the bench config's assets."""
    return worker_dir.joinpath(*BENCH_ASSETS_REL, "account")


def bench_assets_refusal(worker_dir) -> str | None:
    """None when wrangler.bench.toml's [assets] directory is the bench build root and lies outside the production assets directory, else the refusal. Checked before the build, so a config edit can never steer the keyless build back into the directory a production deploy uploads."""
    try:
        with open(worker_dir / CONFIG, "rb") as fh:
            directory = (tomllib.load(fh).get("assets") or {}).get("directory", "")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return "%s cannot be read for its [assets] directory: %s" % (CONFIG, exc)
    assets = (worker_dir / directory).resolve() if directory else None
    want = worker_dir.joinpath(*BENCH_ASSETS_REL).resolve()
    production = worker_dir.joinpath(*PRODUCTION_ASSETS_REL).resolve()
    if assets != want:
        return (
            "%s [assets] directory is %r, not ./%s: the bench portal is built there and nowhere else"
            % (
                CONFIG,
                directory,
                "/".join(BENCH_ASSETS_REL),
            )
        )
    if want == production or production in want.parents or want in production.parents:
        return "the bench portal build root %s overlaps the production assets %s" % (
            want,
            production,
        )
    return None


# The account Worker binds LICENSE_SIGNER to `signer-bench-<region>` (workers/account/wrangler.bench.toml), and Cloudflare refuses the account deploy with error 10143 while that Worker does not exist. The control databases the signers bind are created first. A signer holds the private key, which only the deploy-signer profile binds, so each signer deploys in its own child under that profile.
SIGNER_TARGETS = tuple("bench-%s" % r for r in deploy_signer.BENCH_REGIONS)
# Secrets the account Worker must never hold: `requireSignerOnly` (private/account/src/entry/cloudflare.ts) refuses to serve, HTTP 500 "Server misconfiguration", while the retired private key is present.
RETIRED_SECRETS = (deploy_signer.PRIVATE_KEY,)
SMOKE_PATH = "/account/api/v1/.well-known/server-info"
SMOKE_ATTEMPTS = 5
SMOKE_WAIT_S = 3.0


def _child_env(root) -> dict[str, str]:
    env = dict(os.environ)
    ci = str(root / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _ensure_signers(root, run=None) -> None:
    """Create and migrate the bench control databases, then deploy both bench signers, before the account deploy."""
    run = run or _run
    env = _child_env(root)
    log.step("Ensuring the bench control databases")
    run(
        [sys.executable, "-m", control_db.SELF, "ensure", "--bench"],
        root,
        "control_db ensure --bench",
        env=env,
    )
    for target in SIGNER_TARGETS:
        log.step("Deploying the signer Worker signer-%s (LICENSE_SIGNER binding)" % target)
        run(
            [
                sys.executable,
                "-m",
                "rediacc_ci.core.bws_env",
                "exec",
                "--profile",
                deploy_signer.PROFILE,
                "--",
                sys.executable,
                "-m",
                deploy_signer.SELF,
                "--target",
                target,
            ],
            root,
            "deploy_signer --target %s" % target,
            env=env,
        )


def _remove_retired_secrets(worker_dir, run=None) -> list[str]:
    """Delete each retired secret that `account-bench` still holds (names listed first; nothing else is touched). Returns the names removed."""
    run = run or _run
    listing = run(
        [*wrangler.ARGV, "secret", "list", "--format", "json", "--name", WORKER_NAME],
        worker_dir,
        "wrangler secret list",
        capture=True,
    )
    try:
        rows = control_db.parse_json(listing)
    except control_db.ControlDbError as exc:
        raise DeployError("wrangler secret list printed no JSON list: %s" % exc) from None
    if not isinstance(rows, list):
        raise DeployError("wrangler secret list did not print a list")
    held = {str(r.get("name")) for r in rows if isinstance(r, dict)}
    removed = [name for name in RETIRED_SECRETS if name in held]
    for name in removed:
        run(
            [*wrangler.ARGV, "secret", "delete", name, "--name", WORKER_NAME],
            worker_dir,
            "wrangler secret delete %s" % name,
            stdin="y\n",
        )
        log.info("Removed the retired secret %s from %s" % (name, WORKER_NAME))
    return removed


def _run_curl(url: str) -> subprocess.CompletedProcess[str]:
    """One curl GET of `url` printing only the status code."""
    return subprocess.run(
        [
            "curl",
            "-sS",
            "-o",
            os.devnull,
            "--connect-timeout",
            str(CURL_CONNECT_TIMEOUT_S),
            "--max-time",
            str(CURL_MAX_TIME_S),
            "-w",
            "%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _http_status(url: str) -> int:
    """GET `url` with curl; 0 means no HTTP answer, a missing curl included."""
    try:
        proc = _run_curl(url)
    except OSError:
        return 0
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return 0


def smoke(
    fetch: Callable[[str], int] | None = None, sleep: Callable[[float], None] = time.sleep
) -> None:
    """The deployed Worker must serve: GET server-info answers 200, retried while the new version propagates. A last status other than 200 is a DeployError naming it."""
    fetch = fetch or _http_status
    url = "https://%s%s" % (DOMAIN, SMOKE_PATH)
    status = 0
    for attempt in range(SMOKE_ATTEMPTS):
        status = fetch(url)
        if status == 200:
            log.info("bench smoke: %s answered 200" % url)
            return
        if attempt + 1 < SMOKE_ATTEMPTS:
            sleep(SMOKE_WAIT_S)
    raise DeployError(
        "bench smoke failed: GET %s answered %d%s"
        % (url, status, _blocked_hint(status) if status == 403 else "")
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

    log.step("Preflight: every queue bound in %s exists (missing ones are created)" % CONFIG)
    try:
        for name in deploy_account.check_queues(worker_dir / CONFIG, os.environ):
            log.info("Created queue %s" % name)
    except deploy_account.QueuePreflightError as exc:
        raise DeployError(str(exc)) from None

    log.step("Building account portal SPA (captcha disabled on bench: no Turnstile sitekey)")
    refusal = bench_assets_refusal(worker_dir)
    if refusal:
        raise DeployError(refusal)
    out_dir = portal_out_dir(worker_dir)
    web_dir = root / "private" / "account" / "web"
    if not (web_dir / "node_modules").is_dir():
        _run(["npm", "install"], web_dir, "npm install")
    # The portal imports @rediacc/shared as a file: dependency, so vite bundles whatever packages/shared/dist holds. Without this build a deploy shipped a stale dist: on 2026-11-11 the bench consent page rendered with an empty notice and no Terms link, because dist predated the regenerated consent notices.
    if not local_common.ensure_packages_built():
        raise DeployError("building packages/shared failed; the portal would bundle a stale dist")
    build_env = dict(os.environ)
    build_env["VITE_TURNSTILE_SITE_KEY"] = TURNSTILE_SITEKEY
    build_env["VITE_CI_MODE"] = "false"
    _run(
        ["npx", "--no-install", "vite", "build", "--outDir", str(out_dir)],
        web_dir,
        "vite build",
        env=build_env,
    )
    log.info("Account portal built → %s" % out_dir)

    if not (worker_dir / "node_modules").is_dir():
        _run(["npm", "install"], worker_dir, "npm install")
    _ensure_signers(root)
    capture_bookmark(worker_dir)
    log.step("Applying D1 migrations to %s (remote)" % DB_NAME)
    _run(
        [*wrangler.ARGV, "d1", "migrations", "apply", DB_NAME, "--remote", "--config", CONFIG],
        worker_dir,
        "wrangler d1 migrations apply",
    )
    log.info("Migrations applied")

    log.step("Deploying %s → https://%s" % (WORKER_NAME, DOMAIN))
    deploy_output = _run(
        [*wrangler.ARGV, "deploy", "--config", CONFIG], worker_dir, "wrangler deploy", capture=True
    )
    log.info("Worker deployed")

    _rotation_check(root)
    _remove_retired_secrets(worker_dir)
    _run(
        [*wrangler.ARGV, "secret", "bulk", "--name", WORKER_NAME],
        worker_dir,
        "wrangler secret bulk",
        stdin=body,
    )
    log.info("Worker secrets pushed")
    smoke()
    _seed_and_report()
    # After the whole deploy, so a missing id fails a finished deploy rather than leaving secrets unpushed.
    exists, live_version = deploy_record.worker_version(worker_dir, CONFIG, WORKER_NAME)
    if not exists or not live_version:
        raise DeployError(
            "wrangler reports no live version of %s after the deploy, so none is recorded"
            % WORKER_NAME
        )
    record_version(root, deploy_output, live_version)
    log.info("Bench version recorded in %s" % "/".join(VERSION_RECORD))

    print()
    log.info("bench is live: https://%s" % DOMAIN)
    print("  D1:     %s (ac45c2de-053b-404c-bc47-9ad9cbd2bb15)" % DB_NAME)
    print("  R2:     configs-bench")
    print("  Worker: %s" % WORKER_NAME)
    print()
    print("Test it:")
    print("  npm run login:bench")
    print("  ./rdc.sh --config eu-bench repo create --name my-app -m my-server --size 2G")


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
