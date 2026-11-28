#!/usr/bin/env python3
"""Blanks the named BWS_ variables for every later step of the job, by appending `NAME=` to GITHUB_ENV.

Usage (from action.yml, env NAMES set): python3 "$BWS_SCRUB"
Environment: NAMES (one BWS_[A-Z0-9_]+ per line), GITHUB_ENV.

It sits beside the action because callers sparse-check-out only `.github/actions` (and `.ci/config`), so `.ci/rediacc_ci` is not guaranteed to exist. Standard library only.

A malformed line or an empty list fails with an `::error::` annotation and exit 1; a scrub that blanks nothing is a wiring mistake.
"""

import os
import re
import sys

NAME_RE = re.compile(r"BWS_[A-Z0-9_]+")


def parse(text: str) -> tuple[list[str], str | None]:
    """`(names, bad_line)`: the names in order, and the first malformed line if any."""
    names: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not NAME_RE.fullmatch(line):
            return names, line
        names.append(line)
    return names, None


def main() -> int:
    names, bad = parse(os.environ.get("NAMES", ""))
    if bad is not None:
        print("::error::bws-scrub: malformed name '%s' (want one BWS_[A-Z0-9_]+ per line)" % bad)
        return 1
    if not names:
        print("::error::bws-scrub: no names given; a scrub that blanks nothing is a wiring mistake")
        return 1
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as out:
        out.write("".join("%s=\n" % name for name in names))
    print(
        "bws-scrub: blanked %d variable(s) for the rest of the job: %s"
        % (len(names), " ".join(names))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
