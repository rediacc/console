#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/update-state.sh`.

Renders the autopilot state comment and writes it to the PR: the ONE place any job posts or patches it.

THE LEDGER IS NEVER OPTIONAL (03-v2-autonomy.md section 0). Autopilot commits are attributed to the operator, and this comment is the audit trail recording every round's run, commit and reasoning. It is also the loop's memory: the round counter that bounds the whole design is COUNTED FROM THIS COMMENT, so a round that runs without recording itself is a round the termination proof
cannot see.

ONE WRITER, THREE CALLERS, AND THAT IS WHY THE IDEMPOTENCY LIVES IN ONE `if`. `--comment-id` decides everything:

    absent   POST   repos/<repo>/issues/<pr>/comments        (create it)
    present  PATCH  repos/<repo>/issues/comments/<id>        (rewrite it)

The comment is REWRITTEN WHOLE rather than appended to, and the carry-over of the previous rounds is `state-comment.sh render`'s job, fed the old body through `--body`. So the second round on a PR is not "the first round plus a line" -- it is a fresh render of everything, and the only thing that makes it idempotent is that `--comment-id` and `--body` name the same comment.
`endpoint_for` below is that decision, exported so the differential can drive both arms without a PR.

WHAT THIS PORT DOES NOT RE-IMPLEMENT. `state-comment.sh` (the renderer) and `gh` are spawned, exactly as the twin spawns them. Re-implementing the renderer would create a second writer of a format whose whole design is one reader and one
writer; re-implementing `gh` is not a thing anyone can do.

WHERE jq IS SPAWNED, and the rule is this wave's: the `--verdict` file comes
from `autopilot-push.sh --verdict-out` and can be truncated, and when it is, the
observable is JQ's parse error and JQ's exit code (5, measured on 1.8.1) via `set -e`. Neither is reproducible by hand, so the two `jq -r` calls are run as
`jq`. `gsub("[\\r\\n]+"; " ")` is part of that program and is load-bearing: the
carry-over parser in `state-comment.sh` keeps only lines beginning with `- `, so a multi-line entry would lose its own continuation on the next round.

  DEFECT THE jq CALL CARRIES, PRESERVED: `gsub` refuses a non-string, so a
  verdict whose `ruled_out[]` holds a number dies with
  `jq: error ... number (1) cannot be matched, as it is not a string` and takes
  the state write with it -- the round then runs unrecorded, which is the one
  outcome the header says must not happen. The validator that produces the file
  bounds these arrays, so this is defence-in-depth failing closed rather than a
  live bug, and changing it means changing what the workflow writes. Named here,
  pinned by `test_a_non_string_ruled_out_entry_kills_the_write`.

THE SECOND HAZARD, ALSO PRESERVED: `--verdict` is checked with `[[ -n && -s ]]`, never with `require_file`. A MISPELLED PATH IS THEREFORE SILENT -- the ruled-out and decisions sections render empty and the round looks like it had nothing to say. That is the anti-thrash memory going quietly missing, and it is exactly the `decision.json` asymmetry `compose_prompt.py` documents in its
own twin. Fixing it means editing a live workflow step, which is the cutover box's call.

STAGE FLAG, DOUBLED ON PURPOSE. `AUTOPILOT_ALLOW_STATE` must be exactly `true`;
absent is off. The calling step's `if:` checks the same flag, and this check is the second half of that pair, so a mis-wired step cannot write state the stage forbids. Note the ORDER, kept: usage first, then the flag, so a broken invocation still gets the usage message rather than a confusing refusal.

`gh_retry` IS TRANSLITERATED, NOT IMPORTED, including its sleeps (3s then 6s). `.ci/rediacc_ci/quality/claude_attribution.py:122` and `.ci/rediacc_ci/quality/submodule_branches.py:271` already carry the same transliteration and say why: `ghx` has no `_gh_probe`-compatible entry point yet, and dropping the sleeps stops it being a retry past a rate limit.

Exit: 0 written, 1 refused or the write failed, 2 usage, and jq's or `state-comment.sh`'s own status when either fails.

K=5 LEDGER: `.ci/shadow/w7p6-update-state.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "update-state.py"

USAGE = (
    "usage: update-state.sh --pr <n> --repo <owner/name> [--comment-id <id>] "
    "--body <file> --state <s> --round <r> --rounds-max <n> --head <sha> "
    "--last-run <run> [--ledger <line>] [--verdict <file>] [--campaign <c>] "
    "[--model <id>] [--last-sig <s>] [--sig-count <n>]"
)

# `AUTOPILOT_ALLOW_STATE` must be exactly this. Absent is off, fail closed.
ALLOW_ENV = "AUTOPILOT_ALLOW_STATE"
ALLOW_VALUE = "true"

# The two jq programs, byte for byte from the twin.
RULED_OUT_PROGRAM = '(.ruled_out // [])[] | gsub("[\\r\\n]+"; " ")'
DECISIONS_PROGRAM = '(.decisions // [])[] | gsub("[\\r\\n]+"; " ")'

# `_gh_probe`: three attempts, sleeping 3 then 6 seconds.
GH_ATTEMPTS = 3


def script_dir() -> pathlib.Path:
    """The twin's `SCRIPT_DIR`: `.ci/scripts/autopilot`.

    From THIS file's location, matching `dirname "${BASH_SOURCE[0]}"`.
    `rediacc_ci.paths.repo_root()` is deliberately not used: it honours `$REDIACC_CI_ROOT` and the twin honours nothing.
    """
    return pathlib.Path(__file__).resolve().parents[3] / ".ci" / "scripts" / "autopilot"


def gh_retry(what: str, args: list[str]) -> tuple[bool, str]:
    """`gh_retry <what> -- <gh args...>`. Returns (ok, stdout).

    The exit status is ALWAYS checked and a failure is never turned into an empty answer, which is the whole reason `_gh_probe` exists (`.ci/scripts/lib/common.sh:392-397`). Trailing newlines are stripped because the twin captures this through `$( )`.
    """
    rc = 0
    stderr = ""
    stdout = ""
    for attempt in range(1, GH_ATTEMPTS + 1):
        try:
            proc = subprocess.run(["gh", *args], capture_output=True, check=False)
            rc = proc.returncode
            stdout = proc.stdout.decode("utf-8", "replace")
            stderr = proc.stderr.decode("utf-8", "replace")
        except OSError:
            # No `gh` on PATH: 127 is the shell's own status for it.
            rc, stdout, stderr = 127, "", ""
        if rc == 0:
            return True, re.sub(r"\n+$", "", stdout)
        if attempt < GH_ATTEMPTS:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/%d), retrying..."
                % (what, attempt, GH_ATTEMPTS)
            )
            time.sleep(attempt * 3)
    log.error("%s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc))
    if stderr != "":
        # `sed 's/^/ /' "$err" >&2`.
        for line in stderr.rstrip("\n").split("\n"):
            print("    %s" % line, file=sys.stderr)
        sys.stderr.flush()
    return False, ""


def endpoint_for(repo: str, pr: str, comment_id: str) -> tuple[str, str]:
    """(endpoint, method). The whole idempotency decision, in one place.

    An EMPTY `--comment-id` is "no comment yet" and means POST; any non-empty
    value means PATCH, including the literal `true` that `parse_args` stores for a value-less `--comment-id`. That last one is the twin's behaviour, not a tidy-up: the flag is passed by a workflow that either has an id or omits the flag, and a port that "fixed" it would refuse an invocation the twin accepts.
    """
    if comment_id:
        return "repos/%s/issues/comments/%s" % (repo, comment_id), "PATCH"
    return "repos/%s/issues/%s/comments" % (repo, pr), "POST"


def render_args(args: dict[str, str], work: str) -> list[str]:
    """The `state-comment.sh render` argv, in the twin's order.

    The optional flags are appended only when NON-EMPTY, which is the twin's
    `[[ -n ... ]] && args+=(...)`. An omitted `--campaign` is not the same as
    `--campaign ""`: the renderer carries the previous body's value forward when the flag is absent, and would normalize an empty one to `none`. So a port that always passed the flag would silently CLOSE a campaign on any round that had nothing to say about it.
    """
    argv = [
        "render",
        "--body",
        args.get("ARG_BODY", "") or "/dev/null",
        "--state",
        args.get("ARG_STATE", ""),
        "--round",
        "%s/%s" % (args.get("ARG_ROUND", ""), args.get("ARG_ROUNDS_MAX", "") or "0"),
        "--head",
        args.get("ARG_HEAD", ""),
        "--last-run",
        args.get("ARG_LAST_RUN", ""),
        "--ruled-out-file",
        os.path.join(work, "ruled-out.txt"),
        "--decisions-file",
        os.path.join(work, "decisions.txt"),
    ]
    for flag, key in (
        ("--ledger", "ARG_LEDGER"),
        ("--campaign", "ARG_CAMPAIGN"),
        ("--model", "ARG_MODEL"),
        ("--rounds-max", "ARG_ROUNDS_MAX"),
        ("--last-sig", "ARG_LAST_SIG"),
        ("--sig-count", "ARG_SIG_COUNT"),
    ):
        value = args.get(key, "")
        if value:
            argv += [flag, value]
    return argv


def jq_to_file(program: str, source: str, target: str) -> int:
    """`jq -r '<program>' "$VERDICT" >"$target"`. Returns jq's exit code.

    The target is written with whatever jq produced BEFORE it failed, because that is what a shell redirection does: the file is open and being written as jq runs. A port that buffered and discarded on failure would leave a different file behind for the renderer to read.

    STDERR IS INHERITED so jq's own diagnostic lands on fd 2 in real time, which is what the twin's unredirected jq does.
    """
    with open(target, "wb") as handle:
        proc = subprocess.run(
            ["jq", "-r", program, source],
            stdout=handle,
            check=False,
        )
    return proc.returncode


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    pr = args.get("ARG_PR", "")
    repo = args.get("ARG_REPO", "")
    comment_id = args.get("ARG_COMMENT_ID", "")
    verdict = args.get("ARG_VERDICT", "")

    required = (
        pr,
        repo,
        args.get("ARG_STATE", ""),
        args.get("ARG_ROUND", ""),
        args.get("ARG_HEAD", ""),
        args.get("ARG_LAST_RUN", ""),
    )
    if not all(required):
        log.error(USAGE)
        return 2
    if os.environ.get(ALLOW_ENV, "") != ALLOW_VALUE:
        log.error(
            "stage-flag-disabled: %s is not '%s'; refusing the state write (fail closed)"
            % (ALLOW_ENV, ALLOW_VALUE)
        )
        return 1

    work = tempfile.mkdtemp()
    try:
        return _write(args, pr, repo, comment_id, verdict, work)
    finally:
        # `trap 'rm -rf "$work"' EXIT`.
        shutil.rmtree(work, ignore_errors=True)


def _write(
    args: dict[str, str], pr: str, repo: str, comment_id: str, verdict: str, work: str
) -> int:
    ruled_out = os.path.join(work, "ruled-out.txt")
    decisions = os.path.join(work, "decisions.txt")
    # `: >"$work/ruled-out.txt"`: both files exist and are EMPTY before jq runs, so the renderer's `--*-file` inputs are always present.
    for path in (ruled_out, decisions):
        with open(path, "wb"):
            pass

    # THE HAZARD: `-n && -s`, never `require_file`. A mistyped path is silence.
    if verdict and os.path.isfile(verdict) and os.path.getsize(verdict) > 0:
        for program, target in (
            (RULED_OUT_PROGRAM, ruled_out),
            (DECISIONS_PROGRAM, decisions),
        ):
            code = jq_to_file(program, verdict, target)
            if code != 0:
                return code

    body_md = os.path.join(work, "body.md")
    with open(body_md, "wb") as handle:
        render = subprocess.run(
            [str(script_dir() / "state-comment.sh"), *render_args(args, work)],
            stdout=handle,
            check=False,
        )
    if render.returncode != 0:
        # `set -e` on the renderer's status. The half-written body.md goes with the work directory, exactly as the twin's EXIT trap takes it.
        return render.returncode

    if args.get("ARG_DRY_RUN", "false") == "true":
        # `cat "$work/body.md"` -- BYTES, because the body carries model-authored text that need not be valid UTF-8.
        with open(body_md, "rb") as handle:
            sys.stdout.buffer.write(handle.read())
        sys.stdout.flush()
        log.info(
            "dry-run: would write the state comment for PR #%s (comment id '%s')"
            % (pr, comment_id or "none")
        )
        return 0

    endpoint, method = endpoint_for(repo, pr, comment_id)
    # `-F body=@file`: the rendered body carries model-authored text and never
    # becomes shell or an argv value that a length limit could truncate.
    ok, _ = gh_retry(
        "state-comment %s" % method,
        ["api", "--method", method, endpoint, "-F", "body=@%s" % body_md],
    )
    if not ok:
        # `set -e` on gh_retry's non-zero status: the success line below is never reached, and the round is recorded nowhere.
        return 1
    log.info(
        "state comment %s to %s (round %s/%s, state %s)"
        % (
            method,
            endpoint,
            args.get("ARG_ROUND", ""),
            args.get("ARG_ROUNDS_MAX", "") or "0",
            args.get("ARG_STATE", ""),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
