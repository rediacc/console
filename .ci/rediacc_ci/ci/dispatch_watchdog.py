#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/dispatch-watchdog.sh` (138 lines).

Dispatches ONE generation of the chained watchdog monitor. The twin's header carries why the chain exists (ubuntu-slim's 15-minute job cap against a 1-2h CI run) and who calls it; none of it is restated here.

LIVE CALLERS, not repointed: `.github/workflows/ci.yml` (CI Watchdog bootstrap, `--generation 1`) and `.github/workflows/watchdog-monitor.yml` (chain handoff). The bash twin stays the registered gate; this module is its verified-equivalent alternative, and the cutover is a separate, later, driver-only step.

Ledger: `.ci/shadow/w7p6-dispatch-watchdog.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-dispatch-watchdog --assert --k 5`).

-----------------------------------------------------------------------------
DEFECT C, FIXED AS A DELIBERATE DELTA (Rule T): THE GENERATION CAP WAS
EVALUATED IN OCTAL
-----------------------------------------------------------------------------
`[[ "$GENERATION" =~ ^[0-9]+$ ]]` accepts `08`. The twin's `((GENERATION > 22))`
then read it as a BASE-8 literal. Two consequences, both driven against the twin:

    $ bash .ci/scripts/ci/dispatch-watchdog.sh --run-id 1 --generation 08 \\
        --head-ref m
    .ci/scripts/ci/dispatch-watchdog.sh: line 86: ((: 08: value too great for
      base (error token is "08")
    (info) Dispatched watchdog generation 08 for run 1 on ref m
    exit=0

  `08`, `09` and `019` are invalid octal, so the arithmetic ABORTED, `((...))`
  returned non-zero, the `if` was not taken, and the run proceeded AS IF UNDER
  THE CAP: a check that could not run read as a pass.

    $ bash .ci/scripts/ci/dispatch-watchdog.sh --run-id 1 --generation 025 \\
        --head-ref m        # 025 octal = 21, so 21 <= 22 and it DISPATCHED
    $ bash .ci/scripts/ci/dispatch-watchdog.sh --run-id 1 --generation 030 \\
        --head-ref m        # 030 octal = 24, so 24 > 22 and the chain ENDED

  A caller that zero-padded got a cap of 22 OCTAL generations, not 22.
The port reads the number in base 10 (`over_cap`): `08` is 8 and dispatches without the bash diagnostic, `025` is 25 and ends the chain, `030` is 30 and still ends it. The recordings keep the twin's bytes; `test_delta_a_zero_padded_generation_is_decimal_and_the_cap_runs` pins both sides and fails on the octal behaviour.

-----------------------------------------------------------------------------
DEFECT D, FIXED AS A DELIBERATE DELTA (Rule T): A FAILED DEFAULT-BRANCH LOOKUP
WAS INDISTINGUISHABLE FROM A FAILED DISPATCH
-----------------------------------------------------------------------------
The twin's fallback arm is

    elif try_dispatch "$(gh api "repos/${GITHUB_REPOSITORY}" \\
        --jq '.default_branch')"; then

and a command substitution inside an `elif` condition runs with `set -e` suspended. So when THAT lookup failed, its exit status was discarded, the ref became the EMPTY STRING, and `gh workflow run --ref ''` was attempted and reported as the dispatch having failed:

    (error) Failed to dispatch watchdog generation 1 for run 1: gh workflow run
      watchdog-monitor.yml --repo r/c --ref  -f target_run_id=1 ...

The port checks the lookup's status: a failed lookup is its own error (`Could not determine the default branch of <repo> ...`, exit 1) and no `gh workflow run` is attempted with an empty ref. The recording keeps the twin's bytes as the control; `test_delta_a_failed_default_branch_lookup_is_its_own_error` pins the port.

-----------------------------------------------------------------------------
DEFECT E, FIXED AS A DELIBERATE DELTA (Rule T): AN OPTION AS THE LAST TOKEN
DIED WITHOUT THE SCRIPT'S OWN MESSAGE
-----------------------------------------------------------------------------
`--run-id` / `--generation` / `--pr-number` / `--head-ref` as the LAST token read `"$2"` under `set -u`, so bash refused with `<path>: line 40: $2: unbound variable`, exit 1. The port already named the option (`MISSING_VALUE`, divergence 3). `--pending-rerun` as the last token was worse in the twin: `"${2:-false}"` tolerated the absence, then `shift 2` with one argument left returned non-zero and `set -e` made a **completely silent exit 1** (zero bytes on both streams). The port now prints `MISSING_VALUE` for it too, exit 1; `test_delta_pending_rerun_as_the_last_token_names_the_option` fails on the silent exit.

-----------------------------------------------------------------------------
DEFECT F, FIXED AS A DELIBERATE DELTA (Rule T): A FAILED head_branch LOOKUP
KILLED THE RUN WITH NO MESSAGE OF ITS OWN
-----------------------------------------------------------------------------
`HEAD_REF="$(gh api "$RUN_API" --jq '.head_branch // ""')"` is a plain assignment, so a failing lookup ended the twin at gh's exit status through `set -e` with only gh's own stderr to explain it, while the very next `elif` treated an unreachable API as a reason to fail OPEN. The port keeps the exit status (so callers see what gh returned) and adds one line naming the lookup and the run (`Could not read the head branch of run ...`; the pull-request lookup gets the same treatment). `test_delta_a_failed_run_lookup_names_the_lookup` fails on the silent exit.

-----------------------------------------------------------------------------
DIVERGENCES, ALL IN TEXT ONLY A HUMAN READS
-----------------------------------------------------------------------------
 1. (retired by the Defect C fix: there is no octal reading left to diagnose.)
 2. `${RUN_ID:?--run-id is required}` prints `<path>: line 66: RUN_ID:
    --run-id is required`. This port prints `MISSING_RUN_ID` /
    `MISSING_GENERATION` / `MISSING_REPOSITORY`, same stream, exit 1. Same
    ruling as `deploy/cf_purge_urls.py` divergence 1.
 3. The `$2: unbound variable` shapes of Defect E print `MISSING_VALUE` here, and so does the formerly silent `--pending-rerun` shape.
 4. common.sh's `echo -e` interprets backslash escapes in the message;
    `rediacc_ci.log` formats the message as data.

Exit: 0 dispatched, 0 cap reached, 0 pre-merge bootstrap (fail open), 1 any argument error or dispatch failure.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `MAX_GENERATIONS=22` (twin :85). ~3 hours at ~8-minute generations, matching
# watchdog-monitor.yml's own maxRuntime.
MAX_GENERATIONS = 22

# Divergence 2/3 stand-ins for bash's `${VAR:?}` and `$2: unbound variable`.
MISSING_RUN_ID = "dispatch-watchdog.sh: RUN_ID: --run-id is required"
MISSING_GENERATION = "dispatch-watchdog.sh: GENERATION: --generation is required"
MISSING_REPOSITORY = "dispatch-watchdog.sh: GITHUB_REPOSITORY: GITHUB_REPOSITORY is required"
MISSING_VALUE = "dispatch-watchdog.sh: %s requires a value"

# `^[0-9]+$` from the twin, as a fullmatch. ASCII-only in both engines under
# LC_ALL=C, and fullmatch because Python's `$` also matches before a trailing
# newline while bash's `=~` anchor does not.
NUMERIC = re.compile(r"[0-9]+")

# `grep -qE "not found on the default branch|HTTP 404.*watchdog-monitor"` (twin :126). grep is LINE-oriented and `.` never crosses a newline, so this is applied per line below rather than to the whole blob.
BOOTSTRAP_404 = re.compile(r"not found on the default branch|HTTP 404.*watchdog-monitor")

# The options that consume a following value, and the field each fills.
VALUE_OPTIONS = {
    "--run-id": "run_id",
    "--generation": "generation",
    "--pr-number": "pr_number",
    "--head-ref": "head_ref",
}


class ArgError(Exception):
    """An argument the parser refuses. Carries the exact stderr text, or None.

    `None` is a refusal that prints nothing: the unknown-option arm, whose message the parser already logged itself.
    """

    def __init__(self, message: str | None) -> None:
        super().__init__(message or "")
        self.message = message


def over_cap(value: str, ceiling: int = MAX_GENERATIONS) -> bool:
    """`value > ceiling`, in base 10. `value` has already matched `NUMERIC`, so `08` is 8 and `0022` is 22 (the twin read both as octal; see Defect C)."""
    return int(value, 10) > ceiling


def parse_args(argv: list[str]) -> dict[str, str]:
    """The twin's `while [[ $# -gt 0 ]]` loop, shift semantics included."""
    out = {
        "run_id": "",
        "generation": "",
        "pr_number": "",
        "head_ref": "",
        "pending_rerun": "false",
    }
    i = 0
    while i < len(argv):
        opt = argv[i]
        if opt in VALUE_OPTIONS:
            if i + 1 >= len(argv):
                # `"$2"` under `set -u`. Divergence 3.
                raise ArgError(MISSING_VALUE % opt)
            out[VALUE_OPTIONS[opt]] = argv[i + 1]
            i += 2
        elif opt == "--pending-rerun":
            # `PENDING_RERUN="${2:-false}"` tolerates the absence AND the empty
            # string -- `:-` is a default-on-unset-OR-EMPTY, so `--pending-rerun ''` is accepted as `false` rather than refused by the true/false check below. A missing value is refused above, before this line.
            if i + 1 >= len(argv):
                # The twin's `shift 2` died silently here (Defect E, fixed): the option is named instead.
                raise ArgError(MISSING_VALUE % opt)
            out["pending_rerun"] = argv[i + 1] or "false"
            i += 2
        else:
            log.error("Unknown option: %s" % opt)
            raise ArgError(None)
    return out


def gh_api(endpoint: str, jq: str) -> tuple[int, str]:
    """`gh api <endpoint> --jq <filter>`. Returns (status, stdout, trimmed).

    stderr is NOT captured: the twin lets it through to its own stderr for both of these lookups, and only the DISPATCH merges the two streams.
    """
    try:
        proc = subprocess.run(
            ["gh", "api", endpoint, "--jq", jq],
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, ""
    return proc.returncode, proc.stdout.rstrip("\n")


def dispatch(ref: str, args: dict[str, str], repository: str) -> tuple[int, str]:
    """`gh workflow run watchdog-monitor.yml ...`, both streams MERGED.

    The merge is the twin's (`out="$(dispatch "$1" 2>&1)"`), and it is why a
    SUCCESSFUL dispatch prints nothing: the call's own output is swallowed.
    """
    argv = [
        "gh",
        "workflow",
        "run",
        "watchdog-monitor.yml",
        "--repo",
        repository,
        "--ref",
        ref,
        "-f",
        "target_run_id=%s" % args["run_id"],
        "-f",
        "generation=%s" % args["generation"],
        "-f",
        "pr_number=%s" % args["pr_number"],
        "-f",
        "head_ref=%s" % args["head_ref"],
        "-f",
        "pending_rerun=%s" % args["pending_rerun"],
    ]
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, "gh: command not found"
    return proc.returncode, proc.stdout.rstrip("\n")


def is_bootstrap_404(text: str) -> bool:
    """`grep -qE ... <<<"$DISPATCH_ERR"`, applied per line as grep applies it."""
    return any(BOOTSTRAP_404.search(line) for line in text.split("\n"))


def main(argv: list[str]) -> int:
    try:
        common.require_cmd("gh")
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1

    try:
        args = parse_args(argv)
    except ArgError as exc:
        if exc.message is not None:
            print(exc.message, file=sys.stderr, flush=True)
        return 1

    # Read at the call site, never through an `env = os.environ` alias.
    repository = os.environ.get("GITHUB_REPOSITORY", "")

    for value, message in (
        (args["run_id"], MISSING_RUN_ID),
        (args["generation"], MISSING_GENERATION),
        (repository, MISSING_REPOSITORY),
    ):
        if not value:
            print(message, file=sys.stderr, flush=True)
            return 1

    if not NUMERIC.fullmatch(args["run_id"]):
        log.error("--run-id must be numeric, got: %s" % args["run_id"])
        return 1
    if not NUMERIC.fullmatch(args["generation"]):
        log.error("--generation must be numeric, got: %s" % args["generation"])
        return 1
    if args["pending_rerun"] not in ("true", "false"):
        log.error("--pending-rerun must be true or false, got: %s" % args["pending_rerun"])
        return 1

    if over_cap(args["generation"]):
        log.warn(
            "Generation %s exceeds cap %d (~3h of coverage) - ending the watchdog chain"
            % (args["generation"], MAX_GENERATIONS)
        )
        return 0

    run_api = "repos/%s/actions/runs/%s" % (repository, args["run_id"])
    if not args["head_ref"]:
        status, value = gh_api(run_api, '.head_branch // ""')
        if status != 0:
            # Defect F (fixed): the twin's `set -e` ended the run with no message of its own.
            log.error(
                "Could not read the head branch of run %s (%s exited %d)"
                % (args["run_id"], "gh api", status)
            )
            return status
        args["head_ref"] = value
    if not args["pr_number"]:
        # Best-effort: .pull_requests is populated for same-repo branches. When it stays empty the monitor simply skips the PR-label reads.
        status, value = gh_api(run_api, '.pull_requests[0].number // ""')
        if status != 0:
            log.error(
                "Could not read the pull request of run %s (%s exited %d)"
                % (args["run_id"], "gh api", status)
            )
            return status
        args["pr_number"] = value

    dispatch_err = ""
    if args["head_ref"]:
        status, out = dispatch(args["head_ref"], args, repository)
        if status == 0:
            log.info(
                "Dispatched watchdog generation %s for run %s on ref %s"
                % (args["generation"], args["run_id"], args["head_ref"])
            )
            return 0
        dispatch_err = out

    # Defect D (fixed): the twin discarded this lookup's status and dispatched with an empty ref.
    status, default_branch = gh_api("repos/%s" % repository, ".default_branch")
    if status != 0:
        log.error(
            "Could not determine the default branch of %s (gh api exited %d); "
            "nothing was dispatched" % (repository, status)
        )
        return 1
    status, out = dispatch(default_branch, args, repository)
    if status == 0:
        log.info(
            "Dispatched watchdog generation %s for run %s on the default branch "
            "(head-ref copy unavailable)" % (args["generation"], args["run_id"])
        )
        return 0
    dispatch_err = out

    if is_bootstrap_404(dispatch_err):
        # workflow_dispatch resolves the workflow FILENAME against the DEFAULT branch's registry, so until watchdog-monitor.yml has landed on main it cannot be dispatched from ANY ref. One-time bootstrap condition; fail OPEN with a loud warning instead of failing the job.
        log.warn(
            "watchdog-monitor.yml is not registered on the default branch yet "
            "(pre-merge bootstrap) - run %s continues UNWATCHED" % args["run_id"]
        )
        return 0

    log.error(
        "Failed to dispatch watchdog generation %s for run %s: %s"
        % (args["generation"], args["run_id"], dispatch_err)
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
