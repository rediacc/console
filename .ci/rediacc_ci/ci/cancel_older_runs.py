#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/cancel-older-runs.sh` (124 lines).

Force-cancel the CI runs on this branch that started before this one. The twin's header owns the contract (it replaced the concurrency group's slow normal-cancel and the serializing Queue gate); it is not restated here beyond what the code needs.

LIVE CALLER, not repointed. The bash twin stays the registered gate; this module is its verified-equivalent alternative, and the cutover is a separate, later, driver-only step.

Ledger: `.ci/shadow/w7p6-cancel-older-runs.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-cancel-older-runs --assert --k 5`).

-----------------------------------------------------------------------------
THE TWIN CAN ONLY FAIL FOR TWO REASONS, AND NEITHER IS "IT DID NOT CANCEL"
-----------------------------------------------------------------------------
Read the exit codes rather than the log lines. `GITHUB_REPOSITORY not set` and `GH_TOKEN not set` exit 1. EVERY other outcome the script names -- the current run could not be fetched, the run JSON could not be parsed, the listing call failed on every poll, both cancel endpoints refused for every older run, the timeout expired with older runs still in progress -- ends `exit 0`.

That is defensible as a best-effort pre-step and it is reproduced verbatim, but it means a green from this script is not a claim that anything was cancelled. Driven 2026-09-14 with a recording fake `gh`; the four probes are in `test_ci_cancel_older_runs.py`. Reported to the driver, not repaired here: `.ci/scripts/ci/` is not this writer's to change.

-----------------------------------------------------------------------------
THREE BEHAVIOURS OF THE TWIN THAT ARE NOT IN ITS HEADER, ALL DRIVEN
-----------------------------------------------------------------------------
QUIRK 1 -- A NON-JSON BODY FROM A SUCCESSFUL `gh` KILLS THE SCRIPT WITH EXIT 5.
`RUN_INFO=$(gh api ... 2>&1)` merges gh's STDERR into the body, and the next
line pipes that into `jq`. Under `set -euo pipefail` a jq parse error is fatal:

    $ FAKE_RUN_JSON='not json' GITHUB_RUN_ID=9 GITHUB_REPOSITORY=a/b GH_TOKEN=t \\
        bash .ci/scripts/ci/cancel-older-runs.sh
    -> Checking for older in-progress CI runs...
    jq: parse error: Invalid numeric literal at line 1, column 4
    rc=5

So the one script that otherwise cannot fail exits 5, with jq's raw text and no sentence of its own, whenever `gh` emits a deprecation warning on stderr alongside a perfectly good body. Reproduced exactly, by running the SAME `jq` and propagating its stderr and its status.

QUIRK 2 -- A MALFORMED `--timeout` WAS ARITHMETIC ON AN UNQUOTED WORD, AND THE PORT REFUSES IT (Rule T delta). `[[ $ELAPSED -ge $TIMEOUT ]]` made `--timeout 1abc` an arithmetic SYNTAX error that `[[ ]]` answered false, so the timeout vanished and the loop never ended:

    $ timeout 4 bash .ci/scripts/ci/cancel-older-runs.sh --timeout 1abc \\
        --poll-interval 1     # with an older run always present
    rc=124   (killed by `timeout`, i.e. it was still going)

and `--timeout abc` was an UNBOUND VARIABLE under `set -u`, dying at the twin's line 92 with exit 1 and a bash diagnostic. The port validates the value up front, before any `gh` call: only a whole non-negative decimal number is a timeout, anything else is a usage error (exit 2) naming the flag and the value. The recordings keep the twin's bytes; `test_delta_a_malformed_timeout_is_a_usage_error_naming_the_value` and `test_delta_only_a_whole_non_negative_number_is_a_timeout` fail on the bash behaviour.

QUIRK 3 -- `force_cancel_run` LEAKS THE API RESPONSE BODY ONTO STDOUT.
`gh api -X POST ... 2>/dev/null` redirects stderr only, so the `{}` GitHub
returns is printed to the script's stdout, once per cancelled run, interleaved
with the `log_info` lines on stderr. Reproduced by inheriting stdout for that
child exactly as bash does.

-----------------------------------------------------------------------------
WHY THIS SHELLS OUT TO `jq` AND `sleep` INSTEAD OF USING `json` AND `time`
-----------------------------------------------------------------------------
Both are the twin's own choice of tool and both are observable. `json.loads` raises a Python message with a Python traceback where the twin prints jq's sentence and exits 5; `time.sleep` accepts a float where `sleep zz` prints coreutils' two-line diagnostic and takes the script down with exit 1. Emulating either means guessing bytes that the real binary already produces, so the
real binary is what runs. The jq PROGRAMS are the twin's, copied rather than rewritten, and `test_the_jq_programs_are_the_twins` re-reads the twin to prove it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

from rediacc_ci import log
from rediacc_ci.core import common, gh_retry

# `TIMEOUT="${ARG_TIMEOUT:-60}"` and friends (twin :33-35). Names and defaults.
DEFAULT_TIMEOUT = "60"
DEFAULT_POLL_INTERVAL = "10"
DEFAULT_WORKFLOW = "ci.yml"

# The twin's line numbers for its two `gh api` command substitutions. bash names the line in `command not found`, so a port that cannot fail identically on a machine without `gh` is not equivalent -- and the twin has NO `require_cmd`, so that machine reads as a PASS. See `not_found` below.
RUN_LOOKUP_LINE = 57
LISTING_LINE = 98

# The two jq programs, copied from the twin (:104 and :105). The first is built by interpolating the current run id and its creation timestamp into the filter TEXT, which is the twin's own approach and is why it is a format string here.
JQ_OLDER_RUNS = (
    '[.workflow_runs[] | select(.id != %s and .created_at < "%s") '
    "| {id: .id, run_number: .run_number}]"
)
JQ_LENGTH = "length"
JQ_ROWS = ".[]"

# A timeout is whole seconds. ASCII digits only (`\d` would take other scripts' digits), and no sign, fraction, exponent or radix prefix: those were arithmetic quirks in the twin, not spellings anyone relied on.
_TIMEOUT = re.compile(r"[0-9]+")


def not_found(binary: str, line: int) -> str:
    """What bash writes when a command in `$PATH` does not exist.

    `<script>: line <N>: <binary>: command not found`, and the status is 127. Not cosmetic here: the twin has NO `require_cmd`, so a missing `gh` reaches line 57, its message is captured by `2>&1` INTO the run body, and the script reports `Failed to fetch current run info: ...command not found` and exits 0. A missing tool is a PASS. Found by driving both sides on a PATH without
    `gh` (2026-09-14); the port raised FileNotFoundError and exited 1 until this existed, which is a louder answer than the twin's and therefore a divergence.
    """
    return "%s: line %d: %s: command not found\n" % (sys.argv[0], line, binary)


def jq(
    program: str, payload: str, *, args: tuple[str, ...] = (), line: int
) -> subprocess.CompletedProcess[str]:
    """`echo "$payload" | jq <args> '<program>'`, with the twin's newline.

    `echo` appends one, so the input does too. stderr is CAPTURED rather than discarded because the twin does not redirect it for these three calls, and QUIRK 1 is precisely jq's stderr reaching the user. `line` is the twin's own line number, needed only for the missing-binary message.
    """
    try:
        return subprocess.run(
            ["jq", *args, program],
            input=payload + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=["jq"], returncode=127, stdout="", stderr=not_found("jq", line)
        )


def jq_or_die(program: str, payload: str, *, args: tuple[str, ...] = (), line: int) -> str:
    """Run jq, or reproduce `set -euo pipefail` killing the script.

    The twin's `X=$(echo "$Y" | jq ...)` is a plain assignment, so `set -e`
    applies and `pipefail` hands it jq's status. Command substitution then strips trailing newlines, which `rstrip("\\n")` does.
    """
    proc = jq(program, payload, args=args, line=line)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.stderr.flush()
        raise SystemExit(proc.returncode)
    return proc.stdout.rstrip("\n")


def gh_capture(args: list[str], *, merge_stderr: bool, line: int) -> tuple[int, str]:
    """`$(gh api ... 2>&1)` or `$(gh api ... 2>/dev/null)`.

    `merge_stderr` picks between the twin's two spellings: :57 merges (which is QUIRK 1's cause) and :98 discards. Trailing newlines are stripped by command substitution in both.

    THE MERGE IS `stderr=STDOUT`, NOT `stdout + stderr`, AND THE DIFFERENCE IS
    OBSERVABLE. `2>&1` points both descriptors at ONE pipe, so the bytes arrive in the order the child wrote them; concatenating two separately captured buffers puts all of stdout first regardless. A `gh` that writes a warning BEFORE its body then produces `warning\\nbody` under bash and `body\\nwarning` under the naive version -- and since the next thing that happens is a jq parse
    error, the two report different line numbers for the same failure. Caught by `test_quirk_1_is_reachable_from_a_gh_warning_beside_a_perfectly _good_body`.
    """
    try:
        proc = subprocess.run(
            ["gh", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # bash writes the diagnostic to the SHELL's stderr, so `2>&1` captures it into the body and `2>/dev/null` throws it away. Both arms, exactly.
        return 127, (not_found("gh", line).rstrip("\n") if merge_stderr else "")
    return proc.returncode, proc.stdout.rstrip("\n")


def force_cancel_run(repository: str, run_id: str, run_number: str) -> None:
    """`force_cancel_run` (twin :74-85). force-cancel, then cancel, then warn.

    STDOUT IS INHERITED, NOT CAPTURED. That is QUIRK 3 and it is the twin's behaviour, not an oversight in this port: `gh api -X POST` writes GitHub's response body to the script's stdout because only stderr is redirected.
    """
    for endpoint, message in (
        ("force-cancel", "Force-cancelled run #%s" % run_number),
        ("cancel", "Cancelled run #%s (force-cancel unavailable)" % run_number),
    ):
        try:
            code = subprocess.run(
                [
                    "gh",
                    "api",
                    "-X",
                    "POST",
                    "repos/%s/actions/runs/%s/%s" % (repository, run_id, endpoint),
                ],
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
        except FileNotFoundError:
            # `2>/dev/null` on both POSTs, so bash's message is discarded here and only the 127 survives -- which sends both arms to the warning.
            code = 127
        if code == 0:
            log.info(message)
            return
    log.warn("Failed to cancel run #%s" % run_number)


def sleep_like_bash(interval: str, line: int) -> None:
    """`sleep "$POLL_INTERVAL"`, the real binary.

    The twin passed a malformed interval straight here and died on coreutils' own two-line diagnostic; the port now refuses it up front (Rule T delta, see `main`), so only a whole number arrives. What the twin printed, driven:

        sleep: invalid time interval 'zz'
        Try 'sleep --help' for more information.
        rc=1
    """
    try:
        code = subprocess.run(["sleep", interval], check=False).returncode
    except FileNotFoundError:
        sys.stderr.write(not_found("sleep", line))
        sys.stderr.flush()
        code = 127
    if code != 0:
        raise SystemExit(code)


def main(argv: list[str]) -> int:
    try:
        parsed = common.parse_args(argv)
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code

    timeout = parsed.get("ARG_TIMEOUT", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT
    poll_interval = parsed.get("ARG_POLL_INTERVAL", DEFAULT_POLL_INTERVAL) or DEFAULT_POLL_INTERVAL
    workflow = parsed.get("ARG_WORKFLOW", DEFAULT_WORKFLOW) or DEFAULT_WORKFLOW

    # `${ARG_X:-default}` is an EMPTINESS test, so `--timeout=` falls back to 60
    # rather than to the empty string. That is why the `or DEFAULT_*` is there.

    if not _TIMEOUT.fullmatch(timeout):
        log.error(
            "%s: --timeout must be a whole number of seconds (got %r)" % (sys.argv[0], timeout)
        )
        return 2
    timeout_seconds = int(timeout)
    if not _TIMEOUT.fullmatch(poll_interval):
        log.error(
            "%s: --poll-interval must be a whole number of seconds (got %r)"
            % (sys.argv[0], poll_interval)
        )
        return 2

    if not os.environ.get("GITHUB_RUN_ID", ""):
        log.warn("GITHUB_RUN_ID not set - skipping (not running in GitHub Actions)")
        return 0
    if not os.environ.get("GITHUB_REPOSITORY", ""):
        log.error("GITHUB_REPOSITORY not set")
        return 1
    if not os.environ.get("GH_TOKEN", ""):
        log.error("GH_TOKEN not set")
        return 1

    current_run_id = os.environ.get("GITHUB_RUN_ID", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")

    log.step("Checking for older in-progress CI runs...")

    # The one read that decides whether anything is cancelled at all: a transient 5xx or connection fault is retried (5 s, 15 s) before the existing skip-with-warning, which still names the final failure. The polling reads below stay as they are (the loop is its own retry).
    rc, run_info = gh_retry.retry_transient(
        lambda: gh_capture(
            ["api", "repos/%s/actions/runs/%s" % (repository, current_run_id)],
            merge_stderr=True,
            line=RUN_LOOKUP_LINE,
        ),
        lambda r: None if r[0] == 0 else (r[1] or "failed"),
    )
    if rc != 0:
        log.warn("Failed to fetch current run info: %s" % run_info)
        return 0

    current_created = jq_or_die(".created_at // empty", run_info, args=("-r",), line=62)
    head_branch = jq_or_die(".head_branch // empty", run_info, args=("-r",), line=63)

    if not current_created or not head_branch:
        log.warn("Could not parse run info - skipping")
        return 0

    log.info(
        "Current run: #%s (branch: %s, created: %s)"
        % (current_run_id, head_branch, current_created)
    )

    start_time = int(time.time())

    while True:
        elapsed = int(time.time()) - start_time
        if elapsed >= timeout_seconds:
            log.warn(
                "Timeout reached (%ss) - some older runs may not have been cancelled" % timeout
            )
            return 0

        rc, runs_json = gh_capture(
            [
                "api",
                "repos/%s/actions/workflows/%s/runs?status=in_progress&branch=%s&per_page=10"
                % (repository, workflow, head_branch),
            ],
            merge_stderr=False,
            line=LISTING_LINE,
        )
        if rc != 0:
            log.warn("Failed to list workflow runs - retrying...")
            sleep_like_bash(poll_interval, line=100)
            continue

        older_runs = jq_or_die(
            JQ_OLDER_RUNS % (current_run_id, current_created), runs_json, args=("-c",), line=105
        )
        older_count = jq_or_die(JQ_LENGTH, older_runs, line=106)

        # `[[ "$OLDER_COUNT" -eq 0 ]]` is arithmetic, but `jq 'length'` on an array can only print a non-negative decimal integer, so the string comparison and the arithmetic one agree for every body reachable here.
        if older_count == "0":
            log.info("No older CI runs in progress - done")
            return 0

        log.info("Found %s older run(s) - force-cancelling..." % older_count)

        # `for row in $(echo "$OLDER_RUNS" | jq -c '.[]')` -- UNQUOTED, so bash word-splits on IFS. jq -c emits one space-free object per line and both fields are numbers, so splitting on whitespace and splitting on newlines agree for every body this filter can produce. Split on whitespace anyway, because that is what the twin does.
        rows = jq_or_die(JQ_ROWS, older_runs, args=("-c",), line=116).split()
        for row in rows:
            run_id = jq_or_die(".id", row, args=("-r",), line=117)
            run_number = jq_or_die(".run_number", row, args=("-r",), line=118)
            force_cancel_run(repository, run_id, run_number)

        sleep_like_bash(poll_interval, line=123)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
