#!/usr/bin/env python3
"""Port of `.ci/scripts/housekeeping/cleanup-pr-environments.sh`.

Deletes the empty `pr-N` ENVIRONMENT OBJECTS GitHub leaves behind after a PR
closes. Its already-ported sibling `cleanup_github_deployments.py` deletes the
deployment RECORDS inside an environment, which needs only `deployments:write`;
the object itself needs `Administration:write`, which no CI token here carries,
so this one is an OPERATOR-RUN script and not a workflow step.

Usage: cleanup_pr_environments.py --repo <owner/repo> [--dry-run]

THE THREE REFUSALS ARE THE POINT and are reproduced exactly, because GitHub
cannot restore a deleted environment: only names matching `^pr-[0-9]+$` are
ever touched, an environment whose PR is still OPEN is skipped, and an
environment that still holds deployment records is skipped and reported.

`set -e` IS ON, AND THE TWIN DOES NOT LOOK LIKE IT. The twin's own line 28 is
`set -uo pipefail` -- deliberately without `-e` -- and then line 32 sources
`common.sh`, whose line 11 is `set -euo pipefail`. Sourcing runs in the caller's
shell, so `-e` is switched back on for every line after the source. Driven, not
inferred. That single fact is what produces DEFECT 1 below, and a port that
implemented the script the author appears to have written would disagree with
the script that actually runs.

STREAMS: NOTHING IS EVER WRITTEN TO STDOUT. Every message is `log_step` /
`log_warn` / `log_info`, all of which write to stderr (common.sh:35-49), and the
DELETE call is redirected on both streams. Only the environment listing's stdout
is read, and it is captured.

THE ARGUMENT PARSER IS NOT RE-IMPLEMENTED: `rediacc_ci.core.common.parse_args`
is the port of `parse_args` (common.sh:324-353) and carries its four rules and
both live quirks, including `--dry-run false` meaning NOT a dry run.

THE `sort -t- -k2 -n` ORDER IS REPRODUCED WITH ITS TIE-BREAK, not approximated.
GNU sort compares the numeric key first and falls back to a byte-wise
comparison of the WHOLE LINE when the keys tie, so `pr-2`, `pr-010`, `pr-10`
sorts to exactly that order (driven against real `sort`; `010` and `10` tie at
10 and `pr-010` wins the byte comparison). A port that sorted on the integer
alone would agree on every realistic input and disagree there.

TWO DEFECTS IN THE TWIN, REPRODUCED AND REPORTED RATHER THAN FIXED, on the same
contract this box's sibling states: agreement with the twin is the deliverable,
and changing live behaviour is the operator's call.

  1. "NO PR-N ENVIRONMENTS FOUND" IS UNREACHABLE, AND THE NORMAL CASE EXITS 1
     IN SILENCE. `envs="$(gh api ... | grep -E '^pr-[0-9]+$' | sort ...)"`: when
     nothing matches, `grep` exits 1, `pipefail` gives the pipeline that 1, the
     assignment inherits it, and the `-e` inherited from common.sh kills the
     script THERE -- before the `if [[ -z "$envs" ]]` that was written to
     handle exactly this case. Driven against the real twin with a listing of
     `edge stable production-eu`: one step line, then exit 1, and the "No pr-N
     environments found" text never appears. So the clean-tree outcome an
     operator should see as a green no-op is a bare failure, and a failed API
     call is indistinguishable from it.
  2. NEITHER `--repo` NOR THE ENVIRONMENT NAME IS URL-ENCODED into the
     `deployments?environment=...` query, the same latent defect the sibling
     port documents. Here the name is constrained to `^pr-[0-9]+$` before it is
     interpolated, so it is unreachable through the environment; `--repo` is
     still raw.

K=5 LEDGER: `.ci/shadow/w7p6-cleanup-pr-environments.observations.jsonl`.
"""

from __future__ import annotations

import re
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

USAGE = "Usage: cleanup-pr-environments.sh --repo <owner/repo> [--dry-run]"

# `true`, exactly -- see parse_args quirk 2 in the sibling port.
DRY_RUN_ON = "true"

# `grep -E '^pr-[0-9]+$'`, the first of the three refusals: `edge`, `stable` and
# `production-eu` live in the same listing and must never be touched.
PR_ENV_RE = re.compile(r"^pr-[0-9]+$")


def environments_path(repo: str) -> str:
    return "repos/%s/environments" % repo


def deployments_path(repo: str, env: str) -> str:
    """NOT URL-ENCODED, deliberately: see defect 2 in the module docstring."""
    return "repos/%s/deployments?environment=%s&per_page=100" % (repo, env)


def environment_path(repo: str, env: str) -> str:
    return "repos/%s/environments/%s" % (repo, env)


def sort_key(name: str) -> tuple[int, str]:
    """`sort -t- -k2 -n`, tie-break included.

    Field 2 of `pr-<n>` split on `-` is the number; `-n` compares it
    numerically, and GNU sort's last-resort comparison breaks a tie by
    comparing the entire line byte-wise. Only names that already matched
    PR_ENV_RE reach this, so the numeric field always parses.
    """
    return (int(name.split("-", 1)[1]), name)


def select_environments(names: list[str]) -> list[str]:
    """The `grep | sort` half of the pipeline, as a pure function."""
    return sorted([n for n in names if PR_ENV_RE.match(n)], key=sort_key)


def pipeline_status(gh_rc: int, matched: int) -> int:
    """`pipefail`: the status of the RIGHTMOST command that failed.

    gh -> grep -> sort. `sort` cannot fail here, and `grep` fails with 1 exactly
    when it matched nothing, so a listing that returned nothing usable reports
    1 even when `gh` itself failed with something else -- and a listing that DID
    match reports gh's own code. Both driven against real bash.
    """
    if matched == 0:
        return 1
    return gh_rc


def _gh_capture(args: list[str]) -> subprocess.CompletedProcess[str]:
    """stdout captured, stderr DISCARDED -- every `gh` here carries `2>/dev/null`."""
    return subprocess.run(
        ["gh", *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False
    )


def _gh_silent(args: list[str]) -> int:
    """`gh ... >/dev/null 2>&1`. Returns the exit code."""
    return subprocess.run(
        ["gh", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    ).returncode


def _substitution(proc: subprocess.CompletedProcess[str], fallback: str) -> str:
    """`$(cmd 2>/dev/null || echo <fallback>)`.

    Both halves write to the same captured stdout, so a command that printed
    something AND failed contributes both, exactly as bash concatenates them,
    and command substitution then strips every trailing newline.
    """
    text = proc.stdout
    if proc.returncode != 0:
        text += fallback + "\n"
    return text.rstrip("\n")


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print(str(exc), file=sys.stderr)
        return getattr(exc, "code", 2)

    repo = args.get("ARG_REPO", "")
    dry_run = args.get("ARG_DRY_RUN", "false")

    try:
        common.require_cmd("gh")
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1

    if not repo:
        log.error(USAGE)
        return 1

    log.step("Cleaning up empty pr-N environments in %s" % repo)
    if dry_run == DRY_RUN_ON:
        log.warn("DRY-RUN mode: no deletions will be performed")

    listing = _gh_capture(
        [
            "api",
            environments_path(repo),
            "--paginate",
            "--jq",
            ".environments[]?.name",
        ]
    )
    envs = select_environments([n for n in listing.stdout.split("\n") if n])
    status = pipeline_status(listing.returncode, len(envs))
    if status != 0:
        # DEFECT 1: `set -e` on the failed assignment. No message, and the
        # `if [[ -z "$envs" ]]` branch below the twin's pipeline is dead code.
        return status

    deleted = 0
    skipped = 0
    total = 0
    for env in envs:
        total += 1
        num = env[len("pr-") :]

        state = _substitution(
            _gh_capture(["pr", "view", num, "--repo", repo, "--json", "state", "--jq", ".state"]),
            "UNKNOWN",
        )
        if state == "OPEN":
            log.warn("SKIP %s: PR #%s is still OPEN" % (env, num))
            skipped += 1
            continue

        n_dep = _substitution(
            _gh_capture(["api", deployments_path(repo, env), "--jq", "length"]), "unknown"
        )
        if n_dep != "0":
            log.warn(
                "SKIP %s: still holds %s deployment record(s) -- run "
                "cleanup-github-deployments.sh first" % (env, n_dep)
            )
            skipped += 1
            continue

        if dry_run == DRY_RUN_ON:
            log.warn(
                "[DRY-RUN] Would delete environment %s (PR #%s %s, 0 deployments)"
                % (env, num, state)
            )
            continue

        if _gh_silent(["api", "-X", "DELETE", environment_path(repo, env)]) == 0:
            log.info("Deleted %s (PR #%s %s)" % (env, num, state))
            deleted += 1
        else:
            log.warn("Failed to delete %s -- this needs a token with Administration:write" % env)
            skipped += 1

    if dry_run == DRY_RUN_ON:
        log.info("Would delete %d of %d pr-N environment(s)" % (total - skipped, total))
    else:
        log.info("Deleted %d of %d pr-N environment(s); %d skipped" % (deleted, total, skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
