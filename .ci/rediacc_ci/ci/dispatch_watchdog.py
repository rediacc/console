#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/dispatch-watchdog.sh` (138 lines).

Dispatches ONE generation of the chained watchdog monitor. The twin's header
carries why the chain exists (ubuntu-slim's 15-minute job cap against a 1-2h CI
run) and who calls it; none of it is restated here.

LIVE CALLERS, not repointed: `.github/workflows/ci.yml` (CI Watchdog bootstrap,
`--generation 1`) and `.github/workflows/watchdog-monitor.yml` (chain handoff).
The bash twin stays the registered gate; this module is its verified-equivalent
alternative, and the cutover is a separate, later, driver-only step.

Ledger: `.ci/shadow/w7p6-dispatch-watchdog.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-dispatch-watchdog --assert
--k 5`).

-----------------------------------------------------------------------------
DEFECT C: THE GENERATION CAP IS EVALUATED IN OCTAL, AND A ZERO-PADDED VALUE
EITHER SKIPS THE CAP ENTIRELY OR APPLIES THE WRONG ONE
-----------------------------------------------------------------------------
`[[ "$GENERATION" =~ ^[0-9]+$ ]]` accepts `08`. `((GENERATION > 22))` then
reads it as a BASE-8 literal. Two consequences, both driven:

    $ bash .ci/scripts/ci/dispatch-watchdog.sh --run-id 1 --generation 08 \\
        --head-ref m
    .ci/scripts/ci/dispatch-watchdog.sh: line 86: ((: 08: value too great for
      base (error token is "08")
    (info) Dispatched watchdog generation 08 for run 1 on ref m
    exit=0

  `08`, `09` and `019` are invalid octal, so the arithmetic ABORTS, `((...))`
  returns non-zero, the `if` is not taken, and the run proceeds AS IF UNDER THE
  CAP. The cap check did not run and the script says nothing about it: this is
  the "a check that could not run reads as a pass" shape.

    $ bash .ci/scripts/ci/dispatch-watchdog.sh --run-id 1 --generation 025 \\
        --head-ref m        # 025 octal = 21, so 21 <= 22 and it DISPATCHES
    $ bash .ci/scripts/ci/dispatch-watchdog.sh --run-id 1 --generation 030 \\
        --head-ref m        # 030 octal = 24, so 24 > 22 and the chain ENDS

  A caller that zero-pads gets a cap of 22 OCTAL generations, not 22.
  Reproduced exactly here, including the bash diagnostic's absence from this
  port (divergence 1). `OCTAL_CAP` names it so a test can assert it by name.

-----------------------------------------------------------------------------
DEFECT D: A FAILED DEFAULT-BRANCH LOOKUP IS INDISTINGUISHABLE FROM A FAILED
DISPATCH
-----------------------------------------------------------------------------
The fallback arm is

    elif try_dispatch "$(gh api "repos/${GITHUB_REPOSITORY}" \\
        --jq '.default_branch')"; then

and a command substitution inside an `elif` condition runs with `set -e`
suspended. So when THAT lookup fails, its exit status is discarded, the ref
becomes the EMPTY STRING, and `gh workflow run --ref ''` is attempted and
reported as the dispatch having failed. Driven, with every `gh` call failing:

    (error) Failed to dispatch watchdog generation 1 for run 1: gh workflow run
      watchdog-monitor.yml --repo r/c --ref  -f target_run_id=1 ...

The empty `--ref ` in that message is the whole receipt. "The lookup could not
run" is folded into "the dispatch was refused", and the 404-bootstrap arm below
then greps the WRONG error text for its fail-open decision.

-----------------------------------------------------------------------------
DEFECT E: TWO ARGUMENT SHAPES DIE WITHOUT THE SCRIPT'S OWN MESSAGE
-----------------------------------------------------------------------------
`--run-id` / `--generation` / `--pr-number` / `--head-ref` as the LAST token
reads `"$2"` under `set -u`, so bash refuses with
`<path>: line 40: $2: unbound variable`, exit 1 -- not the `Unknown option`
message the parser exists to print. And `--pending-rerun` as the last token is
worse: `"${2:-false}"` tolerates the absence, then `shift 2` with one argument
left returns non-zero and `set -e` turns it into a **completely silent exit 1**
(driven: zero bytes on both streams). Same class as
`deploy/write_release_sentinel.py`'s FINDING 5.

-----------------------------------------------------------------------------
DEFECT F: A FAILED head_branch LOOKUP KILLS THE RUN WITH NO MESSAGE OF ITS OWN
-----------------------------------------------------------------------------
`HEAD_REF="$(gh api "$RUN_API" --jq '.head_branch // ""')"` is a plain
assignment, so a failing lookup ends the script at exit 1 through `set -e` with
only gh's own stderr to explain it -- while the very next `elif` treats an
unreachable API as a reason to fail OPEN. The two adjacent lookups disagree
about what an unreachable API means.

-----------------------------------------------------------------------------
DIVERGENCES, ALL IN TEXT ONLY A HUMAN READS
-----------------------------------------------------------------------------
 1. bash's arithmetic diagnostic for an invalid octal literal
    (`((: 08: value too great for base ...`) names a line of the twin. This
    port takes the same branch, silently. Exit code, stdout and the script's
    own stderr are identical; the twin emits one extra bash line.
 2. `${RUN_ID:?--run-id is required}` prints `<path>: line 66: RUN_ID:
    --run-id is required`. This port prints `MISSING_RUN_ID` /
    `MISSING_GENERATION` / `MISSING_REPOSITORY`, same stream, exit 1. Same
    ruling as `deploy/cf_purge_urls.py` divergence 1.
 3. The `$2: unbound variable` shapes of Defect E print `MISSING_VALUE` here.
    The silent `shift 2` shape is reproduced exactly: exit 1, nothing printed.
 4. common.sh's `echo -e` interprets backslash escapes in the message;
    `rediacc_ci.log` formats the message as data.

Exit: 0 dispatched, 0 cap reached, 0 pre-merge bootstrap (fail open), 1 any
argument error or dispatch failure.
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

# Defect C, named so the differential can assert it by name.
OCTAL_CAP = True

# Divergence 2/3 stand-ins for bash's `${VAR:?}` and `$2: unbound variable`.
MISSING_RUN_ID = "dispatch-watchdog.sh: RUN_ID: --run-id is required"
MISSING_GENERATION = "dispatch-watchdog.sh: GENERATION: --generation is required"
MISSING_REPOSITORY = "dispatch-watchdog.sh: GITHUB_REPOSITORY: GITHUB_REPOSITORY is required"
MISSING_VALUE = "dispatch-watchdog.sh: %s requires a value"

# `^[0-9]+$` from the twin, as a fullmatch. ASCII-only in both engines under
# LC_ALL=C, and fullmatch because Python's `$` also matches before a trailing
# newline while bash's `=~` anchor does not.
NUMERIC = re.compile(r"[0-9]+")

# `grep -qE "not found on the default branch|HTTP 404.*watchdog-monitor"`
# (twin :126). grep is LINE-oriented and `.` never crosses a newline, so this is
# applied per line below rather than to the whole blob.
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

    `None` is the silent `shift 2` shape of Defect E, which prints nothing at
    all -- and a message-less refusal has to be representable, or the port
    would invent output the twin does not produce.
    """

    def __init__(self, message: str | None) -> None:
        super().__init__(message or "")
        self.message = message


def octal_gt(value: str, ceiling: int) -> bool | None:
    """`((VALUE > ceiling))`, with bash's base rules. None = the arithmetic died.

    A leading `0` makes it OCTAL, a leading `0x` hexadecimal, and an invalid
    digit for the chosen base aborts the whole expression. None is the abort,
    and the twin's `if` then falls through -- which is Defect C.
    """
    try:
        parsed = int(value, 8) if len(value) > 1 and value[0] == "0" else int(value, 10)
    except ValueError:
        return None
    return parsed > ceiling


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
            # string -- `:-` is a default-on-unset-OR-EMPTY, so
            # `--pending-rerun ''` is accepted as `false` rather than refused
            # by the true/false check below. `shift 2` then does not tolerate
            # the absence: Defect E, reproduced exactly as a silent exit 1.
            out["pending_rerun"] = (argv[i + 1] if i + 1 < len(argv) else "") or "false"
            if i + 1 >= len(argv):
                raise ArgError(None)
            i += 2
        else:
            log.error("Unknown option: %s" % opt)
            raise ArgError(None)
    return out


def gh_api(endpoint: str, jq: str) -> tuple[int, str]:
    """`gh api <endpoint> --jq <filter>`. Returns (status, stdout, trimmed).

    stderr is NOT captured: the twin lets it through to its own stderr for both
    of these lookups, and only the DISPATCH merges the two streams.
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

    over_cap = octal_gt(args["generation"], MAX_GENERATIONS)
    if over_cap:
        log.warn(
            "Generation %s exceeds cap %d (~3h of coverage) - ending the watchdog chain"
            % (args["generation"], MAX_GENERATIONS)
        )
        return 0
    # `over_cap is None` is Defect C's abort arm: the twin's `if` is not taken
    # and the run continues, cap unchecked.

    run_api = "repos/%s/actions/runs/%s" % (repository, args["run_id"])
    if not args["head_ref"]:
        status, value = gh_api(run_api, '.head_branch // ""')
        if status != 0:
            # Defect F: `set -e` on a plain assignment. No message of its own.
            return status
        args["head_ref"] = value
    if not args["pr_number"]:
        # Best-effort: .pull_requests is populated for same-repo branches. When
        # it stays empty the monitor simply skips the PR-label reads.
        status, value = gh_api(run_api, '.pull_requests[0].number // ""')
        if status != 0:
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

    # Defect D: the lookup's exit status is DISCARDED and its empty output is
    # used as a ref, exactly as the twin's command substitution in an `elif`
    # condition discards it.
    _status, default_branch = gh_api("repos/%s" % repository, ".default_branch")
    status, out = dispatch(default_branch, args, repository)
    if status == 0:
        log.info(
            "Dispatched watchdog generation %s for run %s on the default branch "
            "(head-ref copy unavailable)" % (args["generation"], args["run_id"])
        )
        return 0
    dispatch_err = out

    if is_bootstrap_404(dispatch_err):
        # workflow_dispatch resolves the workflow FILENAME against the DEFAULT
        # branch's registry, so until watchdog-monitor.yml has landed on main it
        # cannot be dispatched from ANY ref. One-time bootstrap condition; fail
        # OPEN with a loud warning instead of failing the job.
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
