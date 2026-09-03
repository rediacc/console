#!/usr/bin/env python3
"""check:ci-syncpack-sources -- no dependency-declaring manifest may sit outside the pins.

WHY THIS EXISTS, and it is a fix that had no gate. syncpack's DEFAULT `source` is
package.json's `workspaces`. `private/account` is a SUBMODULE and is not a workspace,
so every versionGroup pin in `.syncpackrc.json` silently stopped at that boundary --
including an OpenTelemetry lockstep pin whose whole purpose is to stop the packages
drifting apart. The submodule's ranges matched only because a human had set them, and
`check:version` reported no issues the entire time, because a manifest it never reads
cannot mismatch anything.

That was found by hand on 2026-09-03 and fixed by hand. This gate is what stops it
returning: `source` is now explicit, and an explicit list rots the moment somebody adds
a package.json without thinking about it.

THE RULE. Every TRACKED package.json that declares dependencies must be either matched
by a `source` glob or listed in .ci/config/syncpack-source-exclusions.json with a
substantive BLOCKER reason. A manifest with no dependencies is out of scope by
construction -- there is nothing for a pin to constrain.

WHY AN EXCLUSION LIST RATHER THAN A HEURISTIC. Several manifests genuinely should not be
covered: two are tutorial sample apps whose versions are part of the lesson text, four
are independently deployed Workers, and one is the account portal's own React tree,
which is a real convergence with a 33-dependency blast radius rather than an oversight.
The point of the list is to make that distinction VISIBLE -- an omission and a decision
look identical in a config file, and this gate is what tells them apart.

Exit 1 on any uncovered manifest or unusable reason, 2 on a failed control.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SYNCPACK_SOURCES_ROOT") or Path(__file__).resolve().parents[3])
RC = ROOT / ".syncpackrc.json"
EXCLUSIONS = ROOT / ".ci" / "config" / "syncpack-source-exclusions.json"
# Measured 2026-09-03: 17 tracked manifests, 13 of them declaring dependencies. The
# floor guards the git enumeration, not the population.
MIN_MANIFESTS = int(os.environ.get("SYNCPACK_SOURCES_MIN", "8"))
MIN_REASON_CHARS = 40


def _glob_re(g: str) -> re.Pattern[str]:
    """A glob where `*` does NOT cross a path separator and `**` does.

    NOT fnmatch, and a control caught why: fnmatch's `*` matches `/`, so
    `packages/*/package.json` "matched" `packages/json/templates/x/app/package.json`
    -- this gate would have reported a manifest as COVERED that syncpack never reads,
    which is precisely the silent over-coverage it exists to prevent. A gate whose own
    matcher is more generous than the tool it audits reports a clean tree for files
    nobody scans.
    """
    out, i = [], 0
    while i < len(g):
        if g.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif g.startswith("**", i):
            out.append(".*")
            i += 2
        elif g[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(g[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def covered(rel: str, globs: list[str]) -> bool:
    """Does any `source` glob match this path, with syncpack's segment semantics?"""
    return any(_glob_re(g).match(rel) for g in globs)


def manifests() -> list[str]:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--recurse-submodules", "*package.json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return []
    return [p for p in r.stdout.split() if p and "node_modules/" not in p]


def declares_deps(rel: str) -> bool:
    try:
        d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool((d.get("dependencies") or {}) or (d.get("devDependencies") or {}))


def selftest() -> int:
    """Control-first: the matcher is the gate, so it is proven on both answers."""
    bad = 0
    globs = ["package.json", "packages/*/package.json", "private/account/package.json"]
    cases = [
        ("package.json", True, "the root manifest is covered"),
        ("packages/cli/package.json", True, "a workspace manifest is covered"),
        ("private/account/package.json", True, "an explicitly listed submodule is covered"),
        (
            "private/account/web/package.json",
            False,
            "a DEEPER path is NOT covered by the parent glob",
        ),
        ("workers/www/package.json", False, "an unlisted tree is not covered"),
        (
            "packages/json/templates/x/app/package.json",
            False,
            "a nested template is not covered by packages/*",
        ),
    ]
    for rel, want, label in cases:
        got = covered(rel, globs)
        ok = got == want
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            bad += 1
            print(f"        covered({rel!r}) = {got}, want {want}")
    # THE CONTROL THAT MATTERS: with the pre-fix source, the submodule is NOT covered.
    # If this ever passes, the matcher has stopped distinguishing the very case the
    # gate was written for.
    if covered("private/account/package.json", ["package.json", "packages/*/package.json"]):
        print("  FAIL  CONTROL: the pre-fix source must NOT cover the submodule")
        bad += 1
    else:
        print(
            "  PASS  CONTROL: the pre-fix source does NOT cover the submodule -- the defect is detectable"
        )
    return bad


def main() -> int:
    print("syncpack sources: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    try:
        rc = json.loads(RC.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"VACUOUS INPUT: cannot read {RC.name} ({exc})", file=sys.stderr)
        return 1
    globs = rc.get("source")
    if not globs:
        print(
            "✗ .syncpackrc.json declares no explicit `source`, so syncpack falls back to\n"
            "  package.json's `workspaces` -- which silently excludes every submodule and\n"
            "  every non-workspace tree. That is the exact defect this gate exists for.\n"
            "  Fix: add a `source` array naming every manifest the pins must govern.",
            file=sys.stderr,
        )
        return 1

    try:
        excl = json.loads(EXCLUSIONS.read_text(encoding="utf-8")).get("exclusions") or {}
    except (OSError, ValueError) as exc:
        print(f"VACUOUS INPUT: cannot read {EXCLUSIONS.name} ({exc})", file=sys.stderr)
        return 1

    found = manifests()
    if len(found) < MIN_MANIFESTS:
        print(
            f"VACUOUS INPUT: git listed {len(found)} package.json file(s), floor is "
            f"{MIN_MANIFESTS}. The enumeration lost the corpus; refusing a verdict.",
            file=sys.stderr,
        )
        return 1

    problems: list[str] = []
    n_cov = n_excl = 0
    with_deps = [m for m in found if declares_deps(m)]
    for rel in sorted(with_deps):
        if covered(rel, globs):
            n_cov += 1
            continue
        reason = excl.get(rel)
        if not reason:
            problems.append(
                f"{rel} declares dependencies but is outside syncpack's `source` and is "
                f"not listed in {EXCLUSIONS.name}. No versionGroup pin can reach it, so "
                f"its versions drift with nothing reporting it -- which is how an entire "
                f"submodule sat outside the pins unnoticed. Add it to `source`, or "
                f"exclude it with a reason saying why it must stand alone."
            )
        elif not reason.startswith("BLOCKER:") or len(reason) < MIN_REASON_CHARS:
            problems.append(
                f"{rel} is excluded with a reason that is not substantive. It must start "
                f"with 'BLOCKER:' and say what makes that tree different, or the list "
                f"becomes a place to put anything inconvenient."
            )
        else:
            n_excl += 1

    problems.extend(
        f"{EXCLUSIONS.name} excludes {rel!r}, which is not a tracked manifest that "
        f"declares dependencies. Delete the entry -- an exclusion that suppresses "
        f"nothing is how a list outlives its reasons."
        for rel in sorted(set(excl) - set(with_deps))
    )

    if problems:
        print(f"✗ syncpack sources ({len(problems)} problem(s)):", file=sys.stderr)
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        return 1

    print(
        f"✓ syncpack sources: all {len(with_deps)} dependency-declaring manifest(s) "
        f"(of {len(found)} tracked, floor {MIN_MANIFESTS}) are accounted for -- "
        f"{n_cov} inside the pins, {n_excl} excluded with a stated reason"
    )
    print(
        "  Blind spot: this proves every manifest is REACHED. Whether the versions inside "
        "them agree is check:version's job, and it can only answer for what it reads."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
