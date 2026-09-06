"""Age-based rot detection for suppression entries.

PORTED FROM `.ci/scripts/lib/age-check.sh`, which still exists and now
delegates here. The bash file's own header, preserved:

    Every allowlist / blocklist entry carries an implicit re-review cadence:
      - <= AGE_WARN_DAYS:  silently accepted
      - >  AGE_WARN_DAYS:  warn (reminder to re-evaluate)
      - >  AGE_FAIL_DAYS:  fail (the suppression has outlived any reasonable
                           staleness window; either refresh the BLOCKER with a
                           new date-stamped comment or take the fix)

    Uses git log to determine when a line was added.

--------------------------------------------------------------------------
WHY THIS REFUSES RATHER THAN GUESSING, measured 2026-09-03
--------------------------------------------------------------------------
`git log --diff-filter=A` on a TRUNCATED history attributes every line present
at the graft boundary to the boundary commit, so an old suppression reports as
new. The same real entry, github.com/docker/docker in
.go-deps-upgrade-blocklist:

    full clone       195 days  (added 2026-02-20)
    truncated clone    2 days  (added 2026-09-01)

AGE_WARN_DAYS is 180, so on the truncated clone that entry silently stops
warning, and at AGE_FAIL_DAYS=365 it could never fail. A liveness gate whose
whole job is expiring stale suppressions then expires nothing and says so in
green. Sibling of the same defect in check-plan-housekeeping.sh, found by
sweeping for it after that one landed.

So `entry_age_days` returns CANNOT_VERIFY (-1), and `verdict` turns that into a
refusal in CI and a warning locally -- never into "fresh".

--------------------------------------------------------------------------
WHY THE GRAFT LIST AND NOT `--is-shallow-repository`
--------------------------------------------------------------------------
`git rev-parse --is-shallow-repository` is deliberately not the test: it
answers on the EXISTENCE of .git/shallow, and `git fetch --unshallow` against a
partial clone leaves that file behind EMPTY. What corrupts an age is a GRAFT,
so the graft list is what gets asked, and it counts only when it is non-empty.
(Same reasoning, same words, as check-plan-housekeeping.sh -- and if one of
them is ever wrong, both are.)

--------------------------------------------------------------------------
WHY THE PORT KEEPS emit_advisory IN BASH
--------------------------------------------------------------------------
The decision and the emission are split here, and that split is the design.
`emit_advisory` is a separate bash library with its own contract -- eight
optional associative arrays a caller may populate by advisory id, and a
`::error::` / `::warning::` GitHub-Actions form -- and porting it was not this
phase's job. So this module answers WHAT the verdict is and the shim performs
it. The two callers that matter (`.ci/scripts/security/audit.sh` and
`.ci/scripts/quality/check-go-deps.sh`) keep populating those arrays exactly as
they do today, and neither one changes.

That also keeps the CI-versus-local branch honest: the level is decided here
from the CI flag the shim passes in, so the verdict is testable without a
GitHub runner, while the WORDING of the emission stays where the other
advisories are worded.

--------------------------------------------------------------------------
COMMAND-LINE ENTRY POINT (what the bash shim calls)
--------------------------------------------------------------------------
    python3 -m rediacc_ci.core.age days <file> <pattern>
        prints the integer age in days, or -1 for CANNOT VERIFY. Always
        exits 0: -1 is an answer, not a failure.

    python3 -m rediacc_ci.core.age grafts-file
        prints the path to a NON-EMPTY graft list, or nothing. Always exits 0.

    python3 -m rediacc_ci.core.age verdict <file> <entry> <warn> <fail> <ci>
        prints one TAB-separated line: <level>\\t<message>\\t<remedy>
        level is one of ok | warn | error, remedy may be empty, and the EXIT
        CODE is what `check_entry_age` returns: 1 only for `error`.

<ci> is the literal value of $CI, so the string "true" and nothing else
selects the CI branch -- matching `[[ "${CI:-}" == "true" ]]` in the bash.
"""

from __future__ import annotations

import pathlib
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `os` is reached only by the PathLike annotations below
    import os

from rediacc_ci import gitx

# The bash defaults. They were `readonly AGE_WARN_DAYS="${AGE_WARN_DAYS:-180}"`,
# i.e. environment-overridable, and the shim still resolves the override before
# calling in -- so the numbers live in exactly one place while the override
# keeps working for the gates' own tests.
DEFAULT_WARN_DAYS = 180
DEFAULT_FAIL_DAYS = 365

# The sentinel. Named rather than written as a bare -1 at four call sites,
# because the whole point of the 2026-09-03 finding is that this value must
# never be arithmetic'd into an age.
CANNOT_VERIFY = -1

SECONDS_PER_DAY = 86400


def grafts_file(root: os.PathLike[str] | str | None = None) -> pathlib.Path | None:
    """The path to a NON-EMPTY graft list, or None when history is complete.

    Non-empty is the whole test: see the module docstring on why
    `--is-shallow-repository` is the wrong question.
    """
    result = gitx.git(["rev-parse", "--git-path", "shallow"], root=root)
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    path = pathlib.Path(raw)
    if not path.is_absolute() and root is not None:
        path = pathlib.Path(root) / path
    try:
        if path.stat().st_size == 0:
            return None
    except OSError:
        return None
    return path


def entry_age_days(
    file: str,
    pattern: str,
    root: os.PathLike[str] | str | None = None,
    now: float | None = None,
) -> int:
    """Days since the line matching `pattern` was first introduced in `file`.

    Returns an integer, or CANNOT_VERIFY (-1). Callers must not treat -1 as an
    age.

    -1 is returned when the answer would be fiction: the pattern resolves to no
    commit at all ON A TRUNCATED HISTORY, or it resolves to a graft boundary,
    which reports the boundary's date rather than the line's.

    `pattern` is a grep-style regex passed to `git log -S`, which finds the
    commit where the pattern was added. This is more reliable than git blame
    for files where lines have been renumbered.

    `%H` alongside `%ct` so the commit can be tested against the graft list;
    `tail -1` in the bash, i.e. the OLDEST matching commit, is the last element
    here.
    """
    result = gitx.git(
        [
            "log",
            "--diff-filter=A",
            "--format=%H %ct",
            "--follow",
            "-S",
            pattern,
            "--",
            file,
        ],
        root=root,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        # No commit found. On a complete history that means the line is
        # untracked and genuinely new; on a truncated one it means the
        # introducing commit was cut away, which is not the same thing.
        return CANNOT_VERIFY if grafts_file(root) else 0

    commit_sha, _, commit_date = lines[-1].partition(" ")
    commit_date = commit_date.strip()
    if not commit_date:
        return CANNOT_VERIFY if grafts_file(root) else 0

    grafts = grafts_file(root)
    if grafts is not None:
        try:
            grafted = commit_sha in grafts.read_text().split()
        except OSError:
            grafted = False
        if grafted:
            return CANNOT_VERIFY

    now_epoch = time.time() if now is None else now
    return int((now_epoch - int(commit_date)) // SECONDS_PER_DAY)


class Verdict:
    """What `check_entry_age` should emit, and what it should return.

    A tiny object rather than a tuple because the shim reads the fields by
    name off a TAB-separated line, and a positional tuple is how those two
    orders drift apart.
    """

    __slots__ = ("level", "message", "remedy")

    def __init__(self, level: str, message: str = "", remedy: str = "") -> None:
        self.level = level
        self.message = message
        self.remedy = remedy

    @property
    def failed(self) -> bool:
        """True only for `error`. A warn returns 0, exactly as the bash did."""
        return self.level == "error"

    def as_line(self) -> str:
        return f"{self.level}\t{self.message}\t{self.remedy}"


def verdict(
    age: int,
    warn_days: int = DEFAULT_WARN_DAYS,
    fail_days: int = DEFAULT_FAIL_DAYS,
    ci: bool = False,
) -> Verdict:
    """Turn an age (or CANNOT_VERIFY) into the advisory the caller emits.

    The wording is carried over verbatim from the bash, because these strings
    are what a developer reads in a red CI job and one of them names the exact
    remedy (`fetch-depth: 0` plus `filter: blob:none`) that makes the gate
    answerable again.
    """
    if age < 0:
        # CANNOT VERIFY. In CI that is a refusal: this gate's entire purpose is
        # expiring stale suppressions, and a truncated history makes every one
        # of them look new. Locally it is a warning, because a developer's
        # shallow clone is normal and should not block their run.
        if ci:
            return Verdict(
                "error",
                "CANNOT VERIFY age: this checkout's history is truncated, so "
                "every suppression would report as new",
                "run this gate in a job whose actions/checkout carries "
                "fetch-depth: 0 and filter: blob:none",
            )
        return Verdict(
            "warn",
            "age DEFERRED: this checkout's history is truncated "
            "(git fetch --unshallow --filter=blob:none to answer it here)",
        )
    if age > fail_days:
        return Verdict(
            "error",
            f"suppression entry is {age} days old (>{fail_days}) — yearly re-review required",
            "verify the BLOCKER reason is still valid; either refresh the entry OR take the fix",
        )
    if age > warn_days:
        return Verdict(
            "warn",
            f"suppression entry is {age} days old (>{warn_days}) — due for re-review",
        )
    return Verdict("ok")


# ---------------------------------------------------------------------------
# argv dispatch -- the surface the bash shim in .ci/scripts/lib/age-check.sh calls
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 -m rediacc_ci.core.age <verb> [args]", file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]

    if verb == "days":
        # Always exit 0. -1 is an answer, and a non-zero exit here would make
        # the shim's `age=$(...)` lose it under `set -e`.
        print(entry_age_days(rest[0], rest[1]))
        return 0
    if verb == "grafts-file":
        # Prints the path or nothing, and always exits 0 -- the bash it
        # replaces was `[[ -n "$f" && -s "$f" ]] && echo "$f"; return 0`, and a
        # caller testing `[[ -n "$(_age_grafts_file)" ]]` reads the output, not
        # the status.
        path = grafts_file()
        if path is not None:
            print(path)
        return 0
    if verb == "verdict":
        file, entry = rest[0], rest[1]
        warn_days = int(rest[2]) if len(rest) > 2 and rest[2] else DEFAULT_WARN_DAYS
        fail_days = int(rest[3]) if len(rest) > 3 and rest[3] else DEFAULT_FAIL_DAYS
        ci = (rest[4] if len(rest) > 4 else "") == "true"
        v = verdict(entry_age_days(file, entry), warn_days, fail_days, ci)
        print(v.as_line())
        return 1 if v.failed else 0

    print(f"unknown verb: {verb}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
