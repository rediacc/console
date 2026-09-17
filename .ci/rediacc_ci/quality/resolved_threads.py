r"""Every review thread must be RESOLVED, and nobody may be requesting changes.

Ported from `.ci/scripts/quality/check-resolved-threads.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHAT IT IS, in the twin's own words:

    Check that all review threads are resolved using GitHub GraphQL API.

    This is separate from "unreplied comments" - a thread can have replies but
    still be unresolved. This script ensures all threads are properly resolved.

    Also checks if any reviewer has requested changes.

    Environment variables:
      GH_TOKEN           - GitHub token for API access (must have repo scope)
      PR_NUMBER          - Pull request number
      GITHUB_REPOSITORY  - Repository in owner/repo format

THE PAGINATION IS A FIXED SILENT GREEN, and the twin records the shape:

    PAGINATE. `reviewThreads(first: 100)` with no cursor silently truncates at
    100, and because the gate only ever reports UNRESOLVED threads, thread 101
    being unresolved read as "all threads resolved" -- a silent green on a
    merge-blocking check, which is the same failure class as the `|| echo "[]"`
    bug fixed below. $after is a nullable GraphQL variable, so omitting it on the
    first request is how you ask for page one; there is no valid empty-string
    cursor.

    50 pages is 5000 threads. A real PR never approaches it, so hitting this means
    the cursor stopped advancing; fail closed rather than spin forever.

THE FAIL-CLOSED RULE, twice, because it was broken twice:

    Execute the GraphQL query. `gh api graphql` can exit 0 while returning a
    truncated or malformed body (an upstream hiccup), so a command-exit-code check
    alone misses it -- gh_json validates that the body is PARSEABLE JSON on each of
    its three attempts, which is what the hand-rolled loop that used to live here
    did. It moved to lib/common.sh because eight other call sites across the review
    and attribution gates needed exactly this and had none of it.

    A GraphQL error response is valid JSON and exits 0, so catch it per page rather
    than only on the last one.

    FAIL CLOSED. `|| echo "[]"` here meant a gh failure produced an empty review
    list, so CHANGES_REQUESTED came out 0 and the gate reported that nobody had
    requested changes. That is a silent green on a merge-blocking check.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`gh_json` IS REIMPLEMENTED, NOT SHELLED OUT TO, and the three properties that make it worth having are each reproduced: the exit status is checked, the body must PARSE as JSON, and it retries twice with `sleep attempt*3` between attempts. The retry messages are `log_warn` and the final failure is `log_error` followed by the child's stderr indented four spaces, which is what
`common.sh:_gh_probe` prints and therefore what any caller reading this gate's output already expects.

THE SLEEPS ARE REAL. A retry loop with the sleeps removed would be a different program under a rate limit, and the point of the retries is to outlast a blip. The cost is that a fixture exercising the failure path takes nine seconds on both sides, which is why the committed ledger has no such row and the pytest that does is marked as the slow one.

jq IS REIMPLEMENTED IN PYTHON, and three of its behaviours are load-bearing here: `//` yields its right side when the left is null OR false (so `.line // "N/A"`
covers a null line but would also cover a `false`, which cannot occur);
`group_by` SORTS its groups by key, so the reviewers named in the failure block come out in login order rather than in reply order; and `sort_by` is stable, so two reviews with the same `submitted_at` keep their input order and `last` picks the later of them. A port that used a Python `set` or an unsorted `groupby` would print the same reviewers in a different order and diverge.

THE RE-WRAP IS PRESERVED. The twin rebuilds the paginated node list into the original single-response shape "so every consumer below is unchanged". The port has no such consumer, but the SHAPE is what the failure messages are phrased against, so the intermediate is kept as a named value rather than optimised away.
"""

import io
import json
import os
import subprocess
import sys
import time

from rediacc_ci import log
from rediacc_ci.controls import Controls

# The three variables `require_var` insists on, in the twin's order.
REQUIRED_VARS = ("PR_NUMBER", "GH_TOKEN", "GITHUB_REPOSITORY")

# "50 pages is 5000 threads. A real PR never approaches it, so hitting this means the cursor stopped advancing; fail closed rather than spin forever."
MAX_PAGES = 50

# `_gh_probe` in `.ci/scripts/lib/common.sh`: three attempts, sleeping attempt * 3 seconds between them.
GH_ATTEMPTS = 3
GH_SLEEP_FACTOR = 3

QUERY = """
query($owner: String!, $repo: String!, $pr: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 1) {
            nodes {
              body
              author {
                login
              }
            }
          }
        }
      }
    }
  }
}"""


def gh_json(what: str, argv: list[str], *, sleeper=time.sleep, binary: str = "gh") -> str | None:
    """`gh_json <what> -- <args>`: status checked AND body must parse as JSON.

    Returns the body, or None after three failed attempts. `sleeper` is injectable so a test can exercise the retry ladder without waiting nine seconds; the DEFAULT sleeps, because a retry loop that does not wait is a different program under a rate limit.
    """
    attempt = 1
    rc = 0
    last_stderr = ""
    while attempt <= GH_ATTEMPTS:
        rc = 0
        try:
            proc = subprocess.run(
                [binary, *argv],
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except OSError:
            rc = 127
            last_stderr = ""
        else:
            rc = proc.returncode
            last_stderr = proc.stderr
            if rc == 0 and proc.stdout:
                try:
                    json.loads(proc.stdout)
                except ValueError:
                    pass
                else:
                    # `out="$(gh "$@" ...)"` in `_gh_probe`: COMMAND SUBSTITUTION
                    # STRIPS TRAILING NEWLINES, and the helper then re-emits the stripped value with `printf '%s'`. That matters because `check-review-comments.sh` compares the result against the literal `"[]"`, and an unstripped `"[]\n"` takes the other branch. Found by the differential, on a specimen with no inline comments.
                    return proc.stdout.rstrip("\n")
        if attempt < GH_ATTEMPTS:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/%d), retrying..."
                % (what, attempt, GH_ATTEMPTS)
            )
            sleeper(attempt * GH_SLEEP_FACTOR)
        attempt += 1
    log.error("%s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc))
    if last_stderr:
        for line in last_stderr.rstrip("\n").split("\n"):
            print("    %s" % line, file=sys.stderr)
    return None


def unresolved(nodes: list[dict]) -> list[dict]:
    """`select(.isResolved == false and .isOutdated == false)`.

    AN OUTDATED THREAD IS EXCLUDED ON PURPOSE: it points at a line that no longer exists in the diff, so demanding it be resolved is demanding an action on code that is gone.
    """
    return [
        node
        for node in nodes
        if node.get("isResolved") is False and node.get("isOutdated") is False
    ]


def latest_per_reviewer(reviews: list[dict]) -> list[dict]:
    """`group_by(.user.login) | .[] | sort_by(.submitted_at) | last`.

    GROUPS COME OUT IN LOGIN ORDER, because jq's `group_by` sorts by key, and the failure block prints them in that order. `sort_by` is stable, so two reviews sharing a `submitted_at` keep their input order and `last` picks the later of the two.
    """
    groups: dict[str, list[dict]] = {}
    for review in reviews:
        login = ((review.get("user") or {}).get("login")) or ""
        groups.setdefault(login, []).append(review)
    out: list[dict] = []
    for login in sorted(groups):
        ordered = sorted(groups[login], key=lambda r: r.get("submitted_at") or "")
        out.append(ordered[-1])
    return out


def changes_requested(reviews: list[dict]) -> list[dict]:
    """The latest review per reviewer that is CHANGES_REQUESTED, in login order."""
    return [r for r in latest_per_reviewer(reviews) if r.get("state") == "CHANGES_REQUESTED"]


def thread_lines(threads: list[dict]) -> list[str]:
    """The `jq -r` block that renders one unresolved thread.

    Reproduces the concatenation exactly, including the trailing `...` and the empty line the final `"\\n"` produces, because the differential compares text.
    """
    out: list[str] = []
    for thread in threads:
        line = thread.get("line")
        line_text = "N/A" if line is None or line is False else str(line)
        comments = ((thread.get("comments") or {}).get("nodes")) or [{}]
        first = comments[0] if comments else {}
        author = ((first.get("author") or {}).get("login")) or "unknown"
        body = first.get("body") or ""
        excerpt = body.split("\n")[0][:80]
        out.append("  %s:%s" % (thread.get("path"), line_text))
        out.append("    Author: @%s" % author)
        out.append("    Comment: %s..." % excerpt)
        out.append("")
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when every thread is resolved and nobody blocks, 1 otherwise.

    FAILING CLOSED IS THE DEFAULT EVERYWHERE. Every read that cannot complete exits 1 with a message naming what could not be determined, because this gate blocks a merge and an unreadable probe must block it too.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    for name in REQUIRED_VARS:
        if not os.environ.get(name):
            log.error("Required environment variable '%s' is not set" % name)
            return 1

    pr_number = os.environ["PR_NUMBER"]
    repository = os.environ["GITHUB_REPOSITORY"]
    owner = repository.split("/", 1)[0]
    repo = repository.rsplit("/", 1)[-1]

    log.step("Checking review threads and review status...")
    log.step("Fetching review threads via GraphQL...")

    all_nodes: list[dict] = []
    after = ""
    page = 0
    while True:
        page += 1
        if page > MAX_PAGES:
            log.error(
                "Review-thread pagination did not terminate after %d pages. Failing closed." % page
            )
            return 1
        call = [
            "api",
            "graphql",
            "-f",
            "query=%s" % QUERY,
            "-f",
            "owner=%s" % owner,
            "-f",
            "repo=%s" % repo,
            "-F",
            "pr=%s" % pr_number,
        ]
        if after:
            call += ["-f", "after=%s" % after]
        body = gh_json("review threads for PR #%s (page %d)" % (pr_number, page), call)
        if body is None:
            log.error("Cannot determine whether review threads are resolved. Failing closed.")
            return 1
        payload = json.loads(body)
        # "A GraphQL error response is valid JSON and exits 0, so catch it per page rather than only on the last one."
        if payload.get("errors"):
            first = payload["errors"][0] if payload["errors"] else {}
            log.error("GraphQL query failed: %s" % (first.get("message") or "Unknown error"))
            return 1
        threads = (
            ((payload.get("data") or {}).get("repository") or {}).get("pullRequest") or {}
        ).get("reviewThreads") or {}
        all_nodes += threads.get("nodes") or []
        page_info = threads.get("pageInfo") or {}
        if str(page_info.get("hasNextPage")).lower() != "true":
            break
        after = page_info.get("endCursor") or ""
        if not after or after == "null":
            log.error("hasNextPage was true but the cursor was empty. Failing closed.")
            return 1
    if page > 1:
        log.step("Fetched %d review threads across %d pages" % (len(all_nodes), page))

    open_threads = unresolved(all_nodes)
    unresolved_count = len(open_threads)

    log.step("Checking review status...")

    reviews_body = gh_json(
        "review status for PR #%s" % pr_number,
        ["api", "repos/%s/pulls/%s/reviews" % (repository, pr_number)],
    )
    if reviews_body is None:
        log.error("Cannot determine whether a reviewer requested changes. Failing closed.")
        return 1
    reviews = json.loads(reviews_body)
    blocking = changes_requested(reviews)

    has_issues = False

    if len(blocking) > 0:
        has_issues = True
        print()
        print("============================================================")
        print("  Changes Requested by Reviewer")
        print("============================================================")
        print()
        print("One or more reviewers have requested changes.")
        print()
        print("Reviewers who requested changes:")
        for review in blocking:
            print("  - @%s" % ((review.get("user") or {}).get("login")))
        print()
        print("Please address the reviewer feedback and request a new review.")
        print("------------------------------------------------------------")

    if unresolved_count > 0:
        has_issues = True
        print()
        print("============================================================")
        print("  Unresolved Review Threads")
        print("============================================================")
        print()
        print("Found %d unresolved review thread(s):" % unresolved_count)
        print()
        for line in thread_lines(open_threads):
            print(line)
        print("------------------------------------------------------------")
        print("Please resolve all review threads before merging.")
        print()
        print("Option 1: Via GitHub UI")
        print("  1. Go to the PR: https://github.com/%s/pull/%s" % (repository, pr_number))
        print("  2. Click 'Resolve conversation' on each thread")
        print()
        print("Option 2: Via CLI (resolve all threads at once)")
        print()
        print("  # Get unresolved thread IDs")
        print("  cat > /tmp/query.graphql << 'GRAPHQL'")
        print("  query($owner: String!, $repo: String!, $pr: Int!) {")
        print("    repository(owner: $owner, name: $repo) {")
        print("      pullRequest(number: $pr) {")
        print("        reviewThreads(first: 100) {")
        print("          nodes { id isResolved }")
        print("        }")
        print("      }")
        print("    }")
        print("  }")
        print("  GRAPHQL")
        print()
        print("  cat > /tmp/resolve.graphql << 'GRAPHQL'")
        print("  mutation($threadId: ID!) {")
        print("    resolveReviewThread(input: {threadId: $threadId}) {")
        print("      thread { id isResolved }")
        print("    }")
        print("  }")
        print("  GRAPHQL")
        print()
        print("  # Resolve all unresolved threads")
        print(
            '  for id in $(gh api graphql -F owner="%s" -F repo="%s" -F pr=%s \\'
            % (owner, repo, pr_number)
        )
        print('      -f query="$(cat /tmp/query.graphql)" \\')
        print(
            "      --jq '.data.repository.pullRequest.reviewThreads.nodes[] | "
            "select(.isResolved == false) | .id'); do"
        )
        print(
            '    gh api graphql -F threadId="$id" -f query="$(cat /tmp/resolve.graphql)" --silent'
        )
        print("  done")
        print()
        print("------------------------------------------------------------")

    if has_issues:
        return 1

    total_threads = len(all_nodes)
    resolved_count = total_threads - unresolved_count

    print()
    log.info("Review status: OK")
    if total_threads > 0:
        log.info("All %d review thread(s) are resolved" % resolved_count)
    else:
        log.info("No review threads to resolve")
    log.info("No pending 'Changes Requested' reviews")
    return 0


def selftest() -> int:
    """Both directions on every selector, plus the retry ladder without waiting.

    THE FLOOR IS DERIVED from the case corpus, so a case that stops running turns the suite red rather than quietly shortening it.
    """
    threads = [
        {"isResolved": False, "isOutdated": False, "path": "a.ts", "line": 3},
        {"isResolved": True, "isOutdated": False, "path": "b.ts", "line": 4},
        # AN OUTDATED THREAD IS EXCLUDED even when unresolved: it points at a line that no longer exists.
        {"isResolved": False, "isOutdated": True, "path": "c.ts", "line": 5},
    ]
    unresolved_cases = [
        ("an unresolved, current thread is reported", threads, 1),
        ("a resolved thread is not", [threads[1]], 0),
        ("an unresolved but OUTDATED thread is not", [threads[2]], 0),
        ("an empty list reports nothing", [], 0),
    ]
    reviews = [
        {"user": {"login": "zoe"}, "state": "APPROVED", "submitted_at": "2026-09-01T00:00:00Z"},
        {
            "user": {"login": "amy"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-09-01T00:00:00Z",
        },
        # THE SUPERSEDED CASE: amy's later APPROVED must win over her earlier block.
        {"user": {"login": "amy"}, "state": "APPROVED", "submitted_at": "2026-09-02T00:00:00Z"},
    ]
    review_cases = [
        ("a later approval supersedes an earlier block", reviews, 0),
        ("a standing block is reported", reviews[:2], 1),
        ("an approval alone is not a block", [reviews[0]], 0),
        ("no reviews at all is not a block", [], 0),
    ]

    floor = len(unresolved_cases) + len(review_cases) + 8
    ctl = Controls("resolved-threads", floor=floor)

    for label, nodes, want in unresolved_cases:
        ctl.check("unresolved: %s" % label, len(unresolved(nodes)), want)
    for label, data, want in review_cases:
        ctl.check("reviews: %s" % label, len(changes_requested(data)), want)

    # GROUP ORDER IS LOGIN ORDER, because jq's group_by sorts by key. A port using insertion order would print the same reviewers differently.
    mixed = [
        {
            "user": {"login": "zoe"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-09-01T00:00:00Z",
        },
        {
            "user": {"login": "amy"},
            "state": "CHANGES_REQUESTED",
            "submitted_at": "2026-09-01T00:00:00Z",
        },
    ]
    ctl.check(
        "reviewers are named in login order, not reply order",
        [r["user"]["login"] for r in changes_requested(mixed)],
        ["amy", "zoe"],
    )

    # THE THREAD RENDERER, including the two `//` defaults and the 80-char cut.
    rendered = thread_lines(
        [
            {
                "path": "x.ts",
                "line": None,
                "comments": {"nodes": [{"body": "first line\nsecond", "author": None}]},
            }
        ]
    )
    ctl.check("a null line renders as N/A", rendered[0], "  x.ts:N/A")
    ctl.check("a null author renders as unknown", rendered[1], "    Author: @unknown")
    ctl.check("only the first body line is shown", rendered[2], "    Comment: first line...")
    long_body = "y" * 200
    cut = thread_lines(
        [
            {
                "path": "x",
                "line": 1,
                "comments": {"nodes": [{"body": long_body, "author": {"login": "a"}}]},
            }
        ]
    )
    ctl.check("the excerpt is cut at 80 characters", cut[2], "    Comment: %s..." % ("y" * 80))

    # THE RETRY LADDER, driven without waiting. It must try three times and then
    # return None rather than an empty body: "a gh failure produced an empty review
    # list, so CHANGES_REQUESTED came out 0 and the gate reported that nobody had requested changes."
    #
    # A NONEXISTENT BINARY, not a failing `gh` invocation, so the control does not depend on `gh` being installed and does not print the real tool's usage text into a selftest. The logger is pointed at a buffer for the same reason: the ladder's own warn and error lines are the thing under test, not output.
    waits: list[float] = []
    buffered = io.StringIO()
    log.reset(stream=buffered, colour=False)
    try:
        outcome = gh_json(
            "selftest", ["irrelevant"], sleeper=waits.append, binary="gh-does-not-exist-zzz"
        )
    finally:
        log.reset()
    ctl.check("three failed attempts return None, never an empty list", outcome, None)
    ctl.check("the ladder sleeps 3 then 6 seconds", waits, [3, 6])
    ctl.check(
        "the ladder announces each retry and then the final failure",
        (buffered.getvalue().count("retrying..."), buffered.getvalue().count("failed after 3")),
        (2, 1),
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
