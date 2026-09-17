#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/fetch-review-threads.sh`.

Fetch every review thread on a PR, with its comments, as one JSON array.

THE NETWORK HALF OF THE REVIEW PAYLOAD (03-v2-autonomy.md section 6, residual 1:
"review-response rounds receive a gate-built payload filtered by comment author
before the model sees any text"). It runs in the GATE job, with `github.token`
and read-only permissions, so the fetch itself holds no write capability. The
FILTERING is `review-payload.sh`, which is pure and therefore testable offline;
keeping the two apart is what makes the security decision -- whose text reaches
the model -- reviewable without a network.

THE PAGINATION IS `check-resolved-threads.sh`'s, DELIBERATELY. That script
already paid for the lesson that `reviewThreads(first: 100)` with no cursor
silently truncates, so thread 101 being unresolved read as "all resolved". The
query differs from it in ONE way -- `comments(first: 20)` instead of `first: 1`
-- because the model needs the finding text, not just its author.

LINKED SUBMODULE PRs ARE FETCHED TOO. `check-submodule-branches.sh` reds the
console PR while a linked submodule PR still carries unresolved threads, but the
round only ever saw console's own threads, so it could answer every console
finding, resolve every console thread, and stay red on a complaint living in
another repository. With `--body`, the console PR body is scanned by
`linked-sub-prs.sh` (which recognises only the four known submodules) and each
linked PR's threads are fetched as well. Every thread is TAGGED with the repo
and PR it came from, so everything downstream can route its reply back.

-----------------------------------------------------------------------------
FAIL CLOSED MEANS THE OUTPUT FILE IS NEVER WRITTEN ON FAILURE
-----------------------------------------------------------------------------
"No threads" and "could not ask" must not share an output, so `--out` is written
ONCE, at the very end, after every page of every target has come back. A port
that streamed pages into the file as they arrived would leave a truncated array
behind on a mid-pagination failure, and the reader of that file has no way to
tell it from a short PR. The `open(out_path, "wb")` is therefore the LAST thing
`main` does, after every return-1 path, and
`test_the_out_file_is_absent_after_every_failure` asserts the file does not
exist rather than asserting it is empty -- because an empty file is a value a
reader could act on, and absence is not.

THE LINKED TARGETS ARE THE EXCEPTION, AND THE TWIN EXPLAINS WHY AT LENGTH: this
script runs in the GATE, which by invariant holds no app token, and
`github.token` is scoped to console, so a private submodule's PR is simply not
readable from here. Killing the whole round over that would take fix rounds down
with it. So each linked target degrades on its own, with a `::warning::` on
STDOUT (an Actions annotation, not a log line), and the console target stays
mandatory.

  NOTE THE STREAM: that warning is `echo`, so it lands on STDOUT while every
  other diagnostic in this file is `log_*` on STDERR. That is not a slip -- an
  Actions workflow command has to be on stdout to be recognised -- and a port
  that "tidied" it onto stderr would silently stop the annotation appearing in
  the run summary. Pinned by `test_a_linked_target_that_cannot_be_read`.

-----------------------------------------------------------------------------
WHAT IS SPAWNED, AND WHY EACH ONE STAYS SPAWNED
-----------------------------------------------------------------------------
  * `gh` -- not reimplementable, and the whole subject.
  * `jq` -- four programs. The accumulator (`$acc + (page | map(. + {repo,
    pr}))`) is the one that matters: it decides the SHAPE the payload filter and
    the reply planner both read, including that the tag fields are merged into
    each node rather than wrapping it. A Python `list.extend` plus `dict.update`
    would agree today and would not carry jq's rule that `+` on objects is a
    RIGHT-biased shallow merge, so a node that already had a `repo` key would be
    overwritten by jq and could be kept by a naive port.
  * `linked-sub-prs.sh` -- already ported next door as
    `rediacc_ci.autopilot.linked_sub_prs`, and still spawned as the SHELL
    script, because the twin spawns the shell script and the differential must
    compare against what the twin does. When the cutover flips that script, this
    line follows it; until then, importing the port here would mean the two
    sides of the differential were running different code for the same step.

`_gh_probe` IS TRANSLITERATED, NOT IMPORTED, for the reason `finish.py:51-59`
records: `core.ghx` classifies failures, raises typed errors and does NOT retry
three times with a `log_warn` between attempts. `gh_json` is `_gh_probe true`,
so the body must also PARSE and must not be `null` or `false` -- jq -e's rule,
not `json.loads`'.

-----------------------------------------------------------------------------
A HAZARD IN THE TWIN, REPORTED AND PRESERVED
-----------------------------------------------------------------------------
`fetch_target` is invoked ONLY from an `||` list and an `if !`, and bash
DISABLES `set -e` for the whole body of a function called that way. So a failing
`ALL_NODES="$(jq -n ...)"` inside it does not end the run: the variable is set
to the empty string and the loop carries on, and the next page's `--argjson acc
""` then fails too. The end state is an `--out` file containing one blank line
and a summary line reading `fetched  review thread(s)`. Every input that can
reach that jq has already been validated as JSON by `gh_json`, so it is
defence-in-depth failing quietly rather than a live bug -- but it is the one
place in this script where a failure does not fail closed. Preserved exactly
(see `_accumulate`), named here, and pinned by
`test_a_broken_accumulator_does_not_end_the_run`.

Env: GH_TOKEN. Exit: 0 written, 1 fetch failure, 2 usage.

K=5 LEDGER: `.ci/shadow/w7p6-fetch-review-threads.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "fetch-review-threads.py"

USAGE = "usage: fetch-review-threads.sh --pr <number> --repo <owner/name> --out <file>"

# `_gh_probe`'s loop shape (common.sh:434-473): three attempts, 3s then 6s.
GH_ATTEMPTS = 3
GH_BACKOFF_SECONDS = 3

# 50 pages is 5000 threads; a real PR never approaches it, so reaching it means
# the cursor stopped advancing. Fail closed rather than spin.
PAGE_LIMIT = 50

# THE QUERY, byte for byte from the twin, LEADING NEWLINE INCLUDED. It travels
# as a single `-f query=` argument, so its bytes are part of the request and are
# compared by the differential's call log. Reflowing it would change the request without changing the result, which is exactly the kind of difference a reviewer waves through and a cache does not.
QUERY = """
query($owner: String!, $repo: String!, $pr: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 20) {
            nodes {
              databaseId
              body
              author { login }
            }
          }
        }
      }
    }
  }
}"""

# The accumulator. `+` on two objects is jq's RIGHT-biased shallow merge, which is what tags each node with the repo and PR it came from.
ACCUMULATE_PROGRAM = """$acc + (($page.data.repository.pullRequest.reviewThreads.nodes // [])
                     | map(. + {repo: $repo, pr: $pr}))"""

HAS_NEXT_PAGE = ".data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage"
END_CURSOR = ".data.repository.pullRequest.reviewThreads.pageInfo.endCursor"
ERROR_MESSAGE = '.errors[0].message // "unknown error"'


def _json_usable(body: bytes) -> bool:
    """`[[ -n "$out" ]] && jq -e . <<<"$out"`: parses, and is not null/false."""
    if not body:
        return False
    try:
        value = json.loads(body)
    except ValueError:
        return False
    return value is not None and value is not False


def gh_json(what: str, args: list[str], *, sleeper=time.sleep) -> tuple[bool, str]:
    """`gh_json <what> -- <gh args...>`, i.e. `_gh_probe true`.

    Three attempts, a `log_warn` between them, a 3-then-6-second backoff, and
    the captured stderr replayed indented four spaces on final failure. The
    exit status is ALWAYS checked and a failure is never turned into an empty
    answer, which is the whole reason `_gh_probe` exists: the shape it replaced
    was `X=$(gh api ... 2>/dev/null || echo "[]")`, under which a rate limit and
    "this PR has no threads" produced the same value.
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
        if rc == 0 and _json_usable(out):
            return True, out.decode("utf-8", "surrogateescape")
        if attempt < GH_ATTEMPTS:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/3), retrying..."
                % (what, attempt)
            )
            sleeper(attempt * GH_BACKOFF_SECONDS)
        attempt += 1
    log.error("%s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc))
    if err:
        # `[[ -s "$err" ]] && sed 's/^/ /' "$err" >&2`, including GNU sed's refusal to invent a final newline the input did not have.
        text = err.decode("utf-8", "replace")
        parts = text.split("\n")
        incomplete = parts[-1] != ""
        if not incomplete:
            parts.pop()
        for index, line in enumerate(parts):
            tail = "" if incomplete and index == len(parts) - 1 else "\n"
            print("    %s" % line, end=tail, file=sys.stderr)
        sys.stderr.flush()
    return False, ""


def script_dir() -> pathlib.Path:
    """The twin's `SCRIPT_DIR`: `.ci/scripts/autopilot`.

    Not `rediacc_ci.paths.repo_root()`, which honours `$REDIACC_CI_ROOT` where
    the twin honours nothing. See `update_state.py:108-115`.
    """
    return pathlib.Path(__file__).resolve().parents[3] / ".ci" / "scripts" / "autopilot"


def _jq(args: list[str], stdin: str | None = None) -> tuple[int, str]:
    """jq with stderr INHERITED, which is what an unredirected jq does."""
    proc = subprocess.run(
        ["jq", *args],
        input=(stdin + "\n").encode("utf-8", "surrogateescape") if stdin is not None else b"",
        stdout=subprocess.PIPE,
        check=False,
    )
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "surrogateescape").rstrip("\n")


def _jq_quiet(args: list[str], stdin: str) -> bool:
    """`jq -e ... >/dev/null 2>&1 <<<"$x"`: the exit status, nothing else."""
    proc = subprocess.run(
        ["jq", *args],
        input=(stdin + "\n").encode("utf-8", "surrogateescape"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def page_args(query: str, owner: str, name: str, number: str, after: str) -> list[str]:
    """The twin's `set --` block: the gh argv for one page.

    `-F pr=` is gh's TYPED form (the GraphQL variable is `Int!`), `-f` the
    string form. Getting that pair backwards makes the server reject the query,
    so the two spellings are part of the request and are compared as such.
    `after` is OMITTED on the first page rather than passed empty, because
    `after: ""` is not the same query as `after: null`.
    """
    argv = [
        "-f",
        "query=%s" % query,
        "-f",
        "owner=%s" % owner,
        "-f",
        "repo=%s" % name,
        "-F",
        "pr=%s" % number,
    ]
    if after:
        argv += ["-f", "after=%s" % after]
    return argv


class Fetcher:
    """`fetch_target`'s closure over `ALL_NODES`, which the twin mutates as a
    global. A class rather than a `nonlocal`, so the accumulator can be read by
    the differential's unit half without running the whole script."""

    def __init__(self, *, sleeper=time.sleep) -> None:
        self.all_nodes = "[]"
        self.sleeper = sleeper

    def _accumulate(self, page_json: str, target: str, number: str) -> None:
        """`ALL_NODES="$(jq -n --argjson acc ... )"`.

        SET -e IS OFF HERE. See the module docstring's hazard: this function is
        only ever reached from a call site that disables errexit, so a jq
        failure sets the accumulator to the empty string and the run continues.
        Reproduced rather than repaired.
        """
        code, out = _jq(
            [
                "-n",
                "--argjson",
                "acc",
                self.all_nodes,
                "--argjson",
                "page",
                page_json,
                "--arg",
                "repo",
                target,
                "--argjson",
                "pr",
                number,
                ACCUMULATE_PROGRAM,
            ]
        )
        # `x="$(failing command)"` under `set +e`: the variable takes whatever
        # was on stdout, which for a failed jq is nothing.
        self.all_nodes = out if code == 0 else ""

    def fetch_target(self, target: str, number: str) -> int:
        """`fetch_target <owner/name> <pr>`: 0 appended, 1 failed closed."""
        owner = target.split("/", 1)[0]  # `${target%%/*}`
        name = target.rsplit("/", 1)[-1]  # `${target##*/}`
        after = ""
        page = 0
        while True:
            page += 1
            if page > PAGE_LIMIT:
                log.error(
                    "review-thread pagination did not terminate after %d pages; failing closed"
                    % page
                )
                return 1
            ok, page_json = gh_json(
                "review threads for PR %s#%s (page %d)" % (target, number, page),
                ["api", "graphql", *page_args(QUERY, owner, name, number, after)],
                sleeper=self.sleeper,
            )
            if not ok:
                log.error(
                    "cannot fetch review threads for PR %s#%s; failing closed" % (target, number)
                )
                return 1
            # A GraphQL error response is valid JSON and exits 0, so it is caught per page rather than only on the last one. THIS IS THE CHECK THAT STOPS A PERMISSION ERROR READING AS "no threads".
            if _jq_quiet(["-e", ".errors"], page_json):
                _, message = _jq(["-r", ERROR_MESSAGE], page_json)
                log.error("GraphQL query failed: %s" % message)
                return 1
            self._accumulate(page_json, target, number)
            _, has_next = _jq(["-r", HAS_NEXT_PAGE], page_json)
            if has_next != "true":
                break
            _, after = _jq(["-r", END_CURSOR], page_json)
            if not after or after == "null":
                log.error("hasNextPage was true but the cursor was empty; failing closed")
                return 1
        return 0


def linked_targets(body: str) -> tuple[int, list[tuple[str, str]]]:
    """`< <("$SCRIPT_DIR/linked-sub-prs.sh" --body "$BODY")`.

    Returns (exit code, [(target, number)]). THE EXIT CODE IS RETURNED AND
    IGNORED, exactly as the twin ignores it: a process substitution feeding a
    `while read` loop cannot fail the loop, so a `linked-sub-prs.sh` that died
    reads as "no linked PRs". Returned anyway so the differential can see it and
    the next reader can decide whether to keep ignoring it.

    `read -r target number` splits on IFS, so a line with more than two fields
    puts the REMAINDER in `number`; a line with one field leaves `number` empty
    and is still fetched, as `<repo>#`. Both reproduced.
    """
    proc = subprocess.run(
        [str(script_dir() / "linked-sub-prs.sh"), "--body", body],
        stdout=subprocess.PIPE,
        check=False,
    )
    out = []
    for raw in (proc.stdout or b"").decode("utf-8", "surrogateescape").split("\n"):
        fields = raw.split()
        if not fields:
            # `[[ -n "$target" ]] || continue`: a blank line is skipped.
            continue
        target = fields[0]
        number = " ".join(fields[1:])
        out.append((target, number))
    return proc.returncode, out


def _non_empty(path: str) -> bool:
    """`[[ -n "$p" && -s "$p" ]]`, NOT `require_file`.

    `--body` is optional and a mistyped path therefore reads as "no linked PRs",
    silently. Same asymmetry `autopilot_gate.py` records for `--state`; named
    here because the consequence is the same one the LINKED SUBMODULE paragraph
    above exists to prevent -- a round that cannot see a submodule thread cannot
    answer it -- reached this time by a typo rather than by a missing token.
    """
    if not path:
        return False
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def main(argv: list[str], *, sleeper=time.sleep) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    pr = args.get("ARG_PR", "")
    repo = args.get("ARG_REPO", "")
    out_path = args.get("ARG_OUT", "")
    body = args.get("ARG_BODY", "")

    if not (pr and repo and out_path):
        log.error(USAGE)
        return 2
    # The PR number is the only validated input, and it is validated because it travels as a TYPED GraphQL variable: a non-numeric value would be a server error paid for after the request rather than a refusal before it.
    if not (pr.isascii() and pr.isdigit()):
        log.error("--pr must be a number, got '%s'" % pr)
        return 2

    fetcher = Fetcher(sleeper=sleeper)

    # Console's own threads are REQUIRED: without them the payload describes nothing and a review round would answer findings it never read.
    if fetcher.fetch_target(repo, pr) != 0:
        log.error("cannot fetch review threads for the console PR; failing closed")
        return 1

    # The linked submodule PRs, when the caller supplied the console body.
    # BEST-EFFORT, and the twin's own paragraph says why at length; the short
    # version is that the gate holds no cross-repo token, so a private submodule's PR is unreadable from here and killing the round over it would take fix rounds down with it.
    if _non_empty(body):
        _, targets = linked_targets(body)
        for target, number in targets:
            log.info("also fetching review threads for the linked %s#%s" % (target, number))
            if fetcher.fetch_target(target, number) != 0:
                # STDOUT, because an Actions workflow command has to be on stdout to be recognised. See the module docstring.
                print(
                    "::warning::autopilot gate: could not read review threads for %s#%s "
                    "(the gate holds no cross-repo token); this round cannot answer them"
                    % (target, number),
                    flush=True,
                )

    with open(out_path, "wb") as handle:
        handle.write(fetcher.all_nodes.encode("utf-8", "surrogateescape") + b"\n")
    _, count = _jq(["length"], fetcher.all_nodes)
    _, repos = _jq(["-r", "[.[].repo] | unique | length"], fetcher.all_nodes)
    log.info(
        "fetched %s review thread(s) across %s pull request(s) -> %s" % (count, repos, out_path)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
