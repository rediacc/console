#!/usr/bin/env python3
"""Port of `.ci/scripts/version/detect-bump-type.sh`.

Decides the version bump a release takes -- `major`, `minor` or `patch` -- from the labels of the PRs that release CONTAINS, printing exactly one word on stdout.

Usage: detect_bump_type.py [--verbose] Environment: GITHUB_REPOSITORY, GH_TOKEN, DETECT_BUMP_MAX_COMMITS (default 50).

THE CLASS OF BUG THIS SCRIPT IS THE FIX FOR, and therefore the class this port must not reintroduce: the previous implementation grepped `(#123)` out of the HEAD commit TITLE, a shape that only a squash merge produces. This repo rebase-merges, so 0 of the last 60 commits carried it, every release silently took the "no PR numbers found" path, and `bump-major`/`bump-minor` were
declared, documented and INERT. A wrong answer here is invisible: `patch` is also what a working lookup usually returns. That is why the differential compares the fake `gh` CALL LOG and not only the printed word -- a `patch` from a fallback and a `patch` from a lookup are different verdicts.

FAIL OPEN AND SMALL, PRESERVED EXACTLY. Every error path prints `patch` and exits 0: a missed minor is a version number, an invented major is a statement to every consumer of the version stream. Nine distinct fallback reasons exist and all nine are reproduced, including their `--verbose` text, because the reason is the only way to tell a real `patch` from a degraded one.

GIT IS SHELLED OUT TO, NOT REIMPLEMENTED -- `git tag -l 'v*' --sort=-v:refname`,
`git merge-base --is-ancestor`, `git log --format=%H`, `git rev-parse HEAD`,
each with the twin's own arguments and its own `2>/dev/null`. Reimplementing tag
ordering or ancestry in Python would be a second opinion about the object graph;
the differential builds REAL git repositories and lets one git binary answer for
both sides. `--sort=-v:refname` in particular is git's own version collation,
which is not `sorted()` and not `sort -V`.

THE TWO-LEVEL LOOP'S QUIRKS ARE REPRODUCED, not tidied, because each is reachable from real API output:

  * `pr_num="${row%% *}"` then `labels="${labels# }"` strips exactly ONE space,
    so a label list is split on the FIRST space only.
  * dedupe is a substring test against `" $seen_prs "`, so it is the string
    membership the twin performs, not a set of parsed integers.
  * `grep -qx` against `${labels//,/$'\\n'}` matches a WHOLE segment, so
    `bump-major-ish` does not count and neither does `xbump-major`.
  * the major short-circuit `break`s out of the COMMIT loop after finishing the
    current commit's rows, so a bump-minor on a later commit is never even
    looked up. The call log is the only place that shows it.

NO FALLBACK FOR A MISSING common.sh, matching the twin: this script sources the library unconditionally (unlike `mark-production.sh`, which branches), so a checkout without it dies in bash before this script's first line of logic. That
case is not modelled here, and there is nothing to model: it is a bash `source`
error, not a behaviour of this script.

K=5 LEDGER: `.ci/shadow/w7p6-detect-bump-type.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import log

PREFIX = "[detect-bump]"

# `${DETECT_BUMP_MAX_COMMITS:-50}`: a test seam, and a bound on what a very long
# release window can cost in API calls.
DEFAULT_MAX_COMMITS = "50"

# The two labels. Declared in .github/labels.yml; the gate test
# `test_gate_detect_bump_type.py` fails if either side of that pair drifts.
MAJOR_LABEL = "bump-major"
MINOR_LABEL = "bump-minor"

# The jq expression, byte-identical to the twin's, because the fake `gh` in the differential applies the CALLER's own expression to a fixture file: a reworded expression would mean the two sides are asking different questions.
PULLS_JQ = (
    '.[] | select(.merged_at != null) | "\\(.number) \\((.labels // []) | map(.name) | join(","))"'
)


def pulls_path(repo: str, sha: str) -> str:
    return "repos/%s/commits/%s/pulls" % (repo, sha)


def split_row(row: str) -> tuple[str, str]:
    """`pr_num="${row%% *}"` / `labels="${labels# }"`.

    Split on the FIRST space, then strip exactly one leading space from the remainder. A row with no space at all yields the whole row as the number and an empty label list, which is what the twin's parameter expansions produce.
    """
    pr_num = row.split(" ", 1)[0]
    labels = row[len(pr_num) :].removeprefix(" ")
    return pr_num, labels


def has_label(labels: str, wanted: str) -> bool:
    """`grep -qx "<wanted>" <<<"${labels//,/$'\\n'}"`.

    Commas become newlines and the match is anchored to a WHOLE line, so this is exact-segment membership: `bump-majority` and `xbump-major` do not match. Splitting on newlines too is not decoration -- a label name carrying one would produce two lines through the twin's here-string.
    """
    return wanted in labels.replace(",", "\n").split("\n")


def seen(seen_prs: str, pr_num: str) -> bool:
    """`case " $seen_prs " in *" $pr_num "*)`, as the same substring test."""
    return (" " + pr_num + " ") in (" " + seen_prs + " ")


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    """`git ... 2>/dev/null`, with a missing binary degraded to bash's 127."""
    try:
        return subprocess.run(
            ["git", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(["git", *args], 127, stdout="", stderr="")


class Detector:
    """The script, with `verbose_log` and `fallback_patch` as methods.

    `fallback_patch` raises `_FallbackPatchError` rather than calling `sys.exit`, so the one place that prints the verdict is `run()` -- the twin's `exit 0` from inside a function is the same single exit, spelled the way bash spells it.

    THE THREE ENVIRONMENT READS ARE DIRECT `os.environ` LOOKUPS, not an injected mapping, and that is deliberate. `check:ci-python-env-registry` derives a module's declared inputs by walking the AST for `os.environ` subscripts and `.get` calls, so a `self.env` indirection would hide GITHUB_REPOSITORY, GH_TOKEN and DETECT_BUMP_MAX_COMMITS from the one gate whose job is to notice
    undeclared inputs. Nothing needed the seam: the differential drives both sides through a real process environment, which is what the twin reads too.
    """

    class _FallbackPatchError(Exception):
        pass

    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose

    def verbose_log(self, message: str) -> None:
        if self.verbose:
            log.info("%s %s" % (PREFIX, message))

    def fallback_patch(self, reason: str) -> typing.NoReturn:
        if self.verbose:
            log.warn("%s Falling back to patch: %s" % (PREFIX, reason))
        raise self._FallbackPatchError

    def commit_range(self) -> tuple[list[str], str]:
        """The twin's tag selection, and its two different answers.

        A usable tag: scan `<tag>..HEAD`, and an EMPTY range means nothing new since the last release, which is `patch` rather than "look further". No usable tag: HEAD ALONE, never a blind window of history, because `initialize.sh` calls this BEFORE its own `git fetch --tags` and an unbounded `git log -n 50` would re-read PRs a previous release already consumed.
        """
        max_commits = os.environ.get("DETECT_BUMP_MAX_COMMITS") or DEFAULT_MAX_COMMITS
        tags = _git(["tag", "-l", "v*", "--sort=-v:refname"])
        lines = tags.stdout.split("\n") if tags.returncode == 0 else []
        latest_tag = lines[0] if lines else ""

        if latest_tag and _git(["merge-base", "--is-ancestor", latest_tag, "HEAD"]).returncode == 0:
            proc = _git(["log", "--format=%H", "-n", max_commits, "%s..HEAD" % latest_tag])
            if proc.returncode != 0:
                self.fallback_patch("git log %s..HEAD failed" % latest_tag)
            commits = proc.stdout.rstrip("\n")
            range_desc = "%s..HEAD" % latest_tag
            if not commits:
                self.fallback_patch("no commits between %s and HEAD" % latest_tag)
        else:
            proc = _git(["rev-parse", "HEAD"])
            if proc.returncode != 0:
                self.fallback_patch("cannot resolve HEAD")
            commits = proc.stdout.rstrip("\n")
            range_desc = "HEAD alone (no usable version tag in this checkout)"

        return commits.split("\n"), range_desc

    def scan(self, commits: list[str], range_desc: str) -> str:
        """Commit -> PRs -> labels, one API call per commit.

        The labels ride along in the same response, so this is one call per
        commit rather than one per commit plus one per PR, and `merged_at !=
        null` is load-bearing: an OPEN PR can also contain the commit, and an unmerged PR's label describes a release that has not happened.
        """
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        found_major = False
        found_minor = False
        seen_prs = ""
        api_ok = False

        for sha in commits:
            if not sha:
                continue
            proc = subprocess.run(
                ["gh", "api", pulls_path(repo, sha), "--jq", PULLS_JQ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            rows = proc.stdout.rstrip("\n")
            if proc.returncode != 0:
                self.verbose_log("commits/%s/pulls failed, skipping. Error: %s" % (sha[:7], rows))
                continue
            api_ok = True
            for row in rows.split("\n"):
                if not row:
                    continue
                pr_num, labels = split_row(row)
                if seen(seen_prs, pr_num):
                    continue
                seen_prs = seen_prs + " " + pr_num
                self.verbose_log("PR #%s labels: %s" % (pr_num, labels or "<none>"))
                if has_label(labels, MAJOR_LABEL):
                    found_major = True
                    self.verbose_log("Found %s label on PR #%s" % (MAJOR_LABEL, pr_num))
                elif has_label(labels, MINOR_LABEL):
                    found_minor = True
                    self.verbose_log("Found %s label on PR #%s" % (MINOR_LABEL, pr_num))
            if found_major:
                self.verbose_log("major is the highest priority; short-circuiting the scan")
                break

        if not seen_prs:
            if api_ok:
                self.verbose_log("no merged PRs found in %s" % range_desc)
            else:
                # EVERY lookup failed, so nothing was checked. Reported as a fallback rather than folded into a clean `patch`.
                self.fallback_patch("every commits/<sha>/pulls lookup failed")

        if found_major:
            return "major"
        if found_minor:
            return "minor"
        return "patch"

    def run(self) -> str:
        """The verdict, as the single word the twin echoes."""
        try:
            if not os.environ.get("GITHUB_REPOSITORY"):
                self.fallback_patch("GITHUB_REPOSITORY not set")
            if not os.environ.get("GH_TOKEN"):
                self.fallback_patch("GH_TOKEN not set")
            if shutil.which("gh") is None:
                self.fallback_patch("gh CLI not available")

            commits, range_desc = self.commit_range()
            nonempty = len([c for c in commits if c])
            self.verbose_log("Scanning %d commit(s) in %s" % (nonempty, range_desc))
            return self.scan(commits, range_desc)
        except self._FallbackPatchError:
            return "patch"


def main(argv: list[str]) -> int:
    # The twin's `for arg in "$@"` recognises `--verbose` and silently ignores everything else, including an unknown flag. Reproduced: refusing here would turn a typo into a failed release step.
    verbose = "--verbose" in argv
    print(Detector(verbose).run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
