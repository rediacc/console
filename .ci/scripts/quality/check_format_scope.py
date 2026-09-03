#!/usr/bin/env python3
"""check:ci-format-scope -- a formatter command may not narrow its own config's scope.

WHY THIS EXISTS, measured 2026-09-03. `check:format` ran
`biome format packages/ private/account/` while biome.json's `files.includes` also
covers `scripts/`, `.ci/`, `workers/`, `eslint-rules/` and `.github/actions/`. The gate
inspected a fraction of its own configured scope, so 35 files had drifted where nothing
was looking -- and that blind spot is how a prettier run (not this repo's formatter, and
nothing said so) put a 424-line quote-churn diff into the tree with every gate green.

It is the same shape as the defect check_lint_scope_coverage.py was written for -- a
narrowed path list making files invisible to a rule -- one tool over. That gate asserts
FILES reach a linter; this asserts the COMMAND does not shrink what the config declares.
Neither implies the other: a file can be lintable and unformatted.

THE ORACLE IS THE TOOL'S OWN COUNT, not a reimplementation of biome's glob semantics. A
gate that re-derives `files.includes` by hand would be a second, subtly different matcher
-- exactly the trap check_syncpack_sources.py records, where fnmatch's `*` crossed `/`
and reported files as covered that the real tool never reads. So: run biome with the
command's own arguments, run it with `.`, and compare the counts it reports. If the
declared command sees fewer files than the config would, it narrows.

WHAT THIS DOES NOT COVER, stated rather than implied: shfmt and ruff take explicit paths
with no config-declared corpus to compare against, so there is no equivalent oracle for
them and this gate does not pretend to one. Their scope is gated where it can be --
check:ci-shell-lint and check:ci-python-lint enumerate from git rather than from a path
list.

Exit 1 on a narrowing command, 2 on a failed control.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("FORMAT_SCOPE_ROOT") or Path(__file__).resolve().parents[3])
# A floor: biome reporting zero files means the instrument is broken, not the tree clean.
MIN_FILES = 200
COUNT_RE = re.compile(r"Checked (\d+) files?")


def biome_count(args: list[str], root: Path = ROOT) -> int | None:
    """How many files biome would format for these args, from its own report."""
    exe = root / "node_modules" / ".bin" / "biome"
    if not exe.is_file():
        return None
    try:
        r = subprocess.run(
            [str(exe), "format", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = COUNT_RE.search(r.stdout + r.stderr)
    return int(m.group(1)) if m else None


def declared_args(root: Path = ROOT) -> list[str] | None:
    """The path arguments `check:format` passes to biome, or None if unparseable."""
    try:
        cmd = json.loads((root / "package.json").read_text(encoding="utf-8"))["scripts"][
            "check:format"
        ]
    except (OSError, ValueError, KeyError):
        return None
    toks = cmd.split()
    if toks[:2] != ["biome", "format"]:
        return None
    return [t for t in toks[2:] if not t.startswith("-")]


def selftest() -> int:
    bad = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal bad
        print(
            "  %s  %s%s"
            % ("PASS" if ok else "FAIL", name, "\n        " + detail if (detail and not ok) else "")
        )
        if not ok:
            bad += 1

    check(
        "the declared command parses to path args",
        declared_args() is not None,
        str(declared_args()),
    )
    full = biome_count(["."])
    check(
        "biome reports a count for the whole config scope",
        full is not None and full >= MIN_FILES,
        str(full),
    )
    if full is None:
        print("  (biome unavailable; the verdict below would be vacuous)", file=sys.stderr)
        return bad
    # THE PLANTED DEFECT: the exact pre-2026-09-03 command must be caught.
    narrowed = biome_count(["packages/", "private/account/"])
    check(
        "PLANT: the narrowed command this gate exists for sees FEWER files than the config",
        narrowed is not None and narrowed < full,
        "narrowed=%s full=%s" % (narrowed, full),
    )
    # CONTROL ON THE PLANT: `.` compared with itself must not look like a narrowing,
    # or every verdict below is an artefact of the comparison rather than of the args.
    check("CONTROL: the full scope does not narrow itself", biome_count(["."]) == full)
    return bad


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        n = selftest()
        print("%s format-scope selftest: %d failure(s)" % ("✓" if n == 0 else "✗", n))
        return 1 if n else 0
    print("format scope: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    args = declared_args()
    if args is None:
        print(
            "✗ check:format is not a plain `biome format <paths>` command any more, so this\n"
            "  gate cannot compare its scope. Either restore that shape or teach this gate\n"
            "  the new one -- do not leave the comparison silently skipped.",
            file=sys.stderr,
        )
        return 1
    full = biome_count(["."])
    mine = biome_count(args or ["."])
    if full is None or mine is None:
        print(
            "✗ CANNOT VERIFY: biome did not report a file count. Run `npm ci` first.",
            file=sys.stderr,
        )
        return 1
    if full < MIN_FILES:
        print(
            f"VACUOUS: biome reports {full} file(s) for the whole config, floor {MIN_FILES}.",
            file=sys.stderr,
        )
        return 1
    if mine < full:
        print(
            f"✗ check:format formats {mine} file(s) but biome.json's scope is {full}.\n"
            f"  Its arguments {args} narrow the config, so {full - mine} tracked file(s) are\n"
            f"  formatted by nothing and drift where no gate looks. That is how a 424-line\n"
            f"  quote-churn diff reached this tree with every gate green.\n"
            f"  Fix: make check:format `biome format .` and let biome.json own the scope.",
            file=sys.stderr,
        )
        return 1
    print(
        f"✓ format scope: check:format covers all {full} file(s) biome.json declares (args: {args or ['.']})"
    )
    print("  Blind spot: this compares COUNTS from biome's own report. It does not check")
    print("  shfmt or ruff, which take explicit paths with no config-declared corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
