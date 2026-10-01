"""Port of `scripts/ops/deploy-bench.sh` (293 lines): deploy the account worker to bench.rediacc.com.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench

Bench is the internal "real Cloudflare D1" environment, deliberately NOT wired into CI or CD: a deploy is an operator running this by hand. The steps are the bash's, in order: re-exec under the `deploy-bench` Bitwarden profile (`rediacc_ci.core.bws_env exec`), resolve Cloudflare auth (`cf_auth`), preflight (`bench_preflight`: lockfile and R2 bucket), build the account portal SPA with the bench Turnstile sitekey, apply D1 migrations to `account-db-bench`, `wrangler deploy --config wrangler.bench.toml`, run `./run.sh rotation check --for=bench`, then push the worker secrets with `wrangler secret bulk`.

Resources: D1 `account-db-bench`, R2 `rediacc-configs-bench`, worker `rediacc-account-bench`, domain `bench.rediacc.com`. The cleanup of the Cloudflare token runs on every way out, a supplied `CF_MANAGEMENT_TOKEN` included, as in the bash.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_deploy_bench.py` that fails on the bash behaviour).

  1. ARGUMENTS ARE REJECTED. The script took no arguments and ignored every one it was given, so `deploy-bench.sh --dry-run` (the natural thing to type before a deploy to a shared environment) performed a real deploy. An argument now exits 2 before anything runs; `-h`/`--help` prints usage.
  2. THE TOKEN-PROPAGATION WAIT IS TAKEN ONLY FOR A TOKEN THIS RUN MINTED (`cf_auth.await_propagation`, 8 s). The unconditional `sleep 5` exists because a freshly created management token can race Cloudflare's propagation; an operator-supplied token cannot.
  3. NO `jq`. Every JSON read and the secrets payload are built in-process, so the `require_cmd jq` precondition is gone.
  4. THE SIX REQUIRED SIGNING KEYS REPORT THROUGH THE LOGGER with the same wording, instead of bash's `script: line N: NAME: message` text, which named a line number that no longer meant anything after any edit.
  5. THE SECRETS ARE VALIDATED BEFORE THE FIRST REMOTE WRITE. The six signing keys, the non-empty checks and the OTLP probe ran after the migrations and the deploy, so a missing value left bench on new code with the old secrets, the 2026-09-24 failure shape (state changed, then refused). Only the rotation drift check still runs after the deploy, as it did.
  6. A FAILED STEP NAMES ITSELF. Under `set -e` a failing `npm install`, `vite build`, migration or deploy ended the script silently with that command's status; each exits 1 with `<step> failed (exit N)`.

THE SECRET VALUES ARE READ BY NAME FROM THE ENVIRONMENT, as the bash read them, and are never logged; the `OBS_OTLP_CREDENTIALS` validity probe reports only that the value is not a JSON {user, pass} object, never the value.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.ops import bench_preflight, cf_auth
from rediacc_ci.well_known import BENCH_ORIGIN

BENCH_HOST = BENCH_ORIGIN.removeprefix("https://")

ACCOUNT_ID = cf_auth.DEFAULT_ACCOUNT_ID
WORKER_NAME = "rediacc-account-bench"
CONFIG = "wrangler.bench.toml"
DB_NAME = "account-db-bench"
DOMAIN = BENCH_HOST
TURNSTILE_SITEKEY = "0x4AAAAAAC46Rczgin0T1o04"
PROFILE = "deploy-bench"
MISSING = "%s missing from the deploy-bench profile"
HELP = (
    """Deploy the account worker to """
    + BENCH_HOST
    + """.

Usage:
  deploy_bench          (no arguments)

Credentials come from the deploy-bench Bitwarden profile; see
.ci/config/secret-supply.json. Cloudflare auth: CF_MANAGEMENT_TOKEN, or
CF_GLOBAL_API_KEY + CF_EMAIL, or an interactive prompt.
"""
)


class DeployError(Exception):
    """A step failed; the message is printed and the run exits 1."""


def _first(*values: str | None) -> str:
    """The first non-empty value, as bash `${A:-${B:-}}` resolves it."""
    for value in values:
        if value:
            return value
    return ""


def _backup_values() -> tuple[str, str, str]:
    endpoint = _first(
        os.environ.get("ACCOUNT_BACKUP_S3_ENDPOINT"), os.environ.get("CLOUDFLARE_R2_ENDPOINT")
    )
    key_id = _first(
        os.environ.get("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"),
        os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID"),
    )
    secret = _first(
        os.environ.get("ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"),
        os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
    )
    return endpoint, key_id, secret


def require_nonempty(name: str, value: str) -> None:
    """A secret that reached the push empty would be pushed empty and validated happily by the worker."""
    if not value:
        raise DeployError(
            "%s is EMPTY for bench — check its entry in Bitwarden (deploy-bench profile, "
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
    }
    for name, value in signing.items():
        if not value:
            raise DeployError(MISSING % name)
    endpoint, backup_key, backup_secret = _backup_values()
    require_nonempty("ROOT_EMAIL", os.environ.get("ROOT_EMAIL") or "")
    require_nonempty("AWS_SES_ACCESS_KEY_ID", os.environ.get("AWS_SES_ACCESS_KEY_ID") or "")
    require_nonempty("AWS_SES_SECRET_ACCESS_KEY", os.environ.get("AWS_SES_SECRET_ACCESS_KEY") or "")
    require_nonempty(
        "CLOUDFLARE_TURNSTILE_SECRET_KEY", os.environ.get("CLOUDFLARE_TURNSTILE_SECRET_KEY") or ""
    )
    require_nonempty("ACCOUNT_BACKUP_S3_ENDPOINT", endpoint)
    require_nonempty("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", backup_key)
    require_nonempty("ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY", backup_secret)
    otlp = os.environ.get("OBS_OTLP_CREDENTIALS") or ""
    require_nonempty("OBS_OTLP_CREDENTIALS", otlp)
    if not otlp_credentials_valid(otlp):
        raise DeployError(
            'OBS_OTLP_CREDENTIALS is not a JSON {"user","pass"} object for bench — '
            "re-mint it with ./run.sh rotation rotate otlp-bench"
        )
    return {
        "ACCOUNT_ED25519_PRIVATE_KEY": signing["ACCOUNT_ED25519_PRIVATE_KEY"],
        "ACCOUNT_ED25519_PUBLIC_KEY": signing["ACCOUNT_ED25519_PUBLIC_KEY"],
        "ACCOUNT_X25519_PRIVATE_KEY": signing["ACCOUNT_X25519_PRIVATE_KEY"],
        "ACCOUNT_X25519_PUBLIC_KEY": signing["ACCOUNT_X25519_PUBLIC_KEY"],
        "ACCOUNT_SERVER_API_KEY": signing["ACCOUNT_SERVER_API_KEY"],
        "ACCOUNT_JWT_SECRET": signing["ACCOUNT_JWT_SECRET"],
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
        "ACCOUNT_BACKUP_S3_BUCKET": os.environ.get("ACCOUNT_BACKUP_S3_BUCKET")
        or "rediacc-backups-bench",
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


def _rotation_check(root) -> None:
    log.step("Rotation preflight: ./run.sh rotation check --for=bench")
    rc = subprocess.run(
        [str(root / "run.sh"), "rotation", "check", "--for=bench"], check=False
    ).returncode
    if rc == 0:
        return
    # A verdict is different from a check that never reached one: reporting drift for a missing credential sends the operator to rotate a key that is fine.
    if not _first(
        os.environ.get("AWS_IAM_ADMIN_ACCESS_KEY_ID"), os.environ.get("AWS_SES_ADMIN_KEY_ID")
    ):
        raise DeployError(
            "rotation check could NOT RUN: no AWS IAM admin credentials in the\n"
            "environment even after the deploy-bench profile. This is NOT drift --\n"
            "nothing was compared. Check AWS_IAM_ADMIN_ACCESS_KEY_ID in Bitwarden (ci-shared)."
        )
    raise DeployError(
        "rotation drift detected — refusing to push stale secrets to bench\n"
        "fix: run `./run.sh rotation rotate <slug>` for the credentials that drifted"
    )


def _deploy(auth: cf_auth.Auth, root) -> None:
    worker_dir = root / "workers" / "account"
    if not (worker_dir / CONFIG).is_file():
        raise DeployError("%s missing" % (worker_dir / CONFIG))

    # Validate the secrets before the first remote write: a missing key found after the migrations and the deploy leaves bench on new code with old secrets.
    body = json.dumps(secrets_payload())

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

    log.step("Building account portal SPA (Turnstile sitekey: %s)" % TURNSTILE_SITEKEY)
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
    if argv:
        log.error("Unknown argument: %s" % argv[0])
        log.error("deploy_bench takes no arguments; run with --help for usage.")
        return 2
    for cmd in ("curl", "npx"):
        if shutil.which(cmd) is None:
            log.error("Required command '%s' is not available" % cmd)
            return 1
    rebound = _reexec_under_profile(argv)
    if rebound is not None:
        return rebound
    root = paths.repo_root()
    try:
        auth = cf_auth.resolve(ACCOUNT_ID)
    except cf_auth.CfAuthError as exc:
        log.error(str(exc))
        return 1
    try:
        _deploy(auth, root)
    except DeployError as exc:
        for line in str(exc).splitlines():
            log.error(line)
        return 1
    finally:
        cf_auth.self_destruct(auth)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
