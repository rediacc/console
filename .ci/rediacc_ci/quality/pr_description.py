r"""Is the PR description still describing the PR?

Ported from `.ci/scripts/quality/check-pr-description.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHAT IT CHECKS, in the twin's own words:

    Check that PR description is up-to-date with recent commits.

    After multiple commits, PR descriptions can become stale and misleading.
    This check ensures the description is updated when:
      - The PR has 3+ commits AND
      - The latest commit is more than STALE_THRESHOLD_MINUTES newer than the
        last time the PR body/title was edited

    Uses GitHub's GraphQL lastEditedAt field which only changes when the PR body
    or title is actually edited (not on pushes, comments, or labels).

    Environment variables:
      GH_TOKEN           - GitHub token for API access
      PR_NUMBER          - Pull request number
      GITHUB_REPOSITORY  - Repository in owner/repo format

THE ADVICE BLOCK IS THE POINT OF THE GATE, and one line of it was WRONG in a way
that destroyed data. Carried verbatim because it is the only record of why:

    NOT a whole-body replacement, and the distinction is the point. This repo's
    PR bodies carry TWO machine-written sections, <!-- worklist-epics --> and
    <!-- pushed-head -->, and the edit form writes the WHOLE body: anything the
    new text omits is gone. Advice that says --body "new body" is advice to
    destroy both, and it was printed by the very gate that fires when a
    description needs updating. Corrected 2026-09-03, on the same day the guard
    that refuses those edits was itself found to have been narrowed into allowing
    them.

So the block's step 5 is not decoration: a port that "tightened" the advice would
re-introduce a data-loss instruction, and nothing in the exit code would notice.

THE HEREDOC AROUND THE GRAPHQL QUERY IS ALSO ARCHAEOLOGY: "Use heredoc to safely
construct the GraphQL query (avoids bash ! escaping issues)". Python has no such
hazard, so the note survives here rather than as a constraint, which is what stops
the next reader collapsing the query into a one-liner in the twin and
rediscovering the escaping problem.

-----------------------------------------------------------------------------
DEFECT FOUND WHILE PORTING, REPRODUCED RATHER THAN FIXED.
-----------------------------------------------------------------------------

THE GRAPHQL READ HAS THE UNGUARDED-PIPELINE BUG THAT 96355d3b5 FIXED IN THREE
SIBLING GATES AND NOT IN THIS ONE. The twin runs

    DESCRIPTION_TIME=$(gh api graphql ... 2>/dev/null | jq -r '...')

under `set -euo pipefail`. When `gh` exits non-zero, pipefail promotes that to
the pipeline, the pipeline is the whole right-hand side of an assignment, and
`set -e` kills the script AT THE ASSIGNMENT. The handler written for exactly that
case, three lines below,

    if [[ -z "$DESCRIPTION_TIME" ]] || [[ "$DESCRIPTION_TIME" == "null" ]]; then
        log_warn "Could not get PR description edit time - skipping check"

is therefore UNREACHABLE. Measured 2026-09-06 with a `gh` stub that exits 1: the
script exits 1 with ZERO bytes on both streams, which reads exactly like a gate
failing for a real reason. The same probe with a `gh` that exits 0 printing
non-JSON exits 5 with a `jq: parse error` line.

The port reproduces both statuses, because invariant 5 says the twin is not
edited in the change that ports it and the differential rules on behaviour, not
on intent. It is reported as a defect in the twin.

A SECOND, QUIETER ONE: this gate calls `gh` DIRECTLY rather than through
`gh_json` from `.ci/scripts/lib/common.sh`, so it gets no retry and no
body-parses-as-JSON check. `gh_json`'s own comment says why that matters: "gh api
graphql can exit 0 while returning a truncated or malformed body, so an exit-code
check alone misses it." Eight other call sites across the review gates were moved
onto it; this one was left behind.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`date` IS SHELLED OUT TO, NOT REIMPLEMENTED. The twin's chain is
`date -d <ts> +%s || date -j -f <fmt> <ts> +%s || echo 0` -- GNU first, BSD
second, zero last -- and GNU `date -d` accepts a far wider grammar than
`datetime.fromisoformat`. Re-deriving that grammar in Python would be a new
source of divergence on exactly the inputs nobody tests, so the port runs the
same two commands in the same order and falls back to the same "0".

THE JSON IS PARSED IN PYTHON, NOT THROUGH jq, and the one place that shows is an
UNPARSEABLE body: jq prints `jq: parse error: ...` on stderr and exits 5, and this
port cannot emit jq's wording. `gh pr view --json` either fails (in which case the
twin substitutes `{}`) or emits valid JSON, so the shape is one `gh` does not
produce; the divergence is stated here rather than hidden, and the exit status is
reproduced.

STDERR CARRIES THE PROGRESS, STDOUT CARRIES THE ADVICE. The twin's `log_step` and
`log_info` go to stderr through `common.sh`, and every line of the stale-PR block
is a bare `echo` to stdout. Both are preserved: a caller that redirects one stream
sees exactly what it saw before.
"""

import json
import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.controls import Controls

# Configuration, carried with the twin's own inline comments.
MIN_COMMITS = 3  # Minimum commits before requiring update
STALE_THRESHOLD_MINUTES = 30  # How old description can be (in minutes)

# The three variables `require_var` insists on, in the twin's order. The order is
# observable: the first missing one is the only one reported.
REQUIRED_VARS = ("PR_NUMBER", "GH_TOKEN", "GITHUB_REPOSITORY")

# The query, byte for byte as the heredoc writes it. See the module docstring for
# why it is a heredoc in bash and why that note is kept here.
GRAPHQL_QUERY = """query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      lastEditedAt
      createdAt
    }
  }
}"""


def _run(argv: list[str], *, quiet_stderr: bool = True) -> tuple[int, str]:
    """Run `argv`, returning (status, stdout with trailing newlines stripped).

    THE STRIP IS THE SHELL'S, NOT A TIDY-UP. `$(...)` removes trailing newlines,
    and several comparisons below are against the empty string, so a port that
    kept the newline would take a different branch on an empty-but-newline result.
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except OSError:
        # `gh` absent behaves like `gh` failing, which is what the shell does with
        # a command-not-found inside a command substitution.
        return 127, ""
    if not quiet_stderr and proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode, proc.stdout.rstrip("\n")


def to_epoch(timestamp: str) -> str:
    """`date -d <ts> +%s`, then the BSD form, then "0". Returned as a STRING.

    A string because the twin compares it against the literal `"0"` before doing
    any arithmetic, and because `date` on some hosts prints a value this port has
    no business reinterpreting.
    """
    code, out = _run(["date", "-d", timestamp, "+%s"])
    if code == 0 and out:
        return out
    code, out = _run(["date", "-j", "-f", "%Y-%m-%dT%H:%M:%SZ", timestamp, "+%s"])
    if code == 0 and out:
        return out
    return "0"


def stale_block(repo: str, pr_number: str, commit_count: int, age_minutes: int) -> list[str]:
    """The advice block, as the lines it prints. Empty is never returned.

    A FUNCTION SO A TEST CAN READ IT. The block is the gate's entire product, and
    the one line that matters most -- step 5, about not dropping the generated
    marker sections -- is a correction from 2026-09-03 that no exit code protects.
    """
    return [
        "",
        "============================================================",
        "  PR Description May Be Stale",
        "============================================================",
        "",
        "Your PR has %d commits, but the description hasn't" % commit_count,
        "been updated in %d minutes (threshold: %dm)." % (age_minutes, STALE_THRESHOLD_MINUTES),
        "",
        "After multiple commits, PR descriptions can become outdated",
        "and misleading for reviewers.",
        "",
        "------------------------------------------------------------",
        "FOR AI SYSTEMS (Claude, Copilot, etc.):",
        "------------------------------------------------------------",
        "",
        "You MUST:",
        "  1. Run: git log --oneline origin/main..HEAD",
        "  2. Review ALL commits in the branch",
        "  3. Update PR title to reflect the CURRENT scope",
        "  4. Update PR description with:",
        "     - Summary of ALL changes (not just initial ones)",
        "     - Any new features added during review",
        "     - Breaking changes or migration notes",
        # STEP 5 IS THE CORRECTION. See the module docstring: the advice this
        # replaced told the reader to write the whole body, which deletes both
        # machine-written marker blocks.
        "  5. Update the description WITHOUT dropping its generated sections.",
        "     The body carries <!-- worklist-epics --> and <!-- pushed-head -->, and an",
        "     edit writes the whole body, so anything you omit is deleted:",
        "       .ci/scripts/pr/sync-epic-block.sh %s <branch>" % pr_number,
        "     re-reads the current body and rewrites only its own markers.",
        "     To change the prose, read the body first and keep every marker:",
        "       gh pr view %s --json body --jq .body > /tmp/body.md" % pr_number,
        "       # edit /tmp/body.md, leaving the marker blocks alone",
        "       gh api repos/{owner}/{repo}/pulls/%s -X PATCH -F body=@/tmp/body.md" % pr_number,
        "",
        "------------------------------------------------------------",
        "FOR HUMANS:",
        "------------------------------------------------------------",
        "",
        "Please update the PR title and description to reflect:",
        "  - Current scope of changes",
        "  - Key implementation decisions",
        "  - Any breaking changes or migration notes",
        "",
        "PR: https://github.com/%s/pull/%s" % (repo, pr_number),
        "============================================================",
    ]


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 fresh or not applicable, 1 stale or unreadable.

    THE EXIT STATUSES ARE NOT ALL VERDICTS, and the twin does not distinguish
    them. `1` means "the description is stale", "PR data could not be fetched",
    or -- through the unguarded pipeline described in the module docstring -- "gh
    failed and the script died". The port reproduces all three because the
    differential rules on behaviour; the third is reported as a defect.
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

    log.step("Checking PR description freshness...")

    # `gh pr view ... 2>/dev/null || echo "{}"`.
    code, pr_data = _run(["gh", "pr", "view", pr_number, "--json", "commits,body,title"])
    if code != 0:
        pr_data = "{}"

    if pr_data == "{}":
        log.error("Could not fetch PR data")
        return 1

    # `jq '.commits | length'`. An unparseable body is the divergence named in the
    # port notes: jq exits 5 and pipefail kills the script, so the status is
    # reproduced and jq's wording is not.
    try:
        parsed = json.loads(pr_data)
        commit_count = len(parsed.get("commits") or [])
    except (ValueError, AttributeError):
        return 5

    log.info("PR has %d commit(s)" % commit_count)

    if commit_count < MIN_COMMITS:
        log.info("Less than %d commits - skipping description check" % MIN_COMMITS)
        return 0

    code, latest_commit_time = _run(
        [
            "gh",
            "pr",
            "view",
            pr_number,
            "--json",
            "commits",
            "--jq",
            ".commits | sort_by(.committedDate) | last | .committedDate",
        ]
    )
    if code != 0:
        latest_commit_time = ""
    if not latest_commit_time:
        log.error(
            "Could not fetch the latest commit time for PR #%s (gh call failed or returned "
            "nothing); cannot verify description freshness" % pr_number
        )
        return 1

    owner = repository.split("/", 1)[0]
    repo = repository.rsplit("/", 1)[-1]

    # THE UNGUARDED PIPELINE. See the module docstring: a failing `gh` here kills
    # the twin outright, so the port exits with the same status and says nothing,
    # rather than reaching the handler three lines down that was written for it.
    code, raw = _run(
        [
            "gh",
            "api",
            "graphql",
            "-F",
            "owner=%s" % owner,
            "-F",
            "repo=%s" % repo,
            "-F",
            "number=%s" % pr_number,
            "-f",
            "query=%s" % GRAPHQL_QUERY,
        ]
    )
    if code != 0:
        return 1
    try:
        payload = json.loads(raw) if raw else None
    except ValueError:
        return 5
    description_time = ""
    if isinstance(payload, dict):
        node = payload.get("data", {}).get("repository", {}).get("pullRequest")
        if isinstance(node, dict):
            # `.lastEditedAt // .createdAt`: jq's alternative operator takes the
            # right side when the left is null OR false, which for a timestamp
            # means "never edited".
            description_time = node.get("lastEditedAt") or node.get("createdAt") or "null"

    if not description_time or description_time == "null":
        log.warn("Could not get PR description edit time - skipping check")
        return 0

    commit_epoch = to_epoch(latest_commit_time)
    desc_epoch = to_epoch(description_time)

    if commit_epoch == "0" or desc_epoch == "0":
        log.warn("Could not parse timestamps - skipping check")
        return 0

    age_seconds = int(commit_epoch) - int(desc_epoch)
    # Bash `$((a / 60))` truncates TOWARD ZERO; Python `//` floors. They disagree
    # for a negative age, which is the "description edited after the latest
    # commit" case the twin explicitly calls "always OK". `int(a / 60)` truncates.
    age_minutes = int(age_seconds / 60)
    threshold_seconds = STALE_THRESHOLD_MINUTES * 60

    log.info("Latest commit: %s" % latest_commit_time)
    log.info("Description last edited: %s" % description_time)
    log.info("Time since description edit: %dm" % age_minutes)

    if age_seconds < threshold_seconds:
        log.info("Latest commit is within %dm of description edit - OK" % STALE_THRESHOLD_MINUTES)
        return 0

    for line in stale_block(repository, pr_number, commit_count, age_minutes):
        print(line)
    return 1


def selftest() -> int:
    """Both directions on the arithmetic, the block, and the required variables.

    THE ADVICE BLOCK IS ASSERTED, NOT JUST ITS LENGTH. Its step 5 exists because
    the previous wording told readers to overwrite the whole PR body, deleting two
    machine-written sections. Nothing about the exit code protects that sentence,
    so a control does.
    """
    ctl = Controls("pr-description", floor=14)

    # -- the thresholds are facts, not knobs --------------------------------
    ctl.check("the commit floor is 3", MIN_COMMITS, 3)
    ctl.check("the staleness threshold is 30 minutes", STALE_THRESHOLD_MINUTES, 30)
    ctl.check("all three environment variables are required", len(REQUIRED_VARS), 3)
    ctl.check("PR_NUMBER is checked first", REQUIRED_VARS[0], "PR_NUMBER")

    # -- the advice block, both directions ----------------------------------
    block = stale_block("owner/repo", "42", 7, 90)
    text = "\n".join(block)
    ctl.truthy("the block names the PR", "https://github.com/owner/repo/pull/42" in text)
    ctl.truthy("the block reports the commit count", "Your PR has 7 commits" in text)
    ctl.truthy("the block reports the age and the threshold", "90 minutes (threshold: 30m)" in text)
    # THE CORRECTION OF 2026-09-03, asserted in both directions: the safe advice
    # must be present AND the data-destroying advice must be absent.
    ctl.truthy(
        "the block warns about the generated marker sections",
        "<!-- worklist-epics -->" in text and "<!-- pushed-head -->" in text,
    )
    ctl.truthy("the block names the marker-preserving script", "sync-epic-block.sh 42" in text)
    ctl.check(
        "the block does NOT advise a whole-body replacement",
        '--body "new body"' in text,
        False,
    )
    ctl.check("the block does NOT advise `gh pr edit --body`", "pr edit --body" in text, False)

    # -- the arithmetic, at and around the boundary -------------------------
    # TRUNCATION TOWARD ZERO, not flooring. A negative age is the "edited after
    # the last commit" case, and Python's `//` would report -1 minute where bash
    # reports 0.
    ctl.check("a negative age truncates toward zero, as bash does", int(-30 / 60), 0)
    ctl.check("a positive age truncates the same way", int(3599 / 60), 59)
    ctl.check("29 minutes is under the threshold", STALE_THRESHOLD_MINUTES * 60 > 29 * 60, True)
    ctl.check("30 minutes is not under it", STALE_THRESHOLD_MINUTES * 60 > 30 * 60, False)

    # -- `date` must exist, and its failure must be "0" rather than a crash --
    ctl.check("an unparseable timestamp becomes 0", to_epoch("not a timestamp at all"), "0")
    ctl.truthy("a real timestamp parses", to_epoch("2026-09-06T12:00:00Z") != "0")

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
