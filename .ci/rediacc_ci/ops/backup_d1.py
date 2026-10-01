"""Port of `scripts/ops/backup-d1.sh` (148 lines): export the account D1 databases to `.backups/`.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.backup_d1 [--dry-run] [--self-destruct] [production|edge]

Writes `.backups/production/account-db-<region>-<UTC stamp>.sql` and `.backups/edge/edge-account-db-<region>-<UTC stamp>.sql`, one `wrangler d1 export --remote` per region. One timestamp covers the whole run so a regional set groups as a unit. Auth is `cf_auth` (a ready `CF_MANAGEMENT_TOKEN`, or the Global API Key pair from which a scoped token is minted).

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_backup_d1.py` that fails on the bash behaviour).

  1. A TOKEN THIS RUN MINTED IS ALWAYS DELETED. The bash resolved the Global API Key into a fresh scoped token, printed "will self-destruct after run", and then deleted it only under `--self-destruct`: every default run left a live management token behind, and any failed export left one behind even with the flag, because `set -e` ended the script before the cleanup line. Here a token the run created is destroyed in a `finally`; `--self-destruct` additionally destroys a token the operator supplied.
  2. A FAILED EXPORT IS REPORTED, NOT A SILENT EXIT. `wrangler ... 2>&1 | grep -v` under `set -eo pipefail` ended the script with no message of its own on a wrangler failure, and also ended it falsely when wrangler printed nothing but the filtered URL lines (`grep -v` exits 1 when it selects no line). The exit status of wrangler is read directly and named.
  3. THE SIZE IS THE FILE'S SIZE. `du -h` reports allocated blocks, so a 300-byte export logged as 4.0K.
  4. A MISSING OUTPUT FILE IS AN ERROR WITH A NAME. `wc -l <"$out_file"` on a file wrangler never wrote ended the script with the shell's own redirect error.

THE PRE-SIGNED URL FILTER IS KEPT. Wrangler prints a pre-signed R2 URL valid for an hour; every output line mentioning `r2.cloudflarestorage.com` or `valid for one hour` is dropped before it reaches the terminal. Wrangler's stdout and stderr are merged and the filtered text goes to this process's stdout, as the bash `2>&1 |` did.
"""

from __future__ import annotations

import datetime
import shutil
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.ops import cf_auth

ACCOUNT_ID = cf_auth.DEFAULT_ACCOUNT_ID
REGIONS = ("eu", "us", "asia")
PROD_DB_PREFIX = "account-db"
EDGE_DB_PREFIX = "edge-account-db"
USAGE = "Usage: backup-d1.sh [--dry-run] [--self-destruct] [production|edge]"
FILTERED = ("r2.cloudflarestorage.com", "valid for one hour")


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return "%d%s" % (value, unit) if unit == "B" else "%.1f%s" % (value, unit)
        value /= 1024
    return "%dB" % size


def _export(env: dict[str, str], db_name: str, out_file: str) -> int:
    """Run the wrangler export, echoing its output minus the pre-signed URL lines; return its exit status."""
    proc = subprocess.Popen(
        ["npx", "wrangler", "d1", "export", db_name, "--remote", "--output=%s" % out_file],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.stdout is None:
        return proc.wait()
    for line in proc.stdout:
        if not any(marker in line for marker in FILTERED):
            sys.stdout.write(line)
    sys.stdout.flush()
    return proc.wait()


def _backup_database(
    env: dict[str, str], backup_dir, stamp: str, env_name: str, db_name: str, dry_run: bool
) -> bool:
    out_dir = backup_dir / env_name
    out_file = out_dir / ("%s-%s.sql" % (db_name, stamp))
    log.step("Backing up %s: %s" % (env_name, db_name))
    if dry_run:
        log.warn("[DRY-RUN] Would export %s to %s" % (db_name, out_file))
        return True
    out_dir.mkdir(parents=True, exist_ok=True)
    rc = _export(env, db_name, str(out_file))
    if rc != 0:
        log.error("wrangler d1 export of %s failed (exit %d)" % (db_name, rc))
        return False
    if not out_file.is_file():
        log.error("wrangler reported success but wrote no file: %s" % out_file)
        return False
    data = out_file.read_bytes()
    log.info("Exported %d lines (%s) -> %s" % (data.count(b"\n"), _human_size(len(data)), out_file))
    return True


def main(argv: list[str]) -> int:
    dry_run = False
    self_destruct = False
    target = ""
    for arg in argv:
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--self-destruct":
            self_destruct = True
        elif arg in ("production", "prod"):
            target = "production"
        elif arg == "edge":
            target = "edge"
        else:
            log.error("Unknown argument: %s" % arg)
            log.error(USAGE)
            return 1

    if shutil.which("npx") is None:
        log.error("Required command 'npx' is not available")
        return 1

    try:
        auth = cf_auth.resolve(ACCOUNT_ID)
    except cf_auth.CfAuthError as exc:
        log.error(str(exc))
        return 1

    try:
        if self_destruct:
            try:
                cf_auth.require_self_destruct_capable(auth)
            except cf_auth.CfAuthError as exc:
                for line in str(exc).splitlines():
                    log.error(line)
                return 1
        env = cf_auth.wrangler_env(auth, ACCOUNT_ID)
        backup_dir = paths.repo_root() / ".backups"
        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H-%M-%S")

        log.step("D1 Database Backup (per-region)")
        if dry_run:
            log.warn("DRY-RUN mode: no exports will be performed")
        plan = []
        if target in ("", "production"):
            plan += [("production", "%s-%s" % (PROD_DB_PREFIX, r)) for r in REGIONS]
        if target in ("", "edge"):
            plan += [("edge", "%s-%s" % (EDGE_DB_PREFIX, r)) for r in REGIONS]
        for env_name, db_name in plan:
            if not _backup_database(env, backup_dir, stamp, env_name, db_name, dry_run):
                return 1
        log.info("Backup complete")
        if self_destruct and dry_run:
            log.warn("[DRY-RUN] Would delete CF management token")
        return 0
    finally:
        if auth.created or (self_destruct and not dry_run):
            cf_auth.self_destruct(auth)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
