#!/usr/bin/env python3
"""The sanctioned-command registry: ad-hoc shape -> the tool that replaces it.

WHY A TABLE AND NOT ANOTHER GUARD. This repo already carries 21 separate
pre-bash `block-*.sh` scripts, each with its own regex and its own hand-written
message. That is the same many-copies shape that caused the bug this registry
exists to end: on 2026-08-25 the CI-watch recipe was found in NINE places, two
of them printing advice their own neighbouring prose contradicted. Adding a
class here is a ROW, not a new script, so there is one place to be right.

Each row is a work order, not a ban:
    name      short slug, used in messages and by the gate
    pattern   the ad-hoc shape, as a regex over the command TEXT
    example   a command that MUST match `pattern` -- the gate re-runs this, so a
              row whose pattern has rotted cannot keep reading as an active rule
    counter   a legitimately DIFFERENT command that must NOT match, pinning the
              boundary; without it an over-broad pattern reads as a working one.
              It must be a command, not prose: prose that merely names a banned
              shape DOES match, on purpose (see the note below), so using a
              rejection sentence as the counter would assert the opposite of the
              ruling this registry is built on.
    use       the exact replacement to print
    why       the evidence, in one line, so the message argues rather than asserts

READS COMMAND TEXT, DELIBERATELY. Prose that merely DESCRIBES a banned shape is
matched too. That false positive was put to the operator on 2026-08-25 with four
scored options and the ruling was to keep it: this failure is loud (a blocked
command naming its replacement) while every narrowing that would admit the doc
edit fails silently. Worklist #6a2c9652. The workaround is to write the file with
the Write tool and pass it by path.
"""

import re

CI_TRACE = ".ci/scripts/ci/ci-trace.py"

REGISTRY = [
    {
        "name": "gh-run-watch",
        "pattern": r"gh\s+run\s+watch\b",
        "example": "gh run watch 123 --exit-status --interval 100",
        "counter": "gh run view 123 --json conclusion,jobs",
        "use": "%s --wait" % CI_TRACE,
        "why": (
            "gh run watch dropped 4 times out of 4 in one campaign and has been seen "
            "exiting 1 while the run was still in progress"
        ),
    },
    {
        "name": "hand-rolled-ci-poll",
        "pattern": r"(?:until|while)[^\n]{0,120}gh\s+(?:run|api)[^\n]{0,120}status",
        "example": 'until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do',
        "counter": "%s --wait" % CI_TRACE,
        "use": "%s --wait" % CI_TRACE,
        "why": (
            "a hand-rolled loop reported a SUPERSEDED attempt's verdict as final "
            "(watchdog rerun bumped run_attempt) and another reported on a run a "
            "later push had already cancelled; ci-trace keys on the PR head, never "
            "a run id, so neither is expressible"
        ),
    },
    {
        "name": "gh-pr-edit-body",
        "pattern": r"gh\s+pr\s+edit\b[^\n]*--body",
        "example": 'gh pr edit 574 --body "new text"',
        "counter": "gh api repos/o/r/pulls/574 -X PATCH -F body=@body.md",
        "use": "gh api repos/<owner>/<repo>/pulls/<n> -X PATCH -F body=@<file>",
        "why": (
            "measured 2026-08-25 against PR #574: it exits 1 with "
            "'GraphQL: Projects (classic) is being deprecated ... "
            "(repository.pullRequest.projectCards)' and the body is UNCHANGED. This "
            "repo's docs called it a SILENT failure for months; it is not silent, it "
            "is loud and ignored, which matters because you debug the two differently "
            "-- read stderr rather than hunting a no-op. The gh api PATCH form works."
        ),
    },
]


def compiled():
    return [(row, re.compile(row["pattern"], re.IGNORECASE)) for row in REGISTRY]


def match(command):
    """The first row whose ad-hoc shape appears in `command`, or None."""
    for row, rx in compiled():
        if rx.search(command or ""):
            return row
    return None


def message(row):
    return (
        "BLOCKED (%s): use the sanctioned command instead.\n"
        "  use:  %s\n"
        "  why:  %s\n"
        "If you are EDITING documentation that describes this shape rather than "
        "running it, write the file with the Write tool and pass it by path."
        % (row["name"], row["use"], row["why"])
    )
