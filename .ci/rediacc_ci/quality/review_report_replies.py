r"""The newest automated review REPORT (an issue comment) must have been answered.

Ported from `.ci/scripts/quality/check-review-report-replies.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live.

WHY THERE ARE TWO GATES ON ONE SURFACE, in the twin's own words, because this is
the paragraph that stops someone deleting one of them:

    The Claude review pipeline posts on two surfaces:
      1. Inline code comments (pulls/comments)  -> gated by check-review-comments.sh
      2. Top-level issue comments               -> gated HERE and by that same script

    Issue comments are flat: GitHub has no resolve/reply threading for them, so
    without a gate their findings can be silently ignored.

    WHY TWO SCRIPTS READ THE TOP-LEVEL SURFACE, AND WHY THAT IS NOT DUPLICATION.
    One review pass can leave TWO different top-level comments, produced by two
    different code paths and recognised by two different producer constants:

      - The reviewer's own summary, posted with `gh pr comment` because the prompt
        (review/prompts/initial.md:39) tells it to. Recognised by the
        ```json:review-findings fence. check-review-comments.sh owns that one.
      - The pipeline's report wrapper, posted by claude-review-gate.sh
        --post-report, or the action's own tracking comment. Recognised by the
        "**Claude finished" header. THIS script owns that one.

    Neither key implies the other. On PR #551 the wrapper (5189238220) carried no
    fence at all, and the fence lived only in the reviewer's own summary
    (5189236393). A gate keyed on one is blind to a pass that produced only the
    other, so the two scripts are complementary coverage, not two checks of the
    same thing.

    The obligation, though, is ONE: answer this review pass. Both scripts therefore
    apply the SAME reply rule (below), so a single substantive reply posted after
    both comments satisfies both gates. test-review-status.sh drives both scripts
    against one fixture and asserts exactly that, because the moment they disagree
    this stops being coverage and starts being a tax.

THE BUG THIS FILE CARRIED UNTIL 2026-08-05, verbatim, because it is the reason the
matcher is keyed the way it is:

    The report was matched by the "**Claude finished" header AND-ed with "carries
    the findings fence or a '### Review' heading". That second clause is a guess
    about the report's WORDING, not a constant any producer emits -- and the
    producer does not emit it: --post-report wraps whatever the model's final text
    happened to be. On #551 that text was a short wrap-up ("Posted the review.
    Summary of what I did:") with neither marker, so this gate found no report and
    exited 0 while an 8141-char verdict sat unanswered. Keyed off the header alone
    -- which IS a producer constant, written verbatim at claude-review-gate.sh:188
    -- it fires.

    NOTHING ELSE IS AND-ED ON. Every extra clause is another chance to describe the
    report differently from the way it is produced, which is exactly how this gate
    went blind. Only the NEWEST is gated: each pass supersedes the previous report,
    and re-litigating superseded ones would make a re-reviewed PR permanently
    unmergeable.

THE PER-EPIC FAN-OUT, and why it is a self-invocation rather than a loop:

    The review runs once per epic, so a PR posts one report per epic per round.
    Gating only the newest report across all of them would enforce the LAST epic's
    reply and silently excuse every other, which is worse than not gating: the
    unanswered ones look cleared.

    The rule that already governs this file is kept exactly: NEWEST WINS, so a
    superseded report is never re-litigated and a re-reviewed PR cannot become
    permanently unmergeable. It is now newest-PER-EPIC rather than newest overall.

    IMPLEMENTED AS A BOUNDED SELF-INVOCATION, deliberately, rather than by wrapping
    the 110 lines below in a loop. Those lines are the failure message and the reply
    rule, they are load-bearing and have been corrected twice after live misses
    (#551 among them), and re-indenting them to add a loop is a large diff over
    delicate code for no behavioural gain. Setting the prefix and re-entering runs
    the SAME code path per epic, so nothing below can drift between the flat and
    per-epic cases. REVIEW_EPIC_PREFIX being set is what terminates the recursion;
    it can only ever be one level deep.

    A PR with no epics (no snapshot, or a snapshot declaring none) takes the flat
    path unchanged, which is every PR that predates this feature.

THE GRAPHQL FALLBACK IS A SECOND INSTRUMENT, NOT A SOFTER VERDICT, and its
archaeology is the most easily-deleted paragraph in the file:

    It keeps this gate RUNNABLE while the REST API is degraded, and a gate that
    cannot run does not judge a merge, it blocks every one of them.

    Added during the GitHub incident of 2026-08-17 (status page: "Issues is
    experiencing degraded performance", ~20% error rates site-wide). This endpoint
    returned 404 for repos/rediacc/{renet,account,elite}/issues/<n> while the public
    rediacc/console answered 200, which looks exactly like a private-repo
    permissions property and is NOT one: sampled 8x per repo, the private repo
    passed ONCE and failed seven times while the public one passed 8/8. One success
    is the whole proof -- a token that lacked access would have failed all eight. So
    the split was load, not visibility, and the earlier version of this comment said
    otherwise. Do not "fix" a token.

    GraphQL reads the same comment thread and kept answering throughout. It is a
    different transport for identical data, so it cannot turn a failing PR into a
    passing one: if BOTH instruments fail we still fail closed below.

    Two shape notes, both already tolerated by the logic beneath: GraphQL reports
    the bot as `github-actions` where REST says `github-actions[bot]` (the filter
    uses contains(), so either matches), and `first: 100` caps a single page -- far
    above any real PR here, and an under-read can only HIDE a reply, i.e. fail
    closed, never invent one.

WHAT COUNTS AS A REPLY, all four clauses, because clause (a) is the one that makes
the gate able to fire at all:

    (a) a DIFFERENT author from the reporter. Load-bearing: the pipeline posts
        several comments in a row under one identity (on #551 the reviewed-SHA
        marker landed 4 seconds after this report and is long enough to clear every
        substance test), so without this the review answers itself and the gate can
        never fire.
    (b) posted after it, compared in jq on GitHub's ISO-8601 strings, so bash's
        locale-dependent `>` is never involved.
    (c) substantive: past SUMMARY_MIN_CHARS and not a stock acknowledgement.
    (d) demonstrably about the review: it cites the report id (or its
        #issuecomment-<id> anchor), or it is long-form.

    (d) used to be a hard requirement to cite the id. It is relaxed for the same
    reason its sibling relaxed it: the real answer on #551 (5190623031, 2856 chars,
    per-finding) cites no id, and a gate that calls that unaddressed is a gate that
    gets switched off.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWO CONSTANTS MUST MATCH THEIR TWINS IN `review_comments.py`, and the twin says
why: "THESE TWO MUST MATCH check-review-comments.sh's variables of the same names.
That is what makes one reply clear both gates; test-review-status.sh parses both
files and fails if they drift apart." They are therefore duplicated here rather
than imported, exactly as the bash pair duplicates them, and both ports assert the
agreement in their own tests.

THE SELF-INVOCATION BECOMES A RECURSIVE `main()` CALL, not a subprocess. The twin
re-executes `"$0" "$@"` with `REVIEW_EPIC_PREFIX` set; the port sets the same
variable in `os.environ` and calls `main` again. The recursion is bounded by the
same condition -- the variable being set is what stops the fan-out -- so it is one
level deep on both sides, and the printed output is identical because it is the
same code path.

`review_epic_ids` IS REIMPLEMENTED, INCLUDING ITS ROOT ANCHOR. The twin's helper
resolves `agent/pr/<branch-with-slashes-dashed>.md` against the REPOSITORY ROOT and
its comment says why: "It used to be a bare relative path, so the answer depended on
the caller's CWD: a gate invoked from a subdirectory saw no epics and silently took
the flat path, which looks exactly like a PR that declares none."
`WORKLIST_PUBLISH_ROOT` overrides the root, and that override is honoured here too.

jq's `contains()` IS A SUBSTRING TEST on strings, which is why `github-actions`
matches `github-actions[bot]`. A port using equality would be blind to the REST
spelling, and one using `startswith` would be blind to nothing today and to a
future prefix change tomorrow. Substring, as written.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time

from rediacc_ci.controls import Controls

# "The report header. A PRODUCER CONSTANT, not a wording guess: claude-review-gate.sh:188 writes it verbatim, and the Claude Code action's own tracking comment uses the same prefix (comment-logic.ts, quoted at claude-review-gate.sh:153). An in-progress comment cannot match it -- the word is 'finished'."
REPORT_PREFIX = "**Claude finished"

EPIC_PREFIX_ENV = "REVIEW_EPIC_PREFIX"
PUBLISH_ROOT_ENV = "WORKLIST_PUBLISH_ROOT"

# THESE TWO MUST MATCH `review_comments.py`. See the port notes.
SUMMARY_MIN_CHARS = 30
SUMMARY_LONGFORM_CHARS = 200

# Low-effort filter, same philosophy as check-review-comments.sh: a reply must say what was done (or why not), not just acknowledge.
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

# `sed 's/[.!?]*$//'` after lowercasing and trimming.
TRAILING_PUNCT = re.compile(r"[.!?]*$")

# `grep -oE '^`?PR-TASK:[[:space:]]*[0-9a-f]{6,32}`?$'` then the id out of it.
EPIC_LINE = re.compile(r"^`?PR-TASK:[ \t]*[0-9a-f]{6,32}`?$")
EPIC_ID = re.compile(r"[0-9a-f]{6,32}")

GH_ATTEMPTS = 3
GH_SLEEP_FACTOR = 3

GQL = (
    "query($owner:String!,$name:String!,$number:Int!)"
    "{repository(owner:$owner,name:$name){pullRequest(number:$number)"
    "{comments(first:100){nodes{databaseId body createdAt author{login}}}}}}"
)


def is_low_effort_reply(reply: str, min_chars: int = SUMMARY_MIN_CHARS) -> bool:
    """True when the reply is a stock acknowledgement or too short.

    THE DEFAULT FLOOR HERE IS 30, NOT 10. `check-review-comments.sh`'s function of
    the same name defaults to 10, because a reply to ONE inline thread is allowed
    to be short; a reply to a whole review report is not. Two functions with one
    name and different defaults is exactly the kind of thing a port collapses by
    accident, so the difference is stated at both ends.
    """
    normalized = TRAILING_PUNCT.sub("", reply.lower().strip())
    if normalized in LOW_EFFORT_PATTERNS:
        return True
    return len(normalized) < min_chars


def review_epic_ids(branch: str, root: str) -> list[str]:
    """The epic ids declared for `branch`, from `<root>/agent/pr/<branch>.md`.

    ANCHORED TO THE REPOSITORY ROOT, never to the caller's directory. A bare
    relative path made this return nothing when the gate ran from a subdirectory,
    which looks exactly like a PR that declares no epics.
    """
    if not branch:
        return []
    snapshot = os.path.join(root, "agent", "pr", "%s.md" % branch.replace("/", "-"))
    if not os.path.isfile(snapshot):
        return []
    out: list[str] = []
    with open(snapshot, encoding="utf-8", errors="replace") as handle:
        for line in handle.read().split("\n"):
            if EPIC_LINE.match(line):
                found = EPIC_ID.search(line)
                if found:
                    out.append(found.group(0))
    return out


def newest_report(comments: list[dict], prefix: str) -> dict | None:
    """The newest github-actions comment whose body starts with `prefix`.

    NOTHING ELSE IS AND-ED ON, and the module docstring says what an extra clause
    cost. `contains("github-actions")` is a SUBSTRING test, so the REST spelling
    `github-actions[bot]` and the GraphQL spelling `github-actions` both match.
    """
    matches = [
        comment
        for comment in comments
        if "github-actions" in (((comment.get("user") or {}).get("login")) or "")
        and (comment.get("body") or "").startswith(prefix)
    ]
    if not matches:
        return None
    # `sorted(...)[-1]`, NOT `max(...)`. jq's `sort_by(...) | last` takes the LAST of equal keys and Python's `sorted` is stable, so two reports sharing a
    # created_at resolve the same way on both sides; `max` returns the FIRST of
    # equal keys and would name a different comment id in the success line.
    ordered = sorted(matches, key=lambda c: c.get("created_at") or "")
    return ordered[-1]


def find_reply(comments: list[dict], report: dict) -> dict | None:
    """The first comment satisfying all four clauses (a) to (d).

    ORDERED BY `created_at` ASCENDING and taking the FIRST match, which is what the
    twin's `sort_by(.created_at) | .[]` plus `break` does. Taking the newest instead
    would name a different comment id in the success line for the same PR.
    """
    author = ((report.get("user") or {}).get("login")) or ""
    created = report.get("created_at") or ""
    report_id = str(report.get("id"))
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
        if report_id in body or len(body) >= SUMMARY_LONGFORM_CHARS:
            return candidate
    return None


def gh_json(what: str, argv: list[str], *, sleeper=time.sleep, binary: str = "gh") -> str | None:
    """`gh_json` from `.ci/scripts/lib/common.sh`: status AND parseable body, 3 tries."""
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
            print(
                "\033[1;33m⚠\033[0m %s: gh call failed or returned unusable output "
                "(attempt %d/%d), retrying..." % (what, attempt, GH_ATTEMPTS)
                if _colour()
                else "⚠ %s: gh call failed or returned unusable output (attempt %d/%d), "
                "retrying..." % (what, attempt, GH_ATTEMPTS),
                file=sys.stderr,
            )
            sleeper(attempt * GH_SLEEP_FACTOR)
        attempt += 1
    print(
        "\033[0;31m✗\033[0m %s: gh failed after %d attempts (last exit %d)."
        % (what, GH_ATTEMPTS, rc)
        if _colour()
        else "✗ %s: gh failed after %d attempts (last exit %d)." % (what, GH_ATTEMPTS, rc),
        file=sys.stderr,
    )
    if last_stderr:
        for line in last_stderr.rstrip("\n").split("\n"):
            print("    %s" % line, file=sys.stderr)
    return None


def _colour() -> bool:
    """`common.sh:18`: colour when STDERR is a tty and NO_COLOR is unset.

    Written out rather than delegated to `rediacc_ci.log` because this gate's other
    output is bare `echo`, and mixing the two loggers would produce a file whose
    colour rules differ line by line.
    """
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(sys.stderr.isatty())
    except (AttributeError, ValueError):
        return False


def _branch() -> str:
    """`PR_HEAD_REF`, then `GITHUB_HEAD_REF`, then `git branch --show-current`."""
    for name in ("PR_HEAD_REF", "GITHUB_HEAD_REF"):
        value = os.environ.get(name)
        if value:
            return value
    proc = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 answered or nothing to answer, 1 unanswered or unreadable."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    # ---- the per-epic fan-out, one level deep ------------------------------
    if not os.environ.get(EPIC_PREFIX_ENV):
        branch = _branch()
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
        )
        root = os.environ.get(PUBLISH_ROOT_ENV) or (
            proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "."
        )
        epics = review_epic_ids(branch, root)
        if epics:
            print("Per-epic review reports: %d epic(s) declared for %s" % (len(epics), branch))
            rc = 0
            unanswered: list[str] = []
            for epic in epics:
                print()
                print("--- epic %s ---" % epic)
                os.environ[EPIC_PREFIX_ENV] = "**Claude finished (epic %s)" % epic
                try:
                    if main(args) != 0:
                        rc = 1
                        unanswered.append(epic)
                finally:
                    os.environ.pop(EPIC_PREFIX_ENV, None)
            if unanswered:
                print()
                print("============================================================")
                print("  %d of %d epic report(s) unanswered:" % (len(unanswered), len(epics)))
                for epic in unanswered:
                    print("    %s" % epic)
                print("============================================================")
            return rc

    # One epic's header when fanned out above; the flat header otherwise.
    prefix = os.environ.get(EPIC_PREFIX_ENV) or REPORT_PREFIX

    if not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"):
        print("GH_TOKEN or GITHUB_TOKEN is required")
        return 1

    pr_number = os.environ.get("PR_NUMBER")
    if not pr_number:
        print("PR_NUMBER not set - skipping review report reply check (not a pull request)")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY") or "rediacc/console"

    print("Checking review report replies for PR #%s..." % pr_number)

    body = gh_json(
        "issue comments for PR #%s" % pr_number,
        ["api", "repos/%s/issues/%s/comments" % (repo, pr_number), "--paginate"],
    )
    if body is None:
        # A SECOND INSTRUMENT, not a softer verdict. See the module docstring for the 2026-08-17 incident that produced it.
        raw = gh_json(
            "issue comments for PR #%s (graphql fallback)" % pr_number,
            [
                "api",
                "graphql",
                "-f",
                "query=%s" % GQL,
                "-f",
                "owner=%s" % repo.split("/", 1)[0],
                "-f",
                "name=%s" % repo.rsplit("/", 1)[-1],
                "-F",
                "number=%s" % pr_number,
            ],
        )
        if raw is None:
            print(file=sys.stderr)
            print(
                "Cannot certify that the review report was addressed, because the PR's",
                file=sys.stderr,
            )
            print(
                "issue comments could not be fetched by EITHER the REST issues endpoint",
                file=sys.stderr,
            )
            print(
                "or the GraphQL fallback. Failing closed rather than reporting a clean PR.",
                file=sys.stderr,
            )
            return 1
        nodes = (
            (
                ((json.loads(raw).get("data") or {}).get("repository") or {}).get("pullRequest")
                or {}
            ).get("comments")
            or {}
        ).get("nodes") or []
        comments = [
            {
                "id": node.get("databaseId"),
                "body": node.get("body"),
                "created_at": node.get("createdAt"),
                "user": {"login": ((node.get("author") or {}).get("login")) or ""},
            }
            for node in nodes
        ]
    else:
        comments = json.loads(body)

    report = newest_report(comments, prefix)
    if report is None:
        print("No finished review report found - OK")
        return 0

    report_id = report.get("id")
    report_author = ((report.get("user") or {}).get("login")) or ""
    report_created = report.get("created_at")

    reply = find_reply(comments, report)
    if reply is not None:
        print(
            "Newest review report (comment %s) answered by comment %s - OK"
            % (report_id, reply.get("id"))
        )
        return 0

    print()
    print("============================================================")
    print("  Review Report Requires a Reply")
    print("============================================================")
    print()
    print("The newest automated review report has not been addressed:")
    print()
    print("  - comment %s by @%s, posted %s" % (report_id, report_author, report_created))
    print("    https://github.com/%s/pull/%s#issuecomment-%s" % (repo, pr_number, report_id))
    print()
    print("------------------------------------------------------------")
    print("WHY THIS BLOCKS. This is the pipeline's report for the head it")
    print("reviewed. It is a top-level comment, so it has no thread and")
    print("nothing to resolve: the only evidence anyone read it is a")
    print("later comment answering it. There is none.")
    print()
    print("READ THE REVIEWER'S OWN SUMMARY TOO. The same pass usually")
    print("posts a SEPARATE summary comment carrying the findings, and")
    print("this report can be just a wrap-up. List both before replying:")
    print()
    print("  gh api repos/%s/issues/%s/comments --paginate \\" % (repo, pr_number))
    print("    --jq '.[] | select(.user.login | test(\"github-actions\")) | {id, created_at}'")
    print()
    print("WHAT A SUBSTANTIVE REPLY MUST CONTAIN. Go finding by finding")
    print("and for each one state exactly one of:")
    print("  - fixed: what changed and in which commit")
    print("  - deferred: where it is tracked (issue or worklist id) and why")
    print("  - disagreed: the reason, concretely, not 'out of scope'")
    print("It must be posted by someone other than @%s (a" % report_author)
    print("second comment from the pipeline is not an answer to the")
    print(
        "first), and it must either cite %s or run past %s characters."
        % (report_id, SUMMARY_LONGFORM_CHARS)
    )
    print()
    print("ONE reply covers this AND check-review-comments.sh's summary")
    print("check, as long as it is posted after both comments.")
    print()
    print("To answer using gh CLI:")
    print()
    print("  # 1. Read the full report first")
    print("  gh api repos/%s/issues/comments/%s --jq .body" % (repo, report_id))
    print()
    print("  # 2. Post the answer as a NEW top-level comment")
    print("  gh api repos/%s/issues/%s/comments -X POST \\" % (repo, pr_number))
    print('    -f body="Re: review report %s' % report_id)
    print()
    print("  - <finding 1 title>: fixed in <sha> - <what changed>")
    print("  - <finding 2 title>: not changing - <why>")
    print('  - <nit>: deferred to <issue/worklist id>"')
    print()
    print("  # IMPORTANT: a top-level comment has NO replies endpoint. Both of")
    print("  # these return 404 (verified against the live API):")
    print("  #   repos/%s/issues/%s/comments/%s/replies" % (repo, pr_number, report_id))
    print("  #   repos/%s/pulls/%s/comments/%s/replies" % (repo, pr_number, report_id))
    print("  #     (that path is real, but only for INLINE comment ids)")
    print("  # And repos/%s/issues/comments/%s is GET/PATCH only --" % (repo, report_id))
    print("  # the EDIT endpoint for the report itself. Posting there would")
    print("  # overwrite the review rather than answer it.")
    print()
    print("Or comment directly on GitHub:")
    print("  https://github.com/%s/pull/%s#issuecomment-%s" % (repo, pr_number, report_id))
    print("------------------------------------------------------------")
    return 1


def selftest() -> int:
    """Both directions on the matcher, the reply rule and the epic reader."""
    bot = {"login": "github-actions[bot]"}
    human = {"login": "muhammed"}
    report = {
        "id": 5189238220,
        "user": bot,
        "created_at": "2026-08-05T10:00:00Z",
        "body": "**Claude finished** reviewing.",
    }
    matcher_cases = [
        ("the header alone identifies a report", [report], REPORT_PREFIX, 5189238220),
        # THE 2026-08-05 BUG. A wrap-up with no fence and no heading must still be found: the extra clause is what made this gate blind on PR #551.
        (
            "a wrap-up with no fence and no heading is still a report",
            [dict(report, body="**Claude finished** Posted the review. Summary of what I did:")],
            REPORT_PREFIX,
            5189238220,
        ),
        # NEGATIVES: an in-progress comment, a human's comment, the wrong prefix.
        (
            "an in-progress comment is not a finished report",
            [dict(report, body="**Claude is working...**")],
            REPORT_PREFIX,
            None,
        ),
        (
            "a human comment with the header is not a report",
            [dict(report, user=human)],
            REPORT_PREFIX,
            None,
        ),
        (
            "an epic prefix does not match the flat header",
            [report],
            "**Claude finished (epic ab12cd)",
            None,
        ),
        (
            "the GraphQL spelling of the bot login still matches",
            [dict(report, user={"login": "github-actions"})],
            REPORT_PREFIX,
            5189238220,
        ),
        ("no comments at all", [], REPORT_PREFIX, None),
    ]
    long_reply = "y" * SUMMARY_LONGFORM_CHARS
    reply_cases = [
        (
            "a long-form reply from another author counts",
            [{"id": 9, "user": human, "created_at": "2026-08-05T11:00:00Z", "body": long_reply}],
            9,
        ),
        (
            "a short reply that CITES the report id counts",
            [
                {
                    "id": 9,
                    "user": human,
                    "created_at": "2026-08-05T11:00:00Z",
                    "body": "Re: 5189238220 all fixed in abc",
                }
            ],
            9,
        ),
        # CLAUSE (a), the load-bearing one: the pipeline must not answer itself.
        (
            "a long comment from the SAME author does not count",
            [{"id": 9, "user": bot, "created_at": "2026-08-05T11:00:00Z", "body": long_reply}],
            None,
        ),
        # CLAUSE (b).
        (
            "a long comment posted BEFORE the report does not count",
            [{"id": 9, "user": human, "created_at": "2026-08-05T09:00:00Z", "body": long_reply}],
            None,
        ),
        # CLAUSE (c).
        (
            "a stock acknowledgement does not count",
            [
                {
                    "id": 9,
                    "user": human,
                    "created_at": "2026-08-05T11:00:00Z",
                    "body": "Acknowledged",
                }
            ],
            None,
        ),
        # CLAUSE (d): substantive but unrelated.
        (
            "a substantive but unrelated comment does not count",
            [
                {
                    "id": 9,
                    "user": human,
                    "created_at": "2026-08-05T11:00:00Z",
                    "body": "preview looks good, merging tomorrow",
                }
            ],
            None,
        ),
        (
            "the EARLIEST qualifying reply is the one named",
            [
                {"id": 9, "user": human, "created_at": "2026-08-05T11:00:00Z", "body": long_reply},
                {"id": 10, "user": human, "created_at": "2026-08-05T12:00:00Z", "body": long_reply},
            ],
            9,
        ),
    ]

    floor = len(matcher_cases) + len(reply_cases) + 6
    ctl = Controls("review-report-replies", floor=floor)

    for label, comments, prefix, want in matcher_cases:
        found = newest_report(comments, prefix)
        ctl.check("report: %s" % label, None if found is None else found["id"], want)
    for label, comments, want in reply_cases:
        found = find_reply([report, *comments], report)
        ctl.check("reply: %s" % label, None if found is None else found["id"], want)

    # NEWEST WINS, so a superseded report is never re-litigated.
    older = dict(report, id=1, created_at="2026-08-04T10:00:00Z")
    ctl.check(
        "only the newest report is gated",
        newest_report([older, report], REPORT_PREFIX)["id"],
        5189238220,
    )

    # THE LOW-EFFORT FLOOR IS 30 HERE AND 10 IN THE INLINE GATE.
    ctl.check("a 29-character reply is low effort", is_low_effort_reply("x" * 29), True)
    ctl.check("a 30-character reply is not", is_low_effort_reply("x" * 30), False)
    ctl.check("'Done.' is low effort whatever its length", is_low_effort_reply("Done."), True)
    ctl.check("the two shared constants", (SUMMARY_MIN_CHARS, SUMMARY_LONGFORM_CHARS), (30, 200))

    # THE EPIC READER, both directions, without touching the real tree.
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "agent", "pr"))
        with open(os.path.join(tmp, "agent", "pr", "feat-x.md"), "w", encoding="utf-8") as handle:
            handle.write("`PR-TASK: ab12cd34`\nPR-TASK: ef56ab78\nnot a task line\n")
        ctl.check(
            "epic ids are read from the branch snapshot, slashes dashed",
            review_epic_ids("feat/x", tmp),
            ["ab12cd34", "ef56ab78"],
        )
        ctl.check("a branch with no snapshot declares no epics", review_epic_ids("other", tmp), [])

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
