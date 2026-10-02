"""Port of `scripts/ops/scrub-sentinel.sh` (133 lines): scrub a release sentinel and its versioned bytes from R2.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.scrub_sentinel v1.0.5                  # dry-run
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.scrub_sentinel v1.0.5 --execute        # delete
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.scrub_sentinel v1.0.5 --execute --yes  # skip confirmation

The recovery path the release-state drift gate names for "cli sentinel present, git tag missing". A sentinel exists only if `write-release-sentinel` completed, so the bytes count as released by the invariant; when the downstream tag never happened the operator either re-runs CD to create the tag (preferred, keeps the bytes) or scrubs the sentinel and the bytes with this tool so the version number is freed. Dry-run is the default; deletion needs `--execute`. Deletions are not recoverable (the bucket is assumed unversioned).

Env (required): `CLOUDFLARE_R2_ACCESS_KEY_ID`, `CLOUDFLARE_R2_SECRET_ACCESS_KEY`, `CLOUDFLARE_R2_ENDPOINT`; `RELEASES_BUCKET` optional (default `rediacc-releases`). The aws CLI does the S3 calls, through `rediacc_ci.core.release_state_validator` for the sentinel probe.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_ops_scrub_sentinel.py` that fails on the bash behaviour).

  1. AN UNANSWERED PROBE IS NOT AN ANSWER. `if rsv_sentinel_exists ...` treated the helper's exit 2 (could not tell) as false and printed `sentinel: absent`, and the object count ended `2>/dev/null || echo 0`, so expired credentials or an unreachable endpoint produced a plan reading "sentinel absent, objects: 0" for a release that may be fully sealed. The release-state validator already carries the three states (`Probe.YES/NO/UNKNOWN`); the plan now prints `UNKNOWN` for what it could not establish and the run exits 1, dry-run included, because a plan that could not be drawn is not a plan.
  2. THE DELETE IS VERIFIED. `aws s3 rm --recursive` exiting 0 was the whole proof; the prefix is listed again afterwards and a non-empty answer (or an unanswered one) is a failure rather than "scrubbed".
  3. END OF INPUT AT A PROMPT ABORTS WITH A MESSAGE. `read -r` returning non-zero under `set -e` exited silently.
  4. `--help` PRINTS THIS MODULE'S USAGE, not a `sed -n '2,30p'` window of the script's own comments.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.core import release_state_validator as rsv
from rediacc_ci.well_known import RELEASES_BUCKET

PRODUCT = "cli"
STRICT_VERSION = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
HELP = (
    """Scrub a release sentinel and its versioned bytes from R2.

Usage:
  scrub_sentinel v1.0.5                  dry-run
  scrub_sentinel v1.0.5 --execute        actually delete
  scrub_sentinel v1.0.5 --execute --yes  skip confirmation

Env (required): CLOUDFLARE_R2_ACCESS_KEY_ID, CLOUDFLARE_R2_SECRET_ACCESS_KEY,
CLOUDFLARE_R2_ENDPOINT. RELEASES_BUCKET is optional (default """
    + RELEASES_BUCKET
    + """).
"""
)


def _aws(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["aws", *argv], capture_output=True, text=True, check=False)


def object_count(prefix: str, endpoint: str) -> int | None:
    """Objects under the prefix, or None when the listing did not answer."""
    proc = _aws(
        [
            "s3api",
            "list-objects-v2",
            "--bucket",
            rsv.bucket(),
            "--prefix",
            prefix,
            "--endpoint-url",
            endpoint,
            "--query",
            "length(Contents || `[]`)",
            "--output",
            "text",
        ]
    )
    if proc.returncode != 0:
        log.error(
            "listing s3://%s/%s failed (exit %d): %s"
            % (rsv.bucket(), prefix, proc.returncode, proc.stderr.strip()[:300])
        )
        return None
    text = proc.stdout.strip()
    if text == "None":
        return 0
    return int(text) if text.isdigit() else None


def _tag_exists(repo_root, version: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "refs/tags/%s" % version],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def _ask(prompt: str) -> str:
    """One answer line, the way `read -r -p` gives it: the prompt goes to stderr and only when stdin is a terminal."""
    if sys.stdin.isatty():
        sys.stderr.write(prompt)
        sys.stderr.flush()
    try:
        return input()
    except EOFError:
        return ""


def main(argv: list[str]) -> int:
    # Line-buffered so a merged stdout+stderr keeps the order the bash printed it in.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)
    version = ""
    execute = False
    skip_confirm = False
    for arg in argv:
        if arg == "--execute":
            execute = True
        elif arg in ("--yes", "-y"):
            skip_confirm = True
        elif arg in ("--help", "-h"):
            sys.stdout.write(HELP)
            return 0
        elif re.match(r"v[0-9]", arg):
            if version:
                log.error("only one version argument")
                return 2
            version = arg
        else:
            log.error("unknown argument: %s" % arg)
            return 2
    if not version:
        log.error(
            "usage: PYTHONPATH=.ci python3 -m rediacc_ci.ops.scrub_sentinel v<MAJOR>.<MINOR>.<PATCH> [--execute] [--yes]"
        )
        return 2
    if not STRICT_VERSION.match(version):
        log.error("invalid version '%s' (expected strict semver, e.g. v1.0.5)" % version)
        return 2

    if shutil.which("aws") is None:
        log.error("Required command 'aws' is not available")
        return 1
    key_id = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID")
    secret = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY")
    endpoint = os.environ.get("CLOUDFLARE_R2_ENDPOINT")
    for name, value in (
        ("CLOUDFLARE_R2_ACCESS_KEY_ID", key_id),
        ("CLOUDFLARE_R2_SECRET_ACCESS_KEY", secret),
        ("CLOUDFLARE_R2_ENDPOINT", endpoint),
    ):
        if not value:
            log.error("Required environment variable '%s' is not set" % name)
            return 1
    os.environ["AWS_ACCESS_KEY_ID"] = key_id or ""
    os.environ["AWS_SECRET_ACCESS_KEY"] = secret or ""
    os.environ["AWS_DEFAULT_REGION"] = "auto"

    log.step("scrub plan for %s" % version)
    prefix = "%s/%s/" % (PRODUCT, version)
    print("  s3://%s/%s" % (rsv.bucket(), prefix))
    sentinel = rsv.sentinel_exists(PRODUCT, version)
    if sentinel is rsv.Probe.YES:
        print("    sentinel: PRESENT (will be deleted)")
    elif sentinel is rsv.Probe.NO:
        print("    sentinel: absent")
    else:
        print("    sentinel: UNKNOWN (the probe could not tell; see the error above)")
    count = object_count(prefix, endpoint or "")
    print("    objects: %s" % ("UNKNOWN" if count is None else count))
    if sentinel is rsv.Probe.UNKNOWN or count is None:
        log.error("the scrub plan could not be established; nothing was deleted")
        return 1

    repo_root = paths.repo_root()
    if _tag_exists(repo_root, version):
        log.warn("git tag %s exists in %s" % (version, repo_root))
        log.warn("  scrubbing bytes that back a live release tag will break installs")
        log.warn("  reconsider re-running CD for %s instead" % version)
        if (
            execute
            and not skip_confirm
            and _ask("type 'YES I UNDERSTAND' to proceed: ") != "YES I UNDERSTAND"
        ):
            log.error("aborted")
            return 1

    if not execute:
        log.info("dry-run: pass --execute to delete")
        return 0

    if not skip_confirm and _ask("delete the listed prefixes? [y/N] ") not in ("y", "Y"):
        log.error("aborted")
        return 1

    log.step("deleting s3://%s/%s" % (rsv.bucket(), prefix))
    removed = subprocess.run(
        [
            "aws",
            "s3",
            "rm",
            "s3://%s/%s" % (rsv.bucket(), prefix),
            "--endpoint-url",
            endpoint or "",
            "--recursive",
        ],
        check=False,
    )
    if removed.returncode != 0:
        log.error("aws s3 rm failed (exit %d)" % removed.returncode)
        return removed.returncode
    left = object_count(prefix, endpoint or "")
    if left != 0:
        log.error(
            "the prefix still lists %s after the delete"
            % ("an unanswered result" if left is None else "%d object(s)" % left)
        )
        return 1
    log.info("scrubbed %s" % version)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
