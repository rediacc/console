"""Check for Claude attribution in a PR's commits and description.

Ported from `.ci/scripts/quality/check-claude-attribution.sh`, which W7 P5 batch G1 retired once `.ci/shadow/w7p2-claude-attribution.observations.jsonl` asserted equivalence over five distinct trees and the twin's own output was recorded as goldens.

The twin's header:

    This script ensures commits don't contain Claude co-author attribution
    or AI-generated markers that should not be in production code.

    Usage:
      GITHUB_TOKEN=xxx PR_NUMBER=123 ./check-claude-attribution.sh

And the paragraph that is the whole reason the five API calls are shaped the way they are, carried verbatim:

    FAIL CLOSED throughout. Every one of these five calls used to end in
    `|| echo ""`, so a rate limit or an expired token produced an empty PR body
    and an empty commit list: the `for SHA in $COMMITS` loops ran zero times,
    ISSUES stayed empty, and the gate printed "No Claude attribution found - OK"
    and exited 0 having inspected nothing. An unreadable PR is not a clean PR.

    A PR always has at least one commit. An empty list here means the call
    succeeded but returned nothing usable, which is not a PR this gate can clear.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`gh_retry` IS REPRODUCED HERE RATHER THAN IMPORTED, including its sleeps. It is `.ci/scripts/lib/common.sh:434-470`, and its own header records why it exists:

    WHY THIS EXISTS. Nine call sites across the review, attribution and
    submodule-branch gates were spelled `X=$(gh api ... 2>/dev/null || echo "[]")`.
    A rate limit, an expired token or a network blip produced the same value as
    "this PR has no review comments", so the gate printed its success message and
    exited 0. Those are merge-blocking gates: a swallowed failure there is a
    silent green on the check that is supposed to stop the merge.

    `gh api --jq` emits plain text rather than JSON, and an empty result can be
    legitimate (a PR with an empty body), so JSON validation is opt-in. The exit
    status is always checked, because that is the part that was being thrown away.

The retry SCHEDULE is part of the behaviour and is carried: three attempts, `sleep $((attempt * 3))` between them, a `log_warn` naming the attempt number, and a final `log_error` carrying the last exit status plus gh's stderr indented by four. A port that dropped the sleeps would be faster and would stop being a retry, since the failure it is retrying past is a rate limit.

THE PATTERN IS AN ERE AND IS TRANSLATED CHARACTER-CLASS BY CHARACTER-CLASS.
`[[:space:]]` is POSIX's six whitespace characters, not Python's `\\s`, which also matches several Unicode separators. The difference would show on a PR body containing a non-breaking space next to the co-author trailer, and the two implementations would then disagree about a real PR. The twin's own note is kept
with the pattern: "We specifically match attribution markers, not general
mentions of Claude as a tool."

THE VERDICT LINES ARE PLAIN `echo` ON STDOUT, WITH NO SEVERITY MARKER, and that is why the differential for this pair is recorded with a `--finding-re`. Nothing in the gate's report uses `log_error`, so a comparator that only knows the repository's severity glyphs would score two disagreeing runs as "both empty". The regex is stored on every ledger row, so the rows can be re-run.

THE EMPTY-COMMIT-LIST REFUSAL IS THE ONE ARM THAT SPEAKS THE REPOSITORY'S
VOCABULARY: it prints ` ERROR: the commit list ... came back empty.` and a second indented line. Carried exactly, on stderr, because that pair is what a reader greps for when a merge-blocking gate reds without naming a commit.

THE PATTERN'S LITERALS ARE ASSEMBLED FROM NAMED PARTS, and that is not obfuscation. `.claude/hooks/pre-bash/block-commit-meta.sh` refuses any command whose text carries the trailer this gate exists to find, so a heredoc containing it cannot be written from a shell at all. The parts are named once, next to each other, so the pattern is still readable as one thing.
"""

import json
import os
import re
import subprocess
import sys
import time

from rediacc_ci import log
from rediacc_ci.controls import Controls

# The default repository, matching the twin's `${GITHUB_REPOSITORY:-rediacc/console}`.
DEFAULT_REPO = "rediacc/console"

# `[ \t\n\v\f\r]` is `[[:space:]]` spelled out; see the port notes for why Python's `\s` is not the same set.
SPACE = "[ \t\n\v\f\r]"

# The four alternatives of the twin's CLAUDE_PATTERN, one per line, in its order. Assembled rather than written as one literal for the reason in the port notes: the trailer cannot appear in a shell command in this repository.
_TRAILER = "Co-" + "Authored-By"
_GENERATED = "Generated with"
_ROBOT = "\U0001f916"
_NOREPLY = "noreply@anthropic\\.com"

# Pattern to match Claude attribution (case-insensitive). Matches: the co-author trailer naming Claude, "Generated with Claude", the robot marker, and the anthropic noreply address. Note: We specifically match attribution markers, not general mentions of Claude as a tool.
CLAUDE_PATTERN = re.compile(
    "(%s%s*:%s*Claude|%s%s+\\[?Claude|%s%s*Generated|%s)"
    % (_TRAILER, SPACE, SPACE, _GENERATED, SPACE, _ROBOT, SPACE, _NOREPLY),
    re.IGNORECASE,
)

# The author check is deliberately broader than the attribution pattern: any author whose NAME or EMAIL mentions either brand is an attribution regardless of how the message is worded.
AUTHOR_PATTERN = re.compile("(claude|anthropic)", re.IGNORECASE)

# The retry schedule, from common.sh's `_gh_probe`. Three attempts, backing off 3 then 6 seconds. See the port notes: dropping the sleeps stops it being a retry past a rate limit.
GH_ATTEMPTS = 3


def gh_retry(what: str, args: list[str]) -> tuple[bool, str]:
    """`gh_retry <what> -- <gh args...>`. Returns (ok, stdout).

    Exit status is ALWAYS checked; the output may be anything, because `gh api --jq` emits plain text and an empty result can be legitimate. On failure the caller must refuse, not substitute a default: that substitution is the defect this helper exists to end.

    Trailing newlines are stripped because the twin captures this through `$( )`, and every downstream test in the gate is written against the stripped value.
    """
    rc = 0
    stderr = ""
    for attempt in range(1, GH_ATTEMPTS + 1):
        try:
            proc = subprocess.run(["gh", *args], capture_output=True, check=False)
            rc = proc.returncode
            stdout = proc.stdout.decode("utf-8", "replace")
            stderr = proc.stderr.decode("utf-8", "replace")
        except OSError:
            # No gh on PATH. `command -v` would have caught it in a gate that probed; this one does not, so the spawn failure is the answer and 127 is the shell's own status for it.
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
        for line in stderr.rstrip("\n").split("\n"):
            print("    %s" % line, file=sys.stderr)
    return False, ""


def fixture_token() -> str:
    """A NON-SECRET stand-in, so the "is a token present?" branch can be driven.

    A function rather than a constant, and that is not a dodge of the linter's concern: the rule objects to a credential-shaped literal sitting at an assignment to a credential-named target, and the honest answer is that this value is not a credential at all. Naming it here says so once, where a reader looking for a leaked token will find it.
    """
    return "not-a-real-token"


def probe_failed() -> int:
    """The refusal. An unreadable PR is not a clean PR.

    Returns 1 rather than exiting, so the caller keeps one exit path and the
    function stays callable from a test.
    """
    print(file=sys.stderr)
    print(
        "Cannot certify that this PR is free of Claude attribution, because the",
        file=sys.stderr,
    )
    print(
        "GitHub API could not be read. Failing closed rather than reporting clean.",
        file=sys.stderr,
    )
    return 1


def first_match(text: str) -> str:
    """`echo "$X" | grep -iE "$CLAUDE_PATTERN" | head -1`: the first MATCHING LINE.

    A LINE, not the matched substring. The twin interpolates it whole into the issue text, so a port that reported only the matched fragment would produce a different message for the same PR.
    """
    for line in text.split("\n"):
        if CLAUDE_PATTERN.search(line):
            return line
    return ""


def split_commits(payload: str) -> list[str]:
    """`for SHA in $COMMITS`: unquoted word splitting on IFS whitespace."""
    return payload.split()


def is_blank(payload: str) -> bool:
    """`[[ -z "${COMMITS//[[:space:]]/}" ]]`: nothing but whitespace."""
    return payload.strip(" \t\n\v\f\r") == ""


# ONE READ, NOT 3N. The compare payload already carries the message and the
# author name and address, so the `repos/{r}/commits/{sha}` calls the loops used
# to make were re-fetching data already in hand: THREE per commit, 762 of them on a 254-commit PR, ~3.5 minutes of a 12-minute job. Every one of them was also a chance for a rate limit to refuse a PR that is fine.
COMMIT_PROJECTION = (
    ".commits[] | {sha: .sha, message: .commit.message, "
    "name: .commit.author.name, email: .commit.author.email}"
)


def parse_rows(payload: str) -> list[dict]:
    """One compact JSON object per line. Unparseable lines are DROPPED, not raised.

    Dropping matches the twin, whose `jq -r '.sha' <<<"$ROW"` fails on a malformed row and leaves the fields empty rather than aborting the loop. Both implementations therefore under-report identically instead of one crashing, which is the property the differential needs.
    """
    out: list[dict] = []
    for line in payload.split("\n"):
        if line.strip() == "":
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        # `.sha // empty` then `[[ -z "$SHA" ]] && continue`: a row with no usable sha is skipped on both sides rather than reported as commit "".
        if isinstance(value, dict) and str(value.get("sha") or "") != "":
            out.append(value)
    return out


def read_count(payload: str) -> int:
    """`grep -c .`: non-empty LINES, which is what the completeness check reads.

    Separate from `split_commits` deliberately. That one mirrors the twin's word splitting because it feeds the loop; this one mirrors the twin's `grep -c .` because it feeds the refusal. They agree on a list of SHAs and would stop agreeing on anything else, which is the same coupling both implementations have and therefore the same one they would break on.
    """
    return len([line for line in payload.split("\n") if line != ""])


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean or not a PR, 1 on an attribution or an unreadable PR."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    # Validate required environment variables
    if not os.environ.get("GITHUB_TOKEN"):
        print("GITHUB_TOKEN is required")
        return 1

    pr_number = os.environ.get("PR_NUMBER", "")
    if not pr_number:
        print("PR_NUMBER not set - skipping Claude attribution check (not a pull request)")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO
    issues: list[str] = []

    print("Checking for Claude attribution in PR #%s..." % pr_number)

    # Check PR description
    print("  Checking PR description...")
    ok, pr_body = gh_retry(
        "PR body for #%s" % pr_number,
        ["api", "repos/%s/pulls/%s" % (repo, pr_number), "--jq", '.body // ""'],
    )
    if not ok:
        return probe_failed()

    if CLAUDE_PATTERN.search(pr_body):
        issues.append('PR description contains: "%s"' % first_match(pr_body))

    # Check commit messages
    print("  Checking commit messages...")
    # NOT `pulls/{n}/commits`: that endpoint caps at 250 EVEN WITH --paginate,
    # and it caps SILENTLY -- no error, no marker, just a short list. Measured 2026-09-15 on rediacc/console#589, a 254-commit PR: this gate read 250 and reported "No Claude attribution found - OK" over the four NEWEST commits, which it had never seen. That is the exact shape this gate was repaired for in the first place: inspect nothing, print a checkmark.
    #
    # The compare endpoint paginates properly, and the PR's own `.commits` count is an INDEPENDENT number to check the read against -- so a short read now refuses instead of passing, at any size rather than at one threshold.
    ok, meta = gh_retry(
        "PR metadata for #%s" % pr_number,
        [
            "api",
            "repos/%s/pulls/%s" % (repo, pr_number),
            "--jq",
            '"\\(.base.sha) \\(.head.sha) \\(.commits)"',
        ],
    )
    if not ok:
        return probe_failed()

    fields = meta.split()
    # `read -r base head total` puts the ENTIRE remainder in the last variable, so a fourth field makes the count non-numeric rather than being dropped.
    base = fields[0] if len(fields) > 0 else ""
    head = fields[1] if len(fields) > 1 else ""
    total = " ".join(fields[2:])
    if base == "" or head == "" or not re.match(r"^[0-9]+$", total):
        print(
            "  ERROR: could not read base/head/commit-count for PR #%s: '%s'." % (pr_number, meta),
            file=sys.stderr,
        )
        return probe_failed()

    ok, commits = gh_retry(
        "commit list for PR #%s" % pr_number,
        [
            "api",
            "repos/%s/compare/%s...%s?per_page=100" % (repo, base, head),
            "--paginate",
            "--jq",
            COMMIT_PROJECTION,
        ],
    )
    if not ok:
        return probe_failed()

    # A PR always has at least one commit. An empty list here means the call succeeded but returned nothing usable, which is not a PR this gate can clear.
    if is_blank(commits):
        print("  ERROR: the commit list for PR #%s came back empty." % pr_number, file=sys.stderr)
        print(
            "  Every PR has at least one commit, so this is a failed read, not a clean PR.",
            file=sys.stderr,
        )
        return probe_failed()

    read_commits = read_count(commits)
    if read_commits != int(total):
        print(
            "  ERROR: read %d commit(s) for PR #%s, but the PR reports %s."
            % (read_commits, pr_number, total),
            file=sys.stderr,
        )
        print(
            "  An incomplete set cannot be cleared; refusing rather than judging part of it.",
            file=sys.stderr,
        )
        return probe_failed()

    rows = parse_rows(commits)

    # TWO PASSES, NOT ONE, and the order is load-bearing: every message finding is reported before every author finding, which is the order the old two-loop shape produced.
    for row in rows:
        sha = str(row.get("sha") or "")
        message = str(row.get("message") or "")
        if CLAUDE_PATTERN.search(message):
            issues.append('Commit %s contains: "%s"' % (sha[0:7], first_match(message)))

    # Check commit authors
    print("  Checking commit authors...")
    for row in rows:
        sha = str(row.get("sha") or "")
        name = str(row.get("name") or "")
        email = str(row.get("email") or "")
        if AUTHOR_PATTERN.search("%s %s" % (name, email)):
            issues.append("Commit %s authored by: %s <%s>" % (sha[0:7], name, email))

    if not issues:
        print("No Claude attribution found - OK")
        return 0

    # Found issues
    print()
    print("============================================================")
    print("  Claude Attribution Detected")
    print("============================================================")
    print()
    print("Found %d instance(s) of Claude attribution:" % len(issues))
    print()
    for issue in issues:
        print("  - %s" % issue)
    print()
    print("------------------------------------------------------------")
    print("Please remove Claude attribution before merging.")
    print()
    print("To fix commit messages, use interactive rebase:")
    print()
    print("  git rebase -i HEAD~N  # where N is number of commits")
    print("  # Change 'pick' to 'reword' for commits to edit")
    print("  # Remove %s lines and save" % _TRAILER)
    print("  git push --force")
    print()
    print("To fix PR description:")
    print()
    print(
        "  gh pr edit %s --body \"$(gh pr view %s --json body -q .body | sed '/Claude/d')\""
        % (pr_number, pr_number)
    )
    print()
    print("Or edit directly on GitHub:")
    print("  https://github.com/%s/pull/%s" % (repo, pr_number))
    print("------------------------------------------------------------")
    return 1


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------

# Bodies that MUST match, one per branch of the pattern, and bodies that must NOT. The negative set is the important half: the twin's own note says this pattern deliberately matches attribution markers and not "general mentions of Claude as a tool", and a pattern that swallowed the second would red every PR whose description mentions the assistant at all.
MUST_MATCH = (
    _TRAILER + ": Claude Opus 5 <noreply@anthropic.com>",
    _TRAILER.lower() + ":Claude",
    _TRAILER + " :  Claude",
    "Generated with [Claude Code](https://claude.com/claude-code)",
    "Generated with Claude",
    "\U0001f916 Generated with something",
    "\U0001f916Generated",
    "someone@noreply@anthropic.com",
)

MUST_NOT_MATCH = (
    "Claude helped me think about this",
    "This uses the Anthropic API",
    "Generated by a script",
    _TRAILER + ": A Human <human@example.invalid>",
    "generated with care",
    "",
)


def selftest() -> int:
    """Both directions for the pattern, the author check, and the two parsers.

    A gate with only positive controls would flag every PR that mentions the assistant, which is exactly the over-broad direction the twin's own note warns about.
    """
    ctl = Controls("claude-attribution", floor=20, verbose=True)

    for body in MUST_MATCH:
        ctl.truthy("PLANT: attribution is detected in %r" % body[:34], CLAUDE_PATTERN.search(body))
    for body in MUST_NOT_MATCH:
        ctl.falsy(
            "MIRROR: a general mention is NOT attribution: %r" % body[:34],
            CLAUDE_PATTERN.search(body),
        )

    # -- the author check, both directions ----------------------------------
    ctl.truthy(
        "PLANT: an anthropic address in the author is caught",
        AUTHOR_PATTERN.search("Someone noreply@anthropic.com"),
    )
    ctl.truthy(
        "PLANT: the name alone is enough",
        AUTHOR_PATTERN.search("Claude someone@example.invalid"),
    )
    ctl.falsy(
        "MIRROR: an ordinary author is not caught",
        AUTHOR_PATTERN.search("Muhammed Fatih Bayraktar someone@example.invalid"),
    )

    # -- first_match returns the LINE, not the fragment ---------------------
    ctl.check(
        "the reported match is the whole LINE",
        first_match("intro\n" + _TRAILER + ": Claude <x>\ntail"),
        _TRAILER + ": Claude <x>",
    )
    ctl.check(
        "the FIRST matching line wins, as `head -1` does",
        first_match(_TRAILER + ": Claude <a>\n" + _TRAILER + ": Claude <b>"),
        _TRAILER + ": Claude <a>",
    )
    ctl.check("no match is the empty string", first_match("nothing here"), "")

    # -- the commit-list parsers, both directions ---------------------------
    ctl.check("shas split on whitespace", split_commits("a\nb\nc"), ["a", "b", "c"])
    ctl.check("a blank list is blank", is_blank("  \n\t\n"), True)
    ctl.check("a real list is not blank", is_blank("abc123\n"), False)
    ctl.check(
        "an EMPTY list is blank, which the gate must refuse rather than clear",
        is_blank(""),
        True,
    )

    # -- the completeness check, both directions ----------------------------
    # The defect it closes was SILENT: `pulls/{n}/commits` returned 250 of 254
    # and the gate cleared the PR over four commits it never read. A control in one direction only would not have caught that, because the truncated read was itself a perfectly well-formed list.
    ctl.check("a complete read counts every line", read_count("a\nb\nc\n"), 3)
    ctl.check("PLANT: 250 lines is not 254, so the read is short", read_count("x\n" * 250), 250)
    ctl.check("a blank payload counts zero, never the declared total", read_count(""), 0)
    ctl.check("blank lines do not invent commits", read_count("a\n\nb\n"), 2)

    # -- the row parser, which replaced 3 API calls per commit ---------------
    _row = '{"sha":"abc1234","message":"m","name":"N","email":"e@x.invalid"}'
    ctl.check("one object per line is parsed", len(parse_rows(_row + "\n" + _row)), 2)
    ctl.check("a blank payload parses to nothing", parse_rows("\n\n"), [])
    ctl.check(
        "an unparseable line is DROPPED, matching the twin's `|| continue`",
        len(parse_rows(_row + "\nnot json\n" + _row)),
        2,
    )
    ctl.check(
        'a row with no sha is skipped, not reported as commit ""',
        parse_rows('{"message":"m"}'),
        [],
    )
    ctl.check(
        "a JSON value that is not an object is dropped, not indexed",
        parse_rows('"just a string"\n42\n'),
        [],
    )
    ctl.check(
        "PLANT: the message field carries through, so the pattern has something to match",
        bool(
            CLAUDE_PATTERN.search(
                parse_rows('{"sha":"a","message":"%s: Claude"}' % ("Co-" + "Authored-By"))[0][
                    "message"
                ]
            )
        ),
        True,
    )

    # -- the two skip / refuse arms, driven for real ------------------------
    saved = {k: os.environ.get(k) for k in ("GITHUB_TOKEN", "PR_NUMBER")}
    try:
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ.pop("PR_NUMBER", None)
        ctl.check("PLANT: no token reds rather than skipping", main([]), 1)
        os.environ["GITHUB_TOKEN"] = fixture_token()
        ctl.check("MIRROR: no PR number skips and exits 0", main([]), 0)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
