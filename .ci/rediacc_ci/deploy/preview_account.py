"""Create a customer's account on a PR preview and print a one-time sign-in link.

agent/plans/PLAN-preview-signer.md box P1 (D3, answer 3). Sign-up on a preview answers 403 `PREVIEW_SIGNUP_CLOSED`, so the operator creates the account here:

    PREVIEW_NAME_KEY=... PYTHONPATH=.ci python3 -m rediacc_ci.deploy.preview_account --pr <n> --email <addr>

One batch writes the user (no password), its organisation, the owner membership, the preview subscription `<name>-<8 hex>` and its shard row into the preview D1 `account-pr-<n>`, plus a magic-link row holding only the SHA-256 of the token. The raw token appears once, in the printed link `https://<name>.rediacc.workers.dev/account/magic-link/verify?token=<token>`, valid 15 minutes (MAGIC_LINK_TTL_MS). Nothing from a real account is read.

The subscription fields mirror `previewSubscriptionFields` (private/account/src/services/preview-subscription.service.ts), which tests/integration/preview-subscription.test.ts pins for the account side: PROFESSIONAL on a `trial` row, 7 days, the preview plan's limits. `features` stays NULL, which the Worker resolves from the plan (subscription.service.ts:2116).
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import os
import re
import secrets
import string
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from rediacc_ci import log, paths
from rediacc_ci.core import wrangler
from rediacc_ci.deploy import preview_name
from rediacc_ci.testrun import seed_smoke

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
SUBSCRIPTION_DAYS = 7
LINK_TTL_MINUTES = 15
PLAN = "PROFESSIONAL"
MAX_ACTIVATIONS = 1
MAX_REPOSITORY_SIZE_GB = 100
MAX_ISSUANCES_PER_MONTH = 2000
GRACE_DAYS = 3

SQL = string.Template(
    """
INSERT INTO users (id, email, email_hash, preferred_language, company_name, role, customer_id, totp_enabled, created_at, updated_at)
VALUES ('${user_id}', '${email}', '${email_hash}', 'en', '', 'customer', '${user_id}', 0, '${now}', '${now}');

INSERT INTO subscriptions (id, customer_id, customer_email, type, status, max_activations, plan_code, max_repository_size_gb, max_repo_license_issuances_per_month, repo_license_issuances_usage_adjustment, expires_at, last_check_in, grace_period_ends, created_at, updated_at)
VALUES ('${sub_id}', '${user_id}', '${email}', 'trial', 'active', ${max_activations}, '${plan}', ${max_size}, ${max_issuances}, 0, '${sub_ends}', '${now}', '${grace_ends}', '${now}', '${now}');

INSERT INTO subscription_shards (subscription_id, shard) VALUES ('${sub_id}', '0');

INSERT INTO organizations (id, name, owner_user_id, customer_id, created_at, updated_at)
VALUES ('${org_id}', '${email}', '${user_id}', '${user_id}', '${now}', '${now}');

INSERT INTO org_memberships (id, org_id, user_id, role, joined_at)
VALUES ('${membership_id}', '${org_id}', '${user_id}', 'owner', '${now}');

INSERT INTO magic_links (token_hash, user_id, expires_at, created_at)
VALUES ('${token_hash}', '${user_id}', '${link_ends}', '${now}');
"""
)


def _iso(moment: datetime.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def new_token() -> tuple[str, str]:
    """A raw magic-link token (32 random bytes, base64url, as `createSecureToken`) and its SHA-256 hex."""
    raw = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def build_sql(name: str, email: str, now: datetime.datetime, token_hash: str) -> tuple[str, str]:
    """The batch and the new subscription id. Pure apart from the random ids."""
    if not preview_name.is_preview_worker(name) or name.endswith("-signer"):
        raise ValueError(f"not a preview Worker name: {name!r}")
    email = email.strip().lower()
    if not EMAIL_RE.fullmatch(email) or "'" in email:
        raise ValueError(f"not an acceptable email address: {email!r}")
    sub_id = f"{name}-{secrets.token_hex(4)}"
    values = {
        "user_id": str(uuid.uuid4()),
        "org_id": str(uuid.uuid4()),
        "membership_id": str(uuid.uuid4()),
        "sub_id": sub_id,
        "email": email,
        "email_hash": hashlib.sha256(email.encode()).hexdigest(),
        "now": _iso(now),
        "sub_ends": _iso(now + datetime.timedelta(days=SUBSCRIPTION_DAYS)),
        "grace_ends": _iso(now + datetime.timedelta(days=GRACE_DAYS)),
        "link_ends": _iso(now + datetime.timedelta(minutes=LINK_TTL_MINUTES)),
        "token_hash": token_hash,
        "plan": PLAN,
        "max_activations": MAX_ACTIVATIONS,
        "max_size": MAX_REPOSITORY_SIZE_GB,
        "max_issuances": MAX_ISSUANCES_PER_MONTH,
    }
    return SQL.substitute(values), sub_id


def sign_in_link(name: str, raw_token: str) -> str:
    return f"https://{name}.rediacc.workers.dev/account/magic-link/verify?token={raw_token}"


Runner = Callable[..., subprocess.CompletedProcess[str]]


def run(
    pr: int,
    email: str,
    key: bytes,
    *,
    now: datetime.datetime | None = None,
    runner: Runner = subprocess.run,
    worker_dir: Path | None = None,
) -> int:
    name = preview_name.preview_name(pr, key)
    moment = now or datetime.datetime.now(datetime.UTC)
    raw, token_hash = new_token()
    try:
        sql, sub_id = build_sql(name, email, moment, token_hash)
    except ValueError as exc:
        log.error(str(exc))
        return 1
    db_name = f"account-pr-{pr}"
    cwd = worker_dir or paths.repo_root() / "workers" / "www"
    try:
        listed = runner(
            [*wrangler.ARGV, "d1", "list", "--json"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        log.error(f"npx: {exc.strerror or exc}")
        return 1
    if listed.returncode != 0:
        log.error(
            f"wrangler d1 list failed (rc {listed.returncode}): {listed.stderr.strip()[-500:]}"
        )
        return 1
    db_uuid = seed_smoke.find_db_uuid(listed.stdout, db_name)
    if not db_uuid:
        log.error(f"Database {db_name} not found")
        return 1
    with tempfile.TemporaryDirectory(prefix="wrangler-preview-account-") as tmp:
        config = Path(tmp) / "wrangler.toml"
        config.write_text(seed_smoke.wrangler_config(name, db_name, db_uuid), encoding="utf-8")
        executed = runner(
            [
                *wrangler.ARGV,
                "d1",
                "execute",
                db_name,
                "--remote",
                "--config",
                str(config),
                "--command",
                sql,
            ],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
    if executed.returncode != 0:
        log.error(
            f"wrangler d1 execute failed (rc {executed.returncode}): {executed.stderr.strip()[-500:]}"
        )
        return executed.returncode
    print(f"Preview {name}: account {email.strip().lower()}, subscription {sub_id}")
    print(f"Sign-in link (single use, valid {LINK_TTL_MINUTES} minutes):")
    print(sign_in_link(name, raw))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="preview_account", description=__doc__.splitlines()[0])
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if args.pr < 1:
        log.error(f"--pr must be positive, got {args.pr}")
        return 1
    try:
        key = preview_name.load_key(dict(os.environ))
    except preview_name.PreviewNameError as exc:
        log.error(str(exc))
        return 1
    return run(args.pr, args.email, key)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
