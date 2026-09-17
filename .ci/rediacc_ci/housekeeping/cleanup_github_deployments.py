#!/usr/bin/env python3
"""Port of `.ci/scripts/housekeeping/cleanup-github-deployments.sh`.

Deletes every GitHub deployment RECORD for one environment, which is what
drops a `pr-N` entry from the repository's Deployments view when a PR closes.
The twin's header explains why records and not the environment object:
deleting the environment needs `Administration:write`, which neither
`GITHUB_TOKEN` nor the housekeeping App token carries, while the records need
only `deployments:write` -- so deleting the records achieves the visible
cleanup without admin rights.

Usage: cleanup_github_deployments.py --repo <owner/repo> --environment <name>
[--dry-run]

THE ARGUMENT PARSER IS NOT RE-IMPLEMENTED. `parse_args` (common.sh:324-353)
already has its Python equivalent in `rediacc_ci.core.common.parse_args`, with
the twin's four parsing rules and the `printf -v` security property driven
there. This module calls it and reads `ARG_REPO` / `ARG_ENVIRONMENT` /
`ARG_DRY_RUN` out of the dict exactly as the twin reads them out of the shell's
globals, which preserves two quirks worth naming because they are reachable
from a real command line:

  * `--dry-run false` sets DRY_RUN to the string `false`, so the flag is OFF.
    Only the literal `true` arms it, and `--dry-run` with nothing after it (or
    another `--flag` after it) is what produces `true`.
  * anything not starting with `--` is skipped silently, so a positional
    argument is invisible.

STREAMS: THIS SCRIPT WRITES NOTHING TO STDOUT, EVER. Every message goes
through `log_step` / `log_warn` / `log_info` / `log_error`, all of which write
to stderr (common.sh:35-54), and both `gh` mutation calls are redirected to
/dev/null on both streams. The one command whose stdout is read is the
deployment listing, and it is captured. A port that printed its progress to
stdout would look identical in a terminal and would corrupt any caller that
pipes it.

THE MUTATING PATH IS NEVER DRIVEN AGAINST A REAL REPOSITORY BY ANY TEST HERE.
`test_housekeeping_cleanup_github_deployments.py` puts a recording fake `gh`
on PATH (ruling 7's seam) and drives both the `--dry-run` path and the real
path against it, so the DELETE call sequence is compared without a single
network request.

TWO DEFECTS IN THE TWIN, REPRODUCED AND REPORTED RATHER THAN FIXED, because
this box's contract is agreement with the twin and both are live release-path
behaviour changes that are the operator's call:

  1. A FAILED DELETION DOES NOT AFFECT THE EXIT CODE. Every `gh api -X DELETE`
     that fails produces a `log_warn` and nothing else, so the script prints
     "Deleted 0 of 5 deployment(s)" and exits 0. A workflow step sees a green
     tick while the Deployments view still holds every record. Driven against
     a fake `gh` whose DELETE always fails: exit 0, five warnings.
  2. NEITHER `--repo` NOR `--environment` IS URL-ENCODED into the query
     string. `?environment=$ENVIRONMENT&per_page=100` with an environment name
     containing `&` or a space builds a different request than the caller
     asked for. Today every caller passes `pr-<n>`, so it is latent.

  Both are pinned by tests that state they are pinning a DEFECT, so a future
  fix to the twin turns them red rather than sliding past.

K=5 LEDGER: `.ci/shadow/w7p6-cleanup-github-deployments.observations.jsonl`.
"""

from __future__ import annotations

import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

USAGE = "Usage: cleanup-github-deployments.sh --repo <owner/repo> --environment <name> [--dry-run]"

# `true`, exactly. common.sh's parse_args stores strings, and the twin compares against this one literal -- `--dry-run false` therefore means NOT dry run.
DRY_RUN_ON = "true"


def list_path(repo: str, environment: str) -> str:
    """The listing endpoint, built exactly as the twin builds it.

    NOT URL-ENCODED, deliberately: see defect 2 in the module docstring. This
    is a transliteration, and quietly encoding here would make the port send a
    different request than the twin for the same input.
    """
    return "repos/%s/deployments?environment=%s&per_page=100" % (repo, environment)


def statuses_path(repo: str, deployment_id: str) -> str:
    """Active deployments cannot be deleted; this marks one inactive first."""
    return "repos/%s/deployments/%s/statuses" % (repo, deployment_id)


def delete_path(repo: str, deployment_id: str) -> str:
    return "repos/%s/deployments/%s" % (repo, deployment_id)


def _gh_capture(args: list[str]) -> subprocess.CompletedProcess[str]:
    """stdout captured, stderr INHERITED -- `$(gh ...)` with no redirect."""
    return subprocess.run(["gh", *args], stdout=subprocess.PIPE, text=True, check=False)


def _gh_silent(args: list[str]) -> int:
    """`gh ... >/dev/null 2>&1`. Returns the exit code."""
    return subprocess.run(
        ["gh", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    ).returncode


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        # `printf -v` on a key that is not a valid identifier: bash writes this and returns 2, and `set -e` takes the whole script down with it.
        print(str(exc), file=sys.stderr)
        return getattr(exc, "code", 2)

    repo = args.get("ARG_REPO", "")
    environment = args.get("ARG_ENVIRONMENT", "")
    dry_run = args.get("ARG_DRY_RUN", "false")

    try:
        common.require_cmd("gh")
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1

    if not repo or not environment:
        log.error(USAGE)
        return 1

    log.step("Cleaning up GitHub deployments for environment: %s (%s)" % (environment, repo))
    if dry_run == DRY_RUN_ON:
        log.warn("DRY-RUN mode: no deletions will be performed")

    listing = _gh_capture(
        [
            "api",
            list_path(repo, environment),
            "--paginate",
            "--jq",
            ".[].id",
        ]
    )
    if listing.returncode != 0:
        # `set -e` on a failed command substitution. gh has already written its
        # own diagnostic to the inherited stderr; nothing is fabricated here.
        return listing.returncode
    ids = listing.stdout.rstrip("\n")

    if not ids:
        log.info("No deployments found for %s" % environment)
        return 0

    deleted = 0
    total = 0
    for deployment_id in ids.split("\n"):
        if not deployment_id:
            continue
        total += 1
        if dry_run == DRY_RUN_ON:
            log.warn("[DRY-RUN] Would delete deployment %s (%s)" % (deployment_id, environment))
            continue
        # Best-effort, exactly as the twin: `|| true`. A deployment that is already inactive answers 422 and that is not an error here.
        _gh_silent(
            ["api", statuses_path(repo, deployment_id), "-X", "POST", "-f", "state=inactive"]
        )
        if _gh_silent(["api", "-X", "DELETE", delete_path(repo, deployment_id)]) == 0:
            deleted += 1
        else:
            log.warn("Failed to delete deployment %s (%s)" % (deployment_id, environment))

    if dry_run == DRY_RUN_ON:
        log.info("Would delete %d deployment(s) for %s" % (total, environment))
    else:
        log.info("Deleted %d of %d deployment(s) for %s" % (deleted, total, environment))
    # DEFECT 1, preserved: a failed deletion has not changed this 0.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
