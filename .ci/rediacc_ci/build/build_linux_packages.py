#!/usr/bin/env python3
"""Port of `.ci/scripts/build/build-linux-packages.sh`.

Builds every Linux package -- deb, rpm, apk, archlinux, each for amd64 and arm64 -- by fanning out eight invocations of `build-linux-pkg.sh`, which builds exactly ONE (format, arch) pair. Driven by `.github/workflows/cd-stage.yml:154` ("Build Linux packages") with `NEXT_VERSION`, `RELEASE_GPG_PRIVATE_KEY`, `RELEASE_GPG_PASSPHRASE` and `RELEASE_SIGNING_REQUIRED: '1'`.

WHY THE MATRIX LIVES HERE, from the twin's own header: keeping the eight invocations and the Alpine/musl substitution in one file means they are written down once instead of being duplicated per workflow.

WHY apk IS SPECIAL. apk targets Alpine, which is musl-linked. When a musl build of the binary exists it is preferred; otherwise the glibc binary is packaged as-is. That fallback is not this script's idea -- it is what the workflow block this script replaced already did -- so it is carried unchanged, including the part worth being uneasy about: a glibc binary inside an `.apk`
installs cleanly onto Alpine and fails at exec time, and nothing here says so.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT: `.ci/scripts/build/build-linux-pkg.sh`, eight times, by the same repo-root-relative path the twin uses. It is emphatically NOT reimplemented: it owns the nfpm config, the GPG signing decision, the arch-name translation and the output naming, and a Python copy of it would be a second source of truth for what a shipped `.deb` contains. It is also NOT this wave's port
target.

NOT SHELLED OUT: `mkdir -p dist/packages`, and the `${pair%%:*}` / `${pair##*:}`
splitting, which is `str.partition`.

-----------------------------------------------------------------------------
THE `set -e` QUESTION THE TWIN'S HEADER RAISES, ANSWERED BY DRIVING IT
-----------------------------------------------------------------------------
The twin's header says the workflow block ran under plain `bash -e` and that adding `-uo pipefail` "cannot change the outcome". One line makes that worth checking rather than believing:

    [[ -f "$musl_binary" ]] && binary="$musl_binary"

If errexit fired on the whole AND-list when the test fails, the documented glibc fallback would never happen -- the script would die silently on every apk build with no musl binary present, which is the ordinary case. Driven on bash 5.3.9:

    $ cat t.sh
    set -euo pipefail
    echo "before"
    [[ -f /definitely/not/here ]] && X=1
    echo "after alive"
    $ bash t.sh; echo "rc=$?"
    before
    after alive
    rc=0

It does not fire: a failing member of an AND-OR list is exempt from errexit, and bash does not re-apply errexit to the list's own status. The header's claim holds, the fallback is real, and this port implements the fallback rather than the death. The check is recorded because the opposite result would have been a release-blocking defect and the difference between the two is
invisible in review.

-----------------------------------------------------------------------------
ONE DELIBERATE, DOCUMENTED DIVERGENCE: THE `${NEXT_VERSION:?...}` DIAGNOSTIC
-----------------------------------------------------------------------------
The twin refuses with a bash parameter expansion:

    : "${NEXT_VERSION:?build-linux-packages.sh: NEXT_VERSION must be set}"

which prints `<script path>: line 36: NEXT_VERSION: build-linux-packages.sh: NEXT_VERSION must be set` and exits 1. The path and line name the SCRIPT that refused, so the faithful analogue names this file and this file's line, computed
from the live frame rather than hardcoded so it cannot go stale. The trailing
text -- including the twin's own `build-linux-packages.sh:` prefix inside the message, which is why the shipped line reads as though a filename appears twice -- is reproduced verbatim.

`:?` fires on UNSET **or EMPTY**, so `NEXT_VERSION=""` must refuse too. That is
the whole reason `os.environ.get("NEXT_VERSION", "")` is tested for truthiness instead of for presence.

This divergence is kept OUT of the shadow ledger deliberately (the two paths would fingerprint as a mismatch on the path alone, which says nothing about the port) and is pinned in the pytest differential with the `<path>: line <n>: ` prefix masked, so it is a recorded decision and not an absence.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE
-----------------------------------------------------------------------------
`os.environ.get("NEXT_VERSION", "")`, once, where it is used. No
`env = dict(os.environ)` alias: the env-manifest reader parses direct
`os.environ` reads and an alias makes the name invisible to it.

`RELEASE_GPG_PRIVATE_KEY`, `RELEASE_GPG_PASSPHRASE`, `APK_RSA_PRIVATE_KEY` and `RELEASE_SIGNING_REQUIRED` are NOT read here, exactly as the twin does not read them: they are consumed by `build-linux-pkg.sh`, and they reach it through ordinary environment inheritance. Naming them in this port would create a second place the signing contract is written down.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `Iterator` is used only in an annotation, and
    # `from __future__ import annotations` makes every annotation a string, so importing it at runtime would cost an import for nothing. ruff's TC003 says so; the block is spelled out rather than suppressed.
    from collections.abc import Iterator

# The four package formats, in the twin's order. Order is observable: the eight invocations are sequential and the first failure aborts the rest, so a run that dies in `rpm` has already produced both `deb`s.
FORMATS = ("deb", "rpm", "apk", "archlinux")

# The twin's `for pair in "dist/cli/rdc-linux-x64:amd64" ...`, split here rather than carried as colon-joined strings: the colon form exists in bash because a bash array cannot hold pairs, and reproducing that limitation in Python would be imitating the workaround instead of the behaviour.
BINARY_ARCH_PAIRS = (
    ("dist/cli/rdc-linux-x64", "amd64"),
    ("dist/cli/rdc-linux-arm64", "arm64"),
)

# `${binary/rdc-linux-/rdc-linux-musl-}` -- bash's SINGLE-substitution form, so
# only the first occurrence is replaced. `str.replace(a, b, 1)` below carries the count explicitly for the same reason.
GLIBC_INFIX = "rdc-linux-"
MUSL_INFIX = "rdc-linux-musl-"

# The one format that is musl-linked, and the sibling script every invocation goes through.
MUSL_FORMAT = "apk"
PKG_SCRIPT = ".ci/scripts/build/build-linux-pkg.sh"
OUTPUT_DIR = "dist/packages"


def console_root() -> pathlib.Path:
    """The repository root, from this file's own location.

    Same derivation and same reasoning as `build/pack_cli_npm.py`: the twin uses `get_repo_root` (`common.sh:205-210`), which has no environment override, so `rediacc_ci.paths.repo_root()` -- which honours `$REDIACC_CI_ROOT` -- is not used. A differential that let one side follow an override and not the other would diverge for a reason that has nothing to do with the port.
    """
    # This file: <root>/.ci/rediacc_ci/build/build_linux_packages.py
    return pathlib.Path(__file__).resolve().parents[3]


def binary_for(binary: str, arch_format: str) -> str:
    """Which binary this (format, binary) pair packages.

    `apk` prefers the musl build when it is present on disk and falls back to the glibc one otherwise; every other format takes the glibc binary unconditionally. Exported so the substitution and the fallback can be asserted without running a build, and so the `-f` test is visible as the ONLY thing that decides it.
    """
    if arch_format != MUSL_FORMAT:
        return binary
    musl_binary = binary.replace(GLIBC_INFIX, MUSL_INFIX, 1)
    return musl_binary if pathlib.Path(musl_binary).is_file() else binary


def invocations(version: str) -> Iterator[list[str]]:
    """The eight argv lists, in the twin's exact nesting order: format outer, (binary, arch) inner.

    A GENERATOR, NOT A LIST, and that is the one design decision in this file. The twin evaluates `[[ -f "$musl_binary" ]]` INSIDE the loop, immediately before the invocation it decides, so a `build-linux-pkg.sh` run that produced a musl binary as a side effect would change a LATER pair's decision. A list comprehension resolves all eight against the filesystem as it stood before
    the first invocation, which is a different program on exactly that input. Yielding keeps the twin's evaluation point.

    Tests may call `list(...)` on it: they set the filesystem up front, so eager resolution is the same answer there.
    """
    for fmt in FORMATS:
        for binary, arch in BINARY_ARCH_PAIRS:
            yield [
                PKG_SCRIPT,
                "--binary",
                binary_for(binary, fmt),
                "--version",
                version,
                "--arch",
                arch,
                "--format",
                fmt,
                "--output",
                OUTPUT_DIR,
            ]


def main() -> int:
    # STEP 1: refuse without a version. `:?` fires on unset OR empty; see the module docstring for why the message names this file.
    version = os.environ.get("NEXT_VERSION", "")
    if not version:
        print(
            "%s: line %d: NEXT_VERSION: build-linux-packages.sh: NEXT_VERSION must be set"
            % (__file__, sys._getframe().f_lineno),
            file=sys.stderr,
            flush=True,
        )
        return 1

    # STEP 2: every path below is repo-relative, exactly as it was in the workflow step, so the process moves to the root and stays there.
    root = console_root()
    try:
        os.chdir(root)
    except OSError as exc:
        print(
            "%s: line %d: cd: %s: %s" % (__file__, sys._getframe().f_lineno, root, exc.strerror),
            file=sys.stderr,
            flush=True,
        )
        return 1

    (root / OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # STEP 3: fan out. `set -e` means the FIRST non-zero status aborts the whole matrix and becomes the script's own status, so the loop returns rather than collecting failures -- a port that ran all eight and reported at the end would package against a binary a previous step had already failed on.
    #
    # The musl `-f` test is re-evaluated per invocation, not hoisted, because the twin evaluates it inside the loop; `invocations()` is a generator for that reason and is consumed lazily here.
    for argv in invocations(version):
        sys.stdout.flush()
        sys.stderr.flush()
        try:
            completed = subprocess.run(argv, check=False)
        except PermissionError:
            # bash's "cannot execute": the file is there and not runnable.
            return 126
        except OSError:
            # bash's "command not found", which is what a missing build-linux-pkg.sh produces. The DIAGNOSTIC differs (bash names itself and the line); the status is the one callers branch on.
            print(
                "%s: line %d: %s: No such file or directory"
                % (__file__, sys._getframe().f_lineno, argv[0]),
                file=sys.stderr,
                flush=True,
            )
            return 127
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
