#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/check-rerun-attempt.sh` (48 lines).

The dumb, deterministic backstop under the AI-driven watchdog: read the run's current attempt and refuse to rerun at or past the cap. The twin's header owns why the exported name is `WATCHDOG_SKIP_RERUN` (it is the CONSUMER's spelling, read by `watchdog-monitor.cjs`), and that is not restated here.

LIVE CALLER, not repointed. The bash twin stays the registered gate; this module
is its verified-equivalent alternative, and the cutover is a separate, later, driver-only step.

Ledger: `.ci/shadow/w7p6-check-rerun-attempt.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-check-rerun-attempt --assert --k 5`).

-----------------------------------------------------------------------------
DEFECT A -- THE TWIN EXITS 1 ON ITS OWN HAPPY PATH WHEN `GITHUB_ENV` IS UNSET
-----------------------------------------------------------------------------
Its last line is

    [[ -n "${GITHUB_ENV:-}" ]] && echo "WATCHDOG_SKIP_RERUN=${SKIP}" >>"$GITHUB_ENV"

`GITHUB_ENV` is documented in the twin's own header as OPTIONAL. When it is unset the `[[ -n ]]` is false, the `&&` list therefore has status 1, and it is the LAST command in the script, so the SCRIPT's status is 1. `set -e` is not what does this -- a test on the left of `&&` is exempt -- the script simply ends on a false command. Driven 2026-09-14 with a fake `gh` returning
attempt 1:

    $ RUN_ID=5 GH_REPO=a/b bash .ci/scripts/ci/check-rerun-attempt.sh
    ::group::Fetching run details
    (info) Run ID: 5
    (info) Current run attempt: 1
    ::endgroup::
    (info) Run attempt 1 < max 2 - rerun is allowed
    rc=1

    $ RUN_ID=5 GH_REPO=a/b GITHUB_ENV=/tmp/e bash .ci/scripts/ci/check-rerun-attempt.sh
    ... same five lines ...
    rc=0

So the script reports "rerun is allowed" and then fails, and the only thing separating the two is whether the caller happened to set an OPTIONAL variable.
In the workflow `GITHUB_ENV` is always set, which is why nothing has noticed;
anybody running it by hand, or from a composite action that clears the environment, gets a failure with no failing message. REPRODUCED verbatim, not repaired: `.ci/scripts/ci/` is not this writer's to change.

-----------------------------------------------------------------------------
DEFECT B -- AN UNPARSEABLE ATTEMPT FAILS OPEN, WHICH IS THE WRONG DIRECTION
-----------------------------------------------------------------------------
`ATTEMPT="$(gh api ... --jq '.run_attempt')"` is never checked for shape, and
`[[ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]]` is bash arithmetic. An EMPTY attempt -- which is what an empty body, or a `--jq` filter that selected nothing, yields -- evaluates as 0:

    $ FAKE_ATTEMPT= RUN_ID=5 GH_REPO=a/b GITHUB_ENV=/tmp/e \\
        bash .ci/scripts/ci/check-rerun-attempt.sh
    (info) Run attempt  < max 2 - rerun is allowed
    rc=0 ; /tmp/e contains WATCHDOG_SKIP_RERUN=false

The whole point of the file is to be a cap that cannot be talked out of, and the "I could not read the attempt" case is folded into "the cap is not reached". The neighbouring shape fails CLOSED for an unrelated reason: `.run_attempt` missing
from the JSON makes `jq -r` print the four letters `null`, which bash arithmetic
reads as a VARIABLE NAME, and `set -u` then kills the script at the twin's line 40 with `null: unbound variable`, exit 1. Two malformed inputs, two opposite answers, neither of them a sentence anybody can act on. Both reproduced.

-----------------------------------------------------------------------------
WHY THE BASH DIAGNOSTICS ARE REPRODUCED CHARACTER BY CHARACTER
-----------------------------------------------------------------------------
Three of this script's five exits are bash's own messages rather than the
script's: `${RUN_ID:?...}`, `${GH_REPO:?...}` and the `null` arithmetic above.
They carry `<program>: line <N>:`, so the port carries the twin's line numbers as named constants and `test_the_pinned_line_numbers_still_point_at_the_twins _lines` re-derives all three from the twin on every run. The program NAME
necessarily differs (`.sh` there, the module path here); the differential
normalises exactly that one token and compares the rest byte-for-byte.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `MAX_ATTEMPTS="${MAX_ATTEMPTS:-2}"` (twin :32).
DEFAULT_MAX_ATTEMPTS = "2"

# The consumer's spelling, from the twin's header. One name, spelled once.
SKIP_VAR = "WATCHDOG_SKIP_RERUN"

# Twin line numbers that bash prints inside its own diagnostics. Pinned rather than guessed, and re-derived from the twin by the differential.
RUN_ID_LINE = 29
GH_REPO_LINE = 30
ARITH_LINE = 40

# `[A-Za-z_][A-Za-z0-9_]*`: what bash treats as a variable NAME in an arithmetic context. Not `str.isidentifier()`, which accepts Unicode letters bash rejects.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DECIMAL = re.compile(r"^[+-]?[0-9]+$")


class BashArithError(Exception):
    """A fatal `set -u` arithmetic diagnostic, with the message bash prints."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def bash_ge(left_word: str, right_word: str) -> bool:
    """`[[ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]]`, with bash's arithmetic rules.

    Empty is 0 (DEFECT B's fail-open arm). A decimal is itself. A bare identifier is an unset variable and therefore fatal under `set -u` (DEFECT B's fail-closed arm, which is how `null` behaves). Anything else -- `1abc`, `0x10` -- is an arithmetic syntax error in the twin, `[[ ]]` answers
    false, and the script continues; that arm is not reachable from `gh --jq`
    output and is deliberately mapped onto the same false answer rather than given a second synthetic message.
    """
    values = []
    for word in (left_word.strip(), right_word.strip()):
        if word == "":
            values.append(0)
        elif _DECIMAL.match(word):
            values.append(int(word, 10))
        elif _IDENT.match(word):
            raise BashArithError(
                "%s: line %d: %s: unbound variable" % (sys.argv[0], ARITH_LINE, word)
            )
        else:
            return False
    return values[0] >= values[1]


def require_env(name: str, message: str, line: int) -> str:
    """`: "${NAME:?message}"`, including bash's own diagnostic and exit 1.

    The test is EMPTINESS, not presence: `NAME=` refuses exactly as an unset one
    does. bash writes `<program>: line <N>: NAME: message` and exits 1.
    """
    value = os.environ.get(name, "")
    if not value:
        sys.stderr.write("%s: line %d: %s: %s\n" % (sys.argv[0], line, name, message))
        sys.stderr.flush()
        raise SystemExit(1)
    return value


def gh_run_attempt(repo: str, run_id: str) -> str:
    """`gh api "repos/<repo>/actions/runs/<id>" --jq '.run_attempt'`.

    STDERR IS NOT REDIRECTED by the twin, so it is inherited here. A non-zero status is fatal under `set -e`, and -- this is the observable part -- `::endgroup::` is therefore NEVER printed on that path, leaving the GitHub log with an unclosed group. Reproduced by raising before the print.
    """
    proc = subprocess.run(
        ["gh", "api", "repos/%s/actions/runs/%s" % (repo, run_id), "--jq", ".run_attempt"],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    # Command substitution strips trailing newlines.
    return proc.stdout.rstrip("\n")


def main(argv: list[str]) -> int:
    del argv  # The twin reads no arguments; everything arrives through the env.

    try:
        common.require_cmd("gh")
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code

    run_id = require_env("RUN_ID", "RUN_ID is required", RUN_ID_LINE)
    gh_repo = require_env("GH_REPO", "GH_REPO is required", GH_REPO_LINE)

    max_attempts = os.environ.get("MAX_ATTEMPTS", "") or DEFAULT_MAX_ATTEMPTS

    print("::group::Fetching run details", flush=True)
    log.info("Run ID: %s" % run_id)
    attempt = gh_run_attempt(gh_repo, run_id)
    log.info("Current run attempt: %s" % attempt)
    print("::endgroup::", flush=True)

    try:
        at_cap = bash_ge(attempt, max_attempts)
    except BashArithError as err:
        sys.stderr.write(err.message + "\n")
        sys.stderr.flush()
        return 1

    if at_cap:
        log.warn(
            "Run attempt %s >= max %s - skipping rerun (defense-in-depth)" % (attempt, max_attempts)
        )
        skip = "true"
    else:
        log.info("Run attempt %s < max %s - rerun is allowed" % (attempt, max_attempts))
        skip = "false"

    github_env = os.environ.get("GITHUB_ENV", "")
    if not github_env:
        # DEFECT A. The `&&` list is false and it is the last command, so the twin's exit status is 1 here. Not a bug this port gets to fix.
        return 1
    with open(github_env, "a", encoding="utf-8") as fh:
        fh.write("%s=%s\n" % (SKIP_VAR, skip))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
