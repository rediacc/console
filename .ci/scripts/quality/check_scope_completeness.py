#!/usr/bin/env python3
"""The trees the quality gates read must actually be present before they report.

WHY THIS EXISTS. On 2026-08-07 a newly written gate was found scanning one
repository out of three and reporting green. `actions/checkout` defaults to
`submodules: false`, so in a job that does not ask for them the submodules are
EMPTY DIRECTORIES -- and a gate that walks them finds nothing, has nothing to
complain about, and passes.

That gate was fixed to refuse a partial scan. Then the obvious question was
whether it was alone, and it was not. Measured the same day by moving
`private/account` aside and re-running the real gates:

    check:ci-lockfile             rc=0
    check:ci-subscription-schema  rc=0
    check:ci-lint-scope-coverage  rc=0

Three green verdicts about a submodule that was not on disk. A dozen gates
reach into `private/`, so fixing each one individually is both a large change
and a permanent tax on every gate written afterwards.

The existing anti-vacuity battery does NOT cover this. It proves each gate
rejects an EMPTY tree, which is a different failure: empty input is loud
because everything disappears at once. A PARTIAL tree is quiet, because what
remains still looks like a healthy subject.

WHAT IT DOES. One precondition, checked once, before the lane's verdicts mean
anything: every submodule this repo declares must be present and non-empty. It
converts "twelve gates quietly examine less" into a single loud failure that
names what is missing.

WHAT IT DOES NOT DO. It does not verify each gate's own scope logic -- that
stays each gate's job, and `check_secret_reachability.py` is the model, refusing
a verdict when a repo it knows about is unscannable. This is the floor beneath
them, not a replacement for them.
"""

import argparse
import pathlib
import re
import sys

# A checked-out submodule always has this much. A directory that exists but
# holds only these is an uninitialised placeholder, which is exactly the state
# `submodules: false` leaves behind.
MIN_ENTRIES = 2

# Vacuity floor: this repo declares several submodules. Finding none means
# .gitmodules moved or the parse broke, and every check below would be over an
# empty set -- indistinguishable from full coverage.
MIN_SUBMODULES = 2


def declared(root):
    """Every submodule path declared in .gitmodules."""
    gm = root / ".gitmodules"
    if not gm.is_file():
        return []
    return re.findall(r"^\s*path\s*=\s*(.+?)\s*$", gm.read_text(encoding="utf-8"), re.M)


def verdicts(root, paths):
    """Every complaint. Pure, so the controls can drive it directly."""
    out = []
    for rel in sorted(paths):
        p = root / rel
        if not p.is_dir():
            out.append(
                f"{rel} is DECLARED in .gitmodules but is not on disk. Any gate that reads it "
                f"is examining nothing there and will report success about a tree it never saw."
            )
            continue
        entries = [e for e in p.iterdir() if e.name != ".git"]
        if len(entries) < MIN_ENTRIES:
            out.append(
                f"{rel} exists but holds {len(entries)} entr(y/ies), so it is an uninitialised "
                f"placeholder rather than a checkout. This is the state `submodules: false` "
                f"leaves behind, and it is the quiet one: gates find nothing and pass."
            )
    return out


def controls(root, real_paths):
    """Prove the detector fires in BOTH directions before any real read."""
    if not verdicts(root, ["private/__a_submodule_that_is_not_here__"]):
        return "planted an absent submodule path and the detector stayed silent"
    if verdicts(root, real_paths):
        return "the real, present submodules were reported as missing"
    return None


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    root = pathlib.Path(__file__).resolve().parents[3]

    paths = declared(root)
    if len(paths) < MIN_SUBMODULES:
        print(
            f"VACUOUS INPUT: .gitmodules declares {len(paths)} submodule(s), expected at least "
            f"{MIN_SUBMODULES}. A completeness check over an empty declaration set exits 0 and "
            f"reads exactly like full coverage.",
            file=sys.stderr,
        )
        return 1

    present = [p for p in paths if (root / p).is_dir() and len(list((root / p).iterdir())) > 1]
    broken = controls(root, present)
    if broken:
        print(
            f"CONTROL FAILED, so nothing below is meaningful: {broken}.\n"
            "  Refusing a verdict, because the defect this gate exists for is a check that\n"
            "  reported success while examining nothing.",
            file=sys.stderr,
        )
        return 1

    problems = verdicts(root, paths)
    if problems:
        print(
            "Quality gates would run against an incomplete tree:", file=sys.stderr
        )
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(
            "\n  Measured 2026-08-07 with private/account moved aside: check:ci-lockfile,\n"
            "  check:ci-subscription-schema and check:ci-lint-scope-coverage all returned 0.\n"
            "  Three green verdicts about a submodule that was not on disk.\n"
            "  Fix the CHECKOUT (`submodules: true`), never this gate.",
            file=sys.stderr,
        )
        return 1

    print(
        f"all {len(paths)} declared submodule(s) are present and populated "
        f"(controls fired in both directions)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
