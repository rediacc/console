"""Port of `.ci/scripts/autopilot/finish.sh`.

The deterministic finish line: everything past "CI is green" that needs no model invocation (03-v2-autonomy.md sections 2 and 9 -- ready-flip, review-gate rerun and done-detection are all zero-model-cost paths). Three subcommands, each with its own exit vocabulary:

    check-done    PURE. A fixture in, `{"done":bool,"missing":[...]}` out on
                  STDOUT, exit 0 done / 1 not done / 1 no fixture / 2 usage.
    ready-flip    WRITE. Flips the draft PR ready with the post-model app
                  token, which fires `ready_for_review` and chains the review
                  pipeline.
    rerun-review  WRITE. Reruns the review pipeline's failed run for the PR
                  head. Bounded by the review cap, which the review pipeline
                  enforces; this script never loops.

FAIL CLOSED IS THE FIRST THING BOTH WRITES DO. `AUTOPILOT_ALLOW_PUSH` absent is OFF, and the refusal (`stage-flag-disabled`) happens BEFORE any `gh` call, so a misconfigured stage cannot even read. The order is preserved exactly: usage check, then the flag, then the network.

-----------------------------------------------------------------------------
`jq` IS STILL `jq`, ALL THREE TIMES, AND THAT IS THE POINT OF THIS PORT
-----------------------------------------------------------------------------
`check-done`'s verdict is printed to STDOUT and read by the caller, so its bytes are the interface: `jq -c`'s compact spacing, its key order (`done` then `missing`, in program order, not sorted) and its trailing newline. The program itself is also a piece of REASONING that a rewrite would quietly change, and the twin says so in a comment this port keeps in one piece:

    NOT `.draft // true | not`: jq treats false as empty for `//`, which would
    read a non-draft PR as a draft. A missing draft field still fails closed
    (not done).

So `DONE_PROGRAM` below is the twin's program, character for character, handed to the same `jq`. A `json`-based reimplementation would have to re-derive
`//`'s falsy rule, `has()` versus `==`, and the `to_entries` ordering, and the
first one it got wrong would flip a PR to done.

-----------------------------------------------------------------------------
WHAT `MISSING` MEANS, AND WHY THE ORDER MATTERS
-----------------------------------------------------------------------------
`missing` names every unmet condition so a stalled babysit is diagnosable from the decision line alone. It comes out of `to_entries` over the intermediate object, so it is always a subset of, and in the order of, `[ci_green, not_draft, reviewed, threads_resolved]`. That is a contract with whoever reads the line, and it is asserted in the differential rather than left to jq.

-----------------------------------------------------------------------------
`_gh_probe` IS COPIED IN, NOT IMPORTED, for the reason `quality/submodule_branches.py:128-137` already records: `core.ghx` classifies failures, raises typed errors and does NOT retry three times with a `log_warn` between attempts, so a port built on it would produce different output on the paths a differential cannot reach. The twin sources `common.sh`, which this port does not, so
the 3-attempt loop, the `sleep $((attempt * 3))` backoff, the JSON validation and both message strings are transliterated here. When `ghx` grows a `_gh_probe`-compatible entry point, this copy is the first thing that should go.

`jq -e` IS NOT `json.loads`: it exits 1 when the last output value is `null` or `false`, so a `gh` call that exits 0 with the body `null` is UNUSABLE and gets retried. `_json_usable` implements jq's rule.

-----------------------------------------------------------------------------
THE PIPELINES IN `rerun-review` ARE `pipefail` PIPELINES, and their exit codes are not this script's inventions. `gh_json ... | jq -r '.sha'` fails with 1 when the probe gives up (jq is perfectly happy with empty input) and with JQ's code, 5, when the body cannot be indexed. `set -e` then ends the run with that
number and no message of this script's own. Both are reproduced; neither is
smoothed into a friendly refusal, because a workflow step that branches on 5 versus 1 today would stop working.

-----------------------------------------------------------------------------
ONE HAZARD, REPORTED RATHER THAN REPAIRED. `check-done`'s fixture is read with `require_file`, but the two write paths take `--pr` as a NUMBER and never validate it: `finish.sh ready-flip --pr 'x y' --repo r/c` reaches `gh` as a single argument `x y`, which `gh` refuses with its own message after the stage flag has already been checked. That is a bad-input path with a confusing
diagnostic, not a security hole (nothing is interpolated into a shell), and fixing it means changing a live workflow step's contract, which is the cutover box's call rather than this one's.

K=5 LEDGER: `.ci/shadow/w7p6-finish.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "finish.py"

USAGE_CHECK_DONE = "usage: finish.sh check-done --pr <fixture.json>"
USAGE_READY_FLIP = "usage: finish.sh ready-flip --pr <number> --repo <owner/name>"
USAGE_RERUN_REVIEW = "usage: finish.sh rerun-review --pr <number> --repo <owner/name>"
UNKNOWN_SUBCOMMAND = "unknown subcommand '%s' (check-done|ready-flip|rerun-review)"

# The write gate. Absent is OFF; only the exact string `true` opens it.
ALLOW_PUSH_ENV = "AUTOPILOT_ALLOW_PUSH"
ALLOW_PUSH_VALUE = "true"
STAGE_FLAG_DISABLED = (
    "stage-flag-disabled: %s is not 'true'; refusing the write (fail closed)" % ALLOW_PUSH_ENV
)

# `_gh_probe`'s loop shape (common.sh:434-473).
GH_ATTEMPTS = 3
GH_BACKOFF_SECONDS = 3

# THE TWIN'S jq PROGRAM, VERBATIM, comment and all. See the module docstring for why it is not reimplemented. Changing a character here changes when a PR is declared done.
DONE_PROGRAM = """
            {
                ci_green: (.ci_green // false),
                # NOT `.draft // true | not`: jq treats false as empty for
                # `//`, which would read a non-draft PR as a draft. A missing
                # draft field still fails closed (not done).
                not_draft: (has("draft") and (.draft == false)),
                reviewed: (.reviewed // false),
                threads_resolved: ((.unresolved_threads // 1) == 0)
            }
            | {
                done: (.ci_green and .not_draft and .reviewed and .threads_resolved),
                missing: [to_entries[] | select(.value | not) | .key]
            }
        """

# `gh api ... --jq` filters, which run inside `gh`, and the `jq -r` that reads
# what `gh` printed. Two different jq invocations; the twin's spelling of each.
HEAD_SHA_FILTER = "{sha: .head.sha}"
RUN_ID_FILTER = '{id: ([.workflow_runs[] | select(.name | test("[Rr]eview"))] | first | .id)}'


def _json_usable(body: bytes) -> bool:
    """`[[ -n "$out" ]] && jq -e . <<<"$out"`: parses, and is not null/false."""
    if not body:
        return False
    try:
        value = json.loads(body)
    except ValueError:
        return False
    return value is not None and value is not False


def gh_probe(
    require_json: bool, what: str, args: list[str], *, sleeper=time.sleep
) -> tuple[bool, bytes]:
    """`common.sh`'s `_gh_probe`, transliterated. (ok, stdout bytes).

    Three attempts, a `log_warn` between them, a 3-then-6-second backoff, and the captured stderr replayed indented four spaces on final failure -- including GNU sed's refusal to invent a final newline the input did not have.
    """
    rc = 0
    err = b""
    out = b""
    attempt = 1
    while attempt <= GH_ATTEMPTS:
        try:
            proc = subprocess.run(
                ["gh", *args],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            rc, out, err = 127, b"", b"gh: command not found\n"
        else:
            rc = proc.returncode
            # `$(...)` strips trailing newlines; `printf '%s'` adds none back.
            out = (proc.stdout or b"").rstrip(b"\n")
            err = proc.stderr or b""
        if rc == 0 and (not require_json or _json_usable(out)):
            return True, out
        if attempt < GH_ATTEMPTS:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/3), retrying..."
                % (what, attempt)
            )
            sleeper(attempt * GH_BACKOFF_SECONDS)
        attempt += 1
    log.error("%s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc))
    if err:
        text = err.decode("utf-8", "replace")
        parts = text.split("\n")
        incomplete = parts[-1] != ""
        if not incomplete:
            parts.pop()
        for index, line in enumerate(parts):
            tail = "" if incomplete and index == len(parts) - 1 else "\n"
            print("    %s" % line, end=tail, file=sys.stderr)
        sys.stderr.flush()
    return False, b""


def _jq(args: list[str], stdin: bytes | None = None) -> tuple[int, bytes]:
    """Run jq with stderr INHERITED, the way an unredirected jq behaves.

    stdout is captured because every jq here feeds a shell variable.
    """
    proc = subprocess.run(
        ["jq", *args],
        input=stdin if stdin is not None else b"",
        stdout=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, proc.stdout or b""


def check_done(fixture: str) -> tuple[int, bytes]:
    """`check-done`. Returns (exit code, the verdict line to print).

    The verdict is printed by the caller BEFORE the exit code is decided, because the twin prints it before testing `.done` and a stalled babysit is diagnosed from that line.
    """
    rc, verdict = _jq(["-c", DONE_PROGRAM, fixture])
    if rc != 0:
        # `verdict="$(jq ...)"` under `set -e`: jq's own status, jq's own
        # message already on stderr, and nothing printed to stdout.
        return rc, b""
    # `printf '%s\\n' "$verdict"`: the substitution stripped jq's newline and printf puts exactly one back, so a multi-document fixture prints its
    # verdicts on their own lines and then fails the `== "true"` test.
    line = verdict.rstrip(b"\n") + b"\n"
    rc, done = _jq(["-r", ".done"], stdin=verdict.rstrip(b"\n") + b"\n")
    if rc != 0:
        return rc, line
    return (0 if done.rstrip(b"\n") == b"true" else 1), line


def require_write_flag(env: dict[str, str] | None = None) -> bool:
    """`[[ "${AUTOPILOT_ALLOW_PUSH:-}" != "true" ]]`. True means proceed."""
    environ = os.environ if env is None else env
    if environ.get(ALLOW_PUSH_ENV, "") != ALLOW_PUSH_VALUE:
        log.error(STAGE_FLAG_DISABLED)
        return False
    return True


def main(argv: list[str], *, sleeper=time.sleep) -> int:
    # `cmd="${1:-}"; shift || true`: the first argument is the subcommand and
    # is NOT a flag, so it never reaches parse_args. With no arguments at all the subcommand is the empty string, which lands in the unknown arm.
    cmd = argv[0] if argv else ""
    rest = argv[1:]
    try:
        args = common.parse_args(rest)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    pr = args.get("ARG_PR", "")
    repo = args.get("ARG_REPO", "")

    if cmd == "check-done":
        if not pr:
            log.error(USAGE_CHECK_DONE)
            return 2
        try:
            common.require_file(pr)
        except common.RefusalError as exc:
            exc.report()
            return exc.code
        code, line = check_done(pr)
        if line:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
        return code

    if cmd == "ready-flip":
        if not (pr and repo):
            log.error(USAGE_READY_FLIP)
            return 2
        if not require_write_flag():
            return 1
        ok, body = gh_probe(
            False, "ready-flip", ["pr", "ready", pr, "--repo", repo], sleeper=sleeper
        )
        if not ok:
            return 1
        # `gh_retry`'s `printf '%s'`: gh's stdout, with no newline added.
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()
        log.info("PR #%s flipped ready for review" % pr)
        return 0

    if cmd == "rerun-review":
        if not (pr and repo):
            log.error(USAGE_RERUN_REVIEW)
            return 2
        if not require_write_flag():
            return 1

        ok, body = gh_probe(
            True,
            "rerun-review head",
            ["api", "repos/%s/pulls/%s" % (repo, pr), "--jq", HEAD_SHA_FILTER],
            sleeper=sleeper,
        )
        rc, head_sha = _jq(["-r", ".sha"], stdin=body)
        if not ok or rc != 0:
            # `pipefail`: the rightmost non-zero status wins, which is jq's when jq failed and the probe's 1 when it did not.
            return rc if rc != 0 else 1
        head = head_sha.rstrip(b"\n").decode("utf-8", "surrogateescape")

        ok, body = gh_probe(
            True,
            "rerun-review run",
            [
                "api",
                "repos/%s/actions/runs?head_sha=%s&event=pull_request" % (repo, head),
                "--jq",
                RUN_ID_FILTER,
            ],
            sleeper=sleeper,
        )
        rc, run_id_out = _jq(["-r", ".id"], stdin=body)
        if not ok or rc != 0:
            return rc if rc != 0 else 1
        run_id = run_id_out.rstrip(b"\n").decode("utf-8", "surrogateescape")

        if not run_id or run_id == "null":
            log.error("rerun-review: no review-pipeline run found for head %s" % head)
            return 1

        ok, body = gh_probe(
            False,
            "rerun-review rerun",
            ["run", "rerun", run_id, "--repo", repo, "--failed"],
            sleeper=sleeper,
        )
        if not ok:
            return 1
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()
        log.info("review run %s rerun requested for PR #%s" % (run_id, pr))
        return 0

    log.error(UNKNOWN_SUBCOMMAND % cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
