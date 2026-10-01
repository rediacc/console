"""Port of `.ci/scripts/test/seed-smoke-test.sh`: seed one subscribed user and an API token into a PR preview's D1 database.

The SQL, the row ids and the token shape (`rdt_smoke_<pr>_<first 32 hex of sha256(ACCOUNT_JWT_SECRET)>`) are the twin's, so a differential can compare the `wrangler d1 execute` argv byte for byte once the timestamp is masked.

Deliberate differences from the twin (Rule T), each with a test that fails on the bash behaviour:

  1. `ACCOUNT_JWT_SECRET` falls back to the literal `default` in the twin (`${ACCOUNT_JWT_SECRET:-default}`) although its own header lists it as required. An unset secret then seeds a token any reader of this file can compute, into a remote database, with `license:activate`. It is refused, exit 1.
  2. `PR_NUMBER` is interpolated into SQL and into a wrangler config as text and was never validated. Anything but digits is refused, exit 1, before a command runs.
  3. The wrangler config was written to the fixed `/tmp/wrangler-seed.toml` and removed only on success, so a failed seed left it behind and two runs on one host shared it. It is a private temporary directory removed on every path.
  4. Without `$GITHUB_OUTPUT` the twin failed AFTER seeding with a redirection error. The `SMOKE_TEST_TOKEN=` line goes to stdout instead, so a local run reports the token it just seeded.
  5. The token is announced with `::add-mask::` first. It is a bearer token with a license scope and a step output is not masked on its own.
"""

import datetime
import hashlib
import json
import os
import pathlib
import re
import string
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths

PR_RE = re.compile(r"^[0-9]+$")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def derive(pr: str, jwt_secret: str, now: str) -> dict[str, str]:
    """Every id, hash and the token for one PR. Pure, so the shape is unit-testable."""
    email = f"smoketest-pr{pr}@rediacc.io"
    token = f"rdt_smoke_{pr}_{sha256_hex(jwt_secret)[:32]}"
    return {
        "db_name": f"account-db-pr-{pr}",
        "now": now,
        "user_id": f"smoke-user-pr-{pr}",
        "org_id": f"smoke-org-pr-{pr}",
        "sub_id": f"smoke-sub-pr-{pr}",
        "team_id": f"smoke-team-pr-{pr}",
        "token_id": f"smoke-tok-pr-{pr}",
        "membership_id": f"smoke-mem-pr-{pr}",
        "team_membership_id": f"smoke-tmem-pr-{pr}",
        "email": email,
        "customer_id": f"cus_smoke_pr_{pr}",
        "token": token,
        "token_hash": sha256_hex(token),
        "email_hash": sha256_hex(email.lower()),
    }


SEED_SQL = string.Template(
    """
INSERT OR IGNORE INTO users (id, email, email_hash, preferred_language, company_name, role, created_at, updated_at, totp_enabled)
VALUES ('${user_id}', '${email}', '${email_hash}', 'en', 'Smoke Test', 'customer', '${now}', '${now}', 0);

INSERT OR IGNORE INTO organizations (id, name, owner_user_id, customer_id, data_region, created_at, updated_at)
VALUES ('${org_id}', 'Smoke Test Org', '${user_id}', '${customer_id}', 'eu', '${now}', '${now}');

INSERT OR IGNORE INTO org_memberships (id, org_id, user_id, role, joined_at)
VALUES ('${membership_id}', '${org_id}', '${user_id}', 'owner', '${now}');

INSERT OR IGNORE INTO teams (id, org_id, name, slug, is_default, created_at, updated_at)
VALUES ('${team_id}', '${org_id}', 'Default', 'default', 1, '${now}', '${now}');

INSERT OR IGNORE INTO team_memberships (id, team_id, user_id, role, joined_at)
VALUES ('${team_membership_id}', '${team_id}', '${user_id}', 'member', '${now}');

INSERT OR IGNORE INTO subscriptions (id, customer_id, customer_email, type, status, max_activations, plan_code, created_at, updated_at, org_id, repo_license_issuances_usage_adjustment, metadata)
VALUES ('${sub_id}', '${customer_id}', '${email}', 'subscription', 'active', 2, 'COMMUNITY', '${now}', '${now}', '${org_id}', 0, '{"trialUsedAt":"${now}"}');

INSERT OR IGNORE INTO api_tokens (id, name, token_hash, subscription_id, team_id, scopes, created_at, created_by_user_id)
VALUES ('${token_id}', 'Smoke Test Token', '${token_hash}', '${sub_id}', '${team_id}', '["license:activate","license:read"]', '${now}', '${user_id}');
"""
)


def seed_sql(d: dict[str, str]) -> str:
    """The single-batch seed, text-identical to the twin's `--command` argument."""
    return SEED_SQL.substitute(d)


def wrangler_config(pr: str, db_name: str, db_uuid: str) -> str:
    return f"""name = "pr-{pr}"
main = "src/index.ts"
compatibility_date = "2026-01-20"
[[d1_databases]]
binding = "DB"
database_name = "{db_name}"
database_id = "{db_uuid}"
"""


def find_db_uuid(listing: str, db_name: str) -> str | None:
    """The uuid of `db_name` in `wrangler d1 list --json` output, or None."""
    try:
        data = json.loads(listing)
    except ValueError:
        return None
    for db in data if isinstance(data, list) else []:
        if isinstance(db, dict) and db.get("name") == db_name:
            return db.get("uuid")
    return None


def main(argv: list[str]) -> int:
    if argv:
        print(f"seed-smoke-test.sh takes no arguments, got: {' '.join(argv)}", file=sys.stderr)
        return 2
    pr = os.environ.get("PR_NUMBER", "")
    if not pr:
        print("seed-smoke-test.sh: PR_NUMBER is required", file=sys.stderr)
        return 1
    if not PR_RE.match(pr):
        log.error(f"PR_NUMBER must be digits, got '{pr}'")
        return 1
    jwt_secret = os.environ.get("ACCOUNT_JWT_SECRET", "")
    if not jwt_secret:
        log.error(
            "ACCOUNT_JWT_SECRET is required: an unset secret would seed a token anyone can derive"
        )
        return 1

    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    d = derive(pr, jwt_secret, now)
    worker_dir = paths.repo_root() / "workers" / "www"

    print(f"Seeding smoke test data into {d['db_name']}...")
    print(f"  User: {d['email']}")
    print(f"  Subscription: {d['sub_id']} (COMMUNITY)")
    print(f"  Token hash: {d['token_hash'][:16]}...", flush=True)

    try:
        listed = subprocess.run(
            ["npx", "wrangler", "d1", "list", "--json"],
            cwd=worker_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError as exc:
        log.error(f"npx: {exc.strerror or exc}")
        return 1
    db_uuid = find_db_uuid(listed.stdout, d["db_name"]) if listed.returncode == 0 else None
    if not db_uuid:
        print(f"Database {d['db_name']} not found", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="wrangler-seed-") as tmp:
        config = pathlib.Path(tmp) / "wrangler-seed.toml"
        config.write_text(wrangler_config(pr, d["db_name"], db_uuid), encoding="utf-8")
        sys.stdout.flush()
        executed = subprocess.run(
            [
                "npx",
                "wrangler",
                "d1",
                "execute",
                d["db_name"],
                "--remote",
                "--config",
                str(config),
                "--command",
                seed_sql(d),
            ],
            cwd=worker_dir,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    if executed.returncode != 0:
        return executed.returncode

    print(f"::add-mask::{d['token']}")
    line = f"SMOKE_TEST_TOKEN={d['token']}\n"
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line)
    else:
        sys.stdout.write(line)
    print("Seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
