r"""Every review comment must have a SUBSTANTIVE reply, on both surfaces.

Ported from `.ci/scripts/quality/check-review-comments.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHAT IT IS, in the twin's own words:

    This script ensures all review comments have been addressed before merging. A
    comment is considered "addressed" if it has at least one SUBSTANTIVE reply.

    Low-effort replies like "Acknowledged", "OK", "Understood" etc. are NOT
    considered valid replies - they don't add value to the review process.

    TWO SURFACES, because the review speaks on two endpoints:

      1. INLINE review-thread comments -- repos/{REPO}/pulls/{PR}/comments.
         Threaded: a reply carries in_reply_to_id, so "addressed" is local.

      2. The TOP-LEVEL review summary -- repos/{REPO}/issues/{PR}/comments.
         This is where the verdict actually lives. The review prompt
         (.ci/scripts/review/prompts/initial.md, step 5) tells the reviewer to
         "Finish with ONE summary comment via gh pr comment", carrying the verdict,
         the severity-ordered defects, the nits, and the coverage map. Only the
         top-N findings are ever mirrored inline (claude-review-gate.sh
         --post-findings caps at 20 and silently skips any line not in the diff),
         so the summary is strictly the larger surface, not a duplicate of it.

    THIS GATE READ ONLY SURFACE 1 UNTIL 2026-08-05, and that is exactly the repo's
    recurring class: a check that cannot see the thing it is checking. Live proof,
    PR #551: the reviewer posted issue comment 5189236393 ("## Review verdict:
    approve with one correctness finding to fix", 8141 chars,
    github-actions[bot]); nobody answered it; this gate reported the PR clean and
    the Review Gate went green. The sibling gate check-review-report-replies.sh
    does read issues/{PR}/comments, but it only matches the pipeline's OWN wrapper
    comment ("**Claude finished ..."), and on #551 that wrapper carried neither the
    findings fence nor a "### Review" heading -- so it found no report and exited 0
    vacuously too.

THE FAIL-CLOSED RULE, and what breaking it looked like:

    FAIL CLOSED. This used to be `|| echo "[]"`, so a rate limit, an expired token
    or a network blip produced the same value as a PR with no review comments: the
    gate printed "No review comments found - OK" and exited 0. This is a
    merge-blocking gate, so a probe failure must block the merge, not wave it
    through. gh_json retries twice before giving up.

    Same fail-closed contract on surface 2: an unreadable comment list must not be
    indistinguishable from "the review posted no summary".

HOW THE SUMMARY IS IDENTIFIED, which is the part a reviewer must be able to check:

    issues/{PR}/comments carries ALL PR chatter -- operator notes, watchdog output,
    deploy-preview links, CI reports. Blocking on every unanswered comment would be
    intolerable and would get this gate suppressed within a day, so the summary is
    picked out STRUCTURALLY, by the marker the pipeline already emits:

      author contains "github-actions"  AND  body contains "json:review-findings"

    That is not a heuristic invented here -- it is verbatim the selector
    claude-review-gate.sh --post-findings uses to locate the same comment and parse
    its findings array. If the fence name ever drifts, inline posting breaks in the
    same commit, so the two cannot silently disagree. (test-review-status.sh asserts
    the needle still exists in the gate script.)

    The verdict heading is a SECOND, weaker key for a review that produced no fence
    (nothing to anchor, or a budget halt mid-report): live shape on #551 was a body
    opening "## Review verdict: approve with one correctness finding".

    Excluded: bodies starting with "<!--". Those are the pipeline's bookkeeping
    comments -- MARKER_PREFIX ("<!-- claude-reviewed: <sha> -->") and ATTEMPT_PREFIX
    ("<!-- claude-review-attempt: ...") -- which are state, not findings, and must
    never be mistaken for a verdict awaiting an answer.

    Only the NEWEST match is gated, matching check-review-report-replies.sh: each
    review pass supersedes the previous summary, and re-litigating superseded
    verdicts would make a re-reviewed PR permanently unmergeable.

WHAT COUNTS AS A REPLY TO THE SUMMARY, all four clauses:

    (a) a DIFFERENT author from the reviewer. This is the load-bearing clause, not
        politeness: the pipeline posts several comments in a row under the same
        identity, and on #551 the marker comment (5189238817, 250 chars) landed 14
        SECONDS after the summary. With author ignored, the review would have
        "replied" to itself on every PR and this gate could never fire once.
    (b) posted AFTER it. Compared in jq, on the ISO-8601 strings GitHub returns, so
        bash's locale-dependent `>` is never involved.
    (c) substantive, i.e. past SUMMARY_MIN_CHARS and not a stock acknowledgement.
    (d) demonstrably ABOUT the review -- either it cites the summary's id (or its
        #issuecomment-<id> anchor), or it is long-form (SUMMARY_LONGFORM_CHARS+),
        the shape a genuine per-finding response takes. Without (d) an unrelated
        "preview looks good, merging tomorrow" would clear the gate.

    (d) deliberately does NOT hard-require the id, unlike
    check-review-report-replies.sh. The live answer on #551 (5190623031, 2856 chars,
    per-finding) cites no id, and a rule that calls that unaddressed is a rule that
    would be turned off.

    Accepted imprecision: another bot with a different login could satisfy (a).
    Narrowing that further would need an identity allowlist, which buys little --
    the same-identity self-reply above is the failure that actually happens.

-----------------------------------------------------------------------------
LATENT DEFECT NOTED WHILE PORTING, NOT REPAIRED.
-----------------------------------------------------------------------------

`COMMENT_BODY=$(echo "$comment" | jq -r '.body' | head -c 100)` RUNS UNDER
`set -o pipefail`. If `jq` were still writing when `head` closed the pipe, jq would die on SIGPIPE, pipefail would promote that to the assignment, and `set -e` would end the script mid-report. It does not fire today because a comment body is far smaller than the 64 KB pipe buffer, so jq finishes before head exits. The gate's OTHER excerpt, on the same surface, avoids the shape
deliberately and says why: "Bash slice rather than `| head -c`: a summary is thousands of characters, and head closing the pipe early would SIGPIPE the upstream under pipefail." One of the two excerpts got the treatment and the other did not.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWO SHARED CONSTANTS MUST MATCH `review_report_replies.py`, and the bash pair duplicates them for the same reason: "That is what makes one reply clear both gates; test-review-status.sh parses both files and fails if they drift apart." So they are duplicated here rather than imported, and both ports assert the agreement.

`is_low_effort_reply` DEFAULTS TO 10 HERE AND TO 30 IN THE SIBLING. Same name, different default, on purpose: "min_chars defaults to 10, the floor a single inline thread has always used. A reply to the whole review summary answers many findings at once, so that caller passes a higher floor." A port that unified them would silently tighten one gate or loosen the other.

`head -c 100` IS BYTES, and the bash slice `${SUMMARY_HEAD:0:120}` is bytes too
under `LC_ALL=C`, which `scripts/lib/shadow-gate.ts` pins. Both are reproduced by
slicing the UTF-8 ENCODING rather than the string, so a multi-byte character is cut the same way on both sides. Decoding back uses "replace", which is what a shell would hand to a terminal.

`"$COMMENTS" == "[]"` IS A STRING COMPARISON on gh's raw stdout, not a check that
the parsed array is empty. `gh api --paginate` prints exactly `[]` for an empty list, so the two agree; a whitespace-formatted empty array would take the other branch on both sides, which is why the raw text is compared here as well.
"""

import json
import os
import re
import subprocess
import sys
import time

from rediacc_ci.controls import Controls

# Patterns for low-effort replies that don't count as real responses. These are
# case-insensitive and match the entire reply (with optional punctuation).
LOW_EFFORT_PATTERNS = (
    "acknowledged",
    "ack",
    "ok",
    "okay",
    "understood",
    "noted",
    "done",
    "fixed",
    "will do",
    "will fix",
    "got it",
    "thanks",
    "thank you",
    "ty",
    "thx",
    "yes",
    "no",
    "sure",
    "agreed",
    "makes sense",
    "good point",
    "right",
    "correct",
    "i see",
    "see above",
    "addressed",
    "updated",
    "changed",
    "applied",
)

# The inline floor. See the port notes for why it is not the summary floor.
INLINE_MIN_CHARS = 10

# "A reply to the whole summary must clear a higher bar than a one-line inline thread. Same floor check-review-report-replies.sh uses for the same reason."
SUMMARY_MIN_CHARS = 30
# "...and one that only clears that floor still has to prove it is ABOUT the review, which it does one of two ways (see the reply rule below)."
SUMMARY_LONGFORM_CHARS = 200

TRAILING_PUNCT = re.compile(r"[.!?]*$")

# The two summary keys. The fence is a PRODUCER CONSTANT; the heading is the weaker second key for a pass that produced no fence.
FENCE_NEEDLE = "json:review-findings"
VERDICT_HEADING = re.compile(r"^[ \t\n\r\f\v]*#{1,3}[ \t\n\r\f\v]*Review verdict", re.IGNORECASE)

GH_ATTEMPTS = 3
GH_SLEEP_FACTOR = 3


def is_low_effort_reply(reply: str, min_chars: int = INLINE_MIN_CHARS) -> bool:
    """True when the reply is a stock acknowledgement or shorter than `min_chars`.

    NORMALIZED FIRST: lowercased, trimmed, trailing `.!?` removed, exactly as the twin's three `sed`s do it. "Done." and "done" are therefore the same answer, which is the point.
    """
    normalized = TRAILING_PUNCT.sub("", reply.lower().strip())
    if normalized in LOW_EFFORT_PATTERNS:
        return True
    return len(normalized) < min_chars


def gh_json(what: str, argv: list[str], *, sleeper=time.sleep, binary: str = "gh") -> str | None:
    """`gh_json` from `.ci/scripts/lib/common.sh`: status AND parseable body, 3 tries.

    Returns None after three failures, NEVER an empty list: "a gh failure produced an empty review list ... and the gate printed 'No review comments found - OK'."
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
            _warn(
                "%s: gh call failed or returned unusable output (attempt %d/%d), retrying..."
                % (what, attempt, GH_ATTEMPTS)
            )
            sleeper(attempt * GH_SLEEP_FACTOR)
        attempt += 1
    _error("%s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc))
    if last_stderr:
        for line in last_stderr.rstrip("\n").split("\n"):
            print("    %s" % line, file=sys.stderr)
    return None


def _colour() -> bool:
    """`common.sh:18`: colour when STDERR is a tty and NO_COLOR is unset."""
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(sys.stderr.isatty())
    except (AttributeError, ValueError):
        return False


def _warn(message: str) -> None:
    prefix = "\033[1;33m⚠\033[0m" if _colour() else "⚠"
    print("%s %s" % (prefix, message), file=sys.stderr)


def _error(message: str) -> None:
    prefix = "\033[0;31m✗\033[0m" if _colour() else "✗"
    print("%s %s" % (prefix, message), file=sys.stderr)


def clip(text: str, limit: int) -> str:
    """`head -c <limit>` and `${var:0:limit}`: BYTES, not characters.

    Both are byte operations under `LC_ALL=C`, which the differential pins, so the
    port slices the UTF-8 encoding and decodes with "replace" -- which is what a shell hands to a terminal when it cuts a multi-byte character in half.
    """
    return text.encode("utf-8")[:limit].decode("utf-8", "replace")


def inline_findings(comments: list[dict]) -> tuple[list[str], list[str], int]:
    """(unreplied lines, low-effort lines, original count) for surface 1.

    TWO LISTS, NOT ONE, and the twin counts them differently (`/2` and `/3`) because the low-effort entry carries a third explanatory line. Collapsing them would change both printed counts.
    """
    replies = [c for c in comments if c.get("in_reply_to_id") is not None]
    originals = [c for c in comments if c.get("in_reply_to_id") is None]

    substantive: set = set()
    for reply in replies:
        if not is_low_effort_reply(reply.get("body") or ""):
            substantive.add(reply.get("in_reply_to_id"))

    unreplied: list[str] = []
    low_effort: list[str] = []
    for comment in originals:
        comment_id = comment.get("id")
        if comment_id in substantive:
            continue
        path = comment.get("path")
        line = comment.get("line")
        if line is None:
            line = comment.get("original_line")
        if line is None:
            line = "N/A"
        author = ((comment.get("user") or {}).get("login")) or ""
        body = clip(comment.get("body") or "", 100)
        has_any = any(r.get("in_reply_to_id") == comment_id for r in replies)
        if has_any:
            low_effort.append("  - %s:%s by @%s" % (path, line, author))
            low_effort.append('    "%s..."' % body)
            low_effort.append("    (Reply was low-effort - please provide a substantive response)")
        else:
            unreplied.append("  - %s:%s by @%s" % (path, line, author))
            unreplied.append('    "%s..."' % body)
    return unreplied, low_effort, len(originals)


def newest_summary(comments: list[dict]) -> dict | None:
    """The newest github-actions comment that is a review SUMMARY.

    THE BOOKKEEPING EXCLUSION IS NOT COSMETIC. `<!-- claude-reviewed: <sha> -->` and `<!-- claude-review-attempt: ... -->` are STATE, and mistaking one for a verdict awaiting an answer would block every PR the pipeline has touched.
    """
    matches = []
    for comment in comments:
        login = ((comment.get("user") or {}).get("login")) or ""
        body = comment.get("body") or ""
        if "github-actions" not in login:
            continue
        if body.startswith("<!--"):
            continue
        if FENCE_NEEDLE in body or VERDICT_HEADING.search(body):
            matches.append(comment)
    if not matches:
        return None
    # `sort_by(.created_at) | last`: stable, and the LAST of equal keys.
    ordered = sorted(matches, key=lambda c: c.get("created_at") or "")
    return ordered[-1]


def summary_reply(comments: list[dict], summary: dict) -> dict | None:
    """The first comment satisfying clauses (a) to (d) for the summary."""
    author = ((summary.get("user") or {}).get("login")) or ""
    created = summary.get("created_at") or ""
    summary_id = str(summary.get("id"))
    candidates = [
        comment
        for comment in comments
        if (((comment.get("user") or {}).get("login")) or "") != author
        and (comment.get("created_at") or "") > created
    ]
    for candidate in sorted(candidates, key=lambda c: c.get("created_at") or ""):
        body = candidate.get("body") or ""
        if is_low_effort_reply(body, SUMMARY_MIN_CHARS):
            continue
        if summary_id in body or len(body) >= SUMMARY_LONGFORM_CHARS:
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 when both surfaces are addressed, 1 otherwise."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    if not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"):
        print("GH_TOKEN or GITHUB_TOKEN is required")
        return 1

    pr_number = os.environ.get("PR_NUMBER")
    if not pr_number:
        print("PR_NUMBER not set - skipping review comments check (not a pull request)")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY") or "rediacc/console"

    print("Checking review comments for PR #%s..." % pr_number)

    unreplied: list[str] = []
    low_effort: list[str] = []
    original_count = 0

    # ---- SURFACE 1: inline review threads ---------------------------------
    body = gh_json(
        "review comments for PR #%s" % pr_number,
        ["api", "repos/%s/pulls/%s/comments" % (repo, pr_number), "--paginate"],
    )
    if body is None:
        print(file=sys.stderr)
        print(
            "Cannot certify that review comments were addressed, because the comments",
            file=sys.stderr,
        )
        print(
            "could not be fetched. Failing closed rather than reporting a clean PR.",
            file=sys.stderr,
        )
        return 1

    if body == "[]":
        print("No inline review comments found - OK")
    else:
        comments = json.loads(body)
        unreplied, low_effort, original_count = inline_findings(comments)
        if not unreplied and not low_effort:
            print(
                "All %d inline review comments have been addressed with substantive replies - OK"
                % original_count
            )

    # ---- SURFACE 2: the top-level review summary --------------------------
    issue_body = gh_json(
        "issue comments for PR #%s" % pr_number,
        ["api", "repos/%s/issues/%s/comments" % (repo, pr_number), "--paginate"],
    )
    if issue_body is None:
        print(file=sys.stderr)
        print(
            "Cannot certify that the review summary was addressed, because the PR's",
            file=sys.stderr,
        )
        print("issue comments could not be fetched. Failing closed.", file=sys.stderr)
        return 1

    issue_comments = json.loads(issue_body)
    summary = newest_summary(issue_comments)
    summary_unaddressed = False
    summary_id = summary_author = summary_created = summary_head = ""
    if summary is None:
        print("No top-level review summary found - OK")
    else:
        summary_id = str(summary.get("id"))
        summary_author = ((summary.get("user") or {}).get("login")) or ""
        summary_created = summary.get("created_at")
        # `jq -r '.body' | tr '\n' ' '` ADDS A TRAILING SPACE, because `jq -r` terminates its output with a newline and `tr` turns that newline into a space too. The excerpt therefore ends `... "` rather than `..."`, and a port that translated only the body's INTERNAL newlines produced a one-character difference on every summary. Found by the differential.
        summary_head = clip(((summary.get("body") or "") + "\n").replace("\n", " "), 120)
        reply = summary_reply(issue_comments, summary)
        if reply is not None:
            print(
                "Top-level review summary (comment %s) answered by comment %s - OK"
                % (summary_id, reply.get("id"))
            )
        else:
            summary_unaddressed = True

    if not unreplied and not low_effort and not summary_unaddressed:
        return 0

    has_issues = False
    print()
    print("============================================================")
    print("  Review Comments Require Attention")
    print("============================================================")

    if unreplied:
        has_issues = True
        print()
        print("UNREPLIED COMMENTS (%d):" % (len(unreplied) // 2))
        print()
        for line in unreplied:
            print(line)

    if low_effort:
        has_issues = True
        print()
        print("LOW-EFFORT REPLIES (%d):" % (len(low_effort) // 3))
        print("These replies don't count as addressing the feedback:")
        print()
        for line in low_effort:
            print(line)

    if unreplied or low_effort:
        print()
        print("------------------------------------------------------------")
        print("Please address all review comments with SUBSTANTIVE replies.")
        print()
        print("Low-effort replies like 'Acknowledged', 'OK', 'Done', 'Fixed'")
        print("etc. are NOT accepted. Explain what you did or why you")
        print("disagree with the feedback.")
        print()
        print("Examples of good replies:")
        print("  - 'Fixed by adding null check in validateInput()'")
        print("  - 'Refactored to use the existing helper as suggested'")
        print("  - 'Keeping as-is because X needs to happen before Y due to...'")
        print()
        print("To reply using gh CLI:")
        print()
        print("  # List unreplied comments (find the COMMENT_ID you need to reply to)")
        print("  gh api repos/%s/pulls/%s/comments \\" % (repo, pr_number))
        print("    --jq '.[] | select(.in_reply_to_id == null) | {id, path, line, body}'")
        print()
        print("  # Reply to a specific comment (NOTE: PR number is required in the path!)")
        print("  gh api repos/%s/pulls/%s/comments/{COMMENT_ID}/replies \\" % (repo, pr_number))
        print('    -X POST -f body="Your substantive reply here"')
        print()
        print("  # IMPORTANT: The endpoint is /pulls/{PR_NUMBER}/comments/{COMMENT_ID}/replies")
        print("  # NOT /pulls/comments/{COMMENT_ID}/replies (this will return 404)")
        print()
        print("Or reply directly on GitHub:")
        print("  https://github.com/%s/pull/%s" % (repo, pr_number))
        print("------------------------------------------------------------")

    if summary_unaddressed:
        has_issues = True
        print()
        print("UNANSWERED REVIEW SUMMARY (1):")
        print()
        print("  - comment %s by @%s, posted %s" % (summary_id, summary_author, summary_created))
        print("    https://github.com/%s/pull/%s#issuecomment-%s" % (repo, pr_number, summary_id))
        print('    "%s..."' % summary_head)
        print()
        print("------------------------------------------------------------")
        print("WHY THIS BLOCKS. The automated review posts its verdict, its")
        print("severity-ordered defects, its nits and its coverage map as ONE")
        print("top-level comment. Only the top findings are mirrored inline")
        print("(capped at 20, and any whose line is not in the diff is dropped),")
        print("so resolving the inline threads does NOT address the summary.")
        print("Top-level comments have no thread and nothing to resolve, so the")
        print("only evidence anyone read it is a later comment answering it.")
        print("There is none.")
        print()
        print("WHAT A SUBSTANTIVE REPLY MUST CONTAIN. Go finding by finding, in")
        print("the summary's own order, and for each one state exactly one of:")
        print("  - fixed: what changed and in which commit")
        print("  - deferred: where it is tracked (issue or worklist id) and why")
        print("  - disagreed: the reason, concretely, not 'out of scope'")
        print("Answer the nits and the coverage map too: if the summary says an")
        print("area went unreviewed, say whether that is acceptable and why.")
        print("It must be posted by someone other than @%s (a" % summary_author)
        print("second comment from the reviewer is not an answer to the first),")
        print(
            "and it must either cite %s or run past %s characters."
            % (summary_id, SUMMARY_LONGFORM_CHARS)
        )
        print()
        print("To answer using gh CLI:")
        print()
        print("  # 1. Read the full summary first - the excerpt above is 120 chars")
        print("  gh api repos/%s/issues/comments/%s --jq .body" % (repo, summary_id))
        print()
        print("  # 2. Post the answer as a NEW top-level comment")
        print("  gh api repos/%s/issues/%s/comments -X POST \\" % (repo, pr_number))
        print('    -f body="Re: review summary %s' % summary_id)
        print()
        print("  - <finding 1 title>: fixed in <sha> - <what changed>")
        print("  - <finding 2 title>: not changing - <why>")
        print("  - <nit>: deferred to <issue/worklist id>")
        print()
        print('  Coverage: <the areas the summary flagged as unreviewed, and your call on them>"')
        print()
        print("  # IMPORTANT: a top-level comment has NO replies endpoint. All three")
        print("  # of these are wrong, and the first two return 404 (verified):")
        print(
            "  #   repos/%s/issues/%s/comments/%s/replies   -> 404" % (repo, pr_number, summary_id)
        )
        print(
            "  #   repos/%s/pulls/%s/comments/%s/replies    -> 404" % (repo, pr_number, summary_id)
        )
        print("  #     (that path is real, but only for INLINE comment ids;")
        print("  #      %s is an ISSUE comment id and is not found there)" % summary_id)
        print("  #   repos/%s/issues/comments/%s  -> GET/PATCH only. That" % (repo, summary_id))
        print("  #     is the EDIT endpoint for the summary itself; posting there would")
        print("  #     overwrite the review, not answer it.")
        print()
        print("Or comment directly on GitHub:")
        print("  https://github.com/%s/pull/%s#issuecomment-%s" % (repo, pr_number, summary_id))
        print("------------------------------------------------------------")

    return 1 if has_issues else 0


def selftest() -> int:
    """Both directions on every rule this gate has.

    THE TWO FLOORS ARE DIFFERENT AND BOTH ARE ASSERTED. The inline floor is 10 and the summary floor is 30; a port that unified them would silently tighten one gate or loosen the other, and no differential over one PR would notice.
    """
    low_effort_cases = [
        ("a stock acknowledgement is low effort", ("Acknowledged", INLINE_MIN_CHARS), True),
        ("case and punctuation are normalized away", ("DONE.", INLINE_MIN_CHARS), True),
        ("a 9-character reply is under the inline floor", ("x" * 9, INLINE_MIN_CHARS), True),
        ("a 10-character reply clears it", ("x" * 10, INLINE_MIN_CHARS), False),
        # THE TWO FLOORS DIFFER, and this pair is the proof.
        (
            "the same 10 characters do NOT clear the summary floor",
            ("x" * 10, SUMMARY_MIN_CHARS),
            True,
        ),
        ("30 characters clear the summary floor", ("x" * 30, SUMMARY_MIN_CHARS), False),
        (
            "a substantive short-ish reply is not low effort",
            ("Fixed by adding a null check", INLINE_MIN_CHARS),
            False,
        ),
    ]
    bot = {"login": "github-actions[bot]"}
    human = {"login": "muhammed"}
    summary_cases = [
        (
            "the fence identifies a summary",
            [{"id": 1, "user": bot, "created_at": "t1", "body": "x ```json:review-findings\n[]"}],
            1,
        ),
        (
            "a verdict heading identifies one too",
            [{"id": 2, "user": bot, "created_at": "t1", "body": "## Review verdict: approve"}],
            2,
        ),
        (
            "the heading match is case-insensitive",
            [{"id": 3, "user": bot, "created_at": "t1", "body": "### review VERDICT: block"}],
            3,
        ),
        # THE BOOKKEEPING EXCLUSION. State, not findings.
        (
            "a bookkeeping marker is NOT a summary",
            [{"id": 4, "user": bot, "created_at": "t1", "body": "<!-- claude-reviewed: abc -->"}],
            None,
        ),
        (
            "a human comment quoting the fence is NOT a summary",
            [{"id": 5, "user": human, "created_at": "t1", "body": "json:review-findings"}],
            None,
        ),
        (
            "ordinary PR chatter is NOT a summary",
            [{"id": 6, "user": bot, "created_at": "t1", "body": "deploy preview ready"}],
            None,
        ),
        ("no comments at all", [], None),
    ]

    floor = len(low_effort_cases) + len(summary_cases) + 9
    ctl = Controls("review-comments", floor=floor)

    for label, (text, min_chars), want in low_effort_cases:
        ctl.check("low-effort: %s" % label, is_low_effort_reply(text, min_chars), want)
    for label, comments, want in summary_cases:
        found = newest_summary(comments)
        ctl.check("summary: %s" % label, None if found is None else found["id"], want)

    # NEWEST WINS on the summary too.
    older = {"id": 10, "user": bot, "created_at": "2026-08-01T00:00:00Z", "body": FENCE_NEEDLE}
    newer = {"id": 11, "user": bot, "created_at": "2026-08-02T00:00:00Z", "body": FENCE_NEEDLE}
    ctl.check("only the newest summary is gated", newest_summary([older, newer])["id"], 11)

    # THE SUMMARY REPLY RULE, all four clauses, in both directions.
    summary = {
        "id": 5189236393,
        "user": bot,
        "created_at": "2026-08-05T10:00:00Z",
        "body": FENCE_NEEDLE,
    }
    long_reply = "y" * SUMMARY_LONGFORM_CHARS
    ctl.check(
        "clause (a): a long comment from the reviewer is not an answer",
        summary_reply(
            [
                summary,
                {"id": 12, "user": bot, "created_at": "2026-08-05T10:00:14Z", "body": long_reply},
            ],
            summary,
        ),
        None,
    )
    ctl.check(
        "clause (b): a long comment posted before it is not an answer",
        summary_reply(
            [
                summary,
                {"id": 13, "user": human, "created_at": "2026-08-05T09:00:00Z", "body": long_reply},
            ],
            summary,
        ),
        None,
    )
    ctl.check(
        "clause (c): a stock acknowledgement is not an answer",
        summary_reply(
            [
                summary,
                {"id": 14, "user": human, "created_at": "2026-08-05T11:00:00Z", "body": "Noted"},
            ],
            summary,
        ),
        None,
    )
    ctl.check(
        "clause (d): a substantive but unrelated comment is not an answer",
        summary_reply(
            [
                summary,
                {
                    "id": 15,
                    "user": human,
                    "created_at": "2026-08-05T11:00:00Z",
                    "body": "preview looks good, merging",
                },
            ],
            summary,
        ),
        None,
    )
    answered = summary_reply(
        [
            summary,
            {"id": 16, "user": human, "created_at": "2026-08-05T11:00:00Z", "body": long_reply},
        ],
        summary,
    )
    ctl.check("a long-form answer from another author counts", answered["id"], 16)
    cited = summary_reply(
        [
            summary,
            # PAST THE 30-CHARACTER FLOOR AND WELL SHORT OF 200: the citation is what makes it count, and the substance check runs FIRST, so a 24-character citation would be rejected as low effort before clause (d) ever saw it. That is the twin's order, and getting it wrong here is how a control asserts the opposite of the code.
            {
                "id": 17,
                "user": human,
                "created_at": "2026-08-05T11:00:00Z",
                "body": "Re: 5189236393 all three findings are fixed",
            },
        ],
        summary,
    )
    ctl.check("a mid-length answer citing the summary id counts", cited["id"], 17)

    # THE INLINE SURFACE, both directions plus the low-effort split.
    inline = [
        {
            "id": 1,
            "in_reply_to_id": None,
            "path": "a.ts",
            "line": 3,
            "user": human,
            "body": "please rename",
        },
        {
            "id": 2,
            "in_reply_to_id": 1,
            "user": human,
            "body": "Renamed to validateInput and added the null check",
        },
        {
            "id": 3,
            "in_reply_to_id": None,
            "path": "b.ts",
            "line": 4,
            "user": human,
            "body": "leaks a handle",
        },
        {"id": 4, "in_reply_to_id": 3, "user": human, "body": "Done"},
        {
            "id": 5,
            "in_reply_to_id": None,
            "path": "c.ts",
            "line": 5,
            "user": human,
            "body": "unanswered",
        },
    ]
    unreplied, low, count = inline_findings(inline)
    ctl.check("an answered thread is not reported", count, 3)
    ctl.check("a low-effort reply is its own category, three lines", len(low), 3)
    ctl.check("an unanswered thread is two lines", len(unreplied), 2)

    # `head -c` IS BYTES.
    ctl.check("clip cuts bytes, not characters", clip("a" * 150, 100), "a" * 100)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
