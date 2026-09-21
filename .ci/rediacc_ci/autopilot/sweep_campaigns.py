#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/sweep-campaigns.sh`.

Finds the open PRs whose autopilot CAMPAIGN is still open, so the 2-hourly sweeper can re-dispatch them. PR list and comment dumps in, PR numbers out, one per line, ascending.

THE TRUST RULE IS THE PRODUCT, and it is why this is testable offline. A campaign is believed only when `state-comment.sh select` accepts the comment: its author must equal the autopilot bot AND its body must start with the exact header. Console is public, so a lookalike comment claiming `campaign: open` is the obvious way to make the sweeper dispatch rounds against a PR nobody
armed. The port does not re-implement that check -- it CALLS the same state-comment reader, twice per PR (`select`, then `fields`), exactly as the twin did, so there is still one reader and one writer of that format.

WHY THE SIBLING STAYS A SUBPROCESS. Re-implementing its `select`/`fields` here would create a SECOND parser of the state comment, which is the specific thing the format's own design forbids: the arming gate reads the metadata line through this reader rather than re-parsing it. The port therefore resolves it the way the twin's `SCRIPT_DIR` did, relative to its own file, and
spawns it.

"COULD NOT LOOK" IS NOT "NOT ARMED". A PR with no comment dump is skipped with a warning and does NOT count as scanned; the summary reports the scanned count separately for exactly that reason. Preserved verbatim, including the fact that a sweep over an empty PR list prints `0 open campaign(s) across 0 scanned PR(s)` and exits 0. That is the twin's documented "an empty sweep is a
normal, quiet result", so the port keeps it -- but a reader should know that this line is also what a completely broken input produces, and it is the summary, not the exit code, that tells the two apart.

WHERE jq IS SPAWNED AND WHERE IT IS NOT, which is a rule this wave applies to all four ports:

  SPAWNED   over the `--prs` file, because that file comes from outside and its
            PARSE ERROR is the observable. jq's own text ("jq: parse error:
            Invalid numeric literal at EOF at line 1, column 4") and its exit
            code (5, measured on jq 1.8.1) are what a workflow log shows today,
            and no hand-written message reproduces them.
  NOT       over `state-comment.sh`'s output, which this script produced itself
            one line earlier. Parsing a child's own JSON in Python costs no
            fidelity, and spawning jq three more times per PR to read three
            fields would be a port that got slower than its twin.

`sort -n` IS REPRODUCED, NOT DELEGATED, and the tie-break is the part worth naming: GNU `sort -n` without `-s` falls back to a whole-line byte comparison
for equal keys, so the port sorts on `(numeric, line)` rather than on the number
alone. A duplicate PR number in the input is therefore scanned twice by both implementations, in the same order.

Exit: 0 (an empty sweep is normal), 2 usage, 1 a missing --prs/--comments-dir, and whatever `jq` or `state-comment.sh` exited with when either failed -- under the twin's `set -euo pipefail` those statuses propagate, and so do they here.

K=5 LEDGER: `.ci/shadow/w7p6-sweep-campaigns.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "sweep-campaigns.py"

USAGE = "usage: sweep-campaigns.sh --prs <file> --comments-dir <dir> --bot <login>"

# The twin's `jq -r '...' "$PRS"` program, byte for byte. Kept as one string so a reader can diff it against the twin without reassembling it.
PRS_PROGRAM = """(if type == "array" then . else [] end)
    | map(if type == "object" then .number else . end)
    | map(select(type == "number"))
    | .[]"""


def script_dir() -> pathlib.Path:
    """The twin's `SCRIPT_DIR`: `.ci/scripts/autopilot`.

    Derived from THIS file's location (`.ci/rediacc_ci/autopilot/x.py`, so three parents up is the repository root), matching the twin's own
    `dirname "${BASH_SOURCE[0]}"`. `rediacc_ci.paths.repo_root()` is deliberately
    not used: it honours `$REDIACC_CI_ROOT`, the twin honours nothing, and a fixture that moved one and not the other would diverge for a reason that has nothing to do with this script.
    """
    return pathlib.Path(__file__).resolve().parents[3] / ".ci" / "scripts" / "autopilot"


def state_comment_argv() -> list[str]:
    """The state-comment reader, in the command form its own K=5 ledger licensed.

    ITS BASH TWIN IS GONE (`.ci/shadow/w7p6-state-comment.observations.jsonl` recorded the port against it five times over, and W7P5 batch M3 deleted it), so the spawn names the port by PATH, which is the exact spelling that ledger carries. `-m` is deliberately not used: `check:ci-parity`'s tokenizer cannot read it, and a second spelling of one call is how the two drift apart.

    The sibling is still SPAWNED rather than imported, for the reason this module's header gives: one reader and one writer of the state-comment format, and a child whose failure status propagates exactly as the twin's did.
    """
    return [sys.executable, str(port_dir() / "state_comment.py")]


def port_dir() -> pathlib.Path:
    """`.ci/rediacc_ci/autopilot`, from THIS file's own location."""
    return pathlib.Path(__file__).resolve().parent


def child_env() -> dict[str, str]:
    """This process's environment with `rediacc_ci` importable by the child.

    The parent is reached through `PYTHONPATH=.ci` with the checkout as the working directory, and a child started from anywhere else would not inherit a usable one, so the absolute path is computed here rather than trusted.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pathlib.Path(__file__).resolve().parents[2])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def jq_r(program: str, path: str) -> tuple[int, str]:
    """`jq -r '<program>' <path>`. (exit, stdout).

    STDERR IS INHERITED, NOT CAPTURED, which is what the twin's unredirected jq does: its parse error lands on this process's fd 2 in real time, in the right order relative to anything already flushed there. Capturing and re-emitting would work only as long as every log call flushes, and would put the test in charge of an ordering the subject should own.
    """
    proc = subprocess.run(
        ["jq", "-r", program, path],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def sort_numeric(lines: list[str]) -> list[str]:
    """`LC_ALL=C sort -n`, including GNU sort's last-resort byte comparison.

    A line jq could not have produced (it only emits numbers here) sorts as 0, which is what `sort -n` does with an unparseable key.
    """

    def key(line: str) -> tuple[float, str]:
        try:
            return (float(line), line)
        except ValueError:
            return (0.0, line)

    return sorted(lines, key=key)


def pr_numbers(prs_path: str) -> tuple[int, list[str]]:
    """The `jq | sort -n` pipeline. (exit, numbers).

    Under `set -o pipefail` the pipeline carries jq's status, because `sort` always exits 0. A non-zero status here takes the twin down with `set -e`, so the caller propagates rather than continuing with an empty list -- an unreadable PR list is not an empty one.
    """
    code, out = jq_r(PRS_PROGRAM, prs_path)
    if code != 0:
        return code, []
    # `for n in $numbers` splits on IFS whitespace and drops empty fields.
    return 0, sort_numeric(out.split())


def raw_field(payload: str, field: str) -> str:
    """`jq -r '.<field>' <<<"$payload"`, for JSON this script's own child wrote.

    EMPTY INPUT IS NOT AN ERROR: `jq -r '.found' <<<""` prints nothing and exits 0, so a child that printed nothing yields the empty string here rather than
    an exception. That path is what makes `!= "true"` skip the PR instead of
    crashing the sweep.
    """
    text = payload.strip()
    if text == "":
        return ""
    return jq_raw(json.loads(text).get(field))


def jq_raw(value: Any) -> str:
    """`jq -r`'s rendering of one value: strings bare, everything else JSON."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def run_state_comment(args: list[str]) -> subprocess.CompletedProcess[str]:
    """`"$SCRIPT_DIR/state-comment.sh" <args>`, with stderr INHERITED.

    Only stdout is captured, because only stdout is what the twin captures with `$( )`. The child's diagnostics go to this process's fd 2 untouched.
    """
    return subprocess.run(
        [*state_comment_argv(), *args],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
        env=child_env(),
    )


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    prs = args.get("ARG_PRS", "")
    comments_dir = args.get("ARG_COMMENTS_DIR", "")
    bot = args.get("ARG_BOT", "")

    if not (prs and comments_dir and bot):
        log.error(USAGE)
        return 2
    try:
        common.require_file(prs)
        common.require_dir(comments_dir)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    # `work="$(mktemp -d)"` plus `trap 'rm -rf "$work"' EXIT`, in the twin's
    # order: created before the scan, removed however the scan ends.
    work = tempfile.mkdtemp()
    try:
        return _sweep(prs, comments_dir, bot, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _sweep(prs: str, comments_dir: str, bot: str, work: str) -> int:
    """The scan itself. Split out so the work directory has one owner and one cleanup path, which is what the twin's EXIT trap gives it."""
    code, numbers = pr_numbers(prs)
    if code != 0:
        return code

    found = 0
    scanned = 0
    for number in numbers:
        dump = os.path.join(comments_dir, "%s.json" % number)
        if not os.path.isfile(dump):
            log.warn(
                "sweep-campaigns: no comment dump for PR #%s at %s; skipping "
                "(an unreadable PR is not a closed campaign)" % (number, dump)
            )
            continue
        scanned += 1

        select = run_state_comment(["select", "--comments", dump, "--bot", bot])
        if select.returncode != 0:
            # `sel="$(state-comment.sh select ...)"` under `set -e`: the whole
            # sweep stops, with the child's status. A PR whose dump cannot be read is not a PR without a campaign.
            return select.returncode
        sel = select.stdout.rstrip("\n")
        if raw_field(sel, "found") != "true":
            continue

        # `jq -r '.body // ""' <<<"$sel" >"$work/body.txt"`: the body plus a newline, in a file, because `state-comment.sh fields` takes a path.
        body = raw_field(sel, "body")
        body_file = os.path.join(work, "body.txt")
        with open(body_file, "w", encoding="utf-8") as handle:
            handle.write(body + "\n")

        fields = run_state_comment(["fields", "--body", body_file])
        if fields.returncode != 0:
            # pipefail: `state-comment.sh fields | jq` carries the LEFT side's status when jq succeeds on its truncated input.
            return fields.returncode
        if raw_field(fields.stdout, "campaign") == "open":
            print(number, flush=True)
            found += 1

    log.info("sweep-campaigns: %d open campaign(s) across %d scanned PR(s)" % (found, scanned))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
