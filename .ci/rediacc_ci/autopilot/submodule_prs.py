#!/usr/bin/env python3
"""Port of `.ci/scripts/autopilot/submodule-prs.sh`.

Opens a PR for every submodule branch the round pushed, and links them from the
console PR body.

WHY THE LINK IS NOT COSMETIC. `.ci/scripts/quality/check-submodule-branches.sh`
is a required gate and it reads the CONSOLE PR BODY to decide whether each
submodule PR is accounted for: it accepts the full PR URL as a substring
(check-submodule-branches.sh:251), or `owner/repo#N` / `owner/repo/pull/N`
(:259). A round that pushes a submodule branch and does not link its PR leaves
console red on a gate no later round can clear by editing code. So the link is
part of the push, not a nicety after it.

THE LINK FORMAT IS A SHARED CONTRACT WITH `linked-sub-prs.sh`, which is the
READER of what this script writes: it greps the console body for
`(https://github.com/)?<owner>/<repo>(/pull/|#)<digits>` and turns the links
back into fetch targets so the review machinery can see findings raised in a
submodule PR. Two consequences worth stating, since the two files are edited by
different hands: the URL written here must keep its `owner/repo/pull/N` shape
(the `- \\`path\\` -> ` prefix is decoration, the URL is the contract), and the
`--dry-run` placeholder `.../pull/DRY-RUN` deliberately does NOT match that
grep, which is correct -- a dry run has no PR to fetch from. That file is not
touched by this port; this paragraph exists so the coupling is written down
somewhere both ends can find it.

PLAIN PRs, NOT DRAFTS. The four submodules are private repos on a free plan
where draft pull requests do not exist and `gh pr create --draft` fails.
Console is the repo with the draft flow.

IDEMPOTENCE, TWICE OVER, and both halves are exported so a test can drive them:

  1. THE PR. `gh pr list --head <branch> --state open` first; a PR is created
     only when that finds none, so a second round on the same branch reuses the
     first round's PR. `--dry-run` short-circuits both.
  2. THE BODY BLOCK. `strip_block` then `rebuild_body`: the delimited block is
     REBUILT from scratch every time rather than appended to, so a round that
     changes which submodules it touches does not leave the previous round's
     links behind claiming work this PR no longer contains. The markers must
     stay distinct from `.claude/hooks/post-bash/refresh-pr-body.sh`'s
     `pushed-head` block, which rewrites the whole body on every push and
     destroys anything inside ITS markers.

  HAZARD IN 2, PRESERVED: `strip_block` is a state machine over exact-match
  lines. A body carrying a BEGIN marker with no END -- a hand edit, or a
  truncated write -- makes it drop EVERYTHING after that marker, and the
  rebuilt body then loses the operator's text below it. Pinned by
  `test_an_unterminated_block_swallows_the_rest`, which is a defect report in
  test form, not a requirement.

DEFECT FOUND WHILE PORTING, REPRODUCED NOT REPAIRED, and it is the loudest
thing in this file. `count` comes from `jq -r '(.submodules // []) | length'`,
and jq's `length` on a NUMBER is its absolute value -- so a verdict carrying
`"submodules": 3.5` yields `3.5`, `for ((i = 0; i < 3.5; i++))` is a bash
arithmetic syntax error, and `set -e` DOES NOT CATCH IT. Driven against the twin
on 2026-09-10: the diagnostic prints, the loop body never runs, the script walks
on with an empty links file, PATCHes the console PR body with an EMPTY
`**Submodule PRs**` block -- destroying whatever links the previous round put
there -- and exits 0 with "linked 3.5 submodule PR(s)". Since
`check-submodule-branches.sh` reads those links from that body, the result is a
required gate red on a complaint no later round can clear by editing code.

The handoff validator's enum bounds `submodules` to an array of known paths, so
this is defence-in-depth failing OPEN rather than a live break; the fix is one
`[[ "$count" =~ ^[0-9]+$ ]]` guard, and it belongs to the cutover box, because
this wave's contract is that the twin stays live and the port is proven
equivalent to it. Pinned by
`test_a_non_integer_count_wipes_the_block_and_exits_0`.

THE PATH -> REPO MAP IS A GUARD, NOT A LOOKUP. It is held to
check-submodule-branches.sh:87-92, and the validator's enum already makes an
unknown path unreachable from a handoff. It stays so that the two lists failing
to agree is a loud stop (`submodule-unmapped`, exit 1) rather than a `gh pr
create --repo <owner>/` with an empty name.

WHERE jq IS SPAWNED: over the `--verdict` file, for the same reason as
`update_state.py`. That file comes from outside, a truncated one makes jq print
a parse error and exit 5, and `set -e` turns that into the script's status.
Neither the text nor the code is reproducible by hand.

  `jq -r '.message' | head -1` IS REPRODUCED AS "the first line", and the twin's
  spelling carries a latent trap worth naming: under `set -o pipefail`, `head`
  closing the pipe before jq finishes would make the pipeline fail on SIGPIPE.
  It cannot fire in practice (a commit message shorter than the 64 KiB pipe
  buffer is written before `head` exits) and this port cannot reproduce it at
  all, because it takes the first line of a value it already holds.

`gh_retry` IS TRANSLITERATED, NOT IMPORTED, sleeps included -- see
`update_state.py`'s docstring for the reasoning and the two prior copies.

Exit: 0 (including "the verdict named no submodules"), 1 refused or a write
failed, 2 usage, jq's own status when the verdict will not parse.

K=5 LEDGER: `.ci/shadow/w7p6-submodule-prs.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "submodule-prs.py"

USAGE = (
    "usage: submodule-prs.sh --verdict <file> --repo <owner/name> --pr <n> "
    "--branch <name> [--dry-run]"
)

BEGIN = "<!-- autopilot-submodule-prs:begin -->"
END = "<!-- autopilot-submodule-prs:end -->"

# `AUTOPILOT_ALLOW_PUSH` must be exactly this. Absent is off, fail closed.
ALLOW_ENV = "AUTOPILOT_ALLOW_PUSH"
ALLOW_VALUE = "true"

# The path -> repository map, held to check-submodule-branches.sh:87-92.
SUBMODULE_REPOS = {
    "private/renet": "renet",
    "private/account": "account",
    "private/elite": "elite",
    "private/homebrew-tap": "homebrew-tap",
}

# `_gh_probe`: three attempts, sleeping 3 then 6 seconds.
GH_ATTEMPTS = 3

# What bash's `for ((i = 0; i < $count; i++))` accepts without an arithmetic
# error. jq's `length` never emits a leading zero, so no octal case arises.
COUNT_RE = re.compile(r"^[0-9]+$")

# The URL a dry run pretends to have opened. Deliberately unmatchable by
# `linked-sub-prs.sh`'s digit-bounded grep; see the module docstring.
DRY_RUN_URL = "https://github.com/%s/pull/DRY-RUN"


def gh_retry(what: str, args: list[str]) -> tuple[bool, str]:
    """`gh_retry <what> -- <gh args...>`. Returns (ok, stdout).

    A FAILURE IS NEVER AN EMPTY ANSWER, which matters more here than anywhere
    else in this file: the empty string from `--jq '.[0].url // empty'` is what
    makes the script CREATE a pull request. If a rate-limited `pr list` were
    allowed to look empty, every retry of a round would open another PR.
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
        sys.stderr.flush()
    return False, ""


def submodule_repo(path: str) -> str | None:
    """`submodule_repo` as a lookup. None is the twin's `return 1`."""
    return SUBMODULE_REPOS.get(path)


def strip_block(body: str) -> str:
    """The twin's awk: drop the delimited block, keep everything else.

    A STATE MACHINE OVER EXACT-MATCH LINES, reproduced including the hazard: an
    opening marker with no closing one drops the whole remainder of the body,
    because `skip` is never turned off again. `$0 == b` is a full-line
    comparison, so an indented or inline marker is not a marker.

    THE INPUT IS THE BODY AS `gh` RETURNED IT, with no trailing newline: the
    twin adds one with `printf '%s\n' "$body"` and awk then sees exactly
    `body.split("\n")` lines, printing each kept one with a newline. So an empty
    body yields ONE empty line and a `"\n"` result, not an empty string, and the
    blank line that leaves at the top of a fresh block is real output rather
    than an off-by-one here.
    """
    out = []
    skip = False
    for line in body.split("\n"):
        if line == BEGIN:
            skip = True
            continue
        if line == END:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "".join(line + "\n" for line in out)


def rebuild_body(stripped: str, links: list[str]) -> str:
    """`{ cat stripped; printf '\\n%s\\n' BEGIN; ... }`, byte for byte.

    Note the blank line before BEGIN and the blank line after the heading: both
    come from the twin's printf strings and both are visible in the rendered
    comment, so they are preserved rather than tidied.
    """
    return "%s\n%s\n**Submodule PRs**\n\n%s%s\n" % (stripped, BEGIN, "".join(links), END)


def link_line(path: str, url: str) -> str:
    """`printf -- '- \\`%s\\` -> %s\\n'`. The format `linked-sub-prs.sh` reads."""
    return "- `%s` -> %s\n" % (path, url)


def jq_r(program: str, path: str) -> tuple[int, str]:
    """`jq -r '<program>' <file>`, stderr INHERITED so jq's own diagnostic lands
    on fd 2 in real time, exactly as the twin's unredirected jq does."""
    proc = subprocess.run(
        ["jq", "-r", program, path],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    verdict = args.get("ARG_VERDICT", "")
    repo = args.get("ARG_REPO", "")
    pr = args.get("ARG_PR", "")
    branch = args.get("ARG_BRANCH", "")
    dry_run = args.get("ARG_DRY_RUN", "false") == "true"

    if not (verdict and repo and pr and branch):
        log.error(USAGE)
        return 2
    try:
        common.require_file(verdict)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    code, raw_count = jq_r("(.submodules // []) | length", verdict)
    if code != 0:
        return code
    count_text = raw_count.rstrip("\n")
    if count_text == "0":
        log.info("submodule-prs: the round named no submodules; nothing to open or link")
        return 0
    # THE STAGE FLAG IS CHECKED AFTER THE COUNT, which the twin's own header
    # calls out: "the verdict named no submodules" exits 0 whatever the flag
    # says, because nothing would have been written either way.
    if os.environ.get(ALLOW_ENV, "") != ALLOW_VALUE and not dry_run:
        log.error(
            "stage-flag-disabled: %s is not '%s'; refusing to open or link PRs (fail closed)"
            % (ALLOW_ENV, ALLOW_VALUE)
        )
        return 1

    # THE THIRD PRESERVED DEFECT, and the worst of the three. jq's `length` on a
    # NUMBER is its absolute value, so `"submodules": 3.5` yields the count
    # `3.5`, and bash's `for ((i = 0; i < 3.5; i++))` is an ARITHMETIC SYNTAX
    # ERROR that `set -e` does NOT catch (driven: the diagnostic prints, the loop
    # body never runs, the script CONTINUES). The twin therefore walks on with an
    # empty links file and PATCHes the console PR body with an empty
    # `**Submodule PRs**` block -- wiping any links a previous round put there,
    # which reds `check-submodule-branches.sh` on a gate no later round can clear
    # by editing code -- and exits 0 saying "linked 3.5 submodule PR(s)".
    #
    # Reproduced rather than repaired, on this wave's rule: the twin stays live
    # and the port must be equivalent to it. Naming it here and in
    # `test_a_non_integer_count_wipes_the_block_and_exits_0` is the deliverable;
    # the fix belongs to whoever cuts over, and it is one `[[ "$count" =~ ^[0-9]+$ ]]`
    # guard away.
    if COUNT_RE.match(count_text):
        iterations = int(count_text)
    else:
        iterations = 0
        print(
            "%s: ((: %s: arithmetic syntax error: invalid arithmetic operator" % (SELF, count_text),
            file=sys.stderr,
            flush=True,
        )

    work = tempfile.mkdtemp()
    try:
        return _run(verdict, repo, pr, branch, dry_run, iterations, count_text, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run(
    verdict: str,
    repo: str,
    pr: str,
    branch: str,
    dry_run: bool,
    iterations: int,
    count_text: str,
    work: str,
) -> int:
    owner = repo.split("/", 1)[0]
    links: list[str] = []

    for i in range(iterations):
        code, raw = jq_r(".submodules[%d].path" % i, verdict)
        if code != 0:
            return code
        sub = raw.rstrip("\n")
        name = submodule_repo(sub)
        if name is None:
            log.error(
                "submodule-unmapped: '%s' has no repository in the map; refusing to guess" % sub
            )
            return 1
        target = "%s/%s" % (owner, name)

        if dry_run:
            url = DRY_RUN_URL % target
        else:
            ok, url = gh_retry(
                "existing PR for %s" % target,
                [
                    "pr",
                    "list",
                    "--repo",
                    target,
                    "--head",
                    branch,
                    "--state",
                    "open",
                    "--json",
                    "url",
                    "--jq",
                    ".[0].url // empty",
                ],
            )
            if not ok:
                return 1
            if url == "":
                code, message = jq_r(".submodules[%d].message" % i, verdict)
                if code != 0:
                    return code
                # `| head -1`: the first line, and only the first.
                title = message.split("\n", 1)[0]
                title_file = os.path.join(work, "title.txt")
                with open(title_file, "w", encoding="utf-8") as handle:
                    handle.write(title + "\n")
                body_file = os.path.join(work, "body.txt")
                with open(body_file, "w", encoding="utf-8") as handle:
                    # Neither the title nor this body mentions any agent: the
                    # console body is policed by check-claude-attribution.sh, and
                    # keeping both sides in the same voice avoids a surprise there.
                    handle.write(
                        "Submodule change for %s#%s.\n\nOpened by the autopilot "
                        "harness alongside the console PR; review there.\n" % (repo, pr)
                    )
                ok, url = gh_retry(
                    "create PR in %s" % target,
                    [
                        "pr",
                        "create",
                        "--repo",
                        target,
                        "--head",
                        branch,
                        "--base",
                        "main",
                        "--title",
                        title,
                        "--body-file",
                        body_file,
                    ],
                )
                if not ok:
                    return 1
                log.info("opened %s PR for branch %s: %s" % (target, branch, url))
            else:
                log.info("reusing existing %s PR for branch %s: %s" % (target, branch, url))

        links.append(link_line(sub, url))

    if dry_run:
        # A dry run does not read the live body, so the block it prints is
        # rebuilt onto an EMPTY one. That is the twin's behaviour and it means a
        # dry run cannot show what the merged body would look like.
        body = ""
    else:
        ok, body = gh_retry(
            "console PR body",
            ["pr", "view", pr, "--repo", repo, "--json", "body", "--jq", '.body // ""'],
        )
        if not ok:
            return 1

    # `printf '%s\n' "$body" >"$work/body-old.md"`.
    new_body = rebuild_body(strip_block(body), links)
    body_new = os.path.join(work, "body-new.md")
    with open(body_new, "w", encoding="utf-8") as handle:
        handle.write(new_body)

    if dry_run:
        sys.stdout.write(new_body)
        sys.stdout.flush()
        log.info("dry-run: would link %s submodule PR(s) in %s#%s" % (count_text, repo, pr))
        return 0

    ok, _ = gh_retry(
        "link submodule PRs in %s#%s" % (repo, pr),
        ["pr", "edit", pr, "--repo", repo, "--body-file", body_new],
    )
    if not ok:
        return 1
    log.info(
        # `$count`, NOT the loop bound: the twin interpolates the raw jq output,
        # which is how "linked 3.5 submodule PR(s)" is a sentence this can print.
        "linked %s submodule PR(s) in the %s#%s body (the Submodule Branches gate reads them "
        "from there)" % (count_text, repo, pr)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
