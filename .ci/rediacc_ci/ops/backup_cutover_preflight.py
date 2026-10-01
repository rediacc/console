"""Port of `scripts/ops/backup-cutover-preflight.sh` (204 lines): is this deployment ready to cut over from the rclone/OneDrive path to the chunk store?

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.backup_cutover_preflight
    ACCOUNT_BACKUP_S3_ENDPOINT=... ACCOUNT_BACKUP_S3_BUCKET=... ACCOUNT_BACKUP_S3_ACCESS_KEY_ID=... \\
      ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY=... PYTHONPATH=.ci python3 -m rediacc_ci.ops.backup_cutover_preflight

FAILS CLOSED, AND READ ONLY. Every check either proves its claim or refuses; none degrades to a pass. A preflight that answers "looks fine" because it could not reach the store converts an absent bucket into a green light, and the first thing done with that light is decommissioning the only working restore path. It creates no bucket, writes no object, mints no credential and makes no mutating call: it only runs `renet backup ... --help` probes, reads three source files, and sends one signed HEAD to the bucket.

The four checks, in the bash's order: the restore verb on the built renet, the grant plane wiring (the locally-signed R2 JWT minter must not be selected), the store reachability leg (absent credentials are a REFUSAL, not a skip), and the decommission interlock in the backup unit generator.

Exit 0: every check passed. Exit 1: at least one failed or a required input was absent.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_backup_cutover_preflight.py` that fails on the bash behaviour).

  1. THE CREDENTIALS DO NOT TRAVEL ON ARGV. `--user "$KEY:$SECRET"` put the store secret in `ps` for the length of the request; the pair goes to curl on stdin (`-K -`).
  2. THE SIGV4 PROBE DOES NOT PIPE. `curl --help all | grep -q -- --aws-sigv4` under `set -o pipefail` reads grep's early exit as curl dying of SIGPIPE (exit 141) whenever curl's help is longer than the pipe buffer, so the check could report "curl lacks --aws-sigv4" on a curl that has it. The help text is read whole and searched in-process.
  3. AN UNREADABLE GENERATOR IS ITS OWN FAILURE. A missing or unreadable `backup-schedule-unit-generator.ts` fell into the last branch and was reported as "nothing refuses a non-hosted-service destination", which blames the code for a file that is not there.
  4. THE HEAD IS BOUNDED THE SAME WAY (`--max-time 20`) AND ANSWERS WITH THE CODE; a transport error is the existing `000`, now carrying curl's own message.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log, paths

GRANT_PARENT_VAR = "ACCOUNT_BACKUP_R2_GRANT_PARENT_SECRET"


class Preflight:
    """The check ledger: every verdict counted, every failure kept for the exit status."""

    def __init__(self) -> None:
        self.checks = 0
        self.failures = 0

    def passed(self, message: str) -> None:
        self.checks += 1
        log.info(message)

    def failed(self, message: str, detail: str | None = None) -> None:
        self.checks += 1
        self.failures += 1
        log.error(message)
        if detail:
            sys.stderr.write("      %s\n" % detail)
            sys.stderr.flush()


def _runs_ok(argv: list[str]) -> bool:
    try:
        return subprocess.run(argv, capture_output=True, check=False).returncode == 0
    except OSError:
        return False


def check_restore_verb(pf: Preflight, root) -> None:
    log.step("Restore path")
    renet = root / "private" / "renet" / "bin" / "renet"
    if not (renet.is_file() and os.access(renet, os.X_OK)):
        pf.failed(
            "renet binary is missing at %s" % renet,
            "Build it:  (cd private/renet && ./build.sh dev)",
        )
        return
    if _runs_ok([str(renet), "backup", "restore", "--help"]):
        pf.passed("renet backup restore exists (probed on the binary, not assumed from source)")
    else:
        pf.failed(
            "this renet has no 'backup restore' verb",
            "The deployed binary predates the download engine. Rebuild and redeploy.",
        )
    if _runs_ok([str(renet), "backup", "snapshot", "--help"]):
        pf.passed("renet backup snapshot exists")
    else:
        pf.failed("this renet has no 'backup snapshot' verb")


def check_grant_plane(pf: Preflight, root) -> None:
    log.step("Grant plane selection")
    plane = root / "private" / "account" / "src" / "services" / "backup-chunk-store.ts"
    if not plane.is_file():
        pf.failed("private/account is not checked out; cannot verify the plane wiring")
        return
    if GRANT_PARENT_VAR in plane.read_text(encoding="utf-8", errors="replace"):
        pf.passed("the R2 JWT minter is present in the tree (its selection is the question below)")
    else:
        pf.failed(
            "backup-chunk-store.ts no longer mentions %s" % GRANT_PARENT_VAR,
            "This preflight is out of date with the plane it checks.",
        )
    if os.environ.get(GRANT_PARENT_VAR):
        pf.failed(
            "%s is set, which selects the LOCALLY-SIGNED R2 JWT minter" % GRANT_PARENT_VAR,
            "Live R2 has never accepted a credential from that minter (see "
            "docs/backup-storage/07-execution-record.md 6.1). Unset it and use ACCOUNT_BACKUP_S3_* "
            "unless you have re-probed it.",
        )
    else:
        pf.passed("%s is unset, so the unproven JWT minter is not selected" % GRANT_PARENT_VAR)


def _curl_has_sigv4() -> bool:
    try:
        proc = subprocess.run(
            ["curl", "--help", "all"], capture_output=True, text=True, check=False
        )
    except OSError:
        return False
    return "--aws-sigv4" in proc.stdout


def _head_status(endpoint: str, bucket: str, key_id: str, secret: str) -> tuple[str, str]:
    """HEAD the bucket with a SigV4 signature. `-I`, never `-X HEAD`: the latter waits for a body a HEAD reply never has."""
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-I",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            "20",
            "--aws-sigv4",
            "aws:amz:auto:s3",
            "-K",
            "-",
            "%s/%s" % (endpoint.rstrip("/"), bucket),
        ],
        input='user = "%s:%s"\n' % (key_id, secret),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return "000", proc.stderr.strip()
    return proc.stdout.strip() or "000", ""


def check_store(pf: Preflight) -> None:
    log.step("Chunk store reachability")
    endpoint = os.environ.get("ACCOUNT_BACKUP_S3_ENDPOINT") or ""
    bucket = os.environ.get("ACCOUNT_BACKUP_S3_BUCKET") or ""
    key_id = os.environ.get("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID") or ""
    secret = os.environ.get("ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY") or ""
    missing = [
        name
        for name, value in (
            ("ACCOUNT_BACKUP_S3_ENDPOINT", endpoint),
            ("ACCOUNT_BACKUP_S3_BUCKET", bucket),
            ("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", key_id),
            ("ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY", secret),
        )
        if not value
    ]
    if missing:
        pf.failed(
            "no chunk store to check: %s unset" % " ".join(missing),
            "This is a REFUSAL, not a skip: the cutover cannot be declared ready against a store "
            "nobody reached. Supply them, or accept that this run does not clear the cutover.",
        )
        return
    if bucket == "rediacc-backups":
        pf.failed(
            "ACCOUNT_BACKUP_S3_BUCKET is the bare production name 'rediacc-backups'",
            "Test targets must be named distinctly (e.g. rediacc-backups-probe) so no "
            "misconfiguration can cross test and production backups.",
        )
    if not _curl_has_sigv4():
        pf.failed("curl lacks --aws-sigv4 (needs 7.75+), so the store leg cannot be signed")
        return
    code, why = _head_status(endpoint, bucket, key_id, secret)
    where = "%s/%s" % (endpoint.rstrip("/"), bucket)
    if code in ("200", "204"):
        pf.passed("the bucket %s exists and the credentials are accepted for it" % bucket)
    elif code == "403":
        pf.failed("403 on %s: the credentials are not authorized for this bucket" % bucket)
    elif code == "404":
        pf.failed("404: bucket %s does not exist" % bucket, "Create it before cutting over.")
    elif code == "000":
        pf.failed("the endpoint %s did not answer%s" % (endpoint, " (%s)" % why if why else ""))
    else:
        pf.failed("unexpected HTTP %s from %s" % (code, where))


def check_decommission_interlock(pf: Preflight, root) -> None:
    log.step("Decommission interlock")
    gen = (
        root
        / "packages"
        / "cli"
        / "src"
        / "services"
        / "backup"
        / "backup-schedule-unit-generator.ts"
    )
    # The rclone emission was removed on 2026-08-15 by operator decision. What matters now is the opposite: the generator must REFUSE a non-hosted-service destination rather than emit nothing for it, because silently emitting nothing is the original defect (a timer that backs up nothing, with no error anywhere).
    try:
        text = gen.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        pf.failed("cannot read the unit generator at %s: %s" % (gen, exc.strerror or exc))
        return
    if "backup sync push" in text:
        pf.failed(
            "the rclone schedule path is STILL PRESENT in the unit generator",
            "It was removed on 2026-08-15 by operator decision. If it is back, either the removal "
            "was reverted or a merge resurrected it.",
        )
    elif "Refusing to generate a unit that would back up nothing" in text:
        pf.passed(
            "the rclone path is gone AND a non-hosted-service destination is refused loudly, not silently skipped"
        )
    else:
        pf.failed(
            "the rclone path is gone but nothing refuses a non-hosted-service destination",
            "A strategy still naming a storage destination would generate a unit that backs up "
            "NOTHING, silently. Restore the explicit throw in buildBackupCommands.",
        )


def main() -> int:
    root = paths.repo_root()
    pf = Preflight()
    log.info(
        "Backup cutover preflight (read-only: no bucket creation, no writes, no credential minting)"
    )
    check_restore_verb(pf, root)
    check_grant_plane(pf, root)
    check_store(pf)
    check_decommission_interlock(pf, root)
    print()
    if pf.failures == 0:
        log.info("cutover preflight: %d checks, all passed" % pf.checks)
        return 0
    log.error(
        "cutover preflight: %d of %d checks FAILED. Do not cut over" % (pf.failures, pf.checks)
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
