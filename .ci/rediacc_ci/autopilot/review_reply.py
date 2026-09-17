#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/review-reply.sh`.

Reply to and resolve the review threads a review-response round disposed of.

THE MODEL HOLDS NO WRITE TOKEN, so it cannot reply to a thread or resolve one;
it records dispositions as `decisions` entries shaped `thread <id>:
<disposition>` and exits. This script is the deterministic other half, and it is
split in two ON PURPOSE:

    plan   PURE. Turns the VALIDATED verdict's `decisions[]` into a reply plan.
           Every thread id must (a) match a tight id shape and (b) be present in
           the payload the model was actually shown. Anything else lands in
           `skipped[]` with a reason and raises `flagged` -- never silently.
    apply  THE WRITES. `addPullRequestReviewThreadReply` then
           `resolveReviewThread` per entry, gated on `AUTOPILOT_ALLOW_PUSH`
           (absent = off).

-----------------------------------------------------------------------------
WHY THE ID MUST BE IN THE FIXTURE, NOT MERELY WELL-SHAPED
-----------------------------------------------------------------------------
The twin's own paragraph, kept because it is the security argument for the whole
file: the reply body is MODEL-AUTHORED TEXT and the thread id chooses WHERE it
is posted. A global GraphQL node id names a thread on ANY pull request in any
repo the token can reach, so validating the id's characters alone would let a
round that read a hostile finding post that finding's suggested text onto an
unrelated PR. The payload is the round's whole world; a thread outside it is not
addressable.

That is TWO checks, not one, and the differential drives them separately
(`malformed-id` and `unknown-thread`) because they fail for different reasons
and a port that collapsed them into one would still pass a test that only ever
fed it garbage.

THE ID SHAPE IS RE-CHECKED AT THE WRITE, not only at the plan, and that is not
belt-and-braces: `apply` is a SEPARATE INVOCATION whose input is a file on disk
that some other step wrote. `plan` having been careful is not a property of the
bytes `apply` reads.

-----------------------------------------------------------------------------
THE PLAN PROGRAM IS JQ'S, VERBATIM, AND THAT IS THE POINT OF THIS PORT
-----------------------------------------------------------------------------
`PLAN_PROGRAM` below is the twin's jq program character for character. It is
not a formatting decision; it is a piece of REASONING with four rules a rewrite
would have to re-derive, and the first one it got wrong would post model text
somewhere nobody looked:

  1. `select(test("^thread [^:]+: "))` decides what is thread traffic AT ALL. An
     ordinary `decisions` entry is not a reply and is not an error either, so it
     is dropped silently rather than skipped loudly. Getting that backwards
     makes every round `flagged`.
  2. `capture(...; "s")` -- and this flag does NOT mean what the code that
     chose it appears to believe. See DEFECT 1 below; it is measured, not read.
  3. `.body[0:$max]` is a jq STRING SLICE, which counts CODEPOINTS, not bytes
     and not grapheme clusters. A Python `[:max]` agrees on codepoints today;
     writing it out means the next reader knows which of the three it is.
  4. `$repos[.id] // "console"` is a `//`, so a thread whose payload entry has
     `repo: false` would fall back to `console`. jq's falsy rule, not Python's.

`known` and `known_repos` are two more jq programs, and `(.threads // .) // []`
in both is meant to be the twin's shrug at its own input: `--threads` is
documented as accepting `review-payload.sh`'s object OR a bare array. See
DEFECT 2; it does not.

-----------------------------------------------------------------------------
TWO REAL DEFECTS IN THE TWIN, MEASURED AGAINST jq 1.8.1 ON 2026-09-13,
PRESERVED HERE AND REPORTED RATHER THAN REPAIRED
-----------------------------------------------------------------------------
Both are preserved because this port's contract is to be a verified-equivalent
alternative to a LIVE workflow step (`.github/workflows/autopilot.yml:817-818`),
and changing either one changes what that step does. Repairing them is the
cutover box's call, and each is pinned by a named test so the repair cannot
happen unnoticed.

DEFECT 1, AND IT IS LIVE: A MULTI-LINE DISPOSITION IS SILENTLY DROPPED.

    printf '%s' '{"decisions":["thread T_a: one\\ntwo"]}' \\
      | jq -c 'capture("^thread (?<id>[^:]+): (?<body>.*)$"; "s")'
    (no output, exit 0)

  jq's `s` flag is NOT dotall. jq documents it as "single line mode (^ -> \\A,
  $ -> \\Z)"; the flag that makes `.` match a newline is `m`. So the `.*` still
  stops at the first newline, the anchored `$` then cannot match, and `capture`
  yields NOTHING. `capture` producing no output DROPS the entry from the stream
  entirely -- so the disposition is neither replied nor skipped, `flagged` stays
  false, and the plan reports `0 reply/resolve pair(s) planned` with no warning
  of any kind.

  THAT CONTRADICTS THE TWIN'S OWN HEADER, which says of a disposition that
  cannot be used: "Anything else lands in skipped[] with a reason and raises
  flagged -- never silently." A model writing a two-line answer to a review
  finding gets exactly the silence that sentence promises cannot happen: the
  thread stays unresolved, the Review Gate stays red, and the round's ledger
  says it planned nothing. The one-character fix is `"m"` (or `[\\s\\S]*` in
  place of `.*`), and it is a behaviour change on a live step.
  Pinned by `test_a_multi_line_disposition_is_silently_dropped`.

DEFECT 2, LATENT: THE BARE-ARRAY `--threads` SPELLING DOES NOT WORK.

    printf '[]' | jq -c '(.threads // .) // []'
    jq: error (at <stdin>:1): Cannot index array with string "threads"   (exit 5)

  `.threads` on an ARRAY is an ERROR in jq, not `null`, so `//` never gets the
  chance to fall through. The comment above the program says both spellings are
  accepted and the reason they must be; the code accepts exactly one, and the
  other exits 5 with a jq diagnostic and no plan. It is LATENT rather than live
  because the only caller passes `review-payload.sh`'s object
  (`review-payload.sh:103-106` builds `{threads: ...}`), so the array path is
  documentation of a capability that was never there. The fix is
  `(if type == "object" then .threads else . end) // []` or
  `((.threads? // .) // [])`. Pinned by
  `test_a_bare_array_threads_fixture_is_refused_by_jq`.

-----------------------------------------------------------------------------
WHAT `apply` DOES TO THE WORLD, AND WHAT STOPS IT IN A TEST
-----------------------------------------------------------------------------
Two REAL, MUTATING GitHub writes per entry: a comment posted into a review
thread, and that thread marked resolved. GitHub undoes neither. So the
differential drives `gh` as a recording fake on a stub PATH and asserts the fake
is the `gh` that resolves, and every fixture names `acme/...`. The mutations
themselves are the ones `check-resolved-threads.sh` advertises to humans in its
remediation output, so the automated and manual paths cannot drift.

MODEL TEXT TRAVELS AS `-f k=v`, never as shell: the bytes land in one argv slot
with no re-parse. That is the property the differential checks by putting a
`$(rm -rf /)` in a reply body and comparing the recorded argv.

  THE ORDER IS REPLY THEN RESOLVE, and it is not interchangeable. Resolving
  first would leave a resolved thread with no answer in it if the reply failed,
  which is precisely the state `check-resolved-threads.sh` cannot distinguish
  from a human having dealt with it. `set -e` on the first `gh_json` is what
  stops the second from running.

  AND THE FAILURE IS NOT TRANSACTIONAL. A mutation that fails on entry 3 of 5
  leaves entries 1 and 2 replied-and-resolved and 4 and 5 untouched, with no
  record of where it stopped beyond the per-thread `log_info` lines. Rerunning
  would re-reply to 1 and 2. Reported rather than repaired: fixing it means
  giving the plan a resumable cursor, which is a design change and the cutover
  box's call. Pinned by `test_a_mutation_failure_stops_the_run_mid_plan`.

`_gh_probe` IS TRANSLITERATED, NOT IMPORTED, for the reason `finish.py:51-59`
records. `gh_json` is `_gh_probe true`, so the body must also PARSE and must not
be `null` or `false`.

Exit: 0 planned/applied, 1 write refused or a mutation failed, 2 usage.

K=5 LEDGER: `.ci/shadow/w7p6-review-reply.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "review-reply.py"

USAGE_PLAN = (
    "usage: review-reply.sh plan --verdict <file> --threads <file> [--max-body <n>] [--out <file>]"
)
USAGE_APPLY = "usage: review-reply.sh apply --plan <file>"
UNKNOWN_SUBCOMMAND = "unknown subcommand '%s' (plan|apply)"

# GraphQL node ids are base64url-ish; this is the character set GitHub uses plus
# a hard length bound, so nothing shell-shaped or path-shaped can ride through into a mutation variable.
ID_SHAPE = "^[A-Za-z0-9_=-]{1,128}$"

DEFAULT_MAX_BODY = "2000"

# The write gate. Absent is OFF; only the exact string `true` opens it.
ALLOW_PUSH_ENV = "AUTOPILOT_ALLOW_PUSH"
ALLOW_PUSH_VALUE = "true"

# `_gh_probe`'s loop shape (common.sh:434-473): three attempts, 3s then 6s.
GH_ATTEMPTS = 3
GH_BACKOFF_SECONDS = 3

REPLY_MUTATION = """
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
    comment { id }
  }
}"""

RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}"""

KNOWN_PROGRAM = '[ ((.threads // .) // [])[] | .id ] | map(select(type == "string"))'
KNOWN_REPOS_PROGRAM = (
    '[ ((.threads // .) // [])[] | select(.id | type == "string") '
    '| {key: .id, value: (.repo // "console")} ] | from_entries'
)

# THE TWIN'S PLAN PROGRAM, VERBATIM, comments and all. See the module docstring
# for the four rules a rewrite would have to re-derive. Changing a character
# here changes where model-authored text gets posted.
PLAN_PROGRAM = """
            ($known | map({(.): true}) | add // {}) as $ids
            | [ (.decisions // [])[]
                | select(type == "string")
                # Only entries in the documented disposition shape are thread
                # traffic; an ordinary decisions entry is not a reply and is
                # not an error either.
                | select(test("^thread [^:]+: "))
                | (capture("^thread (?<id>[^:]+): (?<body>.*)$"; "s")) ]
            | map(
                if (.id | test($shape) | not)
                then {kind: "skipped", entry: .id, reason: "malformed-id"}
                elif ($ids[.id] | not)
                then {kind: "skipped", entry: .id, reason: "unknown-thread"}
                else {kind: "reply", thread_id: .id, body: (.body[0:$max]),
                      repo: ($repos[.id] // "console")}
                end)
            | {replies: [ .[] | select(.kind == "reply") | {thread_id, body, repo} ],
               skipped: [ .[] | select(.kind == "skipped") | {entry, reason} ]}
            | . + {flagged: ((.skipped | length) > 0)}
        """

SKIPPED_REPORT_PROGRAM = '.skipped[] | "    - \\(.reason): \\(.entry)"'


def _json_usable(body: bytes) -> bool:
    """`[[ -n "$out" ]] && jq -e . <<<"$out"`: parses, and is not null/false."""
    if not body:
        return False
    try:
        value = json.loads(body)
    except ValueError:
        return False
    return value is not None and value is not False


def gh_json(what: str, args: list[str], *, sleeper=time.sleep) -> bool:
    """`gh_json <what> -- <gh args...> >/dev/null`, i.e. `_gh_probe true`.

    Returns success only; every caller here discards the body. Three attempts,
    a `log_warn` between them, a 3-then-6-second backoff, and the captured
    stderr replayed indented four spaces on final failure.
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
            out = (proc.stdout or b"").rstrip(b"\n")
            err = proc.stderr or b""
        if rc == 0 and _json_usable(out):
            return True
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
    return False


def _jq(args: list[str], stdin: str | None = None) -> tuple[int, str]:
    """jq with stderr INHERITED, stdout captured, `$( )`'s newline stripping."""
    proc = subprocess.run(
        ["jq", *args],
        input=(stdin + "\n").encode("utf-8", "surrogateescape") if stdin is not None else b"",
        stdout=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def matches_id_shape(value: str) -> bool:
    """`[[ "$tid" =~ $ID_SHAPE ]]`, which is ERE and therefore UNANCHORED-safe
    only because the pattern carries its own `^` and `$`.

    `re.search`, not `re.match`, so the `^` in the pattern is doing the work
    rather than Python's implicit anchoring -- if the shape ever loses its
    caret, this port loses it too, which is the behaviour a differential can
    see. Note that bash's `$` and Python's `$` differ on a trailing newline:
    Python's `$` also matches before a final `\\n`, so `\\Z` is used to keep an
    id with a trailing newline REFUSED by both sides.
    """
    return re.search(ID_SHAPE.replace("$", r"\Z"), value) is not None


def plan_max_body(value: str) -> bool:
    """`[[ "$MAX_BODY" =~ ^[0-9]{1,6}$ ]]`."""
    return 1 <= len(value) <= 6 and value.isascii() and value.isdigit()


def _plan(args: dict[str, str]) -> int:
    verdict = args.get("ARG_VERDICT", "")
    threads = args.get("ARG_THREADS", "")
    max_body = args.get("ARG_MAX_BODY", "") or DEFAULT_MAX_BODY
    out_path = args.get("ARG_OUT", "")

    if not (verdict and threads):
        log.error(USAGE_PLAN)
        return 2
    for path in (verdict, threads):
        try:
            common.require_file(path)
        except common.RefusalError as exc:
            exc.report()
            return exc.code
    if not plan_max_body(max_body):
        log.error("--max-body must be a number, got '%s'" % max_body)
        return 2

    # id -> repo, so a planned reply carries the repository its thread lives in. The GraphQL mutations address a thread by its global node id and need no repo argument, but the plan is also an AUDIT RECORD and a log line, and "resolved a thread" is not a useful sentence without naming where.
    code, known = _jq(["-c", KNOWN_PROGRAM, threads])
    if code != 0:
        # `x="$(jq ...)"` under `set -e`: jq's status, jq's message, no stdout.
        return code
    code, known_repos = _jq(["-c", KNOWN_REPOS_PROGRAM, threads])
    if code != 0:
        return code

    code, plan = _jq(
        [
            "-c",
            "--argjson",
            "known",
            known,
            "--argjson",
            "repos",
            known_repos,
            "--arg",
            "shape",
            ID_SHAPE,
            "--argjson",
            "max",
            max_body,
            PLAN_PROGRAM,
            verdict,
        ]
    )
    if code != 0:
        return code

    line = plan + "\n"
    if out_path:
        with open(out_path, "wb") as handle:
            handle.write(line.encode("utf-8", "surrogateescape"))
    else:
        sys.stdout.buffer.write(line.encode("utf-8", "surrogateescape"))
        sys.stdout.buffer.flush()

    code, flagged = _jq(["-r", ".flagged"], plan)
    if code != 0:
        return code
    if flagged == "true":
        # LOUD, because this is the model naming a thread nobody showed it: either the payload filter and the prompt disagree about what the round could see, or the round invented an id.
        _, count = _jq(["-r", ".skipped | length"], plan)
        log.warn(
            "review-reply plan: %s disposition(s) name no thread in this round's payload and "
            "were skipped:" % count
        )
        _, report = _jq(["-r", SKIPPED_REPORT_PROGRAM], plan)
        if report != "":
            print(report, file=sys.stderr, flush=True)
    _, planned = _jq(["-r", ".replies | length"], plan)
    log.info("review-reply plan: %s reply/resolve pair(s) planned" % planned)
    return 0


def _apply(args: dict[str, str], *, sleeper=time.sleep) -> int:
    plan_path = args.get("ARG_PLAN", "")
    if not plan_path:
        log.error(USAGE_APPLY)
        return 2
    try:
        common.require_file(plan_path)
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    # THE FILE IS REQUIRED BEFORE THE FLAG IS TESTED, which is the twin's order: a broken invocation gets a file error rather than a stage refusal, so a typo cannot be mistaken for a closed stage.
    if os.environ.get(ALLOW_PUSH_ENV, "") != ALLOW_PUSH_VALUE:
        log.error(
            "stage-flag-disabled: %s is not '%s'; refusing to reply or resolve (fail closed)"
            % (ALLOW_PUSH_ENV, ALLOW_PUSH_VALUE)
        )
        return 1

    code, count = _jq(["-r", ".replies | length", plan_path])
    if code != 0:
        return code
    if count == "0":
        log.info("review-reply apply: nothing planned; no thread touched")
        return 0

    # `jq length` yields a non-negative integer for every type it accepts and errors on the rest, so this cannot be a leading-zero octal the way the gate's counters can. Named because the sibling port needed a whole `bash_arith` for the same-looking expression.
    total = int(count)
    # Indexed, not piped: a `while read` in a pipeline runs in a subshell, where a failed mutation cannot fail this script.
    for index in range(total):
        code, tid = _jq(["-r", ".replies[%d].thread_id" % index, plan_path])
        if code != 0:
            return code
        code, body = _jq(["-r", ".replies[%d].body" % index, plan_path])
        if code != 0:
            return code
        code, trepo = _jq(["-r", '.replies[%d].repo // "console"' % index, plan_path])
        if code != 0:
            return code
        # Re-checked at the write, not only at the plan: apply is a separate invocation and its input is a file on disk.
        if not matches_id_shape(tid):
            log.error(
                "review-reply apply: thread id '%s' does not match the id shape; refusing" % tid
            )
            return 1
        # Model text travels as a -f VALUE, never as shell: `-f k=v` puts the
        # bytes in one argv slot with no re-parse.
        if not gh_json(
            "review reply for thread %s in %s" % (tid, trepo),
            [
                "api",
                "graphql",
                "-f",
                "query=%s" % REPLY_MUTATION,
                "-f",
                "threadId=%s" % tid,
                "-f",
                "body=%s" % body,
            ],
            sleeper=sleeper,
        ):
            # `set -e` on gh_json's non-zero status. NOTHING is rolled back; see
            # the module docstring on the non-transactional failure.
            return 1
        if not gh_json(
            "resolve thread %s" % tid,
            ["api", "graphql", "-f", "query=%s" % RESOLVE_MUTATION, "-f", "threadId=%s" % tid],
            sleeper=sleeper,
        ):
            return 1
        log.info("replied and resolved thread %s in %s" % (tid, trepo))
    log.info("review-reply apply: %s thread(s) answered and resolved" % count)
    return 0


def main(argv: list[str], *, sleeper=time.sleep) -> int:
    # `cmd="${1:-}"; shift || true`: the subcommand is positional and is NOT a
    # flag, so it never reaches parse_args. No arguments at all gives the empty subcommand, which lands in the unknown arm.
    cmd = argv[0] if argv else ""
    try:
        args = common.parse_args(argv[1:])
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    if cmd == "plan":
        return _plan(args)
    if cmd == "apply":
        return _apply(args, sleeper=sleeper)
    log.error(UNKNOWN_SUBCOMMAND % cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
