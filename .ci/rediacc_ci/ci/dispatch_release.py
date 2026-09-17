#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/dispatch-release.sh` (191 lines).

Decides whether the merged commit that triggered this CI run earns a cd-v2 release, and dispatches it. The twin's own 67-line header carries the contract (the `bump-none` rule, why the HEAD commit and not the release range, why every
failure path FAILS OPEN, and why the decision and the dispatch are separable);
none of it is restated here.

LIVE CALLERS, not repointed. `.github/workflows/ci.yml` runs the bash twin in two steps of `finalize-release-sentinel`, `--decide-only` before the sentinel is
sealed and `--dispatch-only` after. The bash twin stays the registered gate;
this module is its verified-equivalent alternative, and the cutover is a separate, later, driver-only step.

Ledger: `.ci/shadow/w7p6-dispatch-release.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-dispatch-release --assert --k 5`).

-----------------------------------------------------------------------------
DEFECT A, REPRODUCED RATHER THAN REPAIRED: `2>&1` MAKES gh's STDERR INTO DATA
-----------------------------------------------------------------------------
The twin captures the PR lookup with

    rows=$(gh api ".../pulls" --jq '...' 2>&1 </dev/null)

so any line `gh` writes to stderr WHILE SUCCEEDING becomes a row of the PR table. Each such line is then parsed as `<number> <labels>`, and since it carries no `bump-none` it lands in `keep_prs`. Driven, with a fake `gh` that prints one deprecation notice on stderr and the real table on stdout:

    $ FAKE_GH_STDOUT='570 bump-none' \\
      FAKE_GH_STDERR='Warning: your gh version is out of date' \\
      GITHUB_REPOSITORY=r/c GITHUB_SHA=abcdef1234567890 \\
      bash .ci/scripts/ci/dispatch-release.sh --decide-only
    (warn) #570 carries 'bump-none' but #Warning: does not; releasing
    ::notice title=Release::#570 is labelled bump-none, but #Warning: also
      contains abcdef1 and is not; releasing.
    decision: release

Without the stderr line the same call prints `decision: skip`. So one benign diagnostic on a SUCCEEDING lookup invents a phantom PR, flips the verdict, and names that phantom in a notice a human is expected to believe. It errs in the release direction, which is the twin's stated preference, but the reasoning printed for it is false. `STDERR_IS_DATA` names it so a test can assert it
by name. Reported, not fixed: repairing it is a cutover-box decision.

-----------------------------------------------------------------------------
DEFECT B: THE `keep_prs` TRAILING SPACE IS TRIMMED IN THREE MESSAGES AND NOT
IN THE FOURTH
-----------------------------------------------------------------------------
`${skip_prs% }` and `${keep_prs% }` strip the accumulator's trailing space
everywhere except the final `log_info`, which uses `${keep_prs:-no PR}` and
therefore prints `dispatching cd-v2 for abcdef1 (#571 )`. Cosmetic, carried verbatim, and pinned by the differential so nobody "tidies" one side only.

-----------------------------------------------------------------------------
DIVERGENCES, BOTH IN TEXT ONLY A HUMAN READS
-----------------------------------------------------------------------------
 1. `gh` NOT ON PATH. The twin has no `require_cmd gh`, so a missing binary
    reaches the lookup as a command-substitution failure and bash's own
    `bash: line 119: gh: command not found` becomes the `${rows}` interpolated
    into the warn line. That message names a bash line number; this port
    interpolates `GH_NOT_FOUND` instead. Same stream, same exit, same
    fail-open branch.
 2. common.sh logs with `echo -e`, which interprets backslash escapes IN THE
    MESSAGE; `rediacc_ci.log` formats the message as data (see `log.py`'s
    "A SECOND DIVERGENCE"). Only reachable when a repository name, sha or gh
    error text contains a backslash.
 3. AN UNWRITABLE $GITHUB_OUTPUT. `>>"$GITHUB_OUTPUT"` fails as a redirection
    and `set -e` turns that into exit 1, with bash naming its own line. This
    port prints `<path>: <strerror>` and returns 1. Same stream, same exit.

Exit: 0 whether it dispatched or skipped, 1 on a missing required variable, 2 on an unrecognised argument. Anything else is `gh workflow run`'s own status propagated by `set -e`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log

# `SKIP_LABEL='bump-none'` (twin :76). The label's meaning lives in
# `.github/labels.yml` and the reviewer's pr-labels vocabulary.
SKIP_LABEL = "bump-none"

# The three accepted invocations, and the MODE each selects (twin :81-89).
MODES = {"": "full", "--decide-only": "decide", "--dispatch-only": "dispatch"}

# The two variables the twin refuses without, IN ITS ORDER (twin :91-92). The order is load-bearing: with both unset the twin names GITHUB_REPOSITORY and exits before it ever looks at GITHUB_SHA.
REQUIRED_VARS = ("GITHUB_REPOSITORY", "GITHUB_SHA")

# Divergence 1 above. A stand-in for bash's `line N: gh: command not found`, which cannot be reproduced without naming a line of a file this module is not.
GH_NOT_FOUND = "gh: command not found"

# Defect A, named so `test_ci_dispatch_release.py` can assert it by name rather than by restating the sentence.
STDERR_IS_DATA = True

# `--jq '.[] | select(.merged_at != null) | "\\(.number) \\((.labels // []) |
# map(.name) | join(","))"'` (twin :120). Identical to detect-bump-type.sh's, deliberately, and passed to `gh` rather than to a separate `jq` process, so a fake `gh` that ignored `--jq` would exercise a path CI never runs.
PULLS_JQ = (
    '.[] | select(.merged_at != null) | "\\(.number) \\((.labels // []) | map(.name) | join(","))"'
)

# `[[:space:]]` under LC_ALL=C, which is what CI runs (twin :127). Spelled out
# rather than reached through `str.strip()`, whose default set is Python's and includes \x1c-\x1f.
POSIX_SPACE = " \t\n\r\v\f"


def pulls_url(repository: str, sha: str) -> str:
    """`repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls` (twin :119).

    `commits/{sha}/pulls` and not `pulls?q=`: it follows REBASED commits, which
    this repo needs because it rebase-merges and the PR number is therefore absent from the commit message.
    """
    return "repos/%s/commits/%s/pulls" % (repository, sha)


def short_sha(sha: str) -> str:
    """`${GITHUB_SHA:0:7}`. A bash substring, so a shorter sha is NOT padded."""
    return sha[:7]


def parse_row(row: str) -> tuple[str, str]:
    """One `<number> <label,label,...>` row into its two halves.

    `pr_num="${row%% *}"` is text up to the FIRST space, and
    `labels="${row#"$pr_num"}"; labels="${labels# }"` is the rest with exactly
    ONE leading space removed -- so a row whose label field itself begins with a space keeps the second one, and that is reproduced.
    """
    pr_num = row.split(" ", 1)[0]
    labels = row[len(pr_num) :].removeprefix(" ")
    return pr_num, labels


def has_skip_label(labels: str) -> bool:
    """`grep -qx "$SKIP_LABEL" <<<"${labels//,/$'\\n'}"` (twin :138).

    An EXACT whole-line match after commas become newlines, so `no-bump-none` and `bump-none-really` do not count and neither does an empty label field. `bump-none` holds no regex metacharacter, so grep's BRE and this equality agree on every input.
    """
    return any(label == SKIP_LABEL for label in labels.split(","))


def run_gh_pulls(repository: str, sha: str) -> tuple[int, str]:
    """The lookup, with stderr MERGED into stdout exactly as the twin merges it.

    Returns `(exit status, captured text)`. The merge is Defect A and is the whole reason this function does not take a `capture_stderr` argument: an option here would be an invitation to fix the twin's behaviour by accident.

    `</dev/null` is reproduced too. Without it `gh` can consume the caller's stdin, and the twin's callers are workflow steps whose stdin is the job's.

    Trailing newlines are stripped because `$(...)` strips them, and the all-whitespace test below would otherwise never fire.
    """
    try:
        proc = subprocess.run(
            ["gh", "api", pulls_url(repository, sha), "--jq", PULLS_JQ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # Divergence 1. bash reaches the same branch with its own wording.
        return 127, GH_NOT_FOUND
    return proc.returncode, proc.stdout.rstrip("\n")


def decide(repository: str, sha: str) -> bool:
    """Does this commit earn a release? True = yes (the twin's `return 0`).

    Logs its reasoning and emits the same GHA notices in whichever mode it runs. It does NOT touch $GITHUB_OUTPUT; that is `main`'s job, and only for the skip verdict.
    """
    status, rows = run_gh_pulls(repository, sha)
    if status != 0:
        log.warn(
            "could not resolve the PR for %s (%s); dispatching the release anyway"
            % (short_sha(sha), rows)
        )
        print(
            "::notice title=Release::PR lookup failed for %s; releasing rather than "
            "risking a silently withheld release." % short_sha(sha)
        )
        return True

    if not rows.strip(POSIX_SPACE):
        log.info(
            "no merged PR contains %s (direct push, or the API knows of none); dispatching"
            % short_sha(sha)
        )
        return True

    skip_prs = ""
    keep_prs = ""
    for row in rows.split("\n"):
        if not row:
            continue
        pr_num, labels = parse_row(row)
        if has_skip_label(labels):
            skip_prs += "#%s " % pr_num
        else:
            keep_prs += "#%s " % pr_num

    if skip_prs and not keep_prs:
        log.info("release SKIPPED: %s carries '%s'" % (skip_prs[:-1], SKIP_LABEL))
        print(
            "::notice title=Release skipped::%s is labelled %s, so %s earns no release: "
            "no tag, no GitHub release, no R2 upload, no edge deploy. Its commits ship "
            "with the next release-worthy merge." % (skip_prs[:-1], SKIP_LABEL, short_sha(sha))
        )
        return False

    if skip_prs:
        log.warn(
            "%s carries '%s' but %s does not; releasing"
            % (skip_prs[:-1], SKIP_LABEL, keep_prs[:-1])
        )
        print(
            "::notice title=Release::%s is labelled %s, but %s also contains %s and is "
            "not; releasing." % (skip_prs[:-1], SKIP_LABEL, keep_prs[:-1], short_sha(sha))
        )

    # Defect B: `${keep_prs:-no PR}` is NOT `${keep_prs% }`, so the trailing
    # space of the accumulator prints inside the parentheses.
    log.info("dispatching cd-v2 for %s (%s)" % (short_sha(sha), keep_prs or "no PR"))
    return True


def dispatch() -> int:
    """`gh workflow run cd-v2.yml --ref main -f ...` (twin :94-103).

    DISPATCH_RELEASE_DRY_RUN is a TEST SEAM and is tested for non-emptiness,
    not truth: `DISPATCH_RELEASE_DRY_RUN=false` still dry-runs, on both sides.

    Returns the exit status the twin would propagate through `set -e`.
    """
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if os.environ.get("DISPATCH_RELEASE_DRY_RUN", ""):
        print(
            "DRY-RUN: gh workflow run cd-v2.yml --ref main -f release_mode=patch "
            "-f ci_run_id=%s" % run_id
        )
        return 0
    try:
        proc = subprocess.run(
            [
                "gh",
                "workflow",
                "run",
                "cd-v2.yml",
                "--ref",
                "main",
                "-f",
                "release_mode=patch",
                "-f",
                "ci_run_id=%s" % run_id,
            ],
            check=False,
        )
    except FileNotFoundError:
        # `set -e` on a 127 from the shell's own exec failure.
        print(GH_NOT_FOUND, file=sys.stderr, flush=True)
        return 127
    return proc.returncode


def main(argv: list[str]) -> int:
    first = argv[0] if argv else ""
    if first not in MODES:
        log.error(
            "unknown argument '%s' (expected --decide-only, --dispatch-only, or no argument)"
            % first
        )
        return 2
    mode = MODES[first]

    # Read at the call site with a LITERAL name, never through an
    # `env = os.environ` alias and never through a loop variable. The loop
    # variable form is what `check:ci-python-env-registry` has to bank as an OPAQUE entry (`dispatch_release.py:*name`), which is a visible unknown rather than a declared input, and the whole point of that registry is that an environment read is an input a reader can see.
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")

    # `require_var GITHUB_REPOSITORY` then `require_var GITHUB_SHA`, in the twin's order. Reading both first cannot change the verdict: an environment read has no side effect, and only the FIRST empty one is ever reported.
    for name, value in zip(REQUIRED_VARS, (repository, sha), strict=True):
        if not value:
            log.error("Required environment variable '%s' is not set" % name)
            return 1

    skip_release = False
    if mode != "dispatch":
        skip_release = not decide(repository, sha)

    if mode == "decide":
        if skip_release:
            print("decision: skip")
            github_output = os.environ.get("GITHUB_OUTPUT", "")
            if github_output:
                try:
                    with open(github_output, "a", encoding="utf-8") as fh:
                        fh.write("skip_release=true\n")
                except OSError as exc:
                    # Divergence 3: bash's own redirection error names a line of the twin (`line 170: /no/such: No such file or directory`) and `set -e` turns it into exit 1. Same stream, same exit.
                    print("%s: %s" % (github_output, exc.strerror), file=sys.stderr, flush=True)
                    return 1
        else:
            print("decision: release")
        return 0

    if mode == "dispatch":
        # No lookup, by design: --decide-only already asked.
        print("decision: release")
        sys.stdout.flush()
        return dispatch()

    if skip_release:
        print("decision: skip")
        return 0
    print("decision: release")
    sys.stdout.flush()
    return dispatch()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
