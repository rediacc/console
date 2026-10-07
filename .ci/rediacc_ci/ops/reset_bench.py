"""Port of `scripts/ops/reset-bench.sh` (198 lines): wipe the bench environment back to a clean state.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.reset_bench [--yes] [--d1-only] [--r2-only]

DESTRUCTIVE. It drops every table of the bench D1 database (`account-db-bench`) and re-applies migrations, then deletes every object in the bench R2 bucket (`rediacc-configs-bench`). The worker code and DNS are untouched; `deploy_bench` redeploys code. Without `--yes` one confirmation is asked: type `wipe bench`.

Auth is `cf_auth`. As in the bash, the credential is destroyed on the way out whether the run succeeded or not, a pre-supplied `CF_MANAGEMENT_TOKEN` included (the scoped token is treated as single-use for this script).

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_reset_bench.py` that fails on the bash behaviour).

  1. THE R2 WIPE USES THE S3 API, AND A FAILED LISTING IS A FAILURE. The listing was `curl -sS <CF REST .../r2/buckets/<b>/objects> 2>/dev/null || echo '{"result":[]}'` with jq errors discarded. Run live on 2026-10-01 that endpoint answers `Authentication error` to the minted management token (it carries no R2 permission group, and the REST API serves no object listing), so the bash read EVERY run as "Bucket is already empty (or listing API not available -- continuing)" and ended "bench has been reset" with the bucket untouched. The port lists and deletes through the S3-compatible endpoint (ListObjectsV2 with continuation tokens, then DELETE per key) signed with `CLOUDFLARE_R2_ENDPOINT` / `CLOUDFLARE_R2_ACCESS_KEY_ID` / `CLOUDFLARE_R2_SECRET_ACCESS_KEY` (bound by the deploy-bench profile), which are checked before anything is wiped; the credentials travel on curl's stdin, not argv. Any non-200 page stops the run.
  2. TABLE NAMES ARE QUOTED AS DATA. `DROP TABLE IF EXISTS "$t"` interpolated the name unescaped; an embedded double quote now doubles, as SQLite requires.
  8. THE DROP RUNS CHILDREN BEFORE PARENTS. Live against bench on 2026-10-01 the bash failed the drop every time (`no such table: main.organizations: SQLITE_ERROR`, 75 tables, nothing dropped): D1 enforces foreign keys, ignores `PRAGMA foreign_keys = OFF`, and the tables were dropped in name order. The port orders the drops by the `REFERENCES` in each table's `CREATE` text (`drop_order`) and uses `PRAGMA defer_foreign_keys = on`, D1's supported switch.
  3. A FAILED OBJECT DELETE IS NAMED, with the count already deleted (the bash loop ran `npx wrangler r2 object delete ... >/dev/null` under `set -e` and stopped with only wrangler's text).
  4. `jq` IS NOT REQUIRED. The bash demanded it up front; every JSON read is in-process here.
  5. `--help` PRINTS THIS MODULE'S USAGE TEXT, not the script's own comments selected with `grep '^# '` (which also printed every column-zero section comment from the body of the script).
  7. A MINTED TOKEN IS AWAITED before the first D1 query (`cf_auth.await_propagation`, GET probes until D1 and Workers Scripts each accept it twice in a row, at most 60 s). The bash had no wait and failed every real run with `Authentication error` while Cloudflare propagated the new token; a token still refused at the deadline is a named error and exit 1, never a traceback.
  6. END OF INPUT AT THE PROMPT ABORTS. `read -rp` returning non-zero under `set -e` exited with no message; the port prints `Aborted.` and exits 1.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse

from rediacc_ci import log, paths
from rediacc_ci.ops import cf_auth

ACCOUNT_ID = cf_auth.DEFAULT_ACCOUNT_ID
DB_UUID = "ac45c2de-053b-404c-bc47-9ad9cbd2bb15"
DB_NAME = "account-db-bench"
BUCKET = "rediacc-configs-bench"
CONFIRMATION = "wipe bench"
TABLE_QUERY = (
    "SELECT name, sql FROM sqlite_master WHERE type='table' "
    "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%'"
)
HELP = """Wipe the bench environment back to a clean state.

Usage:
  reset_bench [--yes] [--d1-only] [--r2-only]

  --yes, -y   skip the confirmation prompt
  --d1-only   skip the R2 wipe
  --r2-only   skip the D1 wipe

Resources: D1 account-db-bench, R2 rediacc-configs-bench. The worker code and
DNS are not touched; rediacc_ci.ops.deploy_bench redeploys them.
"""


class ResetError(Exception):
    """A step failed; the message is printed and the run exits 1."""


def _query(auth: cf_auth.Auth, sql: str) -> dict:
    url = "%s/accounts/%s/d1/database/%s/query" % (cf_auth.CF_API_BASE, ACCOUNT_ID, DB_UUID)
    try:
        return cf_auth.curl_json("POST", url, auth.headers, json.dumps({"sql": sql}), flags="-sS")
    except cf_auth.CfAuthError as exc:
        raise ResetError(str(exc)) from None


REFERENCES = re.compile(r'REFERENCES\s+[`"\[]?([A-Za-z0-9_]+)', re.IGNORECASE)


def drop_order(rows: list[dict]) -> list[str]:
    """Table names ordered so every table is dropped before the tables it references.

    D1 enforces foreign keys, does not honour `PRAGMA foreign_keys = OFF`, and refuses `pragma_foreign_key_list` (`SQLITE_AUTH`), so the references are read from each table's `CREATE` text. Dropping a parent first makes the child's implicit delete fail with `no such table: main.<parent>`. Tables in a reference cycle keep their listed order after the acyclic ones; `defer_foreign_keys` covers them.
    """
    names = [r["name"] for r in rows]
    parents = {
        r["name"]: {
            m for m in REFERENCES.findall(r.get("sql") or "") if m in names and m != r["name"]
        }
        for r in rows
    }
    ordered: list[str] = []
    remaining = list(names)
    while remaining:
        # A table is droppable once nothing still remaining references it.
        free = [n for n in remaining if not any(n in parents[o] for o in remaining if o != n)]
        if not free:
            ordered += remaining
            break
        ordered += free
        remaining = [n for n in remaining if n not in free]
    return ordered


def quote_identifier(name: str) -> str:
    """A SQLite double-quoted identifier."""
    return '"%s"' % name.replace('"', '""')


def _wipe_d1(auth: cf_auth.Auth, env: dict[str, str]) -> None:
    log.step("Querying D1 table list (%s)" % DB_NAME)
    listed = _query(auth, TABLE_QUERY)
    if listed.get("success") is not True:
        print(json.dumps(listed, indent=2))
        raise ResetError("D1 query failed")
    try:
        tables = drop_order([row for row in listed["result"][0]["results"] if row.get("name")])
    except (KeyError, IndexError, TypeError):
        print(json.dumps(listed, indent=2))
        raise ResetError("D1 query failed: unexpected response shape") from None
    if not tables:
        log.info("No user tables to drop")
    else:
        log.step("Dropping %d tables: %s" % (len(tables), " ".join(tables)))
        sql = "PRAGMA defer_foreign_keys = on;"
        for table in tables:
            sql += " DROP TABLE IF EXISTS %s;" % quote_identifier(table)
        sql += ' DROP TABLE IF EXISTS "__drizzle_migrations";'
        result = _query(auth, sql)
        if result.get("success") is not True:
            print(json.dumps(result, indent=2))
            raise ResetError("Drop tables failed")
        log.info("All tables dropped")
    log.step("Re-applying migrations to %s" % DB_NAME)
    worker_dir = paths.repo_root() / "workers" / "account"
    _npm_install_if_needed(worker_dir, env)
    _run(
        [
            "npx",
            "wrangler",
            "d1",
            "migrations",
            "apply",
            DB_NAME,
            "--remote",
            "--config",
            "wrangler.bench.toml",
        ],
        worker_dir,
        env,
        "wrangler d1 migrations apply",
    )
    log.info("Schema recreated")


def _npm_install_if_needed(worker_dir, env: dict[str, str]) -> None:
    if not (worker_dir / "node_modules").is_dir():
        _run(["npm", "install"], worker_dir, env, "npm install")


def _run(argv: list[str], cwd, env: dict[str, str], what: str, quiet: bool = False) -> None:
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        check=False,
        stdout=subprocess.DEVNULL if quiet else None,
    )
    if proc.returncode != 0:
        raise ResetError("%s failed (exit %d)" % (what, proc.returncode))


XML_KEY = re.compile(r"<Key>([^<]*)</Key>")
XML_NEXT_TOKEN = re.compile(r"<NextContinuationToken>([^<]*)</NextContinuationToken>")


class R2Credentials:
    """The R2 S3-API credentials, read by name from the environment (the deploy-bench Bitwarden profile binds them)."""

    def __init__(self) -> None:
        self.endpoint = (os.environ.get("CLOUDFLARE_R2_ENDPOINT") or "").rstrip("/")
        self.key_id = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID") or ""
        self.secret = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY") or ""

    def missing(self) -> list[str]:
        names = {
            "CLOUDFLARE_R2_ENDPOINT": self.endpoint,
            "CLOUDFLARE_R2_ACCESS_KEY_ID": self.key_id,
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": self.secret,
        }
        return [n for n, v in names.items() if not v]


def _s3(creds: R2Credentials, method: str, path: str) -> tuple[int, str]:
    """One SigV4-signed request to the R2 S3 endpoint; the credentials travel on curl's stdin, never argv. Returns (HTTP status, body)."""
    config = 'user = "%s:%s"\n' % (creds.key_id, creds.secret)
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-X",
            method,
            "--aws-sigv4",
            "aws:amz:auto:s3",
            "-K",
            "-",
            "-w",
            "\n%{http_code}",
            "%s/%s" % (creds.endpoint, path),
        ],
        input=config,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ResetError("R2 request failed: %s" % proc.stderr.strip()[:300])
    body, _, status = proc.stdout.rpartition("\n")
    return int(status or 0), body


def list_bucket_keys(creds: R2Credentials) -> list[str]:
    """Every object key in the bench bucket (ListObjectsV2, following continuation tokens); a failed page raises."""
    keys: list[str] = []
    token = ""
    while True:
        query = "list-type=2&max-keys=1000"
        if token:
            query += "&continuation-token=%s" % urllib.parse.quote(token, safe="")
        status, body = _s3(creds, "GET", "%s?%s" % (BUCKET, query))
        if status != 200:
            raise ResetError("listing %s failed: HTTP %d %s" % (BUCKET, status, body.strip()[:200]))
        if "<ListBucketResult" not in body:
            raise ResetError("listing %s failed: the answer was not a ListBucketResult" % BUCKET)
        # The answer is machine-generated and flat; a regex read avoids an XML parser on a network answer.
        keys += [html.unescape(k) for k in XML_KEY.findall(body)]
        truncated = "true" if "<IsTruncated>true</IsTruncated>" in body else "false"
        found = XML_NEXT_TOKEN.search(body)
        token = html.unescape(found.group(1)) if found else ""
        if truncated != "true" or not token:
            return keys


def _wipe_r2(creds: R2Credentials) -> None:
    log.step("Listing objects in %s (S3 API)" % BUCKET)
    keys = list_bucket_keys(creds)
    if not keys:
        log.info("Bucket is already empty")
        return
    log.step("Deleting %d objects from %s" % (len(keys), BUCKET))
    for index, key in enumerate(keys):
        status, body = _s3(creds, "DELETE", "%s/%s" % (BUCKET, urllib.parse.quote(key, safe="/")))
        if status not in (200, 204):
            raise ResetError(
                "deleting %s failed: HTTP %d %s; %d of %d objects deleted"
                % (key, status, body.strip()[:200], index, len(keys))
            )
    log.info("Objects deleted")


def main(argv: list[str]) -> int:
    assume_yes = False
    do_d1 = True
    do_r2 = True
    for arg in argv:
        if arg in ("--yes", "-y"):
            assume_yes = True
        elif arg == "--d1-only":
            do_r2 = False
        elif arg == "--r2-only":
            do_d1 = False
        elif arg in ("-h", "--help"):
            sys.stdout.write(HELP)
            return 0
        else:
            log.error("Unknown argument: %s" % arg)
            log.error("Run with --help for usage.")
            return 2

    for cmd in ("curl", "npx"):
        if shutil.which(cmd) is None:
            log.error("Required command '%s' is not available" % cmd)
            return 1

    r2 = R2Credentials()
    if do_r2 and r2.missing():
        log.error("the R2 wipe needs %s in the environment" % ", ".join(r2.missing()))
        return 1
    try:
        auth = cf_auth.resolve(ACCOUNT_ID)
    except cf_auth.CfAuthError as exc:
        log.error(str(exc))
        return 1
    try:
        env = cf_auth.wrangler_env(auth, ACCOUNT_ID, scrub_global_key=True)
        cf_auth.await_propagation(auth)
        if not assume_yes:
            print()
            log.warn("About to wipe the bench environment:")
            if do_d1:
                print("  D1: drop all rows from %s, then re-apply migrations" % DB_NAME)
            if do_r2:
                print("  R2: delete all objects from %s" % BUCKET)
            print()
            # `read -rp` semantics: the prompt goes to stderr, and only when stdin is a terminal.
            if sys.stdin.isatty():
                sys.stderr.write("Type 'wipe bench' to continue: ")
                sys.stderr.flush()
            try:
                confirm = input()
            except EOFError:
                confirm = ""
            if confirm != CONFIRMATION:
                log.error("Aborted.")
                return 1
        try:
            if do_d1:
                _wipe_d1(auth, env)
            if do_r2:
                _wipe_r2(r2)
        except ResetError as exc:
            log.error(str(exc))
            return 1
        print()
        log.info("bench has been reset")
        print(
            "  Worker code is unchanged. To redeploy fresh code: "
            "PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench"
        )
        return 0
    except cf_auth.CfAuthError as exc:
        log.error(str(exc))
        return 1
    finally:
        cf_auth.self_destruct(auth)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
