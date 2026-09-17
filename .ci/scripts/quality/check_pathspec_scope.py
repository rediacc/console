#!/usr/bin/env python3
"""check:ci-pathspec-scope -- a `git ls-files` pathspec must not use `**/`.

---- gate ---- step: Pathspec scope needs: none why: a count floor cannot tell the two spellings apart, so only a shape check sees it ---- end gate ----

THE DEFECT, measured 2026-09-06. Two gates enumerated their corpus with `git ls-files '.ci/**/*.sh'`. Git's DEFAULT pathspec matching is wildmatch WITHOUT `WM_PATHNAME`, so `*` already crosses `/`. That makes `.ci/*.sh` reach every depth,
while `.ci/**/*.sh` demands a literal slash after `.ci/` and therefore silently skips
every script sitting directly under `.ci/`. `.ci/bootstrap.sh` was the first file in the repo to occupy that class, so nothing had exposed it before.

WHY A COUNT FLOOR CANNOT CATCH THIS, which is the whole reason this gate exists. Both spellings return 453 tracked files today. They differ only on the files one of them cannot see, so an anti-vacuity floor on the corpus SIZE reads clean under either. The scanner skips files and still reports success, which is the exact failure this repo's gates are built to refuse. Only a check on
the pathspec SHAPE can see it.

`:(glob)` MAGIC IS THE ONE LEGITIMATE USE. Prefixing a pathspec with `:(glob)` turns on WM_PATHNAME, under which `**` means what people expect and `*` stops crossing `/`. A
pathspec that opts in that way is correct and is left alone; the bug is `**` under the
DEFAULT semantics, where it is not a wildcard for depth but a demand for a slash.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# A ls-files (or ls-tree/diff) invocation and the quoted pathspecs on its line.
_LSFILES = re.compile(r"\bgit\b[^\n|;&]*\bls-(?:files|tree)\b([^\n|;&]*)")
_QUOTED = re.compile(r"""(['"])(.+?)\1""")

# Floors. Measured today: 15 call sites across 12 files. Set well below so real churn does not trip them, and above zero so a collapsed enumeration cannot read as clean.
MIN_FILES = 200
MIN_CALL_SITES = 5


# THIS FILE EXEMPTS ITSELF, and the exemption is narrow and stated rather than quiet. The gate has to SPELL the broken pattern to explain it and to test for it, so its docstring and its selftest fixtures are full of exactly what it refuses. Stripping `#` comments is not enough, because a module docstring is a string and its lines do not start with `#`. The precedent is
# check-toolchain-pins.sh, whose A1 strips comments
# for the same reason and says so: prose ABOUT a defect is not an instance of it.
# What keeps this honest is that the selftest exercises the matcher on synthetic lines, so a matcher broken into silence fails there even though the real scan skips this file.
SELF = "/".join(Path(__file__).resolve().parts[-4:])


def offenders(root: Path, files: list[str]) -> list[str]:
    """Every `<pathspec>` containing `**/` that has not opted into :(glob)."""
    out = []
    for rel in files:
        if rel == SELF:
            continue
        p = root / rel
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # prose ABOUT a pathspec is not a pathspec
            for call in _LSFILES.finditer(line):
                for m in _QUOTED.finditer(call.group(1)):
                    spec = m.group(2)
                    if "**/" in spec and not spec.startswith(":("):
                        out.append(f"{rel}:{lineno}: {spec}")
    return sorted(out)


def call_sites(root: Path, files: list[str]) -> int:
    n = 0
    for rel in files:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n += len(_LSFILES.findall(text))
    return n


def selftest() -> int:
    cases = [
        ("a bare ** pathspec is an offender", offenders_in("git ls-files '.ci/**/*.sh'"), 1),
        ("the correct spelling is not", offenders_in("git ls-files '.ci/*.sh'"), 0),
        (
            "CONTROL: :(glob) magic opts in and is left alone",
            offenders_in("git ls-files ':(glob).ci/**/*.sh'"),
            0,
        ),
        ("a comment about the shape is not a use", offenders_in("# git ls-files '.ci/**/*.sh'"), 0),
        (
            "several pathspecs on one line are all seen",
            offenders_in("git ls-files 'a/**/*.sh' 'b/**/*.ts'"),
            2,
        ),
        (
            "an unrelated git call is ignored",
            offenders_in("git log --format=%H -- '.ci/**/*.sh'"),
            0,
        ),
    ]
    bad = [name for name, got, want in cases if got != want]
    for name, got, want in cases:
        print(f"  {'ok  ' if got == want else 'FAIL'} {name} (found {got}, want {want})")
    if bad:
        print(f"\N{MULTIPLICATION X} selftest: {len(bad)} control(s) failed", file=sys.stderr)
        return 1
    print(f"\N{CHECK MARK} selftest: {len(cases)} controls passed")
    return 0


def offenders_in(line: str) -> int:
    """Count offenders in one synthetic line, for the controls."""
    n = 0
    if line.lstrip().startswith("#"):
        return 0
    for call in _LSFILES.finditer(line):
        for m in _QUOTED.finditer(call.group(1)):
            spec = m.group(2)
            if "**/" in spec and not spec.startswith(":("):
                n += 1
    return n


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if selftest() != 0:
        print(
            "\N{MULTIPLICATION X} instrument control failed; the verdict below would be meaningless",
            file=sys.stderr,
        )
        return 1

    files = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "*.sh", "*.py", "*.ts", "*.cjs", "*.mjs"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    if len(files) < MIN_FILES:
        print(
            f"\N{MULTIPLICATION X} VACUOUS: enumerated {len(files)} file(s), floor {MIN_FILES}",
            file=sys.stderr,
        )
        return 1
    sites = call_sites(ROOT, files)
    if sites < MIN_CALL_SITES:
        print(
            f"\N{MULTIPLICATION X} VACUOUS: found {sites} git ls-files call site(s), floor {MIN_CALL_SITES}. "
            "The matcher stopped matching, so a clean result means nothing.",
            file=sys.stderr,
        )
        return 1

    bad = offenders(ROOT, files)
    if bad:
        print(
            f"\N{MULTIPLICATION X} {len(bad)} pathspec(s) use `**/` under git's DEFAULT matching:",
            file=sys.stderr,
        )
        for b in bad:
            print(f"     {b}", file=sys.stderr)
        print(
            "\n  Under the default (non-:(glob)) semantics `*` already crosses `/`, so `**/`\n"
            "  does not widen the match, it DEMANDS a slash and silently skips everything\n"
            "  directly under the prefix. Drop the `**/` (`a/**/*.sh` becomes `a/*.sh`), or\n"
            "  prefix the whole pathspec with `:(glob)` if you truly want pathname semantics.",
            file=sys.stderr,
        )
        return 1

    print(
        f"\N{CHECK MARK} pathspec scope: {sites} git ls-files call site(s) across {len(files)} file(s), none using `**/`."
    )
    print(
        "  Blind spot, stated so a green is not read as more than it is: this gate skips its"
        " OWN source, which must spell the broken pattern in order to document and test it."
        " The selftest is what proves the matcher still fires."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
